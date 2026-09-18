"""Rev 1 §§3-6 — MissionService, the owner-visible state authority.

§37 of the prompt puts it plainly: Temporal may own durable waits and n8n may own
deterministic integrations, but *MissionService remains owner-visible state
authority*. So this module owns exactly two things and delegates everything else:
the legal shape of a mission's life, and the rule that success must be earned.

The rule that matters most is in `transition()`. §55 forbids claiming success
without a postcondition, and the way to make that stick is not a convention but
an unreachable edge: VERIFIED_SUCCESS is refused unless a `VerificationRecord`
is supplied *and* that record carries evidence and no missing postconditions. A
mission whose contract has nothing to check cannot reach it at all — it lands in
UNVERIFIABLE, because a mission with nothing to verify has finished, not
succeeded. There is no argument a caller can make to get past that.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from van_gateway.mission.models import (
    EVENT_FOR_STATE,
    LEGAL_TRANSITIONS,
    TERMINAL_STATES,
    VERIFICATION_OUTCOMES,
    Activity,
    ActivityState,
    AuthorityEnvelope,
    Mission,
    MissionEvent,
    MissionEventType,
    MissionOrigin,
    MissionState,
    Sensitivity,
    SuccessContract,
    VerificationRecord,
    VerificationStatus,
)
from van_gateway.models import ActionClass, OriginChannel, PrincipalType
from van_gateway.storage.db import Store


class MissionError(ValueError):
    """A refusal that names itself, so the caller learns which gate it hit."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


