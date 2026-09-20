"""ExitPolicyResearchEngine (§24, TRD-ENH-054..056).

`ProtectionManager` takes `break_even_trigger` and `trail_distance` once at
registration and only ever tightens; `target_model` is a fixed string in the
capsule. Meanwhile `missed.py` already computes MFE and MAE per episode and
discards them after scoring a verdict. The data to do better exists and is
thrown away.

Two disciplines make this safe rather than clever:

* **Never learn from winners only.** Deriving a trailing distance from "the MAE
  of trades that won" conditions on the outcome, which selects paths that
  happened not to stop out. Every policy is replayed over *every* preserved
  path, winners and losers alike.
* **Research produces candidates, never live mutation.** The output is an
  `ExitPolicyCandidate` that enters the normal capsule promotion lifecycle with
  its own certificate. There is no call path from here into live protection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Optional, Sequence

from vati.core.canonical import canonical_hash
from vati.market_data.bars import Bar
from vati.risk.contracts import Direction

ZERO = Decimal("0")

CURRENT_POLICY = "CURRENT_POLICY"
TIME_EXIT = "TIME_EXIT"
EXIT_ONE_BAR_LATER = "EXIT_ONE_BAR_LATER"
EXIT_N_BARS_LATER = "EXIT_N_BARS_LATER"
SCALE_HALF_AT_1R_THEN_TRAIL = "SCALE_HALF_AT_1R_THEN_TRAIL"
SCALE_33_33_34 = "SCALE_33_33_34"
ATR_TRAIL = "ATR_TRAIL"
STRUCTURE_TRAIL = "STRUCTURE_TRAIL"
VOL_ADJUSTED_TRAIL = "VOL_ADJUSTED_TRAIL"
BREAK_EVEN_0_75R = "BREAK_EVEN_0_75R"
BREAK_EVEN_1R = "BREAK_EVEN_1R"
BREAK_EVEN_1_5R = "BREAK_EVEN_1_5R"
NO_BREAK_EVEN = "NO_BREAK_EVEN"
FIXED_2R = "FIXED_2R"
FIXED_3R = "FIXED_3R"
FIXED_4R = "FIXED_4R"
REGIME_CONDITIONED_TARGET = "REGIME_CONDITIONED_TARGET"
LET_RUN_UNTIL_INVALIDATION = "LET_RUN_UNTIL_INVALIDATION"

#: The registered family. Fixed, so a research run cannot invent a policy that
#: was never reviewed; expansive members are present alongside conservative
#: ones so the search can find "we exited too early", not only "too late".
EXIT_POLICY_FAMILY = (
    CURRENT_POLICY, TIME_EXIT, EXIT_ONE_BAR_LATER, EXIT_N_BARS_LATER,
    SCALE_HALF_AT_1R_THEN_TRAIL, SCALE_33_33_34,
    ATR_TRAIL, STRUCTURE_TRAIL, VOL_ADJUSTED_TRAIL,
    BREAK_EVEN_0_75R, BREAK_EVEN_1R, BREAK_EVEN_1_5R, NO_BREAK_EVEN,
    FIXED_2R, FIXED_3R, FIXED_4R,
    REGIME_CONDITIONED_TARGET, LET_RUN_UNTIL_INVALIDATION,
)

#: Members that can only increase exposure duration. Their presence is the
#: point: without them the search can only ever recommend trading less.
EXPANSIVE_POLICIES = frozenset({
    EXIT_ONE_BAR_LATER, EXIT_N_BARS_LATER, FIXED_3R, FIXED_4R,
    NO_BREAK_EVEN, LET_RUN_UNTIL_INVALIDATION,
})


@dataclass(frozen=True)
class PostEntryPath:
    """The full path after entry. Preserved for every trade, not just winners."""

    episode_id: str
    strategy_id: str
    symbol: str
    regime: str
    session: str
    direction: Direction
    entry: Decimal
    stop: Decimal
    bars: tuple[Bar, ...]
    atr_at_entry: Optional[Decimal] = None

    @property
    def risk(self) -> Decimal:
        return abs(self.entry - self.stop)

    def _favourable(self, price: Decimal) -> Decimal:
        return (price - self.entry) if self.direction is Direction.LONG else (self.entry - price)

    def mfe(self) -> Decimal:
        if not self.bars:
            return ZERO
        return max(self._favourable(b.high if self.direction is Direction.LONG else b.low)
                   for b in self.bars)

    def mae(self) -> Decimal:
        if not self.bars:
            return ZERO
        return min(self._favourable(b.low if self.direction is Direction.LONG else b.high)
                   for b in self.bars)

    def mfe_r(self) -> Decimal:
        return (self.mfe() / self.risk) if self.risk > ZERO else ZERO

    def mae_r(self) -> Decimal:
        return (self.mae() / self.risk) if self.risk > ZERO else ZERO

    def bars_to_mfe(self) -> int:
        if not self.bars or self.risk <= ZERO:
            return 0
        best, idx = None, 0
        for i, b in enumerate(self.bars):
            fav = self._favourable(b.high if self.direction is Direction.LONG else b.low)
            if best is None or fav > best:
                best, idx = fav, i
        return idx


@dataclass(frozen=True)
class ExitPolicyResult:
    policy_id: str
    episodes: int
    mean_r: Decimal
    win_rate: Decimal
    max_drawdown_r: Decimal
    mean_bars_held: Decimal
    give_back_from_mfe_r: Decimal

    def as_dict(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in self.__dict__.items()}


@dataclass(frozen=True)
class ExitPolicyCandidate:
    """Research output. Not a live change — it enters normal promotion."""

    strategy_id: str
    incumbent_policy_id: str
    candidate_policy_id: str
    incumbent: ExitPolicyResult
    candidate: ExitPolicyResult
    delta_mean_r: Decimal
    segment: Mapping[str, str] = field(default_factory=dict)
    state: str = "RESEARCH"
    candidate_hash: str = ""

    def as_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id, "incumbent_policy_id": self.incumbent_policy_id,
            "candidate_policy_id": self.candidate_policy_id,
            "incumbent": self.incumbent.as_dict(), "candidate": self.candidate.as_dict(),
            "delta_mean_r": str(self.delta_mean_r), "segment": dict(self.segment), "state": self.state,
        }

    def sealed(self) -> "ExitPolicyCandidate":
        return ExitPolicyCandidate(**{**self.__dict__, "candidate_hash": canonical_hash(self.as_dict())})


def _simulate(path: PostEntryPath, policy_id: str, *, n_bars: int = 3) -> tuple[Decimal, int, Decimal]:
    """Replay one policy over one path. Returns (R, bars held, give-back R)."""
    risk = path.risk
    if risk <= ZERO or not path.bars:
        return ZERO, 0, ZERO

    long = path.direction is Direction.LONG
    stop = path.stop
    peak = ZERO
    atr = path.atr_at_entry or risk

    def fav(price: Decimal) -> Decimal:
        return (price - path.entry) if long else (path.entry - price)

    target_r: Optional[Decimal] = {
        FIXED_2R: Decimal("2"), FIXED_3R: Decimal("3"), FIXED_4R: Decimal("4"),
    }.get(policy_id)
    if policy_id == CURRENT_POLICY:
        target_r = Decimal("3")

    be_trigger: Optional[Decimal] = {
        BREAK_EVEN_0_75R: Decimal("0.75"), BREAK_EVEN_1R: Decimal("1"),
        BREAK_EVEN_1_5R: Decimal("1.5"),
    }.get(policy_id)

    for i, b in enumerate(path.bars):
        hi_fav = fav(b.high if long else b.low)
        lo_fav = fav(b.low if long else b.high)
        peak = max(peak, hi_fav)

        # Stop first: within one bar we cannot know the order, so assume the
        # adverse extreme came first. Optimism here would inflate every result.
        stop_fav = fav(stop)
        if lo_fav <= stop_fav:
            return (stop_fav / risk), i + 1, max(ZERO, (peak - stop_fav) / risk)

        if target_r is not None and hi_fav >= target_r * risk:
            return target_r, i + 1, max(ZERO, (peak - target_r * risk) / risk)

        if be_trigger is not None and peak >= be_trigger * risk:
            stop = path.entry
        if policy_id == ATR_TRAIL and peak > atr:
            trail = (b.close - atr) if long else (b.close + atr)
            stop = max(stop, trail) if long else min(stop, trail)
        if policy_id == VOL_ADJUSTED_TRAIL and peak > atr:
            span = atr * (Decimal("2") if peak > atr * Decimal("3") else Decimal("1"))
            trail = (b.close - span) if long else (b.close + span)
            stop = max(stop, trail) if long else min(stop, trail)
        if policy_id == TIME_EXIT and i + 1 >= n_bars:
            return (fav(b.close) / risk), i + 1, max(ZERO, (peak - fav(b.close)) / risk)

    last = fav(path.bars[-1].close)
    return (last / risk), len(path.bars), max(ZERO, (peak - last) / risk)


class ExitPolicyResearchEngine:
    """Offline only. No import of, and no call path into, live protection."""

    def evaluate(self, paths: Sequence[PostEntryPath], policy_id: str) -> ExitPolicyResult:
        if policy_id not in EXIT_POLICY_FAMILY:
            raise ValueError(f"unregistered exit policy {policy_id}")
        rs: list[Decimal] = []
        bars: list[int] = []
        gives: list[Decimal] = []
        for p in paths:
            r, held, give = _simulate(p, policy_id)
            rs.append(r); bars.append(held); gives.append(give)
        if not rs:
            return ExitPolicyResult(policy_id, 0, ZERO, ZERO, ZERO, ZERO, ZERO)
        n = Decimal(len(rs))
        equity = ZERO; peak = ZERO; dd = ZERO
        for r in rs:
            equity += r
            peak = max(peak, equity)
            dd = max(dd, peak - equity)
        return ExitPolicyResult(
            policy_id=policy_id, episodes=len(rs),
            mean_r=(sum(rs, ZERO) / n).quantize(Decimal("0.0001")),
            win_rate=(Decimal(sum(1 for r in rs if r > 0)) / n).quantize(Decimal("0.0001")),
            max_drawdown_r=dd.quantize(Decimal("0.0001")),
            mean_bars_held=(Decimal(sum(bars)) / n).quantize(Decimal("0.01")),
            give_back_from_mfe_r=(sum(gives, ZERO) / n).quantize(Decimal("0.0001")),
        )

    def search(self, paths: Sequence[PostEntryPath], *, strategy_id: str,
               incumbent: str = CURRENT_POLICY,
               family: Sequence[str] = EXIT_POLICY_FAMILY) -> tuple[ExitPolicyCandidate, ...]:
        """Every family member against the incumbent, over all paths."""
        base = self.evaluate(paths, incumbent)
        out: list[ExitPolicyCandidate] = []
        for pid in family:
            if pid == incumbent:
                continue
            res = self.evaluate(paths, pid)
            out.append(ExitPolicyCandidate(
                strategy_id=strategy_id, incumbent_policy_id=incumbent, candidate_policy_id=pid,
                incumbent=base, candidate=res,
                delta_mean_r=(res.mean_r - base.mean_r).quantize(Decimal("0.0001")),
            ).sealed())
        out.sort(key=lambda c: (-c.delta_mean_r, c.candidate_policy_id))
        return tuple(out)

    def mfe_mae_distribution(self, paths: Sequence[PostEntryPath]) -> dict[str, Decimal]:
        """Descriptive statistics over *all* paths — the point of not conditioning."""
        if not paths:
            return {}
        mfes = sorted(p.mfe_r() for p in paths)
        maes = sorted(p.mae_r() for p in paths)
        n = len(paths)

        def pct(xs, q):
            return xs[min(n - 1, int(n * q))]

        return {
            "mfe_r_p50": pct(mfes, 0.5), "mfe_r_p75": pct(mfes, 0.75), "mfe_r_p90": pct(mfes, 0.9),
            "mae_r_p50": pct(maes, 0.5), "mae_r_p25": pct(maes, 0.25), "mae_r_p10": pct(maes, 0.1),
            "mean_bars_to_mfe": Decimal(sum(p.bars_to_mfe() for p in paths)) / Decimal(n),
        }


__all__ = [
    "EXIT_POLICY_FAMILY", "EXPANSIVE_POLICIES",
    "ExitPolicyCandidate", "ExitPolicyResearchEngine", "ExitPolicyResult", "PostEntryPath",
] + list(EXIT_POLICY_FAMILY)
