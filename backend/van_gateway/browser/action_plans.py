"""Immutable owner-reviewed browser effects, sealed by canonical A4 authority.

Drafts confer no authority. A broker transaction claims each effect before native
dispatch; an uncertain transport outcome can only be observed, never re-actuated.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from van_gateway.action.models import ActionDefinition, ExecutionStatus, VerifierType
from van_gateway.models import ActionClass, PrincipalType


class PlanError(ValueError):
    pass


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EffectPredicate(Strict):
    kind: Literal["url_equals", "element_text_equals", "element_attribute_equals", "input_value_equals"]
    selector: str | None = Field(default=None, min_length=1, max_length=1024)
    url: str | None = Field(default=None, min_length=1, max_length=8192)
    text: str | None = Field(default=None, max_length=4096)
    attribute: str | None = Field(default=None, pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
    value: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def shape(self):
        required = {"url_equals": {"url"}, "element_text_equals": {"selector", "text"},
                    "element_attribute_equals": {"selector", "attribute", "value"},
                    "input_value_equals": {"selector", "value"}}[self.kind]
        supplied = {key for key in ("selector", "url", "text", "attribute", "value") if getattr(self, key) is not None}
        if supplied != required:
            raise ValueError("browser_effect_predicate_shape_invalid")
        if self.url is not None and not self.url.startswith(("https://", "http://")):
            raise ValueError("browser_effect_predicate_scheme_refused")
        if self.attribute and self.attribute.lower() in {"value", "srcdoc", "nonce", "password", "token"}:
            raise ValueError("browser_effect_sensitive_attribute_refused")
        return self


class EffectStep(Strict):
    step_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    operation: Literal["click_element", "fill_element"]
    selector: str = Field(min_length=1, max_length=1024)
    text: str | None = Field(default=None, max_length=4096)
    postcondition: EffectPredicate

    @model_validator(mode="after")
    def shape(self):
        if (self.operation == "fill_element") != (self.text is not None):
            raise ValueError("browser_effect_text_shape_invalid")
        if self.operation == "fill_element" and (self.postcondition.kind != "input_value_equals"
                or self.postcondition.selector != self.selector or self.postcondition.value != self.text):
            raise ValueError("browser_fill_requires_exact_value_readback")
        return self


class CreatePlan(Strict):
    idempotency_key: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    target_id: str = Field(min_length=1, max_length=128)
    deadline_ms: int = Field(gt=0)
    steps: list[EffectStep] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def unique(self):
        if len({step.step_id for step in self.steps}) != len(self.steps):
            raise ValueError("browser_plan_duplicate_step_id")
        return self


PLAN_ACTION = ActionDefinition(action_id="browser.plan.execute", action_class=ActionClass.A4,
    mutates_state=True, verifier_type=VerifierType.STATE_PREDICATE, no_stale_replay=True,
    max_age_seconds=30, parameter_schema={"type": "object", "additionalProperties": False,
    "required": ["session_id", "plan_id", "plan_sha256"], "properties": {
        "session_id": {"type": "string"}, "plan_id": {"type": "string"},
        "plan_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}})


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class BrowserActionPlanService:
    PREFIX = "browser_action_plan:"

    def __init__(self, *, store, sessions, producers, command_authority, profile_clients=None):
        self.store, self.sessions, self.producers = store, sessions, producers
        self.command_authority = command_authority
        self.profile_clients = profile_clients or {}
        producers.action_plans = self

    async def _read(self, db, plan_id):
        row = await self.producers._one(db, "SELECT value FROM runtime_meta WHERE key=?", (self.PREFIX + plan_id,))
        if row is None:
            raise PlanError("browser_plan_unknown")
        return json.loads(row["value"])

    async def _write(self, db, plan):
        await db.execute("UPDATE runtime_meta SET value=?,updated_at_unix_ms=? WHERE key=?",
                         (json.dumps(plan, sort_keys=True), int(time.time() * 1000), self.PREFIX + plan["plan_id"]))

    async def get(self, *, session_id, owner_device_id, plan_id):
        async with self.store.connection() as db:
            plan = await self._read(db, plan_id)
        if plan["session_id"] != session_id or plan["owner_device_id"] != owner_device_id:
            raise PlanError("browser_plan_unknown")
        return plan

    async def create(self, *, session_id, owner_device_id, body, now_ms=None):
        now = int(time.time() * 1000) if now_ms is None else now_ms
        if not now < body.deadline_ms <= now + 900_000:
            raise PlanError("browser_plan_deadline_invalid")
        request = body.model_dump(mode="json")
        key = "browser_action_plan_idempotency:" + digest([session_id, owner_device_id, body.idempotency_key])
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            session, profile = await self.producers._live(db, session_id, now)
            if session["owner_device_id"] != owner_device_id:
                raise PlanError("browser_plan_unknown")
            task = await self.producers._task_binding(db, session, body.task_id)
            posture = self.sessions.broker.policy.check_profile(session["profile_alias"])
            if profile["mutation_policy"] != "gateway_authorized_only" or posture.get("mutation") != "gateway_authorized_only":
                raise PlanError("browser_plan_profile_mutation_forbidden")
            if body.target_id != session["active_target_id"]:
                raise PlanError("browser_plan_target_not_current")
            from van_gateway.browser.agent_grant import domain_allowed
            for step in body.steps:
                if step.postcondition.url and not domain_allowed(step.postcondition.url, (task["target_domain"],)):
                    raise PlanError("browser_plan_postcondition_outside_task_domain")
            previous = await self.producers._one(db, "SELECT value FROM runtime_meta WHERE key=?", (key,))
            if previous:
                old = await self._read(db, previous["value"])
                if old["request_sha256"] != digest(request):
                    raise PlanError("browser_plan_idempotency_conflict")
                return old
            prior_plan = await self.producers._one(db, "SELECT 1 FROM runtime_meta WHERE key LIKE ? AND json_extract(value,'$.task_id')=? LIMIT 1", (self.PREFIX + "%", body.task_id))
            if prior_plan:
                raise PlanError("browser_prepared_task_already_has_plan")
            immutable = {"session_id": session_id, "owner_device_id": owner_device_id,
                "task_id": body.task_id, "target_id": body.target_id, "deadline_ms": body.deadline_ms,
                "profile_alias": session["profile_alias"], "profile_lease_id": profile["lease_holder"],
                "profile_generation": profile["lease_generation"], "mission_id": session["mission_id"],
                "allowed_domains": [task["target_domain"]], "steps": request["steps"]}
            plan_id = "bplan_" + uuid.uuid4().hex
            plan = {**immutable, "plan_id": plan_id, "plan_sha256": digest(immutable),
                "request_sha256": digest(request), "idempotency_key": body.idempotency_key, "status": "DRAFT", "action_class": "A4",
                "created_at_ms": now, "execution_id": None, "command_id": None,
                "step_states": {step.step_id: {"status": "PENDING"} for step in body.steps},
                "approval_command": "execute browser plan " + json.dumps({"session_id": session_id, "plan_id": plan_id, "plan_sha256": digest(immutable)}, sort_keys=True, separators=(",", ":"))}
            await db.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)",
                (self.PREFIX + plan_id, json.dumps(plan, sort_keys=True), now))
            await db.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)", (key, plan_id, now))
            await db.commit()
            return plan

    async def cancel(self, *, session_id, owner_device_id, plan_id):
        await self.get(session_id=session_id, owner_device_id=owner_device_id, plan_id=plan_id)
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            plan = await self._read(db, plan_id)
            if plan["status"] not in {"VERIFIED_SUCCESS", "CANCELLED"}:
                plan["status"] = "CANCELLED"
                await self._write(db, plan)
            await db.commit()
        return plan

    async def resolve_step(self, db, *, params, operation, session, profile, task_id, consume, result_validation, now):
        if set(params) != {"plan_id", "plan_sha256", "step_id"}:
            raise PlanError("browser_plan_call_shape_invalid")
        plan = await self._read(db, params["plan_id"])
        if ((plan["status"] != "RUNNING" and not (operation == "observe_effect" and plan["status"] in {"VERIFIED_SUCCESS", "UNKNOWN", "UNVERIFIABLE"})) or plan["execution_id"] is None or plan["deadline_ms"] <= now
            or plan["plan_sha256"] != params["plan_sha256"] or plan["session_id"] != session["session_id"]
            or plan["task_id"] != task_id or plan["target_id"] != session["active_target_id"]
            or plan["profile_lease_id"] != profile["lease_holder"] or plan["profile_generation"] != profile["lease_generation"]):
            raise PlanError("browser_plan_authority_stale")
        posture = self.sessions.broker.policy.check_profile(session["profile_alias"])
        if profile["mutation_policy"] != "gateway_authorized_only" or posture.get("mutation") != "gateway_authorized_only":
            raise PlanError("browser_plan_profile_mutation_forbidden")
        execution = await self.producers._one(db, "SELECT * FROM action_executions WHERE execution_id=? AND command_id=?", (plan["execution_id"], plan["command_id"]))
        live_execution = execution is not None and execution["status"] in {"PREFLIGHT_PASSED", "EXECUTING", "SUBMITTED", "VERIFYING"}
        verified_readback = (execution is not None and execution["status"] == "VERIFIED_SUCCESS"
                             and operation == "observe_effect" and plan["status"] == "VERIFIED_SUCCESS")
        if not live_execution and not verified_readback:
            raise PlanError("browser_plan_execution_not_live")
        seal_row = await self.producers._one(db, "SELECT value FROM runtime_meta WHERE key=?", ("command_authority:" + plan["command_id"],))
        seal = json.loads(seal_row["value"]) if seal_row else {}
        exact = {"session_id": plan["session_id"], "plan_id": plan["plan_id"], "plan_sha256": plan["plan_sha256"]}
        if (seal.get("authority_source") != "OWNER_COMMAND" or seal.get("owner_approved") is not True or seal.get("typed_action_id") != PLAN_ACTION.action_id
            or seal.get("typed_parameter_constraints") != exact or seal.get("device_id") != plan["owner_device_id"]
            or seal.get("principal_type") != "OWNER_DEVICE" or seal.get("effective_action_class") != "A4"
            or seal.get("expires_at_unix") is None or now >= seal["expires_at_unix"] * 1000
            or now - seal.get("issued_at_unix", 0) * 1000 > 30_000
            or execution["action_id"] != PLAN_ACTION.action_id or execution["parameters_digest"] != digest(exact)):
            raise PlanError("browser_plan_sealed_authority_stale")
        from van_gateway.mission.control import require_mission_dispatch, MissionControlError
        command_mission = await self.producers._one(db, "SELECT mission_id FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id')=?", (plan["command_id"],))
        if command_mission:
            try:
                await require_mission_dispatch(self.store, command_mission["mission_id"], db=db)
            except MissionControlError as exc:
                raise PlanError(exc.reason) from exc
        from van_gateway.capability.owner_permissions import recheck_permission_execution, enforce_permission_scope, OwnerPermissionDenied
        try:
            await recheck_permission_execution(self.store, plan["execution_id"], db=db)
            await enforce_permission_scope(self.store, action_id=PLAN_ACTION.action_id, parameters=exact,
                execution_id=plan["execution_id"], claim=False, db=db)
        except OwnerPermissionDenied as exc:
            raise PlanError(str(exc)) from exc
        step = next((step for step in plan["steps"] if step["step_id"] == params["step_id"]), None)
        if step is None or operation not in {step["operation"], "observe_effect"}:
            raise PlanError("browser_plan_step_mismatch")
        state = plan["step_states"][step["step_id"]]
        if operation == "observe_effect":
            if state["status"] not in {"IN_FLIGHT", "VERIFIED"}:
                raise PlanError("browser_plan_step_not_dispatched")
        elif result_validation:
            if state["status"] != "IN_FLIGHT":
                raise PlanError("browser_plan_step_not_in_flight")
        else:
            if state["status"] != "PENDING":
                raise PlanError("browser_plan_effect_retry_refused")
            prior = plan["steps"][:plan["steps"].index(step)]
            if any(plan["step_states"][s["step_id"]]["status"] != "VERIFIED" for s in prior):
                raise PlanError("browser_plan_step_order_invalid")
            if consume:
                state.update(status="IN_FLIGHT", dispatched_at_ms=now)
                await self._write(db, plan)
        return {"planned_step": step, "plan_id": plan["plan_id"], "plan_sha256": plan["plan_sha256"], "execution_id": plan["execution_id"]}

    async def verify(self, execution, parameters):
        """Separate post-submission readback for ActionRuntime's trusted observer."""
        from services.browser_control_agent.agent import Call
        from services.browser_control_agent.authority import Operation
        record = await self.command_authority.get(execution.command_id)
        if record is None:
            raise PlanError("browser_plan_command_unknown")
        plan = await self.get(session_id=parameters["session_id"], owner_device_id=record.device_id, plan_id=parameters["plan_id"])
        if plan["plan_sha256"] != parameters["plan_sha256"] or plan["execution_id"] != execution.execution_id:
            raise PlanError("browser_plan_verification_binding_mismatch")
        success = plan["status"] == "VERIFIED_SUCCESS" and all(state["status"] == "VERIFIED" for state in plan["step_states"].values())
        if not success:
            return {"success": False, "status": plan["status"], "plan_id": plan["plan_id"], "independent_readbacks": []}
        client, caller, proxy = self.profile_clients[plan["profile_alias"]]
        grant = await self.store.fetchone("SELECT * FROM browser_control_producer_grants WHERE task_id=? AND session_id=? AND caller_common_name=? AND proxy_principal_sha256=?", (plan["task_id"], plan["session_id"], caller, proxy))
        if grant is None:
            raise PlanError("browser_plan_verification_grant_unknown")
        observations = []
        for step in plan["steps"]:
            call = Call(operation=Operation.OBSERVE_EFFECT, session_id=plan["session_id"], target_id=plan["target_id"],
                lease_id=grant["control_lease_id"], lease_generation=grant["control_generation"], task_id=plan["task_id"],
                params={"plan_id": plan["plan_id"], "plan_sha256": plan["plan_sha256"], "step_id": step["step_id"]})
            observations.append(await client.invoke(call))
        return {"success": all(value.get("postcondition_matched") is True for value in observations),
            "status": plan["status"], "plan_id": plan["plan_id"], "plan_sha256": plan["plan_sha256"],
            "independent_readbacks": observations, "evidence_pointer": "browser-plan://" + plan["plan_id"] + "/" + digest(observations)}

    async def execute(self, execution, parameters):
        """Called only by the canonical action adapter; every fence is checked again."""
        from services.browser_control_agent.agent import Call
        from services.browser_control_agent.authority import Operation
        from van_gateway.mission.control import require_mission_dispatch
        record, age = await self.command_authority.authorize_action(command_id=execution.command_id,
            action=PLAN_ACTION, principal_type=execution.principal_type, requested_by=execution.requested_by,
            turn_id=execution.turn_id, snapshot_id=execution.snapshot_id, parameters=parameters)
        if (age > 30 or record.authority_source.value != "OWNER_COMMAND" or not record.owner_approved
            or record.principal_type != PrincipalType.OWNER_DEVICE or record.typed_action_id != PLAN_ACTION.action_id):
            raise PlanError("browser_plan_fresh_owner_approval_required")
        plan = await self.get(session_id=parameters["session_id"], owner_device_id=record.device_id, plan_id=parameters["plan_id"])
        if plan["plan_sha256"] != parameters["plan_sha256"]:
            raise PlanError("browser_plan_digest_mismatch")
        if plan["status"] != "DRAFT":
            return plan  # durable status/readback only, never retry an effect
        await require_mission_dispatch(self.store, plan["mission_id"])
        if plan["profile_alias"] not in self.profile_clients:
            raise PlanError("browser_plan_native_client_unbound")
        client, caller, proxy = self.profile_clients[plan["profile_alias"]]
        grant = await self.producers.issue_control_grant(task_id=plan["task_id"], session_id=plan["session_id"],
            target_id=plan["target_id"], caller_common_name=caller, proxy_principal_sha256=proxy,
            scope="browser.actuate", step_budget=4 * len(plan["steps"]), deadline_ms=min(plan["deadline_ms"], (record.issued_at_unix + 30) * 1000, (record.expires_at_unix or record.issued_at_unix + 30) * 1000))
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            current = await self._read(db, plan["plan_id"])
            if current["status"] != "DRAFT":
                raise PlanError("browser_plan_concurrent_execution_refused")
            actual = await self.producers._one(db, "SELECT * FROM action_executions WHERE execution_id=?", (execution.execution_id,))
            if actual is None or actual["command_id"] != execution.command_id or actual["action_id"] != PLAN_ACTION.action_id or actual["status"] not in {"PREFLIGHT_PASSED", "EXECUTING"}:
                raise PlanError("browser_plan_execution_not_live")
            current.update(status="RUNNING", execution_id=execution.execution_id, command_id=execution.command_id)
            await self._write(db, current)
            await db.commit()
        for step in plan["steps"]:
            params = {"plan_id": plan["plan_id"], "plan_sha256": plan["plan_sha256"], "step_id": step["step_id"]}
            def call(operation):
                return Call(operation=Operation(operation), session_id=plan["session_id"], target_id=plan["target_id"],
                    lease_id=grant["control_lease_id"], lease_generation=grant["control_generation"], task_id=plan["task_id"], params=params)
            try:
                await require_mission_dispatch(self.store, plan["mission_id"])
                result = await client.invoke(call(step["operation"]))
                observed = await client.invoke(call("observe_effect"))
                verified = result.get("effect_dispatched") is True and observed.get("postcondition_matched") is True
                async with self.store.connection() as db:
                    await db.execute("BEGIN IMMEDIATE")
                    current = await self._read(db, plan["plan_id"])
                    if current["status"] != "RUNNING":
                        raise PlanError("browser_plan_cancelled_during_effect")
                    current["step_states"][step["step_id"]].update(status="VERIFIED" if verified else "UNVERIFIABLE",
                        effect_receipt=result, independent_readback=observed)
                    if not verified:
                        current["status"] = "UNVERIFIABLE"
                    await self._write(db, current)
                    await db.commit()
                if not verified:
                    return current
            except (Exception, asyncio.CancelledError) as exc:
                # Lost reply, owner preemption, or native refusal can occur after an
                # effect. The claim remains consumed; no automatic mutation retry.
                async with self.store.connection() as db:
                    await db.execute("BEGIN IMMEDIATE")
                    current = await self._read(db, plan["plan_id"])
                    if current["status"] == "RUNNING":
                        current["status"] = "UNKNOWN"
                        await self._write(db, current)
                    await db.commit()
                if isinstance(exc, asyncio.CancelledError):
                    raise
                return current
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            current = await self._read(db, plan["plan_id"])
            if current["status"] == "RUNNING":
                current["status"] = "VERIFIED_SUCCESS"
                await self._write(db, current)
            await db.commit()
        return current


