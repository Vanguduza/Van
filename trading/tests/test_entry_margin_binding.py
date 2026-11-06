"""Original intended order -> native quote -> durable binding, without a grant."""
from dataclasses import replace
from contextlib import contextmanager
from decimal import Decimal as D
import pytest

from conftest import NOW,snapshot
from test_mt5_expected_margin import source as mt5_source
from test_native_margin_book import setup_book
from test_native_risk_history_inputs import record
from vati.core import EventKind,Ledger
from vati.execution.base import OrderCommand,StopMode
from vati.risk.contracts import Direction,LossModel
from vati.risk.native_margin_book import NativeMarginBook,NativeMarginError
from vati.risk.entry_margin import EntryMarginUnknown


def entry_command(event):
    i=event.payload['inputs']['intent'];decision=event.payload['decision']
    assert decision['decision'] in ('APPROVED','REDUCED'),decision['reason_code']
    return OrderCommand(i['trade_intent_id'],decision['decision_hash'],i['idempotency_key'],
        i['account_alias'],i['venue'],i['symbol'],Direction(i['direction']),'MARKET',
        D('.10'),D(i['entry']),D(i['stop']),StopMode.VENUE,LossModel.STOP_DISTANCE,
        expires_at_ms=NOW*1000+2000,strategy_id=i['strategy_id'],strategy_version=i['strategy_version']).sealed()


def mt5_entry(tmp_path,eurusd,*,ledger=None):
    sdk,worker,adapter,now,ledger,context=mt5_source(tmp_path,ledger=ledger,at=NOW*1000)
    facts=snapshot(eurusd,account_alias=adapter.account_alias,balance=D('10000'),equity=D('10000'),
        used_margin=D('0'),free_margin=D('10000'),margin_level_pct=None,native_account_context=context)
    event=record(ledger,facts);now['ms']+=1000
    return sdk,adapter,now,ledger,event,NativeMarginBook(ledger,clock=lambda:now['ms'])


def test_actual_signed_sdk_to_sql_binding_retains_original_order_and_read_only_estimate(tmp_path,eurusd):
    sdk,adapter,now,ledger,event,book=mt5_entry(tmp_path,eurusd)
    try:
        cmd=entry_command(event)
        receipt=book.capture_entry(adapter,event.hash,cmd,deadline_ms=NOW*1000+2000)
        read=book.lookup_entry(cmd.command_hash,receipt['source_ref'])
        assert receipt['state']=='ORIGINAL_ENTRY_MARGIN_BOUND' and read['receipt']==receipt
        assert receipt['command_hash']==cmd.command_hash and receipt['original_input_ref']==event.hash
        assert receipt['reservation_qualified'] is receipt['execution_authority'] is False
        assert read['observation']['request']=={'symbol':cmd.symbol,'type':'BUY','volume':str(cmd.quantity),'price':str(cmd.entry_price)}
        assert read['price_binding']=='ORIGINAL_COMMAND_REFERENCE_PRICE'
        assert read['estimate_money']==read['observation']['estimate_money']
        assert ledger.count(EventKind.ORDER_COMMAND)==0 and not sdk.sent
    finally:ledger.close()


def test_actual_ctrader_current_price_quote_binds_exact_order_without_inventing_price_valuation(tmp_path,eurusd):
    ledger,adapter,old,book,now,facts=setup_book(tmp_path,eurusd)
    try:
        event=record(ledger,replace(facts,used_margin=D('0'),free_margin=D('10000'),margin_level_pct=None))
        cmd=replace(entry_command(event),quantity=D('.123'),command_hash='').sealed()
        receipt=book.capture_entry(adapter,event.hash,cmd,deadline_ms=NOW*1000+2000)
        read=book.lookup_entry(cmd.command_hash,receipt['source_ref'])
        assert read['observation']['symbol']==cmd.symbol
        assert D(read['observation']['original_quantity'])==cmd.quantity
        assert read['estimate_money']==read['observation']['buy_margin']
        assert read['price_binding']=='PROVIDER_CURRENT_PRICE_ONLY'
        assert receipt['reservation_qualified'] is receipt['execution_authority'] is False
        assert not any(name in ('ProtoOANewOrderReq','ProtoOAAmendOrderReq') for name,_ in adapter.transport.calls)
    finally:ledger.close()


