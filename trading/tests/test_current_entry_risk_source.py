"""Actual current RiskAuthority evidence joined to the original intended entry."""
from dataclasses import replace
from decimal import Decimal as D
import pytest

from test_router_native_entry_deadline import flow
from test_entry_margin_binding import entry_command
from vati.core import EventKind


def current_entry(tmp_path,eurusd,*,refused=False,native_margin=None,include_runtime=False,mandate_changes=None):
    sdk,worker,adapter,clock,mandate,trade,approved,ledger,router=flow(tmp_path,eurusd)
    original=next(ledger.iter(EventKind.RISK_DECISION))
    if mandate_changes:
        from test_native_risk_history_inputs import record
        from vati.risk import TradingMandate,RiskAuthority
        from vati.risk.serde import snapshot_from_dict
        from vati.execution.risk_refresh import CurrentRiskFacts
        from conftest import mandate_dict
        raw=original.payload['inputs']['mandate']|mandate_changes
        raw.pop('owner_signature_ref',None)
        raw=mandate_dict(**raw)
        mandate=TradingMandate.from_mapping(raw)
        facts=snapshot_from_dict(original.payload['inputs']['snapshot'])
        original=record(ledger,facts,request=trade,grant=raw)
        router.current_risk_authority=RiskAuthority(mandate)
        router.current_risk_facts_provider=lambda *a,**kw:CurrentRiskFacts(facts,clock['ms'])
        approved=RiskAuthority(mandate).evaluate_safe(trade,facts)
    if native_margin is not None:sdk.order_calc_margin=lambda *args:float(native_margin)
    command=replace(entry_command(original),expires_at_ms=mandate.expires_at_unix*1000,command_hash='').sealed()
    margin_ref,_=router._native_entry_margin(command,adapter,now_ms=clock['ms'])
    if refused:
        from vati.execution.risk_refresh import CurrentRiskFacts
        from vati.risk.serde import snapshot_from_dict
        facts=replace(snapshot_from_dict(original.payload['inputs']['snapshot']),free_margin=D('0'))
        router.current_risk_facts_provider=lambda *a,**kw:CurrentRiskFacts(facts,clock['ms'])
        from vati.execution.router import RouterError
        with pytest.raises(RouterError,match='current account risk refused'):
            router._current_account_risk(trade,approved,mandate,command,adapter,
                now_ms=clock['ms'],market_reference=None)
        current_ref=list(ledger.iter(EventKind.RISK_REVALIDATION))[-1].hash
    else:
        current_ref=router._current_account_risk(trade,approved,mandate,command,adapter,
            now_ms=clock['ms'],market_reference=None)
    result=(sdk,clock,ledger,command,margin_ref,current_ref)
    return (*result,router) if include_runtime else result


def test_original_current_risk_and_native_margin_are_one_exact_entry_source(tmp_path,eurusd):
    from vati.risk.current_entry_source import current_entry_source
    sdk,clock,ledger,command,margin_ref,current_ref=current_entry(tmp_path,eurusd)
    try:
        before=ledger.count()
        source=current_entry_source(ledger,command,margin_ref,current_ref,available_at_ms=clock['ms'])
        body=source.body()
        assert body['command_hash']==command.command_hash
        assert body['current_risk_ref']==current_ref and body['entry_margin_ref']==margin_ref
        assert body['risk_state']=='SUFFICIENT'
        assert body['snapshot']['native_account_context']['monetary_scope_hash']==body['monetary_scope_hash']
        assert body['execution_authority'] is body['reservation_qualified'] is False
        assert body['quote_time_state']=='WITHIN_ORIGINAL_WINDOW'
        body['snapshot']['free_margin']='999999999'
        assert source.body()['snapshot']['free_margin']!='999999999'
        assert ledger.count()==before and ledger.count(EventKind.ORDER_COMMAND)==0 and not sdk.sent
    finally:ledger.close()


def test_expired_source_is_original_data_and_never_a_fresh_reservation_grant(tmp_path,eurusd):
    from vati.risk.current_entry_source import current_entry_source
    sdk,clock,ledger,command,margin_ref,current_ref=current_entry(tmp_path,eurusd)
    try:
        first=current_entry_source(ledger,command,margin_ref,current_ref,available_at_ms=clock['ms']).body()
        clock['ms']=command.expires_at_ms
        old=current_entry_source(ledger,command,margin_ref,current_ref,available_at_ms=clock['ms']).body()
        assert old['quote_time_state']=='EXPIRED'
        assert old['quote_valid_until_ms']==first['quote_valid_until_ms']
        assert old['current_risk_ref']==first['current_risk_ref']
        assert old['execution_authority'] is old['reservation_qualified'] is False
        assert not sdk.sent
    finally:ledger.close()


@pytest.mark.parametrize('damage',['command','margin_ref','risk_ref','availability'])
def test_foreign_or_unavailable_source_cannot_supply_original_entry_resources(tmp_path,eurusd,damage):
    from vati.risk.current_entry_source import current_entry_source,CurrentEntrySourceError
    sdk,clock,ledger,command,margin_ref,current_ref=current_entry(tmp_path,eurusd)
    try:
        at=clock['ms'];before=ledger.count()
        if damage=='command':command=replace(command,targets=(D('1.2'),),command_hash='').sealed()
        elif damage=='margin_ref':margin_ref=current_ref
        elif damage=='risk_ref':current_ref=margin_ref
        else:at-=1
        with pytest.raises(CurrentEntrySourceError):
            current_entry_source(ledger,command,margin_ref,current_ref,available_at_ms=at)
        assert ledger.count()==before and not sdk.sent
    finally:ledger.close()


