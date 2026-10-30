"""Ambiguous native facts cannot receive a sealed approval or reach a sender."""
from dataclasses import replace
from decimal import Decimal

import pytest

from conftest import intent,mandate_dict,snapshot
from vati.core import Ledger
from vati.execution.paper import PaperAdapter
from vati.execution.protection import ProtectionManager
from vati.execution.router import ExecutionRouter
from vati.risk import Decision,KillSwitch,RiskAuthority,StrategyState,TradingMandate
from vati.risk.contracts import Direction,KillSwitchTrigger,OpenPosition


@pytest.mark.parametrize('field',['account_verified','broker_connected','reconciliation_ok','clock_sync_ok','risk_store_ok'])
def test_a_truthy_false_string_cannot_get_kernel_approval_and_a_real_paper_fill(eurusd,field):
    contract=replace(eurusd,venue='paper')
    mandate=TradingMandate.from_mapping(mandate_dict(venue='paper',mode='DEMO_TRADER'))
    trade=intent(venue='paper',strategy_state=StrategyState.DEMO)
    native=snapshot(contract,**{field:'false'})
    authority=RiskAuthority(mandate);decision=authority.evaluate_safe(trade,native)
    paper=PaperAdapter(account_alias=mandate.account_alias)
    router=ExecutionRouter(ledger=Ledger(),adapters={'paper':paper},kill_switch=KillSwitch(),protection=ProtectionManager())
    if decision.decision in {Decision.APPROVED,Decision.REDUCED}:
        receipt=router.execute(trade,decision,mandate,now_ms=native.now_unix*1000)
        assert receipt.status=='FILLED' and paper.positions()
    assert decision.decision is Decision.REJECTED,field
    assert not paper.positions() and not paper.pending


@pytest.mark.parametrize('scope,field,value',[
    ('snapshot','preservation_blocks_new_risk',0),
    ('snapshot','tier1_event_blackout_active',0),
    ('intent','is_event_certified','false'),
    ('intent','holds_over_weekend',0),
    ('contract','is_synthetic','false'),
    ('position','has_broker_side_stop','false'),
])
def test_unproven_policy_or_nested_protection_facts_are_explicitly_refused(eurusd,scope,field,value):
    contract=replace(eurusd,venue='paper')
    mandate=TradingMandate.from_mapping(mandate_dict(venue='paper',mode='DEMO_TRADER'))
    trade=intent(venue='paper',strategy_state=StrategyState.DEMO);native=snapshot(contract)
    if scope=='snapshot':native=replace(native,**{field:value})
    elif scope=='intent':
        trade=replace(trade,**{field:value})
        if field=='is_event_certified':native=replace(native,tier1_event_blackout_active=True)
    elif scope=='contract':native=replace(native,symbol_contract=replace(contract,**{field:value}))
    else:
        position=OpenPosition('GBPUSD',Direction.LONG,Decimal('.01'),Decimal('.001'),Decimal('100000'),'GBP','USD',
            has_broker_side_stop=value)
        native=replace(native,open_positions=(position,))
    result=RiskAuthority(mandate).evaluate_safe(trade,native)
    assert result.decision is Decision.REJECTED and result.reason_code=='INVALID_BOOLEAN_FACT'
    assert field in result.reason_detail


def test_known_native_halt_keeps_priority_and_a_refused_fact_does_not_poison_recovery(eurusd):
    contract=replace(eurusd,venue='paper')
    mandate=TradingMandate.from_mapping(mandate_dict(venue='paper',mode='DEMO_TRADER'))
    trade=intent(venue='paper',strategy_state=StrategyState.DEMO);authority=RiskAuthority(mandate)
    invalid=snapshot(contract,account_verified='false')
    halted=authority.evaluate_safe(trade,replace(invalid,kill_switch_triggers=frozenset({KillSwitchTrigger.OWNER_HALT})))
    assert halted.reason_code=='KILL_SWITCH'
    refused=authority.evaluate_safe(trade,invalid)
    assert refused.reason_code=='INVALID_BOOLEAN_FACT'
    recovered=authority.evaluate_safe(trade,snapshot(contract))
    assert recovered.decision in {Decision.APPROVED,Decision.REDUCED}
