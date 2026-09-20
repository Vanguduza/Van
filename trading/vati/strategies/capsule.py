"""StrategyCapsule registry (Rev 2 §21). Capsules are JSON records validated
against the schema's required set, hashed, and moved between states only by
explicit calls: promotion needs an approval signature reference (owner A4);
demotion never does."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Optional

from vati.contracts import required_keys
from vati.core.canonical import canonical_hash
from vati.validation.certificates import StrategyValidationCertificate, evaluate_strategy_certificate
from vati.risk.contracts import StrategyState
from vati.authority import OwnerAuthorityError, OwnerAuthorityVerifier

PROMOTION_ORDER = [StrategyState.RESEARCH, StrategyState.BACKTEST, StrategyState.VALIDATION, StrategyState.DEMO, StrategyState.SHADOW, StrategyState.LIMITED_LIVE, StrategyState.CERTIFIED_LIVE]
DEMOTION_TARGETS = {StrategyState.DEGRADED, StrategyState.SUSPENDED, StrategyState.RETIRED, StrategyState.SHADOW}


class CapsuleError(ValueError):
    pass


@dataclass(frozen=True)
class Capsule:
    data: dict[str, Any]

    @property
    def strategy_id(self) -> str: return self.data["strategy_id"]
    @property
    def version(self) -> str: return self.data["version"]
    @property
    def family(self) -> str: return self.data["strategy_id"].rsplit("-", 1)[0]
    @property
    def state(self) -> StrategyState: return StrategyState(self.data["state"])
    @property
    def instruments(self) -> set[str]: return set(self.data["instruments"])
    @property
    def horizons(self) -> set[str]: return set(self.data["horizons"])
    @property
    def eligible_regimes(self) -> set[str]: return set(self.data["eligible_regimes"])
    @property
    def forbidden_regimes(self) -> set[str]: return set(self.data["forbidden_regimes"])
    @property
    def event_certified(self) -> bool: return bool(self.data.get("event_certified", False))
    @property
    def synthetic_only(self) -> bool: return bool(self.data.get("synthetic_only", False))
    @property
    def granularity(self) -> str: return self.data["required_data_granularity"]
    @property
    def capsule_hash(self) -> str: return self.data["capsule_hash"]

    def body_hash(self) -> str:
        return canonical_hash({k: v for k, v in self.data.items() if k != "capsule_hash"})


class CapsuleRegistry:
    def __init__(
        self,
        capsules: Iterable[Capsule] = (),
        *,
        authority: "OwnerAuthorityVerifier | None" = None,
    ) -> None:
        self._c: dict[str, Capsule] = {}
        # P0-TRADE-001 — an empty verifier refuses every promotion, which is the right
        # default for a registry nobody handed the owner's key to.
        self.authority = authority or OwnerAuthorityVerifier()
        for c in capsules:
            self.add(c)

    @classmethod
    def load_dir(
        cls, path: str | Path, *, authority: "OwnerAuthorityVerifier | None" = None
    ) -> "CapsuleRegistry":
        reg = cls(authority=authority)
        for f in sorted(Path(path).glob("*.json")):
            reg.add(Capsule(json.loads(f.read_text(encoding="utf-8"))))
        return reg

    def add(self, c: Capsule) -> None:
        missing = required_keys("strategy_capsule") - set(c.data)
        if missing:
            raise CapsuleError(f"{c.data.get('strategy_id')}: missing {sorted(missing)}")
        if c.data["capsule_hash"] != c.body_hash():
            raise CapsuleError(f"{c.strategy_id}: capsule_hash mismatch")
        if c.granularity == "BARS" and ({"SCALP", "MICRO"} & c.horizons):
            raise CapsuleError(f"{c.strategy_id}: SCALP/MICRO cannot certify on BARS")
        if "MICRO" in c.horizons:
            raise CapsuleError(f"{c.strategy_id}: MICRO horizon removed in Rev 3")
        self._c[c.strategy_id] = c

    def get(self, strategy_id: str) -> Capsule:
        return self._c[strategy_id]

    def all(self) -> list[Capsule]:
        return sorted(self._c.values(), key=lambda c: c.strategy_id)

    @staticmethod
    def seal(data: dict[str, Any]) -> dict[str, Any]:
        d = {k: v for k, v in data.items() if k != "capsule_hash"}
        return {**d, "capsule_hash": canonical_hash(d)}

    #: TRD-ENH-021. States at or past which a semantic certificate is required.
    #: Below DEMO a capsule is research; from DEMO on it is being trusted.
    CERTIFICATE_REQUIRED_FROM = (
        StrategyState.DEMO, StrategyState.SHADOW,
        StrategyState.LIMITED_LIVE, StrategyState.CERTIFIED_LIVE,
    )

    def promote(self, strategy_id: str, to: StrategyState, *, approval_signature_ref: str, evidence_refs: list[str], approved_at_unix: int,
                certificate: "StrategyValidationCertificate | None" = None) -> Capsule:
        c = self.get(strategy_id)
        if to not in PROMOTION_ORDER:
            raise CapsuleError(f"{to.value} is not a promotion target")
        if c.state in PROMOTION_ORDER and PROMOTION_ORDER.index(to) != PROMOTION_ORDER.index(c.state) + 1:
            raise CapsuleError(f"promotion must advance one state: {c.state.value} → {to.value}")
        # P0-TRADE-001 — promoting a strategy towards live capital took any non-empty
        # string. The target state is in the subject, so authority to promote to
        # LIMITED_LIVE is not authority to promote to CERTIFIED_LIVE.
        try:
            verified = self.authority.verify(
                approval_signature_ref,
                act="capsule-promote",
                subject=f"{strategy_id}:{to.value}",
                now_unix=approved_at_unix,
            )
        except OwnerAuthorityError as exc:
            # Kept as a CapsuleError so callers keep one error type for "this promotion
            # was refused", while the message still says exactly which check failed.
            raise CapsuleError(f"promotion requires owner approval signature: {exc}") from exc
        approval_signature_ref = verified.ref
        if to in (StrategyState.LIMITED_LIVE, StrategyState.CERTIFIED_LIVE) and not evidence_refs:
            raise CapsuleError("live promotion requires evidence references")
        # TRD-ENH-021/022 — evidence_refs are opaque strings, so they prove that
        # someone signed, never what was proven. From DEMO onwards the promotion
        # carries a sealed certificate whose content is checked, and the owner's
        # signature binds that certificate's hash rather than a free-text list.
        certificate_hash = ""
        if to in self.CERTIFICATE_REQUIRED_FROM:
            if certificate is None:
                raise CapsuleError(
                    f"promotion to {to.value} requires a StrategyValidationCertificate; "
                    "opaque evidence references are not semantic evidence"
                )
            if certificate.strategy_id != strategy_id:
                raise CapsuleError(
                    f"certificate is for {certificate.strategy_id}, not {strategy_id}")
            if certificate.capsule_hash and certificate.capsule_hash != c.capsule_hash:
                raise CapsuleError(
                    "certificate was computed against a different capsule revision "
                    f"({certificate.capsule_hash[:12]} != {c.capsule_hash[:12]})")
            passed, reasons = evaluate_strategy_certificate(certificate)
            if not passed:
                raise CapsuleError("certificate does not meet validation policy: " + ",".join(reasons))
            certificate_hash = certificate.validation_hash
        new = self.seal({**c.data, "state": to.value, "approval_signature_ref": approval_signature_ref, "evidence_refs": sorted(set(c.data.get("evidence_refs", [])) | set(evidence_refs)),
                         "approved_at_unix": approved_at_unix, "supersedes": c.capsule_hash,
                         **({"validation_hash": certificate_hash} if certificate_hash else {})})
        self._c[strategy_id] = Capsule(new)
        return self._c[strategy_id]

    def demote(self, strategy_id: str, to: StrategyState, *, reason: str) -> Capsule:
        c = self.get(strategy_id)
        if to not in DEMOTION_TARGETS:
            raise CapsuleError(f"{to.value} is not a demotion target")
        new = self.seal({**c.data, "state": to.value, "demotion_reason": reason, "supersedes": c.capsule_hash})
        self._c[strategy_id] = Capsule(new)
        return self._c[strategy_id]
