"""Actual native source/history readback never reattributes a shared peak."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from conftest import NOW, intent
from test_native_risk_history_inputs import native_facts, record
from test_native_risk_history_index import other_context
from test_physical_control_history import original_control
from vati.core import Ledger, EventKind, make_event
from vati.risk.physical_baselines import PhysicalRiskBasisBook, DAY_MS, WEEK_MS
from vati.risk.serde import snapshot_to_dict, snapshot_from_dict


def book(ledger, facts, now=NOW*1000):
    return PhysicalRiskBasisBook.rebuild(ledger, facts.native_account_context, available_at_ms=now)


def legacy(ledger, facts, trade, peak):
    return record(ledger,replace(facts,peak_equity=D(peak)),
        request=intent(trade_intent_id=trade,account_alias=facts.account_alias))


def shared(ledger, facts, trade):
    before=book(ledger,facts)
    event=before.observation_event(facts.native_account_context,now_ms=NOW*1000,producer='vati-cycle')
    ledger.append(event)
    state=book(ledger,facts)
    values=state.projection(NOW*1000)
    assert not values.issue
    snap=replace(facts,peak_equity=values.peak,day_start_equity=values.day,
        week_start_equity=values.week,native_risk_basis_ref=event.hash)
    risk=record(ledger,snap,request=intent(trade_intent_id=trade,account_alias=facts.account_alias))
    return event,risk


def test_shared_peaks_never_reappear_after_independently_authorized_original_resets(tmp_path,eurusd):
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    legacy(ledger,a,'a-original','15000')
    b=other_context(ledger,adapter,account,a,alias='second_alias')
    legacy(ledger,b,'b-original','13000')
    shared(ledger,b,'b-shared')
    original_control(ledger,a.native_account_context,action='resume_drawdown')
    assert book(ledger,b).projection(NOW*1000).peak == D('13000')
    shared(ledger,a,'a-shared')
    original_control(ledger,b.native_account_context,action='resume_drawdown')
    state=book(ledger,b)
    assert state.projection(NOW*1000).peak == a.equity
    shared(ledger,b,'b-after-both-resets')
    assert book(ledger,a).projection(NOW*1000).peak == a.equity
    reopened=Ledger(ledger.path)
    assert book(reopened,a).projection(NOW*1000) == book(ledger,a).projection(NOW*1000)
    assert ledger.count(EventKind.ORDER_COMMAND) == 0


def test_new_alias_sees_original_baseline_before_its_first_decision(tmp_path,eurusd):
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    legacy(ledger,a,'original','15000')
    b=other_context(ledger,adapter,account,a,alias='second_alias')
    state=book(ledger,b)
    assert state.projection(NOW*1000).peak == D('15000')
    basis,_=shared(ledger,b,'first-b')
    assert basis.payload['peak_equity'] == str(a.equity)
    assert book(ledger,b).origins['second_alias'].peak == a.equity


@pytest.mark.parametrize('damage',['aggregate_seed','stale_previous','missing_query','producer','schema'])
def test_unbound_or_stale_basis_cannot_release_or_inflate_risk(tmp_path,eurusd,damage):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    legacy(ledger,facts,'original','15000')
    planned=book(ledger,facts).observation_event(facts.native_account_context,now_ms=NOW*1000,producer='vati-cycle')
    p=planned.payload
    if damage=='aggregate_seed':p['peak_equity']='999999'
    elif damage=='stale_previous':p['previous_origin_ref']='0'*64
    elif damage=='missing_query':p['native_account_context']['source_query_ref']='0'*64
    elif damage=='schema':p['schema']=True
    bad=make_event(EventKind.SESSION,'model-advisory' if damage=='producer' else 'vati-cycle',p,
        event_time_ms=NOW*1000,received_time_ms=NOW*1000)
    ledger.append(bad)
    value=book(ledger,facts).projection(NOW*1000)
    assert bad.hash in value.unresolved_refs and value.issue
    assert value.peak == D('15000')


@pytest.mark.parametrize('damage',['missing','other_alias','aggregate','stale'])
def test_shared_snapshot_requires_its_exact_original_basis(tmp_path,eurusd,damage):
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    legacy(ledger,a,'original','15000')
    basis,_=shared(ledger,a,'valid-shared')
    b=other_context(ledger,adapter,account,a,alias='second_alias') if damage=='other_alias' else a
    if damage=='stale':
        original_control(ledger,a.native_account_context,action='resume_drawdown')
    bad=record(ledger,replace(b,native_risk_basis_ref='0'*64 if damage=='missing' else basis.hash,
        peak_equity=D('17000') if damage=='aggregate' else D('15000')),
        request=intent(trade_intent_id='invalid-shared',account_alias=b.account_alias))
    assert bad.hash in book(ledger,b).projection(NOW*1000).unresolved_refs


def test_period_roll_preserves_peak_and_current_native_observation_seeds_new_period(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    legacy(ledger,facts,'original','15000')
    later=(NOW*1000//WEEK_MS+1)*WEEK_MS
    state=book(ledger,facts,later)
    value=state.projection(later)
    assert (value.peak,value.day,value.week)==(D('15000'),None,None)
    ledger.append(state.observation_event(facts.native_account_context,now_ms=later,producer='vati-cycle'))
    value=book(ledger,facts,later).projection(later)
    assert (value.peak,value.day,value.week)==(D('15000'),facts.equity,facts.equity)


def test_funding_held_snapshot_never_seeds_a_baseline(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    held=replace(facts,peak_equity=D('999999'),preservation_blocks_new_risk=True,
        preservation_reason='FUNDING_RISK_SOURCE_UNAVAILABLE')
    record(ledger,held)
    assert book(ledger,facts).projection(NOW*1000).peak is None


def test_optional_reference_preserves_legacy_hash_input_and_current_serialization(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    legacy_body=snapshot_to_dict(facts)
    assert 'native_risk_basis_ref' not in legacy_body
    assert snapshot_to_dict(snapshot_from_dict(legacy_body)) == legacy_body
    current=snapshot_to_dict(replace(facts,native_risk_basis_ref='a'*64))
    assert snapshot_to_dict(snapshot_from_dict(current))==current
