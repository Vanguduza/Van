"""TRD-REV51-091 provider registry / quota scheduler, and TRD-REV51-132
model handoff continuity.

Both packets exist to hold one sentence: the hierarchy is availability
routing, and a fallback may never relax controls (INV-MODEL-001).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from vati.cognition.contracts import ModelRole
from vati.cognition.handoff import (
    ContinuityState,
    HandoffReason,
    HandoffRecorder,
    HandoffRefused,
)
from vati.cognition.providers import (
    CONTROL_PROFILE,
    FAILURE_COOLDOWN_THRESHOLD,
    HIERARCHY,
    ModelProvider,
    ProviderRegistry,
    ProviderState,
    QuotaScheduler,
    RegistryError,
    default_registry,
)
from vati.core.events import EventKind
from vati.core.ledger import Ledger

HOUR = 3_600_000


def _sched(**over) -> QuotaScheduler:
    return QuotaScheduler(default_registry())


# --------------------------------------------------------------- 091 registry
def test_the_default_registry_fills_every_rung_in_order():
    reg = default_registry()
    reg.validate_complete()
    assert [p.role for p in reg] == list(HIERARCHY)
    assert [p.model_id for p in reg] == ["fable-5.1", "gpt-6-astra", "claude-opus-5", "gpt-5.6-sol"]


def test_a_provider_declaring_its_own_control_profile_is_refused():
    """The registry will not store per-provider controls, so the cheap rung
    cannot quietly acquire a looser leash."""
    with pytest.raises(RegistryError) as e:
        ProviderRegistry([ModelProvider("cheap-model", ModelRole.FINAL_FALLBACK,
                                        max_requests_per_window=10, window_ms=HOUR,
                                        control_profile="relaxed/1.0")])
    assert "INV-MODEL-001" in str(e.value)


def test_every_registered_provider_reports_the_same_control_profile():
    assert {p.control_profile for p in default_registry()} == {CONTROL_PROFILE}


def test_two_models_cannot_share_a_rung():
    reg = default_registry()
    with pytest.raises(RegistryError):
        reg.register(ModelProvider("another-primary", ModelRole.PRIMARY,
                                   max_requests_per_window=1, window_ms=HOUR))


def test_an_incomplete_hierarchy_is_named_at_startup_not_at_use():
    reg = ProviderRegistry([ModelProvider("only", ModelRole.PRIMARY,
                                          max_requests_per_window=1, window_ms=HOUR)])
    with pytest.raises(RegistryError) as e:
        reg.validate_complete()
    assert "FINAL_FALLBACK" in str(e.value)


def test_an_empty_quota_window_is_refused():
    with pytest.raises(RegistryError):
        ProviderRegistry([ModelProvider("m", ModelRole.PRIMARY,
                                        max_requests_per_window=0, window_ms=HOUR)])


# -------------------------------------------------------------- 091 scheduling
def test_the_primary_is_chosen_while_it_is_available():
    s = _sched()
    lease = s.acquire(now_ms=0)
    assert lease is not None and lease.role is ModelRole.PRIMARY and lease.attempt == 1
    assert not lease.is_fallback


def test_exhausting_a_rung_moves_to_the_next_one_not_to_an_error():
    s = QuotaScheduler(ProviderRegistry([
        ModelProvider("a", ModelRole.PRIMARY, max_requests_per_window=1, window_ms=HOUR),
        ModelProvider("b", ModelRole.FIRST_FALLBACK, max_requests_per_window=1, window_ms=HOUR),
    ]))
    first = s.acquire(now_ms=0)
    s.release(first, ok=True, now_ms=10)
    second = s.acquire(now_ms=20)
    assert first.model_id == "a" and second.model_id == "b"
    assert s.state("a", 20) is ProviderState.QUOTA_EXHAUSTED


def test_every_rung_exhausted_returns_none_rather_than_raising():
    """None is how the system says 'no cognition this cycle'. The caller
    answers it with a sealed abstention and the deterministic path stands."""
    s = QuotaScheduler(ProviderRegistry([
        ModelProvider("a", ModelRole.PRIMARY, max_requests_per_window=1, window_ms=HOUR),
    ]))
    s.release(s.acquire(now_ms=0), ok=True, now_ms=1)
    assert s.acquire(now_ms=2) is None


def test_the_quota_window_rolls_and_the_primary_returns():
    s = QuotaScheduler(ProviderRegistry([
        ModelProvider("a", ModelRole.PRIMARY, max_requests_per_window=1, window_ms=1_000),
        ModelProvider("b", ModelRole.FIRST_FALLBACK, max_requests_per_window=5, window_ms=1_000),
    ]))
    s.release(s.acquire(now_ms=0), ok=True, now_ms=1)
    assert s.acquire(now_ms=10).model_id == "b"
    assert s.acquire(now_ms=5_000).model_id == "a"


def test_concurrency_is_respected_and_released():
    s = QuotaScheduler(ProviderRegistry([
        ModelProvider("a", ModelRole.PRIMARY, max_requests_per_window=10, window_ms=HOUR, max_concurrent=1),
        ModelProvider("b", ModelRole.FIRST_FALLBACK, max_requests_per_window=10, window_ms=HOUR),
    ]))
    held = s.acquire(now_ms=0)
    assert s.acquire(now_ms=1).model_id == "b"
    s.release(held, ok=True, now_ms=2)
    assert s.acquire(now_ms=3).model_id == "a"


def test_consecutive_failures_rest_a_provider():
    s = QuotaScheduler(ProviderRegistry([
        ModelProvider("a", ModelRole.PRIMARY, max_requests_per_window=50, window_ms=HOUR, cooldown_ms=60_000),
        ModelProvider("b", ModelRole.FIRST_FALLBACK, max_requests_per_window=50, window_ms=HOUR),
    ]))
    for i in range(FAILURE_COOLDOWN_THRESHOLD):
        s.release(s.acquire(now_ms=i), ok=False, now_ms=i)
    assert s.state("a", 100) is ProviderState.COOLING_DOWN
    assert s.acquire(now_ms=100).model_id == "b"
    assert s.state("a", 100 + 60_000) is ProviderState.AVAILABLE


def test_a_success_clears_the_failure_streak():
    s = QuotaScheduler(ProviderRegistry([
        ModelProvider("a", ModelRole.PRIMARY, max_requests_per_window=50, window_ms=HOUR),
    ]))
    s.release(s.acquire(now_ms=0), ok=False, now_ms=1)
    s.release(s.acquire(now_ms=2), ok=True, now_ms=3)
    s.release(s.acquire(now_ms=4), ok=False, now_ms=5)
    assert s.state("a", 6) is ProviderState.AVAILABLE


def test_a_late_answer_counts_as_a_failure():
    s = QuotaScheduler(ProviderRegistry([
        ModelProvider("a", ModelRole.PRIMARY, max_requests_per_window=50,
                      window_ms=HOUR, latency_budget_ms=1_000),
    ]))
    lease = s.acquire(now_ms=0)
    s.release(lease, ok=True, now_ms=5_000)     # answered, but past its deadline
    assert s.snapshot(now_ms=5_000)["providers"][0]["total_failures"] == 1


def test_every_lease_carries_the_one_control_profile():
    s = _sched()
    leases = []
    for model in ("fable-5.1", "gpt-6-astra", "claude-opus-5"):
        lease = s.acquire(now_ms=0)
        leases.append(lease)
        s.disable(lease.model_id)
    assert {l.control_profile for l in leases} == {CONTROL_PROFILE}


# ----------------------------------------------------------------- 132 handoff
def _two_leases():
    s = _sched()
    first = s.acquire(now_ms=0)
    s.disable(first.model_id)
    return s, first, s.acquire(now_ms=1)


def test_a_handoff_carries_continuity_rather_than_restarting():
    _, first, second = _two_leases()
    rec = HandoffRecorder()
    cont = ContinuityState(context_hash="ctx-1", prior_assessment_seals=("seal-a",),
                           open_mission_ids=("m1",), spent_micros=400, invocations=1)
    h = rec.record(previous=first, nxt=second, reason=HandoffReason.DISABLED,
                   continuity=cont, now_ms=10)
    assert h.seal_ok() and h.descended
    assert h.continuity.open_mission_ids == ("m1",)
    assert h.continuity.spent_micros == 400


def test_continuity_advances_without_losing_what_came_before():
    c = ContinuityState(context_hash="ctx").advanced(assessment_seal="s1", spent_micros=10)
    c = c.advanced(assessment_seal="s2", mission_ids=("m1",), spent_micros=15)
    assert c.prior_assessment_seals == ("s1", "s2")
    assert c.spent_micros == 25 and c.invocations == 2


def test_the_budget_does_not_reset_by_changing_model():
    """The spend is on the context, not on the rung. A fallback that reset it
    would give the cheapest model the largest allowance."""
    c = ContinuityState(context_hash="ctx", spent_micros=900)
    _, first, second = _two_leases()
    h = HandoffRecorder().record(previous=first, nxt=second,
                                 reason=HandoffReason.BUDGET_EXHAUSTED,
                                 continuity=c, now_ms=1)
    assert h.continuity.spent_micros == 900


def test_a_handoff_that_would_change_the_control_profile_is_refused():
    _, first, second = _two_leases()
    relaxed = type(second)(**{**second.__dict__, "control_profile": "relaxed/1.0"})
    with pytest.raises(HandoffRefused) as e:
        HandoffRecorder().record(previous=first, nxt=relaxed, reason=HandoffReason.TIMEOUT,
                                 continuity=ContinuityState(context_hash="ctx"), now_ms=1)
    assert "control profile" in str(e.value)


def test_a_handoff_to_itself_is_refused():
    s = _sched()
    lease = s.acquire(now_ms=0)
    with pytest.raises(HandoffRefused):
        HandoffRecorder().record(previous=lease, nxt=lease, reason=HandoffReason.TIMEOUT,
                                 continuity=ContinuityState(context_hash="ctx"), now_ms=1)


def test_a_handoff_with_no_context_is_refused():
    _, first, second = _two_leases()
    with pytest.raises(HandoffRefused):
        HandoffRecorder().record(previous=first, nxt=second, reason=HandoffReason.TIMEOUT,
                                 continuity=ContinuityState(context_hash=""), now_ms=1)


def test_handoffs_are_ledgered_against_the_context_for_replay():
    led = Ledger(":memory:")
    _, first, second = _two_leases()
    rec = HandoffRecorder(ledger=led)
    rec.record(previous=first, nxt=second, reason=HandoffReason.QUOTA_EXHAUSTED,
               continuity=ContinuityState(context_hash="ctx-9"), now_ms=3)
    assert led.count(EventKind.MODEL_HANDOFF) == 1
    assert [e.correlation_id for e in led.iter(EventKind.MODEL_HANDOFF)] == ["ctx-9"]
    assert led.verify_chain()[0]


def test_the_chain_for_one_context_is_recoverable_in_order():
    s = _sched()
    rec = HandoffRecorder()
    cont = ContinuityState(context_hash="ctx-c")
    prev = s.acquire(now_ms=0)
    for reason in (HandoffReason.TIMEOUT, HandoffReason.RESULT_REFUSED):
        s.disable(prev.model_id)
        nxt = s.acquire(now_ms=1)
        rec.record(previous=prev, nxt=nxt, reason=reason, continuity=cont, now_ms=1)
        prev = nxt
    chain = rec.chain("ctx-c")
    assert [h.reason for h in chain] == [HandoffReason.TIMEOUT, HandoffReason.RESULT_REFUSED]
    assert [h.to_model_id for h in chain] == ["gpt-6-astra", "claude-opus-5"]
    assert rec.summary()["descents"] == 2



# -------------------------------------------------------- persistent runtime
def test_shadow_cognition_runtime_records_unavailable_model_without_touching_decision(
        mandate, eurusd):
    from conftest import intent, snapshot
    from vati.cognition.runtime import ShadowCognitionRuntime
    from vati.core.events import EventKind
    from vati.core.ledger import Ledger
    from vati.risk import RiskAuthority

    ledger = Ledger(":memory:")
    i = intent()
    snap = snapshot(eurusd)
    decision = RiskAuthority(mandate).evaluate(i, snap)
    original = decision.to_dict()
    runtime = ShadowCognitionRuntime(ledger=ledger)
    result = runtime.wake(
        intent=i, decision=decision, snapshot=snap, now_ms=1_800_000_000_000)

    assert decision.to_dict() == original
    assert result.assessment.reason_codes == ("MODEL_UNAVAILABLE",)
    assert result.shadow_entry.assessment.seal_ok()
    assert ledger.count(EventKind.COGNITIVE_CONTEXT) == 1
    assert ledger.count(EventKind.COGNITIVE_ASSESSMENT) == 1
    assert ledger.count(EventKind.SHADOW_DECISION) == 1


def test_shadow_cognition_runtime_falls_back_without_relaxing_controls(mandate, eurusd):
    from conftest import intent, snapshot
    from vati.cognition.runtime import ShadowCognitionRuntime
    from vati.core.events import EventKind
    from vati.core.ledger import Ledger
    from vati.risk import RiskAuthority

    ledger = Ledger(":memory:")
    seen = []

    def invoke(lease, _context):
        seen.append((lease.model_id, lease.control_profile))
        if lease.model_id == "fable-5.1":
            raise RuntimeError("primary transport unavailable")
        return {
            "verdict": "CONCUR",
            "reason_codes": [],
            "risk_multiplier": "1",
            "confidence": "0.6",
            "horizon_ms": 3600000,
            "narrative": "fallback agrees",
        }

    i = intent()
    snap = snapshot(eurusd)
    decision = RiskAuthority(mandate).evaluate(i, snap)
    result = ShadowCognitionRuntime(ledger=ledger, invoker=invoke).wake(
        intent=i, decision=decision, snapshot=snap, now_ms=1_800_000_000_000)

    assert [m for m, _ in seen] == ["fable-5.1", "gpt-6-astra"]
    assert len({profile for _, profile in seen}) == 1
    assert result.assessment.model_id == "gpt-6-astra"
    assert ledger.count(EventKind.MODEL_HANDOFF) == 1


def test_trade_resolution_compiles_model_performance(mandate, eurusd):
    from conftest import intent, snapshot
    from vati.cognition.runtime import ShadowCognitionRuntime
    from vati.core.events import EventKind
    from vati.core.ledger import Ledger
    from vati.risk import RiskAuthority

    ledger = Ledger(":memory:")
    i = intent()
    snap = snapshot(eurusd)
    decision = RiskAuthority(mandate).evaluate(i, snap)
    runtime = ShadowCognitionRuntime(ledger=ledger)
    runtime.wake(
        intent=i, decision=decision, snapshot=snap, now_ms=1_800_000_000_000)
    runtime.resolve_trade(
        i.trade_intent_id, actual_r=Decimal("1.2"), now_ms=1_800_000_100_000)
    assert ledger.count(EventKind.COGNITIVE_PERFORMANCE) >= 1
