"""Local ASGI end-to-end owner admission/approval/worker/target verification.

The n8n management/provider transports are controlled fixtures, not live canaries.
Canonical authentication, approvals, immutable manifests, grants, worker effects,
durable target reads and mission verification execute their production paths.
"""
import base64
import json
import time
import uuid

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from tests.test_a4_owner_approval import (_settings, client_and_app, _pair, _public_pem, _signed_command)
from tests.test_automation_typed_runtime import source_credentials, write_step
from automation_runtime_fixture import ENDPOINT, WORKER_TOKEN, StatefulN8n
from conftest_automation import policy_with_domains
from van_gateway.automation.api import CompileBody
from van_gateway.automation.canonical import digest
from van_gateway.automation.commands import validate_inputs, AutomationCommandDenied
from van_gateway.automation.external_runtime import ReadinessEvidence
from van_gateway.automation.models import WorkflowIR, WorkflowIRStep
from van_gateway.automation.worker_runtime import WorkerStepBody, GatewayDocumentFetcher
from van_gateway.config import get_settings
from van_gateway.models import ActionClass


@pytest.fixture(autouse=True)
def automation_runtime_settings(_settings, monkeypatch, tmp_path):
    credentials = source_credentials(tmp_path, ["GET", "POST"])
    monkeypatch.setenv("VAN_AUTOMATION_ENABLED", "1")
    monkeypatch.setenv("VAN_AUTOMATION_N8N_API_KEY", "local-fixture-management-token")
    monkeypatch.setenv("VAN_AUTOMATION_N8N_EXPECTED_VERSION", "2.39.7")
    monkeypatch.setenv("VAN_AUTOMATION_GRANT_SIGNING_KEY", "local-fixture-grant-signing-key")
    monkeypatch.setenv("VAN_AUTOMATION_WORKER_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_SCOPED_TOKENS", "automation_worker:" + WORKER_TOKEN)
    monkeypatch.setenv("VAN_AUTOMATION_SOURCE_CREDENTIALS_FILE", credentials.configuration_file)
    get_settings.cache_clear()


async def setup(ac, app):
    private = ec.generate_private_key(ec.SECP256R1())
    device_id = "owner-automation-device"
    token = await _pair(ac, device_id=device_id, secret="owner-automation-secret", public_key_pem=_public_pem(private))
    headers = {"X-Van-Device-Token": token}
    manager = StatefulN8n()
    invokes = []

    async def callback(body):
        # Traverse the actual HTTPS-addressed ASGI machine route, including its
        # dedicated scope and host check. ASGI does not perform a live TLS handshake.
        refused = await ac.post(ENDPOINT, headers={"X-Van-Internal-Token":"wrong-scope"},
                                json=body.model_dump(mode="json"))
        assert refused.status_code in {401,403}, refused.text
        response = await ac.post(ENDPOINT, headers={"X-Van-Internal-Token":WORKER_TOKEN},
                                 json=body.model_dump(mode="json"))
        assert response.status_code == 200, response.text
        return response.json()

    async def transport(request):
        if request.url.path.startswith("/webhook/"):
            invokes.append(json.loads(request.content))
            value = invokes[-1]
            await callback(WorkerStepBody(capability_grant=value["capability_grant"],
                grant=value["grant"], run_id=value["run_id"], step_id="__admit__", input=value["input"]))
            binding = await app.state.automation.runtime_bindings.get(value["grant"]["artifact_id"])
            for step in WorkflowIR.model_validate(binding["ir"]).steps:
                grant = value["step_grants"][step.step_id]
                await callback(WorkerStepBody(**grant, run_id=value["run_id"],
                    step_id=step.step_id, input=value["input"], resolve_bindings=True))
            return httpx.Response(200, json={"executionId": "local-fixture-execution", "run_id": value["run_id"], "success": True})
        return manager.handle(request)

    app.state.automation_dispatcher.client.transport = httpx.MockTransport(transport)
    await app.state.automation_health.runtime.record_evidence(ReadinessEvidence(capability="n8n",
        evidence_pointer="test-fixture://n8n-qualified", runtime_version="2.39.7"))
    async def refuse_hermes(*args, **kwargs):
        raise AssertionError("exact automation must execute locally, never free-form Hermes")
    app.state.orchestrator.hermes.create_run = refuse_hermes
    return private, device_id, headers, manager, invokes


