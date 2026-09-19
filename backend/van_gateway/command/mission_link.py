"""Turn an accepted owner command into one durable mission.

P0-EXEC-001, the audit's root cause RC1: POST /v1/commands authenticated, authorised,
audited and dispatched to Hermes, and then returned. No mission was created, no activity
recorded, no capability routed. The runtime probe drove ten canonical owner intents through
the gateway; all ten came back `accepted`, and `GET /v1/missions` returned `[]`. The
system's model of what the owner had asked for ended at dispatch, which is why nothing
downstream — completion, verification, the needs-you queue, the activity feed — had
anything to work from.

This module is the join. It is deliberately a separate translator rather than inline
orchestrator code, because it makes one claim per mission state and each claim has to be
defensible:

  CAPTURED    the signed command is genuine owner intent that passed the policy gates
  UNDERSTOOD  the typed resolver established what was asked and its effective action class
  PLANNED     what will happen is decided — the typed action for an exact resolution, or
              delegation to the agent runtime under the sealed envelope for free-form text
  AUTHORIZED  the command authority record was sealed
  RUNNING     Hermes accepted the run

A state is only advanced once the corresponding work has actually happened, so a mission
that stops at AUTHORIZED is telling the owner the truth: authorised, never started. That is
the whole point of having the ladder — the audit found the opposite failure, where a
mission could reach VERIFIED_SUCCESS on the strength of a worker asserting it.

Nothing here invents an Activity. `Activity` is defined as specialist work bound by
`executor_ref` — a browser task, an automation run, a Google action — and the gateway's own
dispatch to Hermes is not that. When Hermes goes on to create such work, MissionBinder
binds it. Recording a synthetic activity for the dispatch would mean inventing a capability
registry entry for "delegate to the agent runtime", and the honest authority class for that
is whatever the command's class is, which the registry cannot express.
"""

from __future__ import annotations

import time

from van_gateway.mission.models import (
    AuthorityEnvelope,
    Mission,
    MissionEventType,
    MissionOrigin,
    MissionState,
    Sensitivity,
    SuccessContract,
)
from van_gateway.mission.service import MissionError, MissionService
from van_gateway.models import ActionClass, CommandRequest, OriginChannel, PrincipalType

#: How a command's origin channel becomes a mission origin. VOICE, TEXT and UI are the
#: owner speaking; everything else reached the gateway through a machine, and the audit's
#: finding P0-SEC-002 is precisely about not confusing the two.
ORIGIN_FOR_CHANNEL: dict[OriginChannel, MissionOrigin] = {
    OriginChannel.VOICE: MissionOrigin.OWNER_VOICE,
    OriginChannel.TEXT: MissionOrigin.OWNER_TEXT,
    OriginChannel.UI: MissionOrigin.OWNER_UI,
    OriginChannel.NOTIFICATION_EVENT: MissionOrigin.AUTOMATION_EVENT,
    OriginChannel.SHARE_INTENT: MissionOrigin.AUTOMATION_EVENT,
    OriginChannel.AUTOMATION: MissionOrigin.AUTOMATION_EVENT,
    OriginChannel.HERMES_EVENT: MissionOrigin.AUTOMATION_EVENT,
    OriginChannel.SYSTEM_EVENT: MissionOrigin.SCHEDULED,
}

#: Sensitivity by the authority the command carries. A4 is the class that required a
#: biometric proof, so it is never routine.
SENSITIVITY_FOR_CLASS: dict[ActionClass, Sensitivity] = {
    ActionClass.A1: Sensitivity.ROUTINE,
    ActionClass.A2: Sensitivity.ROUTINE,
    ActionClass.A3: Sensitivity.PERSONAL,
    ActionClass.A4: Sensitivity.SECURITY,
}

TITLE_MAX = 80

#: P0-EXEC-002 — how long VAN waits for a dispatched command before saying it never heard
#: back. Fifteen minutes: long enough that a genuine agent run doing real work is not cut
#: off, short enough that an owner who asked for something at nine is not still being told
#: "working on it" at lunchtime. It is a *reporting* deadline, not a cancellation: VAN has
#: no way to stop an external runtime, and pretending otherwise would be the same class of
#: lie as reporting the command as accepted forever.
EXECUTION_DEADLINE_SECONDS = 15 * 60


