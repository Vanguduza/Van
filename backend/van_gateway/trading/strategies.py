"""Gateway-side owner strategy promotion transport.

The gateway proves current owner-device intent (device signature + A4 CryptoObject
challenge) and forwards the exact request to the private Trading Commander.  The
commander independently verifies the certificate-bound owner authority token and
owns ledger/registry mutation.  Hermes never receives this command.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def canonical_strategy_promotion(
    device_id: str,
    issued_at_unix: int,
    *,
    strategy_id: str,
    target_state: str,
    owner_signature_ref: str,
    certificate: dict,
    evidence_refs: list[str],
) -> str:
    body = {
        "strategy_id": str(strategy_id),
        "target_state": str(target_state),
        "owner_signature_ref": str(owner_signature_ref),
        "certificate": certificate,
        "evidence_refs": [str(x) for x in evidence_refs],
    }
    digest = hashlib.sha256(
        json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    return "|".join([
        "trading-strategy-promotion",
        str(device_id),
        str(int(issued_at_unix)),
        digest,
    ])


def owner_authority_key_id(public_key_pem: str) -> str:
    """Must match trading.commander.strategies.owner_authority_key_id."""
    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "paired owner public key is invalid") from exc
    if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(
        public_key.curve, ec.SECP256R1
    ):
        raise HTTPException(422, "paired owner public key must be EC P-256")
    der = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return "device-" + hashlib.sha256(der).hexdigest()[:24]


@dataclass
class StrategyPromotionGateway:
    """Forward owner-approved promotion to the private commander."""

    control: Any | None

    def candidates(self) -> dict:
        if self.control is None:
            raise HTTPException(
                503, "strategy promotion candidates require the private van-trading commander"
            )
        return self.control.run("capsule_promotion_candidates", {})

    def ensure_owner_authority(
        self, *, device_id: str, public_key_pem: str
    ) -> dict:
        if self.control is None:
            raise HTTPException(
                503, "owner authority enrollment requires the private van-trading commander"
            )
        key_id = owner_authority_key_id(public_key_pem)
        return self.control.run(
            "owner_authority_enroll",
            {
                "device_id": device_id,
                "key_id": key_id,
                "public_key_pem": public_key_pem,
            },
        )

    def promote(
        self,
        *,
        strategy_id: str,
        target_state: str,
        owner_signature_ref: str,
        certificate: dict,
        evidence_refs: list[str],
        approved_at_unix: int,
    ) -> dict:
        if self.control is None:
            raise HTTPException(
                503,
                "strategy promotion requires the private van-trading commander",
            )
        return self.control.run(
            "capsule_promote",
            {
                "strategy_id": strategy_id,
                "target_state": target_state,
                "owner_signature_ref": owner_signature_ref,
                "certificate": certificate,
                "evidence_refs": evidence_refs,
                "approved_at_unix": int(approved_at_unix),
            },
        )


__all__ = [
    "StrategyPromotionGateway",
    "canonical_strategy_promotion",
    "owner_authority_key_id",
]