class MissionService:
    def __init__(self, store: Store, *, capabilities: Any | None = None) -> None:
        self.store = store
        # §7 — when a registry is wired, a capability it does not declare cannot
        # become mission work. Optional so Mission Core stays testable on its
        # own, but `create_app` always supplies one.
        self.capabilities = capabilities

    # ------------------------------------------------------------- creation

    async def create(
        self,
        *,
        owner_principal_id: str,
        origin: MissionOrigin,
        origin_channel: OriginChannel,
        title: str,
        goal: str,
        project_id: str | None = None,
        success_contract: SuccessContract | None = None,
        constraints: list[str] | None = None,
        authority_envelope: AuthorityEnvelope | None = None,
        sensitivity: Sensitivity = Sensitivity.ROUTINE,
        context_snapshot_id: str | None = None,
        priority: int = 50,
        deadline_ms: int | None = None,
        parent_mission_id: str | None = None,
        now_ms: int | None = None,
    ) -> Mission:
        """A mission always starts CAPTURED, never further along.

        §3.2's ladder exists so that understanding, planning and authorization
        are separately observable. Letting a caller create a mission already
        AUTHORIZED would let it skip all three.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        if not goal.strip():
            raise MissionError("MISSION_GOAL_REQUIRED")
        mission = Mission(
            mission_id=f"msn_{uuid.uuid4().hex}",
            owner_principal_id=owner_principal_id,
            project_id=project_id,
            origin=origin,
            origin_channel=origin_channel,
            title=title.strip() or goal.strip()[:80],
            goal=goal.strip(),
            success_contract=success_contract or SuccessContract(),
            constraints=list(constraints or []),
            authority_envelope=authority_envelope or AuthorityEnvelope(),
            sensitivity=sensitivity,
            context_snapshot_id=context_snapshot_id,
            state=MissionState.CAPTURED,
            priority=priority,
            created_at_ms=now,
            updated_at_ms=now,
            deadline_ms=deadline_ms,
            parent_mission_id=parent_mission_id,
        )
        await self.store.execute(
            """
            INSERT INTO missions(
              mission_id, owner_principal_id, project_id, origin, origin_channel, title, goal,
              success_contract_json, constraints_json, authority_envelope_json, sensitivity,
              context_snapshot_id, state, priority, created_at_ms, updated_at_ms, deadline_ms,
              attention_policy, plan_revision, current_phase, parent_mission_id, final_outcome,
              verification_state, verification_record_json, learning_record_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL,
                      ?, NULL, NULL)
            """,
            (
                mission.mission_id, owner_principal_id, project_id, origin.value,
                origin_channel.value, mission.title, mission.goal,
                Store.dumps(mission.success_contract.model_dump(mode="json")),
                Store.dumps(mission.constraints),
                Store.dumps(mission.authority_envelope.model_dump(mode="json")),
                sensitivity.value, context_snapshot_id, mission.state.value, priority,
                now, now, deadline_ms, mission.attention_policy, 0, parent_mission_id,
                mission.verification_state.value,
            ),
        )
        await self.record_event(
            mission_id=mission.mission_id,
            event_type=MissionEventType.MISSION_CREATED,
            actor=PrincipalType.OWNER_DEVICE
            if origin in (MissionOrigin.OWNER_VOICE, MissionOrigin.OWNER_TEXT,
                          MissionOrigin.OWNER_UI)
            else PrincipalType.SYSTEM,
            summary=mission.title,
            now_ms=now,
        )
        return mission

    # ----------------------------------------------------------- transition

    async def transition(
        self,
        mission_id: str,
        *,
        target: MissionState,
        expected: MissionState | None = None,
        verification: VerificationRecord | None = None,
        final_outcome: str | None = None,
        actor: PrincipalType = PrincipalType.HERMES_AGENT,
        now_ms: int | None = None,
    ) -> Mission:
        """The one gate. Everything about a mission's life passes through here."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        mission = await self.get(mission_id)
        if mission is None:
            raise MissionError("MISSION_UNKNOWN", mission_id)

        current = mission.state
        if expected is not None and expected is not current:
            # §3.2 — a stale expectation is a conflict, not an overwrite. Two
            # writers racing a mission must not silently clobber each other.
            raise MissionError(
                "MISSION_STATE_PRECONDITION_FAILED", f"{expected.value}!={current.value}"
            )
        if current in TERMINAL_STATES:
            raise MissionError("MISSION_TERMINAL", current.value)
        if target not in LEGAL_TRANSITIONS[current]:
            raise MissionError("MISSION_ILLEGAL_TRANSITION", f"{current.value}->{target.value}")

        verification_state = mission.verification_state
        if target in VERIFICATION_OUTCOMES:
            verification = self._require_verification(mission, target, verification)
            verification_state = verification.status

        await self.store.execute(
            "UPDATE missions SET state = ?, verification_state = ?, "
            "verification_record_json = COALESCE(?, verification_record_json), "
            "final_outcome = COALESCE(?, final_outcome), updated_at_ms = ? "
            "WHERE mission_id = ? AND state = ?",
            (
                target.value, verification_state.value,
                Store.dumps(verification.model_dump(mode="json")) if verification else None,
                final_outcome, now, mission_id, current.value,
            ),
        )
        event_type = EVENT_FOR_STATE.get(target)
        if event_type is not None:
            await self.record_event(
                mission_id=mission_id, event_type=event_type, actor=actor,
                summary=final_outcome or target.value,
                severity="WARN" if target in (MissionState.FAILED, MissionState.BLOCKED_POLICY,
                                              MissionState.BLOCKED_UNSAFE) else "INFO",
                evidence_ref=(verification.evidence_refs[0]
                              if verification and verification.evidence_refs else None),
                now_ms=now,
            )
        refreshed = await self.get(mission_id)
        assert refreshed is not None
        return refreshed

    @staticmethod
    def _require_verification(
        mission: Mission, target: MissionState, verification: VerificationRecord | None
    ) -> VerificationRecord:
        """§§6, 55 — where "the worker said OK" stops being success.

        Three separate refusals, because there are three separate ways a caller
        could arrive at an unearned VERIFIED_SUCCESS: bringing no receipt,
        bringing a receipt with nothing behind it, or having written a contract
        that never asked anything checkable in the first place.
        """
        if verification is None:
            raise MissionError("MISSION_VERIFICATION_REQUIRED", target.value)
        if target is MissionState.VERIFIED_SUCCESS:
            if not mission.success_contract.is_checkable:
                # Nothing was ever claimed, so nothing was confirmed. Finishing
                # is not succeeding.
                raise MissionError(
                    "MISSION_SUCCESS_CONTRACT_NOT_CHECKABLE",
                    "a mission with no checkable postcondition cannot be VERIFIED_SUCCESS",
                )
            if not verification.supports_success:
                raise MissionError(
                    "MISSION_VERIFICATION_INSUFFICIENT",
                    f"status={verification.status.value} "
                    f"evidence={len(verification.evidence_refs)} "
                    f"missing={len(verification.missing_postconditions)}",
                )
        return verification

    # ------------------------------------------------------------ activities

    async def add_activity(
        self,
        *,
        mission_id: str,
        activity_type: str,
        capability_id: str,
        executor: str,
        executor_ref: str | None = None,
        input_contract: dict[str, Any] | None = None,
        authority_ref: str | None = None,
        dependency_activity_ids: list[str] | None = None,
        retry_policy: str = "NONE",
        verification_contract: dict[str, Any] | None = None,
        now_ms: int | None = None,
    ) -> Activity:
        """§5 — bind specialist work to a mission without absorbing it."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        mission = await self.get(mission_id)
        if mission is None:
            raise MissionError("MISSION_UNKNOWN", mission_id)
        if mission.is_terminal:
            raise MissionError("MISSION_TERMINAL", mission.state.value)
        await self._assert_capability_permitted(mission, capability_id)

        activity = Activity(
            activity_id=f"act_{uuid.uuid4().hex}",
            mission_id=mission_id, activity_type=activity_type, capability_id=capability_id,
            executor=executor, executor_ref=executor_ref,
            input_contract=dict(input_contract or {}), authority_ref=authority_ref,
            dependency_activity_ids=list(dependency_activity_ids or []),
            retry_policy=retry_policy,
            verification_contract=dict(verification_contract or {}),
            started_at_ms=now,
        )
        await self.store.execute(
            """
            INSERT INTO mission_activities(
              activity_id, mission_id, activity_type, capability_id, executor, executor_ref,
              input_contract_json, authority_ref, state, attempt, started_at_ms, ended_at_ms,
              dependency_activity_ids_json, checkpoint_ref, error_class, retry_policy,
              verification_contract_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, NULL, ?, NULL, NULL, ?, ?)
            """,
            (
                activity.activity_id, mission_id, activity_type, capability_id, executor,
                executor_ref, Store.dumps(activity.input_contract), authority_ref,
                activity.state.value, now, Store.dumps(activity.dependency_activity_ids),
                retry_policy, Store.dumps(activity.verification_contract),
            ),
        )
        return activity

    async def set_activity_state(
        self,
        activity_id: str,
        *,
        state: ActivityState,
        error_class: str | None = None,
        checkpoint_ref: str | None = None,
        evidence_ref: str | None = None,
        now_ms: int | None = None,
    ) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        row = await self.store.fetchone(
            "SELECT mission_id FROM mission_activities WHERE activity_id = ?", (activity_id,)
        )
        if row is None:
            raise MissionError("ACTIVITY_UNKNOWN", activity_id)
        ended = state in (ActivityState.COMPLETED, ActivityState.FAILED, ActivityState.SKIPPED)
        await self.store.execute(
            "UPDATE mission_activities SET state = ?, error_class = COALESCE(?, error_class), "
            "checkpoint_ref = COALESCE(?, checkpoint_ref), ended_at_ms = ? WHERE activity_id = ?",
            (state.value, error_class, checkpoint_ref, now if ended else None, activity_id),
        )
        event = {
            ActivityState.RUNNING: MissionEventType.ACTIVITY_STARTED,
            ActivityState.CHECKPOINTED: MissionEventType.ACTIVITY_CHECKPOINTED,
            ActivityState.COMPLETED: MissionEventType.ACTIVITY_COMPLETED,
            ActivityState.FAILED: MissionEventType.ACTIVITY_FAILED,
        }.get(state)
        if event is not None:
            await self.record_event(
                mission_id=str(row["mission_id"]), activity_id=activity_id, event_type=event,
                actor=PrincipalType.SYSTEM, summary=error_class or state.value,
                severity="WARN" if state is ActivityState.FAILED else "INFO",
                evidence_ref=evidence_ref, now_ms=now,
            )

    async def _assert_capability_permitted(self, mission: Mission, capability_id: str) -> None:
        """§7 — "a capability not in the registry must not be routable".

        Enforced here because this is where abstract work becomes real work: an
        Activity is the record that VAN intends to *do* something. Checking at
        the router only would leave a hole for anything that creates an Activity
        directly.

        The mission's own authority envelope is the constraint, so a mission
        authorized for A2 cannot acquire an A3 capability by asking for it as an
        activity.
        """
        if self.capabilities is None:
            return
        from van_gateway.capability.models import RoutingConstraints

        constraints = RoutingConstraints.from_envelope(
            mission.authority_envelope,
            owner_present=mission.authority_envelope.requires_owner_presence,
        )
        verdict = await self.capabilities.routability(capability_id, constraints=constraints)
        if not verdict.routable:
            raise MissionError(
                f"MISSION_CAPABILITY_NOT_PERMITTED:{verdict.reason.value}",
                verdict.detail or capability_id,
            )

    # ---------------------------------------------------------------- events

    async def record_event(
        self,
        *,
        mission_id: str,
        event_type: MissionEventType,
        actor: PrincipalType,
        activity_id: str | None = None,
        summary: str = "",
        severity: str = "INFO",
        owner_visibility: bool = True,
        evidence_ref: str | None = None,
        now_ms: int | None = None,
    ) -> MissionEvent:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        event = MissionEvent(
            event_id=f"mev_{uuid.uuid4().hex}", mission_id=mission_id, activity_id=activity_id,
            event_type=event_type, actor=actor, occurred_at_ms=now, severity=severity,
            owner_visibility=owner_visibility, summary=summary, evidence_ref=evidence_ref,
        )
        await self.store.execute(
            """
            INSERT INTO mission_events(
              event_id, mission_id, activity_id, event_type, actor, occurred_at_ms,
              severity, owner_visibility, summary, evidence_ref
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id, mission_id, activity_id, event_type.value, actor.value, now,
                severity, 1 if owner_visibility else 0, summary, evidence_ref,
            ),
        )
        return event

    # --------------------------------------------------------------- reading

    async def get(self, mission_id: str) -> Mission | None:
        row = await self.store.fetchone(
            "SELECT * FROM missions WHERE mission_id = ?", (mission_id,)
        )
        return None if row is None else self._row_to_mission(row)

    async def verification_record(self, mission_id: str) -> VerificationRecord | None:
        row = await self.store.fetchone(
            "SELECT verification_record_json FROM missions WHERE mission_id = ?", (mission_id,)
        )
        if row is None or not row["verification_record_json"]:
            return None
        return VerificationRecord.model_validate(json.loads(str(row["verification_record_json"])))

    async def activities(self, mission_id: str) -> list[Activity]:
        rows = await self.store.fetchall(
            "SELECT * FROM mission_activities WHERE mission_id = ? ORDER BY started_at_ms",
            (mission_id,),
        )
        return [self._row_to_activity(row) for row in rows]

    async def events(self, mission_id: str, *, owner_visible_only: bool = False) -> list[MissionEvent]:
        sql = "SELECT * FROM mission_events WHERE mission_id = ?"
        if owner_visible_only:
            sql += " AND owner_visibility = 1"
        rows = await self.store.fetchall(sql + " ORDER BY occurred_at_ms", (mission_id,))
        return [
            MissionEvent(
                event_id=str(r["event_id"]), mission_id=str(r["mission_id"]),
                activity_id=r["activity_id"],
                event_type=MissionEventType(str(r["event_type"])),
                actor=PrincipalType(str(r["actor"])), occurred_at_ms=int(r["occurred_at_ms"]),
                severity=str(r["severity"]), owner_visibility=bool(r["owner_visibility"]),
                summary=str(r["summary"]), evidence_ref=r["evidence_ref"],
            )
            for r in rows
        ]

    async def list_missions(
        self,
        *,
        owner_principal_id: str | None = None,
        states: list[MissionState] | None = None,
        limit: int = 50,
    ) -> list[Mission]:
        sql = "SELECT * FROM missions"
        params: list[Any] = []
        clauses = []
        if owner_principal_id is not None:
            clauses.append("owner_principal_id = ?")
            params.append(owner_principal_id)
        if states:
            clauses.append(f"state IN ({','.join('?' * len(states))})")
            params.extend(s.value for s in states)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at_ms DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        return [self._row_to_mission(r) for r in await self.store.fetchall(sql, tuple(params))]

    async def needs_owner(self) -> list[Mission]:
        """§33 — what feeds Needs You."""
        return await self.list_missions(states=[MissionState.WAITING_FOR_OWNER], limit=200)

    # --------------------------------------------------------------- mapping

    @staticmethod
    def _row_to_mission(row: Any) -> Mission:
        return Mission(
            mission_id=str(row["mission_id"]),
            owner_principal_id=str(row["owner_principal_id"]),
            project_id=row["project_id"],
            origin=MissionOrigin(str(row["origin"])),
            origin_channel=OriginChannel(str(row["origin_channel"])),
            title=str(row["title"]),
            goal=str(row["goal"]),
            success_contract=SuccessContract.model_validate(
                json.loads(str(row["success_contract_json"]))
            ),
            constraints=json.loads(str(row["constraints_json"])),
            authority_envelope=AuthorityEnvelope.model_validate(
                json.loads(str(row["authority_envelope_json"]))
            ),
            sensitivity=Sensitivity(str(row["sensitivity"])),
            context_snapshot_id=row["context_snapshot_id"],
            state=MissionState(str(row["state"])),
            priority=int(row["priority"]),
            created_at_ms=int(row["created_at_ms"]),
            updated_at_ms=int(row["updated_at_ms"]),
            deadline_ms=row["deadline_ms"],
            attention_policy=str(row["attention_policy"]),
            plan_revision=int(row["plan_revision"]),
            current_phase=row["current_phase"],
            parent_mission_id=row["parent_mission_id"],
            final_outcome=row["final_outcome"],
            verification_state=VerificationStatus(str(row["verification_state"])),
            learning_record_id=row["learning_record_id"],
        )

    @staticmethod
    def _row_to_activity(row: Any) -> Activity:
        return Activity(
            activity_id=str(row["activity_id"]), mission_id=str(row["mission_id"]),
            activity_type=str(row["activity_type"]), capability_id=str(row["capability_id"]),
            executor=str(row["executor"]), executor_ref=row["executor_ref"],
            input_contract=json.loads(str(row["input_contract_json"])),
            authority_ref=row["authority_ref"], state=ActivityState(str(row["state"])),
            attempt=int(row["attempt"]), started_at_ms=int(row["started_at_ms"]),
            ended_at_ms=row["ended_at_ms"],
            dependency_activity_ids=json.loads(str(row["dependency_activity_ids_json"])),
            checkpoint_ref=row["checkpoint_ref"], error_class=row["error_class"],
            retry_policy=str(row["retry_policy"]),
            verification_contract=json.loads(str(row["verification_contract_json"])),
        )


__all__ = ["MissionError", "MissionService"]
