from __future__ import annotations

import base64
import hashlib
import io

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from pypdf import PdfWriter

from van_gateway.action.models import ExecutionStatus
from van_gateway.app import create_app
from van_gateway.config import get_settings
from van_gateway.google.service import GoogleService
from van_gateway.google.transport import FakeGoogleTransport
from van_gateway.models import PrincipalType
from van_gateway.storage.db import Store


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "extra.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "test-ingress-token-0123456789abcdef")
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "test-internal-token")
    # P0-SEC-001 — device enrolment is its own credential now.
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", "test-internal-token")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def client(monkeypatch):
    app = create_app()

    async def ok():
        return {"ok": True}

    async def run(text, metadata=None):
        return {"id": "r1"}

    monkeypatch.setattr(app.state.orchestrator.hermes, "health", ok)
    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", run)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers={"X-Van-Ingress-Token": "test-ingress-token-0123456789abcdef"}) as ac:
        async with app.router.lifespan_context(app):
            ticket = await app.state.auth.create_pairing_ticket("pytest-client")
            paired = await app.state.auth.pair_device(
                ticket.token,
                "pytest-client",
                "pytest-client-secret",
                "PEM",
                "pytest-client",
            )
            ac.headers.update({"X-Van-Device-Token": paired.access_token})
            yield ac, app


