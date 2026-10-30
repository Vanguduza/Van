"""Actual SQLite joins retain original native owners, not configured labels."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from conftest import NOW, intent
from test_native_risk_history_inputs import native_facts, record
from test_native_risk_history_index import other_context
from vati.core import EventKind, make_event
from vati.core.canonical import canonical_hash
from vati.risk.physical_history import physical_financial_history


def approval(ledger, facts, trade):
    facts = replace(facts, peak_equity=facts.equity,
        day_start_equity=facts.equity, week_start_equity=facts.equity)
    request = intent(trade_intent_id=trade, account_alias=facts.account_alias,
        venue=facts.symbol_contract.venue)
    value = record(ledger, facts, request=request)
    assert value.payload['decision']['decision'] in {'APPROVED','REDUCED'}
    return value


def close(ledger, original, *, alias=None, producer='vati-cycle', **changes):
    p = {'trade_intent_id': original.correlation_id,
        'strategy_id': original.payload['inputs']['intent']['strategy_id'], 'pnl':'-10',
        'pnl_basis':'VENUE_NATIVE_ESTIMATE','broker_ok':True, 'record_revision':0}
    if alias is not None:
        p['account_alias'] = alias
    p.update(changes)
    e = make_event(EventKind.TRADE_REVIEW, producer, p, event_time_ms=NOW*1000,
        received_time_ms=NOW*1000, correlation_id=original.correlation_id)
    ledger.append(e)
    return e


def test_real_original_closes_join_aliases_and_preserve_immutable_review_labels(tmp_path, eurusd):
    ledger, adapter, account, _, facts = native_facts(tmp_path, eurusd)
    first = approval(ledger, facts, 'original-a')
    a = close(ledger, first, alias='native')
    current = other_context(ledger, adapter, account, facts, alias='another_label')
    second = approval(ledger, current, 'original-b')
    b = close(ledger, second)  # legacy unlabelled review uses exact original trade
    before = tuple(e.body() for e in ledger.iter())
    value = physical_financial_history(ledger, current.native_account_context, available_at_ms=NOW*1000)
    reviews = [f for f in value.facts if f.kind == 'TRADE_REVIEW']
    assert [(f.event_ref,f.origin_alias) for f in reviews] == [(a.hash,'native'),(b.hash,'another_label')]
    assert value.unresolved_refs == () and not value.issue
    copy = reviews[0].payload; copy['pnl']='9999'
    assert reviews[0].payload['pnl'] == '-10'
    assert tuple(e.body() for e in ledger.iter()) == before
    assert value.execution_authority is value.risk_capital_qualified is False


def test_reused_alias_does_not_join_a_different_native_account_close(tmp_path, eurusd):
    ledger, adapter, account, _, facts = native_facts(tmp_path, eurusd)
    first = approval(ledger, facts, 'original-a'); close(ledger, first, alias='native')
    current = other_context(ledger, adapter, account, facts, alias='native',server='Other-Broker-Demo')
    second = approval(ledger, current, 'original-b'); own = close(ledger, second, alias='native')
    value = physical_financial_history(ledger, current.native_account_context, available_at_ms=NOW*1000)
    assert [f.event_ref for f in value.facts if f.kind == 'TRADE_REVIEW'] == [own.hash]
    assert value.unresolved_refs == ()


@pytest.mark.parametrize('damage', ['producer','alias','strategy','money','revision','artifact','identity','unknown'])
def test_bad_review_cannot_borrow_an_original_native_approval(tmp_path, eurusd, damage):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    original = approval(ledger, facts, 'original-a')
    changes = {'alias': {'account_alias':'wrong_alias'}, 'strategy': {'strategy_id':'owner.manual'},
        'money': {'pnl':'NaN'}, 'revision': {'record_revision':1}, 'artifact': {'artifact_hash':'0'*64},
        'identity': {'trade_intent_id':'different-trade'}, 'unknown': {'pnl_basis':'UNKNOWN_ORIGINAL_OUTCOME'}}
    bad = close(ledger, original, producer='model-advisory' if damage=='producer' else 'vati-cycle',
        **changes.get(damage,{}))
    value = physical_financial_history(ledger, facts.native_account_context, available_at_ms=NOW*1000)
    assert bad.hash in value.unresolved_refs and value.issue
    assert not [f for f in value.facts if f.kind == 'TRADE_REVIEW']


def test_same_trade_id_with_conflicting_native_owners_remains_unresolved(tmp_path, eurusd):
    ledger, adapter, account, _, facts = native_facts(tmp_path, eurusd)
    original = approval(ledger, facts, 'same-trade')
    current = other_context(ledger, adapter, account, facts, alias='another_label')
    approval(ledger, current, 'same-trade')
    bad = close(ledger, original, alias='native')
    value = physical_financial_history(ledger, current.native_account_context, available_at_ms=NOW*1000)
    assert bad.hash in value.unresolved_refs


def test_rejected_intent_cannot_supply_financial_close_ownership(tmp_path, eurusd):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    rejected = record(ledger, facts, request=intent(account_alias='different_alias'))
    assert rejected.payload['decision']['decision'] == 'REJECTED'
    bad = close(ledger, rejected, alias='native')
    value = physical_financial_history(ledger, facts.native_account_context, available_at_ms=NOW*1000)
    assert bad.hash in value.unresolved_refs


def test_bare_alias_owner_reset_is_not_silently_promoted_to_physical_power(tmp_path, eurusd):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    approval(ledger, facts, 'original-a')
    e = make_event(EventKind.SESSION,'vati-cycle',{'event':'LOSS_STREAK_RESET',
        'account_alias':'native','scope':'*ACCOUNT*','owner_signature_ref':'UNQUALIFIED_TEST_DATA'},
        event_time_ms=NOW*1000,received_time_ms=NOW*1000)
    ledger.append(e)
    value = physical_financial_history(ledger, facts.native_account_context, available_at_ms=NOW*1000)
    assert e.hash in value.unresolved_refs
    assert not [f for f in value.facts if f.kind == 'SESSION']


def test_two_different_original_close_records_cannot_count_one_trade_twice(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    original=approval(ledger,facts,'original-a')
    first=close(ledger,original,alias='native')
    correction=close(ledger,original,alias='native',pnl='-20')
    value=physical_financial_history(ledger,facts.native_account_context,available_at_ms=NOW*1000)
    assert {first.hash,correction.hash} <= set(value.unresolved_refs)
    assert not [f for f in value.facts if f.kind=='TRADE_REVIEW']


def test_paper_settlement_flags_cannot_release_a_native_physical_accounts_losses(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    loss=approval(ledger,facts,'loss');close(ledger,loss,alias='native')
    gain=approval(ledger,facts,'gain')
    paper=close(ledger,gain,alias='native',pnl='100',pnl_basis='REPORTED_NET_CONFIRMED',
        maturity={'parent_final':True,'fees_final':True,'cash_reconciled':True,
            'source':'DETERMINISTIC_PAPER_SETTLEMENT','source_environment':'DEMO','account_currency':'USD'})
    value=physical_financial_history(ledger,facts.native_account_context,available_at_ms=NOW*1000)
    assert paper.hash in value.unresolved_refs
    assert paper.hash not in [f.event_ref for f in value.facts if f.kind=='TRADE_REVIEW']


@pytest.mark.parametrize('later',['publication','availability'])
def test_a_close_cannot_borrow_a_later_original_native_approval(tmp_path,eurusd,later):
    from conftest import intent
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    request=intent(trade_intent_id='not-yet-approved',account_alias=facts.account_alias)
    if later=='publication':
        # Same source clock still requires original approval to precede close.
        from types import SimpleNamespace
        bad=close(ledger,SimpleNamespace(correlation_id=request.trade_intent_id,
            payload={'inputs':{'intent':{'strategy_id':request.strategy_id}}}),alias=facts.account_alias)
        approval(ledger,facts,request.trade_intent_id)
    else:
        original=record(ledger,replace(facts,peak_equity=facts.equity,
            day_start_equity=facts.equity,week_start_equity=facts.equity),
            request=request,now_ms=NOW*1000+1)
        assert original.payload['decision']['decision'] in {'APPROVED','REDUCED'}
        bad=close(ledger,original,alias=facts.account_alias)
    value=physical_financial_history(ledger,facts.native_account_context,available_at_ms=NOW*1000+1)
    assert bad.hash in value.unresolved_refs
    assert bad.hash not in [f.event_ref for f in value.facts if f.kind=='TRADE_REVIEW']
