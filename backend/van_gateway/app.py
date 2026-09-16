from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from van_gateway.attention.engine import AttentionEngine
from van_gateway.audit.service import AuditService
from van_gateway.auth.service import AuthError, AuthService
from van_gateway.briefing.service import BriefingService
from van_gateway.config import get_settings
from van_gateway.decisions.service import DecisionCreate, DecisionService
from van_gateway.degraded.registry import DegradedRegistry
from van_gateway.events.bus import EventBus
from van_gateway.google.control import GoogleControlAuthError, verify_internal_control
from van_gateway.google.mesh import GoogleCapabilityRegistry, GoogleCapabilityRouter, GoogleIdentityBroker, GoogleRouteRequest
from van_gateway.google.service import GoogleAuthError, GoogleService, NARROW_SCOPES
from van_gateway.google.transport import FakeGoogleTransport, GoogleHttpTransport, GoogleOAuthTokenClient
from van_gateway.hermes.bridge import HermesBridge
from van_gateway.idempotency.service import IdempotencyService
from van_gateway.models import ActionClass, AttentionSeverity, CommandRequest, ReminderCreate
from van_gateway.notifications.intelligence import NotificationIntelligence, PhoneNotification
from van_gateway.orchestrator import CommandOrchestrator
from van_gateway.projects.router import ProjectRouter
from van_gateway.reminders.service import ReminderService
from van_gateway.reminders.timeparse import TimeParseError, parse_due_expression
from van_gateway.storage.db import Store


class EnrollBody(BaseModel):
    device_id: str
    device_secret: str
    public_key_pem: str
    label: str | None = None


class GoogleConnectBody(BaseModel):
    refresh_token: str
    scopes: list[str] = Field(default_factory=lambda: list(NARROW_SCOPES))


class GoogleArtifactBody(BaseModel):
    source_tool: str
    output_hash: str
    project_id: str | None = None
    tool_version: str | None = None
    input_hashes: list[str] = Field(default_factory=list)
    trust: str = "UNTRUSTED"
    validation_state: str = "PENDING"
    parent_artifact_ids: list[str] = Field(default_factory=list)


class AttentionUpsertBody(BaseModel):
    title: str
    severity: AttentionSeverity
    source: str
    dedupe_key: str
    project_id: str | None = None


class ReminderParseBody(BaseModel):
    text: str
    due_expression: str
    idempotency_key: str
    project_id: str | None = None


class ProjectTruthBody(BaseModel):
    truth: dict
    truth_sha: str
    repo_sha: str | None = None


class DecisionResolveBody(BaseModel):
    approved: bool


