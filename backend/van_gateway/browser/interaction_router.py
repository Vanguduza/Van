"""Programme B contract B5 — the browser interaction router, and B1 enforced on the VAN side.

```
Browser Fabric → interaction router ─┬ deterministic typed Playwright/CDP
                                     ├ dial-jev PROPOSE_ACTION (only if B2 eligible)
                                     ├ Stagehand semantic fallback
                                     └ owner takeover / policy refusal
           → Browser Harness / Browser Control Agent → same Chromium → independent verifier
```

What this module is, and what it deliberately is not:

* **One Jev.** The Jev lane is a *client call* to the single DDS ``dial-jev`` service through an
  injected proposer. This module starts no service, opens no browser, holds no credential and
  keeps no ledger of its own. Execution happens through the injected executor — the existing
  Browser Harness / Browser Control Agent — in the session the caller names, fenced by the
  existing :class:`~van_gateway.browser.control_lease.ControlLeaseService` generation.
* **Jev proposes, never executes.** A Jev response is data. It is validated here against the
  caller's closed operation set and ephemeral targets (B1), converted into a :class:`TypedStep`
  whose fields are all members of caller-supplied sets, and only then handed to the executor.
  Nothing in a Jev response can name a selector, URL, script, credential or new operation.
* **Eligibility is injected and denies by default.** Until the B2 classifier is wired the
  router never takes the Jev lane. The classifier is anything with
  ``classify_observation(observation) -> EligibilityDecision`` (mapping or object).
* **`done` is VERIFYING.** Only the independent postcondition verifier yields
  ``VERIFIED_SUCCESS``. No lane — Jev, Stagehand or deterministic — can report success itself.
* **Owner touch wins.** Every execution runs under a lease watch: when the owner preempts
  (``ControlLeaseService.owner_preempt``) the generation moves, the in-flight operation is
  cancelled and the result is ``PREEMPTED``.
* **Jev outage never breaks VAN.** Any Jev failure — transport, timeout, invalid, stale,
  abstain — falls through to Stagehand, then to owner takeover.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

from van_gateway.browser.control_lease import ControlLeaseError, ControlLeaseService

# --------------------------------------------------------------------------- vocabulary

#: B1 — the canonical closed operation vocabulary. A caller may narrow it, never widen it.
JEV_CLOSED_OPERATIONS: frozenset[str] = frozenset(
    {"click", "fill", "select", "scroll", "press_key", "done", "abstain"}
)
#: B1 — the only operations that may carry ``target_id: null``.
NULL_TARGET_OPERATIONS: frozenset[str] = frozenset({"done", "abstain", "scroll"})
#: Operations that consume a caller-supplied value slot.
VALUE_OPERATIONS: frozenset[str] = frozenset({"fill", "select"})

#: B1 response schema. Unknown keys reject the whole response.
RESPONSE_KEYS: frozenset[str] = frozenset({"proposal", "confidence", "observation_epoch"})
PROPOSAL_KEYS: frozenset[str] = frozenset({"operation", "target_id", "value_ref"})

#: Action-class rank, including B1's A0 (no effect). VAN's ActionClass enum starts at A1; A0 is
#: accepted only on this wire.
CLASS_RANK: dict[str, int] = {"A0": 0, "A1": 1, "A2": 2, "A3": 3, "A4": 4, "A5": 5}
PROPOSABLE_CEILINGS: frozenset[str] = frozenset({"A0", "A1", "A2", "A3"})

#: The class an operation carries before its target is considered. Computed locally, never
#: taken from Jev.
OPERATION_BASE_CLASS: dict[str, str] = {
    "abstain": "A0",
    "done": "A0",
    "scroll": "A1",
    "press_key": "A2",
    "click": "A2",
    "fill": "A2",
    "select": "A2",
}

_TARGET_ID = re.compile(r"^t_[A-Za-z0-9_-]{1,64}$")


class Eligibility(str, Enum):
    """B2 classes, plus the router's own default for 'no classifier wired'."""

    PUBLIC_ELIGIBLE = "PUBLIC_ELIGIBLE"
    SANITIZABLE_ELIGIBLE = "SANITIZABLE_ELIGIBLE"
    OWNER_PRIVATE = "OWNER_PRIVATE"
    CREDENTIAL = "CREDENTIAL"
    TRADING_PROTECTED = "TRADING_PROTECTED"
    POLICY_DENIED = "POLICY_DENIED"
    #: Not a B2 class: what the default dependency returns. Never Jev-eligible.
    UNCLASSIFIED = "UNCLASSIFIED"


