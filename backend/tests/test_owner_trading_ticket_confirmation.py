"""Phone-shaped signed commands record broker confirmations under both authority gates."""
import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from test_local_typed_actions import (_settings, client, _pair_a4_device, _public_pem,
    OwnerAuthorityHarness, Ledger, EventKind, make_event)
from van_gateway.auth.service import AuthService
from van_gateway.command.resolver import TypedCommandResolver, ResolutionMode
from van_gateway.command.success_contracts import contract_for
from van_gateway.mission.models import VerificationStatus
from van_gateway.verification.production import build_mission_registry


PARAMETERS = {"ticket_id": "ZSE-T-1", "fill_price": "001.2300", "filled_qty": "10.00", "contract_note_ref": "Broker  note #1"}


def _text(parameters=PARAMETERS):
    return "confirm trading ticket " + json.dumps(parameters, separators=(",", ":"))


def _signed(app, suffix, *, proof=None, authority=None):
    issued = int(time.time())
    body = {"command_id": "ticket-" + suffix, "idempotency_key": "ticket-key-" + suffix,
        "device_id": "ticket-owner", "issued_at_unix": issued, "text": _text(), "action_class": "A4",
        "signature_version": 2, "origin_channel": "UI", "principal_type": "OWNER_DEVICE",
        "requested_by": "device:ticket-owner", "context_trust": "CONVERSATION", "no_stale_replay": True,
        "expires_at_unix": issued + 20}
    canonical = AuthService.canonical_command_v2(command_id=body["command_id"], idempotency_key=body["idempotency_key"],
        device_id=body["device_id"], issued_at_unix=issued, text=body["text"], action_class="A4", project_id=None,
        turn_id=None, origin_channel="UI", principal_type="OWNER_DEVICE", requested_by=body["requested_by"],
        expires_at_unix=issued + 20, nonce=None, context_capsule_revision=None, context_capsule_hash=None,
        speech_evidence_ref=None, no_stale_replay=True, context_trust="CONVERSATION")
    body["signature"] = app.state.auth.sign("ticket-owner", canonical)
    if proof is not None:
        body["approval_proof"] = proof
    if authority is not None:
        body["client_context"] = {"owner_ticket_authority_ref": authority}
    return body


