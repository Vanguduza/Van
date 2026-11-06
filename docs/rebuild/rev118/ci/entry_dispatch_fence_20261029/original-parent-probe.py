"""Current unchanged counterexample functions executed against pinned published parent source."""
from dataclasses import replace
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import os
import threading
import pytest
from conftest import NOW, intent, mandate_dict, snapshot
from vati.core import EventKind, Ledger
from vati.execution import ExecutionRouter, PaperAdapter, ProtectionManager, RouterError
from vati.risk import Decision, KillSwitch, RiskAuthority, StrategyState, TradingMandate

def approved_entry(contract):
    mandate = TradingMandate.from_mapping(mandate_dict(venue='paper', mode='DEMO_TRADER'))
    trade = intent(venue='paper', strategy_state=StrategyState.DEMO)
    decision = RiskAuthority(mandate).evaluate_safe(trade, snapshot(replace(contract, venue='paper')))
    assert decision.decision in {Decision.APPROVED, Decision.REDUCED}
    return (mandate, trade, decision)

def sender(ledger, adapter):
    return ExecutionRouter(ledger=ledger, adapters={'paper': adapter}, kill_switch=KillSwitch(), protection=ProtectionManager())

def test_preexisting_independent_routers_cannot_dispatch_the_same_original_twice(tmp_path, eurusd):
    mandate, trade, decision = approved_entry(eurusd)
    path = tmp_path / 'entry.sqlite'
    first, second = (Ledger(path), Ledger(path))
    left, right = (PaperAdapter(), PaperAdapter())
    try:
        a, b = (sender(first, left), sender(second, right))
        a.execute(trade, decision, mandate, now_ms=NOW * 1000)
        try:
            b.execute(trade, decision, mandate, now_ms=NOW * 1000 + 1)
        except RouterError:
            pass
        assert first.count(EventKind.ORDER_COMMAND) == 1
        assert len(left.positions()) + len(right.positions()) == 1
        assert first.verify_chain()[0]
    finally:
        second.close()
        first.close()

def test_ambient_transaction_cannot_send_before_its_command_is_committed(eurusd):
    mandate, trade, decision = approved_entry(eurusd)
    ledger, adapter = (Ledger(), PaperAdapter())
    try:
        router = sender(ledger, adapter)
        with ledger.atomic():
            try:
                router.execute(trade, decision, mandate, now_ms=NOW * 1000)
            except RouterError:
                pass
            assert not adapter.positions(), 'native effect escaped an uncommitted caller transaction'
        assert ledger.count(EventKind.ORDER_COMMAND) == 0
    finally:
        ledger.close()
