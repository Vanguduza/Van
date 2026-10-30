"""Original physical history joins aliases without assigning unbound facts."""
from dataclasses import replace

import pytest

from conftest import NOW
from test_native_risk_history_inputs import native_facts, record
from vati.core import EventKind, Ledger, make_event
from vati.core.ledger import LedgerError
from vati.execution.mt5_identity import Mt5Identity
from vati.funding.mt5_journal import Mt5FundingBook
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk.account_context import context_for_account
from vati.risk.native_history import original_native_risk_history, NativeRiskSourceUnavailable


def other_context(ledger, adapter, account, facts, *, alias, server=None, currency=None):
    frame = replace(account.funding_mark, account_alias=alias,
        server=server or account.funding_mark.server, currency=currency or account.currency)
    current = replace(account, account_alias=alias, currency=frame.currency, funding_mark=frame)
    adapter.account_alias = alias
    adapter.identity = Mt5Identity(str(frame.login), frame.server, frame.currency, frame.demo)
    capture = capture_cached_mt5(ledger, current, now_ms=10001)
    context = context_for_account(ledger, adapter, current, now_ms=10001, mt5_capture=capture)
    return replace(facts, account_alias=alias, native_account_context=context,
        symbol_contract=replace(facts.symbol_contract, account_currency=frame.currency))


def test_aliases_join_only_through_actual_original_source_receipts(tmp_path, eurusd):
    ledger, adapter, account, _, facts = native_facts(tmp_path, eurusd)
    first = record(ledger, facts)
    second = record(ledger, other_context(ledger, adapter, account, facts, alias='new_label'))
    before = tuple(e.body() for e in ledger.iter())
    value = original_native_risk_history(ledger, second.hash, available_at_ms=NOW*1000)
    assert [v.event_ref for v in value.original_inputs] == [first.hash, second.hash]
    assert [v.context.account_alias for v in value.original_inputs] == ['native', 'new_label']
    assert len({v.context.source_query_ref for v in value.original_inputs}) == 1
    assert value.physical_account_key == facts.native_account_context.physical_account_key
    assert value.unresolved_refs == ()
    assert value.execution_authority is value.risk_capital_qualified is False
    assert tuple(e.body() for e in ledger.iter()) == before
    assert adapter.queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0] == 0


def test_same_alias_cannot_merge_another_proven_physical_account(tmp_path, eurusd):
    ledger, adapter, account, _, facts = native_facts(tmp_path, eurusd)
    first = record(ledger, facts)
    second = record(ledger, other_context(ledger, adapter, account, facts,
        alias=facts.account_alias, server='Different-Broker-Demo'))
    value = original_native_risk_history(ledger, second.hash, available_at_ms=NOW*1000)
    assert [v.event_ref for v in value.original_inputs] == [second.hash]
    assert value.physical_account_key != facts.native_account_context.physical_account_key
    assert value.unresolved_refs == ()
    original = original_native_risk_history(ledger, first.hash, available_at_ms=NOW*1000)
    assert [v.event_ref for v in original.original_inputs] == [first.hash]


def test_same_physical_account_with_changed_monetary_scope_requires_reconciliation(tmp_path, eurusd):
    ledger, adapter, account, _, facts = native_facts(tmp_path, eurusd)
    first = record(ledger, facts)
    changed = other_context(ledger, adapter, account, facts, alias='eur_label', currency='EUR')
    second = record(ledger, changed)
    assert changed.native_account_context.physical_account_key == facts.native_account_context.physical_account_key
    value = original_native_risk_history(ledger, second.hash, available_at_ms=NOW*1000)
    assert [v.event_ref for v in value.original_inputs] == [second.hash]
    assert value.unresolved_refs == (first.hash,)


@pytest.mark.parametrize('damage', ['legacy', 'query', 'decision', 'producer'])
def test_unknown_original_identity_is_retained_as_unresolved_not_assigned_from_a_label(tmp_path, eurusd, damage):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    first = record(ledger, facts)
    if damage == 'legacy':
        broken = record(ledger, replace(facts, native_account_context=None))
    elif damage == 'query':
        broken = record(ledger, replace(facts,
            native_account_context=replace(facts.native_account_context, source_query_ref='0'*64)))
    elif damage == 'producer':
        broken = record(ledger, facts, producer='unqualified-model')
    else:
        def change(payload):
            payload['decision']['approved_size'] = '99999'
        broken = record(ledger, facts, damage=change)
    value = original_native_risk_history(ledger, first.hash, available_at_ms=NOW*1000)
    assert [v.event_ref for v in value.original_inputs] == [first.hash]
    assert value.unresolved_refs == (broken.hash,)