async def _prepare(ac, app, tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    await _pair_a4_device(ac, app, device_id="ticket-owner", secret="ticket-owner-secret", public_key_pem=_public_pem(key))
    harness = OwnerAuthorityHarness()
    app.state.trading.owner_authority = harness.verifier
    ledger = Ledger(tmp_path / "vati.sqlite")
    now = int(time.time() * 1000)
    ledger.append(make_event(EventKind.OWNER_TICKET, "vati-router", {"ticket": "ZSE-T-1", "qty": "20", "symbol": "DELTA"},
        event_time_ms=now, received_time_ms=now, correlation_id="intent-1"))
    ledger.close()
    challenge = (await ac.post("/v1/commands", json=_signed(app, "challenge"))).json()
    assert challenge["status"] == "approval_required"
    proof = {"challenge_id": challenge["approval_challenge_id"],
        "signature_b64": base64.b64encode(key.sign(challenge["approval_challenge"].encode(), ec.ECDSA(hashes.SHA256()))).decode()}
    return harness, proof


def test_confirmation_resolves_exact_normalized_amounts_and_preserves_note():
    result = TypedCommandResolver().resolve(_text())
    assert result.mode is ResolutionMode.EXACT_ACTION
    assert result.action_id == "trading.ticket.confirm" and result.canonical_action_class.value == "A4"
    assert result.parameters == {**PARAMETERS, "fill_price": "1.23", "filled_qty": "10"}
    assert result.no_stale_replay and result.max_age_seconds == 30
    assert contract_for(result).verifier_class == "trading-ticket-confirm"


@pytest.mark.parametrize("change", [{"fill_price": "NaN"}, {"filled_qty": "Infinity"}, {"fill_price": "1e99"},
    {"fill_price": "0"}, {"filled_qty": True}, {"owner_approved": True}, {"contract_note_ref": ""}])
def test_invalid_or_unbound_confirmation_parameters_cannot_resolve(change):
    assert TypedCommandResolver().resolve(_text({**PARAMETERS, **change})).mode is not ResolutionMode.EXACT_ACTION


def test_duplicate_json_confirmation_fields_do_not_resolve():
    assert TypedCommandResolver().resolve(_text().replace('"fill_price":', '"fill_price":"1","fill_price":')).mode is not ResolutionMode.EXACT_ACTION


@pytest.mark.asyncio
async def test_real_biometric_and_separate_owner_ticket_authority_record_exact_verified_confirmation(client, tmp_path):
    ac, app, calls = client
    harness, proof = await _prepare(ac, app, tmp_path)
    authority = harness.token(act="ticket-confirm", subject="ZSE-T-1")
    body = _signed(app, "approved", proof=proof, authority=authority)
    result = (await ac.post("/v1/commands", json=body)).json()
    assert result["status"] == "accepted", result
    assert result["local_execution"]["verification_state"] == "VERIFIED_SUCCESS"
    assert calls["create_run"] == 0
    ticket = app.state.trading.tickets()[0]
    assert ticket["status"] == "CONFIRMED" and ticket["fill_price"] == "1.23" and ticket["filled_qty"] == "10"
    assert ticket["contract_note_ref"] == PARAMETERS["contract_note_ref"]
    mission = await app.state.missions.get(result["mission_id"])
    assert mission.state.value == "VERIFIED_SUCCESS"
    # Exact lost response replay cannot append a second confirmation or spend authority twice.
    assert (await ac.post("/v1/commands", json=body)).json() == result
    ledger = Ledger(tmp_path / "vati.sqlite")
    assert len(list(ledger.iter(EventKind.OWNER_TICKET))) == 2
    ledger.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("authority", [None, "owner:unverified-reference"])
async def test_biometric_alone_or_unverified_owner_reference_cannot_confirm(client, tmp_path, authority):
    ac, app, _ = client
    _, proof = await _prepare(ac, app, tmp_path)
    result = (await ac.post("/v1/commands", json=_signed(app, "no-authority", proof=proof, authority=authority))).json()
    assert result["status"] == "denied", result
    assert app.state.trading.tickets()[0]["status"] == "OPEN"


@pytest.mark.asyncio
async def test_signed_ticket_authority_without_biometric_cannot_confirm(client, tmp_path):
    ac, app, _ = client
    harness, _ = await _prepare(ac, app, tmp_path)
    result = (await ac.post("/v1/commands", json=_signed(app, "no-biometric", authority=harness.token(act="ticket-confirm", subject="ZSE-T-1")))).json()
    assert result["status"] == "approval_required"
    assert app.state.trading.tickets()[0]["status"] == "OPEN"


@pytest.mark.asyncio
async def test_independent_confirmation_readback_cannot_verify_wrong_amount_or_broken_chain(client, tmp_path, monkeypatch):
    ac, app, _ = client
    harness, proof = await _prepare(ac, app, tmp_path)
    await ac.post("/v1/commands", json=_signed(app, "verified", proof=proof, authority=harness.token(act="ticket-confirm", subject="ZSE-T-1")))
    resolution = TypedCommandResolver().resolve(_text({**PARAMETERS, "filled_qty": "11"}))
    registry = build_mission_registry(store=app.state.store, trading=app.state.trading, knowledge=app.state.owner_runtime.knowledge)
    outcome = await registry.verify(strategy="trading-ticket-confirm", contract=contract_for(resolution), context={})
    assert outcome.status is VerificationStatus.FAILED and "filled_qty" in outcome.missing_postconditions
    monkeypatch.setattr(app.state.trading, "status", lambda: {"chain_ok": False})
    outcome = await registry.verify(strategy="trading-ticket-confirm", contract=contract_for(TypedCommandResolver().resolve(_text())), context={})
    assert outcome.status is VerificationStatus.FAILED and "ledger_chain_ok" in outcome.missing_postconditions
