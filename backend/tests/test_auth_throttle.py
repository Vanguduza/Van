"""P1-SEC-007: brute-force controls on the owner authentication surfaces.

The audit found no failed-attempt counter, no backoff and no lockout anywhere: device
pairing, the ingress token, the device token, command signatures and A4 approval proofs
all accepted unlimited attempts from anyone who could reach the tunnel.

Two postures are enforced and both are asserted here, because the difference between them
is the whole design and a regression in either direction is a real defect:

  * pairing is a **hard** lockout — checked before the ticket is looked at;
  * every surface on the owner's live command path is **soft** — a correct credential
    always passes, so an attacker can never silence the assistant.
"""

from __future__ import annotations

import base64
import re
import sys
import time
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.approval import service as approval_service
from van_gateway.auth.service import AuthService
from van_gateway.auth.throttle import (
    GLOBAL_SUBJECT,
    POLICIES,
    AuthThrottle,
    Throttled,
)
from van_gateway.config import get_settings

#: GAP-F-005 — "halt autonomous trading" now resolves to the gateway-executed
#: `trading.halt` typed action (command/local_executors.py) rather than a Hermes
#: dispatch, so a genuine approval of it needs a real owner-halt authority token to
#: reach VERIFIED_SUCCESS. Same fixtures test_a4_owner_approval.py and
#: test_local_typed_actions.py use.
sys.path[:0] = [
    str(Path(__file__).resolve().parents[2] / "trading" / "tests"),
    str(Path(__file__).resolve().parents[2] / "trading"),
]
from conftest_owner_authority import OwnerAuthorityHarness  # noqa: E402
from van_gateway.trading.service import _import_vati  # noqa: E402

EventKind, make_event, Ledger = _import_vati()

INGRESS = "throttle-ingress-token-0123456789abcd"


