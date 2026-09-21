"""Rev 1.5 §0D.1, ADR-RB-021 and ADR-RB-023 — what the manifest has to say.

Three declarations that are invisible in Kotlin and decide how VAN Browser behaves as an
Android application:

* `resizeableActivity="true"` is, in Samsung's own documentation, *the* contract that lets
  an activity take part in split-screen and pop-up/freeform modes. Without it none of §12's
  resize protocol is ever exercised, because the window never changes shape;
* an orientation lock would make the same thing true one axis at a time;
* the two entry activities have opposite export postures, and both are deliberate. The
  external-link one must be exported or other apps cannot reach it. The shortcut one must
  not be, or any app on the phone could open the owner's saved pages by guessing ids.

Asserted here rather than in a Kotlin test because the manifest is not Kotlin, and because
the Android build is compiled only in CI: nothing else in this repository would notice.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "android/app/src/main/AndroidManifest.xml"
ANDROID = "{http://schemas.android.com/apk/res/android}"


def _activities() -> dict[str, ET.Element]:
    tree = ET.parse(MANIFEST)
    found = {}
    for activity in tree.iter("activity"):
        name = activity.get(f"{ANDROID}name", "")
        found[name] = activity
    return found


def test_the_browser_activity_is_explicitly_resizeable():
    """ADR-RB-021. The one attribute Samsung names as the contract."""
    activity = _activities()[".browser.BrowserActivity"]
    assert activity.get(f"{ANDROID}resizeableActivity") == "true"


def test_the_browser_activity_does_not_lock_its_orientation():
    """ADR-RB-021 — "SHALL NOT lock portrait/landscape orientation."

    A lock would make the resize protocol unreachable on one axis, and §12's whole
    two-stage design is about a window whose shape changes underneath a live session.
    """
    activity = _activities()[".browser.BrowserActivity"]
    assert activity.get(f"{ANDROID}screenOrientation") is None


def test_picture_in_picture_is_not_enabled_to_imitate_pop_up_view():
    """ADR-RB-021 states this as a prohibition, and it is the kind that gets undone by
    someone trying to make pop-up mode work: PiP looks like the same feature and is a
    different one, with its own lifecycle and its own rules about what may be drawn."""
    activity = _activities()[".browser.BrowserActivity"]
    assert activity.get(f"{ANDROID}supportsPictureInPicture") in (None, "false")


def test_the_activity_handles_the_configuration_changes_it_has_to():
    """ADR-RB-022 — a resize must not rebuild the remote session.

    Letting Android recreate the Activity for these would tear down the renderer and the
    peer connection on every rotation, which is exactly what the ADR forbids.
    """
    activity = _activities()[".browser.BrowserActivity"]
    handled = set((activity.get(f"{ANDROID}configChanges") or "").split("|"))
    for change in ("orientation", "screenSize", "screenLayout", "smallestScreenSize", "density"):
        assert change in handled, change


def test_the_external_link_activity_is_exported_and_the_shortcut_one_is_not():
    """Opposite postures, both deliberate.

    An unexported link activity is a link activity no other app can reach, which is the
    whole feature. An exported shortcut activity lets any app on the phone open the
    owner's saved pages by guessing an id.
    """
    activities = _activities()
    external = activities[".browser.BrowserExternalLinkActivity"]
    shortcut = activities[".browser.BrowserShortcutActivity"]
    assert external.get(f"{ANDROID}exported") == "true"
    assert shortcut.get(f"{ANDROID}exported") == "false"


def test_the_browser_activity_itself_stays_unexported():
    """The session-holding Activity is not an entry point for other apps."""
    assert _activities()[".browser.BrowserActivity"].get(f"{ANDROID}exported") == "false"


def test_the_external_filter_takes_only_http_and_https():
    """§17.5. `intent:`, `file:` and the rest are refused by BrowserExternalLink too, but
    a filter that advertised them would put VAN in the chooser for links it will not
    open — and the owner would pick VAN and get a refusal."""
    external = _activities()[".browser.BrowserExternalLinkActivity"]
    schemes = {
        data.get(f"{ANDROID}scheme")
        for intent_filter in external.iter("intent-filter")
        for data in intent_filter.iter("data")
    }
    assert schemes == {"http", "https"}


def test_the_external_activity_leaves_no_trace_in_recents():
    """It has no UI and exists for one decision. A task in the recents list for it would
    show the owner an empty VAN window they cannot dismiss."""
    external = _activities()[".browser.BrowserExternalLinkActivity"]
    assert external.get(f"{ANDROID}excludeFromRecents") == "true"
    assert external.get(f"{ANDROID}noHistory") == "true"


def test_the_untrusted_profile_is_the_public_one():
    """§17.5 — a link from a messaging app opening in the browser that holds the owner's
    logged-in cookies is the whole of the attack.

    Read out of the Kotlin source rather than asserted in Kotlin, so that the profile a
    link lands in is checked by something outside the module that chooses it.
    """
    source = (
        ROOT / "android/app/src/main/java/com/dial/van/browser/BrowserShortcuts.kt"
    ).read_text(encoding="utf-8")
    match = re.search(r'const val UNTRUSTED_PROFILE = "([a-z_]+)"', source)
    assert match is not None
    assert match.group(1) == "public_research"
