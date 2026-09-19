"""The reconciler's own correctness, and that it is wired into CI.

`tools/ci/ledger_reconcile.py` exists because the maturity gate cannot catch a register
that *understates*. The gate checks that claims are backed; a component claiming to be
unreached claims nothing, so there is nothing to back. That blind spot is how the component
ledger came to list sixty-five entries as unfinished while twenty-two of them had been
wired, tested and shipped.

These tests hold the tool to the two things it could get wrong: calling a dead thing alive,
and calling a live thing dead.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "ci" / "ledger_reconcile.py"
LEDGER = ROOT / "evidence" / "van-system-audit" / "component_ledger.json"


def _components() -> list[dict]:
    d = json.loads(LEDGER.read_text())
    return d["components"] if isinstance(d, dict) else d


def test_the_reconciler_passes_on_the_current_ledger():
    result = subprocess.run([sys.executable, str(TOOL)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_it_runs_in_ci():
    """A checker nobody runs is the thing it was built to find."""
    workflow = (ROOT / ".github" / "workflows" / "van-ci.yml").read_text()
    assert "tools/ci/ledger_reconcile.py" in workflow


def test_a_component_claiming_to_be_unreached_names_what_to_look_for_or_says_it_cannot():
    """Every unreachability claim is either machine-checked or explicitly by hand.

    The failure this prevents is silent: an entry with no symbols is not verified, and
    without this it would be indistinguishable from one that passed.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("ledger_reconcile", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    unchecked = [
        c["component"] for c in _components()
        if not c.get("terminal_state")
        and c.get("maturity_class") in module.CLAIMS_UNREACHED
        and not c.get("reachability_symbols")
    ]
    # These four are dispositioned DELETE or REPLACE and judged by hand; each is named so
    # the list cannot grow quietly.
    assert sorted(unchecked) == sorted([
        "ContextCompiler / ContextPacket",
        "epistemics SemanticClass / Claim",
        "FORBIDDEN_SELF_PROMOTIONS / may_promote",
        "AdmissionOutcome / AdmissionVerdict",
    ]), f"an unreachability claim went unchecked: {unchecked}"


def test_a_reference_from_dead_code_is_not_integration():
    """The limit that produced a wrong answer on the first run.

    `MissionParsing` is called by `MissionRepository`, which nothing constructs. Reading
    that as integration would report a cluster that is dead together as alive, so a
    component may exclude files that are themselves unreached — and entry 45 does.
    """
    entry = next(c for c in _components() if c["n"] == 45)
    assert entry["reachability_excludes"] == [
        "android/app/src/main/java/com/dial/van/mission/MissionRepository.kt"
    ]
    assert not entry.get("terminal_state"), (
        "the dead gateway reads were marked integrated on the strength of a call from "
        "code that is itself dead"
    )


def test_every_terminal_component_names_its_evidence():
    """The maturity gate enforces this too. Asserted here because the reconciliation moved
    twenty-two components at once, and a bulk edit is exactly where evidence gets skipped."""
    for c in _components():
        if c.get("terminal_state") != "INTEGRATED_AND_EVIDENCED":
            continue
        for field in ("producer", "consumer", "production_caller", "tests", "runtime_evidence"):
            assert c.get(field), f"{c['component']} is integrated but names no {field}"


def test_wired_but_untested_is_its_own_answer():
    """Neither NEVER_CALLED nor integrated.

    Two components turned out to be called from VanApplication with no test naming them.
    Marking them integrated would have claimed evidence that does not exist; leaving them
    NEVER_CALLED would have been false. CALLED_UNTESTED is the honest third answer, and it
    is deliberately not a terminal state.
    """
    wired_untested = [c for c in _components() if c.get("maturity_class") == "CALLED_UNTESTED"]
    assert wired_untested, "the CALLED_UNTESTED distinction disappeared"
    for c in wired_untested:
        assert not c.get("terminal_state")
        assert c.get("production_caller")


# --------------------------------------------------------------- the self-test
#
# Everything above runs the tool against the repository's own ledger, which is clean. A
# tool that has stopped checking passes a clean ledger exactly as convincingly as one that
# works — three mutations proved it, surviving every test above: removing the failure
# branch, counting an unverifiable entry as confirmed, and treating a test reference as a
# production consumer. So the tool is also run against ledgers built to be wrong.

import tempfile


def _run_on(ledger: dict, *extra: str) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(ledger, fh)
        path = fh.name
    return subprocess.run(
        [sys.executable, str(TOOL), "--ledger", path, *extra],
        cwd=ROOT, capture_output=True, text=True,
    )


def _entry(**over) -> dict:
    base = {
        "n": 900, "component": "Synthetic", "path": "backend/van_gateway/synthetic.py",
        "maturity_class": "NO_CALLER", "disposition": "WIRE", "remediation_gate": "GATE 2",
        "terminal_state": None,
    }
    base.update(over)
    return base


def test_it_fails_on_a_ledger_that_understates():
    """The whole point. `MissionService` is constructed in app.py; a ledger still calling it
    NOT_WIRED is the drift this exists to catch."""
    result = _run_on({"components": [
        _entry(component="MissionService", maturity_class="NOT_WIRED",
               path="backend/van_gateway/mission/service.py",
               reachability_symbols=["MissionService"]),
    ]})
    assert result.returncode == 1, result.stdout
    assert "STALE" in result.stdout


def test_it_passes_on_a_ledger_that_is_right():
    """And it must be passable, or it is not a check but a refusal."""
    result = _run_on({"components": [
        _entry(reachability_symbols=["ThisSymbolIsNotInTheRepositoryAnywhere"]),
    ]})
    assert result.returncode == 0, result.stdout
    assert "still unreached" in result.stdout


def test_an_entry_with_no_symbols_is_never_counted_as_verified():
    """Silence is not agreement. An unverifiable entry reported as confirmed would make the
    summary count it among the things that were checked."""
    result = _run_on({"components": [_entry()]})
    assert "0 unreached claims confirmed" in result.stdout
    assert "unverifiable" in result.stdout
    assert _run_on({"components": [_entry()]}, "--strict").returncode == 1


def test_a_test_reference_is_not_a_production_consumer():
    """TEST_ONLY is the maturity class this whole programme found most often. A checker that
    counted a test as integration would erase the distinction it exists to draw.

    Two attempts at this test were vacuous, and both for the same reason: the fixture has
    to reach the guard being tested. `trading/` is a production root and `trading/tests/`
    sits inside it, so a symbol defined only there is the case the path filter exists for —
    but a symbol in `test_heat_governor.py` is caught by the *filename* guard instead, so
    mutating the path guard changed nothing. `conftest.py` is under a test path and is not
    named `test_*`, which is the one shape only the path filter covers.
    """
    result = _run_on({"components": [
        _entry(component="OnlyTestsUseThis", maturity_class="TEST_ONLY",
               path="trading/vati/risk/heat.py",
               reachability_symbols=["_register_owner_authority_key"]),
    ]})
    assert result.returncode == 0, result.stdout
    assert "still unreached" in result.stdout


def test_what_counts_as_a_production_reference():
    """Both exclusions, tested where they can be told apart.

    They overlap on every file in this repository, so a mutation removing either survives
    any test driven through the search. Here they are separable: the first path is excluded
    only by the directory rule, the second only by the filename rule.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("ledger_reconcile", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    counts = module.is_production_file

    assert counts("backend/van_gateway/app.py") is True

    # Directory rule only — this filename does not start with test_.
    assert counts("trading/tests/conftest.py") is False
    # Filename rule only. Any *nested* test_*.py already contains "/test", so the one case
    # the filename rule alone decides is a module at the top of a search root — which is
    # why the first two attempts at this assertion were satisfied by the path rule and a
    # mutation removing the filename rule survived both.
    assert counts("test_helpers.py") is False

    assert counts("backend/van_gateway/x.py", "backend/van_gateway/x.py") is False
    assert counts("a/b.py", None, ["a/b.py"]) is False, "a file excluded as dead still counted"
