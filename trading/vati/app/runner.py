"""Live/paper session runner (Rev 2 §44 startup, §61 loop). Startup verifies
account, reconciles ledger vs venue and only then permits new orders; every
bar runs the same DecisionCycle as the backtest."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Iterable, Optional

from vati.app.cycle import CycleResult, DecisionCycle, SessionConfig
from vati.authority import OwnerAuthorityVerifier
from vati.core.events import EventKind, make_event
from vati.execution.reconciliation import LedgerPosition, ReconciliationResult, reconcile
from vati.market_data.bars import Bar
from vati.risk.contracts import KillSwitchTrigger

ZERO = Decimal("0")


@dataclass
class SessionRunner:
    cycle: DecisionCycle
    started: bool = False
    permit_new_orders: bool = False
    startup_report: Optional[ReconciliationResult] = None
    #: P0-TRADE-001. Defaulted to a verifier with no keys, which refuses everything: a
    #: runner nobody gave the owner's key to cannot be halted by a stranger's string, and
    #: the owner's genuine halt still works on a host that was set up.
    authority: OwnerAuthorityVerifier = field(default_factory=OwnerAuthorityVerifier)

    def startup(self, *, now_ms: int, ledger_positions: Iterable[LedgerPosition] = ()) -> ReconciliationResult:
        c = self.cycle
        acct = c.adapter.sync_account()
        hb = c.adapter.heartbeat(now_ms=now_ms)
        if not acct.verified:
            c.kill.trip(KillSwitchTrigger.UNAUTHORIZED_ACCOUNT, now_ms)
        if not hb.connected:
            c.kill.trip(KillSwitchTrigger.VENUE_DISCONNECT, now_ms)
        rep = reconcile(ledger_positions, c.adapter.positions(), account_verified=acct.verified)
        if not rep.permit_new_orders:
            c.kill.trip(KillSwitchTrigger.RECONCILIATION_FAILURE, now_ms)
        c.ledger.append(make_event(EventKind.RECONCILIATION_RESULT, "vati-runner", {"counts": rep.counts(), "permit_new_orders": rep.permit_new_orders, "account_verified": acct.verified, "kill": sorted(t.value for t in c.kill.active)},
                                   event_time_ms=now_ms, received_time_ms=now_ms, correlation_id=c.cfg.session_id))
        self.started, self.permit_new_orders, self.startup_report = True, rep.permit_new_orders and not c.kill.halted, rep
        c.ledger.append(make_event(EventKind.SESSION, "vati-runner", {"event": "STARTED", "permit_new_orders": self.permit_new_orders, "mode": c.mandate.mode.value}, event_time_ms=now_ms, received_time_ms=now_ms, correlation_id=c.cfg.session_id))
        return rep

    def on_bar(self, history: list[Bar], *, now_ms: int, last_quote_ms: int) -> CycleResult:
        if not self.started:
            raise RuntimeError("startup() first")
        bar = history[-1]
        half = self.cycle.cfg.contract.tick_size
        for px in (bar.open, bar.low, bar.high, bar.close):
            self.cycle.mark(px - half, px + half, now_ms=now_ms)
        if not self.permit_new_orders or self.cycle.kill.halted:
            return CycleResult(bar.end_ms, "", "NEW_TRADES_BLOCKED", "reconciliation/kill switch")
        return self.cycle.step(history, now_ms=now_ms, last_quote_ms=last_quote_ms)

    def owner_halt(self, *, now_ms: int, owner_signature_ref: str) -> None:
        """P0-TRADE-001 — "owner halt" used to mean "somebody sent a non-empty string"."""
        verified = self.authority.verify(
            owner_signature_ref,
            act="owner-halt",
            subject=self.cycle.cfg.session_id,
            now_unix=now_ms // 1000,
        )
        owner_signature_ref = verified.ref
        self.cycle.kill.trip(KillSwitchTrigger.OWNER_HALT, now_ms)
        self.permit_new_orders = False
        self.cycle.ledger.append(make_event(EventKind.KILL_SWITCH, "vati-runner", {"trigger": "OWNER_HALT", "sig": owner_signature_ref}, event_time_ms=now_ms, received_time_ms=now_ms, correlation_id=self.cycle.cfg.session_id))
