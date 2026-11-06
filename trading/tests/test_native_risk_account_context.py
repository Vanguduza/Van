"""Source identity is sealed with risk inputs without issuing financial authority."""
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path

import pytest

from vati.core.canonical import canonical_hash, canonical_json
from vati.risk.account_context import context_for_account, inspect_context, validate_snapshot_context
from vati.risk.contracts import NativeAccountRiskContext
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.core import EventKind


def mt5_context(tmp_path):
    from test_mt5_funding_runtime import setup
    ledger, adapter, account = setup(tmp_path)
    captured = capture_cached_mt5(ledger, account, now_ms=10000)
    value = context_for_account(ledger, adapter, account, now_ms=10000, mt5_capture=captured)
    return ledger, adapter, account, captured, value


def test_mt5_context_retains_actual_query_identity_and_does_not_submit_commands(tmp_path):
    ledger, adapter, account, captured, value = mt5_context(tmp_path)
    assert value.provider == 'MT5'
    assert value.source_query_ref == captured['query_ref']
    assert value.observation_ref == account.funding_mark.source_ref
    assert value.monetary_scope_hash == account.funding_mark.scope_hash
    assert json.loads(value.source_mark_json) == account.funding_mark.mark_body()
    assert value.execution_authority is value.risk_capital_qualified is False
    assert ledger.count(EventKind.FUNDING_MT5_QUERY) == 1
    assert adapter.queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0] == 0


def test_aliases_share_physical_identity_but_retain_their_original_source_labels(tmp_path):
    ledger, adapter, account, captured, first = mt5_context(tmp_path)
    original = next(ledger.iter(EventKind.FUNDING_MT5_QUERY))
    adapter.account_alias = 'another_alias'
    second_account = replace(account, account_alias='another_alias',
        funding_mark=replace(account.funding_mark, account_alias='another_alias'))
    again = capture_cached_mt5(ledger, second_account, now_ms=10001)
    second = context_for_account(ledger, adapter, second_account, now_ms=10001, mt5_capture=again)
    assert first.physical_account_key == second.physical_account_key
    assert first.monetary_scope_hash == second.monetary_scope_hash
    assert first.observation_ref == second.observation_ref
    assert first.source_query_ref == second.source_query_ref == original.hash
    assert first.account_alias == 'native' and second.account_alias == 'another_alias'
    assert first.source_mark_json != second.source_mark_json
    assert next(ledger.iter(EventKind.FUNDING_MT5_QUERY)).body() == original.body()
    assert ledger.count(EventKind.FUNDING_MT5_QUERY) == 1


@pytest.mark.parametrize('captured', [None, {}, {'query_ref': '0' * 64}])
def test_original_mt5_source_query_must_exist_before_context_can_bind_it(tmp_path, captured):
    from test_mt5_funding_runtime import setup
    ledger, adapter, account = setup(tmp_path)
    with pytest.raises(ValueError):
        context_for_account(ledger, adapter, account, now_ms=10000, mt5_capture=captured)
    assert ledger.count() == 0


@pytest.mark.parametrize('field,value', [
    ('risk_capital_qualified', True), ('execution_authority', True),
    ('account_alias', 'other'), ('physical_account_key', 'native-account:v1:' + '0' * 64),
    ('monetary_scope_hash', '0' * 64), ('observation_ref', '0' * 64),
    ('source_query_ref', None), ('source_mark_json', '{}'),
])
def test_context_cannot_claim_authority_or_contradict_its_original_source(tmp_path, field, value):
    *_, original = mt5_context(tmp_path)
    with pytest.raises(ValueError):
        inspect_context(replace(original, **{field: value}))


def test_mutable_or_noncanonical_mark_spelling_cannot_change_a_frozen_input(tmp_path):
    *_, value = mt5_context(tmp_path)
    original = value.source_mark_json
    mark = json.loads(original); mark['balance'] = '999999'
    assert value.source_mark_json == original
    with pytest.raises(ValueError):
        inspect_context(replace(value, source_mark_json=json.dumps(json.loads(original), indent=2)))


