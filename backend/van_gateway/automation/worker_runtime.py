"""Canonical per-run n8n callbacks. Workers supply data, never owner authority.

Every effect uses an admitted immutable IR step, a fresh canonical action and
snapshot, and its own signed single-use grant. Completed exact receipts are
replayable; an interrupted callback is never silently executed a second time.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import re
import socket
import sqlite3
import time
from typing import Any
from types import SimpleNamespace
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from van_gateway.action.models import ExecutionStatus
from van_gateway.action.service import ActionRuntime
from van_gateway.auth.control_scopes import ControlScope, require_scoped_internal
from van_gateway.attention.engine import AttentionEngine
from van_gateway.automation.canonical import canonical_json, digest
from van_gateway.automation.grants import CapabilityGrant, GrantDenied, RunGrantService
from van_gateway.automation.models import Primitive, WorkflowIR, WorkflowIRStep, WorkflowLifecycle, strongest_class
from van_gateway.automation.policy import AutomationPolicy, PolicyError, load_automation_policy
from van_gateway.automation.primitive_policy import SUPPORTED_OPERATIONS, assert_primitive_semantics
from van_gateway.automation.registry import AutomationRegistry
from van_gateway.automation.runtime_bindings import RuntimeBindingStore
from van_gateway.automation.source_credentials import SourceCredentialStore
from van_gateway.automation.dsl import DslError, bounded_json, evaluate, pure_result
from van_gateway.command.authority import CommandAuthorityError, CommandAuthorityService
from van_gateway.events.bus import EventBus
from van_gateway.models import AttentionSeverity, ReminderCreate
from van_gateway.reminders.service import ReminderService
from van_gateway.automation.mission_fence import require_automation_missions
from van_gateway.mission.control import MissionControlError
from van_gateway.automation.payments import assert_not_automated_payment, assert_no_instrument
from van_gateway.automation.input_bindings import ARTIFACT_PIN, workflow_inputs
from van_gateway.storage.db import Store

class WorkerDenied(ValueError):
    pass


class WorkerStepBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability_grant: str = Field(min_length=1, max_length=512, repr=False)
    grant: CapabilityGrant
    run_id: str = Field(min_length=1, max_length=160)
    step_id: str = Field(min_length=1, max_length=160)
    input: dict[str, Any] = Field(default_factory=dict)
    value: dict[str, Any] = Field(default_factory=dict)
    resolve_bindings: bool = False


class GatewayDocumentFetcher:
    """Bounded HTTPS GET with DNS pinning and the normal certificate verifier."""
    MAX_BYTES = 2 * 1024 * 1024

    def __init__(self, policy: AutomationPolicy, *, transport: httpx.AsyncBaseTransport | None = None,
                 resolver: Any = None, credentials: Any = None) -> None:
        self.policy, self.transport, self.resolver = policy, transport, resolver
        self.credentials = credentials

    async def fetch(self, url: str, *, timeout_ms: int, credential_alias: str | None = None) -> dict[str, Any]:
        # httpx's read timeout limits gaps between chunks, not the total stream.
        # Keep DNS, connect, headers, and every byte inside the sealed deadline.
        async with asyncio.timeout(min(timeout_ms, 30_000) / 1000):
            return await self._fetch(url, timeout_ms=timeout_ms, credential_alias=credential_alias)

    async def _fetch(self, url: str, *, timeout_ms: int, credential_alias: str | None = None,
                     method: str = "GET", body: Any = None, idempotency_key: str | None = None) -> dict[str, Any]:
        self.policy.domains.check_url(url)
        parsed = urlparse(url)
        if not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None, 443):
            raise WorkerDenied("WORKER_SOURCE_URL_INVALID")
        source_headers: dict[str, str] = {}
        if credential_alias:
            if self.credentials is None:
                raise WorkerDenied("WORKER_SOURCE_CREDENTIAL_ADAPTER_UNAVAILABLE")
            source_headers = await self.credentials.headers(credential_alias, url) if method == "GET" else await self.credentials.headers(credential_alias, url, method=method)
            if not source_headers or any(name.lower() not in {"authorization", "x-api-key"} for name in source_headers):
                raise WorkerDenied("WORKER_SOURCE_CREDENTIAL_HEADERS_INVALID")
        if self.resolver is not None:
            addresses = await self.resolver(parsed.hostname)
        else:
            rows = await asyncio.wait_for(
                asyncio.to_thread(socket.getaddrinfo, parsed.hostname, 443, type=socket.SOCK_STREAM),
                timeout=min(timeout_ms / 1000, 10),
            )
            addresses = [row[4][0] for row in rows]
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise WorkerDenied("WORKER_SOURCE_ADDRESS_DENIED")
        # Connect to the verified address itself, preserving Host and TLS SNI. A
        # second DNS lookup cannot redirect this request into the private network.
        target = httpx.URL(url).copy_with(host=addresses[0])
        async with httpx.AsyncClient(transport=self.transport, trust_env=False,
                                     follow_redirects=False, timeout=min(timeout_ms / 1000, 30)) as client:
            headers = {"Host": parsed.hostname, "Accept": "application/json,text/plain", **source_headers}
            if idempotency_key:
                headers["Idempotency-Key"] = idempotency_key
            request = client.build_request(method, target, headers=headers, **({"json": body} if method in {"POST", "PUT", "PATCH"} else {}))
            request.extensions["sni_hostname"] = parsed.hostname
            response = await client.send(request, stream=True)
            try:
                if (method == "GET" and response.status_code != 200) or (method != "GET" and not 200 <= response.status_code < 300):
                    raise WorkerDenied("WORKER_SOURCE_HTTP_FAILED")
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > self.MAX_BYTES:
                        raise WorkerDenied("WORKER_SOURCE_TOO_LARGE")
                    chunks.append(chunk)
                raw = b"".join(chunks)
                text = raw.decode("utf-8")
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = {"text": text}
                protected = set(source_headers.values())
                for value in source_headers.values():
                    for prefix in ("Bearer ", "Token "):
                        if value.startswith(prefix):
                            protected.add(value[len(prefix):])
                # Check decoded JSON too: escaping a quote or Unicode character
                # must not carry an admitted source secret into the callback.
                pending = [payload, text]
                while pending:
                    item = pending.pop()
                    if isinstance(item, dict):
                        pending.extend(item.keys())
                        pending.extend(item.values())
                    elif isinstance(item, list):
                        pending.extend(item)
                    elif isinstance(item, str) and any(secret and secret in item for secret in protected):
                        raise WorkerDenied("WORKER_SOURCE_RESPONSE_CONTAINS_CREDENTIAL")
                return {"payload": payload, "body_sha256": hashlib.sha256(raw).hexdigest(),
                        "source_url": url, "source_trust": "UNTRUSTED_EXTERNAL",
                        **({"http_status": response.status_code} if method != "GET" else {})}
            finally:
                await response.aclose()

    async def write(self, url: str, *, method: str, body: Any, timeout_ms: int,
                    credential_alias: str, idempotency_key: str) -> dict:
        if method not in {"POST", "PUT", "PATCH", "DELETE"} or not credential_alias:
            raise WorkerDenied("WORKER_WRITE_METHOD_DENIED")
        bounded_json(body)
        # One attempt only, with the same DNS pinning, trust and response bounds
        # as reads. A provider timeout leaves the durable callback uncertain.
        async with asyncio.timeout(min(timeout_ms, 30_000) / 1000):
            response = await self._fetch(url, timeout_ms=timeout_ms, credential_alias=credential_alias,
                                         method=method, body=body, idempotency_key=idempotency_key)
        return {"http_status": response["http_status"], "response_sha256": response["body_sha256"]}


class AutomationWorkerRuntime:
    MAX_INPUT_BYTES = 4 * 1024 * 1024
    MAX_FILE_BYTES = 2 * 1024 * 1024

    def __init__(self, store: Store, *, grants: RunGrantService, actions: ActionRuntime,
                 authority: CommandAuthorityService, registry: AutomationRegistry,
                 enabled: bool, policy: AutomationPolicy | None = None,
                 fetcher: GatewayDocumentFetcher | None = None, settings: Any = None) -> None:
        self.store, self.grants, self.actions = store, grants, actions
        self.authority, self.registry, self.enabled = authority, registry, enabled
        self.policy = policy or load_automation_policy()
        self.bindings = RuntimeBindingStore(store)
        self.fetcher = fetcher or GatewayDocumentFetcher(
            self.policy, credentials=SourceCredentialStore(
                getattr(settings, "automation_source_credentials_file", "") if settings else "",
            ),
        )
        self.router = APIRouter(prefix="/v1/automation/worker", tags=["automation-worker"])

        @self.router.post("/step")
        async def step(body: WorkerStepBody, request: Request,
                       x_van_internal_token: str | None = Header(default=None)):
            if settings is None:
                raise HTTPException(status_code=503, detail="WORKER_MACHINE_INGRESS_UNCONFIGURED")
            require_scoped_internal(settings, x_van_internal_token, ControlScope.AUTOMATION_WORKER)
            endpoint = urlparse(getattr(settings, "automation_worker_endpoint", ""))
            if endpoint.scheme != "https" or not endpoint.hostname:
                raise HTTPException(status_code=503, detail="WORKER_MACHINE_INGRESS_UNCONFIGURED")
            if request.url.scheme != "https" or request.url.hostname != endpoint.hostname:
                raise HTTPException(status_code=403, detail="WORKER_MACHINE_INGRESS_MISMATCH")
            try:
                return await self.execute(body)
            except (WorkerDenied, GrantDenied, CommandAuthorityError, PolicyError) as exc:
                raise HTTPException(status_code=403, detail={"error": str(exc)}) from exc
            except (httpx.HTTPError, TimeoutError, OSError, UnicodeError) as exc:
                raise HTTPException(status_code=502, detail={"error": "WORKER_SOURCE_UNAVAILABLE"}) from exc
            except (ValueError, TypeError, KeyError) as exc:
                raise HTTPException(status_code=403, detail={"error": "WORKER_INPUT_INVALID"}) from exc

    async def ensure(self) -> None:
        await self.store.execute("""CREATE TABLE IF NOT EXISTS automation_worker_steps(
            run_id TEXT NOT NULL REFERENCES automation_runs(run_id), step_id TEXT NOT NULL,
            request_digest TEXT NOT NULL, state TEXT NOT NULL, result_json TEXT,
            result_digest TEXT, created_at_ms INTEGER NOT NULL, completed_at_ms INTEGER,
            PRIMARY KEY(run_id,step_id))""")
        await self.store.execute("""CREATE TABLE IF NOT EXISTS automation_worker_dedupe(
            artifact_id TEXT NOT NULL, step_id TEXT NOT NULL, content_digest TEXT NOT NULL,
            updated_at_ms INTEGER NOT NULL, generation INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(artifact_id,step_id))""")
        await self.store.execute("""CREATE TABLE IF NOT EXISTS automation_worker_files(
            file_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES automation_runs(run_id),
            content BLOB, content_sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
            filename TEXT NOT NULL, state TEXT NOT NULL, created_at_ms INTEGER NOT NULL, deleted_at_ms INTEGER)""")
        await self.store.execute("""CREATE TABLE IF NOT EXISTS automation_worker_evidence(
            evidence_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES automation_runs(run_id),
            step_id TEXT NOT NULL, payload_json TEXT NOT NULL, content_digest TEXT NOT NULL,
            snapshot_id TEXT NOT NULL, source_trust TEXT NOT NULL, created_at_ms INTEGER NOT NULL)""")

    async def execute(self, body: WorkerStepBody) -> dict[str, Any]:
        if not self.enabled:
            raise WorkerDenied("AUTOMATION_FABRIC_DISABLED")
        if len(canonical_json({"input": body.input, "value": body.value})) > self.MAX_INPUT_BYTES:
            raise WorkerDenied("WORKER_INPUT_TOO_LARGE")
        if body.run_id != body.grant.run_id:
            raise WorkerDenied("WORKER_RUN_MISMATCH")
        await self.ensure()
        ir, run, authority = await self._context(body)
        step = None if body.step_id == "__admit__" else next((s for s in ir.steps if s.step_id == body.step_id), None)
        if body.step_id != "__admit__" and step is None:
            raise WorkerDenied("WORKER_STEP_UNKNOWN")
        if step and step.operation not in SUPPORTED_OPERATIONS.get(step.primitive, frozenset()):
            raise WorkerDenied("WORKER_OPERATION_UNSUPPORTED")
        if step:
            assert_primitive_semantics(step)
        operation = "admit_run" if step is None else f"step:{step.step_id}"
        requested_class = body.grant.action_class_ceiling if step is None else step.action_class
        requested_domain = step.external_domain if step and step.primitive in (Primitive.HTTP_GET, Primitive.HTTP_REQUEST) else None
        if body.grant.allowed_gateway_operations != [operation] or body.grant.max_uses != 1:
            raise WorkerDenied("WORKER_GRANT_NOT_STEP_SCOPED")
        await self.grants.validate(token=body.capability_grant, grant=body.grant,
                                   requested_operation=operation, requested_action_class=requested_class,
                                   requested_domain=requested_domain)
        if step is None:
            if body.value:
                raise WorkerDenied("WORKER_ADMISSION_VALUE_INVALID")
            selected, branch_proof = True, None
        else:
            admitted = await self.store.fetchone(
                "SELECT state FROM automation_worker_steps WHERE run_id=? AND step_id='__admit__'", (body.run_id,))
            if admitted is None or admitted["state"] != "COMPLETED":
                raise WorkerDenied("WORKER_RUN_NOT_ADMITTED")
            selected, branch_proof = await self._selection(ir, body.run_id, step.step_id)
            expected = await self._resolve(step.input_bindings, body, ir, step.step_id) if selected else {}
            if body.resolve_bindings:
                if body.value:
                    raise WorkerDenied("WORKER_SERVER_BINDING_VALUE_INVALID")
            elif digest(expected) != digest(body.value):
                raise WorkerDenied("WORKER_BINDING_MISMATCH")
        request_digest = digest({"grant_id": body.grant.grant_id, "input": body.input, "value": body.value,
                                 "resolve_bindings": body.resolve_bindings})
        existing = await self.store.fetchone("SELECT * FROM automation_worker_steps WHERE run_id=? AND step_id=?",
                                             (body.run_id, body.step_id))
        if existing:
            if existing["request_digest"] != request_digest:
                raise WorkerDenied("WORKER_STEP_REPLAY_CONFLICT")
            if existing["state"] not in {"COMPLETED", "SKIPPED"}:
                raise WorkerDenied("WORKER_STEP_RESULT_PENDING")
            result = json.loads(existing["result_json"])
            if digest(result) != existing["result_digest"]:
                raise WorkerDenied("WORKER_RECEIPT_DIGEST_MISMATCH")
            return self._receipt(body, result, existing["result_digest"], True, existing["state"])
        await self.grants.redeem(token=body.capability_grant, grant=body.grant,
                                 requested_operation=operation, requested_action_class=requested_class,
                                 requested_domain=requested_domain)
        now = int(time.time() * 1000)
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                await require_automation_missions(self.store, command_id=authority.command_id,
                    source_command_id=authority.source_command_id, db=db)
            except MissionControlError as exc:
                await db.rollback()
                raise WorkerDenied(exc.reason) from exc
            cur = await db.execute("INSERT OR IGNORE INTO automation_worker_steps VALUES(?,?,?,'IN_PROGRESS',NULL,NULL,?,NULL)",
                                   (body.run_id, body.step_id, request_digest, now))
            await db.commit()
            if cur.rowcount != 1:
                raise WorkerDenied("WORKER_STEP_RESULT_PENDING")
        # Re-read authority after nonce consumption, immediately before work.
        await self._context(body)
        if step and not selected:
            result = {"skipped": True, "reason": "BRANCH_NOT_SELECTED", "branch_proof": branch_proof}
            await self._complete(body, ir, result, digest(result), state="SKIPPED")
            return self._receipt(body, result, digest(result), False, "SKIPPED")
        if step:
            body = body.model_copy(update={"value": expected})
            if step.precondition is not None and not evaluate(step.precondition, expected):
                await self._settle(body, "REFUSED", {"reason": "PRECONDITION_FALSE", "predicate_digest": digest(step.precondition),
                                                     "value_digest": digest(expected), "branch_proof": branch_proof})
                raise WorkerDenied("WORKER_PRECONDITION_FALSE")
        if step is None:
            result = {"admitted": True}
        else:
            async with asyncio.timeout(step.timeout_ms / 1000):
                result = await self._produce(body, step, run, authority)
        result_digest = digest(result)
        await self._complete(body, ir, result, result_digest)
        return self._receipt(body, result, result_digest, False)

    async def cleanup_transient_bytes(self, *, now_ms: int | None = None, retention_ms: int = 86_400_000) -> int:
        """Retire bytes after authority expiry, retaining immutable effect receipts.

        A stalled run whose grants have expired cannot retain a transient document
        forever. Receipt hashes, file metadata and consumed step/nonce records are
        preserved, so cleanup never creates permission to repeat an old effect.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        cutoff = now - max(60_000, retention_ms)
        async with self.store.connection() as db:
            cur = await db.execute("""UPDATE automation_worker_files SET content=NULL,state='RETIRED',deleted_at_ms=?
                WHERE state='STORED' AND created_at_ms<?
                  AND EXISTS(SELECT 1 FROM automation_run_nonces n WHERE n.run_id=automation_worker_files.run_id)
                  AND NOT EXISTS(SELECT 1 FROM automation_run_nonces n WHERE n.run_id=automation_worker_files.run_id
                                 AND n.expires_at_ms>? AND n.revoked_at_ms IS NULL)""", (now, cutoff, now))
            await db.commit()
            return max(0, cur.rowcount)

    @staticmethod
    def _receipt(body: WorkerStepBody, result: dict[str, Any], result_digest: str, replayed: bool, state: str = "COMPLETED") -> dict[str, Any]:
        return {"run_id": body.run_id, "step_id": body.step_id, "status": state, "result": result,
                "result_digest": result_digest, "replayed": replayed,
                **({"admitted": True} if body.step_id == "__admit__" else {})}

    async def _settle(self, body: WorkerStepBody, state: str, result: dict) -> None:
        await self.store.execute("UPDATE automation_worker_steps SET state=?,result_json=?,result_digest=?,completed_at_ms=? WHERE run_id=? AND step_id=? AND state='IN_PROGRESS'",
                                 (state, Store.dumps(result), digest(result), int(time.time() * 1000), body.run_id, body.step_id))

    async def _selection(self, ir: WorkflowIR, run_id: str, step_id: str) -> tuple[bool, list[dict]]:
        edges = sorted((edge for edge in ir.edges if edge.to_step == step_id), key=lambda edge: (edge.from_step, edge.branch or ""))
        proof, active = [], not edges
        for edge in edges:
            source = next(step for step in ir.steps if step.step_id == edge.from_step)
            if source.primitive in {Primitive.SCHEDULE_TRIGGER, Primitive.EVENT_TRIGGER, Primitive.WEBHOOK_TRIGGER}:
                state, result_digest, result = "COMPLETED", None, {}
            else:
                row = await self.store.fetchone("SELECT state,result_json,result_digest FROM automation_worker_steps WHERE run_id=? AND step_id=?", (run_id, source.step_id))
                if row is None or row["state"] not in {"COMPLETED", "SKIPPED"}:
                    raise WorkerDenied("WORKER_BRANCH_PARENT_UNSETTLED")
                state, result_digest = row["state"], row["result_digest"]
                result = json.loads(row["result_json"])
                if digest(result) != result_digest:
                    raise WorkerDenied("WORKER_RECEIPT_DIGEST_MISMATCH")
            edge_active = state == "COMPLETED" and (edge.branch is None or result.get("selected_branch") == edge.branch)
            proof.append({"from_step": source.step_id, "branch": edge.branch, "state": state,
                          "result_digest": result_digest, "selected": edge_active})
            active = active or edge_active
        return active, proof

    @staticmethod
    def _ancestors(ir: WorkflowIR, current_step: str) -> set[str]:
        ancestors, pending = set(), [current_step]
        while pending:
            target = pending.pop()
            for edge in ir.edges:
                if edge.to_step == target and edge.from_step not in ancestors:
                    ancestors.add(edge.from_step)
                    pending.append(edge.from_step)
        return ancestors

    async def _complete(self, body: WorkerStepBody, ir: WorkflowIR, result: dict[str, Any], result_digest: str,
                        *, state: str = "COMPLETED") -> None:
        """Atomically record completion and any independently durable deliveries.

        A staged source change survives an abandoned run. A later run receives the
        same delivery identity until all required downstream notification/evidence
        targets exist. Consumed uncertain callbacks themselves are never repeated.
        """
        rows = await self.store.fetchall("SELECT * FROM automation_worker_steps WHERE run_id=? AND state='COMPLETED'", (body.run_id,))
        skip_rows = {row["step_id"]: row for row in await self.store.fetchall(
            "SELECT * FROM automation_worker_steps WHERE run_id=? AND state='SKIPPED'", (body.run_id,))}
        records = {row["step_id"]: json.loads(row["result_json"]) for row in rows
                   if digest(json.loads(row["result_json"])) == row["result_digest"]}
        if state == "COMPLETED":
            records[body.step_id] = result
        else:
            skip_rows[body.step_id] = {"result_json": Store.dumps(result), "result_digest": result_digest}
        checkpoints = []
        observer = WorkerWorkflowObserver(self)
        for source in ir.steps:
            observed = records.get(source.step_id)
            if source.operation not in {"change_detect", "dedupe", "validate_and_dedupe"} or not observed or observed.get("changed") is not True:
                continue
            sinks = [step for step in ir.steps if step.mutates
                     and source.step_id in self._ancestors(ir, step.step_id)]
            ready = True
            for sink in sinks:
                delivered = records.get(sink.step_id)
                if delivered is None:
                    skipped = skip_rows.get(sink.step_id)
                    if skipped:
                        selected, proof = await self._selection(ir, body.run_id, sink.step_id)
                        receipt = json.loads(skipped["result_json"])
                        if not selected and digest(receipt) == skipped["result_digest"] and receipt == {
                            "skipped": True, "reason": "BRANCH_NOT_SELECTED", "branch_proof": proof}:
                            continue
                    ready = False
                    break
                value = await self._resolve(sink.input_bindings, body, ir, sink.step_id)
                if not await observer._effect_matches(sink, value, delivered, body.run_id):
                    ready = False
                    break
            if ready:
                checkpoints.append((source.step_id, observed))
        now = int(time.time() * 1000)
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute("UPDATE automation_worker_steps SET state=?,result_json=?,result_digest=?,completed_at_ms=? WHERE run_id=? AND step_id=? AND state='IN_PROGRESS'",
                             (state, Store.dumps(result), result_digest, now, body.run_id, body.step_id))
            for step_id, observed in checkpoints:
                cur = await db.execute("SELECT content_digest,generation FROM automation_worker_dedupe WHERE artifact_id=? AND step_id=?",
                                       (body.grant.artifact_id, step_id))
                baseline = await cur.fetchone()
                actual = (baseline["generation"], baseline["content_digest"]) if baseline else (0, None)
                if actual == (observed["baseline_generation"], observed["previous_digest"]):
                    await db.execute("INSERT INTO automation_worker_dedupe(artifact_id,step_id,content_digest,updated_at_ms,generation) VALUES(?,?,?,?,?) "
                                     "ON CONFLICT(artifact_id,step_id) DO UPDATE SET content_digest=excluded.content_digest,updated_at_ms=excluded.updated_at_ms,generation=excluded.generation",
                                     (body.grant.artifact_id, step_id, observed["digest"], now, actual[0] + 1))
            await db.commit()

    async def _event_identity(self, body: Any, step: WorkflowIRStep, device_id: str) -> str:
        binding = await self.bindings.get(body.grant.artifact_id)
        if binding is None:
            raise WorkerDenied("WORKER_ARTIFACT_NOT_ADMITTED")
        ir = WorkflowIR.model_validate(binding["ir"])
        ancestors = self._ancestors(ir, step.step_id)
        deliveries = []
        for source in ir.steps:
            if source.step_id in ancestors and source.operation in {"change_detect", "dedupe", "validate_and_dedupe"}:
                row = await self.store.fetchone("SELECT result_json,result_digest FROM automation_worker_steps WHERE run_id=? AND step_id=? AND state='COMPLETED'",
                                               (body.run_id, source.step_id))
                if row is None:
                    raise WorkerDenied("WORKER_BINDING_SOURCE_UNOBSERVED")
                observed = json.loads(row["result_json"])
                if digest(observed) != row["result_digest"] or not isinstance(observed.get("delivery_key"), str):
                    raise WorkerDenied("WORKER_DELIVERY_RECEIPT_INVALID")
                deliveries.append({"step_id": source.step_id, "key": observed["delivery_key"]})
        identity = {"artifact": body.grant.artifact_id, "step": step.step_id, "device": device_id,
                    "deliveries": deliveries, "value": body.value} if deliveries else {"run": body.run_id, "step": step.step_id}
        return "automation_worker_" + digest(identity)

    async def _context(self, body: WorkerStepBody):
        grant = body.grant
        run = await self.store.fetchone("SELECT * FROM automation_runs WHERE run_id=?", (body.run_id,))
        if run is None or run["status"] not in ("PENDING", "DISPATCHED"):
            raise WorkerDenied("WORKER_RUN_NOT_ACTIVE")
        if (run["command_id"], run["capability_id"], run["artifact_id"], run["input_digest"]) != (
            grant.command_id, grant.capability_id, grant.artifact_id, grant.input_digest,
        ) or digest(body.input) != grant.input_digest:
            raise WorkerDenied("WORKER_RUN_BINDING_MISMATCH")
        artifact = await self.registry.get_artifact(grant.artifact_id)
        capability = await self.registry.get_capability(grant.capability_id)
        binding = await self.bindings.get(grant.artifact_id)
        if (artifact is None or capability is None or artifact.capability_id != capability.capability_id
                or capability.lifecycle_state not in (WorkflowLifecycle.ADMITTED, WorkflowLifecycle.HOT)
                or artifact.version != grant.artifact_version or artifact.lifecycle_state not in (WorkflowLifecycle.ADMITTED, WorkflowLifecycle.HOT)
                or binding is None or binding["binding_state"] != "DEPLOYED" or binding["readiness_errors"]
                or binding["n8n_workflow_id"] != artifact.n8n_workflow_id):
            raise WorkerDenied("WORKER_ARTIFACT_NOT_ADMITTED")
        ir = WorkflowIR.model_validate(binding["ir"])
        if (digest(ir.semantic_payload()) != artifact.workflow_ir_digest
                or ir.action_class != capability.action_class or run["action_class"] != capability.action_class.value
                or strongest_class(ir.steps) != ir.action_class
                or digest(binding["semantic_graph"]) != artifact.compiled_semantic_digest
                or binding["semantic_digest"] != artifact.compiled_semantic_digest
                or not binding["runtime_graph"]
                or self.bindings.dependency_ids(binding["runtime_graph"]) != set(binding["dependencies"])
                or self.bindings.compute_full_digest(binding["runtime_graph"], binding["dependencies"]) != binding["full_digest"]
                or binding["full_digest"] != artifact.compiled_full_digest):
            raise WorkerDenied("WORKER_ARTIFACT_DIGEST_MISMATCH")
        execution = await self.actions.get_execution(run["execution_id"])
        if execution is None or execution.status is not ExecutionStatus.EXECUTING:
            raise WorkerDenied("WORKER_ACTION_NOT_EXECUTING")
        if (execution.command_id != grant.command_id or execution.snapshot_id != grant.context_snapshot_id
                or execution.parameters_digest != self.actions.digest_parameters(body.input)):
            raise WorkerDenied("WORKER_ACTION_BINDING_MISMATCH")
        definition = await self.actions.get_definition(execution.action_id)
        if definition is None or not definition.enabled:
            raise WorkerDenied("WORKER_ACTION_DISABLED")
        if definition.action_class != capability.action_class or execution.principal_type not in definition.allowed_principals:
            raise WorkerDenied("WORKER_ACTION_CLASS_OR_PRINCIPAL_MISMATCH")
        authority, _ = await self.authority.authorize_action(
            command_id=grant.command_id, action=definition, principal_type=execution.principal_type,
            requested_by=execution.requested_by, snapshot_id=execution.snapshot_id,
            turn_id=execution.turn_id, parameters=body.input,
        )
        if (execution.principal_type.value not in capability.allowed_principals
                or authority.origin_channel.value not in capability.allowed_origin_channels):
            raise WorkerDenied("WORKER_CAPABILITY_SOURCE_NOT_ALLOWED")
        snapshot = await self.store.fetchone("SELECT * FROM context_snapshots WHERE snapshot_id=?", (grant.context_snapshot_id,))
        if snapshot is None or snapshot["command_id"] != grant.command_id or snapshot["digest"] != authority.context_digest:
            raise WorkerDenied("WORKER_SNAPSHOT_MISMATCH")
        if grant.standing_authority_id != authority.source_authority_id:
            raise WorkerDenied("WORKER_STANDING_AUTHORITY_MISMATCH")
        if (authority.principal_type.value == "OWNER_DEVICE"
                and authority.typed_action_id == f"automation.workflow.{grant.capability_id}"
                and body.input.get(ARTIFACT_PIN) != grant.artifact_id):
            raise WorkerDenied("WORKER_OWNER_ARTIFACT_PIN_MISMATCH")
        return ir, run, authority

    async def _resolve(self, value: Any, body: WorkerStepBody, ir: WorkflowIR, current_step: str) -> Any:
        if isinstance(value, dict):
            if value.get("kind") == "LITERAL" and set(value) == {"kind", "value"}:
                bounded_json(value["value"])
                return value
            if value.get("kind") == "STEP_RESULT":
                if set(value) != {"kind", "step_id", "path", "optional"} or type(value["optional"]) is not bool or not isinstance(value["path"], str):
                    raise WorkerDenied("WORKER_OPTIONAL_BINDING_INVALID")
                if value["step_id"] not in self._ancestors(ir, current_step):
                    raise WorkerDenied("WORKER_BINDING_SOURCE_NOT_ANCESTOR")
                row = await self.store.fetchone("SELECT * FROM automation_worker_steps WHERE run_id=? AND step_id=?", (body.run_id, value["step_id"]))
                if row is not None and row["state"] == "SKIPPED" and value["optional"]:
                    if digest(json.loads(row["result_json"])) != row["result_digest"]:
                        raise WorkerDenied("WORKER_RECEIPT_DIGEST_MISMATCH")
                    return None
                return await self._resolve("$steps." + value["step_id"] + ("." + value["path"] if value["path"] else ""), body, ir, current_step)
            return {k: await self._resolve(v, body, ir, current_step) for k, v in value.items()}
        if isinstance(value, list):
            return [await self._resolve(v, body, ir, current_step) for v in value]
        if not isinstance(value, str) or not (value.startswith("$") or value.startswith("{{")):
            return value
        reference = value[1:] if value.startswith("$") else value[2:-2].strip() if value.endswith("}}") else ""
        path = reference.split(".")
        if any(re.fullmatch(r"[A-Za-z0-9_-]+", part) is None for part in path):
            raise WorkerDenied("WORKER_BINDING_EXPRESSION_UNSUPPORTED")
        if path[0] == "input":
            result, parts = workflow_inputs(body.input), path[1:]
        else:
            source_id = path[1] if path[0] == "steps" and len(path) > 1 else next(
                (s.step_id for s in ir.steps if s.output_name == path[0]), "")
            ancestors = self._ancestors(ir, current_step)
            if source_id not in ancestors:
                raise WorkerDenied("WORKER_BINDING_SOURCE_NOT_ANCESTOR")
            row = await self.store.fetchone("SELECT result_json,result_digest FROM automation_worker_steps WHERE run_id=? AND step_id=? AND state='COMPLETED'",
                                           (body.run_id, source_id))
            if row is None:
                source = next((s for s in ir.steps if s.step_id == source_id), None)
                if source is not None and source.primitive in (Primitive.WEBHOOK_TRIGGER, Primitive.SCHEDULE_TRIGGER, Primitive.EVENT_TRIGGER):
                    result = body.input
                else:
                    raise WorkerDenied("WORKER_BINDING_SOURCE_UNOBSERVED")
            else:
                result = json.loads(row["result_json"])
                if digest(result) != row["result_digest"]:
                    raise WorkerDenied("WORKER_RECEIPT_DIGEST_MISMATCH")
            parts = path[2:] if path[0] == "steps" else path[1:]
        for part in parts:
            if not isinstance(result, dict) or part not in result:
                raise WorkerDenied("WORKER_BINDING_PATH_MISSING")
            result = result[part]
        return result

    async def _produce(self, body: WorkerStepBody, step: WorkflowIRStep, run: Any, authority: Any) -> dict[str, Any]:
        value, now = body.value, int(time.time() * 1000)
        pure = pure_result(step.primitive.value, step.operation, value)
        if pure is not None:
            return pure
        if step.primitive is Primitive.WAIT:
            await asyncio.sleep(value["delay_ms"] / 1000)
            return {"waited_ms": value["delay_ms"]}
        if step.primitive is Primitive.VAN_CAPABILITY:
            if step.operation != "reminder.create" or set(value) - {"text", "due_at_unix", "project_id"} or not {"text", "due_at_unix"} <= set(value):
                raise WorkerDenied("WORKER_NATIVE_CAPABILITY_INPUT_INVALID")
            if (not isinstance(value["text"], str) or not 1 <= len(value["text"]) <= 2000
                    or type(value["due_at_unix"]) is not int or not 0 < value["due_at_unix"] < 2**63
                    or ("project_id" in value and value["project_id"] is not None
                        and (not isinstance(value["project_id"], str) or not 1 <= len(value["project_id"]) <= 160))):
                raise WorkerDenied("WORKER_NATIVE_CAPABILITY_INPUT_INVALID")
            key = "automation-reminder:" + digest({"run": body.run_id, "step": step.step_id, "command": body.grant.command_id})
            reminder = await ReminderService(self.store).create(ReminderCreate(**value, idempotency_key=key, source="automation-worker"))
            observed = await ReminderService(self.store).get_by_idempotency_key(key)
            if observed is None or observed["text"] != value["text"] or observed["due_at_unix"] != value["due_at_unix"] or observed["project_id"] != value.get("project_id") or observed["status"] != "OPEN":
                raise WorkerDenied("WORKER_NATIVE_CAPABILITY_READBACK_MISMATCH")
            return {"capability": "reminder.create", "reminder_id": reminder["id"], "verified": True,
                    "evidence_pointer": "reminder://" + reminder["id"], "target_digest": digest(observed)}
        if step.primitive in (Primitive.HTTP_GET, Primitive.HTTP_REQUEST):
            if step.operation in {"write_json", "delete_resource"}:
                readback = value["readback"]
                assert_not_automated_payment(operation=step.operation, url=str(value["url"]), domain=step.external_domain or "", effects=list(step.effects), context="resolved_external_write")
                assert_no_instrument(value, context="resolved_external_write")
                if any(not isinstance(url, str) or urlparse(url).hostname != step.external_domain for url in (value["url"], readback["url"])):
                    raise WorkerDenied("WORKER_SOURCE_DOMAIN_MISMATCH")
                key = "van-automation-" + digest({"run": body.run_id, "step": step.step_id, "input": body.grant.input_digest})
                response = await self.fetcher.write(value["url"], method=value["method"], body=value.get("body"),
                    timeout_ms=step.timeout_ms, credential_alias=step.credential_alias, idempotency_key=key)
                observed = await self.fetcher.fetch(readback["url"], timeout_ms=step.timeout_ms, credential_alias=step.credential_alias)
                if not evaluate(readback["predicate"], {"payload": observed["payload"]}):
                    raise WorkerDenied("WORKER_EXTERNAL_WRITE_READBACK_MISMATCH")
                return {"verified": True, "method": value["method"], "request_digest": digest(value),
                        "readback_digest": digest(observed), "provider_correctness_verified": False,
                        "source_trust": "UNTRUSTED_EXTERNAL", **response}
            if set(value) - {"url", "method"} or value.get("method", "GET") != "GET" or not isinstance(value.get("url"), str):
                raise WorkerDenied("WORKER_SOURCE_REQUEST_UNSUPPORTED")
            if urlparse(value["url"]).hostname != step.external_domain:
                raise WorkerDenied("WORKER_SOURCE_DOMAIN_MISMATCH")
            return await self.fetcher.fetch(value["url"], timeout_ms=step.timeout_ms, credential_alias=step.credential_alias)
        if step.primitive is Primitive.HASH:
            if set(value) != {"payload"}:
                raise WorkerDenied("WORKER_HASH_INPUT_INVALID")
            return {"primary": digest(value["payload"]), "algorithm": "sha256"}
        if step.primitive in (Primitive.DEDUPE, Primitive.FILTER):
            if set(value) != {"payload"} or (step.primitive is Primitive.FILTER and not isinstance(value["payload"], dict)):
                raise WorkerDenied("WORKER_DEDUPE_INPUT_INVALID")
            current = digest(value["payload"])
            async with self.store.connection() as db:
                await db.execute("BEGIN IMMEDIATE")
                cur = await db.execute("SELECT content_digest,generation FROM automation_worker_dedupe WHERE artifact_id=? AND step_id=?",
                                       (run["artifact_id"], step.step_id))
                previous = await cur.fetchone()
                changed = previous is None or previous["content_digest"] != current
                await db.commit()
            # This is an observation, not delivery. Only a durable downstream
            # notification/evidence checkpoint advances the delivered baseline.
            generation = previous["generation"] if previous else 0
            previous_digest = previous["content_digest"] if previous else None
            return {"changed": changed, "accepted": changed, "digest": current, "dedupe_key": current,
                    "baseline_generation": generation, "previous_digest": previous_digest,
                    "delivery_key": digest({"artifact": run["artifact_id"], "step": step.step_id,
                        "generation": generation, "previous": previous_digest, "current": current}),
                    "payload": value["payload"], "source_trust": "UNTRUSTED_EXTERNAL"}
        if step.primitive is Primitive.MAP_FIELDS:
            if set(value) != {"payload"}:
                raise WorkerDenied("WORKER_MAP_TRANSFORM_UNSUPPORTED")
            return {"payload": value["payload"], "source_trust": "UNTRUSTED_EXTERNAL"}
        if step.primitive is Primitive.VAN_EVIDENCE:
            if set(value) - {"payload", "digests"} or "payload" not in value:
                raise WorkerDenied("WORKER_EVIDENCE_INPUT_INVALID")
            actual = digest(value["payload"])
            if "digests" in value and value["digests"] != {"primary": actual, "algorithm": "sha256"}:
                raise WorkerDenied("WORKER_EVIDENCE_DIGEST_MISMATCH")
            evidence_id = hashlib.sha256(f"{body.run_id}|{step.step_id}|{actual}".encode()).hexdigest()
            await self.store.execute("INSERT INTO automation_worker_evidence VALUES(?,?,?,?,?,?,?,?)",
                                     (evidence_id, body.run_id, step.step_id, Store.dumps(value["payload"]), actual,
                                      body.grant.context_snapshot_id, "UNTRUSTED_EXTERNAL", now))
            return {"evidence_pointer": f"automation-evidence://{evidence_id}", "content_digest": actual,
                    "source_trust": "UNTRUSTED_EXTERNAL", "provider_correctness_verified": False}
        if step.primitive is Primitive.VAN_EVENT:
            return await self._emit(body, step, authority)
        if step.primitive is Primitive.STORE_TRANSIENT_FILE:
            if set(value) - {"content_base64", "filename"} or not isinstance(value.get("content_base64"), str):
                raise WorkerDenied("WORKER_FILE_INPUT_INVALID")
            try:
                content = base64.b64decode(value["content_base64"], validate=True)
            except ValueError as exc:
                raise WorkerDenied("WORKER_FILE_INPUT_INVALID") from exc
            filename = value.get("filename", "document")
            if not isinstance(filename, str) or len(filename) > 200 or "/" in filename or "\\" in filename or not filename:
                raise WorkerDenied("WORKER_FILE_NAME_INVALID")
            if len(content) > self.MAX_FILE_BYTES:
                raise WorkerDenied("WORKER_FILE_TOO_LARGE")
            content_hash = hashlib.sha256(content).hexdigest()
            file_id = hashlib.sha256(f"{body.run_id}|{step.step_id}|{content_hash}".encode()).hexdigest()
            await self.store.execute("INSERT INTO automation_worker_files VALUES(?,?,?,?,?,?,'STORED',?,NULL)",
                                     (file_id, body.run_id, content, content_hash, len(content), filename, now))
            return {"file_id": file_id, "sha256": content_hash, "size_bytes": len(content)}
        if step.primitive is Primitive.DELETE_TRANSIENT_FILE:
            if set(value) != {"file_id"} or not isinstance(value["file_id"], str):
                raise WorkerDenied("WORKER_FILE_INPUT_INVALID")
            async with self.store.connection() as db:
                cur = await db.execute("UPDATE automation_worker_files SET content=NULL,state='DELETED',deleted_at_ms=? WHERE file_id=? AND run_id=? AND state='STORED'",
                                       (now, value["file_id"], body.run_id))
                await db.commit()
                if cur.rowcount != 1:
                    raise WorkerDenied("WORKER_FILE_NOT_OWNED_OR_AVAILABLE")
            return {"file_id": value["file_id"], "deleted": True}
        raise WorkerDenied("WORKER_OPERATION_UNSUPPORTED")

    async def _emit(self, body: WorkerStepBody, step: WorkflowIRStep, authority: Any) -> dict[str, Any]:
        value = body.value
        event_id = await self._event_identity(body, step, authority.device_id)
        existing = await self.store.fetchone("SELECT * FROM events WHERE event_id=?", (event_id,))
        if existing is not None:
            stored = json.loads(existing["payload_json"])
            receipt = {"emitted": True, "event_id": event_id, "event_seq": existing["seq"], **stored}
            if existing["target_device_id"] != authority.device_id or not await WorkerWorkflowObserver(self)._effect_matches(step, value, receipt, body.run_id):
                raise WorkerDenied("WORKER_DELIVERY_TARGET_MISMATCH")
            return receipt
        if step.operation == "emit_attention":
            if set(value) != {"change", "severity", "title"} or not isinstance(value["change"], dict) or not isinstance(value["title"], str):
                raise WorkerDenied("WORKER_ATTENTION_INPUT_INVALID")
            if value["change"].get("changed") is not True:
                return {"emitted": False, "reason": "SOURCE_UNCHANGED"}
            try:
                severity = AttentionSeverity(value["severity"])
            except ValueError as exc:
                raise WorkerDenied("WORKER_ATTENTION_SEVERITY_INVALID") from exc
            try:
                item = await AttentionEngine(self.store).upsert(
                    title=value["title"][:500], severity=severity, source="automation-worker",
                    dedupe_key=event_id,
                    payload={"run_id": body.run_id, "change": value["change"], "source_trust": "UNTRUSTED_EXTERNAL"},
                )
            except sqlite3.IntegrityError as exc:
                # Two fresh canonical runs can stage the same delivery. Recover
                # only the exact uniquely stored target; never repeat an uncertain
                # callback or reinterpret another store failure as success.
                stored = await self.store.fetchone("SELECT * FROM attention WHERE dedupe_key=?", (event_id,))
                if (stored is None or stored["title"] != value["title"][:500] or stored["severity"] != severity.value
                        or stored["source"] != "automation-worker"
                        or json.loads(stored["payload_json"]).get("change") != value["change"]):
                    raise WorkerDenied("WORKER_ATTENTION_TARGET_UNOBSERVED") from exc
                item = SimpleNamespace(id=stored["id"])
            payload = {"attention_id": item.id, "source_trust": "UNTRUSTED_EXTERNAL"}
            event_type = "attention.upserted"
        else:
            if set(value) != {"payload", "event_type"} or not isinstance(value["payload"], dict) or not isinstance(value["event_type"], str):
                raise WorkerDenied("WORKER_EVENT_INPUT_INVALID")
            if value["payload"].get("accepted") is False or value["payload"].get("changed") is False:
                return {"emitted": False, "reason": "SOURCE_UNCHANGED"}
            # The worker's event type is data, not the event-bus instruction/type.
            event_type = "automation.external_event"
            payload = {"event_type": value["event_type"][:200], "payload": value["payload"],
                       "source_trust": "UNTRUSTED_EXTERNAL", "command_id": body.grant.command_id}
        seq = await EventBus(self.store).publish(event_type, payload, target_device_id=authority.device_id,
                                                event_id=event_id, command_id=body.grant.command_id)
        # Another admitted run can finish the same staged delivery concurrently.
        # Return the actual immutable event, including its original provenance.
        delivered = await self.store.fetchone("SELECT * FROM events WHERE event_id=?", (event_id,))
        if delivered is None or delivered["target_device_id"] != authority.device_id:
            raise WorkerDenied("WORKER_DELIVERY_TARGET_MISMATCH")
        return {"emitted": True, "event_id": event_id, "event_seq": seq, **json.loads(delivered["payload_json"])}


