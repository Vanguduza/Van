"""Frontend registry must expose real routes and preserve service authority.

This validates the supplied contract against the running route definitions,
including optional routers, rather than letting a design file invent APIs.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def exporter():
    spec = importlib.util.spec_from_file_location(
        "owner_endpoint_export", ROOT / "tools/audit/export_owner_endpoints.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_saved_endpoints_match_gateway_and_conditional_contracts():
    actual = exporter().export()
    schemas = actual.pop("schemas")
    saved = json.loads((ROOT / "registries/owner_endpoints.json").read_text())
    assert saved == actual, "Regenerate using tools/audit/export_owner_endpoints.py"
    assert json.loads((ROOT / "registries/owner_endpoint_schemas.json").read_text()) == {
        "components": {"schemas": schemas}
    }
    assert all(e["source"] for e in actual["endpoints"])
    assert len({e["endpoint_id"] for e in actual["endpoints"]}) == len(actual["endpoints"])


def test_redesign_cannot_treat_internal_control_as_phone_authority():
    endpoints = {(e["method"], e["path"]): e for e in exporter().export()["endpoints"]}
    assert endpoints["GET", "/v1/automation/health"]["authentication"].startswith("INTERNAL_CONTROL:")
    assert endpoints["POST", "/v1/devices/pairing-ticket"]["authentication"].startswith("INTERNAL_CONTROL:")
    assert endpoints["GET", "/v1/capabilities/status"]["authentication"] == "INGRESS_BEARER_AND_PAIRED_DEVICE"
    assert endpoints["POST", "/v1/commands"]["device_proof_required_when_bound"]
    assert endpoints["POST", "/v1/browser/interactive-sessions"]["registration"] == "CONDITIONAL"
    assert endpoints["POST", "/v1/browser/interactive-sessions"]["authentication"] == "INGRESS_BEARER_AND_PAIRED_DEVICE"


def test_console_and_socket_authentication_do_not_invent_credential_bypasses():
    endpoints = {(e["method"], e["path"]): e for e in exporter().export()["endpoints"]}
    mint = endpoints["POST", "/v1/artemis/console/session"]
    assert mint["authentication"] == "INGRESS_BEARER_AND_PAIRED_DEVICE"
    assert mint["device_proof_required_when_bound"]
    launch = endpoints["GET", "/v1/artemis/console/launch/{launch_token}"]
    assert launch["authentication"] == "SINGLE_USE_ARTEMIS_LAUNCH_TOKEN"
    assert not launch["device_proof_required_when_bound"]
    for path in ("/v1/artemis/console", "/v1/artemis/console/", "/api/{resource_path}"):
        assert endpoints["GET", path]["authentication"] == (
            "INGRESS_BEARER_AND_PAIRED_DEVICE_OR_AUTHORIZED_ARTEMIS_BROWSER_SESSION"
        )
    socket = endpoints["WEBSOCKET", "/v1/session/ws"]
    assert socket["authentication"] == "PAIRED_DEVICE_TOKEN_AND_OWNED_SESSION"
    assert socket["device_proof_required_when_bound"]


def test_owner_file_contract_and_optional_effect_plans_have_resolved_actual_request_schemas():
    actual = exporter().export()
    endpoints = {(e["method"], e["path"]): e for e in actual["endpoints"]}
    provider = endpoints["GET", "/v1/browser/interactive-sessions/{session_id}/file-provider-contracts"]
    assert not any(p["name"] == "request" and p["in"] == "query" for p in provider["parameters"])
    plan = endpoints["POST", "/v1/browser/interactive-sessions/{session_id}/action-plans"]
    assert plan["registration"] == "CONDITIONAL" and plan["device_proof_required_when_bound"]
    body = plan["request_body"]["content"]["application/json"]["schema"]
    assert body["$ref"].endswith("CreatePlan") and "CreatePlan" in actual["schemas"]
    for suffix in ("", "/{plan_id}"):
        assert ("GET", "/v1/browser/interactive-sessions/{session_id}/action-plans"+suffix) in endpoints


def test_provider_admission_uses_separate_attested_transport_and_actual_typed_drafts():
    actual = exporter().export()
    endpoints = {(e["method"], e["path"]): e for e in actual["endpoints"]}
    for operation in ("introspect", "claim"):
        callback = endpoints["POST", "/v1/browser/artifact-provider/admissions/{admission_id}/"+operation]
        assert callback["authentication"] == (
            "ATTESTED_ARTIFACT_PROVIDER:CURRENT_PINNED_MTLS_AND_SIGNED_EXACT_ADMISSION"
        )
        assert not callback["device_proof_required_when_bound"]
        body = callback["request_body"]["content"]["application/json"]["schema"]
        assert body["$ref"].endswith("AdmissionBody")
    draft = endpoints["POST", "/v1/browser/interactive-sessions/{session_id}/file-provider-requests"]
    assert draft["authentication"] == "INGRESS_BEARER_AND_PAIRED_DEVICE"
    assert draft["device_proof_required_when_bound"]
    assert draft["request_body"]["content"]["application/json"]["schema"]["$ref"].endswith("CreateProviderRequest")
    assert not any("file-provider-requests" in e["path"] and e["path"].endswith("/submit") for e in endpoints.values())
    assert actual["schemas"]["CreateProviderRequest"]["additionalProperties"] is False
    assert actual["schemas"]["AdmissionBody"]["additionalProperties"] is False
