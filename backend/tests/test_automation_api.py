"""Rev 1.3 §§219-222, 227 — the Automation Fabric control surface.

Four properties are worth a test each, because each one is a rule that would be
invisible if it silently stopped holding:

* the whole surface is internal-control only — owner ingress never reaches it;
* `/compile` produces a PROPOSED candidate and nothing else: no deployment, no
  admission, no HOT entry (§51);
* the HOT index only ever contains admitted artifacts (§25);
* a standing intent that cannot seal authority does not survive as an enabled
  row (§227), and A4 can never become standing authority (§391).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.conftest_automation import (
    enroll_device,
    make_store,
    policy_with_domains,
    seal_owner_command,
    seed_snapshot,
)
from van_gateway.automation.api import AutomationApi
from van_gateway.automation.models import IntentSignature, WorkflowLifecycle
from van_gateway.automation.registry import AutomationRegistry, HotWorkflowIndex
from van_gateway.command.authority import CommandAuthorityService
from van_gateway.command.standing import StandingAutomationAuthorityService
from van_gateway.config import get_settings
from van_gateway.models import ActionClass

INGRESS = "test-ingress-token-0123456789abcdef"
INTERNAL = "test-internal-token"
HEADERS = {"X-Van-Internal-Token": INTERNAL}
DOMAIN = "reports.example.com"

SIGNATURE = {
    "goal_class": "DOCUMENT_COLLECTION",
    "source_class": "BROKER_PORTAL",
    "destination_class": "VAN_EVIDENCE",
    "mutation_class": "A3",
}

BINDINGS = {
    "source_label": "Primary broker",
    "document_type": "statement",
    "source_domain": DOMAIN,
    "source_path": "/statements",
    "credential_alias": "connector://broker/primary",
}


@pytest.fixture(autouse=True)
def _settings(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    # P0-SEC-001 — device enrolment is its own credential now.
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_AUTOMATION_ENABLED", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def fabric(tmp_path):
    """The API mounted bare, so policy can be injected without touching the file.

    The shipped policy admits no external domain (correct default-deny), and a
    test that loosened the repository policy would stop testing the real thing.
    """
    store = await make_store(tmp_path)
    await enroll_device(store)
    authority = CommandAuthorityService(store)
    api = AutomationApi(
        store,
        get_settings(),
        registry=AutomationRegistry(store),
        hot_index=HotWorkflowIndex(),
        standing=StandingAutomationAuthorityService(store, authority),
        policy=policy_with_domains(DOMAIN),
    )
    app = FastAPI()
    app.include_router(api.router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, api, store, authority


# --------------------------------------------------------------- ingress gate


async def test_every_automation_route_is_internal_control_only():
    """§219 — owner ingress must not reach the fabric control surface."""
    from van_gateway.app import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        headers={"X-Van-Ingress-Token": INGRESS},
    ) as ac:
        async with app.router.lifespan_context(app):
            # A valid owner ingress token is not enough for any of these.
            for method, path in (
                ("POST", "/v1/automation/route"),
                ("POST", "/v1/automation/compile"),
                ("POST", "/v1/automation/admit"),
                ("POST", "/v1/automation/execute"),
                ("POST", "/v1/automation/generate"),
                ("POST", "/v1/automation/hot/publish"),
                ("POST", "/v1/automation/standing-intents"),
                ("GET", "/v1/automation/templates"),
            ):
                response = await ac.request(method, path, json={})
                assert response.status_code in (401, 403), (path, response.status_code)


async def test_routes_are_reachable_with_the_internal_token():
    from van_gateway.app import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        headers={"X-Van-Ingress-Token": INGRESS},
    ) as ac:
        async with app.router.lifespan_context(app):
            body = (await ac.get("/v1/automation/templates", headers=HEADERS)).json()
    ids = {t["template_id"] for t in body["templates"]}
    assert "collect_normalise_ingest.v1" in ids
    assert all(t["holes"] for t in body["templates"])


# -------------------------------------------------------------------- routing


async def test_route_refuses_a_payment_goal_before_anything_else(fabric):
    """§34 — the payment boundary is checked before medium selection."""
    ac, _api, _store, _auth = fabric
    response = await ac.post(
        "/v1/automation/route",
        headers=HEADERS,
        json={"goal": "log in and pay the electricity invoice", "signature": SIGNATURE},
    )
    assert response.status_code == 200
    assert response.json()["medium"] == "REFUSED"
    assert response.json()["reason"] == "PAYMENT_PROHIBITED"


async def test_route_prefers_a_native_capability_and_compiles_behind_it(fabric):
    """§32 — the owner is served now; the reusable workflow compiles behind."""
    ac, _api, _store, _auth = fabric
    body = (
        await ac.post(
            "/v1/automation/route",
            headers=HEADERS,
            json={
                "goal": "collect this week's statements",
                "signature": SIGNATURE,
                "native_capability_id": "native.statements",
                "wants_reuse": True,
            },
        )
    ).json()
    assert body["medium"] == "NATIVE"
    assert body["immediate_native_capability_id"] == "native.statements"
    assert body["compile_in_background"] is True


async def test_route_falls_to_warm_when_a_template_covers_the_goal_class(fabric):
    ac, _api, _store, _auth = fabric
    body = (
        await ac.post(
            "/v1/automation/route",
            headers=HEADERS,
            json={"goal": "collect statements", "signature": SIGNATURE},
        )
    ).json()
    assert body["medium"] == "N8N_WARM"
    assert body["template_id"] == "collect_normalise_ingest.v1"


async def test_route_falls_to_cold_for_a_novel_goal_class(fabric):
    ac, _api, _store, _auth = fabric
    signature = dict(SIGNATURE, goal_class="SOMETHING_NOBODY_HAS_ASKED_FOR")
    body = (
        await ac.post(
            "/v1/automation/route",
            headers=HEADERS,
            json={"goal": "do a brand new thing", "signature": signature},
        )
    ).json()
    assert body["medium"] == "WORKFLOW_COMPILER"
    assert body["reason"] == "NOVEL_GOAL"


# ------------------------------------------------------------------- compile


async def test_compile_produces_a_proposed_candidate_and_nothing_more(fabric):
    """§51 — compilation is not admission, and nothing is deployed."""
    ac, api, _store, _auth = fabric
    response = await ac.post(
        "/v1/automation/compile",
        headers=HEADERS,
        json={
            "semantic_name": "DOCUMENT_COLLECTION.BROKER_PORTAL.VAN_EVIDENCE",
            "signature": SIGNATURE,
            "template_id": "collect_normalise_ingest.v1",
            "bindings": BINDINGS,
            "credential_ids": {"connector://broker/primary": "n8n-cred-1"},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lifecycle_state"] == WorkflowLifecycle.PROPOSED.value
    assert body["semantic_digest"].startswith("sha256:")
    assert body["validation_report_digest"]

    artifact = await api.registry.get_artifact(body["artifact_id"])
    assert artifact is not None
    assert artifact.lifecycle_state is WorkflowLifecycle.PROPOSED
    # Nothing has been deployed, so there is no engine-side workflow yet.
    assert artifact.n8n_workflow_id is None
    assert api.hot_index.size == 0


async def test_compile_refuses_a_binding_that_leaves_an_admitted_domain(fabric):
    """§147 — default-deny on domains survives a caller choosing its own."""
    ac, _api, _store, _auth = fabric
    response = await ac.post(
        "/v1/automation/compile",
        headers=HEADERS,
        json={
            "semantic_name": "DOCUMENT_COLLECTION.BROKER_PORTAL.VAN_EVIDENCE",
            "signature": SIGNATURE,
            "template_id": "collect_normalise_ingest.v1",
            "bindings": dict(BINDINGS, source_domain="not-admitted.example.net"),
        },
    )
    assert response.status_code == 422
    assert "DOMAIN" in response.text.upper()


async def test_compile_requires_a_template(fabric):
    ac, _api, _store, _auth = fabric
    response = await ac.post(
        "/v1/automation/compile",
        headers=HEADERS,
        json={"semantic_name": "x", "signature": SIGNATURE},
    )
    assert response.status_code == 422
    assert "template" in response.text


async def test_compile_is_refused_while_the_fabric_is_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_AUTOMATION_ENABLED", "0")
    get_settings.cache_clear()
    store = await make_store(tmp_path)
    api = AutomationApi(
        store,
        get_settings(),
        registry=AutomationRegistry(store),
        hot_index=HotWorkflowIndex(),
        standing=StandingAutomationAuthorityService(store, CommandAuthorityService(store)),
        policy=policy_with_domains(DOMAIN),
    )
    app = FastAPI()
    app.include_router(api.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/v1/automation/compile",
            headers=HEADERS,
            json={
                "semantic_name": "x", "signature": SIGNATURE,
                "template_id": "collect_normalise_ingest.v1", "bindings": BINDINGS,
            },
        )
        # Routing stays available while the fabric is off — it decides nothing
        # that touches n8n.
        assert response.status_code == 503
        assert response.json()["detail"] == "AUTOMATION_FABRIC_DISABLED"
        routed = await ac.post(
            "/v1/automation/route",
            headers=HEADERS,
            json={"goal": "collect statements", "signature": SIGNATURE},
        )
        assert routed.status_code == 200


# -------------------------------------------------------- admission and HOT


async def _compile(ac) -> dict:
    response = await ac.post(
        "/v1/automation/compile",
        headers=HEADERS,
        json={
            "semantic_name": "DOCUMENT_COLLECTION.BROKER_PORTAL.VAN_EVIDENCE",
            "signature": SIGNATURE,
            "template_id": "collect_normalise_ingest.v1",
            "bindings": BINDINGS,
            "credential_ids": {"connector://broker/primary": "n8n-cred-1"},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_admission_is_a_guarded_transition(fabric):
    """§154 — a stale `expected` state is a conflict, not a silent overwrite."""
    ac, _api, _store, _auth = fabric
    compiled = await _compile(ac)

    # PROPOSED -> ADMITTED is not a transition the state machine has, so an
    # artifact can never skip quarantine and validation.
    skipped = await ac.post(
        "/v1/automation/admit",
        headers=HEADERS,
        json={
            "artifact_id": compiled["artifact_id"],
            "expected": "PROPOSED",
            "target": "ADMITTED",
        },
    )
    assert skipped.status_code == 409
    assert "illegal_transition" in skipped.json()["detail"]

    # §§152-155 — a compiled workflow is quarantined before it can be validated;
    # there is no path from PROPOSED straight to VALIDATED.
    quarantined = await ac.post(
        "/v1/automation/admit",
        headers=HEADERS,
        json={
            "artifact_id": compiled["artifact_id"],
            "expected": "PROPOSED",
            "target": "QUARANTINED",
        },
    )
    assert quarantined.status_code == 200
    assert quarantined.json()["lifecycle_state"] == "QUARANTINED"

    # A correct target with a now-stale expected state is still refused.
    replayed = await ac.post(
        "/v1/automation/admit",
        headers=HEADERS,
        json={
            "artifact_id": compiled["artifact_id"],
            "expected": "PROPOSED",
            "target": "QUARANTINED",
        },
    )
    assert replayed.status_code == 409


async def test_hot_publish_requires_an_admitted_artifact(fabric):
    """§25 — the HOT index is reachable only through admission."""
    ac, api, _store, _auth = fabric
    compiled = await _compile(ac)

    refused = await ac.post(
        "/v1/automation/hot/publish",
        headers=HEADERS,
        json={"capability_id": compiled["capability_id"], "signature": SIGNATURE},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"] == "CAPABILITY_NOT_ADMITTED"
    assert api.hot_index.size == 0

    for expected, target in (
        ("PROPOSED", "QUARANTINED"), ("QUARANTINED", "VALIDATED"), ("VALIDATED", "ADMITTED")
    ):
        step = await ac.post(
            "/v1/automation/admit",
            headers=HEADERS,
            json={
                "artifact_id": compiled["artifact_id"], "expected": expected,
                "target": target, "n8n_workflow_id": "n8n-wf-1",
            },
        )
        assert step.status_code == 200, step.text

    published = await ac.post(
        "/v1/automation/hot/publish",
        headers=HEADERS,
        json={"capability_id": compiled["capability_id"], "signature": SIGNATURE},
    )
    assert published.status_code == 200
    assert published.json()["hot_index_size"] == 1

    # And now the router takes the HOT path rather than compiling again.
    routed = (
        await ac.post(
            "/v1/automation/route",
            headers=HEADERS,
            json={"goal": "collect statements", "signature": SIGNATURE},
        )
    ).json()
    assert routed["medium"] == "N8N_HOT"
    assert routed["capability_id"] == compiled["capability_id"]

    withdrawn = await ac.post(
        f"/v1/automation/hot/withdraw/{compiled['capability_id']}", headers=HEADERS
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json()["hot_index_size"] == 0


async def test_capability_lookup_reports_the_admitted_artifact(fabric):
    ac, _api, _store, _auth = fabric
    compiled = await _compile(ac)
    body = (
        await ac.get(f"/v1/automation/capabilities/{compiled['capability_id']}", headers=HEADERS)
    ).json()
    assert body["capability"]["lifecycle_state"] == "PROPOSED"
    assert body["admitted_artifact"] is None
    missing = await ac.get("/v1/automation/capabilities/nope", headers=HEADERS)
    assert missing.status_code == 404


# ------------------------------------------------------------------ generate


async def test_generate_specialises_a_template_without_a_model(fabric):
    """§29 — COLD starts from a skeleton whenever one fits, so no model is used."""
    ac, _api, _store, _auth = fabric
    body = (
        await ac.post(
            "/v1/automation/generate",
            headers=HEADERS,
            json={
                "goal": "collect broker statements",
                "signature": SIGNATURE,
                "credential_aliases": ["connector://broker/primary"],
            },
        )
    ).json()
    # collect_normalise_ingest needs a source_path, which is never guessable, so
    # the deterministic proposer honestly declines rather than inventing one.
    assert body["outcome"] == "NO_PROPOSAL"
    contract = body["prompt_contract"]
    assert DOMAIN in contract["admitted_domains"]
    assert contract["credential_aliases"] == ["connector://broker/primary"]
    # §173 — a proposer is told shapes and names, never values.
    assert "credential_values" not in contract
    assert any("no payment" in rule for rule in contract["hard_rules"])


async def test_generate_refuses_a_payment_goal(fabric):
    ac, _api, _store, _auth = fabric
    body = (
        await ac.post(
            "/v1/automation/generate",
            headers=HEADERS,
            json={"goal": "pay the invoice from the broker portal", "signature": SIGNATURE},
        )
    ).json()
    assert body["outcome"] == "REJECTED_BY_PAYMENT_BOUNDARY"
    assert body["ok"] is False


# ----------------------------------------------------------- standing intents


def _standing_body(**overrides) -> dict:
    body = {
        "intent_id": "intent-statements",
        "owner_goal": "collect broker statements every Friday",
        "source_command_id": "cmd-owner-1",
        "capability_id": "wfcap_statements",
        "artifact_id": "artifact-1",
        "workflow_version": 1,
        "action_class_ceiling": "A3",
        "trigger": {"kind": "SCHEDULE", "cron": "0 6 * * 5"},
        "parameter_constraints": {"broker_alias": "primary"},
        "allowed_effects": ["READ", "NETWORK_READ", "WRITE"],
        "allowed_domains": [DOMAIN],
        "owner_authority_evidence_ref": "evidence://owner/approval/1",
    }
    body.update(overrides)
    return body


async def test_standing_intent_seals_authority_from_the_owner_command(fabric):
    """§§388-392 — standing authority is derived, never independently minted."""
    ac, _api, store, authority = fabric
    await seed_snapshot(store, "ctx-owner-1", "cmd-owner-1")
    await seal_owner_command(authority, effective=ActionClass.A3)

    response = await ac.post(
        "/v1/automation/standing-intents", headers=HEADERS, json=_standing_body()
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["action_class_ceiling"] == "A3"
    assert body["source_device_is_revocation_root"] is True

    row = await store.fetchone(
        "SELECT enabled FROM automation_standing_intents WHERE intent_id = ?",
        ("intent-statements",),
    )
    assert int(row["enabled"]) == 1


async def test_a4_can_never_become_standing_authority(fabric):
    """§391 — and the intent row must not survive as enabled after the refusal."""
    ac, _api, store, authority = fabric
    await seed_snapshot(store, "ctx-owner-1", "cmd-owner-1")
    await seal_owner_command(authority, effective=ActionClass.A4, owner_approved=True)

    response = await ac.post(
        "/v1/automation/standing-intents",
        headers=HEADERS,
        json=_standing_body(action_class_ceiling="A4"),
    )
    assert response.status_code == 409
    row = await store.fetchone(
        "SELECT enabled FROM automation_standing_intents WHERE intent_id = ?",
        ("intent-statements",),
    )
    assert int(row["enabled"]) == 0


async def test_disabling_a_standing_intent_revokes_its_authorities(fabric):
    ac, _api, store, authority = fabric
    await seed_snapshot(store, "ctx-owner-1", "cmd-owner-1")
    await seal_owner_command(authority, effective=ActionClass.A3)
    await ac.post("/v1/automation/standing-intents", headers=HEADERS, json=_standing_body())

    disabled = await ac.post(
        "/v1/automation/standing-intents/intent-statements/disable", headers=HEADERS
    )
    assert disabled.status_code == 200
    assert disabled.json()["revoked_authorities"] == 1

    row = await store.fetchone(
        "SELECT enabled FROM automation_standing_intents WHERE intent_id = ?",
        ("intent-statements",),
    )
    assert int(row["enabled"]) == 0
    remaining = await store.fetchall(
        "SELECT authority_id FROM standing_automation_authorities "
        "WHERE standing_intent_id = ? AND revoked_at_ms IS NULL",
        ("intent-statements",),
    )
    assert remaining == []


async def test_standing_intent_without_an_owner_command_is_refused(fabric):
    """No owner command, no standing authority — and no enabled intent row."""
    ac, _api, store, _auth = fabric
    response = await ac.post(
        "/v1/automation/standing-intents", headers=HEADERS, json=_standing_body()
    )
    assert response.status_code == 409
    row = await store.fetchone(
        "SELECT enabled FROM automation_standing_intents WHERE intent_id = ?",
        ("intent-statements",),
    )
    assert int(row["enabled"]) == 0


# --------------------------------------------------------------------- execute


ACTION_ID = "automation.trading.statement.collect"
SIGNING_KEY = "api-test-signing-key"


def _n8n_transport(engine_success: bool = True):
    import json

    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/settings"):
            return httpx.Response(200, json={"versionCli": "2.39.7"})
        if request.url.path.endswith("/run"):
            body = json.loads(request.content)
            # §§159-160 — the engine gets a run-scoped grant, never VAN's own token.
            assert body["capability_grant"]
            assert "X-Van-Internal-Token" not in request.headers
            return httpx.Response(
                200, json={"executionId": "n8n-exec-1", "success": engine_success}
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


class _Observer:
    def __init__(self, result: dict) -> None:
        self.result = result

    async def observe(self, spec, context):
        return self.result


@pytest_asyncio.fixture
async def executable(tmp_path):
    """The API with a dispatcher behind it, wired exactly as `create_app` does."""
    from tests.conftest_automation import (
        make_action_runtime,
        sample_artifact,
        sample_capability,
    )
    from van_gateway.action.models import ActionDefinition, VerifierType
    from van_gateway.automation.dispatch import AutomationDispatcher
    from van_gateway.automation.external_runtime import (
        ExternalRuntimeRegistry,
        ReadinessEvidence,
    )
    from van_gateway.automation.grants import RunGrantService
    from van_gateway.automation.n8n_client import N8nManagementClient
    from van_gateway.automation.verifier import WorkflowVerifier
    from van_gateway.models import PrincipalType

    store = await make_store(tmp_path)
    await enroll_device(store)
    authority = CommandAuthorityService(store)
    await seed_snapshot(store, "ctx-owner-1", "cmd-owner-1")
    await seal_owner_command(authority, effective=ActionClass.A3)

    actions = await make_action_runtime(store)
    await actions.register(
        ActionDefinition(
            action_id=ACTION_ID,
            action_class=ActionClass.A2,
            mutates_state=False,
            allowed_principals={
                PrincipalType.OWNER_DEVICE,
                PrincipalType.HERMES_AGENT,
                PrincipalType.AUTOMATION,
            },
            verifier_type=VerifierType.READ_BACK,
        )
    )

    registry = AutomationRegistry(store)
    await registry.upsert_capability(sample_capability(action_class=ActionClass.A2))
    await registry.record_artifact(sample_artifact(lifecycle=WorkflowLifecycle.ADMITTED))

    runtime_registry = ExternalRuntimeRegistry(store)
    await runtime_registry.record_evidence(
        ReadinessEvidence(
            capability="n8n", evidence_pointer="gateway://automation/cert/1",
            runtime_version="2.39.7",
        )
    )
    dispatcher = AutomationDispatcher(
        store,
        actions=actions,
        authority=authority,
        registry=registry,
        grants=RunGrantService(store, signing_key=SIGNING_KEY),
        client=N8nManagementClient(
            runtime_registry, base_url="http://127.0.0.1:5678/api/v1", api_key="k",
            enabled=True, expected_version="2.39.7", transport=_n8n_transport(),
        ),
        verifier=WorkflowVerifier(
            {"READ_BACK": _Observer({"exists": True, "evidence_pointer": "gateway://evidence/1"})}
        ),
        enabled=True,
    )
    api = AutomationApi(
        store,
        get_settings(),
        registry=registry,
        hot_index=HotWorkflowIndex(),
        standing=StandingAutomationAuthorityService(store, authority),
        policy=policy_with_domains(DOMAIN),
        dispatcher=dispatcher,
    )
    app = FastAPI()
    app.include_router(api.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, api, store


def _execute_body(**overrides) -> dict:
    body = {
        "capability_id": "wfcap_statements",
        "action_id": ACTION_ID,
        "command_id": "cmd-owner-1",
        "snapshot_id": "ctx-owner-1",
        "requested_by": "dev-owner-1",
        "principal_type": "OWNER_DEVICE",
        "inputs": {"broker_alias": "primary"},
        "turn_id": "turn-1",
    }
    body.update(overrides)
    return body


async def test_execute_reports_owner_success_only_when_verified(executable):
    """§17 — an engine success is not an owner success, and the two are distinct."""
    ac, _api, _store = executable
    response = await ac.post("/v1/automation/execute", headers=HEADERS, json=_execute_body())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "VERIFIED_SUCCESS"
    assert body["owner_success"] is True
    assert body["verification_outcome"] == "VERIFIED"
    assert body["evidence_pointer"]


async def test_execute_refuses_a_capability_that_was_never_admitted(executable):
    """§36 — nothing executes before admission, on any path."""
    from tests.conftest_automation import sample_capability

    ac, api, _store = executable
    await api.registry.upsert_capability(
        sample_capability(capability_id="wfcap_proposed", action_class=ActionClass.A2)
    )
    response = await ac.post(
        "/v1/automation/execute", headers=HEADERS,
        json=_execute_body(capability_id="wfcap_proposed"),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "CAPABILITY_NOT_ADMITTED"


async def test_execute_refuses_a_capability_that_does_not_exist(executable):
    ac, _api, _store = executable
    response = await ac.post(
        "/v1/automation/execute", headers=HEADERS,
        json=_execute_body(capability_id="wfcap_never_heard_of"),
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "CAPABILITY_UNKNOWN"


async def test_execute_refuses_an_unknown_action(executable):
    ac, _api, _store = executable
    response = await ac.post(
        "/v1/automation/execute", headers=HEADERS, json=_execute_body(action_id="nope")
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "UNKNOWN_ACTION"


async def test_execute_refuses_without_a_sealed_command_authority(executable):
    """The endpoint carries no approval of its own, so an unsealed command fails."""
    ac, _api, _store = executable
    response = await ac.post(
        "/v1/automation/execute", headers=HEADERS,
        json=_execute_body(command_id="cmd-never-sealed"),
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "AUTHORITY_DENIED"


async def test_execute_is_unavailable_without_a_dispatcher(fabric):
    """An unconfigured dispatcher is a 503, never a silent local execution."""
    ac, _api, _store, _auth = fabric
    response = await ac.post("/v1/automation/execute", headers=HEADERS, json=_execute_body())
    assert response.status_code == 503
    assert response.json()["detail"] == "AUTOMATION_DISPATCH_UNCONFIGURED"


async def test_execute_refuses_a_principal_the_command_was_not_sealed_for(executable):
    """The stated principal is compared against the sealed record, not trusted."""
    ac, _api, _store = executable
    response = await ac.post(
        "/v1/automation/execute", headers=HEADERS,
        json=_execute_body(principal_type="HERMES_AGENT"),
    )
    assert response.status_code == 403
    assert response.json()["detail"]["detail"] == "principal_mismatch"


def test_a_caller_cannot_state_its_own_postcondition():
    """§165 — verification strength is a property of the capability, not the run.

    Asserted on the request model rather than on a response, because the point
    is that there is no field through which a run could ask for a weaker check.
    """
    from van_gateway.automation.api import ExecuteBody

    fields = set(ExecuteBody.model_fields)
    assert not fields & {"postcondition", "verifier_type", "owner_approved", "action_class"}
