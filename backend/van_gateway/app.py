from __future__ import annotations

from contextlib import asynccontextmanager
import base64
import binascii
import hmac
import json
import shutil
import time
from typing import Any
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, ValidationError

from van_gateway.attention.engine import AttentionEngine
from van_gateway.audit.service import AuditService
from van_gateway.auth.service import AuthError, AuthService
from van_gateway.approval.service import OwnerApprovalError, OwnerApprovalService
from van_gateway.auth.control_scopes import ControlAuthority, ControlScope
from van_gateway.auth.rotation import CredentialRotation
from van_gateway.context.forget import OwnerMemory
from van_gateway.context.lifecycle import ContextLifecycle
from van_gateway.learning.feed import LearningFeed
from van_gateway.context.authoring import (
    ContextAuthoringError,
    OwnerFactAuthor,
    ProjectTruthImporter,
)
from van_gateway.auth.throttle import GLOBAL_SUBJECT, AuthThrottle, Throttled
from van_gateway.command.mission_link import CommandMissionLink
from van_gateway.briefing.service import BriefingService
from van_gateway.config import get_settings
from van_gateway.decisions.service import DecisionCreate, DecisionService
from van_gateway.degraded.registry import DegradedRegistry
from van_gateway.events.bus import EventBus
from van_gateway.google.control import GoogleControlAuthError, verify_internal_control
from van_gateway.google.planes import plane_health, summarise
from van_gateway.google.mesh import GoogleCapabilityRegistry, GoogleCapabilityRouter, GoogleIdentityBroker, GoogleRouteRequest
from van_gateway.google.service import GoogleAuthError, GoogleService, NARROW_SCOPES
from van_gateway.google.transport import FakeGoogleTransport, GoogleHttpTransport, GoogleOAuthTokenClient
from van_gateway.hermes.bridge import HermesBridge
from van_gateway.idempotency.service import IdempotencyService
from van_gateway.models import (
    ActionClass,
    AttentionSeverity,
    CommandRequest,
    OwnerApprovalProof,
    PrincipalType,
    ReminderCreate,
)
from van_gateway.notifications.intelligence import NotificationIntelligence, PhoneNotification
from van_gateway.observability import alerts as observability_alerts
from van_gateway.observability import instruments as observability_instruments
from van_gateway.observability.correlation import for_command as correlation_for_command
from van_gateway.observability.logging import configure as configure_logging
from van_gateway.observability.metrics import REGISTRY as METRICS, render_prometheus
from van_gateway.observability.middleware import MetricsMiddleware
from van_gateway.observability.trace import CommandTracer
from van_gateway.coherence import owner_status
from van_gateway.coherence import wire_status
from van_gateway.ops import health as ops_health
from van_gateway.ops.backup import create_backup, drill as backup_drill
from van_gateway.ops.pki import scan as pki_scan
from van_gateway.ops.retention import RetentionService
from van_gateway.ops.scheduler import OpsScheduler, ScheduledJob
from van_gateway.ops.suppression import SuppressionChannel, SuppressionStore
from van_gateway.orchestrator import CommandOrchestrator
from van_gateway.projects.router import ProjectRouter
from van_gateway.reminders.service import ReminderService
from van_gateway.reminders.timeparse import TimeParseError, parse_due_expression
from van_gateway.automation.api import AutomationApi
from van_gateway.automation.dispatch import AutomationDispatcher
from van_gateway.automation.grants import RunGrantService
from van_gateway.automation.health import AutomationHealthApi
from van_gateway.automation.registry import AutomationRegistry, HotWorkflowIndex
from van_gateway.browser.agent_grant import AgentGrantService
from van_gateway.browser.api import BrowserApi
from van_gateway.browser.control_lease import ControlLeaseService
from van_gateway.browser.downloads import DownloadBroker
from van_gateway.browser.downloads_api import build_download_report_router
from van_gateway.browser.interactive_api import (
    build_interactive_router,
    is_interactive_browser_owner_route,
)
from van_gateway.browser.interactive_service import InteractiveSessionService
from van_gateway.browser.quality_api import QualityControllers, build_quality_router
from van_gateway.connectivity.provisioning import (
    build_provisioning_payload,
    sign_provisioning_payload,
)
from van_gateway.browser.stream_grants import (
    SigningKey,
    StreamGrantService,
    StreamGrantSigner,
)
from van_gateway.browser.worker import AdapterBackedWorker
from van_gateway.session.api import build_session_router, is_session_owner_route
from van_gateway.voice.speech_stream import SpeechStreamService
from van_gateway.session.router import (
    SessionDelegateError,
    SessionDelegates,
    SessionRouter,
)
from van_gateway.session.service import VanHermesSessionService
from van_gateway.auth.device_binding import DeviceBindingError, OwnerDeviceBindingService
from van_gateway.auth.device_proof import AttestationPolicy
from van_gateway.connectivity.config import ConnectivityConfigService, ConnectivityError
from van_gateway.capability.models import ReadinessSource
from van_gateway.capability.readiness import (
    AutomationReadiness,
    ExternalRuntimeReadiness,
    GoogleMeshReadiness,
)
from van_gateway.capability.registry import CapabilityRegistry
from van_gateway.capability.router import CapabilityRouter
from van_gateway.mission.api import MissionApi
from van_gateway.mission.models import MissionEventType, MissionState
from van_gateway.mission.service import MissionError
from van_gateway.mission.binding import MissionBinder
from van_gateway.understanding.api import UnderstandingApi
from van_gateway.verification.production import build_automation_verifier, build_mission_registry
from van_gateway.mission.service import MissionService
from van_gateway.command.authority import CommandAuthorityService
from van_gateway.command.standing import StandingAutomationAuthorityService
from van_gateway.runtime_api import OwnerRuntimeApi
from van_gateway.storage.db import Store
from van_gateway.trading import TradingAuthorityError, TradingControlError, TradingService
from van_gateway.trading.accounts import ACTIONS as ACCOUNT_ACTIONS, AccountOnboarding, CommanderAccountControl, LocalAccountControl, OAuthPending, canonical_action, redact as redact_account_args, requires_owner_approval


class EnrollBody(BaseModel):
    """The device identity an enrolment establishes.

    P4-DOC-004 — these fields are documented here, once. `PairDeviceBody` inherits them
    and adds only what pairing adds, rather than restating them: the two descriptions had
    already drifted apart once, and a field whose meaning is written down twice is a field
    whose meaning is eventually written down two different ways.
    """

    device_id: str = Field(
        description="Stable identifier for this device. Chosen by the enroller, not the device.",
    )
    device_secret: str = Field(
        description=(
            "Shared HMAC secret for command signing. Stored encrypted; never returned, "
            "never logged, and never placed in a prompt."
        ),
    )
    public_key_pem: str = Field(
        description=(
            "P-256 public key for owner approval proofs (A4). The private half stays in "
            "the device's hardware keystore and never leaves it."
        ),
    )
    label: str | None = Field(
        default=None,
        description="Human-readable name for this device in the owner's device list.",
    )


class PairDeviceBody(EnrollBody):
    """Enrolment plus the ticket that authorises it.

    Pairing is enrolment performed by the owner's own device rather than by an operator, so
    the only additional field is proof that an operator issued a ticket for it.
    """

    pairing_token: str = Field(
        min_length=32,
        description=(
            "Single-use ticket from POST /v1/devices/pairing-ticket. Consumed atomically "
            "with the enrolment, so a replayed pairing cannot mint a second device."
        ),
    )


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
    #: P1-SEC-004 — required for every action that changes an account or a credential.
    #: The device signs the gateway's one-time challenge inside the biometric callback
    #: with a keystore key, so a prompt that merely succeeded is not authority.
    approval_proof: OwnerApprovalProof | None = None


class AccountChallengeRequest(BaseModel):
    device_id: str
    issued_at_unix: int
    signature: str
    action: str
    args: dict = Field(default_factory=dict)


class OwnerFactBody(BaseModel):
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    value: Any
    scope: str = "global"
    valid_until_ms: int | None = None


class DeviceTelemetrySample(BaseModel):
    """One device-produced measurement (P3-OBS-002).

    The name must be one the catalogue declares — see
    `instruments.DEVICE_HISTOGRAMS` and `DEVICE_GAUGES`. An unknown name is
    refused rather than registered, because a metric that appears at runtime with
    no declared producer is exactly the drift Gate 11 exists to stop.
    """

    name: str
    value: float
    surface: str | None = None
    #: The one dimension a series other than `aura_frame_time_ms` may carry — the
    #: storability of a queued command, today. Kept separate from `surface` because
    #: `surface` is already on the wire and shipped devices post it; renaming it here
    #: would quietly drop the aura label from every phone that had not been updated.
    dimension: str | None = None


class DeviceTelemetryBody(BaseModel):
    samples: list[DeviceTelemetrySample] = Field(default_factory=list)


class OwnerHaltRequest(BaseModel):
    owner_signature_ref: str = Field(min_length=1)
    reason: str = ""


class TicketConfirmRequest(BaseModel):
    owner_signature_ref: str = Field(min_length=1)
    fill_price: str
    filled_qty: str
    contract_note_ref: str = Field(min_length=1)


#: Google routes that require the internal-control credential at the GOOGLE scope.
#:
#: One set with two readers. `control_scope_for` decides what the middleware demands, and
#: the guard below it decides what the handler-level check expects; they held separate
#: copies of this list. A route in one and missing from the other is not an inconsistency,
#: it is a hole — an unscoped route falls through to owner-device authentication, and
#: reaching the owner's Gmail with a device token is the fall-through P0-SEC-001 closed.
#:
#: P2-GOOG-004 added the six in the middle, which had a transport, a service method and no
#: route at all.
GOOGLE_CONTROL_ROUTES: frozenset[str] = frozenset({
    "/v1/google/gmail/search",
    "/v1/google/gmail/send",
    "/v1/google/gmail/draft",
    "/v1/google/calendar/agenda",
    "/v1/google/calendar/reschedule",
    "/v1/google/drive/search",
    "/v1/google/contacts/resolve",
    "/v1/google/tasks",
    "/v1/google/connect",
    "/v1/google/revoke",
    "/v1/google/jobs/plan",
})