class TestThrottlePrimitive:
    def test_failures_below_the_threshold_do_not_lock(self):
        t = AuthThrottle()
        policy = POLICIES["pairing"]
        for _ in range(policy.max_failures - 1):
            t.record_failure("pairing", GLOBAL_SUBJECT)
        assert not t.is_locked("pairing", GLOBAL_SUBJECT)

    def test_the_threshold_failure_locks_for_the_policy_duration(self):
        t = AuthThrottle()
        policy = POLICIES["pairing"]
        for _ in range(policy.max_failures):
            t.record_failure("pairing", GLOBAL_SUBJECT, now=1000.0)

        with pytest.raises(Throttled) as caught:
            t.check("pairing", GLOBAL_SUBJECT, now=1000.0)
        assert caught.value.retry_after_seconds > 0
        assert caught.value.retry_after_seconds <= policy.lockout_seconds + 1

    def test_the_lockout_expires_on_its_own(self):
        t = AuthThrottle()
        policy = POLICIES["device_token"]
        for _ in range(policy.max_failures):
            t.record_failure("device_token", GLOBAL_SUBJECT, now=1000.0)
        assert t.is_locked("device_token", GLOBAL_SUBJECT, now=1000.0)
        assert not t.is_locked(
            "device_token", GLOBAL_SUBJECT, now=1000.0 + policy.lockout_seconds + 1
        )

    def test_failures_outside_the_window_do_not_accumulate(self):
        """A typo a week ago must not combine with a typo today into a lockout."""
        t = AuthThrottle()
        policy = POLICIES["command_signature"]
        base = 1000.0
        for i in range(policy.max_failures - 1):
            t.record_failure("command_signature", "dev-1", now=base + i)
        # Well past the window, so every earlier failure has aged out.
        later = base + policy.window_seconds * 3
        for i in range(policy.max_failures - 1):
            t.record_failure("command_signature", "dev-1", now=later + i)
        assert not t.is_locked("command_signature", "dev-1", now=later + policy.max_failures)

    def test_success_clears_the_history(self):
        t = AuthThrottle()
        policy = POLICIES["command_signature"]
        for _ in range(policy.max_failures - 1):
            t.record_failure("command_signature", "dev-1")
        t.record_success("command_signature", "dev-1")
        for _ in range(policy.max_failures - 1):
            t.record_failure("command_signature", "dev-1")
        assert not t.is_locked("command_signature", "dev-1"), (
            "a successful authentication must reset the counter"
        )

    def test_surfaces_are_isolated(self):
        t = AuthThrottle()
        for _ in range(POLICIES["pairing"].max_failures):
            t.record_failure("pairing", GLOBAL_SUBJECT)
        assert t.is_locked("pairing", GLOBAL_SUBJECT)
        assert not t.is_locked("ingress_token", GLOBAL_SUBJECT), (
            "locking pairing must not lock the owner's command path"
        )

    def test_subjects_are_isolated(self):
        """One device's failures must not lock a different device out."""
        t = AuthThrottle()
        for _ in range(POLICIES["command_signature"].max_failures):
            t.record_failure("command_signature", "dev-attacked")
        assert t.is_locked("command_signature", "dev-attacked")
        assert not t.is_locked("command_signature", "dev-other")

    def test_fail_records_and_raises_in_one_call(self):
        t = AuthThrottle()
        policy = POLICIES["approval_challenge"]
        for _ in range(policy.max_failures - 1):
            t.fail("approval_challenge", "dev-1")
        with pytest.raises(Throttled):
            t.fail("approval_challenge", "dev-1")

    def test_every_named_policy_is_a_real_bound(self):
        """A policy of zero failures or zero lockout would be a control in name only."""
        for surface, policy in POLICIES.items():
            assert policy.max_failures >= 1, surface
            assert policy.window_seconds > 0, surface
            assert policy.lockout_seconds > 0, surface

    def test_reset_forgets_everything(self):
        t = AuthThrottle()
        for _ in range(POLICIES["pairing"].max_failures):
            t.record_failure("pairing", GLOBAL_SUBJECT)
        t.reset()
        assert not t.is_locked("pairing", GLOBAL_SUBJECT)


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "throttle.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "throttle-internal-token")
    # P0-SEC-001 — device enrolment is its own credential now.
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", "throttle-internal-token")
    monkeypatch.setenv("VAN_VATI_LEDGER_PATH", str(tmp_path / "vati.sqlite"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(monkeypatch):
    app = create_app()

    async def fake_health():
        return {"ok": True, "profile": "van"}

    async def fake_create_run(text, metadata=None):
        return {"id": "run-throttle-1", "status": "accepted"}

    monkeypatch.setattr(app.state.orchestrator.hermes, "health", fake_health)
    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", fake_create_run)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            yield ac, app


@pytest.mark.asyncio
class TestGatewayEnforcement:
    async def test_the_ingress_token_locks_out_after_the_policy(self, client):
        ac, app = client
        policy = POLICIES["ingress_token"]
        codes = []
        for _ in range(policy.max_failures + 1):
            resp = await ac.get("/health", headers={"X-Van-Ingress-Token": "wrong"})
            codes.append(resp.status_code)

        assert codes[0] == 401, "the first wrong token must simply be refused"
        assert codes[-1] == 429, f"unlimited attempts were still accepted: {codes}"

    async def test_a_throttled_refusal_tells_the_client_when_to_come_back(self, client):
        ac, app = client
        for _ in range(POLICIES["ingress_token"].max_failures + 1):
            resp = await ac.get("/health", headers={"X-Van-Ingress-Token": "wrong"})
        assert resp.status_code == 429
        assert int(resp.headers["Retry-After"]) > 0
        assert resp.json()["retry_after_seconds"] > 0

    async def test_the_correct_ingress_token_still_works_while_locked_out(self, client):
        """The soft posture, asserted directly: an attacker cannot silence the owner."""
        ac, app = client
        for _ in range(POLICIES["ingress_token"].max_failures + 1):
            await ac.get("/health", headers={"X-Van-Ingress-Token": "wrong"})
        assert app.state.auth_throttle.is_locked("ingress_token", GLOBAL_SUBJECT)

        resp = await ac.get("/health", headers={"X-Van-Ingress-Token": INGRESS})
        assert resp.status_code == 200, (
            "a lockout on the owner's own command path would be a denial of service"
        )

    async def test_a_successful_ingress_auth_clears_the_counter(self, client):
        ac, app = client
        policy = POLICIES["ingress_token"]
        for _ in range(policy.max_failures - 1):
            await ac.get("/health", headers={"X-Van-Ingress-Token": "wrong"})
        await ac.get("/health", headers={"X-Van-Ingress-Token": INGRESS})
        assert not app.state.auth_throttle.is_locked("ingress_token", GLOBAL_SUBJECT)

        resp = await ac.get("/health", headers={"X-Van-Ingress-Token": "wrong"})
        assert resp.status_code == 401, "the counter did not reset after a success"

    async def test_the_device_token_locks_out_after_the_policy(self, client):
        ac, _ = client
        policy = POLICIES["device_token"]
        headers = {"X-Van-Ingress-Token": INGRESS, "X-Van-Device-Token": "not-a-token"}
        codes = [
            (await ac.get("/v1/activity", headers=headers)).status_code
            for _ in range(policy.max_failures + 1)
        ]
        assert codes[0] == 401
        assert codes[-1] == 429, f"unlimited device-token guesses were accepted: {codes}"

    async def test_pairing_is_a_hard_lockout(self, client):
        """Pairing is the one surface where a correct ticket is refused while locked."""
        ac, app = client
        policy = POLICIES["pairing"]
        body = {
            "pairing_token": "x" * 40,
            "device_id": "throttle-dev",
            "device_secret": "s" * 32,
            "public_key_pem": "PEM",
            "label": "L",
        }
        codes = [
            (await ac.post("/v1/devices/pair", json=body)).status_code
            for _ in range(policy.max_failures)
        ]
        assert codes[0] == 400, "a bad ticket is a client error before the policy is hit"

        ticket = await app.state.auth.create_pairing_ticket("throttle-dev")
        resp = await ac.post("/v1/devices/pair", json={**body, "pairing_token": ticket.token})
        assert resp.status_code == 429, (
            "the hard posture must refuse even a genuine ticket during the lockout"
        )
        assert int(resp.headers["Retry-After"]) > 0

    async def test_a_valid_pairing_is_untouched_when_nothing_has_failed(self, client):
        ac, app = client
        ticket = await app.state.auth.create_pairing_ticket("throttle-ok")
        resp = await ac.post(
            "/v1/devices/pair",
            json={
                "pairing_token": ticket.token,
                "device_id": "throttle-ok",
                "device_secret": "s" * 32,
                "public_key_pem": "PEM",
                "label": "L",
            },
        )
        assert resp.status_code == 200

    async def test_re_pairing_an_enrolled_device_does_not_count_as_a_guess(self, client):
        """`already_enrolled` proves the ticket was genuine; it is a client bug, not an attack."""
        ac, app = client
        for i in range(POLICIES["pairing"].max_failures + 2):
            ticket = await app.state.auth.create_pairing_ticket("throttle-dup")
            resp = await ac.post(
                "/v1/devices/pair",
                json={
                    "pairing_token": ticket.token,
                    "device_id": "throttle-dup",
                    "device_secret": "s" * 32,
                    "public_key_pem": "PEM",
                    "label": "L",
                },
            )
            if i == 0:
                assert resp.status_code == 200
            else:
                assert resp.status_code == 409, resp.text
        assert not app.state.auth_throttle.is_locked("pairing", GLOBAL_SUBJECT)


@pytest.mark.asyncio
class TestCommandSignatureThrottle:
    async def _enrol(self, ac, app, device_id):
        ticket = await app.state.auth.create_pairing_ticket(device_id)
        enrolled = await app.state.auth.pair_device(
            ticket.token, device_id, "s" * 32, "PEM", device_id
        )
        ac.headers.update(
            {
                "X-Van-Ingress-Token": INGRESS,
                "X-Van-Device-Token": enrolled.access_token,
            }
        )
        return enrolled

    def _body(self, app, device_id, *, suffix, signature):
        issued = int(time.time())
        cid = f"thr-{device_id}-{suffix}"
        return {
            "command_id": cid,
            "idempotency_key": f"idem-{cid}",
            "device_id": device_id,
            "issued_at_unix": issued,
            "signature": signature,
            "text": "Van, brief me.",
            "action_class": "A1",
        }

    def _signed(self, app, device_id, *, suffix):
        issued = int(time.time())
        cid = f"thr-{device_id}-{suffix}"
        canonical = AuthService.canonical_command(
            command_id=cid,
            idempotency_key=f"idem-{cid}",
            device_id=device_id,
            issued_at_unix=issued,
            text="Van, brief me.",
            action_class="A1",
            project_id=None,
        )
        return {
            "command_id": cid,
            "idempotency_key": f"idem-{cid}",
            "device_id": device_id,
            "issued_at_unix": issued,
            "signature": app.state.auth.sign(device_id, canonical),
            "text": "Van, brief me.",
            "action_class": "A1",
        }

    async def test_invalid_signatures_lock_the_device_out(self, client):
        ac, app = client
        await self._enrol(ac, app, "thr-sig-1")
        policy = POLICIES["command_signature"]

        reasons = []
        for i in range(policy.max_failures + 1):
            body = self._body(app, "thr-sig-1", suffix=i, signature="deadbeef")
            resp = await ac.post("/v1/commands", json=body)
            reasons.append(resp.json()["message"])

        assert "Signature" in reasons[0] or "signature" in reasons[0], reasons[0]
        assert "retry in" in reasons[-1], f"signature guessing was never throttled: {reasons[-1]}"

    async def test_a_correctly_signed_command_still_executes_while_throttled(self, client):
        ac, app = client
        await self._enrol(ac, app, "thr-sig-2")
        for i in range(POLICIES["command_signature"].max_failures + 1):
            await ac.post(
                "/v1/commands",
                json=self._body(app, "thr-sig-2", suffix=i, signature="deadbeef"),
            )
        assert app.state.auth_throttle.is_locked("command_signature", "thr-sig-2")

        resp = await ac.post("/v1/commands", json=self._signed(app, "thr-sig-2", suffix="good"))
        assert resp.json()["status"] in {"accepted", "degraded"}, resp.text

    async def test_a_valid_command_clears_the_signature_counter(self, client):
        ac, app = client
        await self._enrol(ac, app, "thr-sig-3")
        for i in range(POLICIES["command_signature"].max_failures - 1):
            await ac.post(
                "/v1/commands",
                json=self._body(app, "thr-sig-3", suffix=i, signature="deadbeef"),
            )
        await ac.post("/v1/commands", json=self._signed(app, "thr-sig-3", suffix="good"))
        assert not app.state.auth_throttle.is_locked("command_signature", "thr-sig-3")

    async def test_one_device_cannot_throttle_another(self, client):
        ac, app = client
        await self._enrol(ac, app, "thr-sig-4")
        for i in range(POLICIES["command_signature"].max_failures + 1):
            await ac.post(
                "/v1/commands",
                json=self._body(app, "thr-sig-4", suffix=i, signature="deadbeef"),
            )
        assert app.state.auth_throttle.is_locked("command_signature", "thr-sig-4")
        assert not app.state.auth_throttle.is_locked("command_signature", "thr-sig-5")


@pytest.mark.asyncio
class TestApprovalChallengeThrottle:
    """The A4 surface, where a successful forgery authorises a destructive action."""

    @staticmethod
    def _public_pem(key) -> str:
        return key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

    def _a4_command(self, app, *, device_id, idempotency_key, proof=None, client_context=None):
        issued = int(time.time())
        command_id = str(uuid.uuid4())
        nonce = str(uuid.uuid4())
        text = "halt autonomous trading"
        canonical = AuthService.canonical_command_v2(
            command_id=command_id,
            idempotency_key=idempotency_key,
            device_id=device_id,
            issued_at_unix=issued,
            text=text,
            action_class="A1",
            project_id=None,
            turn_id="turn-thr",
            origin_channel="VOICE",
            principal_type="OWNER_DEVICE",
            requested_by=f"device:{device_id}",
            expires_at_unix=issued + 5,
            nonce=nonce,
            context_capsule_revision=None,
            context_capsule_hash=None,
            speech_evidence_ref="speech://thr",
            no_stale_replay=True,
            context_trust="CONVERSATION",
        )
        body = {
            "command_id": command_id,
            "idempotency_key": idempotency_key,
            "device_id": device_id,
            "issued_at_unix": issued,
            "signature": app.state.auth.sign(device_id, canonical),
            "signature_version": 2,
            "text": text,
            "action_class": "A1",
            "turn_id": "turn-thr",
            "origin_channel": "VOICE",
            "principal_type": "OWNER_DEVICE",
            "requested_by": f"device:{device_id}",
            "expires_at_unix": issued + 5,
            "nonce": nonce,
            "speech_evidence_ref": "speech://thr",
            "no_stale_replay": True,
            "context_trust": "CONVERSATION",
        }
        if proof is not None:
            body["approval_proof"] = proof
        if client_context is not None:
            body["client_context"] = client_context
        return body

    async def test_forged_approval_proofs_lock_the_device_out(self, client):
        ac, app = client
        device_id = "thr-a4"
        key = ec.generate_private_key(ec.SECP256R1())
        ticket = await app.state.auth.create_pairing_ticket(device_id)
        enrolled = await app.state.auth.pair_device(
            ticket.token, device_id, "s" * 32, self._public_pem(key), device_id
        )
        ac.headers.update(
            {"X-Van-Ingress-Token": INGRESS, "X-Van-Device-Token": enrolled.access_token}
        )

        messages = []
        for i in range(POLICIES["approval_challenge"].max_failures + 1):
            body = self._a4_command(
                app,
                device_id=device_id,
                idempotency_key=f"thr-a4-{i}",
                proof={
                    "challenge_id": str(uuid.uuid4()),   # a guess at somebody's challenge
                    "signature_b64": base64.b64encode(b"forged").decode("ascii"),
                    "algorithm": "ECDSA_P256_SHA256",
                },
            )
            resp = await ac.post("/v1/commands", json=body)
            messages.append(resp.json()["message"])

        assert "invalid, expired, or already consumed" in messages[0], messages[0]
        assert "retry in" in messages[-1], (
            f"approval-proof forgery was never throttled: {messages[-1]}"
        )

    async def test_a_genuine_approval_still_succeeds_while_throttled(self, client, tmp_path):
        """The soft posture on A4: the owner can always approve, whatever an attacker did."""
        ac, app = client
        now = int(time.time() * 1000)
        led = Ledger(tmp_path / "vati.sqlite")
        led.append(make_event(
            EventKind.SESSION, "vati-runner", {"startup": True},
            event_time_ms=now, received_time_ms=now, correlation_id="thr-s1",
        ))
        led.close()
        harness = OwnerAuthorityHarness()
        app.state.trading.owner_authority = harness.verifier

        device_id = "thr-a4-ok"
        key = ec.generate_private_key(ec.SECP256R1())
        ticket = await app.state.auth.create_pairing_ticket(device_id)
        enrolled = await app.state.auth.pair_device(
            ticket.token, device_id, "s" * 32, self._public_pem(key), device_id
        )
        ac.headers.update(
            {"X-Van-Ingress-Token": INGRESS, "X-Van-Device-Token": enrolled.access_token}
        )

        for i in range(POLICIES["approval_challenge"].max_failures + 1):
            await ac.post(
                "/v1/commands",
                json=self._a4_command(
                    app,
                    device_id=device_id,
                    idempotency_key=f"thr-a4ok-bad-{i}",
                    proof={
                        "challenge_id": str(uuid.uuid4()),
                        "signature_b64": base64.b64encode(b"forged").decode("ascii"),
                        "algorithm": "ECDSA_P256_SHA256",
                    },
                ),
            )
        assert app.state.auth_throttle.is_locked("approval_challenge", device_id)

        issued = await ac.post(
            "/v1/commands",
            json=self._a4_command(app, device_id=device_id, idempotency_key="thr-a4ok-issue"),
        )
        challenge = issued.json()
        assert challenge["status"] == "approval_required", issued.text

        signature = key.sign(
            challenge["approval_challenge"].encode("utf-8"), ec.ECDSA(hashes.SHA256())
        )
        halt_token = harness.token(act="owner-halt", subject="van-trading-core")
        approved = await ac.post(
            "/v1/commands",
            json=self._a4_command(
                app,
                device_id=device_id,
                idempotency_key="thr-a4ok-approve",
                proof={
                    "challenge_id": challenge["approval_challenge_id"],
                    "signature_b64": base64.b64encode(signature).decode("ascii"),
                    "algorithm": "ECDSA_P256_SHA256",
                },
                client_context={"owner_halt_authority_ref": halt_token},
            ),
        )
        assert approved.json()["status"] == "accepted", approved.text

    async def test_an_expired_challenge_is_not_counted_as_a_forgery(self):
        """A slow owner must not be treated as an attacker."""
        from van_gateway.orchestrator import FORGERY_SHAPED_APPROVAL_ERRORS

        legitimate = {
            "approval_proof_missing",
            "approval_challenge_expired",
            "approval_device_revoked",
            "approval_public_key_invalid",
        }
        assert not (FORGERY_SHAPED_APPROVAL_ERRORS & legitimate)

    async def test_the_counted_error_codes_all_exist_in_the_approval_service(self):
        """A typo in the set would silently disable the A4 throttle."""
        from van_gateway.orchestrator import FORGERY_SHAPED_APPROVAL_ERRORS

        source = Path(approval_service.__file__).read_text(encoding="utf-8")
        raised = set(re.findall(r'OwnerApprovalError\("([a-z_]+)"', source))
        assert FORGERY_SHAPED_APPROVAL_ERRORS <= raised, (
            f"counted codes the service never raises: "
            f"{sorted(FORGERY_SHAPED_APPROVAL_ERRORS - raised)}"
        )
