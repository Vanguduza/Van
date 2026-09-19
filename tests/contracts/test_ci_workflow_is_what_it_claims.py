"""P3-OPS-010 — the workflow installer's own invariant, checked.

`tools/ci/install_github_workflow.py` says of its template: "kept byte-for-byte aligned
with the live workflow", and copies the template over `.github/workflows/van-ci.yml` on
`--apply`. Nothing enforced the alignment, and the template had drifted seventy lines
behind: it was missing the maturity gate, the maturity-gate self-test, the Hermes and
trading policy suites, the automation and browser fail-closed proofs, the context-latency
evidence step and the pure-Kotlin verification run.

So the tool whose job is to install CI would have silently deleted most of it, and the
gate that exists to stop a capability being described as BUILT without a production path
would itself have gone out that way.

The failure shape is the audit's own, one level up: a claim in a docstring with nothing
checking it. These tests are the check.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "tools" / "ci" / "github-actions-ci.yml"
LIVE = ROOT / ".github" / "workflows" / "van-ci.yml"

#: Steps whose removal would take a gate out of CI without anything failing. Named
#: individually rather than counted, so a step that is renamed is noticed rather than
#: absorbed by a total that still adds up.
LOAD_BEARING_STEPS = (
    "python tools/ci/maturity_gate.py",
    "python tools/ci/authority_map.py",
    "pytest -q tests/contracts/test_maturity_gate.py",
    "pytest -q tests/contracts/test_authority_map.py",
    "automation and browser fabric correctly refuse to self-certify",
)


def test_the_template_and_the_live_workflow_are_byte_identical():
    """The installer's docstring claims this; running --apply depends on it."""
    assert TEMPLATE.read_bytes() == LIVE.read_bytes(), (
        "tools/ci/github-actions-ci.yml has drifted from .github/workflows/van-ci.yml. "
        "install_github_workflow.py --apply copies the template over the live workflow, so "
        "drift in this direction silently deletes whatever the template is missing."
    )


def test_every_gate_survives_an_install():
    """What --apply would leave behind, asserted step by step."""
    installed = TEMPLATE.read_text(encoding="utf-8")
    missing = [step for step in LOAD_BEARING_STEPS if step not in installed]
    assert missing == [], f"installing the template would remove: {missing}"


def test_the_maturity_gate_runs_before_the_tests_it_guards():
    """A truth gate that runs after the suite reports failures in the wrong order.

    The point of running it first is that a ledger claiming something is integrated when
    nothing calls it should stop the build before anyone reads a test summary and concludes
    the system is fine.
    """
    live = LIVE.read_text(encoding="utf-8")
    assert live.index("tools/ci/maturity_gate.py") < live.index("run: pytest -q")


def test_the_installer_still_copies_the_path_these_tests_check():
    """If the installer's source or destination moves, this file is checking nothing."""
    installer = (ROOT / "tools" / "ci" / "install_github_workflow.py").read_text(
        encoding="utf-8"
    )
    assert '"tools" / "ci" / "github-actions-ci.yml"' in installer
    assert '".github" / "workflows" / "van-ci.yml"' in installer
