"""The three owner surfaces that existed as data layers with no screen.

Each of these is the same defect wearing different clothes: a complete, tested mechanism
that the owner had no way to reach.

- `MissionRepository` — 371 lines whose own docstring calls it "the only place the surfaces
  get data", constructed by no production file, with eighteen `VanGatewayClient` reads
  behind it. The owner could issue a command and had no screen that would ever say how it
  went. It is now constructed from `WorkRoute.kt` (DNA §4's Work/Command Centre destination,
  which replaced the flat module grid `MissionsModule.kt` used to be part of).
- `NotificationPolicyStore.setPolicy` / `setQuietHours` — no caller. The listener service
  reads the policy on every arriving notification and mutes, prioritises or drops
  accordingly, so the mechanism was live and running while every app stayed NORMAL forever.
  VAN holds a notification-listener grant, among the most invasive Android gives, and the
  controls that make it tolerable existed only as functions.
- `PersonalSpeechModel.recordCorrection` / `pinTerm` — no caller. The model is read on every
  voice turn to prime the recogniser and rewrite the transcript, and nothing could put a
  word into it.

These tests are static because the Android Gradle Plugin cannot be fetched here, so Compose
cannot be compiled locally. CI compiles it. What is checkable before a push is that each
screen exists, is reachable from the NavHost, and calls the function that was dead — which
is the half a refactor silently removes.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "dial" / "van"
MODULES = APP / "command" / "modules"
WORK = APP / "command" / "work" / "WorkRoute.kt"
ROUTES = APP / "command" / "nav" / "VanRoute.kt"
ACTIVITY = APP / "command" / "CommandCentreActivity.kt"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mission_repository_is_constructed_and_read_from_work():
    """The surface P2-AND-015 found dead: constructed by nothing, called by nothing."""
    work = _text(WORK)
    assert "MissionRepository(app.gatewayClient)" in work
    assert "runCatching { repository.home() }" in work
    assert ".onSuccess { active = it.activeMissions; waiting = it.waitingMissions" in work


def test_work_survives_rotation():
    """A mission's expanded/collapsed state is exactly what turning the phone used to lose."""
    work = _text(WORK)
    assert "import androidx.compose.runtime.saveable.rememberSaveable" in work
    assert "rememberSaveable(mission.missionId)" in work


#: screen file -> (the route id `VanRoute`/`CommandCentreActivity` must carry it under, the
#: previously-dead calls it must make). The call fragments name the *binding*, not just the
#: function — a presence check on a name that appears more than once tests almost nothing.
SURFACES = {
    "NotificationPolicyModule.kt": ("SETTINGS_NOTIFICATIONS", (
        "store.setPolicy(entry.key, option)",
        "store.setPolicy(pkg, AppNotificationPolicy.MUTE)",
        "store.setQuietHours(quiet.copy(enabled = !quiet.enabled))",
    )),
    "SpeechModule.kt": ("SETTINGS_VOICE", (
        "model.recordCorrection(",
        "model.pinTerm(term, selected)",
    )),
}

#: Per screen, the state that must survive rotation, named individually. `rememberSaveable`
#: appearing once in a file says nothing about the field that actually matters.
SAVED_STATE = {
    "NotificationPolicyModule.kt": ("var draft by rememberSaveable",),
    "SpeechModule.kt": (
        "var heard by rememberSaveable",
        "var meant by rememberSaveable",
        "var term by rememberSaveable",
    ),
}


def test_each_surface_exists():
    for screen in SURFACES:
        assert (MODULES / screen).is_file(), f"{screen} is missing"


def test_each_surface_is_a_known_route():
    """A route nothing declares is a screen nobody can navigate to."""
    routes = _text(ROUTES)
    for screen, (route_const, _) in SURFACES.items():
        assert f"const val {route_const} = " in routes, f"{screen} has no {route_const} route"


def test_each_surface_is_composed_by_the_activity():
    """The route and the composable call are separate, and a route with no call is a tab
    the NavHost opens nothing for."""
    activity = _text(ACTIVITY)
    assert "SettingsNotificationsRoute(app, onBack" in activity
    assert "SettingsVoiceRoute(app, onBack" in activity
    assert "import com.dial.van.command.settings.SettingsNotificationsRoute" in activity
    assert "import com.dial.van.command.settings.SettingsVoiceRoute" in activity


def test_each_surface_calls_the_function_that_was_dead():
    """The point of the screen, asserted.

    A screen that renders the right words and calls nothing would satisfy every other test
    here while leaving the owner exactly as unable as before.
    """
    for screen, (_, calls) in SURFACES.items():
        source = (MODULES / screen).read_text(encoding="utf-8")
        for call in calls:
            assert call in source, f"{screen} does not call {call}"


def test_the_notification_store_can_report_what_it_holds():
    """The screen lists apps the owner has already decided about.

    Enumerating installed packages needs QUERY_ALL_PACKAGES, which Play treats as sensitive
    and VAN does not need — a package reaches this list because a notification from it did.
    Without `decidedPackages` the screen could only offer apps it happened to know, which is
    the screen that makes a setting look absent rather than unset.
    """
    store = (APP / "notification" / "NotificationPolicy.kt").read_text(encoding="utf-8")
    assert "fun decidedPackages()" in store
    manifest = (ROOT / "android" / "app" / "src" / "main" / "AndroidManifest.xml").read_text()
    assert "QUERY_ALL_PACKAGES" not in manifest, (
        "the notification screen reached for a sensitive permission it was built to avoid"
    )


def test_the_speech_screen_does_not_teach_the_model_from_vans_own_guess():
    """`recordCorrection` refuses a trust below OWNER_CONFIRMED, which is why this is a
    screen rather than something inferred from a retry: a model that teaches itself from its
    own second guess learns its own mistakes.

    The screen passes no trust argument, so the OWNER_CONFIRMED default applies.
    """
    source = (MODULES / "SpeechModule.kt").read_text(encoding="utf-8")
    assert "trust =" not in source, (
        "the speech screen supplies its own trust level instead of taking the owner default"
    )


def test_the_surfaces_survive_rotation():
    """P2-AND-016 — Compose state restoration was ABSENT across the app.

    A half-typed package name or a correction pair is exactly what is lost when the phone
    turns, and losing it reads as VAN forgetting.
    """
    for screen, fields in SAVED_STATE.items():
        source = (MODULES / screen).read_text(encoding="utf-8")
        assert "import androidx.compose.runtime.saveable.rememberSaveable" in source
        for field in fields:
            assert field in source, f"{screen}: {field!r} is lost when the phone turns"
