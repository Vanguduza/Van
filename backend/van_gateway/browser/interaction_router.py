"""Programme B contract B5 — the browser interaction router (Jev x OpenMuse Convergence Rev 1).

One browser step, four lanes, in a fixed order:

1. **Deterministic** — a typed Playwright/CDP action the caller already knows
   (``DeterministicAction``), executed by the Browser Harness.
2. **dial-jev PROPOSE_ACTION** — only for an observation the B2 classifier
   (``classify_observation``, unit F) calls ``PUBLIC_ELIGIBLE`` or ``SANITIZABLE_ELIGIBLE``.
   Jev *proposes* one member of a closed operation set against an opaque target id. VAN then
   re-applies the B1 contract here in Python (defence in depth) before anything executes.
3. **Stagehand semantic fallback** — Stagehand ``observe`` proposes one action; the Harness
   performs it (Stagehand ``act`` is not used here, see ``StagehandSemanticFallback``).
4. **Owner takeover / policy refusal** — nothing above produced a safe action, or policy
   refused the one that was produced.

Invariants this module owns (each has a test that removes it and watches it fail):

* default eligibility denies everything; an ineligible observation never reaches Jev;
* a missing eligibility classifier, verifier, executor or Jev client **disables** the Jev lane
  with a recorded reason — it is never silently skipped;
* Jev never executes. The injected executor (Browser Harness) executes;
* a Jev proposal is acted on only when dial-jev returns ``apply_effect: true`` under an
  ``ACTIVE``/``ACTIVE_GATED`` lifecycle. A SHADOW proposal (every one today, blueprint §11)
  is re-validated, counted and compared with what the next lane did, and never executed;
* only the independent postcondition verifier yields ``VERIFIED_SUCCESS``; a Jev ``done`` is a
  claim and moves the step to ``VERIFYING``;
* the router itself is reachable only when ``browser_interaction_router_enabled`` is set
  (default ``False``).

External repositories (browser-use/jev-ultrafast, browserbase/stagehand) are reference only
under DEC-039; nothing here is copied from them.
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Protocol

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from van_gateway.automation.payments import PaymentBoundaryError, assert_not_automated_payment
from van_gateway.automation.verifier import (
    PostconditionSpec,
    VerificationOutcome,
    VerificationResult,
    WorkflowVerifier,
)
from van_gateway.action.models import VerifierType
from van_gateway.browser.adapters import BrowserAdapterError
from van_gateway.browser.models import BrowserTask, BrowserTaskStatus
from van_gateway.browser.policy import BrowserPolicyError
from van_gateway.browser.stagehand_proposal import (
    SemanticProposalRefused,
    typed_action_from_stagehand,
)

# ------------------------------------------------------------------------ B1 vocabulary

B1_OPERATIONS: tuple[str, ...] = ("click", "fill", "select", "scroll", "press_key", "done", "abstain")
B1_ACTION_CLASSES: tuple[str, ...] = ("A0", "A1", "A2", "A3", "A4", "A5")
PROPOSABLE_ACTION_CLASSES = frozenset({"A0", "A1", "A2", "A3"})
NEVER_PROPOSABLE_ACTION_CLASSES = frozenset({"A4", "A5"})
TARGETLESS_OPERATIONS = frozenset({"done", "abstain", "scroll"})
ELIGIBLE_CLASSES = frozenset({"PUBLIC_ELIGIBLE", "SANITIZABLE_ELIGIBLE"})
PAYLOAD_SCHEMA = "van.browser.action_payload.v1"
_PAYLOAD_KEYS = frozenset({
    "payload_schema", "effect_direction", "closed_operation_set", "origin_class",
    "targets", "action_class_ceiling", "observation_epoch",
})
_OPTIONAL_PAYLOAD_KEYS = frozenset({"value_slots"})
_TARGET_KEYS = frozenset({"target_id", "role", "label"})
_TARGET_ID = re.compile(r"^t_[A-Za-z0-9_-]{1,64}$")
_VALUE_SLOT_ID = re.compile(r"^v_[A-Za-z0-9_-]{1,64}$")
_EPOCH = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ORIGIN_CLASSES = frozenset({"PUBLIC_ALLOWLISTED", "PUBLIC_UNLISTED"})


def _rank(action_class: str) -> int:
    return B1_ACTION_CLASSES.index(action_class)


#: Task states a step may run in — the same pair ``/v1/browser/assignments`` admits.
RUNNABLE_TASK_STATUSES = frozenset({BrowserTaskStatus.PENDING, BrowserTaskStatus.RESUME_AUTHORIZED})


def effective_step_ceiling(step_ceiling: str, task: BrowserTask) -> str:
    """Reviewer I M-8 — a step can never act above the class the task was admitted at.

    The caller's ceiling is capped at ``task.action_class``; a task class VAN does not know
    caps to A0 (nothing but done/scroll/abstain), never upward.
    """
    task_class = getattr(getattr(task, "action_class", None), "value", getattr(task, "action_class", None))
    if not isinstance(task_class, str) or task_class not in B1_ACTION_CLASSES:
        return "A0"
    return task_class if _rank(task_class) < _rank(step_ceiling) else step_ceiling


class B1ValidationError(ValueError):
    """The B1 payload or a Jev proposal failed VAN's own re-validation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# ------------------------------------------------------------------------ public types


