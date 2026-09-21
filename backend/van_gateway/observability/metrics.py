"""The metric set Gate 11 names, in a registry something can actually scrape.

P3-OBS-002: metrics were being computed. `automation/telemetry.py` builds ladder
metrics, `attention/scoring.py` builds attention metrics, `reasoning/kernel.py`
builds sycophancy metrics, and the VATI observability package builds trading
metrics. Every one of them is computed on request, returned to the caller that
asked, and then discarded. Nothing aggregates them, nothing exports them, and no
operator outside a Python REPL can see any of them.

Two design choices are worth stating because both were tempting to get wrong.

**The catalogue is closed, and it names a producer for every entry.** Gate 11
lists sixteen metrics. It would have been easy to declare all sixteen, export
them all as zero, and call the gate closed — a dashboard full of green zeros is
indistinguishable from a dashboard full of instruments that were never wired.
So `MetricSource` records where each metric is produced, `Metric.produced_by`
names the module or surface that produces it, and `unobserved()` reports the
declared metrics that have never received a sample. A metric at zero because
nothing happened and a metric at zero because nothing writes it are different
facts and the export distinguishes them.

**Device-produced metrics are ingested, not invented.** Aura frame time, wake
latency, ASR and TTS latency and the battery/memory indicators are produced on
the Android device. The gateway cannot measure them and must not guess them, so
they arrive through `POST /v1/observability/device-telemetry` and are marked
`MetricSource.DEVICE`. Until a device posts, they are honestly unobserved.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping


class MetricKind(str, Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


class MetricSource(str, Enum):
    """Which process produces the samples. Not decoration: it is the difference
    between "the gateway measured zero" and "the gateway cannot measure this"."""

    GATEWAY = "GATEWAY"
    DEVICE = "DEVICE"
    TRADING = "TRADING"
    #: Rev 1.5 §28.1. The Browser Stream Host measures capture, encode and the WebRTC
    #: transport, because it is the only process that can see any of them. Declaring them
    #: with this source rather than GATEWAY is the same distinction this enum exists for,
    #: one host further out: a gateway reporting zero frames per second would be a gateway
    #: claiming to have measured something it has no access to.
    STREAM_HOST = "STREAM_HOST"


#: Latency buckets in milliseconds. Chosen so the interesting boundary for each
#: latency metric falls on a bucket edge rather than inside one: 250ms is the
#: gateway's own budget, 2s is where an owner notices, 30s is where a Hermes run
#: has effectively stalled.
LATENCY_BUCKETS_MS: tuple[float, ...] = (
    5.0, 25.0, 100.0, 250.0, 500.0, 1000.0, 2000.0, 5000.0, 15000.0, 30000.0,
)

#: Frame-time buckets in milliseconds. 16.7 is 60fps and 33.3 is 30fps; the
#: whole question for the aura is which side of those two lines a frame lands on.
FRAME_BUCKETS_MS: tuple[float, ...] = (8.0, 16.7, 33.3, 50.0, 100.0)


@dataclass(frozen=True)
class Metric:
    name: str
    kind: MetricKind
    source: MetricSource
    help: str
    #: The module, route or device surface that writes this metric. A metric with
    #: no producer is a metric nobody can be held to.
    produced_by: str
    unit: str = ""
    buckets: tuple[float, ...] = ()
    labels: tuple[str, ...] = ()
    #: What has to exist before this instrument can produce anything, or "" when a
    #: running gateway must produce it on its own.
    #:
    #: A named component rather than a boolean, because "silence is fine here" is not a
    #: fact about the metric — it is a fact about a *missing* component, and an operator
    #: reading a permanently empty series needs to know which one. The boolean this
    #: replaced said only that nobody would be paged.
    #:
    #: `INSTRUMENT_SILENT` is the rule this feeds, and the distinction is the same one
    #: `MetricSource.DEVICE` already carries: the Gateway does write these, so the source
    #: is right; what it cannot do is write them alone.
    silence_needs: str = ""

    @property
    def silence_is_normal(self) -> bool:
        """Whether `INSTRUMENT_SILENT` should skip this metric."""
        return bool(self.silence_needs)


def _m(name, kind, source, help_, produced_by, unit="", buckets=(), labels=(),
       silence_needs=""):
    return Metric(
        name=name, kind=kind, source=source, help=help_, produced_by=produced_by,
        unit=unit, buckets=buckets, labels=labels, silence_needs=silence_needs,
    )


#: The components a Gateway instrument may be waiting on, and the only values
#: `silence_needs` may take.
#:
#: Closed on purpose. An open string would let the next metric excuse itself from
#: `INSTRUMENT_SILENT` with a sentence nobody checks, which is how an alert that matters
#: gets quietly switched off.
NEEDS_STREAM_HOST = "a Browser Stream Host (§13)"
NEEDS_PAIRED_DEVICE = "a paired owner device driving a logical session (§20)"
SILENCE_REASONS = frozenset({NEEDS_STREAM_HOST, NEEDS_PAIRED_DEVICE})


#: Gate 11's metric list, one entry each, in the blueprint's order.
CATALOGUE: tuple[Metric, ...] = (
    _m("van_gateway_request_duration_ms", MetricKind.HISTOGRAM, MetricSource.GATEWAY,
       "Gateway request latency by route and outcome.",
       "van_gateway.observability.middleware.MetricsMiddleware",
       "milliseconds", LATENCY_BUCKETS_MS, ("route", "result")),
    _m("van_mission_duration_ms", MetricKind.HISTOGRAM, MetricSource.GATEWAY,
       "Wall time from mission creation to a terminal mission state.",
       "van_gateway.mission.service.MissionService.transition",
       "milliseconds", LATENCY_BUCKETS_MS, ("terminal_state",)),
    _m("van_verifier_duration_ms", MetricKind.HISTOGRAM, MetricSource.GATEWAY,
       "Time spent performing an independent postcondition verification.",
       "van_gateway.mission.service.MissionService._perform_verification",
       "milliseconds", LATENCY_BUCKETS_MS, ("kind", "outcome")),
    _m("van_hermes_callback_duration_ms", MetricKind.HISTOGRAM, MetricSource.GATEWAY,
       "Time from Hermes dispatch to the callback that reports the run's result.",
       "van_gateway.observability.instruments.record_hermes_callback",
       "milliseconds", LATENCY_BUCKETS_MS, ("outcome",)),
    _m("van_queue_depth", MetricKind.GAUGE, MetricSource.GATEWAY,
       "Items awaiting work, by queue.",
       "van_gateway.observability.instruments.set_queue_depth", "items", (), ("queue",)),
    _m("van_browser_task_total", MetricKind.COUNTER, MetricSource.GATEWAY,
       "Browser tasks by terminal status.",
       "van_gateway.observability.instruments.record_browser_task", "", (), ("status",)),
    _m("van_automation_run_total", MetricKind.COUNTER, MetricSource.GATEWAY,
       "Automation runs by cache state and outcome.",
       "van_gateway.observability.instruments.record_automation_run", "", (),
       ("cache_state", "outcome")),
    _m("van_trade_halt_latency_ms", MetricKind.HISTOGRAM, MetricSource.TRADING,
       "Time from an owner halt being authorised to the session observing it.",
       "trading.vati.app.cycle (halt observation)", "milliseconds",
       LATENCY_BUCKETS_MS, ()),
    _m("van_event_bus_lag_ms", MetricKind.HISTOGRAM, MetricSource.GATEWAY,
       "Time from an event being published to a subscriber receiving it.",
       "van_gateway.observability.instruments.record_event_lag", "milliseconds",
       LATENCY_BUCKETS_MS, ("topic",)),
    _m("van_wake_latency_ms", MetricKind.HISTOGRAM, MetricSource.DEVICE,
       "Time from wake word detection to the device being ready to listen.",
       "Android device telemetry", "milliseconds", LATENCY_BUCKETS_MS, ()),
    _m("van_asr_latency_ms", MetricKind.HISTOGRAM, MetricSource.DEVICE,
       "Time from end of speech to a final transcript.",
       "Android device telemetry", "milliseconds", LATENCY_BUCKETS_MS, ()),
    _m("van_tts_latency_ms", MetricKind.HISTOGRAM, MetricSource.DEVICE,
       "Time from text being handed to the speech engine to first audio.",
       "Android device telemetry", "milliseconds", LATENCY_BUCKETS_MS, ()),
    _m("van_aura_frame_time_ms", MetricKind.HISTOGRAM, MetricSource.DEVICE,
       "Time to produce one aura frame on the device.",
       "Android device telemetry", "milliseconds", FRAME_BUCKETS_MS, ("surface",)),
    _m("van_device_battery_percent", MetricKind.GAUGE, MetricSource.DEVICE,
       "Device battery level at the time of the last telemetry post.",
       "Android device telemetry", "percent", (), ()),
    _m("van_device_memory_used_mb", MetricKind.GAUGE, MetricSource.DEVICE,
       "Resident memory of the VAN app at the time of the last telemetry post.",
       "Android device telemetry", "megabytes", (), ()),
    _m("van_error_total", MetricKind.COUNTER, MetricSource.GATEWAY,
       "Errors and degraded subsystems, by class and code.",
       "van_gateway.observability.instruments.record_error", "", (),
       ("error_class", "code")),

    # ---- Rev 1.5 §28.1, the Remote Browser -----------------------------------------
    #
    # Split by who can actually measure it. The four the Gateway owns are the four it
    # can see: it holds the session, it mints the grant, it fences the input and it moves
    # the control generation. Everything about pixels and packets belongs to a host that
    # does not exist yet, and is declared STREAM_HOST so a scrape that never shows them
    # reads as "no host" rather than "no traffic".
    _m("van_browser_session_active", MetricKind.GAUGE, MetricSource.GATEWAY,
       "Interactive browser sessions currently in a non-terminal state.",
       "van_gateway.observability.instruments.set_browser_sessions_active",
       "sessions", (), (), silence_needs=NEEDS_STREAM_HOST),
    _m("van_browser_session_connect_ms", MetricKind.HISTOGRAM, MetricSource.GATEWAY,
       "Time from an interactive session being created to its first stream grant.",
       "van_gateway.observability.instruments.record_browser_connect",
       "milliseconds", LATENCY_BUCKETS_MS, (), silence_needs=NEEDS_STREAM_HOST),
    _m("van_browser_input_dispatch_ms", MetricKind.HISTOGRAM, MetricSource.GATEWAY,
       "Time from an input packet being admitted to it being dispatched.",
       "van_gateway.observability.instruments.record_browser_input_dispatch",
       "milliseconds", FRAME_BUCKETS_MS, (), silence_needs=NEEDS_STREAM_HOST),
    _m("van_browser_control_preempt_ms", MetricKind.HISTOGRAM, MetricSource.GATEWAY,
       "Time from an owner preemption to the control generation being invalidated.",
       "van_gateway.observability.instruments.record_control_preempt",
       "milliseconds", FRAME_BUCKETS_MS, (), silence_needs=NEEDS_STREAM_HOST),
    _m("van_browser_agent_grant_total", MetricKind.COUNTER, MetricSource.GATEWAY,
       "Agent grants by the state they ended in, including preemption by the owner.",
       "van_gateway.observability.instruments.record_agent_grant", "", (), ("state",),
       silence_needs=NEEDS_STREAM_HOST),
    _m("van_browser_download_total", MetricKind.COUNTER, MetricSource.GATEWAY,
       "Downloads by the state they reached; QUARANTINED is the one worth watching.",
       "van_gateway.observability.instruments.record_download", "", (), ("state",),
       silence_needs=NEEDS_STREAM_HOST),

    # Rev 1.5 §27 — the quality regime a session is actually in, and §20.10's failover.
    #
    # The Gateway owns these because it owns the decision: it is handed the phone's link
    # observation and picks the rung. Declaring the *mode* rather than the raw link
    # numbers is deliberate — RTT and loss are the device's to report, and a gauge here
    # carrying them would be the Gateway restating a measurement it did not take.
    _m("van_browser_quality_mode", MetricKind.COUNTER, MetricSource.GATEWAY,
       "Quality verdicts by the rung chosen and whether the link was metered.",
       "van_gateway.observability.instruments.record_quality_mode", "", (),
       ("mode", "metered"), silence_needs=NEEDS_STREAM_HOST),
    _m("van_session_failover_total", MetricKind.COUNTER, MetricSource.GATEWAY,
       "Logical-session path failovers by outcome and by whether the route changed.",
       "van_gateway.observability.instruments.record_session_failover", "", (),
       ("outcome", "route_changed"), silence_needs=NEEDS_PAIRED_DEVICE),
    # These two are the device's measurements, not the Gateway's, and saying so is the
    # whole point. The Gateway learns that a failover happened when the resume arrives,
    # which is after the gap the owner experienced; and the store-and-forward queue is on
    # the phone, so a Gateway gauge of its depth would be a number nobody can take.
    #
    # The honest consequence, worth knowing before reading a chart of either: a phone
    # reports these on its next successful post, so the deepest outbox is the one that
    # has not been reported yet. A flat zero means no phone has spoken, not that no
    # phone has work waiting.
    _m("van_session_failover_ms", MetricKind.HISTOGRAM, MetricSource.DEVICE,
       "Owner-visible gap from a path being marked suspect to the new path carrying work.",
       "Android device telemetry", "milliseconds", LATENCY_BUCKETS_MS, ()),
    _m("van_session_outbox_depth", MetricKind.GAUGE, MetricSource.DEVICE,
       "Commands held in store-and-forward, by what the outbox is allowed to do with them.",
       "Android device telemetry", "commands", (), ("storability",)),

    _m("van_browser_frame_fps", MetricKind.GAUGE, MetricSource.STREAM_HOST,
       "Frames per second the stream host is producing for the owner's session.",
       "Browser Stream Host telemetry (RB-010, unprovisioned)", "fps", (), ()),
    _m("van_browser_encode_ms", MetricKind.HISTOGRAM, MetricSource.STREAM_HOST,
       "Time to encode one frame on the stream host.",
       "Browser Stream Host telemetry (RB-010, unprovisioned)", "milliseconds",
       FRAME_BUCKETS_MS, ()),
    _m("van_browser_webrtc_rtt_ms", MetricKind.HISTOGRAM, MetricSource.STREAM_HOST,
       "Round-trip time on the media path between the phone and the stream host.",
       "Browser Stream Host telemetry (RB-010, unprovisioned)", "milliseconds",
       LATENCY_BUCKETS_MS, ()),
    _m("van_browser_webrtc_packet_loss", MetricKind.GAUGE, MetricSource.STREAM_HOST,
       "Fraction of media packets lost, as the stream host observes it.",
       "Browser Stream Host telemetry (RB-010, unprovisioned)", "ratio", (), ()),
    _m("van_browser_turn_relay_ratio", MetricKind.GAUGE, MetricSource.STREAM_HOST,
       "Fraction of sessions relayed through TURN rather than connected directly.",
       "Browser Stream Host telemetry (RB-010, unprovisioned)", "ratio", (), ()),

    _m("van_browser_decode_fps", MetricKind.GAUGE, MetricSource.DEVICE,
       "Frames per second the phone is decoding.",
       "Android device telemetry", "fps", (), ()),
    _m("van_browser_frame_drop_count", MetricKind.COUNTER, MetricSource.DEVICE,
       "Frames the phone received and did not render.",
       "Android device telemetry", "", (), ()),
    _m("van_browser_reconnect_count", MetricKind.COUNTER, MetricSource.DEVICE,
       "Times the phone re-established the media path within one session.",
       "Android device telemetry", "", (), ()),
    _m("van_browser_last_frame_age_ms", MetricKind.GAUGE, MetricSource.DEVICE,
       "Age of the newest frame the phone has drawn; the number behind a frozen picture.",
       "Android device telemetry", "milliseconds", (), ()),
)

BY_NAME: Mapping[str, Metric] = {metric.name: metric for metric in CATALOGUE}


class UnknownMetric(KeyError):
    """Raised when something records a metric that is not in the catalogue.

    Deliberately an error rather than an auto-registration: a metric that appears
    at runtime without a declared producer is exactly the drift this gate exists
    to stop.
    """


def _label_key(metric: Metric, labels: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    given = dict(labels or {})
    missing = [name for name in metric.labels if name not in given]
    extra = [name for name in given if name not in metric.labels]
    if missing or extra:
        raise UnknownMetric(
            f"{metric.name} declares labels {metric.labels}; "
            f"missing={missing} unexpected={extra}"
        )
    return tuple((name, str(given[name])) for name in metric.labels)


@dataclass
class _Histogram:
    buckets: tuple[float, ...]
    counts: list[int] = field(default_factory=list)
    total: float = 0.0
    count: int = 0

    def __post_init__(self) -> None:
        if not self.counts:
            self.counts = [0] * (len(self.buckets) + 1)

    def observe(self, value: float) -> None:
        self.total += value
        self.count += 1
        for index, edge in enumerate(self.buckets):
            if value <= edge:
                self.counts[index] += 1
                return
        self.counts[-1] += 1


class MetricsRegistry:
    """In-process aggregation with a scrape-shaped read.

    Thread-locked rather than async-locked: samples are recorded from request
    handlers, from background tasks and from the scheduler thread, and a lock
    that only works on one event loop would be a lock that silently does nothing
    on the others.
    """

    def __init__(self, catalogue: Iterable[Metric] = CATALOGUE) -> None:
        self._catalogue = {metric.name: metric for metric in catalogue}
        self._lock = threading.Lock()
        self._counters: dict[str, dict[tuple, float]] = {}
        self._gauges: dict[str, dict[tuple, float]] = {}
        self._histograms: dict[str, dict[tuple, _Histogram]] = {}
        self._observed: set[str] = set()

    # -------------------------------------------------------------- recording

    def _metric(self, name: str, kind: MetricKind) -> Metric:
        metric = self._catalogue.get(name)
        if metric is None:
            raise UnknownMetric(f"{name} is not in the Gate 11 metric catalogue")
        if metric.kind is not kind:
            raise UnknownMetric(f"{name} is a {metric.kind.value}, not a {kind.value}")
        return metric

    def increment(self, name: str, *, labels: Mapping[str, str] | None = None,
                  value: float = 1.0) -> None:
        metric = self._metric(name, MetricKind.COUNTER)
        key = _label_key(metric, labels)
        with self._lock:
            series = self._counters.setdefault(name, {})
            series[key] = series.get(key, 0.0) + value
            self._observed.add(name)

    def set_gauge(self, name: str, value: float, *,
                  labels: Mapping[str, str] | None = None) -> None:
        metric = self._metric(name, MetricKind.GAUGE)
        key = _label_key(metric, labels)
        with self._lock:
            self._gauges.setdefault(name, {})[key] = float(value)
            self._observed.add(name)

    def observe(self, name: str, value: float, *,
                labels: Mapping[str, str] | None = None) -> None:
        metric = self._metric(name, MetricKind.HISTOGRAM)
        key = _label_key(metric, labels)
        if not math.isfinite(value):
            raise ValueError(f"{name} observation must be finite, got {value!r}")
        with self._lock:
            series = self._histograms.setdefault(name, {})
            histogram = series.get(key)
            if histogram is None:
                histogram = _Histogram(buckets=metric.buckets)
                series[key] = histogram
            histogram.observe(float(value))
            self._observed.add(name)

    # ----------------------------------------------------------------- reading

    def unobserved(self) -> tuple[Metric, ...]:
        """Declared metrics that have never received a sample in this process."""
        with self._lock:
            observed = set(self._observed)
        return tuple(m for name, m in self._catalogue.items() if name not in observed)

    def snapshot(self) -> dict[str, dict]:
        """A plain-data view, for tests and for the alert evaluator."""
        with self._lock:
            return {
                "counters": {
                    name: {key: value for key, value in series.items()}
                    for name, series in self._counters.items()
                },
                "gauges": {
                    name: {key: value for key, value in series.items()}
                    for name, series in self._gauges.items()
                },
                "histograms": {
                    name: {
                        key: {
                            "buckets": list(histogram.buckets),
                            "counts": list(histogram.counts),
                            "sum": histogram.total,
                            "count": histogram.count,
                        }
                        for key, histogram in series.items()
                    }
                    for name, series in self._histograms.items()
                },
                "observed": sorted(self._observed),
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._observed.clear()


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels_text(pairs: tuple[tuple[str, str], ...], extra: tuple[tuple[str, str], ...] = ()) -> str:
    items = tuple(pairs) + tuple(extra)
    if not items:
        return ""
    body = ",".join(f'{name}="{_escape(value)}"' for name, value in items)
    return "{" + body + "}"


def render_prometheus(registry: MetricsRegistry) -> str:
    """Prometheus text exposition format, version 0.0.4.

    Rendered from the catalogue rather than from the recorded series, so a
    declared metric appears in the scrape with its HELP and TYPE even before
    anything has observed it. A scrape that omits a metric entirely is
    indistinguishable from a scrape of a broken exporter.
    """
    data = registry.snapshot()
    lines: list[str] = []
    for metric in CATALOGUE:
        lines.append(f"# HELP {metric.name} {metric.help}")
        lines.append(f"# TYPE {metric.name} {metric.kind.value}")
        if metric.unit:
            lines.append(f"# UNIT {metric.name} {metric.unit}")
        if metric.kind is MetricKind.COUNTER:
            for key, value in sorted(data["counters"].get(metric.name, {}).items()):
                lines.append(f"{metric.name}{_labels_text(key)} {value:g}")
        elif metric.kind is MetricKind.GAUGE:
            for key, value in sorted(data["gauges"].get(metric.name, {}).items()):
                lines.append(f"{metric.name}{_labels_text(key)} {value:g}")
        else:
            for key, histogram in sorted(data["histograms"].get(metric.name, {}).items()):
                cumulative = 0
                for edge, count in zip(histogram["buckets"], histogram["counts"]):
                    cumulative += count
                    lines.append(
                        f"{metric.name}_bucket"
                        f"{_labels_text(key, (('le', repr(edge)),))} {cumulative}"
                    )
                cumulative += histogram["counts"][-1]
                lines.append(
                    f"{metric.name}_bucket{_labels_text(key, (('le', '+Inf'),))} {cumulative}"
                )
                lines.append(f"{metric.name}_sum{_labels_text(key)} {histogram['sum']:g}")
                lines.append(f"{metric.name}_count{_labels_text(key)} {histogram['count']}")

    # The honesty line. A scraper that alerts on this knows which instruments are
    # declared and silent, which is a different fault from a metric reading zero.
    lines.append("# HELP van_metric_unobserved Declared metrics with no sample in this process.")
    lines.append("# TYPE van_metric_unobserved gauge")
    for metric in registry.unobserved():
        lines.append(
            "van_metric_unobserved"
            f'{{metric="{_escape(metric.name)}",source="{metric.source.value}",'
            f'produced_by="{_escape(metric.produced_by)}"}} 1'
        )
    lines.append("# HELP van_metrics_scrape_unix Unix time the scrape was rendered.")
    lines.append("# TYPE van_metrics_scrape_unix gauge")
    lines.append(f"van_metrics_scrape_unix {int(time.time())}")
    return "\n".join(lines) + "\n"


#: The process-wide registry. A module global because the producers are spread
#: across request handlers, background tasks and the scheduler, and threading one
#: registry object through all of them would be a large diff whose only effect is
#: to make the metric harder to record and therefore less likely to be recorded.
REGISTRY = MetricsRegistry()


__all__ = [
    "CATALOGUE", "BY_NAME", "FRAME_BUCKETS_MS", "LATENCY_BUCKETS_MS", "REGISTRY",
    "Metric", "MetricKind", "MetricSource", "MetricsRegistry", "UnknownMetric",
    "render_prometheus",
]
