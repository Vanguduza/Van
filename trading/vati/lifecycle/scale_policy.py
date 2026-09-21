"""Scale policy registry (TRD-REV51-108, G9).

Scaling into a winner is the single most profitable thing a trading system can
do and the single fastest way to destroy an account, and which one it turns
out to be is decided almost entirely by the conditions attached to it. So the
conditions live here, declared per strategy, rather than inside whatever code
happens to notice a position is up.

Every field is a *restriction*. There is no field that permits a scale the
Risk Authority would otherwise refuse, and no field that raises a ceiling: a
policy can only make expansion harder than the mandate already makes it
(INV-AUTH-001, INV-RISK-001). The strictest policy is therefore the empty one,
and an unregistered strategy gets exactly that — `NO_SCALING` — because a
strategy nobody has thought about scaling is a strategy that does not scale.

The defaults are deliberately unfriendly. They require the position to have
already paid for itself, the family to be healthy rather than merely alive,
real time to have passed since the last add, and each add to be smaller than
the one before. None of these is a measured optimum; they are the conditions
under which the failure mode is survivable, which is a different and more
useful property for a first pass. The laboratory (109) is how they get
argued with.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping, Optional

from vati.core.canonical import canonical_hash, dec
from vati.lifecycle.trade_health import HealthState

POLICY_VERSION = "scale-policy/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")


class PolicyError(ValueError):
    pass


@dataclass(frozen=True)
class ScalePolicy:
    """When a family may be added to, and by how little."""

    policy_id: str
    #: Scaling is off unless this is explicitly true. The default is no.
    enabled: bool = False
    #: R the family must already be in front by before any add.
    min_progress_r: Decimal = Decimal("1.0")
    #: Adds allowed over a family's whole life.
    max_scale_ins: int = 2
    #: Each add, as a fraction of the *root* size. Descending by construction.
    scale_fractions: tuple[Decimal, ...] = (Decimal("0.5"), Decimal("0.25"))
    #: Total family risk ceiling, as a fraction of equity. The authority's own
    #: ceiling still applies and is usually tighter.
    max_family_risk_pct: Decimal = Decimal("0.01")
    #: Health the family must be in. Anything worse withholds.
    required_health: HealthState = HealthState.HEALTHY
    #: Time that must pass between adds.
    cooldown_ms: int = 3_600_000
    #: The stop must already be at or better than the entry before adding.
    require_stop_at_or_better_than_entry: bool = True
    #: Refuse to add inside an event window for the instrument.
    refuse_in_event_window: bool = True

    def __post_init__(self) -> None:
        if self.max_scale_ins < 0:
            raise PolicyError(f"{self.policy_id} has max_scale_ins {self.max_scale_ins}")
        if self.enabled and len(self.scale_fractions) < self.max_scale_ins:
            raise PolicyError(
                f"{self.policy_id} allows {self.max_scale_ins} adds but declares "
                f"{len(self.scale_fractions)} sizes; an undeclared add size would be a default")
        for a, b in zip(self.scale_fractions, self.scale_fractions[1:]):
            if b > a:
                # A later add larger than an earlier one is a pyramid standing
                # on its point: the most exposure at the worst average price.
                raise PolicyError(
                    f"{self.policy_id} scale fractions increase ({a} then {b}); "
                    "each add must be smaller than the one before")
        for f in self.scale_fractions:
            if not (ZERO < f <= ONE):
                raise PolicyError(f"{self.policy_id} has scale fraction {f} outside (0, 1]")
        if self.min_progress_r < ZERO:
            raise PolicyError(f"{self.policy_id} has negative min_progress_r")

    def fraction_for(self, scale_in_index: int) -> Optional[Decimal]:
        """Size of the nth add, as a fraction of the root. None when spent."""
        if not self.enabled or scale_in_index >= self.max_scale_ins:
            return None
        if scale_in_index >= len(self.scale_fractions):
            return None
        return self.scale_fractions[scale_in_index]

    def body(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_version": POLICY_VERSION,
            "enabled": self.enabled,
            "min_progress_r": str(self.min_progress_r),
            "max_scale_ins": self.max_scale_ins,
            "scale_fractions": [str(f) for f in self.scale_fractions],
            "max_family_risk_pct": str(self.max_family_risk_pct),
            "required_health": self.required_health.value,
            "cooldown_ms": self.cooldown_ms,
            "require_stop_at_or_better_than_entry": self.require_stop_at_or_better_than_entry,
            "refuse_in_event_window": self.refuse_in_event_window,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


#: What a strategy nobody has considered gets. Not a placeholder: the correct
#: answer for an unknown strategy is that it does not scale.
NO_SCALING = ScalePolicy(policy_id="NO_SCALING", enabled=False, max_scale_ins=0,
                         scale_fractions=())

#: The shipped starting point for strategies that are allowed to scale at all.
#: Unfriendly on purpose — see the module docstring.
CONSERVATIVE = ScalePolicy(
    policy_id="CONSERVATIVE",
    enabled=True,
    min_progress_r=Decimal("1.0"),
    max_scale_ins=2,
    scale_fractions=(Decimal("0.5"), Decimal("0.25")),
    max_family_risk_pct=Decimal("0.01"),
    required_health=HealthState.HEALTHY,
    cooldown_ms=3_600_000,
)


class ScalePolicyRegistry:
    """Policy lookup at runtime. Unregistered means NO_SCALING."""

    def __init__(self, policies: Optional[Mapping[str, ScalePolicy]] = None) -> None:
        self._by_strategy: dict[str, ScalePolicy] = dict(policies or {})

    def register(self, strategy_id: str, policy: ScalePolicy) -> ScalePolicy:
        self._by_strategy[strategy_id] = policy
        return policy

    def policy_for(self, strategy_id: str) -> ScalePolicy:
        return self._by_strategy.get(strategy_id, NO_SCALING)

    def enabled_strategies(self) -> list[str]:
        return sorted(s for s, p in self._by_strategy.items() if p.enabled)

    def body(self) -> dict[str, Any]:
        return {
            "policy_version": POLICY_VERSION,
            "policies": {s: p.body() for s, p in sorted(self._by_strategy.items())},
            "default": NO_SCALING.body(),
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


def policy_from_mapping(m: Mapping[str, Any]) -> ScalePolicy:
    """Build a policy from configuration, refusing anything it cannot express."""
    known = set(ScalePolicy.__dataclass_fields__)
    unknown = sorted(set(m) - known)
    if unknown:
        # A silently ignored key is a policy the operator believes is in force
        # and is not.
        raise PolicyError(f"unknown policy fields: {', '.join(unknown)}")
    kwargs: dict[str, Any] = {"policy_id": str(m.get("policy_id", "custom"))}
    for key in ("enabled", "require_stop_at_or_better_than_entry", "refuse_in_event_window"):
        if key in m:
            kwargs[key] = bool(m[key])
    for key in ("min_progress_r", "max_family_risk_pct"):
        if key in m:
            kwargs[key] = dec(m[key])
    for key in ("max_scale_ins", "cooldown_ms"):
        if key in m:
            kwargs[key] = int(m[key])
    if "scale_fractions" in m:
        kwargs["scale_fractions"] = tuple(dec(x) for x in m["scale_fractions"])
    if "required_health" in m:
        kwargs["required_health"] = HealthState(str(m["required_health"]).upper())
    return ScalePolicy(**kwargs)