def test_ctrader_context_preserves_actual_reader_facts_without_additional_provider_io(tmp_path):
    from test_funding_runtime import setup
    ledger, transport, adapter = setup(tmp_path)
    account = adapter.sync_account()
    before = list(transport.requests)
    value = context_for_account(ledger, adapter, account, now_ms=3000)
    assert value.provider == 'CTRADER' and value.source_query_ref is None
    assert value.observation_ref == canonical_hash(account.funding_mark.body())
    assert json.loads(value.source_mark_json) == account.funding_mark.body()
    assert inspect_context(value)['equity'] == account.equity
    assert value.execution_authority is value.risk_capital_qualified is False
    assert transport.requests == before and ledger.count() == 0


def test_unsupported_or_unverified_accounts_do_not_invent_native_evidence(tmp_path):
    from test_mt5_funding_runtime import setup
    from vati.execution.paper import PaperAdapter
    ledger, adapter, account = setup(tmp_path)
    assert context_for_account(ledger, adapter, replace(account, verified=False), now_ms=10000) is None
    assert context_for_account(ledger, adapter, replace(account, funding_mark=None), now_ms=10000) is None
    assert context_for_account(ledger, PaperAdapter(), account, now_ms=10000) is None
    assert ledger.count() == 0


def test_new_context_round_trip_is_hashed_and_old_snapshot_remains_byte_compatible(tmp_path, eurusd):
    from conftest import snapshot
    from vati.risk.serde import snapshot_to_dict, snapshot_from_dict
    from vati.risk.authority import _canonical_hash
    *_, account, captured, context = mt5_context(tmp_path)
    value = snapshot(eurusd, account_alias='native', equity=account.equity, balance=account.balance,
                     native_account_context=context)
    validate_snapshot_context(value)
    body = snapshot_to_dict(value)
    assert body['native_account_context']['source_query_ref'] == captured['query_ref']
    recovered = snapshot_from_dict(body)
    assert recovered == value and snapshot_to_dict(recovered) == body
    assert _canonical_hash(recovered) == _canonical_hash(value)
    assert _canonical_hash(replace(value, native_account_context=None)) != _canonical_hash(value)
    old = json.loads((Path(__file__).parent / 'fixtures/legacy_risk_snapshot_b58bb578.json').read_text())
    legacy = snapshot_from_dict(old['snapshot'])
    assert legacy.native_account_context is None
    assert snapshot_to_dict(legacy) == old['snapshot']
    assert _canonical_hash(legacy) == old['original_snapshot_hash']


@pytest.mark.parametrize('change', ['alias', 'balance', 'equity', 'currency', 'venue', 'future'])
def test_snapshot_cannot_borrow_another_account_or_time_currency_valuation(tmp_path, eurusd, change):
    from conftest import snapshot
    *_, account, _, context = mt5_context(tmp_path)
    value = snapshot(eurusd, account_alias='native', equity=account.equity, balance=account.balance,
                     native_account_context=context)
    changes = {'alias': {'account_alias': 'other'}, 'balance': {'balance': Decimal('1')},
        'equity': {'equity': Decimal('1')}, 'currency': {'symbol_contract': replace(eurusd, account_currency='EUR')},
        'venue': {'symbol_contract': replace(eurusd, venue='ctrader')},
        'future': {'now_unix': 0}}
    with pytest.raises(ValueError):
        validate_snapshot_context(replace(value, **changes[change]))


def producer_snapshot(eurusd, ledger, adapter, account, producer):
    from types import SimpleNamespace as N
    from vati.execution.base import Health
    from vati.risk.contracts import MarketIntegrityState
    contract = replace(eurusd, venue=adapter.venue, account_currency=account.currency)
    adapter.sync_account = lambda: account
    adapter.heartbeat = lambda **_: Health(True, 0, 10000)
    adapter.positions = lambda: []
    if producer == 'single':
        from test_recoverable_lockouts import _cycle
        service = _cycle(contract, ledger)
        service.cfg = replace(service.cfg, contract=contract, venue=adapter.venue,
                              account_alias=account.account_alias)
        service.adapter = adapter
        service.peak_equity = service.day_start_equity = service.week_start_equity = Decimal('100')
        facts = service.snapshot(now_ms=10000, quote_age_ms=17)
    else:
        from vati.app.account_service import AccountCoordinatorService
        service = AccountCoordinatorService.__new__(AccountCoordinatorService)
        service.adapter = adapter; service.account = N(); service._ledger = ledger
        service.clock = lambda: 10000; service.contracts = {'EURUSD': contract}
        service.peak_equity = service.day_start_equity = service.week_start_equity = Decimal('100')
        service._entries = {}
        service.cfg = N(account_alias=account.account_alias, max_quote_age_ms=5000)
        service._ledger_positions = lambda: []; service._risk_store_ok = lambda: True
        service._open_positions = lambda: (); service._drawdown_top_state = lambda: None
        service.lifecycle = None; service.consecutive_losses = 0; service.kill = N(active=[])
        from conftest import mandate_dict
        from vati.risk import TradingMandate
        service.mandate = TradingMandate.from_mapping(mandate_dict(account_alias=account.account_alias, venue=adapter.venue))
        service.evaluators = {'EURUSD': N(last_state=N(as_of_ms=10000, quote_age_ms=17,
            event_window=None, integrity=MarketIntegrityState.NORMAL))}
        facts = service._snapshot_for(N(symbol='EURUSD', strategy_id=''))
    return facts


