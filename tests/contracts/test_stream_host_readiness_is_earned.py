"""Rev 1.5 §§13, 23.1 — `browser.interactive.session` is ready only by measurement.

The capability the Mission binder names is declared `EXTERNAL_RUNTIME` against the probe
`browser_stream_host`, which means: until someone runs a canary against a real Stream
Host, VAN refuses to record that a Mission used a remote browser. That refusal is the
whole value of the declaration, and it is exactly the kind of thing that gets quietly
undone — by a default, by a fixture that leaks into production wiring, by a line that
records evidence at startup "so the tests pass".

So this file asserts the three things that would have to stay true for the refusal to
mean anything:

* the capability is declared, and declared against that probe (the defect RB-044 found
  was that it was named by the binder and declared by nobody, so every mission-bound
  browser session was a 500);
* the only code that writes `browser_stream_host` readiness evidence is a certification
  tool that requires a live host;
* nothing in the Gateway writes it.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPABILITY_ID = "browser.interactive.session"
PROBE = "browser_stream_host"


def _declaration() -> dict:
    data = json.loads((ROOT / "registries" / "capabilities.json").read_text(encoding="utf-8"))
    matching = [c for c in data["capabilities"] if c["capability_id"] == CAPABILITY_ID]
    assert len(matching) == 1, f"{CAPABILITY_ID} must be declared exactly once"
    return matching[0]


def test_the_capability_the_binder_names_is_declared():
    """The binder names one string and the registry has to know it.

    Asserted from the binder's constant rather than from a literal here, so renaming the
    capability in one place and not the other fails rather than drifting: that drift is
    what made §23.1 a 500 for the whole life of the feature before this checkpoint.
    """
    source = (ROOT / "backend" / "van_gateway" / "mission" / "binding.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    named = {
        node.targets[0].id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    assert named["INTERACTIVE_BROWSER_CAPABILITY"] == CAPABILITY_ID
    assert _declaration()["capability_id"] == CAPABILITY_ID


def test_readiness_is_external_and_probed_by_the_stream_host():
    declaration = _declaration()
    assert declaration["readiness_source"] == "EXTERNAL_RUNTIME"
    assert declaration["health_probe"] == PROBE
    # STATIC would mean "declared ready", and a gateway with no host would report that it
    # can drive a remote browser it has never seen.
    assert declaration["readiness_source"] != "STATIC"


def test_only_a_live_canary_can_record_the_evidence():
    """Every writer of this probe's readiness evidence, enumerated.

    A grep rather than a mock, because the failure this guards against is a *new* line of
    code somewhere else, and no test double sees one of those.
    """
    writers = set()
    here = Path(__file__).resolve()
    for path in ROOT.rglob("*.py"):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.resolve() == here:
            # This file names both strings in order to look for them.
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if PROBE in text and "record_evidence" in text:
            writers.add(path.relative_to(ROOT).as_posix())

    assert writers == {
        "tools/certification/certify_browser_stream_host.py",
        # The one test file that stages the world to exercise the *bound* path. It
        # constructs its own store and never touches a deployment's.
        "backend/tests/test_browser_mission_binding_regression.py",
    }, writers


def test_the_gateway_never_records_it():
    """The narrower half of the test above, and the one that matters in production."""
    gateway = ROOT / "backend" / "van_gateway"
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in gateway.rglob("*.py")
        if PROBE in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == [], offenders


def test_the_certification_tool_requires_a_live_host():
    """It takes a host address and has no offline mode.

    A `--dry-run` or a default host would be the thing that turns this gate from a
    measurement into a formality.
    """
    source = (
        ROOT / "tools" / "certification" / "certify_browser_stream_host.py"
    ).read_text(encoding="utf-8")
    assert '"--host", required=True' in source
    assert "--dry-run" not in source
    assert "--offline" not in source
    # The evidence is written in the canary that actually speaks the protocol, not in the
    # one that only completes a handshake: an open port is not a working control agent.
    observe = source.split("async def canary_observe", 1)[1].split("async def canary_fence", 1)[0]
    assert "record_evidence" in observe
    mtls = source.split("async def canary_mtls", 1)[1].split("async def canary_observe", 1)[0]
    assert "record_evidence" not in mtls
