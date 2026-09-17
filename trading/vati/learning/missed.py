"""Missed-opportunity and no-trade learning with a hindsight guard
(integration doc §19, §42; Rev 4 improvement). The setup's validity is judged
from the frozen ex-ante snapshot; the later path only scores the outcome, over
the setup's own horizon window, and never rewrites the decision."""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from vati.learning.episodes import Environment, MissedOpportunityEpisode
from vati.market_data.bars import Bar
from vati.risk.contracts import Direction

ZERO = Decimal("0")
HORIZON_WINDOW_MS = {"SCALP": 30 * 60_000, "INTRADAY": 6 * 3_600_000, "SESSION": 10 * 3_600_000, "OVERNIGHT": 24 * 3_600_000, "SWING": 5 * 86_400_000, "POSITION": 30 * 86_400_000}


def evaluate_missed_opportunity(*, episode_id: str, environment: Environment, instrument: str, strategy_id: str, ex_ante_snapshot_hash: str, rejection_reason: str, rejection_layer: str,
                                horizon: str, direction: Direction, entry: Decimal, stop: Decimal, later_bars: Sequence[Bar], decision_ms: int, ex_ante_valid: bool) -> MissedOpportunityEpisode:
    if not ex_ante_snapshot_hash:
        raise ValueError("hindsight guard: an ex-ante snapshot hash is required")
    window = HORIZON_WINDOW_MS.get(horizon, 6 * 3_600_000)
    path = [b for b in later_bars if decision_ms < b.end_ms <= decision_ms + window]
    risk = abs(entry - stop)
    if not path or risk <= ZERO:
        ep = MissedOpportunityEpisode(episode_id, environment, instrument, strategy_id, ex_ante_snapshot_hash, rejection_reason, rejection_layer, horizon, entry, stop, window, {}, ZERO, ex_ante_valid, "INCONCLUSIVE")
        return ep.sealed()
    mfe = max(((b.high - entry) if direction is Direction.LONG else (entry - b.low)) for b in path)
    mae = min(((b.low - entry) if direction is Direction.LONG else (entry - b.high)) for b in path)
    stopped = any((b.low <= stop) if direction is Direction.LONG else (b.high >= stop) for b in path)
    end = path[-1].close
    r = ((stop - entry) if direction is Direction.LONG else (entry - stop)) / risk if stopped else (((end - entry) if direction is Direction.LONG else (entry - end)) / risk)
    if rejection_layer == "RISK_AUTHORITY":
        verdict = "GOOD_NO_TRADE"          # a risk rejection is correct by definition; the lesson belongs to the strategy, not the gate
    elif not ex_ante_valid:
        verdict = "GOOD_NO_TRADE"
    elif r >= Decimal("1"):
        verdict = "COSTLY_NO_TRADE"
    elif r <= Decimal("-0.5"):
        verdict = "GOOD_NO_TRADE"
    else:
        verdict = "INCONCLUSIVE"
    ep = MissedOpportunityEpisode(episode_id, environment, instrument, strategy_id, ex_ante_snapshot_hash, rejection_reason, rejection_layer, horizon, entry, stop, window,
                                  {"mfe": str(mfe), "mae": str(mae), "stopped": stopped, "close_at_window_end": str(end), "bars": len(path)}, r.quantize(Decimal("0.01")), ex_ante_valid, verdict)
    return ep.sealed()
