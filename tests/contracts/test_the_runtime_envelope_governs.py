"""P3-PERF-003 — the envelope governs, rather than merely existing.

`VanResourceEnvelope` is pure Kotlin and `android/verification` executes twenty tests
against its arithmetic. None of that is evidence that anything in the shipping app asks it
anything. The audit's most common defect shape, and one I have reproduced myself in this
programme, is a correct component that no production path reaches — and a resource envelope
nothing consults is worse than none, because the tests say the phone is protected.

These tests are static because they have to be: the Android Gradle Plugin cannot be fetched
in this container, so the files that do the wiring (a Compose composable, a coroutine loop)
cannot be compiled here at all. CI compiles them. What is checkable before a push is that
the wiring is present and points where it claims to, which is the half that a refactor
silently removes.

The counterexample each guards: the envelope is fully tested, CI is green, and the phone is
governed by nothing because the one call site that used to consult it was reverted.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "dial" / "van"
ENVELOPE = APP / "runtime" / "VanResourceEnvelope.kt"
READINGS = APP / "runtime" / "DeviceRuntimeReadings.kt"
HARNESS_BUILD = ROOT / "android" / "verification" / "build.gradle.kts"

#: The subsystems the finding names as competing for one phone, as the enum spells them.
#: Listed here rather than parsed out of the enum, because a test that reads the enum and
#: then checks the enum contains what it read proves nothing.
COMPETING_SUBSYSTEMS = (
    "WAKE_WORD",
    "OWNER_COMMAND",
    "EMBODIMENT",
    "EVENT_STREAM",
    "TELEMETRY",
    "TRADING_UPDATES",
    "NOTIFICATION_PROCESSING",
    "LOCAL_INDEX",
)


def _app_sources() -> dict[Path, str]:
    return {
        path: path.read_text(encoding="utf-8")
        for path in APP.rglob("*.kt")
    }


def test_the_envelope_exists_and_names_every_competitor():
    """The finding lists what competes. An envelope missing one of them owns part of a sum."""
    source = ENVELOPE.read_text(encoding="utf-8")
    missing = [name for name in COMPETING_SUBSYSTEMS if name not in source]
    assert missing == [], f"the envelope does not know about: {missing}"


def test_the_envelope_is_executed_rather_than_only_reasoned_about():
    """It is in the verification harness's include list, so its arithmetic actually runs.

    The harness is the only thing in this repository that can execute Kotlin. A policy file
    outside its include list is a file nobody has ever run.
    """
    build = HARNESS_BUILD.read_text(encoding="utf-8")
    assert '"com/dial/van/runtime/VanResourceEnvelope.kt"' in build

    tests = ROOT / "android" / "verification" / "src" / "test" / "kotlin" / "com" / "dial" / "van"
    assert (tests / "runtime" / "VanResourceEnvelopeTest.kt").is_file()


def test_the_envelope_has_production_consumers_and_not_only_tests():
    """The defect shape this programme keeps finding, and that I have produced myself.

    A component read only by its own tests is not integrated, however green it is.
    """
    consumers = {
        path.relative_to(APP).as_posix()
        for path, text in _app_sources().items()
        if "VanResourceEnvelope" in text and path != ENVELOPE
    }
    assert consumers, "nothing in the shipping app consults the runtime envelope"
    # Named, so a consumer disappearing in a refactor is a failure rather than a smaller set.
    for expected in (
        "events/EventStream.kt",
        "telemetry/DeviceTelemetryReporter.kt",
        "runtime/DeviceRuntimeReadings.kt",
    ):
        assert expected in consumers, f"{expected} stopped consulting the envelope"


def test_the_embodiment_resolves_through_the_envelope_and_not_beside_it():
    """The integration that makes this a closure rather than a new file.

    `rememberVanEffectBudget` is where the app decides how rich to draw VAN. If it calls
    `VanEffectPolicy.resolve` directly again, the visual ladder goes back to being a budget
    that competes with the envelope instead of answering to it — which is the finding,
    restored, with every envelope test still passing.
    """
    fallback = (APP / "visual" / "VanCanvasFallback.kt").read_text(encoding="utf-8")
    assert "VanResourceEnvelope.effectBudget(" in fallback
    assert "VanEffectPolicy.resolve(" not in fallback, (
        "the embodiment resolves its own budget again; the envelope no longer governs it"
    )


def test_the_pollers_pass_a_real_reading_rather_than_the_default():
    """`nextDelayMillis` defaults to NOMINAL so old callers are unchanged.

    That default is right for compatibility and is exactly how the wiring could be present
    and inert: a call site that takes the default consults the envelope in form only.
    """
    work = (APP / "command" / "modules" / "WorkModules.kt").read_text(encoding="utf-8")
    assert "EventStream.nextDelayMillis(" in work
    assert "DeviceRuntimeReadings.pressure(context)" in work, (
        "the event stream loop uses the default pressure, so the envelope governs nothing here"
    )

    reporter = (APP / "telemetry" / "DeviceTelemetryReporter.kt").read_text(encoding="utf-8")
    assert "DeviceRuntimeReadings.pressure(context)" in reporter
    assert "allowance.cadenceScale" in reporter, "the flush interval ignores the allowance"


def test_the_survival_case_is_handled_rather_than_ignored():
    """`nextDelayMillis` returns null at SURVIVAL. A caller that ignores it delays on null.

    Kotlin would not compile `delay(null)`, so this is about the shape of the handling: the
    loop must break or skip, not coerce the null into some number of milliseconds.
    """
    work = (APP / "command" / "modules" / "WorkModules.kt").read_text(encoding="utf-8")
    assert "?: break" in work, "the poll loop has no path for a device that cannot afford it"
    assert "?: 0" not in work and "?: EventStream.IDLE_POLL_MS" not in work, (
        "a null was coerced back into a delay, which turns 'stop' into 'carry on'"
    )


def test_the_readings_need_no_permission_the_manifest_does_not_hold():
    """An envelope the owner can decline is an envelope VAN cannot rely on.

    Every API the reader touches is permission-free on Android. This asserts the list rather
    than the absence of a permission, because "we added no permission" is also true of code
    that calls a permission-gated API and throws — which is precisely P1-AND-014.
    """
    source = READINGS.read_text(encoding="utf-8")
    permission_free = (
        "BATTERY_PROPERTY_CAPACITY",
        "isPowerSaveMode",
        "currentThermalStatus",
        "getMemoryInfo",
        "usableSpace",
    )
    for api in permission_free:
        assert api in source, f"{api} is no longer read; the envelope lost an input"

    # The reader must not reach for anything that needs asking. This list is the set of
    # permission-gated calls a resource reader would plausibly drift towards.
    for gated in ("getRunningAppProcesses", "TelephonyManager", "getRunningServices"):
        assert gated not in source, f"{gated} needs a permission the manifest does not declare"


def test_unknown_readings_do_not_read_as_emergencies():
    """A device whose battery API does not answer must not be treated as nearly flat.

    Asserted at the source level because the failure is a default: `RuntimeReading` with no
    battery percent would, with a zero default, put every such device into SURVIVAL forever.
    The harness tests the behaviour; this pins the constant it depends on.
    """
    source = ENVELOPE.read_text(encoding="utf-8")
    assert "const val UNKNOWN = -1" in source
    assert "const val UNKNOWN_BYTES = -1L" in source
    assert "if (reading.batteryPercent == RuntimeReading.UNKNOWN) return RuntimePressure.NOMINAL" in source


def test_the_never_shed_set_is_not_empty():
    """Every 'survives all pressure' test in the harness passes vacuously on an empty set."""
    source = ENVELOPE.read_text(encoding="utf-8")
    block = source[source.index("val NEVER_SHED") : source.index("// ---- pressure")]
    for subsystem in ("WAKE_WORD", "OWNER_COMMAND", "DEGRADED_REPORTING"):
        assert f"VanSubsystem.{subsystem}" in block, f"{subsystem} can now be shed"
