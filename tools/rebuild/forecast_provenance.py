#!/usr/bin/env python3
"""Reproduce forecast provenance from the original bundled JSON records.

The historical digest recipe is UTF-8(json.dumps(record, sort_keys=True,
ensure_ascii=False)), with Python's default separators and no trailing newline.
Neither source records nor recorded hashes are rewritten.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "docs/review-inputs/van-rev115/package"
OUT = ROOT / "docs/rebuild/rev118/pre002/challenge/review/FORECAST_PROVENANCE.json"
FILES = {
    "requirements": "traceability/REQUIREMENTS_AND_DU_MAPPING.json",
    "crosswalk": "traceability/FORECAST_PACKET_CROSSWALK.json",
    "original_requirements": "lineage/forecast_rev1_1/plan/REQUIREMENTS.json",
    "original_packets": "lineage/forecast_rev1_1/plan/IMPLEMENTATION_PLAN.json",
}


def source_digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def load_inputs():
    return {k: json.loads((PACKAGE / p).read_text()) for k, p in FILES.items()}


def evaluate(inputs):
    findings, rows = [], []

    def index(records, key, label):
        result = {}
        for record in records:
            value = record[key]
            if value in result:
                findings.append(f"DUPLICATE:{label}:{value}")
            result[value] = record
        return result

    originals = index(inputs["original_requirements"]["requirements"], "id", "original_requirement")
    packets = index(inputs["original_packets"]["packets"], "id", "original_packet")
    reqs = index([r for r in inputs["requirements"]["requirements"] if r["id"].startswith("VAN-ML-REQ-")], "id", "requirement")
    crosswalk = index(inputs["crosswalk"]["mappings"], "source_id", "packet_mapping")
    if set(reqs) != set(originals) or len(reqs) != 90:
        findings.append("REQUIREMENT_SET_MISMATCH")
    if set(crosswalk) != set(packets) or len(crosswalk) != 48:
        findings.append("PACKET_SET_MISMATCH")
    for identity, record in sorted(reqs.items()):
        original = originals.get(identity)
        if original is None:
            findings.append(f"MISSING_SOURCE:{identity}")
            continue
        actual = source_digest(original)
        if actual != record["source_obligation_sha256"]:
            findings.append(f"REQUIREMENT_HASH_MISMATCH:{identity}")
        if original["packet_id"] != record["source_packet"] or record["source_packet"] not in crosswalk:
            findings.append(f"REQUIREMENT_PACKET_MISMATCH:{identity}")
        if record["text"] != original["title"] + ": " + original["obligation"]:
            findings.append(f"REQUIREMENT_TEXT_MISMATCH:{identity}")
        if record["source_parent_duties"] != original["parent_units"]:
            findings.append(f"REQUIREMENT_DUTIES_MISMATCH:{identity}")
        rows.append({"id": identity, "source_packet": record["source_packet"],
                     "recorded_sha256": record["source_obligation_sha256"], "reproduced_sha256": actual})
    packet_rows = []
    for identity, record in sorted(crosswalk.items()):
        original = packets.get(identity)
        if original is None:
            findings.append(f"MISSING_PACKET_SOURCE:{identity}")
            continue
        actual = source_digest(original)
        if actual != record["source_obligation_sha256"]:
            findings.append(f"PACKET_HASH_MISMATCH:{identity}")
        if record["all_deliverables_retained"] != original["full_deliverables"]:
            findings.append(f"PACKET_DELIVERABLES_MISMATCH:{identity}")
        if record["all_exit_evidence_retained"] != original["exit_evidence"]:
            findings.append(f"PACKET_EXIT_EVIDENCE_MISMATCH:{identity}")
        packet_rows.append({"id": identity, "recorded_sha256": record["source_obligation_sha256"],
                            "reproduced_sha256": actual})
    return {"requirements": rows, "packets": packet_rows, "findings": findings}


def build():
    result = evaluate(load_inputs())
    return {"schema": "van.rebuild.forecast-provenance/1",
            "state": "SOURCE_PROVENANCE_REPRODUCED_PENDING_INDEPENDENT_REVIEW",
            "recipe": "sha256(json.dumps(original_record, sort_keys=True, ensure_ascii=False).encode('utf-8')); default separators; no newline",
            "source_files": {p: hashlib.sha256((PACKAGE / p).read_bytes()).hexdigest() for p in FILES.values()},
            "correction": "The earlier claim that 90 forecast obligation hashes were unverifiable was an instrument error: it searched strings/paragraphs rather than serialized original JSON records. All recorded values remain unchanged.",
            **result}


def main():
    mode = sys.argv[1] if len(sys.argv) == 2 else "check"
    report = build()
    if mode == "generate":
        if report["findings"]:
            print(json.dumps(report["findings"])); return 1
        OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    elif mode != "check":
        return 2
    drift = not OUT.exists() or json.loads(OUT.read_text()) != report
    print(json.dumps({"requirements": len(report["requirements"]), "packets": len(report["packets"]),
                      "findings": report["findings"], "drift": drift}))
    return int(bool(report["findings"]) or drift)


if __name__ == "__main__":
    sys.exit(main())
