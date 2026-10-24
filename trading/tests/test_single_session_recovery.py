"""Actual service startup must reconcile native history, not empty process memory."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from test_single_session_lease import config
from test_backtest_runner_cli import synthetic_bars
from vati.app.service import SessionService
from vati.core import EventKind
from vati.execution.paper import PaperAdapter
from vati.risk.contracts import KillSwitchTrigger


def opened_service(tmp_path,contract):
    bars=synthetic_bars();clock={'now':bars[100].end_ms}
    cfg=config(tmp_path,contract)
    service=SessionService(cfg,lambda now:[b for b in bars if b.end_ms<=now],clock=lambda:clock['now']).build()
    service.start()
    for bar in bars[101:]:
        clock['now']=bar.end_ms+1000
        service.step_once()
        if service.adapter.positions():return service,cfg,clock
    service.close();service._ledger.close()
    raise AssertionError('fixture did not produce a genuine admitted native position')


def test_real_restart_restores_original_entry_protection_and_context_without_an_order_retry(tmp_path,eurusd):
    first,cfg,clock=opened_service(tmp_path,eurusd)
    adapter=first.adapter;position=adapter.positions()[0];original=dict(first.runner.cycle._entries[position.trade_intent_id])
    before=first._ledger.count(EventKind.ORDER_COMMAND)
    first.close();first._ledger.close()
    second=SessionService(cfg,lambda now:[],clock=lambda:clock['now'],adapter=adapter).build()
    try:
        second.start()
        assert second.runner.permit_new_orders and second.runner.startup_report.permit_new_orders
        entry=second.runner.cycle._entries[position.trade_intent_id]
        for field in ('strategy_id','direction','session','regime','cost_pct','original_approved_risk_pct','event_certified','opened_in_blackout'):
            assert entry[field]==original[field],field
        assert entry['quantity']==position.quantity
        assert position.position_id in second.runner.cycle.protection.rules
        assert second.runner.cycle.protection.stop_of(position.position_id)==position.stop_price
        assert second.runner.cycle.thesis.thesis_for(position.trade_intent_id) is not None
        assert second._ledger.count(EventKind.ORDER_COMMAND)==before
    finally:second.close();second._ledger.close()


def test_cold_paper_process_cannot_treat_a_durable_open_trade_as_a_flat_account(tmp_path,eurusd):
    first,cfg,clock=opened_service(tmp_path,eurusd)
    before=first._ledger.count(EventKind.ORDER_COMMAND)
    first.close();first._ledger.close()
    second=SessionService(cfg,lambda now:[],clock=lambda:clock['now']).build()
    try:
        assert not second.adapter.positions()
        second.start()
        assert not second.runner.permit_new_orders and not second.runner.startup_report.permit_new_orders
        assert KillSwitchTrigger.RECONCILIATION_FAILURE in second.runner.cycle.kill.active
        assert second._ledger.count(EventKind.ORDER_COMMAND)==before
    finally:second.close();second._ledger.close()


@pytest.mark.parametrize('damage',['missing-context','context-after-command','conflicting-context','wrong-context-account','wrong-context-decision','prepared-capsule-content','prepared-capsule-version','prepared-thesis-market','prepared-thesis-risk','prepared-thesis-id','prepared-thesis-time','prepared-setup-shape'])
def test_incomplete_historical_context_keeps_native_protection_without_inventing_feedback(tmp_path,eurusd,damage):
    from vati.core import make_event
    first,cfg,clock=opened_service(tmp_path,eurusd)
    adapter=first.adapter;position=adapter.positions()[0]
    # Rebuild a valid native prefix without the original optional context,
    # representing the actual historical pre-context producer.
    rows=list(first._ledger.iter());first.close();first._ledger.close()
    from vati.core import Ledger
    cfg.ledger=str(tmp_path/'historic.sqlite');history=Ledger(cfg.ledger)
    for event in rows:
        if event.kind is EventKind.SESSION and event.payload.get('event')=='ENTRY_CONTEXT':
            if damage in {'missing-context','context-after-command'}:continue
            if damage=='conflicting-context':history.append(event)
            import copy
            from vati.core.canonical import canonical_hash
            payload=copy.deepcopy(event.payload)
            if damage=='conflicting-context':
                payload['context']['session']='CONFLICTING_ORIGINAL_SESSION'
                payload['context_hash']=canonical_hash(payload['context'])
            elif damage=='wrong-context-account':payload['account_alias']='different_native_account'
            elif damage=='prepared-setup-shape':
                payload['context']['prepared_setup']=[]
                payload['context_hash']=canonical_hash(payload['context'])
            elif damage.startswith('prepared-'):
                setup=payload['context']['prepared_setup'];thesis=setup['thesis']
                if damage=='prepared-capsule-content':setup['capsule']['thesis']={'statement':'unhashed-replacement'}
                elif damage=='prepared-capsule-version':
                    setup['capsule']['version']='different-original-version'
                    setup['capsule']['capsule_hash']=canonical_hash({k:v for k,v in setup['capsule'].items() if k!='capsule_hash'})
                    thesis['capsule_hash']=setup['capsule']['capsule_hash']
                elif damage=='prepared-thesis-market':thesis['market_state_hash']='0'*64
                elif damage=='prepared-thesis-risk':thesis['original_approved_risk_pct']='0.99'
                elif damage=='prepared-thesis-id':thesis['trade_intent_id']='another-original-trade'
                else:thesis['created_ms']+=100000
                thesis['seal']=canonical_hash({k:v for k,v in thesis.items() if k!='seal'})
                payload['context_hash']=canonical_hash(payload['context'])
            else:payload['decision_hash']='0'*64
            history.append(make_event(event.kind,event.producer,payload,event_time_ms=event.event_time_ms,
                received_time_ms=event.received_time_ms,correlation_id=event.correlation_id))
            continue
        history.append(event)
    if damage=='context-after-command':
        for event in rows:
            if event.kind is EventKind.SESSION and event.payload.get('event')=='ENTRY_CONTEXT':
                history.append(make_event(event.kind,event.producer,event.payload,
                    event_time_ms=event.event_time_ms,received_time_ms=event.received_time_ms,
                    correlation_id=event.correlation_id))
    history.close()
    second=SessionService(cfg,lambda now:[],clock=lambda:clock['now'],adapter=adapter).build()
    try:
        second.start()
        assert not second.runner.permit_new_orders
        assert position.trade_intent_id in second.runner.cycle._entries
        entry=second.runner.cycle._entries[position.trade_intent_id]
        assert entry['recovery_context_complete'] is False
        assert position.position_id in second.runner.cycle.protection.rules
        assert second.runner.cycle.protection.stop_of(position.position_id)==position.stop_price
        assert not second.runner.cycle.reviews
        kinds=(EventKind.DECISION_QUADRANT,EventKind.TRADE_LESSON,EventKind.TRADE_EXPERIENCE_ARTIFACT)
        before={kind:second._ledger.count(kind) for kind in kinds}
        receipt=second.runner.cycle.router.apply_preservation(adapter.venue,position_id=position.position_id,
            trade_intent_id=position.trade_intent_id,action='FULL_CLOSE',now_ms=clock['now'],reason='OWNER_ACCEPTED_EXIT')
        second.runner.cycle._on_close(position.trade_intent_id,receipt.average_fill,'OWNER_ACCEPTED_EXIT',clock['now'])
        assert second._ledger.count(EventKind.TRADE_REVIEW)==1
        assert {kind:second._ledger.count(kind) for kind in kinds}==before
    finally:second.close();second._ledger.close()


@pytest.mark.parametrize('changed',['account','currency','ambiguous-verification'])
def test_native_account_readback_must_match_the_runtime_identity_and_money_units(tmp_path,eurusd,changed):
    service=SessionService(config(tmp_path,eurusd),lambda now:[],clock=lambda:1000).build()
    try:
        if changed=='account':service.adapter.account_alias='different_native_account'
        elif changed=='currency':service.adapter.currency='EUR'
        else:
            read=service.adapter.sync_account
            service.adapter.sync_account=lambda:replace(read(),verified='false')
        service.start()
        assert not service.runner.permit_new_orders
        assert KillSwitchTrigger.UNAUTHORIZED_ACCOUNT in service.runner.cycle.kill.active
    finally:service.close();service._ledger.close()


@pytest.mark.parametrize('state',['rejected','pending','lost-reply'])
def test_cold_restart_distinguishes_a_native_refusal_from_pending_or_unknown_effects(tmp_path,eurusd,state):
    bars=synthetic_bars();clock={'now':bars[100].end_ms};cfg=config(tmp_path,eurusd)
    first=SessionService(cfg,lambda now:[b for b in bars if b.end_ms<=now],clock=lambda:clock['now']).build()
    if state=='rejected':first.adapter.inject_reject_order=True
    else:
        submit=first.adapter.submit
        def native_response(command,*,now_ms):
            if state=='pending':return first.adapter._rest(command,now_ms=now_ms)
            submit(command,now_ms=now_ms)
            raise OSError('fixture original native reply lost after effect')
        first.adapter.submit=native_response
    first.start()
    try:
        for bar in bars[101:]:
            clock['now']=bar.end_ms+1000
            try:first.step_once()
            except OSError:
                assert state=='lost-reply'
            if first._ledger.count(EventKind.ORDER_COMMAND):break
        assert first._ledger.count(EventKind.ORDER_COMMAND)==1
    finally:first.close();first._ledger.close()
    second=SessionService(cfg,lambda now:[],clock=lambda:clock['now']).build()
    try:
        second.start()
        assert second.runner.permit_new_orders is (state=='rejected')
        assert second.runner.startup_report.permit_new_orders is (state=='rejected')
        assert second._ledger.count(EventKind.ORDER_COMMAND)==1
        if state!='rejected':assert second.runner.startup_report.counts()['UNRESOLVED_ORDER']>=1
    finally:second.close();second._ledger.close()


def test_genuine_completed_native_review_does_not_reopen_historical_exposure(tmp_path,eurusd):
    first,cfg,clock=opened_service(tmp_path,eurusd)
    adapter=first.adapter;position=adapter.positions()[0];iid=position.trade_intent_id
    receipt=first.runner.cycle.router.apply_preservation(cfg.mandate['venue'] if 'venue' in cfg.mandate else adapter.venue,
        position_id=position.position_id,trade_intent_id=iid,action='FULL_CLOSE',
        now_ms=clock['now'],reason='OWNER_ACCEPTED_EXIT')
    first.runner.cycle._on_close(iid,receipt.average_fill,'OWNER_ACCEPTED_EXIT',clock['now'])
    assert not adapter.positions() and first._ledger.count(EventKind.TRADE_REVIEW)==1
    before=first._ledger.count(EventKind.ORDER_COMMAND);first.close();first._ledger.close()
    second=SessionService(cfg,lambda now:[],clock=lambda:clock['now'],adapter=adapter).build()
    try:
        second.start()
        assert second.runner.permit_new_orders and not second.runner.cycle._entries
        assert second._ledger.count(EventKind.ORDER_COMMAND)==before
        assert second._ledger.count(EventKind.TRADE_REVIEW)==1
    finally:second.close();second._ledger.close()
