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
    # Empty, and it has been a list of four. Every component is now at a terminal state, so
    # nothing is claiming to be unreached at all.
    #
    # The invariant is asserted rather than the membership: an earlier version named the
    # four by hand, which was right while they were open and became a test of a snapshot the
    # moment they closed. What must stay true is that an open unreachability claim is either
    # machine-checked or explicitly left to a human — never silently unverified.
    assert unchecked == [], f"an unreachability claim went unchecked: {unchecked}"


def test_a_reference_from_dead_code_is_not_integration():
    """The limit that produced a wrong answer on the reconciler's first run.

    `MissionParsing` was called by `MissionRepository`, which nothing constructed, and
    reading that as integration reported a cluster dead together as alive. The mechanism is
    `reachability_excludes`.

    This used to assert that entry 45 carried the exclusion. It stopped being true when
    P2-AND-015 built the screen that constructs `MissionRepository`, so the cluster is alive
    and the exclusion is gone — correctly. Pinning the mechanism to a ledger row meant the
    test failed when the row was *fixed*, so it is asserted against a synthetic ledger
    instead, where it stays meaningful however the real one changes.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("ledger_reconcile", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Every production file that names the symbol, derived rather than listed: a hardcoded
    # list goes stale the first time someone imports MissionService somewhere new, and the
    # test would then fail for a reason that has nothing to do with excludes.
    everywhere = module._production_references("MissionService", None)
    assert everywhere, "the fixture symbol is not referenced anywhere; the test proves nothing"

    result = _run_on({"components": [
        _entry(component="AliveOnlyViaDeadCode", maturity_class="UNUSED",
               path="backend/van_gateway/synthetic.py",
               reachability_symbols=["MissionService"],
               reachability_excludes=everywhere),
    ]})
    assert result.returncode == 0, result.stdout
    assert "still unreached" in result.stdout, (
        "every reference was from an excluded file and the component was still called alive"
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
        # They now carry a terminal state, and the one they carry is the argument. Each is
        # called from VanApplication and each needs a device to exercise — an audio
        # acknowledgement has to be played, a TTS engine has to speak — so the repository
        # side is complete and what remains is environmental.
        #
        # This asserted `not terminal_state` while they were open. That was right then and
        # would now forbid ever closing them, which is a test holding a snapshot rather than
        # a rule. What must not happen is either one quietly becoming
        # INTEGRATED_AND_EVIDENCED, because no test names them.
        assert c.get("production_caller"), f"{c['component']} claims a caller it does not name"
        assert c.get("terminal_state") != "INTEGRATED_AND_EVIDENCED", (
            f"{c['component']} claims evidence while no test names it"
        )
        assert not c.get("tests")


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


def test_the_ci_tools_depend_on_no_binary_the_runner_may_not_have():
    """The failure that put this branch red, generalised.

    `ledger_reconcile.py` shelled out to ripgrep. It passed here, where ripgrep is
    installed, and failed on the GitHub runner with FileNotFoundError — a checker built to
    run in the authority that could not run in the authority. Nothing asserted the tool ran
    without external binaries, because every test ran where the binary existed.

    `git` is exempt: `install_github_workflow.py` is a developer command that commits and
    pushes, and a git-less environment is not one where it has anything to do.
    """
    import ast

    exempt = {"install_github_workflow.py"}
    offenders = []
    for tool in sorted((ROOT / "tools" / "ci").glob("*.py")):
        if tool.name in exempt:
            continue
        tree = ast.parse(tool.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(a.name == "subprocess" for a in node.names):
                offenders.append(tool.name)
            if isinstance(node, ast.ImportFrom) and node.module == "subprocess":
                offenders.append(tool.name)
    assert offenders == [], (
        f"{offenders} shell out from a CI gate. The runner is not this container: it has no "
        "ripgrep, and the tool that assumes otherwise fails where it matters most."
    )


def test_the_reconciler_finds_what_it_should_without_ripgrep():
    """The replacement search, exercised directly.

    Asserting only that the tool exits zero would pass just as well if the walk found
    nothing at all, which is precisely how a search that silently matches nothing looks
    from the outside: a clean ledger.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("ledger_reconcile", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    found = module._production_references("MissionService", None)
    assert "backend/van_gateway/app.py" in found
    assert module._production_references("ZzzNotARealSymbolAnywhere", None) == []
