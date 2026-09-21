"""Expected Shortfall over the open book (§17, TRD-ENH-042).

Stop-risk heat sums what each position loses at its own stop. That is the right
number for "how much am I risking", and the wrong one for "what happens if they
all go wrong together" — gaps, correlated shocks and simultaneous stop slippage
do not respect per-position arithmetic.

ES answers the second question: the mean loss in the worst `1 - confidence`
share of outcomes. Deterministic here — a closed-form Gaussian ES over the
portfolio variance implied by position risks and their correlation — so a
replay reproduces it exactly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

#: 97.5% is the Basel FRTB convention and is a reasonable default here.
DEFAULT_CONFIDENCE = 0.975


def _phi(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _norm_ppf(p: float) -> float:
    """Acklam's rational approximation; adequate for an ES multiplier."""
    if not 0 < p < 1:
        raise ValueError("p in (0,1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5]) * q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def es_multiplier(confidence: float = DEFAULT_CONFIDENCE) -> float:
    """E[Z | Z > z_alpha] for a standard normal."""
    return _phi(_norm_ppf(confidence)) / (1.0 - confidence)


@dataclass(frozen=True)
class Position:
    symbol: str
    #: Loss at this position's own stop, in account currency.
    stop_risk: Decimal
    direction: int = 1        # +1 long, -1 short


def portfolio_variance(
    positions: Sequence[Position],
    correlations: Mapping[tuple[str, str], float],
    *,
    default_correlation: float,
) -> float:
    """Sum_i Sum_j w_i w_j rho_ij, with signs from direction.

    `default_correlation` is used for any pair with no estimate — and it is a
    *conservative* number supplied by the caller, never 0. Treating an unknown
    correlation as independence is how a portfolio looks diversified because
    nobody measured it.
    """
    total = 0.0
    for i, pi in enumerate(positions):
        wi = float(pi.stop_risk) * pi.direction
        for j, pj in enumerate(positions):
            wj = float(pj.stop_risk) * pj.direction
            if i == j:
                rho = 1.0
            else:
                key = (pi.symbol, pj.symbol)
                rev = (pj.symbol, pi.symbol)
                rho = correlations.get(key, correlations.get(rev, default_correlation))
            total += wi * wj * rho
    return max(0.0, total)


def expected_shortfall(
    positions: Sequence[Position],
    correlations: Mapping[tuple[str, str], float],
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    default_correlation: float = 0.5,
) -> Decimal:
    if not positions:
        return Decimal("0")
    sigma = math.sqrt(portfolio_variance(positions, correlations,
                                         default_correlation=default_correlation))
    return Decimal(str(round(sigma * es_multiplier(confidence), 8)))


__all__ = ["DEFAULT_CONFIDENCE", "Position", "es_multiplier", "expected_shortfall",
           "portfolio_variance"]
