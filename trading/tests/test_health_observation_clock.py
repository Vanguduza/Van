"""Reading diagnostics or retrying evidence cannot advance a demotion clock."""
from decimal import Decimal as D

from test_learning_evidence import Src
from vati.learning.episodes import Environment
from vati.learning.health import StrategyHealthTracker


def add_bad(tracker, source, number):
    ref = source.review("clock", number, r="-1", process_ok=False, cost="2.5")
    return ref, tracker.observe_evidence("clock", ref, resolver=source.resolver, regime_fit=False)


def test_diagnostic_reads_cannot_supply_missing_sustained_observations():
    source = Src(Environment.LIVE)
    tracker = StrategyHealthTracker(sustain=4)
    _, first = add_bad(tracker, source, 0)
    assert first.state_recommendation is None
    for _ in range(100):
        current = tracker.verdict("clock")
        tracker.live_adjustment("clock")
        assert current == first
    assert tracker._below_count["clock"] == 1


def test_retried_evidence_does_not_advance_hysteresis():
    source = Src(Environment.LIVE)
    tracker = StrategyHealthTracker(sustain=4)
    ref, first = add_bad(tracker, source, 0)
    for _ in range(20):
        assert tracker.observe_evidence("clock", ref, resolver=source.resolver, regime_fit=False) == first
    assert tracker._below_count["clock"] == 1
    for number in (1, 2):
        assert add_bad(tracker, source, number)[1].state_recommendation is None
    assert add_bad(tracker, source, 3)[1].state_recommendation == "SHADOW"
    assert tracker.verdict("clock").weighted_samples == D("4")


def test_warm_and_cold_health_match_despite_different_poll_frequencies():
    source = Src(Environment.LIVE)
    warm = StrategyHealthTracker(sustain=6)
    cold = StrategyHealthTracker(sustain=6)
    refs = []
    for number in range(5):
        ref, _ = add_bad(warm, source, number)
        refs.append(ref)
        for _ in range(7):
            warm.verdict("clock")
            warm.live_adjustment("clock")
    for ref in refs:
        cold.observe_evidence("clock", ref, resolver=source.resolver, regime_fit=False)
    assert cold.verdict("clock") == warm.verdict("clock")
    assert warm.verdict("clock").state_recommendation is None


def test_new_good_observation_resets_consecutive_breach_count():
    source = Src(Environment.LIVE)
    tracker = StrategyHealthTracker(sustain=3, window=1)
    add_bad(tracker, source, 0)
    good = source.review("clock", 1, r="1", process_ok=True, cost="1")
    tracker.observe_evidence("clock", good, resolver=source.resolver)
    assert tracker._below_count["clock"] == 0
    assert add_bad(tracker, source, 2)[1].state_recommendation is None
    assert tracker._below_count["clock"] == 1
