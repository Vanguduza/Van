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
from vati.core.events import EventKind, make_event
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


# ===========================================================================
# Adaptive position management (GAP-F-003, REQ-TRD-08, REQ-FLOW-09)
# ===========================================================================
"""Turning a ThesisAssessment into a proposal, and nothing further.

The audit's REQ-TRD-08 finding was that adaptive position management existed
only as a deterministic preservation path: VAN could tighten and it could
close, but it had no vocabulary for "this trade has changed, here is what to
do about it" and no way to say so to the owner. What follows is that
vocabulary.

Everything here is a *proposal*. A proposal is not an order, is not a size and
is not an approval; it is a recommendation with a rationale, persisted so the
owner can see what VAN thought and so the decision can be scored later. The
three things that make a proposal matter all happen elsewhere:

* any size change is expressed as a **delta TradeIntent** and goes through
  `RiskAuthority.evaluate` — portfolio heat, open stop risk, per-trade ceiling,
  correlation legs, drawdown and mandate all apply to it exactly as they do to
  an opening trade (INV-AUTH-001);
* the resulting order goes through `ExecutionRouter.execute`, the only caller
  of `adapter.submit` (INV-EXEC-001);
* a protection move goes through `execution/protection.py`, where stops only
  tighten.

The ADD rule is the one worth reading twice. An add is permitted only when
protection is already at or beyond break-even **and** the position's total risk
after the add is no greater than the risk originally approved for it. Those two
together mean an add can never convert an unrealised gain into additional
exposure: the account is never risking more on this idea than it agreed to risk
when the idea was untested. "Winning" is not evidence that more can be
afforded, and a system that treats it as evidence compounds beautifully until
it does not.
"""


class Adjustment(str, Enum):
    """What VAN proposes doing with an open position.

    There is no INCREASE_RISK and no WIDEN_STOP, for the same reason the
    cognition verdict vocabulary has no OVERRIDE: the vocabulary is the control
    surface.
    """

    HOLD = "HOLD"                      # nothing to do; the claim still holds
    ADD = "ADD"                        # scale in, bounded by the original risk
    REDUCE = "REDUCE"                  # same trade, less of it
    MOVE_PROTECTION = "MOVE_PROTECTION"  # tighten only, via protection.py
    PARTIAL_TAKE = "PARTIAL_TAKE"      # bank part of the move
    EXIT = "EXIT"                      # close the position


#: Proposals that change position size and therefore require a delta intent,
#: a RiskAuthority decision and a router submission.
SIZE_CHANGING = frozenset({Adjustment.ADD, Adjustment.REDUCE, Adjustment.PARTIAL_TAKE})

#: The safest execution set. A capsule that declares nothing gets exactly this:
#: hold the position or leave it. Matching `NO_SCALING`, the correct answer for
#: a strategy nobody has thought about is that it does not adapt.
DEFAULT_PERMITTED: frozenset = frozenset({Adjustment.HOLD, Adjustment.EXIT})

#: Everything a fully-adaptive capsule may be granted.
ALL_ADJUSTMENTS: frozenset = frozenset(Adjustment)

#: Why a proposal was made. Closed vocabulary, checked on construction.
ADJUSTMENT_REASONS: dict[str, str] = {
    "THESIS_INVALIDATED": "the claim the trade was making no longer holds",
    "THESIS_WEAKER": "evidence has accumulated against the claim",
    "THESIS_RISKIER": "the same claim is being carried on worse terms",
    "THESIS_OVEREXTENDED": "the move has run past what the thesis claimed",
    "THESIS_ASYMMETRIC": "downside is bounded and the position is in front",
    "THESIS_STRONGER": "a declared confirmation condition was met",
    "THESIS_INTACT": "nothing has changed; the position stands as approved",
    "HEALTH_FAILING": "the deterministic health verdict is FAILING",
    "HEALTH_BLOCKS_SCALING": "health is not HEALTHY, so no add is available",
    "PROTECTION_BELOW_BREAK_EVEN": "protection is not yet at break-even",
    "PROTECTION_CAN_TIGHTEN": "protection can be moved to a better level",
    "RISK_BUDGET_SPENT": "an add would exceed the risk originally approved here",
    "EVENT_RISK": "a relevant event bears on this position",
    "POLICY_FORBIDS": "the capsule's policy does not permit this action",
    "SCALE_POLICY_EXHAUSTED": "the family has used its permitted adds",
    "NO_ORIGINAL_RISK": "the original approved risk for this position is unknown",
}


