"""Exact values bind to original SQL snapshots, never to an alias or cash grant."""
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, localcontext, Inexact, Rounded, ROUND_UP, ROUND_DOWN
import os
import uuid

import pytest

from test_native_balance_reconciliation import mark, snapshot
from vati.core import Ledger, EventKind, make_event
from vati.core.units import UnitError
from vati.funding.valuation import ValuationSnapshot, read_valuation


@pytest.fixture(params=['sqlite','postgres'])
def original(tmp_path,request):
    if request.param=='postgres':
        if os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1' or not os.environ.get('VATI_TEST_PG_DSN'):
            pytest.skip('requires actual isolated PostgreSQL valuation fixture')
        from vati.core.ledger_pg import PostgresLedger
        ledger=PostgresLedger(os.environ['VATI_TEST_PG_DSN'],ledger_name='valuation-'+uuid.uuid4().hex)
    else:ledger=Ledger(tmp_path/'valuation.sqlite')
    with closing(ledger):
        point=replace(mark(1000,balance='9007199254740993.01',equity='9007199254740993.0100000001'),
            manager_bonus=Decimal('3.01'),nonwithdrawable_bonus=Decimal('5'))
        event=snapshot(ledger,point,received=2000)
        yield ledger,event,point


def read(original,**changes):
    ledger,event,point=original
    return read_valuation(ledger,**({'source_ref':event.hash,'scope_hash':point.scope_hash}|changes))


def test_original_exact_native_value_and_optional_credit_keep_distinct_bases(original):
    ledger,event,point=original;before=ledger.head(),ledger.count()
    with localcontext() as context:
        context.prec=2;context.Emax=2;context.Emin=-2
        context.traps[Inexact]=context.traps[Rounded]=True
        value=read(original);body=value.body()
        assert value.net_equity.decimal==point.net_equity
        assert body['net_equity']['minor_units']=='90071992547409930100000001'
        assert body['net_equity']['scale']==10
        assert body['cash_balance']['minor_units']=='900719925474099301'
        assert body['separate_credits']['manager_bonus']['minor_units']=='301'
        assert body['separate_credits']['ib_bonus'] is None
        assert body['separate_credits']['nonwithdrawable_bonus']['minor_units']=='5'
        assert value.equity_point().native_order==point.balance_version
        assert value.equity_point().source_ref==event.hash
    assert body['source_ref']==event.hash and body['available_at_ms']==2000 and body['observed_at_ms']==1000
    assert body['risk_capital_qualified'] is body['execution_authority'] is body['holdings_valuation_complete'] is False
    assert body['settlement_qualification']=='NOT_ISSUED'
    body['net_equity']['minor_units']='0'
    assert value.net_equity.decimal==point.net_equity and (ledger.head(),ledger.count())==before


def test_source_reference_and_native_scope_cannot_be_replaced_by_matching_alias(original):
    ledger,event,point=original;before=ledger.head(),ledger.count()
    with pytest.raises(UnitError,match='SOURCE_UNAVAILABLE'):read(original,source_ref='0'*64)
    with pytest.raises(UnitError,match='SCOPE_MISMATCH'):read(original,scope_hash='f'*64)
    with ledger.atomic():
        with pytest.raises(UnitError,match='OWN_WRITER'):read(original)
    with ledger.read_snapshot():assert read(original).body()['source_ref']==event.hash
    assert (ledger.head(),ledger.count())==before


@pytest.mark.parametrize('capacity',['bytes','count'])
def test_read_capacity_refuses_without_partial_or_zero_valuation(original,capacity):
    ledger,event,point=original
    if capacity=='count':
        snapshot(ledger,replace(point,observed_at_ms=3000),received=4000)
        kwargs={'max_snapshots':1}
    else:kwargs={'max_bytes':1}
    before=ledger.head(),ledger.count()
    with pytest.raises(UnitError,match='CAPACITY'):read(original,**kwargs)
    assert (ledger.head(),ledger.count())==before


def test_actual_period_resolves_original_valuation_lineage_without_creating_new_facts(original):
    from test_native_balance_reconciliation import observe
    from vati.funding.reconciliation import period_report
    ledger,event,point=original
    last=snapshot(ledger,replace(point,observed_at_ms=3000,net_equity=Decimal('9007199254740992.01')),received=4000)
    scope=observe(ledger);before=ledger.head(),ledger.count()
    result=period_report(ledger,scope)
    assert result['state']=='MEASURED' and result['balance_state']=='RECONCILED'
    values=result['valuation_snapshots']
    assert values['baseline']==read(original).body()
    assert values['closing']==read(original,source_ref=last.hash).body()
    assert values['baseline']['source_ref']==result['baseline_ref']==event.hash
    assert values['closing']['source_ref']==result['closing_ref']==last.hash
    assert result['performance']['input_refs']==[event.hash,last.hash]
    assert result['flow_adjusted_risk']['state']=='MEASURED'
    assert result['flow_adjusted_risk']['calculation']['flow_neutral_return']==result['performance']['flow_neutral_return']
    assert values['closing']['risk_capital_qualified'] is values['closing']['execution_authority'] is False
    assert (ledger.head(),ledger.count())==before


