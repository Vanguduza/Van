"""Uncertain protective effects must be reconciled before another send."""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import threading

import pytest

from vati.core.events import EventKind
from vati.core.events import make_event
from vati.core.ledger import Ledger
from vati.execution.base import ExecutionReceipt
from vati.execution.protection import ProtectionManager
from vati.execution.router import ExecutionRouter, RouterError
from vati.risk import KillSwitch
from vati.risk.contracts import Direction, KillSwitchTrigger


class CloseProbe:
    venue = "probe"

    def __init__(self, status="UNKNOWN", error=None):
        self.calls = 0
        self.status = status
        self.error = error

    def close(self, position_id, quantity, *, now_ms, reason):
        self.calls += 1
        if self.error:
            raise self.error
        return ExecutionReceipt("intent", "", self.venue, self.status, D("0"), None,
            D("100"), D("100"), D("100"), True, now_ms, now_ms,
            broker_position_id=position_id, reject_reason=reason).sealed()


def build(ledger, adapter):
    protection = ProtectionManager()
    protection.register("position", symbol="TEST", direction=Direction.LONG,
        entry=D("100"), stop=D("90"), target=None, opened_ms=0)
    return ExecutionRouter(ledger=ledger, adapters={adapter.venue:adapter},
        kill_switch=KillSwitch(), protection=protection)


def mark(router, when=1):
    return router.apply_exits("probe", "TEST", D("89"), D("90"), now_ms=when)


def test_unknown_close_does_not_retry_on_the_next_market_update():
    adapter = CloseProbe()
    router = build(Ledger(), adapter)
    assert mark(router)[0].status == "UNKNOWN"
    assert mark(router, 2) == []
    assert adapter.calls == 1
    assert router.protection.is_close_pending("position")
    assert KillSwitchTrigger.RECONCILIATION_FAILURE in router.kill.active


def test_transport_exception_cannot_turn_into_a_blind_retry():
    adapter = CloseProbe(error=TimeoutError("response lost after venue may have applied close"))
    router = build(Ledger(), adapter)
    with pytest.raises(TimeoutError):
        mark(router)
    assert mark(router, 2) == [] and adapter.calls == 1
    assert KillSwitchTrigger.RECONCILIATION_FAILURE in router.kill.active


def test_receipt_and_exit_disposition_are_committed_together():
    class FailingLedger(Ledger):
        fail_once = True

        def append(self, event):
            if event.kind is EventKind.EXIT_ATTEMPT and event.payload["state"] != "REQUESTED" and self.fail_once:
                self.fail_once = False
                raise OSError("injected disk failure after receipt insert")
            return super().append(event)
    adapter = CloseProbe()
    ledger = FailingLedger()
    router = build(ledger, adapter)
    with pytest.raises(OSError, match="disk failure"):
        mark(router)
    assert ledger.count(EventKind.EXECUTION_RECEIPT) == 0
    assert ledger.count(EventKind.EXIT_ATTEMPT) == 1
    assert router.exit_journal.pending("probe", "position").payload["state"] == "REQUESTED"
    assert mark(router, 2) == [] and adapter.calls == 1


def test_two_ledger_writers_cannot_send_the_same_position_close(tmp_path):
    entered, release = threading.Event(), threading.Event()
    class Blocking(CloseProbe):
        def close(self, *args, **kwargs):
            entered.set()
            assert release.wait(10)
            return super().close(*args, **kwargs)
    adapter, path = Blocking(), tmp_path/"writers.sqlite"
    def run(when):
        return mark(build(Ledger(path), adapter), when)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, 1)
        assert entered.wait(10)
        try:
            assert pool.submit(run, 2).result(timeout=10) == []
        finally:
            release.set()
        assert first.result(timeout=10)[0].status == "UNKNOWN"
    assert adapter.calls == 1
    assert Ledger(path).verify_chain()[0]


@pytest.mark.parametrize("stage,effects", [("after_request", 0), ("after_effect", 1),
    ("before_receipt_commit", 1), ("after_receipt_commit", 1)])
