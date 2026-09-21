"""Conformal interval engine (TRD-REV51-117, G8).

Every forecast in this system currently arrives as a point — an expected move,
an expected cost — and a point estimate cannot be wrong in a way anyone
notices. Split conformal prediction is the cheapest honest fix: given a set of
past errors, it returns an interval with a distribution-free marginal coverage
guarantee, and it makes no assumption about the model that produced the point.

Three properties earn it a place next to the Risk Authority.

**It fails closed and loudly.** A coverage level of 90% needs at least nine
calibration residuals for the quantile to exist at all. With fewer, the engine
raises rather than returning a narrower interval computed from what it has —
which is exactly what a naive quantile would do, and exactly the failure that
makes a thin sample look confident (INV-FAIL-001).

**It can only narrow admission.** `admits` asks whether the *worst* end of the
interval is survivable. A tight interval never licenses more size; the Risk
Authority still sizes, and a policy that requires conformal evidence uses this
to reject, never to expand (INV-AUTH-001, INV-RISK-001).

**It reports its own realised coverage.** A guarantee that is never checked is
a claim. `coverage_report` compares nominal against realised on held-out
observations, so a calibration set that has gone stale shows up as a number
rather than as a surprise.

Residuals are absolute errors, so intervals are symmetric. That is the right
default for a first pass: an asymmetric variant needs its own evidence that
the asymmetry is real and not an artefact of the sample.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Optional, Sequence

from vati.core.canonical import canonical_hash, dec
from vati.core.events import EventKind, make_event

PRODUCER = "vati-conformal"
CONFORMAL_VERSION = "conformal/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")

#: Default miscoverage. 0.10 means a 90% interval, which needs >= 9 residuals.
DEFAULT_ALPHA = Decimal("0.10")

#: Calibration older than this is not calibration. Kept as an explicit input
#: rather than a clock read, so replay gives the same answer.
DEFAULT_MAX_CALIBRATION_AGE_MS = 30 * 24 * 3_600_000


class InsufficientCalibration(RuntimeError):
    """Too few residuals for the requested coverage to exist."""


class CalibrationStale(RuntimeError):
    """The residuals are older than their useful life."""


def min_calibration_size(alpha: Decimal) -> int:
    """Smallest n for which the (1-alpha) conformal quantile is defined."""
    if not (ZERO < alpha < ONE):
        raise ValueError(f"alpha {alpha} is outside (0, 1)")
    return int(math.ceil(ONE / alpha)) - 1


@dataclass(frozen=True)
class Residual:
    """One past absolute error, and when it was observed."""

    value: Decimal
    observed_ms: int
    label: str = ""

    def __post_init__(self) -> None:
        if self.value < ZERO:
            raise ValueError(f"residual {self.value} is negative; scores are absolute errors")


@dataclass(frozen=True)
class ConformalInterval:
    point: Decimal
    lower: Decimal
    upper: Decimal
    alpha: Decimal
    calibration_size: int
    quantile: Decimal
    bucket: str
    conformal_version: str = CONFORMAL_VERSION

    @property
    def nominal_coverage(self) -> Decimal:
        return ONE - self.alpha

    @property
    def width(self) -> Decimal:
        return self.upper - self.lower

    def contains(self, value: Decimal) -> bool:
        return self.lower <= value <= self.upper

    def admits(self, *, worst_tolerable: Decimal) -> bool:
        """Whether the bad end of the interval is survivable.

        Only ever a reason to refuse. A narrow interval does not license more
        size; sizing belongs to the Risk Authority and stays there.
        """
        return self.lower >= worst_tolerable

    def body(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "point": str(self.point),
            "lower": str(self.lower),
            "upper": str(self.upper),
            "width": str(self.width),
            "alpha": str(self.alpha),
            "nominal_coverage": str(self.nominal_coverage),
            "calibration_size": self.calibration_size,
            "quantile": str(self.quantile),
            "conformal_version": self.conformal_version,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


@dataclass(frozen=True)
class CoverageReport:
    """Nominal against realised. A guarantee nobody checks is a claim."""

    bucket: str
    nominal: Decimal
    realised: Optional[Decimal]
    observations: int
    covered: int

    @property
    def shortfall(self) -> Optional[Decimal]:
        if self.realised is None:
            return None
        return self.nominal - self.realised

    @property
    def is_undercovering(self) -> bool:
        s = self.shortfall
        return s is not None and s > Decimal("0.05")

    def body(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "nominal": str(self.nominal),
            "realised": None if self.realised is None else str(self.realised),
            "observations": self.observations,
            "covered": self.covered,
            "shortfall": None if self.shortfall is None else str(self.shortfall),
            "is_undercovering": self.is_undercovering,
            "conformal_version": CONFORMAL_VERSION,
        }



@dataclass(frozen=True)
class ConformalAdmissionPolicy:
    """One strategy's explicit conformal admission requirement.

    This policy can only add a refusal condition.  It carries no sizing value
    and cannot widen mandate or platform ceilings.
    """

    strategy_id: str
    bucket: str
    worst_tolerable: Decimal
    required: bool = True


class ConformalAdmissionRefused(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class ConformalAdmissionGate:
    """RiskAuthority-side conformal evidence gate (TRD-REV51-117 hook).

    Strategies not explicitly registered here retain their existing deterministic
    authority path.  A registered strategy must have a point forecast and enough
    fresh calibration evidence; the interval may only reject, never increase size.
    """

    def __init__(self, engine: "ConformalEngine",
                 policies: Mapping[str, ConformalAdmissionPolicy]) -> None:
        self.engine = engine
        self._policies = dict(policies)

    def policy_for(self, strategy_id: str) -> Optional[ConformalAdmissionPolicy]:
        return self._policies.get(strategy_id)

    def check(self, intent, snapshot) -> Optional[ConformalInterval]:
        policy = self.policy_for(str(intent.strategy_id))
        if policy is None or not policy.required:
            return None
        point = getattr(intent, "expected_gross_move_pct", None)
        if point is None:
            raise ConformalAdmissionRefused(
                "CONFORMAL_POINT_MISSING",
                f"{intent.strategy_id} requires conformal evidence but has no point forecast",
            )
        bucket = policy.bucket.format(
            strategy_id=intent.strategy_id,
            symbol=intent.symbol,
            account_alias=intent.account_alias,
        )
        try:
            interval = self.engine.interval(
                bucket,
                point=dec(point),
                now_ms=int(snapshot.now_unix) * 1000,
            )
        except (InsufficientCalibration, CalibrationStale) as exc:
            raise ConformalAdmissionRefused(
                "CONFORMAL_EVIDENCE_UNAVAILABLE", str(exc)) from exc
        if not interval.admits(worst_tolerable=policy.worst_tolerable):
            raise ConformalAdmissionRefused(
                "CONFORMAL_WORST_CASE",
                f"{bucket}: lower bound {interval.lower} is below "
                f"{policy.worst_tolerable}",
            )
        return interval


class ConformalEngine:
    """Split-conformal intervals per bucket, with their own coverage record."""

    def __init__(self, *, alpha: Decimal = DEFAULT_ALPHA,
                 max_calibration_age_ms: int = DEFAULT_MAX_CALIBRATION_AGE_MS,
                 ledger=None, producer: str = PRODUCER) -> None:
        if not (ZERO < alpha < ONE):
            raise ValueError(f"alpha {alpha} is outside (0, 1)")
        self.alpha = alpha
        self.max_calibration_age_ms = max_calibration_age_ms
        self._ledger = ledger
        self._producer = producer
        self._residuals: dict[str, list[Residual]] = {}

    # ------------------------------------------------------------ calibration
    def observe(self, bucket: str, *, predicted: Decimal, actual: Decimal,
                observed_ms: int, label: str = "") -> Residual:
        r = Residual(abs(dec(actual) - dec(predicted)), observed_ms, label)
        self._residuals.setdefault(bucket, []).append(r)
        return r

    def add_residual(self, bucket: str, residual: Residual) -> None:
        self._residuals.setdefault(bucket, []).append(residual)

    def calibration_size(self, bucket: str, *, now_ms: Optional[int] = None) -> int:
        return len(self._fresh(bucket, now_ms))

    def _fresh(self, bucket: str, now_ms: Optional[int]) -> list[Residual]:
        rs = self._residuals.get(bucket, [])
        if now_ms is None:
            return list(rs)
        cutoff = now_ms - self.max_calibration_age_ms
        return [r for r in rs if r.observed_ms >= cutoff]

    # --------------------------------------------------------------- interval
    def interval(self, bucket: str, *, point: Decimal, now_ms: Optional[int] = None,
                 alpha: Optional[Decimal] = None) -> ConformalInterval:
        a = alpha if alpha is not None else self.alpha
        need = min_calibration_size(a)
        residuals = self._fresh(bucket, now_ms)
        if len(residuals) < need:
            raise InsufficientCalibration(
                f"{bucket}: {len(residuals)} usable residuals, {need} needed for "
                f"{(ONE - a)} coverage; a narrower interval from fewer points is "
                "exactly the failure this refuses to make")

        scores = sorted(r.value for r in residuals)
        n = len(scores)
        # The conformal quantile: the ceil((n+1)(1-alpha))-th smallest score.
        k = int(math.ceil((n + 1) * float(ONE - a)))
        q = scores[min(k, n) - 1]

        p = dec(point)
        iv = ConformalInterval(point=p, lower=p - q, upper=p + q, alpha=a,
                               calibration_size=n, quantile=q, bucket=bucket)
        if self._ledger is not None and now_ms is not None:
            self._ledger.append(make_event(
                EventKind.CONFORMAL_INTERVAL, self._producer, iv.body(),
                event_time_ms=now_ms, received_time_ms=now_ms, correlation_id=bucket))
        return iv

    def try_interval(self, bucket: str, *, point: Decimal,
                     now_ms: Optional[int] = None,
                     alpha: Optional[Decimal] = None) -> Optional[ConformalInterval]:
        """For callers whose policy tolerates absent evidence. A policy that
        requires conformal evidence uses `interval` and lets it raise."""
        try:
            return self.interval(bucket, point=point, now_ms=now_ms, alpha=alpha)
        except InsufficientCalibration:
            return None

    # --------------------------------------------------------------- coverage
    def coverage_report(self, bucket: str,
                        observations: Sequence[tuple[Decimal, ConformalInterval]],
                        ) -> CoverageReport:
        """Realised coverage over (actual, interval) pairs from held-out data."""
        nominal = ONE - self.alpha
        if not observations:
            return CoverageReport(bucket, nominal, None, 0, 0)
        covered = sum(1 for actual, iv in observations if iv.contains(dec(actual)))
        return CoverageReport(bucket, nominal,
                              Decimal(covered) / Decimal(len(observations)),
                              len(observations), covered)

    def report(self, *, now_ms: Optional[int] = None) -> dict[str, Any]:
        return {
            "conformal_version": CONFORMAL_VERSION,
            "alpha": str(self.alpha),
            "min_calibration_size": min_calibration_size(self.alpha),
            "buckets": {
                b: {"usable": self.calibration_size(b, now_ms=now_ms),
                    "total": len(self._residuals[b])}
                for b in sorted(self._residuals)
            },
        }
