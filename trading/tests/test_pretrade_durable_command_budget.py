"""An account's original command window must survive control-owner restart."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from conftest import NOW, snapshot
from test_mandate_dispatch_validity import flow
from vati.core import EventKind, Ledger
from vati.execution import ExecutionRouter, PaperAdapter, ProtectionManager, RouterError
from vati.execution.policy import ExecutionBucket, ExecutionPolicyEngine
from vati.execution.pretrade import MarketReference, PreTradeControls, PreTradeConfigError
from vati.execution.route_registry import RouteRegistry
from vati.execution.style_selector import ExecutionStyleSelector, LiquidityView
from vati.risk import Decision, KillSwitch, RiskAuthority
from vati.risk.contracts import OpenPosition


def durable_controls(ledger, eurusd, *, max_orders=30, account_alias=None):
    """Actual signed source mandate, risk owner and configured router."""
    mandate, trade, native = flow(eurusd, max_positions_per_instrument=2,
        **({'account_alias': account_alias} if account_alias is not None else {}))
    trade=replace(trade,account_alias=mandate.account_alias)
    native=replace(native,account_alias=mandate.account_alias)
    adapter = PaperAdapter(account_alias=mandate.account_alias)
    routes = RouteRegistry()
    routes.refresh(account_alias=mandate.account_alias, adapter_id='paper',
        contracts={'EURUSD':replace(eurusd,venue='paper')}, now_ms=NOW*1000)
    controls = PreTradeControls(routes=routes,ledger=ledger,max_orders_per_window=max_orders)
    router = ExecutionRouter(ledger=ledger,adapters={'paper':adapter},kill_switch=KillSwitch(),
        protection=ProtectionManager(),route_registry=routes,pretrade_controls=controls,
        style_selector=ExecutionStyleSelector(),enforce_rev51_controls=True)
    def send(index, *, risk=None, now=None):
        request=replace(trade,trade_intent_id='command-'+str(index),idempotency_key='command-key-'+str(index),
            **({'requested_risk_pct':risk} if risk is not None else {}))
        decision=RiskAuthority(mandate).evaluate_safe(request,native)
        assert decision.decision in {Decision.APPROVED,Decision.REDUCED}
        policy=ExecutionPolicyEngine().select(candidate_id=request.trade_intent_id,
            bucket=ExecutionBucket('paper',mandate.account_alias,'EURUSD','LONDON','NORMAL','NONE','LONG'))
        return router.execute(request,decision,mandate,now_ms=NOW*1000 if now is None else now,
            execution_policy_decision=policy,market_reference=MarketReference(request.entry,0),liquidity=LiquidityView())
    return mandate,adapter,controls,router,send


@pytest.mark.parametrize('restart', [False, True])
def test_actual_account_command_window_survives_a_recreated_control_owner(tmp_path, eurusd, restart):
    mandate, first, native = flow(eurusd, max_positions_per_instrument=2)
    path = tmp_path/'commands.sqlite'
    ledger, adapter = Ledger(path), PaperAdapter(account_alias=mandate.account_alias)
    routes = RouteRegistry()
    contract = replace(eurusd, venue='paper')
    routes.refresh(account_alias=mandate.account_alias, adapter_id='paper',
        contracts={'EURUSD': contract}, now_ms=NOW*1000)
    def owner(connection):
        return ExecutionRouter(ledger=connection, adapters={'paper': adapter},
            kill_switch=KillSwitch(), protection=ProtectionManager(), route_registry=routes,
            pretrade_controls=PreTradeControls(routes=routes, ledger=connection, max_orders_per_window=1),
            style_selector=ExecutionStyleSelector(), enforce_rev51_controls=True)
    def execute(router, trade, decision, at):
        policy = ExecutionPolicyEngine().select(candidate_id=trade.trade_intent_id,
            bucket=ExecutionBucket('paper',mandate.account_alias,'EURUSD','LONDON','NORMAL','NONE','LONG'))
        return router.execute(trade,decision,mandate,now_ms=at,execution_policy_decision=policy,
            market_reference=MarketReference(trade.entry,0),liquidity=LiquidityView())
    connection = None
    try:
        router = owner(ledger)
        decision = RiskAuthority(mandate).evaluate_safe(first,native)
        assert decision.decision in {Decision.APPROVED,Decision.REDUCED}
        assert execute(router,first,decision,NOW*1000).status == 'FILLED'
        position = adapter.positions()[0]
        existing = OpenPosition(position.symbol,position.direction,position.quantity,
            abs(position.entry_price-position.stop_price),contract.value_per_price_unit_per_lot,
            contract.base_currency,contract.quote_currency,strategy_id=first.strategy_id,
            broker_position_id=position.position_id)
        second = replace(first,trade_intent_id='second-original',idempotency_key='second-original-key')
        current = snapshot(contract,open_positions=(existing,))
        approved = RiskAuthority(mandate).evaluate_safe(second,current)
        assert approved.decision in {Decision.APPROVED,Decision.REDUCED}
        if restart:
            connection = Ledger(path)
            router = owner(connection)
        try:
            execute(router,second,approved,NOW*1000+1)
        except RouterError as error:
            assert 'ORDER_RATE_LIMIT' in str(error)
        assert ledger.count(EventKind.ORDER_COMMAND) == 1
        assert len(adapter.positions()) == 1
        assert ledger.verify_chain()[0]
    finally:
        if connection is not None:
            connection.close()
        ledger.close()


@pytest.mark.parametrize('options', [
    {'max_orders_per_window': True}, {'max_orders_per_window': 1.5},
    {'max_orders_per_window': float('nan')},
    {'order_window_ms': 0}, {'order_window_ms': -1}, {'order_window_ms': True},
    {'order_window_ms': float('nan')}, {'max_notional': D('NaN')},
    {'max_notional': float('inf')},
])
def test_invalid_command_control_parameters_cannot_disable_a_budget(options):
    with pytest.raises(PreTradeConfigError):
        PreTradeControls(routes=RouteRegistry(), **options)


@pytest.mark.parametrize('field,value', [
    ('max_orders_per_window',True),('max_orders_per_window',float('nan')),
    ('order_window_ms',-1),('max_notional',D('NaN')),
    ('max_orders_per_window',1000),('order_window_ms',1),
])
def test_mutated_joint_control_parameters_are_refused_at_the_actual_sender(tmp_path,eurusd,field,value):
    ledger=Ledger(tmp_path/'invalid-control.sqlite')
    try:
        _,adapter,controls,_,send=durable_controls(ledger,eurusd)
        setattr(controls,field,value)
        with pytest.raises(RouterError,match='CONTROL_CONFIG_INVALID'):
            send(1)
        assert not adapter.positions() and ledger.count(EventKind.ORDER_COMMAND)==0
    finally:
        ledger.close()


def test_durable_command_window_expires_only_from_original_publication_time(tmp_path,eurusd):
    path=tmp_path/'window.sqlite';ledger=Ledger(path)
    try:
        _,adapter,_,_,send=durable_controls(ledger,eurusd,max_orders=1)
        opened=send(1);assert opened.status=='FILLED'
        adapter.close(opened.broker_position_id,None,now_ms=NOW*1000,reason='source-test-close')
    finally:
        ledger.close()
    ledger=Ledger(path)
    try:
        _,adapter,_,_,send=durable_controls(ledger,eurusd,max_orders=1)
        with pytest.raises(RouterError,match='ORDER_RATE_LIMIT'):
            send(2,now=NOW*1000+60_000)
        assert send(2,now=NOW*1000+60_001).status=='FILLED'
        assert ledger.count(EventKind.ORDER_COMMAND)==2 and len(adapter.positions())==1
        assert ledger.verify_chain()[0]
    finally:
        ledger.close()


def test_original_command_sizes_restore_fat_finger_control_after_reopen(tmp_path,eurusd):
    path=tmp_path/'sizes.sqlite';ledger=Ledger(path)
    try:
        _,adapter,_,_,send=durable_controls(ledger,eurusd,max_orders=100)
        for index in range(20):
            receipt=send(index,risk=D('.0003'))
            assert receipt.status=='FILLED' and receipt.filled_qty==D('.01')
            adapter.close(receipt.broker_position_id,None,now_ms=NOW*1000,reason='source-test-close')
        assert not adapter.positions()
    finally:
        ledger.close()
    ledger=Ledger(path)
    try:
        _,adapter,_,_,send=durable_controls(ledger,eurusd,max_orders=100)
        with pytest.raises(RouterError,match='FAT_FINGER'):
            send(21)
        assert ledger.count(EventKind.ORDER_COMMAND)==20 and not adapter.positions()
    finally:
        ledger.close()


@pytest.mark.parametrize('defect',['duplicate','producer','future','unbound-account','bad-command-seal'])
def test_unreconciled_history_cannot_be_used_as_a_clean_budget(tmp_path,eurusd,defect):
    from vati.core import make_event
    from vati.core.canonical import canonical_hash
    ledger=Ledger(tmp_path/'history.sqlite')
    try:
        _,adapter,_,_,send=durable_controls(ledger,eurusd,max_orders=10)
        assert send(1).status=='FILLED'
        original=next(ledger.iter(EventKind.ORDER_COMMAND));payload=dict(original.payload)
        if defect=='duplicate':
            event=original
        else:
            payload['trade_intent_id']='history-conflict';payload['idempotency_key']='history-conflict-key'
            if defect=='unbound-account':payload.pop('account_alias')
            payload['command_hash']=canonical_hash({k:v for k,v in payload.items() if k!='command_hash'})
            if defect=='bad-command-seal':payload['command_hash']='0'*64
            event=make_event(EventKind.ORDER_COMMAND,'untrusted-producer' if defect=='producer' else original.producer,
                payload,event_time_ms=NOW*1000+(1 if defect=='future' else 0),
                received_time_ms=NOW*1000+(1 if defect=='future' else 0),correlation_id=payload['trade_intent_id'])
        ledger.append(event)
        with pytest.raises(RouterError,match='COMMAND_HISTORY_UNAVAILABLE'):
            send(2)
        assert len(adapter.positions())==1 and ledger.count(EventKind.ORDER_COMMAND)==2
        assert ledger.verify_chain()[0], 'semantic conflicts remain conflicts even in a valid hash chain'
    finally:
        ledger.close()


def test_a_command_from_another_account_does_not_consume_this_accounts_window(tmp_path,eurusd):
    ledger=Ledger(tmp_path/'scope.sqlite')
    try:
        _,foreign,_,_,other_send=durable_controls(ledger,eurusd,max_orders=1,account_alias='another-account')
        assert other_send(0).status=='FILLED'
        _,adapter,_,_,send=durable_controls(ledger,eurusd,max_orders=1)
        assert send(1).status=='FILLED'
        with pytest.raises(RouterError,match='ORDER_RATE_LIMIT'):
            send(2)
        assert len(adapter.positions())==len(foreign.positions())==1
        assert ledger.count(EventKind.ORDER_COMMAND)==2
    finally:
        ledger.close()


def test_active_command_exclusion_requires_exact_original_bindings(tmp_path,eurusd):
    from vati.execution.command_history import account_command_history,CommandHistoryUnavailable
    ledger=Ledger(tmp_path/'active.sqlite')
    try:
        mandate,_,_,_,send=durable_controls(ledger,eurusd)
        assert send(1).status=='FILLED'
        event=next(ledger.iter(EventKind.ORDER_COMMAND));p=event.payload
        active={'ref':event.hash,'command_hash':p['command_hash'],'decision_hash':p['decision_hash'],
            'trade_intent_id':p['trade_intent_id'],'key':p['idempotency_key'],'producer':event.producer}
        rows,selected=account_command_history(ledger,mandate.account_alias,now_ms=NOW*1000,active=active)
        assert not rows and selected['ref']==event.hash
        for key in active:
            with pytest.raises(CommandHistoryUnavailable):
                account_command_history(ledger,mandate.account_alias,now_ms=NOW*1000,active={**active,key:'incorrect'})
        assert len(account_command_history(ledger,mandate.account_alias,now_ms=NOW*1000)[0])==1
    finally:
        ledger.close()


@pytest.mark.parametrize('defect',['producer','duplicate'])
def test_unreconciled_command_history_keeps_protective_reduction_available(tmp_path,eurusd,defect):
    from vati.core import make_event
    ledger=Ledger(tmp_path/'protect.sqlite')
    try:
        _,adapter,_,router,send=durable_controls(ledger,eurusd,max_orders=10)
        opened=send(1);assert opened.status=='FILLED'
        original=next(ledger.iter(EventKind.ORDER_COMMAND))
        invalid=original if defect=='duplicate' else make_event(EventKind.ORDER_COMMAND,'untrusted-producer',
            original.payload,event_time_ms=NOW*1000,received_time_ms=NOW*1000,
            correlation_id=original.correlation_id)
        ledger.append(invalid)
        with pytest.raises(RouterError,match='COMMAND_HISTORY_UNAVAILABLE'):
            send(2)
        closed=router.apply_preservation('paper',position_id=opened.broker_position_id,
            trade_intent_id=opened.trade_intent_id,action='FULL_CLOSE',reason='protective-reduction',now_ms=NOW*1000+1)
        assert closed.status=='FILLED' and not adapter.positions()
        assert ledger.verify_chain()[0]
    finally:
        ledger.close()


def test_history_precision_is_independent_of_callers_decimal_traps(tmp_path,eurusd):
    from decimal import localcontext,Inexact,Rounded
    from vati.execution.command_history import account_command_history
    ledger=Ledger(tmp_path/'precision.sqlite')
    try:
        mandate,_,_,_,send=durable_controls(ledger,eurusd)
        assert send(1).status=='FILLED'
        with localcontext() as context:
            context.prec=2;context.traps[Inexact]=True;context.traps[Rounded]=True
            before=dict(context.flags)
            rows,selected=account_command_history(ledger,mandate.account_alias,now_ms=NOW*1000)
            assert len(rows)==1 and rows[0]['quantity']==D('.18') and selected is None
            assert dict(context.flags)==before
    finally:
        ledger.close()


def test_binding_a_durable_owner_cannot_discard_legacy_in_memory_notes(tmp_path,eurusd):
    controls=PreTradeControls(routes=RouteRegistry())
    controls.note_sent(account_alias='legacy',idempotency_key='legacy-key',quantity=D('.01'),now_ms=NOW*1000)
    ledger=Ledger(tmp_path/'legacy.sqlite')
    try:
        with pytest.raises(PreTradeConfigError,match='legacy command notes'):
            controls.bind_ledger(ledger)
        assert 'legacy-key' in controls._sent_keys and ledger.count()==0
    finally:
        ledger.close()


def test_actual_router_cannot_read_command_budget_from_another_ledger_owner(tmp_path,eurusd):
    original=Ledger(tmp_path/'owner.sqlite');foreign=Ledger(tmp_path/'foreign.sqlite')
    try:
        _,adapter,controls,_,send=durable_controls(original,eurusd)
        controls._ledger=foreign
        with pytest.raises(RouterError,match='COMMAND_HISTORY_UNAVAILABLE'):
            send(1)
        assert not adapter.positions() and original.count(EventKind.ORDER_COMMAND)==foreign.count()==0
    finally:
        foreign.close();original.close()
