"""Durable provisional holds; incomplete obligations cannot dispatch orders."""
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal as D
import pytest

from test_current_entry_risk_source import current_entry
from vati.core import EventKind
from vati.risk import TradingMandate,RiskAuthority
from vati.risk.provisional_resource_book import ProvisionalResourceBook,ResourceHoldUnknown,ResourceHoldError


def prepared(tmp_path,eurusd,*,native_margin=None,mandate_changes=None):
    sdk,clock,ledger,command,margin_ref,current_ref,router=current_entry(tmp_path,eurusd,
        native_margin=native_margin,include_runtime=True,mandate_changes=mandate_changes)
    authority=router.current_risk_authority
    book=ProvisionalResourceBook(ledger,clock=lambda:clock['ms'])
    return sdk,clock,ledger,command,margin_ref,current_ref,authority,book,router


def test_actual_source_and_current_owner_control_publish_one_incomplete_hold_not_an_order(tmp_path,eurusd):
    sdk,clock,ledger,command,margin_ref,current_ref,authority,book,router=prepared(tmp_path,eurusd)
    try:
        before=ledger.count();receipt=book.reserve_entry(command,margin_ref,current_ref,authority)
        assert receipt['state']=='PROVISIONAL_RESOURCE_HOLD'
        assert receipt['execution_authority'] is receipt['reservation_qualified'] is receipt['eligible_for_native_dispatch'] is False
        assert 'FEES' in receipt['missing_requirements'] and 'ACTIVE_SHARED_POLICY' in receipt['missing_requirements']
        assert receipt['command_hash']==command.command_hash and ledger.count()==before+1
        assert ledger.count(EventKind.ORDER_COMMAND)==0 and not sdk.sent and ledger.verify_chain()[0]
    finally:ledger.close()


def test_original_hold_replay_after_expiry_keeps_first_receipt_and_retains_obligation(tmp_path,eurusd):
    sdk,clock,ledger,command,margin_ref,current_ref,authority,book,router=prepared(tmp_path,eurusd)
    try:
        receipt=book.reserve_entry(command,margin_ref,current_ref,authority);count=ledger.count()
        clock['ms']=command.expires_at_ms+100000
        assert book.reserve_entry(command,margin_ref,current_ref,authority)==receipt
        assert ledger.count()==count and not sdk.sent
    finally:ledger.close()


def test_actual_hold_commit_ack_loss_requires_original_readback_without_another_write(tmp_path,eurusd,monkeypatch):
    sdk,clock,ledger,command,margin_ref,current_ref,authority,book,router=prepared(tmp_path,eurusd)
    try:
        atomic=ledger.atomic
        @contextmanager
        def lost_ack():
            outer=not ledger._conn.in_transaction
            with atomic():yield ledger
            if outer:raise OSError('fixture original provisional-hold commit ACK lost')
        monkeypatch.setattr(ledger,'atomic',lost_ack)
        with pytest.raises(ResourceHoldUnknown) as error:book.reserve_entry(command,margin_ref,current_ref,authority)
        assert len(error.value.key)==64
        count=ledger.count();monkeypatch.setattr(ledger,'atomic',atomic)
        receipt=book.reserve_entry(command,margin_ref,current_ref,authority)
        assert receipt['key']==error.value.key and ledger.count()==count and not sdk.sent
    finally:ledger.close()


def test_distinct_original_entries_share_the_actual_projected_margin_floor_budget(tmp_path,eurusd):
    from test_native_risk_history_inputs import record
    from test_entry_margin_binding import entry_command
    from vati.risk.serde import intent_from_dict,snapshot_from_dict
    sdk,clock,ledger,command,margin_ref,current_ref,authority,book,router=prepared(tmp_path,eurusd,
        native_margin=D('2500'),mandate_changes={'max_positions_per_instrument':2})
    try:
        first=book.reserve_entry(command,margin_ref,current_ref,authority)
        original=next(e for e in ledger.iter(EventKind.RISK_DECISION) if e.payload['decision']['decision_hash']==command.decision_hash)
        facts=snapshot_from_dict(original.payload['inputs']['snapshot'])
        trade=replace(intent_from_dict(original.payload['inputs']['intent']),trade_intent_id='other-entry',idempotency_key='other-entry')
        event=record(ledger,facts,request=trade,grant=original.payload['inputs']['mandate'])
        approved=RiskAuthority(authority.mandate).evaluate_safe(trade,facts)
        other=replace(entry_command(event),expires_at_ms=command.expires_at_ms,command_hash='').sealed()
        margin,_=router._native_entry_margin(other,router.adapters['mt5'],now_ms=clock['ms'])
        current=router._current_account_risk(trade,approved,authority.mandate,other,router.adapters['mt5'],
            now_ms=clock['ms'],market_reference=None)
        before=ledger.count()
        with pytest.raises(ResourceHoldError,match='RESOURCE_CAPACITY_EXCEEDED:margin_floor_equity'):
            book.reserve_entry(other,margin,current,authority)
        assert ledger.count()==before and ledger.count(EventKind.ORDER_COMMAND)==0 and not sdk.sent
        assert first['eligible_for_native_dispatch'] is False
    finally:ledger.close()


