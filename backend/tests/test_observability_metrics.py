"""P3-OBS-002 — the metric set Gate 11 names, in a form something can scrape.

The tests that matter here are the ones about *honesty*, not about arithmetic:
that a metric nobody produces is reported as unproduced rather than as zero, that
a metric nobody declared cannot appear at runtime, and that a label cannot be
built from a value that grows without bound.
"""

from __future__ import annotations

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


def test_every_blueprint_metric_is_declared_with_a_named_producer():
    """Gate 11 lists sixteen metrics. Declaring them is easy; naming who writes
    each one is what makes an undeclared silence detectable."""
    assert len(CATALOGUE) == 16
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


def test_device_produced_metrics_are_marked_as_such():
    """The gateway cannot measure a frame time and must not pretend to."""
    device = {m.name for m in CATALOGUE if m.source is MetricSource.DEVICE}
    assert device == {
        "van_wake_latency_ms", "van_asr_latency_ms", "van_tts_latency_ms",
        "van_aura_frame_time_ms", "van_device_battery_percent",
        "van_device_memory_used_mb",
    }


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
