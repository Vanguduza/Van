"""Rev 1.5 §40.5 — the Remote Browser programme ledger cannot outrun the component ledger.

The Remote Browser matrix is a programme register: 122 work items, each with a status and a
set of completion booleans. The component ledger is the repository's maturity authority. The
danger is the obvious one, and it is the same shape the whole closure programme was about: a
programme row saying `CERTIFIED` while the component it names has no production caller, and
nobody comparing the two registers.

`tools/ci/ledger_reconcile.py` compares them. These tests drive that comparison with
deliberately invalid rows, because a checker that has only ever seen valid input has not been
shown to refuse anything.

RB-122 lives here too: the four §0F corrections are pinned, so an edit that reintroduces the
stale text fails a test rather than starting an argument.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "ci"))

import ledger_reconcile  # noqa: E402

MATRIX = ROOT / "docs" / "project-state" / "REMOTE_BROWSER_IMPLEMENTATION_MATRIX.json"
BLUEPRINT = ROOT / "docs" / "VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md"
REGISTRY = ROOT / "registries" / "remote_browser_dependencies.json"
DECISIONS = ROOT / "docs" / "decisions"

LEDGER = ROOT / "evidence" / "van-system-audit" / "component_ledger.json"


def _components() -> list[dict]:
    return json.loads(LEDGER.read_text())["components"]


def _component_with(terminal_state: str | None) -> dict:
    for c in _components():
        if c.get("terminal_state") == terminal_state:
            return c
    pytest.skip(f"no component with terminal_state={terminal_state!r} to build a fixture from")


def _row(**overrides) -> dict:
    row = {
        "id": "RB-TEST",
        "name": "a fixture",
        "status": "NOT_STARTED",
        "built": False,
        "wired": False,
        "reachable": False,
        "live": False,
        "verified": False,
        "observed": False,
        "recoverable": False,
        "certified": False,
        "component_refs": [],
        "ledger_expectation": "NONE",
        # Every non-CERTIFIED row names one, so the fixture does too. A default of `[]`
        # would add the same violation to every assertion below and make each of them
        # pass for a second reason.
        "external_gates": ["nothing external: a fixture"],
    }
    row.update(overrides)
    return row


def _check(tmp_path: Path, *rows: dict) -> list[str]:
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps({"rows": list(rows)}))
    return ledger_reconcile.check_matrix(path, LEDGER)


# --------------------------------------------------------------------------- the real file


def test_the_repositorys_matrix_satisfies_its_own_rules():
    assert ledger_reconcile.check_matrix(MATRIX, LEDGER) == []


def test_the_matrix_carries_every_work_item_section_41_names():
    rows = json.loads(MATRIX.read_text())["rows"]
    ids = [r["id"] for r in rows]
    assert ids == [f"RB-{n:03d}" for n in range(1, 123)], (
        "§41 says no item may disappear because an implementation agent defers it silently. "
        "That is enforced by the list being contiguous and complete, not by intention."
    )


def test_the_matrix_is_not_the_maturity_authority_and_says_so():
    doc = json.loads(MATRIX.read_text())
    assert "component_ledger.json" in doc["purpose"]
    assert "NOT the repository-wide" in doc["purpose"]


# --------------------------------------------------------------------------- §40.5 rule 1


def test_a_component_ref_that_does_not_exist_is_refused(tmp_path):
    problems = _check(
        tmp_path,
        _row(component_refs=[99999], ledger_expectation="NON_TERMINAL"),
    )
    assert any("not in the component ledger" in p for p in problems)


def test_a_reference_that_expects_nothing_is_refused(tmp_path):
    """A ref with expectation NONE can never be compared, so it is not a claim at all."""
    problems = _check(tmp_path, _row(component_refs=[1], ledger_expectation="NONE"))
    assert any("cannot be checked" in p for p in problems)


# --------------------------------------------------------------------------- §40.5 rules 2-4


def test_certified_may_not_expect_anything_weaker_than_integration(tmp_path):
    problems = _check(
        tmp_path,
        _row(
            status="CERTIFIED",
            built=True, wired=True, reachable=True, live=True, verified=True, certified=True,
            ledger_expectation="NON_TERMINAL",
        ),
    )
    assert any("may not expect NON_TERMINAL" in p for p in problems)


def test_certified_pointing_at_an_externally_blocked_component_is_refused(tmp_path):
    blocked = _component_with("EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE")
    problems = _check(
        tmp_path,
        _row(
            status="CERTIFIED",
            built=True, wired=True, reachable=True, live=True, verified=True, certified=True,
            component_refs=[blocked["n"]],
            ledger_expectation="INTEGRATED_AND_EVIDENCED",
        ),
    )
    assert any("expects" in p and "INTEGRATED_AND_EVIDENCED" in p for p in problems), (
        "This is the rule the whole bridge exists for: a programme calling a work item "
        "certified while the thing it names is waiting on a runtime that does not exist."
    )


def test_certified_requires_the_five_evidence_fields_on_the_component(tmp_path):
    integrated = _component_with("INTEGRATED_AND_EVIDENCED")
    stripped = dict(integrated)
    stripped["production_caller"] = None
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"components": [stripped]}))

    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps({"rows": [
        _row(
            status="CERTIFIED",
            built=True, wired=True, reachable=True, live=True, verified=True, certified=True,
            component_refs=[stripped["n"]],
            ledger_expectation="INTEGRATED_AND_EVIDENCED",
        )
    ]}))
    problems = ledger_reconcile.check_matrix(matrix, ledger)
    assert any("names no production_caller" in p for p in problems)


def test_an_externally_blocked_row_may_not_claim_certified(tmp_path):
    problems = _check(tmp_path, _row(status="BLOCKED", certified=True))
    assert any("requires certified=False" in p for p in problems)


# --------------------------------------------------------------------------- §40.5 rule 5


def test_deliberately_removed_must_point_at_a_removal(tmp_path):
    integrated = _component_with("INTEGRATED_AND_EVIDENCED")
    problems = _check(
        tmp_path,
        _row(
            status="DELIBERATELY_REMOVED",
            component_refs=[integrated["n"]],
            ledger_expectation="DELIBERATELY_REMOVED_CANON_CORRECTED",
        ),
    )
    assert any("expects" in p and "DELIBERATELY_REMOVED_CANON_CORRECTED" in p for p in problems)


def test_deliberately_removed_may_not_expect_a_live_component(tmp_path):
    problems = _check(tmp_path, _row(status="DELIBERATELY_REMOVED", ledger_expectation="NON_TERMINAL"))
    assert any("may not expect NON_TERMINAL" in p for p in problems)


# --------------------------------------------------------------------------- coherence


def test_a_row_with_no_external_gates_is_refused(tmp_path):
    """The column exists to say which rows a commit can still move.

    An empty list could mean "nothing external is blocking this" or "nobody filled this
    in", and those are the two answers a reader most needs to tell apart. Forty rows
    carried an empty list, several of them genuinely blocked, so the column could not
    answer the one question it is for. A row with nothing external now says so in words.
    """
    problems = _check(tmp_path, _row(external_gates=[]))
    assert any("names no external_gates" in p for p in problems)


def test_a_certified_row_needs_no_external_gate(tmp_path):
    """The one status where an empty list is the honest answer: nothing is left."""
    component = _component_with("INTEGRATED_AND_EVIDENCED")
    problems = _check(
        tmp_path,
        _row(
            status="CERTIFIED", built=True, wired=True, reachable=True, live=True,
            verified=True, observed=True, recoverable=True, certified=True,
            component_refs=[component["n"]],
            ledger_expectation="INTEGRATED_AND_EVIDENCED",
            external_gates=[],
        ),
    )
    assert not any("external_gates" in p for p in problems), problems


def test_every_row_in_the_repositorys_matrix_names_a_gate_or_says_it_has_none(tmp_path):
    """Over the real file, so the rule is not only enforceable but enforced.

    Read separately from `test_the_repositorys_matrix_satisfies_its_own_rules` because
    that one asserts an empty problem list and would pass if this rule were deleted.
    """
    doc = json.loads(MATRIX.read_text())
    unfilled = [
        r["id"] for r in doc["rows"]
        if r["status"] != "CERTIFIED" and not r.get("external_gates")
    ]
    assert unfilled == [], unfilled
    # And the two sentences a row with nothing external may use are written down, so
    # "nothing external" cannot be said forty different ways.
    assert len(doc["no_external_gate_sentences"]) == 2


def test_a_status_that_contradicts_its_own_booleans_is_refused(tmp_path):
    problems = _check(tmp_path, _row(status="NOT_STARTED", built=True))
    assert any("requires built=False" in p for p in problems)


def test_a_row_cannot_skip_a_rung_of_the_ladder(tmp_path):
    problems = _check(
        tmp_path,
        _row(status="LIVE_UNVERIFIED", built=True, wired=False, reachable=True, live=True),
    )
    assert any("earlier rung of the ladder is false" in p for p in problems)


def test_certified_with_an_incomplete_ladder_is_refused(tmp_path):
    problems = _check(
        tmp_path,
        _row(
            status="CERTIFIED",
            built=True, wired=True, reachable=True, live=True, verified=False, certified=True,
            ledger_expectation="INTEGRATED_AND_EVIDENCED",
        ),
    )
    assert any("incomplete ladder" in p for p in problems)


def test_an_unknown_status_is_refused(tmp_path):
    problems = _check(tmp_path, _row(status="DONE"))
    assert any("is not one of" in p for p in problems)


def test_a_non_terminal_expectation_against_a_terminal_component_is_refused(tmp_path):
    integrated = _component_with("INTEGRATED_AND_EVIDENCED")
    problems = _check(
        tmp_path,
        _row(component_refs=[integrated["n"]], ledger_expectation="NON_TERMINAL"),
    )
    assert any("non-terminal component but" in p for p in problems)


def test_an_absent_matrix_is_not_a_violation(tmp_path):
    assert ledger_reconcile.check_matrix(tmp_path / "nothing.json", LEDGER) == []


def test_the_summary_line_distinguishes_absent_from_clean(tmp_path):
    """A missing matrix must not read like a passing one."""
    assert ledger_reconcile._matrix_summary(tmp_path / "nothing.json") == "absent"
    assert "122 rows" in ledger_reconcile._matrix_summary(MATRIX)


# --------------------------------------------------------------------------- RB-122


def _normative_text() -> str:
    """The blueprint with its correction register removed.

    §0F exists to quote the stale strings and say why they were wrong, so a naive search of
    the whole file can never distinguish a corrected document from an uncorrected one. The
    guard has to read what the document still *asserts*, which is everything but its own
    history section.
    """
    text = BLUEPRINT.read_text()
    start = text.index("# 0F. REV 1.5.1 REPOSITORY-LANDING CORRECTION REGISTER")
    end = text.index("# 1. PRODUCT OUTCOME", start)
    return text[:start] + text[end:]


def test_the_correction_register_is_actually_excluded_from_the_guard():
    """Otherwise the guards below would be reading the history that quotes what they forbid."""
    normative = _normative_text()
    assert "REPOSITORY-LANDING CORRECTION REGISTER" not in normative
    assert len(normative) < len(BLUEPRINT.read_text())
    assert "# 49. PR #48 ALIGNMENT CHECKLIST" in normative


def test_the_ledger_quote_distinguishes_maturity_from_terminal_state():
    """§0F.1, and the correction to my own first draft of it.

    The blueprint listed `CALLED_UNTESTED` in the column its neighbours use for a terminal
    state. The maturity class really is still CALLED_UNTESTED — both paths are called and
    neither is tested — so the first version of this guard asserted the class was gone and
    failed, correctly. What P2-LEDGER-002 changed is the terminal state.
    """
    named = {
        "WakeAcknowledgementManager.play",
        "TtsOutputManager.speak",
    }
    rows = [c for c in _components() if c.get("component") in named]
    assert len(rows) == len(named), "the components this correction is about must still exist"
    for c in rows:
        assert c["maturity_class"] == "CALLED_UNTESTED"
        assert c["terminal_state"] == "EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE"

    normative = _normative_text()
    assert "CALLED_UNTESTED / device gate" not in normative, (
        "the stale two-field conflation is back"
    )
    assert "CALLED_UNTESTED maturity, terminal EXTERNALLY_BLOCKED / device gate" in normative


def test_the_component_ledger_has_no_non_terminal_rows_at_this_baseline():
    """Why §40.3's mapping table has to be read carefully rather than applied literally."""
    non_terminal = [c["component"] for c in _components() if not c.get("terminal_state")]
    assert non_terminal == [], (
        "If this ever fails it is news, not a broken test: new Remote Browser components may "
        "carry a null terminal state, and this guard should then be replaced by one that "
        "names them rather than deleted."
    )


