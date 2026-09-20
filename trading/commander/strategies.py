"""Owner-only strategy promotion command for van-trading-core.

This is deliberately NOT an MCP capability.  The gateway reaches it only after
the owner device has passed the trading A4 challenge, and the commander still
requires the existing certificate-bound van-oa1 owner authority token.  The
ledger is written before the registry projection so a crash can never activate
an unledgered promotion; startup capsule-state replay repairs a missed file
projection from the durable event.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from fastapi import HTTPException
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from vati.authority import OwnerAuthority, OwnerAuthorityError
from vati.core.events import EventKind, make_event
from vati.core.ledger_pg import open_ledger
from vati.learning.replay import restore_capsule_state_runtime
from vati.risk.contracts import StrategyState
from vati.strategies import CapsuleRegistry
from vati.strategies.capsule import CapsuleError, PROMOTION_ORDER
from vati.validation.certificates import (
    CertificateError,
    evaluate_strategy_certificate,
    strategy_certificate_from_mapping,
)

PROMOTION_COMMANDS = (
    "capsule_promotion_candidates",
    "owner_authority_enroll",
    "capsule_promote",
)
PROMOTION_TOOL_SCHEMAS = {
    "capsule_promotion_candidates": {
        "description": (
            "Owner-app read of strategy promotion candidates derived from durable "
            "policy-passing validation certificates and current capsule lineage."
        ),
        "properties": {},
    },
    "owner_authority_enroll": {
        "description": (
            "Owner-app bootstrap of the paired device public key into the runtime "
            "trading owner-authority registry. Hidden from agents/MCP."
        ),
        "properties": {
            "device_id": {"type": "string"},
            "key_id": {"type": "string"},
            "public_key_pem": {"type": "string"},
        },
        "required": ["device_id", "key_id", "public_key_pem"],
    },
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
    owner_authority_keys_path: str = ""


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



def owner_authority_key_id(public_key_pem: str) -> str:
    """Deterministic id for the paired owner's EC P-256 public key."""
    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ValueError("owner authority public key is not valid PEM") from exc
    if not isinstance(public_key, ec.EllipticCurvePublicKey):
        raise ValueError("owner authority public key must be EC")
    if not isinstance(public_key.curve, ec.SECP256R1):
        raise ValueError("owner authority public key must use P-256")
    der = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return "device-" + hashlib.sha256(der).hexdigest()[:24]


def _write_owner_authority_registry(path: Path, key_id: str, public_key_pem: str) -> None:
    """Persist one owner public key. Replacement is a separate recovery ceremony."""
    existing: dict[str, str] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            keys = raw.get("keys", raw) if isinstance(raw, dict) else {}
            existing = {
                str(k): str(v) for k, v in dict(keys).items() if str(v).strip()
            }
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError("owner authority registry is unreadable") from exc
    others = {k: v for k, v in existing.items() if k != key_id}
    if others:
        raise PermissionError(
            "a different owner authority key is already enrolled; explicit owner-device rebind is required"
        )
    if key_id in existing and existing[key_id].strip() != public_key_pem.strip():
        raise PermissionError("owner authority key id collides with different key material")
    payload = {
        "version": 1,
        "principle": (
            "Runtime owner authority public keys only. Enrollment is performed through "
            "the paired owner-device A4 path; private keys never leave Android Keystore."
        ),
        "format": "key_id -> PEM SubjectPublicKeyInfo for an EC P-256 public key",
        "keys": {key_id: public_key_pem.strip() + "\n"},
    }
    _atomic_project(path, payload)
    os.chmod(path, 0o600)