def create_app() -> FastAPI:
    settings = get_settings()
    store = Store(settings.database_path)
    auth = AuthService(store, settings.device_secret_fernet_key)
    idempotency = IdempotencyService(store)
    hermes = HermesBridge(settings.hermes_base_url, settings.hermes_bearer_token, settings.hermes_profile)
    project_registry_path = str(Path(__file__).resolve().parents[2] / "registries" / "projects.json")
    google_registry_path = str(Path(__file__).resolve().parents[2] / "registries" / "google_capabilities.json")
    projects = ProjectRouter(store, project_registry_path)
    audit = AuditService(store)
    degraded = DegradedRegistry()
    attention = AttentionEngine(store, settings.attention_budget_per_hour)
    briefing = BriefingService(store, attention)
    reminders = ReminderService(store)
    decisions = DecisionService(store, attention)

    google_transport = None
    google_oauth = None
    if settings.google_oauth_client_id and settings.google_oauth_client_secret:
        google_transport = GoogleHttpTransport()
        google_oauth = GoogleOAuthTokenClient(settings.google_oauth_client_id, settings.google_oauth_client_secret)
    google = GoogleService(store, settings.google_token_fernet_key, transport=google_transport, oauth=google_oauth)
    google_registry = GoogleCapabilityRegistry(google_registry_path)
    google_broker = GoogleIdentityBroker(
        store,
        google_registry,
        ai_plan=settings.google_ai_plan,
        cloud_project_id=settings.google_cloud_project_id,
        gemini_runtime_configured=settings.google_gemini_runtime_configured,
        cloud_runtime_configured=settings.google_cloud_runtime_configured,
        consumer_connected_capabilities=settings.google_consumer_connected_capabilities,
    )
    google_router = GoogleCapabilityRouter(store, google_broker)

    events = EventBus(store, settings.event_page_size)
    notifications = NotificationIntelligence()
    orchestrator = CommandOrchestrator(
        auth=auth,
        idempotency=idempotency,
        hermes=hermes,
        projects=projects,
        audit=audit,
        degraded=degraded,
        owner_intent_max_age_seconds=settings.owner_intent_max_age_seconds,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await store.migrate()
        await auth.load_persisted_secrets()
        yield

    app = FastAPI(title="VAN Gateway", version="0.5.0-dev", lifespan=lifespan)
    app.state.store = store
    app.state.auth = auth
    app.state.degraded = degraded
    app.state.google = google
    app.state.google_broker = google_broker
    app.state.google_router = google_router
    app.state.orchestrator = orchestrator
    app.state.decisions = decisions
    app.state.projects = projects
    app.state.reminders = reminders

    def require_internal_control(x_van_internal_token: str | None) -> None:
        try:
            verify_internal_control(settings.internal_control_token, x_van_internal_token)
        except GoogleControlAuthError as exc:
            code = 503 if exc.code == "internal_control_token_unconfigured" else 403
            raise HTTPException(status_code=code, detail=exc.code) from exc

    @app.get("/health")
    async def health():
        hermes_health = await hermes.health()
        hermes_ok = bool(hermes_health.get("ok"))
        if hermes_ok:
            degraded.set(__import__("van_gateway.models", fromlist=["DegradedCode"]).DegradedCode.HERMES_OFFLINE, False)
        else:
            degraded.set(__import__("van_gateway.models", fromlist=["DegradedCode"]).DegradedCode.HERMES_OFFLINE, True)
        gstatus = await google.status()
        mesh = await google_broker.mesh_status(workspace=gstatus)
        configured = sum(1 for item in mesh["capabilities"] if item["state"] in {"READY", "CONFIGURED"})
        ready = sum(1 for item in mesh["capabilities"] if item["state"] == "READY")
        workspace = next(
            (item for item in mesh["capabilities"] if item["capability_id"] == "workspace_api"),
            None,
        )
        if workspace:
            raw_workspace_state = workspace["state"]
            workspace_state = getattr(raw_workspace_state, "value", str(raw_workspace_state))
        else:
            workspace_state = "UNVERIFIED"
        return {
            "ok": hermes_ok,
            "service": "van-gateway",
            "hermes": hermes_health,
            "google": gstatus.model_dump(),
            "google_mesh": {
                "principal": mesh["principal"],
                "configured_capabilities": configured,
                "ready_capabilities": ready,
                "total_capabilities": len(mesh["capabilities"]),
                "workspace_api_state": workspace_state,
                "workspace_api_ready": workspace_state == "READY",
                "hermes_is_sole_agent_runtime": True,
            },
            "degraded": degraded.snapshot(),
        }

    @app.post("/v1/devices/enroll")
    async def enroll(body: EnrollBody):
        try:
            device = await auth.enroll(body.device_id, body.device_secret, body.public_key_pem, body.label)
        except AuthError as exc:
            raise HTTPException(status_code=409 if exc.code == "already_enrolled" else 400, detail=exc.message) from exc
        return {"device_id": device.device_id, "enrolled_at_unix": device.enrolled_at_unix}

    @app.post("/v1/devices/{device_id}/revoke")
    async def revoke(device_id: str):
        try:
            await auth.revoke(device_id)
        except AuthError as exc:
            raise HTTPException(status_code=404, detail=exc.message) from exc
        return {"revoked": True, "device_id": device_id}

    @app.post("/v1/commands")
    async def commands(req: CommandRequest):
        return await orchestrator.handle(req)

    @app.get("/v1/briefing")
    async def get_briefing():
        hermes_health = await hermes.health()
        gstatus = await google.status()
        deg = degraded.codes() + gstatus.degraded
        if not hermes_health.get("ok"):
            deg.append("HERMES_OFFLINE")
        calendar_items = None
        mail_items = None
        if gstatus.connected and gstatus.services.get("calendar") == "ok" and google.transport is not None:
            try:
                calendar_items = await google.calendar_agenda()
            except GoogleAuthError:
                deg.append("GOOGLE_TOKEN_EXPIRED")
        return await briefing.build(calendar_items=calendar_items, mail_items=mail_items, hermes_health=hermes_health, degraded=deg)

    @app.post("/v1/reminders")
    async def create_reminder(body: ReminderCreate):
        return await reminders.create(body)

    @app.get("/v1/reminders")
    async def list_reminders():
        return await reminders.list_open()

    @app.post("/v1/reminders/{reminder_id}/resolve")
    async def resolve_reminder(reminder_id: str):
        try:
            await reminders.resolve(reminder_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="reminder_not_found") from exc
        return {"resolved": True}

    @app.post("/v1/reminders/{reminder_id}/cancel")
    async def cancel_reminder(reminder_id: str):
        await reminders.cancel(reminder_id)
        return {"cancelled": True}

    @app.post("/v1/reminders/parse")
    async def parse_reminder(body: ReminderParseBody):
        try:
            due = parse_due_expression(body.due_expression)
        except TimeParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return await reminders.create(ReminderCreate(text=body.text, due_at_unix=due, idempotency_key=body.idempotency_key, project_id=body.project_id))

    @app.post("/v1/decisions/escalate")
    async def escalate_decision(body: DecisionCreate):
        item = await decisions.escalate(body)
        await events.publish("decision.escalated", item.model_dump())
        return item

    @app.get("/v1/decisions")
    async def list_decisions():
        return await decisions.list_open()

    @app.post("/v1/decisions/{decision_id}/resolve")
    async def resolve_decision(decision_id: str, body: DecisionResolveBody):
        try:
            return await decisions.resolve(decision_id, approved=body.approved)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="decision_not_found") from exc

    @app.put("/v1/projects/{project_id}/truth")
    async def put_project_truth(
        project_id: str,
        body: ProjectTruthBody,
        x_van_internal_token: str | None = Header(default=None),
    ):
        require_internal_control(x_van_internal_token)
        if project_id not in projects.known_projects():
            raise HTTPException(status_code=404, detail="unknown_project")
        body_project = body.truth.get("project_id") if isinstance(body.truth, dict) else None
        if body_project is not None and str(body_project) != project_id:
            raise HTTPException(status_code=400, detail="truth_project_mismatch")
        await projects.cache_truth(project_id, body.truth, body.truth_sha, body.repo_sha)
        return await projects.load_truth(project_id)

    @app.post("/v1/google/test-transport")
    async def enable_fake_google_transport(x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token)
        google.transport = FakeGoogleTransport()
        google.oauth = None
        return {"transport": "fake", "live": False}

    @app.get("/v1/google/gmail/search")
    async def gmail_search(q: str, x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token)
        try:
            return {"messages": await google.gmail_search(q), "live": google.transport is not None and not isinstance(google.transport, FakeGoogleTransport)}
        except GoogleAuthError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/v1/google/gmail/send")
    async def gmail_send(draft_id: str, approved: bool = False, x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token)
        try:
            return await google.gmail_send(draft_id, action_class=ActionClass.A4, approved=approved)
        except GoogleAuthError as exc:
            code = 403 if str(exc) == "approval_required" else 503
            raise HTTPException(status_code=code, detail=str(exc)) from exc

    @app.get("/v1/google/status")
    async def google_status():
        return await google.status()

    @app.post("/v1/google/connect")
    async def google_connect(body: GoogleConnectBody, x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token)
        try:
            await google.store_refresh_token("owner", body.refresh_token, body.scopes)
        except GoogleAuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return await google.status()

    @app.post("/v1/google/revoke")
    async def google_revoke(x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token)
        await google.revoke()
        return await google.status()

    @app.get("/v1/google/mesh")
    async def google_mesh():
        return await google_broker.mesh_status(workspace=await google.status())

    @app.get("/v1/google/capabilities")
    async def google_capabilities():
        mesh = await google_broker.mesh_status(workspace=await google.status())
        return {"registry_version": mesh["registry_version"], "capabilities": mesh["capabilities"]}

    @app.post("/v1/google/jobs/plan")
    async def plan_google_job(body: GoogleRouteRequest, x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token)
        return await google_router.plan(body, workspace=await google.status())

    @app.get("/v1/google/jobs/{job_id}")
    async def get_google_job(job_id: str, x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token)
        job = await google_router.job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="google_job_not_found")
        return job

    @app.post("/v1/google/jobs/{job_id}/artifacts")
    async def record_google_artifact(job_id: str, body: GoogleArtifactBody, x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token)
        try:
            return await google_router.record_artifact(job_id=job_id, source_tool=body.source_tool, output_hash=body.output_hash, project_id=body.project_id, tool_version=body.tool_version, input_hashes=body.input_hashes, trust=body.trust, validation_state=body.validation_state, parent_artifact_ids=body.parent_artifact_ids)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/attention")
    async def upsert_attention(body: AttentionUpsertBody):
        item = await attention.upsert(title=body.title, severity=body.severity, source=body.source, dedupe_key=body.dedupe_key, project_id=body.project_id)
        await events.publish("attention.upserted", item.model_dump())
        return item

    @app.get("/v1/attention")
    async def list_attention():
        return await attention.list_open()

    @app.post("/v1/attention/{item_id}/ack")
    async def ack_attention(item_id: str):
        await attention.acknowledge(item_id)
        return {"acknowledged": True}

    @app.post("/v1/notifications/ingest")
    async def ingest_notification(note: PhoneNotification):
        filtered = notifications.ingest(note)
        if not filtered.suppressed:
            await attention.upsert(title=filtered.title, severity=__import__("van_gateway.models", fromlist=["AttentionSeverity"]).AttentionSeverity(filtered.classification.value), source=f"notification:{filtered.package}", dedupe_key=f"notif:{filtered.key}", payload={"text": filtered.text, "redacted": filtered.redacted})
        return filtered

    @app.get("/v1/degraded")
    async def get_degraded():
        return degraded.snapshot()

    @app.get("/v1/projects")
    async def list_projects():
        return {"projects": projects.known_projects()}

    @app.get("/v1/projects/{project_id}/truth")
    async def project_truth(project_id: str):
        return await projects.load_truth(project_id)

    @app.get("/v1/events")
    async def get_events(device_id: str, after_seq: int = 0):
        return await events.replay(device_id, after_seq)

    @app.post("/v1/events/reset")
    async def reset_events(device_id: str):
        await events.reset_cursor(device_id)
        from van_gateway.models import DegradedCode
        degraded.set(DegradedCode.EVENT_CURSOR_RESET, True)
        return {"reset": True, "device_id": device_id}

    return app


app = create_app()
