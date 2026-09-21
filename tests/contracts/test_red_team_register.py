"""Rev 1.5 §38 — the red-team register, and why a register needs a checker.

RB-052. §38 lists fifty release-suite scenarios and nine Rev 1.2 continuity attacks, and
ends with a rule that is easy to read past: every finding is `PASS`, `FAIL`,
`BLOCKED_EXTERNAL` or `NOT_APPLICABLE_WITH_REASON`, and **never `assumed`**.

A register of fifty-nine statuses is the natural way to record that and also the natural
way to accumulate fifty-nine assertions nobody checks. The first version of this one
proved the point: every PASS named a test that existed, and twenty-five of them named it
in a way that could not be run, because the test lived inside a class the citation omitted.
Every claim was true and a quarter of them were unusable as evidence.

So these tests check the checker as well as the register — the rules that matter are the
ones that fail on a register that has quietly gone wrong.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "ci"))

import red_team_register  # noqa: E402

REGISTER = ROOT / "evidence/van-system-audit/red_team_register.json"
BLUEPRINT = ROOT / "docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md"


def _doc() -> dict:
    return json.loads(REGISTER.read_text(encoding="utf-8"))


def _write(tmp_path: Path, doc: dict) -> Path:
    path = tmp_path / "register.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- the real file


def test_the_repositorys_register_passes_its_own_checker():
    assert red_team_register.check(REGISTER) == []


def test_it_carries_every_scenario_section_38_names():
    """Read out of the blueprint rather than counted, so a dropped one is visible.

    §41's rule applied to §38: no item may disappear because somebody deferred it
    silently. The numbered list is parsed from the authority and compared by wording.
    """
    text = BLUEPRINT.read_text(encoding="utf-8")
    section = text[text.index("# 38. RED-TEAM MATRIX"):]
    section = section[: section.index("Every finding is")]
    numbered = re.findall(r"^\d+\.\s+(.+?);\s*$", section, re.M)
    numbered += re.findall(r"^\d+\.\s+(.+?)\.\s*$", section, re.M)
    assert len(numbered) >= 50, len(numbered)

    registered = {s["scenario"] for s in _doc()["scenarios"]}
    missing = [item for item in numbered if item not in registered]
    assert missing == [], missing


def test_it_also_carries_the_rev_1_2_continuity_attacks():
    text = BLUEPRINT.read_text(encoding="utf-8")
    block = text[text.index("### Rev 1.2 additional continuity attacks"):]
    block = block[block.index("```text") + len("```text"): block.index("```", block.index("```text") + 8)]
    attacks = [line.strip() for line in block.strip().splitlines() if line.strip()]
    assert attacks, "the continuity attacks are no longer readable from the blueprint"

    registered = {s["scenario"] for s in _doc()["scenarios"]}
    missing = [a for a in attacks if a not in registered]
    assert missing == [], missing


def test_no_scenario_is_a_claim_without_evidence():
    for scenario in _doc()["scenarios"]:
        if scenario["status"] == "PASS":
            assert scenario["evidence"], scenario["scenario"]
        else:
            assert scenario.get("blocked_by") or scenario.get("note"), scenario["scenario"]


def test_the_blocked_ones_say_what_is_missing_rather_than_that_something_is():
    """"Blocked" with no subject is the same as "assumed" with better manners."""
    for scenario in _doc()["scenarios"]:
        if scenario["status"] != "BLOCKED_EXTERNAL":
            continue
        blocked_by = scenario.get("blocked_by", "")
        assert len(blocked_by) > 20, scenario["scenario"]
        assert blocked_by.lower() != "external", scenario["scenario"]


# --------------------------------------------------------------------------- the checker


def test_a_pass_with_no_evidence_is_refused(tmp_path):
    doc = _doc()
    doc["scenarios"][0]["evidence"] = []
    assert any("no evidence" in p for p in red_team_register.check(_write(tmp_path, doc)))


def test_a_pass_citing_a_file_that_does_not_exist_is_refused(tmp_path):
    doc = _doc()
    doc["scenarios"][0]["evidence"] = ["backend/tests/test_nothing_here.py"]
    assert any("does not exist" in p for p in red_team_register.check(_write(tmp_path, doc)))


def test_a_pass_citing_a_test_inside_a_class_without_its_class_is_refused(tmp_path):
    """The failure that made twenty-five citations unusable.

    `file.py::test_name` for a test defined inside `class TestThing` resolves against
    nothing pytest can run. The name is in the file, so a substring check passes; the
    citation is still not evidence anyone can re-run.
    """
    doc = _doc()
    doc["scenarios"][0]["evidence"] = [
        "backend/tests/test_interactive_browser_session.py::test_a_grant_is_redeemable_exactly_once"
    ]
    problems = red_team_register.check(_write(tmp_path, doc))
    assert any("not a runnable pytest node id" in p for p in problems), problems


def test_the_same_citation_with_its_class_is_accepted(tmp_path):
    """The other half. A checker that refused everything would pass the test above."""
    doc = _doc()
    doc["scenarios"][0]["evidence"] = [
        "backend/tests/test_interactive_browser_session.py::TestStreamGrants"
        "::test_a_grant_is_redeemable_exactly_once"
    ]
    assert red_team_register.check(_write(tmp_path, doc)) == []


def test_a_citation_naming_a_test_that_was_renamed_is_refused(tmp_path):
    doc = _doc()
    doc["scenarios"][0]["evidence"] = [
        "backend/tests/test_interactive_browser_session.py::TestStreamGrants::test_gone"
    ]
    assert any("not a runnable" in p for p in red_team_register.check(_write(tmp_path, doc)))


@pytest.mark.parametrize("word", ["assumed", "ASSUMED", "Assumed-pass"])
def test_the_word_section_38_forbids_is_refused_wherever_it_appears(tmp_path, word):
    doc = _doc()
    doc["scenarios"][0]["note"] = f"{word}: nobody ran this"
    problems = red_team_register.check(_write(tmp_path, doc))
    assert any("forbids" in p for p in problems), problems


def test_an_unknown_status_is_refused(tmp_path):
    doc = _doc()
    doc["scenarios"][0]["status"] = "PROBABLY_FINE"
    assert any("is not one of" in p for p in red_team_register.check(_write(tmp_path, doc)))


def test_a_missing_scenario_is_refused(tmp_path):
    """Contiguous numbering, so an inconvenient item cannot be dropped quietly."""
    doc = _doc()
    del doc["scenarios"][10]
    assert any("contiguous" in p for p in red_team_register.check(_write(tmp_path, doc)))


def test_a_blocked_scenario_with_no_subject_is_refused(tmp_path):
    doc = _doc()
    blocked = next(s for s in doc["scenarios"] if s["status"] == "BLOCKED_EXTERNAL")
    blocked.pop("blocked_by")
    blocked.pop("note", None)
    problems = red_team_register.check(_write(tmp_path, doc))
    assert any("no reason given" in p or "must name what is missing" in p for p in problems)
