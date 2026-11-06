"""Signed original pending cancellation, real SQL, replay and uncertain effects."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal as D

import pytest

from conftest_owner_authority import OwnerAuthorityHarness
from test_native_fee_terms import original_fee_entry
from test_ctrader_order_details import native_reply
from vati.authority import OwnerAuthorityError
from vati.core import EventKind, Ledger, make_event
from vati.core.ledger import LedgerError
from vati.execution import ExecutionRouter, ProtectionManager
from vati.execution.base import ExecutionReceipt
from vati.execution.ctrader.transport import _cancel_gate
from vati.execution.native_cancel import ACT, NativeCancelOwner, NativeCancelError, NativeCancelUnknown, cancel_subject
from vati.risk import KillSwitch


def setup_cancel(tmp_path, eurusd, *, ledger=None, original_epoch=None, current_epoch=None):
    ledger, adapter, margin, clock, old_command, old_binding = original_fee_entry(tmp_path, eurusd, ledger=ledger)
    command = replace(old_command, entry_type='LIMIT', lease_epoch=original_epoch, command_hash='').sealed()
    binding = margin.capture_entry(adapter, old_binding['original_input_ref'], command, deadline_ms=clock['ms']+1000)
    at = clock['ms']+1
    ledger.append(make_event(EventKind.ORDER_COMMAND,'vati-execution-router',
        asdict(command)|{'native_entry_margin_ref':binding['record_ref']},
        event_time_ms=at,received_time_ms=at,decision_time_ms=at,correlation_id=command.trade_intent_id))
    receipt = ExecutionReceipt(command.trade_intent_id,command.decision_hash,'ctrader','ACCEPTED',D(0),None,
        command.entry_price,command.entry_price,command.entry_price,False,at+1,at+1,broker_order_id='2').sealed()
    ledger.append(make_event(EventKind.EXECUTION_RECEIPT,'vati-execution-router',asdict(receipt),
        event_time_ms=at+1,received_time_ms=at+1,correlation_id=command.trade_intent_id))
    clock['ms']=at+2
    transport=adapter.transport; response=native_reply();response['order']['orderId']=2
    response['order']['orderStatus']='ORDER_STATUS_ACCEPTED'
    for deal in response['deal']:deal['orderId']=2;deal['positionId']=3
    transport.order_reply=response;transport.cancel_sends=[];transport.before_cancel=lambda:None
    transport.lose_reply=False;original=transport.call
    def read(name,body):
        if name=='ProtoOAOrderDetailsReq':
            transport.calls.append((name,deepcopy(body)))
            return 'ProtoOAOrderDetailsRes',deepcopy(transport.order_reply)
        return original(name,body)
    def cancel(name,body,*,expires_at_ms,clock,recheck):
        transport.before_cancel();_cancel_gate(expires_at_ms,clock,recheck)
        transport.cancel_sends.append((name,deepcopy(body)))
        transport.order_reply['order']['orderStatus']='ORDER_STATUS_CANCELLED'
        if transport.lose_reply:raise OSError('fixture cancelled but native reply lost')
        return 'ProtoOAExecutionEvent',{'ctidTraderAccountId':12345,'executionType':'ORDER_CANCELLED',
            'order':deepcopy(transport.order_reply['order']),'deal':deepcopy(transport.order_reply['deal'][0])}
    transport.call=read;transport.call_cancel=cancel
    router=ExecutionRouter(ledger=ledger,adapters={'ctrader':adapter},kill_switch=KillSwitch(),
        protection=ProtectionManager(),clock=lambda:clock['ms'])
    if current_epoch is not None:
        from contextlib import nullcontext
        router.lease_fence=lambda epoch:epoch==current_epoch
        router.lease_submission_guard=lambda epoch:nullcontext(epoch==current_epoch)
    authority=OwnerAuthorityHarness();owner=NativeCancelOwner(router,authority=authority.verifier)
    intent=owner.prepare('cancel-1',command.command_hash,binding['source_ref'],2,
                         deadline_ms=clock['ms']+1000,lease_epoch=current_epoch)
    token=authority.token(act=ACT,subject=cancel_subject(intent),issued_at_unix=clock['ms']//1000)
    return ledger,adapter,router,owner,authority,clock,intent,token


def test_real_signed_cancel_is_committed_once_and_historical_replay_needs_no_adapter(tmp_path,eurusd):
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd)
    try:
        result=owner.execute(intent,token)
        assert result['state']==result['attempt_state']=='WIRE_OBSERVED'
        assert result['original_response']['body']['deal']['filledVolume']==200000
        assert adapter.transport.cancel_sends==[('ProtoOACancelOrderReq',{'ctidTraderAccountId':12345,'orderId':2})]
        count=ledger.count();calls=len(adapter.transport.calls);clock['ms']+=999999
        router.adapters.clear();authority.verifier.keys.clear()
        assert owner.execute(intent,None)==result
        assert ledger.count()==count and len(adapter.transport.calls)==calls
        assert result['remaining_entry_allowance'] is result['position_flat'] is None
        assert result['cash_settled'] is result['fees_final'] is result['execution_authority'] is False
        assert ledger.count(EventKind.ORDER_COMMAND)==ledger.count(EventKind.EXECUTION_RECEIPT)==1
        assert ledger.verify_chain()[0]
    finally:ledger.close()


def test_lost_cancel_reply_recovers_by_original_read_without_a_second_send(tmp_path,eurusd):
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd)
    reopened=None
    try:
        adapter.transport.lose_reply=True
        result=owner.execute(intent,token);assert result['state']==result['attempt_state']=='UNKNOWN'
        clock['ms']+=100000
        reopened=Ledger(ledger.path)
        recovered_router=ExecutionRouter(ledger=reopened,adapters={'ctrader':adapter},kill_switch=KillSwitch(),
            protection=ProtectionManager(),clock=lambda:clock['ms'])
        recovered=NativeCancelOwner(recovered_router,authority=authority.verifier)
        assert recovered.execute(intent,None)['original_request_ref']==result['original_request_ref']
        current=recovered.reconcile('cancel-1','cancel-read-1',deadline_ms=clock['ms']+1000)
        assert current['state']=='ORDER_OBSERVED' and current['attempt_state']=='UNKNOWN'
        assert current['original_response']=={'error_type':'OSError'}
        assert current['latest_native_order_query']['request_id']=='cancel-read-1'
        from vati.execution.native_order_book import NativeOrderBook
        native=NativeOrderBook(reopened).lookup('cancel-read-1')['observation']
        assert native['facts']['native_order_status']=='ORDER_STATUS_CANCELLED'
        assert native['facts']['recorded_gross_deal_volume']==500000
        assert current['position_flat'] is None and current['cash_settled'] is False
        assert len(adapter.transport.cancel_sends)==1 and ledger.verify_chain()[0]
    finally:
        if reopened is not None:reopened.close()
        ledger.close()


@pytest.mark.parametrize('defect',['missing','stranger','different-act','different-subject','expired','revoked','tampered-intent'])
def test_invalid_owner_control_never_queries_or_sends(tmp_path,eurusd,defect):
    from vati.core.canonical import canonical_hash
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd)
    count=ledger.count();calls=len(adapter.transport.calls)
    if defect=='missing':token=None
    elif defect=='stranger':token=authority.stranger_token(act=ACT,subject=cancel_subject(intent),issued_at_unix=clock['ms']//1000)
    elif defect=='different-act':token=authority.token(act='owner-halt',subject=cancel_subject(intent),issued_at_unix=clock['ms']//1000)
    elif defect=='different-subject':token=authority.token(act=ACT,subject='foreign',issued_at_unix=clock['ms']//1000)
    elif defect=='expired':clock['ms']+=1000000
    elif defect=='revoked':authority.verifier.keys.clear()
    else:
        intent=dict(intent);intent['account_alias']='foreign'
        intent['intent_hash']=canonical_hash({k:v for k,v in intent.items() if k!='intent_hash'})
    try:
        with pytest.raises((ValueError,OwnerAuthorityError)):owner.execute(intent,token)
        assert ledger.count()==count and len(adapter.transport.calls)==calls and not adapter.transport.cancel_sends
    finally:ledger.close()


def test_staged_caller_transaction_cannot_query_or_send_a_cancel(tmp_path,eurusd):
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd)
    count=ledger.count();calls=len(adapter.transport.calls)
    try:
        with ledger.atomic():
            with pytest.raises(LedgerError,match='committed_source_read_requires'):owner.execute(intent,token)
        assert ledger.count()==count and len(adapter.transport.calls)==calls and not adapter.transport.cancel_sends
    finally:ledger.close()


def test_owner_key_revoked_at_native_send_is_a_durable_not_sent_result(tmp_path,eurusd):
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd)
    adapter.transport.before_cancel=lambda:authority.verifier.keys.clear()
    try:
        result=owner.execute(intent,token)
        assert result['state']==result['attempt_state']=='NOT_SENT'
        assert not adapter.transport.cancel_sends and ledger.verify_chain()[0]
        assert owner.execute(intent,None)==result
    finally:ledger.close()


def test_original_commit_ack_loss_blocks_send_and_restart_never_resubmits(tmp_path,eurusd,monkeypatch):
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd)
    atomic=ledger.atomic;outer_writes=[]
    @contextmanager
    def lost_ack():
        outer=not ledger._conn.in_transaction
        with atomic():yield ledger
        if outer:
            outer_writes.append(1)
            if len(outer_writes)==2:raise OSError('fixture cancel request committed, ACK lost')
    try:
        monkeypatch.setattr(ledger,'atomic',lost_ack)
        with pytest.raises(NativeCancelUnknown) as error:owner.execute(intent,token)
        assert error.value.request_id=='cancel-1'
        monkeypatch.setattr(ledger,'atomic',atomic)
        assert owner.lookup('cancel-1')['state']=='REQUESTED'
        assert owner.execute(intent,None)['state']=='REQUESTED' and not adapter.transport.cancel_sends
        assert ledger.verify_chain()[0]
    finally:ledger.close()


def test_sql_writer_expiry_is_rechecked_without_publishing_or_sending_control(tmp_path,eurusd,monkeypatch):
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd)
    atomic=ledger.atomic;outer_writes=[]
    @contextmanager
    def delayed():
        outer=not ledger._conn.in_transaction
        with atomic():
            if outer:
                outer_writes.append(1)
                if len(outer_writes)==2:clock['ms']=intent['deadline_ms']
            yield ledger
    try:
        monkeypatch.setattr(ledger,'atomic',delayed)
        with pytest.raises(NativeCancelError,match='FENCE_CHANGED'):owner.execute(intent,token)
        assert owner.lookup('cancel-1') is None and not adapter.transport.cancel_sends and ledger.verify_chain()[0]
    finally:ledger.close()


def test_repeated_reconciliation_reads_original_query_without_republishing(tmp_path,eurusd):
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd)
    try:
        owner.execute(intent,token)
        first=owner.reconcile('cancel-1','read-after-cancel',deadline_ms=clock['ms']+1000)
        count=ledger.count();calls=len(adapter.transport.calls);clock['ms']+=999999
        second=owner.reconcile('cancel-1','read-after-cancel',deadline_ms=1)
        assert second==first
        assert ledger.count()==count and len(adapter.transport.calls)==calls
        assert len(adapter.transport.cancel_sends)==1
    finally:ledger.close()


def test_old_preflight_query_cannot_be_presented_as_post_cancel_reconciliation(tmp_path,eurusd):
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd)
    try:
        owner.execute(intent,token);count=ledger.count()
        with pytest.raises(NativeCancelError,match='LATER'):
            owner.reconcile('cancel-1','cancel-pre-'+intent['intent_hash'],deadline_ms=clock['ms']+1000)
        assert ledger.count()==count and len(adapter.transport.cancel_sends)==1
    finally:ledger.close()


def test_explicit_rejected_cancel_can_have_a_new_signed_attempt_after_fresh_reconciliation(tmp_path,eurusd):
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd)
    def rejected(name,body,*,expires_at_ms,clock,recheck):
        _cancel_gate(expires_at_ms,clock,recheck)
        adapter.transport.cancel_sends.append((name,deepcopy(body)))
        return 'ProtoOAExecutionEvent',{'ctidTraderAccountId':12345,'executionType':'ORDER_CANCEL_REJECTED',
            'order':deepcopy(adapter.transport.order_reply['order'])}
    adapter.transport.call_cancel=rejected
    try:
        first=owner.execute(intent,token)
        owner.reconcile('cancel-1','read-after-rejection',deadline_ms=clock['ms']+1000)
        next_intent=owner.prepare('cancel-2',intent['command_hash'],intent['margin_source_ref'],2,
                                  deadline_ms=clock['ms']+1000)
        next_token=authority.token(act=ACT,subject=cancel_subject(next_intent),issued_at_unix=clock['ms']//1000)
        second=owner.execute(next_intent,next_token)
        assert second['original_request_ref']!=first['original_request_ref']
        assert len(adapter.transport.cancel_sends)==2
        count=ledger.count()
        assert owner.execute(intent,token)['original_request_ref']==first['original_request_ref']
        assert ledger.count()==count and len(adapter.transport.cancel_sends)==2
    finally:ledger.close()


def test_new_runtime_lease_can_cancel_original_order_without_rewriting_its_origin_epoch(tmp_path,eurusd):
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd,
        original_epoch=2,current_epoch=3)
    try:
        assert intent['original_lease_epoch']==2 and intent['lease_epoch']==3
        result=router.cancel_native_order(intent,token,authority=authority.verifier)
        assert result['state']=='WIRE_OBSERVED' and len(adapter.transport.cancel_sends)==1
        count=ledger.count()
        router.lease_fence=lambda epoch:False
        assert router.cancel_native_order(intent,None,authority=authority.verifier)==result
        assert ledger.count()==count
    finally:ledger.close()


def test_stale_runtime_fence_cannot_query_or_send_control(tmp_path,eurusd):
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd,
        original_epoch=2,current_epoch=3)
    router.lease_fence=lambda epoch:False;count=ledger.count();calls=len(adapter.transport.calls)
    try:
        with pytest.raises(NativeCancelError,match='LEASE_REFUSED'):owner.execute(intent,token)
        assert ledger.count()==count and len(adapter.transport.calls)==calls and not adapter.transport.cancel_sends
    finally:ledger.close()


def test_reduction_cancel_remains_available_when_new_entries_are_halted(tmp_path,eurusd):
    from vati.risk.contracts import KillSwitchTrigger
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd)
    try:
        router.kill.trip(KillSwitchTrigger.OWNER_HALT,clock['ms'])
        assert router.kill.halted
        assert owner.execute(intent,token)['state']=='WIRE_OBSERVED'
        assert len(adapter.transport.cancel_sends)==1 and ledger.verify_chain()[0]
    finally:ledger.close()


def test_clock_loss_after_native_reply_retains_known_response_and_explicit_unavailable_time(tmp_path,eurusd):
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd)
    cancel=adapter.transport.call_cancel
    def lost_clock(*args,**kwargs):
        reply=cancel(*args,**kwargs);clock['ms']=None;return reply
    adapter.transport.call_cancel=lost_clock
    try:
        result=owner.execute(intent,token)
        assert result['state']=='WIRE_OBSERVED'
        assert result['availability']=={'state':'UNAVAILABLE','received_at_ms':None}
        assert result['original_response']['body']['deal']['filledVolume']==200000
        assert len(adapter.transport.cancel_sends)==1 and ledger.verify_chain()[0]
    finally:ledger.close()


def test_control_journal_reserves_a_result_slot_before_native_send(tmp_path,eurusd):
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd)
    limited=NativeCancelOwner(router,authority=authority.verifier,max_records=1)
    try:
        with pytest.raises(NativeCancelError,match='CAPACITY'):limited.execute(intent,token)
        assert not adapter.transport.cancel_sends and owner.lookup('cancel-1') is None
        assert ledger.verify_chain()[0]
    finally:ledger.close()


def test_uncertain_attempt_cannot_be_retried_under_a_new_signed_request(tmp_path,eurusd):
    ledger,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd)
    try:
        adapter.transport.lose_reply=True
        assert owner.execute(intent,token)['attempt_state']=='UNKNOWN'
        # A current working snapshot alone does not prove the earlier cancel
        # was not applied. It cannot grant a second native attempt.
        adapter.transport.order_reply['order']['orderStatus']='ORDER_STATUS_ACCEPTED'
        owner.reconcile('cancel-1','read-still-working',deadline_ms=clock['ms']+1000)
        other=owner.prepare('cancel-2',intent['command_hash'],intent['margin_source_ref'],2,
                            deadline_ms=clock['ms']+1000)
        other_token=authority.token(act=ACT,subject=cancel_subject(other),issued_at_unix=clock['ms']//1000)
        with pytest.raises(NativeCancelError,match='REQUIRES_RECONCILIATION'):owner.execute(other,other_token)
        assert len(adapter.transport.cancel_sends)==1 and ledger.verify_chain()[0]
    finally:ledger.close()
