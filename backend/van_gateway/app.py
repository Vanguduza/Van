from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
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
from van_gateway.automation.api import AutomationApi
from van_gateway.automation.dispatch import AutomationDispatcher
from van_gateway.automation.grants import RunGrantService
from van_gateway.automation.health import AutomationHealthApi
from van_gateway.automation.registry import AutomationRegistry, HotWorkflowIndex
from van_gateway.browser.api import BrowserApi
from van_gateway.capability.models import ReadinessSource
from van_gateway.capability.readiness import (
    AutomationReadiness,
    ExternalRuntimeReadiness,
    GoogleMeshReadiness,
)
from van_gateway.capability.registry import CapabilityRegistry
from van_gateway.capability.router import CapabilityRouter
from van_gateway.mission.api import MissionApi
from van_gateway.understanding.api import UnderstandingApi
from van_gateway.mission.service import MissionService
from van_gateway.command.authority import CommandAuthorityService
from van_gateway.command.standing import StandingAutomationAuthorityService
from van_gateway.runtime_api import OwnerRuntimeApi
from van_gateway.storage.db import Store
from van_gateway.trading import TradingControlError, TradingService
from van_gateway.trading.accounts import ACTIONS as ACCOUNT_ACTIONS, AccountOnboarding, CommanderAccountControl, LocalAccountControl, OAuthPending, canonical_action, redact as redact_account_args


class EnrollBody(BaseModel):
    device_id: str
    device_secret: str
    public_key_pem: str
    label: str | None = None


class PairDeviceBody(EnrollBody):
    pairing_token: str = Field(min_length=32)


class PairingTicketCreate(BaseModel):
    label: str | None = None
    ttl_seconds: int = Field(default=600, ge=60, le=3600)


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


class AccountActionRequest(BaseModel):
    device_id: str
    issued_at_unix: int
    signature: str
    action: str
    args: dict = Field(default_factory=dict)


class OwnerHaltRequest(BaseModel):
    owner_signature_ref: str = Field(min_length=1)
    reason: str = ""


