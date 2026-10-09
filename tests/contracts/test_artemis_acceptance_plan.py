"""Actual registry coverage and refusal rules, without synthetic live claims."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import re

import pytest

from tools.certification import artemis_acceptance as acceptance

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def plan():
    return acceptance.build_plan()


def subset(plan, case_id="OF-HOME-001:happy"):
    value = copy.deepcopy(plan)
    value["cases"] = [next(c for c in value["cases"] if c["id"] == case_id)]
    value.pop("plan_sha256")
    value["plan_sha256"] = acceptance.digest(value)
    return value


def bindings(plan):
    return {"repository_sha": "a" * 40, "apk_sha256": "b" * 64,
            "deployment_receipt_id": "unit-deployment", "fixture_receipt_id": "unit-fixture",
            "wireless_admission_receipt_id": "unit-admission", "device_serial": "unit-s24:37123",
            "device_identity_receipt_id": "unit-identity", "device_model": "SM-S928B",
            "inputs_sha256": plan["inputs_sha256"], "isolated_acceptance_realm": True,
            "no_production_service_disruption": True}


def status(bound):
    return {"plane": "HERMES_ANDROID_TESTING_PLANE", "authority": "HERMES_CONTROL_AUTHORITY",
            "subordinate": "ARTEMIS", "raw_upstream_mcp_exposed": False,
            "admitted_devices": [bound["device_serial"]], "connected_admitted_devices": [bound["device_serial"]],
            "security": {"device_admission_required": True, "hermes_is_only_exposed_control_surface": True}}


def export_receipt(plan, root):
    bound = bindings(plan)
    case = plan["cases"][0]
    call = acceptance.invocation(plan, case["id"], device_serial=bound["device_serial"])
    run_id = "unit-run"
    artifacts = []

    def put(kind, data):
        encoded = data if isinstance(data, bytes) else json.dumps(data).encode()
        path = root / f"{kind}.bin"
        path.write_bytes(encoded)
        item = {"id": kind, "kind": kind, "path": path.name, "sha256": hashlib.sha256(encoded).hexdigest()}
        artifacts.append(item)
        return item

    screenshot = put("screenshot", b"unit synthetic screenshot; no device run")
    logcat = put("logcat", b"unit synthetic Logcat; no device run")
    put("step_trace", {"broker_run_id": run_id, "objective_sha256": call["objective_sha256"],
                       "source_receipt_ref": "unit-source-not-live", "steps": [{"number": 1, "observed_action": "unit fixture observation",
                       "screenshot_sha256": screenshot["sha256"]}]})
    put("installed_apk_readback", {"device_serial": bound["device_serial"], "device_model": "SM-S928B",
                                  "package_name": "com.dial.van", "apk_sha256": bound["apk_sha256"],
                                  "broker_run_id": run_id, "independent_observation": True})
    correlation = {"record_id": "unit-record"}
    for kind, producer in (("backend_readback", "gateway_readback"), ("hermes_receipt", "hermes_observer"),
                           ("service_readback", "service_readback"), ("local_device_readback", "android_speaker_profile_readback")):
        if kind in case["required_artifact_kinds"]:
            body = {"case_id": case["id"], "broker_run_id": run_id, "apk_sha256": bound["apk_sha256"],
                       "repository_sha": bound["repository_sha"], "inputs_sha256": plan["inputs_sha256"],
                       "producer": producer, "source_receipt_ref": "unit-original-not-live", "independent_observation": True,
                       "correlation": correlation, "outcome": "VERIFIED_READ"}
            if kind == "local_device_readback":
                operation = case["local_speaker_operation"]
                present, consent = operation != "REMOVE", operation != "READ"
                body.update(schema_version=1, device_serial=bound["device_serial"], observed_at_ms=1_791_367_230_000,
                            outcome=case["expected_postcondition_outcomes"][0], speaker_profile={
                    "operation": operation, "profile_present": present, "profile_revision": "c" * 64 if present else None,
                    "model_sha256": case["local_speaker_model_sha256"], "dimension": 256 if present else 0,
                    "remote_binding_status": "NOT_REQUIRED" if operation == "REMOVE" else "CURRENT",
                    "local_keys_verified": True, "similarity_evidence_usable": present,
                    "consent_purpose": "van.local-speaker-profile" if consent else None,
                    "consent_verified": consent, "consent_consumed": consent, "consent_age_ms": 10_000 if consent else None,
                    "raw_audio_exported": False, "embedding_exported": False, "action_authority_granted": False,
                })
            put(kind, body)
    summary = {"run_id": run_id, "success": True, "project": "van", "device_serial": bound["device_serial"],
               "repository_sha": bound["repository_sha"], "objective_sha256": call["objective_sha256"],
               "started_at": "2026-10-07T10:00:00+00:00", "finished_at": "2026-10-07T10:01:00+00:00",
               "authority": "TEST_EVIDENCE_NON_AUTHORITATIVE_UNTIL_RECONCILED",
               "artifacts": {"screenshot": screenshot, "logcat": logcat}}
    return {"plan_sha256": plan["plan_sha256"], "bindings": bound, "cases": [{"case_id": case["id"], "outcome": "VERIFIED",
            "broker_summary": summary, "artifacts": artifacts, "correlation": correlation,
            "assertions": [{"id": a, "observed": True, "observation": "Unit fixture assertion; no live observation",
                            "artifact_id": ("local_device_readback" if case.get("local_speaker_operation") else "backend_readback")
                            if a == "independent_postcondition" else "screenshot"}
                            for a in case["required_assertions"]]}]}


def rewrite_artifact(receipt, root, kind, mutate):
    artifact = next(a for a in receipt["cases"][0]["artifacts"] if a["kind"] == kind)
    path = root / artifact["path"]
    value = json.loads(path.read_text())
    mutate(value)
    path.write_text(json.dumps(value))
    artifact["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


def test_plan_covers_every_feature_function_surface_and_state(plan):
    features = json.loads((ROOT / "registries/owner_features.json").read_text())["features"]
    screens = json.loads((ROOT / "registries/owner_screens.json").read_text())["screens"]
    cases = plan["cases"]
    assert len({c["id"] for c in cases}) == len(cases)
    functions = sum(len(f["current_implementation"]["functions"]) for f in features)
    recoveries = sum(bool(fn.get("acceptance_contract", {}).get("recovery")) for f in features for fn in f["current_implementation"]["functions"])
    expected_cases = sum(len(f["required_acceptance_states"]) + 1 for f in features) + functions * 2 + recoveries + len(screens) * 2 + 12
    assert plan["coverage"] == {"features": len(features), "functions": functions, "surfaces": len(screens), "cases": expected_cases}
    for feature in features:
        actual = {c["state"] for c in cases if c["kind"] == "feature" and c["feature_ids"] == [feature["id"]]}
        assert actual == set(feature["required_acceptance_states"]) | {"recovery"}
        for function in feature["current_implementation"]["functions"]:
            expected_states = {"happy", "error"} | ({"recovery"} if function.get("acceptance_contract", {}).get("recovery") else set())
            assert {c["state"] for c in cases if function["id"] in c["function_ids"]} == expected_states
    for screen in screens:
        assert {c["state"] for c in cases if c["kind"] == "surface" and c["surface_ids"] == [screen["id"]]} == {"reachability", "restoration"}
    assert {c["id"] for c in cases if c["kind"] == "cross_cutting"} >= {"CC-PHONE-REBOOT", "CC-WS-POST-SSE", "CC-PROVIDER-UNKNOWN", "CC-LOG-PRIVACY"}


def test_owner_calls_never_direct_privileged_projection_endpoints(plan):
    from tools.audit.registry_sources import service_endpoint

    endpoints = {e["endpoint_id"]: e for e in json.loads((ROOT / "registries/owner_endpoints.json").read_text())["endpoints"]}
    for case in plan["cases"]:
        for endpoint_id in case["owner_endpoint_ids"]:
            assert not service_endpoint(endpoints[endpoint_id]["authentication"])
        for endpoint_id in case["service_endpoint_ids"]:
            assert service_endpoint(endpoints[endpoint_id]["authentication"])
        assert not set(case["owner_endpoint_ids"]) & set(case["service_endpoint_ids"])
    runtime = next(c for c in plan["cases"] if c["id"] == "OF-AUTOMATION-001:canonical-runtime:happy")
    assert not runtime["owner_endpoint_ids"]
    assert runtime["service_endpoint_ids"] and runtime["execution_role"] == "OWNER_PROJECTION_AND_INDEPENDENT_SERVICE_OBSERVATION"
    assert plan["adapter_route"] == "LEGACY_DDS_HERMES_ANDROID_TESTING_PLANE"
    assert plan["owner_selected_execution_route"] == "NATIVE_ARTEMIS_VIA_DIAL_COMMANDER"
    assert plan["physical_cases_executed"] == 0
    screens = json.loads((ROOT / "registries/owner_screens.json").read_text())["screens"]
    assert set(plan["known_missing_surfaces"]) == {s["id"] for s in screens if s["current_coverage_status"] == "missing"}
    assert any("no pairing tool" in x for x in plan["prerequisites"])


def test_used_mcp_and_core_deployment_closure_is_hashed(plan):
    required = {"hermes/mcp/owner_runtime_stdio.mjs", "tools/hermes/register_owner_runtime_mcp.sh",
                "tools/hermes/install_van_profile.sh", "tools/runtime/install_van_gateway_service.sh",
                "tools/runtime/prepare_owner_core_deployment.py", "tools/runtime/preflight_owner_core.py",
                "tools/runtime/render_systemd_unit.py", "deploy/systemd/van-gateway.service",
                "deploy/van-owner-core/profile.example.json", "deploy/van-browser-stream/prepare_profiles.py",
                "deploy/van-browser-stream/install_profiles.py", "registries/owner_endpoint_schemas.json"}
    qualification = json.loads((ROOT / "registries/owner_features.json").read_text())["current_source_qualification"]
    required.add(qualification.get("source_freeze_manifest", qualification["source_review_manifest"]))
    assert required <= plan["inputs_sha256"].keys()
    for path in required:
        assert plan["inputs_sha256"][path] == hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    changed = copy.deepcopy(plan)
    changed["inputs_sha256"]["hermes/mcp/owner_runtime_stdio.mjs"] = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        acceptance.verify_plan(changed)


def test_read_functions_do_not_inherit_whole_capability_mutation_requirements(plan):
    functions = {c["id"]: c for c in plan["cases"] if c["kind"] == "function"}
    reminder_read = functions["OF-REMINDER-001:read:happy"]
    assert "Read open reminders" in reminder_read["expected"]
    assert "created reminder" not in reminder_read["expected"]
    assert "read-only projection or metadata cannot prove" in reminder_read["expected"]
    features = {c["id"]: c for c in plan["cases"] if c["kind"] == "feature"}
    assert "created reminder" in features["OF-REMINDER-001:happy"]["expected"]


def test_download_metadata_functions_never_require_or_qualify_phone_binary_transfer(plan, tmp_path):
    for function_id in ("review-downloads", "remove-download-record"):
        case_id = f"OF-BROWSER-004:{function_id}:happy"
        p = subset(plan, case_id)
        case = p["cases"][0]
        assert "exact artifact bytes" not in case["readback"]
        assert "read-only projection or metadata cannot prove" in case["expected"]
        assert "byte_effect_readback" not in case["required_artifact_kinds"]
    p = subset(plan, "OF-BROWSER-004:review-downloads:happy")
    receipt = export_receipt(p, tmp_path)
    assert acceptance.validate_evidence(p, receipt, tmp_path)["outcome"] == "CONSISTENT_IMPORTED_EVIDENCE"
    rewrite_artifact(receipt, tmp_path, "backend_readback", lambda d: d.update(outcome="VERIFIED_SUCCESS"))
    assert acceptance.validate_evidence(p, receipt, tmp_path)["outcome"] == "FAIL"


@pytest.mark.parametrize("function_id", ["save-to-phone", "upload-from-phone", "explicit-clipboard"])
@pytest.mark.parametrize("empty_content", [False, True])
def test_phone_byte_functions_require_actual_bytes_and_independent_matching_effects(plan, tmp_path, function_id, empty_content):
    p = subset(plan, f"OF-BROWSER-004:{function_id}:happy")
    case = p["cases"][0]
    assert "byte_effect_readback" in case["required_artifact_kinds"]
    assert "exact artifact bytes" in case["readback"]
    receipt = export_receipt(p, tmp_path)
    assert acceptance.validate_evidence(p, receipt, tmp_path)["outcome"] == "FAIL"
    rewrite_artifact(receipt, tmp_path, "backend_readback", lambda d: d.update(outcome="VERIFIED_SUCCESS"))
    bound = receipt["bindings"]; artifacts = receipt["cases"][0]["artifacts"]
    effects = []
    for operation in case["byte_effect_operations"]:
        content = b"" if empty_content else ("harmless fixture " + operation).encode()
        path = tmp_path / (operation + ".bin"); path.write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()
        artifacts.append({"id": operation, "kind": "transfer_bytes", "path": path.name, "sha256": sha})
        effects.append({"operation": operation, "content_artifact_id": operation,
                        "expected_sha256": sha, "observed_effect_sha256": sha, "length_bytes": len(content),
                        "session_id": "unit-session", "target_id": "unit-target", "producer_epoch": 7,
                        "producer_session_id":"unit-producer",
                        "transfer_id": "unit-transfer-" + operation, "source_receipt_ref": "unit-target-not-live",
                        "independent_observation": True})
    correlation={**receipt["cases"][0]["correlation"],"byte_effects":{effect["operation"]:{key:effect[key] for key in
        ("session_id","target_id","transfer_id","producer_session_id","producer_epoch")} for effect in effects}}
    receipt["cases"][0]["correlation"]=correlation
    for kind in ("backend_readback","hermes_receipt","service_readback"):
        if any(a["kind"]==kind for a in artifacts):
            rewrite_artifact(receipt,tmp_path,kind,lambda d:d.update(correlation=correlation))
    proof = {"case_id": case["id"], "broker_run_id": "unit-run", "apk_sha256": bound["apk_sha256"],
             "repository_sha": bound["repository_sha"], "inputs_sha256": p["inputs_sha256"],
             "producer": "browser_transfer_readback", "independent_observation": True,
             "source_receipt_ref": "unit-original-not-live", "effects": effects,"correlation":correlation}
    path = tmp_path / "byte-effects.json"; path.write_text(json.dumps(proof))
    artifacts.append({"id": "byte_effect_readback", "kind": "byte_effect_readback", "path": path.name,
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    for assertion in receipt["cases"][0]["assertions"]:
        if assertion["id"] == "exact_byte_effect":assertion["artifact_id"] = "byte_effect_readback"
    result = acceptance.validate_evidence(p, receipt, tmp_path)
    assert result["outcome"] == "CONSISTENT_IMPORTED_EVIDENCE" and result["live_qualified"] is False
    for identity in ("session_id","target_id","transfer_id","producer_session_id","producer_epoch"):
        original=effects[0][identity]
        rewrite_artifact(receipt,tmp_path,"byte_effect_readback",lambda d:d["effects"][0].update({identity:8 if type(original) is int else "different-context"}))
        assert acceptance.validate_evidence(p,receipt,tmp_path)["outcome"]=="FAIL"
        rewrite_artifact(receipt,tmp_path,"byte_effect_readback",lambda d:d["effects"][0].update({identity:original}))
    rewrite_artifact(receipt, tmp_path, "byte_effect_readback", lambda d: d["effects"][0].update(observed_effect_sha256="0" * 64))
    assert acceptance.validate_evidence(p, receipt, tmp_path)["outcome"] == "FAIL"


def test_payload_matches_actual_synchronous_tool_fields_and_bound(plan):
    source = (ROOT.parent / "dial-development-system/agent-system/orchestration/android-testing-mcp.mjs").read_text()
    tool = source[source.index("name:'android_test_run'"):source.index("function send(v)")]
    declared = set(re.findall(r"^\s{8}(\w+):\{type:", tool, re.M))
    assert declared == acceptance.CALL_KEYS
    for case in plan["cases"]:
        if case["execution_readiness"] != "MISSING_FRONTEND":
            call = acceptance.invocation(plan, case["id"], device_serial="unit-s24:37123")
            assert call["tool"] == "android_test_run"
            assert set(call["arguments"]) <= declared
            assert len(call["arguments"]["objective"]) <= 12000
            assert call["arguments"]["profile"] == "pro"
            assert "trace_id" not in call["arguments"]


@pytest.mark.parametrize("change", ["plan_hash", "unknown_case", "missing_surface", "apk_escape", "timeout"])
def test_invalid_execution_arguments_refused(plan, change):
    p = copy.deepcopy(plan)
    kwargs = {"case_id": "OF-HOME-001:happy", "device_serial": "unit-s24:37123"}
    if change == "plan_hash":
        p["target"]["backend"] = "other-host"
    elif change == "unknown_case":
        kwargs["case_id"] = "invented:happy"
    elif change == "missing_surface":
        kwargs["case_id"] = "van.browser.downloads:reachability"
        next(c for c in p["cases"] if c["id"] == kwargs["case_id"])["execution_readiness"] = "MISSING_FRONTEND"
        p.pop("plan_sha256")
        p["plan_sha256"] = acceptance.digest(p)
    elif change == "apk_escape":
        kwargs["apk_path"] = "../../outside.apk"
    else:
        kwargs["timeout_ms"] = 10
    with pytest.raises(ValueError):
        acceptance.invocation(p, **kwargs)


@pytest.mark.parametrize("state", ["no_pairing_receipt", "not_connected", "not_admitted", "raw_mcp"])
def test_wireless_phone_not_currently_admitted_blocks_before_task(plan, state):
    p = subset(plan)
    bound = bindings(p)
    observed = status(bound)
    if state == "no_pairing_receipt":
        bound.pop("wireless_admission_receipt_id")
    elif state == "not_connected":
        observed["connected_admitted_devices"] = []
    elif state == "not_admitted":
        observed["admitted_devices"] = []
    else:
        observed["raw_upstream_mcp_exposed"] = True
    calls = []

    async def tool(name, args):
        calls.append(name)
        assert name == "android_testing_status"
        return observed

    result = asyncio.run(acceptance.run_case(tool, p, p["cases"][0]["id"], bound))
    assert result["outcome"] == "BLOCKED"
    assert result["live_qualified"] is False
    assert "android_test_run" not in calls


def test_ambiguous_transport_never_restarts_device_task(plan):
    p = subset(plan)
    bound = bindings(p)
    calls = []

    async def tool(name, args):
        calls.append(name)
        if name == "android_testing_status":
            return status(bound)
        raise OSError("synthetic response lost")

    result = asyncio.run(acceptance.run_case(tool, p, p["cases"][0]["id"], bound))
    assert result["outcome"] == "OUTCOME_UNKNOWN"
    assert calls == ["android_testing_status", "android_test_run"]


@pytest.mark.parametrize("case_id", ["OF-MEMORY-002:happy", "OF-TRADING-003:happy", "OF-APPROVAL-001:happy"])
def test_destructive_demo_and_private_owner_gates_block_before_any_call(plan, case_id):
    p = subset(plan, case_id)
    bound = bindings(p)

    async def tool(name, args):
        pytest.fail("Missing exact safety bindings must not make any phone call")

    result = asyncio.run(acceptance.run_case(tool, p, case_id, bound))
    assert result["outcome"] == "BLOCKED"


@pytest.mark.parametrize("model", ["SM-G998B", "SM-S928U", "SM-S928N", "SM-S928B/DS", "SM_S928B", "model:SM_S928B"])
def test_different_admitted_handset_cannot_be_used_for_s24_acceptance(plan, model):
    p = subset(plan)
    bound = bindings(p)
    bound["device_model"] = model

    async def tool(name, args):
        pytest.fail("Wrong handset must not make a phone call")

    result = asyncio.run(acceptance.run_case(tool, p, p["cases"][0]["id"], bound))
    assert result["outcome"] == "BLOCKED"


def test_successful_cli_exit_remains_unqualified(plan, tmp_path):
    p = subset(plan)
    receipt = export_receipt(p, tmp_path)
    bound = receipt["bindings"]

    async def tool(name, args):
        return status(bound) if name == "android_testing_status" else receipt["cases"][0]["broker_summary"]

    result = asyncio.run(acceptance.run_case(tool, p, p["cases"][0]["id"], bound))
    assert result["outcome"] == "EXECUTED_REQUIRES_RECONCILIATION"
    assert result["live_qualified"] is False


def test_broker_success_alone_and_empty_coverage_cannot_pass(plan, tmp_path):
    p = subset(plan)
    receipt = export_receipt(p, tmp_path)
    receipt["cases"][0]["artifacts"] = []
    assert acceptance.validate_evidence(p, receipt, tmp_path)["outcome"] == "FAIL"
    receipt["cases"] = []
    assert acceptance.validate_evidence(p, receipt, tmp_path)["outcome"] == "BLOCKED"


def test_even_consistent_synthetic_exports_are_not_live_qualified(plan, tmp_path):
    p = subset(plan)
    result = acceptance.validate_evidence(p, export_receipt(p, tmp_path), tmp_path)
    assert result["outcome"] == "CONSISTENT_IMPORTED_EVIDENCE"
    assert result["live_qualified"] is False
    assert result["producer_authenticity_verified"] is False


@pytest.mark.parametrize("model", ["SM-S928U", "SM-S928N", "SM-S928B/DS", "SM_S928B"])
def test_installed_phone_model_must_match_exact_plan_and_binding_even_if_variant_shares_prefix(plan, tmp_path, model):
    p = subset(plan)
    receipt = export_receipt(p, tmp_path)
    rewrite_artifact(receipt, tmp_path, "installed_apk_readback", lambda d: d.update(device_model=model))
    assert acceptance.validate_evidence(p, receipt, tmp_path)["outcome"] == "FAIL"


@pytest.mark.parametrize("change", ["altered_file", "path_escape", "wrong_apk", "wrong_source", "unknown_effect", "wrong_producer", "wrong_phone", "trace_missing", "unobserved_assertion", "duplicate_case", "unknown_case_outcome"])
def test_false_positive_evidence_is_rejected(plan, tmp_path, change):
    p = subset(plan, "OF-COMMAND-001:happy")
    receipt = export_receipt(p, tmp_path)
    case = receipt["cases"][0]
    if change == "altered_file":
        (tmp_path / case["artifacts"][0]["path"]).write_bytes(b"changed")
    elif change == "path_escape":
        case["artifacts"][0]["path"] = "../outside"
    elif change == "wrong_apk":
        rewrite_artifact(receipt, tmp_path, "backend_readback", lambda d: d.update(apk_sha256="c" * 64))
    elif change == "wrong_source":
        receipt["bindings"]["inputs_sha256"] = {}
    elif change == "unknown_effect":
        rewrite_artifact(receipt, tmp_path, "hermes_receipt", lambda d: d.update(outcome="ACCEPTED"))
    elif change == "wrong_producer":
        rewrite_artifact(receipt, tmp_path, "service_readback", lambda d: d.update(producer="gateway_readback"))
    elif change == "wrong_phone":
        rewrite_artifact(receipt, tmp_path, "installed_apk_readback", lambda d: d.update(device_model="SM-G998B"))
    elif change == "trace_missing":
        rewrite_artifact(receipt, tmp_path, "step_trace", lambda d: d.update(steps=[]))
    elif change == "unobserved_assertion":
        case["assertions"][0]["observed"] = False
    elif change == "unknown_case_outcome":
        case["outcome"] = "UNRECOGNIZED"
    else:
        receipt["cases"].append(copy.deepcopy(case))
    assert acceptance.validate_evidence(p, receipt, tmp_path)["outcome"] == "FAIL"


@pytest.mark.parametrize("outcome", ["FAIL", "BLOCKED", "PARTIAL", "OUTCOME_UNKNOWN"])
def test_non_success_receipts_are_preserved(plan, tmp_path, outcome):
    p = subset(plan)
    receipt = export_receipt(p, tmp_path)
    receipt["cases"][0]["outcome"] = outcome
    result = acceptance.validate_evidence(p, receipt, tmp_path)
    assert result["outcome"] == outcome
    assert result["live_qualified"] is False


def test_provider_admission_requires_bytes_but_observation_never_reports_new_success(plan):
    cases = {c["id"]: c for c in plan["cases"]}
    admission = cases["OF-BROWSER-004:provider-admission:happy"]
    assert admission["byte_effect_operations"] == ["PROVIDER_WRITE"]
    assert "byte_effect_readback" in admission["required_artifact_kinds"]
    observation = cases["OF-BROWSER-004:provider-observation:happy"]
    assert observation["expected_postcondition_outcomes"] == ["VERIFIED_READ"]
    assert "no replacement-fence release" in observation["authority_gate"]
    assert "no old canonical UNKNOWN/UNVERIFIABLE promotion" in observation["authority_gate"]


def provider_export_fixture(plan,root,provider="ORACLE_OWNER_ARCHIVE"):
    """Synthetic consistency fixture, never an actual claim or live receipt."""
    p=subset(plan,"OF-BROWSER-004:provider-admission:happy")
    receipt=export_receipt(p,root)
    content=b"harmless provider fixture; no live target"
    sha=hashlib.sha256(content).hexdigest()
    capability={"contract":"VAN_OWNER_ARTIFACT_ADMISSION_V1","provider":provider,"provider_identity":"unit-provider-not-live",
        "namespace_admissions":[{"owner_namespace":"unit-owner","project_namespace":"unit-project"}],
        "current_admission_introspection":True,"atomic_one_use_admission_claim":True,"admission_issuer":"van-trading-core",
        "admission_signer_public_sha256":"e"*64,"provider_transport_principal_sha256":"d"*64,
        "claimed_readback_expiry_field":"observation_expires_at_ms"}
    if provider=="VEKL_OWNER_CANDIDATE_INGRESS":
        capability["oracle_instruction_job_id"]="unit-job-not-live"
    immutable={"download_id":"unit-file","provider":provider,"owner_namespace":"unit-owner","project_namespace":"unit-project",
        "content_sha256":sha,"byte_size":len(content),"deadline_ms":1791367260000,"idempotency_key":"unit-draft-not-live",
        "session_id":"unit-session","owner_device_id":"unit-owner-device","target_id":"unit-target","producer_session_id":"unit-producer",
        "artifact_producer_session_id":"unit-producer","profile_alias":"authenticated_owner","profile_lease_id":"unit-profile-lease",
        "profile_generation":7,"source_mission_id":"unit-source-mission","source_mission_state_at_creation":"RUNNING",
        "provider_identity":"unit-provider-not-live","provider_principal_sha256":"d"*64,
        "capability_receipt_sha256":acceptance.digest(capability),"source_authority":"UNTRUSTED_OWNER_FILE_EVIDENCE","automatic_truth_promotion":False}
    request={**immutable,"request_id":"bfile_"+"2"*32,"request_sha256":acceptance.digest(immutable),"status":"VERIFIED_SUCCESS",
        "execution_id":"unit-execution-not-live","command_id":"unit-command-not-live","admission_id":"bfa_"+"1"*32,"effect_attempted":True,
        "source_readback":{"observer":"VAN_NATIVE_PERSISTED_BYTES_READBACK","transfer_id":"unit-transfer-not-live","content_sha256":sha,"byte_size":len(content)}}
    parameters={name:request[name] for name in ("session_id","request_id","request_sha256")}
    claim_id="bfclaim_"+"3"*32
    persisted={"contract":"VAN_OWNER_ARTIFACT_ADMISSION_V1","provider":provider,"provider_identity":request["provider_identity"],
        "owner_namespace":"unit-owner","project_namespace":"unit-project","content_sha256":sha,"byte_size":len(content),
        "admission_id":request["admission_id"],"admission_claim_id":claim_id,"receipt_id":"unit-target-not-live",
        "source_authority":"UNTRUSTED_OWNER_FILE_EVIDENCE","executed_content":False,"owner_truth_promoted":False,"project_truth_promoted":False,
        "status":"ARCHIVED" if provider=="ORACLE_OWNER_ARCHIVE" else "CANDIDATE_RECORDED",
        "independent_content_readback":{"content_sha256":sha,"byte_size":len(content),"observer":"VAN_BOUNDED_PERSISTED_BYTES_READBACK"}}
    if provider=="VEKL_OWNER_CANDIDATE_INGRESS":persisted["canonical_candidate_id"]="unit-candidate-not-live"
    request.update(effect_receipt=copy.deepcopy(persisted),verification_receipts=[copy.deepcopy(persisted),copy.deepcopy(persisted)])
    effect={"operation":"PROVIDER_WRITE","content_artifact_id":"transfer_bytes","expected_sha256":sha,"observed_effect_sha256":sha,
        "length_bytes":len(content),"session_id":"unit-session","target_id":"unit-target","transfer_id":"unit-transfer-not-live",
        "producer_session_id":"unit-producer","producer_epoch":7,"independent_observation":True,"source_receipt_ref":"unit-byte-effect-not-live"}
    correlation={"record_id":request["request_id"],"execution_id":request["execution_id"],"command_id":request["command_id"],
        "mission_id":"unit-provider-mission-not-live","byte_effects":{"PROVIDER_WRITE":{name:effect[name] for name in
            ("session_id","target_id","transfer_id","producer_session_id","producer_epoch")}}}
    record=receipt["cases"][0]
    record["correlation"]=correlation
    for kind in ("backend_readback","hermes_receipt","service_readback"):
        if any(a["kind"]==kind for a in record["artifacts"]):
            rewrite_artifact(receipt,root,kind,lambda d:d.update(correlation=correlation,outcome="VERIFIED_SUCCESS"))
    authority={"authority_source":"OWNER_COMMAND","principal_type":"OWNER_DEVICE","effective_action_class":"A4","owner_approved":True,
        "no_stale_replay":True,"issued_at_unix":1791367200,"expires_at_unix":1791367220,
        "typed_action_id":"browser.file.provider.submit","typed_parameter_constraints":parameters,"command_id":request["command_id"],
        "device_id":request["owner_device_id"],"snapshot_id":"unit-snapshot-not-live"}
    execution={"execution_id":request["execution_id"],"command_id":request["command_id"],"action_id":"browser.file.provider.submit",
        "action_class":"A4","principal_type":"OWNER_DEVICE","status":"VERIFIED_SUCCESS","parameters_digest":acceptance.digest(parameters),
        "snapshot_id":authority["snapshot_id"]}
    claims={name:request[name] for name in ("request_id","request_sha256","session_id","download_id","producer_session_id","content_sha256",
        "byte_size","provider","owner_namespace","project_namespace","provider_identity","provider_principal_sha256","command_id","execution_id","owner_device_id")}
    claims.update(jti=request["admission_id"],purpose="OWNER_ARTIFACT_WRITE_ADMISSION",iss="van-trading-core",aud=request["provider_identity"],
        issued_at_ms=1791367200000,expires_at_ms=1791367230000)
    witness={"request":request,"command_authority":authority,"action_execution":execution,
        "mission":{"mission_id":correlation["mission_id"],"state":"VERIFIED_SUCCESS","authority_envelope":{"source_command_id":request["command_id"]}},
        "admission_claim":{"claims":claims,"claim_id":claim_id,"claimed_at_ms":1791367201000},"target_capability":capability,
        "readback_observations":[{"stage":stage,"source_receipt_ref":"unit-independent-read-not-live-"+stage,
            "independent_observation":True,"receipt_sha256":acceptance.digest(persisted)} for stage in ("INITIAL","ACTION","MISSION")]}
    bound=receipt["bindings"]
    proof={"case_id":p["cases"][0]["id"],"broker_run_id":"unit-run","apk_sha256":bound["apk_sha256"],"repository_sha":bound["repository_sha"],
        "inputs_sha256":p["inputs_sha256"],"producer":"browser_transfer_readback","independent_observation":True,
        "source_receipt_ref":"unit-original-not-live","correlation":correlation,"effects":[effect],"provider_admission":witness}
    for kind,data in (("transfer_bytes",content),("byte_effect_readback",json.dumps(proof).encode())):
        path=root/(kind+".bin");path.write_bytes(data)
        record["artifacts"].append({"id":kind,"kind":kind,"path":path.name,"sha256":hashlib.sha256(data).hexdigest()})
    next(a for a in record["assertions"] if a["id"]=="exact_byte_effect")["artifact_id"]="byte_effect_readback"
    return p,receipt


@pytest.mark.parametrize("provider",["ORACLE_OWNER_ARCHIVE","VEKL_OWNER_CANDIDATE_INGRESS"])
def test_provider_write_import_needs_exact_actual_record_shapes_but_never_authenticates_fixture(plan,tmp_path,provider):
    p,receipt=provider_export_fixture(plan,tmp_path,provider)
    result=acceptance.validate_evidence(p,receipt,tmp_path)
    assert result["outcome"]=="CONSISTENT_IMPORTED_EVIDENCE",result
    assert result["live_qualified"] is result["producer_authenticity_verified"] is False


@pytest.mark.parametrize("fault",["generic_bytes_only","unknown_command","unknown_mission","unapproved","other_namespace","other_claim",
    "unclaimed","late_claim","expired_command","stale_replay","changed_request","source_transfer","source_producer","missing_reader","reused_reader","truth_promotion","metadata_only","stale_capability"])
def test_provider_write_cannot_pass_with_unapproved_uncertain_or_metadata_only_effect(plan,tmp_path,fault):
    p,receipt=provider_export_fixture(plan,tmp_path)
    def mutate(proof):
        witness=proof["provider_admission"]
        if fault=="generic_bytes_only":del proof["provider_admission"]
        elif fault=="unknown_command":witness["action_execution"]["status"]="UNVERIFIABLE"
        elif fault=="unknown_mission":witness["mission"]["state"]="UNVERIFIABLE"
        elif fault=="unapproved":witness["command_authority"]["owner_approved"]=False
        elif fault=="other_namespace":witness["request"]["effect_receipt"]["project_namespace"]="other-project"
        elif fault=="other_claim":witness["request"]["effect_receipt"]["admission_claim_id"]="bfclaim_"+"9"*32
        elif fault=="unclaimed":witness["admission_claim"]["claimed_at_ms"]=None
        elif fault=="late_claim":witness["admission_claim"]["claimed_at_ms"]=witness["admission_claim"]["claims"]["expires_at_ms"]
        elif fault=="expired_command":witness["command_authority"]["expires_at_unix"]=1791367200
        elif fault=="stale_replay":witness["command_authority"]["no_stale_replay"]=False
        elif fault=="changed_request":witness["request"]["owner_namespace"]="another-owner"
        elif fault=="source_transfer":witness["request"]["source_readback"]["transfer_id"]="unrelated-transfer"
        elif fault=="source_producer":witness["request"]["producer_session_id"]="unrelated-producer"
        elif fault=="missing_reader":witness["readback_observations"].pop()
        elif fault=="reused_reader":witness["readback_observations"][2]["source_receipt_ref"]=witness["readback_observations"][0]["source_receipt_ref"]
        elif fault=="truth_promotion":witness["request"]["effect_receipt"]["owner_truth_promoted"]=True
        elif fault=="metadata_only":del witness["request"]["effect_receipt"]["independent_content_readback"]
        else:witness["target_capability"]["atomic_one_use_admission_claim"]=False
    rewrite_artifact(receipt,tmp_path,"byte_effect_readback",mutate)
    assert acceptance.validate_evidence(p,receipt,tmp_path)["outcome"]=="FAIL"


@pytest.mark.parametrize("function", ["local-owner-enrollment", "local-profile-readback", "local-profile-erasure"])
def test_speaker_cases_use_private_local_metadata_not_fabricated_gateway_readback(plan, tmp_path, function):
    p = subset(plan, f"OF-VOICE-002:{function}:happy")
    case = p["cases"][0]
    assert "local_device_readback" in case["required_artifact_kinds"]
    assert "backend_readback" not in case["required_artifact_kinds"]
    assert case["safety"]["private_owner_interaction"] is True
    assert not case["owner_endpoint_ids"] and not case["service_endpoint_ids"]
    receipt = export_receipt(p, tmp_path)
    result = acceptance.validate_evidence(p, receipt, tmp_path)
    assert result["outcome"] == "CONSISTENT_IMPORTED_EVIDENCE", result
    assert result["live_qualified"] is result["producer_authenticity_verified"] is False


@pytest.mark.parametrize("change", ["wrong_model", "wrong_device", "stale_observation", "unknown_fields", "raw_audio", "embedding",
                                     "action_authority", "profile_absent", "consent_missing", "consent_replayed", "consent_stale",
                                     "consent_other_purpose", "binding_unavailable", "profile_revision_missing", "wrong_dimension",
                                     "numeric_boolean", "gateway_producer", "gateway_postcondition"])
def test_speaker_metadata_cannot_qualify_unbound_or_privacy_leaking_enrollment(plan, tmp_path, change):
    p = subset(plan, "OF-VOICE-002:local-owner-enrollment:happy")
    receipt = export_receipt(p, tmp_path)
    def mutate(body):
        metadata = body["speaker_profile"]
        if change == "wrong_model": metadata["model_sha256"] = "0" * 64
        elif change == "wrong_device": body["device_serial"] = "other:1"
        elif change == "stale_observation": body["observed_at_ms"] = 1
        elif change == "unknown_fields": metadata["embedding_values"] = [1, 0]
        elif change == "raw_audio": metadata["raw_audio_exported"] = True
        elif change == "embedding": metadata["embedding_exported"] = True
        elif change == "action_authority": metadata["action_authority_granted"] = True
        elif change == "profile_absent": metadata.update(profile_present=False, profile_revision=None, dimension=0, similarity_evidence_usable=False)
        elif change == "consent_missing": metadata.update(consent_verified=False, consent_purpose=None, consent_age_ms=None)
        elif change == "consent_replayed": metadata["consent_consumed"] = False
        elif change == "consent_stale": metadata["consent_age_ms"] = 30_000
        elif change == "consent_other_purpose": metadata["consent_purpose"] = "owner.command.approval"
        elif change == "binding_unavailable": metadata["remote_binding_status"] = "UNAVAILABLE"
        elif change == "profile_revision_missing": metadata["profile_revision"] = None
        elif change == "wrong_dimension": metadata["dimension"] = 255
        elif change == "numeric_boolean": metadata["local_keys_verified"] = 1
        elif change == "gateway_producer": body["producer"] = "gateway_readback"
    rewrite_artifact(receipt, tmp_path, "local_device_readback", mutate)
    if change == "gateway_postcondition":
        for artifact in receipt["cases"][0]["artifacts"]:
            if artifact["kind"] == "local_device_readback": artifact["kind"] = "backend_readback"
    result = acceptance.validate_evidence(p, receipt, tmp_path)
    assert result["outcome"] == "FAIL", result


def test_offline_speaker_erasure_witness_requires_actual_local_key_match_and_absence(plan, tmp_path):
    p = subset(plan, "OF-VOICE-002:local-profile-erasure:happy")
    receipt = export_receipt(p, tmp_path)
    rewrite_artifact(receipt, tmp_path, "local_device_readback", lambda b: b["speaker_profile"].update(local_keys_verified=False))
    assert acceptance.validate_evidence(p, receipt, tmp_path)["outcome"] == "FAIL"
    receipt = export_receipt(p, tmp_path)
    rewrite_artifact(receipt, tmp_path, "local_device_readback", lambda b: b["speaker_profile"].update(
        profile_present=True, profile_revision="c" * 64, dimension=256))
    assert acceptance.validate_evidence(p, receipt, tmp_path)["outcome"] == "FAIL"