class BootstrapCreateBody(BaseModel):
    note: str | None = None


class ProvisioningPayloadBody(BaseModel):
    """ADR-RB-026 — what the installer asks for, which is deliberately almost nothing.

    The installer names the Gateway the device should reach, because it is the only party
    that knows which deployment this is. Everything else — the one-time credential, the
    attestation challenge, the expiry — is the Gateway's to mint, so that an installer
    cannot extend a provisioning window or reuse a token by asking for it.
    """

    gateway_url: str = Field(min_length=1)
    note: str | None = None

class BootstrapChallengeBody(BaseModel):
    token: str

class BootstrapAttestBody(BaseModel):
    token: str
    device_id: str
    public_key_pem: str
    #: Base64 of the raw attestation extension octets from the device key's certificate.
    attestation_extension_b64: str
    attestation_root_fingerprint: str | None = None
    os_version: str | None = None
    os_patch_level: str | None = None

class RebindBody(BaseModel):
    reason: str


def _read_stream_signing_key(path: str) -> str:
    """Load the grant-signing key from disk (§5.5: it never leaves the Gateway host).

    A missing or unreadable file raises rather than falling back to a generated key. A
    gateway that quietly generates its own would mint grants the stream host cannot verify,
    and the failure would appear as "the browser will not connect" on the owner's phone
    rather than as a misconfiguration here.
    """
    return Path(path).read_text(encoding="utf-8")


