"""One bounded continuation of an existing task, issued by a fresh exact owner A4.

Advisory decisions never create grants. The durable witness binds the original
task, escalation, immutable requested scope and verified owner command. Grant and
task transition commit together; workers spend a grant once before taking action.
"""
from __future__ import annotations

import json
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from van_gateway.action.models import ActionDefinition, VerifierType
from van_gateway.browser.action_plans import digest
from van_gateway.browser.models import BrowserTaskStatus
from van_gateway.browser.subagent import plausible_hostname
from van_gateway.browser.task_scope import load_scope
from van_gateway.command.authority import AuthoritySource, CommandAuthorityService
from van_gateway.models import ActionClass, PrincipalType

ACTION = ActionDefinition(action_id="browser.task.resume", action_class=ActionClass.A4,
    mutates_state=True, allowed_principals={PrincipalType.OWNER_DEVICE},
    verifier_type=VerifierType.STATE_PREDICATE, no_stale_replay=True, max_age_seconds=30,
    parameter_schema={"required": ["task_id", "escalation_id", "scope_sha256"],
        "properties": {"task_id": "string", "escalation_id": "string", "scope_sha256": "string"}})


class ResumeError(ValueError):
    pass


class ResumeContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    escalation_id: str
    scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope: dict[str, Any]
    action_id: Literal["browser.task.resume"]
    action_class: Literal["A4"]
    approval_command: str
    grants_authority: Literal[False]
    single_use: Literal[True]


