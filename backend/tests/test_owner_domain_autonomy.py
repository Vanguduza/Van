"""Real signed owner commands change bounded ceilings, never underlying authority."""

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from tests.test_local_typed_actions import client, _settings  # noqa: F401
from tests.test_owner_memory_erasure import _command, _pair
from van_gateway.action.models import ExecutionStatus
from van_gateway.action.service import ActionPolicyError
from van_gateway.command.resolver import ResolutionMode, TypedCommandResolver
from van_gateway.command.success_contracts import contract_for
from van_gateway.models import ActionClass, PrincipalType
from van_gateway.mission.models import VerificationStatus
from van_gateway.proactive import owner_control
from van_gateway.proactive.autonomy import ActionAutonomyGate, AutonomyLevel, DomainTrustService


def _text(domain="google.gmail", level="S3", **extra):
    return owner_control.COMMAND_PREFIX + json.dumps({"domain": domain, "level": level, **extra}, separators=(",", ":"))


async def _approve(ac, app, key, *, domain="google.gmail", level="S3", idem="ceiling"):
    text = _text(domain, level)
    response = await ac.post("/v1/commands", json=_command(app, text=text, idem=idem + "-challenge"))
    challenge = response.json()
    assert challenge["status"] == "approval_required", challenge
    assert challenge["resolved_parameters"] == {"domain": domain, "level": level}
    assert challenge["resolved_action_id"] == owner_control.ACTION_ID and challenge["effective_action_class"] == "A4"
    proof = {"challenge_id": challenge["approval_challenge_id"],
        "signature_b64": base64.b64encode(key.sign(challenge["approval_challenge"].encode(), ec.ECDSA(hashes.SHA256()))).decode()}
    return _command(app, text=text, idem=idem, proof=proof, expires=int(time.time()) + 20, no_stale=True)


def test_closed_resolver_and_success_contract():
    resolution = TypedCommandResolver().resolve(_text())
    assert resolution.mode is ResolutionMode.EXACT_ACTION
    assert resolution.canonical_action_class is ActionClass.A4
    assert resolution.no_stale_replay and resolution.max_age_seconds == 30
    assert resolution.parameters == {"domain": "google.gmail", "level": "S3"}
    contract = contract_for(resolution)
    assert contract.verifier_class == "domain-autonomy-readback"
    assert contract.postconditions["owner_granted_ceiling"] == "S3"


@pytest.mark.parametrize("domain,level", [("*", "S3"), ("global.*", "S4"), ("GLOBAL", "S3"),
    ("google/gmail", "S3"), ("google.gmail", "S5"), ("google.gmail", "s3"),
    ("google.gmail", 3), (True, "S3"), ("google.gmail", None)])
def test_malformed_unlimited_or_untyped_ceiling_cannot_resolve(domain, level):
    assert TypedCommandResolver().resolve(_text(domain, level)).mode is not ResolutionMode.EXACT_ACTION


@pytest.mark.parametrize("text", [_text(owner_approved=True), _text().replace('"level":', '"level":"S0","level":'),
    owner_control.COMMAND_PREFIX + '["google.gmail","S3"]'])
def test_extra_duplicate_or_nonobject_parameters_cannot_resolve(text):
    assert TypedCommandResolver().resolve(text).mode is not ResolutionMode.EXACT_ACTION


