"""P3-OBS-002 — the metric set Gate 11 names, in a form something can scrape.

The tests that matter here are the ones about *honesty*, not about arithmetic:
that a metric nobody produces is reported as unproduced rather than as zero, that
a metric nobody declared cannot appear at runtime, and that a label cannot be
built from a value that grows without bound.
"""

from __future__ import annotations

import inspect

import pytest

from van_gateway.observability import instruments
from van_gateway.observability.metrics import (
    CATALOGUE,
    LATENCY_BUCKETS_MS,
    MetricKind,
    MetricSource,
    MetricsRegistry,
    UnknownMetric,
    render_prometheus,
)


@pytest.fixture
def registry() -> MetricsRegistry:
    return MetricsRegistry()


def test_every_metric_is_declared_with_a_named_producer():
    """Declaring a metric is easy; naming who writes it is what makes silence detectable.

    This asserted `len(CATALOGUE) == 16`, which pinned a snapshot rather than a rule and
    had to be edited every time a metric was legitimately added — the same shape as the
    `SCHEMA_VERSION == 27` assertion this programme replaced earlier. The rule is below:
    every metric names a producer, and both blueprint lists are covered.
    """
    for metric in CATALOGUE:
        assert metric.help.strip(), metric.name
        assert metric.produced_by.strip(), metric.name
        assert metric.name.startswith("van_"), metric.name
        if metric.kind is MetricKind.HISTOGRAM:
            assert metric.buckets, f"{metric.name} is a histogram with no buckets"
            assert list(metric.buckets) == sorted(metric.buckets), metric.name


def test_a_metric_nobody_declared_cannot_be_recorded(registry):
    with pytest.raises(UnknownMetric):
        registry.increment("van_something_someone_invented")
    with pytest.raises(UnknownMetric):
        # Right name, wrong kind: a counter recorded as a histogram would render
        # as a series Prometheus cannot parse.
        registry.observe("van_error_total", 1.0)


def test_a_label_set_that_does_not_match_the_declaration_is_refused(registry):
    with pytest.raises(UnknownMetric):
        registry.increment("van_error_total", labels={"error_class": "X"})  # missing code
    with pytest.raises(UnknownMetric):
        registry.increment(
            "van_error_total", labels={"error_class": "X", "code": "y", "extra": "z"}
        )


def test_zero_because_nothing_happened_is_distinguishable_from_never_wired(registry):
    """The whole point. Both render as no samples; only one is a fault."""
    instruments.record_error("AuthError", "denied", registry=registry)
    unobserved = {metric.name for metric in registry.unobserved()}
    assert "van_error_total" not in unobserved
    assert "van_mission_duration_ms" in unobserved

    text = render_prometheus(registry)
    # Declared-but-silent metrics still appear with HELP/TYPE, so a scrape that
    # omits one means a broken exporter rather than an idle subsystem.
    assert "# TYPE van_mission_duration_ms histogram" in text
    assert 'van_metric_unobserved{metric="van_mission_duration_ms"' in text
    assert "van_metric_unobserved{metric=\"van_error_total\"" not in text


def test_both_blueprint_metric_lists_are_covered():
    """Gate 11's sixteen and Rev 1.5 §28.1's Remote Browser set.

    Named rather than counted, so adding a metric does not require editing a number and
    removing one that the blueprint requires fails here rather than silently.
    """
    names = {metric.name for metric in CATALOGUE}
    gate_eleven = {
        "van_gateway_request_duration_ms", "van_mission_duration_ms",
        "van_verifier_duration_ms", "van_hermes_callback_duration_ms",
        "van_queue_depth", "van_browser_task_total", "van_automation_run_total",
        "van_trade_halt_latency_ms", "van_event_bus_lag_ms", "van_wake_latency_ms",
        "van_asr_latency_ms", "van_tts_latency_ms", "van_aura_frame_time_ms",
        "van_device_battery_percent", "van_device_memory_used_mb", "van_error_total",
    }
    remote_browser = {
        "van_browser_session_active", "van_browser_session_connect_ms",
        "van_browser_input_dispatch_ms", "van_browser_control_preempt_ms",
        "van_browser_frame_fps", "van_browser_encode_ms", "van_browser_webrtc_rtt_ms",
        "van_browser_decode_fps", "van_browser_frame_drop_count",
        "van_browser_reconnect_count", "van_browser_last_frame_age_ms",
    }
    assert gate_eleven <= names, sorted(gate_eleven - names)
    assert remote_browser <= names, sorted(remote_browser - names)


def test_every_device_metric_can_actually_be_ingested():
    """The rule behind the old exact-set assertion, and a stronger one.

    A metric declared with `MetricSource.DEVICE` that the ingest route refuses is a metric
    the device can never write — it renders as permanently unobserved, which reads as a
    broken subsystem rather than as a wiring mistake nobody made on purpose.
    """
    ingestible = (
        {name for name, _ in instruments.DEVICE_HISTOGRAMS.values()}
        | set(instruments.DEVICE_GAUGES.values())
        | set(instruments.DEVICE_COUNTERS.values())
    )
    declared = {m.name for m in CATALOGUE if m.source is MetricSource.DEVICE}
    assert declared == ingestible, {
        "declared but not ingestible": sorted(declared - ingestible),
        "ingestible but not declared": sorted(ingestible - declared),
    }


