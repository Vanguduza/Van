"""InstrumentEvaluator: everything symbol-local, stopping before sizing (§12, TRD-ENH-032).

`DecisionCycle` is one pass per bar for one instrument, and it owns a great deal
of symbol-specific state — regime engine, contract, protection bookkeeping, TCA
learning, entry tracking, symbol-scoped idempotency. Widening it into an
N-symbol object would turn each of those into a hidden collection *and* put the
shared heat budget inside a loop that also owns per-symbol execution state.

So the split is by responsibility rather than by loop: this class keeps
everything `DecisionCycle` owns per symbol and stops one step earlier, emitting
candidates. Account-level authority — mandate, Risk Authority, router, kill
switch, heat — belongs to the coordinator above it, and there is exactly one of
those per account alias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Optional, Sequence

from vati.arbiter.candidate import CandidateOpportunity
from vati.arbiter.opportunity import OpportunityEngine
from vati.intelligence.market_state import MarketState
from vati.intelligence.mtf import MultiTimeframeMarketState
from vati.intelligence.confluence import (
    ConfluenceAxis, ConfluenceEngine, NEUTRAL, OPPOSING, SUPPORTIVE, UNKNOWN,
)
from vati.market_data.bars import Bar
from vati.observability import metrics
from vati.observability.enhancement_metrics import MTF_MISSING_TIMEFRAME
from vati.risk.contracts import Direction
from vati.strategies.base import StrategyContext


@dataclass
class InstrumentEvaluatorConfig:
    symbol: str
    base: str
    quote: str
    venue: str
    account_alias: str
    timeframe: str = "UNKNOWN"


class InstrumentEvaluator:
    """One symbol's opinion. It cannot size, execute, or see the account book."""

    #: Attributes an evaluator must never acquire. A coordinator owns these.
    FORBIDDEN_ATTRS = ("router", "risk_authority", "kill_switch", "mandate_authority")

    def __init__(
        self,
        cfg: InstrumentEvaluatorConfig,
        *,
        engine: OpportunityEngine,
        state_fn: Callable[[Sequence[Bar], int], MarketState],
        ctx_fn: Callable[[MarketState], StrategyContext],
        regime_label_fn: Callable[[MarketState], str] = lambda s: s.regime.trend.value,
        currency_regime_label_fn: Optional[Callable[[MarketState], Optional[str]]] = None,
        mtf_state_fn: Optional[Callable[[int], MultiTimeframeMarketState]] = None,
    ) -> None:
        self.cfg = cfg
        self.engine = engine
        self.state_fn = state_fn
        self.ctx_fn = ctx_fn
        self.regime_label_fn = regime_label_fn
        self.currency_regime_label_fn = currency_regime_label_fn
        self.mtf_state_fn = mtf_state_fn
        self.last_state: Optional[MarketState] = None
        self.last_mtf_state: Optional[MultiTimeframeMarketState] = None
        self.last_candidates: tuple[CandidateOpportunity, ...] = ()
        self.last_confluence: dict[str, object] = {}
        self._confluence = ConfluenceEngine()

    @property
    def symbol(self) -> str:
        return self.cfg.symbol

    def evaluate(self, bars: Sequence[Bar], *, now_ms: int, mtf_state_hash: str = "") -> tuple[CandidateOpportunity, ...]:
        """Produce this symbol's candidates for this pass.

        Returns an empty tuple rather than raising when there is nothing to say:
        no bars, no eligible capsule, no signal, or a meta-label that is not
        TRADE/REDUCE_SIZE. An empty result is a normal outcome.
        """
        if not bars:
            self.last_candidates = ()
            return ()
        mtf = self.mtf_state_fn(now_ms) if self.mtf_state_fn is not None else None
        self.last_mtf_state = mtf
        if mtf is not None and not mtf.complete:
            for tf in mtf.missing_timeframes:
                metrics.inc(
                    MTF_MISSING_TIMEFRAME,
                    symbol=self.cfg.symbol, timeframe=tf,
                )
            if self.cfg.timeframe in mtf.missing_timeframes:
                self.last_candidates = ()
                return ()
        # MTF_SCHEMA_ADOPTION was recorded as strategy_logic_changed=false, so
        # existing strategy formulas still evaluate on the configured primary
        # timeframe. The complete MTF state is now a required causal envelope;
        # role-specific strategy logic requires a later validated capsule revision.
        state = (
            mtf.state_for(self.cfg.timeframe)
            if mtf is not None and mtf.state_for(self.cfg.timeframe) is not None
            else self.state_fn(bars, now_ms)
        )
        self.last_state = state
        ctx = self.ctx_fn(state)
        currency_label = (self.currency_regime_label_fn(state)
                          if self.currency_regime_label_fn else None)
        source_hashes = ()
        if mtf is not None:
            source_hashes = tuple(
                mtf.constituent_states[tf].timeframe_state_hash
                for tf in mtf.required_timeframes if tf in mtf.constituent_states
            )
        cands = self.engine.assess_candidates(
            state, ctx,
            regime_label=self.regime_label_fn(state),
            currency_regime_label=currency_label,
            account_alias=self.cfg.account_alias,
            venue=self.cfg.venue,
            mtf_state_hash=(mtf.mtf_state_hash if mtf is not None else mtf_state_hash) or state.state_hash,
            source_state_hashes=source_hashes or (state.state_hash,),
            mtf_state=mtf,
            now_ms=now_ms,
        )
        self.last_candidates = cands
        self.last_confluence = {
            candidate.candidate_id: self._candidate_confluence(candidate, state)
            for candidate in cands
        }
        return cands

    def _candidate_confluence(self, candidate: CandidateOpportunity, state: MarketState):
        """Read model only: functional evidence relative to a candidate direction."""
        f = state.features
        trend = state.regime.trend.value
        if trend == "BULL":
            trend_state = SUPPORTIVE if candidate.direction is Direction.LONG else OPPOSING
        elif trend == "BEAR":
            trend_state = SUPPORTIVE if candidate.direction is Direction.SHORT else OPPOSING
        else:
            trend_state = NEUTRAL

        momentum_state = UNKNOWN
        if f.rsi is not None:
            momentum_state = (
                SUPPORTIVE if (
                    candidate.direction is Direction.LONG and f.rsi >= Decimal("50")
                    or candidate.direction is Direction.SHORT and f.rsi <= Decimal("50")
                ) else OPPOSING
            )
        volatility_state = OPPOSING if state.regime.vol.value == "EXTREME" else NEUTRAL
        liquidity_state = (
            OPPOSING if f.spread_percentile >= Decimal("0.90") else SUPPORTIVE
        )
        event_state = OPPOSING if state.in_event_window() else NEUTRAL
        axes = (
            ConfluenceAxis("trend", trend_state, ("regime.trend",), (), state.timeframe, state.as_of_ms),
            ConfluenceAxis("momentum", momentum_state, ("features.rsi",) if f.rsi is not None else (), (), state.timeframe, state.as_of_ms),
            ConfluenceAxis("volatility", volatility_state, ("regime.vol",), (), state.timeframe, state.as_of_ms),
            ConfluenceAxis("liquidity", liquidity_state, ("features.spread_percentile",), (), state.timeframe, state.as_of_ms),
            ConfluenceAxis("event", event_state, ("event_window",), (), state.timeframe, state.as_of_ms),
        )
        return self._confluence.build(symbol=state.symbol, as_of_ms=state.as_of_ms, axes=axes)


__all__ = ["InstrumentEvaluator", "InstrumentEvaluatorConfig"]
