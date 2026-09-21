"""Expansion counterfactual laboratory (TRD-REV51-109, G10).

G11 turns expansion on. This is what has to be run before that conversation is
worth having: a replay of closed families under alternative scale policies,
offline, with no connection to any live path.

The honest limits are stated up front because they determine what the output
may be used for.

* **It replays what happened, not what would have happened.** Adding size to a
  position does not move the market in a backtest, and in life sometimes it
  does. The laboratory assumes the same price path, which is a good assumption
  for a small add in a liquid instrument and a bad one otherwise.
* **It cannot invent adds that never had a price.** A counterfactual add is
  priced at a mark the family actually traded through, so the laboratory can
  only evaluate adds at moments it has data for.
* **Survivorship is checked, not assumed.** Families that were still open when
  the sample ended are excluded and counted, because the open ones skew
  optimistic: winners run.

The output is a comparison, never a recommendation. It reports what each
policy would have produced over the same families, including the worst family
outcome, which is the number that decides whether a policy is survivable —
the mean is the number that makes every scaling policy look good.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Optional, Sequence

from vati.core.canonical import canonical_hash, dec
from vati.lifecycle.family import FamilyState, MemberRole, PositionFamily
from vati.lifecycle.scale_policy import NO_SCALING, ScalePolicy
from vati.risk.contracts import Direction

LAB_VERSION = "expansion-lab/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")

#: Below this many closed families the comparison is not evidence, whatever it
#: says. Scaling results are dominated by a handful of large winners, so a
#: small sample is not a small amount of evidence — it is none.
MIN_FAMILIES_FOR_EVIDENCE = 30


class LabError(RuntimeError):
    pass


@dataclass(frozen=True)
class PricePoint:
    """A mark the family actually traded through, with its R progress."""

    at_ms: int
    price: Decimal
    progress_r: Decimal
    health_ok: bool = True
    in_event_window: bool = False


@dataclass(frozen=True)
class FamilyReplay:
    """One closed family and the marks it passed through."""

    family_id: str
    strategy_id: str
    symbol: str
    direction: Direction
    root_quantity: Decimal
    entry_price: Decimal
    original_stop: Decimal
    exit_price: Decimal
    opened_ms: int
    closed_ms: int
    path: tuple[PricePoint, ...]
    was_open_at_sample_end: bool = False

    @property
    def sign(self) -> Decimal:
        return ONE if self.direction is Direction.LONG else Decimal("-1")

    @property
    def risk_distance(self) -> Decimal:
        return abs(self.entry_price - self.original_stop)

    @property
    def baseline_r(self) -> Decimal:
        if self.risk_distance <= ZERO:
            raise LabError(f"{self.family_id} has no risk distance")
        return self.sign * (self.exit_price - self.entry_price) / self.risk_distance


@dataclass(frozen=True)
class PolicyOutcome:
    """What one policy would have produced over one family."""

    family_id: str
    policy_id: str
    adds: int
    total_r: Decimal
    baseline_r: Decimal

    @property
    def delta_r(self) -> Decimal:
        return self.total_r - self.baseline_r

    def body(self) -> dict[str, Any]:
        return {"family_id": self.family_id, "policy_id": self.policy_id,
                "adds": self.adds, "total_r": str(self.total_r),
                "baseline_r": str(self.baseline_r), "delta_r": str(self.delta_r)}


@dataclass(frozen=True)
class PolicyComparison:
    policy_id: str
    outcomes: tuple[PolicyOutcome, ...]
    families_considered: int
    families_excluded_open: int

    @property
    def total_delta_r(self) -> Decimal:
        return sum((o.delta_r for o in self.outcomes), ZERO)

    @property
    def mean_delta_r(self) -> Optional[Decimal]:
        if not self.outcomes:
            return None
        return self.total_delta_r / Decimal(len(self.outcomes))

    @property
    def worst_delta_r(self) -> Optional[Decimal]:
        """The number that decides whether a policy is survivable.

        The mean is the number that makes every scaling policy look good.
        """
        if not self.outcomes:
            return None
        return min(o.delta_r for o in self.outcomes)

    @property
    def families_scaled(self) -> int:
        return sum(1 for o in self.outcomes if o.adds > 0)

    @property
    def has_evidence(self) -> bool:
        return len(self.outcomes) >= MIN_FAMILIES_FOR_EVIDENCE

    def body(self) -> dict[str, Any]:
        return {
            "lab_version": LAB_VERSION,
            "policy_id": self.policy_id,
            "families_considered": self.families_considered,
            "families_excluded_open": self.families_excluded_open,
            "families_scaled": self.families_scaled,
            "total_delta_r": str(self.total_delta_r),
            "mean_delta_r": None if self.mean_delta_r is None else str(self.mean_delta_r),
            "worst_delta_r": None if self.worst_delta_r is None else str(self.worst_delta_r),
            "has_evidence": self.has_evidence,
            "minimum_sample": MIN_FAMILIES_FOR_EVIDENCE,
            "assumptions": [
                "same price path: an add does not move the market",
                "adds priced only at marks the family actually traded through",
                "families still open at sample end are excluded",
            ],
            "is_recommendation": False,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class ExpansionLaboratory:
    """Replays closed families under alternative policies. Offline only."""

    def __init__(self, replays: Optional[Iterable[FamilyReplay]] = None) -> None:
        self._replays: list[FamilyReplay] = list(replays or ())

    def add(self, replay: FamilyReplay) -> FamilyReplay:
        self._replays.append(replay)
        return replay

    def __len__(self) -> int:
        return len(self._replays)

    # ------------------------------------------------------------------ replay
    def replay_policy(self, policy: ScalePolicy) -> PolicyComparison:
        outcomes: list[PolicyOutcome] = []
        excluded = 0
        for r in self._replays:
            if r.was_open_at_sample_end:
                # Open families skew optimistic: winners run.
                excluded += 1
                continue
            outcomes.append(self._one(r, policy))
        return PolicyComparison(policy.policy_id, tuple(outcomes),
                                len(self._replays), excluded)

    def _one(self, r: FamilyReplay, policy: ScalePolicy) -> PolicyOutcome:
        baseline = r.baseline_r
        if not policy.enabled:
            return PolicyOutcome(r.family_id, policy.policy_id, 0, baseline, baseline)

        adds: list[tuple[Decimal, Decimal]] = []     # (fraction, entry price)
        last_add_ms: Optional[int] = None
        for point in sorted(r.path, key=lambda p: p.at_ms):
            index = len(adds)
            fraction = policy.fraction_for(index)
            if fraction is None:
                break
            if point.progress_r < policy.min_progress_r:
                continue
            if policy.required_health.value != "HEALTHY" or not point.health_ok:
                if not point.health_ok:
                    continue
            if policy.refuse_in_event_window and point.in_event_window:
                continue
            if last_add_ms is not None and point.at_ms - last_add_ms < policy.cooldown_ms:
                continue
            adds.append((fraction, point.price))
            last_add_ms = point.at_ms

        if not adds:
            return PolicyOutcome(r.family_id, policy.policy_id, 0, baseline, baseline)

        # Each add carries its own R measured from its own entry, scaled by
        # its fraction of the root. The stop for an add sits at the family's
        # entry by the time adds are permitted, so an add's downside is
        # bounded by its own distance travelled, not by the original risk.
        total = baseline
        for fraction, price in adds:
            add_r = r.sign * (r.exit_price - price) / r.risk_distance
            total += add_r * fraction
        return PolicyOutcome(r.family_id, policy.policy_id, len(adds), total, baseline)

    # -------------------------------------------------------------- comparison
    def compare(self, policies: Sequence[ScalePolicy]) -> dict[str, Any]:
        """Every policy over the same families, plus the do-nothing baseline."""
        results = [self.replay_policy(p) for p in (NO_SCALING, *policies)]
        best = max((r for r in results if r.has_evidence),
                   key=lambda r: (r.total_delta_r, r.policy_id), default=None)
        return {
            "lab_version": LAB_VERSION,
            "families": len(self._replays),
            "policies": [r.body() for r in results],
            "best_by_total_delta": None if best is None else best.policy_id,
            "note": ("a comparison, not a recommendation; the worst family outcome "
                     "decides survivability, not the mean"),
        }
