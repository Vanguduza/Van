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
from vati.market_data.bars import Bar
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
    ) -> None:
        self.cfg = cfg
        self.engine = engine
        self.state_fn = state_fn
        self.ctx_fn = ctx_fn
        self.regime_label_fn = regime_label_fn
        self.currency_regime_label_fn = currency_regime_label_fn
        self.last_state: Optional[MarketState] = None
        self.last_candidates: tuple[CandidateOpportunity, ...] = ()

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
        state = self.state_fn(bars, now_ms)
        self.last_state = state
        ctx = self.ctx_fn(state)
        currency_label = (self.currency_regime_label_fn(state)
                          if self.currency_regime_label_fn else None)
        cands = self.engine.assess_candidates(
            state, ctx,
            regime_label=self.regime_label_fn(state),
            currency_regime_label=currency_label,
            account_alias=self.cfg.account_alias,
            venue=self.cfg.venue,
            mtf_state_hash=mtf_state_hash or state.state_hash,
            now_ms=now_ms,
        )
        self.last_candidates = cands
        return cands


__all__ = ["InstrumentEvaluator", "InstrumentEvaluatorConfig"]
