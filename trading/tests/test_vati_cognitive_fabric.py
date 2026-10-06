from copy import deepcopy

import pytest

from vati.cognition.fabric import TriAnalystPlane, FabricError
from vati.core.ledger import Ledger


def setup_plane(*, deadline=1000):
    ledger = Ledger()
    plane = TriAnalystPlane(ledger, account_alias='test', qualified_providers={
        'van-native': {'model_or_agent_id': 'native-v1', 'expires_at_ms': 1000, 'qualification_ref': 'test:q1'},
        'openai-programmatic': {'model_or_agent_id': 'openai-v1', 'expires_at_ms': 1000, 'qualification_ref': 'test:q2'},
    })
    universe = plane.universe(instruments=[{'symbol': 'XAUUSD', 'broker_symbol': 'XAUUSD',
        'asset_class': 'METAL', 'contract_hash': 'h', 'market_data_available': True,
        'discovery_allowed': True, 'execution_supported': False, 'execution_eligibility_state': 'RESEARCH_ONLY'}],
        broker='test', venue='test', now_ms=100)
    signal = {'candidate_id': 'signal', 'origin_lane': 'META_ANALYST', 'provider_product': 'personal-muse-free',
        'universe_snapshot_id': universe['snapshot_id'], 'symbol': 'XAUUSD', 'venue': 'test',
        'horizon': 'SWING', 'initial_thesis': 'Watch breakout', 'evidence_refs': ['source'], 'expires_at_ms': deadline}
    plane.discover(signal, now_ms=101)
    ev = plane.evidence(symbol='XAUUSD', state={'market_data_hash': 'market-hash'}, source_refs=['market:canonical'], now_ms=102, deadline_ms=deadline)
    return plane, ev, signal


def packet(ev, *, lane='VAN_NATIVE_ANALYST', product='van-native', lineage='native-lineage', identity='VAN_NATIVE', model='native-v1', thesis='BUY_IF_TRIGGER'):
    return {'packet_id': product, 'candidate_id': 'signal', 'analyst_lane': lane, 'analysis_lineage_id': lineage,
        'independence_class': identity, 'provider_product': product, 'model_or_agent_id': model,
        'evidence_epoch': ev['evidence_epoch'], 'evidence_hash': ev['content_hash'],
        'generated_at_ms': 103, 'expires_at_ms': 1000, 'prior_lane_outputs_seen': [],
        'directional_thesis': thesis, 'supporting_evidence': ['market:canonical'],
        'contradicting_evidence': ['event risk'], 'missing_inputs': [], 'uncertainty': 'Bounded', 'abstain': False}


def second(ev, **changes):
    body = packet(ev, lane='OPENAI_ANALYST', product='openai-programmatic', lineage='openai-lineage', identity='OPENAI_PROGRAMMATIC', model='openai-v1', thesis='WAIT_EVENT_RISK')
    body.update(changes)
    return body


def test_two_independent_disagreeing_lineages_request_only_evaluation():
    plane, ev, _ = setup_plane()
    plane.packet(packet(ev), now_ms=104)
    plane.packet(second(ev), now_ms=104)
    assessment = plane.consolidate(candidate_id='signal', evidence_epoch=ev['evidence_epoch'], now_ms=105)
    assert assessment['independence_gate_passed']
    assert len(assessment['disagreement_map']) == 2
    admission = plane.admission(candidate_id='signal', evidence_epoch=ev['evidence_epoch'], now_ms=105)
    assert admission['allowed_effects'] == ['REQUEST_DETERMINISTIC_CANDIDATE_EVALUATION']
    assert 'CREATE_ORDER' in admission['forbidden_effects']
    assert not any(hasattr(plane, name) for name in ('router', 'execute', 'risk_authority'))


@pytest.mark.parametrize('field', ['approved_size', 'broker_order', 'requested_risk_pct', 'leverage_override', 'mandate_override'])
def test_execution_fields_rejected_even_nested(field):
    plane, ev, _ = setup_plane()
    body = packet(ev)
    body['uncertainty'] = {'nested': {field: 100}}
    with pytest.raises(FabricError, match='EXECUTION_AUTHORITY'):
        plane.packet(body, now_ms=104)


@pytest.mark.parametrize('change', [{'prior_lane_outputs_seen': ['peer']}, {'analysis_lineage_id': ''}, {'evidence_hash': 'wrong'}, {'provider_product': 'muse-spark-api'}, {'approved_size': 1}, {'abstain': 'false'}])
def test_malformed_contaminated_or_paid_packets_fail(change):
    plane, ev, _ = setup_plane()
    body = packet(ev)
    body.update(change)
    with pytest.raises(FabricError):
        plane.packet(body, now_ms=104)