def test_incomplete_independent_source_readback_cannot_claim_a_complete_original(original,monkeypatch):
    ledger,event,point=original
    snapshot(ledger,replace(point,observed_at_ms=3000),received=4000)
    iterator=ledger.iter
    def missing(kind=None,**kwargs):
        for row in iterator(kind,**kwargs):
            if kind is EventKind.ACCOUNT_SNAPSHOT and row.hash!=event.hash:continue
            yield row
    monkeypatch.setattr(ledger,'iter',missing)
    assert ledger.verify_chain()[0]
    with pytest.raises(UnitError,match='READBACK_COUNT_INVALID'):read(original)


def test_actual_period_keeps_intermediate_drawdown_in_the_immutable_calculation(original):
    from test_native_balance_reconciliation import observe
    from vati.funding.reconciliation import period_report
    ledger,event,point=original
    trough=snapshot(ledger,replace(point,observed_at_ms=2000,net_equity=Decimal('4503599627370496.50500000005')),received=2100)
    peak=snapshot(ledger,replace(point,observed_at_ms=3000,net_equity=Decimal('18014398509481986.0200000002')),received=3100)
    last=snapshot(ledger,replace(point,observed_at_ms=4000),received=4100)
    scope=observe(ledger,to_ms=4000);before=ledger.head(),ledger.count()
    result=period_report(ledger,scope);calculation=result['flow_adjusted_risk']
    assert result['state']==calculation['state']=='MEASURED'
    assert Decimal(result['performance']['flow_neutral_return'])==0
    assert Decimal(result['performance']['worst_observed_drawdown'])==Decimal('.5')
    assert calculation['source_refs']==[event.hash,trough.hash,peak.hash,last.hash]
    assert calculation['calculation']['worst_observed_drawdown']==result['performance']['worst_observed_drawdown']
    assert calculation['risk_capital_qualified'] is calculation['execution_authority'] is False
    assert (ledger.head(),ledger.count())==before


@pytest.mark.parametrize('damage',['producer','kind','schema','decision','verified','alias','currency',
    'balance','equity','float-equity','native-scope','native-basis','early-receipt','bool-clock','future-event','oversize'])
def test_sealed_foreign_or_ill_typed_snapshot_cannot_be_a_native_valuation(original,damage):
    ledger,event,point=original;payload=deepcopy(event.payload)
    producer=event.producer;kind=event.kind;schema=1;decision=None;received=2000;at=event.event_time_ms
    if damage=='producer':producer='unqualified-advisor'
    elif damage=='kind':kind=EventKind.SESSION
    elif damage=='schema':schema=True
    elif damage=='decision':decision=1500
    elif damage=='verified':payload['verified']=1
    elif damage=='alias':payload['account_alias']='other'
    elif damage=='currency':payload['currency']='USD'
    elif damage in {'balance','equity'}:payload[damage]='1'
    elif damage=='float-equity':payload['equity']=1.0
    elif damage=='native-scope':payload['native_account_mark']['native_account_id']=999
    elif damage=='native-basis':payload['native_account_mark']['valuation_basis']='TOTAL_WITH_CREDIT'
    elif damage=='early-receipt':received=999
    elif damage=='future-event':at=2001
    elif damage=='oversize':payload['equity']='0'*129+'1'
    else:at=True
    forged=make_event(kind,producer,payload,event_time_ms=at,received_time_ms=received,
        decision_time_ms=decision,schema_version=schema,correlation_id=event.correlation_id)
    with pytest.raises(UnitError,match='VALUATION_'):ValuationSnapshot(forged)


def test_actual_period_drawdown_does_not_inherit_unrelated_decimal_rounding_or_traps(tmp_path):
    from test_native_balance_reconciliation import observe
    from vati.funding.reconciliation import period_report
    with closing(Ledger(tmp_path/'period.sqlite')) as ledger:
        snapshot(ledger,mark(1000,balance='3',equity='3'))
        snapshot(ledger,mark(3000,balance='3',equity='2'))
        scope=observe(ledger)
        reports=[]
        for rounding in (ROUND_UP,ROUND_DOWN):
            with localcontext() as context:
                context.rounding=rounding
                reports.append(period_report(ledger,scope))
        assert reports[0]['state']=='MEASURED' and reports[0]==reports[1]
        with localcontext() as context:
            context.traps[Inexact]=context.traps[Rounded]=True
            assert period_report(ledger,scope)==reports[0]
