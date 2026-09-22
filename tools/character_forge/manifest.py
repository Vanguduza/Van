from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Iterable
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "character_forge"
MANIFEST_PATH = DOCS / "MANIFEST.yaml"
SOURCE_ROOTS = (
    ROOT / "visual-authority" / "assets",
    ROOT / "visual-authority" / "rive_contract.json",
    ROOT / "docs" / "VAN_CHARACTER_VISUAL_IDENTITY.md",
    ROOT / "docs" / "VAN_VISUAL_ACCEPTANCE_MATRIX.md",
)

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()

def load_yaml(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}

def dump_yaml(data: dict[str, Any], path: Path = MANIFEST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    os.replace(tmp, path)

def iter_source_files() -> list[Path]:
    files: list[Path] = []
    for root in SOURCE_ROOTS:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(path for path in root.rglob("*") if path.is_file())
        else:
            raise FileNotFoundError(root)
    return sorted(set(files), key=lambda p: rel(p))

def source_records() -> list[dict[str, Any]]:
    records = []
    for path in iter_source_files():
        sha = sha256_file(path)
        records.append({"artifact_id": f"source:{sha}", "kind": "source", "path": rel(path), "sha256": sha, "stage": "admitted", "promotion": "CANDIDATE", "produced_by": "owner", "inputs": []})
    return records

def verify_records(records: Iterable[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    for record in records:
        raw_path = str(record.get("path") or "")
        if not raw_path:
            problems.append("record has no path")
            continue
        path = ROOT / raw_path
        if not path.is_file():
            problems.append(f"missing: {raw_path}")
            continue
        expected = str(record.get("sha256") or "")
        actual = sha256_file(path)
        if expected != actual:
            problems.append(f"hash mismatch: {raw_path}")
        artifact_id = str(record.get("artifact_id") or "")
        if artifact_id and not artifact_id.endswith(actual):
            problems.append(f"artifact_id/hash mismatch: {raw_path}")
    return problems

def upsert_artifact(manifest: dict[str, Any], artifact: dict[str, Any]) -> None:
    artifacts = list(manifest.get("artifacts") or [])
    key = (artifact.get("kind"), artifact.get("sha256"), artifact.get("path"))
    for index, current in enumerate(artifacts):
        if (current.get("kind"), current.get("sha256"), current.get("path")) == key:
            artifacts[index] = artifact
            break
    else:
        artifacts.append(artifact)
    manifest["artifacts"] = artifacts

def append_receipt(manifest: dict[str, Any], receipt: dict[str, Any]) -> None:
    receipts = list(manifest.get("receipts") or [])
    identity = (receipt.get("command"), tuple(receipt.get("inputs") or []), tuple(receipt.get("outputs") or []))
    if not any((r.get("command"), tuple(r.get("inputs") or []), tuple(r.get("outputs") or [])) == identity for r in receipts):
        receipts.append(receipt)
    manifest["receipts"] = receipts

def find_artifact(manifest: dict[str, Any], *, kind: str | None = None, sha256: str | None = None) -> dict[str, Any] | None:
    for artifact in manifest.get("artifacts") or []:
        if kind is not None and artifact.get("kind") != kind:
            continue
        if sha256 is not None and artifact.get("sha256") != sha256:
            continue
        return artifact
    return None