def test_the_migration_number_in_the_checklist_matches_section_5_6():
    """§0F.3. The checklist said 27, which is the migration §5.6 requires."""
    normative = _normative_text()
    assert "no migration-27 event text remains normative" not in normative
    assert "no migration-17 event text remains normative" in normative


def test_the_stagehand_decision_is_not_described_as_pending_without_its_correction():
    """§0F.2. The decision has been owner-signed since 2026-09-18."""
    stagehand = yaml.safe_load((DECISIONS / "VAN-ADOPT-STAGEHAND-001.yaml").read_text())
    assert stagehand["owner_signature_status"] == "SIGNED"
    assert "Rev 1.5.1 correction (§0F.2)" in BLUEPRINT.read_text()


def test_the_correction_register_exists_and_names_every_correction():
    text = BLUEPRINT.read_text()
    assert "# 0F. REV 1.5.1 REPOSITORY-LANDING CORRECTION REGISTER" in text
    for marker in ("0F.1", "0F.2", "0F.3", "0F.4", "0F.5"):
        assert marker in text, f"{marker} missing from the correction register"


def test_the_blueprint_is_at_its_canonical_path():
    """§33.2 / §49. The authority map may point only at a repository path."""
    assert BLUEPRINT.is_file()


# --------------------------------------------------------------------------- §32 dependencies


