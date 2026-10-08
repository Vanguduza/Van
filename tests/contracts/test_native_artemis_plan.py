"""Native preparation uses actual MCP schema shape; fixtures confer no live authority."""
import asyncio
import copy
from pathlib import Path
from datetime import datetime, timezone, timedelta
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

def test_native_wireless_is_default_without_windows_or_dds(schema):
    p = a.build_plan(dds_root=Path("/nonexistent"), native_schema=schema)
    assert p["target"]["device_transport"] == a.WIRELESS_ADB
    assert p["status"] == "NATIVE_PLAN_PREPARED_NOT_EXECUTED"
    assert p["physical_cases_executed"] == 0
    assert p["coverage"]["cases"] == 826
    assert p["target"]["hermes"] == "van-trading-core"
    assert p["target"]["artemis"] == "dial-control"
    assert p["governed_schema_sources"] == []
    assert not p["dds_readiness_required"]
    assert "Windows" not in str(p["prerequisites"])
    assert "USB" not in str(p["prerequisites"])
    assert "pairing" in str(p["prerequisites"])
    assert p["transport_adaptation"]["verified_applicable_cases"] == 0

@pytest.fixture(scope="module")
def wireless_plan(schema):
    return a.build_plan(dds_root=Path("/nonexistent"), native_schema=schema)

def wireless_readbacks(serial="10.66.66.2:37123"):
    # Synthetic unit fixture: neither paired nor measured on a real handset.
    return {"record_kind": "NATIVE_WIRELESS_ADB_IDENTITY_READBACK",
            "device_transport": a.WIRELESS_ADB, "adb_serial": serial,
            "authentication": "ANDROID_WIRELESS_DEBUGGING_TLS_PAIRED",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "reads": [{"argv": ["adb", "-s", serial, *suffix], "exit_code": 0, "stdout": value + "\n"}
                      for suffix, value in [(["get-state"], "device"),
                                            (["shell", "getprop", "ro.serialno"], "RFCX2054F5W"),
                                            (["shell", "getprop", "ro.product.model"], "SM-S928B")]]}

@pytest.mark.parametrize("serial", ["10.66.66.2:37123", "127.0.0.1:37123"])
def test_wireless_uses_transport_address_and_binds_separate_physical_identity(wireless_plan, schema, serial):
    call = a.native_invocation(wireless_plan, "OF-HOME-001:happy", device_serial=serial,
                               native_schema=schema, device_binding=wireless_readbacks(serial))
    assert call["arguments"]["device_serial"] == serial
    assert call["transport_binding"]["physical_serial"] == "RFCX2054F5W"
    assert call["transport_binding"]["device_model"] == "SM-S928B"
    assert call["transport_binding"]["requires_live_device_recheck"] is True
    assert call["transport_binding"]["producer_authenticity_verified"] is False
    assert call["execution_state"] == "PREPARED_NATIVE_ARGUMENTS_NOT_EXECUTED"
    assert call["live_qualified"] is False

@pytest.mark.parametrize("change", ["missing", "public", "physical_serial", "model", "offline",
                                   "expired", "future", "naive", "auth", "serial", "failed", "duplicate"])
def test_wireless_unpaired_public_stale_or_wrong_hardware_refused(wireless_plan, schema, change):
    serial = "10.66.66.2:37123"
    b = wireless_readbacks(serial)
    if change == "missing": b = None
    elif change == "public":
        serial = "8.8.8.8:37123"; b = wireless_readbacks(serial)
    elif change == "physical_serial": b["reads"][1]["stdout"] = "OTHER"
    elif change == "model": b["reads"][2]["stdout"] = "OTHER"
    elif change == "offline": b["reads"][0]["stdout"] = "unauthorized"
    elif change == "expired": b["observed_at"] = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
    elif change == "future": b["observed_at"] = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    elif change == "naive": b["observed_at"] = datetime.now().isoformat()
    elif change == "auth": b["authentication"] = "LEGACY_PLAINTEXT_ADB"
    elif change == "serial": serial = "10.66.66.2:37124"
    elif change == "failed": b["reads"][0]["exit_code"] = 1
    elif change == "duplicate": b["reads"].append(copy.deepcopy(b["reads"][1]))
    with pytest.raises(ValueError):
        a.native_invocation(wireless_plan, "OF-HOME-001:happy", device_serial=serial,
                            native_schema=schema, device_binding=b)


@pytest.mark.parametrize("stdout", [None, 1, True, [], {}])
def test_wireless_malformed_stdout_has_explicit_refusal(wireless_plan, schema, stdout):
    serial = "10.66.66.2:37123"
    b = wireless_readbacks(serial)
    b["reads"][1]["stdout"] = stdout
    with pytest.raises(ValueError, match="physical handset identity"):
        a.native_invocation(wireless_plan, "OF-HOME-001:happy", device_serial=serial,
                            native_schema=schema, device_binding=b)
