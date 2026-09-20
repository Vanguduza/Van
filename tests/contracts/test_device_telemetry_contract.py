"""The device's metric names and the gateway's catalogue are one contract in two languages.

P3-OBS-002. Six metrics are declared `MetricSource.DEVICE` because only the phone can
measure them, and `POST /v1/observability/device-telemetry` refuses a name it does not
know. So a device that posts a name the gateway has not declared does not get an error the
owner ever sees: its telemetry is counted as `refused` and disappears, and the scrape goes
on reporting the metric as unobserved — which is exactly the state this finding was about.

The two lists are necessarily written twice, in Python and in Kotlin. This is what stops
them drifting.
"""

import re
from pathlib import Path

# P3-OPS-012 — imported as `van_gateway`, not `backend.van_gateway`.
#
# `backend/` has no __init__.py, so `backend.van_gateway` resolves only when the repository
# root happens to be on sys.path. `python -m pytest` puts the working directory there and
# the bare `pytest` binary does not, so this file passed locally and failed in CI on the
# first run that ever reached it. pytest.ini already puts `backend` on the path, which is
# what makes the short form work under either invocation.

ROOT = Path(__file__).resolve().parents[2]
INSTRUMENTS = ROOT / "backend/van_gateway/observability/instruments.py"
KOTLIN = ROOT / "android/app/src/main/java/com/dial/van/telemetry/DeviceTelemetry.kt"
REPORTER = ROOT / "android/app/src/main/java/com/dial/van/telemetry/DeviceTelemetryReporter.kt"
APP_ROUTES = ROOT / "backend/van_gateway/app.py"


def gateway_metrics() -> tuple[set[str], set[str]]:
    """The histogram names, and every other device name the route will accept.

    Gauges and counters are returned together because this comparison is about *names*
    and the route takes a name from whichever dict holds it. Reading only two of the
    three is how two of §28.1's four device metrics reached the gateway with nothing
    checking that any phone could post them: `DEVICE_COUNTERS` was added beside the two
    this function already read, and the test whose whole job is to catch that drift did
    not know the third dict existed.
    """
    from van_gateway.observability import instruments

    return (
        set(instruments.DEVICE_HISTOGRAMS),
        set(instruments.DEVICE_GAUGES) | set(instruments.DEVICE_COUNTERS),
    )


def kotlin_metrics() -> dict[str, str]:
    """Wire name -> the dimension the Kotlin enum says it carries, or "" for none.

    The dimension is compared by *name*, not by a boolean. A device that posted its
    outbox depth in the `surface` field would be posting a label the route resolves for a
    different metric, and a true/false answer here could not tell the two apart.
    """
    text = KOTLIN.read_text(encoding="utf-8")
    body = text[text.index("enum class DeviceMetric") : text.index("val surfaced")]
    found = {}
    for wire, dimension in re.findall(
        r'\(\s*"([a-z_]+)"\s*(?:,\s*dimension\s*=\s*"([a-z_]+)"\s*)?\)', body
    ):
        found[wire] = dimension
    return found


def test_the_device_posts_exactly_what_the_gateway_declares():
    histograms, gauges_and_counters = gateway_metrics()
    assert kotlin_metrics().keys() == histograms | gauges_and_counters


def test_every_declared_device_metric_is_ingestible_under_its_wire_name():
    """The name the phone sends has to be one `record_device_sample` accepts.

    The set comparison above proves the two lists agree. This proves the list means what
    it says: a name present in a dict the ingest function does not consult would pass the
    comparison and still be refused at the route, and the phone's telemetry would vanish
    with the scrape still reporting the metric unobserved.
    """
    from van_gateway.observability import instruments
    from van_gateway.observability.metrics import MetricsRegistry

    registry = MetricsRegistry()
    landed = {
        wire: instruments.record_device_sample(
            wire, 1.0, surface="overlay", dimension="safe_to_retry", registry=registry
        )
        for wire in kotlin_metrics()
    }
    # Every one landed in a catalogue series, and no two landed in the same one: a
    # duplicated target would mean one phone measurement overwriting another's.
    assert len(set(landed.values())) == len(landed), landed
    assert not {m.name for m in registry.unobserved()} & set(landed.values())


def test_each_side_names_the_same_dimension_for_the_same_metric():
    """Not "both sides label it" — both sides label it *the same thing*.

    The ingest resolves the value from `surface` when the declared dimension is `surface`
    and from `dimension` otherwise. A phone that disagreed with the catalogue about which
    field carries the label would post into the one the route does not read, and the
    sample would be refused with nothing on either side saying why.
    """
    from van_gateway.observability import instruments

    gateway = {
        name: declared.dimension
        for table in instruments.DEVICE_TABLES
        for name, declared in table.items()
    }
    assert kotlin_metrics() == gateway, {
        "kotlin": kotlin_metrics(), "gateway": gateway,
    }
    # The two that carry one, named, so adding a third is a deliberate act.
    assert {n: d for n, d in gateway.items() if d} == {
        "aura_frame_time_ms": "surface",
        "session_outbox_depth": "storability",
    }


def test_the_device_names_are_the_wire_names_not_the_series_names():
    # The route looks the posted name up in DEVICE_HISTOGRAMS/DEVICE_GAUGES, whose keys are
    # the short names; the `van_`-prefixed strings are what they land in.
    assert all(not wire.startswith("van_") for wire in kotlin_metrics())


def test_the_batch_size_does_not_exceed_what_the_route_reads():
    route = APP_ROUTES.read_text(encoding="utf-8")
    limit = int(re.search(r"body\.samples\[:(\d+)\]", route).group(1))
    kotlin = KOTLIN.read_text(encoding="utf-8")
    batch = int(re.search(r"const val BATCH = (\d+)", kotlin).group(1))
    # Over the limit is not an error the device sees. It is telemetry thrown away.
    assert batch <= limit, f"the device batches {batch}, the route reads {limit}"


def kotlin_code(path: Path) -> str:
    """Source with comments removed.

    A commented-out call still contains its own text. Asserting on the raw file would let
    `// telemetry.start()` satisfy "the producer is started", which is the exact shape of
    the defect this finding is about: something that looks present and never runs.
    """
    out, in_block = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if in_block:
            in_block = "*/" not in stripped
            continue
        if stripped.startswith("/*"):
            in_block = "*/" not in stripped
            continue
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        out.append(line.split("//")[0])
    return "\n".join(out)


def test_the_producer_is_actually_wired():
    # The finding was a catalogue and a route with nothing posting to them, so the closure
    # has to assert the caller exists and runs, not just that the code exists.
    app = kotlin_code(ROOT / "android/app/src/main/java/com/dial/van/VanApplication.kt")
    assert "DeviceTelemetryReporter(" in app
    assert "telemetry.start()" in app
    reporter = kotlin_code(REPORTER)
    assert "postDeviceTelemetry" in reporter
    # And that it stands down when the gateway is unreachable, rather than spending the
    # owner's radio on frame times while their commands are queued.
    assert "backgroundCallsAdvisable" in reporter
