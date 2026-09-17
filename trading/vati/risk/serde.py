"""Serialisation of Risk Authority inputs so a RISK_DECISION ledger event can
be replayed byte-for-byte (Rev 2 §42 decision replay)."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Any

from vati.risk.contracts import Direction, KillSwitchTrigger, LossModel, MarketIntegrityState, OpenPosition, RiskSnapshot, StrategyState, SymbolContract, TradeIntent

DEC_FIELDS_INTENT = {"entry", "stop", "requested_risk_pct", "stake", "expected_gross_move_pct", "regime_multiplier", "confidence_multiplier", "volatility_multiplier", "liquidity_multiplier", "event_risk_multiplier", "correlation_multiplier"}


def _enc(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if hasattr(v, "value"):
        return v.value
    if isinstance(v, (set, frozenset)):
        return sorted(_enc(x) for x in v)
    if isinstance(v, tuple):
        return [_enc(x) for x in v]
    if isinstance(v, dict):
        return {k: _enc(x) for k, x in v.items()}
    return v


def intent_to_dict(i: TradeIntent) -> dict: return _enc(asdict(i))
def contract_to_dict(c: SymbolContract) -> dict: return _enc(asdict(c))
def position_to_dict(p: OpenPosition) -> dict: return _enc(asdict(p))


def snapshot_to_dict(s: RiskSnapshot) -> dict:
    d = _enc(asdict(s))
    d["symbol_contract"] = contract_to_dict(s.symbol_contract)
    d["open_positions"] = [position_to_dict(p) for p in s.open_positions]
    return d


def _D(v): return None if v is None else Decimal(str(v))


def intent_from_dict(d: dict) -> TradeIntent:
    kw = dict(d)
    for k in DEC_FIELDS_INTENT:
        if k in kw:
            kw[k] = _D(kw[k])
    kw["direction"] = Direction(kw["direction"]); kw["strategy_state"] = StrategyState(kw["strategy_state"])
    return TradeIntent(**kw)


def contract_from_dict(d: dict) -> SymbolContract:
    kw = dict(d)
    for k in ("contract_size", "tick_size", "tick_value", "volume_min", "volume_step", "volume_max", "min_stop_distance", "max_stake", "board_lot", "adv_20d", "max_adv_participation", "liquidity_haircut", "round_trip_cost_pct"):
        if k in kw:
            kw[k] = _D(kw[k])
    kw["loss_model"] = LossModel(kw["loss_model"])
    return SymbolContract(**kw)


def position_from_dict(d: dict) -> OpenPosition:
    kw = dict(d)
    for k in ("lots", "stop_distance", "value_per_price_unit_per_lot", "stake", "liquidity_haircut_per_unit"):
        if k in kw:
            kw[k] = _D(kw[k])
    kw["direction"] = Direction(kw["direction"]); kw["loss_model"] = LossModel(kw["loss_model"])
    return OpenPosition(**kw)


def snapshot_from_dict(d: dict) -> RiskSnapshot:
    kw = dict(d)
    for k in ("equity", "balance", "peak_equity", "day_start_equity", "week_start_equity"):
        kw[k] = _D(kw[k])
    kw["symbol_contract"] = contract_from_dict(kw["symbol_contract"])
    kw["open_positions"] = tuple(position_from_dict(p) for p in kw["open_positions"])
    kw["market_integrity"] = MarketIntegrityState(kw["market_integrity"])
    kw["kill_switch_triggers"] = frozenset(KillSwitchTrigger(t) for t in kw.get("kill_switch_triggers", []))
    return RiskSnapshot(**kw)