async def proposal(app, *, external=False):
    if external:
        steps = [write_step()]
        policy = policy_with_domains("api.example.com")
        app.state.automation.policy = policy
        app.state.automation.validator.policy = policy
        app.state.automation.compiler.policy = policy
        domains, credentials = ["api.example.com"], ["connector://example"]
    else:
        steps = [WorkflowIRStep(step_id="remind", primitive="VAN_CAPABILITY", operation="reminder.create",
            input_bindings={"text":"Review the bounded result", "due_at_unix":int(time.time()) + 3600},
            action_class="A3", effects=["WRITE"], retry_class="NEVER_RETRY", max_attempts=1, timeout_ms=1000,
            postcondition={"kind":"READ_BACK","field":"verified","expected":True})]
        domains, credentials = [], []
    action_class = ActionClass.A4 if external else ActionClass.A3
    ir = WorkflowIR(ir_id="local-owner-e2e", family="owner-test", semantic_goal="Perform exact bounded owner operation",
        version=1, trigger={"kind":"INVOKE"}, steps=steps, action_class=action_class, external_domains=domains,
        credential_requirements=credentials, verifier={"kind":"READ_BACK","field":"verified","expected":True},
        policy_version="local-e2e", compiler_version="local-e2e")
    return await app.state.automation.compile_candidate(CompileBody(semantic_name="Bounded owner operation", workflow_ir=ir,
        signature={"goal_class":"OWNER_TEST","source_class":"OWNER","destination_class":"VAN","mutation_class":action_class}))


async def command(ac, app, device_id, headers, text, private=None):
    issued = int(time.time())
    initial = await ac.post("/v1/commands", headers=headers, json=_signed_command(app, device_id=device_id,
        text=text, idempotency_key="initial-" + uuid.uuid4().hex, issued_at=issued))
    assert initial.status_code == 200, initial.text
    if private is None:
        return initial.json(), None
    challenge = initial.json()
    assert challenge["status"] == "approval_required", challenge
    assert challenge["effective_action_class"] in {"A3", "A4"} and challenge["resolved_parameters"]
    proof = {"challenge_id":challenge["approval_challenge_id"], "algorithm":"ECDSA_P256_SHA256",
        "signature_b64":base64.b64encode(private.sign(challenge["approval_challenge"].encode(),ec.ECDSA(hashes.SHA256()))).decode()}
    approved_at = int(time.time())
    body = _signed_command(app, device_id=device_id, text=text, idempotency_key="approved-" + uuid.uuid4().hex,
        issued_at=approved_at, expires_at=approved_at+5, no_stale_replay=True, approval_proof=proof)
    approved = await ac.post("/v1/commands", headers=headers, json=body)
    assert approved.status_code == 200, approved.text
    return approved.json(), body


async def test_actual_owner_admits_then_executes_exact_native_plan_with_verified_mission_and_no_hermes(client_and_app):
    ac, app = client_and_app
    private, device_id, headers, manager, invokes = await setup(ac, app)
    candidate = await proposal(app)
    admitted, _ = await command(ac, app, device_id, headers, "automation admit " + candidate["artifact_id"], private)
    assert admitted["status"] == "accepted", admitted
    assert (await app.state.missions.get(admitted["mission_id"])).state.value == "VERIFIED_SUCCESS"
    exact = f"automation execute {candidate['capability_id']} artifact {candidate['artifact_id']} with {{}}"
    result, _ = await command(ac, app, device_id, headers, exact, private)
    assert result["status"] == "accepted", result
    mission = await app.state.missions.get(result["mission_id"])
    assert mission.state.value == "VERIFIED_SUCCESS" and mission.verification_state.value == "VERIFIED"
    assert len(invokes) == 1
    assert invokes[0]["input"] == {"_automation_artifact_id":candidate["artifact_id"]}
    assert (await app.state.store.fetchone("SELECT count(*) AS n FROM reminders"))["n"] == 1
    run = await ac.get("/v1/owner/automation/runs/" + invokes[0]["run_id"], headers=headers)
    assert run.json()["owner_success"] is True and run.json()["replay_permitted"] is False


