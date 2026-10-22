import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("forecast_provenance", ROOT / "tools/rebuild/forecast_provenance.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_all_original_requirement_and_packet_hashes_reproduce():
    report = module.evaluate(module.load_inputs())
    assert report["findings"] == []
    assert len(report["requirements"]) == 90
    assert len(report["packets"]) == 48
    assert all(x["recorded_sha256"] == x["reproduced_sha256"] for x in report["requirements"] + report["packets"])


@pytest.mark.parametrize("mutation,expected", [
    ("source_obligation", "REQUIREMENT_HASH_MISMATCH:"),
    ("recorded_hash", "REQUIREMENT_HASH_MISMATCH:"),
    ("packet_mapping", "REQUIREMENT_PACKET_MISMATCH:"),
    ("packet_deliverable", "PACKET_HASH_MISMATCH:"),
    ("missing_requirement", "REQUIREMENT_SET_MISMATCH"),
    ("duplicate_requirement", "DUPLICATE:"),
])
def test_corrupted_provenance_fails(mutation, expected):
    inputs = copy.deepcopy(module.load_inputs())
    original = inputs["original_requirements"]["requirements"][0]
    current = next(r for r in inputs["requirements"]["requirements"] if r["id"] == original["id"])
    if mutation == "source_obligation": original["obligation"] += " changed"
    elif mutation == "recorded_hash": current["source_obligation_sha256"] = "0" * 64
    elif mutation == "packet_mapping": current["source_packet"] = "VAN-ML-PKT-002"
    elif mutation == "packet_deliverable": inputs["original_packets"]["packets"][0]["full_deliverables"].pop()
    elif mutation == "missing_requirement": inputs["original_requirements"]["requirements"].pop()
    elif mutation == "duplicate_requirement": inputs["original_requirements"]["requirements"].append(copy.deepcopy(original))
    assert any(x.startswith(expected) for x in module.evaluate(inputs)["findings"])
