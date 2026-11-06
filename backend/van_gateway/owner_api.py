"""Paired-owner projections of local knowledge, automation and diagnostic state.

These reads do not probe providers, mint authority or accept runtime credentials.
Controls describe the existing signed command ingress; they are never direct
aliases of the internal control API. Configuration and cached results do not
create a readiness or owner-success claim.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from van_gateway.automation.health import AutomationHealthApi, governance_state
from van_gateway.automation.telemetry import TelemetryService
from van_gateway.automation.workflow_health import WorkflowHealthService
from van_gateway.mission.models import VerificationRecord
from van_gateway.owner_models import (
    AutomationCapability, AutomationDeadLetter, AutomationRun, BrowserEvidenceSummary,
    KnowledgeCitation, KnowledgeOperation, MissionOutcome, OwnerAutomationView,
    OwnerBrowserOutcomeView, OwnerCommandControl, OwnerDiagnosticsView,
    OwnerKnowledgeView, OwnerReadView, OwnerResearchView, ProjectionError,
    ProviderReadiness, ResearchCitation, RuntimeReadiness, StandingIntent,
)
from van_gateway.storage.db import Store

T = TypeVar("T")
from van_gateway.owner_privacy import _SECRET, _text, _reference


def _json(value: Any, *, default: T) -> Any | T:
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return default


def _runtime(value: Any) -> RuntimeReadiness:
    raw = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    pointer = _reference(raw.get("evidence_pointer"))
    state = _text(raw["state"])
    if state == "READY" and not (pointer and raw.get("verified_at_ms")):
        state = "UNVERIFIED"
    return RuntimeReadiness(
        capability=_text(raw["capability"]), state=state,
        configured=bool(raw["configured"]), egress_enabled=bool(raw["egress_enabled"]),
        runtime_version=_text(raw["runtime_version"]) if raw.get("runtime_version") else None,
        expected_version=_text(raw["expected_version"]) if raw.get("expected_version") else None,
        evidence_pointer=pointer,
        verified_at_ms=raw.get("verified_at_ms"),
        degraded_code=_text(raw["degraded_code"]) if raw.get("degraded_code") else None,
    )


class OwnerServiceApi:
    def __init__(
        self, store: Store, *, knowledge: Any, research: Any,
        automation_health: Any, ops_health: Callable[[], Awaitable[dict[str, Any]]],
    ) -> None:
        self.store = store
        self.knowledge = knowledge
        self.research = research
        self.automation_health = automation_health
        self.ops_health = ops_health
        self.router = APIRouter(prefix="/v1/owner", tags=["owner-services"])
        self._install_routes()

    async def _section(
        self, section: str, operation: Callable[[], Awaitable[T]], default: T,
        errors: list[ProjectionError],
    ) -> T:
        try:
            return await operation()
        except Exception:  # a failed subsystem must not erase independent local sections
            errors.append(ProjectionError(section=section))
            return default

    @staticmethod
    def _finish(view: OwnerReadView, errors: list[ProjectionError]) -> OwnerReadView:
        view.errors = errors
        view.status = "PARTIAL" if errors else "AVAILABLE"
        return view

    async def _control(
        self, action_id: str, label: str, template: str, fields: list[str],
        *, permitted: bool = True, reason: str = "PROVIDER_UNAVAILABLE",
    ) -> OwnerCommandControl:
        row = await self.store.fetchone(
            "SELECT enabled, action_class, allowed_principals_json FROM action_definitions WHERE action_id=?",
            (action_id,),
        )
        registered = bool(row and row["enabled"] and "OWNER_DEVICE" in _json(
            row["allowed_principals_json"], default=[]
        ))
        return OwnerCommandControl(
            control_id=action_id, label=label, action_id=action_id,
            command_template=template, required_fields=fields,
            available=registered and permitted,
            unavailable_reason=None if registered and permitted else (
                "OWNER_COMMAND_NOT_REGISTERED" if not registered else reason
            ),
            action_class=str(row["action_class"]) if row else None,
        )

    async def knowledge_view(self, limit: int = 30) -> OwnerKnowledgeView:
        errors: list[ProjectionError] = []
        view = OwnerKnowledgeView(observed_at_ms=int(time.time() * 1000))

        async def providers():
            certifications = await self.store.fetchall(
                "SELECT provider, verified_at_unix_ms FROM knowledge_provider_certifications"
            )
            times = {r["provider"]: r["verified_at_unix_ms"] for r in certifications}
            result = []
            for name in ("vekl", "obsidian", "notebook_enterprise", "notebook_consumer"):
                async def provider(name=name):
                    status = await getattr(self.knowledge, name).status()
                    p = status.model_dump(mode="json")
                    return ProviderReadiness(
                        provider=_text(p["provider"]), state=("UNVERIFIED" if p["state"] == "READY" and not (
                            _reference(p.get("evidence_pointer")) and times.get(p["provider"])
                        ) else _text(p["state"])),
                        credential_locus=_text(p["credential_locus"]),
                        evidence_pointer=_reference(p.get("evidence_pointer")),
                        verified_at_ms=times.get(p["provider"]),
                    )
                value = await self._section(name, provider, None, errors)
                if value is not None:
                    result.append(value)
            return result

        async def evidence():
            rows = await self.store.fetchall(
                "SELECT evidence_id,provider,query_id,source_ref,title,source_trust,epistemic_state,"
                "scope,retrieved_at_unix_ms,content_digest,snippet FROM knowledge_evidence "
                "ORDER BY retrieved_at_unix_ms DESC,evidence_id LIMIT ?", (limit,),
            )
            return [KnowledgeCitation(
                evidence_id=_text(r["evidence_id"]), provider=_text(r["provider"]),
                query_id=_text(r["query_id"]), source_ref=_reference(r["source_ref"]),
                title=_text(r["title"]) if r["title"] else None,
                source_trust=_text(r["source_trust"]), epistemic_state=_text(r["epistemic_state"]),
                scope=_text(r["scope"]), retrieved_at_ms=r["retrieved_at_unix_ms"],
                content_digest=_text(r["content_digest"]), snippet=_text(r["snippet"], 2000),
            ) for r in rows]

        async def operations():
            rows = await self.store.fetchall(
                "SELECT operation_id,provider,operation,status,resource_id,evidence_pointer,"
                "error_code,updated_at_unix_ms FROM notebook_operations "
                "ORDER BY updated_at_unix_ms DESC,operation_id LIMIT ?", (limit,),
            )
            return [KnowledgeOperation(
                operation_id=_text(r["operation_id"]), provider=_text(r["provider"]),
                operation=_text(r["operation"]), status=_text(r["status"]),
                resource_id=_reference(r["resource_id"]), evidence_pointer=_reference(r["evidence_pointer"]),
                error_code=_text(r["error_code"]) if r["error_code"] else None,
                updated_at_ms=r["updated_at_unix_ms"],
            ) for r in rows]

        view.providers = await self._section("providers", providers, [], errors)
        view.evidence = await self._section("evidence", evidence, [], errors)
        view.operations = await self._section("operations", operations, [], errors)
        usable = any(p.provider == "NOTEBOOK_CONSUMER" and p.state in {"CONFIGURED", "READY"}
                     for p in view.providers)

        async def controls():
            enterprise = any(p.provider == "NOTEBOOK_ENTERPRISE" and p.state in {"CONFIGURED", "READY"}
                             for p in view.providers)
            return [await self._control(
                "google.notebook.note.create", "Create a notebook note",
                "create note in notebook {notebook_id} named {title}", ["notebook_id", "title"],
                permitted=usable,
            ), await self._control(
                "google.notebook.enterprise.delete", "Delete an Enterprise notebook",
                "delete notebook enterprise notebook id {notebook_id}", ["notebook_id"],
                permitted=enterprise,
            ), await self._control(
                "google.notebook.enterprise.sources.delete", "Delete Enterprise notebook sources",
                "delete sources {source_names} from notebook enterprise notebook id {notebook_id}",
                ["notebook_id", "source_names"], permitted=enterprise,
            )]

        view.controls = await self._section("controls", controls, [], errors)
        return self._finish(view, errors)

    async def research_view(self, limit: int = 30) -> OwnerResearchView:
        errors: list[ProjectionError] = []
        view = OwnerResearchView(observed_at_ms=int(time.time() * 1000))

        async def readiness():
            raw = await self.research.status()
            pointer = _reference(raw.get("evidence_pointer"))
            return ProviderReadiness(
                provider=_text(raw["provider"]), state="UNVERIFIED" if raw["state"] == "READY" and not pointer else _text(raw["state"]),
                credential_locus=_text(raw["credential_locus"]),
                evidence_pointer=pointer,
            ), bool(raw["egress_enabled"])

        view.provider, view.egress_enabled = await self._section("provider", readiness, (None, False), errors)

        async def evidence():
            rows = await self.store.fetchall(
                "SELECT evidence_id,research_id,source_url,source_title,source_trust,published_at,"
                "retrieved_at_unix_ms,content_digest,evidence_json FROM research_evidence "
                "ORDER BY retrieved_at_unix_ms DESC,evidence_id LIMIT ?", (limit,),
            )
            result = []
            for r in rows:
                raw = _json(r["evidence_json"], default={})
                highlights = raw.get("highlights", []) if isinstance(raw, dict) else []
                result.append(ResearchCitation(
                    evidence_id=_text(r["evidence_id"]), research_id=_text(r["research_id"]),
                    source_url=_reference(r["source_url"]), title=_text(r["source_title"]) if r["source_title"] else None,
                    source_trust=_text(r["source_trust"]), published_at=_text(r["published_at"]) if r["published_at"] else None,
                    retrieved_at_ms=r["retrieved_at_unix_ms"], content_digest=_text(r["content_digest"]),
                    highlights=[_text(h, 1000) for h in highlights[:4]] if isinstance(highlights, list) else [],
                ))
            return result

        view.evidence = await self._section("evidence", evidence, [], errors)

        async def controls():
            return [await self._control(
                "research.web.search", "Research the web", "research {query}", ["query"],
                permitted=bool(view.provider and view.provider.state in {"CONFIGURED", "READY"}),
            )]

        view.controls = await self._section("controls", controls, [], errors)
        return self._finish(view, errors)

    async def automation_view(self, device_id: str, limit: int = 30) -> OwnerAutomationView:
        errors: list[ProjectionError] = []
        now = int(time.time() * 1000)
        view = OwnerAutomationView(
            observed_at_ms=now,
            ingress_enabled=self.automation_health.settings.automation_ingress_enabled,
            egress_enabled=self.automation_health.settings.automation_egress_enabled,
        )

        async def governance():
            return governance_state()

        view.governance = await self._section("governance", governance, {}, errors)

        async def runtime():
            return _runtime(await self.automation_health.n8n.status())

        async def capabilities():
            rows = await self.store.fetchall(
                "SELECT capability_id,semantic_name,engine,action_class,mutates_state,lifecycle_state,"
                "verifier_type,updated_at_ms FROM automation_capabilities ORDER BY updated_at_ms DESC,capability_id LIMIT ?", (limit,),
            )
            return [AutomationCapability(**{k: _text(r[k]) for k in (
                "capability_id", "semantic_name", "engine", "action_class", "lifecycle_state", "verifier_type"
            )}, mutates_state=bool(r["mutates_state"]), updated_at_ms=r["updated_at_ms"]) for r in rows]

        async def runs():
            rows = await self.store.fetchall(
                "SELECT run_id,capability_id,artifact_id,command_id,execution_id,status,verifier_status,evidence_pointer,error_code,started_at_ms,completed_at_ms "
                "FROM automation_runs ORDER BY started_at_ms DESC,run_id LIMIT ?", (limit,),
            )
            return [AutomationRun(
                run_id=_text(r["run_id"]), capability_id=_text(r["capability_id"]), status=_text(r["status"]),
                artifact_id=_text(r["artifact_id"]), command_id=_text(r["command_id"]) if r["command_id"] else None,
                execution_id=_text(r["execution_id"]) if r["execution_id"] else None,
                verifier_status=_text(r["verifier_status"]) if r["verifier_status"] else None,
                evidence_pointer=_reference(r["evidence_pointer"]), error_code=_text(r["error_code"]) if r["error_code"] else None,
                owner_success=r["status"] == "VERIFIED_SUCCESS" and r["verifier_status"] == "VERIFIED_SUCCESS"
                and bool(_reference(r["evidence_pointer"])),
                started_at_ms=r["started_at_ms"], completed_at_ms=r["completed_at_ms"],
            ) for r in rows]

        async def standing():
            rows = await self.store.fetchall(
                "SELECT i.intent_id,i.owner_goal,i.capability_id,i.workflow_version,i.action_class,i.enabled,i.expires_at_ms,"
                "(SELECT COUNT(*) FROM standing_automation_authorities a JOIN devices d ON d.device_id=a.source_device_id "
                " WHERE a.standing_intent_id=i.intent_id AND a.revoked_at_ms IS NULL AND d.revoked_at_unix IS NULL "
                " AND (a.expires_at_ms IS NULL OR a.expires_at_ms>?)) AS active_authorities,"
                "(SELECT COUNT(*) FROM standing_automation_authorities a JOIN devices d ON d.device_id=a.source_device_id "
                " WHERE a.standing_intent_id=i.intent_id AND a.revoked_at_ms IS NULL AND d.revoked_at_unix IS NULL "
                " AND a.source_device_id=? AND (a.expires_at_ms IS NULL OR a.expires_at_ms>?)) AS current_device_authorities,"
                "(SELECT COUNT(*) FROM standing_automation_authorities a JOIN devices d ON d.device_id=a.source_device_id "
                " WHERE a.standing_intent_id=i.intent_id AND d.revoked_at_unix IS NULL "
                " AND a.source_device_id=?) AS current_device_authority_roots "
                "FROM automation_standing_intents i ORDER BY i.updated_at_ms DESC,i.intent_id LIMIT ?", (now, device_id, now, device_id, limit),
            )
            result = []
            for r in rows:
                own = bool(r["current_device_authority_roots"])
                enabled = bool(r["enabled"])
                supported = bool(re.fullmatch(r"[A-Za-z0-9._-]{1,256}", str(r["intent_id"])))
                control = await self._control(
                    "automation.standing_intent.disable", "Disable standing work",
                    "disable standing intent " + _text(r["intent_id"]), [],
                    permitted=enabled and own and supported, reason=("UNSUPPORTED_INTENT_IDENTIFIER" if not supported
                        else "ALREADY_DISABLED" if not enabled else "CURRENT_DEVICE_NOT_AUTHORITY_ROOT"),
                )
                expired = r["expires_at_ms"] is not None and r["expires_at_ms"] <= now
                result.append(StandingIntent(
                    intent_id=_text(r["intent_id"]), owner_goal=_text(r["owner_goal"], 1000),
                    capability_id=_text(r["capability_id"]), workflow_version=r["workflow_version"],
                    action_class=_text(r["action_class"]), enabled=enabled,
                    expires_at_ms=r["expires_at_ms"], expired=expired,
                    active_authorities=r["active_authorities"], current_device_authorities=r["current_device_authorities"],
                    current_device_authority_roots=r["current_device_authority_roots"],
                    executable_authority_present=enabled and not expired and bool(r["active_authorities"]),
                    disable_control=control,
                ))
            return result

        async def dead_letters():
            rows = await self.store.fetchall(
                "SELECT dead_letter_id,run_id,capability_id,failure_class,last_error_code,attempt_count,next_action,"
                "evidence_refs_json,created_at_ms FROM automation_dead_letter WHERE resolved_at_ms IS NULL "
                "ORDER BY created_at_ms DESC,dead_letter_id LIMIT ?", (limit,),
            )
            return [AutomationDeadLetter(
                dead_letter_id=_text(r["dead_letter_id"]), run_id=_text(r["run_id"]) if r["run_id"] else None,
                capability_id=_text(r["capability_id"]) if r["capability_id"] else None,
                failure_class=_text(r["failure_class"]), error_code=_text(r["last_error_code"]) if r["last_error_code"] else None,
                attempt_count=r["attempt_count"], next_action=_text(r["next_action"]),
                evidence_refs=[ref for raw in _json(r["evidence_refs_json"], default=[]) if (ref := _reference(raw))],
                created_at_ms=r["created_at_ms"],
            ) for r in rows]

        view.runtime = await self._section("runtime", runtime, None, errors)
        view.capabilities = await self._section("capabilities", capabilities, [], errors)
        view.runs = await self._section("runs", runs, [], errors)
        view.standing_intents = await self._section("standing_intents", standing, [], errors)
        view.dead_letters = await self._section("dead_letters", dead_letters, [], errors)
        view.workflow_health = await self._section(
            "workflow_health", WorkflowHealthService(self.store).counts_by_status, {}, errors,
        )

        async def attention():
            rows = await self.store.fetchall(
                "SELECT capability_id,workflow_version,status,consecutive_failures,last_failure_class "
                "FROM automation_workflow_health WHERE status IN ('DEGRADED','REPAIR_REQUIRED','QUARANTINED') "
                "ORDER BY updated_at_ms DESC,capability_id LIMIT ?", (limit,),
            )
            return [{"capability_id": _text(r["capability_id"]), "workflow_version": r["workflow_version"],
                     "status": _text(r["status"]), "consecutive_failures": r["consecutive_failures"],
                     "last_failure_class": _text(r["last_failure_class"]) if r["last_failure_class"] else None} for r in rows]

        async def ladder():
            return AutomationHealthApi._ladder_payload(await TelemetryService(self.store).ladder_metrics())

        view.workflows_needing_attention = await self._section("workflows_needing_attention", attention, [], errors)
        view.ladder = await self._section("ladder", ladder, {}, errors)
        return self._finish(view, errors)

    async def diagnostics_view(self) -> OwnerDiagnosticsView:
        errors: list[ProjectionError] = []
        view = OwnerDiagnosticsView(observed_at_ms=int(time.time() * 1000))

        async def governance():
            return governance_state()

        view.governance = await self._section("governance", governance, {}, errors)
        for name in ("n8n", "harness", "stagehand"):
            async def service(name=name):
                return _runtime(await getattr(self.automation_health, name).status())
            value = await self._section(name, service, None, errors)
            if value is not None:
                view.services.append(value)
        async def computer_use():
            surfaces = self.automation_health.computer_use.surfaces()
            return {"surfaces": surfaces, "surfaces_with_a_worker": sorted(k for k, v in surfaces.items() if v)}

        view.computer_use = await self._section("computer_use", computer_use, {}, errors)
        health = await self._section("operations", self.ops_health, {}, errors)
        raw_scheduler = health.get("scheduler", {})
        view.scheduler = {
            "running": bool(raw_scheduler.get("running")),
            "jobs": [{
                "name": _text(j.get("name")), "interval_seconds": j.get("interval_seconds"),
                "next_due_unix": j.get("next_due_unix"),
                "last_run": {k: j["last_run"].get(k) for k in (
                    "run_at_unix", "finished_at_unix", "outcome"
                )} if isinstance(j.get("last_run"), dict) else None,
            } for j in raw_scheduler.get("jobs", [])],
        }
        for field in ("pki", "device_pki"):
            raw = health.get(field, {})
            setattr(view, field, {k: raw.get(k) for k in ("configured", "present", "days_remaining")})
        view.backup = {k: health.get("backup", {}).get(k) for k in (
            "configured", "present", "age_seconds", "created_at_unix"
        )}
        settings = self.automation_health.settings
        temporal_enabled = bool(getattr(settings, "temporal_enabled", False))
        temporal_configured = bool(getattr(settings, "temporal_bridge_url", "") and getattr(settings, "temporal_bridge_token", ""))
        view.temporal = {
            "enabled": temporal_enabled, "configured": temporal_configured,
            "state": "CONFIGURED" if temporal_enabled and temporal_configured else (
                "POLICY_DISABLED" if not temporal_enabled else "UNCONFIGURED"
            ), "readiness_source": "CONFIGURATION_ONLY", "live_runtime_verified": False,
        }
        signing_configured = bool(getattr(settings, "browser_stream_signing_key_file", ""))
        signal_configured = bool(getattr(settings, "browser_stream_signal_url", ""))
        view.interactive_browser = {
            "signing_key_configured": signing_configured, "signal_configured": signal_configured,
            "state": "CONFIGURED" if signing_configured and signal_configured else "UNCONFIGURED",
            "readiness_source": "CONFIGURATION_ONLY", "live_stream_verified": False,
        }
        return self._finish(view, errors)

    async def browser_outcome(self, task_id: str, limit: int = 30) -> OwnerBrowserOutcomeView:
        try:
            task = await self.store.fetchone("SELECT task_id,status FROM browser_tasks WHERE task_id=?", (task_id,))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="OWNER_STATE_UNAVAILABLE") from exc
        if task is None:
            raise HTTPException(status_code=404, detail="BROWSER_TASK_NOT_FOUND")
        errors: list[ProjectionError] = []
        completed = task["status"] == "COMPLETED"
        view = OwnerBrowserOutcomeView(
            observed_at_ms=int(time.time() * 1000), task_id=_text(task_id),
            task_status=_text(task["status"]), execution_completed=completed,
        )

        async def evidence():
            rows = await self.store.fetchall(
                "SELECT evidence_id,kind,source_trust,injection_assessment,created_at_ms,url_digest,dom_digest,"
                "screenshot_digest,extraction_digest FROM browser_evidence WHERE task_id=? AND contains_secrets=0 "
                "ORDER BY created_at_ms DESC,evidence_id LIMIT ?", (task_id, limit),
            )
            return [BrowserEvidenceSummary(
                evidence_id=_text(r["evidence_id"]), kind=_text(r["kind"]), source_trust=_text(r["source_trust"]),
                injection_assessment=_text(r["injection_assessment"]), created_at_ms=r["created_at_ms"],
                content_digests={k: _text(r[k]) for k in (
                    "url_digest", "dom_digest", "screenshot_digest", "extraction_digest"
                ) if r[k]},
            ) for r in rows]

        async def missions():
            rows = await self.store.fetchall(
                "SELECT DISTINCT m.mission_id,m.state,m.verification_state,m.verification_record_json "
                "FROM missions m JOIN mission_activities a ON a.mission_id=m.mission_id "
                "WHERE a.executor='BROWSER_FABRIC' AND a.executor_ref=? ORDER BY m.updated_at_ms DESC LIMIT ?", (task_id, limit),
            )
            result = []
            for r in rows:
                record = VerificationRecord.model_validate_json(r["verification_record_json"]) if r["verification_record_json"] else None
                result.append(MissionOutcome(
                    mission_id=_text(r["mission_id"]), state=_text(r["state"]),
                    verification_state=_text(r["verification_state"]),
                    owner_success=bool(r["state"] == "VERIFIED_SUCCESS" and record and record.supports_success),
                    evidence_refs=[ref for e in record.evidence_refs if (ref := _reference(e))] if record else [],
                    verified_at_ms=record.verified_at_ms if record else None,
                ))
            return result

        view.evidence = await self._section("evidence", evidence, [], errors)
        view.mission_outcomes = await self._section("mission_outcomes", missions, [], errors)
        return self._finish(view, errors)

    def _install_routes(self) -> None:
        async def device(request: Request) -> str:
            device_id = getattr(request.state, "van_device_id", "")
            if not device_id:
                raise HTTPException(status_code=401, detail="owner_device_required")
            try:
                row = await self.store.fetchone("SELECT revoked_at_unix FROM devices WHERE device_id=?", (device_id,))
            except Exception as exc:
                raise HTTPException(status_code=503, detail="OWNER_STATE_UNAVAILABLE") from exc
            if row is None or row["revoked_at_unix"] is not None:
                raise HTTPException(status_code=403, detail="owner_device_revoked_or_unknown")
            return str(device_id)

        def response(view: OwnerReadView):
            return JSONResponse(view.model_dump(mode="json"), headers={"Cache-Control": "no-store"})

        @self.router.get("/knowledge", response_model=OwnerKnowledgeView)
        async def knowledge(request: Request, limit: int = Query(30, ge=1, le=100)):
            await device(request)
            return response(await self.knowledge_view(limit))

        @self.router.get("/research", response_model=OwnerResearchView)
        async def research(request: Request, limit: int = Query(30, ge=1, le=100)):
            await device(request)
            return response(await self.research_view(limit))

        @self.router.get("/automation", response_model=OwnerAutomationView)
        async def automation(request: Request, limit: int = Query(30, ge=1, le=100)):
            return response(await self.automation_view(await device(request), limit))

        @self.router.get("/diagnostics", response_model=OwnerDiagnosticsView)
        async def diagnostics(request: Request):
            await device(request)
            return response(await self.diagnostics_view())

        @self.router.get("/browser/tasks/{task_id}/outcome", response_model=OwnerBrowserOutcomeView)
        async def browser_outcome(request: Request, task_id: str, limit: int = Query(30, ge=1, le=100)):
            await device(request)
            return response(await self.browser_outcome(task_id, limit))


__all__ = ["OwnerServiceApi"]
