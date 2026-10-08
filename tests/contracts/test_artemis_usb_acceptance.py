"""USB acceptance uses actual governed receipt exports; unit fixtures are never live evidence."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path

import pytest

from tools.certification import artemis_acceptance as acceptance
from tests.contracts.test_artemis_acceptance_plan import export_receipt, subset


@pytest.fixture(scope="module")
def usb_plan():
    return acceptance.build_plan(device_transport=acceptance.USB_PRIVATE_BRIDGE)


def usb_bindings(plan):
    return {"repository_sha": "a" * 40, "apk_sha256": "b" * 64,
            "deployment_receipt_id": "unit-deployment", "fixture_receipt_id": "unit-fixture",
            "device_transport": "USB_PRIVATE_BRIDGE", "device_admission_receipt_id": "unit-usb-admission-not-live",
            "device_serial": "unit-usb-s24", "device_identity_receipt_id": "unit-identity",
            "device_model": "SM-S928B", "inputs_sha256": plan["inputs_sha256"],
            "isolated_acceptance_realm": True, "no_production_service_disruption": True}


def put_transport_proof(plan, bound, root, *, mutate=None):
    original = root / "unit-original-admission-export.bin"
    original.write_bytes(b"Synthetic original broker export fixture; no live device admission or authenticated producer.")
    proof = {
        "transport": "USB_PRIVATE_BRIDGE", "authority": "HERMES_CONTROL_AUTHORITY",
        "producer": "hermes_device_admission", "receipt_id": bound["device_admission_receipt_id"],
        "device_serial": bound["device_serial"], "device_model": bound["device_model"],
        "device_identity_receipt_id": bound["device_identity_receipt_id"], "host": "dial-control",
        "usb_device_state": "device", "usb_authorization_verified": True,
        "private_bridge_verified": True, "loopback_only_verified": True,
        "endpoint_consistency_verified": True, "independent_observation": True,
        "source_receipt_ref": "unit-original-export-not-live", "bridge_profile_id": "unit-isolated-bridge",
        "source_artifact": {"path": original.name, "sha256": hashlib.sha256(original.read_bytes()).hexdigest()},
        "adb_endpoint": {"host": "127.0.0.1", "port": 15037,
                         "server_socket": "tcp:127.0.0.1:15037", "endpoint_id": "tcp:127.0.0.1:15037"},
        "plan_sha256": plan["plan_sha256"], "reviewed_case_ids": [case["id"] for case in plan["cases"]],
    }
    if mutate:
        mutate(proof)
    path = root / "unit-usb-transport.json"
    path.write_text(json.dumps(proof))
    bound["device_transport_evidence"] = {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return path


def admitted_status(bound):
    return {"plane": "HERMES_ANDROID_TESTING_PLANE", "authority": "HERMES_CONTROL_AUTHORITY",
            "subordinate": "ARTEMIS", "raw_upstream_mcp_exposed": False,
            "admitted_devices": [bound["device_serial"]], "connected_admitted_devices": [bound["device_serial"]],
            "security": {"device_admission_required": True, "hermes_is_only_exposed_control_surface": True,
                         "adb_expected_binding": "loopback_or_governed_device_bridge"}}


def run(plan, bound, root, observed=None):
    calls = []
    async def tool(name, args):
        calls.append((name, args))
        if name == "android_testing_status":
            return observed if observed is not None else admitted_status(bound)
        assert name == "android_test_run"
        return {"run_id": "unit-usb-run-not-live", "success": True, "device_serial": bound["device_serial"],
                "repository_sha": bound["repository_sha"], "objective_sha256": hashlib.sha256(args["objective"].encode()).hexdigest()}
    result = asyncio.run(acceptance.run_case(tool, plan, plan["cases"][0]["id"], bound, evidence_root=root))
    return result, calls


def test_usb_candidate_plan_is_separate_and_does_not_promote_wireless_coverage(usb_plan):
    wireless = acceptance.build_plan()
    assert wireless["target"]["phone_connection"] == "wireless_adb_via_governed_artemis"
    assert usb_plan["target"]["device_transport"] == "USB_PRIVATE_BRIDGE"
    assert usb_plan["status"] == "USB_CANDIDATE_PLAN_PREPARED_NOT_EXECUTED"
    assert usb_plan["transport_adaptation"]["verified_applicable_cases"] == 0
    assert usb_plan["plan_sha256"] != wireless["plan_sha256"]
    assert "wireless endpoint" not in next(case for case in usb_plan["cases"] if case["id"] == "CC-PHONE-REBOOT")["expected"]
    assert all("private USB bridge" in case["fixture"]["state_setup"] for case in usb_plan["cases"] if case["state"] == "offline")
    # VAN enrollment ticket pairing remains an application case, not an ADB pairing assertion.
    assert any(case["id"] == "CC-PAIR-REPLY-LOST" for case in usb_plan["cases"])


def test_export_binding_and_current_admission_allow_exact_task_but_never_qualify(usb_plan, tmp_path):
    plan = subset(usb_plan)
    bound = usb_bindings(plan)
    put_transport_proof(plan, bound, tmp_path)
    result, calls = run(plan, bound, tmp_path)
    assert [name for name, _ in calls] == ["android_testing_status", "android_test_run"]
    assert set(calls[1][1]) <= acceptance.CALL_KEYS
    assert result["outcome"] == "EXECUTED_REQUIRES_RECONCILIATION"
    assert result["device_transport"] == "USB_PRIVATE_BRIDGE"
    assert result["device_admission_receipt_id"] == bound["device_admission_receipt_id"]
    assert result["live_qualified"] is False


@pytest.mark.parametrize("change", ["missing_receipt", "wireless_alias", "missing_artifact", "missing_root", "wrong_plan_transport", "tampered_artifact"])
def test_usb_wiring_or_fake_wireless_substitution_blocks_before_phone_calls(usb_plan, tmp_path, change):
    plan = subset(usb_plan)
    bound = usb_bindings(plan)
    path = put_transport_proof(plan, bound, tmp_path)
    root = tmp_path
    if change == "missing_receipt":
        bound.pop("device_admission_receipt_id")
    elif change == "wireless_alias":
        bound["wireless_admission_receipt_id"] = bound["device_admission_receipt_id"]
    elif change == "missing_artifact":
        path.unlink()
    elif change == "missing_root":
        root = None
    elif change == "wrong_plan_transport":
        plan = subset(acceptance.build_plan())
        bound["inputs_sha256"] = plan["inputs_sha256"]
    else:
        path.write_text("tampered")
    result, calls = run(plan, bound, root)
    assert result["outcome"] == "BLOCKED"
    assert calls == []


@pytest.mark.parametrize("field,value", [
    ("usb_device_state", "unauthorized"), ("usb_device_state", "offline"),
    ("usb_authorization_verified", False), ("loopback_only_verified", False),
    ("private_bridge_verified", False), ("endpoint_consistency_verified", False),
    ("independent_observation", 1), ("source_receipt_ref", ""),
    ("device_serial", "another-unit-phone"), ("device_model", "SM-G998B"),
    ("receipt_id", "another-unit-receipt"), ("plan_sha256", "c" * 64),
    ("reviewed_case_ids", []), ("reviewed_case_ids", ["invented-case"]),
])
def test_usb_original_receipt_mismatch_or_unauthorized_phone_blocks_before_status(usb_plan, tmp_path, field, value):
    plan = subset(usb_plan)
    bound = usb_bindings(plan)
    put_transport_proof(plan, bound, tmp_path, mutate=lambda proof: proof.update({field: value}))
    result, calls = run(plan, bound, tmp_path)
    assert result["outcome"] == "BLOCKED"
    assert calls == []


@pytest.mark.parametrize("endpoint", [
    {"host": "0.0.0.0", "port": 15037, "server_socket": "tcp:0.0.0.0:15037", "endpoint_id": "tcp:0.0.0.0:15037"},
    {"host": "127.0.0.1", "port": 5037, "server_socket": "tcp:127.0.0.1:5037", "endpoint_id": "tcp:127.0.0.1:5037"},
    {"host": "127.0.0.1", "port": 5555, "server_socket": "tcp:127.0.0.1:5555", "endpoint_id": "tcp:127.0.0.1:5555"},
    {"host": "127.0.0.1", "port": 15037, "server_socket": "tcp:127.0.0.1:15038", "endpoint_id": "tcp:127.0.0.1:15037"},
])
def test_public_shared_or_inconsistent_adb_endpoint_is_refused(usb_plan, tmp_path, endpoint):
    plan = subset(usb_plan)
    bound = usb_bindings(plan)
    put_transport_proof(plan, bound, tmp_path, mutate=lambda proof: proof.update(adb_endpoint=endpoint))
    result, calls = run(plan, bound, tmp_path)
    assert result["outcome"] == "BLOCKED"
    assert calls == []


@pytest.mark.parametrize("change", ["not_admitted", "not_connected", "missing_private_boundary"])
def test_saved_usb_receipt_does_not_override_current_hermes_status(usb_plan, tmp_path, change):
    plan = subset(usb_plan)
    bound = usb_bindings(plan)
    put_transport_proof(plan, bound, tmp_path)
    observed = admitted_status(bound)
    if change == "not_admitted":
        observed["admitted_devices"] = []
    elif change == "not_connected":
        observed["connected_admitted_devices"] = []
    else:
        observed["security"].pop("adb_expected_binding")
    result, calls = run(plan, bound, tmp_path, observed)
    assert result["outcome"] == "BLOCKED"
    assert [name for name, _ in calls] == ["android_testing_status"]


def test_usb_import_integrity_is_consistent_but_never_authenticates_producer(usb_plan, tmp_path):
    plan = subset(usb_plan)
    receipt = export_receipt(plan, tmp_path)
    bound = receipt["bindings"]
    bound.pop("wireless_admission_receipt_id")
    bound.update(device_transport="USB_PRIVATE_BRIDGE", device_admission_receipt_id="unit-usb-admission-not-live")
    put_transport_proof(plan, bound, tmp_path)
    result = acceptance.validate_evidence(plan, receipt, tmp_path)
    assert result["outcome"] == "CONSISTENT_IMPORTED_EVIDENCE"
    assert result["live_qualified"] is False
    assert result["producer_authenticity_verified"] is False
    bound["device_admission_receipt_id"] = "forged-other-reference"
    assert acceptance.validate_evidence(plan, receipt, tmp_path)["outcome"] == "FAIL"


def test_case_scoped_usb_review_cannot_authorize_another_case(usb_plan, tmp_path):
    plan = copy.deepcopy(usb_plan)
    plan["cases"] = plan["cases"][:2]
    plan.pop("plan_sha256")
    plan["plan_sha256"] = acceptance.digest(plan)
    bound = usb_bindings(plan)
    put_transport_proof(plan, bound, tmp_path, mutate=lambda proof: proof.update(reviewed_case_ids=[plan["cases"][0]["id"]]))
    assert acceptance.device_transport_errors(plan, bound, tmp_path, case_id=plan["cases"][0]["id"]) == []
    assert acceptance.device_transport_errors(plan, bound, tmp_path, case_id=plan["cases"][1]["id"])


@pytest.mark.parametrize("field", ["device_identity_receipt_id", "device_model"])
def test_offline_usb_import_cannot_use_missing_identity_matching_null_in_proof(usb_plan, tmp_path, field):
    plan = subset(usb_plan)
    bound = usb_bindings(plan)
    put_transport_proof(plan, bound, tmp_path, mutate=lambda proof: proof.update({field: None}))
    bound.pop(field)
    assert acceptance.device_transport_errors(plan, bound, tmp_path)


@pytest.mark.parametrize("change", ["missing_original", "tampered_original", "wrong_original_hash", "escaping_original", "normalization_as_original"])
def test_original_export_must_be_separate_present_and_hash_verified(usb_plan, tmp_path, change):
    plan = subset(usb_plan)
    bound = usb_bindings(plan)
    path = put_transport_proof(plan, bound, tmp_path)
    proof = json.loads(path.read_text())
    original = tmp_path / proof["source_artifact"]["path"]
    if change == "missing_original":
        original.unlink()
    elif change == "tampered_original":
        original.write_bytes(b"changed original")
    elif change == "wrong_original_hash":
        proof["source_artifact"]["sha256"] = "c" * 64
    elif change == "escaping_original":
        proof["source_artifact"]["path"] = "../outside"
    else:
        proof["source_artifact"]["path"] = path.name
    path.write_text(json.dumps(proof))
    bound["device_transport_evidence"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    result, calls = run(plan, bound, tmp_path)
    assert result["outcome"] == "BLOCKED"
    assert calls == []
