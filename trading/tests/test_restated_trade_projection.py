"""Real close/replay consumers plus native-envelope correction and crash cases.

These are deterministic paper/source tests, not provider correction admission or
financial policy, independent certification, or profitability evidence.
"""
from dataclasses import replace
from decimal import Decimal as D, localcontext
import json
import os
import uuid

import pytest

from conftest import intent, snapshot, mandate_dict, NOW
from test_account_lifecycle import _command, _lifecycle
from vati.core import Ledger, EventKind, make_event
from vati.core.canonical import canonical_hash
from vati.execution.paper import PaperAdapter
from vati.learning.episodes import Environment
from vati.learning.hooks import LearningHooks
from vati.learning.scope import LearningScope
from vati.learning.restatement import RestatedTradeProjection
from vati.learning.projection_store import ProjectionCorrupt
from vati.risk import RiskAuthority
from vati.risk.contracts import Direction, StrategyState
from vati.risk.mandate import TradingMandate
from vati.risk.serde import intent_to_dict, snapshot_to_dict

STRATEGY = 'FX-TREND-PULLBACK-01'


def native_parent(ledger, eurusd, *, alias='fx_primary', trade='parent', partial=False):
    mandate = TradingMandate.from_mapping(mandate_dict(account_alias=alias, venue='paper',
        mode='DEMO_TRADER', allowed_strategies=[STRATEGY]))
    candidate = intent(trade_intent_id=trade, idempotency_key=trade, account_alias=alias,
        venue='paper', strategy_id=STRATEGY, strategy_state=StrategyState.DEMO)
    inputs = snapshot(replace(eurusd, venue='paper'), account_alias=alias)
    decision = RiskAuthority(mandate).evaluate(candidate, inputs)
    assert decision.approved_size > 0
    risk_event = make_event(EventKind.RISK_DECISION, 'vati-account-coordinator',
        {'inputs': {'intent': intent_to_dict(candidate), 'snapshot': snapshot_to_dict(inputs),
                    'mandate': {'account_alias': alias, 'mode': 'DEMO_TRADER'}},
         'decision': decision.to_dict()}, event_time_ms=NOW*1000,
        received_time_ms=NOW*1000, correlation_id=trade)
    ledger.append(risk_event)
    adapter = PaperAdapter(account_alias=alias)
    command = replace(_command(trade), account_alias=alias, entry_type='MARKET',
        entry_price=candidate.entry, protective_stop=candidate.stop,
        decision_hash=decision.decision_hash, quantity=decision.approved_size,
        command_hash='').sealed()
    opened = adapter.submit(command, now_ms=NOW*1000+1)
    if partial:
        adapter.last_price['EURUSD'] = candidate.entry+D('0.001')
        adapter.close(opened.broker_position_id, command.quantity/2, now_ms=NOW*1000+2, reason='PARTIAL')
    adapter.last_price['EURUSD'] = candidate.entry+D('0.002')
    closed = adapter.close(opened.broker_position_id, None, now_ms=NOW*1000+3, reason='TARGET')
    learning = LearningHooks(environment=Environment.DEMO, account_alias=alias)
    lifecycle = _lifecycle(ledger, adapter)
    lifecycle.mandate = mandate
    lifecycle.learning = learning
    lifecycle.entries[trade] = {'entry': opened.average_fill, 'stop': candidate.stop,
        'quantity': command.quantity, 'direction': Direction.LONG, 'symbol': 'EURUSD',
        'strategy_id': STRATEGY, 'fees': D('0'), 'opened_ms': NOW*1000+1}
    lifecycle._on_close(trade, closed.average_fill, 'TARGET', NOW*1000+3)
    review = next(ledger.iter(EventKind.TRADE_REVIEW, correlation_id=trade))
    return review, learning, adapter, inputs.equity*decision.approved_risk_pct


def projector(ledger, alias='fx_primary', **kwargs):
    return RestatedTradeProjection(ledger, LearningScope(ledger, alias, Environment.DEMO), **kwargs)


