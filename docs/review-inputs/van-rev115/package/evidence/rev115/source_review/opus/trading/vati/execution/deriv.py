"""Deriv adapter contract (Rev 2 §5.3, §20). Maps Deriv products to VATI loss
models, builds proposal/buy messages, fails closed without transport. Synthetic
indices are refused unless the capsule is synthetic_only (Rev 3 A.8: OBSERVE)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Optional

from vati.execution.base import AccountState, ExecutionReceipt, Health, OrderCommand, VenuePosition, VenueUnavailable
from vati.risk.contracts import Direction, LossModel

ZERO = Decimal("0")

DERIV_CONTRACTS = {
    # deriv contract family → (VATI loss model, Nautilus instrument class)
    "RISE_FALL": (LossModel.FULL_STAKE, "BinaryOption"),
    "HIGHER_LOWER": (LossModel.FULL_STAKE, "BinaryOption"),
    "TOUCH_NO_TOUCH": (LossModel.FULL_STAKE, "BinaryOption"),
    "DIGITS": (LossModel.FULL_STAKE, "BinaryOption"),
    "MULTIPLIERS": (LossModel.FULL_STAKE, "Cfd"),
    "ACCUMULATORS": (LossModel.FULL_STAKE, "BinaryOption"),
    "TURBOS": (LossModel.FULL_STAKE, "OptionContract"),
    "VANILLAS": (LossModel.FULL_STAKE, "OptionContract"),
    "CFD": (LossModel.STOP_DISTANCE, "Cfd"),
}
SYNTHETIC_PREFIXES = ("R_", "1HZ", "BOOM", "CRASH", "JD", "RDBEAR", "RDBULL", "stpRNG")


def map_deriv_contract(family: str) -> tuple[LossModel, str]:
    if family not in DERIV_CONTRACTS:
        raise ValueError(f"unknown Deriv contract family {family}")
    return DERIV_CONTRACTS[family]


def is_synthetic(symbol: str) -> bool:
    return symbol.upper().startswith(tuple(p.upper() for p in SYNTHETIC_PREFIXES))


@dataclass
class DerivAdapter:
    venue: str = "deriv"
    account_alias: str = "deriv_primary"
    transport: Optional[Callable[[dict], dict]] = None
    allow_synthetics: bool = False
    sent: list[dict] = field(default_factory=list)

    def _call(self, msg: dict) -> dict:
        if self.transport is None:
            raise VenueUnavailable("Deriv transport not configured; fail closed")
        self.sent.append(msg)
        return self.transport(msg)

    def sync_account(self) -> AccountState:
        r = self._call({"authorize": "<token-from-vault-never-in-prompt>"})
        a = r.get("authorize", {})
        return AccountState(self.account_alias, Decimal(str(a.get("balance", "0"))), Decimal(str(a.get("balance", "0"))), a.get("currency", "USD"), bool(a.get("loginid")))

    def positions(self) -> list[VenuePosition]:
        r = self._call({"portfolio": 1})
        out = []
        for c in r.get("portfolio", {}).get("contracts", []):
            out.append(VenuePosition(str(c["contract_id"]), c["symbol"], Direction.LONG, Decimal(str(c.get("buy_price", "0"))), Decimal(str(c.get("buy_price", "0"))), None, str(c.get("passthrough", {}).get("trade_intent_id", "")), LossModel.FULL_STAKE))
        return out

    def heartbeat(self, *, now_ms: int) -> Health:
        try:
            r = self._call({"ping": 1})
            return Health(r.get("ping") == "pong", 0, now_ms)
        except VenueUnavailable:
            return Health(False, 0, now_ms)

    def build_proposal(self, cmd: OrderCommand, *, family: str, duration: int, duration_unit: str = "m") -> dict:
        loss_model, _ = map_deriv_contract(family)
        if loss_model is not cmd.loss_model:
            raise ValueError(f"contract family {family} implies {loss_model.value}, command carries {cmd.loss_model.value}")
        return {"proposal": 1, "amount": str(cmd.quantity), "basis": "stake", "contract_type": "CALL" if cmd.direction is Direction.LONG else "PUT", "currency": "USD",
                "duration": duration, "duration_unit": duration_unit, "symbol": cmd.symbol, "passthrough": {"trade_intent_id": cmd.trade_intent_id, "decision_hash": cmd.decision_hash}}

    def submit(self, cmd: OrderCommand, *, now_ms: int, family: str = "MULTIPLIERS", duration: int = 60) -> ExecutionReceipt:
        if is_synthetic(cmd.symbol) and not self.allow_synthetics:
            return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "REJECTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason="synthetic index: OBSERVE only (Rev 3 A.8)").sealed()
        prop = self._call(self.build_proposal(cmd, family=family, duration=duration))
        pid = prop.get("proposal", {}).get("id")
        if not pid:
            return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "REJECTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason=str(prop.get("error", "no proposal"))).sealed()
        buy = self._call({"buy": pid, "price": str(cmd.quantity), "passthrough": {"trade_intent_id": cmd.trade_intent_id, "decision_hash": cmd.decision_hash}})
        b = buy.get("buy")
        if not b:
            return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "REJECTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason=str(buy.get("error", "buy failed"))).sealed()
        # FULL_STAKE: the stake is the maximum loss, so protection is inherent → confirmed
        return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "FILLED", Decimal(str(b.get("buy_price", cmd.quantity))), Decimal(str(b.get("buy_price", cmd.quantity))), cmd.entry_price, cmd.entry_price, cmd.entry_price, True,
                                int(b.get("purchase_time", now_ms // 1000)) * 1000, now_ms, broker_order_id=str(b.get("transaction_id", "")), broker_position_id=str(b.get("contract_id", ""))).sealed()

    def modify_stop(self, position_id: str, new_stop: Decimal, *, now_ms: int) -> ExecutionReceipt:
        r = self._call({"contract_update": 1, "contract_id": int(position_id), "limit_order": {"stop_loss": str(new_stop)}})
        return ExecutionReceipt("", "", self.venue, "ACCEPTED" if "contract_update" in r else "REJECTED", ZERO, None, ZERO, ZERO, ZERO, "contract_update" in r, now_ms, now_ms, broker_position_id=position_id).sealed()

    def close(self, position_id: str, quantity: Optional[Decimal], *, now_ms: int, reason: str) -> ExecutionReceipt:
        r = self._call({"sell": int(position_id), "price": 0})
        s = r.get("sell", {})
        return ExecutionReceipt("", "", self.venue, "FILLED" if s else "REJECTED", Decimal(str(s.get("sold_for", "0"))), Decimal(str(s.get("sold_for", "0"))) if s else None, ZERO, ZERO, ZERO, True, now_ms, now_ms, broker_position_id=position_id, reject_reason=reason).sealed()