class RouterLane(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    JEV = "JEV"
    STAGEHAND = "STAGEHAND"
    OWNER_TAKEOVER = "OWNER_TAKEOVER"
    POLICY_REFUSAL = "POLICY_REFUSAL"


class StepState(str, Enum):
    PROPOSED = "PROPOSED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    #: The verifier observed the postcondition false. The router falls back to the next lane.
    NOT_SATISFIED = "NOT_SATISFIED"
    #: The verifier could not observe the postcondition (none declared, no observer, verifier
    #: absent or failing). Never success; terminal, and escalated to the owner.
    UNVERIFIABLE = "UNVERIFIABLE"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    OWNER_TAKEOVER = "OWNER_TAKEOVER"
    POLICY_REFUSED = "POLICY_REFUSED"


class DeterministicAction(BaseModel):
    """A typed action the caller already knows. No model involved."""

    operation: str
    locator: str | None = None
    #: ``secretref://`` for fill, a key name for press_key.
    value_ref: str | None = None


@dataclass(frozen=True)
class RouterAction:
    """What the executor receives. Always the fabric's own locator, never a Jev string."""

    lane: RouterLane
    operation: str
    locator: str | None
    value_ref: str | None
    action_class: str | None
    target_id: str | None = None
    #: Only the Stagehand lane: the observed Stagehand action, kept as evidence. It is never
    #: replayed through Stagehand; the Harness performs ``operation`` on ``locator``.
    semantic_action: dict[str, Any] | None = None
    #: Human-readable text of what is acted on (target label / Stagehand description),
    #: checked by the payment boundary exactly as the subagent runner checks instructions.
    description: str | None = None


@dataclass
class InteractionStep:
    task: BrowserTask
    #: B1 ceiling for this step, in B1 vocabulary (A0..A3).
    action_class_ceiling: str
    closed_operation_set: tuple[str, ...] = ("click", "fill", "select", "scroll", "press_key", "done", "abstain")
    deterministic_action: DeterministicAction | None = None
    postcondition: PostconditionSpec | None = None
    semantic_instruction: str | None = None
    #: B1 value slot id -> reference the executor resolves (secretref:// or key name).
    value_slots: dict[str, str] = field(default_factory=dict)
    #: The page observation for B2. When ``None`` the router asks its observer.
    observation: dict[str, Any] | None = None
    #: Set by the Jev lane when dial-jev proposed without effect (SHADOW): what Jev would
    #: have done, kept for the shadow comparison. Never executed.
    shadow_jev: dict[str, Any] | None = None


@dataclass
class StepResult:
    lane: RouterLane
    state: StepState
    trail: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    jev_consulted: bool = False
    eligibility_class: str | None = None
    action: RouterAction | None = None
    verification: VerificationResult | None = None
    #: Earlier lanes whose action executed and was NOT_SATISFIED before this one.
    attempts: list[dict[str, Any]] = field(default_factory=list)
    #: True when automation stops and the owner must look (UNVERIFIABLE, takeover).
    escalated: bool = False
    #: The SHADOW Jev proposal for this step, if any, and whether the lane that did act
    #: agreed with it. Evidence for §8 only; it never influenced what executed.
    shadow_jev: dict[str, Any] | None = None

    @property
    def verified_success(self) -> bool:
        return self.state is StepState.VERIFIED_SUCCESS

    def to_json(self) -> dict[str, Any]:
        return {
            "lane": self.lane.value,
            "state": self.state.value,
            "trail": list(self.trail),
            "reasons": list(self.reasons),
            "jev_consulted": self.jev_consulted,
            "eligibility_class": self.eligibility_class,
            "action": None if self.action is None else {
                "lane": self.action.lane.value,
                "operation": self.action.operation,
                "target_id": self.action.target_id,
                "action_class": self.action.action_class,
            },
            "verification": None if self.verification is None else {
                "outcome": self.verification.outcome.value,
                "detail": self.verification.detail,
            },
            "attempts": list(self.attempts),
            "escalated": self.escalated,
            "shadow_jev": None if self.shadow_jev is None else dict(self.shadow_jev),
            "verified_success": self.verified_success,
        }


# ------------------------------------------------------------------------ dependencies


class ActionExecutor(Protocol):
    """The Browser Harness / Browser Control Agent. The only thing that acts on the page."""

    async def execute(self, task: BrowserTask, action: RouterAction) -> dict[str, Any]: ...


class PostconditionVerifier(Protocol):
    """Independent of the executor and of Jev. The only source of VERIFIED_SUCCESS."""

    async def verify(
        self, task: BrowserTask, action: RouterAction,
        postcondition: PostconditionSpec | None, *, claimed_done: bool,
    ) -> VerificationResult: ...


class SemanticFallback(Protocol):
    """Stagehand: observe, then propose one observed action (or ``None``)."""

    async def propose(self, task: BrowserTask, step: InteractionStep) -> RouterAction | None: ...


class JevProposer(Protocol):
    async def propose_action(
        self, *, request: dict[str, Any], caller_action_classes: list[dict[str, Any]],
        current_epoch: str,
    ) -> Any: ...


PageObserver = Callable[[BrowserTask], Awaitable[dict[str, Any]]]
#: Locator -> what the Browser Harness observes of that element (role, accessible name,
#: attributes), or ``None`` when the Harness cannot resolve it.
TargetResolver = Callable[[BrowserTask, str], Awaitable[dict[str, Any] | None]]
EligibilityClassifier = Callable[..., Any]
ActionClassifier = Callable[[str, dict[str, Any] | None, Any], str]


_HIGH_RISK_LABEL = re.compile(
    r"\b(pay|payment|purchase|buy|checkout|order|transfer|send|submit|confirm|delete|remove|"
    r"sign|authori[sz]e|approve|subscribe|withdraw|deposit)\b",
    re.IGNORECASE,
)


def default_action_classifier(operation: str, target: dict[str, Any] | None, target_entry: Any) -> str:
    """VAN's own (operation, target) -> action class. Conservative by construction.

    ``done``/``scroll``/``abstain`` change nothing -> A0. Anything whose label reads as a
    commitment (pay, submit, delete, send ...) -> A4, which is never proposable. ``fill``
    writes owner data -> A3. Other clicks/selects/keys -> A2. A class the fabric attached to
    the target (``target_entry["action_class"]``) can only raise this, never lower it.
    """
    if operation in TARGETLESS_OPERATIONS:
        base = "A0"
    elif target is not None and _HIGH_RISK_LABEL.search(str(target.get("label") or "")):
        base = "A4"
    elif operation == "fill":
        base = "A3"
    else:
        base = "A2"
    declared = target_entry.get("action_class") if isinstance(target_entry, dict) else None
    if isinstance(declared, str) and declared in B1_ACTION_CLASSES and _rank(declared) > _rank(base):
        return declared
    return base


_ELEMENT_TEXT_KEYS = (
    "role", "label", "name", "accessible_name", "aria_label", "text", "title", "value",
    "placeholder", "input_type", "type", "id", "href", "action", "formaction",
)


def _words(text: str) -> str:
    """Selector/attribute text as words: ``//button[@id='payNow_btn']`` -> ``button id pay Now btn``.

    ``_HIGH_RISK_LABEL`` and the payment boundary match whole words, and a selector joins
    them with punctuation, underscores and camelCase, all of which hide a word boundary.
    """
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "")
    return re.sub(r"[^A-Za-z0-9]+", " ", text).strip()


def observed_element_text(element: dict[str, Any], locator: str | None) -> str:
    """Everything the Harness observed about the element, plus the selector, as one text.

    This — not the proposer's own description — is what the action class and the payment
    boundary are judged on (reviewer I M-5).
    """
    parts: list[str] = []
    for key in _ELEMENT_TEXT_KEYS:
        value = element.get(key)
        if isinstance(value, str) and value:
            parts.append(value)
    attributes = element.get("attributes")
    if isinstance(attributes, dict):
        for name, value in attributes.items():
            if isinstance(value, str):
                parts.append(f"{name} {value}")
    if locator:
        parts.append(locator)
    return " | ".join(parts + [_words(p) for p in parts])


class HarnessTargetResolver:
    """Resolves a Stagehand locator to the element the Browser Harness itself reports.

    Uses the ``elements`` list of the Harness ``page_info`` (the same list B2 reads). An
    element is resolved only when its ``ref`` is exactly the locator the Harness will act
    on. The live Harness does not report elements today, so this resolves nothing and every
    targeted Stagehand action goes to owner takeover — the fail-closed answer.
    """

    def __init__(self, harness: Any) -> None:
        self.harness = harness

    async def __call__(self, task: BrowserTask, locator: str) -> dict[str, Any] | None:
        page = await self.harness.page_info(task)
        for raw in (page or {}).get("elements") or ():
            if isinstance(raw, dict) and raw.get("ref") == locator:
                return raw
        return None


def load_eligibility_classifier() -> EligibilityClassifier | None:
    """Unit F's ``classify_observation``, imported lazily; ``None`` when it is not built."""
    try:
        from van_gateway.browser import jev_eligibility  # type: ignore[attr-defined]
    except ImportError:
        return None
    return getattr(jev_eligibility, "classify_observation", None)


# ------------------------------------------------------------------------ B1 re-validation


def validate_b1_payload(payload: Any, *, ceiling: str, closed_operation_set: tuple[str, ...]) -> dict[str, Any]:
    """Re-check the B2 payload against B1 before it leaves VAN. Returns the B1 *request*
    (payload minus ``payload_schema`` and ``origin_class``)."""
    if not isinstance(payload, dict):
        raise B1ValidationError("PAYLOAD_NOT_OBJECT")
    keys = set(payload)
    if not _PAYLOAD_KEYS <= keys:
        raise B1ValidationError(f"PAYLOAD_KEY_MISSING:{sorted(_PAYLOAD_KEYS - keys)[0]}")
    unknown = keys - _PAYLOAD_KEYS - _OPTIONAL_PAYLOAD_KEYS
    if unknown:
        raise B1ValidationError(f"PAYLOAD_UNKNOWN_KEY:{sorted(unknown)[0]}")
    if payload["payload_schema"] != PAYLOAD_SCHEMA:
        raise B1ValidationError("PAYLOAD_SCHEMA_MISMATCH")
    if payload["effect_direction"] != "PROPOSE_ACTION":
        raise B1ValidationError("EFFECT_DIRECTION_MISMATCH")
    if payload["origin_class"] not in _ORIGIN_CLASSES:
        raise B1ValidationError("ORIGIN_CLASS_INVALID")
    ops = payload["closed_operation_set"]
    if not isinstance(ops, list) or not ops or len(set(ops)) != len(ops):
        raise B1ValidationError("OPERATION_SET_INVALID")
    for op in ops:
        if op not in B1_OPERATIONS:
            raise B1ValidationError(f"OPERATION_NOT_CLOSED:{op}")
        if op not in closed_operation_set:
            raise B1ValidationError(f"OPERATION_OUTSIDE_STEP_SET:{op}")
    targets = payload["targets"]
    if not isinstance(targets, list):
        raise B1ValidationError("TARGETS_INVALID")
    seen: set[str] = set()
    for target in targets:
        if not isinstance(target, dict) or set(target) != _TARGET_KEYS:
            raise B1ValidationError("TARGET_SHAPE_INVALID")
        tid = target["target_id"]
        if not isinstance(tid, str) or not _TARGET_ID.match(tid):
            raise B1ValidationError("TARGET_ID_INVALID")
        if tid in seen:
            raise B1ValidationError("TARGET_ID_DUPLICATE")
        seen.add(tid)
        for key in ("role", "label"):
            if not isinstance(target[key], str) or len(target[key]) > 200:
                raise B1ValidationError(f"TARGET_{key.upper()}_INVALID")
    payload_ceiling = payload["action_class_ceiling"]
    if payload_ceiling in NEVER_PROPOSABLE_ACTION_CLASSES:
        raise B1ValidationError("CEILING_NEVER_PROPOSABLE")
    if payload_ceiling not in PROPOSABLE_ACTION_CLASSES:
        raise B1ValidationError("CEILING_INVALID")
    if _rank(payload_ceiling) > _rank(ceiling):
        raise B1ValidationError("PAYLOAD_CEILING_ABOVE_STEP_CEILING")
    epoch = payload["observation_epoch"]
    if not isinstance(epoch, str) or not _EPOCH.match(epoch):
        raise B1ValidationError("EPOCH_INVALID")
    request = {k: payload[k] for k in (
        "effect_direction", "closed_operation_set", "targets", "action_class_ceiling", "observation_epoch",
    )}
    if "value_slots" in payload:
        slots = payload["value_slots"]
        if not isinstance(slots, list) or not all(isinstance(s, str) and _VALUE_SLOT_ID.match(s) for s in slots):
            raise B1ValidationError("VALUE_SLOTS_INVALID")
        request["value_slots"] = list(slots)
    return request