@pytest.mark.parametrize('authority_value',[None,True,{'approved':True}])
def test_source_data_and_boolean_approval_never_replace_the_existing_authority(tmp_path,eurusd,authority_value):
    sdk,clock,ledger,command,margin_ref,current_ref,authority,book,router=prepared(tmp_path,eurusd)
    try:
        before=ledger.count()
        with pytest.raises(ResourceHoldError,match='RESOURCE_CURRENT_AUTHORITY_REQUIRED'):
            book.reserve_entry(command,margin_ref,current_ref,authority_value)
        assert ledger.count()==before and not sdk.sent
    finally:ledger.close()


def test_real_test_key_revocation_refuses_new_hold_but_keeps_original_history(tmp_path,eurusd):
    import json
    from pathlib import Path
    from vati.risk.current_entry_source import current_entry_source
    sdk,clock,ledger,command,margin_ref,current_ref,authority,book,router=prepared(tmp_path,eurusd)
    key_path=Path(authority.mandate._verified_owner_key_bindings[0].registry_path)
    key_bytes=key_path.read_bytes()
    assert set(json.loads(key_bytes)['keys'])=={'owner-test-1'}
    assert 'pytest-' in str(key_path),'only the explicit test registry may be changed'
    try:
        before=ledger.count();key_path.write_text(json.dumps({'keys':{}}))
        assert authority.mandate.owner_keys_current() is False
        with pytest.raises(ResourceHoldError,match='RESOURCE_OWNER_AUTHORITY_UNAVAILABLE'):
            book.reserve_entry(command,margin_ref,current_ref,authority)
        assert ledger.count()==before and not sdk.sent
        key_path.write_bytes(key_bytes)
        receipt=book.reserve_entry(command,margin_ref,current_ref,authority)
        source=current_entry_source(ledger,command,margin_ref,current_ref,available_at_ms=clock['ms']).body()
        count=ledger.count();key_path.write_text(json.dumps({'keys':{}}))
        original=book.lookup(source['physical_account_key'],source['monetary_scope_hash'],command.account_alias,command.idempotency_key)
        assert original==receipt and original['eligible_for_native_dispatch'] is False
        assert book.reserve_entry(command,margin_ref,current_ref,None)==receipt
        assert ledger.count()==count and not sdk.sent
    finally:key_path.write_bytes(key_bytes);ledger.close()


def test_another_alias_cannot_ignore_existing_holds_on_the_same_native_account(tmp_path,eurusd):
    from conftest import NOW,mandate_dict
    from test_native_risk_history_inputs import record
    from test_entry_margin_binding import entry_command
    from vati.execution.mt5_bridge import Mt5BridgeAdapter
    from vati.execution import ExecutionRouter,ProtectionManager
    from vati.execution.risk_refresh import CurrentRiskFacts
    from vati.funding.mt5_runtime import capture_cached_mt5
    from vati.risk.account_context import context_for_account
    from vati.risk import KillSwitch
    from vati.risk.serde import intent_from_dict,snapshot_from_dict
    sdk,clock,ledger,command,margin_ref,current_ref,authority,book,router=prepared(tmp_path,eurusd)
    try:
        first=book.reserve_entry(command,margin_ref,current_ref,authority)
        original=next(e for e in ledger.iter(EventKind.RISK_DECISION) if e.payload['decision']['decision_hash']==command.decision_hash)
        old_adapter=router.adapters['mt5'];worker=old_adapter.client._transport.__self__
        alias='same_native_other_label'
        worker.cfg['accounts'][alias]=dict(worker.cfg['accounts'][command.account_alias])
        adapter=Mt5BridgeAdapter(old_adapter.client,account_alias=alias,clock=lambda:clock['ms'],identity=old_adapter.identity)
        account=adapter.sync_account();captured=capture_cached_mt5(ledger,account,now_ms=clock['ms'])
        context=context_for_account(ledger,adapter,account,now_ms=clock['ms'],mt5_capture=captured)
        facts=replace(snapshot_from_dict(original.payload['inputs']['snapshot']),account_alias=alias,native_account_context=context)
        trade=replace(intent_from_dict(original.payload['inputs']['intent']),account_alias=alias,
            trade_intent_id='other-label-entry',idempotency_key='other-label-entry')
        grant=mandate_dict(account_alias=alias,max_risk_per_trade=D('.004'),
            max_open_stop_risk=D('.004'),expires_at_unix=NOW+2)
        other_authority=RiskAuthority(TradingMandate.from_mapping(grant))
        event=record(ledger,facts,request=trade,grant=grant);approved=other_authority.evaluate_safe(trade,facts)
        other=entry_command(event)
        other_router=ExecutionRouter(ledger=ledger,adapters={'mt5':adapter},kill_switch=KillSwitch(),
            protection=ProtectionManager(),clock=lambda:clock['ms'],current_risk_authority=other_authority,
            current_risk_facts_provider=lambda *a,**kw:CurrentRiskFacts(facts,clock['ms']))
        margin,_=other_router._native_entry_margin(other,adapter,now_ms=clock['ms'])
        current=other_router._current_account_risk(trade,approved,other_authority.mandate,other,adapter,
            now_ms=clock['ms'],market_reference=None)
        before=ledger.count()
        with pytest.raises(ResourceHoldError,match='RESOURCE_CAPACITY_EXCEEDED:stop_risk'):
            book.reserve_entry(other,margin,current,other_authority)
        assert ledger.count()==before and not sdk.sent
        assert first['eligible_for_native_dispatch'] is False
    finally:ledger.close()


