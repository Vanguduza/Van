"""Paired-owner plan proposals and durable readback, without runtime credentials.

The application authenticates the device and verifies hardware proof on every
mutation before this router. Proposing a plan never deploys or admits it.
"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from van_gateway.automation.api import AutomationApi, CompileBody
from van_gateway.automation.canonical import canonical_json, digest
from van_gateway.automation.models import IntentSignature, Primitive, WorkflowIR
from van_gateway.automation.primitive_policy import SUPPORTED_OPERATIONS


OWNER_PLANS_SQL = """CREATE TABLE IF NOT EXISTS automation_owner_plans(
    device_id TEXT NOT NULL REFERENCES devices(device_id), idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL, state TEXT NOT NULL, result_json TEXT,
    created_at_ms INTEGER NOT NULL, completed_at_ms INTEGER,
    PRIMARY KEY(device_id,idempotency_key))"""


class OwnerPlanBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=8, max_length=160)
    semantic_name: str = Field(min_length=1, max_length=160)
    workflow_ir: WorkflowIR
    capability_id: str | None = Field(default=None, min_length=1, max_length=160)


def operation_contract() -> dict:
    return {
        "schema_version": 1, "workflow_ir_schema": WorkflowIR.model_json_schema(),
        "operations": {primitive.value: sorted(operations) for primitive, operations in SUPPORTED_OPERATIONS.items()},
        "predicate_operators": ["EQ", "NE", "LT", "LTE", "GT", "GTE", "IN", "CONTAINS", "EXISTS", "ALL", "ANY", "NOT"],
        "value_kinds": ["LITERAL", "PATH"], "optional_branch_binding_kind": "STEP_RESULT",
        "limits": {"steps": 40, "branches": 10, "predicate_depth": 8, "predicate_nodes": 64,
                   "mapping_fields": 64, "switch_cases": 10, "wait_ms": 30000, "data_bytes": 1048576},
        "triggers": ["INVOKE", "SCHEDULE", "EVENT", "WEBHOOK"], "schedule_timezone": "UTC",
        "trigger_authority": "GATEWAY_STANDING_AUTHORITY_ONLY",
        "external_write_methods": ["POST", "PUT", "PATCH", "DELETE"], "external_write_action_class": "A4",
        "external_write_requires": ["ADMITTED_IMMUTABLE_ARTIFACT", "CURRENT_CANONICAL_OWNER_AUTHORITY",
                                    "OPERATOR_BOUND_CREDENTIAL_METHOD_DOMAIN", "INDEPENDENT_GET_READBACK"],
        "native_capabilities": ["reminder.create"], "native_capability_action_class": "A3",
        "candidate_grants_execution": False, "engine_success_is_owner_success": False,
        "uncertain_effect_replay": "REFUSED_READ_DURABLE_STATE_AND_REQUIRE_NEW_OWNER_DECISION",
        "branch_join": "ALL_PARENTS_SETTLED_ANY_SELECTED_EDGE",
        "execution_command_template": "automation execute {capability_id} artifact {artifact_id} with {inputs_json}",
        "admission_command_template": "automation admit {artifact_id}",
        "execution_action_id_template": "automation.workflow.{capability_id}",
    }


class OwnerAutomationApi:
    def __init__(self, api: AutomationApi):
        self.api, self.store = api, api.store
        self.router = APIRouter(prefix="/v1/owner/automation", tags=["owner-automation"])
        self._install()

    async def ensure(self):
        await self.store.execute(OWNER_PLANS_SQL)

    async def _device(self, request: Request) -> str:
        device_id = getattr(request.state, "van_device_id", "")
        if not device_id:
            raise HTTPException(401, "owner_device_required")
        row = await self.store.fetchone("SELECT revoked_at_unix FROM devices WHERE device_id=?", (device_id,))
        if row is None or row["revoked_at_unix"] is not None:
            raise HTTPException(403, "owner_device_revoked_or_unknown")
        return device_id

    @staticmethod
    def _response(value: dict, status_code: int = 200):
        return JSONResponse(value, status_code=status_code, headers={"Cache-Control": "no-store"})

    async def plan_view(self, artifact_id: str) -> dict:
        artifact = await self.api.registry.get_artifact(artifact_id)
        binding = await self.api.runtime_bindings.get(artifact_id)
        if artifact is None or binding is None:
            raise HTTPException(404, "AUTOMATION_PLAN_NOT_FOUND")
        return {"artifact_id": artifact_id, "capability_id": artifact.capability_id, "version": artifact.version,
                "lifecycle_state": artifact.lifecycle_state.value, "workflow_ir": binding["ir"],
                "workflow_ir_digest": artifact.workflow_ir_digest, "semantic_digest": artifact.compiled_semantic_digest,
                "full_digest": artifact.compiled_full_digest, "validation_report_digest": artifact.validation_report_digest,
                "binding_state": binding["binding_state"], "runtime_readiness_errors": binding["readiness_errors"],
                "action_id": "automation.workflow." + artifact.capability_id,
                "execution_command_template": "automation execute {capability_id} artifact {artifact_id} with {inputs_json}",
                "admission_command_template": "automation admit {artifact_id}",
                "owner_success": False, "created_at_ms": artifact.created_at_ms}

    async def propose(self, body: OwnerPlanBody, device_id: str) -> dict:
        await self.ensure()
        if len(canonical_json(body.model_dump(mode="json"))) > 2 * 1024 * 1024:
            raise HTTPException(422, "AUTOMATION_PLAN_TOO_LARGE")
        request_digest = digest(body.model_dump(mode="json"))
        # A revision must refer to this device's own recorded capability. It may
        # create a new immutable artifact, never overwrite an admitted version.
        if body.capability_id:
            rows = await self.store.fetchall("SELECT result_json FROM automation_owner_plans WHERE device_id=? AND state='COMPLETED'", (device_id,))
            if not any(json.loads(row["result_json"]).get("capability_id") == body.capability_id for row in rows):
                raise HTTPException(403, "AUTOMATION_PLAN_REVISION_NOT_OWNED")
        now = int(time.time() * 1000)
        async with self.store.connection() as db:
            cursor = await db.execute("INSERT OR IGNORE INTO automation_owner_plans VALUES(?,?,?,'IN_PROGRESS',NULL,?,NULL)",
                                      (device_id, body.idempotency_key, request_digest, now))
            await db.commit()
            claimed = cursor.rowcount == 1
        if not claimed:
            row = await self.store.fetchone("SELECT * FROM automation_owner_plans WHERE device_id=? AND idempotency_key=?", (device_id, body.idempotency_key))
            if row["request_digest"] != request_digest:
                raise HTTPException(409, "AUTOMATION_PLAN_IDEMPOTENCY_CONFLICT")
            if row["state"] != "COMPLETED":
                raise HTTPException(409, "AUTOMATION_PLAN_OUTCOME_PENDING")
            return {**json.loads(row["result_json"]), "replayed": True}
        try:
            result = await self.api.compile_candidate(CompileBody(
                semantic_name=body.semantic_name, workflow_ir=body.workflow_ir, capability_id=body.capability_id,
                signature=IntentSignature(goal_class=body.workflow_ir.family, source_class="OWNER_DEFINED",
                                          destination_class="VAN", mutation_class=body.workflow_ir.action_class)))
        except HTTPException as exc:
            # Validation refusal has no deployable effect. Preserve the claim and
            # refuse repeats rather than silently create another artifact.
            await self.store.execute("UPDATE automation_owner_plans SET state='REFUSED',completed_at_ms=? WHERE device_id=? AND idempotency_key=?",
                                     (now, device_id, body.idempotency_key))
            raise exc
        result = {**result, "idempotency_key": body.idempotency_key, "candidate_only": True,
                  "owner_success": False, "replayed": False}
        await self.store.execute("UPDATE automation_owner_plans SET state='COMPLETED',result_json=?,completed_at_ms=? WHERE device_id=? AND idempotency_key=? AND state='IN_PROGRESS'",
                                 (self.store.dumps(result), int(time.time() * 1000), device_id, body.idempotency_key))
        return result

    def _install(self):
        @self.router.get("/contracts")
        async def contracts(request: Request):
            await self._device(request)
            return self._response(operation_contract())

        @self.router.post("/plans")
        async def propose(body: OwnerPlanBody, request: Request):
            device_id = await self._device(request)
            return self._response(await self.propose(body, device_id), 201)

        @self.router.get("/plans")
        async def plans(request: Request, limit: int = Query(30, ge=1, le=100)):
            await self._device(request)
            rows = await self.store.fetchall("SELECT artifact_id FROM automation_artifacts ORDER BY created_at_ms DESC,artifact_id LIMIT ?", (limit,))
            return self._response({"plans": [await self.plan_view(row["artifact_id"]) for row in rows]})

        @self.router.get("/plans/{artifact_id}")
        async def plan(artifact_id: str, request: Request):
            await self._device(request)
            return self._response(await self.plan_view(artifact_id))

        @self.router.get("/requests/{idempotency_key}")
        async def proposal_request(idempotency_key: str, request: Request):
            device_id = await self._device(request)
            await self.ensure()
            row = await self.store.fetchone("SELECT * FROM automation_owner_plans WHERE device_id=? AND idempotency_key=?", (device_id, idempotency_key))
            if row is None:
                raise HTTPException(404, "AUTOMATION_PROPOSAL_REQUEST_NOT_FOUND")
            return self._response({"idempotency_key": idempotency_key, "state": row["state"],
                "request_digest": row["request_digest"], "result": json.loads(row["result_json"]) if row["result_json"] else None,
                "recovery_read_only": True, "replay_permitted": False})

        @self.router.get("/runs/{run_id}")
        async def run(run_id: str, request: Request):
            device_id = await self._device(request)
            row = await self.store.fetchone("SELECT * FROM automation_runs WHERE run_id=?", (run_id,))
            authority = await self.api.dispatcher.authority.get(row["command_id"]) if row and self.api.dispatcher else None
            if row is None or authority is None or authority.device_id != device_id:
                raise HTTPException(404, "AUTOMATION_RUN_NOT_FOUND")
            steps = await self.store.fetchall("SELECT step_id,state,result_digest,completed_at_ms FROM automation_worker_steps WHERE run_id=? ORDER BY created_at_ms,step_id", (run_id,))
            return self._response({"run_id": run_id, "artifact_id": row["artifact_id"], "capability_id": row["capability_id"],
                "status": row["status"], "verifier_status": row["verifier_status"],
                "owner_success": row["status"] == "VERIFIED_SUCCESS" and row["verifier_status"] == "VERIFIED_SUCCESS",
                "evidence_pointer": row["evidence_pointer"], "steps": [dict(step) for step in steps],
                "replay_permitted": False})