def title_for(text: str) -> str:
    """A one-line title the owner will recognise as their own words."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= TITLE_MAX:
        return collapsed
    return collapsed[: TITLE_MAX - 1].rstrip() + "…"


class CommandMissionLink:
    """Opens and advances the one mission that belongs to a command."""

    def __init__(
        self,
        missions: MissionService,
        *,
        execution_deadline_seconds: int = EXECUTION_DEADLINE_SECONDS,
    ) -> None:
        self.missions = missions
        self.execution_deadline_seconds = max(int(execution_deadline_seconds), 0)

    async def existing_for_command(self, command_id: str) -> Mission | None:
        """The mission already opened for this command, if there is one.

        A command can reach the orchestrator twice — a failed idempotency claim is
        retryable by design — and the owner asked for one thing once.
        """
        rows = await self.missions.store.fetchall(
            "SELECT mission_id FROM missions "
            "WHERE json_extract(authority_envelope_json, '$.source_command_id') = ?",
            (command_id,),
        )
        if not rows:
            return None
        return await self.missions.get(str(rows[0]["mission_id"]))

    async def open(
        self,
        req: CommandRequest,
        *,
        effective_action_class: ActionClass,
        owner_approved: bool,
        constraints: list[str] | None = None,
    ) -> Mission:
        """Open the mission for this command, or return the one already open."""
        existing = await self.existing_for_command(req.command_id)
        if existing is not None:
            return existing

        envelope = AuthorityEnvelope(
            max_action_class=effective_action_class,
            requires_owner_presence=owner_approved,
            source_command_id=req.command_id,
        )
        return await self.missions.create(
            owner_principal_id=f"device:{req.device_id}",
            origin=ORIGIN_FOR_CHANNEL.get(req.origin_channel, MissionOrigin.OWNER_UI),
            origin_channel=req.origin_channel,
            title=title_for(req.text),
            goal=req.text,
            project_id=req.project_id,
            # §6 — an empty contract is legal and can never yield VERIFIED_SUCCESS. The
            # gateway does not know how to check an arbitrary instruction, and inventing a
            # postcondition it cannot observe is how a mission ends up "verified" on
            # nothing. Whoever knows the contract sets it.
            success_contract=SuccessContract(),
            constraints=list(constraints or []),
            authority_envelope=envelope,
            sensitivity=SENSITIVITY_FOR_CLASS.get(effective_action_class, Sensitivity.ROUTINE),
        )

    async def understood(self, mission: Mission, *, summary: str) -> Mission:
        return await self._advance(mission, MissionState.UNDERSTOOD, summary=summary)

    async def planned(self, mission: Mission, *, summary: str) -> Mission:
        return await self._advance(mission, MissionState.PLANNED, summary=summary)

    async def authorized(self, mission: Mission, *, summary: str) -> Mission:
        return await self._advance(mission, MissionState.AUTHORIZED, summary=summary)

    async def running(self, mission: Mission, *, hermes_run_id: str | None) -> Mission:
        """One event, carrying the run it can be traced to, and a deadline.

        The arrival at RUNNING already announces itself as `mission.started`; recording a
        second event for the same fact would make the owner's timeline say a thing twice.
        The run id rides on that event as its evidence reference instead.

        P0-EXEC-002 — the deadline is set *here*, at the moment VAN hands the work to
        something outside itself, because that is the moment it stops being able to observe
        progress. `create_run` returned a run id that nothing polled, no callback was keyed
        to it, and no deadline existed, so a Hermes that never called back left the mission
        at RUNNING forever while the owner was told "working on it". The deadline is what
        makes that condition detectable; `MissionDeadlineSweeper` is what acts on it.
        """
        deadline_ms = None
        if self.execution_deadline_seconds:
            deadline_ms = int(time.time() * 1000) + self.execution_deadline_seconds * 1000
        advanced = await self._advance(
            mission,
            MissionState.RUNNING,
            summary="delegated to the Hermes agent runtime",
            evidence_ref=f"hermes-run:{hermes_run_id}" if hermes_run_id else None,
        )
        if deadline_ms is not None:
            await self.missions.set_deadline(advanced.mission_id, deadline_ms)
            advanced = advanced.model_copy(update={"deadline_ms": deadline_ms})
        return advanced

    async def blocked_by_policy(self, mission: Mission, *, reason: str) -> Mission:
        """A refusal the owner must see. BLOCKED_POLICY is terminal, which is correct:
        the command was refused, and a new owner decision produces a new mission."""
        return await self._advance(
            mission, MissionState.BLOCKED_POLICY, summary=reason, final_outcome=reason
        )

    async def note_stall(self, mission: Mission, *, reason: str) -> None:
        """A degradation that is not a refusal: the mission stays where it is.

        Hermes being offline or the context snapshot failing does not mean the command was
        denied, so moving the mission to a terminal state would be a lie. It stops where it
        honestly got to, carrying an event that says why.
        """
        await self.missions.record_event(
            mission_id=mission.mission_id,
            event_type=MissionEventType.MISSION_FAILED,
            actor=PrincipalType.SYSTEM,
            summary=reason,
            severity="WARN",
            owner_visibility=True,
        )

    async def _advance(
        self,
        mission: Mission,
        target: MissionState,
        *,
        summary: str,
        final_outcome: str | None = None,
        evidence_ref: str | None = None,
    ) -> Mission:
        """Advance one rung, tolerating a mission that is already there.

        A retried command must not fail because its mission has already been walked up the
        ladder; it must land on the same mission in the same state.
        """
        if mission.state is target:
            return mission
        try:
            return await self.missions.transition(
                mission.mission_id,
                target=target,
                expected=mission.state,
                actor=PrincipalType.OWNER_DEVICE,
                summary=summary,
                final_outcome=final_outcome,
                evidence_ref=evidence_ref,
            )
        except MissionError as exc:
            if exc.code in {"MISSION_ILLEGAL_TRANSITION", "MISSION_STATE_PRECONDITION_FAILED"}:
                refreshed = await self.missions.get(mission.mission_id)
                if refreshed is not None:
                    return refreshed
            raise