@pytest.mark.asyncio
async def test_decision_escalation_surfaces_attention(client):
    ac, _app = client
    esc = await ac.post(
        "/v1/decisions/escalate",
        json={"title": "Council needs judgment", "body": "Approve architecture?", "source": "hermes", "blocking": True},
    )
    assert esc.status_code == 200
    decision_id = esc.json()["id"]
    attention = (await ac.get("/v1/attention")).json()
    assert any(i["title"] == "Council needs judgment" for i in attention)
    resolved = await ac.post(f"/v1/decisions/{decision_id}/resolve", json={"approved": True})
    assert resolved.json()["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_attention_snooze_route_is_durable_and_validated(client):
    ac, _app = client
    created = await ac.post(
        "/v1/attention",
        json={
            "title": "Follow up supplier",
            "severity": "FOLLOW_UP",
            "source": "pytest",
            "dedupe_key": "pytest:snooze",
        },
    )
    assert created.status_code == 200
    item_id = created.json()["id"]

    now = int(__import__("time").time())
    invalid = await ac.post(
        f"/v1/attention/{item_id}/snooze",
        json={"until_unix": now - 1},
    )
    assert invalid.status_code == 400

    snoozed = await ac.post(
        f"/v1/attention/{item_id}/snooze",
        json={"until_unix": now + 3600},
    )
    assert snoozed.status_code == 200
    assert snoozed.json()["snoozed"] is True
    visible = (await ac.get("/v1/attention")).json()
    assert all(item["id"] != item_id for item in visible)

    missing = await ac.post(
        "/v1/attention/not-a-real-item/snooze",
        json={"until_unix": now + 3600},
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_project_truth_put_requires_internal_token(client):
    ac, _app = client
    denied = await ac.put(
        "/v1/projects/dde/truth",
        json={"truth": {"project": "dde", "rules": ["fail_closed"]}, "truth_sha": "abc", "repo_sha": "def"},
    )
    assert denied.status_code in {403, 503}
    put = await ac.put(
        "/v1/projects/dde/truth",
        headers={"X-Van-Internal-Token": "test-internal-token"},
        json={"truth": {"project": "dde", "rules": ["fail_closed"]}, "truth_sha": "abc", "repo_sha": "def"},
    )
    assert put.status_code == 200
    assert put.json()["ok"] is True
    loaded = await ac.get("/v1/projects/dde/truth")
    assert loaded.json()["truth_sha"] == "abc"


@pytest.mark.asyncio
async def test_health_ok_false_when_hermes_offline(client, monkeypatch):
    ac, app = client

    async def offline():
        return {"ok": False, "degraded": "HERMES_OFFLINE"}

    monkeypatch.setattr(app.state.orchestrator.hermes, "health", offline)
    body = (await ac.get("/health")).json()
    assert body["ok"] is False
    assert body["hermes"]["ok"] is False
    assert any(item["code"] == "HERMES_OFFLINE" for item in body["degraded"])


@pytest.mark.asyncio
async def test_project_truth_put_enables_mutation_gate(client):
    ac, _app = client
    put = await ac.put(
        "/v1/projects/dde/truth",
        headers={"X-Van-Internal-Token": "test-internal-token"},
        json={"truth": {"project": "dde", "rules": ["fail_closed"]}, "truth_sha": "abc", "repo_sha": "def"},
    )
    assert put.json()["ok"] is True
    loaded = await ac.get("/v1/projects/dde/truth")
    assert loaded.json()["truth_sha"] == "abc"


@pytest.mark.asyncio
async def test_reminder_parse_expression(client):
    ac, _app = client
    body = await ac.post(
        "/v1/reminders/parse",
        json={"text": "Supplier", "due_expression": "in 15 minutes", "idempotency_key": "parse-1"},
    )
    assert body.status_code == 200
    assert body.json()["status"] == "OPEN"


@pytest.mark.asyncio
async def test_google_fake_transport_requires_authorized_execution_and_readback(client):
    ac, _app = client
    headers = {"X-Van-Internal-Token": "test-internal-token"}
    connected = await ac.post(
        "/v1/google/connect",
        headers=headers,
        json={
            "refresh_token": "refresh-xyz",
            "scopes": [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.compose",
                "https://www.googleapis.com/auth/gmail.send",
            ],
        },
    )
    assert connected.status_code == 200
    google_transport = FakeGoogleTransport()
    seed_raw = base64.urlsafe_b64encode(
        b"From: owner@example.com\r\nTo: supplier@example.com\r\nSubject: Reviewed\r\n\r\nReady"
    ).decode("ascii").rstrip("=")
    google_transport.drafts["d1"] = {
        "id": "d1",
        "message": {"id": "md1", "threadId": "t1", "raw": seed_raw},
    }
    _app.state.google.transport = google_transport
    _app.state.google.oauth = None
    reviewed_sha = hashlib.sha256(seed_raw.encode("ascii")).hexdigest()

    # An internal-control credential is not owner approval. The historical route accepted
    # approved=true here; the new route has no such authority-bearing parameter.
    bypass = await ac.post(
        "/v1/google/gmail/send",
        headers=headers,
        params={"draft_id": "d1", "approved": True},
    )
    assert bypass.status_code == 422

    preview = await _app.state.google.gmail_draft_preview("d1")
    parameters = {"draft_id": "d1", "draft_content_sha256": preview["draft_content_sha256"]}
    _app.state.google.transport.calls.clear()
    execution = await _app.state.owner_runtime.actions.begin(
        execution_id="exec-google-send",
        command_id="cmd-google-send",
        turn_id="turn-google-send",
        action_id="google.gmail.send",
        principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:pytest-client",
        idempotency_key="turn-google-send:google.gmail.send",
        parameters=parameters,
        snapshot_id=None,
        owner_approved=True,
    )
    assert execution.status is ExecutionStatus.AUTHORIZED

    ok = await ac.post(
        "/v1/google/actions/execute",
        headers=headers,
        json={"execution_id": execution.execution_id, "parameters": parameters},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["verification"]["status"] == "VERIFIED_SUCCESS"
    calls = [name for name, _args in _app.state.google.transport.calls]
    assert calls == ["gmail_draft_get", "gmail_message_send", "gmail_message_get"]

    # A4 without owner approval produces an execution record, but not one the provider
    # executor may use. This separates "has an execution id" from "is authorized".
    blocked = await _app.state.owner_runtime.actions.begin(
        execution_id="exec-google-send-blocked",
        command_id="cmd-google-send-blocked",
        turn_id="turn-google-send-blocked",
        action_id="google.gmail.send",
        principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:pytest-client",
        idempotency_key="turn-google-send-blocked:google.gmail.send",
        parameters={"draft_id": "d2", "draft_content_sha256": "0" * 64},
        snapshot_id=None,
        owner_approved=False,
    )
    assert blocked.status is ExecutionStatus.AUTHORIZATION_REQUIRED
    before = list(_app.state.google.transport.calls)
    refused = await ac.post(
        "/v1/google/actions/execute",
        headers=headers,
        json={"execution_id": blocked.execution_id, "parameters": {"draft_id": "d2", "draft_content_sha256": "0" * 64}},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"] == "execution_not_authorized"
    assert _app.state.google.transport.calls == before

    # Owner approval binds the irreversible send to the exact reviewed MIME bytes.
    stale_parameters = {"draft_id": "d1", "expected_raw_sha256": "0" * 64}
    stale = await _app.state.owner_runtime.actions.begin(
        execution_id="exec-google-send-stale",
        command_id="cmd-google-send-stale",
        turn_id="turn-google-send-stale",
        action_id="google.gmail.send",
        principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:pytest-client",
        idempotency_key="turn-google-send-stale:google.gmail.send",
        parameters=stale_parameters,
        snapshot_id=None,
        owner_approved=True,
    )
    before_send = len([name for name, _args in google_transport.calls if name == "gmail_send"])
    stale_response = await ac.post(
        "/v1/google/actions/execute",
        headers=headers,
        json={"execution_id": stale.execution_id, "parameters": stale_parameters},
    )
    assert stale_response.status_code == 503
    assert stale_response.json()["detail"] == "gmail_draft_version_changed"
    after_send = len([name for name, _args in google_transport.calls if name == "gmail_send"])
    assert after_send == before_send

    scrubbed = GoogleService.scrub_for_prompt({"access_token": "tok", "snippet": "hi"})
    assert "access_token" not in scrubbed
    assert scrubbed["snippet"] == "hi"


@pytest.mark.asyncio
async def test_google_control_plane_rejects_missing_internal_token(client):
    ac, _app = client
    response = await ac.post(
        "/v1/google/connect",
        json={"refresh_token": "refresh-xyz", "scopes": ["https://www.googleapis.com/auth/gmail.readonly"]},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_migration_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "mig.sqlite3"))
    get_settings.cache_clear()
    store = Store(str(tmp_path / "mig.sqlite3"))
    await store.migrate()
    await store.migrate()
    row = await store.fetchone("SELECT COUNT(*) AS c FROM schema_migrations")
    assert int(row["c"]) >= 1


@pytest.mark.asyncio
async def test_internal_control_token_is_not_general_ingress(client):
    _ac, app = client
    transport = ASGITransport(app=app)
    headers = {"X-Van-Internal-Token": "test-internal-token"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as internal:
        put = await internal.put(
            "/v1/projects/dde/truth",
            json={"truth": {"project": "dde"}, "truth_sha": "abc", "repo_sha": "def"},
        )
        assert put.status_code == 200

        general = await internal.get("/v1/projects")
        assert general.status_code == 401
        assert general.json()["detail"] == "ingress_auth_failed"



@pytest.mark.asyncio
async def test_google_filled_pdf_reply_round_trip_is_action_bound(client):
    """Canonical OpenMuse→VAN acceptance #3 through the real ActionRuntime boundary."""
    ac, app = client
    headers = {"X-Van-Internal-Token": "test-internal-token"}
    connected = await ac.post(
        "/v1/google/connect",
        headers=headers,
        json={
            "refresh_token": "refresh-round-trip",
            "scopes": [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.compose",
                "https://www.googleapis.com/auth/gmail.send",
            ],
        },
    )
    assert connected.status_code == 200
    transport = FakeGoogleTransport()
    app.state.google.transport = transport
    app.state.google.oauth = None

    writer=PdfWriter()
    writer.add_blank_page(width=100,height=100)
    pdf=io.BytesIO()
    writer.write(pdf)
    document=await app.state.documents.import_pdf(
        filename="permission.pdf",data=pdf.getvalue(),mission_id="mission-google-round-trip"
    )
    filled=await app.state.documents.fill(document.document_id,{})
    assert filled.output_artifact_id

    draft_parameters={
        "thread_id":"thread-1",
        "body":"Attached is the completed form.",
        "attachment_document_id":document.document_id,
    }
    draft_execution=await app.state.owner_runtime.actions.begin(
        execution_id="exec-google-draft-attachment",
        command_id="cmd-google-draft-attachment",
        turn_id="turn-google-draft-attachment",
        action_id="google.gmail.draft",
        principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:pytest-client",
        idempotency_key="turn-google-draft-attachment:google.gmail.draft",
        parameters=draft_parameters,
        snapshot_id=None,
        owner_approved=False,
    )
    assert draft_execution.status is ExecutionStatus.AUTHORIZED
    drafted=await ac.post(
        "/v1/google/actions/execute",
        headers=headers,
        json={"execution_id":draft_execution.execution_id,"parameters":draft_parameters},
    )
    assert drafted.status_code==200,drafted.text
    review=drafted.json()["review"]
    assert review["attachment_document_id"]==document.document_id
    assert len(review["raw_sha256"])==64
    assert drafted.json()["verification"]["status"]=="VERIFIED_SUCCESS"

    send_parameters={
        "draft_id":review["draft_id"],
        "expected_raw_sha256":review["raw_sha256"],
    }
    send_execution=await app.state.owner_runtime.actions.begin(
        execution_id="exec-google-send-attachment",
        command_id="cmd-google-send-attachment",
        turn_id="turn-google-send-attachment",
        action_id="google.gmail.send",
        principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:pytest-client",
        idempotency_key="turn-google-send-attachment:google.gmail.send",
        parameters=send_parameters,
        snapshot_id=None,
        owner_approved=True,
    )
    assert send_execution.status is ExecutionStatus.AUTHORIZED
    sent=await ac.post(
        "/v1/google/actions/execute",
        headers=headers,
        json={"execution_id":send_execution.execution_id,"parameters":send_parameters},
    )
    assert sent.status_code==200,sent.text
    assert sent.json()["verification"]["status"]=="VERIFIED_SUCCESS"
    calls=[name for name,_args in transport.calls]
    assert calls==[
        "gmail_draft","gmail_draft_get",
        "gmail_draft_get","gmail_send","gmail_message_get",
    ]