JEV_ELIGIBLE: frozenset[Eligibility] = frozenset(
    {Eligibility.PUBLIC_ELIGIBLE, Eligibility.SANITIZABLE_ELIGIBLE}
)


class Lane(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    JEV_PROPOSE_ACTION = "JEV_PROPOSE_ACTION"
    STAGEHAND = "STAGEHAND"
    OWNER_TAKEOVER = "OWNER_TAKEOVER"
    POLICY_REFUSAL = "POLICY_REFUSAL"


class RouteStatus(str, Enum):
    VERIFYING = "VERIFYING"
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    OWNER_TAKEOVER = "OWNER_TAKEOVER"
    POLICY_REFUSED = "POLICY_REFUSED"
    STALE_OBSERVATION = "STALE_OBSERVATION"
    PREEMPTED = "PREEMPTED"
    FAILED = "FAILED"


class ProposalRejected(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# --------------------------------------------------------------------------- data


@dataclass(frozen=True)
class InteractionTarget:
    """A caller-minted ephemeral target. Only ``target_id``, ``role`` and ``label`` go to Jev.

    ``action_class`` is the caller's own classification of actuating this element (a submit
    button may be A3, a payment control A4). It never leaves VAN, so Jev cannot see or argue it.
    """

    target_id: str
    role: str
    label: str
    action_class: str = "A2"

    def wire(self) -> dict[str, str]:
        return {"target_id": self.target_id, "role": self.role, "label": self.label}


@dataclass(frozen=True)
class TypedStep:
    """What the executor receives. Every field is a member of a caller-supplied set."""

    operation: str
    target_id: str | None
    value_ref: str | None
    lane: Lane
    action_class: str


@dataclass(frozen=True)
class InteractionRequest:
    session_id: str
    control_lease_id: str
    control_generation: int
    observation: Any
    observation_epoch: str
    targets: tuple[InteractionTarget, ...]
    closed_operation_set: frozenset[str] = JEV_CLOSED_OPERATIONS
    action_class_ceiling: str = "A2"
    value_slots: frozenset[str] = frozenset()
    #: A step the deterministic (Playwright/CDP) lane already knows. Tried first.
    deterministic_step: tuple[str, str | None, str | None] | None = None
    #: Optional ``van.browser.state.v1`` annotation. Recorded only; never authority.
    browser_state_annotation: Mapping[str, Any] | None = None

    def target(self, target_id: str | None) -> InteractionTarget | None:
        for item in self.targets:
            if item.target_id == target_id:
                return item
        return None


@dataclass
class RouteResult:
    lane: Lane
    status: RouteStatus
    reason: str
    step: TypedStep | None = None
    execution: dict[str, Any] | None = None
    trail: list[str] = field(default_factory=list)
    annotations: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- dependencies


class EligibilityClassifier(Protocol):
    def classify_observation(self, observation: Any) -> Any: ...


class DenyAllEligibility:
    """The default B2 dependency: nothing is Jev-eligible until a real classifier is wired."""

    def classify_observation(self, observation: Any) -> dict[str, Any]:
        return {
            "eligibility": Eligibility.UNCLASSIFIED.value,
            "reasons": ["eligibility_classifier_not_wired"],
            "data_class": None,
            "jev_payload": None,
        }


class JevProposer(Protocol):
    """Transport to the single ``dial-jev``. Returns the raw B1 response; never executes."""

    async def propose_action(self, payload: dict[str, Any]) -> Mapping[str, Any]: ...


class StepExecutor(Protocol):
    """The Browser Harness / Browser Control Agent. Resolves ``target_id`` to its own locator."""

    async def execute(self, step: TypedStep, *, request: InteractionRequest) -> dict[str, Any]: ...


class StagehandLane(Protocol):
    """The existing semantic fallback, acting in the same session under the same lease."""

    async def act(self, request: InteractionRequest) -> dict[str, Any]: ...


class PostconditionVerifier(Protocol):
    async def verify(
        self, request: InteractionRequest, step: TypedStep | None, execution: dict[str, Any] | None
    ) -> bool: ...


class EpochSource(Protocol):
    async def current_epoch(self, session_id: str) -> str: ...


# --------------------------------------------------------------------------- pure checks


def coerce_eligibility(decision: Any) -> tuple[Eligibility, Any]:
    """Accept a B2 decision as a mapping or an object; anything malformed is not eligible."""
    if isinstance(decision, Mapping):
        raw, payload = decision.get("eligibility"), decision.get("jev_payload")
    else:
        raw, payload = getattr(decision, "eligibility", None), getattr(decision, "jev_payload", None)
    raw = getattr(raw, "value", raw)
    try:
        eligibility = Eligibility(str(raw))
    except ValueError:
        return Eligibility.UNCLASSIFIED, None
    if eligibility not in JEV_ELIGIBLE:
        payload = None
    return eligibility, payload


def action_class_for(operation: str, target: InteractionTarget | None) -> str:
    """B1 — the caller computes the class from (operation, target). Jev has no say."""
    base = OPERATION_BASE_CLASS.get(operation, "A5")
    if target is None or operation in {"done", "abstain"}:
        return base
    target_class = target.action_class if target.action_class in CLASS_RANK else "A5"
    return base if CLASS_RANK[base] >= CLASS_RANK[target_class] else target_class


def check_request(request: InteractionRequest) -> None:
    """Refuse a request the router must never serve, whatever the lane."""
    if request.action_class_ceiling not in PROPOSABLE_CEILINGS:
        raise ProposalRejected(f"ceiling_prohibited:{request.action_class_ceiling}")
    extra = set(request.closed_operation_set) - JEV_CLOSED_OPERATIONS
    if extra:
        # A caller cannot smuggle an `execute`/`eval`/`navigate` primitive into the set.
        raise ProposalRejected("closed_operation_set_not_subset:" + ",".join(sorted(extra)))
    seen: set[str] = set()
    for target in request.targets:
        if not _TARGET_ID.fullmatch(target.target_id) or target.target_id in seen:
            raise ProposalRejected("target_id_invalid")
        seen.add(target.target_id)


def build_step(
    request: InteractionRequest,
    operation: Any,
    target_id: Any,
    value_ref: Any,
    *,
    lane: Lane,
) -> TypedStep:
    """B1 membership + class checks shared by the deterministic and Jev lanes."""
    if not isinstance(operation, str) or operation not in request.closed_operation_set:
        raise ProposalRejected("operation_not_in_closed_set")
    if target_id is None:
        if operation not in NULL_TARGET_OPERATIONS:
            raise ProposalRejected("target_required")
        target = None
    else:
        if operation in {"done", "abstain"}:
            raise ProposalRejected("target_not_allowed")
        if not isinstance(target_id, str):
            raise ProposalRejected("target_not_supplied")
        target = request.target(target_id)
        if target is None:
            raise ProposalRejected("target_not_supplied")
    if operation in VALUE_OPERATIONS:
        if not isinstance(value_ref, str) or value_ref not in request.value_slots:
            raise ProposalRejected("value_ref_not_supplied")
    elif value_ref is not None:
        raise ProposalRejected("value_ref_not_allowed")
    action_class = action_class_for(operation, target)
    if CLASS_RANK[action_class] >= CLASS_RANK["A4"]:
        raise ProposalRejected(f"action_class_never_proposable:{action_class}")
    if CLASS_RANK[action_class] > CLASS_RANK[request.action_class_ceiling]:
        raise ProposalRejected(f"action_class_above_ceiling:{action_class}")
    return TypedStep(operation, target_id, value_ref, lane, action_class)


def validate_proposal(response: Any, request: InteractionRequest) -> TypedStep:
    """B1 validator, VAN side. Anything off-contract raises :class:`ProposalRejected`."""
    if not isinstance(response, Mapping):
        raise ProposalRejected("response_not_object")
    unknown = set(response) - RESPONSE_KEYS
    if unknown:
        raise ProposalRejected("unknown_response_key")
    if response.get("observation_epoch") != request.observation_epoch:
        raise ProposalRejected("stale_observation_epoch")
    confidence = response.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
        raise ProposalRejected("confidence_invalid")
    proposal = response.get("proposal")
    if not isinstance(proposal, Mapping):
        raise ProposalRejected("proposal_not_object")
    if set(proposal) - PROPOSAL_KEYS:
        raise ProposalRejected("unknown_proposal_key")
    if "operation" not in proposal:
        raise ProposalRejected("operation_missing")
    return build_step(
        request,
        proposal.get("operation"),
        proposal.get("target_id"),
        proposal.get("value_ref"),
        lane=Lane.JEV_PROPOSE_ACTION,
    )


def propose_action_payload(request: InteractionRequest, jev_payload: Any) -> dict[str, Any]:
    """The B1 request. Every field is supplied by the caller (the Browser Fabric)."""
    return {
        "effect_direction": "PROPOSE_ACTION",
        "closed_operation_set": sorted(request.closed_operation_set),
        "targets": [target.wire() for target in request.targets],
        "action_class_ceiling": request.action_class_ceiling,
        "observation_epoch": request.observation_epoch,
        "observation": jev_payload,
    }


# --------------------------------------------------------------------------- the router


class InteractionRouter:
    def __init__(
        self,
        *,
        leases: ControlLeaseService,
        executor: StepExecutor | None = None,
        verifier: PostconditionVerifier | None = None,
        eligibility: EligibilityClassifier | None = None,
        jev: JevProposer | None = None,
        stagehand: StagehandLane | None = None,
        epochs: EpochSource | None = None,
        jev_timeout_seconds: float = 1.5,
        lease_poll_seconds: float = 0.05,
    ) -> None:
        self.leases = leases
        self.executor = executor
        self.verifier = verifier
        self.eligibility: EligibilityClassifier = eligibility or DenyAllEligibility()
        self.jev = jev
        self.stagehand = stagehand
        self.epochs = epochs
        self.jev_timeout_seconds = jev_timeout_seconds
        self.lease_poll_seconds = lease_poll_seconds

    def describe(self) -> dict[str, Any]:
        """Owner-facing read model of which lanes are wired. No secrets, no session data."""
        return {
            "lanes": [lane.value for lane in Lane],
            "deterministic_executor": self.executor is not None,
            "jev_service": "dial-jev" if self.jev is not None else None,
            "jev_eligibility_classifier": type(self.eligibility).__name__,
            "jev_lane_reachable": self.jev is not None
            and not isinstance(self.eligibility, DenyAllEligibility),
            "stagehand_fallback": self.stagehand is not None,
            "independent_verifier": self.verifier is not None,
        }

    async def route(self, request: InteractionRequest) -> RouteResult:
        trail: list[str] = []
        annotations: dict[str, Any] = {}
        if request.browser_state_annotation is not None:
            # van.browser.state.v1 is recorded as evidence. It cannot authorize anything.
            annotations["van.browser.state.v1"] = dict(request.browser_state_annotation)

        def result(lane: Lane, status: RouteStatus, reason: str, **kw: Any) -> RouteResult:
            return RouteResult(lane, status, reason, trail=trail, annotations=annotations, **kw)

        try:
            check_request(request)
        except ProposalRejected as exc:
            return result(Lane.POLICY_REFUSAL, RouteStatus.POLICY_REFUSED, exc.code)
        try:
            await self._assert_lease(request)
        except ControlLeaseError as exc:
            return result(Lane.OWNER_TAKEOVER, RouteStatus.OWNER_TAKEOVER, str(exc))

        # 1. deterministic typed Playwright/CDP
        if request.deterministic_step is not None and self.executor is not None:
            try:
                step = build_step(request, *request.deterministic_step, lane=Lane.DETERMINISTIC)
            except ProposalRejected as exc:
                trail.append(f"deterministic:{exc.code}")
            else:
                return await self._run_step(step, request, trail, annotations)

        # 2. dial-jev PROPOSE_ACTION, only when B2-eligible
        try:
            decision = self.eligibility.classify_observation(request.observation)
            eligibility, jev_payload = coerce_eligibility(decision)
        except Exception:  # noqa: BLE001 - a classifier fault is "not eligible", never "eligible"
            eligibility, jev_payload = Eligibility.UNCLASSIFIED, None
        trail.append(f"eligibility:{eligibility.value}")
        if eligibility in {Eligibility.TRADING_PROTECTED, Eligibility.POLICY_DENIED}:
            return result(Lane.POLICY_REFUSAL, RouteStatus.POLICY_REFUSED, f"eligibility:{eligibility.value}")
        if eligibility is Eligibility.CREDENTIAL:
            return result(Lane.OWNER_TAKEOVER, RouteStatus.OWNER_TAKEOVER, "credential_surface")

        if eligibility in JEV_ELIGIBLE and jev_payload is not None and self.jev is not None:
            outcome = await self._jev_lane(request, jev_payload, trail, annotations)
            if outcome is not None:
                return outcome
        elif eligibility in JEV_ELIGIBLE:
            trail.append("jev:unavailable")

        # 3. Stagehand semantic fallback
        if self.stagehand is not None:
            return await self._run_stagehand(request, trail, annotations)

        # 4. owner takeover
        return result(Lane.OWNER_TAKEOVER, RouteStatus.OWNER_TAKEOVER, "no_automated_lane")

    # ------------------------------------------------------------------ lanes

    async def _jev_lane(
        self, request: InteractionRequest, jev_payload: Any, trail: list[str], annotations: dict[str, Any]
    ) -> RouteResult | None:
        assert self.jev is not None
        try:
            response = await asyncio.wait_for(
                self.jev.propose_action(propose_action_payload(request, jev_payload)),
                timeout=self.jev_timeout_seconds,
            )
        except Exception:  # noqa: BLE001 - Jev outage is a fallback, never a VAN failure
            trail.append("jev:unavailable")
            return None
        try:
            step = validate_proposal(response, request)
        except ProposalRejected as exc:
            trail.append(f"jev:rejected:{exc.code}")
            return None
        if step.operation == "abstain":
            trail.append("jev:abstain")
            return None
        if self.epochs is not None:
            current = await self.epochs.current_epoch(request.session_id)
            if current != request.observation_epoch:
                trail.append("jev:stale_dom")
                return RouteResult(
                    Lane.JEV_PROPOSE_ACTION, RouteStatus.STALE_OBSERVATION, "observation_epoch_changed",
                    step=step, trail=trail, annotations=annotations,
                )
        if step.operation == "done":
            # B1 — `done` is a claim to verify, never success.
            return await self._verify(Lane.JEV_PROPOSE_ACTION, step, None, request, trail, annotations)
        if self.executor is None:
            trail.append("jev:no_executor")
            return None
        return await self._run_step(step, request, trail, annotations)

    async def _run_step(
        self, step: TypedStep, request: InteractionRequest, trail: list[str], annotations: dict[str, Any]
    ) -> RouteResult:
        assert self.executor is not None
        executor = self.executor
        return await self._guarded(
            step.lane, step, lambda: executor.execute(step, request=request), request, trail, annotations
        )

    async def _run_stagehand(
        self, request: InteractionRequest, trail: list[str], annotations: dict[str, Any]
    ) -> RouteResult:
        assert self.stagehand is not None
        stagehand = self.stagehand
        return await self._guarded(
            Lane.STAGEHAND, None, lambda: stagehand.act(request), request, trail, annotations
        )

    async def _guarded(
        self,
        lane: Lane,
        step: TypedStep | None,
        start: Any,
        request: InteractionRequest,
        trail: list[str],
        annotations: dict[str, Any],
    ) -> RouteResult:
        """Run one actuation under a live lease watch. Owner preemption cancels it."""
        try:
            await self._assert_lease(request)
        except ControlLeaseError as exc:
            return RouteResult(Lane.OWNER_TAKEOVER, RouteStatus.OWNER_TAKEOVER, str(exc),
                               step=step, trail=trail, annotations=annotations)
        task = asyncio.ensure_future(start())
        while True:
            done, _ = await asyncio.wait({task}, timeout=self.lease_poll_seconds)
            try:
                await self._assert_lease(request)
            except ControlLeaseError as exc:
                task.cancel()
                try:
                    await task
                except BaseException:  # noqa: BLE001 - the operation is being abandoned
                    pass
                trail.append(f"{lane.value.lower()}:preempted")
                return RouteResult(lane, RouteStatus.PREEMPTED, str(exc),
                                   step=step, trail=trail, annotations=annotations)
            if done:
                break
        try:
            execution = task.result()
        except Exception as exc:  # noqa: BLE001 - a failed actuation is reported, not retried here
            return RouteResult(lane, RouteStatus.FAILED, type(exc).__name__,
                               step=step, trail=trail, annotations=annotations)
        return await self._verify(lane, step, dict(execution or {}), request, trail, annotations)

    async def _verify(
        self,
        lane: Lane,
        step: TypedStep | None,
        execution: dict[str, Any] | None,
        request: InteractionRequest,
        trail: list[str],
        annotations: dict[str, Any],
    ) -> RouteResult:
        if self.verifier is None:
            return RouteResult(lane, RouteStatus.VERIFYING, "no_independent_verifier",
                               step=step, execution=execution, trail=trail, annotations=annotations)
        try:
            verified = await self.verifier.verify(request, step, execution)
        except Exception:  # noqa: BLE001 - an unverifiable outcome is not a success
            verified = False
        status = RouteStatus.VERIFIED_SUCCESS if verified is True else RouteStatus.VERIFICATION_FAILED
        return RouteResult(lane, status, "independent_verifier",
                           step=step, execution=execution, trail=trail, annotations=annotations)

    async def _assert_lease(self, request: InteractionRequest) -> None:
        await self.leases.assert_may_actuate(
            session_id=request.session_id,
            control_lease_id=request.control_lease_id,
            control_generation=request.control_generation,
        )


# --------------------------------------------------------------------------- fabric ranking


@dataclass(frozen=True)
class FabricAnnotation:
    """Jev's view of one caller-supplied ComputerInteractionFabric candidate. Data only."""

    candidate_id: str
    rank: int
    note: str | None = None


_RANKING_KEYS = frozenset({"ranking"})
_RANK_ENTRY_KEYS = frozenset({"candidate_id", "note"})


def annotate_fabric_operations(
    candidate_ids: Sequence[str], jev_response: Any
) -> list[FabricAnnotation]:
    """ORDER_ONLY over typed fabric operations the caller already built.

    Jev can reorder and annotate the candidates it was shown; it cannot add one, name an
    operation type, or return anything executable. Off-contract output yields the caller's
    original order, unannotated.
    """
    original = [FabricAnnotation(cid, index) for index, cid in enumerate(candidate_ids)]
    if not isinstance(jev_response, Mapping) or set(jev_response) - _RANKING_KEYS:
        return original
    ranking = jev_response.get("ranking")
    if not isinstance(ranking, list):
        return original
    known = set(candidate_ids)
    ordered: list[FabricAnnotation] = []
    seen: set[str] = set()
    for entry in ranking:
        if not isinstance(entry, Mapping) or set(entry) - _RANK_ENTRY_KEYS:
            return original
        cid = entry.get("candidate_id")
        note = entry.get("note")
        if cid not in known or cid in seen or (note is not None and not isinstance(note, str)):
            return original
        seen.add(cid)
        ordered.append(FabricAnnotation(cid, len(ordered), (note or None) and note[:200]))
    for cid in candidate_ids:
        if cid not in seen:
            ordered.append(FabricAnnotation(cid, len(ordered)))
    return ordered


__all__ = [
    "DenyAllEligibility",
    "Eligibility",
    "FabricAnnotation",
    "InteractionRequest",
    "InteractionRouter",
    "InteractionTarget",
    "JEV_CLOSED_OPERATIONS",
    "Lane",
    "ProposalRejected",
    "RouteResult",
    "RouteStatus",
    "TypedStep",
    "action_class_for",
    "annotate_fabric_operations",
    "build_step",
    "check_request",
    "coerce_eligibility",
    "propose_action_payload",
    "validate_proposal",
]