def validate_jev_proposal(
    *,
    request: dict[str, Any],
    proposal: Any,
    current_epoch: str | None,
    classify: Callable[[str, dict[str, Any] | None], str],
    jev_action_class: str | None = None,
) -> tuple[str, dict[str, Any] | None, str]:
    """VAN-side B1 re-validation of a Jev proposal. Returns (operation, target, class).

    Raises ``B1ValidationError`` for every violation; the router treats that as ABSTAIN.
    """
    if not isinstance(proposal, dict) or set(proposal) != {"operation", "target_id", "value_ref"}:
        raise B1ValidationError("PROPOSAL_SHAPE_INVALID")
    operation = proposal["operation"]
    if not isinstance(operation, str) or operation not in request["closed_operation_set"]:
        raise B1ValidationError("OPERATION_NOT_IN_CLOSED_SET")
    if operation == "abstain":
        raise B1ValidationError("JEV_ABSTAINED")
    target_id = proposal["target_id"]
    target: dict[str, Any] | None = None
    if target_id is None:
        if operation not in TARGETLESS_OPERATIONS:
            raise B1ValidationError("TARGET_REQUIRED")
    else:
        target = next((t for t in request["targets"] if t["target_id"] == target_id), None)
        if target is None:
            raise B1ValidationError("TARGET_NOT_SUPPLIED")
    value_ref = proposal["value_ref"]
    if value_ref is not None and value_ref not in (request.get("value_slots") or []):
        raise B1ValidationError("VALUE_REF_NOT_SUPPLIED")
    if not current_epoch or request["observation_epoch"] != current_epoch:
        raise B1ValidationError("STALE_OBSERVATION_EPOCH")
    action_class = classify(operation, target)
    if action_class not in B1_ACTION_CLASSES:
        raise B1ValidationError("ACTION_CLASS_UNKNOWN")
    if action_class in NEVER_PROPOSABLE_ACTION_CLASSES:
        raise B1ValidationError("ACTION_CLASS_NEVER_PROPOSABLE")
    if _rank(action_class) > _rank(request["action_class_ceiling"]):
        raise B1ValidationError("ACTION_CLASS_ABOVE_CEILING")
    if jev_action_class is not None and jev_action_class != action_class:
        # dial-jev echoes the class it was told; a different one means the two sides
        # disagree about what this action is, and VAN does not guess which is right.
        raise B1ValidationError("ACTION_CLASS_DISAGREES_WITH_JEV")
    return operation, target, action_class


# ------------------------------------------------------------------------ metrics (§8)


class RouterMetrics:
    """The §8 pre-registered counters. Every rate is published with its denominator."""

    COUNTERS = (
        "total_steps",
        "deterministic_steps",
        "jev_candidate_steps",
        "eligible_steps",
        "b2_privacy_rejections",
        "dds_egress_rejections",
        "jev_lane_disabled_steps",
        "jev_calls",
        "jev_responses",
        "jev_proposals_received",
        "jev_fallbacks",
        "jev_stale_rejections",
        "jev_executed",
        "jev_executed_verified_success",
        "jev_wrong_actions",
        "jev_done_proposals",
        "jev_done_postcondition_failures",
        #: Reviewer I M-3 — proposals dial-jev returned without effect (SHADOW). Counted,
        #: re-validated and compared, never executed.
        "jev_shadow_proposals",
        "jev_shadow_valid",
        "jev_shadow_comparisons",
        "jev_shadow_agreements",
        "stagehand_steps",
        "owner_takeovers",
        "policy_refusals",
    )

    def __init__(self) -> None:
        self.counts: dict[str, int] = {name: 0 for name in self.COUNTERS}

    def inc(self, name: str, by: int = 1) -> None:
        if name not in self.counts:
            raise KeyError(name)
        self.counts[name] += by

    def record_owner_judged_wrong(self) -> None:
        """An owner said an executed Jev proposal was wrong (verifier passed it)."""
        self.inc("jev_wrong_actions")

    @staticmethod
    def _rate(numerator: int, denominator: int) -> dict[str, Any]:
        return {
            "numerator": numerator,
            "denominator": denominator,
            "rate": (numerator / denominator) if denominator else None,
        }

    def snapshot(self) -> dict[str, Any]:
        c = self.counts
        return {
            "counters": dict(c),
            "metrics": {
                "total_steps": c["total_steps"],
                "eligible_steps": c["eligible_steps"],
                "eligibility_rate": self._rate(c["eligible_steps"], c["total_steps"]),
                "success_on_eligible_set": self._rate(c["jev_executed_verified_success"], c["jev_executed"]),
                "fallback_rate": self._rate(c["jev_fallbacks"], c["eligible_steps"]),
                "wrong_action_rate": self._rate(c["jev_wrong_actions"], c["jev_executed"]),
                "stale_action_rate": self._rate(c["jev_stale_rejections"], c["jev_responses"]),
                "privacy_rejection_rate": self._rate(
                    c["b2_privacy_rejections"] + c["dds_egress_rejections"], c["total_steps"]
                ),
                "postcondition_failure_rate": self._rate(
                    c["jev_done_postcondition_failures"], c["jev_done_proposals"]
                ),
                "shadow_validity_rate": self._rate(c["jev_shadow_valid"], c["jev_shadow_proposals"]),
                "shadow_agreement_rate": self._rate(
                    c["jev_shadow_agreements"], c["jev_shadow_comparisons"]
                ),
            },
            "definitions": {
                "eligible_steps": "steps whose B2 class is PUBLIC_ELIGIBLE or SANITIZABLE_ELIGIBLE; "
                                  "B2 runs only for steps the deterministic lane did not resolve "
                                  "(jev_candidate_steps)",
                "success_on_eligible_set": "VERIFIED_SUCCESS / executed Jev proposals (done excluded)",
                "stale_action_rate": "STALE_OBSERVATION_EPOCH rejections (DDS or VAN) / well-formed Jev responses",
                "shadow_validity_rate": "SHADOW proposals that passed VAN's B1 re-validation / SHADOW proposals",
                "shadow_agreement_rate": "steps where a later lane executed the same operation on the same "
                                         "element the SHADOW proposal named / steps with a SHADOW proposal "
                                         "and an executed later-lane action",
            },
        }


# ------------------------------------------------------------------------ router