class AdjustmentError(ValueError):
    pass


@dataclass(frozen=True)
class AdjustmentPolicy:
    """Which adjustments a capsule's positions may actually execute.

    Deterministic per capsule: the same capsule always produces the same
    permitted set, so "what would VAN have done" is answerable on replay. A
    capsule may permit only HOLD and EXIT, which is the default.
    """

    policy_id: str
    permitted: frozenset = DEFAULT_PERMITTED
    #: Fraction of the position a REDUCE takes off. Bounded (0, 1].
    reduce_fraction: Decimal = Decimal("0.5")
    #: Fraction a PARTIAL_TAKE banks. Bounded (0, 1].
    partial_take_fraction: Decimal = Decimal("0.33")

    def __post_init__(self) -> None:
        unknown = sorted(str(a) for a in self.permitted if not isinstance(a, Adjustment))
        if unknown:
            raise AdjustmentError(f"{self.policy_id} permits unknown adjustments: {unknown}")
        if Adjustment.HOLD not in self.permitted:
            # Every policy must be able to do nothing, or the engine has no
            # answer when nothing is the right answer.
            raise AdjustmentError(f"{self.policy_id} does not permit HOLD")
        for name, value in (("reduce_fraction", self.reduce_fraction),
                            ("partial_take_fraction", self.partial_take_fraction)):
            if not (ZERO < value <= ONE):
                raise AdjustmentError(f"{self.policy_id} has {name} {value} outside (0, 1]")

    def allows(self, action: "Adjustment") -> bool:
        return action in self.permitted

    def body(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "permitted": sorted(a.value for a in self.permitted),
            "reduce_fraction": str(self.reduce_fraction),
            "partial_take_fraction": str(self.partial_take_fraction),
        }


#: Hold or leave. What an unconfigured capsule gets.
HOLD_OR_EXIT = AdjustmentPolicy(policy_id="HOLD_OR_EXIT", permitted=DEFAULT_PERMITTED)

#: Defensive management: may reduce, bank and tighten, but never add.
DEFENSIVE = AdjustmentPolicy(
    policy_id="DEFENSIVE",
    permitted=frozenset({
        Adjustment.HOLD, Adjustment.EXIT, Adjustment.REDUCE,
        Adjustment.PARTIAL_TAKE, Adjustment.MOVE_PROTECTION,
    }),
)

#: Full adaptive management. ADD is still capped at the original approved risk
#: by the engine, whatever this policy says.
ADAPTIVE = AdjustmentPolicy(policy_id="ADAPTIVE", permitted=ALL_ADJUSTMENTS)


