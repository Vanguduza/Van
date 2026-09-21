"""The recording side of the metric catalogue.

Every function here takes already-typed arguments and builds the label set
itself, so a call site cannot produce a label error. That matters: the
alternative is a bare `REGISTRY.increment(name, labels={...})` at each call site,
where a typo raises `UnknownMetric` *inside the owner's command path*. Metrics
must never be able to fail a command, and the way to get that is to make the
mistake impossible rather than to wrap every recording in `try/except` — a
swallowed metric error is how an exporter goes quietly blind.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from van_gateway.observability.metrics import REGISTRY, MetricsRegistry


def _clean(value: object, *, fallback: str = "unknown") -> str:
    text = str(getattr(value, "value", value) if value is not None else "").strip()
    return text or fallback


@contextmanager
def timed() -> Iterator[list]:
    """Yields a one-element list that receives the elapsed milliseconds.

    A monotonic clock, not `time.time()`: a wall-clock step (NTP, a suspend)
    produces a negative duration, and a negative latency sample is worse than no
    sample because it silently drags a percentile down.
    """
    started = time.monotonic()
    box: list = [0.0]
    try:
        yield box
    finally:
        box[0] = (time.monotonic() - started) * 1000.0


def record_request(route: str, result: str, duration_ms: float,
                   registry: MetricsRegistry = REGISTRY) -> None:
    registry.observe(
        "van_gateway_request_duration_ms", max(duration_ms, 0.0),
        labels={"route": _clean(route, fallback="unrouted"), "result": _clean(result)},
    )


def record_mission_duration(terminal_state: object, duration_ms: float,
                            registry: MetricsRegistry = REGISTRY) -> None:
    registry.observe(
        "van_mission_duration_ms", max(duration_ms, 0.0),
        labels={"terminal_state": _clean(terminal_state)},
    )


def record_verification(kind: object, outcome: object, duration_ms: float,
                        registry: MetricsRegistry = REGISTRY) -> None:
    registry.observe(
        "van_verifier_duration_ms", max(duration_ms, 0.0),
        labels={"kind": _clean(kind), "outcome": _clean(outcome)},
    )


def record_hermes_callback(outcome: object, duration_ms: float,
                           registry: MetricsRegistry = REGISTRY) -> None:
    registry.observe(
        "van_hermes_callback_duration_ms", max(duration_ms, 0.0),
        labels={"outcome": _clean(outcome)},
    )


def set_queue_depth(queue: str, depth: int, registry: MetricsRegistry = REGISTRY) -> None:
    registry.set_gauge("van_queue_depth", max(int(depth), 0), labels={"queue": _clean(queue)})


def record_browser_task(status: object, registry: MetricsRegistry = REGISTRY) -> None:
    registry.increment("van_browser_task_total", labels={"status": _clean(status)})


def record_automation_run(cache_state: object, outcome: object,
                          registry: MetricsRegistry = REGISTRY) -> None:
    registry.increment(
        "van_automation_run_total",
        labels={"cache_state": _clean(cache_state), "outcome": _clean(outcome)},
    )


def record_trade_halt_latency(duration_ms: float, registry: MetricsRegistry = REGISTRY) -> None:
    registry.observe("van_trade_halt_latency_ms", max(duration_ms, 0.0))


def record_event_lag(topic: object, lag_ms: float, registry: MetricsRegistry = REGISTRY) -> None:
    registry.observe("van_event_bus_lag_ms", max(lag_ms, 0.0), labels={"topic": _clean(topic)})


def record_error(error_class: object, code: object, registry: MetricsRegistry = REGISTRY) -> None:
    registry.increment(
        "van_error_total",
        labels={"error_class": _clean(error_class), "code": _clean(code, fallback="none")},
    )


# ------------------------------------------------- Rev 1.5 §28.1, the Remote Browser
#
# Only the ones the Gateway can actually see. Capture, encode and WebRTC belong to the
# Stream Host and are declared with `MetricSource.STREAM_HOST`, so a scrape that never
# shows them reads as "no host" rather than "no traffic" — which is the difference
# between a system that is idle and one that was never built.


def set_browser_sessions_active(count: int, registry: MetricsRegistry = REGISTRY) -> None:
    registry.set_gauge("van_browser_session_active", max(int(count), 0))


def record_browser_connect(duration_ms: float, registry: MetricsRegistry = REGISTRY) -> None:
    """Session created to first stream grant. Not "time to first frame".

    The Gateway does not see a frame, and naming this metric as if it did would make a
    green dashboard for a session the owner is staring at a black rectangle in.
    """
    registry.observe("van_browser_session_connect_ms", max(duration_ms, 0.0))


def record_browser_input_dispatch(duration_ms: float, registry: MetricsRegistry = REGISTRY) -> None:
    registry.observe("van_browser_input_dispatch_ms", max(duration_ms, 0.0))


def record_control_preempt(duration_ms: float, registry: MetricsRegistry = REGISTRY) -> None:
    """§26 gives owner takeover acknowledgement a 100ms target.

    Worth its own metric rather than a log line: this is the number that says whether
    "Take over" felt instant, and the owner's judgement of the whole feature rests on it.
    """
    registry.observe("van_browser_control_preempt_ms", max(duration_ms, 0.0))


def record_agent_grant(state: object, registry: MetricsRegistry = REGISTRY) -> None:
    registry.increment("van_browser_agent_grant_total", labels={"state": _clean(state)})


def record_download(state: object, registry: MetricsRegistry = REGISTRY) -> None:
    registry.increment("van_browser_download_total", labels={"state": _clean(state)})


def record_quality_mode(mode: object, *, metered: bool,
                        registry: MetricsRegistry = REGISTRY) -> None:
    """§27 — which rung a session was put on, and under which ceiling.

    `metered` is a label rather than a separate metric because the question an operator
    asks is "how often does a mobile session end up in SURVIVAL", and that is one series
    with two labels rather than two series that have to be joined.
    """
    registry.increment(
        "van_browser_quality_mode",
        labels={"mode": _clean(mode), "metered": "true" if metered else "false"},
    )


def record_session_failover(outcome: object, *, route_changed: bool,
                            registry: MetricsRegistry = REGISTRY) -> None:
    """§20.10 — a path switch completed, or did not.

    `route_changed` is the label that matters: failing over to another carrier on the road
    that just broke is the most common way a failover changes nothing, and a counter that
    did not distinguish them would report recovery for a session that is still down.
    """
    registry.increment(
        "van_session_failover_total",
        labels={
            "outcome": _clean(outcome),
            "route_changed": "true" if route_changed else "false",
        },
    )


@dataclass(frozen=True)
class DeviceMetric:
    """One device-produced series, and the single dimension it may carry.

    One dimension, not an open label set. A device that could name its own labels could
    make the cardinality of a series a function of what it decided to send, and the first
    symptom is a scrape that takes a minute.

    `dimension_default` is the value used when the device posts nothing for the label. An
    empty default means the sample is refused instead: `aura_frame_time_ms` without a
    surface is still a frame time and `overlay` is the honest guess, but an outbox depth
    without a storability is a number with no meaning, and recording it under `unknown`
    would put a queue of approval-bearing commands into the same bucket as a retry queue.
    """

    metric: str
    dimension: str = ""
    dimension_default: str = ""


#: Device-produced metrics, keyed by the name the device posts. Closed on purpose:
#: a device that posts a name not in here is reporting something nobody declared,
#: and the ingest route refuses it rather than inventing a series.
DEVICE_HISTOGRAMS: dict[str, DeviceMetric] = {
    "wake_latency_ms": DeviceMetric("van_wake_latency_ms"),
    "asr_latency_ms": DeviceMetric("van_asr_latency_ms"),
    "tts_latency_ms": DeviceMetric("van_tts_latency_ms"),
    "aura_frame_time_ms": DeviceMetric("van_aura_frame_time_ms", "surface", "overlay"),
    # §20.16 — the owner-visible interruption, which only the device can measure. The
    # Gateway learns a failover happened when the resume arrives; by then the gap the
    # owner actually experienced is already over and nothing server-side saw its start.
    "session_failover_ms": DeviceMetric("van_session_failover_ms"),
}

DEVICE_GAUGES: dict[str, DeviceMetric] = {
    "battery_percent": DeviceMetric("van_device_battery_percent"),
    "memory_used_mb": DeviceMetric("van_device_memory_used_mb"),
    # §28.1's Android half. `last_frame_age_ms` is the number behind a frozen picture,
    # which is the failure §7 names and the one an owner cannot describe any other way.
    "browser_decode_fps": DeviceMetric("van_browser_decode_fps"),
    "browser_last_frame_age_ms": DeviceMetric("van_browser_last_frame_age_ms"),
    # §20.15 — the store-and-forward queue, which lives on the phone.
    "session_outbox_depth": DeviceMetric(
        "van_session_outbox_depth", "storability", "",
    ),
}

#: Device counters. Separate from gauges because a dropped frame accumulates and a decode
#: rate does not, and rendering one as the other produces a chart that means nothing.
DEVICE_COUNTERS: dict[str, DeviceMetric] = {
    "browser_frame_drop_count": DeviceMetric("van_browser_frame_drop_count"),
    "browser_reconnect_count": DeviceMetric("van_browser_reconnect_count"),
}


#: Every device table, in the order the ingest tries them. One place, so that a caller
#: asking "what can a device write" cannot get an answer that is a table out of date.
DEVICE_TABLES: tuple[dict[str, DeviceMetric], ...] = (
    DEVICE_HISTOGRAMS, DEVICE_COUNTERS, DEVICE_GAUGES,
)


def ingestible_metrics() -> set[str]:
    """The catalogue series a device can actually write."""
    return {declared.metric for table in DEVICE_TABLES for declared in table.values()}


class UnknownDeviceMetric(ValueError):
    pass


class DeviceDimensionMissing(ValueError):
    """A sample for a labelled series that carried no value for the label."""


def record_device_sample(name: str, value: float, *, surface: str | None = None,
                         dimension: str | None = None,
                         registry: MetricsRegistry = REGISTRY) -> str:
    """Ingest one device-produced sample. Returns the catalogue metric it landed in.

    `surface` is kept as its own argument rather than folded into `dimension` because it
    is already on the wire and posted by shipped devices; a rename here would silently
    drop the aura surface label from every phone that had not been updated.
    """
    recorders = (
        lambda m, v, l: registry.observe(m, max(v, 0.0), labels=l),
        lambda m, v, l: registry.increment(m, value=max(v, 0.0), labels=l),
        lambda m, v, l: registry.set_gauge(m, v, labels=l),
    )
    for table, record in zip(DEVICE_TABLES, recorders):
        declared = table.get(name)
        if declared is None:
            continue
        labels = None
        if declared.dimension:
            posted = surface if declared.dimension == "surface" else dimension
            resolved = _clean(posted, fallback=declared.dimension_default)
            if not resolved:
                raise DeviceDimensionMissing(f"{name} requires {declared.dimension}")
            labels = {declared.dimension: resolved}
        record(declared.metric, float(value), labels)
        return declared.metric
    raise UnknownDeviceMetric(name)


__all__ = [
    "DEVICE_COUNTERS", "DEVICE_GAUGES", "DEVICE_HISTOGRAMS", "DeviceDimensionMissing",
    "DEVICE_TABLES", "DeviceMetric", "UnknownDeviceMetric", "ingestible_metrics",
    "record_automation_run",
    "record_browser_task", "record_device_sample", "record_error", "record_event_lag",
    "record_quality_mode", "record_session_failover",
    "record_hermes_callback", "record_mission_duration", "record_request",
    "record_trade_halt_latency", "record_verification", "set_queue_depth", "timed",
]
