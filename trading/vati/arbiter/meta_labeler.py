"""Meta-labeller v0 (Rev 2 §22, Rev 3 A.6/A.7).

This is a deterministic RULE model, not a probability model. Per Rev 2 §22 an
uncalibrated probability may not act as a multiplier, so v0 emits only rule
multipliers (each ≤ 1) and a TRADE/WAIT/SKIP/REDUCE_SIZE label. A calibrated
statistical model can replace `score()` later behind the same interface once
its Brier/ECE gate passes; until then `calibration_state` says so."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from vati.intelligence.events import EventWindowState
from vati.intelligence.market_state import MarketState
from vati.intelligence.regimes import TransitionPhase, VolRegime
from vati.strategies.base import Signal, StrategyContext
from vati.zse.currency import CurrencyRegime

ONE, ZERO = Decimal(1), Decimal(0)


class MetaLabel(str, Enum):
    TRADE = "TRADE"
    WAIT = "WAIT"
    SKIP = "SKIP"
    REDUCE_SIZE = "REDUCE_SIZE"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"


@dataclass(frozen=True)
class MetaVerdict:
    label: MetaLabel
    confidence_multiplier: Decimal
    volatility_multiplier: Decimal
    liquidity_multiplier: Decimal
    event_risk_multiplier: Decimal
    regime_multiplier: Decimal
    reasons: tuple[str, ...]
    calibration_state: str = "RULES_V0_UNCALIBRATED"
    model_disagreement: Decimal = ZERO


class MetaLabeler:
    def __init__(self, *, capsule_health: dict[str, Decimal] | None = None, t2_assessment: dict | None = None, broker_liquidity: dict[str, Decimal] | None = None) -> None:
        self.capsule_health = capsule_health or {}
        self.t2 = t2_assessment or {}
        # Learned broker execution profile per symbol (Rev 4 Part L): reduce-only, ≤ 1, 0 = SUSPENDED
        self.broker_liquidity = broker_liquidity or {}

    def score(self, state: MarketState, signal: Signal, cost_multiple: Decimal, ctx: StrategyContext | None = None) -> MetaVerdict:
        reasons: list[str] = []
        f, r = state.features, state.regime
        if ctx is not None and ctx.zse is not None:
            # Illiquid end-of-day equity: FX microstructure penalties do not apply.
            # Liquidity from thin-trading days; regime from the ZiG premium regime.
            z = ctx.zse
            vol_m = ONE
            liq_m = Decimal(z.trading_days_of_20) / Decimal(20)
            if liq_m < Decimal("0.5"):
                reasons.append(f"thin counter: traded {z.trading_days_of_20}/20 sessions")
            regime_m = {CurrencyRegime.ANCHORED: ONE, CurrencyRegime.ELEVATED: Decimal("0.8"), CurrencyRegime.STRESSED: Decimal("0.5"), CurrencyRegime.DISORDERLY: ZERO}[z.currency_regime]
            if regime_m == ZERO:
                return MetaVerdict(MetaLabel.SKIP, ZERO, vol_m, liq_m, ONE, regime_m, tuple(reasons + ["currency regime DISORDERLY"]))
        else:
            regime_m = r.risk_multiplier()
            vol_m = ONE
            if r.vol is VolRegime.HIGH:
                vol_m = Decimal("0.7")
            elif r.vol is VolRegime.EXTREME:
                vol_m = Decimal("0.25")
            liq_m = ONE
            if f.spread_percentile > Decimal("0.8"):
                liq_m = Decimal("0.5"); reasons.append("spread in top quintile")
            elif f.spread_percentile > Decimal("0.6"):
                liq_m = Decimal("0.75")
        bl = min(ONE, max(ZERO, self.broker_liquidity.get(signal.symbol, ONE)))
        if bl == ZERO:
            return MetaVerdict(MetaLabel.SKIP, ZERO, vol_m, ZERO, ONE, regime_m, tuple(reasons + ["broker execution profile SUSPENDED for symbol"]))
        if bl < liq_m:
            liq_m = bl; reasons.append(f"learned broker liquidity {bl}")
        ev_m = ONE
        if state.event_window is EventWindowState.QUIET:
            ev_m = Decimal("0.5"); reasons.append("quiet window after Tier-1 release")
        elif state.event_window is EventWindowState.DRIFT:
            ev_m = Decimal("0.75")
        elif state.minutes_to_next_event is not None and state.minutes_to_next_event <= 60:
            ev_m = Decimal("0.5"); reasons.append(f"Tier-1 event in {state.minutes_to_next_event} min")
        conf_m = min(ONE, signal.confidence_hint)
        health = self.capsule_health.get(signal.strategy_id, ONE)
        if health < Decimal("0.55"):
            return MetaVerdict(MetaLabel.SKIP, ZERO, vol_m, liq_m, ev_m, regime_m, tuple(reasons + [f"capsule health {health} below 0.55"]))
        if health < Decimal("0.70"):
            conf_m = min(conf_m, Decimal("0.6")); reasons.append(f"capsule health {health}")
        # T2 (LLM) assessment may only reduce, and only when fresh
        dis = Decimal(str(self.t2.get("model_disagreement", "0"))) if self.t2.get("fresh", False) else ZERO
        if dis > Decimal("0.6"):
            return MetaVerdict(MetaLabel.WAIT, ZERO, vol_m, liq_m, ev_m, regime_m, tuple(reasons + [f"model disagreement {dis} > 0.6"]), model_disagreement=dis)
        if dis > Decimal("0.35"):
            conf_m = min(conf_m, Decimal("0.5")); reasons.append(f"model disagreement {dis}")
        if r.phase is TransitionPhase.TRANSITION and not (ctx is not None and ctx.zse is not None):
            return MetaVerdict(MetaLabel.WAIT, ZERO, vol_m, liq_m, ev_m, regime_m, tuple(reasons + ["regime in TRANSITION"]), model_disagreement=dis)
        if cost_multiple < Decimal("2"):
            return MetaVerdict(MetaLabel.SKIP, ZERO, vol_m, liq_m, ev_m, regime_m, tuple(reasons + [f"edge {cost_multiple:.2f}× cost"]), model_disagreement=dis)
        product = regime_m * vol_m * liq_m * ev_m * conf_m
        label = MetaLabel.TRADE if product >= Decimal("0.75") else (MetaLabel.REDUCE_SIZE if product >= Decimal("0.25") else MetaLabel.SKIP)
        if label is MetaLabel.SKIP:
            reasons.append(f"combined multiplier {product:.2f} < 0.25")
        return MetaVerdict(label, conf_m, vol_m, liq_m, ev_m, regime_m, tuple(reasons), model_disagreement=dis)
