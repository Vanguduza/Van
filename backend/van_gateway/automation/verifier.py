"""Rev 1.3 §§80-82, 165-167 — independent postcondition verification.

The single most important rule here is from `config/automation/policy.yaml`:
``engine_success_is_owner_success: false``. n8n reporting "workflow succeeded" is
an engine claim about its own execution, not evidence that the world changed.
VAN only reports ``VERIFIED_SUCCESS`` when an **independent** observation
confirms the declared postcondition.

Where no verifier can observe the effect, the honest answer is ``UNVERIFIABLE``
(a first-class Rev 3.1 ExecutionStatus), never success.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from van_gateway.action.models import VerifierType


class VerificationOutcome(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    UNVERIFIABLE = "UNVERIFIABLE"


class PostconditionSpec(BaseModel):
    """What the IR declared must become true (§165)."""

    kind: str
    field: str | None = None
    expected: Any = None
    correlation_keys: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    outcome: VerificationOutcome
    verifier_type: VerifierType
    observed: dict[str, Any] = Field(default_factory=dict)
    correlation: dict[str, Any] = Field(default_factory=dict)
    evidence_pointer: str | None = None
    detail: str | None = None

    @property
    def success(self) -> bool:
        return self.outcome is VerificationOutcome.VERIFIED


class PostconditionObserver(Protocol):
    """Independent observation of the target system. Never the executing engine."""

    async def observe(self, spec: PostconditionSpec, context: dict[str, Any]) -> dict[str, Any]:
        ...


class WorkflowVerifier:
    """§§165-167 — turns a declared postcondition plus an observation into an outcome."""

    def __init__(self, observers: dict[str, PostconditionObserver] | None = None) -> None:
        self.observers = observers or {}

    async def verify(
        self,
        *,
        spec: PostconditionSpec | None,
        verifier_type: VerifierType,
        engine_reported_success: bool,
        context: dict[str, Any] | None = None,
    ) -> VerificationResult:
        context = context or {}

        if verifier_type is VerifierType.NONE or spec is None:
            # No declared postcondition: the honest result is UNVERIFIABLE, even
            # when the engine is happy. §21: 200/accepted is not completion.
            return VerificationResult(
                outcome=VerificationOutcome.UNVERIFIABLE,
                verifier_type=verifier_type,
                detail="no postcondition declared",
            )

        observer = self.observers.get(spec.kind)
        if observer is None:
            return VerificationResult(
                outcome=VerificationOutcome.UNVERIFIABLE,
                verifier_type=verifier_type,
                detail=f"no observer registered for {spec.kind}",
            )

        try:
            observed = await observer.observe(spec, context)
        except Exception as exc:  # noqa: BLE001 - an observer failure is not success
            return VerificationResult(
                outcome=VerificationOutcome.UNVERIFIABLE,
                verifier_type=verifier_type,
                detail=f"observation failed: {type(exc).__name__}",
            )

        if not observed.get("exists", False):
            # The engine may have reported success; the world disagrees.
            return VerificationResult(
                outcome=VerificationOutcome.FAILED,
                verifier_type=verifier_type,
                observed=observed,
                detail="declared postcondition absent"
                + (" despite engine success" if engine_reported_success else ""),
            )

        if spec.field is not None and spec.expected is not None:
            actual = observed.get(spec.field)
            if actual != spec.expected:
                return VerificationResult(
                    outcome=VerificationOutcome.FAILED,
                    verifier_type=verifier_type,
                    observed=observed,
                    detail=f"{spec.field} mismatch",
                )

        correlation = {key: observed.get(key) for key in spec.correlation_keys}
        if spec.correlation_keys and any(value is None for value in correlation.values()):
            # §166 — a correlated existence check that cannot correlate is partial,
            # because something exists but we cannot prove it is *ours*.
            return VerificationResult(
                outcome=VerificationOutcome.PARTIAL,
                verifier_type=verifier_type,
                observed=observed,
                correlation=correlation,
                detail="correlation incomplete",
            )

        return VerificationResult(
            outcome=VerificationOutcome.VERIFIED,
            verifier_type=verifier_type,
            observed=observed,
            correlation=correlation,
            evidence_pointer=observed.get("evidence_pointer"),
        )


class DocumentUploadObserver:
    """§166 — example postcondition: the document exists with the expected digest."""

    def __init__(self, lookup: Any) -> None:
        self._lookup = lookup

    async def observe(self, spec: PostconditionSpec, context: dict[str, Any]) -> dict[str, Any]:
        return await self._lookup(spec, context)


class NotificationObserver:
    """§167 — a notification is verified by provider receipt, not by send returning 200."""

    def __init__(self, lookup: Any) -> None:
        self._lookup = lookup

    async def observe(self, spec: PostconditionSpec, context: dict[str, Any]) -> dict[str, Any]:
        return await self._lookup(spec, context)


__all__ = [
    "DocumentUploadObserver",
    "NotificationObserver",
    "PostconditionObserver",
    "PostconditionSpec",
    "VerificationOutcome",
    "VerificationResult",
    "WorkflowVerifier",
]
