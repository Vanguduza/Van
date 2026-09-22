"""GAP-F-027 — one on-device storage policy, checked.

Credentials, the command queue, the session outbox, the overlay state and the browser
session record are all `EncryptedSharedPreferences`. The only plain `SharedPreferences`
writers left are the three whose contents carry nothing about the owner: an event-stream
sequence cursor, a calendar-day marker for the first-session-of-day gesture, and the
onboarding-complete flag. Each one is named here with its reason; a new plain writer
anywhere else in the app fails this test until it is either encrypted or defended here.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_SRC = ROOT / "android" / "app" / "src" / "main" / "java"

#: file (relative to the repo) -> why plain storage is acceptable for it.
EXPLAINED_PLAIN_PREFERENCES: dict[str, str] = {
    "android/app/src/main/java/com/dial/van/events/PreferencesEventCursorStore.kt": (
        "P3-AND-002 — a single `after_seq` long: the last event sequence number the device "
        "has applied. Not owner data; encrypting it would only add a Keystore round-trip to "
        "every event page."
    ),
    "android/app/src/main/java/com/dial/van/VanApplication.kt": (
        "GAP-F-012 — HELLO_WAVE's `yyyy-MM-dd` marker for the first session of a calendar "
        "day, kept apart from the encrypted stores on purpose (see publishFirstSessionOfDay). "
        "The browser session record in the same file is encrypted."
    ),
    "android/app/src/main/java/com/dial/van/onboarding/OnboardingActivity.kt": (
        "A single boolean: onboarding finished. It reveals nothing beyond the fact that the "
        "app has been opened before."
    ),
}

PLAIN_CALL = re.compile(r"\bgetSharedPreferences\s*\(")


def _plain_writers() -> dict[str, int]:
    found: dict[str, int] = {}
    for path in sorted(APP_SRC.rglob("*.kt")):
        text = path.read_text(encoding="utf-8")
        hits = len(PLAIN_CALL.findall(text))
        if hits:
            found[path.relative_to(ROOT).as_posix()] = hits
    return found


def test_every_plain_preferences_writer_is_explained() -> None:
    unexplained = sorted(set(_plain_writers()) - set(EXPLAINED_PLAIN_PREFERENCES))
    assert unexplained == [], (
        "plain SharedPreferences writers with no recorded reason (encrypt them, or defend "
        f"them in EXPLAINED_PLAIN_PREFERENCES): {unexplained}"
    )


def test_explanations_are_not_stale() -> None:
    stale = sorted(set(EXPLAINED_PLAIN_PREFERENCES) - set(_plain_writers()))
    assert stale == [], f"explained files no longer use plain SharedPreferences: {stale}"


def test_sensitive_stores_are_encrypted() -> None:
    """The stores that hold owner or session material are encrypted, by name."""
    expected = {
        "android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt": "van_gateway_creds",
        "android/app/src/main/java/com/dial/van/overlay/OverlayStateStore.kt": "van_overlay_state",
        "android/app/src/main/java/com/dial/van/VanApplication.kt": "van_browser_session",
    }
    for rel, store_name in expected.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "EncryptedSharedPreferences.create(" in text, rel
        assert store_name in text, (rel, store_name)
