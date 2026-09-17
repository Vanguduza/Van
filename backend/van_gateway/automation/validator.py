"""Rev 1.3 §§40, 145-146 — workflow static analyser.

§40's closing line is the point of this module: *"This turns workflow safety into
code, not prompt instructions."* Nothing here consults a model. A WorkflowIR
either satisfies the repository's policy or it is rejected with a named reason.

The analyser runs before compilation, so an unsafe graph never becomes n8n JSON.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from van_gateway.automation.canonical import digest
from van_gateway.automation.models import (
    DISALLOWED_PRIMITIVE_NAMES,
    MUTATING_EFFECTS,
    PROHIBITED_EFFECTS,
    RANK,
    Primitive,
    RetryClass,
    TRIGGER_PRIMITIVES,
    WorkflowIR,
    WorkflowStepEffect,
    strongest_class,
)
from van_gateway.automation.policy import AutomationPolicy, PolicyError, load_automation_policy
from van_gateway.models import ActionClass


@dataclass
class ValidationReport:
    """§311 — the report is itself an artifact, digested and stored."""

    ok: bool
    ir_id: str
    derived_action_class: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    topological_order: list[str] = field(default_factory=list)
    policy_version: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "ir_id": self.ir_id,
            "derived_action_class": self.derived_action_class,
            "errors": sorted(self.errors),
            "warnings": sorted(self.warnings),
            "topological_order": self.topological_order,
            "policy_version": self.policy_version,
        }

    @property
    def report_digest(self) -> str:
        return digest(self.as_dict())


class WorkflowValidator:
    """Rejects an IR that violates graph invariants, effect policy or class derivation."""

    def __init__(self, policy: AutomationPolicy | None = None) -> None:
        self.policy = policy or load_automation_policy()

    def validate(self, ir: WorkflowIR) -> ValidationReport:
        errors: list[str] = []
        warnings: list[str] = []

        errors.extend(self._check_steps(ir))
        order, graph_errors = self._check_graph(ir)
        errors.extend(graph_errors)
        errors.extend(self._check_effects(ir))
        errors.extend(self._check_domains(ir))
        errors.extend(self._check_credentials(ir))
        errors.extend(self._check_limits(ir))

        derived = strongest_class(ir.steps)
        errors.extend(self._check_action_class(ir, derived))

        if not ir.verifier and any(step.mutates for step in ir.steps):
            errors.append("MISSING_WORKFLOW_VERIFIER")

        return ValidationReport(
            ok=not errors,
            ir_id=ir.ir_id,
            derived_action_class=derived.value,
            errors=errors,
            warnings=warnings,
            topological_order=order,
            policy_version=self.policy.policy_version,
        )

    def validate_or_raise(self, ir: WorkflowIR) -> ValidationReport:
        report = self.validate(ir)
        if not report.ok:
            raise PolicyError(";".join(sorted(report.errors)))
        return report

    # ------------------------------------------------------------------ checks

    def _check_steps(self, ir: WorkflowIR) -> list[str]:
        errors: list[str] = []
        if not ir.steps:
            errors.append("EMPTY_WORKFLOW")
        seen: set[str] = set()
        for step in ir.steps:
            if step.step_id in seen:
                errors.append(f"DUPLICATE_STEP_ID:{step.step_id}")
            seen.add(step.step_id)

            if step.primitive.value in DISALLOWED_PRIMITIVE_NAMES:
                errors.append(f"DISALLOWED_PRIMITIVE:{step.primitive.value}")
            if step.timeout_ms <= 0:
                errors.append(f"MISSING_TIMEOUT:{step.step_id}")
            if step.retry_class not in set(RetryClass):
                errors.append(f"INVALID_RETRY_CLASS:{step.step_id}")

            # §79 — a non-idempotent mutation must never be retried blindly.
            if step.mutates and step.retry_class is RetryClass.IDEMPOTENT:
                errors.append(f"MUTATION_MARKED_BLINDLY_IDEMPOTENT:{step.step_id}")
            if step.retry_class is RetryClass.NON_IDEMPOTENT and step.max_attempts > 1:
                errors.append(f"NON_IDEMPOTENT_STEP_RETRIED:{step.step_id}")
            if step.retry_class is RetryClass.NEVER_RETRY and step.max_attempts != 1:
                errors.append(f"NEVER_RETRY_STEP_RETRIED:{step.step_id}")
            if step.retry_class is RetryClass.IDEMPOTENT_WITH_KEY and not step.idempotency_key_expr:
                errors.append(f"MISSING_IDEMPOTENCY_KEY:{step.step_id}")

            # §40 — a consequential operation without a verifier is rejected.
            if (
                step.mutates
                and self.policy.consequential_effects_require_verifier
                and step.postcondition is None
            ):
                errors.append(f"CONSEQUENTIAL_STEP_WITHOUT_VERIFIER:{step.step_id}")

            # A mutation that never declared a mutating effect is a hidden effect.
            if step.action_class in (ActionClass.A3, ActionClass.A4) and not step.mutates:
                errors.append(f"MUTATION_WITHOUT_DECLARED_EFFECT:{step.step_id}")

            if step.primitive in (Primitive.HTTP_GET, Primitive.HTTP_REQUEST) and not step.external_domain:
                errors.append(f"HTTP_STEP_WITHOUT_DOMAIN:{step.step_id}")
        return errors

    def _check_graph(self, ir: WorkflowIR) -> tuple[list[str], list[str]]:
        """§145 — deterministic topological ordering, no cycles, no orphans."""
        errors: list[str] = []
        ids = [step.step_id for step in ir.steps]
        id_set = set(ids)

        adjacency: dict[str, list[str]] = defaultdict(list)
        indegree: dict[str, int] = {step_id: 0 for step_id in ids}
        for edge in ir.edges:
            if edge.from_step not in id_set:
                errors.append(f"EDGE_FROM_UNKNOWN_STEP:{edge.from_step}")
                continue
            if edge.to_step not in id_set:
                errors.append(f"EDGE_TO_UNKNOWN_STEP:{edge.to_step}")
                continue
            adjacency[edge.from_step].append(edge.to_step)
            indegree[edge.to_step] += 1

        starts = [step_id for step_id, deg in indegree.items() if deg == 0]
        trigger_ids = {s.step_id for s in ir.steps if s.primitive in TRIGGER_PRIMITIVES}
        if len(starts) > 1 and len(ir.steps) > 1:
            # Multiple roots are only legitimate when exactly one is a trigger.
            if len(trigger_ids.intersection(starts)) != 1:
                errors.append("MULTIPLE_UNDEFINED_START_NODES")
        if len(ir.steps) > 1 and not trigger_ids:
            errors.append("MISSING_TRIGGER")

        # Kahn's algorithm with a sorted frontier: deterministic ordering (§145, §150).
        order: list[str] = []
        frontier = sorted(starts)
        remaining = dict(indegree)
        while frontier:
            node = frontier.pop(0)
            order.append(node)
            for neighbour in sorted(adjacency[node]):
                remaining[neighbour] -= 1
                if remaining[neighbour] == 0:
                    frontier.append(neighbour)
                    frontier.sort()
        if len(order) != len(ids):
            errors.append("WORKFLOW_GRAPH_CYCLE")

        if len(ir.steps) > 1:
            connected = set(order)
            orphans = sorted(id_set - connected)
            for orphan in orphans:
                errors.append(f"ORPHANED_STEP:{orphan}")

        terminals = [step_id for step_id in ids if not adjacency.get(step_id)]
        if not terminals:
            errors.append("MISSING_TERMINAL_STATE")

        errors.extend(self._check_variable_bindings(ir))
        return order, errors

    def _check_variable_bindings(self, ir: WorkflowIR) -> list[str]:
        """Reject unbound variables and undefined output references (§145)."""
        errors: list[str] = []
        defined: set[str] = set(ir.variables) | set(ir.inputs_schema.get("properties", {}))
        for step in ir.steps:
            for binding in step.input_bindings.values():
                if not isinstance(binding, str) or not binding.startswith("$"):
                    continue
                name = binding[1:].split(".", 1)[0]
                if name not in defined:
                    errors.append(f"UNBOUND_VARIABLE:{step.step_id}:{name}")
            if step.output_name:
                defined.add(step.output_name)
        return errors

    def _check_effects(self, ir: WorkflowIR) -> list[str]:
        errors: list[str] = []
        for step in ir.steps:
            for effect in step.effects:
                if effect in PROHIBITED_EFFECTS:
                    errors.append(f"PROHIBITED_EFFECT:{step.step_id}:{effect.value}")
            if step.action_class is ActionClass.A5:
                errors.append(f"PROHIBITED_WORKFLOW:{step.step_id}")
            if WorkflowStepEffect.SECURITY in step.effects and step.action_class is ActionClass.A1:
                errors.append(f"SECURITY_EFFECT_UNDERCLASSED:{step.step_id}")
        return errors

    def _check_domains(self, ir: WorkflowIR) -> list[str]:
        errors: list[str] = []
        declared = set(ir.external_domains)
        for step in ir.steps:
            if step.external_domain is None:
                continue
            if step.external_domain not in declared:
                errors.append(f"UNDECLARED_STEP_DOMAIN:{step.step_id}:{step.external_domain}")
            try:
                self.policy.domains.check_domain(step.external_domain)
            except PolicyError as exc:
                errors.append(f"UNAPPROVED_EXTERNAL_DOMAIN:{step.step_id}:{exc}")
        return errors

    def _check_credentials(self, ir: WorkflowIR) -> list[str]:
        """§46 — the IR carries credential aliases, never values."""
        errors: list[str] = []
        for step in ir.steps:
            alias = step.credential_alias
            if alias is None:
                continue
            if not alias.startswith("connector://"):
                errors.append(f"CREDENTIAL_ALIAS_MALFORMED:{step.step_id}")
            if alias not in ir.credential_requirements:
                errors.append(f"UNDECLARED_CREDENTIAL:{step.step_id}:{alias}")
            for marker in ("secret", "token", "password", "apikey", "api_key", "bearer"):
                for value in step.input_bindings.values():
                    if isinstance(value, str) and marker in value.lower() and "$" not in value:
                        errors.append(f"RAW_CREDENTIAL_VALUE_SUSPECTED:{step.step_id}")
                        break
        return errors

    def _check_limits(self, ir: WorkflowIR) -> list[str]:
        errors: list[str] = []
        policy = self.policy
        if policy.max_steps and len(ir.steps) > policy.max_steps:
            errors.append(f"WORKFLOW_TOO_LARGE:{len(ir.steps)}>{policy.max_steps}")
        if policy.max_external_domains and len(set(ir.external_domains)) > policy.max_external_domains:
            errors.append("TOO_MANY_EXTERNAL_DOMAINS")
        branches = sum(1 for s in ir.steps if s.primitive in (Primitive.SWITCH, Primitive.FILTER))
        if policy.max_branches and branches > policy.max_branches:
            errors.append("TOO_MANY_BRANCHES")
        return errors

    def _check_action_class(self, ir: WorkflowIR, derived: ActionClass) -> list[str]:
        """§146 — never trust the class the caller supplied."""
        errors: list[str] = []
        if derived is ActionClass.A5:
            errors.append("PROHIBITED_WORKFLOW")
        if RANK[ir.action_class.value] < RANK[derived.value]:
            errors.append(f"ACTION_CLASS_UNDERDECLARED:{ir.action_class.value}<{derived.value}")
        if self.policy.allowed_action_classes and derived.value not in self.policy.allowed_action_classes:
            errors.append(f"ACTION_CLASS_NOT_PERMITTED:{derived.value}")
        return errors


__all__ = ["ValidationReport", "WorkflowValidator"]
