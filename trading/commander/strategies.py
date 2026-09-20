"""Owner-only strategy promotion command for van-trading-core.

This is deliberately NOT an MCP capability.  The gateway reaches it only after
the owner device has passed the trading A4 challenge, and the commander still
requires the existing certificate-bound van-oa1 owner authority token.  The
ledger is written before the registry projection so a crash can never activate
an unledgered promotion; startup capsule-state replay repairs a missed file
projection from the durable event.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from fastapi import HTTPException

from vati.authority import OwnerAuthority, OwnerAuthorityError
from vati.core.events import EventKind, make_event
from vati.core.ledger_pg import open_ledger
from vati.learning.replay import restore_capsule_state_runtime
from vati.risk.contracts import StrategyState
from vati.strategies import CapsuleRegistry
from vati.strategies.capsule import CapsuleError
from vati.validation.certificates import StrategyValidationCertificate
from vati.validation.policy import ValidationStatistics

PROMOTION_COMMANDS = ("capsule_promote",)
PROMOTION_TOOL_SCHEMAS = {
    "capsule_promote": {
        "description": (
            "Owner-only strategy promotion. Hidden from agents/MCP. Requires a sealed "
            "StrategyValidationCertificate and owner authority bound to its validation hash."
        ),
        "properties": {
            "strategy_id": {"type": "string"},
            "target_state": {"type": "string"},
            "owner_signature_ref": {"type": "string"},
            "certificate": {"type": "object"},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
            "approved_at_unix": {"type": "integer"},
        },
        "required": [
            "strategy_id", "target_state", "owner_signature_ref",
            "certificate", "approved_at_unix",
        ],
    }
}


@dataclass(frozen=True)
class StrategyPromotionSettings:
    capsule_dir: str
    ledger: str
    owner_authority: Any


class _PreverifiedAuthority:
    """Allow CapsuleRegistry to consume exactly the authority already checked under lock."""

    def __init__(self, verified: OwnerAuthority, *, act: str, subject: str) -> None:
        self.verified = verified
        self.act = act
        self.subject = subject

    def verify(self, _token, *, act: str, subject: str, **_kw):
        if act != self.act or subject != self.subject:
            raise OwnerAuthorityError("preverified authority scope mismatch")
        return self.verified


def certificate_from_mapping(raw: Mapping[str, Any]) -> StrategyValidationCertificate:
    try:
        stats_raw = dict(raw["stats"])
        stats = ValidationStatistics(**stats_raw)
        cert = StrategyValidationCertificate(
            certificate_id=str(raw["certificate_id"]),
            strategy_id=str(raw["strategy_id"]),
            strategy_version=str(raw["strategy_version"]),
            capsule_hash=str(raw.get("capsule_hash") or ""),
            data_manifest_hash=str(raw["data_manifest_hash"]),
            evidence_refs=tuple(str(x) for x in raw.get("evidence_refs", ())),
            feature_set_version=str(raw["feature_set_version"]),
            cost_model_revision=str(raw["cost_model_revision"]),
            stats=stats,
            expectancy_R=float(raw["expectancy_R"]),
            expectancy_lower_bound_R=float(raw["expectancy_lower_bound_R"]),
            profit_factor=float(raw["profit_factor"]),
            max_drawdown=float(raw["max_drawdown"]),
            cost_stress_2x=str(raw.get("cost_stress_2x", "RED")),
            latency_slippage_stress=str(raw.get("latency_slippage_stress", "RED")),
            parameter_perturbation_stability=str(
                raw.get("parameter_perturbation_stability", "RED")),
            leakage_switch_result=str(raw.get("leakage_switch_result", "RED")),
            feature_certificate_refs=tuple(
                str(x) for x in raw.get("feature_certificate_refs", ())),
            regime_breakdown=dict(raw.get("regime_breakdown") or {}),
            cpcv_configuration=dict(raw.get("cpcv_configuration") or {}),
            validation_policy_version=str(raw.get(
                "validation_policy_version", stats.validation_policy_version)),
            validation_hash=str(raw.get("validation_hash") or ""),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, f"invalid strategy validation certificate: {exc}") from exc
    if not cert.verify_seal():
        raise HTTPException(422, "strategy validation certificate seal is invalid")
    return cert


def _authority_ref_already_used(ledger, ref: str) -> bool:
    for event in ledger.iter(EventKind.CAPSULE_STATE):
        if (
            event.payload.get("authority") == "OWNER_SIGNED_PROMOTION"
            and event.payload.get("owner_authority_ref") == ref
        ):
            return True
    return False


def _atomic_project(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def build_strategy_handlers(settings: StrategyPromotionSettings):
    import fcntl

    capsule_dir = Path(settings.capsule_dir)

    def promote(args: dict) -> dict:
        strategy_id = str(args.get("strategy_id") or "").strip()
        target_raw = str(args.get("target_state") or "").strip()
        token = str(args.get("owner_signature_ref") or "").strip()
        approved_at = int(args.get("approved_at_unix") or int(time.time()))
        evidence_refs = [
            str(x) for x in (args.get("evidence_refs") or ()) if str(x).strip()
        ]
        if not strategy_id or not target_raw or not token:
            raise HTTPException(
                422, "strategy_id, target_state and owner_signature_ref are required")
        try:
            target = StrategyState(target_raw)
        except ValueError as exc:
            raise HTTPException(422, f"unknown target_state {target_raw!r}") from exc
        cert_raw = args.get("certificate")
        if not isinstance(cert_raw, dict):
            raise HTTPException(422, "certificate must be an object")
        cert = certificate_from_mapping(cert_raw)
        if cert.strategy_id != strategy_id:
            raise HTTPException(
                422, f"certificate is for {cert.strategy_id}, not {strategy_id}")

        capsule_dir.mkdir(parents=True, exist_ok=True)
        lock_path = capsule_dir / ".promotion.lock"
        with lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            ledger = open_ledger(settings.ledger)
            try:
                ok, _ = ledger.verify_chain()
                if not ok:
                    raise HTTPException(503, "VATI ledger chain verification failed")

                registry = CapsuleRegistry.load_dir(capsule_dir)
                # The ledger is the capsule-state authority across a crash between
                # event commit and file projection. Reconstruct it before evaluating
                # another owner request so two valid tokens cannot fork one parent.
                restore_capsule_state_runtime(
                    ledger,
                    {"promotion-authority": SimpleNamespace(registry=registry)},
                )
                try:
                    current = registry.get(strategy_id)
                except KeyError as exc:
                    raise HTTPException(404, f"unknown strategy {strategy_id}") from exc
                if cert.capsule_hash and cert.capsule_hash != current.capsule_hash:
                    raise HTTPException(
                        409,
                        "certificate capsule hash does not match the current strategy revision",
                    )

                subject = f"{strategy_id}:{target.value}:{cert.validation_hash}"
                try:
                    verified = settings.owner_authority.verify(
                        token,
                        act="capsule-promote",
                        subject=subject,
                        now_unix=approved_at,
                        single_use=False,
                    )
                except OwnerAuthorityError as exc:
                    raise HTTPException(
                        403, f"owner-signed promotion authority required: {exc}") from exc
                if _authority_ref_already_used(ledger, verified.ref):
                    raise HTTPException(
                        409, "owner promotion authority has already been consumed")

                registry.authority = _PreverifiedAuthority(
                    verified, act="capsule-promote", subject=subject)
                try:
                    promoted = registry.promote(
                        strategy_id,
                        target,
                        approval_signature_ref=token,
                        evidence_refs=evidence_refs,
                        approved_at_unix=approved_at,
                        certificate=cert,
                    )
                except CapsuleError as exc:
                    raise HTTPException(422, str(exc)) from exc

                now_ms = approved_at * 1000
                event = make_event(
                    EventKind.CAPSULE_STATE,
                    "vati-capsule-promotion",
                    {
                        "strategy_id": strategy_id,
                        "from": current.state.value,
                        "to": promoted.state.value,
                        "capsule_hash": promoted.capsule_hash,
                        "supersedes": current.capsule_hash,
                        "capsule": promoted.data,
                        "validation_hash": cert.validation_hash,
                        "certificate_id": cert.certificate_id,
                        "evidence_refs": list(cert.evidence_refs),
                        "owner_authority_ref": verified.ref,
                        "by": "owner",
                        "authority": "OWNER_SIGNED_PROMOTION",
                    },
                    event_time_ms=now_ms,
                    received_time_ms=now_ms,
                    correlation_id=strategy_id,
                )
                chain_hash = ledger.append(event)

                projection = "WRITTEN"
                projection_error = None
                try:
                    _atomic_project(
                        capsule_dir / f"{strategy_id}.json", promoted.data)
                except OSError as exc:
                    # The ledger event is the durable authority. Startup replay can
                    # reconstruct this exact capsule even when the file projection
                    # was interrupted after the authoritative commit.
                    projection = "DEFERRED_LEDGER_AUTHORITY"
                    projection_error = str(exc)[:160]

                return {
                    "promoted": True,
                    "strategy_id": strategy_id,
                    "from": current.state.value,
                    "to": promoted.state.value,
                    "capsule_hash": promoted.capsule_hash,
                    "supersedes": current.capsule_hash,
                    "validation_hash": cert.validation_hash,
                    "owner_authority_ref": verified.ref,
                    "event_hash": event.hash,
                    "chain_hash": chain_hash,
                    "registry_projection": projection,
                    "projection_error": projection_error,
                    "requires_session_restart": True,
                }
            finally:
                ledger.close()
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    return {"capsule_promote": promote}


__all__ = [
    "PROMOTION_COMMANDS",
    "PROMOTION_TOOL_SCHEMAS",
    "StrategyPromotionSettings",
    "build_strategy_handlers",
    "certificate_from_mapping",
]