def test_process_death_keeps_the_original_attempt_fenced(tmp_path, stage, effects):
    database, effect = tmp_path/"death.sqlite", tmp_path/"venue-effects.txt"
    script = '''
import os,sys
from pathlib import Path
from decimal import Decimal as D
from vati.core.ledger import Ledger
from vati.core.events import EventKind
from vati.execution.router import ExecutionRouter
from vati.execution.protection import ProtectionManager
from vati.execution.base import ExecutionReceipt
from vati.risk import KillSwitch
from vati.risk.contracts import Direction
path,effect,stage=sys.argv[1:]
ledger=Ledger(path)
protection=ProtectionManager()
protection.register('position',symbol='TEST',direction=Direction.LONG,entry=D('100'),stop=D('90'),target=None,opened_ms=0)
class Adapter:
    venue='probe'
    def close(self,position_id,quantity,*,now_ms,reason):
        with Path(effect).open('a') as stream:stream.write('applied\\n')
        if stage=='after_effect':os._exit(23)
        return ExecutionReceipt('intent','','probe','FILLED',D('1'),D('89'),D('100'),D('100'),D('100'),True,now_ms,now_ms,broker_position_id='position').sealed()
router=ExecutionRouter(ledger=ledger,adapters={'probe':Adapter()},kill_switch=KillSwitch(),protection=protection)
if stage=='after_request':
    original=router.exit_journal.begin
    def begin(**kwargs):
        original(**kwargs)
        os._exit(23)
    router.exit_journal.begin=begin
if stage=='before_receipt_commit':
    original=ledger.append
    def append(event):
        if event.kind is EventKind.EXIT_ATTEMPT and event.payload['state']=='CONFIRMED':os._exit(23)
        return original(event)
    ledger.append=append
if stage=='after_receipt_commit':protection.close_confirmed=lambda position_id:os._exit(23)
router.apply_exits('probe','TEST',D('89'),D('90'),now_ms=1)
raise AssertionError('crash injection not reached')
'''
    result = subprocess.run([sys.executable,"-c",script,str(database),str(effect),stage],
        cwd=Path(__file__).resolve().parents[2], text=True, capture_output=True)
    assert result.returncode == 23, result.stderr
    assert (len(effect.read_text().splitlines()) if effect.exists() else 0) == effects
    ledger, adapter = Ledger(database), CloseProbe()
    cold = build(ledger, adapter)
    assert mark(cold, 2) == [] and adapter.calls == 0
    assert ledger.verify_chain()[0]
    assert ledger.count(EventKind.EXECUTION_RECEIPT) == (1 if stage == "after_receipt_commit" else 0)


def owner_fixture():
    from vati.execution.zse_ticket import OwnerTicketAdapter
    owner = OwnerTicketAdapter(equity=D("10000"), csd_verified=True)
    owner._positions["position"] = {"symbol":"TEST", "qty":D("10"), "entry":D("100"), "intent":"intent"}
    ledger = Ledger()
    router = build(ledger, owner)
    accepted = router.apply_preservation("zse", position_id="position", trade_intent_id="intent",
        action="FULL_CLOSE", reason="PROTECT", now_ms=1)
    return owner,ledger,router,accepted


def durable_confirmation(ledger, receipt, producer="vati-account-service"):
    ledger.append(make_event(EventKind.EXECUTION_RECEIPT, producer, receipt.__dict__,
        event_time_ms=2, received_time_ms=2, correlation_id=receipt.trade_intent_id))


