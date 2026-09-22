from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .manifest import ROOT, sha256_file

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def packaging_receipt(*, candidate: Path, stage: str, editor_version: str, rive_file_id: str, rive_revision: str, svg_sha: str, contract_sha: str, artist: str, notes: str = "") -> dict[str, Any]:
    if stage not in {"core_rig", "full_rig"}: raise ValueError("stage must be core_rig or full_rig")
    if not candidate.is_file(): raise FileNotFoundError(candidate)
    fields = {"candidate_sha256": sha256_file(candidate), "candidate_path": candidate.resolve().relative_to(ROOT.resolve()).as_posix(), "stage": stage, "rive_editor_version": editor_version, "rive_file_id": rive_file_id, "rive_revision": rive_revision, "svg_sha256": svg_sha, "contract_sha256": contract_sha, "artist": artist, "exported_at": now_iso(), "notes": notes}
    for key in ("rive_editor_version", "rive_file_id", "rive_revision", "svg_sha256", "contract_sha256", "artist"):
        if not str(fields[key]).strip(): raise ValueError(f"{key} is required")
    return fields

def token_payload(token: str) -> dict[str, Any]:
    parts = token.strip().split(".")
    if len(parts) != 3 or parts[0] != "van-oa1": raise ValueError("not a van-oa1 token")
    raw = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(raw).decode("utf-8"))

def verify_owner_token(token: str, public_key_pem: str, *, act: str, subject: str) -> dict[str, Any]:
    payload = token_payload(token)
    key_id = str(payload.get("kid") or "")
    if not key_id: raise ValueError("token has no key id")
    trading = ROOT / "trading"
    if str(trading) not in sys.path: sys.path.insert(0, str(trading))
    from vati.authority import OwnerAuthorityVerifier
    authority = OwnerAuthorityVerifier({key_id: public_key_pem}).verify(token, act=act, subject=subject, single_use=False)
    return {"act": authority.act, "subject": authority.subject, "key_id": authority.key_id, "issued_at_unix": authority.issued_at_unix, "expires_at_unix": authority.expires_at_unix, "nonce": authority.nonce}
