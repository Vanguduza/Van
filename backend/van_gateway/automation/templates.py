"""Rev 1.3 §§27, 60, 171, 291-294 — the WARM template library.

§23's WARM path: *"A WARM workflow is not generated node-by-node. It is
specialised."* A template is a graph skeleton with named holes; specialising it
binds parameters, connectors and credential aliases and then compiles. No model
participates, which is what makes WARM fast enough to sit on the owner-interactive
path (§57 targets p95 <= 250 ms) and cheap enough to be the default.

Templates are built from the §60 topology macros so the compiler composes known
shapes rather than reasoning about raw nodes each time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from van_gateway.automation.canonical import COMPILER_VERSION, new_id
from van_gateway.automation.models import (
    Primitive,
    RetryClass,
    WorkflowIR,
    WorkflowIREdge,
    WorkflowIRStep,
    WorkflowStepEffect,
    strongest_class,
)
from van_gateway.automation.policy import PolicyError
from van_gateway.models import ActionClass

#: §142 — a binding reference in a template, e.g. ``{{broker_alias}}``.
_HOLE = re.compile(r"\{\{([a-z0-9_]+)\}\}")


class TemplateError(PolicyError):
    """Raised when a template cannot be specialised with the given bindings."""


@dataclass(frozen=True)
class TemplateHole:
    """A named parameter a template needs before it can compile."""

    name: str
    description: str
    required: bool = True
    #: Closed value set, when the template only makes sense for certain values.
    enum: tuple[str, ...] | None = None
    default: Any = None


@dataclass(frozen=True)
class WorkflowTemplate:
    """§171 — a reusable graph skeleton plus the holes that specialise it."""

    template_id: str
    family: str
    macro: str
    summary: str
    holes: tuple[TemplateHole, ...]
    steps: tuple[dict[str, Any], ...]
    edges: tuple[tuple[str, str], ...]
    verifier: dict[str, Any] = field(default_factory=dict)
    evidence_requirements: tuple[str, ...] = ()
    latency_class: str = "T3"

    def specialise(
        self,
        *,
        bindings: dict[str, Any],
        policy_version: str,
        version: int = 1,
    ) -> WorkflowIR:
        """Bind the holes and produce a compilable IR. Deterministic; no model."""
        resolved = self._resolve(bindings)

        steps: list[WorkflowIRStep] = []
        domains: set[str] = set()
        credentials: set[str] = set()
        for raw in self.steps:
            step = dict(raw)
            bound = {key: _substitute(value, resolved) for key, value in step.items()}

            effects = [WorkflowStepEffect(e) for e in bound.pop("effects", ["READ"])]
            domain = bound.pop("external_domain", None)
            credential = bound.pop("credential_alias", None)
            if domain:
                domains.add(str(domain))
            if credential:
                credentials.add(str(credential))

            steps.append(
                WorkflowIRStep(
                    step_id=str(bound["step_id"]),
                    primitive=Primitive(str(bound["primitive"])),
                    operation=str(bound["operation"]),
                    input_bindings=dict(bound.get("input_bindings", {})),
                    output_name=bound.get("output_name"),
                    external_domain=str(domain) if domain else None,
                    credential_alias=str(credential) if credential else None,
                    effects=effects,
                    action_class=ActionClass(str(bound.get("action_class", "A1"))),
                    timeout_ms=int(bound.get("timeout_ms", 30_000)),
                    retry_class=RetryClass(str(bound.get("retry_class", "IDEMPOTENT"))),
                    max_attempts=int(bound.get("max_attempts", 1)),
                    idempotency_key_expr=bound.get("idempotency_key_expr"),
                    precondition=bound.get("precondition"),
                    postcondition=bound.get("postcondition"),
                )
            )

        return WorkflowIR(
            ir_id=new_id("ir"),
            family=self.family,
            semantic_goal=_substitute(self.summary, resolved),
            version=version,
            trigger=_substitute(dict(self.steps[0].get("trigger", {})), resolved) or {"kind": "INVOKE"},
            inputs_schema={"properties": {hole.name: {"type": "string"} for hole in self.holes}},
            variables={},
            steps=steps,
            edges=[WorkflowIREdge(from_step=a, to_step=b) for a, b in self.edges],
            credential_requirements=sorted(credentials),
            external_domains=sorted(domains),
            evidence_requirements=list(self.evidence_requirements),
            verifier=dict(self.verifier),
            # §146 — derived, never taken from the template's own claim.
            action_class=strongest_class(steps),
            latency_class=self.latency_class,
            generated_from=[f"template:{self.template_id}"],
            policy_version=policy_version,
            compiler_version=COMPILER_VERSION,
        )

    def _resolve(self, bindings: dict[str, Any]) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for hole in self.holes:
            if hole.name in bindings:
                value = bindings[hole.name]
            elif hole.default is not None:
                value = hole.default
            elif hole.required:
                raise TemplateError(f"template_binding_missing:{self.template_id}:{hole.name}")
            else:
                continue
            if hole.enum is not None and value not in hole.enum:
                raise TemplateError(
                    f"template_binding_not_permitted:{self.template_id}:{hole.name}:{value}"
                )
            resolved[hole.name] = value

        unknown = sorted(set(bindings) - {hole.name for hole in self.holes})
        if unknown:
            # A caller passing an unknown binding is usually specialising the wrong
            # template; silently ignoring it produces a subtly wrong workflow.
            raise TemplateError(f"template_binding_unknown:{self.template_id}:{','.join(unknown)}")
        return resolved


def _substitute(value: Any, bindings: dict[str, Any]) -> Any:
    """Replace ``{{hole}}`` references throughout a nested structure."""
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in bindings:
                raise TemplateError(f"template_hole_unbound:{name}")
            return str(bindings[name])

        if _HOLE.fullmatch(value):
            # A whole-value hole keeps its native type (dict, list, int).
            return bindings[_HOLE.fullmatch(value).group(1)]  # type: ignore[union-attr]
        return _HOLE.sub(replace, value)
    if isinstance(value, dict):
        return {key: _substitute(item, bindings) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute(item, bindings) for item in value]
    return value


# --------------------------------------------------------------- the library

#: §27's skeletons, expressed as §60 topology macros. Deliberately small: each is
#: a shape that recurs across many goals, not a one-off workflow.
COLLECT_NORMALISE_INGEST = WorkflowTemplate(
    template_id="collect_normalise_ingest.v1",
    family="collect_normalise_ingest",
    macro="COLLECT_NORMALISE_INGEST",
    summary="collect {{document_type}} from {{source_label}} and seal it into VAN evidence",
    holes=(
        TemplateHole("source_label", "human name of the source system"),
        TemplateHole("document_type", "what is being collected, e.g. statement"),
        TemplateHole("source_domain", "admitted domain the documents come from"),
        TemplateHole("source_path", "path returning the document list"),
        TemplateHole("credential_alias", "connector:// alias for the source"),
        TemplateHole("cron", "schedule expression", required=False, default="0 6 * * 5"),
    ),
    steps=(
        {
            "step_id": "s_trigger",
            "primitive": "SCHEDULE_TRIGGER",
            "operation": "fire",
            "trigger": {"kind": "SCHEDULE", "cron": "{{cron}}"},
            "input_bindings": {"rule": {"cron": "{{cron}}"}},
            "effects": ["READ"],
            "action_class": "A1",
            "timeout_ms": 5_000,
            "retry_class": "IDEMPOTENT",
            "max_attempts": 1,
        },
        {
            "step_id": "s_fetch",
            "primitive": "HTTP_GET",
            "operation": "fetch_documents",
            "input_bindings": {"url": "https://{{source_domain}}{{source_path}}"},
            "external_domain": "{{source_domain}}",
            "credential_alias": "{{credential_alias}}",
            "effects": ["NETWORK_READ"],
            "action_class": "A2",
            "timeout_ms": 20_000,
            "retry_class": "IDEMPOTENT",
            "max_attempts": 3,
            "output_name": "documents",
        },
        {
            "step_id": "s_hash",
            "primitive": "HASH",
            "operation": "digest_documents",
            "input_bindings": {"payload": "$documents"},
            "effects": ["READ"],
            "action_class": "A1",
            "timeout_ms": 10_000,
            "retry_class": "IDEMPOTENT",
            "max_attempts": 1,
            "output_name": "digests",
        },
        {
            "step_id": "s_seal",
            "primitive": "VAN_EVIDENCE",
            "operation": "seal_artifact",
            "input_bindings": {"payload": "$documents", "digests": "$digests"},
            "effects": ["WRITE"],
            "action_class": "A3",
            "timeout_ms": 15_000,
            "retry_class": "IDEMPOTENT_WITH_KEY",
            "max_attempts": 2,
            "idempotency_key_expr": "$digests.primary",
            "postcondition": {"kind": "READ_BACK", "field": "evidence_pointer"},
        },
    ),
    edges=(("s_trigger", "s_fetch"), ("s_fetch", "s_hash"), ("s_hash", "s_seal")),
    verifier={"kind": "READ_BACK"},
    evidence_requirements=("document_digest", "evidence_pointer"),
)

MONITOR_DIFF_NOTIFY = WorkflowTemplate(
    template_id="monitor_diff_notify.v1",
    family="monitor_diff_notify",
    macro="MONITOR_DIFF_NOTIFY",
    summary="watch {{source_label}} and raise an attention item when it changes",
    holes=(
        TemplateHole("source_label", "human name of the watched source"),
        TemplateHole("source_domain", "admitted domain to poll"),
        TemplateHole("source_path", "path to poll"),
        TemplateHole("cron", "poll schedule", required=False, default="0 * * * *"),
        TemplateHole("severity", "attention severity", required=False, default="INFO",
                     enum=("INFO", "FOLLOW_UP", "BLOCKER", "URGENT")),
    ),
    steps=(
        {
            "step_id": "s_trigger",
            "primitive": "SCHEDULE_TRIGGER",
            "operation": "fire",
            "trigger": {"kind": "SCHEDULE", "cron": "{{cron}}"},
            "input_bindings": {"rule": {"cron": "{{cron}}"}},
            "effects": ["READ"],
            "action_class": "A1",
            "timeout_ms": 5_000,
            "retry_class": "IDEMPOTENT",
            "max_attempts": 1,
        },
        {
            "step_id": "s_poll",
            "primitive": "HTTP_GET",
            "operation": "poll_source",
            "input_bindings": {"url": "https://{{source_domain}}{{source_path}}"},
            "external_domain": "{{source_domain}}",
            "effects": ["NETWORK_READ"],
            "action_class": "A2",
            "timeout_ms": 20_000,
            "retry_class": "IDEMPOTENT",
            "max_attempts": 3,
            "output_name": "current",
        },
        {
            "step_id": "s_diff",
            "primitive": "DEDUPE",
            "operation": "change_detect",
            "input_bindings": {"payload": "$current"},
            "effects": ["READ"],
            "action_class": "A1",
            "timeout_ms": 10_000,
            "retry_class": "IDEMPOTENT",
            "max_attempts": 1,
            "output_name": "change",
        },
        {
            "step_id": "s_emit",
            "primitive": "VAN_EVENT",
            "operation": "emit_attention",
            "input_bindings": {
                "change": "$change",
                "severity": "{{severity}}",
                "title": "{{source_label}} changed",
            },
            "effects": ["NOTIFY"],
            "action_class": "A3",
            "timeout_ms": 10_000,
            "retry_class": "IDEMPOTENT_WITH_KEY",
            "max_attempts": 2,
            "idempotency_key_expr": "$change.digest",
            "postcondition": {"kind": "RECEIPT", "field": "attention_id"},
        },
    ),
    edges=(("s_trigger", "s_poll"), ("s_poll", "s_diff"), ("s_diff", "s_emit")),
    verifier={"kind": "RECEIPT"},
    evidence_requirements=("change_digest",),
)

EVENT_FILTER_EMIT = WorkflowTemplate(
    template_id="event_filter_emit.v1",
    family="event_filter_emit",
    macro="EVENT_FILTER_EMIT",
    summary="turn {{source_label}} webhooks into canonical VAN events",
    holes=(
        TemplateHole("source_label", "human name of the event source"),
        TemplateHole("webhook_path", "private ingress path for this source"),
        TemplateHole("event_type", "canonical event type to emit"),
    ),
    steps=(
        {
            "step_id": "s_hook",
            "primitive": "WEBHOOK_TRIGGER",
            "operation": "receive",
            "trigger": {"kind": "WEBHOOK", "path": "{{webhook_path}}"},
            "input_bindings": {"path": "{{webhook_path}}", "method": "POST"},
            "effects": ["READ"],
            "action_class": "A1",
            "timeout_ms": 5_000,
            "retry_class": "NEVER_RETRY",
            "max_attempts": 1,
            "output_name": "inbound",
        },
        {
            "step_id": "s_filter",
            "primitive": "FILTER",
            "operation": "validate_and_dedupe",
            "input_bindings": {"payload": "$inbound"},
            "effects": ["READ"],
            "action_class": "A1",
            "timeout_ms": 5_000,
            "retry_class": "IDEMPOTENT",
            "max_attempts": 1,
            "output_name": "accepted",
        },
        {
            "step_id": "s_emit",
            "primitive": "VAN_EVENT",
            "operation": "emit_external_event",
            "input_bindings": {"payload": "$accepted", "event_type": "{{event_type}}"},
            "effects": ["WRITE"],
            "action_class": "A2",
            "timeout_ms": 10_000,
            "retry_class": "IDEMPOTENT_WITH_KEY",
            "max_attempts": 2,
            "idempotency_key_expr": "$accepted.dedupe_key",
            "postcondition": {"kind": "RECEIPT", "field": "event_id"},
        },
    ),
    edges=(("s_hook", "s_filter"), ("s_filter", "s_emit")),
    verifier={"kind": "RECEIPT"},
)

FETCH_MAP_VERIFY = WorkflowTemplate(
    template_id="fetch_map_verify.v1",
    family="fetch_map_verify",
    macro="FETCH_MAP_VERIFY",
    summary="read {{resource_label}} from {{source_domain}} and map it to a VAN schema",
    holes=(
        TemplateHole("resource_label", "what is being read"),
        TemplateHole("source_domain", "admitted domain"),
        TemplateHole("source_path", "path to read"),
        TemplateHole("credential_alias", "connector:// alias", required=False),
    ),
    steps=(
        {
            "step_id": "s_fetch",
            "primitive": "HTTP_GET",
            "operation": "fetch_resource",
            "input_bindings": {"url": "https://{{source_domain}}{{source_path}}"},
            "external_domain": "{{source_domain}}",
            "effects": ["NETWORK_READ"],
            "action_class": "A2",
            "timeout_ms": 20_000,
            "retry_class": "IDEMPOTENT",
            "max_attempts": 3,
            "output_name": "raw",
        },
        {
            "step_id": "s_map",
            "primitive": "MAP_FIELDS",
            "operation": "to_van_schema",
            "input_bindings": {"payload": "$raw"},
            "effects": ["READ"],
            "action_class": "A1",
            "timeout_ms": 10_000,
            "retry_class": "IDEMPOTENT",
            "max_attempts": 1,
            "output_name": "mapped",
        },
    ),
    edges=(("s_fetch", "s_map"),),
    verifier={},
)

TEMPLATES: dict[str, WorkflowTemplate] = {
    template.template_id: template
    for template in (
        COLLECT_NORMALISE_INGEST,
        MONITOR_DIFF_NOTIFY,
        EVENT_FILTER_EMIT,
        FETCH_MAP_VERIFY,
    )
}

#: §26 — goal classes the WARM path can serve without any model involvement.
GOAL_CLASS_TEMPLATES: dict[str, str] = {
    "BROKER_STATEMENT_COLLECTION": "collect_normalise_ingest.v1",
    "DOCUMENT_COLLECTION": "collect_normalise_ingest.v1",
    "SOURCE_MONITORING": "monitor_diff_notify.v1",
    "CHANGE_NOTIFICATION": "monitor_diff_notify.v1",
    "EVENT_INGESTION": "event_filter_emit.v1",
    "RESOURCE_READ": "fetch_map_verify.v1",
}


class TemplateLibrary:
    """Lookup and specialisation for the WARM path."""

    def __init__(self, templates: dict[str, WorkflowTemplate] | None = None) -> None:
        self._templates = dict(templates or TEMPLATES)

    def get(self, template_id: str) -> WorkflowTemplate:
        try:
            return self._templates[template_id]
        except KeyError as exc:
            raise TemplateError(f"unknown_template:{template_id}") from exc

    def for_goal_class(self, goal_class: str) -> WorkflowTemplate | None:
        """§26 — map a canonical goal class onto a skeleton, or None for COLD."""
        template_id = GOAL_CLASS_TEMPLATES.get(goal_class.strip().upper().replace(" ", "_"))
        return self._templates.get(template_id) if template_id else None

    def specialise(
        self, template_id: str, *, bindings: dict[str, Any], policy_version: str, version: int = 1
    ) -> WorkflowIR:
        return self.get(template_id).specialise(
            bindings=bindings, policy_version=policy_version, version=version
        )

    @property
    def template_ids(self) -> list[str]:
        return sorted(self._templates)


__all__ = [
    "GOAL_CLASS_TEMPLATES",
    "TEMPLATES",
    "TemplateError",
    "TemplateHole",
    "TemplateLibrary",
    "WorkflowTemplate",
]
