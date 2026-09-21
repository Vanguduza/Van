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


#: Device-produced metrics, keyed by the name the device posts. Closed on purpose:
#: a device that posts a name not in here is reporting something nobody declared,
#: and the ingest route refuses it rather than inventing a series.
DEVICE_HISTOGRAMS: dict[str, tuple[str, tuple[str, ...]]] = {
    "wake_latency_ms": ("van_wake_latency_ms", ()),
    "asr_latency_ms": ("van_asr_latency_ms", ()),
    "tts_latency_ms": ("van_tts_latency_ms", ()),
    "aura_frame_time_ms": ("van_aura_frame_time_ms", ("surface",)),
}

DEVICE_GAUGES: dict[str, str] = {
    "battery_percent": "van_device_battery_percent",
    "memory_used_mb": "van_device_memory_used_mb",
}


class UnknownDeviceMetric(ValueError):
    pass


def record_device_sample(name: str, value: float, *, surface: str | None = None,
                         registry: MetricsRegistry = REGISTRY) -> str:
    """Ingest one device-produced sample. Returns the catalogue metric it landed in."""
    if name in DEVICE_HISTOGRAMS:
        metric, labels = DEVICE_HISTOGRAMS[name]
        label_values = {"surface": _clean(surface, fallback="overlay")} if labels else None
        registry.observe(metric, max(float(value), 0.0), labels=label_values)
        return metric
    if name in DEVICE_GAUGES:
        metric = DEVICE_GAUGES[name]
        registry.set_gauge(metric, float(value))
        return metric
    raise UnknownDeviceMetric(name)


__all__ = [
    "DEVICE_GAUGES", "DEVICE_HISTOGRAMS", "UnknownDeviceMetric", "record_automation_run",
    "record_browser_task", "record_device_sample", "record_error", "record_event_lag",
    "record_hermes_callback", "record_mission_duration", "record_request",
    "record_trade_halt_latency", "record_verification", "set_queue_depth", "timed",
]
