from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from van_gateway.config import Settings
from van_gateway.google.control import GoogleControlAuthError, verify_internal_control
from van_gateway.google.mesh import GoogleCapabilityRegistry, GoogleCapabilityRouter, GoogleCapabilityState, GoogleIdentityBroker, GoogleRouteRequest
from van_gateway.google.service import GoogleService
from van_gateway.models import ActionClass
from van_gateway.storage.db import SCHEMA_VERSION, Store


def registry_path() -> str:
    return str(Path(__file__).resolve().parents[2] / "registries" / "google_capabilities.json")


@pytest.mark.asyncio
async def test_google_migration_and_principal_hash(tmp_path):
    store = Store(str(tmp_path / "mesh.sqlite3"))
    await store.migrate()
    row = await store.fetchone("SELECT MAX(version) AS version FROM schema_migrations")
    # 6 adds the Rev 1.3 Automation & Browser Fabric tables; 7-8 add
    # resumable browser escalation and separately auditable owner-approved scope grants;
    # 9 adds workflow health, repair lineage, dead letters and telemetry;
    # 10 Mission Core; 11 the canonical capability registry; 12 the owner
    # understanding layer; 13 critical reasoning; 14 autonomy and attention
    # scoring; 15 external reality, evolution radar, benchmarks and eval.
    # 16 adds the owner permission registry and computer-use operations.
    # 17 adds single-use command nonces and the audit hash chain.
    #
    # The applied version must equal SCHEMA_VERSION, and SCHEMA_VERSION must not regress
    # below the migrations this test's assumptions depend on. Pinning the exact literal
    # made every legitimate forward migration fail here, which teaches the next author to
    # edit the assertion rather than think about it.
    assert row["version"] == SCHEMA_VERSION
    assert SCHEMA_VERSION >= 16, "the Google mesh assumptions require migrations through 16"
    broker = GoogleIdentityBroker(store, GoogleCapabilityRegistry(registry_path()), ai_plan="PRO")
    status = await broker.register_principal(subject="owner-google-subject", ai_plan="PRO")
    assert status.registered is True
    assert status.ai_plan == "PRO"
    raw = await store.fetchone("SELECT subject_hash FROM google_principal WHERE owner_id='owner_google_account'")
    assert raw["subject_hash"] != "owner-google-subject"
    assert len(raw["subject_hash"]) == 64


def test_stitch_registry_uses_programmatic_cloud_plane():
    registry = GoogleCapabilityRegistry(registry_path())
    stitch = registry.get("stitch")
    assert stitch.credential_plane.value == "cloud_service"
    assert stitch.public_api is True


@pytest.mark.asyncio
async def test_consumer_capability_requires_canonical_principal(tmp_path):
    store = Store(str(tmp_path / "mesh.sqlite3")); await store.migrate()
    broker = GoogleIdentityBroker(store, GoogleCapabilityRegistry(registry_path()), consumer_connected_capabilities="mixboard,stitch")
    assert (await broker.capability_status("mixboard")).state == GoogleCapabilityState.UNVERIFIED
    await broker.register_principal(subject="sub-1", ai_plan="PRO")
    after = await broker.capability_status("mixboard")
    assert after.state == GoogleCapabilityState.CONFIGURED
    assert after.configured_by_account is True


@pytest.mark.asyncio
async def test_antigravity_requires_its_delegated_identity(tmp_path):
    store = Store(str(tmp_path / "mesh.sqlite3")); await store.migrate()
    registry = GoogleCapabilityRegistry(registry_path())
    broker = GoogleIdentityBroker(store, registry, consumer_connected_capabilities="antigravity,jules")
    await broker.register_principal(subject="canonical-subject")
    antigravity = await broker.capability_status("antigravity")
    assert antigravity.identity_alias == "antigravity_worker_account"
    assert antigravity.state == GoogleCapabilityState.UNVERIFIED
    jules = await broker.capability_status("jules")
    assert jules.identity_alias == "owner_google_account"
    assert jules.state == GoogleCapabilityState.CONFIGURED
    await broker.register_principal(subject="worker-subject", owner_id="antigravity_worker_account")
    antigravity = await broker.capability_status("antigravity")
    assert antigravity.state == GoogleCapabilityState.CONFIGURED
    with pytest.raises(ValueError, match="google_identity_binding_mismatch"):
        await broker.record_capability_evidence("antigravity", state=GoogleCapabilityState.READY, owner_id="owner_google_account")


@pytest.mark.asyncio
async def test_antigravity_route_exposes_delegated_identity(tmp_path):
    store = Store(str(tmp_path / "mesh.sqlite3")); await store.migrate()
    registry = GoogleCapabilityRegistry(registry_path())
    broker = GoogleIdentityBroker(store, registry, consumer_connected_capabilities="antigravity")
    await broker.register_principal(subject="worker-subject", owner_id="antigravity_worker_account")
    decision = await GoogleCapabilityRouter(store, broker).plan(GoogleRouteRequest(owner_intent_id="intent-dev", intent="development", action_class=ActionClass.A2))
    assert decision.status == "planned"
    assert decision.capability_id == "antigravity"
    assert decision.identity_alias == "antigravity_worker_account"