def test_same_lineage_does_not_count_twice():
    plane, ev, _ = setup_plane()
    plane.packet(packet(ev), now_ms=104)
    plane.packet(second(ev, analysis_lineage_id='native-lineage'), now_ms=104)
    with pytest.raises(FabricError, match='TWO_LINEAGE'):
        plane.admission(candidate_id='signal', evidence_epoch=ev['evidence_epoch'], now_ms=105)


def test_late_personal_muse_is_research_never_backdated_live():
    plane, ev, _ = setup_plane(deadline=110)
    body = packet(ev, lane='META_ANALYST', product='personal-muse-free', lineage='meta', identity='META_PERSONAL_MUSE', model='muse')
    result = plane.packet(body, now_ms=111)
    assert result['live_eligible'] is False
    assert plane.consolidate(candidate_id='signal', evidence_epoch=ev['evidence_epoch'], now_ms=112)['disposition'] == 'WATCH'


def test_focus_deduplicates_epoch_across_restart():
    plane, ev, _ = setup_plane()
    a = plane.focus(candidate_id='signal', evidence_epoch=ev['evidence_epoch'], reason='one', now_ms=104)
    restarted = TriAnalystPlane(plane.ledger, account_alias='test')
    b = restarted.focus(candidate_id='signal', evidence_epoch=ev['evidence_epoch'], reason='different wording', now_ms=105)
    assert a['lease_id'] == b['lease_id']
    assert len(plane._rows('TradeFocusLease')) == 1


def test_first_pass_context_has_no_peer_output_or_origin_thesis():
    plane, ev, _ = setup_plane()
    plane.packet(packet(ev), now_ms=104)
    ctx = plane.first_pass_context(candidate_id='signal', evidence_epoch=ev['evidence_epoch'])
    assert ctx['prior_lane_outputs_seen'] == []
    assert 'BUY_IF_TRIGGER' not in str(ctx)
    assert 'Watch breakout' not in str(ctx)


def test_no_strategy_no_candidate_and_learning_freezes_ex_ante():
    plane, ev, _ = setup_plane()
    plane.packet(packet(ev), now_ms=104)
    plane.packet(second(ev), now_ms=104)
    plane.admission(candidate_id='signal', evidence_epoch=ev['evidence_epoch'], now_ms=105)
    result = plane.evaluate_pending(evaluators={}, bars_by_symbol={}, now_ms=106)
    assert result[0]['disposition'] == 'WATCH_RESEARCH'
    assert result[0]['vati_candidate_ids'] == []
    assert plane._rows('TradeLearningEpisode')[0]['ex_ante_validity_frozen']
    assert plane.evaluate_pending(evaluators={}, bars_by_symbol={}, now_ms=107) == []
    assert plane.ledger.verify_chain()[0] if isinstance(plane.ledger.verify_chain(), tuple) else plane.ledger.verify_chain()


def test_expired_qualification_fails_gate():
    plane, ev, _ = setup_plane()
    plane.packet(packet(ev), now_ms=104)
    plane.packet(second(ev), now_ms=104)
    plane.qualified['openai-programmatic']['expires_at_ms'] = 105
    assert not plane.consolidate(candidate_id='signal', evidence_epoch=ev['evidence_epoch'], now_ms=106)['independence_gate_passed']


def test_packet_retry_idempotent_and_collision_rejected():
    plane, ev, _ = setup_plane()
    body = packet(ev)
    first = plane.packet(body, now_ms=104)
    assert plane.packet(deepcopy(body), now_ms=105) == first
    body['directional_thesis'] = 'changed'
    with pytest.raises(FabricError, match='COLLISION'):
        plane.packet(body, now_ms=105)


