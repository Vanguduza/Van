from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from van_gateway.attention.engine import AttentionEngine
from van_gateway.audit.service import AuditService
from van_gateway.auth.service import AuthError, AuthService
from van_gateway.briefing.service import BriefingService
from van_gateway.config import get_settings
from van_gateway.degraded.registry import DegradedRegistry
from van_gateway.events.bus import EventBus
from van_gateway.google.service import GoogleAuthError, GoogleService, NARROW_SCOPES
from van_gateway.hermes.bridge import HermesBridge
from van_gateway.idempotency.service import IdempotencyService
from van_gateway.models import (
    AttentionSeverity,
    CommandRequest,
    ReminderCreate,
)
from van_gateway.notifications.intelligence import NotificationIntelligence, PhoneNotification
from van_gateway.orchestrator import CommandOrchestrator
from van_gateway.projects.router import ProjectRouter
from van_gateway.reminders.service import ReminderService
from van_gateway.storage.db import Store


class EnrollBody(BaseModel):
    device_id: str
    device_secret: str
    public_key_pem: str
    label: str | None = None


class GoogleConnectBody(BaseModel):
    refresh_token: str
    scopes: list[str] = Field(default_factory=lambda: list(NARROW_SCOPES))


class AttentionUpsertBody(BaseModel):
    title: str
    severity: AttentionSeverity
    source: str
    dedupe_key: str
    project_id: str | None = None


def create_app() -> FastAPI:
    settings = get_settings()
    store = Store(settings.database_path)
    auth = AuthService(store)
    idempotency = IdempotencyService(store)
    hermes = HermesBridge(settings.hermes_base_url, settings.hermes_bearer_token, settings.hermes_profile)
    registry_path = str(Path(__file__).resolve().parents[2] / "registries" / "projects.json")
    projects = ProjectRouter(store, registry_path)
    audit = AuditService(store)
    degraded = DegradedRegistry()
    attention = AttentionEngine(store, settings.attention_budget_per_hour)
    briefing = BriefingService(store, attention)
    reminders = ReminderService(store)
    google = GoogleService(store, settings.google_token_fernet_key)
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
        yield

    app = FastAPI(title="VAN Gateway", version="0.5.0-dev", lifespan=lifespan)
    app.state.store = store
    app.state.auth = auth
    app.state.degraded = degraded
    app.state.google = google
    app.state.orchestrator = orchestrator

    @app.get("/health")
    async def health():
        hermes_health = await hermes.health()
        if not hermes_health.get("ok"):
            degraded.set(__import__("van_gateway.models", fromlist=["DegradedCode"]).DegradedCode.HERMES_OFFLINE, True)
        gstatus = await google.status()
        return {
            "ok": True,
            "service": "van-gateway",
            "hermes": hermes_health,
            "google": gstatus.model_dump(),
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
        brief = await briefing.build(calendar_items=calendar_items, mail_items=mail_items, hermes_health=hermes_health, degraded=deg)
        return brief

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
                severity=__import__("van_gateway.models", fromlist=["AttentionSeverity"]).AttentionSeverity(filtered.classification.value),
                source=f"notification:{filtered.package}",
                dedupe_key=f"notif:{filtered.key}",
                payload={"text": filtered.text, "redacted": filtered.redacted},
            )
        return filtered

    @app.get("/v1/degraded")
    async def get_degraded():
        return degraded.snapshot()

    @app.get("/v1/google/status")
    async def google_status():
        return await google.status()

    @app.post("/v1/google/connect")
    async def google_connect(body: GoogleConnectBody):
        try:
            await google.store_refresh_token("owner", body.refresh_token, body.scopes)
        except GoogleAuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return await google.status()

    @app.post("/v1/google/revoke")
    async def google_revoke():
        await google.revoke()
        return await google.status()

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