def correction(ledger, original, *, revision=1, predecessor=None, patch=None, producer='vati-account-lifecycle'):
    payload = {**original.payload, 'record_revision': revision,
               'supersedes_review_ref': predecessor if predecessor is not None else original.payload['artifact_hash'],
               **(patch or {})}
    if patch and 'pnl' in patch and 'r_multiple' not in patch:
        payload['r_multiple'] = str((D(payload['pnl'])/D(payload['initial_money_risk'])).quantize(D('0.01')))
    payload['artifact_hash'] = canonical_hash({k: v for k, v in payload.items() if k != 'artifact_hash'})
    event = make_event(EventKind.TRADE_REVIEW_REVISION, producer, payload,
        event_time_ms=original.event_time_ms-100, received_time_ms=original.received_time_ms+revision+1,
        correlation_id=original.correlation_id)
    ledger.append(event)
    return event


def test_real_partial_close_producer_and_cold_projection_keep_one_parent(eurusd, tmp_path):
    path = tmp_path/'source.sqlite'; ledger = Ledger(path)
    review, learning, adapter, risk = native_parent(ledger, eurusd, partial=True)
    result = learning.update_projection(ledger)
    assert result['status'] == 'ANALYSIS_ONLY' and not result['selection_authority']
    assert result['parent_count'] == 1 and result['immature_parents'] == 0
    aggregate = result['views']['RESTATED_ANALYSIS']['USD']
    assert aggregate['count'] == 1 and D(aggregate['net_pnl']) == adapter.realised_pnl
    with localcontext() as ctx:
        ctx.prec = 50
        assert D(aggregate['net_r']) == adapter.realised_pnl/risk
    count, head = ledger.count(), ledger.head()
    cold = projector(Ledger(path)).catch_up()
    assert cold['snapshot_hash'] == result['snapshot_hash']
    assert cold['views'] == result['views'] and ledger.count() == count and ledger.head() == head
    assert review.payload['broker_ok'] is True


def test_correction_subtracts_old_contribution_without_changing_original_view(eurusd):
    ledger = Ledger(); original, _, _, _ = native_parent(ledger, eurusd)
    projection = projector(ledger); before = projection.catch_up()
    updated = correction(ledger, original, patch={'pnl': '-5'})
    after = projection.catch_up()
    assert after['views']['AS_DECIDED'] == before['views']['AS_DECIDED']
    assert after['views']['RESTATED_ANALYSIS']['USD']['count'] == 1
    assert D(after['views']['RESTATED_ANALYSIS']['USD']['net_pnl']) == D('-5')
    # An older native revision published later cannot overwrite revision 1.
    ledger.append(make_event(original.kind, original.producer, original.payload,
        event_time_ms=original.event_time_ms, received_time_ms=original.received_time_ms+1000,
        correlation_id=original.correlation_id))
    assert projection.catch_up()['views'] == after['views']
    assert next(ledger.iter(EventKind.TRADE_REVIEW)).hash == original.hash
    assert ledger.count(EventKind.TRADE_REVIEW_REVISION) == 1


@pytest.mark.parametrize('kind', ['same_revision_conflict', 'missing_predecessor', 'wrong_predecessor'])
def test_ambiguous_native_lineage_quarantines_instead_of_double_learning(eurusd, kind):
    ledger = Ledger(); original, _, _, _ = native_parent(ledger, eurusd)
    projection = projector(ledger); before = projection.catch_up()
    if kind == 'same_revision_conflict':
        correction(ledger, original, patch={'pnl': '3'})
        correction(ledger, original, patch={'pnl': '4'})
    elif kind == 'missing_predecessor':
        correction(ledger, original, revision=2)
    else:
        correction(ledger, original, predecessor='f'*64)
    result = projection.catch_up()
    assert result['status'] == 'RECONCILIATION_REQUIRED' and result['quarantined_parents'] == 1
    assert result['views']['RESTATED_ANALYSIS'] == {}
    assert result['views']['AS_DECIDED'] == before['views']['AS_DECIDED']


@pytest.mark.parametrize('patch', [
    {'maturity': {}}, {'maturity': {'parent_final': True, 'fees_final': False, 'cash_reconciled': True}},
    {'broker_ok': False}, {'initial_risk_evidence_ref': 'risk-decision://'+'f'*64},
    {'pnl_basis': 'UNKNOWN_FEES'},
])
def test_unsettled_or_unbound_economics_never_enter_the_sample(eurusd, patch):
    ledger = Ledger(); original, _, _, _ = native_parent(ledger, eurusd)
    correction(ledger, original, patch=patch)
    result = projector(ledger).catch_up()
    assert result['status'] == 'MATURITY_PENDING'
    assert result['views']['RESTATED_ANALYSIS'] == {} and result['views']['AS_DECIDED']['USD']['count'] == 1