@pytest.mark.asyncio
async def test_owner_biometric_command_commits_verified_ceiling_and_exact_lost_response_replay(client):
    ac, app, calls = client
    key = await _pair(ac, app)
    body = await _approve(ac, app, key)
    result = (await ac.post("/v1/commands", json=body)).json()
    assert result["status"] == "accepted", result
    assert result["local_execution"]["verification_state"] == "VERIFIED_SUCCESS"
    trust = await DomainTrustService(app.state.store).get("google.gmail")
    assert trust.owner_granted_ceiling is AutonomyLevel.S3_REVERSIBLE_EXECUTION
    assert (await app.state.missions.get(result["mission_id"])).state.value == "VERIFIED_SUCCESS"
    assert calls["create_run"] == 0
    witness = await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",
        (owner_control.WITNESS_PREFIX + body["command_id"],))
    assert (await ac.post("/v1/commands", json=body)).json() == result
    assert (await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",
        (owner_control.WITNESS_PREFIX + body["command_id"],)))["value"] == witness["value"]
    assert not await app.state.store.fetchone("SELECT policy_id FROM proactive_policies")
    # Raising trust never bypasses an action's native biometric or principal gate.
    runtime = app.state.owner_runtime.actions
    execution = await runtime.begin(execution_id="ceiling-cannot-mint-a4", command_id="other-command",
        turn_id=None, action_id="google.gmail.send", principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:dev-erasure", idempotency_key="no-native-a4", parameters={}, snapshot_id=None,
        owner_approved=False)
    assert execution.status is ExecutionStatus.AUTHORIZATION_REQUIRED
    with pytest.raises(ActionPolicyError, match="principal_not_allowed"):
        await runtime.begin(execution_id="model-cannot-grant", command_id="other-command", turn_id=None,
            action_id=owner_control.ACTION_ID, principal_type=PrincipalType.HERMES_AGENT, requested_by="hermes",
            idempotency_key="model-grant", parameters={"domain": "google.gmail", "level": "S4"},
            snapshot_id=None, owner_approved=True)


@pytest.mark.asyncio
async def test_lower_owner_ceiling_limits_earned_history_and_false_success_still_suspends_grant(client):
    ac, app, _ = client
    key = await _pair(ac, app)
    trust = DomainTrustService(app.state.store)
    await trust.record("google.gmail", verified_success=20)
    for level in ("S4", "S1", "S0"):
        body = await _approve(ac, app, key, level=level, idem="level-" + level)
        assert (await ac.post("/v1/commands", json=body)).json()["status"] == "accepted"
        assert (await trust.get("google.gmail")).effective_ceiling.value == level
    body = await _approve(ac, app, key, level="S4", idem="grant-suspended")
    await trust.record("google.gmail", false_success=1)
    result = (await ac.post("/v1/commands", json=body)).json()
    assert result["status"] == "accepted", result
    actual = await trust.get("google.gmail")
    assert actual.owner_granted_ceiling.value == "S4" and actual.effective_ceiling.value == "S0"
    row = await app.state.store.fetchone("SELECT current_autonomy_ceiling FROM domain_trust WHERE domain='google.gmail'")
    assert row["current_autonomy_ceiling"] == "S0"
    verdict = await ActionAutonomyGate(trust).permits(action_id="google.gmail.send", action_class=ActionClass.A4,
        principal_type=PrincipalType.HERMES_AGENT, requested_by="hermes")
    assert verdict.allowed is False


@pytest.mark.asyncio
async def test_existing_trust_domain_is_editable_but_unknown_domain_cannot_be_created(client):
    ac, app, _ = client
    key = await _pair(ac, app)
    await DomainTrustService(app.state.store).record("custom.domain", verified_success=1)
    for domain, expected in (("custom.domain", "accepted"), ("invented.domain", "denied")):
        body = await _approve(ac, app, key, domain=domain, idem=domain)
        result = (await ac.post("/v1/commands", json=body)).json()
        assert result["status"] == expected, result
    assert not await app.state.store.fetchone("SELECT domain FROM domain_trust WHERE domain='invented.domain'")
    discovery = (await ac.get("/v1/autonomy")).json()
    assert "google.gmail" in discovery["known_domains"] and "custom.domain" in discovery["known_domains"]
    assert "invented.domain" not in discovery["known_domains"]
    assert discovery["supported_levels"] == ["S0", "S1", "S2", "S3", "S4"]
    assert discovery["typed_command_prefix"] == owner_control.COMMAND_PREFIX
    assert discovery["owner_ceiling_command"]["overrides_native_action_authority"] is False
    declaration = app.state.capability_registry.get(owner_control.ACTION_ID)
    assert declaration.authority_class is ActionClass.A4 and declaration.requires_owner_presence