def test_original_knowledge_cutoff_does_not_import_a_later_record(tmp_path, eurusd):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    first = record(ledger, facts)
    second = record(ledger, replace(facts, peak_equity=facts.peak_equity+1), now_ms=NOW*1000+1)
    value = original_native_risk_history(ledger, first.hash, available_at_ms=NOW*1000)
    assert [v.event_ref for v in value.original_inputs] == [first.hash]
    assert value.unresolved_refs == ()
    later = original_native_risk_history(ledger, first.hash, available_at_ms=NOW*1000+1)
    assert [v.event_ref for v in later.original_inputs] == [first.hash, second.hash]


def test_chain_and_each_original_query_scope_are_verified_once_per_batch(tmp_path, eurusd, monkeypatch):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    events = [record(ledger, replace(facts, peak_equity=facts.peak_equity+i)) for i in range(12)]
    verify, queries = ledger.verify_chain, Mt5FundingBook._queries
    seen = {'chain': 0, 'queries': []}
    def counted_chain():
        seen['chain'] += 1
        return verify()
    def counted_queries(book, scope):
        seen['queries'].append(scope)
        return queries(book, scope)
    monkeypatch.setattr(ledger, 'verify_chain', counted_chain)
    monkeypatch.setattr(Mt5FundingBook, '_queries', counted_queries)
    value = original_native_risk_history(ledger, events[-1].hash, available_at_ms=NOW*1000)
    assert [v.event_ref for v in value.original_inputs] == [e.hash for e in events]
    assert seen == {'chain': 1, 'queries': [facts.native_account_context.monetary_scope_hash]}


def test_writer_staged_facts_cannot_masquerade_as_original_history(tmp_path, eurusd):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    first = record(ledger, facts)
    before = ledger.count()
    with pytest.raises(LedgerError, match='committed_source_read_requires'):
        with ledger.atomic():
            record(ledger, replace(facts, peak_equity=facts.peak_equity+1))
            original_native_risk_history(ledger, first.hash, available_at_ms=NOW*1000)
    assert ledger.count() == before


def test_owner_controls_remain_original_alias_scoped_facts_not_aggregate_resets(tmp_path, eurusd):
    ledger, adapter, account, _, facts = native_facts(tmp_path, eurusd)
    first = record(ledger, facts)
    control = make_event(EventKind.SESSION, 'vati-cycle',
        {'event': 'DRAWDOWN_RESUMED', 'account_alias': 'native',
         'old_peak_equity': '12000', 'new_peak_equity': '10000',
         'owner_signature_ref': 'UNQUALIFIED_SOURCE_FIXTURE_NOT_A_GRANT'},
        event_time_ms=NOW*1000, received_time_ms=NOW*1000)
    ledger.append(control)
    second = record(ledger, other_context(ledger, adapter, account, facts, alias='another_label'))
    value = original_native_risk_history(ledger, second.hash, available_at_ms=NOW*1000)
    assert [v.event_ref for v in value.original_inputs] == [first.hash, second.hash]
    assert next(e for e in ledger.iter() if e.hash == control.hash).body() == control.body()
    assert value.execution_authority is False


@pytest.mark.parametrize('anchor', ['0'*64, 'not-a-digest'])
def test_missing_or_invalid_anchor_cannot_claim_complete_history(tmp_path, anchor):
    ledger = Ledger(tmp_path/'empty.sqlite')
    try:
        with pytest.raises(NativeRiskSourceUnavailable):
            original_native_risk_history(ledger, anchor, available_at_ms=NOW*1000)
    finally:
        ledger.close()


def test_changed_original_ledger_bytes_cannot_supply_a_history_index(tmp_path, eurusd):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    event = record(ledger, facts)
    ledger._conn.execute('UPDATE events SET producer=? WHERE event_hash=?',
        ('changed-native-producer', event.hash))
    ledger._conn.commit()
    with pytest.raises(NativeRiskSourceUnavailable, match='integrity'):
        original_native_risk_history(ledger, event.hash, available_at_ms=NOW*1000)