@pytest.mark.parametrize('change',[
    {'account_alias':'foreign'},{'venue':'ctrader'},{'symbol':'GBPUSD'},{'direction':Direction.SHORT},
    {'strategy_id':'foreign'},{'strategy_version':'foreign'},{'idempotency_key':'foreign'},
    {'trade_intent_id':'foreign'},{'decision_hash':'f'*64},{'quantity':D('9999')},
    {'quantity':D('0')},{'quantity':D('NaN')},{'quantity':D('1e129')},
])
def test_foreign_or_invalid_entry_never_reaches_original_native_read(tmp_path,eurusd,change):
    sdk,adapter,now,ledger,event,book=mt5_entry(tmp_path,eurusd)
    try:
        cmd=replace(entry_command(event),**change,command_hash='')
        if change.get('quantity')!=D('1e129'):cmd=cmd.sealed()
        with pytest.raises(NativeMarginError):book.capture_entry(adapter,event.hash,cmd,deadline_ms=NOW*1000+2000)
        assert sdk.margin_calls==[] and not sdk.sent and ledger.count(EventKind.ORDER_COMMAND)==0
    finally:ledger.close()


@pytest.mark.parametrize('changes',[{'lots':D('.11')},{'price':D('1.101')},{'direction':Direction.SHORT},{'symbol':'GBPUSD'}])
def test_independent_native_read_for_other_request_cannot_bind_this_order(tmp_path,eurusd,changes):
    sdk,adapter,now,ledger,event,book=mt5_entry(tmp_path,eurusd)
    try:
        cmd=entry_command(event);args={'symbol':cmd.symbol,'lots':cmd.quantity,'price':cmd.entry_price,'direction':cmd.direction}|changes
        raw=book.capture(adapter,event.hash,deadline_ms=NOW*1000+2000,**args)
        calls=len(sdk.margin_calls)
        with pytest.raises(NativeMarginError):book.bind_entry(event.hash,cmd,raw['source_ref'])
        assert len(sdk.margin_calls)==calls and not sdk.sent
    finally:ledger.close()


def test_original_binding_reopen_and_expired_replay_keep_first_availability_without_native_read(tmp_path,eurusd):
    sdk,adapter,now,ledger,event,book=mt5_entry(tmp_path,eurusd);second=None
    try:
        cmd=entry_command(event);receipt=book.capture_entry(adapter,event.hash,cmd,deadline_ms=NOW*1000+2000)
        count=ledger.count();calls=len(sdk.margin_calls);now['ms']+=900000
        second=Ledger(ledger.path);historical=NativeMarginBook(second,clock=lambda:now['ms'])
        read=historical.lookup_entry(cmd.command_hash,receipt['source_ref'])
        assert read['receipt']==receipt
        assert historical.bind_entry(event.hash,cmd,receipt['source_ref'])==receipt
        assert second.count()==count and len(sdk.margin_calls)==calls and not sdk.sent
    finally:
        if second is not None:second.close()
        ledger.close()


def test_binding_commit_ack_loss_reads_original_without_requery_or_duplicate_write(tmp_path,eurusd,monkeypatch):
    sdk,adapter,now,ledger,event,book=mt5_entry(tmp_path,eurusd)
    try:
        cmd=entry_command(event);raw=book.capture(adapter,event.hash,cmd.symbol,cmd.quantity,
            price=cmd.entry_price,direction=cmd.direction,deadline_ms=NOW*1000+2000)
        original=ledger.atomic
        @contextmanager
        def lost_ack():
            outer=not ledger._conn.in_transaction
            with original():yield ledger
            if outer:raise OSError('fixture original entry-binding commit ACK lost')
        monkeypatch.setattr(ledger,'atomic',lost_ack)
        with pytest.raises(EntryMarginUnknown) as error:book.bind_entry(event.hash,cmd,raw['source_ref'])
        assert error.value.command_hash==cmd.command_hash and error.value.source_ref==raw['source_ref']
        count=ledger.count();calls=len(sdk.margin_calls)
        monkeypatch.setattr(ledger,'atomic',original)
        receipt=book.lookup_entry(cmd.command_hash,raw['source_ref'])['receipt']
        assert book.bind_entry(event.hash,cmd,raw['source_ref'])==receipt
        assert ledger.count()==count and len(sdk.margin_calls)==calls and not sdk.sent
    finally:ledger.close()