@pytest.mark.asyncio
async def test_changed_parameters_or_reused_biometric_proof_cannot_set_a_new_ceiling(client):
    ac, app, _ = client
    key = await _pair(ac, app)
    body = await _approve(ac, app, key)
    changed = _command(app, text=_text(level="S4"), idem="changed-level", proof=body["approval_proof"],
        expires=int(time.time()) + 20, no_stale=True)
    assert (await ac.post("/v1/commands", json=changed)).json()["status"] == "denied"
    assert (await ac.post("/v1/commands", json=body)).json()["status"] == "accepted"
    reused = _command(app, text=body["text"], idem="new-occurrence", proof=body["approval_proof"],
        expires=int(time.time()) + 20, no_stale=True)
    assert (await ac.post("/v1/commands", json=reused)).json()["status"] == "denied"


@pytest.mark.asyncio
@pytest.mark.parametrize("race", ["revoke", "expiry"])
async def test_writer_rechecks_current_device_and_real_expiry_under_lock(client, monkeypatch, race):
    from van_gateway.command import local_executors

    ac, app, _ = client
    key = await _pair(ac, app)
    body = await _approve(ac, app, key, idem=race)
    original = local_executors.set_owner_domain_ceiling

    async def race_before_lock(store, parameters, command_id, **kwargs):
        if race == "revoke":
            await store.execute("UPDATE devices SET revoked_at_unix=? WHERE device_id=?", (int(time.time()), "dev-erasure"))
        else:
            monkeypatch.setattr(owner_control, "_now_ms", lambda: int(time.time() * 1000) + 60_000)
        await original(store, parameters, command_id, **kwargs)

    monkeypatch.setattr(local_executors, "set_owner_domain_ceiling", race_before_lock)
    result = (await ac.post("/v1/commands", json=body)).json()
    assert result["status"] == "denied", result
    assert not await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",
        (owner_control.WITNESS_PREFIX + body["command_id"],))
    assert not await app.state.store.fetchone("SELECT domain FROM domain_trust WHERE domain='google.gmail'")


@pytest.mark.asyncio
async def test_independent_observer_refuses_changed_target_unbound_receipt_and_superseded_command(client):
    ac, app, _ = client
    key = await _pair(ac, app)
    first = await _approve(ac, app, key, idem="first-grant")
    assert (await ac.post("/v1/commands", json=first)).json()["status"] == "accepted"
    contract = contract_for(TypedCommandResolver().resolve(first["text"]))
    registry = app.state.missions.verifiers
    context = {"authority_envelope": {"source_command_id": first["command_id"]}}
    outcome = await registry.verify(strategy="domain-autonomy-readback", contract=contract, context=context)
    assert outcome.status is VerificationStatus.VERIFIED
    unbound = await owner_control.domain_ceiling_readback(app.state.store, {"domain": "google.gmail", "level": "S3"}, "fabricated")
    assert unbound["owner_approved_command_bound"] is False and "evidence_refs" not in unbound
    await app.state.store.execute("UPDATE domain_trust SET owner_granted_ceiling='S4' WHERE domain='google.gmail'")
    outcome = await registry.verify(strategy="domain-autonomy-readback", contract=contract, context=context)
    assert outcome.status is VerificationStatus.FAILED
    second = await _approve(ac, app, key, level="S0", idem="newer-lower-ceiling")
    assert (await ac.post("/v1/commands", json=second)).json()["status"] == "accepted"
    # Reconstruct an abandoned delivery claim: recovery must not reapply S3.
    await app.state.store.execute("UPDATE idempotency SET status='FAILED',response_json=NULL WHERE idempotency_key=?", (first["idempotency_key"],))
    recovered = (await ac.post("/v1/commands", json=first)).json()
    assert recovered["status"] == "outcome_unknown", recovered
    assert (await DomainTrustService(app.state.store).get("google.gmail")).owner_granted_ceiling.value == "S0"