def test_owner_sell_definition_is_durable_for_preservation_and_final_partial_keeps_protection():
    owner, ledger, router, accepted = owner_fixture()
    assert ledger.count(EventKind.OWNER_TICKET) == 1
    issued = next(ledger.iter(EventKind.OWNER_TICKET)).payload
    assert issued["ticket"] == accepted.broker_order_id and issued["position_id"] == "position"
    assert issued["qty"] == "10"
    confirmed = owner.confirm(accepted.broker_order_id, fill_price=D("89"), filled_qty=D("4"),
        contract_note_ref="fixture-native-note", now_ms=2)
    durable_confirmation(ledger, confirmed)
    assert router.confirm_owner_exit(confirmed, now_ms=2)
    assert router.exit_journal.pending("zse", "position") is None
    assert router.exit_journal.latest("zse", "position").payload["state"] == "PARTIAL_CONFIRMED"
    assert "position" in router.protection.rules and not router.protection.is_close_pending("position")
    # The first ticket is final, with a known residual. A distinct remaining
    # objective may create one new ticket; the first ticket is never replayed.
    another = router.apply_preservation("zse", position_id="position", trade_intent_id="intent",
        action="FULL_CLOSE", reason="PROTECT_REMAINDER", now_ms=3)
    assert another.broker_order_id != accepted.broker_order_id
    assert owner.tickets[another.broker_order_id].quantity_shares == D("6")


@pytest.mark.parametrize("fault", ["not_durable", "non_native", "wrong_ticket"])
def test_owner_assertion_cannot_settle_an_unbound_exit_ticket(fault):
    owner, ledger, router, accepted = owner_fixture()
    confirmed = owner.confirm(accepted.broker_order_id, fill_price=D("89"), filled_qty=D("10"),
        contract_note_ref="fixture-native-note", now_ms=2)
    if fault == "wrong_ticket":
        confirmed = replace(confirmed, broker_order_id="another-ticket").sealed()
    if fault != "not_durable":
        durable_confirmation(ledger, confirmed, "model-output" if fault == "non_native" else "vati-account-service")
    with pytest.raises(RouterError, match="binding"):
        router.confirm_owner_exit(confirmed, now_ms=2)
    assert router.exit_journal.pending("zse", "position") is not None
    assert "position" in router.protection.rules


def test_full_native_owner_confirmation_resolves_without_another_transport():
    owner, ledger, router, accepted = owner_fixture()
    confirmed = owner.confirm(accepted.broker_order_id, fill_price=D("89"), filled_qty=D("10"),
        contract_note_ref="fixture-native-note", now_ms=2)
    durable_confirmation(ledger, confirmed)
    assert router.confirm_owner_exit(confirmed, now_ms=2)
    assert router.exit_journal.pending("zse", "position") is None
    assert "position" not in router.protection.rules and not owner.positions()
    count = ledger.count()
    assert not router.confirm_owner_exit(confirmed, now_ms=3)
    assert ledger.count() == count


@pytest.mark.parametrize("runtime", ["account", "single_symbol"])
@pytest.mark.parametrize("price", [None, D("NaN"), D("Infinity")])
def test_missing_or_nonfinite_close_price_retains_entry_for_later_reconciliation(eurusd, runtime, price):
    from types import SimpleNamespace
    from vati.app.trade_lifecycle import AccountTradeLifecycle
    from vati.app.cycle import DecisionCycle
    from vati.execution.paper import PaperAdapter
    from vati.intelligence.events import EventMatrix
    from vati.market_data import FX_CALENDAR
    from test_backtest_runner_cli import fx_cfg, fx_engine
    ledger, adapter = Ledger(), PaperAdapter()
    if runtime == "account":
        obj = AccountTradeLifecycle(ledger=ledger, adapter=adapter, router=SimpleNamespace(),
            protection=ProtectionManager(), contracts={"EURUSD":eurusd}, engines_by_symbol={}, modelled_costs={})
        rows = obj.entries
    else:
        cfg = fx_cfg(eurusd)
        obj = DecisionCycle(cfg=cfg, adapter=adapter, ledger=ledger, engine=fx_engine(cfg),
            cost_fn=lambda state:D("0.0001"), calendar=FX_CALENDAR, events=EventMatrix())
        rows = obj._entries
    rows["reconcile"] = {"symbol":"EURUSD", "entry":D("1.1000"), "stop":D("1.0990"),
        "direction":Direction.LONG, "quantity":D("0.1"), "strategy_id":"test", "decision_price":D("1.1000")}
    obj._on_close("reconcile", price, "VENUE_STOP", 1)
    assert "reconcile" in rows and ledger.count(EventKind.TRADE_REVIEW) == 0
    assert any(e.payload.get("event") == "CLOSE_PRICE_UNRESOLVED" for e in ledger.iter(EventKind.SESSION))
    obj._on_close("reconcile", D("1.1001"), "VENUE_RECONCILED", 2)
    assert "reconcile" not in rows and ledger.count(EventKind.TRADE_REVIEW) == 1


