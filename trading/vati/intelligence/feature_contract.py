"""Required features become an executable contract (blueprint Rev 1.1 §5.2, P0-B).

Every capsule declares `required_features`. Nothing read that key, so a capsule
could name a feature it never received and trade anyway on whatever the engine
happened to compute. With eleven always-computed features that was latent; with a
growing registry it is a strategy trading blind on a dependency it declared.

Validation runs **per evaluation pass**, not only at admission: a feed can satisfy
the contract at startup and lose an input an hour later. The verdict is fail-closed
— an unsatisfied contract makes the capsule abstain with a reason code, and it
never falls back to "trade on the remaining features".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from vati.core.canonical import canonical_hash

#: The reason code a capsule abstains under. One code, so the owner surface and
#: the ledger agree on what happened.
FEATURE_CONTRACT_UNSATISFIED = "FEATURE_CONTRACT_UNSATISFIED"


@dataclass(frozen=True)
class FeatureContractVerdict:
    satisfied: bool
    missing: tuple[str, ...] = ()
    none_valued: tuple[str, ...] = ()
    stale: tuple[str, ...] = ()
    unsupported_for_venue: tuple[str, ...] = ()
    insufficient_history: tuple[str, ...] = ()
    bad_provenance: tuple[str, ...] = ()
    invalid_timeframe: tuple[str, ...] = ()
    degraded: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    verdict_hash: str = ""

    def as_dict(self) -> dict:
        return {
            "satisfied": self.satisfied, "missing": list(self.missing), "none_valued": list(self.none_valued),
            "stale": list(self.stale), "unsupported_for_venue": list(self.unsupported_for_venue),
            "insufficient_history": list(self.insufficient_history), "bad_provenance": list(self.bad_provenance),
            "invalid_timeframe": list(self.invalid_timeframe), "degraded": list(self.degraded),
            "reasons": list(self.reasons), "verdict_hash": self.verdict_hash,
        }

    def sealed(self) -> "FeatureContractVerdict":
        d = self.as_dict(); d.pop("verdict_hash")
        return FeatureContractVerdict(**{**self.__dict__, "verdict_hash": canonical_hash(d)})


@dataclass(frozen=True)
class FeatureAvailability:
    """What the state layer can actually supply for one feature, right now."""

    feature_id: str
    present: bool
    value_is_none: bool = False
    as_of_ms: Optional[int] = None
    timeframe: str = "UNKNOWN"
    venue_class: Optional[str] = None
    history_bars: Optional[int] = None
    provenance_ok: bool = True
    degraded: bool = False


@dataclass(frozen=True)
class FeatureRequirement:
    """What a capsule asked for. Only `feature_id` is mandatory."""

    feature_id: str
    timeframe: Optional[str] = None
    max_age_ms: Optional[int] = None
    minimum_history: Optional[int] = None
    venue_classes: frozenset[str] = field(default_factory=frozenset)


class FeatureContractValidator:
    """Deterministic, side-effect free. Every unmet condition is named."""

    def validate(
        self,
        *,
        requirements: Sequence[FeatureRequirement],
        available: Mapping[str, FeatureAvailability],
        now_ms: int,
        venue_class: Optional[str] = None,
    ) -> FeatureContractVerdict:
        missing: list[str] = []
        none_valued: list[str] = []
        stale: list[str] = []
        unsupported: list[str] = []
        short_history: list[str] = []
        bad_provenance: list[str] = []
        bad_timeframe: list[str] = []
        degraded: list[str] = []
        reasons: list[str] = []

        for req in requirements:
            av = available.get(req.feature_id)
            if av is None or not av.present:
                missing.append(req.feature_id)
                reasons.append(f"missing:{req.feature_id}")
                continue
            # A feature that is present but None is not a satisfied dependency.
            # This is the case the old code silently accepted.
            if av.value_is_none:
                none_valued.append(req.feature_id)
                reasons.append(f"none_value:{req.feature_id}")
            if req.timeframe is not None and av.timeframe != req.timeframe:
                bad_timeframe.append(req.feature_id)
                reasons.append(f"timeframe:{req.feature_id}:{av.timeframe}!={req.timeframe}")
            if req.max_age_ms is not None and av.as_of_ms is not None:
                age = now_ms - av.as_of_ms
                if age > req.max_age_ms:
                    stale.append(req.feature_id)
                    reasons.append(f"stale:{req.feature_id}:{age}ms>{req.max_age_ms}ms")
            effective_venue = av.venue_class or venue_class
            if req.venue_classes and effective_venue is not None and effective_venue not in req.venue_classes:
                unsupported.append(req.feature_id)
                reasons.append(f"venue:{req.feature_id}:{effective_venue}")
            if req.minimum_history is not None and av.history_bars is not None and av.history_bars < req.minimum_history:
                short_history.append(req.feature_id)
                reasons.append(f"history:{req.feature_id}:{av.history_bars}<{req.minimum_history}")
            if not av.provenance_ok:
                bad_provenance.append(req.feature_id)
                reasons.append(f"provenance:{req.feature_id}")
            if av.degraded:
                degraded.append(req.feature_id)
                reasons.append(f"degraded:{req.feature_id}")

        return FeatureContractVerdict(
            satisfied=not reasons,
            missing=tuple(missing), none_valued=tuple(none_valued), stale=tuple(stale),
            unsupported_for_venue=tuple(unsupported), insufficient_history=tuple(short_history),
            bad_provenance=tuple(bad_provenance), invalid_timeframe=tuple(bad_timeframe),
            degraded=tuple(degraded), reasons=tuple(reasons),
        ).sealed()


def availability_from_feature_vector(fv, *, venue_class: Optional[str] = None, history_bars: Optional[int] = None) -> dict[str, FeatureAvailability]:
    """Project the existing `FeatureVector` into availability facts.

    Compatibility shim: the current vector is a flat dataclass, so "present"
    means the attribute exists and "value_is_none" means it is None. A registry
    -backed vector supplies richer facts and replaces this.
    """
    skip = {"symbol", "as_of_ms", "complete", "feature_version", "timeframe"}
    out: dict[str, FeatureAvailability] = {}
    for name, value in fv.__dict__.items():
        if name in skip:
            continue
        out[name] = FeatureAvailability(
            feature_id=name, present=True, value_is_none=value is None,
            as_of_ms=fv.as_of_ms, timeframe=getattr(fv, "timeframe", "UNKNOWN"),
            venue_class=venue_class, history_bars=history_bars,
        )
    return out


#: Capsule vocabulary that does not match the snapshot attribute name. Kept
#: explicit rather than fuzzy-matching, so a typo in a capsule stays an error.
_CONTEXT_ALIASES = {"adv_20d": "adv_20d_shares"}


def availability_from_context(ctx: Any, *, as_of_ms: int, venue_class: Optional[str] = None,
                              timeframe: str = "UNKNOWN") -> dict[str, FeatureAvailability]:
    """Project non-price context (currently the ZSE snapshot) into availability.

    ZSE capsules declare fundamentals and liquidity that never lived in the price
    feature vector — `value_score`, `adv_20d`, `median_spread_pct`,
    `currency_regime`. Without this the contract would refuse every ZSE capsule,
    which is a false refusal rather than a caught dependency.
    """
    out: dict[str, FeatureAvailability] = {}
    snapshot = getattr(ctx, "zse", None) if ctx is not None else None
    if snapshot is None:
        return out
    fields = dict(snapshot.__dict__)
    for alias, real in _CONTEXT_ALIASES.items():
        if real in fields:
            fields[alias] = fields[real]
    for name, value in fields.items():
        if name in ("symbol", "exchange"):
            continue
        out[name] = FeatureAvailability(
            feature_id=name, present=True, value_is_none=value is None,
            as_of_ms=as_of_ms, timeframe=timeframe, venue_class=venue_class,
        )
    return out


def requirements_from_capsule(capsule: Any, *, timeframe: Optional[str] = None) -> tuple[FeatureRequirement, ...]:
    """Read `required_features` from a capsule document. This is the key nothing read."""
    data = getattr(capsule, "data", capsule)
    raw = data.get("required_features") or () if isinstance(data, dict) else ()
    return tuple(FeatureRequirement(feature_id=str(f), timeframe=timeframe) for f in raw)


__all__ = [
    "FEATURE_CONTRACT_UNSATISFIED",
    "FeatureAvailability",
    "FeatureContractValidator",
    "FeatureContractVerdict",
    "FeatureRequirement",
    "availability_from_context",
    "availability_from_feature_vector",
    "requirements_from_capsule",
]
