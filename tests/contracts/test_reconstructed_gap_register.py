"""Self-consistency rules for the reconstructed 2026-09-21 gap register.

The original Sol machine-readable register was not recoverable. This reconstructed register
therefore has to be stricter about provenance and internally computed counts: a hand-written
summary that disagrees with its own rows is not closure truth.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTER = ROOT / "docs" / "audit" / "van-whole-project-2026-09-21" / "21_GAP_REGISTER.json"


def _load() -> dict:
    return json.loads(REGISTER.read_text(encoding="utf-8"))


def test_reconstructed_register_never_impersonates_the_lost_sol_source():
    data = _load()
    provenance = data["provenance"]
    assert provenance["source_register_recovered"] is False
    assert "reconstruction" in provenance["unrecovered_source_note"].lower()
    assert provenance["original_reported_summary"] == {
        "total": 24,
        "severity_counts": {"P0": 3, "P1": 9, "P2": 10, "P3": 2},
    }


def test_closure_summary_is_computed_truth_not_a_stale_hand_count():
    data = _load()
    counts = Counter(row["status"] for row in data["findings"])
    summary = data["closure_summary"]

    assert summary["closed"] == counts["CLOSED"]
    assert summary["open"] == counts["OPEN"]
    assert summary["external_gate"] == counts["EXTERNAL_GATE"]
    assert summary["superseded"] == counts["SUPERSEDED"]
    assert sum(counts.values()) == len(data["findings"])


def test_repository_closure_has_no_open_finding_hidden_by_external_gates():
    data = _load()
    open_rows = [row["id"] for row in data["findings"] if row["status"] == "OPEN"]
    assert open_rows == []
    assert data["closure_summary"]["open"] == 0


def test_newly_discovered_findings_are_marked_as_reconstruction_additions():
    data = _load()
    additions = [
        row for row in data["findings"]
        if row.get("provenance") == "NEWLY_DISCOVERED_DURING_RECONSTRUCTION"
    ]
    assert additions, "later audit findings must be distinguishable from reconstructed Sol rows"
    assert all(row["status"] == "CLOSED" for row in additions)