@pytest.mark.asyncio
async def test_runtime_route_is_deterministic_and_persisted(tmp_path):
    store = Store(str(tmp_path / "mesh.sqlite3")); await store.migrate()
    broker = GoogleIdentityBroker(store, GoogleCapabilityRegistry(registry_path()), ai_plan="PRO", gemini_runtime_configured=True)
    await broker.register_principal(subject="sub-2", ai_plan="PRO")
    router = GoogleCapabilityRouter(store, broker)
    decision = await router.plan(GoogleRouteRequest(owner_intent_id="intent-1", intent="deep_research", action_class=ActionClass.A2, input_refs=["artifact://a", "artifact://b"]))
    assert decision.status == "planned" and decision.capability_id == "deep_research" and decision.job_id
    job = await router.job(decision.job_id)
    assert job["capability_id"] == "deep_research" and job["status"] == "PLANNED" and len(job["input_hash"]) == 64


@pytest.mark.asyncio
async def test_mutation_requires_truth_and_a4_requires_approval(tmp_path):
    store = Store(str(tmp_path / "mesh.sqlite3")); await store.migrate()
    broker = GoogleIdentityBroker(store, GoogleCapabilityRegistry(registry_path()), consumer_connected_capabilities="antigravity")
    await broker.register_principal(subject="sub-3", ai_plan="PRO")
    router = GoogleCapabilityRouter(store, broker)
    a3 = await router.plan(GoogleRouteRequest(owner_intent_id="intent-a3", intent="development", action_class=ActionClass.A3, project_id="gtr", grant_id="grant-1"))
    assert a3.status == "degraded" and "STALE_PROJECT_TRUTH" in a3.degraded
    a4 = await router.plan(GoogleRouteRequest(owner_intent_id="intent-a4", intent="workspace_operation", action_class=ActionClass.A4, owner_approved=False))
    assert a4.status == "approval_required" and a4.requires_approval is True


@pytest.mark.asyncio
async def test_a_fallback_nothing_can_execute_is_not_a_fallback(tmp_path):
    """P2-GOOG-001 — this used to assert `planned` on workspace_studio.

    The primary for workspace_operation is workspace_api, which is gateway code. Falling
    back to a surface with no implementation anywhere turns "the deterministic path is
    unavailable" into "the operation was planned", which is worse than an honest refusal.
    """
    store = Store(str(tmp_path / "mesh.sqlite3")); await store.migrate()
    broker = GoogleIdentityBroker(store, GoogleCapabilityRegistry(registry_path()), consumer_connected_capabilities="workspace_studio")
    await broker.register_principal(subject="sub-fallback", ai_plan="PRO")
    decision = await GoogleCapabilityRouter(store, broker).plan(GoogleRouteRequest(owner_intent_id="intent-fallback", intent="workspace_operation", action_class=ActionClass.A2))
    # The deterministic primary is reported as the reason it could not proceed, which is
    # the honest answer: the Workspace OAuth connection is what is missing. What must not
    # happen is a `planned` decision naming a capability nothing can run.
    assert decision.status == "degraded", decision
    assert decision.capability_id != "workspace_studio", (
        "the router still selected a capability with no implementation"
    )


@pytest.mark.asyncio
async def test_a_fallback_something_can_execute_still_works(tmp_path):
    """The restriction must not break the fallbacks that were always sound."""
    store = Store(str(tmp_path / "mesh.sqlite3")); await store.migrate()
    registry = GoogleCapabilityRegistry(registry_path())
    assert registry.get("antigravity").executable and registry.get("jules").executable
    assert not registry.get("workspace_studio").executable


@pytest.mark.asyncio
async def test_every_capability_declares_an_executor(tmp_path):
    """A capability added without one would be routable to nothing again."""
    import json
    from pathlib import Path

    raw = json.loads(Path(registry_path()).read_text())
    for capability in raw["capabilities"]:
        assert "executor" in capability, capability["id"]
        assert capability["executor"] in (None, "gateway", "hermes"), capability["id"]


@pytest.mark.asyncio
async def test_a3_google_job_requires_explicit_grant(tmp_path):
    store = Store(str(tmp_path / "mesh.sqlite3")); await store.migrate()
    broker = GoogleIdentityBroker(store, GoogleCapabilityRegistry(registry_path()), consumer_connected_capabilities="antigravity")
    await broker.register_principal(subject="sub-grant", ai_plan="PRO")
    decision = await GoogleCapabilityRouter(store, broker).plan(GoogleRouteRequest(owner_intent_id="intent-no-grant", intent="development", action_class=ActionClass.A3, project_id="gtr", truth_sha="truth-sha"))
    assert decision.status == "degraded" and "capability grant" in decision.reason