@pytest.mark.asyncio
async def test_crash_after_atomic_commit_recovers_by_readback_without_second_effect_even_after_expiry(client, monkeypatch):
    ac, app, calls = client
    key = await _pair(ac, app)
    body = await _approve(ac, app, key, idem="crash-after-grant")
    actions = app.state.owner_runtime.actions
    original = actions.mark_submitted
    writes = 0
    from van_gateway.command import local_executors
    actual_writer = local_executors.set_owner_domain_ceiling

    async def counted_writer(*args, **kwargs):
        nonlocal writes
        writes += 1
        return await actual_writer(*args, **kwargs)

    async def crash_after_commit(*args, **kwargs):
        raise RuntimeError("simulated process interruption before local receipt")

    monkeypatch.setattr(local_executors, "set_owner_domain_ceiling", counted_writer)
    monkeypatch.setattr(actions, "mark_submitted", crash_after_commit)
    with pytest.raises(RuntimeError, match="simulated process interruption"):
        await ac.post("/v1/commands", json=body)
    witness = (await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",
        (owner_control.WITNESS_PREFIX + body["command_id"],)))["value"]
    monkeypatch.setattr(actions, "mark_submitted", original)
    # Make the original delivery claim recoverable; this is not a new owner command.
    await app.state.store.execute("UPDATE idempotency SET status='FAILED',response_json=NULL WHERE idempotency_key=?", (body["idempotency_key"],))
    # Recovery deliberately observes the already committed grant, without invoking
    # the writer even when its live effect-clock would now reject this authority.
    future = int(time.time()) + 60
    monkeypatch.setattr(time, "time", lambda: future)
    assert time.time() >= body["expires_at_unix"]
    recovered = (await ac.post("/v1/commands", json=body)).json()
    assert recovered["status"] == "accepted", recovered
    assert recovered["local_execution"]["verification_state"] == "VERIFIED_SUCCESS"
    assert writes == 1 and calls["create_run"] == 0
    assert (await app.state.missions.get(recovered["mission_id"])).state.value == "VERIFIED_SUCCESS"
    assert (await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",
        (owner_control.WITNESS_PREFIX + body["command_id"],)))["value"] == witness


@pytest.mark.asyncio
async def test_expiry_at_commit_rolls_back_ceiling_and_witness(client, monkeypatch):
    ac, app, _ = client
    key = await _pair(ac, app)
    body = await _approve(ac, app, key, idem="commit-expiry")
    calls = 0
    now = int(time.time() * 1000)

    def advances_at_commit():
        nonlocal calls
        calls += 1
        return now + (60_000 if calls >= 2 else 0)

    monkeypatch.setattr(owner_control, "_now_ms", advances_at_commit)
    result = (await ac.post("/v1/commands", json=body)).json()
    assert result["status"] == "denied", result
    assert calls == 2
    assert not await app.state.store.fetchone("SELECT domain FROM domain_trust WHERE domain='google.gmail'")
    assert not await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",
        (owner_control.WITNESS_PREFIX + body["command_id"],))


@pytest.mark.asyncio
async def test_missing_owner_authority_and_readback_failure_never_report_a_grant_success(client, monkeypatch):
    from van_gateway.command import local_executors

    ac, app, _ = client
    key = await _pair(ac, app)
    with pytest.raises(owner_control.DomainCeilingDenied, match="fresh_owner_approval_required"):
        await owner_control.set_owner_domain_ceiling(app.state.store, {"domain": "google.gmail", "level": "S4"},
            "model-suggested-reference", device_id="dev-erasure")
    body = await _approve(ac, app, key, idem="readback-unavailable")

    async def unavailable(*args):
        raise OSError("simulated unavailable target observer")

    monkeypatch.setattr(local_executors, "domain_ceiling_readback", unavailable)
    result = (await ac.post("/v1/commands", json=body)).json()
    assert result["status"] == "degraded" and "may have changed" in result["message"]
    assert result["local_execution"]["verification_state"] == "EXECUTION_FAILED"
    assert (await app.state.missions.get(result["mission_id"])).state.value == "FAILED"
    assert (await DomainTrustService(app.state.store).get("google.gmail")).owner_granted_ceiling.value == "S3"