@pytest.mark.parametrize('producer', ['single', 'account'])
@pytest.mark.parametrize('provider', ['MT5', 'CTRADER'])
def test_actual_snapshot_producers_bind_original_native_sources(tmp_path, eurusd, producer, provider):
    from vati.risk.serde import snapshot_to_dict
    if provider == 'MT5':
        from test_mt5_funding_runtime import setup
        ledger, adapter, account = setup(tmp_path)
    else:
        from test_funding_risk_fence import book, native, mark
        ledger, _, _ = book(tmp_path)
        adapter, account = native(mark(3500, equity='98'))
    facts = producer_snapshot(eurusd, ledger, adapter, account, producer)
    context = facts.native_account_context
    assert type(context) is NativeAccountRiskContext and context.provider == provider
    assert context.account_alias == facts.account_alias == account.account_alias
    assert context.monetary_scope_hash == account.funding_mark.scope_hash
    assert context.risk_capital_qualified is context.execution_authority is False
    validate_snapshot_context(facts)
    assert snapshot_to_dict(facts)['native_account_context']['observation_ref'] == context.observation_ref
    if provider == 'MT5':
        assert context.source_query_ref == next(ledger.iter(EventKind.FUNDING_MT5_QUERY)).hash
        assert adapter.queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0] == 0
    else:
        assert context.source_query_ref is None


def test_real_sealed_decision_and_durable_replay_bind_original_native_source(tmp_path, eurusd):
    from copy import deepcopy
    from conftest import snapshot, intent, mandate_dict
    from vati.core import make_event
    from vati.execution.review import initial_risk_from_ledger
    from vati.risk import RiskAuthority, TradingMandate, Decision
    from vati.risk.authority import _canonical_hash
    from vati.risk.serde import (snapshot_to_dict, snapshot_from_dict,
        intent_to_dict, intent_from_dict)
    ledger, adapter, account, captured, context = mt5_context(tmp_path)
    grant = mandate_dict(account_alias='native')
    mandate = TradingMandate.from_mapping(grant)
    request = intent(account_alias='native')
    facts = snapshot(eurusd, account_alias='native', equity=account.equity,
        balance=account.balance, native_account_context=context)
    decision = RiskAuthority(mandate).evaluate_safe(request, facts)
    assert decision.decision in {Decision.APPROVED, Decision.REDUCED}, decision
    assert decision.risk_snapshot_hash == _canonical_hash(facts)
    payload = {'inputs': {'intent': intent_to_dict(request), 'snapshot': snapshot_to_dict(facts),
                         'mandate': grant}, 'decision': decision.to_dict()}
    event = make_event(EventKind.RISK_DECISION, 'vati-cycle', payload,
        event_time_ms=facts.now_unix * 1000, received_time_ms=facts.now_unix * 1000,
        correlation_id=request.trade_intent_id)
    ledger.append(event)
    original_body = next(ledger.iter(EventKind.RISK_DECISION)).body()
    assert payload['inputs']['snapshot']['native_account_context']['source_query_ref'] == captured['query_ref']
    assert initial_risk_from_ledger(ledger, request.trade_intent_id) is not None
    def replay(inputs):
        return RiskAuthority(TradingMandate.from_mapping(inputs['mandate'])).evaluate_safe(
            intent_from_dict(inputs['intent']), snapshot_from_dict(inputs['snapshot'])).to_dict()
    assert ledger.replay_decisions(replay).ok
    assert next(ledger.iter(EventKind.RISK_DECISION)).body() == original_body
    # A different source reference cannot borrow the original approval even
    # when the event envelope is sealed again; its decision binds the inputs.
    altered = deepcopy(payload)
    altered['inputs']['snapshot']['native_account_context']['source_query_ref'] = '0' * 64
    from vati.core import Ledger
    damaged = Ledger(tmp_path / 'damaged.sqlite')
    damaged.append(make_event(EventKind.RISK_DECISION, 'vati-cycle', altered,
        event_time_ms=event.event_time_ms, received_time_ms=event.received_time_ms,
        correlation_id=event.correlation_id))
    assert initial_risk_from_ledger(damaged, request.trade_intent_id) is None
    assert not damaged.replay_decisions(replay).ok
    assert adapter.queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0] == 0