def test_the_gateway_cannot_write_a_stream_host_metric():
    """§28.1 — the gateway does not see a frame and must not be able to report one.

    A scrape that never shows these must read as "there is no stream host", which is true
    today. If the gateway could write them, a zero would be indistinguishable from a
    measurement, and RB-010 would look provisioned.
    """
    stream_host = {m.name for m in CATALOGUE if m.source is MetricSource.STREAM_HOST}
    assert stream_host, "the Remote Browser's host-side metrics are not declared"

    device_ingest = (
        {name for name, _ in instruments.DEVICE_HISTOGRAMS.values()}
        | set(instruments.DEVICE_GAUGES.values())
        | set(instruments.DEVICE_COUNTERS.values())
    )
    assert not (stream_host & device_ingest), "a stream-host metric is writable as device telemetry"

    source = inspect.getsource(instruments)
    for name in stream_host:
        assert name not in source, f"{name} has a gateway-side writer"


def test_a_device_metric_name_nobody_declared_is_refused(registry):
    with pytest.raises(instruments.UnknownDeviceMetric):
        instruments.record_device_sample("cpu_temperature_c", 40.0, registry=registry)


def test_histogram_buckets_are_cumulative_and_end_at_inf(registry):
    for value in (1.0, 30.0, 300.0, 99_999.0):
        instruments.record_request("/v1/commands", "2xx", value, registry=registry)
    text = render_prometheus(registry)
    lines = [l for l in text.splitlines() if l.startswith("van_gateway_request_duration_ms_bucket")]
    counts = [int(line.rsplit(" ", 1)[1]) for line in lines]
    assert counts == sorted(counts), "bucket counts must be cumulative"
    assert counts[-1] == 4
    assert lines[-1].count('le="+Inf"') == 1
    assert f"van_gateway_request_duration_ms_count" in text
    # The 99999 sample lands only in +Inf, so the largest finite bucket holds 3.
    assert counts[len(LATENCY_BUCKETS_MS) - 1] == 3


def test_label_values_are_escaped_so_a_quote_cannot_break_the_scrape(registry):
    instruments.record_error('Weird"Class', "line\nbreak", registry=registry)
    text = render_prometheus(registry)
    assert 'error_class="Weird\\"Class"' in text
    assert "line\\nbreak" in text
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        assert line.count("{") <= 1


def test_a_negative_duration_cannot_drag_a_percentile_down(registry):
    """A clock step can produce one. It is clamped rather than recorded."""
    instruments.record_request("/v1/commands", "2xx", -50.0, registry=registry)
    snapshot = registry.snapshot()["histograms"]["van_gateway_request_duration_ms"]
    series = next(iter(snapshot.values()))
    assert series["sum"] == 0.0
    assert series["count"] == 1


def test_a_non_finite_observation_is_refused(registry):
    with pytest.raises(ValueError):
        registry.observe(
            "van_gateway_request_duration_ms", float("inf"),
            labels={"route": "/x", "result": "2xx"},
        )


def test_only_the_stream_host_instruments_are_allowed_to_be_silent():
    """`silence_is_normal` is an exemption from alerting, so it is fenced by a rule.

    The flag exists for one reason: a Gateway-written instrument that cannot fire without
    a Browser Stream Host, which a deployment may not have. Anything else marked with it
    is an instrument whose disappearance nobody will be told about — which is exactly the
    failure `INSTRUMENT_SILENT` was added to catch. So the set is asserted against the
    property rather than against a list of names, and a new metric joins it only by being
    produced by the interactive browser surface.
    """
    from van_gateway.observability.metrics import CATALOGUE, MetricSource

    exempt = {m.name for m in CATALOGUE if m.silence_is_normal}
    interactive = {
        m.name for m in CATALOGUE
        if m.source is MetricSource.GATEWAY
        and m.produced_by.startswith("van_gateway.observability.instruments.")
        and any(
            token in m.produced_by
            for token in (
                "browser_sessions_active", "browser_connect", "browser_input_dispatch",
                "control_preempt", "agent_grant", "record_download",
            )
        )
    }
    assert exempt == interactive
    # And nothing outside the Gateway carries it: a DEVICE or STREAM_HOST metric is
    # already exempt by source, so marking one would hide that the two mechanisms had
    # drifted apart.
    assert all(
        m.source is MetricSource.GATEWAY for m in CATALOGUE if m.silence_is_normal
    )


def test_an_ordinary_gateway_instrument_still_pages_when_it_goes_quiet():
    """The other half. A filter that exempted too much would pass the test above and
    leave the rule unable to fire at all."""
    from van_gateway.observability.alerts import evaluate
    from van_gateway.observability.metrics import CATALOGUE, MetricsRegistry, MetricSource

    registry = MetricsRegistry()
    firing = {
        alert.rule
        for alert in evaluate(registry=registry, uptime_seconds=5_000, ops_facts={})
    }
    assert "INSTRUMENT_SILENT" in firing
    silent = next(
        alert for alert in evaluate(registry=registry, uptime_seconds=5_000, ops_facts={})
        if alert.rule == "INSTRUMENT_SILENT"
    )
    named = set(silent.detail["silent"])
    assert "van_gateway_request_duration_ms" in named
    assert "van_browser_download_total" not in named
    # Every unobserved GATEWAY metric that is not exempt, and nothing else.
    assert named == {
        m.name for m in CATALOGUE
        if m.source is MetricSource.GATEWAY and not m.silence_is_normal
    }
