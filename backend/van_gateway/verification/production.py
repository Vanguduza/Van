"""What the gateway actually installs: one set of observations, two adapters.

P0-VERIFY-001 — `VerifierRegistry` was constructed only in tests, so mission core accepted
whatever receipt its caller supplied.
P1-AUTO-001 — `AutomationDispatcher` was constructed with an empty observer map, so every
production automation run returned UNVERIFIABLE and `owner_success` could never be true.
P2-COH-002 (verifier half) — the two systems each had their own idea of verification.

Both are built here from `observations.py`, so the question "what can VAN independently
observe?" has one answer and each subsystem wraps it in the record shape it persists.

What is deliberately *not* registered matters as much as what is. There is no adapter that
asks n8n whether its workflow succeeded, none that asks Hermes whether its run worked, and
none for `RECEIPT` or `DOMAIN_ATTESTATION`, because the gateway has no independent source
for either. Those resolve to the honest fallback and the owner is told VAN could not
confirm it worked. Filling them with something optimistic is the defect, not the fix.
"""

from __future__ import annotations

from typing import Any

from van_gateway.automation.verifier import DocumentUploadObserver, PostconditionSpec, WorkflowVerifier
from van_gateway.mission.verifiers import (
    ApiReadbackVerifier,
    LedgerEventVerifier,
    ScreenshotVerifier,
    VerifierRegistry,
    UnobservableStrategyVerifier,
)
from van_gateway.storage.db import Store
from van_gateway.verification import observations


# ------------------------------------------------------------------ mission core

def _ledger_observation(trading: Any):
    async def observe(context: dict[str, Any]) -> dict[str, Any]:
        postconditions = context.get("postconditions") or {}
        trade_intent_id = str(postconditions.get("trade_intent_id") or "").strip()
        if not trade_intent_id:
            # The contract did not say which trade to look for. Raising rather than
            # returning {} keeps "nothing to check" from reading as "checked and fine":
            # ObservationVerifier turns the exception into UNVERIFIABLE.
            raise ValueError("success contract names no trade_intent_id to read back")
        return await observations.trading_ledger_readback(trading, trade_intent_id)

    return observe


def _browser_observation(store: Store):
    async def observe(context: dict[str, Any]) -> dict[str, Any]:
        return await observations.browser_evidence_readback(
            store, str(context.get("mission_id") or "")
        )

    return observe


def _trading_halt_observation(trading: Any):
    async def observe(context: dict[str, Any]) -> dict[str, Any]:
        return await observations.trading_halt_readback(trading)

    return observe


def _notebook_readback_observation(knowledge: Any):
    async def observe(context: dict[str, Any]) -> dict[str, Any]:
        postconditions = context.get("postconditions") or {}
        notebook_id = str(postconditions.get("notebook_id") or "").strip()
        if not notebook_id:
            # The contract did not say which notebook to read. Raising rather than
            # returning {} keeps "nothing to check" from reading as "checked and fine".
            raise ValueError("success contract names no notebook_id to read back")
        observed = await observations.notebook_enterprise_readback(knowledge, notebook_id)
        # The id is the contract's own statement of *where to look*, not a claim about the
        # world, so echoing it lets `_compare` judge the claim that remains: whether the
        # notebook is there. Inventing anything else here would be the verifier answering
        # its own question.
        return {**observed, "notebook_id": notebook_id}

    return observe


#: P2-VERIFY-002 — strategies the codebase implements and this process cannot perform,
#: with the reason. Each is registered, so a contract naming one gets UNVERIFIABLE *and the
#: reason*, rather than the record a capability that promised nothing would get.
#:
#: These are not aspirational entries. `RepositoryShaVerifier` and `CiRunVerifier` are
#: complete; what is missing is an independent source — a git remote the gateway can read,
#: a CI API it can query — and inventing one is how a verifier starts certifying its own
#: subject. `api-readback` used to sit here for the same reason and no longer does: the
#: notebook provider is a source the gateway can ask, independent of whoever acted
#: (P1-VERIFY-003).
DECLARED_BUT_UNOBSERVABLE_STRATEGIES: dict[str, str] = {
    "repository-sha": "no git remote is configured for the gateway to read",
    "ci-run": "no CI API is configured for the gateway to query",
}