@pytest.mark.asyncio
async def test_provider_artifact_is_never_owner_authority(tmp_path):
    store = Store(str(tmp_path / "mesh.sqlite3")); await store.migrate()
    broker = GoogleIdentityBroker(store, GoogleCapabilityRegistry(registry_path()), gemini_runtime_configured=True)
    await broker.register_principal(subject="sub-4", ai_plan="PRO")
    router = GoogleCapabilityRouter(store, broker)
    decision = await router.plan(GoogleRouteRequest(owner_intent_id="intent-2", intent="image_generation", action_class=ActionClass.A2))
    with pytest.raises(ValueError, match="provider_artifact_cannot_be_owner_signed"):
        await router.record_artifact(job_id=decision.job_id, source_tool="nano_banana", output_hash="a" * 64, trust="OWNER_SIGNED")
    artifact = await router.record_artifact(job_id=decision.job_id, source_tool="nano_banana", output_hash="b" * 64, validation_state="VALIDATED")
    assert artifact.trust == "UNTRUSTED" and artifact.validation_state == "VALIDATED"


@pytest.mark.asyncio
async def test_workspace_refresh_token_exchanged_before_live_transport(tmp_path):
    class OAuthSpy:
        def __init__(self): self.seen = None
        async def access_token(self, refresh_token: str) -> str:
            self.seen = refresh_token; return "access-token"
    class LiveSpyTransport:
        requires_access_token = True
        def __init__(self): self.token = None
        async def gmail_search(self, token: str, query: str):
            self.token = token; return [{"id": "m1"}]
    store = Store(str(tmp_path / "oauth.sqlite3")); await store.migrate()
    oauth, transport = OAuthSpy(), LiveSpyTransport()
    service = GoogleService(store, Fernet.generate_key().decode(), transport=transport, oauth=oauth)
    await service.store_refresh_token("owner", "refresh-secret", ["https://www.googleapis.com/auth/gmail.readonly"])
    assert await service.gmail_search("from:supplier") == [{"id": "m1"}]
    assert oauth.seen == "refresh-secret" and transport.token == "access-token"


def test_settings_keep_google_credential_planes_separate(monkeypatch):
    monkeypatch.setenv("VAN_GOOGLE_AI_PLAN", "PRO")
    monkeypatch.setenv("VAN_GOOGLE_CLOUD_PROJECT_ID", "van-google-ai")
    monkeypatch.setenv("VAN_GOOGLE_GEMINI_RUNTIME_CONFIGURED", "true")
    settings = Settings()
    assert settings.google_ai_plan == "PRO" and settings.google_cloud_project_id == "van-google-ai"
    assert settings.google_gemini_runtime_configured is True and settings.google_oauth_client_secret == ""


def test_internal_google_control_plane_fails_closed():
    with pytest.raises(GoogleControlAuthError, match="internal_control_token_unconfigured"):
        verify_internal_control("", None)
    with pytest.raises(GoogleControlAuthError, match="internal_control_unauthorized"):
        verify_internal_control("secret", "wrong")
    verify_internal_control("secret", "secret")


@pytest.mark.asyncio
async def test_antigravity_capacity_limited_falls_back_to_jules(tmp_path):
    store = Store(str(tmp_path / "mesh.sqlite3"))
    await store.migrate()
    broker = GoogleIdentityBroker(
        store,
        GoogleCapabilityRegistry(registry_path()),
        consumer_connected_capabilities="antigravity,jules",
    )
    await broker.register_principal(subject="sub-owner", ai_plan="PRO")
    await broker.register_principal(subject="sub-ag", owner_id="antigravity_worker_account", ai_plan="PRO")
    await broker.record_capability_evidence(
        "antigravity",
        state=GoogleCapabilityState.CAPACITY_LIMITED,
        evidence_pointer="live://antigravity/capacity_limited",
        metadata={"classification": "CAPACITY_LIMITED", "scope": "antigravity_only"},
        owner_id="antigravity_worker_account",
    )
    await broker.record_capability_evidence(
        "jules",
        state=GoogleCapabilityState.CONFIGURED,
        evidence_pointer="config://jules",
    )
    decision = await GoogleCapabilityRouter(store, broker).plan(
        GoogleRouteRequest(owner_intent_id="dev-1", intent="development", action_class=ActionClass.A2)
    )
    assert decision.status == "planned"
    assert decision.capability_id == "jules"
    assert decision.identity_alias == "owner_google_account"
    assert "ANTIGRAVITY_CAPACITY_LIMITED" in decision.degraded
    ag = await broker.capability_status("antigravity")
    assert ag.state == GoogleCapabilityState.CAPACITY_LIMITED