def test_model_output_cannot_publish_a_native_correction(eurusd):
    ledger = Ledger(); original, _, _, _ = native_parent(ledger, eurusd)
    projection = projector(ledger); before = projection.catch_up()
    correction(ledger, original, patch={'pnl': '99999'}, producer='model-output')
    result = projection.catch_up()
    assert result['views'] == before['views'] and result['status'] == 'ANALYSIS_ONLY'


@pytest.mark.parametrize('stage', ['after_history_before_cursor', 'after_cursor_before_commit', 'after_commit_before_reply'])
def test_actual_reducer_crash_recovery_does_not_duplicate_or_lose_contributions(eurusd, tmp_path, stage):
    path = tmp_path/'crash.sqlite'; ledger = Ledger(path)
    original, _, _, _ = native_parent(ledger, eurusd)
    projection = projector(ledger); before = projection.catch_up()
    correction(ledger, original, patch={'pnl': '-9'})
    def fail(point):
        if point == stage:
            raise RuntimeError('induced process fault')
    projection.store.fault = fail
    with pytest.raises(RuntimeError, match='induced process fault'):
        projection.catch_up()
    # Observe the real transaction boundary with an independent connection.
    cold = projector(Ledger(path))
    saved = cold.store.load()
    if stage == 'after_commit_before_reply':
        assert saved['snapshot_hash'] != before['snapshot_hash']
    else:
        assert saved['snapshot_hash'] == before['snapshot_hash']
    result = cold.catch_up()
    assert result['views']['RESTATED_ANALYSIS']['USD']['count'] == 1
    assert D(result['views']['RESTATED_ANALYSIS']['USD']['net_pnl']) == D('-9')
    assert result['views']['AS_DECIDED'] == before['views']['AS_DECIDED']


def test_corrupt_cache_rebuilds_from_native_history_but_corrupt_source_refuses(eurusd):
    ledger = Ledger(); native_parent(ledger, eurusd)
    projection = projector(ledger); before = projection.catch_up()
    retained = projection.store._read(f'SELECT COUNT(*) FROM {projection.store.history}')[0][0]
    projection.store._query(f'UPDATE {projection.store.history} SET snapshot_json=?', ('{}',))
    cold = projector(ledger); result = cold.catch_up()
    assert result['views'] == before['views']
    assert result['recovery_reason'].startswith('verified_native_source_rebuild:')
    assert cold.store._read(f'SELECT COUNT(*) FROM {cold.store.history}')[0][0] == retained+1
    ledger._conn.execute("UPDATE events SET payload_json='{}' WHERE seq=1")
    with pytest.raises(ProjectionCorrupt, match='source journal'):
        projector(ledger).catch_up()


def test_real_service_heartbeat_and_account_snapshot_consume_later_revisions(eurusd, tmp_path):
    from test_learning_account_scope import service
    ledger = Ledger(tmp_path/'shared.sqlite')
    original, _, _, _ = native_parent(ledger, eurusd, alias='paper_lab')
    runtime = service(tmp_path, eurusd)
    before = runtime.learning.projection_summary
    correction(runtime._ledger, original, patch={'pnl': '-7'})
    runtime._heartbeat('TEST')
    result = json.loads((tmp_path/'heartbeat.json').read_text())['restated_learning']
    assert result['views']['RESTATED_ANALYSIS']['USD']['net_pnl'] == '-7'
    assert result['views']['AS_DECIDED'] == before['views']['AS_DECIDED']
    runtime._account_snapshot(NOW*1000+100)
    snapshot_event = list(runtime._ledger.iter(EventKind.ACCOUNT_SNAPSHOT))[-1]
    assert snapshot_event.payload['restated_learning']['learned_state_hash'] == result['learned_state_hash']
    assert not result['selection_authority']
    from van_gateway.trading.service import TradingService
    count, head = runtime._ledger.count(), runtime._ledger.head()
    account = TradingService(str(tmp_path/'shared.sqlite')).accounts()['accounts'][0]
    reported = account['restated_learning']
    assert reported['views'] == result['views'] and reported['scope']['account_alias'] == 'paper_lab'
    assert reported['source_event_hash'] == snapshot_event.hash
    assert runtime._ledger.count() == count and runtime._ledger.head() == head


