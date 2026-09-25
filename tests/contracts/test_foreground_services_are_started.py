"""P1-VOICE-001 — every foreground service the manifest declares has a production caller.

The wake listener was declared, typed `microphone`, recorded as INTEGRATED in the component
ledger — and nothing in the app ever started it. Its own `start()` existed and its only
"caller" was the service's own `onStartCommand`, so a phone with a correct wake bundle
would still never listen for its name. Reachability checks did not catch it because the
manifest makes the class reachable; what was missing was the call.

System-bound services (accessibility, notification listener) are started by Android and
are excluded by their bind permission.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
APP_SRC = ROOT / "android" / "app" / "src" / "main" / "java"
PACKAGE_DIR = APP_SRC / "com" / "dial" / "van"

SERVICE = re.compile(r"<service\b(?P<attrs>[^>]*)>", re.S)


def _foreground_services() -> list[str]:
    found = []
    for match in SERVICE.finditer(MANIFEST.read_text(encoding="utf-8")):
        attrs = match.group("attrs")
        if "foregroundServiceType" not in attrs or "android:permission=" in attrs:
            continue
        name = re.search(r'android:name="\.?([\w.]+)"', attrs).group(1)
        found.append(name)
    return found


def test_the_manifest_declares_the_foreground_services_this_checks() -> None:
    names = _foreground_services()
    assert "overlay.FloatingOverlayService" in names
    assert "voice.WakeListenerService" in names


def test_every_foreground_service_is_started_from_outside_its_own_file() -> None:
    missing = []
    for name in _foreground_services():
        own = PACKAGE_DIR / (name.replace(".", "/") + ".kt")
        simple = name.rsplit(".", 1)[-1]
        caller = re.compile(rf"\b{simple}\.(start|startIfReady)\(")
        callers = [
            path for path in APP_SRC.rglob("*.kt")
            if path != own and caller.search(path.read_text(encoding="utf-8"))
        ]
        if not callers:
            missing.append(simple)
    assert not missing, f"foreground services nothing starts: {missing}"


def test_the_wake_listener_starts_from_a_visible_activity() -> None:
    # Android 14+ refuses a `microphone` foreground service started from the background,
    # so the caller must be an activity lifecycle method, not the Application or a receiver.
    activity = (PACKAGE_DIR / "command" / "CommandCentreActivity.kt").read_text(encoding="utf-8")
    resume = activity[activity.index("override fun onResume()"):]
    assert "WakeListenerService.startIfReady(this)" in resume.split("override fun", 2)[1]


def test_the_wake_listener_refuses_without_a_model_or_the_microphone() -> None:
    service = (PACKAGE_DIR / "voice" / "WakeListenerService.kt").read_text(encoding="utf-8")
    start_if_ready = service[service.index("fun startIfReady"):]
    assert "wakeModel.status().ready" in start_if_ready
    assert "RECORD_AUDIO" in start_if_ready
    # Never re-arm an armed listener: arm() clears the active turn.
    assert "if (running) return false" in start_if_ready
    assert "if (running) return START_STICKY" in service


def test_opening_van_restores_an_overlay_a_force_stop_left_off() -> None:
    # A force-stop skips onDestroy and sends no broadcast; before this, only Settings › Start
    # brought Floating VAN back, so the checklist's process_kill row could not pass.
    activity = (PACKAGE_DIR / "command" / "CommandCentreActivity.kt").read_text(encoding="utf-8")
    resume = activity[activity.index("override fun onResume()"):].split("override fun", 2)[1]
    assert "OverlayRecovery.restoreIfOwnerHadItOn(this)" in resume
    recovery = (PACKAGE_DIR / "overlay" / "OverlayRecoveryReceiver.kt").read_text(encoding="utf-8")
    rule = recovery[recovery.index("fun restoreIfOwnerHadItOn"):]
    # Only when the owner left it on, never twice, never without the overlay grant.
    assert "state.serviceRunning" in rule
    assert "FloatingOverlayService.isRunning()" in rule
    assert "Settings.canDrawOverlays(context)" in rule
    # The boot path uses the same rule rather than a second copy of it.
    assert "OverlayRecovery.restoreIfOwnerHadItOn(context)" in recovery
