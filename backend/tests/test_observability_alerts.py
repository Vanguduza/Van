"""P3-OBS-003 — thresholds that are evaluated, not written in a YAML file nobody loads.

Each rule is tested from both sides: it fires when the condition holds, and it
stays quiet when it does not. A rule tested only for firing is a rule that fires
on everything, which is the same as no alerting at all.
"""

from __future__ import annotations

import pytest

from van_gateway.observability import instruments
from van_gateway.observability.alerts import RULES, AlertSeverity, evaluate
from van_gateway.observability.metrics import MetricsRegistry


@pytest.fixture
def registry() -> MetricsRegistry:
    return MetricsRegistry()


def _firing(registry, **kwargs) -> set[str]:
    return {alert.rule for alert in evaluate(registry, **kwargs)}


def test_every_rule_names_what_the_operator_should_do():
    """A threshold with no action is a notification, and an operator who cannot
    act on a page learns to ignore pages."""
    assert RULES
    for rule in RULES:
        assert len(rule.action) > 40, rule.name
        assert rule.name.isupper()
        assert rule.severity in (AlertSeverity.CRITICAL, AlertSeverity.WARNING)


def test_a_single_bad_sample_is_not_an_incident(registry):
    """One denied command out of one is a 100% error rate and means nothing."""
    instruments.record_request("/v1/commands", "4xx", 5.0, registry=registry)
    instruments.record_error("AuthError", "denied", registry=registry)
    assert "ERROR_RATE_HIGH" not in _firing(registry)


def test_a_sustained_error_rate_is_an_incident(registry):
    for _ in range(40):
        instruments.record_request("/v1/commands", "2xx", 5.0, registry=registry)
    for _ in range(3):  # 7.5%, under the 10% threshold
        instruments.record_error("AuthError", "denied", registry=registry)
    assert "ERROR_RATE_HIGH" not in _firing(registry)
    for _ in range(3):  # 15%, over it
        instruments.record_error("AuthError", "denied", registry=registry)
    assert "ERROR_RATE_HIGH" in _firing(registry)


def test_gateway_latency_fires_only_past_the_budget(registry):
    for _ in range(25):
        instruments.record_request("/v1/commands", "2xx", 100.0, registry=registry)
    assert "GATEWAY_LATENCY_BUDGET_BREACHED" not in _firing(registry)
    for _ in range(25):
        instruments.record_request("/v1/commands", "2xx", 4000.0, registry=registry)
    assert "GATEWAY_LATENCY_BUDGET_BREACHED" in _firing(registry)


def test_an_owner_halt_that_takes_too_long_is_critical(registry):
    """The most safety-critical number in the system, so its floor is one sample:
    a single slow halt is already the incident."""
    instruments.record_trade_halt_latency(500.0, registry=registry)
    assert "TRADE_HALT_LATENCY" not in _firing(registry)
    instruments.record_trade_halt_latency(20_000.0, registry=registry)
    firing = {alert.rule: alert for alert in evaluate(registry)}
    assert firing["TRADE_HALT_LATENCY"].severity is AlertSeverity.CRITICAL


def test_verification_failing_is_critical_because_van_is_claiming_unverified_work(registry):
    for _ in range(10):
        instruments.record_verification("READ_BACK", "VERIFIED_SUCCESS", 10.0, registry=registry)
    assert "VERIFICATION_FAILING" not in _firing(registry)
    for _ in range(6):
        instruments.record_verification("READ_BACK", "FAILED", 10.0, registry=registry)
    firing = {alert.rule: alert for alert in evaluate(registry)}
    assert firing["VERIFICATION_FAILING"].severity is AlertSeverity.CRITICAL


def test_queue_backlog_uses_the_deepest_queue_not_the_total(registry):
    instruments.set_queue_depth("reminders_due", 10, registry=registry)
    instruments.set_queue_depth("event_backlog", 45, registry=registry)
    assert "QUEUE_BACKLOG" not in _firing(registry)
    instruments.set_queue_depth("event_backlog", 500, registry=registry)
    assert "QUEUE_BACKLOG" in _firing(registry)


def test_an_exporter_that_went_blind_is_itself_an_alert(registry):
    """Every other rule reads healthy when the instruments stopped recording."""
    assert "INSTRUMENT_SILENT" not in _firing(registry, uptime_seconds=60)
    assert "INSTRUMENT_SILENT" in _firing(registry, uptime_seconds=5_000)


def test_silence_on_a_device_metric_is_not_a_fault(registry):
    """A gateway with no paired device has no frame times, forever. Alerting on
    that would be an alert that can never be cleared."""
    for name in (
        "van_gateway_request_duration_ms", "van_mission_duration_ms",
        "van_verifier_duration_ms", "van_hermes_callback_duration_ms",
        "van_event_bus_lag_ms",
    ):
        registry.observe(name, 1.0, labels={
            label: "x" for label in
            {m.name: m.labels for m in __import__(
                "van_gateway.observability.metrics", fromlist=["CATALOGUE"]
            ).CATALOGUE}[name]
        })
    instruments.set_queue_depth("q", 1, registry=registry)
    instruments.record_browser_task("COMPLETED", registry=registry)
    instruments.record_automation_run("HOT", "ok", registry=registry)
    instruments.record_error("X", "y", registry=registry)
    # Every DEVICE metric is still unobserved, and the rule does not fire.
    assert registry.unobserved()
    assert "INSTRUMENT_SILENT" not in _firing(registry, uptime_seconds=5_000)


def test_pki_expiry_pages_before_the_outage_not_on_the_day(registry):
    assert "PKI_EXPIRING" not in _firing(registry, ops_facts={"pki_days_remaining": 90})
    assert "PKI_EXPIRING" in _firing(registry, ops_facts={"pki_days_remaining": 29})
    # A missing certificate reports as -1, which is more urgent than any expiry.
    assert "PKI_EXPIRING" in _firing(registry, ops_facts={"pki_days_remaining": -1})


def test_a_fact_that_is_not_knowable_does_not_fire(registry):
    """A deployment with no trading PKI is not a deployment whose PKI expired."""
    assert _firing(registry, ops_facts={}) == set()


def test_criticals_are_reported_first(registry):
    for _ in range(25):
        instruments.record_request("/v1/commands", "2xx", 4000.0, registry=registry)
    instruments.record_trade_halt_latency(20_000.0, registry=registry)
    firing = evaluate(registry, ops_facts={"pki_days_remaining": 1})
    severities = [alert.severity for alert in firing]
    assert severities == sorted(severities, key=lambda s: s is not AlertSeverity.CRITICAL)
