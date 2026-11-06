"""Signed owner preparation binds an existing command Mission, never starts a worker."""
from __future__ import annotations
import json
import time

from van_gateway.action.models import ActionDefinition, VerifierType
from van_gateway.browser.action_plans import PlanError, digest
from van_gateway.browser.models import BrowserStrategy, AutonomyTier
from van_gateway.browser.service import BrowserTaskTransitionRefused, TERMINAL_TASK_STATUSES
from van_gateway.models import ActionClass, PrincipalType

PREPARE_ACTION = ActionDefinition(action_id="browser.task.prepare", action_class=ActionClass.A3,
    mutates_state=True, verifier_type=VerifierType.STATE_PREDICATE,
    allowed_principals={PrincipalType.OWNER_DEVICE}, no_stale_replay=True, max_age_seconds=30,
    parameter_schema={"type":"object","additionalProperties":False,"required":["session_id","target_domain","goal"],
        "properties":{"session_id":{"type":"string"},"target_domain":{"type":"string","maxLength":253},
                      "goal":{"type":"string","minLength":1,"maxLength":1000}}})


class BrowserTaskPreparationService:
    PREFIX = "browser_task_preparation:"

    def __init__(self, *, store, sessions, producers, tasks, binder, command_authority):
        self.store, self.sessions, self.producers = store, sessions, producers
        self.tasks, self.binder, self.command_authority = tasks, binder, command_authority

    async def _admission(self, db, *, execution, parameters, mission_id, record):
        from van_gateway.mission.control import require_mission_dispatch
        from van_gateway.capability.owner_permissions import recheck_permission_execution, enforce_permission_scope
        now = int(time.time()*1000)
        session, profile = await self.producers._live(db, parameters["session_id"], now)
        if session["owner_device_id"] != record.device_id:
            raise PlanError("browser_preparation_session_unknown")
        await self.producers._check_control(db, session, session["control_lease_id"], session["control_generation"], now,
            holder="OWNER", issued_for=record.device_id)
        if not session["active_target_id"] or session["acked_viewport_revision"] != session["viewport_revision"]:
            raise PlanError("browser_preparation_current_frame_required")
        producer = await self.producers._one(db, "SELECT * FROM browser_stream_producers WHERE session_id=? AND revoked_at_ms IS NULL", (session["session_id"],))
        if producer is None or session["acked_media_epoch"] != producer["producer_session_id"]:
            raise PlanError("browser_preparation_native_producer_required")
        await self.producers._stream_binding(db, producer["producer_session_id"], producer["producer_principal_sha256"], now)
        origin_row = await self.producers._one(db, "SELECT value FROM runtime_meta WHERE key=?", ("browser_target_origin:"+session["session_id"]+":"+session["active_target_id"],))
        origin = json.loads(origin_row["value"]) if origin_row else {}
        if (origin.get("producer_session_id") != producer["producer_session_id"] or origin.get("url_digest") != session["active_url_digest"]
            or origin.get("hostname") != parameters["target_domain"].lower() or origin.get("scheme") not in {"http","https"}):
            raise PlanError("browser_preparation_domain_not_observed")
        mission = await self.producers._one(db,"SELECT * FROM missions WHERE mission_id=?",(mission_id,))
        envelope = json.loads(mission["authority_envelope_json"]) if mission and mission["authority_envelope_json"] else {}
        if session["mission_id"] is not None and session["mission_id"] != mission_id:
            from van_gateway.mission.models import TERMINAL_STATES
            prior = await self.producers._one(db,"SELECT state FROM missions WHERE mission_id=?",(session["mission_id"],))
            if prior is None or prior["state"] not in {state.value for state in TERMINAL_STATES}:
                raise PlanError("browser_preparation_prior_mission_active")
        if (mission is None or mission["owner_principal_id"] != record.requested_by
            or envelope.get("source_command_id") != execution.command_id):
            raise PlanError("browser_preparation_canonical_mission_mismatch")
        actual = await self.producers._one(db,"SELECT * FROM action_executions WHERE execution_id=?",(execution.execution_id,))
        if (actual is None or actual["command_id"] != execution.command_id or actual["action_id"] != PREPARE_ACTION.action_id
            or actual["status"] not in {"PREFLIGHT_PASSED","EXECUTING"} or actual["parameters_digest"] != digest(parameters)):
            raise PlanError("browser_preparation_execution_not_live")
        await require_mission_dispatch(self.store, mission_id, db=db)
        await recheck_permission_execution(self.store, execution.execution_id, db=db)
        await enforce_permission_scope(self.store, action_id=PREPARE_ACTION.action_id, parameters=parameters,
            execution_id=execution.execution_id, claim=False, db=db)
        return session, profile

    async def prepare(self, execution, parameters, mission_id):
        if (set(parameters) != {"session_id","target_domain","goal"} or not isinstance(parameters["goal"],str)
            or not 1 <= len(parameters["goal"]) <= 1000 or not isinstance(parameters["target_domain"],str)
            or not 1 <= len(parameters["target_domain"]) <= 253):
            raise PlanError("browser_preparation_parameters_invalid")
        record, age = await self.command_authority.authorize_action(command_id=execution.command_id, action=PREPARE_ACTION,
            principal_type=execution.principal_type, requested_by=execution.requested_by, snapshot_id=execution.snapshot_id,
            turn_id=execution.turn_id, parameters=parameters)
        if (age > 30 or record.authority_source.value != "OWNER_COMMAND"
            or record.principal_type != PrincipalType.OWNER_DEVICE or record.typed_action_id != PREPARE_ACTION.action_id):
            raise PlanError("browser_preparation_exact_owner_command_required")
        # A new exact signed preparation may finish an interrupted metadata-only
        # reconciliation of previously verified effects. This never dispatches a
        # browser operation and is unavailable to GET/model/advisory paths.
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            session, _ = await self.producers._live(db, parameters["session_id"], int(time.time()*1000))
            if session["owner_device_id"] != record.device_id:
                raise PlanError("browser_preparation_session_unknown")
            await self.producers._check_control(db, session, session["control_lease_id"], session["control_generation"],
                int(time.time()*1000), holder="OWNER", issued_for=record.device_id)
            previous_mission = session["mission_id"]
        if previous_mission and previous_mission != mission_id:
            from van_gateway.mission.models import TERMINAL_STATES
            previous = await self.store.fetchone("SELECT state FROM missions WHERE mission_id=?",(previous_mission,))
            if previous and previous["state"] not in {state.value for state in TERMINAL_STATES}:
                completion = await self.store.fetchone("SELECT value FROM runtime_meta WHERE key LIKE 'browser_prepared_task_completion:%' AND json_extract(value,'$.parent_mission_id')=? ORDER BY updated_at_unix_ms DESC LIMIT 1",(previous_mission,))
                if completion:
                    marker = json.loads(completion["value"])
                    await self.complete_after_verified_plan(marker["plan_command_id"])
        key = self.PREFIX+execution.execution_id
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            session, profile = await self._admission(db, execution=execution, parameters=parameters, mission_id=mission_id, record=record)
            previous = await self.producers._one(db,"SELECT value FROM runtime_meta WHERE key=?",(key,))
            if previous:
                value = json.loads(previous["value"])
                if value["parameters_sha256"] != digest(parameters) or value["mission_id"] != mission_id:
                    raise PlanError("browser_preparation_idempotency_conflict")
                if value["status"] == "PREPARED":
                    return value
                raise PlanError("browser_preparation_outcome_unknown")
            value = {"execution_id":execution.execution_id,"command_id":execution.command_id,"mission_id":mission_id,
                "session_id":session["session_id"],"target_id":session["active_target_id"],"profile_alias":session["profile_alias"],
                "profile_lease_id":profile["lease_holder"],"profile_generation":profile["lease_generation"],
                "parameters_sha256":digest(parameters),"status":"PREPARING","task_id":None,
                "mutating_task":False,"worker_started":False,"control_delegated":False,"mission_pending":True}
            await db.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)",(key,json.dumps(value),int(time.time()*1000)))
            await db.commit()
        task = await self.tasks.create_task(profile_alias=session["profile_alias"],strategy=BrowserStrategy.HARNESS,
            autonomy_tier=AutonomyTier.L1_HARNESS_DETERMINISTIC,action_class=ActionClass.A1,
            target_domain=parameters["target_domain"],goal=parameters["goal"],mutating=False,
            command_id=execution.command_id,execution_id=execution.execution_id,capability_id=PREPARE_ACTION.action_id)
        # Persist the real created task before binder effects; interrupted binding
        # leaves a visible uncertain preparation, never fabricated completion.
        value["task_id"] = task.task_id
        await self.store.execute("UPDATE runtime_meta SET value=?,updated_at_unix_ms=? WHERE key=?",(json.dumps(value),int(time.time()*1000),key))
        await self.binder.bind_browser_task(mission_id=mission_id,task_id=task.task_id,capability_id=PREPARE_ACTION.action_id)
        await self.binder.bind_browser_session(mission_id=mission_id,session_id=session["session_id"],capability_id=PREPARE_ACTION.action_id)
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            await self._admission(db, execution=execution, parameters=parameters, mission_id=mission_id, record=record)
            await db.execute("UPDATE browser_interactive_sessions SET mission_id=? WHERE session_id=?",(mission_id,session["session_id"]))
            value["status"] = "PREPARED"
            await db.execute("UPDATE runtime_meta SET value=?,updated_at_unix_ms=? WHERE key=?",(json.dumps(value),int(time.time()*1000),key))
            await db.commit()
        return await self.readback(execution, parameters, mission_id)

    async def readback(self, execution, parameters, mission_id):
        row = await self.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",(self.PREFIX+execution.execution_id,))
        if not row:
            raise PlanError("browser_preparation_unknown")
        value = json.loads(row["value"])
        if value["parameters_sha256"] != digest(parameters) or value["mission_id"] != mission_id or value["status"] != "PREPARED":
            raise PlanError("browser_preparation_not_confirmed")
        session = await self.sessions.get(parameters["session_id"])
        task = await self.store.fetchone("SELECT * FROM browser_tasks WHERE task_id=?",(value["task_id"],))
        bound = await self.store.fetchone("SELECT 1 FROM mission_activities WHERE mission_id=? AND executor='BROWSER_FABRIC' AND executor_ref=?",(mission_id,value["task_id"]))
        if (session is None or session.mission_id != mission_id or task is None or bound is None
            or task["command_id"] != execution.command_id or task["execution_id"] != execution.execution_id
            or task["target_domain"] != parameters["target_domain"] or task["goal"] != parameters["goal"]):
            raise PlanError("browser_preparation_binding_not_observed")
        return {**value,"success":True,"evidence_pointer":"browser-preparation://"+execution.execution_id+"/"+digest(value)}

    async def complete_after_verified_plan(self, plan_command_id):
        """Reconcile the prepared task only after canonical plan verification.

        Completing exact approved effects does not measure the arbitrary owner
        goal. The parent Mission closes UNVERIFIABLE, with that distinction.
        """
        from van_gateway.mission.models import MissionState, TERMINAL_STATES
        from van_gateway.command.authority import AuthoritySource
        seal = await self.command_authority.get(plan_command_id)
        parameters = seal.typed_parameter_constraints if seal else {}
        if (seal is None or seal.authority_source is not AuthoritySource.OWNER_COMMAND
            or seal.principal_type is not PrincipalType.OWNER_DEVICE
            or seal.effective_action_class is not ActionClass.A4
            or seal.typed_action_id != "browser.plan.execute" or not seal.owner_approved
            or set(parameters) != {"session_id","plan_id","plan_sha256"}):
            raise PlanError("browser_parent_completion_approved_plan_required")
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            plan_row = await self.producers._one(db,"SELECT value FROM runtime_meta WHERE key=?",("browser_action_plan:"+parameters["plan_id"],))
            plan = json.loads(plan_row["value"]) if plan_row else {}
            execution = await self.producers._one(db,"SELECT * FROM action_executions WHERE command_id=? AND action_id='browser.plan.execute' AND status='VERIFIED_SUCCESS'",(plan_command_id,))
            plan_mission = await self.producers._one(db,"SELECT state FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id')=?",(plan_command_id,))
            receipt = await self.producers._one(db,"SELECT * FROM action_receipts WHERE execution_id=? AND status='VERIFIED_SUCCESS' ORDER BY created_at_unix_ms DESC LIMIT 1",(execution["execution_id"] if execution else "",))
            observed = json.loads(receipt["observed_postcondition_json"]) if receipt else {}
            native_readbacks = observed.get("independent_readbacks", [])
            expected_step_ids = {step["step_id"] for step in plan.get("steps", [])}
            witnessed_step_ids = {value.get("step_id") for value in native_readbacks if isinstance(value, dict)}
            if (not execution or not receipt or not plan_mission or plan_mission["state"] != "VERIFIED_SUCCESS"
                or plan.get("status") != "VERIFIED_SUCCESS" or plan.get("execution_id") != execution["execution_id"]
                or plan.get("command_id") != plan_command_id or plan.get("plan_sha256") != parameters["plan_sha256"]
                or plan.get("session_id") != parameters["session_id"] or plan.get("owner_device_id") != seal.device_id
                or execution["parameters_digest"] != digest(parameters)
                or execution["principal_type"] != "OWNER_DEVICE" or execution["requested_by"] != seal.requested_by
                or execution["action_class"] != "A4" or execution["snapshot_id"] != seal.snapshot_id
                or receipt["verifier_type"] != "STATE_PREDICATE"
                or observed.get("success") is not True or observed.get("plan_id") != plan.get("plan_id")
                or observed.get("plan_sha256") != plan.get("plan_sha256")
                or not expected_step_ids or witnessed_step_ids != expected_step_ids or len(native_readbacks) != len(expected_step_ids)
                or any(not isinstance(value, dict) or value.get("postcondition_matched") is not True
                    or value.get("plan_id") != plan.get("plan_id")
                    or value.get("observation_source") != "NATIVE_CDP_INDEPENDENT_READBACK" for value in native_readbacks)
                or any(value.get("status") != "VERIFIED" for value in plan.get("step_states",{}).values())
                or not receipt["evidence_pointer"] or not str(receipt["evidence_pointer"]).startswith("browser-plan://")):
                raise PlanError("browser_parent_completion_plan_not_verified")
            task = await self.producers._one(db,"SELECT * FROM browser_tasks WHERE task_id=?",(plan["task_id"],))
            prepared_row = await self.producers._one(db,"SELECT value FROM runtime_meta WHERE key=?",(self.PREFIX+(task["execution_id"] if task else ""),))
            prepared = json.loads(prepared_row["value"]) if prepared_row else {}
            parent = await self.producers._one(db,"SELECT * FROM missions WHERE mission_id=?",(plan["mission_id"],))
            prepare_execution = await self.producers._one(db,"SELECT * FROM action_executions WHERE execution_id=?",(task["execution_id"] if task else "",))
            contract = json.loads(parent["success_contract_json"]) if parent else {}
            if (not task or prepared.get("status") != "PREPARED" or prepared.get("task_id") != task["task_id"]
                or prepared.get("mission_id") != plan["mission_id"] or parent is None
                or prepared.get("session_id") != plan["session_id"] or prepared.get("command_id") != task["command_id"]
                or prepare_execution is None or prepare_execution["status"] != "VERIFIED_SUCCESS"
                or prepare_execution["action_id"] != PREPARE_ACTION.action_id
                or prepare_execution["principal_type"] != "OWNER_DEVICE" or prepare_execution["requested_by"] != seal.requested_by
                or parent["owner_principal_id"] != seal.requested_by
                or json.loads(parent["authority_envelope_json"]).get("source_command_id") != task["command_id"]
                or contract.get("postconditions") or contract.get("verifier_class")):
                raise PlanError("browser_parent_completion_source_not_confirmed")
            marker = {"task_id":task["task_id"],"parent_mission_id":plan["mission_id"],
                "plan_id":plan["plan_id"],"plan_sha256":plan["plan_sha256"],"plan_command_id":plan_command_id,
                "approved_effects_verified":True,"freeform_goal_independently_verified":False,
                "evidence_pointer":receipt["evidence_pointer"]}
            previous = await self.producers._one(db,"SELECT value FROM runtime_meta WHERE key=?",("browser_prepared_task_completion:"+task["task_id"],))
            if previous and json.loads(previous["value"]) != marker:
                raise PlanError("browser_parent_completion_conflict")
            await db.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?) ON CONFLICT(key) DO NOTHING",
                ("browser_prepared_task_completion:"+task["task_id"],json.dumps(marker),int(time.time()*1000)))
            await db.commit()
        # Exact plan effects are verified, but this task's freeform goal is not.
        # Keep that distinction in the task state as well as the parent Mission.
        try:
            await self.tasks.hold_for_verification(
                task_id=task["task_id"], error_code="BROWSER_FREEFORM_GOAL_UNVERIFIABLE",
                evidence_pointer=marker["evidence_pointer"],
            )
        except BrowserTaskTransitionRefused as exc:
            if exc.current not in {state.value for state in TERMINAL_TASK_STATUSES}:
                raise
            # A concurrent owner cancellation or other end state remains sticky.
        await self.binder.sync_from_subsystems(plan["mission_id"])
        current = await self.binder.missions.get(plan["mission_id"])
        if current.state is MissionState.RUNNING:
            current = await self.binder.missions.transition(current.mission_id,target=MissionState.VERIFYING,
                expected=MissionState.RUNNING,actor=PrincipalType.SYSTEM,evidence_ref=marker["evidence_pointer"],
                summary="Exact approved browser effects were verified; the broader goal remains unmeasured")
        if current.state is MissionState.VERIFYING:
            current = await self.binder.missions.transition(current.mission_id,target=MissionState.UNVERIFIABLE,
                expected=MissionState.VERIFYING,actor=PrincipalType.SYSTEM,evidence_ref=marker["evidence_pointer"],
                summary="Browser task effects completed; freeform owner goal lacks an independent success contract")
        if current.state not in TERMINAL_STATES:
            raise PlanError("browser_parent_completion_reconciliation_pending")
        return {**marker,"parent_state":current.state.value,"reconciliation_complete":True}