def test_no_admitted_dependency_floats():
    registry = json.loads(REGISTRY.read_text())
    for platform, entries in registry.items():
        if not isinstance(entries, dict) or platform.startswith("$"):
            continue
        for name, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            version = str(entry.get("version") or entry.get("coordinate", ""))
            assert "latest" not in version.lower(), f"{platform}.{name} floats"
            assert not version.endswith("+"), f"{platform}.{name} floats"


def test_a_dependency_claiming_a_verified_digest_carries_one():
    """`PINNED_DIGEST_VERIFIED` means the digest was measured, so it must exist and be a digest."""
    registry = json.loads(REGISTRY.read_text())
    for platform, entries in registry.items():
        if not isinstance(entries, dict) or platform.startswith("$"):
            continue
        for name, entry in entries.items():
            if not isinstance(entry, dict) or entry.get("pin_status") != "PINNED_DIGEST_VERIFIED":
                continue
            digest = entry.get("artifact_sha256", "")
            assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), (
                f"{platform}.{name} claims a verified digest that is not a sha256"
            )


def test_the_okhttp_deviation_is_recorded_rather_than_silent():
    """§32.2's candidate was rejected on a compatibility fact; that fact must be written down."""
    registry = json.loads(REGISTRY.read_text())
    okhttp = registry["android"]["okhttp"]
    deviation = okhttp["deviation_from_blueprint"]
    assert deviation["blueprint_candidate"].endswith("5.5.0")
    assert "kotlin" in deviation["rejected_because"].lower()
    kotlin_line = (ROOT / "android" / "build.gradle.kts").read_text()
    assert '"1.9.24"' in kotlin_line, (
        "the deviation is justified by the project's Kotlin version; if that changes, "
        "the deviation must be revisited rather than inherited"
    )


