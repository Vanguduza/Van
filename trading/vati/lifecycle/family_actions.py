"""Versioned native-leg action contracts; planning does not grant execution authority.

Family economics remain the existing weighted-average fold. These records bind
which original native positions an already authorized reduction may affect.
The candidate allocator is SHADOW until an existing authentic policy owner
resolves its eligibility; a caller-supplied binding is evidence, not a grant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
import hashlib
from pathlib import Path
from typing import Mapping

from vati.core.canonical import canonical_hash
from vati.risk.arithmetic import fraction

VERSION = "family-native-action/1"
PROPORTIONAL_FLOOR_V1 = "PROPORTIONAL_FLOOR_V1"
EXPLICIT_LEGS_V1 = "EXPLICIT_LEGS_V1"


class FamilyActionError(ValueError):
    pass


def exact_decimal(value: Fraction) -> Decimal:
    """Convert an expressible quantity without the caller's Decimal context."""
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        twos += 1
        denominator //= 2
    while denominator % 5 == 0:
        fives += 1
        denominator //= 5
    if denominator != 1:
        raise FamilyActionError("quantity is not expressible as a finite native decimal")
    scale = max(twos, fives)
    coefficient = abs(value.numerator) * 2 ** (scale - twos) * 5 ** (scale - fives)
    return Decimal((int(value < 0), tuple(int(x) for x in str(coefficient)), -scale))


def amount(value: Decimal, *, positive: bool = False) -> Fraction:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise FamilyActionError("native quantity must be a finite Decimal")
    result = fraction(value)
    if result < 0 or (positive and result == 0):
        raise FamilyActionError("native quantity is outside its allowed positive range")
    return result


def number(value: Decimal | Fraction | None):
    if value is None:
        return None
    value = fraction(value) if isinstance(value, Decimal) else value
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


