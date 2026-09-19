"""The three owner surfaces that existed as data layers with no screen.

Each of these is the same defect wearing different clothes: a complete, tested mechanism
that the owner had no way to reach.

- `MissionRepository` — 371 lines whose own docstring calls it "the only place the surfaces
  get data", constructed by no production file, with eighteen `VanGatewayClient` reads
  behind it. The owner could issue a command and had no screen that would ever say how it
  went.
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
screen exists, is reachable from the navigation enum, and calls the function that was dead
— which is the half a refactor silently removes.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "dial" / "van"
MODULES = APP / "command" / "modules"
NAV = APP / "command" / "CommandModule.kt"
ACTIVITY = APP / "command" / "CommandCentreActivity.kt"

#: screen file -> (navigation enum member, the previously-dead calls it must make)
#:
#: The call fragments name the *binding*, not just the function. A first version asserted
#: `repository.home()` and `store.setPolicy(` — substrings any single occurrence satisfies —
#: so mutations that dropped the result assignment, or emptied one of two call sites,
#: survived every test here. A presence check on a name that appears more than once tests
#: almost nothing.
SURFACES = {
    "MissionsModule.kt": ("MISSIONS", (
        "MissionRepository(app.gatewayClient)",
        "runCatching { repository.home() }",
        ".onSuccess { snapshot = it; error = null }",
    )),
    "NotificationPolicyModule.kt": ("NOTIFICATIONS", (
        "store.setPolicy(entry.key, option)",
        "store.setPolicy(pkg, AppNotificationPolicy.MUTE)",
        "store.setQuietHours(quiet.copy(enabled = !quiet.enabled))",
    )),
    "SpeechModule.kt": ("SPEECH", (
        "model.recordCorrection(",
        "model.pinTerm(term, selected)",
    )),
}

#: Per screen, the state that must survive rotation, named individually. `rememberSaveable`
#: appearing once in a file says nothing about the field that actually matters.
SAVED_STATE = {
    "MissionsModule.kt": ("var expanded by rememberSaveable",),
    "NotificationPolicyModule.kt": ("var draft by rememberSaveable",),
    "SpeechModule.kt": (
        "var heard by rememberSaveable",
        "var meant by rememberSaveable",
        "var term by rememberSaveable",
    ),
}


def _nav() -> str:
    return NAV.read_text(encoding="utf-8")


def _activity() -> str:
    return ACTIVITY.read_text(encoding="utf-8")


def test_each_surface_exists():
    for screen in SURFACES:
        assert (MODULES / screen).is_file(), f"{screen} is missing"


def test_each_surface_is_in_the_navigation_enum():
    """A Composable nothing navigates to is a Composable nobody sees.

    `CommandModule` is the whole of the Command Centre's navigation; a screen absent from it
    cannot be opened however correct it is.
    """
    nav = _nav()
    for screen, (member, _) in SURFACES.items():
        assert f"{member}(" in nav, f"{screen} has no {member} entry in CommandModule"


def test_each_surface_is_rendered_by_the_activity():
    """The enum entry and the render branch are separate, and an entry with no branch is a
    tab that opens nothing."""
    activity = _activity()
    for screen, (member, _) in SURFACES.items():
        composable = screen.removesuffix(".kt")
        assert f"CommandModule.{member} -> {composable}(" in activity, (
            f"{member} has no render branch"
        )
        assert f"import com.dial.van.command.modules.{composable}" in activity


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

    A half-typed package name or the mission the owner had open is exactly what is lost when
    the phone turns, and losing it reads as VAN forgetting.
    """
    for screen, fields in SAVED_STATE.items():
        source = (MODULES / screen).read_text(encoding="utf-8")
        assert "import androidx.compose.runtime.saveable.rememberSaveable" in source
        for field in fields:
            assert field in source, f"{screen}: {field!r} is lost when the phone turns"
