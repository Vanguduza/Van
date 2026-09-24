"""VAN-DEV-001 — the gateway's proxy onto DIAL's Development Projection API v1.

Driven through the real app and its middleware, with DIAL replaced by an in-process fake
behind `httpx.MockTransport`. The questions (DIAL VAN-DEVCC-R1 §8, backend half):

* does every read need owner-device authentication, and the one mutation a device proof;
* does the DIAL-scoped credential reach DIAL and never come back out, on any path;
* is DIAL's envelope passed through unchanged, 409 STALE_VIEW included;
* is "DIAL is not there" a 503 the phone can render, rather than a 500 or a hang;
* is the action vocabulary closed, and is a retried action forwarded once.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time

import httpx
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils
from httpx import ASGITransport, AsyncClient

from dial_dev_fakes import DIAL_BASE_URL, DIAL_TOKEN, FakeDial, envelope
from test_owner_device_binding import PACKAGE, SIGNING_CERT, _attestation, _keypair
from van_gateway.app import create_app
from van_gateway.auth.device_proof import request_signing_input
from van_gateway.config import get_settings
from van_gateway.dial_dev.config import ACTIONS

INGRESS = "dial-dev-ingress-token-0123456789"
INTERNAL = "dial-dev-internal-token-0123456789"
ACTIONS_PATH = "/v1/dial-dev/actions"


def _env(monkeypatch, tmp_path, *, enabled: bool = True, bind: bool = True) -> None:
    token = tmp_path / "dial-dev.token"
    token.write_text(DIAL_TOKEN + "\n")
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "dial-dev.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")
    if bind:
        monkeypatch.setenv("VAN_OWNER_DEVICE_PACKAGE", PACKAGE)
        monkeypatch.setenv("VAN_OWNER_DEVICE_SIGNING_CERT_SHA256", SIGNING_CERT)
    monkeypatch.setenv("VAN_DIAL_DEV_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("VAN_DIAL_DEV_BASE_URL", DIAL_BASE_URL)
    monkeypatch.setenv("VAN_DIAL_DEV_TOKEN_FILE", str(token))
    monkeypatch.setenv("VAN_DIAL_DEV_TIMEOUT_S", "2")
    # The ingestion worker has its own tests; here it would race the fake's request log.
    monkeypatch.setenv("VAN_DIAL_DEV_ATTENTION_ENABLED", "false")
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def gateway(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    app = create_app()
    dial = FakeDial()
    app.state.dial_dev_client.transport = dial.transport()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            yield ac, app, dial
    get_settings.cache_clear()


async def _paired(app):
    ticket = await app.state.auth.create_pairing_ticket("owner-phone")
    return await app.state.auth.pair_device(ticket.token, "owner-phone", "s" * 32, "PEM", "owner-phone")


async def _bind(app, device_id: str):
    service = app.state.owner_device_bindings
    token, challenge = await service.create_bootstrap_token()
    pem, private_key = _keypair()
    await service.bind(
        token=token, device_id=device_id, public_key_pem=pem,
        attestation_extension=_attestation(challenge.encode()),
    )
    return private_key


def _auth(enrolled) -> dict:
    return {"X-Van-Ingress-Token": INGRESS, "X-Van-Device-Token": enrolled.access_token}


def _proof(private_key, *, device_id: str, body: bytes, path: str = ACTIONS_PATH) -> dict:
    issued_at_ms = int(time.time() * 1000)
    signing_input = request_signing_input(
        method="POST", path=path, device_id=device_id, issued_at_ms=issued_at_ms,
        body_sha256=hashlib.sha256(body).hexdigest(),
    )
    r, s = asym_utils.decode_dss_signature(private_key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
    return {
        "X-Van-Device-Proof": base64.b64encode(r.to_bytes(32, "big") + s.to_bytes(32, "big")).decode(),
        "X-Van-Device-Proof-Issued-At": str(issued_at_ms),
    }


async def _owner(app):
    enrolled = await _paired(app)
    key = await _bind(app, enrolled.device.device_id)
    return enrolled, key


async def _post_action(ac, enrolled, key, body: dict):
    raw = json.dumps(body).encode()
    headers = {**_auth(enrolled), **_proof(key, device_id=enrolled.device.device_id, body=raw),
               "content-type": "application/json"}
    return await ac.post(ACTIONS_PATH, content=raw, headers=headers)


def _action(action: str = "PAUSE_TASK_SAFE", *, key: str = "idem-0001-abcdef", **extra) -> dict:
    body = {
        "action": action,
        "target": {"project_id": "dial-development-system", "task_id": "HOT-DU-021"},
        "params": {},
        "idempotency_key": key,
        "expected_projection_revision": "sha256:rev-1",
    }
    body.update(extra)
    return body


#: Every read the Android client may call, and the DIAL path it must reach.
READS = [
    ("/v1/dial-dev/projects", "/v1/dev/projects", {}),
    ("/v1/dial-dev/projects/dial-development-system/home", "/v1/dev/projects/dial-development-system/home", {}),
    ("/v1/dial-dev/projects/dial-development-system/stage-plan", "/v1/dev/projects/dial-development-system/stage-plan", {}),
    ("/v1/dial-dev/projects/dial-development-system/tasks?view=needs_me", "/v1/dev/projects/dial-development-system/tasks", {"view": "needs_me"}),
    ("/v1/dial-dev/projects/dial-development-system/graph", "/v1/dev/projects/dial-development-system/graph", {}),
    ("/v1/dial-dev/tasks/HOT-DU-021", "/v1/dev/tasks/HOT-DU-021", {}),
    ("/v1/dial-dev/agents", "/v1/dev/agents", {}),
    ("/v1/dial-dev/workspaces", "/v1/dev/workspaces", {}),
    ("/v1/dial-dev/workspaces/ws-7", "/v1/dev/workspaces/ws-7", {}),
    ("/v1/dial-dev/workspaces/ws-7/diff", "/v1/dev/workspaces/ws-7/diff", {}),
    ("/v1/dial-dev/workspaces/ws-7/terminal-tail?lines=50", "/v1/dev/workspaces/ws-7/terminal-tail", {"lines": "50"}),
    ("/v1/dial-dev/reviews", "/v1/dev/reviews", {}),
    ("/v1/dial-dev/memory", "/v1/dev/memory", {}),
    ("/v1/dial-dev/research", "/v1/dev/research", {}),
    ("/v1/dial-dev/design", "/v1/dev/design", {}),
    ("/v1/dial-dev/ci", "/v1/dev/ci", {}),
    ("/v1/dial-dev/security", "/v1/dev/security", {}),
    ("/v1/dial-dev/evidence/EV-sha256:abc123", "/v1/dev/evidence/EV-sha256:abc123", {}),
    ("/v1/dial-dev/infrastructure", "/v1/dev/infrastructure", {}),
]


def _serve_all(dial: FakeDial) -> None:
    for _van, upstream, _params in READS:
        dial.json("GET", upstream, envelope({"path": upstream}))


# --------------------------------------------------------------------- authentication


@pytest.mark.asyncio
class TestReadsNeedOwnerDeviceAuth:

    @pytest.mark.parametrize("van_path", [r[0] for r in READS] + ["/v1/dial-dev/events"])
    async def test_no_ingress_token_is_refused_before_dial_is_asked(self, gateway, van_path):
        ac, _app, dial = gateway
        response = await ac.get(van_path)
        assert response.status_code == 401
        assert dial.requests == []

    @pytest.mark.parametrize("van_path", [r[0] for r in READS])
    async def test_ingress_without_a_device_token_is_refused(self, gateway, van_path):
        ac, _app, dial = gateway
        response = await ac.get(van_path, headers={"X-Van-Ingress-Token": INGRESS})
        assert response.status_code == 401
        assert response.json()["detail"] == "device_access_denied"
        assert dial.requests == []

    async def test_an_internal_control_credential_is_not_an_owner_device(self, gateway):
        """A Hermes-runtime credential does not reach DIAL development state."""
        ac, _app, dial = gateway
        response = await ac.get(
            "/v1/dial-dev/projects",
            headers={"X-Van-Ingress-Token": INGRESS, "X-Van-Internal-Token": INTERNAL},
        )
        assert response.status_code == 401
        assert dial.requests == []

    async def test_reads_do_not_demand_a_hardware_proof(self, gateway):
        """A poll must not put a Keystore signature in the battery path (ADR-RB-025)."""
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        _serve_all(dial)
        response = await ac.get("/v1/dial-dev/projects", headers=_auth(enrolled))
        assert response.status_code == 200


@pytest.mark.asyncio
class TestActionsNeedADeviceProof:

    async def test_a_bound_device_without_a_proof_is_refused(self, gateway):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        response = await ac.post(ACTIONS_PATH, json=_action(), headers=_auth(enrolled))
        assert response.status_code == 401
        assert response.json()["detail"] == "device_proof_required"
        assert dial.calls("POST", "/v1/dev/actions") == []

    async def test_a_proof_for_another_body_is_refused(self, gateway):
        ac, app, dial = gateway
        enrolled, key = await _owner(app)
        signed = json.dumps(_action("PAUSE_TASK_SAFE")).encode()
        sent = json.dumps(_action("REVOKE_TASK")).encode()
        headers = {**_auth(enrolled), **_proof(key, device_id=enrolled.device.device_id, body=signed),
                   "content-type": "application/json"}
        response = await ac.post(ACTIONS_PATH, content=sent, headers=headers)
        assert response.status_code == 401
        assert dial.calls("POST", "/v1/dev/actions") == []

    async def test_a_signed_action_is_forwarded(self, gateway):
        ac, app, dial = gateway
        enrolled, key = await _owner(app)
        dial.json("POST", "/v1/dev/actions", {"action_id": "act-1", "state": "ACCEPTED"}, status=202)
        response = await _post_action(ac, enrolled, key, _action())
        assert response.status_code == 202, response.text
        assert response.json() == {"action_id": "act-1", "state": "ACCEPTED"}
        [sent] = dial.calls("POST", "/v1/dev/actions")
        forwarded = json.loads(sent.content)
        assert set(forwarded) == {
            "action", "target", "params", "idempotency_key",
            "expected_projection_revision", "owner_device_proof_ref",
        }
        assert forwarded["action"] == "PAUSE_TASK_SAFE"
        assert forwarded["owner_device_proof_ref"].startswith("van-device-proof:sha256:")

    async def test_the_device_cannot_choose_its_own_proof_ref(self, gateway):
        ac, app, dial = gateway
        enrolled, key = await _owner(app)
        dial.json("POST", "/v1/dev/actions", {"action_id": "act-1", "state": "ACCEPTED"}, status=202)
        response = await _post_action(
            ac, enrolled, key, _action(owner_device_proof_ref="forged-ref")
        )
        assert response.status_code == 202
        forwarded = json.loads(dial.calls("POST", "/v1/dev/actions")[0].content)
        assert forwarded["owner_device_proof_ref"] != "forged-ref"


@pytest.mark.asyncio
async def test_an_unbound_device_cannot_act_on_dial_on_its_token_alone(tmp_path, monkeypatch):
    """The middleware's migration fallback lets an unbound device through on its token.

    Other owner routes accept that while a deployment migrates. A DIAL action does not: it
    is refused unless a proof was actually verified.
    """
    _env(monkeypatch, tmp_path, bind=False)
    app = create_app()
    dial = FakeDial()
    app.state.dial_dev_client.transport = dial.transport()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            enrolled = await _paired(app)
            response = await ac.post(ACTIONS_PATH, json=_action(), headers=_auth(enrolled))
    get_settings.cache_clear()
    assert response.status_code == 403
    assert response.json() == {"error": "device_proof_required"}
    assert dial.requests == []


# ------------------------------------------------------------------ pass-through


@pytest.mark.asyncio
class TestEnvelopePassThrough:

    @pytest.mark.parametrize("van_path,upstream,params", READS)
    async def test_every_read_reaches_its_dial_path_and_returns_the_envelope_unchanged(
        self, gateway, van_path, upstream, params
    ):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        _serve_all(dial)
        response = await ac.get(van_path, headers=_auth(enrolled))
        assert response.status_code == 200, response.text
        [sent] = dial.requests
        assert sent.url.path == upstream
        assert dict(sent.url.params) == params
        # Byte for byte: the gateway neither re-serialises nor annotates the envelope.
        assert response.content == json.dumps(envelope({"path": upstream})).encode()
        assert response.headers["cache-control"] == "no-store"

    async def test_the_bearer_reaches_dial_and_no_van_credential_does(self, gateway):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        _serve_all(dial)
        await ac.get("/v1/dial-dev/projects", headers={**_auth(enrolled), "Cookie": "x=y"})
        [sent] = dial.requests
        assert sent.headers["authorization"] == f"Bearer {DIAL_TOKEN}"
        lowered = {k.lower() for k in sent.headers}
        assert not any(k.startswith("x-van-") for k in lowered)
        assert "cookie" not in lowered
        assert str(sent.url).startswith(DIAL_BASE_URL)

    async def test_stale_thresholds_travel_beside_the_envelope(self, gateway):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        _serve_all(dial)
        tasks = await ac.get("/v1/dial-dev/agents", headers=_auth(enrolled))
        spaces = await ac.get("/v1/dial-dev/workspaces", headers=_auth(enrolled))
        assert tasks.headers["x-van-dial-dev-stale-after-ms"] == "30000"
        assert spaces.headers["x-van-dial-dev-stale-after-ms"] == "10000"

    async def test_a_dial_404_is_dials_answer_not_the_gateways(self, gateway):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        dial.json("GET", "/v1/dev/tasks/HOT-DU-999", {"error": "task_unknown"}, status=404)
        response = await ac.get("/v1/dial-dev/tasks/HOT-DU-999", headers=_auth(enrolled))
        assert response.status_code == 404
        assert response.json() == {"error": "task_unknown"}

    async def test_stale_view_is_passed_through_unchanged(self, gateway):
        ac, app, dial = gateway
        enrolled, key = await _owner(app)
        stale = {"error": "STALE_VIEW", "projection_revision": "sha256:rev-2",
                 "expected_projection_revision": "sha256:rev-1"}
        dial.json("POST", "/v1/dev/actions", stale, status=409)
        response = await _post_action(ac, enrolled, key, _action())
        assert response.status_code == 409
        assert response.content == json.dumps(stale).encode()

    async def test_degraded_rows_map_onto_vans_degraded_model_and_clear(self, gateway):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        rows = [{"subsystem": "OPENVIKING", "effect": "semantic recall unavailable",
                 "still_works": ["tasks"]}, {"subsystem": "orca"}, {"subsystem": "UNHEARD_OF"}]
        dial.json("GET", "/v1/dev/agents", envelope({}, degraded=rows))
        response = await ac.get("/v1/dial-dev/agents", headers=_auth(enrolled))
        assert response.json()["degraded"] == rows  # unchanged for the device
        codes = app.state.degraded.codes()
        assert "DIAL_OPENVIKING_DEGRADED" in codes and "DIAL_ORCA_DEGRADED" in codes
        dial.json("GET", "/v1/dev/agents", envelope({}, degraded=[]))
        await ac.get("/v1/dial-dev/agents", headers=_auth(enrolled))
        assert not any(c.startswith("DIAL_") for c in app.state.degraded.codes())


# ------------------------------------------------------------------- unavailable


@pytest.mark.asyncio
class TestDialUnavailableIs503:

    @pytest.mark.parametrize("failure,reason", [
        (httpx.ConnectError("refused"), "unreachable"),
        (httpx.ReadTimeout("slow"), "timeout"),
        (httpx.ConnectTimeout("slow"), "timeout"),
    ])
    async def test_transport_failure(self, gateway, failure, reason):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        dial.fail_with = failure
        response = await ac.get("/v1/dial-dev/projects", headers=_auth(enrolled))
        assert response.status_code == 503
        assert response.json() == {"error": "dial_dev_unavailable", "reason": reason}
        assert "DIAL_DEV_UNAVAILABLE" in app.state.degraded.codes()
        # The address is configuration, not something the phone needs to learn.
        assert "dial-control.test" not in response.text

    @pytest.mark.parametrize("status,reason", [
        (500, "upstream_error"), (502, "upstream_error"),
        (401, "upstream_auth_refused"), (403, "upstream_auth_refused"),
        (302, "upstream_redirect"),
    ])
    async def test_upstream_status(self, gateway, status, reason):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        dial.json("GET", "/v1/dev/projects", {"error": "x"}, status=status)
        response = await ac.get("/v1/dial-dev/projects", headers=_auth(enrolled))
        assert response.status_code == 503
        assert response.json() == {"error": "dial_dev_unavailable", "reason": reason}

    async def test_a_body_that_is_not_an_envelope_is_not_passed_off_as_one(self, gateway):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        dial.json("GET", "/v1/dev/projects", {"projects": []})
        response = await ac.get("/v1/dial-dev/projects", headers=_auth(enrolled))
        assert response.status_code == 503
        assert response.json()["reason"] == "upstream_malformed"

    async def test_recovery_clears_the_degraded_entry(self, gateway):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        dial.fail_with = httpx.ConnectError("refused")
        await ac.get("/v1/dial-dev/projects", headers=_auth(enrolled))
        assert "DIAL_DEV_UNAVAILABLE" in app.state.degraded.codes()
        dial.fail_with = None
        _serve_all(dial)
        assert (await ac.get("/v1/dial-dev/projects", headers=_auth(enrolled))).status_code == 200
        assert "DIAL_DEV_UNAVAILABLE" not in app.state.degraded.codes()

    async def test_a_missing_token_file_is_unavailable_not_a_crash(self, gateway, tmp_path):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        (tmp_path / "dial-dev.token").unlink()
        response = await ac.get("/v1/dial-dev/projects", headers=_auth(enrolled))
        assert response.status_code == 503
        assert response.json()["reason"] == "unconfigured"
        assert dial.requests == []

    async def test_an_action_dial_never_received_can_be_retried_under_the_same_key(self, gateway):
        ac, app, dial = gateway
        enrolled, key = await _owner(app)
        dial.fail_with = httpx.ConnectError("refused")
        first = await _post_action(ac, enrolled, key, _action())
        assert first.status_code == 503
        dial.fail_with = None
        dial.json("POST", "/v1/dev/actions", {"action_id": "act-9", "state": "ACCEPTED"}, status=202)
        second = await _post_action(ac, enrolled, key, _action())
        assert second.status_code == 202
        assert len(dial.calls("POST", "/v1/dev/actions")) == 2


@pytest.mark.asyncio
async def test_disabled_is_404_feature_disabled(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path, enabled=False)
    app = create_app()
    dial = FakeDial()
    app.state.dial_dev_client.transport = dial.transport()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            enrolled, key = await _owner(app)
            read = await ac.get("/v1/dial-dev/projects", headers=_auth(enrolled))
            events = await ac.get("/v1/dial-dev/events", headers=_auth(enrolled))
            act = await _post_action(ac, enrolled, key, _action())
    get_settings.cache_clear()
    for response in (read, events, act):
        assert response.status_code == 404
        assert response.json() == {"error": "dial_dev_disabled"}
    assert dial.requests == []


# ------------------------------------------------------------------ the credential


@pytest.mark.asyncio
class TestTheCredentialNeverComesBack:

    async def test_no_route_ever_returns_the_dial_credential(self, gateway):
        ac, app, dial = gateway
        enrolled, key = await _owner(app)
        _serve_all(dial)
        dial.json("POST", "/v1/dev/actions", {"action_id": "a", "state": "ACCEPTED"}, status=202)
        responses = [await ac.get(van, headers=_auth(enrolled)) for van, _u, _p in READS]
        responses.append(await _post_action(ac, enrolled, key, _action()))
        dial.fail_with = httpx.ConnectError(f"refused {DIAL_TOKEN}")
        responses.append(await ac.get("/v1/dial-dev/projects", headers=_auth(enrolled)))
        responses.append(await ac.get("/health", headers=_auth(enrolled)))
        responses.append(await ac.get("/v1/degraded", headers=_auth(enrolled)))
        for response in responses:
            assert DIAL_TOKEN not in response.text
            assert all(DIAL_TOKEN not in v for v in response.headers.values())

    async def test_dial_echoing_the_bearer_is_refused_not_relayed(self, gateway):
        ac, app, dial = gateway
        enrolled, key = await _owner(app)

        def echo(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=envelope({"auth": request.headers["authorization"]}))

        dial.raw("GET", "/v1/dev/agents", echo)
        dial.raw("POST", "/v1/dev/actions", echo)
        read = await ac.get("/v1/dial-dev/agents", headers=_auth(enrolled))
        act = await _post_action(ac, enrolled, key, _action())
        for response in (read, act):
            assert response.status_code == 503
            assert response.json()["reason"] == "upstream_echoed_credential"
            assert DIAL_TOKEN not in response.text

    async def test_the_event_stream_drops_a_line_carrying_the_credential(self, gateway):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        frames = (
            'data: {"projection_revision": "sha256:rev-2", "changed": ["tasks"]}\n\n'
            f'data: {{"leak": "{DIAL_TOKEN}"}}\n\n'
            'data: {"projection_revision": "sha256:rev-3", "changed": ["workspaces"]}\n\n'
        )
        dial.raw("GET", "/v1/dev/events", httpx.Response(
            200, content=frames.encode(), headers={"content-type": "text/event-stream"}))
        response = await ac.get("/v1/dial-dev/events", headers=_auth(enrolled))
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert '"sha256:rev-2"' in response.text and '"sha256:rev-3"' in response.text
        assert DIAL_TOKEN not in response.text
        [sent] = dial.calls("GET", "/v1/dev/events")
        assert sent.headers["accept"] == "text/event-stream"

    async def test_the_event_stream_unreachable_is_503(self, gateway):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        dial.fail_with = httpx.ConnectError("refused")
        response = await ac.get("/v1/dial-dev/events", headers=_auth(enrolled))
        assert response.status_code == 503
        assert response.json() == {"error": "dial_dev_unavailable", "reason": "unreachable"}


# ---------------------------------------------------------------- request shape


@pytest.mark.asyncio
class TestRequestsAreRefusedBeforeDialSeesThem:

    @pytest.mark.parametrize("van_path,reason", [
        ("/v1/dial-dev/projects/p1/tasks", "view"),
        ("/v1/dial-dev/projects/p1/tasks?view=everything", "view"),
        ("/v1/dial-dev/workspaces/ws-7/terminal-tail?lines=201", "lines"),
        ("/v1/dial-dev/workspaces/ws-7/terminal-tail?lines=0", "lines"),
        ("/v1/dial-dev/workspaces/ws-7/terminal-tail?lines=all", "lines"),
        ("/v1/dial-dev/tasks/.hidden", "task_id"),
        ("/v1/dial-dev/tasks/a..b", "task_id"),
        ("/v1/dial-dev/evidence/%20x", "evidence_ref"),
    ])
    async def test_invalid_reads(self, gateway, van_path, reason):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        response = await ac.get(van_path, headers=_auth(enrolled))
        assert response.status_code == 422, response.text
        assert response.json() == {"error": "dial_dev_request_invalid", "reason": reason}
        assert dial.requests == []

    async def test_an_encoded_slash_cannot_reach_another_dial_endpoint(self, gateway):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        _serve_all(dial)
        response = await ac.get("/v1/dial-dev/tasks/x%2F..%2Factions", headers=_auth(enrolled))
        assert response.status_code in (404, 422)
        assert all(r.url.path.startswith("/v1/dev/") and "actions" not in r.url.path
                   for r in dial.requests)

    async def test_terminal_tail_defaults_to_the_contract_bound(self, gateway):
        ac, app, dial = gateway
        enrolled, _key = await _owner(app)
        _serve_all(dial)
        await ac.get("/v1/dial-dev/workspaces/ws-7/terminal-tail", headers=_auth(enrolled))
        assert dict(dial.requests[0].url.params) == {"lines": "200"}

    async def test_an_action_outside_the_closed_set_never_leaves_the_gateway(self, gateway):
        ac, app, dial = gateway
        enrolled, key = await _owner(app)
        for action in ("RUN_SHELL", "TERMINAL_INPUT", "pause_task_safe", "MARK_DONE", ""):
            response = await _post_action(ac, enrolled, key, _action(action, key=f"idem-{action}-xyz"))
            assert response.status_code == 422, action
            assert response.json()["error"] == "dial_dev_action_not_allowed"
        assert dial.calls("POST", "/v1/dev/actions") == []

    @pytest.mark.parametrize("action", sorted(ACTIONS))
    async def test_every_action_in_the_closed_set_is_forwardable(self, gateway, action):
        ac, app, dial = gateway
        enrolled, key = await _owner(app)
        dial.json("POST", "/v1/dev/actions", {"action_id": "a", "state": "ACCEPTED"}, status=202)
        target = {"project_id": "dial-development-system", "task_id": "HOT-DU-021"}
        params: dict = {}
        if action == "STEER_TASK":
            params = {"guidance": "Prefer the existing lease index over a new table."}
        if action == "DECIDE":
            target["decision_id"] = "DEC-77"
            params = {"decision": "APPROVE", "reason": "evidence admitted"}
        response = await _post_action(
            ac, enrolled, key, _action(action, key=f"idem-{action}", target=target, params=params)
        )
        assert response.status_code == 202, response.text
        assert json.loads(dial.calls("POST", "/v1/dev/actions")[0].content)["action"] == action

    @pytest.mark.parametrize("mutate,reason", [
        (lambda b: b.update(action="STEER_TASK"), "params.guidance"),
        (lambda b: b.update(action="DECIDE", params={"decision": "APPROVE"}), "target.decision_id"),
        (lambda b: (b.update(action="DECIDE", params={"decision": "MAYBE"}),
                    b["target"].update(decision_id="DEC-1")), "params.decision"),
        (lambda b: b["target"].pop("task_id"), "target.task_id"),
        (lambda b: b["target"].update(project_id="../etc"), "target.project_id"),
        (lambda b: b.pop("expected_projection_revision"), "expected_projection_revision"),
        (lambda b: b.update(idempotency_key="short"), "idempotency_key"),
        (lambda b: b.update(raw_terminal_input="rm -rf /"), "raw_terminal_input"),
    ])
    async def test_malformed_actions(self, gateway, mutate, reason):
        ac, app, dial = gateway
        enrolled, key = await _owner(app)
        body = _action()
        mutate(body)
        response = await _post_action(ac, enrolled, key, body)
        assert response.status_code == 422, response.text
        assert response.json() == {"error": "dial_dev_request_invalid", "reason": reason}
        assert dial.calls("POST", "/v1/dev/actions") == []


# ------------------------------------------------------------------ idempotency


@pytest.mark.asyncio
class TestIdempotentRetry:

    async def test_a_retried_action_is_forwarded_once_and_answered_the_same(self, gateway):
        ac, app, dial = gateway
        enrolled, key = await _owner(app)
        dial.json("POST", "/v1/dev/actions", {"action_id": "act-1", "state": "ACCEPTED"}, status=202)
        first = await _post_action(ac, enrolled, key, _action())
        second = await _post_action(ac, enrolled, key, _action())
        assert first.status_code == second.status_code == 202
        assert first.json() == second.json()
        assert second.headers["x-van-idempotent-replay"] == "true"
        assert len(dial.calls("POST", "/v1/dev/actions")) == 1

    async def test_the_same_key_for_a_different_action_is_a_conflict(self, gateway):
        ac, app, dial = gateway
        enrolled, key = await _owner(app)
        dial.json("POST", "/v1/dev/actions", {"action_id": "act-1", "state": "ACCEPTED"}, status=202)
        await _post_action(ac, enrolled, key, _action("PAUSE_TASK_SAFE"))
        response = await _post_action(ac, enrolled, key, _action("REVOKE_TASK"))
        assert response.status_code == 409
        assert response.json() == {"error": "idempotency_conflict"}
        assert len(dial.calls("POST", "/v1/dev/actions")) == 1

    async def test_keys_are_namespaced_away_from_owner_commands(self, gateway):
        ac, app, dial = gateway
        enrolled, key = await _owner(app)
        dial.json("POST", "/v1/dev/actions", {"action_id": "act-1", "state": "ACCEPTED"}, status=202)
        await _post_action(ac, enrolled, key, _action(key="shared-key-123"))
        rows = await app.state.store.fetchall(
            "SELECT idempotency_key FROM idempotency WHERE idempotency_key LIKE ?", ("%shared-key-123",)
        )
        assert [r["idempotency_key"] for r in rows] == ["dial-dev:shared-key-123"]