class TicketConfirmRequest(BaseModel):
    owner_signature_ref: str = Field(min_length=1)
    fill_price: str
    filled_qty: str
    contract_note_ref: str = Field(min_length=1)


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
    owner_runtime = OwnerRuntimeApi(store, settings)
    automation_registry = AutomationRegistry(store)
    automation_hot_index = HotWorkflowIndex()
    # One index, so `/v1/automation/health` reports the index work is routed
    # through rather than an empty copy of it.
    automation_health = AutomationHealthApi(
        store, settings, degraded=degraded, hot_index=automation_hot_index
    )
    # The dispatcher shares the owner runtime's ActionRuntime and command
    # authority: an automation run must meet the same single final authority
    # check as everything else VAN does, not a second copy of it.
    automation_dispatcher = AutomationDispatcher(
        store,
        actions=owner_runtime.actions,
        authority=owner_runtime.authority,
        registry=automation_registry,
        grants=RunGrantService(store, signing_key=settings.automation_grant_signing_key),
        client=automation_health.n8n,
        enabled=settings.automation_enabled,
    )
    automation = AutomationApi(
        store,
        settings,
        registry=automation_registry,
        hot_index=automation_hot_index,
        standing=StandingAutomationAuthorityService(store, owner_runtime.authority),
        dispatcher=automation_dispatcher,
    )
    # No worker is configured: the semantic worker is a separate private service
    # and the gateway refuses an assignment rather than pretending to run one.
    browser = BrowserApi(store, settings, decisions=decisions)


    trading = TradingService(
        settings.vati_ledger_path,
        accounts_registry=settings.vati_accounts_registry,
        lake_root=settings.vati_lake_root,
        reporting_currency=settings.vati_reporting_currency,
    )
    account_control = (
        CommanderAccountControl(settings.van_commander_url, settings.van_commander_token_file, settings.van_commander_ca_file)
        if settings.van_commander_url
        else LocalAccountControl(settings.vati_accounts_registry, settings.vati_secrets_dir)
    )
    oauth_pending = OAuthPending(store, settings.google_token_fernet_key)
    onboarding = AccountOnboarding(account_control, oauth_pending, settings.van_public_base_url, settings.vati_deriv_app_id)

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
    # Rev 1 §7 — one canonical declaration set. Readiness is delegated to the
    # subsystems that already own it, so this registry never becomes a third
    # copy of automation or Google state.
    capability_registry = CapabilityRegistry(
        store,
        probes={
            ReadinessSource.AUTOMATION_REGISTRY: AutomationReadiness(
                store, enabled=settings.automation_enabled
            ),
            ReadinessSource.GOOGLE_MESH: GoogleMeshReadiness(google_broker),
            ReadinessSource.EXTERNAL_RUNTIME: ExternalRuntimeReadiness(
                automation_health.runtime, enabled=settings.browser_enabled
            ),
        },
    )
    capability_router = CapabilityRouter(store, capability_registry)
    missions = MissionService(store, capabilities=capability_registry)
    mission_api = MissionApi(
        store, settings, missions=missions, registry=capability_registry,
        router=capability_router,
    )
    understanding_api = UnderstandingApi(store, settings)
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
        context=owner_runtime.context,
        authority=owner_runtime.authority,
        resolver=owner_runtime.resolver,
        owner_intent_max_age_seconds=settings.owner_intent_max_age_seconds,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await store.migrate()
        await auth.load_persisted_secrets()
        await oauth_pending.migrate()
        await owner_runtime.startup()
        # §273 — the HOT index is a cache of durable state, so it is rebuilt on
        # every boot rather than trusted to survive a restart.
        await automation_hot_index.rebuild(store)
        # §7 — the declaration set is sealed by digest and synced on boot,
        # so a manifest edit takes effect on restart and is auditable after.
        await capability_registry.sync()
        yield

    app = FastAPI(title="VAN Gateway", version="0.5.0-dev", lifespan=lifespan)
    app.state.store = store
    app.state.auth = auth
    app.state.degraded = degraded
    app.state.google = google
    app.state.google_broker = google_broker
    app.state.google_router = google_router
    app.state.orchestrator = orchestrator
    app.state.owner_runtime = owner_runtime
    app.state.automation_health = automation_health
    app.state.automation = automation
    app.state.automation_registry = automation_registry
    app.state.automation_hot_index = automation_hot_index
    app.state.automation_dispatcher = automation_dispatcher
    app.state.browser = browser
    app.state.capability_registry = capability_registry
    app.state.capability_router = capability_router
    app.state.missions = missions
    app.state.mission_api = mission_api
    app.state.understanding_api = understanding_api
    app.state.decisions = decisions
    app.state.projects = projects
    app.state.reminders = reminders
    app.state.trading = trading
    app.state.onboarding = onboarding
    app.include_router(owner_runtime.router)
    app.include_router(automation_health.router)
    app.include_router(automation.router)
    app.include_router(browser.router)
    app.include_router(mission_api.router)
    app.include_router(understanding_api.router)

    def internal_control_route(method: str, path: str) -> bool:
        if path.startswith("/v1/runtime/"):
            return True
        # Rev 1.3 §219 — automation/browser health is an internal control surface;
        # it exposes runtime identity and governance state, never an owner route.
        if path in {"/v1/automation/health", "/v1/browser/health"}:
            return True
        # §§219-222 — the whole automation control surface is Hermes-only. It never
        # accepts owner ingress, so a compromised ingress token cannot compile,
        # admit or publish a capability.
        if path.startswith("/v1/automation/"):
            return True
        # §§2.3, 43 — the mission read model is owner-facing; planning is not.
        # Cancel and message are the two mutations that are the owner's to make.
        if path.startswith("/v1/missions") or path in ("/v1/needs-you", "/v1/activity",
                                                        "/v1/capabilities/status"):
            if method == "GET":
                return False
            return not (path.endswith("/cancel") or path.endswith("/message"))
        # §§33, 63.6 — the Understanding surface is the owner's. Hermes may
        # observe; only the owner confirms, corrects, rejects or reverts.
        if path.startswith("/v1/understanding") or path in (
            "/v1/technology-radar", "/v1/eval", "/v1/autonomy"
        ):
            return path == "/v1/understanding/observe"
        # Owner Android may inspect browser truth through authenticated GETs.
        # Browser mutations/assignments remain Hermes internal-control only.
        if path.startswith("/v1/browser/"):
            return method != "GET"
        if method == "PUT" and path.startswith("/v1/projects/") and path.endswith("/truth"):
            return True
        if method == "POST" and path in {
            "/v1/devices/enroll",
            "/v1/devices/pairing-ticket",
        }:
            return True
        if method == "POST" and path.startswith("/v1/devices/") and path.endswith("/revoke"):
            return True
        if method == "POST" and path == "/v1/trading/halt":
            return True
        if method == "POST" and path.startswith("/v1/trading/tickets/") and path.endswith("/confirm"):
            return True
        if path in {
            "/v1/google/test-transport",
            "/v1/google/gmail/search",
            "/v1/google/gmail/send",
            "/v1/google/connect",
            "/v1/google/revoke",
            "/v1/google/jobs/plan",
        }:
            return True
        return path.startswith("/v1/google/jobs/")

    @app.middleware("http")
    async def require_ingress_auth(request: Request, call_next):
        if request.method == "POST" and request.url.path == "/v1/devices/pair":
            return await call_next(request)
        if request.method == "GET" and request.url.path.startswith("/v1/trading/oauth/") and request.url.path.endswith("/callback"):
            return await call_next(request)

        # Privileged local Hermes control uses an independent machine credential.
        if internal_control_route(request.method, request.url.path):
            expected_internal = settings.internal_control_token.strip()
            presented_internal = request.headers.get("X-Van-Internal-Token", "")
            if expected_internal and presented_internal and hmac.compare_digest(expected_internal, presented_internal):
                return await call_next(request)

        configured = settings.ingress_token.strip()
        presented = request.headers.get("X-Van-Ingress-Token", "")
        if not configured:
            return JSONResponse(status_code=503, content={"detail": "ingress_auth_unconfigured"})
        if not presented or not hmac.compare_digest(configured, presented):
            return JSONResponse(status_code=401, content={"detail": "ingress_auth_failed"})

        # Health is the only ingress-only route, used by local/tunnel probes.
        if request.method == "GET" and request.url.path == "/health":
            return await call_next(request)

        try:
            device = await auth.require_access_token(request.headers.get("X-Van-Device-Token", ""))
        except AuthError:
            return JSONResponse(status_code=401, content={"detail": "device_access_denied"})
        request.state.van_device_id = device.device_id
        return await call_next(request)

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
        runtime_status = await owner_runtime.status()
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
            "owner_runtime": runtime_status,
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

    @app.post("/v1/devices/pairing-ticket")
    async def create_pairing_ticket(
        body: PairingTicketCreate,
        x_van_internal_token: str | None = Header(default=None),
    ):
        require_internal_control(x_van_internal_token)
        ticket = await auth.create_pairing_ticket(body.label, body.ttl_seconds)
        return JSONResponse(
            {
                "pairing_token": ticket.token,
                "expires_at_unix": ticket.expires_at_unix,
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/v1/devices/pair")
    async def pair_device(body: PairDeviceBody):
        ingress_token = settings.ingress_token.strip()
        if not ingress_token:
            raise HTTPException(status_code=503, detail="ingress_auth_unconfigured")
        try:
            result = await auth.pair_device(
                body.pairing_token,
                body.device_id,
                body.device_secret,
                body.public_key_pem,
                body.label,
            )
        except AuthError as exc:
            code = 409 if exc.code in {"already_enrolled", "device_revoked"} else 400
            raise HTTPException(status_code=code, detail=exc.message) from exc
        return JSONResponse(
            {
                "device_id": result.device.device_id,
                "enrolled_at_unix": result.device.enrolled_at_unix,
                "ingress_token": ingress_token,
                "device_access_token": result.access_token,
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/v1/devices/enroll")
    async def enroll(
        body: EnrollBody,
        x_van_internal_token: str | None = Header(default=None),
    ):
        require_internal_control(x_van_internal_token)
        try:
            device = await auth.enroll(body.device_id, body.device_secret, body.public_key_pem, body.label)
        except AuthError as exc:
            raise HTTPException(status_code=409 if exc.code == "already_enrolled" else 400, detail=exc.message) from exc
        return {"device_id": device.device_id, "enrolled_at_unix": device.enrolled_at_unix}

    @app.post("/v1/devices/{device_id}/revoke")
    async def revoke(
        device_id: str,
        x_van_internal_token: str | None = Header(default=None),
    ):
        require_internal_control(x_van_internal_token)
        try:
            await auth.revoke(device_id)
        except AuthError as exc:
            raise HTTPException(status_code=404, detail=exc.message) from exc
        revoked_executions = await owner_runtime.actions.revoke_privileged_for_device(f"device:{device_id}")
        return {
            "revoked": True,
            "device_id": device_id,
            "revoked_privileged_executions": revoked_executions,
        }

    @app.post("/v1/commands")
    async def commands(req: CommandRequest, request: Request):
        if getattr(request.state, "van_device_id", None) != req.device_id:
            raise HTTPException(status_code=403, detail="device_identity_mismatch")
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
        return await reminders.create(
            ReminderCreate(
                text=body.text,
                due_at_unix=due,
                idempotency_key=body.idempotency_key,
                project_id=body.project_id,
            )
        )

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
            return {
                "messages": await google.gmail_search(q),
                "live": google.transport is not None and not isinstance(google.transport, FakeGoogleTransport),
            }
        except GoogleAuthError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/v1/google/gmail/send")
    async def gmail_send(
        draft_id: str,
        approved: bool = False,
        x_van_internal_token: str | None = Header(default=None),
    ):
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
    async def record_google_artifact(
        job_id: str,
        body: GoogleArtifactBody,
        x_van_internal_token: str | None = Header(default=None),
    ):
        require_internal_control(x_van_internal_token)
        try:
            return await google_router.record_artifact(
                job_id=job_id,
                source_tool=body.source_tool,
                output_hash=body.output_hash,
                project_id=body.project_id,
                tool_version=body.tool_version,
                input_hashes=body.input_hashes,
                trust=body.trust,
                validation_state=body.validation_state,
                parent_artifact_ids=body.parent_artifact_ids,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/attention")
    async def upsert_attention(body: AttentionUpsertBody):
        item = await attention.upsert(
            title=body.title,
            severity=body.severity,
            source=body.source,
            dedupe_key=body.dedupe_key,
            project_id=body.project_id,
        )
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
            await attention.upsert(
                title=filtered.title,
                severity=__import__("van_gateway.models", fromlist=["AttentionSeverity"]).AttentionSeverity(
                    filtered.classification.value
                ),
                source=f"notification:{filtered.package}",
                dedupe_key=f"notif:{filtered.key}",
                payload={"text": filtered.text, "redacted": filtered.redacted},
            )
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
    async def get_events(request: Request, device_id: str, after_seq: int = 0):
        if getattr(request.state, "van_device_id", None) != device_id:
            raise HTTPException(status_code=403, detail="device_identity_mismatch")
        return await events.replay(device_id, after_seq)

    # ------------------------------------------------------------ VATI trading
    def _trading_status_payload() -> dict:
        from van_gateway.models import DegradedCode

        try:
            status = trading.status()
        except Exception as exc:
            degraded.set(DegradedCode.TRADING_LEDGER_UNAVAILABLE, True)
            return {
                "ledger_available": False,
                "ledger_path": trading.ledger_path,
                "chain_ok": None,
                "error": str(exc),
                "degraded": degraded.codes(),
            }
        degraded.set(
            DegradedCode.TRADING_LEDGER_UNAVAILABLE,
            not (status.get("ledger_available") and status.get("chain_ok")),
        )
        status["degraded"] = degraded.codes()
        return status

    @app.get("/v1/trading/status")
    async def trading_status():
        return _trading_status_payload()

    @app.get("/v1/trading/trades")
    async def trading_trades(view: str = "all", limit: int = 50):
        try:
            return trading.trade_book(view=view, limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/v1/trading/portfolio")
    async def trading_portfolio():
        return trading.portfolio()

    @app.get("/v1/trading/accounts")
    async def trading_accounts():
        return trading.accounts()

    @app.get("/v1/trading/market-state")
    async def trading_market_state(symbol: str | None = None):
        return trading.market_state(symbol)

    @app.get("/v1/trading/risk")
    async def trading_risk():
        return trading.risk()

    @app.get("/v1/trading/trades/{trade_intent_id}")
    async def trading_trade_detail(trade_intent_id: str):
        detail = trading.trade_detail(trade_intent_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="unknown trade intent")
        return detail

    @app.get("/v1/trading/bars")
    async def trading_bars(symbol: str, timeframe: str = "H1", limit: int = 300, end_ms: int | None = None):
        try:
            return trading.bars(symbol, timeframe, limit=limit, end_ms=end_ms)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/v1/trading/accounts/action")
    async def trading_account_action(request: Request, req: AccountActionRequest):
        if getattr(request.state, "van_device_id", None) != req.device_id:
            raise HTTPException(status_code=403, detail="device_identity_mismatch")
        if req.action not in ACCOUNT_ACTIONS:
            raise HTTPException(status_code=404, detail="unknown account action")
        try:
            await auth.require_device(req.device_id)
            auth.verify_signature(
                req.device_id,
                canonical_action(req.device_id, req.issued_at_unix, req.action, req.args),
                req.signature,
            )
        except AuthError as exc:
            await audit.record(
                result="denied",
                device_id=req.device_id,
                capability=f"trading.account.{req.action}",
                failure_reason=exc.code,
            )
            raise HTTPException(status_code=403, detail=exc.message) from exc
        import time as _time

        if abs(int(_time.time()) - req.issued_at_unix) > 300:
            raise HTTPException(status_code=403, detail="stale owner action; sign again")
        try:
            result = await onboarding.run(req.action, req.args)
        except HTTPException as exc:
            await audit.record(
                result="refused",
                device_id=req.device_id,
                capability=f"trading.account.{req.action}",
                failure_reason=str(exc.detail)[:200],
                before=redact_account_args(req.args),
            )
            raise
        await audit.record(
            result="ok",
            device_id=req.device_id,
            capability=f"trading.account.{req.action}",
            before=redact_account_args(req.args),
            after={
                k: v
                for k, v in result.items()
                if k in ("account", "alias", "state", "ready", "stored_keys", "removed", "ok")
            },
        )
        return result

    @app.get("/v1/trading/oauth/{broker}/callback")
    async def trading_oauth_callback(broker: str, request: Request):
        from fastapi.responses import HTMLResponse

        try:
            result = await onboarding.oauth_callback(broker, dict(request.query_params))
        except HTTPException as exc:
            return HTMLResponse(
                f"<h2>Van: linking failed</h2><p>{exc.detail}</p>",
                status_code=exc.status_code,
            )
        return HTMLResponse(
            f"<h2>Van: {result['broker']} linked</h2>"
            "<p>Return to the Van app to choose the account. You can close this page.</p>"
        )

    @app.get("/v1/trading/tickets")
    async def trading_tickets(status: str | None = None):
        return {"tickets": trading.tickets(status=status)}

    @app.post("/v1/trading/halt")
    async def trading_halt(
        req: OwnerHaltRequest,
        x_van_internal_token: str | None = Header(default=None),
    ):
        require_internal_control(x_van_internal_token)
        try:
            result = trading.halt(owner_signature_ref=req.owner_signature_ref, reason=req.reason)
        except TradingControlError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        await audit.record(
            result="owner_halt_recorded",
            capability="trading.owner_halt",
            approval=req.owner_signature_ref,
            tool="vati_ledger",
            after={"event_hash": result["event_hash"], "chain_hash": result["chain_hash"]},
            evidence_pointer=result["event_hash"],
        )
        return result

    @app.post("/v1/trading/tickets/{ticket_id}/confirm")
    async def trading_confirm_ticket(
        ticket_id: str,
        req: TicketConfirmRequest,
        x_van_internal_token: str | None = Header(default=None),
    ):
        require_internal_control(x_van_internal_token)
        try:
            result = trading.confirm_ticket(
                ticket_id,
                owner_signature_ref=req.owner_signature_ref,
                fill_price=req.fill_price,
                filled_qty=req.filled_qty,
                contract_note_ref=req.contract_note_ref,
            )
        except TradingControlError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        await audit.record(
            result="owner_ticket_confirmed",
            capability="trading.ticket_confirm",
            approval=req.owner_signature_ref,
            tool="vati_ledger",
            after={"ticket": ticket_id, "event_hash": result["event_hash"]},
            evidence_pointer=result["event_hash"],
        )
        return result

    @app.post("/v1/events/reset")
    async def reset_events(request: Request, device_id: str):
        if getattr(request.state, "van_device_id", None) != device_id:
            raise HTTPException(status_code=403, detail="device_identity_mismatch")
        await events.reset_cursor(device_id)
        from van_gateway.models import DegradedCode

        degraded.set(DegradedCode.EVENT_CURSOR_RESET, True)
        return {"reset": True, "device_id": device_id}

    return app


app = create_app()