def test_actual_current_risk_refusal_remains_refused_despite_a_positive_margin_quote(tmp_path,eurusd):
    from vati.risk.current_entry_source import current_entry_source
    sdk,clock,ledger,command,margin_ref,current_ref=current_entry(tmp_path,eurusd,refused=True)
    try:
        source=current_entry_source(ledger,command,margin_ref,current_ref,available_at_ms=clock['ms']).body()
        assert source['risk_state']=='REFUSED' and source['risk_reason_code']=='NO_FREE_MARGIN'
        assert source['execution_authority'] is source['reservation_qualified'] is False
        assert ledger.count(EventKind.ORDER_COMMAND)==0 and not sdk.sent
    finally:ledger.close()


@pytest.mark.parametrize('damage',['extra_field','authority','command_hash','quantity','state','decision','snapshot'])
def test_resealed_current_record_cannot_change_inner_binding_or_authority(tmp_path,eurusd,damage):
    import json
    from vati.core import make_event
    from vati.risk.current_entry_source import current_entry_source,CurrentEntrySourceError
    sdk,clock,ledger,command,margin_ref,current_ref=current_entry(tmp_path,eurusd)
    try:
        original=next(e for e in ledger.iter(EventKind.RISK_REVALIDATION) if e.hash==current_ref)
        p=json.loads(json.dumps(original.payload))
        if damage=='extra_field':p['financial_authority']=True
        elif damage=='authority':p['execution_authority']=True
        elif damage=='command_hash':p['original_command_hash']='f'*64
        elif damage=='quantity':p['original_command_quantity']='999'
        elif damage=='state':p['state']='REFUSED'
        elif damage=='decision':p['decision']['approved_size']='999'
        else:p['snapshot']['free_margin']='999999'
        changed=make_event(EventKind.RISK_REVALIDATION,original.producer,p,event_time_ms=original.event_time_ms,
            received_time_ms=original.received_time_ms,correlation_id=original.correlation_id,
            decision_time_ms=original.decision_time_ms)
        ledger.append(changed);before=ledger.count()
        assert ledger.verify_chain()[0]
        with pytest.raises(CurrentEntrySourceError):
            current_entry_source(ledger,command,margin_ref,changed.hash,available_at_ms=clock['ms'])
        assert ledger.count()==before and not sdk.sent
    finally:ledger.close()


def test_source_reader_never_promotes_its_callers_open_writer_to_durable_evidence(tmp_path,eurusd):
    from vati.core.ledger import LedgerError
    from vati.risk.current_entry_source import current_entry_source
    sdk,clock,ledger,command,margin_ref,current_ref=current_entry(tmp_path,eurusd)
    try:
        before=ledger.count()
        with ledger.atomic():
            with pytest.raises(LedgerError,match='committed_source_read_requires'):
                current_entry_source(ledger,command,margin_ref,current_ref,available_at_ms=clock['ms'])
        assert ledger.count()==before and not sdk.sent
    finally:ledger.close()


@pytest.mark.parametrize('refused',[False,True])
def test_ctrader_current_price_source_retains_actual_risk_result(tmp_path,eurusd,refused):
    from test_native_margin_book import setup_book
    from test_native_risk_history_inputs import record
    from vati.execution import ExecutionRouter,ProtectionManager
    from vati.execution.risk_refresh import CurrentRiskFacts
    from vati.execution.router import RouterError
    from vati.risk import TradingMandate,RiskAuthority,KillSwitch
    from vati.risk.serde import intent_from_dict
    from vati.risk.current_entry_source import current_entry_source
    ledger,adapter,old,book,clock,facts=setup_book(tmp_path,eurusd)
    try:
        facts=replace(facts,used_margin=D('0'),free_margin=D('10000'),margin_level_pct=None)
        original=record(ledger,facts)
        m=TradingMandate.from_mapping(original.payload['inputs']['mandate'])
        trade=intent_from_dict(original.payload['inputs']['intent']);authority=RiskAuthority(m)
        approved=authority.evaluate_safe(trade,facts)
        command=replace(entry_command(original),quantity=D('.123'),command_hash='').sealed()
        current=replace(facts,now_unix=clock['ms']//1000,free_margin=D('0') if refused else facts.free_margin)
        router=ExecutionRouter(ledger=ledger,adapters={'ctrader':adapter},kill_switch=KillSwitch(),
            protection=ProtectionManager(),clock=lambda:clock['ms'],current_risk_authority=authority,
            current_risk_facts_provider=lambda *a,**kw:CurrentRiskFacts(current,clock['ms']))
        margin_ref,_=router._native_entry_margin(command,adapter,now_ms=clock['ms'])
        if refused:
            with pytest.raises(RouterError,match='current account risk refused'):
                router._current_account_risk(trade,approved,m,command,adapter,now_ms=clock['ms'],market_reference=None)
        else:router._current_account_risk(trade,approved,m,command,adapter,now_ms=clock['ms'],market_reference=None)
        current_ref=list(ledger.iter(EventKind.RISK_REVALIDATION))[-1].hash
        before=ledger.count()
        source=current_entry_source(ledger,command,margin_ref,current_ref,available_at_ms=clock['ms']).body()
        assert source['risk_state']==('REFUSED' if refused else 'SUFFICIENT')
        assert source['price_binding']=='PROVIDER_CURRENT_PRICE_ONLY'
        assert source['execution_authority'] is source['reservation_qualified'] is False
        assert ledger.count()==before and ledger.count(EventKind.ORDER_COMMAND)==0
        assert not any(name=='ProtoOANewOrderReq' for name,_ in adapter.transport.calls)
    finally:ledger.close()