def test_independent_sqlite_connections_serialize_distinct_entries_and_keep_the_first_hold(tmp_path,eurusd):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from vati.core import Ledger
    from test_current_entry_risk_source_postgres import restore_original_history
    from test_entry_resource_groups import another_entry
    sdk,clock,original,command,margin,current,authority,old,router=prepared(tmp_path,eurusd,
        native_margin=D('2500'),mandate_changes={'max_positions_per_instrument':2})
    other,other_margin,other_current=another_entry(original,command,authority,router,clock)
    path=tmp_path/'financial-owner.sqlite';ledger=Ledger(path)
    try:
        restore_original_history(ledger,original);before=ledger.count();start=threading.Barrier(2)
        entries=[(command,margin,current),(other,other_margin,other_current)]
        def reserve(entry):
            connection=Ledger(path)
            try:
                start.wait(5)
                try:return ProvisionalResourceBook(connection,clock=lambda:clock['ms']).reserve_entry(*entry,authority)
                except ResourceHoldError as error:return error
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(reserve,e) for e in entries]
            results=[job.result(timeout=20) for job in futures]
        winners=[i for i,r in enumerate(results) if isinstance(r,dict)]
        assert len(winners)==1 and ledger.count()==before+1
        winner=winners[0];loser=1-winner
        assert isinstance(results[loser],ResourceHoldError)
        assert str(results[loser]) in {'RESOURCE_SOURCE_CHANGED_RETRY_ORIGINAL',
            'RESOURCE_CAPACITY_EXCEEDED:margin_floor_equity'}
        book=ProvisionalResourceBook(ledger,clock=lambda:clock['ms'])
        assert book.reserve_entry(*entries[winner],authority)==results[winner]
        with pytest.raises(ResourceHoldError,match='RESOURCE_CAPACITY_EXCEEDED:margin_floor_equity'):
            book.reserve_entry(*entries[loser],authority)
        assert ledger.count()==before+1 and ledger.verify_chain()[0] and not sdk.sent
    finally:ledger.close();original.close()


def test_resealed_requirement_history_cannot_remove_original_unresolved_obligations(tmp_path,eurusd):
    import json
    from vati.core import make_event
    sdk,clock,ledger,command,margin,current,authority,book,router=prepared(tmp_path,eurusd)
    try:
        receipt=book.reserve_entry(command,margin,current,authority)
        original=next(e for e in ledger.iter(EventKind.SESSION) if e.hash==receipt['record_ref'])
        assert original.payload['missing_requirements']==receipt['missing_requirements']
        body=json.loads(json.dumps(original.payload));body['missing_requirements']=[]
        ledger.append(make_event(EventKind.SESSION,original.producer,body,event_time_ms=clock['ms'],
            received_time_ms=clock['ms'],correlation_id=original.correlation_id))
        assert ledger.verify_chain()[0]
        p=body['projection']
        with pytest.raises(ResourceHoldError,match='RESOURCE_ORIGINAL_REQUIREMENTS_INVALID'):
            book.lookup(p['physical_account_key'],p['monetary_scope_hash'],command.account_alias,command.idempotency_key)
        assert not sdk.sent
    finally:ledger.close()