@dataclass(frozen=True)
class NativeCloseRules:
    """An owner's verified close capability, separate from entry-size limits.

    References must resolve to current provider/configuration evidence at effect
    admission. This immutable value itself cannot certify a provider or grant a
    close. Full odd-lot close is deliberately independent of partial increments.
    """
    evidence_ref: str
    contract_ref: str
    quantity_quantum: Decimal | None
    partial_allowed: bool
    full_close_allowed: bool
    partial_min: Decimal = Decimal(0)
    partial_max: Decimal | None = None
    minimum_remaining: Decimal = Decimal(0)
    full_close_odd_lot: bool = True

    def __post_init__(self):
        if not self.evidence_ref or not self.contract_ref:
            raise FamilyActionError("native close capability requires original evidence and contract references")
        if self.quantity_quantum is not None:
            amount(self.quantity_quantum, positive=True)
        amount(self.partial_min)
        amount(self.minimum_remaining)
        if self.partial_max is not None:
            if amount(self.partial_max, positive=True) < amount(self.partial_min):
                raise FamilyActionError("native partial close bounds conflict")
        for value in (self.partial_allowed, self.full_close_allowed, self.full_close_odd_lot):
            if type(value) is not bool:
                raise FamilyActionError("native close capability flags must be explicit booleans")

    def body(self):
        return {"evidence_ref": self.evidence_ref, "contract_ref": self.contract_ref,
                "quantity_quantum": number(self.quantity_quantum),
                "partial_allowed": self.partial_allowed, "full_close_allowed": self.full_close_allowed,
                "partial_min": number(self.partial_min), "partial_max": number(self.partial_max),
                "minimum_remaining": number(self.minimum_remaining),
                "full_close_odd_lot": self.full_close_odd_lot}

    def bound_partial(self, requested: Fraction, remaining: Fraction) -> tuple[Fraction, str]:
        if not self.partial_allowed:
            return Fraction(0), "NATIVE_PARTIAL_CLOSE_UNAVAILABLE"
        if self.quantity_quantum is None:
            return Fraction(0), "NATIVE_CLOSE_QUANTUM_UNVERIFIED"
        quantum = amount(self.quantity_quantum, positive=True)
        capped = min(requested, remaining)
        if self.partial_max is not None:
            capped = min(capped, amount(self.partial_max))
        target = (capped // quantum) * quantum
        if 0 < remaining - target < amount(self.minimum_remaining):
            target = (max(Fraction(0), remaining - amount(self.minimum_remaining)) // quantum) * quantum
        if target <= 0:
            return Fraction(0), "BELOW_NATIVE_CLOSE_QUANTUM"
        if target < amount(self.partial_min):
            return Fraction(0), "BELOW_NATIVE_PARTIAL_MINIMUM"
        if target == remaining and not self.permits_full(remaining):
            return Fraction(0), "NATIVE_FULL_CLOSE_UNAVAILABLE"
        return target, "" if target == requested else "NATIVE_CONSTRAINT_RESIDUAL"

    def permits_full(self, remaining: Fraction) -> bool:
        if not self.full_close_allowed or remaining <= 0:
            return False
        if self.full_close_odd_lot:
            return True
        return (self.quantity_quantum is not None
                and remaining % amount(self.quantity_quantum, positive=True) == 0)


@dataclass(frozen=True)
class FamilyLeg:
    position_id: str
    trade_intent_id: str
    remaining: Decimal | None
    entry_price: Decimal
    stop: Decimal | None
    protection_confirmed: bool
    source_refs: tuple[str, ...]
    close_rules: NativeCloseRules | None

    def __post_init__(self):
        if not self.position_id or not self.trade_intent_id or not self.source_refs or any(not x for x in self.source_refs):
            raise FamilyActionError("native family leg requires original position, intent and source evidence")
        if self.remaining is not None:
            amount(self.remaining)
        amount(self.entry_price, positive=True)
        if self.stop is not None:
            amount(self.stop, positive=True)
        if type(self.protection_confirmed) is not bool:
            raise FamilyActionError("leg protection must be independently confirmed")

    def body(self):
        return {"position_id": self.position_id, "trade_intent_id": self.trade_intent_id,
                "remaining": number(self.remaining), "entry_price": number(self.entry_price),
                "stop": number(self.stop), "protection_confirmed": self.protection_confirmed,
                "source_refs": list(self.source_refs),
                "close_rules": self.close_rules.body() if self.close_rules is not None else None}


@dataclass(frozen=True)
class FamilySnapshot:
    family_id: str
    family_revision: str
    account_alias: str
    venue: str
    symbol: str
    direction: str
    legs: tuple[FamilyLeg, ...]
    membership_refs: tuple[str, ...]
    ambiguous: bool = False

    def __post_init__(self):
        if (not all((self.family_id, self.family_revision, self.account_alias, self.venue, self.symbol))
                or self.direction not in {"LONG", "SHORT"} or not self.membership_refs
                or any(not ref for ref in self.membership_refs)):
            raise FamilyActionError("original family scope and membership evidence are required")
        if not self.legs or len({x.position_id for x in self.legs}) != len(self.legs):
            raise FamilyActionError("family native position identities are missing or ambiguous")
        if type(self.ambiguous) is not bool:
            raise FamilyActionError("membership ambiguity must be explicit")

    @property
    def known(self):
        return not self.ambiguous and all(x.remaining is not None for x in self.legs)

    @property
    def remaining_exact(self):
        if not self.known:
            raise FamilyActionError("unknown original native quantities prevent automatic allocation")
        return sum((amount(x.remaining) for x in self.legs), Fraction(0))

    def body(self):
        return {"version": VERSION, "family_id": self.family_id, "family_revision": self.family_revision,
                "account_alias": self.account_alias, "venue": self.venue, "symbol": self.symbol,
                "direction": self.direction, "legs": [x.body() for x in sorted(self.legs, key=lambda x: x.position_id)],
                "membership_refs": list(self.membership_refs), "ambiguous": self.ambiguous}

    @property
    def digest(self):
        return canonical_hash(self.body())


def policy_implementation_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


@dataclass(frozen=True)
class FamilyPolicy:
    policy_id: str = "family-partial-reduction"
    version: str = PROPORTIONAL_FLOOR_V1
    mode: str = "SHADOW"
    qualification_ref: str | None = None
    implementation_source_hash: str = field(default_factory=policy_implementation_hash)

    def __post_init__(self):
        if not self.policy_id or self.version not in {PROPORTIONAL_FLOOR_V1, EXPLICIT_LEGS_V1}:
            raise FamilyActionError("family allocation policy identity is unavailable")
        if self.mode not in {"SHADOW", "ADMITTED"}:
            raise FamilyActionError("family policy mode is invalid")
        if self.mode == "ADMITTED" and not self.qualification_ref:
            raise FamilyActionError("policy admission evidence must be resolved by its existing owner")

    def body(self):
        return {"version": self.version, "policy_id": self.policy_id,
                "allocation": "EXACT_RATIONAL_FLOOR_EACH_NATIVE_QUANTUM" if self.version == PROPORTIONAL_FLOOR_V1 else "EXPLICIT_ORIGINAL_LEG_TARGETS",
                "redistribute_residual": False, "implicit_round_up": False}

    @property
    def implementation_hash(self):
        return self.implementation_source_hash

    @property
    def artifact_hash(self):
        return canonical_hash({"policy_id": self.policy_id, "version": self.version,
                               "implementation_hash": self.implementation_hash})

    @property
    def digest(self):
        return canonical_hash(self.body())


@dataclass(frozen=True)
class LegTarget:
    position_id: str
    trade_intent_id: str
    quantity: Decimal
    ideal_quantity: Fraction
    action: str
    reason: str = ""

    def body(self):
        return {"position_id": self.position_id, "trade_intent_id": self.trade_intent_id,
                "quantity": number(self.quantity), "ideal_quantity": number(self.ideal_quantity),
                "action": self.action, "reason": self.reason}


@dataclass(frozen=True)
class FamilyActionPlan:
    snapshot: FamilySnapshot
    policy: FamilyPolicy
    action: str
    requested_quantity: Decimal | None
    bounded_quantity: Decimal
    targets: tuple[LegTarget, ...]
    residual_quantity: Decimal | None
    reason: str
    authority_refs: tuple[tuple[str, str], ...]

    def body(self):
        return {"version": VERSION, "snapshot": self.snapshot.body(), "snapshot_ref": self.snapshot.digest,
                "policy": self.policy.body(), "policy_hash": self.policy.artifact_hash,
                "policy_source_hash": self.policy.implementation_hash,
                "policy_mode": self.policy.mode, "qualification_ref": self.policy.qualification_ref,
                "action": self.action, "requested_quantity": number(self.requested_quantity),
                "bounded_quantity": number(self.bounded_quantity),
                "targets": [x.body() for x in self.targets], "residual_quantity": number(self.residual_quantity),
                "reason": self.reason, "authority_refs": dict(self.authority_refs)}

    @property
    def digest(self):
        return canonical_hash(self.body())

    @property
    def allocated_exact(self):
        return sum((amount(x.quantity) for x in self.targets), Fraction(0))


BINDING_KEYS = frozenset({"original_mandate_ref", "current_mandate_ref", "grant_ref", "lease_ref", "fence_ref"})


def plan_reduction(snapshot: FamilySnapshot, *, policy: FamilyPolicy, action: str,
                   requested_quantity: Decimal | None = None,
                   explicit_targets: Mapping[str, Decimal] | None = None,
                   authority_refs: Mapping[str, str]) -> FamilyActionPlan:
    """Bind an inspectable plan. Current authority/eligibility is checked at dispatch."""
    if action not in {"PARTIAL_CLOSE", "FULL_CLOSE"}:
        raise FamilyActionError("family reduction action is invalid")
    if not BINDING_KEYS <= set(authority_refs) or any(not isinstance(authority_refs[k], str) or not authority_refs[k].strip() for k in BINDING_KEYS):
        raise FamilyActionError("original/current authority and lease/fence bindings are required")
    if action == "FULL_CLOSE" and explicit_targets is not None:
        raise FamilyActionError("full-family close binds every original leg; explicit partial targets are separate")
    if explicit_targets is not None and not set(explicit_targets) <= {x.position_id for x in snapshot.legs}:
        raise FamilyActionError("explicit target includes a foreign or manual position")
    if explicit_targets is not None and policy.version != EXPLICIT_LEGS_V1:
        raise FamilyActionError("explicit targets require their explicit policy binding")
    if explicit_targets is None and action == "PARTIAL_CLOSE" and policy.version != PROPORTIONAL_FLOOR_V1:
        raise FamilyActionError("automatic partial reduction requires PROPORTIONAL_FLOOR_V1")
    if requested_quantity is None and explicit_targets is not None:
        requested = sum((amount(x) for x in explicit_targets.values()), Fraction(0))
        if requested <= 0:
            raise FamilyActionError("explicit reduction quantity must be positive")
    elif requested_quantity is None:
        if action != "FULL_CLOSE" or not snapshot.known:
            raise FamilyActionError("a bound requested quantity is required")
        requested = snapshot.remaining_exact
    else:
        requested = amount(requested_quantity, positive=True)
    if explicit_targets is not None and sum((amount(x) for x in explicit_targets.values()), Fraction(0)) != requested:
        raise FamilyActionError("explicit per-leg quantities differ from their bound aggregate request")
    total = snapshot.remaining_exact if snapshot.known else Fraction(0)
    bounded = min(requested, total)
    targets = []
    for leg in sorted(snapshot.legs, key=lambda x: x.position_id):
        remaining = amount(leg.remaining) if leg.remaining is not None else Fraction(0)
        if not snapshot.known:
            ideal = target = Fraction(0)
            reason = "ORIGINAL_MEMBERSHIP_OR_QUANTITY_UNRESOLVED"
        elif action == "FULL_CLOSE":
            ideal = remaining
            target = remaining if leg.close_rules is not None and leg.close_rules.permits_full(remaining) else Fraction(0)
            reason = "" if target == remaining else "NATIVE_FULL_CLOSE_UNVERIFIED"
        else:
            ideal = (amount(explicit_targets.get(leg.position_id, Decimal(0))) if explicit_targets is not None
                     else bounded * remaining / total if total else Fraction(0))
            if ideal == 0:
                target, reason = Fraction(0), ""
            elif leg.close_rules is None:
                target, reason = Fraction(0), "NATIVE_CLOSE_CAPABILITY_UNVERIFIED"
            else:
                target, reason = leg.close_rules.bound_partial(ideal, remaining)
            if explicit_targets is not None and target != ideal:
                target, reason = Fraction(0), "EXPLICIT_NATIVE_TARGET_UNREPRESENTABLE"
        targets.append(LegTarget(leg.position_id, leg.trade_intent_id, exact_decimal(target), ideal, action, reason))
    allocated = sum((amount(x.quantity) for x in targets), Fraction(0))
    if allocated > requested or allocated > total:
        raise FamilyActionError("native leg targets exceed the original family request")
    residual = requested - allocated
    reason = ("ORIGINAL_MEMBERSHIP_OR_QUANTITY_UNRESOLVED" if not snapshot.known else
              "REQUEST_EXCEEDS_CONFIRMED_FAMILY" if requested > total else
              "UNALLOCATED_NATIVE_RESIDUAL" if residual else "")
    return FamilyActionPlan(snapshot, policy, action, exact_decimal(requested), exact_decimal(bounded),
                            tuple(targets), exact_decimal(residual), reason,
                            tuple(sorted((str(k), str(v)) for k, v in authority_refs.items())))


def plan_mandatory_full_close(snapshot, *, policy, authority_refs):
    """Bind known original full targets while retaining unknown obligations.

    Only the existing mandatory protection owner consumes this plan. Partial
    automatic allocation still requires a wholly known original snapshot.
    No quantity is invented for an absent/uncertain original native leg.
    """
    if snapshot.known:
        return plan_reduction(snapshot,policy=policy,action='FULL_CLOSE',authority_refs=authority_refs)
    if not BINDING_KEYS<=set(authority_refs) or any(not isinstance(authority_refs[k],str)
            or not authority_refs[k].strip() for k in BINDING_KEYS):
        raise FamilyActionError('original/current mandatory authority and fence are required')
    targets=[];known=Fraction(0)
    for leg in sorted(snapshot.legs,key=lambda x:x.position_id):
        if leg.remaining is None:
            targets.append(LegTarget(leg.position_id,leg.trade_intent_id,Decimal(0),Fraction(0),
                'FULL_CLOSE','ORIGINAL_NATIVE_QUANTITY_UNKNOWN'))
            continue
        remaining=amount(leg.remaining);known+=remaining
        permitted=remaining==0 or (leg.close_rules is not None and leg.close_rules.permits_full(remaining))
        targets.append(LegTarget(leg.position_id,leg.trade_intent_id,
            exact_decimal(remaining) if permitted else Decimal(0),remaining,'FULL_CLOSE',
            '' if permitted else 'NATIVE_FULL_CLOSE_UNVERIFIED'))
    return FamilyActionPlan(snapshot,policy,'FULL_CLOSE',None,exact_decimal(known),tuple(targets),None,
        'ORIGINAL_NATIVE_QUANTITY_UNKNOWN',tuple(sorted((str(k),str(v)) for k,v in authority_refs.items())))


def plan_from_body(body):
    """Decode original immutable journal data; never infer targets on replay."""
    def rational(value):
        return Fraction(int(value['numerator']),int(value['denominator']))
    def decimal(value):
        return None if value is None else exact_decimal(rational(value))
    raw=body['snapshot'];legs=[]
    for leg in raw['legs']:
        close=leg['close_rules']
        rules=None if close is None else NativeCloseRules(close['evidence_ref'],close['contract_ref'],
            decimal(close['quantity_quantum']),close['partial_allowed'],close['full_close_allowed'],
            decimal(close['partial_min']),decimal(close['partial_max']),decimal(close['minimum_remaining']),
            close['full_close_odd_lot'])
        legs.append(FamilyLeg(leg['position_id'],leg['trade_intent_id'],decimal(leg['remaining']),
            decimal(leg['entry_price']),decimal(leg['stop']),leg['protection_confirmed'],
            tuple(leg['source_refs']),rules))
    snapshot=FamilySnapshot(raw['family_id'],raw['family_revision'],raw['account_alias'],raw['venue'],
        raw['symbol'],raw['direction'],tuple(legs),tuple(raw['membership_refs']),raw['ambiguous'])
    policy=FamilyPolicy(policy_id=body['policy']['policy_id'],version=body['policy']['version'],
        mode=body['policy_mode'],qualification_ref=body['qualification_ref'],
        implementation_source_hash=body['policy_source_hash'])
    targets=tuple(LegTarget(t['position_id'],t['trade_intent_id'],decimal(t['quantity']),
        rational(t['ideal_quantity']),t['action'],t['reason']) for t in body['targets'])
    result=FamilyActionPlan(snapshot,policy,body['action'],decimal(body['requested_quantity']),
        decimal(body['bounded_quantity']),targets,decimal(body['residual_quantity']),body['reason'],
        tuple(sorted(body['authority_refs'].items())))
    if canonical_hash(result.body()) != canonical_hash(body):
        raise FamilyActionError('original family action plan schema/identity differs')
    return result