def test_restart_preserves_uncertainty_even_with_a_fresh_protection_projection(tmp_path):
    path = tmp_path/"uncertain.sqlite"
    adapter = CloseProbe()
    original = build(Ledger(path), adapter)
    mark(original)
    cold = build(Ledger(path), adapter)
    assert mark(cold, 2) == [] and adapter.calls == 1
    assert KillSwitchTrigger.RECONCILIATION_FAILURE in cold.kill.active
    assert cold.protection.is_close_pending("position")


def test_upgrade_does_not_erase_a_legacy_unknown_close_receipt():
    ledger, adapter = Ledger(), CloseProbe()
    receipt = adapter.close("position", None, now_ms=1, reason="OLD_UNKNOWN")
    ledger.append(make_event(EventKind.EXECUTION_RECEIPT, "vati-execution-router",
        {**receipt.__dict__, "exit_action":"CLOSE", "exit_reason":"OLD_UNKNOWN"},
        event_time_ms=1, received_time_ms=1, correlation_id="intent"))
    cold = build(ledger, adapter)
    assert mark(cold, 2) == [] and adapter.calls == 1
    with pytest.raises(RouterError, match="reconcil"):
        cold.apply_preservation("probe", position_id="position", trade_intent_id="intent",
            action="FULL_CLOSE", reason="NO_BLIND_RETRY", now_ms=3)
    assert ledger.count(EventKind.EXIT_ATTEMPT) == 0
    assert KillSwitchTrigger.RECONCILIATION_FAILURE in cold.kill.active


def test_an_unknown_partial_preservation_close_blocks_another_close_request():
    adapter = CloseProbe()
    router = build(Ledger(), adapter)
    first = router.apply_preservation("probe", position_id="position", trade_intent_id="intent",
        action="PARTIAL_CLOSE", quantity=D("1"), reason="REDUCE", now_ms=1)
    assert first.status == "UNKNOWN"
    with pytest.raises(RouterError, match="reconcil"):
        router.apply_preservation("probe", position_id="position", trade_intent_id="intent",
            action="FULL_CLOSE", reason="PROTECT", now_ms=2)
    assert adapter.calls == 1


def test_definitive_zero_fill_refusal_allows_a_later_protective_retry():
    adapter = CloseProbe(status="REJECTED")
    router = build(Ledger(), adapter)
    assert mark(router)[0].status == "REJECTED"
    assert not router.protection.is_close_pending("position")
    mark(router, 2)
    assert adapter.calls == 2


@pytest.mark.parametrize("patch", [dict(status="FILLED"), dict(status="CANCELLED",filled_qty=D("1")),
    dict(status="FILLED",filled_qty=D("1"),average_fill=D("99"),broker_position_id="another")])
def test_incomplete_or_wrong_position_receipt_cannot_remove_protection(patch):
    class Malformed(CloseProbe):
        def close(self, *args, **kwargs):
            return replace(super().close(*args, **kwargs), **patch).sealed()
    adapter = Malformed()
    router = build(Ledger(), adapter)
    with pytest.raises(RouterError, match="reconcil"):
        mark(router)
    assert "position" in router.protection.rules
    assert router.protection.is_close_pending("position")
    assert mark(router, 2) == [] and adapter.calls == 1