class BrowserResumeService:
    PREFIX = "browser_resume_witness:"

    def __init__(self, browser, authority: CommandAuthorityService):
        self.browser, self.store, self.authority = browser, browser.store, authority

    @staticmethod
    async def _one(db, sql, params=()):
        return await (await db.execute(sql, params)).fetchone()

    @staticmethod
    def _object(value):
        try:
            result = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise ResumeError("browser_resume_record_invalid") from exc
        if not isinstance(result, dict):
            raise ResumeError("browser_resume_record_invalid")
        return result

    async def _scope(self, db, task_id, device_id, *, now):
        task = await self._one(db, "SELECT * FROM browser_tasks WHERE task_id=?", (task_id,))
        if task is None or not task["command_id"]:
            raise ResumeError("browser_resume_task_unknown")
        source = await self._one(db, "SELECT value FROM runtime_meta WHERE key=?",
                                 (CommandAuthorityService.PREFIX + task["command_id"],))
        owner = self._object(source["value"]) if source else {}
        if owner.get("device_id") != device_id or owner.get("principal_type") != "OWNER_DEVICE":
            raise ResumeError("browser_resume_task_unknown")
        # A fresh approval narrows/extends this task's scope; it cannot resume
        # a paused or terminal parent mission as a side effect.
        from van_gateway.mission.control import require_mission_dispatch
        parents = await (await db.execute("SELECT DISTINCT mission_id FROM mission_activities "
            "WHERE executor='BROWSER_FABRIC' AND executor_ref=?", (task_id,))).fetchall()
        for parent in parents:
            await require_mission_dispatch(self.store, parent["mission_id"], db=db)
        escalation = await self._one(db, "SELECT e.*,d.status AS decision_status FROM browser_escalations e "
            "JOIN decisions d ON d.id=e.decision_id WHERE e.task_id=? ORDER BY e.created_at_ms DESC,e.escalation_id DESC LIMIT 1", (task_id,))
        if (escalation is None or escalation["status"] != "OPEN"
            or escalation["boundary_type"] != "OWNER_EXTENSION_REQUIRED"
            or escalation["decision_status"] in {"REJECTED", "EXPIRED"}
            or escalation["expires_at_ms"] is None or now >= escalation["expires_at_ms"]):
            raise ResumeError("browser_resume_escalation_unavailable")
        current = self._object(escalation["current_scope_json"])
        delta = self._object(escalation["requested_scope_delta_json"])
        domains = current.get("allowed_domains")
        ceiling = delta.get("action_class_ceiling", current.get("action_class_ceiling"))
        scope = load_scope(task["scope_json"])
        if (scope is None or not isinstance(domains, list) or not domains or len(domains) > 64
            or any(not isinstance(d, str) or not plausible_hostname(d) for d in domains)
            or ceiling not in {"A1", "A2", "A3"}
            or set(delta) not in ({"allowed_domain"}, {"action_class_ceiling"})):
            raise ResumeError("browser_resume_scope_refused")
        if not set(domains).issubset(scope.hosts()):
            raise ResumeError("browser_resume_original_scope_changed")
        domain = delta.get("allowed_domain")
        if domain is not None:
            if not isinstance(domain, str) or not plausible_hostname(domain):
                raise ResumeError("browser_resume_scope_refused")
            scope.with_origin(domain, "OWNER_COMMAND_REVIEW")  # also enforces estate isolation
            domains = [*domains, domain]
        if len(set(domains)) > 64:
            raise ResumeError("browser_resume_scope_refused")
        immutable = {"task_id": task_id, "escalation_id": escalation["escalation_id"],
            "decision_id": escalation["decision_id"], "source_command_id": task["command_id"],
            "owner_device_id": device_id, "profile_alias": task["profile_alias"],
            "goal": task["goal"], "scope_json": task["scope_json"], "original_action_class": task["action_class"],
            "current_scope": current, "requested_scope_delta": delta,
            "approved_domains": sorted(set(domains)), "approved_action_class_ceiling": ceiling,
            "escalation_expires_at_ms": escalation["expires_at_ms"]}
        return task, immutable

    async def contract(self, task_id, device_id):
        self.browser._require_enabled()
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            task, scope = await self._scope(db, task_id, device_id, now=int(time.time()*1000))
            if task["status"] != "WAITING_FOR_OWNER":
                raise ResumeError("browser_resume_task_not_waiting")
        parameters = {"task_id": task_id, "escalation_id": scope["escalation_id"], "scope_sha256": digest(scope)}
        return {**parameters, "scope": scope, "action_id": ACTION.action_id, "action_class": "A4",
            "approval_command": "resume browser task " + json.dumps(parameters, sort_keys=True, separators=(",", ":")),
            "grants_authority": False, "single_use": True}

    async def authorize(self, execution, parameters):
        if not self.browser.settings.browser_enabled:
            raise ResumeError("browser_resume_disabled")
        record, age = await self.authority.authorize_action(command_id=execution.command_id, action=ACTION,
            principal_type=execution.principal_type, requested_by=execution.requested_by,
            snapshot_id=execution.snapshot_id, turn_id=execution.turn_id, parameters=parameters)
        if (age > 30 or record.authority_source is not AuthoritySource.OWNER_COMMAND
            or record.principal_type is not PrincipalType.OWNER_DEVICE or not record.owner_approved
            or not record.no_stale_replay or record.expires_at_unix is None
            or record.typed_action_id != ACTION.action_id or record.typed_parameter_constraints != parameters):
            raise ResumeError("browser_resume_fresh_exact_owner_approval_required")
        now = int(time.time()*1000)
        authorization_id = "bresume_" + digest([execution.command_id, parameters])[:32]
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            task, scope = await self._scope(db, parameters["task_id"], record.device_id, now=now)
            if scope["escalation_id"] != parameters["escalation_id"] or digest(scope) != parameters["scope_sha256"]:
                raise ResumeError("browser_resume_scope_changed")
            actual = await self._one(db, "SELECT * FROM action_executions WHERE execution_id=?", (execution.execution_id,))
            if (actual is None or actual["command_id"] != execution.command_id or actual["action_id"] != ACTION.action_id
                or actual["status"] not in {"PREFLIGHT_PASSED", "EXECUTING"}
                or actual["parameters_digest"] != digest(parameters)):
                raise ResumeError("browser_resume_execution_not_live")
            if task["status"] != "WAITING_FOR_OWNER":
                raise ResumeError("browser_resume_task_not_waiting")
            if await self._one(db, "SELECT 1 FROM browser_scope_authorizations WHERE escalation_id=?", (scope["escalation_id"],)):
                raise ResumeError("browser_resume_already_issued")
            expires = min(scope["escalation_expires_at_ms"], record.expires_at_unix*1000, (record.issued_at_unix+30)*1000)
            witness = {"authorization_id": authorization_id, "execution_id": execution.execution_id,
                "command_id": execution.command_id, "owner_device_id": record.device_id,
                "parameters": parameters, "scope": scope, "expires_at_ms": expires}
            await db.execute("INSERT INTO browser_scope_authorizations(authorization_id,escalation_id,task_id,decision_id,"
                "approved_domains_json,approved_action_class_ceiling,status,issued_at_ms,expires_at_ms) VALUES(?,?,?,?,?,?,'ACTIVE',?,?)",
                (authorization_id, scope["escalation_id"], task["task_id"], scope["decision_id"],
                 json.dumps(scope["approved_domains"]), scope["approved_action_class_ceiling"], now, expires))
            await db.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)",
                (self.PREFIX+authorization_id, json.dumps(witness, sort_keys=True), now))
            await self.browser.tasks.set_working_status(task_id=task["task_id"],
                status=BrowserTaskStatus.RESUME_AUTHORIZED, now_ms=now, connection=db)
            await db.commit()
        return await self.readback(execution.command_id, parameters)

    async def _validated(self, db, grant, *, now, require_verified):
        raw = await self._one(db, "SELECT value FROM runtime_meta WHERE key=?", (self.PREFIX+grant["authorization_id"],))
        if raw is None:
            raise ResumeError("browser_resume_sealed_witness_missing")
        witness = self._object(raw["value"])
        if (set(witness) != {"authorization_id", "execution_id", "command_id", "owner_device_id", "parameters", "scope", "expires_at_ms"}
            or not isinstance(witness["parameters"], dict) or not isinstance(witness["scope"], dict)
            or set(witness["parameters"]) != {"task_id", "escalation_id", "scope_sha256"}
            or type(witness["expires_at_ms"]) is not int
            or any(not isinstance(witness[key], str) or not witness[key] for key in
                   ("authorization_id", "execution_id", "command_id", "owner_device_id"))):
            raise ResumeError("browser_resume_record_invalid")
        task, scope = await self._scope(db, grant["task_id"], witness["owner_device_id"], now=now)
        source = await self._one(db, "SELECT value FROM runtime_meta WHERE key=?", (CommandAuthorityService.PREFIX+witness["command_id"],))
        seal = self._object(source["value"]) if source else {}
        if type(seal.get("expires_at_unix")) is not int or type(seal.get("issued_at_unix")) is not int:
            raise ResumeError("browser_resume_authority_stale")
        device = await self._one(db, "SELECT revoked_at_unix FROM devices WHERE device_id=?", (witness["owner_device_id"],))
        execution = await self._one(db, "SELECT status,command_id,action_id,parameters_digest FROM action_executions WHERE execution_id=?", (witness["execution_id"],))
        if (witness["authorization_id"] != grant["authorization_id"]
            or grant["authorization_id"] != "bresume_"+digest([witness["command_id"], witness["parameters"]])[:32]
            or witness["scope"] != scope or witness["parameters"]["scope_sha256"] != digest(scope)
            or witness["parameters"]["task_id"] != grant["task_id"]
            or witness["parameters"]["escalation_id"] != grant["escalation_id"]
            or grant["decision_id"] != scope["decision_id"]
            or json.loads(grant["approved_domains_json"]) != scope["approved_domains"]
            or grant["approved_action_class_ceiling"] != scope["approved_action_class_ceiling"]
            or grant["expires_at_ms"] != witness["expires_at_ms"] or now >= witness["expires_at_ms"]
            or witness["expires_at_ms"] != min(scope["escalation_expires_at_ms"], seal["expires_at_unix"]*1000, (seal["issued_at_unix"]+30)*1000)
            or seal.get("authority_source") != "OWNER_COMMAND" or seal.get("owner_approved") is not True
            or seal.get("principal_type") != "OWNER_DEVICE" or seal.get("device_id") != witness["owner_device_id"]
            or seal.get("effective_action_class") != "A4" or seal.get("typed_action_id") != ACTION.action_id
            or seal.get("typed_parameter_constraints") != witness["parameters"] or seal.get("no_stale_replay") is not True
            or seal.get("expires_at_unix") is None or now >= seal["expires_at_unix"]*1000
            or now >= (seal.get("issued_at_unix", 0)+30)*1000
            or device is None or device["revoked_at_unix"] is not None
            or execution is None or execution["command_id"] != witness["command_id"] or execution["action_id"] != ACTION.action_id
            or execution["parameters_digest"] != digest(witness["parameters"])
            or execution["status"] not in {"PREFLIGHT_PASSED", "EXECUTING", "SUBMITTED", "VERIFYING", "VERIFIED_SUCCESS"}
            or (require_verified and execution["status"] != "VERIFIED_SUCCESS")
            or task["status"] not in {"RESUME_AUTHORIZED", "RUNNING"}):
            raise ResumeError("browser_resume_authority_stale")
        return witness

    async def readback(self, command_id, parameters):
        authorization_id = "bresume_" + digest([command_id, parameters])[:32]
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            grant = await self._one(db, "SELECT * FROM browser_scope_authorizations WHERE authorization_id=?", (authorization_id,))
            if grant is None or grant["status"] != "ACTIVE":
                raise ResumeError("browser_resume_authorization_missing")
            await self._validated(db, grant, now=int(time.time()*1000), require_verified=False)
        return {**parameters, "authorization_id": authorization_id, "success": True,
            "status": "RESUME_AUTHORIZED", "evidence_pointer": "browser-resume://"+authorization_id}

    async def consume(self, task, *, requested_domains=None, requested_class=None):
        from fastapi import HTTPException
        now = int(time.time()*1000)
        try:
            async with self.store.connection() as db:
                await db.execute("BEGIN IMMEDIATE")
                grant = await self._one(db, "SELECT * FROM browser_scope_authorizations WHERE task_id=? AND status='ACTIVE' "
                    "ORDER BY issued_at_ms DESC LIMIT 1", (task.task_id,))
                if grant is None:
                    spent = await self._one(db, "SELECT 1 FROM browser_scope_authorizations WHERE task_id=? AND status='CONSUMED'", (task.task_id,))
                    if spent is not None and task.status is BrowserTaskStatus.RESUME_AUTHORIZED:
                        raise ResumeError("BROWSER_RESUME_OUTCOME_UNKNOWN_RECONCILE_EXISTING_TASK")
                    raise ResumeError("BROWSER_RESUME_AUTHORIZATION_MISSING")
                await self._validated(db, grant, now=now, require_verified=True)
                domains = json.loads(grant["approved_domains_json"])
                ceiling = ActionClass(grant["approved_action_class_ceiling"])
                if requested_domains is not None and not set(requested_domains).issubset(domains):
                    raise ResumeError("BROWSER_RESUME_SCOPE_EXCEEDS_APPROVAL")
                if requested_class is not None and int(requested_class.value[1:]) > int(ceiling.value[1:]):
                    raise ResumeError("BROWSER_RESUME_CLASS_EXCEEDS_APPROVAL")
                cur = await db.execute("UPDATE browser_scope_authorizations SET status='CONSUMED',consumed_at_ms=? "
                    "WHERE authorization_id=? AND status='ACTIVE' AND expires_at_ms>?", (now, grant["authorization_id"], now))
                if cur.rowcount != 1:
                    raise ResumeError("BROWSER_RESUME_AUTHORIZATION_MISSING")
                await db.commit()
            # Only this in-flight copy receives the newly admitted class. Original
            # task/decision records remain unchanged; a second run needs new authority.
            task.action_class = ceiling
            return {"authorization_id": grant["authorization_id"], "approved_domains": domains,
                "approved_action_class_ceiling": ceiling.value, "expires_at_ms": grant["expires_at_ms"]}
        except (ResumeError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
