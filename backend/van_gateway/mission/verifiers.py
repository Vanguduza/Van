"""Rev 1 §6 — verifier adapters per capability class.

Mission Core refuses VERIFIED_SUCCESS without a receipt. This is where receipts
come from, and the design rule is the one §6 states and §55 repeats: *no success
without verifier evidence*. Each adapter observes the target system
independently and reports what it actually saw.

The word doing the work is **independently**. A verifier that asks the executor
whether it succeeded has verified nothing — it has forwarded a claim. So every
adapter takes an observation callable that reaches the target system, and
`EngineReportVerifier` exists only to make the forbidden case explicit and
always UNVERIFIABLE, so "the worker said OK" can be represented without ever
being mistaken for confirmation.

§39's development flow is served by the same machinery: a repository SHA and a
CI run are evidence in exactly the way a provider receipt is, which is why
"merge happened" and "the notebook exists" verify through one interface.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Protocol

from van_gateway.mission.models import (
    SuccessContract,
    VerificationRecord,
    VerificationStatus,
)

#: An observation reaches the target system and returns what it found. Async
#: because every real one is I/O.
Observation = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class Verifier(Protocol):
    verifier_version: str

    async def verify(
        self, contract: SuccessContract, context: dict[str, Any]
    ) -> VerificationRecord:
        ...


def _record(
    *,
    status: VerificationStatus,
    version: str,
    observed: dict[str, Any] | None = None,
    missing: list[str] | None = None,
    evidence: list[str] | None = None,
    now_ms: int | None = None,
) -> VerificationRecord:
    return VerificationRecord(
        status=status, observed_postconditions=observed or {},
        missing_postconditions=sorted(missing or []),
        evidence_refs=sorted(set(evidence or [])), verifier_version=version,
        verified_at_ms=int(time.time() * 1000) if now_ms is None else now_ms,
    )


def _compare(contract: SuccessContract, observed: dict[str, Any]) -> list[str]:
    """Which declared postconditions the observation did not satisfy.

    A postcondition the observation simply did not mention counts as missing
    rather than satisfied: absence of contradiction is not confirmation.
    """
    missing = []
    for key, expected in contract.postconditions.items():
        if key not in observed:
            missing.append(key)
            continue
        actual = observed[key]
        if isinstance(expected, bool):
            if bool(actual) != expected:
                missing.append(key)
        elif isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            # A numeric postcondition is a floor: "minimum_sources: 5" is met by 7.
            if actual < expected:
                missing.append(key)
        elif actual != expected:
            missing.append(key)
    return missing


class ObservationVerifier:
    """The general case: look at the target system and compare with the contract."""

    def __init__(
        self, observe: Observation, *, verifier_version: str, evidence_prefix: str
    ) -> None:
        self._observe = observe
        self.verifier_version = verifier_version
        self.evidence_prefix = evidence_prefix

    async def verify(
        self, contract: SuccessContract, context: dict[str, Any]
    ) -> VerificationRecord:
        if not contract.postconditions:
            # Nothing was claimed, so nothing can be confirmed. UNVERIFIABLE is
            # the honest answer; Mission Core refuses to call it success.
            return _record(
                status=VerificationStatus.UNVERIFIABLE, version=self.verifier_version,
                now_ms=context.get("now_ms"),
            )
        try:
            observed = await self._observe(context)
        except Exception as exc:  # noqa: BLE001 - an unreachable target is not a pass
            return _record(
                status=VerificationStatus.UNVERIFIABLE, version=self.verifier_version,
                observed={"error": type(exc).__name__},
                missing=list(contract.postconditions), now_ms=context.get("now_ms"),
            )

        missing = _compare(contract, observed)
        evidence = list(observed.get("evidence_refs", []))
        if not evidence and observed.get("evidence_ref"):
            evidence = [str(observed["evidence_ref"])]
        if missing or not evidence:
            # §55 — evidence is not optional for a success claim, so an
            # observation that satisfied everything but produced no citable
            # reference still cannot confirm.
            return _record(
                status=VerificationStatus.FAILED if missing else VerificationStatus.UNVERIFIABLE,
                version=self.verifier_version, observed=observed, missing=missing,
                evidence=evidence, now_ms=context.get("now_ms"),
            )
        return _record(
            status=VerificationStatus.VERIFIED, version=self.verifier_version,
            observed=observed, evidence=evidence, now_ms=context.get("now_ms"),
        )


class ApiReadbackVerifier(ObservationVerifier):
    """§34 — read the resource back from the provider that was asked to create it."""

    def __init__(self, observe: Observation) -> None:
        super().__init__(observe, verifier_version="api-readback/1",
                         evidence_prefix="provider-readback://")


class RepositoryShaVerifier(ObservationVerifier):
    """§39 — a commit either exists on the branch or it does not."""

    def __init__(self, observe: Observation) -> None:
        super().__init__(observe, verifier_version="repository-sha/1",
                         evidence_prefix="git://")


class CiRunVerifier(ObservationVerifier):
    """§39 — CI green on the exact head, which is a different claim from "I pushed"."""

    def __init__(self, observe: Observation) -> None:
        super().__init__(observe, verifier_version="ci-run/1", evidence_prefix="ci://")


class LedgerEventVerifier(ObservationVerifier):
    """§22 — VATI's ledger is the authority on whether a trade happened."""

    def __init__(self, observe: Observation) -> None:
        super().__init__(observe, verifier_version="ledger-event/1",
                         evidence_prefix="ledger://")


class ScreenshotVerifier(ObservationVerifier):
    """§34 — the weakest admissible evidence, and typed as such.

    A screenshot proves a page rendered something, not that a system changed
    state. Admissible where nothing better exists; never preferred by the router,
    which scores it well below a readback.
    """

    def __init__(self, observe: Observation) -> None:
        super().__init__(observe, verifier_version="screenshot/1",
                         evidence_prefix="browser-evidence://")


class EngineReportVerifier:
    """The forbidden case, made explicit so it cannot be used by accident.

    §6: "Submitted", "clicked", "worker returned OK", HTTP 2xx, or model
    assertion MUST NOT be sufficient. This adapter exists so that a capability
    with no real verifier has something honest to return — always UNVERIFIABLE,
    whatever the engine said.
    """

    verifier_version = "engine-report/1"

    async def verify(
        self, contract: SuccessContract, context: dict[str, Any]
    ) -> VerificationRecord:
        return _record(
            status=VerificationStatus.UNVERIFIABLE, version=self.verifier_version,
            observed={"engine_reported": context.get("engine_reported_success")},
            missing=list(contract.postconditions), now_ms=context.get("now_ms"),
        )


class VerifierRegistry:
    """Maps a capability's declared verification strategy to an adapter."""

    def __init__(self) -> None:
        self._adapters: dict[str, Verifier] = {"NONE": EngineReportVerifier()}

    def register(self, strategy: str, verifier: Verifier) -> None:
        self._adapters[strategy] = verifier

    def get(self, strategy: str) -> Verifier:
        """An unknown strategy gets the honest fallback, never an optimistic one."""
        return self._adapters.get(strategy, self._adapters["NONE"])

    async def verify(
        self, *, strategy: str, contract: SuccessContract, context: dict[str, Any]
    ) -> VerificationRecord:
        return await self.get(strategy).verify(contract, context)


__all__ = [
    "ApiReadbackVerifier",
    "CiRunVerifier",
    "EngineReportVerifier",
    "LedgerEventVerifier",
    "ObservationVerifier",
    "RepositoryShaVerifier",
    "ScreenshotVerifier",
    "Verifier",
    "VerifierRegistry",
]
