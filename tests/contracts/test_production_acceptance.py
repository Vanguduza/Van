"""Rev 1.5 §43 — the Production Acceptance register, and the verdict it may not assert.

RB-058. §43 lists one hundred and four things that must be true before Remote Browser
Rev 1.5 is production complete. A list that long is also a hundred and four places for an
unchallenged claim, and the specific claim worth guarding is the one at the top: a verdict.

A verdict written by a person at the top of a ledger is written once and never re-derived.
So the checker recomputes it from the rows, and this file is what proves the checker
actually would fail — on a register that quietly went accepted, on one that dropped a
requirement, and on one whose evidence has been renamed out from under it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "ci"))

import production_acceptance  # noqa: E402

REGISTER = ROOT / "evidence/van-system-audit/production_acceptance.json"


def _doc() -> dict:
    return json.loads(REGISTER.read_text(encoding="utf-8"))


def _write(tmp_path: Path, doc: dict) -> Path:
    path = tmp_path / "acceptance.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- the real file


def test_the_repositorys_register_passes_its_own_checker():
    assert production_acceptance.check(REGISTER) == []


def test_it_carries_every_requirement_section_43_names():
    """Read out of the blueprint rather than counted.

    A copy of an authority drifts, and the direction is always the same: the copy is the
    one that gets shorter.
    """
    declared = production_acceptance.blueprint_requirements()
    assert len(declared) >= 100, len(declared)
    registered = {r["requirement"] for r in _doc()["requirements"]}
    assert set(declared) == registered


def test_the_verdict_is_not_production_accepted_and_says_why():
    """The honest state, and the one this programme exists to be able to state.

    Forty-four of the hundred and four need a Browser Stream Host, a carrier, a handset or
    something the owner provisions. Saying PRODUCTION_ACCEPTED while that is true would be
    the substitution the whole audit refuses.
    """
    doc = _doc()
    assert doc["verdict"] == "REPOSITORY_COMPLETE_PENDING_EXTERNAL"
    assert doc["blocked_count"] > 0
    blocked = [r for r in doc["requirements"] if r["status"] != "REPOSITORY_PROVEN"]
    assert len(blocked) == doc["blocked_count"]
    for row in blocked:
        assert row.get("blocked_by"), row["requirement"]


def test_every_proven_requirement_names_something():
    for row in _doc()["requirements"]:
        if row["status"] == "REPOSITORY_PROVEN":
            assert row["evidence"], row["requirement"]


def test_repository_proven_is_defined_as_weaker_than_certification():
    """The vocabulary carries the distinction, because the word does not.

    "Proven" reads like "certified" to anyone who did not write it. The register says in
    its own definition that it is not, and this is what stops that sentence being edited
    away quietly.
    """
    doc = _doc()
    definition = doc["vocabulary"]["REPOSITORY_PROVEN"].lower()
    assert "not a claim" in definition
    assert "real hardware" in definition


# --------------------------------------------------------------------------- the checker


def test_a_verdict_that_disagrees_with_the_rows_is_refused(tmp_path):
    """The rule that makes this a program rather than a document."""
    doc = _doc()
    doc["verdict"] = "PRODUCTION_ACCEPTED"
    problems = production_acceptance.check(_write(tmp_path, doc))
    assert any("the rows say" in p for p in problems), problems


def test_a_stale_blocked_count_is_refused(tmp_path):
    doc = _doc()
    doc["blocked_count"] = 0
    assert any("blocked_count" in p for p in production_acceptance.check(_write(tmp_path, doc)))


def test_accepted_is_reachable_when_every_row_is_settled(tmp_path):
    """The other half. A checker that always said pending would pass the tests above.

    Built by settling every row, which is what a real acceptance would look like: the
    verdict is not withheld by the checker, it is withheld by the rows.
    """
    doc = _doc()
    for row in doc["requirements"]:
        row["status"] = "NOT_APPLICABLE_WITH_REASON"
        row["blocked_by"] = "a fixture, not a real disposition"
    doc["verdict"] = "PRODUCTION_ACCEPTED"
    doc["blocked_count"] = 0
    assert production_acceptance.check(_write(tmp_path, doc)) == []


def test_a_dropped_requirement_is_refused(tmp_path):
    doc = _doc()
    dropped = doc["requirements"].pop(3)["requirement"]
    problems = production_acceptance.check(_write(tmp_path, doc))
    assert any(dropped in p for p in problems), problems


def test_an_invented_requirement_is_refused(tmp_path):
    """A register may not be padded with requirements the authority does not make."""
    doc = _doc()
    doc["requirements"].append({
        "n": 999, "group": "Invented", "requirement": "everything is fine",
        "status": "REPOSITORY_PROVEN", "evidence": ["README.md"],
    })
    problems = production_acceptance.check(_write(tmp_path, doc))
    assert any("§43 does not require" in p for p in problems), problems


def test_a_proven_row_citing_a_renamed_test_is_refused(tmp_path):
    doc = _doc()
    row = next(r for r in doc["requirements"] if r["status"] == "REPOSITORY_PROVEN")
    row["evidence"] = [
        "backend/tests/test_interactive_browser_session.py::TestStreamGrants::test_gone"
    ]
    problems = production_acceptance.check(_write(tmp_path, doc))
    assert any("not a runnable pytest node id" in p for p in problems), problems


def test_a_blocked_row_with_no_subject_is_refused(tmp_path):
    doc = _doc()
    row = next(r for r in doc["requirements"] if r["status"] == "BLOCKED_EXTERNAL")
    row.pop("blocked_by")
    problems = production_acceptance.check(_write(tmp_path, doc))
    assert any("must name what is missing" in p for p in problems), problems


@pytest.mark.parametrize("status", ["PASS", "DONE", "probably"])
def test_a_status_outside_the_vocabulary_is_refused(tmp_path, status):
    doc = _doc()
    doc["requirements"][0]["status"] = status
    assert any("is not one of" in p for p in production_acceptance.check(_write(tmp_path, doc)))
