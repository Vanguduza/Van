"""Workspace revocation and replacement cannot reuse a prior credential's canary."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from van_gateway.capability.readiness import GoogleMeshReadiness
from van_gateway.google.mesh import (
    GoogleCapabilityRegistry, GoogleCapabilityRouter, GoogleCapabilityState,
    GoogleIdentityBroker, GoogleRouteRequest,
)
from van_gateway.google.service import GoogleService
from van_gateway.models import ActionClass, GoogleConnectionStatus
from van_gateway.storage.db import Store


@pytest.mark.asyncio
async def test_revoke_reconnect_requires_new_workspace_certification(tmp_path):
    store = Store(str(tmp_path / "google.sqlite3"))
    await store.migrate()
    registry = GoogleCapabilityRegistry(str(Path(__file__).resolve().parents[2] / "registries/google_capabilities.json"))
    broker = GoogleIdentityBroker(store, registry)
    google = GoogleService(store, Fernet.generate_key().decode())
    await broker.register_principal(subject="synthetic-owner")
    await google.store_refresh_token("owner", "synthetic-token", ["https://www.googleapis.com/auth/gmail.readonly"])
    for capability in ("workspace_api", "stitch", "gemini"):
        await broker.record_capability_evidence(capability, state=GoogleCapabilityState.READY, evidence_pointer=f"synthetic://{capability}")
    router = GoogleCapabilityRouter(store, broker)
    request = GoogleRouteRequest(owner_intent_id="synthetic-intent", intent="workspace_operation", action_class=ActionClass.A2)
    assert (await router.plan(request, workspace=await google.status())).status == "planned"

    await google.revoke()
    status = await broker.capability_status("workspace_api", workspace=await google.status())
    assert status.state == GoogleCapabilityState.AUTH_REQUIRED
    assert status.evidence_pointer == "synthetic://workspace_api"
    # The capability registry invokes the broker without a Workspace status argument.
    declaration = SimpleNamespace(health_probe="workspace_api", capability_id="google.workspace_api")
    assert (await GoogleMeshReadiness(broker).is_ready(declaration))[0] is False
    assert (await router.plan(request, workspace=await google.status())).status == "degraded"
    assert (await broker.capability_status("stitch")).state == GoogleCapabilityState.READY
    assert (await broker.capability_status("gemini")).state == GoogleCapabilityState.READY

    await google.store_refresh_token("owner", "replacement-token", ["https://www.googleapis.com/auth/gmail.readonly"])
    status = await broker.capability_status("workspace_api", workspace=await google.status())
    assert status.state == GoogleCapabilityState.CONFIGURED
    assert status.verified_at_unix is None
    assert status.evidence_pointer == "synthetic://workspace_api"
    assert (await router.plan(request, workspace=await google.status())).status == "degraded"
    await broker.record_capability_evidence("workspace_api", state=GoogleCapabilityState.READY, evidence_pointer="synthetic://replacement-canary")
    assert (await GoogleMeshReadiness(broker).is_ready(declaration))[0] is True
    assert (await router.plan(request, workspace=await google.status())).status == "planned"


@pytest.mark.asyncio
async def test_disconnected_workspace_overrides_old_ready_receipt(tmp_path):
    store = Store(str(tmp_path / "google.sqlite3"))
    await store.migrate()
    broker = GoogleIdentityBroker(store, GoogleCapabilityRegistry(str(Path(__file__).resolve().parents[2] / "registries/google_capabilities.json")))
    await broker.register_principal(subject="synthetic-owner")
    await broker.record_capability_evidence("workspace_api", state=GoogleCapabilityState.READY, evidence_pointer="synthetic://stale")
    status = await broker.capability_status("workspace_api", workspace=GoogleConnectionStatus(connected=False))
    assert status.state == GoogleCapabilityState.AUTH_REQUIRED
    assert status.evidence_pointer == "synthetic://stale"
