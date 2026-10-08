"""Native preparation uses actual MCP schema shape; fixtures confer no live authority."""
import asyncio
import copy
from pathlib import Path
import pytest
from tools.certification import artemis_acceptance as a

ROOT = Path(__file__).resolve().parents[2]
@pytest.fixture(scope="module")
def schema():
    fields = {"task_desc", "device_serial", "model", "locked_app_package", "verification_level", "expected_output_desc"}
    tools = {n: {} for n in ("mobile_manage_task", "mobile_inspect_trace", "mobile_get_device_state", "mobile_diagnose")}
    tools["mobile_run_task"] = {"properties": {n: {"type": "string"} for n in fields}, "required": ["task_desc"]}
    return {"record_kind": "NATIVE_ARTEMIS_SCHEMA_DISCOVERY", "route": "NATIVE_ARTEMIS_MCP_DIRECT_COMMANDER",
            "root": "/unit/native-artemis-not-live", "tools": tools}
@pytest.fixture(scope="module")
def plan(schema):
    return a.build_plan(dds_root=Path("/nonexistent-dds-not-required"),
                        device_transport=a.USB_PRIVATE_BRIDGE, native_schema=schema)

def test_native_matrix_needs_no_dds_tree_and_keeps_real_evidence_requirements(plan):
    assert plan["coverage"]["cases"] == 826
    assert plan["target"]["hermes"] == "van-trading-core"
    assert plan["target"]["artemis"] == "dial-control"
    assert plan["target"]["device_serial"] == "RFCX2054F5W"
    assert not plan["governed_schema_sources"]
    assert plan["dds_readiness_required"] is False
    assert plan["physical_cases_executed"] == 0
    assert plan["transport_adaptation"]["verified_applicable_cases"] == 0
    provider = next(c for c in plan["cases"] if c["id"] == "CC-PROVIDER-UNKNOWN")
    assert "unknown" in str(provider).lower()
    speaker = next(c for c in plan["cases"] if c.get("local_speaker_operation"))
    assert "local_device_readback" in speaker["required_artifact_kinds"]
    assert "Owner" in str(plan["prerequisites"]) or "owner" in str(plan["prerequisites"])

def test_representative_native_cases_match_schema_and_exact_device(plan, schema):
    representatives = {}
    for c in plan["cases"]:
        representatives.setdefault((c["kind"], c["state"]), c)
    for c in representatives.values():
        if c["execution_readiness"] == "MISSING_FRONTEND":
            continue
        call = a.native_invocation(plan, c["id"], device_serial="RFCX2054F5W", native_schema=schema)
        assert call["tool"] == "mobile_run_task"
        assert set(call["arguments"]) <= schema["tools"]["mobile_run_task"]["properties"].keys()
        assert call["arguments"]["model"] == "Pro"
        assert call["arguments"]["verification_level"] == "strict"
        assert call["arguments"]["locked_app_package"] == "com.dial.van"
        assert call["execution_state"] == "PREPARED_NATIVE_ARGUMENTS_NOT_EXECUTED"
        assert call["live_qualified"] is False
        assert "Hermes/Artemis authority" not in call["arguments"]["task_desc"]

@pytest.mark.parametrize("change", ["hash", "serial", "schema", "root", "case", "missing"])
def test_native_drift_and_missing_controls_refused(plan, schema, change):
    p, s = copy.deepcopy(plan), copy.deepcopy(schema)
    serial, case = "RFCX2054F5W", "OF-HOME-001:happy"
    if change == "hash": p["target"]["backend"] = "other"
    elif change == "serial": serial = "OTHER"
    elif change == "schema": s["tools"]["mobile_run_task"]["properties"].pop("model")
    elif change == "root": s["root"] = "/other"
    elif change == "case": case = "invented"
    else:
        next(c for c in p["cases"] if c["id"] == case)["execution_readiness"] = "MISSING_FRONTEND"
        p.pop("plan_sha256");p["plan_sha256"] = a.digest(p)
    with pytest.raises(ValueError):
        a.native_invocation(p, case, device_serial=serial, native_schema=s)

def test_legacy_dispatch_and_import_cannot_interpret_native_plan(plan):
    with pytest.raises(ValueError, match="Native"):
        a.invocation(plan, "OF-HOME-001:happy", device_serial="RFCX2054F5W")
    with pytest.raises(ValueError, match="Native"):
        asyncio.run(a.run_case(None, plan, "OF-HOME-001:happy", {}))
    with pytest.raises(ValueError, match="Native"):
        a.validate_evidence(plan, {}, Path("/nonexistent"))

def test_fabricated_or_incompatible_schema_discovery_refused(schema):
    for s in ({}, {**schema, "route": "HERMES"}, {**schema, "tools": {}}):
        with pytest.raises(ValueError):
            a.build_plan(dds_root=Path("/nonexistent"), device_transport=a.USB_PRIVATE_BRIDGE, native_schema=s)

@pytest.mark.parametrize("root", [None, "", "relative", "/a/../b"])
def test_native_runtime_root_must_be_explicit_absolute(schema, root):
    with pytest.raises(ValueError, match="runtime root"):
        a.build_plan(dds_root=Path("/nonexistent"), device_transport=a.USB_PRIVATE_BRIDGE,
                     native_schema={**schema, "root": root})

def test_native_wireless_cannot_claim_the_owner_usb_route(schema):
    with pytest.raises(ValueError, match="USB_PRIVATE_BRIDGE"):
        a.build_plan(dds_root=Path("/nonexistent"), native_schema=schema)
