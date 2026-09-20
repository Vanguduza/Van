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
    ingestible = instruments.ingestible_metrics()
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

    device_ingest = instruments.ingestible_metrics()
    assert not (stream_host & device_ingest), "a stream-host metric is writable as device telemetry"

    source = inspect.getsource(instruments)
    for name in stream_host:
        assert name not in source, f"{name} has a gateway-side writer"


def test_a_device_metric_name_nobody_declared_is_refused(registry):
    with pytest.raises(instruments.UnknownDeviceMetric):
        instruments.record_device_sample("cpu_temperature_c", 40.0, registry=registry)


def test_a_labelled_device_sample_without_its_label_is_refused_not_bucketed(registry):
    """§20.15 — an outbox depth with no storability is a number with no meaning.

    The tempting alternative is to record it under `unknown`, which puts a queue of
    approval-bearing commands in the same bucket as a retry queue. An operator reading
    that series would be told the opposite of what is true, and no error would exist
    anywhere to lead them back to it.
    """
    with pytest.raises(instruments.DeviceDimensionMissing):
        instruments.record_device_sample("session_outbox_depth", 3.0, registry=registry)


def test_a_labelled_device_sample_lands_under_the_label_the_catalogue_declares(registry):
    instruments.record_device_sample(
        "session_outbox_depth", 3.0, dimension="REQUIRE_RECONFIRM_ON_RECONNECT",
        registry=registry,
    )
    text = render_prometheus(registry)
    assert 'storability="REQUIRE_RECONFIRM_ON_RECONNECT"' in text
    assert "van_session_outbox_depth" in text


def test_the_aura_surface_still_comes_from_its_own_field(registry):
    """The two dimension slots are not interchangeable.

    `surface` is on the wire and shipped devices post it. A refactor that folded it into
    the generic slot would drop the label from every phone that had not been updated, and
    the symptom would be one merged series rather than an error.
    """
    instruments.record_device_sample(
        "aura_frame_time_ms", 16.0, surface="overlay", registry=registry,
    )
    assert 'surface="overlay"' in render_prometheus(registry)


def test_an_unlabelled_device_metric_ignores_a_dimension_it_did_not_declare(registry):
    """A device sending a label nobody declared does not get a second series for it."""
    instruments.record_device_sample(
        "battery_percent", 73.0, dimension="nonsense", registry=registry,
    )
    text = render_prometheus(registry)
    assert "van_device_battery_percent 73" in text
    assert "nonsense" not in text


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


def test_every_exempt_instrument_names_a_component_that_is_missing():
    """`silence_needs` is an exemption from alerting, so it is fenced by a rule.

    The field replaced a boolean, and the reason is that "silence is fine here" was never
    a fact about the metric: it is a fact about a component the deployment does not have.
    An operator reading a permanently empty series needs to know which one, and a boolean
    could not tell them.

    The set of reasons is closed. An open string would let the next metric excuse itself
    from `INSTRUMENT_SILENT` with a sentence nobody checks, which is how an alert that
    matters gets quietly switched off.
    """
    from van_gateway.observability.metrics import CATALOGUE, SILENCE_REASONS, MetricSource

    exempt = [m for m in CATALOGUE if m.silence_is_normal]
    assert exempt, "the exemption exists and something uses it"
    for metric in exempt:
        assert metric.silence_needs in SILENCE_REASONS, (metric.name, metric.silence_needs)
        # Only a Gateway metric needs the exemption: DEVICE and STREAM_HOST are already
        # excluded by source, and marking one would mean the two mechanisms had drifted.
        assert metric.source is MetricSource.GATEWAY, metric.name


def test_nothing_the_gateway_produces_alone_is_exempt():
    """The other direction: an instrument a running gateway must produce cannot excuse
    itself.

    Asserted by naming the ones that would be most tempting to silence — the request,
    mission and error instruments are noisy and always populated, and an exemption on any
    of them would turn the silence rule off for the subsystems it exists to watch.
    """
    from van_gateway.observability.metrics import CATALOGUE

    by_name = {m.name: m for m in CATALOGUE}
    for name in (
        "van_gateway_request_duration_ms",
        "van_mission_duration_ms",
        "van_error_total",
        "van_verifier_duration_ms",
        "van_event_bus_lag_ms",
    ):
        assert not by_name[name].silence_is_normal, name


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
