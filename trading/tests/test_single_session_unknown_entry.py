"""Real service + signed MT5 polling + durable queue: silence is not NoEffect."""
import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import historical_mandate_dict
from test_backtest_runner_cli import synthetic_bars
from vati.accounts import Account,AccountRegistry,CredentialRef
from vati.app.service import ServiceConfig,SessionService
from vati.core import EventKind
from vati.execution.mt5_pull import BridgeQueue,Mt5PullAdapter,create_pull_app,sign_poll
from vati.risk.serde import contract_to_dict

pytestmark=pytest.mark.skipif(not os.environ.get('VATI_TEST_PG_DSN') or os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1',
    reason='requires explicitly isolated native PostgreSQL fixture')


@contextmanager
def delayed_native_session(tmp_path,contract,*,lose_enqueue_reply=False,initial_partial_status=None,omit_context=False,initial_terminal_status=None):
    alias='delayed_mt5_'+uuid.uuid4().hex[:12];key=b'local-source-fixture-key-32-bytes!'
    bars=synthetic_bars();clock={'ms':bars[100].end_ms};queue=BridgeQueue(tmp_path/'native-ea.sqlite')
    app=create_pull_app(queue,lambda who:key if who==alias else None,clock=lambda:clock['ms'])
    client=TestClient(app);delivered=[];nonces={'n':0};terminal_positions=[]
    def poll(*,results=(),positions=None):
        if positions is not None:terminal_positions[:]=positions
        nonces['n']+=1;ts=str(clock['ms']//1000);nonce='owner-ea-'+str(nonces['n'])
        body=json.dumps({'account':{'login':12345678,'equity':'10000','balance':'10000','currency':'USD',
            'trade_allowed':True,'hedging':True,'server_time_ms':clock['ms']},'positions':terminal_positions,'results':list(results)}).encode()
        response=client.post('/ea/v1/'+alias+'/poll',content=body,headers={'x-van-ts':ts,'x-van-nonce':nonce,
            'x-van-signature':sign_poll(key,ts,nonce,alias,body),'content-type':'application/json'})
        assert response.status_code==200
        delivered.extend(response.text.splitlines())
    adapter=Mt5PullAdapter(BridgeQueue(tmp_path/'native-ea.sqlite'),account_alias=alias,clock=lambda:clock['ms'],timeout_s=.003,poll_s=.001)
    if initial_partial_status:
        def partial_reply(cid):
            from decimal import Decimal
            poll();fields=delivered[-1].split('|')
            qty=str(Decimal(fields[4])/2)
            native={'ticket':900,'symbol':fields[2],'type':fields[3],'volume':qty,'price_open':fields[5],
                'sl':fields[6],'tp':fields[7] or 0,'comment':fields[9],'magic':int(fields[10]),'profit':0}
            poll(results=[{'id':cid,'status':initial_partial_status,'volume':qty,'price':fields[5],
                'order':'partial-original','position':900,'sl_confirmed':True,'server_time_ms':clock['ms']}],positions=[native])
            return adapter.queue.result(cid)
        adapter._await=partial_reply
    if initial_terminal_status:
        def terminal_reply(cid):
            poll();poll(results=[{'id':cid,'status':initial_terminal_status,'volume':'0','reason':'original native no-effect outcome'}])
            return adapter.queue.result(cid)
        adapter._await=terminal_reply
    if lose_enqueue_reply:
        enqueue=adapter.queue.enqueue
        def lost_reply(*args,**kwargs):
            cid=enqueue(*args,**kwargs)
            raise OSError('fixture queue commit reply lost after original claim')
        adapter.queue.enqueue=lost_reply
    registry=AccountRegistry(tmp_path/'accounts.json')
    registry.add(Account(alias=alias,broker='MT5',mode='DEMO_TRADER',currency='USD',demo=True,
        credential_ref=CredentialRef(env_var='SOURCE_FIXTURE_NOT_READ'),login='12345678',server='fixture-native-ea'))
    cfg=ServiceConfig(account_alias=alias,symbol='EURUSD',base='EUR',quote='USD',timeframe='H1',
        contract=contract_to_dict(contract),mandate=historical_mandate_dict(account_alias=alias,venue='mt5',mode='DEMO_TRADER',
            allowed_strategies=['FX-TREND-PULLBACK-01']),capsules=['FX-TREND-PULLBACK-01'],registry_path=str(registry.path),
        ledger=os.environ['VATI_TEST_PG_DSN'],heartbeat_path=str(tmp_path/'heartbeat.json'))
    poll();service=SessionService(cfg,lambda now:[b for b in bars if b.end_ms<=now],clock=lambda:clock['ms'],adapter=adapter).build()
    if omit_context:
        publish=service.runner.cycle._log
        def old_context_producer(kind,payload,**kwargs):
            if kind is EventKind.SESSION and payload.get('event')=='ENTRY_CONTEXT':return
            return publish(kind,payload,**kwargs)
        service.runner.cycle._log=old_context_producer
    def orders():return [e for e in service._ledger.iter(EventKind.ORDER_COMMAND) if e.payload['account_alias']==alias]
    try:
        service.start()
        if not service.runner.permit_new_orders:
            from vati.risk.history_scope import risk_history_for_account
            scope=risk_history_for_account(service._ledger.iter(),alias)
            rows=[]
            for e in service._ledger.iter():
                if e.hash in scope.unresolved_refs:
                    p=e.payload;i=(p.get('inputs') or {}).get('intent') or {}
                    rows.append({'kind':e.kind.value,'producer':e.producer,'hash':e.hash,'corr':e.correlation_id,
                        'alias':p.get('account_alias'),'intent_alias':i.get('account_alias'),
                        'intent_id':i.get('trade_intent_id'),'command_id':p.get('trade_intent_id')})
            Path('/tmp/van-single-unknown-start-issues.json').write_text(json.dumps(rows,indent=2))
        assert service.runner.permit_new_orders,(service.runner.cycle.kill.active,service.learning.recovery_issue,service.runner.cycle.streaks.recovery_issue,service.runner.startup_report)
        for index,bar in enumerate(bars[101:],101):
            clock['ms']=bar.end_ms+1000;poll()
            try:result=service.step_once()
            except OSError:
                assert lose_enqueue_reply
                result='DISPATCH_EXCEPTION'

            if orders():
                receipts=list(service._ledger.iter(EventKind.EXECUTION_RECEIPT,correlation_id=orders()[0].correlation_id))
                if receipts:
                    assert receipts[-1].payload['status']==(initial_terminal_status or ('PARTIAL' if initial_partial_status else 'UNKNOWN'))
                    if not initial_partial_status:assert receipts[-1].payload['filled_qty']=='0'
                else:
                    assert lose_enqueue_reply
                    assert queue._conn.execute('SELECT count(*) FROM commands WHERE alias=?',(alias,)).fetchone()[0]==1

                yield service,bars,index,clock,poll,orders,result,queue,delivered
                break
        else:raise AssertionError('fixture never queued a genuinely approved native order')
    finally:
        service.close();service._ledger.close();client.close();adapter.queue._conn.close();queue._conn.close()


def test_original_timed_out_native_entry_is_not_reported_as_executed_or_approved(tmp_path,eurusd):
    with delayed_native_session(tmp_path,eurusd) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        assert len(orders())==1 and not service.adapter.positions()
        assert result=='UNKNOWN'


def test_current_empty_positions_do_not_release_original_unresolved_entry_risk(tmp_path,eurusd):
    with delayed_native_session(tmp_path,eurusd) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        for bar in bars[index+1:]:
            clock['ms']=bar.end_ms+1000;poll();service.step_once()
            assert service.adapter.heartbeat(now_ms=clock['ms']).connected
            assert service.adapter.sync_account().verified is True and not service.adapter.positions()
        assert delivered,'the authentic EA poll must have claimed the original command'
        assert len(orders())==1,'fresh empty account snapshots allowed additional native sends while the original result was unknown'


def test_late_original_native_rejection_releases_only_that_attempt_without_replaying_it(tmp_path,eurusd):
    with delayed_native_session(tmp_path,eurusd) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original=orders()[0].correlation_id;poll();cid=int(delivered[0].split('|')[0])
        poll(results=[{'id':cid,'status':'REJECTED','volume':'0','reason':'original native order refused'}])
        assert queue.result(cid)['status']=='REJECTED'
        service.step_once()  # reconciliation must also run while waiting for the next bar
        assert original not in service.runner.cycle.unresolved_entry_attempts
        assert original not in service.runner.cycle._entries
        assert len(orders())==1 and not service.adapter.positions()


def test_late_original_native_fill_restores_full_trade_identity_and_protection_without_another_send(tmp_path,eurusd):
    with delayed_native_session(tmp_path,eurusd) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        from decimal import Decimal as D
        original=orders()[0].correlation_id;poll();fields=delivered[0].split('|');cid=int(fields[0])
        native={'ticket':900,'symbol':fields[2],'type':fields[3],'volume':fields[4],'price_open':fields[5],
            'sl':fields[6],'tp':fields[7] or 0,'comment':fields[9],'magic':int(fields[10]),'profit':0}
        ack={'id':cid,'status':'FILLED','order':'original-broker-order','position':900,'volume':fields[4],
            'price':fields[5],'sl_confirmed':True,'server_time_ms':clock['ms']}
        poll(results=[ack],positions=[native])
        assert service.adapter.positions()[0].trade_intent_id==original,'MT5 comment truncation must not lose the original native trade identity'
        service.step_once()
        cycle=service.runner.cycle
        assert original not in cycle.unresolved_entry_attempts
        assert cycle._entries[original]['pending'] is False and cycle._entries[original]['open'] is True
        assert cycle._entries[original]['quantity']==D(fields[4])
        assert cycle.protection.stop_of('900')==D(fields[6])
        assert cycle.thesis.thesis_for(original) is not None
        assert len(orders())==1


def test_missing_native_enqueue_reply_holds_the_durable_original_attempt(tmp_path,eurusd):
    with delayed_native_session(tmp_path,eurusd,lose_enqueue_reply=True) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original=orders()[0].correlation_id
        assert result=='UNKNOWN'
        assert original in service.runner.cycle.unresolved_entry_attempts
        assert not service.runner.cycle._reconciliation_ok(account_verified=True)
        assert len(orders())==1


@pytest.mark.parametrize('damage',['wrong-symbol','oversized-fill','stop-unconfirmed','rejected-with-fill','malformed-volume'])
def test_contradictory_or_partial_native_evidence_cannot_release_the_original_hold(tmp_path,eurusd,damage):
    with delayed_native_session(tmp_path,eurusd) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original=orders()[0].correlation_id;poll();fields=delivered[0].split('|');cid=int(fields[0])
        native={'ticket':900,'symbol':fields[2],'type':fields[3],'volume':fields[4],'price_open':fields[5],
            'sl':fields[6],'tp':fields[7] or 0,'comment':fields[9],'magic':int(fields[10]),'profit':0}
        ack={'id':cid,'status':'FILLED','order':'original-order','position':900,'volume':fields[4],
            'price':fields[5],'sl_confirmed':True,'server_time_ms':clock['ms']}
        if damage=='wrong-symbol':native['symbol']='GBPUSD'
        elif damage=='oversized-fill':ack['volume']=native['volume']='99'
        elif damage=='stop-unconfirmed':ack['sl_confirmed']='false'
        elif damage=='rejected-with-fill':ack['status']='REJECTED'
        else:ack['volume']='NaN'
        poll(results=[ack],positions=[native]);service.step_once()
        assert original in service.runner.cycle.unresolved_entry_attempts
        assert not service.runner.cycle._reconciliation_ok(account_verified=True)
        assert len(orders())==1


def test_lost_enqueue_reply_can_read_the_original_native_refusal_without_repeating_the_write(tmp_path,eurusd):
    with delayed_native_session(tmp_path,eurusd,lose_enqueue_reply=True) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original=orders()[0].correlation_id;poll();cid=int(delivered[0].split('|')[0])
        poll(results=[{'id':cid,'status':'REJECTED','volume':'0','reason':'genuine original native refusal'}])
        service.step_once()
        assert original not in service.runner.cycle.unresolved_entry_attempts
        assert len(orders())==1 and len(queue.native_entries(service.cfg.account_alias))==1


def test_owner_heartbeat_reports_the_original_unknown_hold(tmp_path,eurusd):
    with delayed_native_session(tmp_path,eurusd) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        heartbeat=json.loads(Path(service.cfg.heartbeat_path).read_text())
        assert heartbeat['permit_new_orders'] is False
        assert heartbeat['unresolved_entry_count']==1
        assert heartbeat['unresolved_entry_ids']==[orders()[0].correlation_id]


@pytest.mark.parametrize('when',['before-tca','after-tca'])
def test_original_late_fill_recovery_retries_a_local_publication_failure_without_losing_context_or_double_cost(tmp_path,eurusd,when):
    with delayed_native_session(tmp_path,eurusd) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original=orders()[0].correlation_id;poll();fields=delivered[0].split('|');cid=int(fields[0]);cycle=service.runner.cycle
        native={'ticket':900,'symbol':fields[2],'type':fields[3],'volume':fields[4],'price_open':fields[5],
            'sl':fields[6],'tp':fields[7] or 0,'comment':fields[9],'magic':int(fields[10]),'profit':0}
        ack={'id':cid,'status':'FILLED','order':'original-order','position':900,'volume':fields[4],
            'price':fields[5],'sl_confirmed':True,'server_time_ms':clock['ms']}
        write=cycle._record_tca
        def interrupted(*args,**kwargs):
            if when=='after-tca':write(*args,**kwargs)
            raise OSError('fixture original local cost-publication reply lost')
        cycle._record_tca=interrupted
        poll(results=[ack],positions=[native]);service.step_once()
        assert original in cycle.unresolved_entry_attempts and cycle.protection.stop_of('900') is not None
        cycle._record_tca=write;clock['ms']+=1;service.step_once()
        assert original not in cycle.unresolved_entry_attempts
        assert len(list(service._ledger.iter(EventKind.TCA_RECORD,correlation_id=original)))==1
        assert len(list(service._ledger.iter(EventKind.TRADE_THESIS,correlation_id=original)))==1
        assert len(orders())==1


@pytest.mark.parametrize('when',['before-thesis','after-thesis'])
def test_native_thesis_write_failure_recovers_from_real_persistence_not_a_memory_only_claim(tmp_path,eurusd,when):
    with delayed_native_session(tmp_path,eurusd) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original=orders()[0].correlation_id;poll();fields=delivered[0].split('|');cid=int(fields[0]);cycle=service.runner.cycle
        native={'ticket':900,'symbol':fields[2],'type':fields[3],'volume':fields[4],'price_open':fields[5],
            'sl':fields[6],'tp':fields[7] or 0,'comment':fields[9],'magic':int(fields[10]),'profit':0}
        ack={'id':cid,'status':'FILLED','order':'original-order','position':900,'volume':fields[4],
            'price':fields[5],'sl_confirmed':True,'server_time_ms':clock['ms']}
        append=service._ledger.append
        def interrupted(event):
            if event.kind is EventKind.TRADE_THESIS and event.correlation_id==original:
                if when=='after-thesis':append(event)
                raise OSError('fixture native thesis-publication reply lost')
            return append(event)
        service._ledger.append=interrupted
        poll(results=[ack],positions=[native]);service.step_once()
        if when=='before-thesis':
            assert original in cycle.unresolved_entry_attempts and cycle.thesis.thesis_for(original) is None
        service._ledger.append=append;clock['ms']+=1;service.step_once()
        assert original not in cycle.unresolved_entry_attempts
        assert len(list(service._ledger.iter(EventKind.TRADE_THESIS,correlation_id=original)))==1
        assert len(list(service._ledger.iter(EventKind.TCA_RECORD,correlation_id=original)))==1
        assert len(orders())==1


@pytest.mark.parametrize('outcome',['REJECTED','FILLED'])
def test_already_resolved_original_result_replays_consistently_after_real_service_restart(tmp_path,eurusd,outcome):
    with delayed_native_session(tmp_path,eurusd) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original=orders()[0].correlation_id;poll();fields=delivered[0].split('|');cid=int(fields[0])
        ack={'id':cid,'status':outcome,'volume':'0','reason':'genuine original native refusal'};positions=[]
        if outcome=='FILLED':
            ack.update(order='original-order',position=900,volume=fields[4],price=fields[5],sl_confirmed=True,server_time_ms=clock['ms'])
            positions=[{'ticket':900,'symbol':fields[2],'type':fields[3],'volume':fields[4],'price_open':fields[5],
                'sl':fields[6],'tp':fields[7] or 0,'comment':fields[9],'magic':int(fields[10]),'profit':0}]
        poll(results=[ack],positions=positions);service.step_once()
        assert original not in service.runner.cycle.unresolved_entry_attempts
        service.close();service._ledger.close()
        restarted=SessionService(service.cfg,lambda now:[],clock=lambda:clock['ms'],adapter=service.adapter).build()
        try:
            restarted.start()
            assert restarted.runner.permit_new_orders and restarted.runner.startup_report.permit_new_orders
            assert len(queue.native_entries(service.cfg.account_alias))==1
            if outcome=='FILLED':assert restarted.runner.cycle.protection.stop_of('900') is not None
        finally:restarted.close();restarted._ledger.close()


def test_zero_fill_refusal_cannot_erase_an_earlier_native_report_of_possible_filled_quantity(tmp_path,eurusd):
    from copy import deepcopy
    from vati.core import make_event
    from vati.core.canonical import canonical_hash
    with delayed_native_session(tmp_path,eurusd) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original=orders()[0].correlation_id
        initial=list(service._ledger.iter(EventKind.EXECUTION_RECEIPT,correlation_id=original))[0]
        ambiguous=deepcopy(initial.payload);ambiguous['filled_qty']='0.01'
        ambiguous['receipt_hash']=canonical_hash({k:v for k,v in ambiguous.items() if k!='receipt_hash'})
        service._ledger.append(make_event(EventKind.EXECUTION_RECEIPT,'vati-cycle',ambiguous,
            event_time_ms=clock['ms'],received_time_ms=clock['ms'],correlation_id=original))
        poll();cid=int(delivered[0].split('|')[0])
        poll(results=[{'id':cid,'status':'REJECTED','volume':'0','reason':'native refusal with contradictory history'}])
        service.step_once()
        assert original in service.runner.cycle.unresolved_entry_attempts
        assert not service.runner.cycle._reconciliation_ok(account_verified=True)
        assert len(orders())==1


def test_loss_of_original_queue_record_is_unknown_and_cannot_create_a_replacement_command(tmp_path,eurusd):
    with delayed_native_session(tmp_path,eurusd) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original=orders()[0].correlation_id;poll()
        assert delivered,'the original native command must already have reached the EA outbox'
        queue._conn.execute('DELETE FROM commands WHERE alias=?',(service.cfg.account_alias,))
        poll();service.step_once()
        assert original in service.runner.cycle.unresolved_entry_attempts
        assert not queue.native_entries(service.cfg.account_alias),'reading an unknown original operation created a replacement native command'
        assert len(orders())==1


@pytest.mark.parametrize('native_status',['PARTIAL','FILLED'])
def test_initial_native_partial_fill_keeps_remaining_risk_and_truthful_status(tmp_path,eurusd,native_status):
    with delayed_native_session(tmp_path,eurusd,initial_partial_status=native_status) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original=orders()[0].correlation_id;cycle=service.runner.cycle
        assert result=='PARTIAL'
        assert original in cycle.unresolved_entry_attempts
        assert not cycle._reconciliation_ok(account_verified=True)
        assert cycle.protection.stop_of('900') is not None
        assert cycle._entries[original]['pending_quantity']>0
        for bar in bars[index+1:index+4]:
            clock['ms']=bar.end_ms+1000;poll();service.step_once()
        assert len(orders())==1 and original in cycle.unresolved_entry_attempts


@pytest.mark.parametrize('outcome',['REJECTED','FILLED'])
def test_process_restart_before_original_native_result_can_reconcile_without_resending(tmp_path,eurusd,outcome):
    with delayed_native_session(tmp_path,eurusd) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original=orders()[0].correlation_id;poll();fields=delivered[0].split('|');cid=int(fields[0])
        service.close();service._ledger.close()
        restarted=SessionService(service.cfg,lambda now:[],clock=lambda:clock['ms'],adapter=service.adapter).build()
        try:
            restarted.start()
            assert original in restarted.runner.cycle.recovery_unresolved
            assert not restarted.runner.permit_new_orders
            ack={'id':cid,'status':outcome,'volume':'0','reason':'original native refusal'};positions=[]
            if outcome=='FILLED':
                ack.update(order='original-order',position=900,volume=fields[4],price=fields[5],sl_confirmed=True,server_time_ms=clock['ms'])
                positions=[{'ticket':900,'symbol':fields[2],'type':fields[3],'volume':fields[4],'price_open':fields[5],
                    'sl':fields[6],'tp':fields[7] or 0,'comment':fields[9],'magic':int(fields[10]),'profit':0}]
            poll(results=[ack],positions=positions);restarted.step_once()
            assert original not in restarted.runner.cycle.recovery_unresolved
            assert original not in restarted.runner.cycle.unresolved_entry_attempts
            assert len(queue.native_entries(service.cfg.account_alias))==1
            if outcome=='FILLED':
                assert restarted.runner.cycle.protection.stop_of('900') is not None
                assert restarted.runner.cycle.thesis.thesis_for(original) is not None
                assert restarted.runner.cycle._entries[original]['recovery_context_complete'] is True
            # Reconciliation evidence cannot clear the existing owner-signed kill latch.
            from vati.risk.contracts import KillSwitchTrigger
            assert KillSwitchTrigger.RECONCILIATION_FAILURE in restarted.runner.cycle.kill.active
        finally:restarted.close();restarted._ledger.close()


def test_late_original_fill_uses_approved_capsule_not_a_current_replacement(tmp_path,eurusd):
    from copy import deepcopy
    from vati.strategies.capsule import Capsule
    with delayed_native_session(tmp_path,eurusd) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original=orders()[0].correlation_id;cycle=service.runner.cycle;strategy=orders()[0].payload['strategy_id']
        old=cycle.engine.registry.get(strategy);original_hash=old.capsule_hash
        new=deepcopy(old.data);new['version']='post-dispatch-fixture-version'
        cycle.engine.registry.add(Capsule(cycle.engine.registry.seal(new)))
        assert cycle.engine.registry.get(strategy).capsule_hash!=original_hash
        poll();fields=delivered[0].split('|');cid=int(fields[0])
        native={'ticket':900,'symbol':fields[2],'type':fields[3],'volume':fields[4],'price_open':fields[5],
            'sl':fields[6],'tp':fields[7] or 0,'comment':fields[9],'magic':int(fields[10]),'profit':0}
        poll(results=[{'id':cid,'status':'FILLED','volume':fields[4],'price':fields[5],'order':'original-order',
            'position':900,'sl_confirmed':True,'server_time_ms':clock['ms']}],positions=[native])
        service.step_once()
        thesis=cycle.thesis.thesis_for(original)
        assert thesis is not None and thesis.capsule_hash==original_hash
        assert len(orders())==1


def test_original_cold_refusal_does_not_require_missing_historical_thesis_inputs(tmp_path,eurusd):
    # Historical producer without ENTRY_CONTEXT; genuine command/risk/queue remain.
    with delayed_native_session(tmp_path,eurusd,omit_context=True) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original=orders()[0].correlation_id;poll();cid=int(delivered[0].split('|')[0])
        service.close();service._ledger.close()
        restarted=SessionService(service.cfg,lambda now:[],clock=lambda:clock['ms'],adapter=service.adapter).build()
        try:
            restarted.start();assert original in restarted.runner.cycle.recovery_unresolved
            poll(results=[{'id':cid,'status':'REJECTED','volume':'0','reason':'native original refused'}]);restarted.step_once()
            assert original not in restarted.runner.cycle.recovery_unresolved
            assert original not in restarted.runner.cycle.unresolved_entry_attempts
            assert not list(restarted._ledger.iter(EventKind.TRADE_THESIS,correlation_id=original))
            assert not list(restarted._ledger.iter(EventKind.TCA_RECORD,correlation_id=original))
            assert len(queue.native_entries(service.cfg.account_alias))==1
        finally:restarted.close();restarted._ledger.close()


def test_late_native_fill_keeps_original_setup_and_derives_target_r_from_actual_fill(tmp_path,eurusd):
    from decimal import Decimal as D
    with delayed_native_session(tmp_path,eurusd) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original=orders()[0].correlation_id;poll();fields=delivered[0].split('|');cid=int(fields[0])
        fill=D(fields[5])+D('0.00001')
        native={'ticket':900,'symbol':fields[2],'type':fields[3],'volume':fields[4],'price_open':str(fill),
            'sl':fields[6],'tp':fields[7] or 0,'comment':fields[9],'magic':int(fields[10]),'profit':0}
        poll(results=[{'id':cid,'status':'FILLED','volume':fields[4],'price':str(fill),'order':'original-order',
            'position':900,'sl_confirmed':True,'server_time_ms':clock['ms']}],positions=[native])
        service.step_once();thesis=service.runner.cycle.thesis.thesis_for(original)
        assert thesis is not None and thesis.entry==fill
        expected=(D(fields[7])-fill)/abs(fill-D(fields[6]))
        assert D(thesis.expected_path['target_r'])==expected
        assert len(orders())==1


@pytest.mark.parametrize('native_status',['REJECTED','CANCELLED','EXPIRED'])
def test_initial_confirmed_native_no_effect_is_not_reported_as_a_risk_approval(tmp_path,eurusd,native_status):
    with delayed_native_session(tmp_path,eurusd,initial_terminal_status=native_status) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original=orders()[0].correlation_id
        assert result==native_status
        assert original not in service.runner.cycle._entries
        assert original not in service.runner.cycle.unresolved_entry_attempts
        assert len(orders())==1 and not service.adapter.positions()