@pytest.mark.parametrize('change', ['authority', 'source', 'physical', 'alias', 'venue'])
def test_actual_authority_seals_a_refusal_for_invalid_native_context(tmp_path, eurusd, change):
    from conftest import snapshot, intent, mandate_dict
    from vati.risk import RiskAuthority, TradingMandate, Decision
    ledger, adapter, account, _, context = mt5_context(tmp_path)
    contract = eurusd
    if change == 'authority': context = replace(context, risk_capital_qualified=True)
    elif change == 'source': context = replace(context, observation_ref='0' * 64)
    elif change == 'physical': context = replace(context, physical_account_key='0' * 64)
    elif change == 'alias': context = replace(context, account_alias='another-account')
    else: contract = replace(contract, venue='ctrader')
    venue = contract.venue
    mandate = TradingMandate.from_mapping(mandate_dict(account_alias='native', venue=venue))
    result = RiskAuthority(mandate).evaluate_safe(intent(account_alias='native', venue=venue),
        snapshot(contract, account_alias='native', equity=account.equity, balance=account.balance,
                 native_account_context=context))
    assert result.decision is Decision.REJECTED and result.reason_code == 'AUTHORITY_FAULT'
    body = result.to_dict()
    assert body['decision_hash'] == canonical_hash({k: v for k, v in body.items() if k != 'decision_hash'})
    assert ledger.count(EventKind.RISK_DECISION) == ledger.count(EventKind.ORDER_COMMAND) == 0
    assert adapter.queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0] == 0


@pytest.mark.parametrize('producer', ['single', 'account'])
@pytest.mark.parametrize('damage', ['identity', 'realm', 'equity'])
def test_actual_producers_preserve_original_funding_holds_and_baselines(tmp_path, eurusd, producer, damage):
    from test_funding_risk_fence import book, native, mark
    from vati.funding.risk_fence import funding_risk_fence
    ledger, _, _ = book(tmp_path)
    point = mark(3500, equity='98')
    if damage == 'identity': point = replace(point, native_account_id=99999)
    elif damage == 'realm': point = replace(point, environment='LIVE')
    adapter, account = native(point)
    if damage == 'equity': account = replace(account, equity=Decimal('999999'))
    original = funding_risk_fence(ledger, adapter, account, now_ms=10000)
    assert not original.available and original.reason.endswith('CURRENT_NATIVE_ACCOUNT_BINDING_INVALID')
    facts = producer_snapshot(eurusd, ledger, adapter, account, producer)
    assert facts.preservation_blocks_new_risk and facts.preservation_reason == original.reason
    assert facts.native_account_context is None
    assert facts.peak_equity == facts.day_start_equity == facts.week_start_equity == Decimal('100')
    assert ledger.count(EventKind.ORDER_COMMAND) == 0


@pytest.mark.parametrize('producer', ['single', 'account'])
def test_actual_producers_hold_new_risk_on_source_capture_failure_without_leaking_notes(tmp_path, eurusd, producer, monkeypatch):
    from test_funding_risk_fence import book, native, mark
    from vati.risk import account_context
    ledger, _, _ = book(tmp_path)
    adapter, account = native(mark(3500, equity='98'))
    def unavailable(*args, **kwargs):
        raise OSError('isolated provider-private detail must not enter owner diagnostics')
    monkeypatch.setattr(account_context, 'context_for_account', unavailable)
    facts = producer_snapshot(eurusd, ledger, adapter, account, producer)
    assert facts.preservation_blocks_new_risk
    assert facts.preservation_reason == 'NATIVE_RISK_ACCOUNT_SOURCE_UNAVAILABLE:OSError'
    assert facts.native_account_context is None
    assert facts.peak_equity == facts.day_start_equity == facts.week_start_equity == Decimal('100')
    assert ledger.count(EventKind.ORDER_COMMAND) == 0
