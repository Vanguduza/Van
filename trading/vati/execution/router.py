"""Execution Router (Rev 2 §29, Rev 2.1 §E.2 plane 3): the only order sender.

Refuses anything without a sealed APPROVED/REDUCED RiskDecision whose hash it
can recompute for this exact intent; refuses replayed idempotency keys, halted
kill switches, non-order-sending modes, and venues without a heartbeat. If a
venue stop is not confirmed on a filled order it flattens immediately and trips
STOP_REJECTED. Every step is a ledger event."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict
from decimal import Decimal
from typing import Callable, Optional

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.core.ledger import Ledger
from vati.execution.base import ExecutionReceipt, OrderCommand, StopMode, VenueAdapter
from vati.execution.exit_journal import ExitJournal, ExitPending
from vati.execution.protection import ProtectionManager
from vati.execution.policy_templates import DO_NOT_EXECUTE, LIMIT_AT_TOUCH, entry_compatible, slippage_bound_in_price, template as execution_template
from vati.execution.pretrade import MarketReference, PreTradeControls
from vati.execution.route_registry import RouteRegistry
from vati.execution.style_selector import (
    ExecutionStyleSelector, LiquidityView, StyleRefused, Urgency,
)
from vati.observability import metrics
from vati.risk.authority import Decision, RiskDecision, RiskAuthority
from vati.risk.contracts import KillSwitchTrigger, LossModel, TradeIntent
from vati.risk.governor import KillSwitch
from vati.risk.mandate import TradingMandate
from vati.risk.serde import intent_binding_hash, mandate_binding_hash, RISK_APPROVAL_SCHEMA_VERSION

ZERO = Decimal("0")


class RouterError(RuntimeError):
    pass


class ExitInFlight(RouterError):
    pass


def recompute_decision_hash(d: RiskDecision) -> str:
    body = d.to_dict(); body.pop("decision_hash", None)
    return canonical_hash(body)


def resolve_execution_policy(decision, *, entry_type: str, max_slippage: Optional[Decimal]):
    """Validate a sealed ExecutionPolicyDecision and return bounded router inputs."""
    if decision is None:
        return entry_type, max_slippage
    as_dict = getattr(decision, "as_dict", None)
    decision_hash = getattr(decision, "decision_hash", "")
    if not callable(as_dict) or not decision_hash or canonical_hash(as_dict()) != decision_hash:
        raise RouterError("execution policy decision seal is invalid")
    t = execution_template(getattr(decision, "template_id", ""))
    if t.template_id == DO_NOT_EXECUTE or not t.allowed_entry_types:
        raise RouterError(f"execution policy refused order: {t.template_id}")
    chosen_entry = getattr(decision, "entry_type", None) or t.allowed_entry_types[0]
    if chosen_entry not in t.allowed_entry_types:
        raise RouterError(
            f"execution policy entry type {chosen_entry!r} is outside template {t.template_id}")
    if entry_type and not entry_compatible(entry_type, chosen_entry):
        # P1-TRADE-EXEC-004: the strategy's entry type is binding; a STOP entry is never
        # quietly turned into a LIMIT (or anything else).
        raise RouterError(
            f"ENTRY_TYPE_NOT_PERMITTED: strategy requested {entry_type}, template {t.template_id} executes {chosen_entry}")
    bounded_slippage = t.max_slippage
    if max_slippage is not None:
        bounded_slippage = min(max_slippage, t.max_slippage)
    return chosen_entry, bounded_slippage


class ExecutionRouter:
    def __init__(self, *, ledger: Ledger, adapters: dict[str, VenueAdapter], kill_switch: KillSwitch, protection: ProtectionManager, producer: str = "vati-execution-router",
                 lease_fence: Optional[Callable[[Optional[int]], bool]] = None,
                 lease_submission_guard: Optional[Callable[[Optional[int]], object]] = None,
                 route_registry: Optional[RouteRegistry] = None,
                 pretrade_controls: Optional[PreTradeControls] = None,
                 style_selector: Optional[ExecutionStyleSelector] = None,
                 enforce_rev51_controls: bool = False,
                 clock: Optional[Callable[[], int]] = None,
                 current_risk_facts_provider: Optional[Callable] = None,
                 current_risk_authority: Optional[RiskAuthority] = None) -> None:
        self.ledger, self.adapters, self.kill, self.protection, self.producer = ledger, adapters, kill_switch, protection, producer
        self.lease_fence = lease_fence
        self.lease_submission_guard = lease_submission_guard
        self.route_registry = route_registry
        self.pretrade_controls = pretrade_controls
        self.style_selector = style_selector
        self.enforce_rev51_controls = enforce_rev51_controls
        self.clock = clock
        if (current_risk_facts_provider is None) != (current_risk_authority is None):
            raise RouterError('current risk requires both a facts provider and RiskAuthority')
        if current_risk_authority is not None and (
            not callable(current_risk_facts_provider) or not isinstance(current_risk_authority,RiskAuthority)):
            raise RouterError('current risk provider or authority is invalid')
        self.current_risk_facts_provider = current_risk_facts_provider
        self.current_risk_authority = current_risk_authority
        if enforce_rev51_controls and (
            route_registry is None or pretrade_controls is None or style_selector is None
        ):
            raise RouterError(
                "Rev 5.1 execution controls are mandatory when enforce_rev51_controls=True")
        if pretrade_controls is not None and route_registry is not None and pretrade_controls.routes is not route_registry:
            raise RouterError("pre-trade controls and router must share the same RouteRegistry")
        self._seen: set[str] = {e.payload["idempotency_key"] for e in ledger.iter(EventKind.ORDER_COMMAND)}
        self.exit_journal = ExitJournal(ledger, producer)
        for pending in self.exit_journal.unresolved():
            if pending.payload.get("state", "UNKNOWN") != "ACCEPTED":
                self.kill.trip(KillSwitchTrigger.RECONCILIATION_FAILURE, pending.received_time_ms)

    def _log(self, kind: EventKind, payload: dict, *, now_ms: int, corr: str, decision_time: Optional[int] = None) -> str:
        event = make_event(kind, self.producer, payload, event_time_ms=now_ms, received_time_ms=now_ms, decision_time_ms=decision_time, correlation_id=corr)
        self.ledger.append(event)
        return event.hash

    def _dispatch_time(self, mandate: TradingMandate, *, now_ms: int) -> int:
        # Native service builders supply their current clock. Isolated replay
        # callers supply their explicit event clock through now_ms.
        observed=self.clock() if self.clock is not None else now_ms
        if type(observed) is not int or type(now_ms) is not int or observed < 0 or observed < now_ms:
            raise RouterError('mandate dispatch clock unavailable or moved backwards')
        if not mandate.signed_at_unix*1000 <= observed < mandate.expires_at_unix*1000:
            raise RouterError('mandate is outside its current validity interval; re-admission required')
        if not mandate.owner_keys_current():
            raise RouterError('current mandate owner signer is unavailable; re-admission required')
        return observed

    def _current_account_risk(self, intent, decision, mandate, command, adapter, *, now_ms, market_reference):
        from vati.execution.paper import PaperAdapter
        from vati.execution.zse_ticket import OwnerTicketAdapter
        from vati.execution.risk_refresh import CurrentRiskFacts
        from vati.risk.contracts import RiskSnapshot
        from vati.risk.serde import snapshot_to_dict
        if self.current_risk_facts_provider is None:
            if not isinstance(adapter,(PaperAdapter,OwnerTicketAdapter)):
                raise RouterError('current native account risk facts unavailable; not dispatched')
            return None
        if mandate_binding_hash(self.current_risk_authority.mandate)!=mandate_binding_hash(mandate):
            raise RouterError('current RiskAuthority differs from the exact mandate')
        try:
            facts=self.current_risk_facts_provider(intent,now_ms=now_ms,market_reference=market_reference)
        except Exception as exc:
            raise RouterError('current account risk read unavailable: '+type(exc).__name__) from None
        observed=self._dispatch_time(mandate,now_ms=now_ms)
        if (type(facts) is not CurrentRiskFacts or type(facts.snapshot) is not RiskSnapshot
            or type(facts.observed_at_ms) is not int or not now_ms<=facts.observed_at_ms<=observed
            or facts.snapshot.now_unix!=facts.observed_at_ms//1000):
            raise RouterError('current account risk facts have no valid original observation clock')
        # The original authority already consumed the proposal key. A separate
        # calculator with the same exact policy rechecks facts; it cannot reset
        # that original key or grant a second native submission.
        calculator=RiskAuthority(self.current_risk_authority.mandate,
            ceilings=self.current_risk_authority.ceilings,
            conformal_gate=self.current_risk_authority.conformal_gate)
        fresh=calculator.evaluate_safe(intent,facts.snapshot)
        if (fresh.decision_hash!=recompute_decision_hash(fresh)
            or fresh.intent_hash!=decision.intent_hash or fresh.mandate_hash!=decision.mandate_hash):
            raise RouterError('current RiskAuthority result is not bound to the exact intent and mandate')
        fits=(fresh.decision in (Decision.APPROVED,Decision.REDUCED) and fresh.approved_size.is_finite()
            and command.quantity<=fresh.approved_size)
        reason=(fresh.reason_code if fresh.decision is Decision.REJECTED else
            'CURRENT_COMMAND_EXCEEDS_RISK' if not fits else fresh.reason_code)
        detail=(fresh.reason_detail if fresh.decision is Decision.REJECTED or fits else
            f'current size limit {fresh.approved_size} is below original command {command.quantity}')
        try:
            current_snapshot=snapshot_to_dict(facts.snapshot)
        except Exception:
            raise RouterError('current account risk facts cannot be journaled; not dispatched') from None
        try:
            evidence=make_event(EventKind.RISK_REVALIDATION,self.producer,{'schema':'vati.current-account-risk/1',
                'account_alias':intent.account_alias,'original_decision_hash':decision.decision_hash,
                'original_command_hash':command.command_hash,'observed_at_ms':facts.observed_at_ms,
                'original_command_quantity':str(command.quantity),'state':'SUFFICIENT' if fits else 'REFUSED',
                'reason_code':reason,'reason_detail':detail,
                'snapshot':current_snapshot,'decision':fresh.to_dict(),
                'execution_authority':False},event_time_ms=observed,received_time_ms=observed,
                correlation_id=intent.trade_intent_id,decision_time_ms=now_ms)
            # No provider read belongs in this short journal transaction. An
            # identical retry after a lost commit ACK retains first availability.
            with self.ledger.atomic():
                if not self.ledger.verify_incremental()[0]:raise RouterError('risk journal invalid')
                previous=list(self.ledger.iter(EventKind.RISK_REVALIDATION,correlation_id=intent.trade_intent_id))
                if any(e.hash!=canonical_hash(e.body()) for e in previous):raise RouterError('risk evidence invalid')
                if not any(e.hash==evidence.hash for e in previous):self.ledger.append(evidence)
            ref=evidence.hash
        except Exception:
            raise RouterError('current account risk evidence not committed; not dispatched') from None
        if fresh.decision not in (Decision.APPROVED,Decision.REDUCED):
            raise RouterError('current account risk refused '+fresh.reason_code+': '+fresh.reason_detail)
        if not fresh.approved_size.is_finite() or command.quantity>fresh.approved_size:
            raise RouterError('current account risk budget is below the original command; re-evaluation required')
        return ref

    def _current_command_controls(self, intent, decision, command, *, market_reference, decision_time_ms, now_ms):
        if not self.enforce_rev51_controls:
            return
        current_mark=market_reference.aged(observed_at_ms=decision_time_ms,now_ms=now_ms) if market_reference is not None else None
        result=self.pretrade_controls.check(intent=intent,decision=decision,mark=current_mark,now_ms=now_ms)
        if not result.passed or result.quantised is None:
            raise RouterError(f"pre-trade refused {result.reason_code}: {result.reason_detail}")
        current=result.quantised
        if (current.quantity!=command.quantity or (current.entry_price or intent.entry)!=command.entry_price
            or (current.stop_price if intent.stop is not None else None)!=command.protective_stop):
            raise RouterError('current venue quantisation changed; re-evaluation required')

    def _uncertain_exit(self, position_id: str, *, now_ms: int, request_ref: str) -> None:
        if position_id in self.protection.rules:
            self.protection.mark_close_pending(position_id)
        if KillSwitchTrigger.RECONCILIATION_FAILURE not in self.kill.active:
            self.kill.trip(KillSwitchTrigger.RECONCILIATION_FAILURE, now_ms)
            self._log(EventKind.KILL_SWITCH, {"trigger": KillSwitchTrigger.RECONCILIATION_FAILURE.value,
                "reason": "protective exit outcome unresolved", "exit_request_ref": request_ref},
                now_ms=now_ms, corr=position_id)

    def _send_close(self, venue: str, *, position_id: str, trade_intent_id: str,
                    quantity: Optional[Decimal], action: str, reason: str, now_ms: int) -> ExecutionReceipt:
        try:
            request = self.exit_journal.begin(venue=venue, position_id=position_id,
                trade_intent_id=trade_intent_id, action=action, quantity=quantity, reason=reason, now_ms=now_ms)
        except ExitPending as exc:
            raise ExitInFlight(str(exc)) from exc
        if position_id in self.protection.rules:
            self.protection.mark_close_pending(position_id)
        try:
            receipt = self.adapters[venue].close(position_id, quantity, now_ms=now_ms, reason=reason)
            state = self.exit_journal.receipt_state(receipt, venue=venue,
                position_id=position_id, trade_intent_id=trade_intent_id)
            ticket = None
            if state == "ACCEPTED" and receipt.execution_channel == "OWNER_TICKET":
                ticket = getattr(self.adapters[venue], "tickets", {}).get(receipt.broker_order_id)
                if ticket is None or ticket.side != "SELL" or ticket.source_position_id != position_id:
                    state = "UNKNOWN"
            with self.ledger.atomic():
                receipt_ref = self._log(EventKind.EXECUTION_RECEIPT,
                    {**{k:(v.value if hasattr(v, "value") else v) for k,v in asdict(receipt).items()},
                     "exit_action": "CLOSE", "exit_reason": reason,
                     "preservation_action": action, "exit_request_ref": request.hash},
                    now_ms=now_ms, corr=receipt.trade_intent_id or trade_intent_id or position_id)
                self.exit_journal.finish(request, state=state, receipt_event_ref=receipt_ref, now_ms=now_ms)
                if state == "ACCEPTED" and ticket is not None:
                    self._log(EventKind.OWNER_TICKET, {"ticket": receipt.broker_order_id,
                        "symbol": ticket.symbol, "side": "SELL", "position_id": position_id,
                        "trade_intent_id": receipt.trade_intent_id, "exit_reason": reason,
                        "qty": str(ticket.quantity_shares), "limit_price": str(ticket.limit_price),
                        "exit_request_ref": request.hash}, now_ms=now_ms,
                        corr=receipt.trade_intent_id or trade_intent_id or position_id)
        except BaseException:
            # The request is already durable. Even a missing response or a
            # receipt-persistence failure cannot authorize another send.
            self._uncertain_exit(position_id, now_ms=now_ms, request_ref=request.hash)
            raise
        if state == "UNKNOWN":
            self._uncertain_exit(position_id, now_ms=now_ms, request_ref=request.hash)
            if receipt.status not in {"UNKNOWN", "PARTIAL"}:
                raise RouterError("protective exit evidence incomplete or inconsistent; reconcile before retry")
        elif state == "CONFIRMED":
            if action == "FULL_CLOSE":
                self.protection.close_confirmed(position_id)
            else:
                self.protection.close_failed(position_id)
        elif state == "NOT_EXECUTED":
            self.protection.close_failed(position_id)
        return receipt

    def confirm_owner_exit(self, receipt: ExecutionReceipt, *, now_ms: int) -> bool:
        """Fold a durable native owner-ticket confirmation of this exact attempt.

        AccountService verifies/adopts the original owner confirmation and
        persists its receipt before this call. A different ticket, free-form
        assertion or derived producer cannot settle the pending request.
        """
        pending = self.exit_journal.pending(receipt.venue, receipt.broker_position_id)
        if pending is None:
            return False  # legacy/non-journal owner recovery retains its existing path
        request_ref = pending.payload.get("request_ref", pending.hash)
        request = next((e for e in self.exit_journal._events(receipt.venue, receipt.broker_position_id)
                        if e.hash == request_ref), None)
        issued = None
        confirmed = None
        fields = asdict(receipt)
        for event in self.ledger.iter(EventKind.EXECUTION_RECEIPT):
            if event.hash != canonical_hash(event.body()):
                continue
            if event.hash == pending.payload.get("receipt_event_ref"):
                issued = event
            if (event.producer == "vati-account-service" and event.payload.get("receipt_hash") == receipt.receipt_hash
                and canonical_hash({k:event.payload.get(k) for k in fields}) == canonical_hash(fields)):
                confirmed = event
        if (request is None or issued is None or confirmed is None
            or issued.producer != self.producer or issued.payload.get("execution_channel") != "OWNER_TICKET"
            or issued.payload.get("status") != "ACCEPTED" or not receipt.broker_order_id
            or issued.payload.get("broker_order_id") != receipt.broker_order_id
            or receipt.execution_channel != "OWNER_TICKET"
            or self.exit_journal.receipt_state(receipt, venue=receipt.venue, position_id=receipt.broker_position_id,
                trade_intent_id=request.payload["trade_intent_id"]) != "CONFIRMED"):
            raise RouterError("owner exit confirmation lacks its native request/ticket/receipt binding; reconcile")
        # The owner-ticket adapter's position projection has just applied this
        # exact confirmation. A final partial ticket leaves residual protection.
        remaining = [p for p in self.adapters[receipt.venue].positions() if p.position_id == receipt.broker_position_id]
        with self.ledger.atomic():
            self.exit_journal.finish(request, state="PARTIAL_CONFIRMED" if remaining else "CONFIRMED",
                receipt_event_ref=confirmed.hash, now_ms=now_ms)
        if remaining:
            self.protection.close_failed(receipt.broker_position_id)
        else:
            self.protection.close_confirmed(receipt.broker_position_id)
        return True

    def execute(self, intent: TradeIntent, decision: RiskDecision, mandate: TradingMandate, *, now_ms: int, stop_mode: StopMode = StopMode.VENUE,
                targets: tuple[Decimal, ...] = (), time_in_force: str = "DAY", entry_type: str = "LIMIT", max_slippage: Optional[Decimal] = None,
                lease_epoch: Optional[int] = None, execution_policy_decision=None,
                market_reference: Optional[MarketReference] = None,
                liquidity: Optional[LiquidityView] = None,
                urgency: Urgency = Urgency.NORMAL) -> ExecutionReceipt:
        corr = intent.trade_intent_id
        for pending in self.exit_journal.unresolved():
            if pending.payload.get("state", "UNKNOWN") != "ACCEPTED":
                self._uncertain_exit(pending.payload.get("position_id", pending.payload.get("broker_position_id")), now_ms=now_ms,
                    request_ref=pending.payload.get("request_ref", pending.hash))
        if not isinstance(urgency, Urgency):
            raise RouterError("execution urgency must be a registered deterministic state")
        if urgency is Urgency.IMMEDIATE:
            raise RouterError("protective-exit urgency cannot authorize a new entry; use the protective reduction path")
        # --- gate chain (fail closed, first failure names the reason) ---
        if self.lease_fence is not None and not self.lease_fence(lease_epoch):
            raise RouterError(f"account runtime lease fence refused epoch {lease_epoch!r}")
        if self.kill.halted:
            raise RouterError(f"kill switch active: {sorted(t.value for t in self.kill.active)}")
        if decision.trade_intent_id != intent.trade_intent_id:
            raise RouterError("decision does not belong to this intent")
        if decision.decision not in (Decision.APPROVED, Decision.REDUCED):
            raise RouterError(f"decision is {decision.decision.value}")
        if recompute_decision_hash(decision) != decision.decision_hash:
            raise RouterError("decision hash does not recompute; refusing")
        if getattr(decision, "approval_schema_version", None) != RISK_APPROVAL_SCHEMA_VERSION or not getattr(decision, "intent_hash", None):
            raise RouterError("risk approval lacks exact intent binding; re-evaluation required")
        if decision.intent_hash != intent_binding_hash(intent):
            raise RouterError("risk approval does not match the exact trade intent; re-evaluation required")
        if decision.mandate_id != mandate.mandate_id or decision.mandate_version != mandate.version:
            raise RouterError("decision was made under a different mandate")
        if not mandate.sends_orders():
            raise RouterError(f"mode {mandate.mode.value} does not send orders")
        if getattr(decision, "mandate_hash", None) != mandate_binding_hash(mandate):
            raise RouterError("risk approval does not match the current mandate; re-evaluation required")
        if not mandate.authority_matches_policy():
            raise RouterError("current mandate lacks its original policy-bound owner grant; re-admission required")
        self._dispatch_time(mandate,now_ms=now_ms)
        if intent.idempotency_key in self._seen:
            raise RouterError("duplicate idempotency key")
        adapter = self.adapters.get(intent.venue)
        if adapter is None:
            raise RouterError(f"no adapter for venue {intent.venue}")
        from vati.execution.paper import PaperAdapter
        # Legacy isolated simulation can represent a caller's chosen venue;
        # native and owner-ticket targets must be bound before any provider I/O.
        if not isinstance(adapter, PaperAdapter) and (
            getattr(adapter, 'account_alias', None) != intent.account_alias
            or getattr(adapter, 'venue', None) != intent.venue):
            raise RouterError('execution adapter target differs from the intent account or venue')
        hb = adapter.heartbeat(now_ms=now_ms)
        if not hb.connected:
            self.kill.trip(KillSwitchTrigger.VENUE_DISCONNECT, now_ms)
            self._log(EventKind.KILL_SWITCH, {"trigger": "VENUE_DISCONNECT", "venue": intent.venue}, now_ms=now_ms, corr=corr)
            raise RouterError("venue heartbeat failed; kill switch tripped")

        # Rev 5.1 G5b/G6. In production these controls live *inside* the only
        # order sender so no caller can construct a broker-bound command around them.
        quantity = decision.approved_size
        command_entry = intent.entry
        command_stop = intent.stop
        if self.enforce_rev51_controls:
            assert self.route_registry is not None
            assert self.pretrade_controls is not None
            assert self.style_selector is not None
            pretrade = self.pretrade_controls.check(
                intent=intent, decision=decision, mark=market_reference, now_ms=now_ms)
            if not pretrade.passed or pretrade.quantised is None:
                raise RouterError(
                    f"pre-trade refused {pretrade.reason_code}: {pretrade.reason_detail}")
            quantised = pretrade.quantised
            quantity = quantised.quantity
            command_entry = quantised.entry_price or intent.entry
            command_stop = quantised.stop_price if intent.stop is not None else None
            route = self.route_registry.resolve(
                intent.account_alias, intent.symbol, now_ms=now_ms, direction=intent.direction)
            requested_entry = entry_type
            entry_type, max_slippage = resolve_execution_policy(
                execution_policy_decision, entry_type=entry_type, max_slippage=max_slippage)
            try:
                style = self.style_selector.select(
                    trade_intent_id=intent.trade_intent_id,
                    policy_decision=execution_policy_decision,
                    route=route,
                    quantity=quantity,
                    liquidity=liquidity or LiquidityView(),
                    urgency=urgency,
                    now_ms=now_ms,
                )
            except StyleRefused as exc:
                raise RouterError(f"execution style refused: {exc}") from exc
            if not style.seal_ok():
                raise RouterError("execution style seal is invalid")
            if style.total_quantity != quantity:
                raise RouterError("execution style quantity differs from the approved quantised quantity")
            if style.slices != 1:
                # The current router has one broker submission per intent. Silently
                # ignoring a multi-slice plan would violate the selected style; refuse
                # until a child-command protocol is explicitly admitted.
                raise RouterError(
                    f"execution style requires {style.slices} slices; single-command router refuses")
            if not entry_compatible(requested_entry, style.entry_type):
                raise RouterError(
                    f"ENTRY_TYPE_NOT_PERMITTED: strategy requested {requested_entry}, style chose {style.entry_type}")
            entry_type = style.entry_type
            max_slippage = (
                style.max_slippage if max_slippage is None
                else min(max_slippage, style.max_slippage)
            )
        else:
            entry_type, max_slippage = resolve_execution_policy(
                execution_policy_decision, entry_type=entry_type, max_slippage=max_slippage)

        # Venue capability (P1-TRADE-EXEC-004). A venue that declares what it can execute
        # is held to it: an unsupported type is refused, not sent as something else. The
        # one explicit, logged exception is an at-touch LIMIT on a venue that can only
        # send market orders — that is what such a venue already did silently, and the
        # slippage cap still bounds it.
        requested_entry_type = entry_type
        substituted = False
        supported = getattr(adapter, "supported_entry_types", None)
        if supported is not None and entry_type not in supported:
            template_id = getattr(execution_policy_decision, "template_id", LIMIT_AT_TOUCH) if execution_policy_decision is not None else LIMIT_AT_TOUCH
            if entry_type == "LIMIT" and "MARKET" in supported and template_id == LIMIT_AT_TOUCH:
                entry_type, substituted = "MARKET", True
            else:
                raise RouterError(
                    f"ENTRY_TYPE_NOT_SUPPORTED: venue {intent.venue} cannot execute {entry_type} (supports {sorted(supported)})")

        # Template, style and caller bounds are fractions of price (policy_templates 1.1.0);
        # the order command and every adapter work in price units of this instrument.
        if max_slippage is not None:
            max_slippage = slippage_bound_in_price(max_slippage, command_entry)

        if execution_policy_decision is not None:
            self._log(
                EventKind.EXECUTION_POLICY_DECISION,
                execution_policy_decision.as_dict() | {
                    "decision_hash": execution_policy_decision.decision_hash},
                now_ms=now_ms, corr=corr, decision_time=now_ms,
            )

        loss_model = LossModel.ILLIQUID_EQUITY if intent.venue in ("zse", "vfex") else (LossModel.FULL_STAKE if intent.stake is not None and intent.stop is None else LossModel.STOP_DISTANCE)
        if loss_model is LossModel.STOP_DISTANCE and command_stop is None:
            raise RouterError("stop-distance order without protective stop")
        from vati.execution.mt5_bridge import Mt5BridgeAdapter
        from vati.execution.mt5_pull import Mt5PullAdapter
        from vati.execution.ctrader.adapter import CtraderAdapter
        from vati.execution.deriv import DerivAdapter
        native_deadline = mandate.expires_at_unix*1000 if isinstance(adapter,(Mt5BridgeAdapter,Mt5PullAdapter,CtraderAdapter,DerivAdapter)) else None
        if native_deadline is not None and market_reference is not None:
            if (type(market_reference.mark_age_ms) is not int or type(market_reference.max_mark_age_ms) is not int
                or not 0<=market_reference.mark_age_ms<=market_reference.max_mark_age_ms):
                raise RouterError('native entry quote lifetime unavailable; not dispatched')
            # Quote freshness includes its last valid millisecond. Bind an
            # exclusive deadline without renewing that original observation.
            native_deadline=min(native_deadline,now_ms+market_reference.max_mark_age_ms-market_reference.mark_age_ms+1)
        cmd = OrderCommand(
            trade_intent_id=intent.trade_intent_id,
            decision_hash=decision.decision_hash,
            idempotency_key=intent.idempotency_key,
            account_alias=intent.account_alias,
            venue=intent.venue,
            symbol=intent.symbol,
            direction=intent.direction,
            entry_type=entry_type,
            quantity=quantity,
            entry_price=command_entry,
            protective_stop=command_stop,
            stop_mode=StopMode.SOFTWARE if loss_model is LossModel.ILLIQUID_EQUITY else stop_mode,
            loss_model=loss_model,
            targets=targets,
            time_in_force=time_in_force,
            max_slippage=max_slippage,
            expires_at_ms=native_deadline,
            strategy_id=intent.strategy_id,
            strategy_version=intent.strategy_version,
            lease_epoch=lease_epoch,
        ).sealed()
        guard = (
            self.lease_submission_guard(lease_epoch)
            if self.lease_submission_guard is not None
            else nullcontext(True)
        )
        with guard as lease_guard_ok, mandate.owner_authority_submission_guard() as owner_key_ok:
            if not lease_guard_ok:
                raise RouterError(
                    f"account runtime submission guard refused epoch {lease_epoch!r}")
            if not owner_key_ok:
                raise RouterError('current mandate owner signer is unavailable; re-admission required')
            decision_time_ms=now_ms
            now_ms=self._dispatch_time(mandate,now_ms=now_ms)
            # Heartbeat and guard acquisition may have changed every mutable
            # refusal fact checked above. Recheck before consuming the key or
            # publishing a command; this never grants or increases risk.
            lease_current=self.lease_fence(lease_epoch) if self.lease_fence is not None else True
            now_ms=self._dispatch_time(mandate,now_ms=now_ms)
            if self.kill.halted:
                raise RouterError(f"kill switch active: {sorted(t.value for t in self.kill.active)}")
            if not lease_current:
                raise RouterError(f"account runtime lease fence refused epoch {lease_epoch!r}")
            self._current_command_controls(intent,decision,cmd,market_reference=market_reference,
                decision_time_ms=decision_time_ms,now_ms=now_ms)
            current_risk_ref=self._current_account_risk(intent,decision,mandate,cmd,adapter,now_ms=now_ms,
                market_reference=market_reference.aged(observed_at_ms=decision_time_ms,now_ms=now_ms) if market_reference is not None else None)
            if current_risk_ref is not None:
                # Account reads may block. Preserve refusal facts across that
                # read as well as across lease and signer acquisition.
                now_ms=self._dispatch_time(mandate,now_ms=now_ms)
                lease_current=self.lease_fence(lease_epoch) if self.lease_fence is not None else True
                now_ms=self._dispatch_time(mandate,now_ms=now_ms)
                if self.kill.halted:
                    raise RouterError(f"kill switch active: {sorted(t.value for t in self.kill.active)}")
                if not lease_current:
                    raise RouterError(f"account runtime lease fence refused epoch {lease_epoch!r}")
                self._current_command_controls(intent,decision,cmd,market_reference=market_reference,
                    decision_time_ms=decision_time_ms,now_ms=now_ms)
            self._seen.add(intent.idempotency_key)
            if self.enforce_rev51_controls:
                assert self.pretrade_controls is not None
                self.pretrade_controls.note_sent(
                    account_alias=intent.account_alias,
                    idempotency_key=intent.idempotency_key,
                    quantity=cmd.quantity,
                    now_ms=now_ms,
                )
            self._log(EventKind.ORDER_COMMAND, {**asdict(cmd), "direction": cmd.direction.value, "stop_mode": cmd.stop_mode.value, "loss_model": cmd.loss_model.value,
                                                **({'risk_revalidation_ref':current_risk_ref} if current_risk_ref is not None else {}),
                                                **({"requested_entry_type": requested_entry_type, "entry_type_substituted": True} if substituted else {})},
                      now_ms=now_ms, corr=corr, decision_time=decision_time_ms)
            metrics.inc("vati_orders_sent_total", venue=intent.venue)
            receipt = adapter.submit(cmd, now_ms=now_ms)
            self._log(EventKind.EXECUTION_RECEIPT, {k: (v.value if hasattr(v, "value") else v) for k, v in asdict(receipt).items()}, now_ms=now_ms, corr=corr)
            # --- protection ---
            if receipt.status in ("FILLED", "PARTIAL") and receipt.filled_qty > ZERO:
                if cmd.stop_mode is StopMode.VENUE and not receipt.protective_stop_confirmed:
                    self.kill.trip(KillSwitchTrigger.STOP_REJECTED, now_ms)
                    self._log(EventKind.KILL_SWITCH, {"trigger": "STOP_REJECTED", "position": receipt.broker_position_id}, now_ms=now_ms, corr=corr)
                    try:
                        flat = self._send_close(intent.venue, position_id=receipt.broker_position_id,
                            trade_intent_id=corr, quantity=None, action="FULL_CLOSE",
                            now_ms=now_ms, reason="STOP_REJECTED_FLATTEN")
                    except Exception as exc:
                        raise RouterError("protective stop not confirmed; protective recovery unresolved; reconcile before new risk") from exc
                    if flat.status in ("FILLED", "OWNER_EXECUTED", "BROKER_CONFIRMED"):
                        metrics.inc("vati_unprotected_flatten_total", venue=intent.venue)
                        raise RouterError("protective stop not confirmed; position flattened and kill switch tripped")
                    latest = self.exit_journal.latest(intent.venue, receipt.broker_position_id)
                    self._uncertain_exit(receipt.broker_position_id, now_ms=now_ms,
                        request_ref=latest.payload.get("request_ref", latest.hash))
                    raise RouterError("protective stop not confirmed; protective recovery unresolved; reconcile before new risk")
                if cmd.protective_stop is not None:
                    self.protection.register(receipt.broker_position_id, symbol=intent.symbol, direction=intent.direction, entry=receipt.average_fill or cmd.entry_price, stop=cmd.protective_stop,
                                             target=targets[0] if targets else None, opened_ms=now_ms, software_stop=(cmd.stop_mode is StopMode.SOFTWARE))
                metrics.inc("vati_fills_total", venue=intent.venue)
            elif receipt.status == "ACCEPTED" and receipt.execution_channel == "OWNER_TICKET":
                self._log(
                    EventKind.OWNER_TICKET,
                    {
                        "ticket": receipt.broker_order_id,
                        "symbol": intent.symbol,
                        "qty": str(decision.approved_size),
                        "side": "BUY",
                        "trade_intent_id": intent.trade_intent_id,
                        "limit_price": str(intent.entry),
                        "software_stop": (
                            str(intent.stop) if intent.stop is not None else None
                        ),
                    },
                    now_ms=now_ms, corr=corr,
                )
            elif receipt.status in ("REJECTED", "UNKNOWN"):
                metrics.inc("vati_rejects_total", venue=intent.venue)
            return receipt

    def apply_preservation(self, venue: str, *, position_id: str,
                           trade_intent_id: str, action: str,
                           now_ms: int, new_stop: Optional[Decimal] = None,
                           quantity: Optional[Decimal] = None,
                           reason: str = "REV51_PRESERVATION") -> Optional[ExecutionReceipt]:
        """Execute a deterministic preservation action through the router boundary.

        This path cannot add exposure. Software-stop tightening mutates only the
        local protection rule; venue stops and closes use the same adapter and
        receipt ledger as every other exit.
        """
        adapter = self.adapters[venue]
        if action == "TIGHTEN_STOP":
            if new_stop is None:
                raise RouterError("preservation tighten has no stop")
            old = self.protection.stop_of(position_id)
            self.protection.tighten(position_id, new_stop)
            if self.protection.is_software(position_id):
                return None
            try:
                receipt = adapter.modify_stop(position_id, new_stop, now_ms=now_ms)
            except Exception:
                self.protection.rollback_unconfirmed_tighten(
                    position_id, previous_stop=old, attempted_stop=new_stop)
                raise
            self._log(
                EventKind.EXECUTION_RECEIPT,
                {**{k: (v.value if hasattr(v, "value") else v)
                    for k, v in asdict(receipt).items()},
                 "exit_action": "MODIFY_STOP", "exit_reason": reason},
                now_ms=now_ms, corr=receipt.trade_intent_id or trade_intent_id,
            )
            if receipt.status in ("REJECTED", "CANCELLED", "EXPIRED", "UNKNOWN"):
                self.protection.rollback_unconfirmed_tighten(
                    position_id, previous_stop=old, attempted_stop=new_stop)
                if not self.protection.is_software(position_id):
                    self.kill.trip(KillSwitchTrigger.STOP_REJECTED, now_ms)
            return receipt

        if action not in ("PARTIAL_CLOSE", "FULL_CLOSE"):
            raise RouterError(f"unsupported preservation action {action}")
        if action == "FULL_CLOSE":
            quantity = None
        return self._send_close(venue, position_id=position_id, trade_intent_id=trade_intent_id,
            action=action, quantity=quantity, now_ms=now_ms, reason=reason)

    def apply_exits(self, venue: str, symbol: str, bid: Decimal, ask: Decimal, *, now_ms: int) -> list[ExecutionReceipt]:
        adapter = self.adapters[venue]
        out = []
        # A fresh protection projection cannot erase an earlier transport
        # attempt. Restore its fence before on_mark can emit another close.
        for position_id, rule in list(self.protection.rules.items()):
            if rule.symbol == symbol:
                pending = self.exit_journal.pending(venue, position_id)
                if pending is not None:
                    self.protection.mark_close_pending(position_id)
                    if pending.payload.get("state", "UNKNOWN") != "ACCEPTED":
                        self._uncertain_exit(position_id, now_ms=now_ms, request_ref=pending.payload.get("request_ref", pending.hash))
        for ins in self.protection.on_mark(symbol, bid, ask, now_ms=now_ms):
            if ins.action == "CLOSE":
                try:
                    r = self._send_close(venue, position_id=ins.position_id, trade_intent_id="",
                        action="FULL_CLOSE", quantity=None, now_ms=now_ms, reason=ins.reason)
                except ExitInFlight:
                    # Another ledger writer committed the same position's
                    # attempt after this mark was calculated.
                    latest = self.exit_journal.latest(venue, ins.position_id)
                    if latest is not None and latest.payload["state"] != "ACCEPTED":
                        self._uncertain_exit(ins.position_id, now_ms=now_ms,
                            request_ref=latest.payload.get("request_ref", latest.hash))
                    continue
            else:
                r = adapter.modify_stop(ins.position_id, ins.price, now_ms=now_ms)  # type: ignore[arg-type]

            if ins.action != "CLOSE":
                self._log(
                    EventKind.EXECUTION_RECEIPT,
                    {
                        **{k: (v.value if hasattr(v, "value") else v) for k, v in asdict(r).items()},
                        "exit_action": ins.action,
                        "exit_reason": ins.reason,
                    },
                    now_ms=now_ms,
                    corr=r.trade_intent_id or ins.position_id,
                )

            if ins.action == "CLOSE":
                if r.status in ("FILLED", "OWNER_EXECUTED", "BROKER_CONFIRMED"):
                    self.protection.close_confirmed(ins.position_id)
                elif r.status in ("REJECTED", "CANCELLED", "EXPIRED"):
                    self.protection.close_failed(ins.position_id)
            else:
                # on_mark has already tentatively moved the in-memory stop. A
                # failed venue modification means the venue still owns the old
                # stop, so rollback local truth and stop new risk.
                if r.status in ("REJECTED", "CANCELLED", "EXPIRED", "UNKNOWN"):
                    if ins.previous_stop is not None and ins.price is not None:
                        self.protection.rollback_unconfirmed_tighten(
                            ins.position_id,
                            previous_stop=ins.previous_stop,
                            attempted_stop=ins.price,
                        )
                    if not self.protection.is_software(ins.position_id):
                        self.kill.trip(KillSwitchTrigger.STOP_REJECTED, now_ms)
                        self._log(
                            EventKind.KILL_SWITCH,
                            {
                                "trigger": "STOP_REJECTED",
                                "position": ins.position_id,
                                "reason": f"{ins.reason}_MODIFY_FAILED",
                            },
                            now_ms=now_ms,
                            corr=r.trade_intent_id or ins.position_id,
                        )
            out.append(r)
        return out


__all__ = ["ExecutionRouter", "RouterError", "resolve_execution_policy"]