def test_postgres_native_projection_crash_restart_and_logical_ledger_isolation(eurusd):
    dsn = os.environ.get('VATI_TEST_PG_DSN')
    if not dsn or os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE') != '1':
        pytest.skip('explicit isolated PostgreSQL fixture required')
    from vati.core.ledger_pg import PostgresLedger
    name = 'restatement_'+uuid.uuid4().hex[:12]
    ledger = PostgresLedger(dsn, ledger_name=name)
    other = PostgresLedger(dsn, ledger_name=name+'_other')
    try:
        original, _, _, _ = native_parent(ledger, eurusd, partial=True)
        projection = projector(ledger); before = projection.catch_up()
        assert projector(other).catch_up()['status'] == 'NO_OBSERVATIONS'
        for stage, pnl in [('after_history_before_cursor', '-1'), ('after_cursor_before_commit', '-2'), ('after_commit_before_reply', '-3')]:
            current = list(ledger.iter(EventKind.TRADE_REVIEW_REVISION))
            prior = current[-1] if current else original
            correction(ledger, prior, revision=len(current)+1, patch={'pnl': pnl})
            def fail(point):
                if point == stage:
                    raise RuntimeError('induced PostgreSQL fault')
            projection.store.fault = fail
            with pytest.raises(RuntimeError, match='induced PostgreSQL fault'):
                projection.catch_up()
            projection.store.fault = None
            cold = PostgresLedger(dsn, ledger_name=name)
            try:
                restored = projector(cold).catch_up()
                assert restored['views']['RESTATED_ANALYSIS']['USD']['net_pnl'] == pnl
                assert restored['views']['RESTATED_ANALYSIS']['USD']['count'] == 1
                assert restored['views']['AS_DECIDED'] == before['views']['AS_DECIDED']
                assert cold.verify_chain()[0]
            finally:
                cold.close()
        assert projector(other).catch_up()['status'] == 'NO_OBSERVATIONS'
    finally:
        ledger.close(); other.close()


@pytest.mark.parametrize('patch', [
    {'maturity': {'parent_final': True, 'fees_final': True, 'cash_reconciled': True,
                  'source_environment': 'DEMO', 'account_currency': 'EUR'}},
    {'maturity': {'parent_final': True, 'fees_final': True, 'cash_reconciled': True,
                  'source_environment': 'LIVE', 'account_currency': 'USD'}},
])
def test_settlement_currency_and_environment_cannot_be_inferred_from_the_consumer(eurusd, patch):
    ledger = Ledger(); original, _, _, _ = native_parent(ledger, eurusd)
    correction(ledger, original, patch=patch)
    result = projector(ledger).catch_up()
    assert result['status'] == 'MATURITY_PENDING' and result['views']['RESTATED_ANALYSIS'] == {}


def test_a_corrected_r_label_must_match_cash_over_original_money_risk(eurusd):
    ledger = Ledger(); original, _, _, _ = native_parent(ledger, eurusd)
    correction(ledger, original, patch={'pnl': '-10', 'r_multiple': '100'})
    result = projector(ledger).catch_up()
    assert result['status'] == 'RECONCILIATION_REQUIRED' and result['views']['RESTATED_ANALYSIS'] == {}


def test_restated_precision_contract_does_not_inherit_a_callers_rounding_mode(eurusd):
    from decimal import ROUND_UP, ROUND_HALF_EVEN
    ledger = Ledger(); native_parent(ledger, eurusd)
    with localcontext() as context:
        context.rounding = ROUND_HALF_EVEN
        expected = projector(ledger).catch_up()
    # Remove only the derived pointer, retaining history, to force a verified raw replay.
    projection = projector(ledger)
    projection.store._query(f'DELETE FROM {projection.store.current}')
    with localcontext() as context:
        context.prec = 12
        context.rounding = ROUND_UP
        observed = projection.catch_up()
    assert observed['views'] == expected['views']
    assert observed['learned_state_hash'] == expected['learned_state_hash']