def build_mission_registry(
    *, store: Store, trading: Any, knowledge: Any
) -> VerifierRegistry:
    """The registry MissionService runs when a mission asks for a verification outcome."""
    registry = VerifierRegistry()
    registry.register("ledger-event", LedgerEventVerifier(_ledger_observation(trading)))
    # §§22, 421 — a halt is a ledger fact like a fill is, written by the trading process
    # and hash-chained there, so the same adapter reads it. P1-VERIFY-003: `trading.halt`
    # is the one A4 command an owner issues under time pressure, and until this was
    # registered the mission for it could only ever end COMPLETED_UNVERIFIED.
    registry.register("trading-halt", LedgerEventVerifier(_trading_halt_observation(trading)))
    # §34 names stored browser artefacts the weakest admissible evidence and this adapter
    # is typed as such. It is registered because the artefacts are real, not because they
    # are strong.
    registry.register("browser-evidence", ScreenshotVerifier(_browser_observation(store)))
    # §166 — ask the notebook provider what exists. Independent of the executor: the
    # knowledge runtime performed the action, and this asks Google what is there now.
    registry.register("api-readback", ApiReadbackVerifier(_notebook_readback_observation(knowledge)))
    # P2-VERIFY-002 — named, so "I could not check" is distinguishable from "nothing was
    # promised". The adapter classes stay in the tree because the day a remote or a CI API
    # is configured, registering them is a one-line change rather than a rewrite.
    for strategy, reason in DECLARED_BUT_UNOBSERVABLE_STRATEGIES.items():
        registry.register(strategy, UnobservableStrategyVerifier(strategy, reason))
    return registry


#: Mission verification strategies a success contract may name today.
WIRED_MISSION_STRATEGIES = ("ledger-event", "trading-halt", "browser-evidence", "api-readback")



# -------------------------------------------------------------------- automation

class _GoogleReadBackObserver:
    """READ_BACK — ask the provider what is there now, not n8n what it did."""

    def __init__(self, google: Any) -> None:
        self._google = google

    async def observe(self, spec: PostconditionSpec, context: dict[str, Any]) -> dict[str, Any]:
        readback = context.get("readback")
        if not isinstance(readback, dict):
            raise ValueError("no readback descriptor on the run context")
        return await observations.google_resource_readback(self._google, readback)


class _RunStatePredicateObserver:
    """STATE_PREDICATE — the gateway's own row for the run, written by its dispatch path."""

    def __init__(self, store: Store) -> None:
        self._store = store

    async def observe(self, spec: PostconditionSpec, context: dict[str, Any]) -> dict[str, Any]:
        run_id = str(context.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("state predicate needs a run_id")
        return await observations.automation_run_state_predicate(self._store, run_id)


def build_automation_verifier(*, store: Store, google: Any) -> WorkflowVerifier:
    """The verifier AutomationDispatcher runs, with a map that is not empty."""
    return WorkflowVerifier(
        observers={
            "READ_BACK": _GoogleReadBackObserver(google),
            "STATE_PREDICATE": _RunStatePredicateObserver(store),
            # §166 — a document is verified by existing with the expected digest, which is
            # the provider readback asked a narrower question. P2-VERIFY-002: the observer
            # was written and registered nowhere, so a capability declaring DOCUMENT_UPLOAD
            # fell through to UNVERIFIABLE while the means to observe it sat in the tree.
            "DOCUMENT_UPLOAD": DocumentUploadObserver(_GoogleReadBackObserver(google).observe),
        }
    )


#: Postcondition kinds an automation capability may declare and have observed today.
WIRED_POSTCONDITION_KINDS = ("READ_BACK", "STATE_PREDICATE", "DOCUMENT_UPLOAD")

#: Declared on purpose: kinds with no independent source in this process. A capability
#: naming one of these is UNVERIFIABLE, which is reported to the owner rather than hidden.
UNOBSERVABLE_POSTCONDITION_KINDS = {
    "RECEIPT": "no provider receipt store the gateway can read independently of the engine",
    "DOMAIN_ATTESTATION": "no attestation authority is wired",
}

__all__ = [
    "DECLARED_BUT_UNOBSERVABLE_STRATEGIES",
    "UNOBSERVABLE_POSTCONDITION_KINDS",
    "WIRED_MISSION_STRATEGIES",
    "WIRED_POSTCONDITION_KINDS",
    "build_automation_verifier",
    "build_mission_registry",
]
