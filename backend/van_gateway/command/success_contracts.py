"""What the owner asked for, stated as something a verifier can check.

P1-VERIFY-003. The spine was complete and one joint was missing. `TypedCommandResolver`
resolves an exact owner phrase to a registered action and copies that action's declared
`verifier_type` onto the resolution; `MissionService._perform_verification` picks a
verifier from the mission's success contract and refuses VERIFIED_SUCCESS without evidence;
`VerifierRegistry` holds adapters that observe the target system independently. Between
them, `CommandMissionLink.open` created every mission with `SuccessContract()` — empty. So
`verifier_type` was written by the resolver and read by nothing, and *no owner command
could ever be verified*: every mission from a phone ended at COMPLETED_UNVERIFIED, however
exactly VAN had understood it and however readable the result was.

This module is that joint, and it is a separate translator for the same reason
`mission_link` is: each contract it emits is a claim VAN will be held to, and each one has
to be defensible on its own.

The rule for adding one is the rule `observations.py` states, not a wish list:

  A contract may only name a strategy whose observation reaches a system independent of
  whoever did the work.

So `trading.halt` gets a contract, because the VATI kill-switch ledger is written by the
trading process and hash-chained, and the notebook actions get one, because the provider
can be asked what exists. `research.web.search` does not, because its declared RECEIPT has
no independent source in this process — and the honest outcome for it is the empty contract
it already had, with `no_contract_reason` recording *why* rather than leaving the gap
looking like an oversight. An empty contract still cannot become VERIFIED_SUCCESS; that
refusal is Mission Core's and this module does not soften it.
"""

from __future__ import annotations

from van_gateway.command.resolver import CommandResolution, ResolutionMode
from van_gateway.mission.models import SuccessContract

#: Strategy names, matching the registrations in `verification.production`.
TRADING_HALT = "trading-halt"
NOTEBOOK_READBACK = "api-readback"
NOTEBOOK_SOURCE_READBACK = "notebook-source-readback"

#: Why an exactly-resolved action still gets no checkable contract. Recorded rather than
#: implied: "VAN cannot confirm this" is a supported outcome and the owner is entitled to
#: the reason, but it must never be reachable by accident.
NO_CONTRACT_REASONS: dict[str, str] = {
    "research.web.search": (
        "a web search leaves nothing the gateway can read back independently of the "
        "engine that performed it"
    ),
    "owner.context.read": (
        "a read changes nothing, so there is no post-state to observe; the answer itself "
        "is the result and it is returned to the owner, not verified against the world"
    ),
}

#: Notebook actions whose claim is about the notebook itself.
#:
#: Only two belong here. `create` says a notebook exists afterwards and `delete` says it
#: does not, and for both the notebook *is* the object the owner asked about.
_NOTEBOOK_ACTIONS: dict[str, bool] = {
    "google.notebook.enterprise.create": True,
    "google.notebook.enterprise.delete": False,
}

#: Notebook actions whose claim is about named sources, and whether each must be there.
#:
#: P1-VERIFY-004 — these were in `_NOTEBOOK_ACTIONS` with the postcondition
#: `notebook_exists: True`, which is the defect this whole finding family is about wearing
#: the right architecture. Deleting a source does not change whether the notebook exists,
#: so a delete that silently failed satisfied the contract and the mission could reach
#: VERIFIED_SUCCESS with the source still there. A related but weaker condition must never
#: certify the requested effect.
_NOTEBOOK_SOURCE_ACTIONS: dict[str, bool] = {
    "google.notebook.enterprise.sources.add": True,
    "google.notebook.enterprise.sources.delete": False,
}


def contract_for(resolution: CommandResolution) -> SuccessContract:
    """The success contract for an exactly-resolved command, or an empty one.

    Free-form text resolves to no action, and the gateway does not know how to check an
    arbitrary instruction — inventing a postcondition it cannot observe is how a mission
    ends up "verified" on nothing. That case, and every exact action with no independent
    observation, returns an empty contract.
    """
    if resolution.mode is not ResolutionMode.EXACT_ACTION or not resolution.action_id:
        return SuccessContract()

    action_id = resolution.action_id

    if action_id == "trading.halt":
        # Not "the ledger accepted an event" — that is what `halt()` returns and it is the
        # claim, not the check. What must be true afterwards is that the kill switch is
        # *active and owner-triggered*, which only the ledger can say.
        return SuccessContract(
            verifier_class=TRADING_HALT,
            postconditions={"kill_switch_active": True, "owner_halt_active": True},
            evidence_required=True,
        )

    if action_id in _NOTEBOOK_SOURCE_ACTIONS:
        notebook_id = str(resolution.parameters.get("notebook_id") or "").strip()
        names = sorted(
            {str(n).strip() for n in (resolution.parameters.get("source_names") or []) if str(n).strip()}
            | {str(n).strip() for n in (resolution.parameters.get("sources") or []) if str(n).strip()}
        )
        if not notebook_id or not names:
            return SuccessContract()
        must_be_present = _NOTEBOOK_SOURCE_ACTIONS[action_id]
        return SuccessContract(
            verifier_class=NOTEBOOK_SOURCE_READBACK,
            postconditions={
                "notebook_id": notebook_id,
                "source_names": names,
                # The claim is about these exact sources. An add says all of them are
                # there afterwards and a delete says none of them is, and each is stated
                # as the full expected list rather than a count: a count is satisfied by
                # the right number of the wrong sources.
                "sources_present": names if must_be_present else [],
                "sources_absent": [] if must_be_present else names,
            },
            evidence_required=True,
        )

    if action_id in _NOTEBOOK_ACTIONS:
        notebook_id = str(resolution.parameters.get("notebook_id") or "").strip()
        if not notebook_id:
            # `enterprise.create` names the notebook only after the provider assigns an id,
            # so there is nothing to look up at command time. Leaving the contract empty is
            # correct: the mission completes unverified rather than claiming a readback
            # that pointed at nothing.
            return SuccessContract()
        return SuccessContract(
            verifier_class=NOTEBOOK_READBACK,
            postconditions={
                "notebook_id": notebook_id,
                "notebook_exists": _NOTEBOOK_ACTIONS[action_id],
            },
            evidence_required=True,
        )

    return SuccessContract()


def no_contract_reason(resolution: CommandResolution) -> str | None:
    """Why this resolution produced no checkable contract, for the mission's own record."""
    if contract_for(resolution).is_checkable:
        return None
    if resolution.mode is not ResolutionMode.EXACT_ACTION or not resolution.action_id:
        return (
            "the command was not resolved to a known action, so there is no declared "
            "post-state for the gateway to observe"
        )
    if resolution.action_id in _NOTEBOOK_ACTIONS:
        return (
            "the notebook this action creates has no id until the provider assigns one, "
            "so there is nothing to read back at command time"
        )
    if resolution.action_id in _NOTEBOOK_SOURCE_ACTIONS:
        return (
            "the command named no notebook or no sources, so there is no specific object "
            "for the gateway to read back"
        )
    return NO_CONTRACT_REASONS.get(
        resolution.action_id,
        f"no independent observation is registered for {resolution.action_id}",
    )


__all__ = [
    "NOTEBOOK_READBACK",
    "NOTEBOOK_SOURCE_READBACK",
    "NO_CONTRACT_REASONS",
    "TRADING_HALT",
    "contract_for",
    "no_contract_reason",
]
