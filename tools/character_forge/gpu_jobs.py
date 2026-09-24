from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import re

SHA = re.compile(r"^[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_see_through_job(
    *,
    source: Path,
    master_sha256: str,
    code_commit: str,
    mode: str,
    resolution: int,
    weight_hashes: dict[str, str],
) -> dict[str, Any]:
    if not SHA.fullmatch(master_sha256):
        raise ValueError("master_sha256 is invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", code_commit):
        raise ValueError("code_commit is invalid")
    if mode not in {"full_precision", "group_offload", "nf4_quantized", "trial"}:
        raise ValueError("unsupported See-through mode")
    if resolution < 1024 or resolution > 2048:
        raise ValueError("resolution outside reviewed range")
    if mode != "trial":
        if not weight_hashes:
            raise ValueError("production See-through job requires weight hashes")
        for name, value in weight_hashes.items():
            if not SHA.fullmatch(value):
                raise ValueError(f"weight hash for {name} is invalid")
    return {
        "schema_version": 1,
        "job_type": "see_through_decomposition",
        "source_path": source.as_posix(),
        "source_sha256": sha256_file(source),
        "approved_master_sha256": master_sha256,
        "tool_repository": "shitagaki-lab/see-through",
        "tool_commit": code_commit,
        "mode": mode,
        "resolution": resolution,
        "weight_hashes": dict(sorted(weight_hashes.items())),
        "output_policy": {
            "visible": "DERIVED_VISIBLE",
            "hidden_generated": "INFERRED_OCCLUSION",
            "visible_generated": "GENERATIVE_VISIBLE",
        },
    }


def canonical_job_sha256(job: dict[str, Any]) -> str:
    payload=json.dumps(job,sort_keys=True,separators=(",",":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