def _class_value(eligibility_class: Any) -> str:
    value = getattr(eligibility_class, "value", eligibility_class)
    if isinstance(value, str):
        return value
    return str(getattr(eligibility_class, "name", "UNKNOWN"))


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _observation_digest(observation: Any) -> str:
    if dataclasses.is_dataclass(observation) and not isinstance(observation, type):
        observation = dataclasses.asdict(observation)
    raw = json.dumps(observation, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def harness_page_to_jev_observation(page: Any, *, profile_alias: str) -> Any:
    """Build B2's ``JevPageObservation`` from what the Browser Harness reports.

    Never guesses in the permissive direction. The Harness ``page_info`` today returns
    ``url``/``title``/``extraction`` and, when the page marks one, ``account_identity``; it
    does not return an element list, a login state or a cookie state. So:

    * ``authenticated``/``cookies_present`` are taken only when the Harness reports a real
      bool; otherwise ``None`` (unknown), which B2 treats as an authenticated session. An
      ``account_identity`` marker means signed in.
    * ``elements`` come only from a Harness-reported ``elements`` list; each ``ref`` is the
      Harness locator used to act on it. No list means no targets, which B2 denies.
    """
    from van_gateway.browser.jev_eligibility import JevPageObservation, ObservedElement

    page = page if isinstance(page, dict) else {}

    def tri(key: str) -> bool | None:
        value = page.get(key)
        return value if isinstance(value, bool) else None

    authenticated = tri("authenticated")
    if page.get("account_identity"):
        authenticated = True
    elements = []
    for raw in page.get("elements") or ():
        if not isinstance(raw, dict) or not isinstance(raw.get("ref"), str) or not raw.get("ref"):
            continue
        elements.append(ObservedElement(
            ref=raw["ref"], role=str(raw.get("role") or ""),
            label=str(raw.get("label") or ""), aria_label=str(raw.get("aria_label") or ""),
            placeholder=str(raw.get("placeholder") or ""), title=str(raw.get("title") or ""),
            value=str(raw.get("value") or ""), input_type=str(raw.get("input_type") or ""),
            autocomplete=str(raw.get("autocomplete") or ""), hidden=bool(raw.get("hidden", False)),
        ))
    return JevPageObservation(
        url=str(page.get("url") or ""), profile_alias=profile_alias,
        authenticated=authenticated, cookies_present=tri("cookies_present"),
        elements=tuple(elements), page_title=str(page.get("title") or ""),
    )


def _locator_from_entry(entry: Any) -> str | None:
    if isinstance(entry, str) and entry:
        return entry
    if isinstance(entry, dict):
        for key in ("locator", "selector", "backend_node_ref", "ref"):
            value = entry.get(key)
            if isinstance(value, str) and value:
                return value
    return None


class BrowserInteractionRouter:
    """Routes one browser step through the four lanes. Holds no browser authority itself."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        executor: ActionExecutor | None = None,
        verifier: PostconditionVerifier | None = None,
        eligibility_classifier: EligibilityClassifier | None = None,
        jev_client: JevProposer | None = None,
        semantic_fallback: SemanticFallback | None = None,
        observer: PageObserver | None = None,
        action_classifier: ActionClassifier = default_action_classifier,
        epoch_source: Callable[[BrowserTask, InteractionStep], Awaitable[str | None]] | None = None,
        eligibility_policy: Any = None,
        metrics: RouterMetrics | None = None,
        owner_control_probe: Callable[[BrowserTask], Awaitable[bool]] | None = None,
        stagehand_gate: Callable[[], Any] | None = None,
        target_resolver: TargetResolver | None = None,
        require_owner_private_terms: bool = False,
    ) -> None:
        self.enabled = enabled
        self.executor = executor
        self.verifier = verifier
        self.eligibility_classifier = eligibility_classifier
        self.jev_client = jev_client
        self.semantic_fallback = semantic_fallback
        self.observer = observer
        self.action_classifier = action_classifier
        self.epoch_source = epoch_source
        self.eligibility_policy = eligibility_policy
        self.metrics = metrics or RouterMetrics()
        #: B2 epochs are random per classification, so "is the page still the one Jev saw?"
        #: is answered by a digest of the observation the epoch was issued for.
        self._epoch_digests: OrderedDict[str, str] = OrderedDict()
        #: Owner takeover preempts automation (owner decision §9). Unknown = preempted.
        self.owner_control_probe = owner_control_probe
        #: Unit M's `stagehand_production_enabled`, bound to settings. Absent = lane off.
        self.stagehand_gate = stagehand_gate
        #: Reviewer I M-5: how a Stagehand locator becomes an observed element. Absent =
        #: every targeted Stagehand action is unclassifiable and goes to the owner.
        self.target_resolver = target_resolver
        #: Reviewer I minor 1: production requires B2 to know the owner's own name/handles.
        self.require_owner_private_terms = require_owner_private_terms

    # ----------------------------------------------------------- lane readiness

    def jev_lane_disabled_reasons(self) -> list[str]:
        """Why the Jev lane cannot run. Empty means it can. Missing deps fail closed."""
        reasons = []
        if self.eligibility_classifier is None:
            reasons.append("JEV_LANE_DISABLED:ELIGIBILITY_CLASSIFIER_MISSING")
        if self.verifier is None:
            reasons.append("JEV_LANE_DISABLED:VERIFIER_MISSING")
        if self.executor is None:
            reasons.append("JEV_LANE_DISABLED:EXECUTOR_MISSING")
        if self.jev_client is None:
            reasons.append("JEV_LANE_DISABLED:JEV_CLIENT_MISSING")
        elif getattr(self.jev_client, "configured", True) is False:
            reasons.append("JEV_LANE_DISABLED:JEV_CLIENT_UNCONFIGURED")
        if self.action_classifier is None:
            reasons.append("JEV_LANE_DISABLED:ACTION_CLASSIFIER_MISSING")
        if self.require_owner_private_terms and not tuple(
            getattr(self.eligibility_policy, "owner_private_terms", ()) or ()
        ):
            reasons.append("JEV_LANE_DISABLED:OWNER_PRIVATE_TERMS_UNCONFIGURED")
        return reasons

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "jev_lane_disabled_reasons": self.jev_lane_disabled_reasons(),
            "deterministic_lane": self.executor is not None,
            "stagehand_lane": self.semantic_fallback is not None,
            "owner_control_probe": self.owner_control_probe is not None,
            "verifier": self.verifier is not None,
        }

    # ----------------------------------------------------------- entry point

    async def _stagehand_disabled_reason(self) -> str | None:
        if self.semantic_fallback is None:
            return "STAGEHAND_LANE_DISABLED:FALLBACK_MISSING"
        if self.executor is None:
            return "STAGEHAND_LANE_DISABLED:EXECUTOR_MISSING"
        if self.stagehand_gate is None:
            return "STAGEHAND_LANE_DISABLED:PRODUCTION_GATE_MISSING"
        try:
            permitted, reason = await _maybe_await(self.stagehand_gate())
        except Exception as exc:  # noqa: BLE001 - a gate fault is "not permitted"
            return f"STAGEHAND_LANE_DISABLED:PRODUCTION_GATE_FAILED:{type(exc).__name__}"
        if permitted is not True:
            return f"STAGEHAND_LANE_DISABLED:{reason or 'PRODUCTION_DISABLED'}"
        return None

    async def _owner_preempts(self, task: BrowserTask) -> str | None:
        """Owner takeover preempts automation at any point. Unknown control state = preempt."""
        if self.owner_control_probe is None:
            return "OWNER_CONTROL_STATE_UNKNOWN"
        try:
            owner_has_control = await self.owner_control_probe(task)
        except Exception as exc:  # noqa: BLE001
            return f"OWNER_CONTROL_PROBE_FAILED:{type(exc).__name__}"
        return "OWNER_HAS_CONTROL" if owner_has_control else None

    def _takeover(self, reasons: list[str], attempts: list[dict[str, Any]], why: str | None = None) -> StepResult:
        self.metrics.inc("owner_takeovers")
        if why:
            reasons = reasons + [f"OWNER_TAKEOVER:{why}"]
        return StepResult(
            lane=RouterLane.OWNER_TAKEOVER, state=StepState.OWNER_TAKEOVER,
            trail=[StepState.OWNER_TAKEOVER.value], reasons=reasons, attempts=attempts,
            escalated=True,
            jev_consulted=any(r.startswith("JEV_CONSULTED") for r in reasons),
            eligibility_class=next((r.split(":", 1)[1] for r in reasons if r.startswith("B2:")), None),
        )

    async def route(self, step: InteractionStep) -> StepResult:
        if not self.enabled:
            raise RuntimeError("BROWSER_INTERACTION_ROUTER_DISABLED")
        self.metrics.inc("total_steps")
        if step.action_class_ceiling not in PROPOSABLE_ACTION_CLASSES:
            # A4/A5 are never routed autonomously; an unknown ceiling is not guessed at.
            self.metrics.inc("policy_refusals")
            return StepResult(
                lane=RouterLane.POLICY_REFUSAL, state=StepState.POLICY_REFUSED,
                trail=[StepState.POLICY_REFUSED.value],
                reasons=[f"STEP_CEILING_NOT_ROUTABLE:{step.action_class_ceiling}"],
            )
        if step.task.status not in RUNNABLE_TASK_STATUSES:
            # Reviewer I M-8 — a COMPLETED/FAILED/CANCELLED/... task is not driven further.
            # The HTTP route answers 409 before this; this holds for any other caller.
            self.metrics.inc("policy_refusals")
            status = getattr(step.task.status, "value", step.task.status)
            return StepResult(
                lane=RouterLane.POLICY_REFUSAL, state=StepState.POLICY_REFUSED,
                trail=[StepState.POLICY_REFUSED.value],
                reasons=[f"BROWSER_TASK_NOT_RUNNABLE:{status}"],
            )
        reasons: list[str] = []
        capped = effective_step_ceiling(step.action_class_ceiling, step.task)
        if capped != step.action_class_ceiling:
            reasons.append(f"STEP_CEILING_CAPPED_BY_TASK:{step.action_class_ceiling}->{capped}")
            step.action_class_ceiling = capped
        attempts: list[dict[str, Any]] = []
        # Locked order (owner decision §9). A lane returns None when it has nothing to do.
        lanes = (self._deterministic_lane, self._jev_lane_entry, self._stagehand_lane)
        for lane in lanes:
            preempt = await self._owner_preempts(step.task)
            if preempt is not None:
                return self._takeover(reasons, attempts, preempt)
            result = await lane(step, reasons)
            if result is None:
                continue
            if result.state is StepState.NOT_SATISFIED:
                # §7: NOT_SATISFIED -> fallback. The page may have changed, so anything
                # observed before this action is stale and must be re-read.
                attempts.append(result.to_json())
                reasons.append(f"{result.lane.value}_NOT_SATISFIED")
                step.observation = None
                continue
            result.attempts = attempts
            return self._finish(step, result)
        return self._finish(step, self._takeover(reasons, attempts))

    def _finish(self, step: InteractionStep, result: StepResult) -> StepResult:
        """Attach the SHADOW Jev proposal (if any) and compare it with what actually ran."""
        if "JEV_CONSULTED" in result.reasons:
            result.jev_consulted = True
        shadow = step.shadow_jev
        if shadow is None:
            return result
        shadow = dict(shadow)
        acted = result.action
        if (
            shadow.get("valid")
            and acted is not None
            and acted.lane is not RouterLane.JEV
            and StepState.EXECUTING.value in result.trail
        ):
            self.metrics.inc("jev_shadow_comparisons")
            agreed = acted.operation == shadow.get("operation") and acted.locator == shadow.get("locator")
            if agreed:
                self.metrics.inc("jev_shadow_agreements")
            shadow["compared_with_lane"] = acted.lane.value
            shadow["agreed"] = agreed
        # The locator is VAN-internal; the record keeps the opaque target id only.
        shadow.pop("locator", None)
        result.shadow_jev = shadow
        return result

    async def _deterministic_lane(self, step: InteractionStep, reasons: list[str]) -> StepResult | None:
        if step.deterministic_action is None:
            return None
        if self.executor is None:
            reasons.append("DETERMINISTIC_LANE_EXECUTOR_MISSING")
            return None
        det = step.deterministic_action
        action = RouterAction(
            lane=RouterLane.DETERMINISTIC, operation=det.operation, locator=det.locator,
            value_ref=det.value_ref, action_class=None,
        )
        self.metrics.inc("deterministic_steps")
        return await self._execute_and_verify(step, action, reasons, claimed_done=det.operation == "done")

    async def _jev_lane_entry(self, step: InteractionStep, reasons: list[str]) -> StepResult | None:
        self.metrics.inc("jev_candidate_steps")
        return await self._jev_lane(step, reasons)

    async def _stagehand_lane(self, step: InteractionStep, reasons: list[str]) -> StepResult | None:
        disabled = await self._stagehand_disabled_reason()
        if disabled is not None:
            reasons.append(disabled)
            return None
        try:
            proposal = await self.semantic_fallback.propose(step.task, step)  # type: ignore[union-attr]
        except SemanticProposalRefused as exc:
            reasons.append(f"STAGEHAND_PROPOSAL_REFUSED:{exc.code}")
            return None
        except (BrowserAdapterError, BrowserPolicyError, PaymentBoundaryError) as exc:
            reasons.append(f"STAGEHAND_UNAVAILABLE:{getattr(exc, 'code', type(exc).__name__)}")
            return None
        if proposal is None:
            # "Nothing left to do" from Stagehand is not success (§7): nothing to verify.
            reasons.append("STAGEHAND_NO_ACTION")
            return None
        # Reviewer I M-5 — Stagehand's own description is untrusted text: a selector
        # `//button[@id='pay-now']` described as "Continue" was executed as A2. VAN
        # classifies what the *Harness* observes of the target (role, accessible name,
        # attributes, resolved through the selector) together with the selector itself.
        # The description is also checked, so it can only make the answer stricter.
        observed_text = ""
        if proposal.operation not in TARGETLESS_OPERATIONS:
            unclassifiable = await self._resolve_stagehand_target(step, proposal)
            if isinstance(unclassifiable, str):
                reasons.append(f"STAGEHAND_ACTION_UNCLASSIFIABLE:{unclassifiable}")
                return self._takeover(reasons, [], "STAGEHAND_ACTION_UNCLASSIFIABLE")
            observed_text = observed_element_text(unclassifiable, proposal.locator)
        stagehand_class = self._stricter_class(
            self.action_classifier(proposal.operation, {"label": observed_text}, None) if observed_text else "A0",
            self.action_classifier(proposal.operation, {"label": proposal.description or ""}, None),
        )
        if (
            stagehand_class not in B1_ACTION_CLASSES
            or stagehand_class in NEVER_PROPOSABLE_ACTION_CLASSES
            or _rank(stagehand_class) > _rank(step.action_class_ceiling)
        ):
            reasons.append(f"STAGEHAND_ACTION_ABOVE_CEILING:{stagehand_class}")
            return None
        self.metrics.inc("stagehand_steps")
        action = RouterAction(
            lane=RouterLane.STAGEHAND, operation=proposal.operation, locator=proposal.locator,
            value_ref=proposal.value_ref, action_class=stagehand_class,
            semantic_action=proposal.semantic_action,
            # The payment boundary in _execute_and_verify reads this: the Harness-observed
            # element and selector as well as Stagehand's description.
            description=" | ".join(t for t in (proposal.description, observed_text) if t) or None,
        )
        return await self._execute_and_verify(step, action, reasons, claimed_done=proposal.operation == "done")

    @staticmethod
    def _stricter_class(*classes: str) -> str:
        known = [c for c in classes if c in B1_ACTION_CLASSES]
        if len(known) != len(classes):
            return next(c for c in classes if c not in B1_ACTION_CLASSES)
        return max(known, key=_rank)

    async def _resolve_stagehand_target(
        self, step: InteractionStep, proposal: RouterAction,
    ) -> dict[str, Any] | str:
        """The Harness-observed element for the proposal's locator, or why there is none."""
        if not proposal.locator:
            return "NO_LOCATOR"
        if self.target_resolver is None:
            return "NO_TARGET_RESOLVER"
        try:
            element = await self.target_resolver(step.task, proposal.locator)
        except Exception as exc:  # noqa: BLE001 - cannot observe the target = cannot classify it
            return f"RESOLVER_FAILED:{type(exc).__name__}"
        if not isinstance(element, dict) or not element:
            return "TARGET_NOT_RESOLVED_BY_HARNESS"
        if element.get("hidden") is True:
            return "TARGET_HIDDEN"
        if not any(isinstance(element.get(k), str) and element.get(k) for k in ("role", "label", "name", "accessible_name", "aria_label", "text")):
            return "TARGET_HAS_NO_ROLE_OR_NAME"
        return element

    # ----------------------------------------------------------- Jev lane

    async def _observe(self, step: InteractionStep) -> dict[str, Any] | None:
        if step.observation is not None:
            return step.observation
        if self.observer is None:
            return None
        return await self.observer(step.task)

    async def _classify(self, observation: Any, step: InteractionStep) -> Any:
        assert self.eligibility_classifier is not None
        return await _maybe_await(self.eligibility_classifier(
            observation,
            closed_operation_set=tuple(step.closed_operation_set),
            action_class_ceiling=step.action_class_ceiling,
            policy=self.eligibility_policy,
        ))

    def _remember_epoch(self, epoch: str, observation: Any) -> None:
        self._epoch_digests[epoch] = _observation_digest(observation)
        while len(self._epoch_digests) > 64:
            self._epoch_digests.popitem(last=False)

    async def _current_epoch(self, step: InteractionStep, request_epoch: str) -> str | None:
        """The page's epoch *now*, not when it was classified.

        A fresh read-back whose digest equals the one the epoch was issued for is the same
        page, so the epoch still holds; anything else (page changed, no observer, epoch never
        issued here) is a different epoch and every proposal against the old one is stale.
        """
        if self.epoch_source is not None:
            return await self.epoch_source(step.task, step)
        if self.observer is None:
            return None
        issued_for = self._epoch_digests.get(request_epoch)
        if issued_for is None:
            return None
        try:
            fresh = await self.observer(step.task)
        except Exception:  # noqa: BLE001 - cannot re-read the page => cannot prove freshness
            return None
        now = _observation_digest(fresh)
        return request_epoch if now == issued_for else f"page_{now[:16]}"

    async def _jev_lane(self, step: InteractionStep, reasons: list[str]) -> StepResult | None:
        """Returns a terminal result when a Jev proposal was acted on, else ``None``."""
        if self.eligibility_classifier is None:
            # Cannot tell eligible from ineligible, so nothing is eligible. Recorded, not silent.
            self.metrics.inc("jev_lane_disabled_steps")
            reasons.extend(self.jev_lane_disabled_reasons())
            return None

        observation = await self._observe(step)
        if observation is None:
            self.metrics.inc("jev_lane_disabled_steps")
            reasons.append("JEV_LANE_DISABLED:NO_OBSERVATION")
            return None
        try:
            eligibility = await self._classify(observation, step)
        except Exception as exc:  # noqa: BLE001 - a classifier fault is "not eligible"
            reasons.append(f"B2_CLASSIFIER_FAILED:{type(exc).__name__}")
            self.metrics.inc("b2_privacy_rejections")
            return None
        cls = _class_value(getattr(eligibility, "eligibility_class", None))
        reasons.append(f"B2:{cls}")
        payload = getattr(eligibility, "jev_payload", None)
        if cls not in ELIGIBLE_CLASSES or payload is None or getattr(eligibility, "eligible", True) is False:
            self.metrics.inc("b2_privacy_rejections")
            return None
        self.metrics.inc("eligible_steps")

        disabled = self.jev_lane_disabled_reasons()
        if disabled:
            self.metrics.inc("jev_lane_disabled_steps")
            self.metrics.inc("jev_fallbacks")
            reasons.extend(disabled)
            return None

        try:
            request = validate_b1_payload(
                payload, ceiling=step.action_class_ceiling,
                closed_operation_set=tuple(step.closed_operation_set),
            )
            if request["observation_epoch"] != getattr(eligibility, "observation_epoch", None):
                raise B1ValidationError("PAYLOAD_EPOCH_NOT_OBSERVATION_EPOCH")
        except B1ValidationError as exc:
            self.metrics.inc("jev_fallbacks")
            reasons.append(f"JEV_REQUEST_REJECTED_BY_VAN:{exc.code}")
            return None

        target_map = getattr(eligibility, "target_map", None) or {}
        if isinstance(getattr(eligibility, "observation_epoch", None), str):
            self._remember_epoch(eligibility.observation_epoch, observation)

        def classify(operation: str, target: dict[str, Any] | None) -> str:
            entry = target_map.get(target["target_id"]) if target else None
            return self.action_classifier(operation, target, entry)

        caller_classes: list[dict[str, Any]] = []
        for op in request["closed_operation_set"]:
            if op == "abstain":
                continue
            if op in TARGETLESS_OPERATIONS:
                caller_classes.append({"operation": op, "target_id": None, "action_class": classify(op, None)})
            else:
                for target in request["targets"]:
                    caller_classes.append({
                        "operation": op, "target_id": target["target_id"],
                        "action_class": classify(op, target),
                    })

        epoch_at_call = await self._current_epoch(step, request["observation_epoch"])
        if not epoch_at_call or epoch_at_call != request["observation_epoch"]:
            # The page moved between classification and the call; asking Jev about a page
            # that no longer exists would only produce a stale proposal.
            self.metrics.inc("jev_fallbacks")
            reasons.append("JEV_NOT_CALLED:OBSERVATION_STALE_BEFORE_CALL")
            return None
        self.metrics.inc("jev_calls")
        reasons.append("JEV_CONSULTED")
        try:
            response = await self.jev_client.propose_action(  # type: ignore[union-attr]
                request=request, caller_action_classes=caller_classes,
                current_epoch=epoch_at_call,
            )
        except Exception as exc:  # noqa: BLE001 - any client fault is an abstention
            response = None
            reasons.append(f"JEV_CLIENT_FAILED:{type(exc).__name__}")
        if response is None or not getattr(response, "transport_ok", False):
            self.metrics.inc("jev_fallbacks")
            if response is not None:
                reasons.extend(f"JEV:{r}" for r in response.reasons)
            return None
        self.metrics.inc("jev_responses")
        if any("EGRESS" in r for r in response.reasons):
            self.metrics.inc("dds_egress_rejections")
        if not response.proposes:
            if any("STALE_OBSERVATION_EPOCH" in r for r in response.reasons):
                self.metrics.inc("jev_stale_rejections")
            self.metrics.inc("jev_fallbacks")
            reasons.extend(f"JEV:{r}" for r in response.reasons)
            return None
        self.metrics.inc("jev_proposals_received")

        shadow = not response.carries_effect
        if shadow:
            # Reviewer I M-3 — PRD Rev 2.1: "SHADOW: Jev runs; consumer ignores result", and
            # blueprint §11: no Jev module can carry effect today. The proposal is still
            # re-validated (so §8 can say how often it *would* have been admissible) and
            # recorded for comparison, and then this lane falls through. Nothing executes.
            self.metrics.inc("jev_shadow_proposals")
            step.shadow_jev = {
                "lifecycle_state": response.lifecycle_state,
                "apply_effect": response.apply_effect,
                "operation": (response.proposal or {}).get("operation"),
                "target_id": (response.proposal or {}).get("target_id"),
                "valid": False,
            }

        # VAN-side B1 re-validation, against the epoch *now* (right before execution).
        epoch_now = await self._current_epoch(step, request["observation_epoch"])
        try:
            operation, target, action_class = validate_jev_proposal(
                request=request, proposal=response.proposal, current_epoch=epoch_now,
                classify=classify, jev_action_class=response.action_class,
            )
        except B1ValidationError as exc:
            if exc.code == "STALE_OBSERVATION_EPOCH":
                self.metrics.inc("jev_stale_rejections")
            self.metrics.inc("jev_fallbacks")
            reasons.append(f"JEV_PROPOSAL_REJECTED_BY_VAN:{exc.code}")
            return None

        locator = None
        if target is not None:
            # B2's target_map (t_* -> VAN element ref) is the only way back to the page. An id
            # that is not in it is invalid, whatever the payload said.
            locator = _locator_from_entry(target_map.get(target["target_id"]))
            if locator is None:
                self.metrics.inc("jev_fallbacks")
                reasons.append("JEV_PROPOSAL_REJECTED_BY_VAN:TARGET_NOT_RESOLVABLE")
                return None
        value = None
        slot = response.proposal["value_ref"]
        if slot is not None:
            value = step.value_slots.get(slot)
            if value is None:
                self.metrics.inc("jev_fallbacks")
                reasons.append("JEV_PROPOSAL_REJECTED_BY_VAN:VALUE_SLOT_UNBOUND")
                return None

        if shadow:
            self.metrics.inc("jev_shadow_valid")
            self.metrics.inc("jev_fallbacks")
            step.shadow_jev.update(valid=True, action_class=action_class, locator=locator)
            reasons.append(f"JEV_SHADOW_NOT_EXECUTED:{response.lifecycle_state or 'LIFECYCLE_UNREPORTED'}")
            return None

        action = RouterAction(
            lane=RouterLane.JEV, operation=operation, locator=locator, value_ref=value,
            action_class=action_class, target_id=target["target_id"] if target else None,
            description=target["label"] if target else None,
        )
        if operation == "done":
            self.metrics.inc("jev_done_proposals")
        else:
            self.metrics.inc("jev_executed")
        result = await self._execute_and_verify(step, action, reasons, claimed_done=operation == "done")
        result.jev_consulted = True
        result.eligibility_class = cls
        if operation == "done":
            if result.state is not StepState.VERIFIED_SUCCESS:
                self.metrics.inc("jev_done_postcondition_failures")
        else:
            if result.state is StepState.VERIFIED_SUCCESS:
                self.metrics.inc("jev_executed_verified_success")
            elif result.state is StepState.NOT_SATISFIED:
                self.metrics.inc("jev_wrong_actions")
        return result

    # ----------------------------------------------------------- execute + verify

    async def _execute_and_verify(
        self, step: InteractionStep, action: RouterAction, reasons: list[str], *, claimed_done: bool,
    ) -> StepResult:
        trail = [StepState.PROPOSED.value]
        try:
            assert_not_automated_payment(
                operation=action.operation, goal=action.description or "",
                domain=step.task.target_domain,
                context=f"interaction_router_{action.lane.value.lower()}",
            )
        except PaymentBoundaryError as exc:
            self.metrics.inc("policy_refusals")
            return StepResult(
                lane=RouterLane.POLICY_REFUSAL, state=StepState.POLICY_REFUSED,
                trail=trail + [StepState.POLICY_REFUSED.value], reasons=reasons + [str(exc)],
                action=action,
            )

        if claimed_done:
            # `done` is a claim. Nothing executes; the verifier decides.
            trail.append(StepState.VERIFYING.value)
        else:
            preempt = await self._owner_preempts(step.task)
            if preempt is not None:
                self.metrics.inc("owner_takeovers")
                return StepResult(
                    lane=RouterLane.OWNER_TAKEOVER, state=StepState.OWNER_TAKEOVER,
                    trail=trail + [StepState.OWNER_TAKEOVER.value],
                    reasons=reasons + [f"OWNER_TAKEOVER:{preempt}"], action=action, escalated=True,
                )
            trail.append(StepState.EXECUTING.value)
            try:
                await self.executor.execute(step.task, action)  # type: ignore[union-attr]
            except (BrowserPolicyError, PaymentBoundaryError) as exc:
                self.metrics.inc("policy_refusals")
                return StepResult(
                    lane=RouterLane.POLICY_REFUSAL, state=StepState.POLICY_REFUSED,
                    trail=trail + [StepState.POLICY_REFUSED.value],
                    reasons=reasons + [f"POLICY_REFUSED:{exc}"], action=action,
                )
            except BrowserAdapterError as exc:
                return StepResult(
                    lane=action.lane, state=StepState.EXECUTION_FAILED,
                    trail=trail + [StepState.EXECUTION_FAILED.value],
                    reasons=reasons + [f"EXECUTION_FAILED:{exc.code}"], action=action,
                )
            trail.append(StepState.VERIFYING.value)

        if self.verifier is None:
            state = StepState.UNVERIFIABLE
            reasons = reasons + ["VERIFIER_MISSING"]
            verification = None
        else:
            try:
                verification = await self.verifier.verify(
                    step.task, action, step.postcondition, claimed_done=claimed_done,
                )
            except Exception as exc:  # noqa: BLE001 - a verifier fault is never success
                verification = VerificationResult(
                    outcome=VerificationOutcome.UNVERIFIABLE, verifier_type=VerifierType.STATE_PREDICATE,
                    detail=f"verifier_failed:{type(exc).__name__}",
                )
            if verification.outcome is VerificationOutcome.VERIFIED:
                state = StepState.VERIFIED_SUCCESS
            elif verification.outcome is VerificationOutcome.FAILED:
                state = StepState.NOT_SATISFIED
            else:
                state = StepState.UNVERIFIABLE
        trail.append(state.value)
        if state is StepState.UNVERIFIABLE:
            reasons = reasons + ["ESCALATED:UNVERIFIABLE"]
        return StepResult(
            lane=action.lane, state=state, trail=trail, reasons=reasons, action=action,
            verification=verification, escalated=state is StepState.UNVERIFIABLE,
        )


# ------------------------------------------------------------------------ production adapters


class HarnessActionExecutor:
    """Executes a routed action through the existing Browser Harness adapter."""

    def __init__(self, harness: Any) -> None:
        self.harness = harness

    async def execute(self, task: BrowserTask, action: RouterAction) -> dict[str, Any]:
        op = action.operation
        if op == "click":
            if not action.locator:
                raise BrowserAdapterError("BROWSER_LOCATOR_MISSING", op)
            return await self.harness.click(task, action.locator)
        if op == "fill":
            if not action.locator or not action.value_ref:
                raise BrowserAdapterError("BROWSER_FILL_REF_MISSING", op)
            # fill_ref refuses anything that is not a secretref:// reference.
            return await self.harness.fill_ref(task, action.locator, action.value_ref)
        if op == "press_key":
            if not action.value_ref:
                raise BrowserAdapterError("BROWSER_KEY_MISSING", op)
            return await self.harness.press(task, action.value_ref)
        if op == "scroll":
            return await self.harness.scroll(task, {"direction": "down"})
        raise BrowserAdapterError("BROWSER_ACTION_UNSUPPORTED", op)


class StagehandSemanticFallback:
    """Stagehand *observes and proposes*; the Browser Harness executes (owner decision §8).

    ``observe()`` only — this lane never calls ``act()``. The observed candidate becomes a
    typed Harness operation via ``typed_action_from_stagehand``, or is refused. ``observe()``
    finding no controls returns ``None``, which is never success.
    """

    def __init__(self, stagehand: Any) -> None:
        self.stagehand = stagehand

    async def propose(self, task: BrowserTask, step: InteractionStep) -> RouterAction | None:
        if not getattr(self.stagehand, "configured", False) or not getattr(self.stagehand, "enabled", False):
            raise SemanticProposalRefused("STAGEHAND_UNCONFIGURED")
        instruction = step.semantic_instruction or f"Choose the single next action for: {task.goal}"
        observation = await self.stagehand.observe(task, instruction)
        if not observation.controls:
            return None
        typed = typed_action_from_stagehand(
            observation.controls[0], allowed_operations=step.closed_operation_set,
        )
        return RouterAction(
            lane=RouterLane.STAGEHAND, operation=typed.operation, locator=typed.selector,
            value_ref=typed.key, action_class=None, semantic_action=typed.observed,
            description=typed.description,
        )


class OwnerControlProbe:
    """True when the owner holds control of a live interactive session on the task's profile.

    ADR-RB-007 "owner touch wins": the interactive session's control holder is the fence.
    """

    def __init__(self, store: Any) -> None:
        self.store = store

    async def __call__(self, task: BrowserTask) -> bool:
        now = int(time.time() * 1000)
        row = await self.store.fetchone(
            "SELECT 1 FROM browser_interactive_sessions WHERE profile_alias = ? "
            "AND control_holder = 'OWNER' AND terminated_at_ms IS NULL AND expires_at_ms > ? LIMIT 1",
            (task.profile_alias, now),
        )
        return row is not None


async def _fetch_stagehand_worker_health(stagehand: Any) -> dict[str, Any] | None:
    """GET the Stagehand worker's ``/health`` through the van-browser-core edge. None on any failure."""
    import httpx

    base = (getattr(stagehand, "base_url", "") or "").rstrip("/")
    if not base:
        return None
    kwargs_fn = getattr(stagehand, "client_kwargs", None)
    kwargs = kwargs_fn() if callable(kwargs_fn) else {
        "base_url": base, "transport": getattr(stagehand, "transport", None),
    }
    kwargs["timeout"] = 5.0
    try:
        async with httpx.AsyncClient(**kwargs) as client:
            response = await client.get("/health")
        if response.status_code != 200:
            return None
        body = response.json()
        return body if isinstance(body, dict) else None
    except Exception:  # noqa: BLE001 - unreachable health is absent health
        return None


def load_stagehand_production_gate(settings: Any, stagehand: Any = None) -> Callable[[], Any]:
    """The Stagehand lane's production gate: placement/model AND the production gate model.

    * unit M's ``stagehand_production_enabled(settings, worker_health=...)`` (placement on
      van-browser-core + model/provider-key rules), fed the worker's live ``/health``; absent
      module or absent health fails closed;
    * ``evaluate_production_gates()`` (owner decision §6; includes signed ingress and the
      §7/§8 blocker records) must report ``production_activation_permitted``.
    """

    async def gate() -> tuple[bool, str]:
        try:
            from van_gateway.automation import placement  # type: ignore[attr-defined]
        except ImportError:
            return False, "PLACEMENT_GATE_MISSING"
        fn = getattr(placement, "stagehand_production_enabled", None)
        if fn is None:
            return False, "PLACEMENT_GATE_MISSING"
        health = await _fetch_stagehand_worker_health(stagehand) if stagehand is not None else None
        permitted, reason = fn(settings, worker_health=health)
        if permitted is not True:
            return False, str(reason or "PRODUCTION_DISABLED")
        try:
            from van_gateway.automation.production_gates import evaluate_production_gates
        except ImportError:
            return False, "PRODUCTION_GATE_MODEL_MISSING"
        gates = evaluate_production_gates()
        if gates.get("production_activation_permitted") is not True:
            not_green = ",".join(gates.get("production_gates_not_green") or [])[:200]
            return False, f"PRODUCTION_GATES_NOT_GREEN:{not_green or gates.get('gate_model_error') or 'UNKNOWN'}"
        return True, str(reason)

    return gate


class HarnessReadBackObserver:
    """``PostconditionObserver`` that reads the page back fresh through the harness."""

    def __init__(self, harness: Any) -> None:
        self.harness = harness

    async def observe(self, spec: PostconditionSpec, context: dict[str, Any]) -> dict[str, Any]:
        page = await self.harness.page_info(context["task"])
        observed = dict(page.get("extraction") or {})
        for key in ("url", "title"):
            if page.get(key) is not None:
                observed.setdefault(key, page[key])
        observed["exists"] = bool(page)
        return observed


class IndependentPostconditionVerifier:
    """The existing ``WorkflowVerifier`` over a fresh harness read-back.

    No declared postcondition, or no observer for its kind, is ``UNVERIFIABLE`` — never
    success. Neither the executor's return value nor Jev's claim is consulted.
    """

    def __init__(self, harness: Any) -> None:
        self.workflow = WorkflowVerifier({"READ_BACK": HarnessReadBackObserver(harness)})

    async def verify(
        self, task: BrowserTask, action: RouterAction,
        postcondition: PostconditionSpec | None, *, claimed_done: bool,
    ) -> VerificationResult:
        return await self.workflow.verify(
            spec=postcondition, verifier_type=VerifierType.READ_BACK,
            engine_reported_success=claimed_done, context={"task": task},
        )


def load_owner_private_terms(path: str) -> tuple[str, ...]:
    """Owner-private terms for B2, one per line. Unset/unreadable/empty -> ``()`` (lane off)."""
    if not path:
        return ()
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return ()
    terms = []
    for line in text.splitlines():
        term = line.strip()
        if term and not term.startswith("#") and term not in terms:
            terms.append(term)
    return tuple(terms)


def build_eligibility_policy(settings: Any) -> Any:
    """B2 policy with the owner's private terms, or ``None`` when none are configured."""
    terms = load_owner_private_terms(str(getattr(settings, "browser_jev_owner_private_terms_file", "") or ""))
    if not terms:
        return None
    from van_gateway.browser.jev_eligibility import JevEligibilityPolicy

    return JevEligibilityPolicy(owner_private_terms=terms)


def build_interaction_router(
    *,
    settings: Any,
    harness: Any,
    stagehand: Any,
    jev_client: JevProposer | None,
    store: Any = None,
    eligibility_classifier: EligibilityClassifier | None = None,
    verifier: PostconditionVerifier | None = None,
) -> BrowserInteractionRouter:
    """Production wiring. Everything optional fails closed; the router is off by default."""
    classifier = eligibility_classifier if eligibility_classifier is not None else load_eligibility_classifier()

    async def observe(task: BrowserTask) -> Any:
        # B2 refuses VAN's generic BrowserObservation; it gets the frozen record it defines.
        return harness_page_to_jev_observation(await harness.page_info(task), profile_alias=task.profile_alias)

    return BrowserInteractionRouter(
        enabled=bool(getattr(settings, "browser_interaction_router_enabled", False)),
        # One executor for every lane: the Browser Harness. Jev and Stagehand only propose.
        executor=HarnessActionExecutor(harness),
        verifier=verifier if verifier is not None else IndependentPostconditionVerifier(harness),
        eligibility_classifier=classifier,
        jev_client=jev_client,
        semantic_fallback=StagehandSemanticFallback(stagehand),
        observer=observe,
        owner_control_probe=OwnerControlProbe(store) if store is not None else None,
        stagehand_gate=load_stagehand_production_gate(settings, stagehand),
        target_resolver=HarnessTargetResolver(harness),
        eligibility_policy=build_eligibility_policy(settings),
        require_owner_private_terms=True,
    )


# ------------------------------------------------------------------------ HTTP surface


class InteractionStepBody(BaseModel):
    task_id: str
    action_class_ceiling: str = "A1"
    closed_operation_set: list[str] = Field(default_factory=lambda: list(B1_OPERATIONS))
    deterministic_action: DeterministicAction | None = None
    postcondition: PostconditionSpec | None = None
    semantic_instruction: str | None = None
    value_slots: dict[str, str] = Field(default_factory=dict)


def build_interaction_routes(browser_api: Any, router: BrowserInteractionRouter) -> APIRouter:
    """``/v1/browser/interaction/*`` — Hermes-scoped, and 503 unless the flag is on.

    The observation is never taken from the request body: the router reads the page
    itself through the harness, so a caller cannot hand B2 a page it did not see.
    """
    api = APIRouter(prefix="/v1/browser/interaction", tags=["browser"])

    def _guard(token: str | None) -> None:
        browser_api._require_internal(token)
        browser_api._require_enabled()
        if not router.enabled:
            raise HTTPException(status_code=503, detail="BROWSER_INTERACTION_ROUTER_DISABLED")

    @api.get("/status")
    async def interaction_status(x_van_internal_token: str | None = Header(default=None)):
        browser_api._require_internal(x_van_internal_token)
        return router.status()

    @api.get("/metrics")
    async def interaction_metrics(x_van_internal_token: str | None = Header(default=None)):
        browser_api._require_internal(x_van_internal_token)
        return router.metrics.snapshot()

    @api.post("/step")
    async def interaction_step(
        body: InteractionStepBody, x_van_internal_token: str | None = Header(default=None),
    ):
        _guard(x_van_internal_token)
        task = await browser_api._load_task(body.task_id)
        # Reviewer I M-8 — the same lifecycle gate /v1/browser/assignments applies.
        status = task.status
        if status is BrowserTaskStatus.WAITING_FOR_OWNER:
            sync = getattr(browser_api, "_sync_waiting_owner_decision", None)
            if sync is not None:
                status = await sync(task)
        if status not in RUNNABLE_TASK_STATUSES:
            raise HTTPException(status_code=409, detail=f"BROWSER_TASK_NOT_RUNNABLE:{status.value}")
        if status is not task.status:
            task = task.model_copy(update={"status": status})
        for op in body.closed_operation_set:
            if op not in B1_OPERATIONS:
                raise HTTPException(status_code=422, detail=f"OPERATION_NOT_CLOSED:{op}")
        step = InteractionStep(
            task=task,
            action_class_ceiling=body.action_class_ceiling,
            closed_operation_set=tuple(body.closed_operation_set),
            deterministic_action=body.deterministic_action,
            postcondition=body.postcondition,
            semantic_instruction=body.semantic_instruction,
            value_slots=dict(body.value_slots),
        )
        result = await router.route(step)
        return {"task_id": task.task_id, "at_ms": int(time.time() * 1000), **result.to_json()}

    return api


__all__ = [
    "B1ValidationError",
    "BrowserInteractionRouter",
    "DeterministicAction",
    "HarnessActionExecutor",
    "HarnessTargetResolver",
    "IndependentPostconditionVerifier",
    "InteractionStep",
    "RouterAction",
    "RouterLane",
    "OwnerControlProbe",
    "RouterMetrics",
    "SemanticProposalRefused",
    "StagehandSemanticFallback",
    "StepResult",
    "StepState",
    "build_eligibility_policy",
    "build_interaction_router",
    "build_interaction_routes",
    "default_action_classifier",
    "effective_step_ceiling",
    "harness_page_to_jev_observation",
    "observed_element_text",
    "load_eligibility_classifier",
    "load_owner_private_terms",
    "load_stagehand_production_gate",
    "validate_b1_payload",
    "validate_jev_proposal",
]