def test_runtime_native_send_independently_journals_original_order_margin_binding(tmp_path,eurusd):
    from test_router_native_entry_deadline import flow
    sdk,worker,adapter,clock,mandate,trade,approved,ledger,router=flow(tmp_path,eurusd)
    try:
        receipt=router.execute(trade,approved,mandate,now_ms=clock['ms'],entry_type='MARKET')
        assert receipt.status=='FILLED' and len(sdk.sent)==1
        command=next(ledger.iter(EventKind.ORDER_COMMAND))
        binding=next(e for e in ledger.iter(EventKind.SESSION) if e.hash==command.payload['native_entry_margin_ref'])
        read=NativeMarginBook(ledger,clock=lambda:clock['ms']).lookup_entry(command.payload['command_hash'],binding.payload['source_ref'])
        assert read['receipt']['record_ref']==binding.hash and read['command']['command_hash']==command.payload['command_hash']
        assert read['receipt']['execution_authority'] is read['receipt']['reservation_qualified'] is False
    finally:ledger.close()


@pytest.mark.parametrize('refusal',['kill','lease'])
def test_native_margin_read_cannot_carry_lost_final_dispatch_permission(tmp_path,eurusd,refusal):
    from test_router_native_entry_deadline import flow
    from vati.execution.router import RouterError
    from vati.risk.contracts import KillSwitchTrigger
    sdk,worker,adapter,clock,mandate,trade,approved,ledger,router=flow(tmp_path,eurusd)
    try:
        original=sdk.order_calc_margin;state={'valid':True}
        router.lease_fence=lambda epoch:state['valid']
        def calculated(*args):
            value=original(*args)
            if refusal=='kill':router.kill.trip(KillSwitchTrigger.RECONCILIATION_FAILURE,clock['ms'])
            else:state['valid']=False
            return value
        sdk.order_calc_margin=calculated
        with pytest.raises(RouterError):router.execute(trade,approved,mandate,now_ms=clock['ms'],entry_type='MARKET')
        assert not sdk.sent and ledger.count(EventKind.ORDER_COMMAND)==0
    finally:ledger.close()


def test_expiry_is_rechecked_after_the_real_sql_writer_lock(tmp_path,eurusd):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    sdk,adapter,now,ledger,event,book=mt5_entry(tmp_path,eurusd);blocker=None
    try:
        cmd=entry_command(event);raw=book.capture(adapter,event.hash,cmd.symbol,cmd.quantity,
            price=cmd.entry_price,direction=cmd.direction,deadline_ms=NOW*1000+2000)
        count=ledger.count();path=ledger.path;waiting=threading.Event();blocker=Ledger(path)
        blocker._conn.execute('BEGIN IMMEDIATE')
        def bind():
            connection=Ledger(path)
            try:
                connection._conn.set_trace_callback(lambda sql:waiting.set() if sql=='BEGIN IMMEDIATE' else None)
                return NativeMarginBook(connection,clock=lambda:now['ms']).bind_entry(event.hash,cmd,raw['source_ref'])
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            job=pool.submit(bind)
            try:
                assert waiting.wait(5),'binding never reached the actual writer lock'
                now['ms']=NOW*1000+2000
            finally:blocker._conn.rollback()
            with pytest.raises(NativeMarginError):job.result(timeout=5)
        assert ledger.count()==count and not sdk.sent
    finally:
        if blocker is not None:blocker.close()
        ledger.close()