def test_real_instrument_evaluator_capsule_engine_pool_and_risk_path(eurusd):
    """Authentic admitted strategies produce the candidate; analyst thesis is dissent only."""
    from decimal import Decimal
    from vati.app.instrument_evaluator import InstrumentEvaluator, InstrumentEvaluatorConfig
    from vati.app.account_coordinator import AccountDecisionCoordinator, CoordinatorConfig
    from vati.arbiter.portfolio_allocator import OpportunityPortfolioAllocator
    from vati.arbiter.opportunity import OpportunityEngine
    from vati.core.canonical import canonical_hash
    from vati.risk import RiskAuthority, Decision
    from vati.strategies import CapsuleRegistry, STRATEGY_IMPLEMENTATIONS, StrategyContext
    from test_strategies_arbiter import REG, demo_mandate, state_for
    from test_intelligence import pullback_fixture, mk_bars
    from conftest import snapshot
    state = state_for(pullback_fixture())
    bars = mk_bars(pullback_fixture())
    now = state.as_of_ms
    mandate = demo_mandate()
    registry = CapsuleRegistry.load_dir(REG)
    impl = {sid: STRATEGY_IMPLEMENTATIONS[sid.rsplit('-', 1)[0]](strategy_id=sid)
            for sid in ('FX-TREND-PULLBACK-01', 'FX-LONDON-BREAKOUT-01')}
    evaluator = InstrumentEvaluator(InstrumentEvaluatorConfig(symbol='EURUSD', base='EUR', quote='USD',
        venue='mt5', account_alias='fx_primary', timeframe='H1'), engine=OpportunityEngine(registry, impl, mandate),
        state_fn=lambda _bars, _now: state, ctx_fn=lambda _state: StrategyContext(Decimal('.0003')))
    deterministic = evaluator.evaluate(bars, now_ms=now)
    assert deterministic
    horizon = deterministic[0].horizon
    plane = TriAnalystPlane(Ledger(), account_alias='fx_primary', qualified_providers={
        'van-native': {'model_or_agent_id': 'native-v1', 'expires_at_ms': now + 300000, 'qualification_ref': 'test:q1'},
        'openai-programmatic': {'model_or_agent_id': 'openai-v1', 'expires_at_ms': now + 300000, 'qualification_ref': 'test:q2'}})
    universe = plane.universe(instruments=[{'symbol': 'EURUSD', 'discovery_allowed': True}], broker='mt5', venue='mt5', now_ms=now)
    plane.discover({'candidate_id': 'signal', 'origin_lane': 'META_ANALYST', 'provider_product': 'personal-muse-free',
        'universe_snapshot_id': universe['snapshot_id'], 'symbol': 'EURUSD', 'venue': 'mt5', 'horizon': horizon,
        'initial_thesis': 'Observe strategy setup', 'evidence_refs': [state.state_hash], 'expires_at_ms': now + 1000}, now_ms=now)
    ev = plane.evidence(symbol='EURUSD', state={'market_data_hash': canonical_hash([str(b) for b in bars])},
        source_refs=[state.state_hash], now_ms=now, deadline_ms=now + 1000)
    for body in (packet(ev), second(ev)):
        body.update(generated_at_ms=now, expires_at_ms=now + 1000)
        plane.packet(body, now_ms=now)
    plane.admission(candidate_id='signal', evidence_epoch=ev['evidence_epoch'], now_ms=now)
    risk = RiskAuthority(mandate)
    coordinator = AccountDecisionCoordinator(CoordinatorConfig(account_alias='fx_primary'), evaluators=[evaluator],
        allocator=OpportunityPortfolioAllocator(), snapshot_fn=lambda _candidate: snapshot(eurusd),
        risk_fn=risk.evaluate_safe, mandate=mandate, candidate_intent_fn=plane.bind_intent)
    result = plane.evaluate_pending(evaluators={'EURUSD': evaluator}, bars_by_symbol={'EURUSD': bars},
        now_ms=now, candidate_sink=coordinator.pool.admit)
    assert result[0]['vati_candidate_ids'] == [c.candidate_id for c in deterministic if c.horizon == horizon]
    assert result[0]['disposition'] == 'DETERMINISTIC_CANDIDATE'
    # The authentic coordinator reaches risk; no execution route is installed in this test.
    passed = coordinator.step(now_ms=now, bars_by_symbol={})
    assert passed.outcomes
    assert passed.outcomes[0].decision == 'EXECUTION_REFUSED'
    assert passed.outcomes[0].risk_decision.decision in (Decision.APPROVED, Decision.REDUCED)
    assert plane._rows('CandidateIntentBinding')


def test_changed_market_cannot_reuse_prior_epoch():
    from vati.core.canonical import canonical_hash
    plane, ev, _ = setup_plane()
    plane.packet(packet(ev), now_ms=104)
    plane.packet(second(ev), now_ms=104)
    plane.admission(candidate_id='signal', evidence_epoch=ev['evidence_epoch'], now_ms=105)
    class Evaluator:
        def evaluate(self, *args, **kwargs):
            raise AssertionError('changed market must be refused before strategy evaluation')
    result = plane.evaluate_pending(evaluators={'XAUUSD': Evaluator()}, bars_by_symbol={'XAUUSD': ['new-market']}, now_ms=106)
    assert result[0]['vati_candidate_ids'] == []


def test_expired_discovery_becomes_no_trade_learning_without_hindsight_revision():
    plane, _ev, _ = setup_plane(deadline=110)
    plane.join_outcomes(now_ms=111)
    assert plane._rows('TradeLearningEpisode')[0]['outcome_state'] == 'EXPIRED_NO_TRADE'
    assert plane._rows('TradeLearningEpisode')[0]['ex_ante_validity_frozen'] is True
    plane.join_outcomes(now_ms=112)
    assert len(plane._rows('TradeLearningEpisode')) == 1
