"""Committed original native sources are data, never fresh order authority."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D
import json

import pytest

from conftest import snapshot, intent, mandate_dict, NOW
from test_native_risk_account_context import mt5_context
from vati.core import EventKind, Ledger, make_event
from vati.core.canonical import canonical_json
from vati.core.ledger import LedgerError
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk import RiskAuthority, TradingMandate
from vati.risk.account_context import context_for_account
from vati.risk.native_history import original_native_risk_input, NativeRiskSourceUnavailable
from vati.risk.serde import snapshot_to_dict, intent_to_dict


def record(ledger, facts, *, producer='vati-cycle', request=None, grant=None,
           now_ms=NOW*1000, damage=None):
    request = request or intent(account_alias=facts.account_alias, venue=facts.symbol_contract.venue)
    grant = grant or mandate_dict(account_alias=request.account_alias, venue=request.venue)
    decision = RiskAuthority(TradingMandate.from_mapping(grant)).evaluate_safe(request, facts)
    payload = {'inputs': {'intent': intent_to_dict(request), 'snapshot': snapshot_to_dict(facts),
                          'mandate': grant}, 'decision': decision.to_dict()}
    if damage is not None:
        damage(payload)
    event = make_event(EventKind.RISK_DECISION, producer, payload,
        event_time_ms=now_ms, received_time_ms=now_ms, correlation_id=request.trade_intent_id)
    ledger.append(event)
    return event


def native_facts(tmp_path, eurusd):
    ledger, adapter, account, captured, context = mt5_context(tmp_path)
    facts = snapshot(eurusd, account_alias=account.account_alias,
        balance=account.balance, equity=account.equity, native_account_context=context)
    return ledger, adapter, account, captured, facts


@pytest.mark.parametrize('producer', ['vati-cycle', 'vati-account-coordinator'])
def test_readback_binds_original_risk_snapshot_and_original_query_without_effects(tmp_path, eurusd, producer):
    ledger, adapter, account, captured, facts = native_facts(tmp_path, eurusd)
    event = record(ledger, facts, producer=producer)
    before = ledger.count()
    value = original_native_risk_input(ledger, event.hash, available_at_ms=NOW*1000)
    assert value.event_ref == event.hash and value.trade_intent_id == event.correlation_id
    assert value.snapshot_json == canonical_json(event.payload['inputs']['snapshot'])
    assert value.context.source_query_ref == captured['query_ref']
    assert value.context == facts.native_account_context
    assert value.recorded_decision == event.payload['decision']['decision']
    assert value.execution_authority is value.risk_capital_qualified is False
    assert ledger.count() == before and ledger.count(EventKind.ORDER_COMMAND) == 0
    assert adapter.queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0] == 0


def test_an_expired_historical_approval_is_still_original_data_but_never_new_authority(tmp_path, eurusd):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    event = record(ledger, facts)
    before = ledger.count()
    value = original_native_risk_input(ledger, event.hash, available_at_ms=(NOW+90*86400)*1000)
    assert value.event_ref == event.hash and value.execution_authority is False
    assert ledger.count() == before


def test_alias_changes_reuse_actual_receipt_without_rewriting_its_original_label(tmp_path, eurusd):
    ledger, adapter, account, captured, facts = native_facts(tmp_path, eurusd)
    first = next(ledger.iter(EventKind.FUNDING_MT5_QUERY))
    adapter.account_alias = 'another_native_label'
    current = replace(account, account_alias=adapter.account_alias,
        funding_mark=replace(account.funding_mark, account_alias=adapter.account_alias))
    capture = capture_cached_mt5(ledger, current, now_ms=10001)
    context = context_for_account(ledger, adapter, current, now_ms=10001, mt5_capture=capture)
    event = record(ledger, replace(facts, account_alias=adapter.account_alias, native_account_context=context))
    value = original_native_risk_input(ledger, event.hash, available_at_ms=NOW*1000)
    assert value.context.account_alias == value.intent_account_alias == adapter.account_alias
    assert value.context.source_query_ref == first.hash == captured['query_ref']
    assert value.context.physical_account_key == facts.native_account_context.physical_account_key
    assert next(ledger.iter(EventKind.FUNDING_MT5_QUERY)).body() == first.body()
    assert ledger.count(EventKind.FUNDING_MT5_QUERY) == 1


@pytest.mark.parametrize('damage', ['intent', 'snapshot', 'decision', 'schema', 'producer', 'inputs'])
def test_changed_or_unbound_original_inputs_cannot_supply_historical_identity(tmp_path, eurusd, damage):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    def change(payload):
        if damage == 'intent': payload['inputs']['intent']['stop'] = '1.0'
        elif damage == 'snapshot': payload['inputs']['snapshot']['balance'] = '999999'
        elif damage == 'decision': payload['decision']['approved_risk_pct'] = '0.9'
        elif damage == 'schema': payload['decision']['approval_schema_version'] = 1
        elif damage == 'inputs': payload['inputs'] = []
    event = record(ledger, facts, producer='model-advisory' if damage == 'producer' else 'vati-cycle', damage=change)
    with pytest.raises(NativeRiskSourceUnavailable):
        original_native_risk_input(ledger, event.hash, available_at_ms=NOW*1000)


@pytest.mark.parametrize('damage', ['query', 'mark'])
def test_valid_risk_seal_cannot_substitute_for_independent_original_query_readback(tmp_path, eurusd, damage):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    context = facts.native_account_context
    if damage == 'query':
        context = replace(context, source_query_ref='0'*64)
    else:
        mark = json.loads(context.source_mark_json)
        mark['source_nonce'] = 'unrecorded-native-source'
        context = replace(context, source_mark_json=canonical_json(mark))
    event = record(ledger, replace(facts, native_account_context=context))
    with pytest.raises(NativeRiskSourceUnavailable, match='MT5 query'):
        original_native_risk_input(ledger, event.hash, available_at_ms=NOW*1000)


def test_identical_risk_event_in_another_named_source_cannot_borrow_the_query(tmp_path, eurusd):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    event = record(ledger, facts)
    other = Ledger(tmp_path/'other.sqlite')
    try:
        other.append(event)
        with pytest.raises(NativeRiskSourceUnavailable, match='query receipt is unavailable'):
            original_native_risk_input(other, event.hash, available_at_ms=NOW*1000)
    finally:
        other.close()


def test_a_legacy_alias_cannot_be_relabelled_as_a_physical_account_from_current_settings(tmp_path, eurusd):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    event = record(ledger, replace(facts, native_account_context=None))
    with pytest.raises(NativeRiskSourceUnavailable, match='no native account binding'):
        original_native_risk_input(ledger, event.hash, available_at_ms=NOW*1000)


def test_original_source_cannot_be_used_before_original_first_availability(tmp_path, eurusd):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    event = record(ledger, facts)
    with pytest.raises(NativeRiskSourceUnavailable, match='not yet available'):
        original_native_risk_input(ledger, event.hash, available_at_ms=NOW*1000-1)


def test_later_query_publication_cannot_supply_an_earlier_decision(tmp_path, eurusd):
    from test_mt5_funding_runtime import setup
    ledger, adapter, account = setup(tmp_path)
    query_time = NOW*1000 + 1
    captured = capture_cached_mt5(ledger, account, now_ms=query_time)
    context = context_for_account(ledger, adapter, account, now_ms=query_time, mt5_capture=captured)
    facts = snapshot(eurusd, account_alias=account.account_alias, equity=account.equity,
        balance=account.balance, native_account_context=context)
    event = record(ledger, facts, now_ms=NOW*1000)
    with pytest.raises(NativeRiskSourceUnavailable, match='query does not bind'):
        original_native_risk_input(ledger, event.hash, available_at_ms=query_time)


def test_staged_writer_rows_are_not_committed_historical_source(tmp_path, eurusd):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    event = record(ledger, facts)
    count = ledger.count()
    with pytest.raises(LedgerError, match='committed_source_read_requires'):
        with ledger.atomic():
            ledger.append(make_event(EventKind.SESSION, 'isolated-fixture', {'uncommitted': True},
                event_time_ms=NOW*1000, received_time_ms=NOW*1000))
            original_native_risk_input(ledger, event.hash, available_at_ms=NOW*1000)
    assert ledger.count() == count and ledger.verify_chain()[0]


def test_rejected_mismatched_intent_stays_rejected_data_for_its_original_snapshot(tmp_path, eurusd):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    event = record(ledger, facts, request=intent(account_alias='different_alias'))
    value = original_native_risk_input(ledger, event.hash, available_at_ms=NOW*1000)
    assert value.recorded_decision == 'REJECTED'
    assert value.context.account_alias == facts.account_alias
    assert value.intent_account_alias == 'different_alias'
    assert value.execution_authority is False


def test_ctrader_original_mark_is_bound_without_fabricating_an_mt5_query(tmp_path, eurusd):
    from test_funding_runtime import setup
    ledger, transport, adapter = setup(tmp_path)
    account = adapter.sync_account()
    requests = list(transport.requests)
    context = context_for_account(ledger, adapter, account, now_ms=3000)
    contract = replace(eurusd, venue='ctrader', account_currency=account.currency)
    facts = snapshot(contract, account_alias=account.account_alias, equity=account.equity,
        balance=account.balance, native_account_context=context)
    event = record(ledger, facts)
    value = original_native_risk_input(ledger, event.hash, available_at_ms=NOW*1000)
    assert value.context.provider == 'CTRADER' and value.context.source_query_ref is None
    assert transport.requests == requests and value.execution_authority is False
