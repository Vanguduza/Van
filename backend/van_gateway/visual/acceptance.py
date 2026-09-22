"""Owner-accepted Character Forge artifact binding."""
from __future__ import annotations

import hashlib
import re
import sys
import time
from pathlib import Path
from typing import Any

from van_gateway.storage.db import Store

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class VisualAcceptanceError(PermissionError):
    pass


def _owner_authority_verifier():
    try:
        from vati.authority import OwnerAuthorityVerifier
    except ImportError:
        trading_dir = Path(__file__).resolve().parents[3] / "trading"
        if trading_dir.is_dir() and str(trading_dir) not in sys.path:
            sys.path.append(str(trading_dir))
        from vati.authority import OwnerAuthorityVerifier
    return OwnerAuthorityVerifier()


class VisualAcceptanceService:
    def __init__(self, store: Store, owner_authority: Any = None) -> None:
        self.store = store
        self.owner_authority = owner_authority

    def _verifier(self):
        if self.owner_authority is None:
            self.owner_authority = _owner_authority_verifier()
        return self.owner_authority

    @staticmethod
    def _sha(value: str, field: str) -> str:
        value = str(value or "").strip().lower()
        if not SHA256_RE.fullmatch(value):
            raise VisualAcceptanceError(f"{field}_must_be_sha256")
        return value

    async def record(
        self,
        *,
        token: str,
        rive_sha256: str,
        apk_sha256: str,
        device_model: str,
        android_build: str,
    ) -> dict[str, Any]:
        rive_sha = self._sha(rive_sha256, "rive_sha256")
        apk_sha = self._sha(apk_sha256, "apk_sha256")
        subject = f"sha256:{rive_sha}"
        try:
            verified = self._verifier().verify(
                token,
                act="visual-accept",
                subject=subject,
                single_use=False,
            )
        except Exception as exc:
            raise VisualAcceptanceError(str(exc)) from exc

        existing = await self.store.fetchone(
            "SELECT * FROM visual_acceptances WHERE token = ?",
            (token,),
        )
        if existing is not None:
            row = dict(existing)
            if row["rive_sha256"] != rive_sha or row["apk_sha256"] != apk_sha:
                raise VisualAcceptanceError("acceptance_token_replayed_with_different_artifact")
            return self._public(row)

        verified_at = int(time.time())
        receipt_id = "visual-acceptance:" + hashlib.sha256(token.encode("utf-8")).hexdigest()
        await self.store.execute(
            """
            INSERT INTO visual_acceptances(
              id, rive_sha256, apk_sha256, token, key_id, device_model, android_build, verified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt_id,
                rive_sha,
                apk_sha,
                token,
                verified.key_id,
                str(device_model or "")[:256],
                str(android_build or "")[:512],
                verified_at,
            ),
        )
        row = await self.store.fetchone(
            "SELECT * FROM visual_acceptances WHERE id = ?",
            (receipt_id,),
        )
        if row is None:
            raise RuntimeError("visual_acceptance_write_lost")
        return self._public(dict(row))

    async def latest(self) -> dict[str, Any] | None:
        row = await self.store.fetchone(
            "SELECT * FROM visual_acceptances ORDER BY verified_at DESC, id DESC LIMIT 1"
        )
        return None if row is None else self._public(dict(row))

    @staticmethod
    def _public(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "rive_sha256": row["rive_sha256"],
            "apk_sha256": row["apk_sha256"],
            "token": row["token"],
            "key_id": row["key_id"],
            "device_model": row["device_model"],
            "android_build": row["android_build"],
            "verified_at": row["verified_at"],
            "act": "visual-accept",
            "subject": "sha256:" + row["rive_sha256"],
            "verified": True,
        }