def _parse_ice_servers(raw: str) -> list[dict]:
    """Deployment configuration. Malformed JSON is empty rather than fatal: no ICE server
    means direct connectivity only, which is a degraded browser, not a broken gateway."""
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def create_app() -> FastAPI:
    settings = get_settings()
    store = Store(settings.database_path)
    auth = AuthService(store, settings.device_secret_fernet_key)
    throttle = AuthThrottle()
    rotation = CredentialRotation(store)
    # P0-CTX-002 — writers for the authoritative epistemic tiers, which had none.
    # P0-SEC-001 — scoped privileged credentials, so one token is no longer root.
    control_authority = ControlAuthority(
        legacy_token=settings.internal_control_token,
        scoped=settings.internal_control_scoped_tokens,
        device_enrolment_token=settings.device_enrolment_token,
        observability_token=settings.observability_token,
    )
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
    # P2-BROW-001 — the browser task path reaches a real adapter. `worker` was None, so
    # POST /v1/browser/assignments answered 503 and the only way a task acquired evidence
    # was for its caller to hand the evidence in: a page snapshot in the evidence table was
    # whatever somebody said it was. The adapter is `automation_health`'s, not a second
    # one, so there is one connection to the browser worker and one readiness verdict about
    # it — two adapters would mean the health surface could report READY while the task
    # path talked to something else.
    browser = BrowserApi(
        store, settings, decisions=decisions,
        worker=AdapterBackedWorker(automation_health.harness),
    )


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
    # Constructed before the mission service, which publishes every owner-visible
    # mission event to it (P0-EXEC-001).
    events = EventBus(store, settings.event_page_size)
    # Rev 1.5 §§5, 6 — the interactive browser session.
    #
    # It shares the Browser Fabric's broker and policy engine rather than constructing its
    # own: ADR-RB-005 says the existing fabric owns browser authority, and two brokers would
    # mean two answers to "who holds this profile".
    browser_control_leases = ControlLeaseService(store)
    interactive_sessions = InteractiveSessionService(
        store, browser.broker, browser_control_leases, events=events,
    )
    # §5.5 — a dedicated ES256 key, separate from owner approval and device enrolment.
    # Absent configuration means grants cannot be minted, which is the honest state of a
    # deployment with no stream host: the routes refuse rather than issuing a credential
    # nothing can verify.
    browser_stream_grants = (
        StreamGrantService(
            store,
            StreamGrantSigner(SigningKey(
                kid=settings.browser_stream_signing_kid,
                private_pem=_read_stream_signing_key(settings.browser_stream_signing_key_file),
            )),
        )
        if settings.browser_stream_signing_key_file
        else None
    )

    # P0-VERIFY-001 — the registry that performs verification, rather than a receipt
    # the claimant writes. Built before the service because the service fails closed
    # without it.
    verifiers = build_mission_registry(
        store=store, trading=trading, knowledge=owner_runtime.knowledge,
    )
    # P1-AUTO-001 — the dispatcher was constructed with an empty observer map, so every
    # production run came back UNVERIFIABLE and owner_success could never be true; the
    # tests passed only because they injected their own observers. Assigned here rather
    # than at construction because the Google service the READ_BACK observer reads is
    # built after the dispatcher, and reordering that is a larger change than this is.
    automation_dispatcher.verifier = build_automation_verifier(store=store, google=google)
    learning = LearningFeed(store)
    missions = MissionService(
        store, capabilities=capability_registry, bus=events, verifiers=verifiers,
        learning=learning,
    )
    mission_api = MissionApi(
        store, settings, missions=missions, registry=capability_registry,
        router=capability_router,
    )
    # §5 — one binder shared by every executor, so browser tasks and
    # automation runs become Activities as they happen rather than by a
    # later backfill.
    owner_fact_author = OwnerFactAuthor(owner_runtime.context)
    truth_importer = ProjectTruthImporter(owner_runtime.context)
    # P2-MEM-002 — the owner's ability to end what VAN concluded about them.
    owner_memory = OwnerMemory(store)
    context_lifecycle = ContextLifecycle(store, owner_runtime.context)
    mission_binder = MissionBinder(store, missions)
    # P0-EXEC-001 — the join that makes an accepted command a durable mission.
    command_missions = CommandMissionLink(
        missions, execution_deadline_seconds=settings.execution_deadline_seconds,
    )
    browser.binder = mission_binder
    automation.binder = mission_binder
    understanding_api = UnderstandingApi(store, settings)
    google_router = GoogleCapabilityRouter(store, google_broker)

    # P3-OPS-005 — dedupe that survives a restart, instead of a set() on the instance.
    suppressions = SuppressionStore(store)
    notifications = NotificationIntelligence(suppressions=suppressions)
    retention = RetentionService(store)
    tracer = CommandTracer(store)
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
        throttle=throttle,
        missions=command_missions,
    )

    # ---------------------------------------------------------- Gate 11: ops jobs
    async def _sweep_reminders() -> dict:
        """P3-OPS-004 — fire_due, actually called, and its result actually delivered.

        Firing a reminder and not telling anyone is the same as not firing it, so the
        job publishes an event the device replays and raises an attention item the
        owner sees. The attention item is keyed by reminder id, so the same reminder
        never becomes two things to look at.
        """
        fired = await reminders.fire_due()
        for item in fired:
            await events.publish("reminder.fired", {
                "reminder_id": item["id"],
                "text": item["text"],
                "due_at_unix": item["due_at_unix"],
            })
            await attention.upsert(
                title=item["text"],
                severity=AttentionSeverity.FOLLOW_UP,
                source="reminder",
                dedupe_key=f"reminder:{item['id']}",
                payload={"reminder_id": item["id"], "due_at_unix": item["due_at_unix"]},
            )
        observability_instruments.set_queue_depth(
            "reminders_due", len(await reminders.list_open())
        )
        return {"fired": len(fired)}

    async def _expire_overdue_missions() -> dict:
        """P0-EXEC-002 — notice the commands that never came back.

        Swept on the same cadence as reminders because the failure it detects is the same
        shape: something the owner asked for that the system stopped tracking. Without
        this the deadline set at RUNNING would be a column nothing reads.
        """
        expired = await missions.expire_overdue()
        for mission_id in expired:
            await attention.upsert(
                title="VAN never heard back about this",
                severity=AttentionSeverity.BLOCKER,
                source="mission",
                dedupe_key=f"mission-expired:{mission_id}",
                payload={"mission_id": mission_id},
            )
        return {"expired": len(expired)}

    async def _run_retention() -> dict:
        results = await retention.prune()
        audit_prune = await retention.prune_audit_prefix()
        return {
            "deleted": sum(result.deleted for result in results),
            "tables": len(results),
            "audit_pruned": audit_prune["pruned"],
        }

    async def _scan_pki() -> dict:
        report = pki_scan(settings.pki_dir)
        app.state.ops_pki = report
        return {"present": report["present"], "days_remaining": report["days_remaining"]}

    async def _take_backup() -> dict:
        destination = Path(settings.backup_dir) / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        manifest = create_backup(
            database_path=settings.database_path,
            destination=destination,
            project_state_dir=str(Path(__file__).resolve().parents[2] / "docs" / "project-state"),
        )
        return {"destination": str(destination), "entries": len(manifest.entries)}

    async def _mark_stale_intents() -> dict:
        """§20 — surface a standing goal nobody has mentioned, rather than acting on it.

        P2-MEM-001 — `mark_stale` had no caller, so an intent observed once stayed ACTIVE
        forever and "active goal" meant "goal ever stated". STALE is deliberately not
        abandoned: it means ask before assuming this still matters, and only the owner
        abandons a goal.
        """
        marked = await learning.intents.mark_stale()
        return {"marked_stale": marked}

    async def _demote_regressions() -> dict:
        """§41 — a strategy that stopped working loses its promotion, without being asked.

        `StrategyLearning.auto_demote` was written, tested and never called. Promotion
        needs eval evidence and an owner-visible decision; demotion needs neither, because
        the asymmetry is the safety property: it is always safe to trust something less.
        """
        demoted = await learning.strategies.auto_demote()
        for strategy_id in demoted:
            await events.publish("strategy.demoted", {"strategy_id": strategy_id})
        return {"demoted": len(demoted)}

    async def _run_backup_drill() -> dict:
        """P3-OPS-009 — prove the backup restores, not only that it was written.

        Owner decision 10 said "local only, with the drill enabled", and the drill was
        the half with no caller: `ops.backup.drill` was complete and referenced only by
        its own tests. A backup nobody has restored is a hypothesis, and the night it
        matters is the wrong time to test it.

        The drill restores into a scratch directory under the backup root and compares
        row counts, schema version and the audit chain head with the manifest. It never
        touches the live database. A failure raises an attention item rather than only
        logging, because "the backup does not restore" is a thing the owner has to act
        on before the next one is taken.
        """
        workspace = Path(settings.backup_dir) / "drill"
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)
        report = backup_drill(
            database_path=settings.database_path,
            workspace=workspace,
            project_state_dir=str(Path(__file__).resolve().parents[2] / "docs" / "project-state"),
        )
        app.state.ops_backup_drill = report
        if not report["ok"]:
            await attention.upsert(
                title="A backup could not be restored",
                severity=AttentionSeverity.BLOCKER,
                source="ops",
                dedupe_key="backup-drill-failed",
                payload={
                    "differing_tables": report["differing_tables"],
                    "schema_version": report["schema_version"],
                    "verification_ok": report["verification"]["ok"],
                },
            )
        # The scratch copy is a full second database; leaving it behind would double the
        # disk the deployment needs and would be read as a backup by anyone who found it.
        shutil.rmtree(workspace, ignore_errors=True)
        return {
            "ok": report["ok"],
            "tables_compared": report["tables_compared"],
            "rows_compared": report["rows_compared"],
        }

    def _scheduler_jobs() -> tuple[ScheduledJob, ...]:
        jobs = [
            ScheduledJob("reminders.fire_due", settings.reminder_sweep_seconds, _sweep_reminders),
            ScheduledJob(
                "missions.expire_overdue", settings.reminder_sweep_seconds,
                _expire_overdue_missions,
            ),
            ScheduledJob("ops.retention", settings.retention_interval_seconds, _run_retention),
        ]
        if settings.pki_dir:
            jobs.append(ScheduledJob("ops.pki_scan", settings.pki_scan_interval_seconds, _scan_pki))
        if settings.backup_enabled and settings.backup_dir:
            jobs.append(ScheduledJob("ops.backup", settings.backup_interval_seconds, _take_backup))
        if settings.backup_drill_enabled and settings.backup_dir:
            jobs.append(ScheduledJob(
                "ops.backup_drill", settings.backup_drill_interval_seconds, _run_backup_drill,
            ))
        # P1-LEARN-004 — §41 asks for regression auto-demotion and the method had no
        # caller, so a strategy that stopped working kept its promotion for as long as the
        # process ran. Demotion is automatic where promotion is not, deliberately: removing
        # trust from something that stopped working needs no ceremony, granting it does.
        jobs.append(ScheduledJob(
            "learning.auto_demote", settings.retention_interval_seconds, _demote_regressions,
        ))
        jobs.append(ScheduledJob(
            "understanding.mark_stale_intents", settings.retention_interval_seconds,
            _mark_stale_intents,
        ))
        return tuple(jobs)

    scheduler = OpsScheduler(store, _scheduler_jobs())
    started_at = time.monotonic()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # P3-OBS-001 — the gateway emitted no application logs at all. This is the
        # one place that installs the JSON formatter, so every module's logger
        # inherits it instead of each one deciding for itself.
        configure_logging(settings.log_level)
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
        if settings.scheduler_enabled:
            await scheduler.start()
        try:
            yield
        finally:
            await scheduler.stop()

    app = FastAPI(title="VAN Gateway", version="0.5.0-dev", lifespan=lifespan)
    # P3-OBS-001/P3-OBS-002 — outermost, so it measures what the client waited
    # for rather than what the handler took after every other middleware.
    app.add_middleware(MetricsMiddleware)
    app.state.store = store
    app.state.auth = auth
    app.state.auth_throttle = throttle
    app.state.credential_rotation = rotation
    app.state.control_authority = control_authority
    app.state.owner_fact_author = owner_fact_author
    app.state.truth_importer = truth_importer
    app.state.owner_memory = owner_memory
    app.state.learning = learning
    app.state.degraded = degraded
    # Exposed like `degraded`: which jobs a build actually installs is a property of
    # the running app, and a job list that exists only inside a closure is how
    # `learning.auto_demote` went uncalled for as long as it did.
    app.state.scheduler = scheduler
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
    app.state.mission_binder = mission_binder
    app.state.command_missions = command_missions
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
    if browser_stream_grants is not None:
        # Rev 1.5 §§22.2, 22.3 — what Hermes is handed when it drives the owner's
        # browser, and what is destroyed when the owner takes it back.
        agent_grants = AgentGrantService()
        app.state.browser_agent_grants = agent_grants
        downloads_broker = DownloadBroker(store)
        app.state.browser_downloads = downloads_broker
        # §27 — the link report. `BrowserQualityController` was written, correct and
        # called by nothing; this is the caller. The phone measures what only it can see,
        # the Gateway picks the rung, and the target travels back.
        #
        # Built before the interactive router because that router is handed its
        # `forget`: the §27.3 byte accounting and the §27.4 hysteresis are per session,
        # and a controller that outlived its session would report the previous owner's
        # data usage to the next one.
        quality_controllers = QualityControllers()
        app.state.browser_quality = quality_controllers
        app.include_router(build_interactive_router(
            sessions=interactive_sessions,
            control=browser_control_leases,
            grants=browser_stream_grants,
            agent_grants=agent_grants,
            downloads_broker=downloads_broker,
            signal_url=settings.browser_stream_signal_url,
            ice_servers=_parse_ice_servers(settings.browser_stream_ice_servers),
            mission_binder=mission_binder,
            audit=audit,
            on_session_ended=quality_controllers.forget,
        ))
        # §18 — the Hermes-scoped side of the same records. Separate router because
        # it is a different authority, not a different concern: the owner's phone
        # never saw the download happen.
        app.include_router(build_download_report_router(
            broker=downloads_broker,
            sessions=interactive_sessions,
            audit=audit,
        ))
        app.include_router(build_quality_router(
            controllers=quality_controllers,
            sessions=interactive_sessions,
        ))
    # Rev 1.5 §20 — the durable logical session. It holds no command authority: the
    # router delegates to the same POST /v1/commands path the phone has always used, and
    # §20.2 forbids a second one.
    van_sessions = VanHermesSessionService(store, events=events)

    async def _submit_command_through_session(payload: dict, device_id: str) -> dict:
        try:
            request = CommandRequest(**{**payload, "device_id": device_id})
        except ValidationError as exc:
            # A malformed command is the phone's mistake, not the Gateway's fault: it is
            # refused rather than raised. Left as an exception it became a 500, which the
            # client's retry policy treats as "try again" — and the same malformed payload
            # would be retried forever.
            raise SessionDelegateError("command_payload_invalid") from exc
        result = await orchestrator.handle(request)
        return result if isinstance(result, dict) else result.model_dump(mode="json")

    async def _answer_decision_through_session(payload: dict, device_id: str) -> dict:
        """§20.2 — the owner's answer, delivered to the authority that already owns it."""
        decision_id = str(payload.get("decision_id") or "")
        if not decision_id:
            raise SessionDelegateError("decision_id_required")
        if "approved" not in payload:
            # Not defaulted. An absent answer is not a "no", and guessing either way
            # decides something on the owner's behalf that they did not say.
            raise SessionDelegateError("approved_required")
        try:
            record = await decisions.resolve(
                decision_id, approved=bool(payload["approved"])
            )
        except KeyError as exc:
            raise SessionDelegateError("decision_not_found") from exc
        return record.model_dump(mode="json")

    async def _cancel_mission_through_session(payload: dict, device_id: str) -> dict:
        """Stopping your own mission is yours to say — over this carrier too."""
        mission_id = str(payload.get("mission_id") or "")
        if not mission_id:
            raise SessionDelegateError("mission_id_required")
        try:
            mission = await missions.transition(
                mission_id,
                target=MissionState.CANCELLED,
                actor=PrincipalType.OWNER_DEVICE,
                final_outcome="cancelled by owner",
            )
        except MissionError as exc:
            raise SessionDelegateError(str(exc)) from exc
        return {"mission_id": mission.mission_id, "state": mission.state.value}

    async def _message_mission_through_session(payload: dict, device_id: str) -> dict:
        """§2.3 — a note on the record. It does not move the mission by itself."""
        mission_id = str(payload.get("mission_id") or "")
        text = str(payload.get("text") or payload.get("message") or "")
        if not mission_id or not text:
            raise SessionDelegateError("mission_id_and_text_required")
        if await missions.get(mission_id) is None:
            raise SessionDelegateError("mission_unknown")
        event = await missions.record_event(
            mission_id=mission_id,
            event_type=MissionEventType.MISSION_CREATED,
            actor=PrincipalType.OWNER_DEVICE,
            summary=text[:500],
            severity="INFO",
        )
        return {"event_id": event.event_id, "recorded": True}

    # Rev 1.5 §20.2 — all four kinds the router knows, delegated to the authorities that
    # already exist.
    #
    # Three of these were left unwired, and the effect was not a missing feature. The
    # router admitted the envelope into §20.12's table *before* discovering it had nobody
    # to hand it to, so "cancel this mission" sent over the durable session was recorded,
    # refused, and — because its idempotency key was now taken — answered ALREADY_KNOWN
    # on every retry. Acknowledged, never performed, and unrepeatable.
    session_router = SessionRouter(
        van_sessions,
        SessionDelegates(
            submit_command=_submit_command_through_session,
            answer_decision=_answer_decision_through_session,
            cancel_mission=_cancel_mission_through_session,
            message_mission=_message_mission_through_session,
        ),
    )

    # Rev 1.5 §21.16 — the spoken half of an answer, so a reconnect does not start it
    # again from the beginning. Held in memory deliberately: a restart loses the text of an
    # answer in flight, while the command that produced it and its result are both durable.
    speech_streams = SpeechStreamService()
    app.state.speech_streams = speech_streams

    async def _resume_snapshot(
        *, device_id: str, van_session_id: str, pending_command_ids: list[str]
    ) -> dict:
        """§20.11 — what the Gateway authoritatively knows about what the client lost.

        Answered from two places, because the Gateway knows a thing in two ways and the
        client cannot tell which applies. A mission is the richer answer and is preferred.
        Failing that, `van_session_messages` is the §20.12 admission table — the record
        that makes a resubmission safe — and a row in it means the Gateway holds this
        message whether or not anything downstream opened a mission for it.

        Consulting only the mission table made every answer for an admitted-but-missionless
        message `UNKNOWN`, which the client correctly reads as *resend*. The command was
        not lost, but it was re-sent on every single resume for the life of the session,
        because nothing the client could ever receive would settle it.

        `UNKNOWN` is emitted rather than the key omitted: the client treats both as
        resend, and sending it makes "I looked and I do not have this" a statement the
        client can be tested against rather than an absence it has to infer.
        """
        states: dict[str, str] = {}
        for identity in pending_command_ids[:50]:
            mission = await command_missions.existing_for_command(identity)
            if mission is not None:
                states[identity] = mission.state.value
                continue
            # The client asks by command id when it has one and by message id otherwise,
            # and a resubmitted envelope carries both. Matching either is what lets one
            # question be answered without the two sides agreeing in advance which
            # identity a given command happens to have.
            row = await store.fetchone(
                """
                SELECT admitted_state FROM van_session_messages
                 WHERE van_session_id = ? AND (command_id = ? OR message_id = ?)
                 LIMIT 1
                """,
                (van_session_id, identity, identity),
            )
            states[identity] = row["admitted_state"] if row is not None else "UNKNOWN"
        cursor_row = await store.fetchone(
            "SELECT last_seq FROM event_cursors WHERE device_id = ?", (device_id,)
        )
        return {
            "command_states": states,
            "authoritative_event_cursor": int(cursor_row["last_seq"]) if cursor_row else 0,
            # §21.16 — where the owner actually got to in the spoken answer. Absent when
            # there is nothing in flight, which is the ordinary case.
            "response_state": speech_streams.response_state(device_id),
        }

    app.include_router(build_session_router(
        sessions=van_sessions, router=session_router, events=events,
        resume_snapshot=_resume_snapshot,
    ))
    # Rev 1.5 §§0D.3, 5.7 — the owner-device binding.
    #
    # The policy is configuration because the signing certificate differs between a debug
    # build and the owner's release build, and pinning the debug one would mean the
    # production APK could never enrol. Absent configuration disables enrolment rather than
    # weakening it: §0E.1 D5 forbids a downgrade to a weaker binding, and an unconfigured
    # deployment is exactly where one would be tempting.
    owner_device_bindings = (
        OwnerDeviceBindingService(
            store,
            AttestationPolicy(
                expected_package=settings.owner_device_package,
                expected_signing_cert_sha256=settings.owner_device_signing_cert_sha256,
                allowed_root_fingerprints=frozenset(
                    f.strip() for f in settings.owner_device_attestation_roots.split(",") if f.strip()
                ),
            ),
        )
        if settings.owner_device_signing_cert_sha256
        else None
    )
    connectivity_config = ConnectivityConfigService(
        store,
        private_pem=(
            _read_stream_signing_key(settings.connectivity_signing_key_file)
            if settings.connectivity_signing_key_file else None
        ),
        kid=settings.connectivity_signing_kid,
    )
    app.state.owner_device_bindings = owner_device_bindings
    app.state.connectivity_config = connectivity_config
    app.state.van_sessions = van_sessions
    app.state.session_router = session_router
    app.state.interactive_sessions = interactive_sessions
    app.state.browser_control_leases = browser_control_leases
    app.state.browser_stream_grants = browser_stream_grants
    app.include_router(mission_api.router)
    app.include_router(understanding_api.router)

    def control_scope_for(method: str, path: str) -> ControlScope | None:
        """Which privileged scope a route belongs to, or None if it is not one.

        P0-SEC-001 — one token reached all of these. Naming the scope per route is what
        makes "the Hermes runtime may drive automation but may not enrol a device"
        expressible at all.
        """
        if path.startswith("/v1/runtime/"):
            return ControlScope.RUNTIME
        # P2-CU-001 adds the computer-use fabric's health on the same terms as the other
        # two: it reports which surfaces have a worker, which is runtime shape.
        if path in {
            "/v1/automation/health", "/v1/browser/health", "/v1/computer-use/health",
        }:
            return ControlScope.RUNTIME
        # Gate 11. Device telemetry is excluded on purpose: its producer is the
        # owner's paired device, so it authenticates as a device like every other
        # device-produced payload, and an operator credential is not required to
        # report a frame time.
        if path.startswith("/v1/observability/") and path != "/v1/observability/device-telemetry":
            return ControlScope.OBSERVABILITY
        if path.startswith("/v1/automation/"):
            return ControlScope.AUTOMATION
        if path.startswith("/v1/missions") or path in ("/v1/needs-you", "/v1/activity",
                                                        "/v1/capabilities/status"):
            if method == "GET":
                return None
            return None if (path.endswith("/cancel") or path.endswith("/message")) else ControlScope.MISSIONS
        if path.startswith("/v1/understanding") or path.startswith("/v1/permissions") or (
            path in ("/v1/technology-radar", "/v1/eval", "/v1/autonomy")
        ):
            return ControlScope.UNDERSTANDING if path == "/v1/understanding/observe" else None
        if is_session_owner_route(path):
            # §20 — the logical session carries the owner's own commands, so it
            # authenticates as the owner's device. Same predicate-with-one-reader shape as
            # the interactive browser routes below.
            return None
        if is_interactive_browser_owner_route(path):
            # Rev 1.5 §6.1 — the owner's phone creates, heartbeats and closes its own
            # browser session, so these are device-authenticated rather than Hermes-only.
            # One predicate, two readers: a route classified here and not below would fall
            # through to owner-device authentication on a Hermes surface, which is the hole
            # P0-SEC-001 closed and P2-GOOG-004 nearly reopened.
            return None
        if path.startswith("/v1/browser/"):
            return None if method == "GET" else ControlScope.BROWSER
        if method == "PUT" and path.startswith("/v1/projects/") and path.endswith("/truth"):
            return ControlScope.PROJECTS
        if method == "POST" and path in {
            "/v1/devices/bootstrap/create", "/v1/devices/rebind",
            "/v1/devices/provisioning-payload",
        }:
            # ADR-RB-026 — minting an enrolment credential, and replacing the owner's
            # device, are the same authority as enrolment itself.
            return ControlScope.DEVICE_ENROLMENT
        if method == "POST" and path in {"/v1/devices/enroll", "/v1/devices/pairing-ticket"}:
            # The scope that can mint owner-device authority, and the reason this module
            # exists. Not granted to the legacy token.
            return ControlScope.DEVICE_ENROLMENT
        if method == "POST" and path.startswith("/v1/devices/") and path.endswith("/revoke"):
            return ControlScope.DEVICE_ENROLMENT
        if method == "POST" and path == "/v1/trading/halt":
            return ControlScope.TRADING
        if method == "POST" and path.startswith("/v1/trading/tickets/") and path.endswith("/confirm"):
            return ControlScope.TRADING
        if path in GOOGLE_CONTROL_ROUTES:
            return ControlScope.GOOGLE
        if path.startswith("/v1/google/jobs/"):
            return ControlScope.GOOGLE
        return None

    def requires_device_proof(method: str, path: str) -> bool:
        """ADR-RB-025 — which owner requests must prove possession of the bound key.

        Reading a session or a browser tab list is not on this list; *changing* something
        is. The distinction matters because a proof costs a hardware-key signature on the
        phone, and demanding one for a polling read would put a Keystore operation in the
        battery path for no security gain.

        `require_proof` existed in `OwnerDeviceBindingService` before this predicate did,
        and nothing called it. A binding nobody checks is a fingerprint in a table: a
        stolen device token would have worked on every route, with or without a bound
        device, and `/v1/device-binding/status` would still have reported `bound: true`.
        """
        if method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return False
        if path in {"/v1/devices/bootstrap/challenge", "/v1/devices/bootstrap/attest"}:
            # The enrolment itself. There is no bound key yet to prove possession of.
            return False
        return (
            is_interactive_browser_owner_route(path)
            or is_session_owner_route(path)
            or path == "/v1/commands"
        )

    async def enforce_device_proof(request: Request, device_id: str) -> JSONResponse | None:
        """Refuse a privileged request from a bound device that did not sign it.

        Fail-closed where it can be: once a device is bound, a missing or invalid proof is
        a refusal, and there is no header a caller can omit to get the old behaviour back.

        For an *unbound* device this returns None and the token alone carries the request,
        because a gateway that already has paired devices would otherwise lock its owner
        out the moment this shipped. That downgrade is visible rather than silent:
        `/v1/device-binding/status` reports `bound: false`, and `settings.require_device_
        binding` turns the fallback off for a deployment that has finished enrolling.
        """
        if owner_device_bindings is None:
            if settings.require_device_binding:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "owner_device_binding_unconfigured"},
                )
            return None
        # Once *any* device is bound, the owner has one device and this is not a question
        # about the caller: a second paired phone asking to be treated as unbound is the
        # downgrade §0E.1 D5 forbids. A first version asked `for_device(device_id)`, so a
        # second paired device skipped the gate entirely by never having enrolled — the
        # proof was mandatory only for the device that had already proved itself.
        binding = await owner_device_bindings.active()
        if binding is None:
            if settings.require_device_binding:
                return JSONResponse(status_code=403, content={"detail": "device_not_bound"})
            return None
        if binding.device_id != device_id:
            return JSONResponse(
                status_code=403, content={"detail": "device_not_owner_device"}
            )

        signature_b64 = request.headers.get("X-Van-Device-Proof", "")
        issued_at_raw = request.headers.get("X-Van-Device-Proof-Issued-At", "")
        if not signature_b64 or not issued_at_raw:
            return JSONResponse(
                status_code=401, content={"detail": "device_proof_required"}
            )
        try:
            signature = base64.b64decode(signature_b64, validate=True)
            issued_at_ms = int(issued_at_raw)
        except (ValueError, binascii.Error):
            return JSONResponse(
                status_code=400, content={"detail": "device_proof_malformed"}
            )

        # The handler still needs this body after we have read it.
        #
        # A first version followed `await request.body()` with a hand-rolled replay that
        # reassigned `request._receive`. A mutation deleting that replay changed nothing,
        # which is how it was found to be dead: Starlette's `BaseHTTPMiddleware` already
        # wraps the request in a `_CachedRequest` whose documented behaviour is that a body
        # read in `dispatch` is cached and passed downstream. Poking a private attribute to
        # re-implement that was two mechanisms for one job, and the one I wrote was the
        # one nothing exercised.
        #
        # The dependency is real, so it is tested rather than assumed: a proved POST must
        # come back with the field it sent, which fails if this ever stops being true.
        body = await request.body()

        try:
            await owner_device_bindings.require_proof(
                device_id=device_id,
                signature=signature,
                method=request.method,
                path=request.url.path,
                issued_at_ms=issued_at_ms,
                body=body,
            )
        except DeviceBindingError as exc:
            return JSONResponse(status_code=401, content={"detail": exc.reason})
        request.state.van_device_proved = True
        return None

    def throttled_response(detail: str, locked: Throttled) -> JSONResponse:
        """429 with the one header a client can actually act on."""
        return JSONResponse(
            status_code=429,
            content={"detail": detail, "retry_after_seconds": locked.retry_after_seconds},
            headers={"Retry-After": str(locked.retry_after_seconds)},
        )

    # `internal_control_route` used to live here: a second copy of the route
    # classification that once let the internal token bypass the device gate. P0-SEC-001
    # replaced that mechanism with `control_scope_for` plus scoped credentials, and left
    # this behind. A repository-wide search finds no caller — not in the middleware, not in
    # a handler, not in a test — so it has been decided-by-nobody since that closure.
    #
    # It was deleted rather than updated when the interactive browser routes were added.
    # A mutation removing the exemption I had just written into it changed nothing, which
    # is how it was found: a guard whose removal is undetectable is not protecting
    # anything. Keeping it would have meant two classifiers to edit and one of them
    # silently ignored, which is exactly how the Rev 1.3 drift this programme closed began.

    @app.middleware("http")
    async def require_ingress_auth(request: Request, call_next):
        if request.method == "POST" and request.url.path == "/v1/devices/pair":
            return await call_next(request)
        # ADR-RB-026 — a phone being enrolled has no device token yet, by definition. These
        # two are protected by the single-use bootstrap token instead, which is the whole
        # credential: short-lived, hashed at rest, and spent by the enrolment it authorises.
        if request.method == "POST" and request.url.path in {
            "/v1/devices/bootstrap/challenge", "/v1/devices/bootstrap/attest",
        }:
            return await call_next(request)
        if request.method == "GET" and request.url.path.startswith("/v1/trading/oauth/") and request.url.path.endswith("/callback"):
            return await call_next(request)

        # Privileged local Hermes control uses an independent machine credential.
        scope = control_scope_for(request.method, request.url.path)
        presented_internal = request.headers.get("X-Van-Internal-Token", "")
        if scope is not None:
            if control_authority.permits(presented_internal, scope):
                request.state.van_control_scope = scope.value
                return await call_next(request)
            if not control_authority.configured:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "internal_control_token_unconfigured"},
                )
            if presented_internal.strip():
                # P0-SEC-001. A wrong or under-scoped credential used to fall through to
                # ingress plus device authentication, so a route declared Hermes-only was
                # reachable with an owner device token. The check is terminal now, and
                # names the scope so an operator can tell "wrong credential" from "this
                # credential does not reach that surface".
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "internal_control_unauthorized",
                        "required_scope": scope.value,
                    },
                )
            # Nothing was presented at all. The ingress gate below answers first, so an
            # unauthenticated stranger learns nothing about which routes exist; the scope
            # check then refuses, still without ever reaching device authentication.

        configured = settings.ingress_token.strip()
        presented = request.headers.get("X-Van-Ingress-Token", "")
        if not configured:
            return JSONResponse(status_code=503, content={"detail": "ingress_auth_unconfigured"})
        if not presented or not hmac.compare_digest(configured, presented):
            # P1-SEC-007, soft posture: the credential was already judged wrong, so counting
            # this failure can never keep a correct token out. Past the policy, further wrong
            # tokens are answered flat and the device lookup below is never reached.
            try:
                throttle.fail("ingress_token", GLOBAL_SUBJECT)
            except Throttled as locked:
                return throttled_response("ingress_auth_throttled", locked)
            return JSONResponse(status_code=401, content={"detail": "ingress_auth_failed"})
        throttle.record_success("ingress_token", GLOBAL_SUBJECT)

        # Health is the only ingress-only route, used by local/tunnel probes.
        if request.method == "GET" and request.url.path == "/health":
            return await call_next(request)

        if scope is not None:
            # Reached only when no internal credential was presented. An owner device
            # token is not an answer to a privileged control route, so this is where the
            # fall-through used to happen and no longer does.
            return JSONResponse(
                status_code=403,
                content={"detail": "internal_control_unauthorized", "required_scope": scope.value},
            )

        try:
            device = await auth.require_access_token(request.headers.get("X-Van-Device-Token", ""))
        except AuthError:
            try:
                throttle.fail("device_token", GLOBAL_SUBJECT)
            except Throttled as locked:
                return throttled_response("device_access_throttled", locked)
            return JSONResponse(status_code=401, content={"detail": "device_access_denied"})
        throttle.record_success("device_token", GLOBAL_SUBJECT)
        request.state.van_device_id = device.device_id
        if requires_device_proof(request.method, request.url.path):
            refusal = await enforce_device_proof(request, device.device_id)
            if refusal is not None:
                return refusal
        return await call_next(request)

    def require_internal_control(
        x_van_internal_token: str | None,
        scope: ControlScope | None = None,
    ) -> None:
        """Handler-level check, which must agree with the middleware's.

        P0-SEC-001 — this compared against the single internal token, so a route the
        middleware had already let through on a scoped credential would then be refused
        here. It now asks the same authority the same question. `scope` defaults to the
        one the route's path implies, so existing callers keep working.
        """
        if not control_authority.configured:
            raise HTTPException(status_code=503, detail="internal_control_token_unconfigured")
        if scope is None:
            scope = ControlScope.RUNTIME
        if not control_authority.permits(x_van_internal_token, scope):
            raise HTTPException(status_code=403, detail="internal_control_unauthorized")

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
            # P2-SEC-008 — credential age, so a token older than its policy says so
            # instead of nothing saying anything. Reporting only: rotating the ingress
            # token unattended would lock the owner out far more reliably than it would
            # stop anybody.
            "credentials": await rotation.report(
                {
                    "ingress_token": settings.ingress_token,
                    "internal_control_token": settings.internal_control_token,
                    "automation_grant_signing_key": settings.automation_grant_signing_key,
                }
            ),
            "enrolment_grants": await auth.expiring_grants(),
        }

    @app.post("/v1/devices/pairing-ticket")
    async def create_pairing_ticket(
        body: PairingTicketCreate,
        x_van_internal_token: str | None = Header(default=None),
    ):
        require_internal_control(x_van_internal_token, ControlScope.DEVICE_ENROLMENT)
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
        # P1-SEC-007, hard posture. This is the only unauthenticated route in the gateway
        # and the only credential that mints owner-device authority, so the lockout is
        # checked before the ticket is looked at. See van_gateway/auth/throttle.py for why
        # this surface, and only this surface, accepts the availability cost.
        try:
            throttle.check("pairing", GLOBAL_SUBJECT)
        except Throttled as locked:
            raise HTTPException(
                status_code=429,
                detail="pairing_throttled",
                headers={"Retry-After": str(locked.retry_after_seconds)},
            ) from locked
        try:
            result = await auth.pair_device(
                body.pairing_token,
                body.device_id,
                body.device_secret,
                body.public_key_pem,
                body.label,
            )
        except AuthError as exc:
            # `already_enrolled` and `device_revoked` mean the ticket was genuine, so they
            # are a client mistake, not a guess, and must not count toward the lockout.
            if exc.code not in {"already_enrolled", "device_revoked"}:
                throttle.record_failure("pairing", GLOBAL_SUBJECT)
            code = 409 if exc.code in {"already_enrolled", "device_revoked"} else 400
            raise HTTPException(status_code=code, detail=exc.message) from exc
        throttle.record_success("pairing", GLOBAL_SUBJECT)
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
        require_internal_control(x_van_internal_token, ControlScope.DEVICE_ENROLMENT)
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
        require_internal_control(x_van_internal_token, ControlScope.DEVICE_ENROLMENT)
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

    def _require_binding_service() -> OwnerDeviceBindingService:
        if owner_device_bindings is None:
            # §0E.1 D5 — no configuration means no enrolment, not a weaker one.
            raise HTTPException(status_code=503, detail="owner_device_binding_unconfigured")
        return owner_device_bindings

    @app.post("/v1/devices/bootstrap/create")
    async def create_bootstrap(body: BootstrapCreateBody):
        """ADR-RB-026 — the installer's one-time credential, for the deployment pipeline."""
        token, challenge = await _require_binding_service().create_bootstrap_token(note=body.note)
        await audit.record(
            result="ok", capability="device.bootstrap.create", after={"note": body.note}
        )
        return {"bootstrap_token": token, "attestation_challenge": challenge}

    @app.post("/v1/devices/provisioning-payload")
    async def create_provisioning_payload(
        body: ProvisioningPayloadBody,
        x_van_internal_token: str | None = Header(default=None),
    ):
        """ADR-RB-026 — the installer's one call, and the owner types nothing.

        One call rather than three, because the alternative is an installer that mints a
        token, reads a challenge and assembles a document itself — and an installer that
        assembles the document decides its expiry. §0D.2's rule survives only if the
        short-lived, single-use, signed envelope is built by the party that also enforces
        those three properties.
        """
        require_internal_control(x_van_internal_token, ControlScope.DEVICE_ENROLMENT)
        if not connectivity_config.private_pem or not connectivity_config.kid:
            # No signing key means no provisioning, not an unsigned one. A payload the
            # device cannot verify is a payload it must refuse, and handing the installer
            # one would make the failure look like the phone's.
            raise HTTPException(status_code=503, detail="connectivity_signing_unconfigured")
        token, challenge = await _require_binding_service().create_bootstrap_token(
            note=body.note
        )
        # Both credentials, minted together, because provisioning is one act. A device
        # that paired but did not bind would hold working tokens and no hardware identity,
        # which is §0D.3's failure exactly: an APK copied to another handset would work.
        ticket = await auth.create_pairing_ticket(body.note or "owner-device")
        active = await connectivity_config.active()
        try:
            payload = build_provisioning_payload(
                gateway_url=body.gateway_url,
                pairing_token=ticket.token,
                bootstrap_token=token,
                attestation_challenge=challenge,
                manifest_version=active.manifest_version if active else 0,
            )
            signature = sign_provisioning_payload(
                payload, private_pem=connectivity_config.private_pem
            )
        except ConnectivityError as exc:
            raise HTTPException(status_code=400, detail=exc.reason) from exc
        await audit.record(
            result="ok", capability="device.provisioning.issue",
            # The token is not recorded. An audit row that carried it would be a second
            # copy of the one credential that can bind a new device, in the table a backup
            # copies — which is the reason `create_bootstrap_token` only stores its hash.
            after={"provisioning_id": payload["provisioning_id"], "note": body.note},
        )
        return JSONResponse(
            {"payload": payload, "signature": signature, "kid": connectivity_config.kid},
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/v1/devices/bootstrap/challenge")
    async def bootstrap_challenge(body: BootstrapChallengeBody):
        """The challenge this enrolment must be attested against."""
        try:
            challenge = await _require_binding_service().challenge_for(body.token)
        except DeviceBindingError as exc:
            raise HTTPException(status_code=403, detail=exc.reason) from exc
        return {"attestation_challenge": challenge}

    @app.post("/v1/devices/bootstrap/attest")
    async def bootstrap_attest(body: BootstrapAttestBody):
        """Bind the owner's device, or refuse and record why."""
        try:
            extension = base64.b64decode(body.attestation_extension_b64, validate=True)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="attestation_not_base64") from exc
        try:
            binding = await _require_binding_service().bind(
                token=body.token,
                device_id=body.device_id,
                public_key_pem=body.public_key_pem,
                attestation_extension=extension,
                attestation_root_fingerprint=body.attestation_root_fingerprint,
                os_version=body.os_version,
                os_patch_level=body.os_patch_level,
            )
        except DeviceBindingError as exc:
            await audit.record(
                result="refused", device_id=body.device_id,
                capability="device.bootstrap.attest", error_class=exc.reason,
            )
            raise HTTPException(status_code=403, detail=exc.reason) from exc
        await audit.record(
            result="ok", device_id=body.device_id, capability="device.bootstrap.attest",
            after={"fingerprint": binding.device_key_fingerprint},
        )
        return {
            "binding_id": binding.binding_id,
            "device_id": binding.device_id,
            "device_key_fingerprint": binding.device_key_fingerprint,
            "key_security_level": binding.key_security_level,
            "verified_boot_state": binding.verified_boot_state,
        }

    @app.get("/v1/device-binding/status")
    async def device_binding_status(request: Request):
        """What this device's binding looks like from the Gateway's side."""
        device_id = getattr(request.state, "van_device_id", None)
        if not device_id:
            raise HTTPException(status_code=403, detail="device_identity_required")
        if owner_device_bindings is None:
            return {"configured": False, "bound": False, "reason": "binding_unconfigured"}
        binding = await owner_device_bindings.for_device(device_id)
        if binding is None:
            return {"configured": True, "bound": False}
        return {
            "configured": True,
            "bound": binding.status.value == "ACTIVE",
            "status": binding.status.value,
            "device_key_fingerprint": binding.device_key_fingerprint,
            "key_security_level": binding.key_security_level,
            "verified_boot_state": binding.verified_boot_state,
            "bound_at_ms": binding.bound_at_ms,
            "last_proof_at_ms": binding.last_proof_at_ms,
        }

    @app.post("/v1/devices/rebind")
    async def rebind_owner_device(body: RebindBody):
        """§0D.3's recovery path: revoke the current binding and issue one enrolment token.

        Administrative on purpose. A device that could rebind on its own behalf would be a
        way to become the owner's phone by asserting that it is.
        """
        token, challenge = await _require_binding_service().rebind_token(reason=body.reason)
        await audit.record(
            result="ok", capability="device.rebind", after={"reason": body.reason}
        )
        return {"bootstrap_token": token, "attestation_challenge": challenge}

    @app.get("/v1/connectivity/manifest")
    async def connectivity_manifest(request: Request, known_version: int = 0):
        """ADR-RB-027 — a newer signed manifest when there is one, nothing when there is not."""
        device_id = getattr(request.state, "van_device_id", None)
        if not device_id:
            raise HTTPException(status_code=403, detail="device_identity_required")
        served = await connectivity_config.serve(known_version=known_version)
        if served is None:
            return {"current": True, "manifest": None}
        return {"current": False, **served}

    @app.get("/v1/commands/{command_id}")
    async def command_status(command_id: str, request: Request):
        """What happened to a command the owner sent.

        P0-EXEC-002 — this returned 404 for every command. The audit's probe drove ten
        intents through POST /v1/commands, got `accepted` for all ten, and then had nowhere
        to ask what became of them; the terminal owner-visible status was "accepted"
        forever. The device could not show a completion because there was nothing to read.

        Device-authenticated and scoped to the calling device: a command's status names
        what the owner asked for, and one paired device has no business reading another's.
        """
        device_id = getattr(request.state, "van_device_id", None)
        mission = await command_missions.existing_for_command(command_id)
        rows = await store.fetchall(
            "SELECT device_id, result, failure_reason, created_at_unix FROM audit "
            "WHERE command_id = ? ORDER BY COALESCE(chain_seq, 0) DESC LIMIT 1",
            (command_id,),
        )
        if mission is None and not rows:
            raise HTTPException(status_code=404, detail="command_unknown")
        if rows and device_id and rows[0]["device_id"] and rows[0]["device_id"] != device_id:
            # Not 403: that would confirm the command exists to a device that should not
            # know it does.
            raise HTTPException(status_code=404, detail="command_unknown")

        if mission is not None:
            status = wire_status.from_mission_state(mission.state.value)
            return {
                "command_id": command_id,
                "correlation_id": correlation_for_command(command_id),
                "mission_id": mission.mission_id,
                "mission_state": mission.state.value,
                "owner_status": status.value,
                "sentence": owner_status.SENTENCE[status],
                "needs_you": status in owner_status.NEEDS_OWNER,
                "finished": status in owner_status.FINISHED,
                "final_outcome": mission.final_outcome,
                "verification_state": mission.verification_state.value,
                "deadline_ms": mission.deadline_ms,
                "updated_at_ms": mission.updated_at_ms,
            }

        # Refused before a mission was opened: the audit row is the whole story.
        status = wire_status.from_command_result(str(rows[0]["result"]))
        return {
            "command_id": command_id,
            "correlation_id": correlation_for_command(command_id),
            "mission_id": None,
            "mission_state": None,
            "owner_status": status.value,
            "sentence": owner_status.SENTENCE[status],
            "needs_you": status in owner_status.NEEDS_OWNER,
            "finished": status in owner_status.FINISHED,
            "final_outcome": rows[0]["failure_reason"],
            "verification_state": None,
            "deadline_ms": None,
            "updated_at_ms": int(rows[0]["created_at_unix"]) * 1000,
        }

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
        require_internal_control(x_van_internal_token, ControlScope.PROJECTS)
        if project_id not in projects.known_projects():
            raise HTTPException(status_code=404, detail="unknown_project")
        body_project = body.truth.get("project_id") if isinstance(body.truth, dict) else None
        if body_project is not None and str(body_project) != project_id:
            raise HTTPException(status_code=400, detail="truth_project_mismatch")
        await projects.cache_truth(project_id, body.truth, body.truth_sha, body.repo_sha)
        # P0-CTX-002 — the PROJECT_TRUTH tier had no writer, so it was empty in every
        # deployment while retrieval happily excluded the one tier that did. Importing
        # here rather than on a separate route means the facts and the cache cannot
        # disagree about which SHA is current.
        loaded = await projects.load_truth(project_id)
        try:
            imported = await truth_importer.import_truth(
                project_id, {**loaded, "truth_sha": body.truth_sha}
            )
        except ContextAuthoringError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {**loaded, "facts_imported": len(imported)}

    @app.post("/v1/context/facts")
    async def state_owner_fact(request: Request, body: OwnerFactBody):
        """The owner saying something about themselves, at CANONICAL_OWNER.

        P0-CTX-002 — the only production writer was the Hermes admission route, correctly
        limited to INFERRED/MODEL_DERIVED, which is the one tier retrieval excludes. So
        the authoritative tiers were empty everywhere. This is the writer that fills them,
        and it is device-authenticated because a canonical fact about the owner can only
        come from the owner.
        """
        device_id = getattr(request.state, "van_device_id", None)
        if not device_id:
            raise HTTPException(status_code=403, detail="device_identity_required")
        record = await owner_fact_author.state(
            device_id=device_id,
            subject=body.subject,
            predicate=body.predicate,
            value=body.value,
            scope=body.scope,
            valid_until_ms=body.valid_until_ms,
        )
        await audit.record(
            result="ok", device_id=device_id, capability="context.owner_fact.state",
            after={"subject": body.subject, "predicate": body.predicate, "scope": body.scope},
        )
        return record.model_dump(mode="json")

    @app.get("/v1/context/memory")
    async def owner_memory_inventory(request: Request):
        """P2-MEM-002 — what VAN holds about the owner, before deciding to end it."""
        device_id = getattr(request.state, "van_device_id", None)
        if not device_id:
            raise HTTPException(status_code=403, detail="device_identity_required")
        return await owner_memory.inventory()

    @app.delete("/v1/context/memory")
    async def owner_memory_forget(request: Request, store: str | None = None):
        """Delete what VAN has concluded about the owner.

        P2-MEM-002 — only owner_facts and owner_context_edges could be erased. The
        cognitive model, the reasoning ledger, the growth ledger, strategic memory,
        decision fingerprints, the shared vocabulary and the intent graph all accumulated
        owner-derived material with no way out.
        """
        device_id = getattr(request.state, "van_device_id", None)
        if not device_id:
            raise HTTPException(status_code=403, detail="device_identity_required")
        if store:
            try:
                removed = await owner_memory.forget_store(store)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            result = {"removed": {store: removed}}
        else:
            result = await owner_memory.forget_all()
        await audit.record(
            result="ok", device_id=device_id, capability="context.memory.forget",
            after={"removed": result["removed"]},
        )
        return result

    @app.get("/v1/context/export")
    async def owner_context_export(request: Request):
        """P2-CTX-003 — everything VAN holds about the owner, not a count of it.

        /v1/context/memory already reported how many rows each store held. That is the
        wrong half of the answer: the owner could see that VAN had concluded 47 things
        about how they work and could delete all 47, without ever being allowed to read
        one. This is an owner route for the same reason the erasure is — the person the
        data describes does not ask an operator for permission to see it.
        """
        device_id = getattr(request.state, "van_device_id", None)
        if not device_id:
            raise HTTPException(status_code=403, detail="device_identity_required")
        exported = await context_lifecycle.export()
        await audit.record(
            result="ok", device_id=device_id, capability="context.export",
            after={
                store: detail["rows_exported"]
                for store, detail in exported["stores"].items()
            },
        )
        return exported

    @app.get("/v1/context/history")
    async def owner_context_history(
        request: Request, subject: str, predicate: str, scope: str = "global"
    ):
        """P2-CTX-003 — what VAN believed before, and what changed its mind.

        Unauditable before migration 25: admit_fact closed the superseded record's validity
        window and dropped the link, so a correction and two independent expiries left
        identical rows.
        """
        device_id = getattr(request.state, "van_device_id", None)
        if not device_id:
            raise HTTPException(status_code=403, detail="device_identity_required")
        return await context_lifecycle.history(
            subject=subject, predicate=predicate, scope=scope
        )

    @app.get("/v1/context/conflicts")
    async def owner_context_conflicts(request: Request):
        """P2-CTX-003 — what VAN holds two contradictory answers to.

        resolve_requirement has always detected these, but only for a claim something
        asked about. A contradiction nothing queries was held silently. VAN reports both
        sides and does not choose: picking between two things the owner is recorded as
        having said is not a retrieval decision.
        """
        device_id = getattr(request.state, "van_device_id", None)
        if not device_id:
            raise HTTPException(status_code=403, detail="device_identity_required")
        return await context_lifecycle.conflicts()

    @app.delete("/v1/context/facts")
    async def forget_owner_fact(
        request: Request, subject: str, predicate: str, scope: str = "global"
    ):
        """P2-MEM-002 — the owner's own way to end a fact they stated."""
        device_id = getattr(request.state, "van_device_id", None)
        if not device_id:
            raise HTTPException(status_code=403, detail="device_identity_required")
        ended = await owner_fact_author.forget(subject=subject, predicate=predicate, scope=scope)
        await audit.record(
            result="ok", device_id=device_id, capability="context.owner_fact.forget",
            after={"subject": subject, "predicate": predicate, "ended": ended},
        )
        return {"subject": subject, "predicate": predicate, "scope": scope, "ended": ended}

    # There is deliberately no route that swaps the live Google transport for a fake.
    # /v1/google/test-transport used to do exactly that on the running production app, with
    # no undo route (finding P2-SEC-009). Tests install a fake transport directly on
    # app.state.google, which is where that capability belongs. tools/ci/maturity_gate.py
    # fails CI if the route reappears.
    @app.get("/v1/google/gmail/search")
    async def gmail_search(q: str, x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token, ControlScope.GOOGLE)
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
        require_internal_control(x_van_internal_token, ControlScope.GOOGLE)
        try:
            return await google.gmail_send(draft_id, action_class=ActionClass.A4, approved=approved)
        except GoogleAuthError as exc:
            code = 403 if str(exc) == "approval_required" else 503
            raise HTTPException(status_code=code, detail=str(exc)) from exc

    # P2-GOOG-004 — six capabilities with a transport, a service method and no way in.
    #
    # gmail_draft, calendar_agenda, calendar_reschedule, drive_search, contacts_resolve and
    # tasks_list were implemented end to end in google/transport.py and google/service.py
    # and reachable from nothing. The mesh reported them as capabilities; the component
    # ledger recorded three entries of NO_ROUTE against them. A capability whose only caller
    # is its own test is not a capability the owner has.
    #
    # Each mirrors gmail_search exactly: internal control at the GOOGLE scope, and
    # GoogleAuthError to 503 because an absent or expired credential is VAN being unable
    # rather than the caller being wrong. No new authority is introduced anywhere.

    @app.post("/v1/google/gmail/draft")
    async def gmail_draft(
        thread_id: str, body: str, x_van_internal_token: str | None = Header(default=None)
    ):
        """A draft is written, not sent, which is why it is not gated like a send.

        gmail_send is A4 and demands an owner approval bound to the command. Drafting
        leaves something the owner can read and discard; gating it the same way would train
        them to approve without reading, and the approval that matters is the one on the
        send.
        """
        require_internal_control(x_van_internal_token, ControlScope.GOOGLE)
        try:
            return await google.gmail_draft(thread_id, body)
        except GoogleAuthError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/v1/google/calendar/agenda")
    async def calendar_agenda(x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token, ControlScope.GOOGLE)
        try:
            return {"events": await google.calendar_agenda()}
        except GoogleAuthError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/v1/google/calendar/reschedule")
    async def calendar_reschedule(
        event_id: str,
        new_start_unix: int,
        approved: bool = False,
        x_van_internal_token: str | None = Header(default=None),
    ):
        """Moving something in the owner's calendar needs their approval.

        The service already refuses without it. The route passes the flag rather than
        deciding, so there is one place that says what rescheduling costs.
        """
        require_internal_control(x_van_internal_token, ControlScope.GOOGLE)
        try:
            return await google.calendar_reschedule(event_id, new_start_unix, approved=approved)
        except GoogleAuthError as exc:
            code = 403 if str(exc) == "approval_required" else 503
            raise HTTPException(status_code=code, detail=str(exc)) from exc

    @app.get("/v1/google/drive/search")
    async def drive_search(q: str, x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token, ControlScope.GOOGLE)
        try:
            return {"files": await google.drive_search(q)}
        except GoogleAuthError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/v1/google/contacts/resolve")
    async def contacts_resolve(q: str, x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token, ControlScope.GOOGLE)
        try:
            return {"contacts": await google.contacts_resolve(q)}
        except GoogleAuthError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/v1/google/tasks")
    async def tasks_list(x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token, ControlScope.GOOGLE)
        try:
            return {"tasks": await google.tasks_list()}
        except GoogleAuthError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/v1/google/status")
    async def google_status():
        return await google.status()

    @app.get("/v1/google/planes")
    async def google_credential_planes():
        """P2-GOOG-003 — the four Google credentials, reported one by one.

        `/v1/google/status` answers "is Google connected" with one boolean derived from the
        owner's refresh token. Four credentials reach Google and they expire
        independently: the refresh token, the model runtime's entitlement, the cloud
        project credentials for discoveryengine, and a browser profile the owner signed in
        with. So an expired cloud credential and a signed-out profile were both invisible
        there, and a revoked refresh token made the whole of Google look down when the
        enterprise notebook path was fine.

        §421 requires degradation to be scoped. A reader who cannot see which plane failed
        cannot know what still works, and the two wrong answers are symmetrical: everything
        broken because one credential lapsed, or everything fine because the one credential
        that is checked happens to be good.
        """
        knowledge = owner_runtime.knowledge
        return summarise(
            await plane_health(
                google=google,
                notebook_enterprise=knowledge.notebook_enterprise,
                notebook_consumer=knowledge.notebook_consumer,
                broker=google_broker,
            )
        )

    @app.post("/v1/google/connect")
    async def google_connect(body: GoogleConnectBody, x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token, ControlScope.GOOGLE)
        try:
            await google.store_refresh_token("owner", body.refresh_token, body.scopes)
        except GoogleAuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return await google.status()

    @app.post("/v1/google/revoke")
    async def google_revoke(x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token, ControlScope.GOOGLE)
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
        require_internal_control(x_van_internal_token, ControlScope.GOOGLE)
        return await google_router.plan(body, workspace=await google.status())

    @app.get("/v1/google/jobs/{job_id}")
    async def get_google_job(job_id: str, x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token, ControlScope.GOOGLE)
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
        require_internal_control(x_van_internal_token, ControlScope.GOOGLE)
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
        # P3-OPS-005 — the durable path. `ingest` alone deduped against a set()
        # that a restart emptied, so a restart re-showed what the owner had seen.
        filtered = await notifications.ingest_durable(note)
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

    # --------------------------------------------------- Gate 11: operator surface
    @app.post("/v1/observability/device-telemetry")
    async def ingest_device_telemetry(body: DeviceTelemetryBody):
        """P3-OBS-002 — aura frame time, wake/ASR/TTS latency and the battery and
        memory indicators are measured on the device. The gateway cannot produce
        them and must not invent them, so this is where they arrive.

        Device-authenticated, not operator-authenticated: the producer is the
        owner's paired device.
        """
        accepted, refused = [], []
        for sample in body.samples[:200]:
            try:
                accepted.append(observability_instruments.record_device_sample(
                    sample.name, sample.value,
                    surface=sample.surface, dimension=sample.dimension,
                ))
            except observability_instruments.UnknownDeviceMetric:
                refused.append(sample.name)
            except observability_instruments.DeviceDimensionMissing:
                # Refused rather than recorded under a default. A depth with no
                # storability would put approval-bearing commands in the same bucket as
                # a retry queue, and an operator reading that chart would be told the
                # opposite of what is true.
                refused.append(sample.name)
        return {"accepted": len(accepted), "refused": refused}

    @app.get("/v1/observability/metrics")
    async def metrics_scrape(x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token, ControlScope.OBSERVABILITY)
        return PlainTextResponse(
            render_prometheus(METRICS),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    async def _ops_health() -> dict:
        return await ops_health.collect(
            scheduler=scheduler,
            pki_dir=settings.pki_dir or None,
            backup_root=settings.backup_dir or None,
        )

    @app.get("/v1/observability/alerts")
    async def observability_alert_state(x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token, ControlScope.OBSERVABILITY)
        health = await _ops_health()
        firing = observability_alerts.evaluate(
            METRICS,
            uptime_seconds=time.monotonic() - started_at,
            ops_facts=ops_health.ops_facts(health),
        )
        return {
            "firing": [alert.as_dict() for alert in firing],
            "rules_evaluated": len(observability_alerts.RULES),
            "uptime_seconds": round(time.monotonic() - started_at),
        }

    @app.get("/v1/observability/health")
    async def observability_health(x_van_internal_token: str | None = Header(default=None)):
        require_internal_control(x_van_internal_token, ControlScope.OBSERVABILITY)
        health = await _ops_health()
        audit_chain = await audit.verify_chain()
        return {
            **health,
            "audit_chain": audit_chain,
            "unobserved_metrics": [m.name for m in METRICS.unobserved()],
            "uptime_seconds": round(time.monotonic() - started_at),
        }

    @app.get("/v1/observability/trace/{command_id}")
    async def observability_trace(
        command_id: str, x_van_internal_token: str | None = Header(default=None)
    ):
        """P2-OBS-001 — the join an operator used to do by hand, in one call."""
        require_internal_control(x_van_internal_token, ControlScope.OBSERVABILITY)
        trace = await tracer.trace(command_id)
        if not trace.found:
            raise HTTPException(status_code=404, detail="no_trace_for_command")
        return trace.as_dict()

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
        # P0-TRADE-004 — a stale ledger is unavailable for the purpose of answering, even
        # though the file opens and the chain verifies. Reporting it as available was how
        # old data came back as current.
        degraded.set(
            DegradedCode.TRADING_LEDGER_UNAVAILABLE,
            not (
                status.get("ledger_available")
                and status.get("chain_ok")
                and not status.get("ledger_stale", False)
            ),
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

    async def _authenticate_account_action(request: Request, req) -> None:
        """Device identity, known action, device signature and freshness. Shared by the
        challenge route and the action route so they cannot diverge."""
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

    @app.post("/v1/trading/accounts/challenge")
    async def trading_account_challenge(request: Request, req: AccountChallengeRequest):
        """P1-SEC-004 — the one-time challenge the device signs inside the biometric.

        The challenge is bound to the device, the action and a digest of the arguments, so
        an approval for "verify this account" cannot be presented for "issue me a signing
        key", and approving one set of credentials does not approve a different set.
        """
        await _authenticate_account_action(request, req)
        if not requires_owner_approval(req.action):
            raise HTTPException(
                status_code=400,
                detail="this action is read-only and needs no owner approval",
            )
        challenge = await app.state.orchestrator.approvals.issue(
            device_id=req.device_id,
            source_command_id=f"account:{req.action}",
            turn_id=None,
            action_id=f"trading.account.{req.action}",
            text=canonical_action(req.device_id, req.issued_at_unix, req.action, req.args),
            project_id=None,
        )
        return {
            "approval_challenge_id": challenge.challenge_id,
            "approval_challenge": challenge.canonical,
            "approval_expires_at_unix": challenge.expires_at_unix,
            "resolved_action_id": f"trading.account.{req.action}",
        }

    @app.post("/v1/trading/accounts/action")
    async def trading_account_action(request: Request, req: AccountActionRequest):
        await _authenticate_account_action(request, req)
        # P1-SEC-004. This used to be guarded on the device by a biometric prompt whose
        # only output was "the prompt succeeded", which the gateway never saw and which
        # nothing bound to this action. The strong path already existed for A4 commands;
        # trading credential changes were on the weak one.
        if requires_owner_approval(req.action):
            proof = req.approval_proof
            if proof is None or proof.algorithm != OwnerApprovalService.ALGORITHM:
                await audit.record(
                    result="denied",
                    device_id=req.device_id,
                    capability=f"trading.account.{req.action}",
                    failure_reason="approval_proof_missing",
                )
                raise HTTPException(
                    status_code=403,
                    detail="owner biometric approval proof is required for this action",
                )
            try:
                await app.state.orchestrator.approvals.verify_and_consume(
                    challenge_id=proof.challenge_id,
                    source_command_id=f"account:{req.action}",
                    signature_b64=proof.signature_b64,
                    device_id=req.device_id,
                    turn_id=None,
                    action_id=f"trading.account.{req.action}",
                    text=canonical_action(
                        req.device_id, req.issued_at_unix, req.action, req.args
                    ),
                    project_id=None,
                )
            except OwnerApprovalError as exc:
                await audit.record(
                    result="denied",
                    device_id=req.device_id,
                    capability=f"trading.account.{req.action}",
                    approval="invalid",
                    failure_reason=str(exc),
                )
                raise HTTPException(status_code=403, detail=str(exc)) from exc
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
        """The one HTML response in the gateway, and the only one a stranger can reach.

        P4-SEC-011: this built its markup by interpolation. Every interpolated value was a
        constant at the time, so it was not exploitable — but `broker` is a path segment
        and an HTTPException detail can carry a query parameter back, so it was one
        parameter away from being so. Escaping is cheap and the pattern is what matters:
        the next person to add a field here should not have to notice this.
        """
        import html

        from fastapi.responses import HTMLResponse

        try:
            result = await onboarding.oauth_callback(broker, dict(request.query_params))
        except HTTPException as exc:
            return HTMLResponse(
                f"<h2>Van: linking failed</h2><p>{html.escape(str(exc.detail))}</p>",
                status_code=exc.status_code,
            )
        return HTMLResponse(
            f"<h2>Van: {html.escape(str(result['broker']))} linked</h2>"
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
        require_internal_control(x_van_internal_token, ControlScope.TRADING)
        try:
            result = trading.halt(owner_signature_ref=req.owner_signature_ref, reason=req.reason)
        except TradingControlError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        await audit.record(
            result="owner_halt_recorded",
            capability="trading.owner_halt",
            # The verified authority's reference, never the raw token: these rows are
            # long-lived and the token is a credential (P0-TRADE-001).
            approval=result["sig"],
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
        require_internal_control(x_van_internal_token, ControlScope.TRADING)
        try:
            result = trading.confirm_ticket(
                ticket_id,
                owner_signature_ref=req.owner_signature_ref,
                fill_price=req.fill_price,
                filled_qty=req.filled_qty,
                contract_note_ref=req.contract_note_ref,
            )
        except TradingAuthorityError as exc:
            # Not authorised is a 403; a ticket already confirmed is the 409 below.
            raise HTTPException(status_code=403, detail=str(exc)) from exc
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
