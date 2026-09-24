from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import struct
import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "visual-authority" / "character-forge" / "00-source" / "production-v3" / "MASTER_PROVENANCE.yaml"
IDENTITY_LOCK = ROOT / "visual-authority" / "character-forge" / "00-source" / "asset-pack" / "APPROVED_IDENTITY_LOCK.yaml"
# CF-D-05-REV2_1: new master candidates are measured against Candidate B, the primary visual.
CANONICAL = ROOT / "visual-authority" / "character-forge" / "01-master-candidates" / "van_master_source_candidate_b.png"
APPROVED = ROOT / "visual-authority" / "character-forge" / "01-master-approved" / "van_master_highres.png"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"{path} is not a PNG with a valid IHDR")
    return struct.unpack(">II", header[16:24])


def _yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def stage_master(candidate: Path, *, receipt_path: Path | None = None) -> dict[str, Any]:
    candidate = candidate.resolve()
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    width, height = png_dimensions(candidate)
    policy = _yaml(POLICY)
    requirement = int(((policy.get("candidate") or {}).get("minimum_short_edge_px")) or 2048)
    if min(width, height) < requirement:
        raise ValueError(f"master candidate short edge {min(width,height)}px is below {requirement}px")
    if not CANONICAL.is_file():
        raise FileNotFoundError(CANONICAL)
    receipt = {
        "schema_version": 1,
        "status": "CANDIDATE_NOT_AUTHORITY",
        "candidate_path": _display_path(candidate),
        "candidate_sha256": sha256_file(candidate),
        "width": width,
        "height": height,
        "canonical_source_path": CANONICAL.relative_to(ROOT).as_posix(),
        "canonical_source_sha256": sha256_file(CANONICAL),
        "canonical_source_git_blob_sha": (policy.get("source_authority") or {}).get("git_blob_sha"),
        "identity_lock_sha256": sha256_file(IDENTITY_LOCK),
        "visible_identity_invention": "FORBIDDEN",
        "owner_approval_required": True,
    }
    candidate_state = policy.setdefault("candidate", {})
    candidate_state.update({
        "expected_path": _display_path(candidate),
        "sha256": receipt["candidate_sha256"],
        "status": "STAGED_OWNER_REVIEW",
        "dimensions": [width, height],
    })
    _write_yaml(POLICY, policy)
    if receipt_path:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(yaml.safe_dump(receipt, sort_keys=False), encoding="utf-8")
    return receipt


def approve_master(candidate: Path, approval: Path) -> dict[str, Any]:
    staged = stage_master(candidate)
    record = _yaml(approval)
    if record.get("decision") != "APPROVE":
        raise ValueError("owner approval decision must be APPROVE")
    if record.get("authority") != "owner":
        raise ValueError("master approval authority must be owner")
    for key, expected in (
        ("candidate_sha256", staged["candidate_sha256"]),
        ("canonical_source_git_blob_sha", staged["canonical_source_git_blob_sha"]),
        ("identity_lock_sha256", staged["identity_lock_sha256"]),
    ):
        if record.get(key) != expected:
            raise ValueError(f"master approval {key} does not bind current candidate/authority")
    APPROVED.parent.mkdir(parents=True, exist_ok=True)
    APPROVED.write_bytes(candidate.read_bytes())
    approved_sha = sha256_file(APPROVED)
    policy = _yaml(POLICY)
    policy.setdefault("candidate", {}).update({
        "sha256": staged["candidate_sha256"],
        "status": "OWNER_APPROVED_SOURCE",
        "dimensions": [staged["width"], staged["height"]],
    })
    policy.setdefault("approved_master", {}).update({
        "expected_path": _display_path(APPROVED),
        "sha256": approved_sha,
        "status": "OWNER_APPROVED",
        "approved_by": record.get("approved_by") or "owner",
        "approved_at": record.get("approved_at"),
        "approval_record": _display_path(approval),
    })
    _write_yaml(POLICY, policy)
    return {
        **staged,
        "status": "OWNER_APPROVED_MASTER",
        "approved_master_path": _display_path(APPROVED),
        "approved_master_sha256": approved_sha,
        "approval_path": _display_path(approval),
    }
