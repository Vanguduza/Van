"""Rev 1 §43 — the owner-safe mission surface.

§33 gives the owner six surfaces and the rule that Home answers "is Van okay,
what is it working on, does it need me" in under five seconds. That is a read
model problem: these endpoints exist so Android asks one question and gets one
answer, instead of assembling a picture from five subsystem tables.

Two boundaries hold here:

**Owner reads, Hermes writes.** §2.3 says Android is not a second planner, so
the GETs are owner-authenticated and every mutation that changes what VAN will
*do* stays internal-control. The exceptions are the two things that are the
owner's to say — cancelling their own mission, and sending it a message — which
are owner-authenticated by design.

**Nothing here re-decides policy.** The routes resolve, delegate and translate
refusals into HTTP. `MissionService` owns the state machine and
`CapabilityRegistry` owns routability; a second opinion in the API layer would be
a second place for those rules to drift.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from van_gateway.capability.models import CapabilityClass, RoutingConstraints
from van_gateway.capability.registry import CapabilityRegistry, CapabilityRegistryError
from van_gateway.capability.router import CapabilityRouter
from van_gateway.config import Settings
from van_gateway.google.control import GoogleControlAuthError, verify_internal_control
from van_gateway.mission.binding import MissionBinder
from van_gateway.mission.models import (
    MissionOrigin,
    MissionState,
    Sensitivity,
    SuccessContract,
    VerificationRecord,
)
from van_gateway.mission.service import MissionError, MissionService
from van_gateway.models import OriginChannel, PrincipalType
from van_gateway.storage.db import Store

#: States the owner thinks of as "Van is working on this".
ACTIVE_STATES = [
    MissionState.CAPTURED, MissionState.UNDERSTOOD, MissionState.PLANNED,
    MissionState.AUTHORIZED, MissionState.RUNNING, MissionState.WAITING_EXTERNAL,
    MissionState.RESUME_AUTHORIZED, MissionState.VERIFYING,
]


class CreateMissionBody(BaseModel):
    owner_principal_id: str
    origin: MissionOrigin
    origin_channel: OriginChannel
    title: str
    goal: str
    project_id: str | None = None
    success_contract: SuccessContract | None = None
    constraints: list[str] = Field(default_factory=list)
    sensitivity: Sensitivity = Sensitivity.ROUTINE
    context_snapshot_id: str | None = None
    priority: int = 50
    deadline_ms: int | None = None
    parent_mission_id: str | None = None


class TransitionBody(BaseModel):
    target: MissionState
    expected: MissionState | None = None
    verification: VerificationRecord | None = None
    final_outcome: str | None = None


class AddActivityBody(BaseModel):
    activity_type: str
    capability_id: str
    executor: str
    executor_ref: str | None = None
    input_contract: dict[str, Any] = Field(default_factory=dict)
    authority_ref: str | None = None


class RouteBody(BaseModel):
    goal_class: str
    #: Required for the same reason the router requires it: deciding which
    #: classes serve a goal is goal interpretation, and that is Hermes's (§2.1).
    candidate_classes: list[CapabilityClass] = Field(min_length=1)
    mission_id: str | None = None


class MessageBody(BaseModel):
    message: str = Field(min_length=1)


class MissionApi:
    """`/v1/missions/*`, `/v1/needs-you`, `/v1/activity`, `/v1/capabilities/status`."""

    def __init__(
        self,
        store: Store,
        settings: Settings,
        *,
        missions: MissionService,
        registry: CapabilityRegistry,
        router: CapabilityRouter,
    ) -> None:
        self.store = store
        self.settings = settings
        self.missions = missions
        self.registry = registry
        self.capability_router = router
        self.binder = MissionBinder(store, missions)
        self.router = APIRouter(prefix="/v1", tags=["missions"])
        self._install_routes()

    def _require_internal(self, token: str | None) -> None:
        try:
            verify_internal_control(self.settings.internal_control_token, token)
        except GoogleControlAuthError as exc:
            code = 503 if exc.code == "internal_control_token_unconfigured" else 403
            raise HTTPException(status_code=code, detail=exc.code) from exc

    @staticmethod
    def _translate(exc: MissionError) -> HTTPException:
        """A refusal's shape should say what kind of problem it is."""
        status = 409
        if exc.code.startswith("MISSION_UNKNOWN") or exc.code.startswith("ACTIVITY_UNKNOWN"):
            status = 404
        elif exc.code.startswith("MISSION_CAPABILITY_NOT_PERMITTED"):
            status = 403
        elif exc.code in ("MISSION_GOAL_REQUIRED",):
            status = 422
        return HTTPException(status_code=status, detail={"error": exc.code, "detail": exc.detail})

    async def _mission_summary(self, mission) -> dict[str, Any]:
        """What Home and Missions need, without the owner opening a log."""
        return {
            "mission_id": mission.mission_id,
            "title": mission.title,
            "goal": mission.goal,
            "project_id": mission.project_id,
            "state": mission.state.value,
            "current_phase": mission.current_phase,
            "verification_state": mission.verification_state.value,
            "needs_owner": mission.needs_owner,
            "is_terminal": mission.is_terminal,
            "priority": mission.priority,
            "sensitivity": mission.sensitivity.value,
            "final_outcome": mission.final_outcome,
            "created_at_ms": mission.created_at_ms,
            "updated_at_ms": mission.updated_at_ms,
            "deadline_ms": mission.deadline_ms,
        }

    # -------------------------------------------------------------- routes

    def _install_routes(self) -> None:
        router = self.router

        @router.get("/missions")
        async def list_missions(owner_principal_id: str | None = None, active: bool = False):
            missions = await self.missions.list_missions(
                owner_principal_id=owner_principal_id,
                states=ACTIVE_STATES if active else None,
            )
            return [await self._mission_summary(m) for m in missions]

        @router.get("/missions/{mission_id}")
        async def get_mission(mission_id: str):
            mission = await self.missions.get(mission_id)
            if mission is None:
                raise HTTPException(status_code=404, detail="MISSION_UNKNOWN")
            verification = await self.missions.verification_record(mission_id)
            return {
                **await self._mission_summary(mission),
                "success_contract": mission.success_contract.model_dump(mode="json"),
                "constraints": mission.constraints,
                "authority_envelope": mission.authority_envelope.model_dump(mode="json"),
                # §6 — the receipt travels with the claim, so "verified" is
                # inspectable rather than a word in a status field.
                "verification": verification.model_dump(mode="json") if verification else None,
            }

        @router.get("/missions/{mission_id}/activity")
        async def mission_activity(mission_id: str):
            if await self.missions.get(mission_id) is None:
                raise HTTPException(status_code=404, detail="MISSION_UNKNOWN")
            # Pull subsystem truth before answering: an Activity that disagrees
            # with browser_tasks is the Activity that is wrong.
            await self.binder.sync_from_subsystems(mission_id)
            activities = await self.missions.activities(mission_id)
            events = await self.missions.events(mission_id, owner_visible_only=True)
            return {
                "mission_id": mission_id,
                "activities": [a.model_dump(mode="json") for a in activities],
                "events": [e.model_dump(mode="json") for e in events],
            }

        @router.get("/missions/{mission_id}/evidence")
        async def mission_evidence(mission_id: str):
            """§34 — every side effect's proof, gathered in one place."""
            mission = await self.missions.get(mission_id)
            if mission is None:
                raise HTTPException(status_code=404, detail="MISSION_UNKNOWN")
            events = await self.missions.events(mission_id)
            verification = await self.missions.verification_record(mission_id)
            refs = [e.evidence_ref for e in events if e.evidence_ref]
            if verification:
                refs.extend(verification.evidence_refs)
            return {
                "mission_id": mission_id,
                "verification": verification.model_dump(mode="json") if verification else None,
                "evidence_refs": sorted(set(refs)),
                "route_decisions": await self.capability_router.decisions_for(mission_id),
            }

        @router.get("/needs-you")
        async def needs_you():
            """§33 — one surface for everything waiting on the owner."""
            missions = await self.missions.needs_owner()
            decisions = await self.store.fetchall(
                "SELECT id, title, body, source, created_at_unix FROM decisions "
                "WHERE status = 'OPEN' ORDER BY created_at_unix DESC LIMIT 100"
            )
            return {
                "count": len(missions) + len(decisions),
                "missions": [await self._mission_summary(m) for m in missions],
                "decisions": [dict(d) for d in decisions],
            }

        @router.get("/activity")
        async def activity_feed(limit: int = 100):
            """§34 — grouped by mission; raw provider logs stay a drill-down."""
            rows = await self.store.fetchall(
                "SELECT e.*, m.title AS mission_title, m.state AS mission_state "
                "FROM mission_events e JOIN missions m ON m.mission_id = e.mission_id "
                "WHERE e.owner_visibility = 1 ORDER BY e.occurred_at_ms DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            )
            grouped: dict[str, dict[str, Any]] = {}
            for row in rows:
                mission_id = str(row["mission_id"])
                bucket = grouped.setdefault(
                    mission_id,
                    {
                        "mission_id": mission_id, "title": row["mission_title"],
                        "state": row["mission_state"], "events": [],
                    },
                )
                bucket["events"].append({
                    "event_id": row["event_id"], "event_type": row["event_type"],
                    "actor": row["actor"], "severity": row["severity"],
                    "summary": row["summary"], "evidence_ref": row["evidence_ref"],
                    "occurred_at_ms": row["occurred_at_ms"],
                })
            return {"missions": list(grouped.values())}

        @router.get("/capabilities/status")
        async def capability_status():
            """§43 — what VAN can currently do, and why not where it cannot."""
            out = []
            for capability_id in self.registry.capability_ids:
                declaration = self.registry.require(capability_id)
                verdict = await self.registry.routability(
                    capability_id,
                    constraints=RoutingConstraints(
                        max_action_class=declaration.authority_class, owner_present=True
                    ),
                )
                out.append({
                    "capability_id": capability_id,
                    "capability_class": declaration.capability_class.value,
                    "authority_class": declaration.authority_class.value,
                    "provider": declaration.provider,
                    "readiness_source": declaration.readiness_source.value,
                    "routable": verdict.routable,
                    "reason": verdict.reason.value,
                    "detail": verdict.detail,
                })
            return {"manifest_digest": self.registry.manifest_digest, "capabilities": out}

        # ------------------------------------------------ owner mutations

        @router.post("/missions/{mission_id}/cancel")
        async def cancel_mission(mission_id: str):
            """Owner-authenticated: stopping your own mission is yours to say."""
            try:
                mission = await self.missions.transition(
                    mission_id, target=MissionState.CANCELLED,
                    actor=PrincipalType.OWNER_DEVICE, final_outcome="cancelled by owner",
                )
            except MissionError as exc:
                raise self._translate(exc) from exc
            return await self._mission_summary(mission)

        @router.post("/missions/{mission_id}/message")
        async def message_mission(mission_id: str, body: MessageBody):
            """A note on the record. It does not move the mission by itself.

            §2.3 — Android is not a planner. The message becomes an event Hermes
            can read on its next turn; letting it drive a transition would make
            the UI a second decision-maker.
            """
            if await self.missions.get(mission_id) is None:
                raise HTTPException(status_code=404, detail="MISSION_UNKNOWN")
            from van_gateway.mission.models import MissionEventType

            event = await self.missions.record_event(
                mission_id=mission_id, event_type=MissionEventType.MISSION_CREATED,
                actor=PrincipalType.OWNER_DEVICE, summary=body.message[:500],
                severity="INFO",
            )
            return {"event_id": event.event_id, "recorded": True}

        # ---------------------------------------------- internal control

        @router.post("/missions")
        async def create_mission(
            body: CreateMissionBody, x_van_internal_token: str | None = Header(default=None)
        ):
            self._require_internal(x_van_internal_token)
            try:
                mission = await self.missions.create(
                    owner_principal_id=body.owner_principal_id, origin=body.origin,
                    origin_channel=body.origin_channel, title=body.title, goal=body.goal,
                    project_id=body.project_id, success_contract=body.success_contract,
                    constraints=body.constraints, sensitivity=body.sensitivity,
                    context_snapshot_id=body.context_snapshot_id, priority=body.priority,
                    deadline_ms=body.deadline_ms, parent_mission_id=body.parent_mission_id,
                )
            except MissionError as exc:
                raise self._translate(exc) from exc
            return await self._mission_summary(mission)

        @router.post("/missions/{mission_id}/transition")
        async def transition_mission(
            mission_id: str, body: TransitionBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            try:
                mission = await self.missions.transition(
                    mission_id, target=body.target, expected=body.expected,
                    verification=body.verification, final_outcome=body.final_outcome,
                )
            except MissionError as exc:
                raise self._translate(exc) from exc
            return await self._mission_summary(mission)

        @router.post("/missions/{mission_id}/activities")
        async def add_activity(
            mission_id: str, body: AddActivityBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            try:
                activity = await self.missions.add_activity(
                    mission_id=mission_id, activity_type=body.activity_type,
                    capability_id=body.capability_id, executor=body.executor,
                    executor_ref=body.executor_ref, input_contract=body.input_contract,
                    authority_ref=body.authority_ref,
                )
            except MissionError as exc:
                raise self._translate(exc) from exc
            return activity.model_dump(mode="json")

        @router.post("/missions/route")
        async def route_capability(
            body: RouteBody, x_van_internal_token: str | None = Header(default=None)
        ):
            self._require_internal(x_van_internal_token)
            constraints = RoutingConstraints()
            if body.mission_id:
                mission = await self.missions.get(body.mission_id)
                if mission is None:
                    raise HTTPException(status_code=404, detail="MISSION_UNKNOWN")
                constraints = RoutingConstraints.from_envelope(
                    mission.authority_envelope,
                    owner_present=mission.authority_envelope.requires_owner_presence,
                )
            try:
                decision = await self.capability_router.route(
                    goal_class=body.goal_class, candidate_classes=body.candidate_classes,
                    constraints=constraints, mission_id=body.mission_id,
                )
            except CapabilityRegistryError as exc:
                raise HTTPException(
                    status_code=422, detail={"error": exc.code, "detail": exc.detail}
                ) from exc
            return {
                "decision_id": decision.decision_id,
                "routed": decision.routed,
                "selected_capability_id": decision.selected_capability_id,
                "fallback_chain": list(decision.fallback_chain),
                "candidates": [c.as_evidence() for c in decision.candidates],
                "rejected": [
                    {"capability_id": r.capability_id, "reason": r.reason.value,
                     "detail": r.detail}
                    for r in decision.rejected
                ],
                "routing_policy_version": decision.routing_policy_version,
                "manifest_digest": decision.manifest_digest,
            }

        @router.post("/missions/{mission_id}/backfill")
        async def backfill(
            mission_id: str, x_van_internal_token: str | None = Header(default=None)
        ):
            """§42 — adopt pre-existing subsystem rows. Idempotent."""
            self._require_internal(x_van_internal_token)
            try:
                report = await self.binder.backfill(mission_id=mission_id)
            except MissionError as exc:
                raise self._translate(exc) from exc
            return {
                "mission_id": mission_id,
                "browser_tasks_bound": report.browser_tasks_bound,
                "automation_runs_bound": report.automation_runs_bound,
                "already_bound": report.already_bound,
                "unbindable": report.unbindable,
                "total_bound": report.total_bound,
            }


__all__ = ["ACTIVE_STATES", "MissionApi"]