@pytest.mark.parametrize('damage',['command','estimate','price_scope','authority'])
def test_corrupt_original_binding_is_unavailable_and_never_requeries_native(tmp_path,eurusd,damage):
    import json
    sdk,adapter,now,ledger,event,book=mt5_entry(tmp_path,eurusd)
    try:
        cmd=entry_command(event);receipt=book.capture_entry(adapter,event.hash,cmd,deadline_ms=NOW*1000+2000)
        row=ledger._conn.execute('SELECT seq,payload_json FROM events WHERE event_hash=?',(receipt['record_ref'],)).fetchone()
        payload=json.loads(row[1])
        if damage=='command':payload['command']['quantity']='99'
        elif damage=='estimate':payload['estimate_money']['minor_units']='0'
        elif damage=='price_scope':payload['price_binding']='QUALIFIED_LIMIT_PRICE'
        else:payload['execution_authority']=True
        ledger._conn.execute('UPDATE events SET payload_json=? WHERE seq=?',(json.dumps(payload),row[0]))
        calls=len(sdk.margin_calls)
        with pytest.raises(NativeMarginError):book.lookup_entry(cmd.command_hash,receipt['source_ref'])
        assert len(sdk.margin_calls)==calls and not sdk.sent
    finally:ledger.close()


def test_current_risk_is_read_after_margin_query_and_cannot_extend_margin_expiry(tmp_path,eurusd):
    from vati.execution import ExecutionRouter,ProtectionManager
    from vati.execution.router import RouterError
    from vati.execution.risk_refresh import CurrentRiskFacts
    from vati.risk import RiskAuthority,TradingMandate,KillSwitch
    from vati.risk.serde import intent_from_dict,snapshot_from_dict
    sdk,adapter,now,ledger,event,book=mt5_entry(tmp_path,eurusd)
    try:
        m=TradingMandate.from_mapping(event.payload['inputs']['mandate']);authority=RiskAuthority(m)
        trade=intent_from_dict(event.payload['inputs']['intent']);facts=snapshot_from_dict(event.payload['inputs']['snapshot'])
        approved=authority.evaluate_safe(trade,facts);original=sdk.order_calc_margin;observed=[]
        def margin(*args):
            value=original(*args);observed.append('native-margin');return value
        sdk.order_calc_margin=margin
        def current(*args,**kwargs):
            assert observed==['native-margin']
            at=now['ms'];result=CurrentRiskFacts(replace(facts,now_unix=at//1000),at)
            now['ms']+=5000
            return result
        router=ExecutionRouter(ledger=ledger,adapters={'mt5':adapter},kill_switch=KillSwitch(),protection=ProtectionManager(),
            clock=lambda:now['ms'],current_risk_authority=authority,current_risk_facts_provider=current)
        with pytest.raises(RouterError,match='bound native margin expired'):
            router.execute(trade,approved,m,now_ms=now['ms'],entry_type='MARKET')
        assert not sdk.sent and ledger.count(EventKind.ORDER_COMMAND)==0
    finally:ledger.close()


@pytest.mark.parametrize('later',['quote','binding'])
def test_quote_and_binding_share_one_monotonic_original_storage_clock(tmp_path,eurusd,later):
    sdk,adapter,now,ledger,event,book=mt5_entry(tmp_path,eurusd)
    try:
        cmd=entry_command(event)
        raw=book.capture(adapter,event.hash,cmd.symbol,cmd.quantity,price=cmd.entry_price,
            direction=cmd.direction,deadline_ms=NOW*1000+2000)
        now['ms']+=1
        if later=='quote':
            book.capture(adapter,event.hash,cmd.symbol,cmd.quantity,price=cmd.entry_price,
                direction=cmd.direction,deadline_ms=NOW*1000+2000)
        else:book.bind_entry(event.hash,cmd,raw['source_ref'])
        before=ledger.count();now['ms']-=1
        with pytest.raises(NativeMarginError,match='CLOCK_REGRESSED'):
            if later=='quote':book.bind_entry(event.hash,cmd,raw['source_ref'])
            else:book.capture(adapter,event.hash,cmd.symbol,cmd.quantity,price=cmd.entry_price,
                direction=cmd.direction,deadline_ms=NOW*1000+2000)
        assert ledger.count()==before and ledger.verify_chain()[0] and not sdk.sent
    finally:ledger.close()