# --------------------------------------------------------------------------- decisions


@pytest.mark.parametrize(
    "name",
    ["VAN-ADOPT-REMOTE-BROWSER-STREAMING-001", "VAN-ADOPT-OFFLINE-VOICE-RUNTIME-001"],
)
def test_a_delegated_decision_does_not_pretend_to_be_a_signature(name):
    decision = yaml.safe_load((DECISIONS / f"{name}.yaml").read_text())
    assert decision["decision_type"] in {"OWNER_DELEGATED_RECOMMENDATION", "OWNER_SUPERSESSION"}
    assert decision.get("owner_signature_status") != "SIGNED", (
        "these were taken by delegation. Recording them as owner signatures would be the "
        "forgery the authority rules exist to prevent."
    )


def test_the_supersession_names_what_it_supersedes():
    """§0E.2 requires the prior decision to be referenced, not overwritten."""
    decision = yaml.safe_load((DECISIONS / "VAN-ADOPT-OFFLINE-VOICE-RUNTIME-001.yaml").read_text())
    prior = decision["supersedes"]
    assert prior["record"].startswith("docs/")
    assert (ROOT / prior["record"]).is_file()
    assert "Sherpa ASR" in prior["item"]
    assert decision["state_at_this_decision"]["wake_model"] == "ABSENT", (
        "the reversal admits a runtime; it does not put a model in the repository"
    )
