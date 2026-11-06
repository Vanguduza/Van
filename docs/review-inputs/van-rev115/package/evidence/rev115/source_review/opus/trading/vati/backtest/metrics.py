"""Performance metrics (Rev 2 §48, §26): expectancy, drawdown, per-trade Sharpe,
deflated Sharpe ratio (Bailey & López de Prado), probability of backtest
overfitting via CSCV, walk-forward splits. Stdlib only."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations
from typing import Sequence


@dataclass(frozen=True)
class Metrics:
    trades: int
    wins: int
    win_rate: float
    expectancy: float          # mean pnl per trade (account currency)
    expectancy_r: float        # mean R multiple
    profit_factor: float
    max_drawdown: float        # currency
    max_drawdown_pct: float
    sharpe_per_trade: float
    skew: float
    kurtosis: float
    net_pnl: float

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _moments(xs: Sequence[float]) -> tuple[float, float, float, float]:
    n = len(xs)
    if n < 2:
        return (xs[0] if xs else 0.0, 0.0, 0.0, 3.0)
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return mean, 0.0, 0.0, 3.0
    skew = sum(((x - mean) / sd) ** 3 for x in xs) / n
    kurt = sum(((x - mean) / sd) ** 4 for x in xs) / n
    return mean, sd, skew, kurt


def compute_metrics(pnls: Sequence[Decimal], r_multiples: Sequence[Decimal], start_equity: Decimal) -> Metrics:
    p = [float(x) for x in pnls]
    r = [float(x) for x in r_multiples]
    n = len(p)
    if n == 0:
        return Metrics(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 3.0, 0.0)
    wins = [x for x in p if x > 0]; losses = [-x for x in p if x < 0]
    mean, sd, skew, kurt = _moments(p)
    eq = float(start_equity); peak = eq; mdd = 0.0; mdd_pct = 0.0
    for x in p:
        eq += x; peak = max(peak, eq); dd = peak - eq
        if dd > mdd:
            mdd, mdd_pct = dd, dd / peak if peak else 0.0
    pf = (sum(wins) / sum(losses)) if losses else (float("inf") if wins else 0.0)
    return Metrics(n, len(wins), len(wins) / n, mean, (sum(r) / n) if r else 0.0, pf, mdd, mdd_pct, (mean / sd) if sd else 0.0, skew, kurt, sum(p))


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    # Acklam's rational approximation, adequate for the DSR use
    if p <= 0 or p >= 1:
        raise ValueError("p in (0,1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p)); return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p)); return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5; r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def deflated_sharpe(observed_sr: float, *, n_obs: int, skew: float, kurtosis: float, n_trials: int, sr_variance_across_trials: float) -> float:
    """Probability that the observed (per-observation) Sharpe exceeds the expected
    maximum Sharpe from `n_trials` unskilled trials. > 0.95 ⇒ DSR passes."""
    if n_obs < 3 or n_trials < 1:
        return 0.0
    euler = 0.5772156649
    if n_trials == 1 or sr_variance_across_trials <= 0:
        sr0 = 0.0
    else:
        sr0 = math.sqrt(sr_variance_across_trials) * ((1 - euler) * _norm_ppf(1 - 1 / n_trials) + euler * _norm_ppf(1 - 1 / (n_trials * math.e)))
    denom = math.sqrt(max(1e-12, 1 - skew * observed_sr + (kurtosis - 1) / 4 * observed_sr ** 2))
    z = (observed_sr - sr0) * math.sqrt(n_obs - 1) / denom
    return _norm_cdf(z)


def pbo_cscv(returns_matrix: Sequence[Sequence[float]], *, partitions: int = 4) -> float:
    """Probability of backtest overfitting via combinatorially symmetric CV.
    returns_matrix[trial][t]; each trial is one strategy configuration.
    Splits time into `partitions` blocks; for every half/half combination picks
    the in-sample best trial and measures its out-of-sample rank. PBO = share of
    combinations where the IS-best is below median OOS."""
    if not returns_matrix or partitions < 2 or partitions % 2:
        raise ValueError("need ≥1 trial and an even partition count")
    T = min(len(r) for r in returns_matrix)
    if T < partitions:
        return 1.0
    block = T // partitions
    blocks = [(i * block, (i + 1) * block) for i in range(partitions)]
    n_trials = len(returns_matrix)
    below = total = 0
    for is_idx in combinations(range(partitions), partitions // 2):
        oos_idx = [i for i in range(partitions) if i not in is_idx]
        def perf(trial, idxs):
            xs = [returns_matrix[trial][t] for i in idxs for t in range(*blocks[i])]
            m, sd, _, _ = _moments(xs)
            return m / sd if sd else 0.0
        is_perf = [perf(k, is_idx) for k in range(n_trials)]
        best = max(range(n_trials), key=lambda k: is_perf[k])
        oos_perf = [perf(k, oos_idx) for k in range(n_trials)]
        rank = sum(1 for k in range(n_trials) if oos_perf[k] < oos_perf[best]) / max(1, n_trials - 1)
        total += 1
        if rank < 0.5:
            below += 1
    return below / total if total else 1.0


def walk_forward_splits(n: int, *, train: int, test: int) -> list[tuple[range, range]]:
    out = []
    start = 0
    while start + train + test <= n:
        out.append((range(start, start + train), range(start + train, start + train + test)))
        start += test
    return out
