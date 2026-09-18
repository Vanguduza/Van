"""Rev 1.3 §§22, 29-31, 172-174 — COLD workflow generation.

COLD is the only expensive path (§23), and §24 frames what it is for: workflow
generation is **capability acquisition, not routine execution**. A COLD run
happens once per novel goal; everything after it is WARM or HOT.

The planner never lets a model emit n8n JSON (§20). A model may propose a
`WorkflowIR` — and only within a contract this module enforces:

* the primitive catalog and node allowlist bound what it may use (§§41, 147);
* the proposal is validated by the same static analyser as everything else, so a
  model cannot talk its way past policy (§40);
* the derived action class is recomputed from the steps, never trusted (§146);
* retrieval runs in parallel before planning, so first-use latency is retrieval-
  bound rather than serial (§31).

`ColdGenerationPlanner` is deliberately model-agnostic: it takes an
`IRProposer` callable. The gateway supplies one backed by Hermes; tests supply a
deterministic one. Nothing here imports a model client.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from van_gateway.automation.canonical import COMPILER_VERSION, digest
from van_gateway.automation.models import (
    DISALLOWED_PRIMITIVE_NAMES,
    IntentSignature,
    Primitive,
    WorkflowIR,
    strongest_class,
)
from van_gateway.automation.payments import PaymentBoundaryError, assert_not_automated_payment
from van_gateway.automation.policy import AutomationPolicy, PolicyError, load_automation_policy
from van_gateway.automation.templates import TemplateLibrary
from van_gateway.automation.validator import ValidationReport, WorkflowValidator
from van_gateway.models import ActionClass


class GenerationOutcome(str, Enum):
    """§§352-353 — how a COLD attempt ended."""

    ADMITTED_CANDIDATE = "ADMITTED_CANDIDATE"
    REQUIRES_OWNER_APPROVAL = "REQUIRES_OWNER_APPROVAL"
    REJECTED_BY_POLICY = "REJECTED_BY_POLICY"
    REJECTED_BY_PAYMENT_BOUNDARY = "REJECTED_BY_PAYMENT_BOUNDARY"
    NO_PROPOSAL = "NO_PROPOSAL"
    PROPOSER_FAILED = "PROPOSER_FAILED"


@dataclass(frozen=True)
class RetrievalContext:
    """§§29-30, 174 — everything preloaded before planning starts.

    §30's point is that COLD generation must not spend its time discovering basic
    n8n syntax or which nodes exist. All of this is resident.
    """

    allowed_primitives: tuple[str, ...]
    allowed_nodes: tuple[str, ...]
    admitted_domains: tuple[str, ...]
    credential_aliases: tuple[str, ...]
    template_ids: tuple[str, ...]
    similar_patterns: tuple[dict[str, Any], ...] = ()
    recent_failures: tuple[str, ...] = ()
    policy_version: str = ""
    compiler_version: str = COMPILER_VERSION

    def as_prompt_contract(self) -> dict[str, Any]:
        """§173 — exactly what a proposer is told, and nothing else.

        Notably absent: credential *values*, owner context, evidence. A proposer
        gets shapes and names, never secrets.
        """
        return {
            "allowed_primitives": list(self.allowed_primitives),
            "allowed_nodes": list(self.allowed_nodes),
            "admitted_domains": list(self.admitted_domains),
            "credential_aliases": list(self.credential_aliases),
            "reusable_templates": list(self.template_ids),
            "known_patterns": [dict(p) for p in self.similar_patterns],
            "recent_failures": list(self.recent_failures),
            "policy_version": self.policy_version,
            "compiler_version": self.compiler_version,
            "hard_rules": [
                "every step must declare timeout, retry class and effects",
                "a mutating step must declare a postcondition",
                "external domains must come from admitted_domains",
                "credentials are referenced by alias, never by value",
                "no payment, no payment instrument, at any class",
                "no FINANCIAL or AUTHORITY effect",
            ],
        }


@dataclass
class GenerationResult:
    outcome: GenerationOutcome
    ir: WorkflowIR | None = None
    report: ValidationReport | None = None
    signature: IntentSignature | None = None
    detail: str | None = None
    elapsed_ms: int = 0
    retrieval: RetrievalContext | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.outcome in (
            GenerationOutcome.ADMITTED_CANDIDATE,
            GenerationOutcome.REQUIRES_OWNER_APPROVAL,
        )


class IRProposer(Protocol):
    """Produces a candidate IR for a goal. Usually model-backed; never trusted."""

    async def propose(
        self, *, goal: str, signature: IntentSignature, context: RetrievalContext
    ) -> WorkflowIR | None:
        ...


class PatternSource(Protocol):
    """§§52-54 — VEKL/corpus patterns, retrieved but never executed directly."""

    async def similar(self, *, goal: str, signature: IntentSignature, limit: int) -> list[dict[str, Any]]:
        ...


class ColdGenerationPlanner:
    """Turns a novel goal into a validated candidate, or an honest refusal."""

    def __init__(
        self,
        *,
        policy: AutomationPolicy | None = None,
        templates: TemplateLibrary | None = None,
        validator: WorkflowValidator | None = None,
        patterns: PatternSource | None = None,
        credential_aliases: list[str] | None = None,
    ) -> None:
        self.policy = policy or load_automation_policy()
        self.templates = templates or TemplateLibrary()
        self.validator = validator or WorkflowValidator(self.policy)
        self.patterns = patterns
        self._credential_aliases = list(credential_aliases or [])

    # ---------------------------------------------------------- retrieval

    async def retrieve(self, *, goal: str, signature: IntentSignature) -> RetrievalContext:
        """§31 — fan out, do not chain.

        The four lookups are independent, so running them serially would make
        first-use latency the sum rather than the max.
        """

        async def _patterns() -> tuple[dict[str, Any], ...]:
            if self.patterns is None:
                return ()
            try:
                found = await self.patterns.similar(goal=goal, signature=signature, limit=5)
            except Exception:  # noqa: BLE001 - retrieval is best-effort
                return ()
            return tuple(found)

        async def _primitives() -> tuple[str, ...]:
            return tuple(
                p.value for p in Primitive if p.value not in DISALLOWED_PRIMITIVE_NAMES
            )

        async def _nodes() -> tuple[str, ...]:
            return tuple(sorted(self.policy.nodes.allowed))

        async def _domains() -> tuple[str, ...]:
            return tuple(sorted(self.policy.domains.admitted))

        patterns, primitives, nodes, domains = await asyncio.gather(
            _patterns(), _primitives(), _nodes(), _domains()
        )
        return RetrievalContext(
            allowed_primitives=primitives,
            allowed_nodes=nodes,
            admitted_domains=domains,
            credential_aliases=tuple(sorted(self._credential_aliases)),
            template_ids=tuple(self.templates.template_ids),
            similar_patterns=patterns,
            policy_version=self.policy.policy_version,
        )

    # ----------------------------------------------------------- generate

    async def generate(
        self,
        *,
        goal: str,
        signature: IntentSignature,
        proposer: IRProposer,
        now_ms: int | None = None,
    ) -> GenerationResult:
        started = int(time.time() * 1000) if now_ms is None else now_ms

        # §34 — refuse a payment goal before any model is asked to plan it.
        try:
            assert_not_automated_payment(goal=goal, context="cold_generation_goal")
        except PaymentBoundaryError as exc:
            return GenerationResult(
                outcome=GenerationOutcome.REJECTED_BY_PAYMENT_BOUNDARY,
                signature=signature, detail=str(exc),
                elapsed_ms=self._elapsed(started, now_ms),
            )

        context = await self.retrieve(goal=goal, signature=signature)

        try:
            proposal = await proposer.propose(goal=goal, signature=signature, context=context)
        except Exception as exc:  # noqa: BLE001 - a proposer fault is not a policy pass
            return GenerationResult(
                outcome=GenerationOutcome.PROPOSER_FAILED, signature=signature,
                detail=f"{type(exc).__name__}", retrieval=context,
                elapsed_ms=self._elapsed(started, now_ms),
            )

        if proposal is None:
            return GenerationResult(
                outcome=GenerationOutcome.NO_PROPOSAL, signature=signature, retrieval=context,
                elapsed_ms=self._elapsed(started, now_ms),
            )

        # §146 — recompute the class from the steps. A proposal that under-declares
        # is corrected here rather than rejected, then validated on the truth.
        proposal = proposal.model_copy(
            update={
                "action_class": strongest_class(proposal.steps),
                "generated_from": sorted(
                    set(proposal.generated_from)
                    | {f"cold:{digest({'goal': goal})}"}
                ),
                "policy_version": self.policy.policy_version,
                "compiler_version": COMPILER_VERSION,
            }
        )

        report = self.validator.validate(proposal)
        if not report.ok:
            payment_errors = [e for e in report.errors if "PAYMENT" in e]
            return GenerationResult(
                outcome=(
                    GenerationOutcome.REJECTED_BY_PAYMENT_BOUNDARY
                    if payment_errors
                    else GenerationOutcome.REJECTED_BY_POLICY
                ),
                ir=proposal, report=report, signature=signature, retrieval=context,
                errors=sorted(report.errors),
                detail="; ".join(sorted(report.errors)[:3]),
                elapsed_ms=self._elapsed(started, now_ms),
            )

        # §36 — only A1/A2 may auto-admit, and only if policy says so. A3 needs
        # verified owner mutation intent; A4 is never a generated first run.
        derived = proposal.action_class
        outcome = (
            GenerationOutcome.ADMITTED_CANDIDATE
            if derived in (ActionClass.A1, ActionClass.A2)
            and self.policy.may_auto_admit(derived.value)
            else GenerationOutcome.REQUIRES_OWNER_APPROVAL
        )
        return GenerationResult(
            outcome=outcome, ir=proposal, report=report, signature=signature,
            retrieval=context, elapsed_ms=self._elapsed(started, now_ms),
        )

    @staticmethod
    def _elapsed(started: int, now_ms: int | None) -> int:
        if now_ms is not None:
            return 0
        return max(0, int(time.time() * 1000) - started)


class TemplateBackedProposer:
    """A deterministic proposer that specialises a template when one fits.

    §29: *"Generation does not begin from a blank canvas unless absolutely
    necessary."* This is the cheap first attempt — if a template covers the goal
    class, no model is needed at all and COLD collapses into WARM.
    """

    def __init__(self, templates: TemplateLibrary | None = None) -> None:
        self.templates = templates or TemplateLibrary()

    async def propose(
        self, *, goal: str, signature: IntentSignature, context: RetrievalContext
    ) -> WorkflowIR | None:
        template = self.templates.for_goal_class(signature.goal_class)
        if template is None:
            return None
        bindings = self._infer_bindings(template, goal=goal, context=context)
        if bindings is None:
            return None
        try:
            return template.specialise(
                bindings=bindings, policy_version=context.policy_version
            )
        except PolicyError:
            return None

    @staticmethod
    def _infer_bindings(
        template: Any, *, goal: str, context: RetrievalContext
    ) -> dict[str, Any] | None:
        """Fill required holes from retrieval, or give up so a model can try.

        Deliberately conservative: guessing a domain or credential would produce a
        workflow that looks right and targets the wrong system.
        """
        if not context.admitted_domains:
            return None
        bindings: dict[str, Any] = {}
        for hole in template.holes:
            if not hole.required:
                continue
            if hole.name == "source_domain":
                bindings[hole.name] = context.admitted_domains[0]
            elif hole.name == "credential_alias":
                if not context.credential_aliases:
                    return None
                bindings[hole.name] = context.credential_aliases[0]
            elif hole.name in ("source_label", "resource_label"):
                bindings[hole.name] = goal[:80]
            elif hole.name == "document_type":
                bindings[hole.name] = "document"
            elif hole.name == "source_path":
                return None  # never guessable
            elif hole.name == "webhook_path":
                return None
            elif hole.name == "event_type":
                return None
            else:
                return None
        return bindings


__all__ = [
    "ColdGenerationPlanner",
    "GenerationOutcome",
    "GenerationResult",
    "IRProposer",
    "PatternSource",
    "RetrievalContext",
    "TemplateBackedProposer",
]
