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


#: The observer's own "I could read something" signal. It is not a fact about the world the
#: action was meant to change, so naming it as the predicate field declares nothing.
EXISTENCE_SIGNAL = "exists"


def is_blank_expected(value: Any) -> bool:
    """Review I3 MINOR-5 — an empty (or whitespace-only) expected string matches a blank
    page's ``visible_text``/``title``, so it asserts nothing an observation can be wrong
    about. It is refused like an undeclared value."""
    return isinstance(value, str) and not value.strip()


def strictly_equal(expected: Any, observed: Any) -> bool:
    """Type-strict equality (review I3 MINOR-5).

    Python's ``==`` says ``True == 1`` and ``1 == 1.0``, so a declared ``True`` was VERIFIED by
    an observed ``1``. Types must match exactly (``bool`` is not ``int``, ``int`` is not
    ``float``), recursively through lists and dicts.
    """
    if type(expected) is not type(observed):
        return False
    if isinstance(expected, dict):
        return expected.keys() == observed.keys() and all(
            strictly_equal(expected[key], observed[key]) for key in expected
        )
    if isinstance(expected, (list, tuple)):
        return len(expected) == len(observed) and all(
            strictly_equal(e, o) for e, o in zip(expected, observed)
        )
    return expected == observed


class PostconditionSpec(BaseModel):
    """What the IR declared must become true (§165)."""

    kind: str
    field: str | None = None
    expected: Any = None
    correlation_keys: list[str] = Field(default_factory=list)
    #: Reviewer I2 N-1 — the caller-declared value each correlation key must be observed to
    #: hold. A key with no declared value is only a name for something the observer reports
    #: about itself (a Harness read-back always carries ``url``, ``title``, ``visible_text``
    #: and ``exists``), so it can never be observed *wrong* and asserts nothing.
    expected_correlation: dict[str, Any] = Field(default_factory=dict)

    @property
    def correlation_predicates(self) -> dict[str, Any]:
        """Every correlation key the spec names, mapped to its declared expected value.

        A key named in ``correlation_keys`` without a declared value maps to ``None``, which
        :attr:`undeclared_correlation_keys` reports and :attr:`declares_predicate` refuses.
        """
        keys = list(dict.fromkeys([*self.correlation_keys, *self.expected_correlation]))
        return {key: self.expected_correlation.get(key) for key in keys}

    @property
    def undeclared_correlation_keys(self) -> list[str]:
        """Correlation keys that carry no caller-declared expected value, or name the
        observer's own existence signal. Each one would pass on any readable observation."""
        return [
            key for key, value in self.correlation_predicates.items()
            if value is None or key == EXISTENCE_SIGNAL or is_blank_expected(value)
        ]

    @property
    def declares_predicate(self) -> bool:
        """True when the spec names something an observation can be *wrong* about.

        Reviewer I M-1: ``{"kind": "READ_BACK"}`` alone was VERIFIED whenever the observer
        returned anything at all (a readable page is ``exists: True``), so a spec that
        asserted nothing passed. Reviewer I2 N-1: ``correlation_keys=["url"]`` (or ``title``,
        ``exists``, ``visible_text``) did the same, because the observer supplies those keys
        on every read. A predicate is a ``field`` with an ``expected`` value (other than the
        existence signal itself) or correlation keys *each* matched against a caller-declared
        expected value; one undeclared key makes the whole spec assert nothing reliable, so
        it fails closed rather than silently dropping the key.
        """
        if self.undeclared_correlation_keys:
            return False
        if self.field is not None and is_blank_expected(self.expected):
            # Review I3 MINOR-5: `expected=""` is VERIFIED by any blank page.
            return False
        has_field_predicate = (
            self.field is not None and self.field != EXISTENCE_SIGNAL and self.expected is not None
        )
        return has_field_predicate or bool(self.correlation_predicates)


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

        if not spec.declares_predicate:
            # M-1 — a postcondition that names no field/expected value and no correlation
            # key cannot be observed false, so observing it proves nothing. Enforced here so
            # every caller (automation dispatch, the browser router, the subagent runner)
            # gets the same answer.
            return VerificationResult(
                outcome=VerificationOutcome.UNVERIFIABLE,
                verifier_type=verifier_type,
                detail=(
                    "postcondition declares no predicate (field/expected, or correlation keys "
                    "each with a declared, non-blank expected value)"
                    + (
                        f"; undeclared correlation keys: {sorted(spec.undeclared_correlation_keys)}"
                        if spec.undeclared_correlation_keys else ""
                    )
                ),
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
            if not strictly_equal(spec.expected, actual):
                return VerificationResult(
                    outcome=VerificationOutcome.FAILED,
                    verifier_type=verifier_type,
                    observed=observed,
                    detail=f"{spec.field} mismatch",
                )

        predicates = spec.correlation_predicates
        correlation = {key: observed.get(key) for key in predicates}
        if any(value is None for value in correlation.values()):
            # §166 — a correlated existence check that cannot correlate is partial,
            # because something exists but we cannot prove it is *ours*.
            return VerificationResult(
                outcome=VerificationOutcome.PARTIAL,
                verifier_type=verifier_type,
                observed=observed,
                correlation=correlation,
                detail="correlation incomplete",
            )
        mismatched = sorted(
            key for key, value in correlation.items() if not strictly_equal(predicates[key], value)
        )
        if mismatched:
            # N-1 — an observed correlation value that is not the declared one is evidence the
            # effect is someone else's (or absent), never a pass.
            return VerificationResult(
                outcome=VerificationOutcome.FAILED,
                verifier_type=verifier_type,
                observed=observed,
                correlation=correlation,
                detail=f"correlation mismatch: {mismatched}",
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


# §167 — "a notification is verified by provider receipt, not by send returning 200" —
# is enforced in `verification.production.UNOBSERVABLE_POSTCONDITION_KINDS`, which declares
# RECEIPT unobservable because no receipt store exists that the gateway can read
# independently of the engine that sent the notification. `NotificationObserver` was a
# wrapper around a lookup that cannot exist, referenced by nothing (P2-VERIFY-002). Keeping
# it would suggest the observation is available; the rule survives where it is enforced.


__all__ = [
    "EXISTENCE_SIGNAL",
    "DocumentUploadObserver",
    "PostconditionObserver",
    "PostconditionSpec",
    "VerificationOutcome",
    "VerificationResult",
    "WorkflowVerifier",
    "is_blank_expected",
    "strictly_equal",
]