@dataclass(frozen=True)
class PositionAdjustmentProposal:
    """A recommendation about one open position, with its reasoning attached.

    `delta_risk_pct` is what the proposal would *request* if it were turned
    into a delta intent. It is a request and nothing more: the Risk Authority
    decides the size, and may reject the intent outright.
    """

    trade_intent_id: str
    symbol: str
    strategy_id: str
    action: Adjustment
    reasons: tuple[str, ...]
    rationale: str
    #: Fraction of the current position the action applies to, where meaningful.
    size_fraction: Optional[Decimal] = None
    #: Requested risk for an ADD, as a fraction of equity. Never above the
    #: headroom left under the position's original approved risk.
    delta_risk_pct: Optional[Decimal] = None
    #: Where protection would move to. Tighter than the current stop, always.
    new_stop: Optional[Decimal] = None
    thesis_state: str = ""
    thesis_seal: str = ""
    health_state: str = ""
    policy_id: str = ""
    original_approved_risk_pct: Optional[Decimal] = None
    risk_after_action_pct: Optional[Decimal] = None
    proposed_ms: int = 0
    proposal_version: str = "position-adjustment/5.1.0"

    def __post_init__(self) -> None:
        for r in self.reasons:
            if r not in ADJUSTMENT_REASONS:
                raise AdjustmentError(f"{r!r} is not a classified adjustment reason")
        if self.action in SIZE_CHANGING and self.size_fraction is None and self.delta_risk_pct is None:
            raise AdjustmentError(
                f"{self.action.value} changes size but names neither a fraction nor a risk")
        if self.action is Adjustment.ADD:
            if self.delta_risk_pct is None or self.delta_risk_pct <= ZERO:
                raise AdjustmentError("an ADD must request a positive risk")
            if self.original_approved_risk_pct is None:
                raise AdjustmentError(
                    "an ADD without the position's original approved risk cannot be bounded")
            if self.risk_after_action_pct is None or (
                self.risk_after_action_pct > self.original_approved_risk_pct
            ):
                # The whole point of the rule, restated where it cannot be
                # skipped: an add may not take total risk past what was
                # originally approved for this position.
                raise AdjustmentError(
                    f"ADD would take risk to {self.risk_after_action_pct}, past the "
                    f"originally approved {self.original_approved_risk_pct}")

    @property
    def changes_size(self) -> bool:
        return self.action in SIZE_CHANGING

    @property
    def requires_authority(self) -> bool:
        """Whether this proposal must reach `RiskAuthority.evaluate` to happen."""
        return self.changes_size

    def body(self) -> dict[str, Any]:
        return {
            "trade_intent_id": self.trade_intent_id,
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "action": self.action.value,
            "reasons": list(self.reasons),
            "reason_detail": [ADJUSTMENT_REASONS[r] for r in self.reasons],
            "rationale": self.rationale,
            "size_fraction": None if self.size_fraction is None else str(self.size_fraction),
            "delta_risk_pct": None if self.delta_risk_pct is None else str(self.delta_risk_pct),
            "new_stop": None if self.new_stop is None else str(self.new_stop),
            "thesis_state": self.thesis_state,
            "thesis_seal": self.thesis_seal,
            "health_state": self.health_state,
            "policy_id": self.policy_id,
            "original_approved_risk_pct": (
                None if self.original_approved_risk_pct is None
                else str(self.original_approved_risk_pct)),
            "risk_after_action_pct": (
                None if self.risk_after_action_pct is None
                else str(self.risk_after_action_pct)),
            "changes_size": self.changes_size,
            "requires_authority": self.requires_authority,
            "authority": "PROPOSAL_ONLY_RISK_AUTHORITY_DECIDES",
            "proposed_ms": self.proposed_ms,
            "proposal_version": self.proposal_version,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class AdjustmentPolicyRegistry:
    """Per-capsule adjustment policy. Unregistered means HOLD_OR_EXIT."""

    def __init__(self, policies: Optional[Mapping[str, AdjustmentPolicy]] = None) -> None:
        self._by_strategy: dict[str, AdjustmentPolicy] = dict(policies or {})

    def register(self, strategy_id: str, policy: AdjustmentPolicy) -> AdjustmentPolicy:
        self._by_strategy[strategy_id] = policy
        return policy

    def policy_for(self, strategy_id: str) -> AdjustmentPolicy:
        return self._by_strategy.get(strategy_id, HOLD_OR_EXIT)

    def body(self) -> dict[str, Any]:
        return {
            "policies": {s: p.body() for s, p in sorted(self._by_strategy.items())},
            "default": HOLD_OR_EXIT.body(),
        }


class PositionAdjustmentEngine:
    """ThesisAssessment -> one proposal. Deterministic, and it cannot execute.

    This class deliberately imports nothing from `vati.execution` or
    `vati.risk.authority`. It produces a recommendation; the lifecycle turns a
    size-changing recommendation into a delta intent and sends it through the
    authority and the router, which is where it can be refused.
    """

    def __init__(self, *, ledger=None, policies: Optional[AdjustmentPolicyRegistry] = None,
                 producer: str = "vati-position-adjustment") -> None:
        self._ledger = ledger
        self._producer = producer
        self.policies = policies or AdjustmentPolicyRegistry()

    def propose(self, assessment, *, health, policy: Optional[AdjustmentPolicy] = None,
                original_approved_risk_pct: Optional[Decimal] = None,
                current_risk_pct: Optional[Decimal] = None,
                protection_at_break_even: bool = False,
                scale_policy: Optional[ScalePolicy] = None,
                scale_ins_used: int = 0,
                proposed_stop: Optional[Decimal] = None,
                now_ms: int = 0,
                persist: bool = True) -> PositionAdjustmentProposal:
        """The proposal for one position this cycle.

        Order of consideration is fixed: leave, then protect, then reduce, then
        bank, then add, then hold. Anything the policy does not permit falls
        through to the next weaker action, so a capsule that permits only HOLD
        and EXIT still gets a sound answer.
        """
        from vati.lifecycle.thesis import ThesisState

        pol = policy or self.policies.policy_for(assessment.strategy_id)
        reasons: list[str] = []
        state = assessment.state

        def with_action(action: Adjustment, rationale: str, **kw) -> PositionAdjustmentProposal:
            proposal = PositionAdjustmentProposal(
                trade_intent_id=assessment.trade_intent_id,
                symbol=assessment.symbol,
                strategy_id=assessment.strategy_id,
                action=action,
                reasons=tuple(reasons),
                rationale=rationale,
                thesis_state=state.value,
                thesis_seal=assessment.thesis_seal,
                health_state=health.state.value,
                policy_id=pol.policy_id,
                original_approved_risk_pct=original_approved_risk_pct,
                proposed_ms=now_ms,
                **kw,
            )
            if persist and self._ledger is not None:
                self._ledger.append(make_event(
                    EventKind.POSITION_ADJUSTMENT, self._producer,
                    proposal.body() | {"proposal_hash": proposal.digest},
                    event_time_ms=now_ms, received_time_ms=now_ms,
                    correlation_id=assessment.trade_intent_id))
            return proposal

        def note(reason: str) -> None:
            if reason not in reasons:
                reasons.append(reason)

        # --- 1. leave -----------------------------------------------------
        if state is ThesisState.INVALIDATED or health.is_urgent:
            note("THESIS_INVALIDATED" if state is ThesisState.INVALIDATED else "HEALTH_FAILING")
            if pol.allows(Adjustment.EXIT):
                return with_action(
                    Adjustment.EXIT,
                    "the reason for this position no longer holds; close it")
            note("POLICY_FORBIDS")

        # --- 2. protect ---------------------------------------------------
        weakening = state in (ThesisState.WEAKER, ThesisState.RISKIER, ThesisState.OVEREXTENDED)
        if weakening:
            note({
                ThesisState.WEAKER: "THESIS_WEAKER",
                ThesisState.RISKIER: "THESIS_RISKIER",
                ThesisState.OVEREXTENDED: "THESIS_OVEREXTENDED",
            }[state])
        if assessment.event_materiality > ZERO:
            note("EVENT_RISK")

        if weakening and proposed_stop is not None and pol.allows(Adjustment.MOVE_PROTECTION) \
                and not pol.allows(Adjustment.REDUCE):
            note("PROTECTION_CAN_TIGHTEN")
            return with_action(
                Adjustment.MOVE_PROTECTION,
                "the claim has weakened; tighten protection rather than carry it as approved",
                new_stop=proposed_stop)

        # --- 3. reduce ----------------------------------------------------
        if weakening:
            if pol.allows(Adjustment.REDUCE):
                return with_action(
                    Adjustment.REDUCE,
                    "evidence has moved against the claim; carry less of it",
                    size_fraction=pol.reduce_fraction)
            if proposed_stop is not None and pol.allows(Adjustment.MOVE_PROTECTION):
                note("PROTECTION_CAN_TIGHTEN")
                return with_action(
                    Adjustment.MOVE_PROTECTION,
                    "the claim has weakened and no reduction is permitted; tighten protection",
                    new_stop=proposed_stop)
            if pol.allows(Adjustment.EXIT) and state is ThesisState.INVALIDATED:
                return with_action(Adjustment.EXIT, "close a claim that no longer holds")
            note("POLICY_FORBIDS")

        # --- 4. bank ------------------------------------------------------
        if state is ThesisState.ASYMMETRIC and pol.allows(Adjustment.PARTIAL_TAKE) \
                and not pol.allows(Adjustment.ADD):
            note("THESIS_ASYMMETRIC")
            return with_action(
                Adjustment.PARTIAL_TAKE,
                "downside is bounded and the position is in front; bank part of it",
                size_fraction=pol.partial_take_fraction)

        # --- 5. add, under the original-risk ceiling ----------------------
        if state in (ThesisState.STRONGER, ThesisState.ASYMMETRIC) and pol.allows(Adjustment.ADD):
            note("THESIS_STRONGER" if state is ThesisState.STRONGER else "THESIS_ASYMMETRIC")
            add = self._add_or_none(
                assessment=assessment, health=health, policy=pol,
                original_approved_risk_pct=original_approved_risk_pct,
                current_risk_pct=current_risk_pct,
                protection_at_break_even=protection_at_break_even,
                scale_policy=scale_policy, scale_ins_used=scale_ins_used,
                note=note)
            if add is not None:
                delta, after = add
                return with_action(
                    Adjustment.ADD,
                    "protection is at or beyond break-even and the add stays inside the "
                    "risk originally approved for this position",
                    delta_risk_pct=delta,
                    risk_after_action_pct=after,
                    size_fraction=None)
            if pol.allows(Adjustment.PARTIAL_TAKE) and state is ThesisState.ASYMMETRIC:
                return with_action(
                    Adjustment.PARTIAL_TAKE,
                    "an add is not available; bank part of a bounded-downside position",
                    size_fraction=pol.partial_take_fraction)

        # --- 6. hold ------------------------------------------------------
        if not reasons:
            note("THESIS_INTACT" if state is ThesisState.INTACT else "THESIS_STRONGER")
        return with_action(
            Adjustment.HOLD,
            "the position stands as approved; nothing about it has changed enough to act on")

    def _add_or_none(self, *, assessment, health, policy: AdjustmentPolicy,
                     original_approved_risk_pct: Optional[Decimal],
                     current_risk_pct: Optional[Decimal],
                     protection_at_break_even: bool,
                     scale_policy: Optional[ScalePolicy],
                     scale_ins_used: int,
                     note) -> Optional[tuple[Decimal, Decimal]]:
        """The add's requested risk and resulting total, or None with a reason.

        Four conditions, all of which must hold. None of them is negotiable by
        a policy: a policy can only make this harder (INV-RISK-001).
        """
        if original_approved_risk_pct is None or original_approved_risk_pct <= ZERO:
            note("NO_ORIGINAL_RISK")
            return None
        if not protection_at_break_even:
            # Without this, an add converts an unrealised gain into exposure
            # that can still lose the original risk twice over.
            note("PROTECTION_BELOW_BREAK_EVEN")
            return None
        if health.blocks_scaling:
            note("HEALTH_BLOCKS_SCALING")
            return None

        sp = scale_policy or NO_SCALING
        if not sp.enabled:
            note("POLICY_FORBIDS")
            return None
        fraction = sp.fraction_for(scale_ins_used)
        if fraction is None:
            note("SCALE_POLICY_EXHAUSTED")
            return None
        if sp.required_health.rank < health.state.rank:
            note("HEALTH_BLOCKS_SCALING")
            return None

        remaining = original_approved_risk_pct - (current_risk_pct or ZERO)
        if remaining <= ZERO:
            note("RISK_BUDGET_SPENT")
            return None
        delta = min(original_approved_risk_pct * fraction, remaining)
        if delta <= ZERO:
            note("RISK_BUDGET_SPENT")
            return None
        after = (current_risk_pct or ZERO) + delta
        if after > original_approved_risk_pct:
            note("RISK_BUDGET_SPENT")
            return None
        return delta, after