async def test_actual_fresh_a1_to_a4_challenge_pins_plan_and_executes_one_protected_write_not_forged_approval(client_and_app):
    ac, app = client_and_app
    private, device_id, headers, manager, invokes = await setup(ac, app)
    candidate = await proposal(app, external=True)
    admitted, _ = await command(ac, app, device_id, headers, "automation admit " + candidate["artifact_id"], private)
    assert admitted["status"] == "accepted", admitted
    effects, state = [], {"status":"old"}
    def provider(request):
        effects.append(request.method)
        if request.method == "POST":
            assert request.headers["idempotency-key"].startswith("van-automation-")
            state["status"] = "ready"
            return httpx.Response(202,json={"accepted":True})
        return httpx.Response(200,json=state)
    async def resolver(host): return ["8.8.8.8"]
    app.state.automation_worker.fetcher = GatewayDocumentFetcher(policy_with_domains("api.example.com"),
        transport=httpx.MockTransport(provider), resolver=resolver, credentials=app.state.automation.source_credentials)
    text = f"automation execute {candidate['capability_id']} artifact {candidate['artifact_id']} with {{}}"
    forged = _signed_command(app, device_id=device_id, text=text, idempotency_key="forged-owner-approved",
        issued_at=int(time.time()),client_context={"owner_approved":True})
    refused = await ac.post("/v1/commands",headers=headers,json=forged)
    assert refused.json()["status"] == "approval_required" and effects == [] and invokes == []
    result, approved_body = await command(ac, app, device_id, headers, text, private)
    assert result["status"] == "accepted", {"runs": [dict(row) for row in await app.state.store.fetchall("SELECT status,error_code,verifier_status FROM automation_runs")], "effects": effects, "invokes": len(invokes)}
    authority = await app.state.automation_dispatcher.authority.get(result["command_id"])
    assert authority.signed_action_class is ActionClass.A1 and authority.effective_action_class is ActionClass.A4 and authority.owner_approved
    assert authority.typed_parameter_constraints == {"_automation_artifact_id":candidate["artifact_id"]}
    assert effects.count("POST") == 1 and effects.count("GET") >= 2 and len(invokes) == 1
    assert (await app.state.missions.get(result["mission_id"])).state.value == "VERIFIED_SUCCESS"
    repeated = await ac.post("/v1/commands", headers=headers, json=approved_body)
    assert repeated.json()["command_id"] == result["command_id"] and effects.count("POST") == 1


async def test_recognized_unadmitted_malformed_or_unpinned_owner_command_never_falls_back_to_hermes(client_and_app):
    ac, app = client_and_app
    private, device_id, headers, manager, invokes = await setup(ac, app)
    candidate = await proposal(app)
    for text in ("automation execute " + candidate["capability_id"],
                 f"automation execute {candidate['capability_id']} artifact {candidate['artifact_id']} with {{}}",
                 "automation execute unknown artifact unknown with {\"x\":1,\"x\":2}", "automation write any code"):
        result, _ = await command(ac, app, device_id, headers, text)
        assert result["status"] == "denied", result
    assert invokes == [] and manager.workflows == {}


@pytest.mark.parametrize("schema", [
    {"type":"string","maxLength":"5"}, {"type":"array","items":{"type":"integer"},"minItems":True},
    {"type":"number","minimum":[]}, {"type":"object","additionalProperties":{"type":"string"}},
    {"type":"object","properties":{"unused":{"type":"string","maxLength":"5"}}},
    {"type":"object","properties":{"x":{"type":"string"}},"required":[["x"]]},
    {"type":"string","minLength":4,"maxLength":2}, {"type":"integer","minimum":float("inf")},
    {"type":"object","properties":{"_automation_artifact_id":{"type":"string"}}},
    {"type":"string","pattern":".*"}, {"type":["string","string"]}, {"type":"string","items":{"type":"string"}},
])
def test_malformed_or_unsupported_schema_never_disappears_or_raises_uncontrolled_type_error(schema):
    with pytest.raises(AutomationCommandDenied, match="SCHEMA_UNSUPPORTED"):
        validate_inputs({}, schema)


def test_declared_typed_inputs_preserve_bool_number_boundary_and_bounds():
    schema = {"type":"object","properties":{"count":{"type":"integer","minimum":1,"maximum":5},
        "names":{"type":"array","items":{"type":"string","minLength":1,"maxLength":10},"maxItems":2}},"required":["count"]}
    validate_inputs({"count":3,"names":["ready"]}, schema)
    for value in ({"count":True}, {"count":6}, {"count":2,"names":["ready"]*3}, {"count":2,"extra":1}):
        with pytest.raises(AutomationCommandDenied):
            validate_inputs(value, schema)
