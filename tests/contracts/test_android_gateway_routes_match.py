"""The routes the phone calls have to be the routes the gateway serves.

Every other seam between these two has a schema or a test on both sides. The URL does not:
the device builds a string, the gateway registers a path, and nothing compares them. A
mismatch is a 404 at runtime on the owner's phone, with the gateway's logs showing a request
for a route it does not have and the phone showing "Could not reach the browser".

The prefixes are the part worth pinning, because they are the part that gets refactored.
Per-route suffixes are checked against the registered router so a renamed action is caught
too, but the prefix is where a rename actually happens.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLIENT = (
    ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "dial" / "van"
    / "gateway" / "VanGatewayClient.kt"
)

sys.path.insert(0, str(ROOT / "backend"))

from van_gateway.browser.interactive_api import (  # noqa: E402
    INTERACTIVE_SESSION_PREFIX,
    is_interactive_browser_owner_route,
)
from van_gateway.session.api import SESSION_PREFIX  # noqa: E402


def _kotlin_const(name: str) -> str:
    match = re.search(rf'const val {name} = "([^"]+)"', CLIENT.read_text())
    assert match, f"{name} is not declared in {CLIENT.name}"
    return match.group(1)


def test_the_interactive_browser_prefix_matches():
    assert _kotlin_const("INTERACTIVE_SESSIONS") == INTERACTIVE_SESSION_PREFIX


def test_the_session_prefix_matches():
    assert _kotlin_const("SESSION_PREFIX") == SESSION_PREFIX


def test_every_interactive_path_the_device_builds_is_classified_as_an_owner_route():
    """A route the classifier does not recognise falls through to the wrong authority.

    This is the seam `P2-GOOG-004` was found at: six routes outside the scope set. Here the
    consequence would be the owner's own phone being refused on its own browser session.
    """
    text = CLIENT.read_text()
    suffixes = re.findall(r'"\$INTERACTIVE_SESSIONS(/[^"]*)"', text)
    assert suffixes, "no interactive routes found, so this test proves nothing"
    for suffix in suffixes:
        # The interpolations are session ids; any non-empty segment exercises the same rule.
        concrete = INTERACTIVE_SESSION_PREFIX + re.sub(r"\$\{[^}]+\}", "ibs_1", suffix)
        assert is_interactive_browser_owner_route(concrete), concrete


def test_the_device_never_builds_a_navigate_route():
    """§6.1 — navigation is an actuation, fenced by the control lease, not by REST.

    A `navigate` route on the gateway would be a second actuation path with a different
    authority, which is precisely what the interactive surface is designed to avoid. The
    device having a method for one would be the first half of building it.
    """
    text = CLIENT.read_text()
    assert "/navigate" not in text
    assert "interactiveBrowserNavigate" not in text


def test_the_bootstrap_routes_are_called_without_ingress_authentication():
    """A phone being enrolled has no device token yet, by definition (ADR-RB-026).

    Calling these with `useIngress = true` makes first enrolment impossible on a fresh
    device and the failure looks like a credential problem rather than a design one.
    """
    text = CLIENT.read_text()
    for route in ("/v1/devices/bootstrap/challenge", "/v1/devices/bootstrap/attest"):
        index = text.index(route)
        window = text[index : index + 800]
        assert "useIngress = false" in window, route


def test_every_mutating_interactive_call_carries_a_proof():
    """ADR-RB-025 — a mutation sent without a proof is refused by a bound gateway.

    Read structurally rather than by name: any call that posts to the interactive prefix
    must go through `postProved`, and the session end must go through `deleteProved`. A new
    route added with plain `postJson` would authenticate and then fail at the gate.
    """
    text = CLIENT.read_text()
    for call in re.findall(r'(postJson|postRawAt)\(\s*"?\$?INTERACTIVE_SESSIONS', text):
        raise AssertionError(f"an interactive mutation bypasses the proof helper: {call}")
    assert "deleteProved(\"$INTERACTIVE_SESSIONS" in text