def build_action_plan_router(service):
    router = APIRouter(prefix="/v1/browser/interactive-sessions", tags=["browser-action-plans"])

    def owner(request):
        value = getattr(request.state, "van_device_id", None)
        if not value:
            raise HTTPException(401, "device_proof_required")
        return value

    async def guard(operation):
        try:
            return await operation
        except ValueError as exc:
            raise HTTPException(404 if str(exc) == "browser_plan_unknown" else 409, str(exc)) from exc

    @router.post("/{session_id}/action-plans")
    async def create(request: Request, session_id: str, body: CreatePlan):
        return await guard(service.create(session_id=session_id, owner_device_id=owner(request), body=body))

    @router.get("/{session_id}/action-plans")
    async def list_plans(request: Request, session_id: str):
        device = owner(request)
        rows = await service.store.fetchall("SELECT value FROM runtime_meta WHERE key LIKE ? ORDER BY updated_at_unix_ms DESC LIMIT 128", (service.PREFIX + "%",))
        session = await service.sessions.get(session_id)
        if session is None or session.owner_device_id != device:
            raise HTTPException(404, "interactive_session_unknown")
        tasks = await service.store.fetchall("SELECT t.task_id,t.goal,t.target_domain,t.action_class,t.status FROM browser_tasks t JOIN mission_activities a ON a.executor_ref=t.task_id WHERE a.mission_id=? AND a.executor='BROWSER_FABRIC' AND t.profile_alias=? AND t.status IN ('PENDING','LEASED','RUNNING','RESUME_AUTHORIZED') ORDER BY t.updated_at_ms DESC LIMIT 32", (session.mission_id, session.profile_alias))
        origin_row = await service.store.fetchone("SELECT value FROM runtime_meta WHERE key=?", ("browser_target_origin:"+session_id+":"+(session.active_target_id or ""),))
        origin = json.loads(origin_row["value"]) if origin_row else {}
        binding = await service.store.fetchone("SELECT producer_session_id FROM browser_stream_producers WHERE session_id=? AND revoked_at_ms IS NULL", (session_id,))
        observed_domain = origin.get("hostname") if binding and origin.get("producer_session_id") == binding["producer_session_id"] and origin.get("url_digest") == session.active_url_digest and origin.get("scheme") in {"https","http"} else None
        profile = await service.store.fetchone("SELECT mutation_policy FROM browser_profiles WHERE profile_alias=?", (session.profile_alias,))
        posture = service.sessions.broker.policy.check_profile(session.profile_alias)
        mutation_permitted = profile is not None and profile["mutation_policy"] == "gateway_authorized_only" and posture.get("mutation") == "gateway_authorized_only"
        plan_contract = {"action_id":"browser.plan.execute", "profile_alias":session.profile_alias,
            "profile_mutation_policy":profile["mutation_policy"] if profile else None,
            "profile_mutation_permitted":mutation_permitted, "required_action_class":"A4",
            "freshness_seconds":30, "max_steps":12, "task_plan_limit":1}
        return {"plan_contract":plan_contract,"preparation_contract": {"profile_mutation_permitted":mutation_permitted,"freshness_seconds":30,"action_id":"browser.task.prepare", "action_class":"A3", "command_prefix":"prepare browser task ", "required_fields":["session_id","target_domain","goal"], "observed_target_domain": observed_domain, "native_domain_observation_available": observed_domain is not None}, "task_candidates": [dict(row) for row in tasks], "plans": [plan for row in rows if (plan := json.loads(row["value"]))["session_id"] == session_id and plan["owner_device_id"] == device]}

    @router.get("/{session_id}/action-plans/{plan_id}")
    async def get(request: Request, session_id: str, plan_id: str):
        return await guard(service.get(session_id=session_id, owner_device_id=owner(request), plan_id=plan_id))

    @router.post("/{session_id}/action-plans/{plan_id}/cancel")
    async def cancel(request: Request, session_id: str, plan_id: str):
        return await guard(service.cancel(session_id=session_id, owner_device_id=owner(request), plan_id=plan_id))
    return router