def build_strategy_handlers(settings: StrategyPromotionSettings):
    import fcntl

    capsule_dir = Path(settings.capsule_dir)

    def candidates(_args: dict) -> dict:
        capsule_dir.mkdir(parents=True, exist_ok=True)
        lock_path = capsule_dir / ".promotion.lock"
        with lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
            ledger = open_ledger(settings.ledger)
            try:
                ok, _ = ledger.verify_chain()
                if not ok:
                    raise HTTPException(503, "VATI ledger chain verification failed")
                registry = CapsuleRegistry.load_dir(capsule_dir)
                restore_capsule_state_runtime(
                    ledger,
                    {"promotion-authority": SimpleNamespace(registry=registry)},
                )
                latest: dict[str, tuple[int, Any, dict]] = {}
                for event in ledger.iter(EventKind.STRATEGY_VALIDATION_CERTIFICATE):
                    raw = dict(event.payload)
                    try:
                        cert = strategy_certificate_from_mapping(raw)
                    except CertificateError:
                        continue
                    passed, reasons = evaluate_strategy_certificate(cert)
                    if not passed:
                        continue
                    try:
                        current = registry.get(cert.strategy_id)
                    except KeyError:
                        continue
                    if cert.capsule_hash != current.capsule_hash:
                        continue
                    if current.state not in PROMOTION_ORDER:
                        continue
                    idx = PROMOTION_ORDER.index(current.state)
                    if idx + 1 >= len(PROMOTION_ORDER):
                        continue
                    target = PROMOTION_ORDER[idx + 1]
                    row = {
                        "strategy_id": cert.strategy_id,
                        "current_state": current.state.value,
                        "target_state": target.value,
                        "capsule_hash": current.capsule_hash,
                        "validation_hash": cert.validation_hash,
                        "certificate_id": cert.certificate_id,
                        "certificate": cert.as_dict() | {
                            "validation_hash": cert.validation_hash
                        },
                        "evidence_refs": list(cert.evidence_refs),
                        "data_manifest_hash": cert.data_manifest_hash,
                        "dsr_probability": cert.stats.dsr_probability,
                        "pbo_probability": cert.stats.pbo_probability,
                        "expectancy_R": cert.expectancy_R,
                        "expectancy_lower_bound_R": cert.expectancy_lower_bound_R,
                        "profit_factor": cert.profit_factor,
                        "max_drawdown": cert.max_drawdown,
                        "certificate_event_hash": event.hash,
                        "certificate_event_ms": event.event_time_ms,
                    }
                    previous = latest.get(cert.strategy_id)
                    if previous is None or event.event_time_ms >= previous[0]:
                        latest[cert.strategy_id] = (event.event_time_ms, cert, row)
                return {
                    "candidates": [
                        item[2] for _, item in sorted(latest.items())
                    ],
                    "authority": "OWNER_DECISION_REQUIRED",
                }
            finally:
                ledger.close()
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def enroll_owner_authority(args: dict) -> dict:
        device_id = str(args.get("device_id") or "").strip()
        key_id = str(args.get("key_id") or "").strip()
        public_key_pem = str(args.get("public_key_pem") or "").strip()
        if not device_id or not key_id or not public_key_pem:
            raise HTTPException(422, "device_id, key_id and public_key_pem are required")
        try:
            derived = owner_authority_key_id(public_key_pem)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if key_id != derived:
            raise HTTPException(422, "owner authority key_id does not match public key fingerprint")
        path_raw = settings.owner_authority_keys_path.strip()
        if not path_raw:
            raise HTTPException(503, "runtime owner authority registry path is not configured")
        path = Path(path_raw)
        try:
            _write_owner_authority_registry(path, key_id, public_key_pem)
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc
        # The commander constructed the verifier before first enrollment. Refresh
        # its public-key view in-process without touching its consumed-token set.
        settings.owner_authority.keys.clear()
        settings.owner_authority.keys[key_id] = public_key_pem.strip() + "\n"
        return {
            "enrolled": True,
            "device_id": device_id,
            "key_id": key_id,
            "registry": str(path),
            "active_owner_keys": 1,
        }

    def promote(args: dict) -> dict:
        strategy_id = str(args.get("strategy_id") or "").strip()
        target_raw = str(args.get("target_state") or "").strip()
        token = str(args.get("owner_signature_ref") or "").strip()
        # approved_at_unix is presentation metadata from the gateway, not a
        # trusted clock. Promotion freshness is always evaluated against this
        # commander's current time; the gateway separately verifies its signed
        # device-action timestamp.
        _requested_approved_at = int(args.get("approved_at_unix") or 0)
        now_unix = int(time.time())
        approved_at = now_unix
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
        try:
            cert = strategy_certificate_from_mapping(cert_raw)
        except CertificateError as exc:
            raise HTTPException(422, str(exc)) from exc
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

                subject = f"{strategy_id}:{target.value}:{cert.validation_hash}"
                try:
                    verified = settings.owner_authority.verify(
                        token,
                        act="capsule-promote",
                        subject=subject,
                        now_unix=now_unix,
                        single_use=False,
                    )
                except OwnerAuthorityError as exc:
                    raise HTTPException(
                        403, f"owner-signed promotion authority required: {exc}") from exc
                if _authority_ref_already_used(ledger, verified.ref):
                    raise HTTPException(
                        409, "owner promotion authority has already been consumed")

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

    return {
        "capsule_promotion_candidates": candidates,
        "owner_authority_enroll": enroll_owner_authority,
        "capsule_promote": promote,
    }


__all__ = [
    "PROMOTION_COMMANDS",
    "PROMOTION_TOOL_SCHEMAS",
    "StrategyPromotionSettings",
    "build_strategy_handlers",
    "owner_authority_key_id",
]
