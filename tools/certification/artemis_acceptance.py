#!/usr/bin/env python3
"""Prepare governed Artemis calls and validate imported evidence, never raw ADB.

This module has no host login, network client, subprocess or MCP server launcher.
An authorized host can pass its existing typed MCP call function to run_case.
Offline receipts prove consistency only, not the authenticity of a live producer.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Awaitable, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.certification.artemis_scenarios import (JOURNEYS, STATE_FIXTURES, RECOVERY_JOURNEYS,
                                                FUNCTION_OUTCOMES, BYTE_EFFECT_FUNCTIONS, LOCAL_SPEAKER_FUNCTIONS)
from tools.audit.registry_sources import service_endpoint

SHA = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40}$")
SERIAL = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")
CALL_KEYS = {"project", "device_serial", "objective", "profile", "gradle_task", "apk_path", "package_name", "timeout_ms"}
HERMES_FEATURES = {"OF-COMMAND-001", "OF-GOOGLE-002", "OF-KNOWLEDGE-001", "OF-AUTOMATION-001", "OF-BROWSER-001", "OF-BROWSER-002", "OF-BROWSER-003", "OF-VOICE-001"}
PRIVATE_FEATURES = {"OF-APPROVAL-001", "OF-MEMORY-002", "OF-GOOGLE-001", "OF-GOOGLE-002", "OF-VOICE-001", "OF-VOICE-002", "OF-TRADING-003", "OF-TRADING-004", "OF-TRADING-005"}
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
WIRELESS_ADB = "WIRELESS_ADB"
USB_PRIVATE_BRIDGE = "USB_PRIVATE_BRIDGE"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("JSON input exceeds the evidence size bound")
    return json.loads(path.read_text())


def contained(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Evidence/source path escapes the selected root or is not a file")
    return path


def build_plan(root: Path = ROOT, dds_root: Path | None = None, *, device_transport: str = WIRELESS_ADB,
               source_manifest: str | Path | None = None) -> dict:
    if device_transport not in {WIRELESS_ADB, USB_PRIVATE_BRIDGE}:
        raise ValueError("Unsupported governed device transport")
    feature_document = read_json(root / "registries/owner_features.json")
    features = feature_document["features"]
    screens = read_json(root / "registries/owner_screens.json")["screens"]
    endpoints = read_json(root / "registries/owner_endpoints.json")["endpoints"]
    if set(JOURNEYS) != {f["id"] for f in features}:
        raise ValueError("Concrete journey catalog does not cover the current feature registry exactly")
    if len({s["id"] for s in screens}) != len(screens):
        raise ValueError("Duplicate registered surface")
    inputs = {"registries/owner_features.json", "registries/owner_screens.json", "registries/owner_endpoints.json",
              "registries/owner_endpoint_schemas.json",
              "tools/certification/artemis_acceptance.py", "tools/certification/artemis_scenarios.py",
              "tools/audit/registry_sources.py",
              "android/voice/voice_asset_manifest.json",
              "android/app/build.gradle.kts", "android/build.gradle.kts", "android/settings.gradle.kts", "android/van-gateway.properties",
              "deploy/systemd/van-gateway.service", "deploy/van-owner-core/profile.example.json",
              "deploy/van-browser-stream/prepare_profiles.py", "deploy/van-browser-stream/install_profiles.py",
              "android/buildSrc/src/main/java/com/dial/van/buildconfig/VanProductionTarget.java"}
    qualification = feature_document.get("current_source_qualification", {})
    manifest_name = source_manifest or qualification.get("source_freeze_manifest") or qualification.get("source_review_manifest")
    if manifest_name:
        manifest_path = Path(manifest_name)
        relative_manifest = str(manifest_path.relative_to(root.resolve())) if manifest_path.is_absolute() else str(manifest_path)
        contained(root, relative_manifest)
        inputs.add(relative_manifest)
    for row in features + screens:
        implementation = row.get("current_implementation", {})
        for item in [implementation] + implementation.get("functions", []):
            inputs.update(c["file"] for c in item.get("source_citations", []) if c.get("ref") == "WORKSPACE_PATCH")
    # Baseline citations also refer to actual build inputs. Hash the implementation
    # trees rather than treating an unchanged citation or Git HEAD as build proof.
    for directory in ("android/app/src", "backend/van_gateway", "services", "hermes/profile", "hermes/mcp",
                      "tools/runtime", "tools/hermes", "trading/vati"):
        for path in (root / directory).rglob("*"):
            relative = path.relative_to(root)
            if (path.is_file() and path.suffix in {".kt", ".java", ".xml", ".py", ".json", ".properties", ".yaml", ".yml", ".toml", ".mjs", ".ts", ".md", ".riv", ".sh", ".service"}
                    and not set(relative.parts) & {"__pycache__", "build", ".gradle", "tests", ".git", "receipts", "generated", "artifacts"}):
                inputs.add(str(relative))
    manifest = {p: hashlib.sha256(contained(root, p).read_bytes()).hexdigest() for p in sorted(inputs)}
    endpoint_ids = {e["endpoint_id"] for e in endpoints}
    service_ids = {e["endpoint_id"] for e in endpoints if service_endpoint(e["authentication"])}
    speaker_manifest = read_json(root / "android/voice/voice_asset_manifest.json")
    speaker_entries = [e for e in speaker_manifest["files"]
                       if e.get("capability") == "speaker" and e.get("kind") == "model" and e.get("path") == "speaker/model.onnx"]
    if len(speaker_entries) != 1 or not SHA.fullmatch(str(speaker_entries[0].get("sha256", ""))):
        raise ValueError("Actual compiled speaker model manifest lacks an exact single digest")
    speaker_model_sha256 = speaker_entries[0]["sha256"]
    cases = []

    def add(case_id, kind, row, state, action, expected, fixture, functions=()):
        ids = row.get("owner_endpoint_ids", [])
        if not set(ids) <= endpoint_ids:
            raise ValueError("Unknown owner endpoint in acceptance contract")
        if set(ids) & service_ids:
            raise ValueError("Private machine producer cannot be an owner phone endpoint")
        feature_ids = [row["id"]] if kind != "surface" else row["feature_ids"]
        required = ["screenshot", "logcat", "step_trace", "backend_readback", "installed_apk_readback"]
        if set(feature_ids) & HERMES_FEATURES:
            required += ["hermes_receipt", "service_readback"]
        cases.append({
            "id": case_id, "kind": kind, "state": state, "feature_ids": feature_ids,
            "function_ids": list(functions), "surface_ids": row.get("screen_ids", []) if kind != "surface" else [row["id"]],
            "title": row["title"], "owner_action": action, "fixture": fixture,
            "expected": expected, "readback": JOURNEYS[feature_ids[0]][3],
            "owner_endpoint_ids": ids, "required_artifact_kinds": required,
            "service_endpoint_ids": row.get("service_endpoint_ids", []),
            "endpoint_access_rule": "Phone uses admitted owner routes; internal and attested provider service endpoints are observed through their separate receipts and never called with phone credentials.",
            "required_assertions": ["owner_visible_state", "exact_context_identity", "independent_postcondition", "no_unverified_success"],
            "expected_postcondition_outcomes": ["VERIFIED_SUCCESS", "VERIFIED_READ"] if state == "happy" else
                ["VERIFIED_SUCCESS", "VERIFIED_READ", "VERIFIED_FAILURE", "VERIFIED_REFUSAL", "VERIFIED_NO_EFFECT", "VERIFIED_CANCELLED"],
            "source_coverage": row["current_coverage_status"],
            "execution_readiness": "MISSING_FRONTEND" if row["current_coverage_status"] == "missing" else "REQUIRES_LIVE_FIXTURE",
            "safety": {"isolated_acceptance_realm": True, "demo_trading_only": any(x.startswith("OF-TRADING-") for x in feature_ids),
                       "disposable_owner_memory": "OF-MEMORY-002" in feature_ids,
                       "private_owner_interaction": bool(set(feature_ids) & PRIVATE_FEATURES),
                       "no_production_service_disruption": True},
            "route": row.get("route"), "host_route": row.get("host_route"),
            "interaction_kind": row.get("interaction_kind"),
        })

    for feature in features:
        prepared, action, failure, readback = JOURNEYS[feature["id"]]
        for state, expected in feature["required_acceptance_states"].items():
            if state not in STATE_FIXTURES:
                raise ValueError(f"Unspecified state fixture: {state}")
            add(f"{feature['id']}:{state}", "feature", feature, state, action, expected,
                {"prepared_data": prepared, "state_setup": STATE_FIXTURES[state], "specific_failure": failure})
        add(f"{feature['id']}:recovery", "feature", feature, "recovery", action,
            f"Recover original record, selected IDs and draft without duplicate effect. {readback}",
            {"prepared_data": prepared, "state_setup": STATE_FIXTURES["recovery"], "specific_failure": failure})
        for function in feature["current_implementation"]["functions"]:
            contract = function.get("acceptance_contract", {})
            for state in ("happy", "error", *(("recovery",) if contract.get("recovery") else ())):
                expected = (f"Verify only the advertised action: {function['owner_action']}. Read back its exact record/effect; "
                            "a read-only projection or metadata cannot prove a provider write or binary transfer. "
                            "Do not infer completion of other capability actions.") if state == "happy" else (
                            "Exercise this exact function under its declared access/validation/transition/transport failure. "
                            "Preserve confirmed state/draft; distinguish refusal and unknown outcome without blind replay or unverified success.")
                if state in contract:
                    expected = contract[state]
                add(f"{function['id']}:{state}", "function", feature, state, function["owner_action"], expected,
                    {"prepared_data": prepared, "state_setup": STATE_FIXTURES[state], "specific_failure": failure}, [function["id"]])
                ids = set(function["endpoint_ids"])
                if not ids <= endpoint_ids:
                    raise ValueError("Unknown function endpoint in acceptance contract")
                cases[-1]["owner_endpoint_ids"] = [eid for eid in function["endpoint_ids"] if eid not in service_ids]
                cases[-1]["service_endpoint_ids"] = [eid for eid in function["endpoint_ids"] if eid in service_ids]
                if ids and ids <= service_ids:
                    cases[-1]["execution_role"] = "OWNER_PROJECTION_AND_INDEPENDENT_SERVICE_OBSERVATION"
                cases[-1]["readback"] = f"Independent exact record/effect of this action only: {function['owner_action']}"
                if state == "happy" and function["id"] in FUNCTION_OUTCOMES:
                    cases[-1]["expected_postcondition_outcomes"] = FUNCTION_OUTCOMES[function["id"]]
                cases[-1]["authority_gate"] = function.get("authority_gate", "Use exact declared owner authority; no gate bypass")
                if function["id"] in LOCAL_SPEAKER_FUNCTIONS:
                    cases[-1]["local_speaker_operation"] = LOCAL_SPEAKER_FUNCTIONS[function["id"]]
                    cases[-1]["local_speaker_model_sha256"] = speaker_model_sha256
                    cases[-1]["required_artifact_kinds"].remove("backend_readback")
                    cases[-1]["required_artifact_kinds"].append("local_device_readback")
                    cases[-1]["readback"] = "Independent private device-local encrypted profile metadata/presence/revision and consent outcome; no raw PCM or embedding export. Current model and genuine local key binding must match; imported consistency never authenticates the producer."
                    cases[-1]["execution_role"] = "OWNER_PRIVATE_NATIVE_INTERACTION_AND_LOCAL_DEVICE_OBSERVATION"
                if state == "happy" and function["id"] in BYTE_EFFECT_FUNCTIONS:
                    cases[-1]["byte_effect_operations"] = BYTE_EFFECT_FUNCTIONS[function["id"]]
                    cases[-1]["required_artifact_kinds"].append("byte_effect_readback")
                    cases[-1]["required_assertions"].append("exact_byte_effect")
                    cases[-1]["readback"] = (
                        "Require exact artifact bytes/hash/length and independent current session/target/producer-epoch effect "
                        "for each declared normalized byte-effect operation. Metadata, grant minting and HTTP acceptance alone cannot pass.")
                    cases[-1]["expected"] += " Compare exported harmless fixture bytes with independent target-effect hashes and lengths; a metadata-only receipt is insufficient."
    for screen in screens:
        for state in ("reachability", "restoration"):
            expected = ("Reach the actual registered navigation screen, modal, native/overlay or headless intake; "
                        "verify the intended record and every advertised information/control. A proposed route is not a real destination.")
            if state == "restoration":
                expected = ("Recreate process/activity and restore selected concrete record IDs and query context; "
                            "preserve last confirmed state and pending identity. Headless intake must reconcile its delivery receipt.")
            add(f"{screen['id']}:{state}", "surface", screen, state, "; ".join(screen["actions"]), expected,
                {"prepared_data": "Bound record IDs from isolated fixture; never literal route-template placeholders",
                 "state_setup": "Open via actual UI/Android intake; then recreate for restoration case",
                 "specific_failure": "Missing control, wrong record, unresolved template, or inaccessible state"})
    by_feature = {f["id"]: f for f in features}
    for case_id, feature_id, action, expected, fixture in RECOVERY_JOURNEYS:
        add(case_id, "cross_cutting", by_feature[feature_id], "recovery", action, expected,
            {"prepared_data": fixture, "state_setup": "Exact admitted fault/recovery boundary; keep original identities",
             "specific_failure": "Duplicate effect, widened trust, lost record or falsely reported completion"})
    dds = dds_root or root.parent / "dial-development-system"
    contract_paths = ["agent-system/orchestration/android-testing-mcp.mjs", "agent-system/orchestration/android-testing-plane.mjs",
                      "deploy/netcup/hermes-control/artemis/dial_artemis_mcp_bridge.py"]
    plan = {
        "schema_version": 1, "kind": "VAN_GOVERNED_ARTEMIS_ACCEPTANCE_PLAN", "status": "PREPARED_NOT_EXECUTED",
        "target": {"backend": "van-trading-core", "hermes_and_artemis": "dial-control", "handset": "Samsung S24 Ultra",
                   "phone_connection": "wireless_adb_via_governed_artemis", "product_ingress": "DEDICATED_PINNED_TLS_INGRESS_REQUIRED"},
        "adapter_route": "LEGACY_DDS_HERMES_ANDROID_TESTING_PLANE",
        "owner_selected_execution_route": "NATIVE_ARTEMIS_VIA_DIAL_COMMANDER",
        "coverage": {"features": len(features), "functions": sum(len(f["current_implementation"]["functions"]) for f in features),
                     "surfaces": len(screens), "cases": len(cases)},
        "inputs_sha256": manifest,
        "governed_schema_sources": [{"repository": "dial-development-system", "path": p,
                                      "sha256": hashlib.sha256(contained(dds, p).read_bytes()).hexdigest()} for p in contract_paths],
        "prerequisites": ["Current Global DIAL/Hermes connector and actual exposed Android tool schemas",
                          "Governed one-use wireless pairing and device admission recipe; current schema has no pairing tool",
                          "Phone private pairing code delivered only through secure ephemeral binding, never objective/chat/logs",
                          "Device present in both admitted_devices and connected_admitted_devices",
                          "Reviewed immutable backend/Hermes deployment revisions and owner-signed APK digest",
                          "Matching signed provisioning envelope, public CA/pins, hardware attestation and actual session admission",
                          "Isolated acceptance data, admitted fault fixtures, private owner dialogs and demo-only trading",
                          "Authorized export of per-step CLI traces and independent backend/Hermes/provider receipts"],
        "known_missing_surfaces": [s["id"] for s in screens if s["current_coverage_status"] == "missing"],
        "known_partial_features": [f["id"] for f in features if f["current_coverage_status"] == "partial"],
        "evidence_limits": ["android_test_run success is process exit success, not per-case or owner-goal verification",
                            "Synchronous run_id is not an async owned trace_id; do not feed it to android_trace_inspect",
                            "An offline evidence import checks consistency; it does not establish producer authenticity or live qualification",
                            "Missing/unavailable tests remain BLOCKED; missing frontend controls FAIL; unknown effects remain OUTCOME_UNKNOWN"],
        "physical_cases_executed": 0,
        "preferred_execution_route": "Direct native Artemis through DIAL/Commander without Hermes; see NATIVE_ARTEMIS_HANDOFF_PROMPT.md. This adapter remains bound to the separately declared DDS wrapper schema.",
        "cases": cases,
    }
    if device_transport == USB_PRIVATE_BRIDGE:
        plan["target"]["phone_connection"] = "usb_private_bridge_via_governed_artemis"
        plan["target"]["device_transport"] = USB_PRIVATE_BRIDGE
        plan["status"] = "USB_CANDIDATE_PLAN_PREPARED_NOT_EXECUTED"
        plan["prerequisites"][1:3] = [
            "Authorized Windows USB device plus an admitted private loopback ADB-server bridge to dial-control",
            "Original Hermes device-admission receipt and measured USB/bridge endpoint evidence; caller claims are insufficient",
        ]
        adapted = []
        for case in cases:
            if case["state"] == "offline":
                case["fixture"]["state_setup"] = (
                    "Disconnect phone networking only through the admitted fixture; keep the owner PC/private USB bridge independently connected.")
                adapted.append(case["id"])
            if case["id"] == "CC-PHONE-REBOOT":
                case["expected"] = (
                    "Re-establish the admitted USB/private bridge and exact authorized USB serial; original hardware identity/outbox/session persist and no duplicate effect occurs")
                case["fixture"]["prepared_data"] = "Independent governed USB/private-bridge recovery and harmless acceptance pending command"
                adapted.append(case["id"])
        plan["transport_adaptation"] = {
            "source_transport": WIRELESS_ADB, "selected_transport": USB_PRIVATE_BRIDGE,
            "adapted_case_ids": adapted, "applicability": "CANDIDATES_REQUIRING_CASE_SCOPED_USB_REVIEW",
            "verified_applicable_cases": 0,
            "note": "Registry coverage is candidate coverage; no wireless plan or prior device receipt is promoted to USB acceptance",
        }
    plan["plan_sha256"] = digest(plan)
    return plan


def verify_plan(plan: dict) -> None:
    claimed = plan.get("plan_sha256")
    if claimed != digest({k: v for k, v in plan.items() if k != "plan_sha256"}):
        raise ValueError("Acceptance plan hash mismatch")


def invocation(plan: dict, case_id: str, *, device_serial: str, apk_path: str | None = None, timeout_ms: int = 300000) -> dict:
    verify_plan(plan)
    if not SERIAL.fullmatch(device_serial):
        raise ValueError("An exact admitted device serial is required")
    case = next((c for c in plan["cases"] if c["id"] == case_id), None)
    if not case:
        raise ValueError("Case is not in the frozen plan")
    if case["execution_readiness"] == "MISSING_FRONTEND":
        raise ValueError("Missing frontend control cannot be certified as available")
    if not 60000 <= timeout_ms <= 2700000:
        raise ValueError("Timeout is outside the actual governed schema")
    if apk_path and (Path(apk_path).is_absolute() or ".." in Path(apk_path).parts or not apk_path.endswith(".apk")):
        raise ValueError("APK must be an exact existing repository-relative host path")
    objective = (
        "Run one bounded VAN acceptance case on the admitted owner S24 Ultra; remain within Hermes/Artemis authority. "
        "Use the prepared isolated fixture only. No real trades, private-memory erasure, production service faults, "
        "raw pairing/admission, credential retrieval or permission changes beyond the admitted case. Owner handles "
        "biometrics/OAuth privately; unavailable fixture/dialog/control means BLOCKED or FAIL, never pass. "
        "Do not create another command after ambiguous acceptance; reconcile original identity. "
        "Capture per-step screenshots/trace and final Logcat. Record case ID, source/APK identities, expected/observed "
        "assertions and exact backend/Hermes/service correlation IDs. A successful CLI exit is insufficient. "
        "Report separately VERIFIED, FAIL, BLOCKED, PARTIAL or OUTCOME_UNKNOWN. Case: " + json.dumps(case, ensure_ascii=False)
    )
    if len(objective) > 12000:
        raise ValueError("Objective exceeds actual Hermes admission bound")
    args = {"project": "van", "device_serial": device_serial, "objective": objective, "profile": "pro",
            "package_name": "com.dial.van", "timeout_ms": timeout_ms}
    if apk_path:
        args["apk_path"] = apk_path
    return {"tool": "android_test_run", "arguments": args, "case_id": case_id,
            "plan_sha256": plan["plan_sha256"], "objective_sha256": hashlib.sha256(objective.encode()).hexdigest()}


def unwrap(response: dict) -> dict:
    if response.get("isError") is True:
        raise ValueError("Governed MCP tool returned an error; outcome may require reconciliation")
    value = response.get("structuredContent", response)
    if not isinstance(value, dict):
        raise ValueError("Governed tool result requires a structured object")
    return value


def device_transport_errors(plan: dict, bindings: dict, evidence_root: Path | None = None, *, case_id: str | None = None) -> list[str]:
    """Check normalized original transport evidence; never mint admission or assert authenticity."""
    transport = bindings.get("device_transport", WIRELESS_ADB)
    selected = plan.get("target", {}).get("device_transport", WIRELESS_ADB)
    if transport not in {WIRELESS_ADB, USB_PRIVATE_BRIDGE} or transport != selected:
        return ["Device transport does not match the source-bound plan"]
    if transport == WIRELESS_ADB:
        return [] if bindings.get("wireless_admission_receipt_id") else ["Missing wireless_admission_receipt_id"]
    if not bindings.get("device_admission_receipt_id"):
        return ["Missing device_admission_receipt_id for USB/private bridge"]
    identity_ref = bindings.get("device_identity_receipt_id")
    model = bindings.get("device_model")
    if not isinstance(identity_ref, str) or not identity_ref.strip() or not isinstance(model, str) or not model.startswith("SM-S928"):
        return ["USB/private bridge requires an independently observed S24 identity receipt/model"]
    if bindings.get("wireless_admission_receipt_id"):
        return ["USB/private bridge cannot substitute or reuse a wireless admission receipt"]
    if evidence_root is None:
        return ["USB/private-bridge original evidence root is required"]
    artifact = bindings.get("device_transport_evidence", {})
    try:
        if not isinstance(artifact, dict) or not SHA.fullmatch(str(artifact.get("sha256", ""))):
            raise ValueError()
        path = contained(evidence_root, artifact["path"])
        if path.stat().st_size > MAX_ARTIFACT_BYTES or hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ValueError()
        proof = read_json(path)
        required_matches = {
            "transport": USB_PRIVATE_BRIDGE, "authority": "HERMES_CONTROL_AUTHORITY",
            "producer": "hermes_device_admission", "receipt_id": bindings["device_admission_receipt_id"],
            "device_serial": bindings.get("device_serial"), "device_model": bindings.get("device_model"),
            "device_identity_receipt_id": bindings.get("device_identity_receipt_id"), "host": "dial-control",
            "usb_device_state": "device", "usb_authorization_verified": True,
            "private_bridge_verified": True, "loopback_only_verified": True,
            "endpoint_consistency_verified": True, "independent_observation": True,
        }
        if any(proof.get(name) != value or (type(value) is bool and type(proof.get(name)) is not bool)
               for name, value in required_matches.items()):
            raise ValueError()
        if not proof.get("source_receipt_ref") or not proof.get("bridge_profile_id"):
            raise ValueError()
        # Hash/read the original export separately from its normalization. Neither hash nor
        # a caller-provided source reference proves a producer's identity or authenticity.
        original = proof.get("source_artifact", {})
        if not isinstance(original, dict) or not SHA.fullmatch(str(original.get("sha256", ""))):
            raise ValueError()
        original_path = contained(evidence_root, original["path"])
        if original_path == path or not 0 < original_path.stat().st_size <= MAX_ARTIFACT_BYTES:
            raise ValueError()
        if hashlib.sha256(original_path.read_bytes()).hexdigest() != original["sha256"]:
            raise ValueError()
        endpoint = proof.get("adb_endpoint", {})
        port = endpoint.get("port")
        if endpoint.get("host") != "127.0.0.1" or type(port) is not int or not 1024 <= port <= 65535 or port in {5037, 5555}:
            raise ValueError()
        socket = f"tcp:127.0.0.1:{port}"
        if endpoint.get("server_socket") != socket or endpoint.get("endpoint_id") != socket:
            raise ValueError()
        reviewed = proof.get("reviewed_case_ids")
        if (not isinstance(reviewed, list) or not reviewed or len(reviewed) != len(set(reviewed))
                or not set(reviewed) <= {case["id"] for case in plan["cases"]}
                or (case_id is not None and case_id not in reviewed)):
            raise ValueError()
        if proof.get("plan_sha256") != plan["plan_sha256"]:
            raise ValueError()
    except (ValueError, KeyError, TypeError, OSError):
        return ["USB/private-bridge original admission/endpoint/case-review evidence is missing or mismatched"]
    return []


async def run_case(call_tool: Callable[[str, dict], Awaitable[dict]], plan: dict, case_id: str, bindings: dict,
                   *, evidence_root: Path | None = None) -> dict:
    """Invoke the existing typed MCP only; transport ambiguity is never retried."""
    required = ("repository_sha", "apk_sha256", "deployment_receipt_id", "fixture_receipt_id", "device_serial",
                "device_identity_receipt_id", "device_model", "inputs_sha256")
    if any(not bindings.get(x) for x in required):
        return {"outcome": "BLOCKED", "reason": "Missing deployment/APK/isolation/device-identity bindings", "live_qualified": False}
    if not REVISION.fullmatch(bindings["repository_sha"]) or not SHA.fullmatch(bindings["apk_sha256"]):
        raise ValueError("Immutable source/APK identities are required")
    if not str(bindings["device_model"]).startswith("SM-S928"):
        return {"outcome": "BLOCKED", "reason": "Selected device identity is not the owner's S24 Ultra", "live_qualified": False}
    if bindings["inputs_sha256"] != plan["inputs_sha256"]:
        return {"outcome": "BLOCKED", "reason": "Source/deployment input manifest differs from frozen acceptance plan", "live_qualified": False}
    transport_errors = device_transport_errors(plan, bindings, evidence_root, case_id=case_id)
    if transport_errors:
        return {"outcome": "BLOCKED", "reason": "; ".join(transport_errors), "live_qualified": False}
    call = invocation(plan, case_id, device_serial=bindings["device_serial"], apk_path=bindings.get("apk_path"))
    case = next(c for c in plan["cases"] if c["id"] == case_id)
    for safety, needed in case["safety"].items():
        if needed and bindings.get(safety) is not True:
            return {"outcome": "BLOCKED", "reason": f"Missing exact safety binding: {safety}", "live_qualified": False}
    try:
        status = unwrap(await asyncio.wait_for(call_tool("android_testing_status", {}), 60))
        serial = bindings["device_serial"]
        security = status.get("security", {})
        admitted = (status.get("plane") == "HERMES_ANDROID_TESTING_PLANE"
                    and status.get("authority") == "HERMES_CONTROL_AUTHORITY" and status.get("subordinate") == "ARTEMIS"
                    and status.get("raw_upstream_mcp_exposed") is False
                    and security.get("device_admission_required") is True
                    and security.get("hermes_is_only_exposed_control_surface") is True
                    and serial in status.get("admitted_devices", []) and serial in status.get("connected_admitted_devices", []))
        if not admitted:
            return {"outcome": "BLOCKED", "reason": "Current Hermes device admission/connection not established", "live_qualified": False}
        if bindings.get("device_transport") == USB_PRIVATE_BRIDGE and security.get("adb_expected_binding") != "loopback_or_governed_device_bridge":
            return {"outcome": "BLOCKED", "reason": "Current Hermes private ADB bridge boundary not established", "live_qualified": False}
        raw = unwrap(await asyncio.wait_for(call_tool(call["tool"], call["arguments"]), call["arguments"]["timeout_ms"] / 1000 + 120))
    except (asyncio.TimeoutError, OSError, ValueError):
        return {"outcome": "OUTCOME_UNKNOWN", "case_id": case_id, "plan_sha256": plan["plan_sha256"],
                "reason": "Inspect existing broker run before any new action; no automatic task retry", "live_qualified": False}
    if raw.get("device_serial") != serial or raw.get("objective_sha256") != call["objective_sha256"] or raw.get("repository_sha") != bindings["repository_sha"]:
        return {"outcome": "FAIL", "reason": "Broker source/device/objective identity drift", "live_qualified": False}
    installed = (raw.get("install") or {}).get("apk_sha256")
    if bindings.get("apk_path") and installed != bindings["apk_sha256"]:
        return {"outcome": "FAIL", "reason": "Installed APK digest drift", "live_qualified": False}
    return {"schema_version": 1, "outcome": "EXECUTED_REQUIRES_RECONCILIATION" if raw.get("success") is True else "FAIL",
            "case_id": case_id, "plan_sha256": plan["plan_sha256"], "observed_at": utc(),
            "broker_run_id": raw.get("run_id"), "broker_summary": raw,
            "apk_sha256": bindings["apk_sha256"], "live_qualified": False,
            "device_transport": bindings.get("device_transport", WIRELESS_ADB),
            "device_admission_receipt_id": bindings.get("device_admission_receipt_id"),
            "note": "Obtain per-case assertions, trace export and independent readback before accepting this run"}


def local_speaker_readback_matches(case: dict, body: dict, serial: str, broker: dict) -> bool:
    """Check a private metadata witness; this never authenticates its producer or audio identity."""
    try:
        common_keys = {"schema_version", "case_id", "broker_run_id", "apk_sha256", "repository_sha", "inputs_sha256",
                       "producer", "source_receipt_ref", "independent_observation", "correlation", "outcome",
                       "device_serial", "observed_at_ms", "speaker_profile"}
        if (set(body) != common_keys or type(body["schema_version"]) is not int or body["schema_version"] != 1
                or body["device_serial"] != serial):
            return False
        observed = body["observed_at_ms"]
        if (type(observed) is not int or observed < int(datetime.fromisoformat(broker["started_at"]).timestamp() * 1000)
                or observed > int(datetime.fromisoformat(broker["finished_at"]).timestamp() * 1000)):
            return False
        metadata = body["speaker_profile"]
        keys = {"operation", "profile_present", "profile_revision", "model_sha256", "dimension", "remote_binding_status",
                "local_keys_verified", "similarity_evidence_usable", "consent_purpose", "consent_verified", "consent_consumed",
                "consent_age_ms", "raw_audio_exported", "embedding_exported", "action_authority_granted"}
        if (not isinstance(metadata, dict) or set(metadata) != keys or not case.get("local_speaker_operation")
                or metadata["operation"] != case["local_speaker_operation"]
                or metadata["model_sha256"] != case["local_speaker_model_sha256"]):
            return False
        booleans = {"profile_present", "local_keys_verified", "similarity_evidence_usable", "consent_verified",
                    "consent_consumed", "raw_audio_exported", "embedding_exported", "action_authority_granted"}
        if any(type(metadata[key]) is not bool for key in booleans):
            return False
        if any(metadata[key] for key in ("raw_audio_exported", "embedding_exported", "action_authority_granted")):
            return False
        present = metadata["profile_present"]
        if (type(metadata["dimension"]) is not int or metadata["dimension"] != (256 if present else 0)
                or (present and not SHA.fullmatch(str(metadata["profile_revision"])))
                or (not present and metadata["profile_revision"] is not None)):
            return False
        if metadata["remote_binding_status"] not in {"CURRENT", "UNAVAILABLE", "NOT_REQUIRED"}:
            return False
        if metadata["similarity_evidence_usable"] and not (present and metadata["local_keys_verified"] and metadata["remote_binding_status"] == "CURRENT"):
            return False
        verified = metadata["consent_verified"]
        if verified:
            if (metadata["consent_purpose"] != "van.local-speaker-profile" or not metadata["consent_consumed"]
                    or type(metadata["consent_age_ms"]) is not int or not 0 <= metadata["consent_age_ms"] < 30_000):
                return False
        elif metadata["consent_purpose"] is not None or metadata["consent_age_ms"] is not None:
            return False
        if case["state"] == "happy":
            if metadata["operation"] == "ENROLL":
                return present and verified and metadata["local_keys_verified"] and metadata["remote_binding_status"] == "CURRENT"
            if metadata["operation"] == "REMOVE":
                return not present and verified and metadata["local_keys_verified"]
            return not verified and not metadata["consent_consumed"]
        return True
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def provider_write_readback_matches(proof: dict, effect: dict, correlations: dict, sha: str, size: int) -> bool:
    """Validate exported actual admission records; never authenticate a producer.

    These fields are normalized evidence from VAN's existing request, authority,
    action, mission and admission records, not new provider wire parameters.
    """
    try:
        witness=proof["provider_admission"]
        request=witness["request"]
        immutable=("download_id","provider","owner_namespace","project_namespace","content_sha256","byte_size","deadline_ms","idempotency_key",
            "session_id","owner_device_id","target_id","producer_session_id","artifact_producer_session_id","profile_alias","profile_lease_id",
            "profile_generation","source_mission_id","source_mission_state_at_creation","provider_identity","provider_principal_sha256",
            "capability_receipt_sha256","source_authority","automatic_truth_promotion")
        parameters={name:request[name] for name in ("session_id","request_id","request_sha256")}
        if (request["status"]!="VERIFIED_SUCCESS" or request["effect_attempted"] is not True
                or request["source_authority"]!="UNTRUSTED_OWNER_FILE_EVIDENCE" or request["automatic_truth_promotion"] is not False
                or digest({name:request[name] for name in immutable})!=request["request_sha256"]
                or not re.fullmatch(r"bfile_[0-9a-f]{32}",request["request_id"])
                or not re.fullmatch(r"bfa_[0-9a-f]{32}",request["admission_id"])
                or request["request_id"]!=correlations["record_id"]
                or request["content_sha256"]!=sha or type(request["byte_size"]) is not int or request["byte_size"]!=size
                or request["session_id"]!=effect["session_id"] or request["target_id"]!=effect["target_id"]
                or request["producer_session_id"]!=effect["producer_session_id"] or request["profile_generation"]!=effect["producer_epoch"]):
            return False
        if (type(request["profile_generation"]) is not int or not SHA.fullmatch(request["provider_principal_sha256"])
                or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}",request[name]) for name in ("owner_namespace","project_namespace","provider_identity"))):
            return False
        source=request["source_readback"]
        if (source["observer"]!="VAN_NATIVE_PERSISTED_BYTES_READBACK" or source["transfer_id"]!=effect["transfer_id"]
                or source["content_sha256"]!=sha or type(source["byte_size"]) is not int or source["byte_size"]!=size):
            return False
        authority=witness["command_authority"]
        execution=witness["action_execution"]
        mission=witness["mission"]
        if (authority["authority_source"]!="OWNER_COMMAND" or authority["principal_type"]!="OWNER_DEVICE"
                or authority["effective_action_class"]!="A4" or authority["owner_approved"] is not True
                or authority["no_stale_replay"] is not True
                or authority["typed_action_id"]!="browser.file.provider.submit" or authority["typed_parameter_constraints"]!=parameters
                or authority["command_id"]!=request["command_id"] or authority["device_id"]!=request["owner_device_id"]
                or execution["action_id"]!="browser.file.provider.submit" or execution["action_class"]!="A4"
                or execution["principal_type"]!="OWNER_DEVICE" or execution["status"]!="VERIFIED_SUCCESS"
                or execution["parameters_digest"]!=digest(parameters) or execution["execution_id"]!=request["execution_id"]
                or execution["command_id"]!=request["command_id"] or execution["snapshot_id"]!=authority["snapshot_id"]
                or execution["execution_id"]!=correlations["execution_id"] or execution["command_id"]!=correlations["command_id"]
                or mission["state"]!="VERIFIED_SUCCESS" or mission["mission_id"]!=correlations["mission_id"]
                or mission["authority_envelope"]["source_command_id"]!=request["command_id"]):
            return False
        admission=witness["admission_claim"]
        claims=admission["claims"]
        if (not re.fullmatch(r"bfclaim_[0-9a-f]{32}",admission["claim_id"])
                or type(admission["claimed_at_ms"]) is not int or type(claims["issued_at_ms"]) is not int
                or type(claims["expires_at_ms"]) is not int
                or not claims["issued_at_ms"]<=admission["claimed_at_ms"]<claims["expires_at_ms"]<=claims["issued_at_ms"]+30000
                or claims["jti"]!=request["admission_id"] or claims["purpose"]!="OWNER_ARTIFACT_WRITE_ADMISSION"
                or claims["iss"]!="van-trading-core" or claims["aud"]!=request["provider_identity"]
                or type(authority["issued_at_unix"]) is not int or type(authority["expires_at_unix"]) is not int
                or not authority["issued_at_unix"]*1000<=claims["issued_at_ms"]<=admission["claimed_at_ms"]<min(authority["expires_at_unix"]*1000,(authority["issued_at_unix"]+30)*1000)
                or any(claims[name]!=request[name] or type(claims[name]) is not type(request[name]) for name in ("request_id","request_sha256","session_id","download_id","producer_session_id",
                    "content_sha256","byte_size","provider","owner_namespace","project_namespace","provider_identity","provider_principal_sha256",
                    "command_id","execution_id","owner_device_id"))):
            return False
        capability=witness["target_capability"]
        if (digest(capability)!=request["capability_receipt_sha256"] or capability["contract"]!="VAN_OWNER_ARTIFACT_ADMISSION_V1"
                or capability["provider"]!=request["provider"] or capability["provider_identity"]!=request["provider_identity"]
                or capability["namespace_admissions"]!=[{"owner_namespace":request["owner_namespace"],"project_namespace":request["project_namespace"]}]
                or capability["current_admission_introspection"] is not True or capability["atomic_one_use_admission_claim"] is not True
                or capability["admission_issuer"]!="van-trading-core"
                or not SHA.fullmatch(capability["admission_signer_public_sha256"])
                or capability["provider_transport_principal_sha256"]!=request["provider_principal_sha256"]
                or capability["claimed_readback_expiry_field"]!="observation_expires_at_ms"):
            return False
        if request["provider"] not in {"ORACLE_OWNER_ARCHIVE","VEKL_OWNER_CANDIDATE_INGRESS"}:
            return False
        if request["provider"]=="VEKL_OWNER_CANDIDATE_INGRESS" and (not isinstance(capability.get("oracle_instruction_job_id"),str)
                or not re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}",capability["oracle_instruction_job_id"])):
            return False
        receipts=[request["effect_receipt"],*request["verification_receipts"]]
        observations=witness["readback_observations"]
        if (len(receipts)!=3 or not isinstance(observations,list) or len(observations)!=3
                or [item["stage"] for item in observations]!=["INITIAL","ACTION","MISSION"]
                or len({item["source_receipt_ref"] for item in observations})!=3):
            return False
        for receipt,observation in zip(receipts,observations):
            expected={"contract":"VAN_OWNER_ARTIFACT_ADMISSION_V1","provider":request["provider"],"provider_identity":request["provider_identity"],
                "owner_namespace":request["owner_namespace"],"project_namespace":request["project_namespace"],"content_sha256":sha,
                "byte_size":size,"admission_id":request["admission_id"],"admission_claim_id":admission["claim_id"],
                "source_authority":"UNTRUSTED_OWNER_FILE_EVIDENCE","executed_content":False,"owner_truth_promoted":False,"project_truth_promoted":False,
                "status":"ARCHIVED" if request["provider"]=="ORACLE_OWNER_ARCHIVE" else "CANDIDATE_RECORDED"}
            if (any(receipt.get(name)!=value or type(receipt.get(name)) is not type(value) for name,value in expected.items())
                    or not receipt.get("receipt_id") or observation["independent_observation"] is not True
                    or not observation["source_receipt_ref"] or observation["receipt_sha256"]!=digest(receipt)
                    or receipt["independent_content_readback"]!={"content_sha256":sha,"byte_size":size,"observer":"VAN_BOUNDED_PERSISTED_BYTES_READBACK"}
                    or (request["provider"]=="VEKL_OWNER_CANDIDATE_INGRESS" and not receipt.get("canonical_candidate_id"))):
                return False
        return True
    except (KeyError,ValueError,TypeError):
        return False


def validate_evidence(plan: dict, receipt: dict, evidence_root: Path) -> dict:
    """Fail closed on missing/stale/mismatched evidence; never promote offline claims."""
    verify_plan(plan)
    problems = []
    if receipt.get("plan_sha256") != plan["plan_sha256"]:
        problems.append("Receipt belongs to a different plan/source snapshot")
    bindings = receipt.get("bindings", {})
    for name, pattern in (("repository_sha", REVISION), ("apk_sha256", SHA)):
        if not pattern.fullmatch(str(bindings.get(name, ""))):
            problems.append(f"Missing immutable {name}")
    for name in ("deployment_receipt_id", "fixture_receipt_id", "device_serial"):
        if not bindings.get(name):
            problems.append(f"Missing {name}")
    problems.extend(device_transport_errors(plan, bindings, evidence_root))
    if not SERIAL.fullmatch(str(bindings.get("device_serial", ""))):
        problems.append("Invalid admitted device serial")
    if bindings.get("inputs_sha256") != plan["inputs_sha256"]:
        problems.append("Deployed/built input manifest does not match the frozen plan")
    records = receipt.get("cases", [])
    if not isinstance(records, list):
        raise ValueError("Receipt cases must be an array")
    case_ids = [r.get("case_id") for r in records]
    planned = {c["id"] for c in plan["cases"]}
    if len(case_ids) != len(set(case_ids)) or set(case_ids) - planned:
        problems.append("Duplicate or unplanned case receipts")
    by_id = {r.get("case_id"): r for r in records}
    results = []
    for case in plan["cases"]:
        errors = []
        errors.extend(device_transport_errors(plan, bindings, evidence_root, case_id=case["id"]))
        r = by_id.get(case["id"])
        if case["execution_readiness"] == "MISSING_FRONTEND":
            results.append({"case_id": case["id"], "outcome": "FAIL", "reasons": ["Required frontend surface is missing"]})
            continue
        if not r:
            results.append({"case_id": case["id"], "outcome": "BLOCKED", "reasons": ["No actual case receipt"]})
            continue
        if r.get("outcome") in {"FAIL", "BLOCKED", "PARTIAL", "OUTCOME_UNKNOWN"}:
            results.append({"case_id": case["id"], "outcome": r["outcome"], "reasons": ["Recorded non-success remains non-success"]})
            continue
        if r.get("outcome") != "VERIFIED":
            errors.append("Case has no recognized verified assertion outcome")
        serial = str(bindings.get("device_serial", ""))
        call = invocation(plan, case["id"], device_serial=serial if SERIAL.fullmatch(serial) else "UNBOUND")
        broker = r.get("broker_summary", {})
        if broker.get("success") is not True or not broker.get("run_id"):
            errors.append("Missing successful terminal broker run")
        for key, expected in (("device_serial", bindings.get("device_serial")), ("repository_sha", bindings.get("repository_sha")),
                              ("objective_sha256", call["objective_sha256"]), ("project", "van")):
            if broker.get(key) != expected:
                errors.append(f"Broker {key} mismatch")
        if broker.get("authority") != "TEST_EVIDENCE_NON_AUTHORITATIVE_UNTIL_RECONCILED":
            errors.append("Unexpected broker evidence authority")
        try:
            start = datetime.fromisoformat(broker["started_at"])
            end = datetime.fromisoformat(broker["finished_at"])
            if not start.tzinfo or not end.tzinfo or end < start or (end - start).total_seconds() > 2820:
                raise ValueError()
        except (KeyError, ValueError, TypeError):
            errors.append("Invalid bounded broker observation window")
        artifacts = {}
        for artifact in r.get("artifacts", []):
            try:
                path = contained(evidence_root, artifact["path"])
                data = path.read_bytes() if path.stat().st_size <= MAX_ARTIFACT_BYTES else b""
                if ((not data and artifact.get("kind") != "transfer_bytes")
                        or path.stat().st_size > MAX_ARTIFACT_BYTES
                        or hashlib.sha256(data).hexdigest() != artifact["sha256"]):
                    raise ValueError()
                if artifact["id"] in artifacts:
                    raise ValueError()
                artifacts[artifact["id"]] = artifact
            except (KeyError, ValueError, TypeError, OSError):
                errors.append("Missing, altered, duplicate or escaping exported artifact")
        kinds = {a.get("kind") for a in artifacts.values()}
        for kind in case["required_artifact_kinds"]:
            if kind not in kinds:
                errors.append(f"Missing exported {kind}")
        for kind in ("screenshot", "logcat"):
            observed_hash = (broker.get("artifacts", {}).get(kind) or {}).get("sha256")
            if not observed_hash or not any(a.get("kind") == kind and a["sha256"] == observed_hash for a in artifacts.values()):
                errors.append(f"{kind} does not match broker capture")
        for artifact in [a for a in artifacts.values() if a.get("kind") == "step_trace"]:
            try:
                trace = read_json(contained(evidence_root, artifact["path"]))
                if trace.get("broker_run_id") != broker.get("run_id") or trace.get("objective_sha256") != call["objective_sha256"]:
                    raise ValueError()
                if not trace.get("source_receipt_ref") or not isinstance(trace.get("steps"), list) or not trace["steps"]:
                    raise ValueError()
                for step in trace["steps"]:
                    if not isinstance(step.get("number"), int) or step["number"] < 1 or not step.get("observed_action"):
                        raise ValueError()
                    if not any(a.get("kind") == "screenshot" and a["sha256"] == step.get("screenshot_sha256") for a in artifacts.values()):
                        raise ValueError()
            except (ValueError, KeyError, TypeError, OSError):
                errors.append("Missing or uncorrelated per-step trace/screenshots")
        for artifact in [a for a in artifacts.values() if a.get("kind") == "installed_apk_readback"]:
            try:
                installed = read_json(contained(evidence_root, artifact["path"]))
                if (installed.get("device_serial") != serial or installed.get("package_name") != "com.dial.van"
                        or installed.get("apk_sha256") != bindings.get("apk_sha256")
                        or not str(installed.get("device_model", "")).startswith("SM-S928")
                        or installed.get("independent_observation") is not True
                        or installed.get("broker_run_id") != broker.get("run_id")):
                    raise ValueError()
            except (ValueError, KeyError, TypeError, OSError):
                errors.append("Installed APK/S24 Ultra identity readback missing or mismatched")
        assertions = r.get("assertions", [])
        if {a.get("id") for a in assertions} != set(case["required_assertions"]) or len(assertions) != len(case["required_assertions"]):
            errors.append("Missing, duplicated or unplanned assertion results")
        for assertion in assertions:
            if assertion.get("observed") is not True or not assertion.get("observation") or assertion.get("artifact_id") not in artifacts:
                errors.append("Assertion lacks observed evidence and a verified artifact reference")
            elif assertion.get("id") == "independent_postcondition" and artifacts[assertion["artifact_id"]].get("kind") not in (
                    {"local_device_readback"} if case.get("local_speaker_operation") else {"backend_readback", "service_readback"}):
                errors.append("Independent postcondition is not backed by the exact planned backend/service/local-device readback")
            elif assertion.get("id") == "exact_byte_effect" and artifacts[assertion["artifact_id"]].get("kind") != "byte_effect_readback":
                errors.append("Byte effect assertion is not backed by independent byte-effect readback")
        correlations = r.get("correlation", {})
        for kind in ("backend_readback", "hermes_receipt", "service_readback", "local_device_readback"):
            for artifact in [a for a in artifacts.values() if a.get("kind") == kind]:
                try:
                    body = read_json(contained(evidence_root, artifact["path"]))
                    if body.get("case_id") != case["id"] or body.get("broker_run_id") != broker.get("run_id") or body.get("apk_sha256") != bindings.get("apk_sha256"):
                        raise ValueError()
                    if body.get("repository_sha") != bindings.get("repository_sha") or body.get("inputs_sha256") != plan["inputs_sha256"]:
                        raise ValueError()
                    if body.get("correlation") != correlations or not correlations.get("record_id"):
                        raise ValueError()
                    if not body.get("source_receipt_ref"):
                        raise ValueError()
                    expected_producer = {"backend_readback": "gateway_readback", "hermes_receipt": "hermes_observer",
                                         "service_readback": "service_readback", "local_device_readback": "android_speaker_profile_readback"}[kind]
                    if body.get("independent_observation") is not True or body.get("producer") != expected_producer:
                        raise ValueError()
                    if body.get("outcome") not in {"VERIFIED_SUCCESS", "VERIFIED_READ", "VERIFIED_FAILURE", "VERIFIED_REFUSAL", "VERIFIED_NO_EFFECT", "VERIFIED_CANCELLED"}:
                        raise ValueError()
                    # Rejected actions can be valid error tests only after no-effect readback.
                    if body.get("outcome") not in case["expected_postcondition_outcomes"]:
                        raise ValueError()
                    if kind == "local_device_readback" and not local_speaker_readback_matches(case, body, serial, broker):
                        raise ValueError()
                except (ValueError, KeyError, TypeError, OSError):
                    errors.append(f"Uncorrelated/non-independent/pending {kind}")
        if case.get("byte_effect_operations"):
            proofs = [a for a in artifacts.values() if a.get("kind") == "byte_effect_readback"]
            try:
                if len(proofs) != 1:
                    raise ValueError()
                proof = read_json(contained(evidence_root, proofs[0]["path"]))
                identities = {"case_id": case["id"], "broker_run_id": broker.get("run_id"),
                              "apk_sha256": bindings.get("apk_sha256"), "repository_sha": bindings.get("repository_sha"),
                              "inputs_sha256": plan["inputs_sha256"], "producer": "browser_transfer_readback",
                              "independent_observation": True}
                if any(proof.get(name) != value or (type(value) is bool and type(proof.get(name)) is not bool)
                       for name, value in identities.items()) or not proof.get("source_receipt_ref"):
                    raise ValueError()
                if proof.get("correlation")!=correlations:
                    raise ValueError()
                expected_effects=correlations.get("byte_effects",{})
                if not isinstance(expected_effects,dict) or set(expected_effects)!=set(case["byte_effect_operations"]):
                    raise ValueError()
                records = proof.get("effects", [])
                if (not isinstance(records, list) or len(records) != len(case["byte_effect_operations"])
                        or sorted(record.get("operation", "") for record in records) != sorted(case["byte_effect_operations"])):
                    raise ValueError()
                for effect in records:
                    expected_identity=expected_effects.get(effect.get("operation"),{})
                    identity_fields=("session_id","target_id","transfer_id","producer_session_id","producer_epoch")
                    if (set(expected_identity)!=set(identity_fields)
                            or any(effect.get(name)!=expected_identity[name] or type(effect.get(name)) is not type(expected_identity[name]) for name in identity_fields)):
                        raise ValueError()
                    content = artifacts.get(effect.get("content_artifact_id"), {})
                    if content.get("kind") != "transfer_bytes":
                        raise ValueError()
                    data = contained(evidence_root, content["path"]).read_bytes()
                    actual_sha = hashlib.sha256(data).hexdigest()
                    if (effect.get("expected_sha256") != actual_sha or effect.get("observed_effect_sha256") != actual_sha
                            or type(effect.get("length_bytes")) is not int or effect["length_bytes"] != len(data)
                            or any(not isinstance(effect.get(name),str) or not effect[name].strip() for name in identity_fields[:-1])
                            or type(effect.get("producer_epoch")) is not int or effect["producer_epoch"] < 1
                            or effect.get("independent_observation") is not True or not effect.get("source_receipt_ref")):
                        raise ValueError()
                    if effect["operation"].startswith("CLIPBOARD_"):
                        if len(data) > 64 * 1024:
                            raise ValueError()
                        data.decode("utf-8", errors="strict")
                    if effect["operation"]=="PROVIDER_WRITE" and not provider_write_readback_matches(proof,effect,correlations,actual_sha,len(data)):
                        raise ValueError()
            except (ValueError, KeyError, TypeError, OSError, UnicodeError):
                errors.append("Missing or mismatched independently observed exact byte effect")
        results.append({"case_id": case["id"], "outcome": "FAIL" if errors else "CONSISTENT_IMPORTED_EVIDENCE", "reasons": errors})
    counts = {name: sum(r["outcome"] == name for r in results) for name in {r["outcome"] for r in results}}
    outcome = "FAIL" if problems or counts.get("FAIL") else "BLOCKED" if counts.get("BLOCKED") else "OUTCOME_UNKNOWN" if counts.get("OUTCOME_UNKNOWN") else "PARTIAL" if counts.get("PARTIAL") else "CONSISTENT_IMPORTED_EVIDENCE"
    return {"schema_version": 1, "outcome": outcome, "plan_sha256": plan["plan_sha256"], "coverage": plan["coverage"],
            "counts": counts, "problems": problems, "cases": results, "live_qualified": False,
            "producer_authenticity_verified": False, "known_partial_features": plan["known_partial_features"],
            "verification_scope": "Imported artifact integrity and receipt correlation only; current governed live reconciliation still required"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--device-transport", choices=[WIRELESS_ADB, USB_PRIVATE_BRIDGE], default=WIRELESS_ADB)
    prepare.add_argument("--source-manifest", type=Path)
    prepare.add_argument("--out", type=Path, required=True)
    invoke = sub.add_parser("call")
    invoke.add_argument("--plan", type=Path, required=True)
    invoke.add_argument("--case", required=True)
    invoke.add_argument("--device-serial", required=True)
    invoke.add_argument("--apk-path")
    invoke.add_argument("--out", type=Path, required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--plan", type=Path, required=True)
    validate.add_argument("--receipt", type=Path, required=True)
    validate.add_argument("--evidence-root", type=Path, required=True)
    validate.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        value = build_plan(device_transport=args.device_transport, source_manifest=args.source_manifest)
    elif args.action == "call":
        value = invocation(read_json(args.plan), args.case, device_serial=args.device_serial, apk_path=args.apk_path)
        value["execution_state"] = "PREPARED_TOOL_ARGUMENTS_NOT_EXECUTED"
    else:
        value = validate_evidence(read_json(args.plan), read_json(args.receipt), args.evidence_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps({"outcome": value.get("outcome", value.get("status", value.get("execution_state"))),
                      "coverage": value.get("coverage"), "output": str(args.out), "live_qualified": False}))
    return 2 if args.action == "validate" and value["outcome"] != "CONSISTENT_IMPORTED_EVIDENCE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
