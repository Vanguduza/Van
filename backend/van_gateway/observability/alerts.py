"""What counts as an actionable production failure, written down and evaluated.

P3-OBS-003: nothing in the repository defined a threshold for anything, so no
condition could ever page anyone. "Add alerting" usually means writing a YAML
file for a monitoring system nobody has installed; that would have closed the
finding on paper and left VAN exactly as unalertable as before. So the rules are
evaluated here, in process, against the same registry the scrape renders, and
`GET /v1/observability/alerts` returns the ones that are firing right now.

Three rules about the rules:

**Every rule names the operator action.** A threshold with no action is a
notification, not an alert, and an operator who cannot act on a page learns to
ignore pages. `AlertRule.action` is required and there is a test that it is.

**A rule can fire on silence.** `INSTRUMENT_SILENT` fires when a metric the
gateway is supposed to produce has had no sample after the process has been up
long enough to have produced one. This is the failure the other rules cannot
see: an exporter that went blind reports every threshold as healthy.

**Ratios need a floor.** One denied command out of one is a 100% denial rate and
means nothing. Every ratio rule carries `min_samples`, below which it does not
evaluate rather than firing on noise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping

from van_gateway.observability.metrics import REGISTRY, MetricsRegistry


class AlertSeverity(str, Enum):
    #: Owner-visible harm is happening now. Wake someone.
    CRITICAL = "CRITICAL"
    #: Owner-visible harm is imminent or the system has lost an ability it needs.
    WARNING = "WARNING"


@dataclass(frozen=True)
class Alert:
    rule: str
    severity: AlertSeverity
    summary: str
    action: str
    value: float
    threshold: float
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity.value,
            "summary": self.summary,
            "action": self.action,
            "value": self.value,
            "threshold": self.threshold,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AlertRule:
    name: str
    severity: AlertSeverity
    threshold: float
    #: What an operator should do. Required — see the module docstring.
    action: str
    evaluate: Callable[["Signals", "AlertRule"], Alert | None]
    #: Below this many observations the rule does not evaluate at all.
    min_samples: int = 0


def _percentile_ms(histograms: Mapping[tuple, dict], quantile: float) -> tuple[float | None, int]:
    """Upper-bucket-bound estimate of a quantile across every label set.

    Returns the *bucket edge*, not an interpolated value. Interpolating inside a
    bucket invents precision the histogram does not have, and for an alert the
    honest statement is "at least this slow".
    """
    buckets: list[float] = []
    counts: list[int] = []
    total = 0
    for series in histograms.values():
        if not buckets:
            buckets = list(series["buckets"])
            counts = [0] * (len(buckets) + 1)
        for index, value in enumerate(series["counts"]):
            counts[index] += value
        total += series["count"]
    if total == 0:
        return None, 0
    target = quantile * total
    seen = 0
    for index, edge in enumerate(buckets):
        seen += counts[index]
        if seen >= target:
            return edge, total
    return float("inf"), total


class Signals:
    """Everything the rules are allowed to read, in one place.

    Rules take this rather than the registry so an operational fact that is not a
    metric — a certificate expiry, a backup age — can be alerted on with the same
    machinery, and so every rule is testable by constructing one of these.
    """

    def __init__(
        self,
        registry: MetricsRegistry = REGISTRY,
        *,
        uptime_seconds: float = 0.0,
        ops_facts: Mapping[str, float] | None = None,
    ) -> None:
        self.snapshot = registry.snapshot()
        self.registry = registry
        self.uptime_seconds = uptime_seconds
        self.ops_facts = dict(ops_facts or {})

    def counter_total(self, name: str, **match: str) -> float:
        total = 0.0
        for key, value in self.snapshot["counters"].get(name, {}).items():
            labels = dict(key)
            if all(labels.get(k) == v for k, v in match.items()):
                total += value
        return total

    def gauge_max(self, name: str) -> float | None:
        series = self.snapshot["gauges"].get(name, {})
        return max(series.values()) if series else None

    def histogram_count(self, name: str, **match: str) -> int:
        total = 0
        for key, series in self.snapshot["histograms"].get(name, {}).items():
            labels = dict(key)
            if all(labels.get(k) == v for k, v in match.items()):
                total += series["count"]
        return total

    def percentile_ms(self, name: str, quantile: float) -> tuple[float | None, int]:
        return _percentile_ms(self.snapshot["histograms"].get(name, {}), quantile)

    def request_total(self) -> int:
        return self.histogram_count("van_gateway_request_duration_ms")


# ------------------------------------------------------------------ the rules

def _latency_rule(metric: str, label: str):
    def evaluate(signals: Signals, rule: AlertRule) -> Alert | None:
        value, total = signals.percentile_ms(metric, 0.95)
        if value is None or total < rule.min_samples:
            return None
        if value <= rule.threshold:
            return None
        return Alert(
            rule=rule.name, severity=rule.severity,
            summary=f"{label} p95 is at least {value:g}ms over {total} samples",
            action=rule.action, value=value, threshold=rule.threshold,
            detail={"metric": metric, "samples": total},
        )
    return evaluate


def _error_rate(signals: Signals, rule: AlertRule) -> Alert | None:
    requests = signals.request_total()
    if requests < rule.min_samples:
        return None
    errors = signals.counter_total("van_error_total")
    ratio = errors / requests
    if ratio <= rule.threshold:
        return None
    return Alert(
        rule=rule.name, severity=rule.severity,
        summary=f"{errors:g} errors across {requests} requests ({ratio:.0%})",
        action=rule.action, value=ratio, threshold=rule.threshold,
        detail={"errors": errors, "requests": requests},
    )


def _verification_failure_rate(signals: Signals, rule: AlertRule) -> Alert | None:
    total = signals.histogram_count("van_verifier_duration_ms")
    if total < rule.min_samples:
        return None
    failed = signals.histogram_count("van_verifier_duration_ms", outcome="FAILED")
    ratio = failed / total
    if ratio <= rule.threshold:
        return None
    return Alert(
        rule=rule.name, severity=rule.severity,
        summary=f"{failed} of {total} verifications failed ({ratio:.0%})",
        action=rule.action, value=ratio, threshold=rule.threshold,
        detail={"failed": failed, "verified": total},
    )


def _queue_depth(signals: Signals, rule: AlertRule) -> Alert | None:
    depth = signals.gauge_max("van_queue_depth")
    if depth is None or depth <= rule.threshold:
        return None
    return Alert(
        rule=rule.name, severity=rule.severity,
        summary=f"a work queue is {depth:g} items deep",
        action=rule.action, value=depth, threshold=rule.threshold,
    )


def _instrument_silent(signals: Signals, rule: AlertRule) -> Alert | None:
    """Fires on an instrument the gateway owns that has never produced a sample.

    Scoped to `MetricSource.GATEWAY`: a device metric is silent whenever no
    device has posted, which is a normal state for a gateway running with no
    paired device and would make this rule fire forever.
    """
    from van_gateway.observability.metrics import MetricSource

    if signals.uptime_seconds < rule.threshold:
        return None
    silent = sorted(
        metric.name for metric in signals.registry.unobserved()
        if metric.source is MetricSource.GATEWAY
    )
    if not silent:
        return None
    return Alert(
        rule=rule.name, severity=rule.severity,
        summary=f"{len(silent)} gateway instruments have produced no sample",
        action=rule.action, value=float(len(silent)), threshold=rule.threshold,
        detail={"silent": silent, "uptime_seconds": round(signals.uptime_seconds)},
    )


def _ops_fact_below(fact: str, label: str):
    """Fires when an operational fact has fallen below its floor (days remaining)."""
    def evaluate(signals: Signals, rule: AlertRule) -> Alert | None:
        value = signals.ops_facts.get(fact)
        if value is None:
            return None
        if value > rule.threshold:
            return None
        return Alert(
            rule=rule.name, severity=rule.severity,
            summary=f"{label} is at {value:g}, floor is {rule.threshold:g}",
            action=rule.action, value=float(value), threshold=rule.threshold,
            detail={"fact": fact},
        )
    return evaluate


RULES: tuple[AlertRule, ...] = (
    AlertRule(
        name="GATEWAY_LATENCY_BUDGET_BREACHED", severity=AlertSeverity.WARNING,
        threshold=2000.0, min_samples=20,
        action="Check Hermes reachability and SQLite contention; the owner is waiting "
               "more than two seconds for a gateway response.",
        evaluate=_latency_rule("van_gateway_request_duration_ms", "gateway request"),
    ),
    AlertRule(
        name="HERMES_CALLBACK_STALLED", severity=AlertSeverity.CRITICAL,
        threshold=30000.0, min_samples=5,
        action="Hermes is accepting runs and not reporting them. Check the agent runtime "
               "is alive and that its callback can reach the gateway.",
        evaluate=_latency_rule("van_hermes_callback_duration_ms", "Hermes callback"),
    ),
    AlertRule(
        name="TRADE_HALT_LATENCY", severity=AlertSeverity.CRITICAL,
        threshold=5000.0, min_samples=1,
        action="An owner halt took longer than five seconds to reach the trading session. "
               "Verify the session is observing the halt store, then halt at the broker.",
        evaluate=_latency_rule("van_trade_halt_latency_ms", "owner halt"),
    ),
    AlertRule(
        name="ERROR_RATE_HIGH", severity=AlertSeverity.WARNING,
        threshold=0.10, min_samples=20,
        action="Read the van_error_total label breakdown in the scrape to find the "
               "failing class, then the structured logs for that correlation id.",
        evaluate=_error_rate,
    ),
    AlertRule(
        name="VERIFICATION_FAILING", severity=AlertSeverity.CRITICAL,
        threshold=0.25, min_samples=8,
        action="VAN is reporting work it cannot verify as done. Check the verifier's "
               "external dependency before trusting any recent mission outcome.",
        evaluate=_verification_failure_rate,
    ),
    AlertRule(
        name="QUEUE_BACKLOG", severity=AlertSeverity.WARNING, threshold=50.0,
        action="Work is arriving faster than it is being drained. Check the scheduler "
               "is running and that its dispatch target is reachable.",
        evaluate=_queue_depth,
    ),
    AlertRule(
        name="INSTRUMENT_SILENT", severity=AlertSeverity.WARNING, threshold=900.0,
        action="A gateway instrument has produced nothing in fifteen minutes of uptime. "
               "Either that subsystem is not running or its recording was removed — "
               "every other alert reads healthy in both cases.",
        evaluate=_instrument_silent,
    ),
    AlertRule(
        name="PKI_EXPIRING", severity=AlertSeverity.CRITICAL, threshold=30.0,
        action="Re-run deploy/van-trading-core/pki/make-bridge-pki.sh, which re-issues any "
               "certificate inside its renewal window, before commander mTLS and the "
               "MT5 worker link both stop.",
        evaluate=_ops_fact_below("pki_days_remaining", "the soonest PKI expiry, in days"),
    ),
    AlertRule(
        name="BACKUP_STALE", severity=AlertSeverity.CRITICAL, threshold=0.0,
        action="No usable backup is newer than the retention floor. Run "
               "tools/ops/backup.py and confirm the restore drill passes.",
        evaluate=_ops_fact_below("backup_age_within_policy", "backup freshness (1 = within policy)"),
    ),
)


def evaluate(
    registry: MetricsRegistry = REGISTRY,
    *,
    uptime_seconds: float = 0.0,
    ops_facts: Mapping[str, float] | None = None,
    rules: tuple[AlertRule, ...] = RULES,
) -> list[Alert]:
    """Every rule that is firing, criticals first."""
    signals = Signals(registry, uptime_seconds=uptime_seconds, ops_facts=ops_facts)
    firing = [alert for rule in rules if (alert := rule.evaluate(signals, rule)) is not None]
    firing.sort(key=lambda a: (a.severity is not AlertSeverity.CRITICAL, a.rule))
    return firing


__all__ = [
    "RULES", "Alert", "AlertRule", "AlertSeverity", "Signals", "evaluate",
]
