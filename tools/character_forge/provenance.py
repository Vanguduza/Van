from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import yaml

PROVENANCE_CLASSES = {
    "CANONICAL_VISIBLE",
    "DERIVED_VISIBLE",
    "INFERRED_OCCLUSION",
    "OWNER_APPROVED_OCCLUSION",
    "GENERATIVE_VISIBLE",
}
PRODUCTION_ADMISSIBLE = {
    "CANONICAL_VISIBLE",
    "DERIVED_VISIBLE",
    "OWNER_APPROVED_OCCLUSION",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ProvenanceFinding:
    code: str
    detail: str


@dataclass(frozen=True)
class ProvenanceReport:
    ok: bool
    findings: tuple[ProvenanceFinding, ...]


def classify_layer(record: dict[str, Any]) -> ProvenanceReport:
    findings: list[ProvenanceFinding] = []
    value = str(record.get("provenance") or "")
    if value not in PROVENANCE_CLASSES:
        findings.append(ProvenanceFinding("UNKNOWN_PROVENANCE", value or "<missing>"))
        return ProvenanceReport(False, tuple(findings))

    if value == "GENERATIVE_VISIBLE":
        findings.append(ProvenanceFinding(
            "GENERATIVE_VISIBLE_FORBIDDEN",
            str(record.get("part") or record.get("name") or "<unnamed>"),
        ))

    if value == "INFERRED_OCCLUSION":
        receipt = str(record.get("approved_occlusion_receipt") or "").strip()
        if receipt:
            findings.append(ProvenanceFinding(
                "INFERRED_OCCLUSION_STILL_UNPROMOTED",
                "approval reference exists but provenance was not promoted to OWNER_APPROVED_OCCLUSION",
            ))
        else:
            findings.append(ProvenanceFinding(
                "INFERRED_OCCLUSION_REQUIRES_OWNER_APPROVAL",
                str(record.get("part") or record.get("name") or "<unnamed>"),
            ))

    if value == "OWNER_APPROVED_OCCLUSION":
        receipt = str(record.get("approved_occlusion_receipt") or "").strip()
        if not receipt:
            findings.append(ProvenanceFinding(
                "APPROVED_OCCLUSION_RECEIPT_MISSING",
                str(record.get("part") or record.get("name") or "<unnamed>"),
            ))

    return ProvenanceReport(not findings, tuple(findings))


def production_admissible(record: dict[str, Any]) -> bool:
    report = classify_layer(record)
    return report.ok and record.get("provenance") in PRODUCTION_ADMISSIBLE


def write_decomposition_receipt(
    *,
    source: Path,
    output: Path,
    tool_repository: str,
    tool_commit: str,
    model_hashes: dict[str, str],
    config: dict[str, Any],
    seed: int | None,
    layers: list[dict[str, Any]],
    receipt_path: Path,
) -> dict[str, Any]:
    for name, value in model_hashes.items():
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value.lower()):
            raise ValueError(f"model hash for {name} is not a SHA-256")
    for layer in layers:
        report = classify_layer(layer)
        if any(f.code == "UNKNOWN_PROVENANCE" for f in report.findings):
            raise ValueError(f"unknown provenance in layer {layer!r}")

    receipt = {
        "schema_version": 1,
        "source_path": source.as_posix(),
        "source_sha256": sha256_file(source),
        "output_path": output.as_posix(),
        "output_sha256": sha256_file(output),
        "tool_repository": tool_repository,
        "tool_commit": tool_commit,
        "model_hashes": dict(sorted(model_hashes.items())),
        "config": config,
        "seed": seed,
        "layers": layers,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(yaml.safe_dump(receipt, sort_keys=False), encoding="utf-8")
    return receipt


def canonical_json_sha256(data: Any) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
