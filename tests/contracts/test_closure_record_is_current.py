"""The closure record's numbers come from the registers, or it is the thing it criticises.

`docs/project-state/REMOTE_BROWSER_CLOSURE_RECORD.md` states counts: findings, components,
matrix rows, red-team scenarios, §43 requirements. A document that states numbers is a
document whose numbers go stale, and this programme's whole subject is claims that were
true when written and are not re-derived.

So these read the registers and compare. Not the prose — the numbers, and the verdict,
which are the parts a reader acts on.
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "docs/project-state/REMOTE_BROWSER_CLOSURE_RECORD.md"
FINDINGS = ROOT / "evidence/van-system-audit/findings.json"
LEDGER = ROOT / "evidence/van-system-audit/component_ledger.json"
MATRIX = ROOT / "docs/project-state/REMOTE_BROWSER_IMPLEMENTATION_MATRIX.json"
RED_TEAM = ROOT / "evidence/van-system-audit/red_team_register.json"
ACCEPTANCE = ROOT / "evidence/van-system-audit/production_acceptance.json"


def _text() -> str:
    return RECORD.read_text(encoding="utf-8")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_findings_counts_are_the_registers():
    findings = _load(FINDINGS)["findings"]
    states = collections.Counter(f["closure"]["state"] for f in findings)
    text = _text()
    assert f"{len(findings)} findings, all closed" in text
    assert f"{states['INTEGRATED_AND_EVIDENCED']} `INTEGRATED_AND_EVIDENCED`" in text
    assert f"{states['EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE']} `EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE`" in text


def test_the_component_counts_are_the_ledgers():
    ledger = _load(LEDGER)
    states = collections.Counter(c["terminal_state"] for c in ledger["components"])
    text = _text()
    assert f"{ledger['component_count']} components, all at a terminal state" in text
    assert f"{states['INTEGRATED_AND_EVIDENCED']} integrated" in text
    assert f"{states['EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE']} externally blocked" in text


def test_the_matrix_counts_are_the_matrixs():
    rows = _load(MATRIX)["rows"]
    status = collections.Counter(r["status"] for r in rows)
    text = _text()
    assert f"{len(rows)} rows:" in text
    for name in ("WIRED_UNPROVEN", "NOT_STARTED", "BUILT_UNWIRED", "BLOCKED",
                 "VERIFIED_UNCERTIFIED"):
        assert f"{status[name]} `{name}`" in text, name


def test_the_red_team_counts_are_the_registers():
    scenarios = _load(RED_TEAM)["scenarios"]
    status = collections.Counter(s["status"] for s in scenarios)
    text = _text()
    assert f"{len(scenarios)} scenarios: {status['PASS']} `PASS`" in text
    assert f"{status['BLOCKED_EXTERNAL']} `BLOCKED_EXTERNAL`" in text
    # The number §38 cares about most.
    assert status["PASS"] + status["BLOCKED_EXTERNAL"] == len(scenarios)
    assert "**0 assumed**" in text


def test_the_acceptance_counts_and_verdict_are_the_registers():
    doc = _load(ACCEPTANCE)
    status = collections.Counter(r["status"] for r in doc["requirements"])
    text = _text()
    assert f"{len(doc['requirements'])} requirements: {status['REPOSITORY_PROVEN']} proven" in text
    assert f"{status['BLOCKED_EXTERNAL']} blocked external" in text
    assert f"{status['OWNER_DEPLOYMENT_DECISION']} owner deployment" in text
    assert f"**Verdict:** `{doc['verdict']}`" in text


def test_the_prose_numbers_agree_with_the_counts():
    """The sentences, not only the table. A reader acts on the sentence.

    "sixty are proven here and forty-four are not" is the line somebody quotes, and it is
    in words rather than digits, which is exactly how a number survives a change to the
    thing it counts.
    """
    doc = _load(ACCEPTANCE)
    status = collections.Counter(r["status"] for r in doc["requirements"])
    words = {
        60: "sixty", 44: "forty-four", 37: "thirty-seven", 7: "seven",
        104: "one hundred and four",
    }
    # Case-folded: the same number opens one sentence and sits mid-sentence in another,
    # and a test that failed on the capital would be about prose rather than counts.
    text = _text().lower()
    assert words[len(doc["requirements"])] in text
    assert words[status["REPOSITORY_PROVEN"]] in text
    assert words[status["BLOCKED_EXTERNAL"]] in text
    assert words[status["OWNER_DEPLOYMENT_DECISION"]] in text
    assert words[len(doc["requirements"]) - status["REPOSITORY_PROVEN"]] in text


def test_it_does_not_claim_production_acceptance():
    """The one claim this record must never make on the repository's behalf."""
    text = _text()
    assert "is **not production accepted**" in text
    assert "REPOSITORY_PROVEN` is the strongest thing this repository can say" in text


def test_every_checker_it_names_exists_and_is_in_ci():
    workflow = (ROOT / ".github/workflows/van-ci.yml").read_text(encoding="utf-8")
    named = set(re.findall(r"`(tools/ci/\w+\.py)`", _text()))
    assert named, "the record names no checkers"
    for checker in sorted(named):
        assert (ROOT / checker).is_file(), checker
        assert checker in workflow, f"{checker} is named in the record and not run in CI"


def test_every_register_it_names_exists():
    named = set(re.findall(r"`((?:evidence|docs)/[\w/.-]+\.(?:json|yaml))`", _text()))
    assert len(named) >= 5, named
    for register in sorted(named):
        assert (ROOT / register).is_file(), register