class WorkerWorkflowObserver:
    """Observe the declared target state independently of n8n's success response.

    A sealed external document remains untrusted external data. Verification here
    proves the exact requested local receipt/storage effect and source readback;
    it never changes external content into owner instructions or provider truth.
    """
    def __init__(self, worker: AutomationWorkerRuntime) -> None:
        self.worker, self.store = worker, worker.store

    async def observe(self, spec: Any, context: dict[str, Any]) -> dict[str, Any]:
        run_id, inputs = context.get("run_id"), context.get("inputs")
        if not isinstance(run_id, str) or not isinstance(inputs, dict):
            raise WorkerDenied("WORKER_OBSERVATION_BINDING_MISSING")
        run = await self.store.fetchone("SELECT * FROM automation_runs WHERE run_id=?", (run_id,))
        if run is None or run["input_digest"] != digest(inputs):
            raise WorkerDenied("WORKER_OBSERVATION_INPUT_MISMATCH")
        execution = await self.worker.actions.get_execution(run["execution_id"])
        if execution is None or execution.parameters_digest != self.worker.actions.digest_parameters(inputs):
            raise WorkerDenied("WORKER_OBSERVATION_ACTION_MISMATCH")
        definition = await self.worker.actions.get_definition(execution.action_id)
        if definition is None or not definition.enabled:
            raise WorkerDenied("WORKER_OBSERVATION_ACTION_DISABLED")
        await self.worker.authority.authorize_action(
            command_id=run["command_id"], action=definition, principal_type=execution.principal_type,
            requested_by=execution.requested_by, snapshot_id=execution.snapshot_id,
            turn_id=execution.turn_id, parameters=inputs,
        )
        binding = await self.worker.bindings.get(run["artifact_id"])
        artifact = await self.worker.registry.get_artifact(run["artifact_id"])
        if binding is None or artifact is None or binding["binding_state"] != "DEPLOYED":
            raise WorkerDenied("WORKER_OBSERVATION_ARTIFACT_MISSING")
        ir = WorkflowIR.model_validate(binding["ir"])
        if (digest(ir.semantic_payload()) != artifact.workflow_ir_digest
                or strongest_class(ir.steps) != ir.action_class or definition.action_class != ir.action_class):
            raise WorkerDenied("WORKER_OBSERVATION_ARTIFACT_CHANGED")
        if ir.verifier.get("kind") not in ("READ_BACK", "RECEIPT", "STATE_PREDICATE"):
            raise WorkerDenied("WORKER_OWNER_POSTCONDITION_UNOBSERVABLE")
        rows = await self.store.fetchall("SELECT * FROM automation_worker_steps WHERE run_id=?", (run_id,))
        records = {row["step_id"]: row for row in rows}
        if "__admit__" not in records or records["__admit__"]["state"] != "COMPLETED":
            return {"exists": False, "reason": "RUN_NOT_ADMITTED"}
        evidence_pointer, observed = None, []
        body = SimpleNamespace(run_id=run_id, input=inputs)
        for step in ir.steps:
            if step.primitive in (Primitive.SCHEDULE_TRIGGER, Primitive.WEBHOOK_TRIGGER, Primitive.EVENT_TRIGGER):
                continue
            assert_primitive_semantics(step)
            row = records.get(step.step_id)
            selected, proof = await self.worker._selection(ir, run_id, step.step_id)
            if row is None or row["state"] not in {"COMPLETED", "SKIPPED"}:
                return {"exists": False, "reason": "STEP_NOT_COMPLETED", "step_id": step.step_id}
            result = json.loads(row["result_json"])
            if digest(result) != row["result_digest"]:
                return {"exists": False, "reason": "RECEIPT_DIGEST_MISMATCH", "step_id": step.step_id}
            if not selected:
                if row["state"] != "SKIPPED" or result != {"skipped": True, "reason": "BRANCH_NOT_SELECTED", "branch_proof": proof}:
                    return {"exists": False, "reason": "BRANCH_SKIP_RECEIPT_MISMATCH", "step_id": step.step_id}
                observed.append({"step_id": step.step_id, "status": "SKIPPED", "result_digest": row["result_digest"]})
                continue
            if row["state"] != "COMPLETED":
                return {"exists": False, "reason": "SELECTED_STEP_SKIPPED", "step_id": step.step_id}
            if step.mutates and not step.postcondition:
                raise WorkerDenied("WORKER_MUTATION_POSTCONDITION_UNOBSERVABLE")
            value = await self.worker._resolve(step.input_bindings, body, ir, step.step_id)
            if step.precondition is not None and not evaluate(step.precondition, value):
                return {"exists": False, "reason": "PRECONDITION_FALSE", "step_id": step.step_id}
            if not await self._effect_matches(step, value, result, run_id):
                return {"exists": False, "reason": "TARGET_READBACK_MISMATCH", "step_id": step.step_id}
            if step.postcondition:
                if step.postcondition.get("kind") not in ("READ_BACK", "RECEIPT", "STATE_PREDICATE"):
                    raise WorkerDenied("WORKER_STEP_POSTCONDITION_UNOBSERVABLE")
                field = step.postcondition.get("field")
                skipped_unchanged = step.primitive is Primitive.VAN_EVENT and result.get("emitted") is False
                if field and not skipped_unchanged and (field not in result or result[field] is None):
                    return {"exists": False, "reason": "DECLARED_FIELD_MISSING", "step_id": step.step_id}
                if field and "expected" in step.postcondition and result[field] != step.postcondition["expected"]:
                    return {"exists": False, "reason": "DECLARED_FIELD_MISMATCH", "step_id": step.step_id}
            observed.append({"step_id": step.step_id, "status": "COMPLETED", "result_digest": row["result_digest"]})
            evidence_pointer = result.get("evidence_pointer", evidence_pointer)
        if not observed:
            raise WorkerDenied("WORKER_OWNER_POSTCONDITION_UNOBSERVABLE")
        work_ids = {step.step_id for step in ir.steps if step.primitive not in (
            Primitive.SCHEDULE_TRIGGER, Primitive.WEBHOOK_TRIGGER, Primitive.EVENT_TRIGGER)}
        sinks = work_ids - {edge.from_step for edge in ir.edges if edge.to_step in work_ids}
        selected_sinks = [key for key in sorted(sinks) if records.get(key) and records[key]["state"] == "COMPLETED"]
        if len(selected_sinks) != 1:
            raise WorkerDenied("WORKER_OWNER_POSTCONDITION_UNOBSERVABLE")
        result = json.loads(records[selected_sinks[0]]["result_json"])
        field = ir.verifier.get("field")
        if field and field not in result:
            raise WorkerDenied("WORKER_OWNER_POSTCONDITION_FIELD_UNOBSERVABLE")
        if field and "expected" in ir.verifier and result[field] != ir.verifier["expected"]:
            return {"exists": False, "reason": "OWNER_POSTCONDITION_MISMATCH"}
        # A pointer to immutable callback receipts is evidence of the independently
        # read local effect. It does not claim a provider-issued receipt.
        return {**({field: result[field]} if field else {}),
                "exists": True, "correlation": {"run_id": run_id}, "steps": observed,
                "evidence_pointer": evidence_pointer or f"automation-run://{run_id}",
                "source_trust": "UNTRUSTED_EXTERNAL", "provider_correctness_verified": False}

    async def _effect_matches(self, step: WorkflowIRStep, value: dict[str, Any], result: dict[str, Any], run_id: str) -> bool:
        pure = pure_result(step.primitive.value, step.operation, value)
        if pure is not None:
            return pure == result
        if step.primitive is Primitive.WAIT:
            return result == {"waited_ms": value["delay_ms"]}
        if step.primitive is Primitive.VAN_CAPABILITY:
            if step.operation != "reminder.create":
                return False
            run = await self.store.fetchone("SELECT command_id FROM automation_runs WHERE run_id=?", (run_id,))
            if run is None:
                return False
            key = "automation-reminder:" + digest({"run": run_id, "step": step.step_id, "command": run["command_id"]})
            observed = await ReminderService(self.store).get_by_idempotency_key(key)
            return bool(observed and observed["text"] == value["text"] and observed["due_at_unix"] == value["due_at_unix"]
                        and observed["project_id"] == value.get("project_id") and observed["status"] == "OPEN"
                        and observed["source"] == "automation-worker"
                        and result == {"capability": "reminder.create", "reminder_id": observed["id"], "verified": True,
                                      "evidence_pointer": "reminder://" + observed["id"], "target_digest": digest(observed)})
        if step.primitive is Primitive.HTTP_REQUEST and step.operation in {"write_json", "delete_resource"}:
            observed = await self.worker.fetcher.fetch(value["readback"]["url"], timeout_ms=step.timeout_ms, credential_alias=step.credential_alias)
            return (result.get("verified") is True and result.get("request_digest") == digest(value)
                    and result.get("method") == value["method"] and result.get("readback_digest") == digest(observed)
                    and evaluate(value["readback"]["predicate"], {"payload": observed["payload"]}))
        if step.primitive is Primitive.HASH:
            return result == {"primary": digest(value["payload"]), "algorithm": "sha256"}
        if step.primitive in (Primitive.HTTP_GET, Primitive.HTTP_REQUEST):
            fresh = await self.worker.fetcher.fetch(value["url"], timeout_ms=step.timeout_ms, credential_alias=step.credential_alias)
            return fresh == result
        if step.primitive is Primitive.MAP_FIELDS:
            return result == {"payload": value["payload"], "source_trust": "UNTRUSTED_EXTERNAL"}
        if step.primitive in (Primitive.DEDUPE, Primitive.FILTER):
            return result.get("digest") == digest(value["payload"]) and result.get("payload") == value["payload"]
        if step.primitive is Primitive.VAN_EVIDENCE:
            pointer = result.get("evidence_pointer", "")
            row = await self.store.fetchone("SELECT * FROM automation_worker_evidence WHERE evidence_id=? AND run_id=? AND step_id=?",
                                            (pointer.removeprefix("automation-evidence://"), run_id, step.step_id))
            return bool(row and row["content_digest"] == digest(value["payload"])
                        and digest(json.loads(row["payload_json"])) == row["content_digest"]
                        and result.get("content_digest") == row["content_digest"])
        if step.primitive is Primitive.STORE_TRANSIENT_FILE:
            row = await self.store.fetchone("SELECT * FROM automation_worker_files WHERE file_id=? AND run_id=?", (result.get("file_id"), run_id))
            if row is None or row["content_sha256"] != result.get("sha256"):
                return False
            if row["state"] == "STORED":
                return hashlib.sha256(row["content"]).hexdigest() == row["content_sha256"]
            # A declared later release may remove the transient bytes. That is a
            # different, independently observed step, not a failed earlier store.
            return row["state"] == "DELETED" and row["content"] is None and row["deleted_at_ms"] is not None
        if step.primitive is Primitive.DELETE_TRANSIENT_FILE:
            row = await self.store.fetchone("SELECT * FROM automation_worker_files WHERE file_id=? AND run_id=?", (value.get("file_id"), run_id))
            return bool(row and row["state"] == "DELETED" and row["content"] is None and result.get("deleted") is True)
        if step.primitive is Primitive.VAN_EVENT:
            if result.get("emitted") is False:
                source = value.get("change", value.get("payload", {}))
                return isinstance(source, dict) and (source.get("changed") is False or source.get("accepted") is False)
            run = await self.store.fetchone("SELECT artifact_id,command_id FROM automation_runs WHERE run_id=?", (run_id,))
            authority = await self.worker.authority.get(run["command_id"]) if run else None
            if authority is None:
                return False
            expected_id = await self.worker._event_identity(
                SimpleNamespace(run_id=run_id, value=value, grant=SimpleNamespace(artifact_id=run["artifact_id"])),
                step, authority.device_id)
            if result.get("event_id") != expected_id:
                return False
            event = await self.store.fetchone("SELECT * FROM events WHERE event_id=? AND target_device_id=?",
                                              (expected_id, authority.device_id))
            if event is None:
                return False
            stored = json.loads(event["payload_json"])
            if stored.get("source_trust") != "UNTRUSTED_EXTERNAL" or event["seq"] != result.get("event_seq"):
                return False
            if step.operation == "emit_attention":
                attention = await self.store.fetchone("SELECT * FROM attention WHERE id=?", (result.get("attention_id"),))
                return bool(event["event_type"] == "attention.upserted" and stored.get("attention_id") == result.get("attention_id")
                            and attention and attention["title"] == value["title"][:500]
                            and attention["severity"] == value["severity"]
                            and json.loads(attention["payload_json"]).get("change") == value["change"])
            return (event["event_type"] == "automation.external_event" and stored.get("payload") == value.get("payload")
                    and stored.get("event_type") == value.get("event_type", "")[:200])
        raise WorkerDenied("WORKER_EFFECT_OBSERVER_UNAVAILABLE")
