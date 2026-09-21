"""Model handoff and continuity state (TRD-REV51-132, G14).

Every Fable → Astra → Opus → Sol transition passes through here. The packet
sits in the owner-surfaces gate because the owner needs to see the chain, but
the reason it exists is narrower than reporting: a fallback that silently
restarts is worse than no fallback at all.

When the primary has already established something — the sealed context it was
answering, the missions it opened, the assessment it had got as far as — the
next model must resume from that, not re-derive it. Re-derivation is where
continuity bugs hide: the fallback reaches a different conclusion from
different inputs, and nothing in the record says the inputs differed. So
continuity is *carried*, as an explicit sealed payload, and the handoff record
names exactly what was carried.

The other half is the one thing a handoff may never do. It may not change the
control profile. A transition whose two sides disagree about controls is
refused outright rather than reconciled, because the reconciliation would
always be in the direction of the model that is still running — which is the
fallback, which is exactly the relaxation INV-MODEL-001 forbids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from vati.cognition.contracts import ModelRole
from vati.cognition.providers import CONTROL_PROFILE, ProviderLease
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event

PRODUCER = "vati-model-handoff"
HANDOFF_VERSION = "model-handoff/5.1.0"


class HandoffRefused(RuntimeError):
    """The transition would have changed more than which model answers."""


class HandoffReason(str, Enum):
    """Why the previous rung stopped being usable. Closed vocabulary."""

    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    AT_CONCURRENCY = "AT_CONCURRENCY"
    COOLING_DOWN = "COOLING_DOWN"
    DISABLED = "DISABLED"
    TIMEOUT = "TIMEOUT"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    RESULT_REFUSED = "RESULT_REFUSED"     # the normaliser rejected the answer
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


@dataclass(frozen=True)
class ContinuityState:
    """What the next model must be handed rather than work out again."""

    context_hash: str
    #: Assessment seals already produced for this context, oldest first. A
    #: fallback that contradicts one of these is visible as a contradiction.
    prior_assessment_seals: tuple[str, ...] = ()
    #: Research missions opened while working this context (118).
    open_mission_ids: tuple[str, ...] = ()
    #: Budget already spent on this context, so the fallback cannot restart
    #: the allowance by being a different model (096).
    spent_micros: int = 0
    invocations: int = 0
    #: Free-form notes the previous rung sealed. Read by the owner surface,
    #: never parsed for behaviour.
    notes: str = ""

    def body(self) -> dict[str, Any]:
        return {
            "context_hash": self.context_hash,
            "prior_assessment_seals": list(self.prior_assessment_seals),
            "open_mission_ids": list(self.open_mission_ids),
            "spent_micros": self.spent_micros,
            "invocations": self.invocations,
            "notes": self.notes,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())

    def advanced(self, *, assessment_seal: str = "", mission_ids: tuple[str, ...] = (),
                 spent_micros: int = 0, notes: str = "") -> "ContinuityState":
        seals = self.prior_assessment_seals + ((assessment_seal,) if assessment_seal else ())
        missions = tuple(dict.fromkeys(self.open_mission_ids + mission_ids))
        return ContinuityState(
            context_hash=self.context_hash,
            prior_assessment_seals=seals,
            open_mission_ids=missions,
            spent_micros=self.spent_micros + spent_micros,
            invocations=self.invocations + 1,
            notes=notes or self.notes,
        )


@dataclass(frozen=True)
class ModelHandoff:
    handoff_id: str
    from_model_id: str
    from_role: Optional[ModelRole]
    to_model_id: str
    to_role: ModelRole
    reason: HandoffReason
    continuity: ContinuityState
    control_profile: str
    occurred_ms: int
    handoff_version: str = HANDOFF_VERSION
    seal: str = ""

    def body(self) -> dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "from_model_id": self.from_model_id,
            "from_role": None if self.from_role is None else self.from_role.value,
            "to_model_id": self.to_model_id,
            "to_role": self.to_role.value,
            "reason": self.reason.value,
            "continuity": self.continuity.body(),
            "continuity_digest": self.continuity.digest,
            "control_profile": self.control_profile,
            "occurred_ms": self.occurred_ms,
            "handoff_version": self.handoff_version,
        }

    def sealed(self) -> "ModelHandoff":
        return ModelHandoff(**{**self.__dict__, "seal": canonical_hash(self.body())})

    def seal_ok(self) -> bool:
        return bool(self.seal) and self.seal == canonical_hash(self.body())

    @property
    def descended(self) -> bool:
        """True when this moved down the hierarchy, which is the normal case."""
        from vati.cognition.providers import HIERARCHY
        if self.from_role is None:
            return False
        return HIERARCHY.index(self.to_role) > HIERARCHY.index(self.from_role)


class HandoffRecorder:
    """Records transitions and carries continuity between them."""

    def __init__(self, *, ledger=None, producer: str = PRODUCER) -> None:
        self._ledger = ledger
        self._producer = producer
        self._handoffs: list[ModelHandoff] = []
        self._seq = 0

    def record(self, *, previous: Optional[ProviderLease], nxt: ProviderLease,
               reason: HandoffReason, continuity: ContinuityState,
               now_ms: int) -> ModelHandoff:
        if nxt.control_profile != CONTROL_PROFILE:
            raise HandoffRefused(
                f"{nxt.model_id} would run control profile {nxt.control_profile!r}, "
                f"not {CONTROL_PROFILE!r}")
        if previous is not None and previous.control_profile != nxt.control_profile:
            raise HandoffRefused(
                f"handoff {previous.model_id} -> {nxt.model_id} changes the control "
                f"profile; INV-MODEL-001 forbids a fallback relaxing controls")
        if previous is not None and previous.model_id == nxt.model_id:
            raise HandoffRefused(f"{nxt.model_id} cannot hand off to itself")
        if continuity.context_hash == "":
            raise HandoffRefused("handoff carries no context; continuity would be lost")

        self._seq += 1
        h = ModelHandoff(
            handoff_id=f"handoff-{now_ms}-{self._seq}",
            from_model_id="" if previous is None else previous.model_id,
            from_role=None if previous is None else previous.role,
            to_model_id=nxt.model_id,
            to_role=nxt.role,
            reason=reason,
            continuity=continuity,
            control_profile=nxt.control_profile,
            occurred_ms=now_ms,
        ).sealed()
        self._handoffs.append(h)
        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.MODEL_HANDOFF, self._producer, {**h.body(), "seal": h.seal},
                event_time_ms=now_ms, received_time_ms=now_ms,
                correlation_id=continuity.context_hash))
        return h

    def chain(self, context_hash: str) -> list[ModelHandoff]:
        """Every transition recorded for one context, in order."""
        return [h for h in self._handoffs if h.continuity.context_hash == context_hash]

    def all(self) -> list[ModelHandoff]:
        return list(self._handoffs)

    def summary(self) -> dict[str, Any]:
        by_reason: dict[str, int] = {}
        for h in self._handoffs:
            by_reason[h.reason.value] = by_reason.get(h.reason.value, 0) + 1
        return {
            "handoffs": len(self._handoffs),
            "by_reason": dict(sorted(by_reason.items())),
            "descents": sum(1 for h in self._handoffs if h.descended),
            "control_profile": CONTROL_PROFILE,
        }
