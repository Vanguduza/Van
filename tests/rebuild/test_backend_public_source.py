"""Exercise the qualification instrument, not application acceptance cases."""
import copy
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("backend_public_source_gate", ROOT / "tools/rebuild/backend_public_source.py")
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


@pytest.fixture
def instrument(tmp_path):
    manifest = GATE.plan()
    for group in ("gateway", "media"):
        suite = ET.Element("testsuite")
        for row in manifest["selected"]:
            if GATE.runtime(row["path"]) == group:
                ET.SubElement(suite, "testcase", classname=row["path"].removesuffix(".py").replace("/", "."),
                              name="synthetic_instrument_fixture_not_application_execution")
        (tmp_path / (group + "-report.xml")).write_bytes(ET.tostring(suite))
        (tmp_path / (group + "-storage-audit.json")).write_text(json.dumps({"forbidden_events": []}))
    return manifest, tmp_path


def judge(manifest, folder):
    return GATE.verify(manifest, folder / "report.xml", folder / "storage-audit.json")


def test_both_runtime_instruments_cover_the_actual_selection(instrument):
    manifest, folder = instrument
    result = judge(manifest, folder)
    assert result["passed"] == len(manifest["selected"])
    assert set(result["isolated_runtimes"]) == {"gateway", "media"}
    assert result["certificates_issued"] == []


@pytest.mark.parametrize("damage", ["drop-selection", "change-separate", "source-hash", "failure", "error",
    "unexpected-skip", "missing-module", "foreign-case", "wrong-skip-module", "source-write",
    "missing-media-report", "wrong-runtime"])
def test_instrument_rejects_induced_missing_or_false_evidence(instrument, damage):
    manifest, folder = instrument
    manifest = copy.deepcopy(manifest)
    report = folder / "gateway-report.xml"
    suite = ET.parse(report).getroot()
    if damage == "drop-selection":
        manifest["selected"].pop()
    elif damage == "change-separate":
        manifest["separate"][0]["reason"] = "pretend-qualified"
    elif damage == "source-hash":
        manifest["selected"][0]["sha256"] = "0" * 64
    elif damage in {"failure", "error", "unexpected-skip", "wrong-skip-module"}:
        kind = "skipped" if "skip" in damage else damage
        reason = "member of the B1 closed set by definition" if damage == "wrong-skip-module" else "unexplained"
        ET.SubElement(suite[0], kind, message=reason)
        report.write_bytes(ET.tostring(suite))
    elif damage == "missing-module":
        suite.remove(suite[0])
        report.write_bytes(ET.tostring(suite))
    elif damage in {"foreign-case", "wrong-runtime"}:
        module = "outside.selected.scope" if damage == "foreign-case" else next(
            r["path"].removesuffix(".py").replace("/", ".") for r in manifest["selected"] if GATE.runtime(r["path"]) == "media")
        ET.SubElement(suite, "testcase", classname=module, name="false-count")
        report.write_bytes(ET.tostring(suite))
    elif damage == "source-write":
        (folder / "gateway-storage-audit.json").write_text(json.dumps({"forbidden_events": ["fixture-write"]}))
    elif damage == "missing-media-report":
        (folder / "media-report.xml").unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        judge(manifest, folder)


def test_exact_prerequisite_skip_is_disclosed_without_claiming_it_executed(instrument):
    manifest, folder = instrument
    report = folder / "gateway-report.xml"
    suite = ET.parse(report).getroot()
    case = next(c for c in suite if c.get("classname") == "backend.tests.test_jev_no_generic_executor")
    case.set('name', 'test_no_fabric_or_generic_operation_survives_the_b1_validator[click]')
    ET.SubElement(case, "skipped", message="member of the B1 closed set by definition")
    report.write_bytes(ET.tostring(suite))
    result = judge(manifest, folder)
    assert result["passed"] == len(manifest["selected"]) - 1
    assert len(result["declared_unexecuted"]) == 1


@pytest.mark.parametrize('wrong_case', [False, True])
def test_android_guard_skip_is_disclosed_only_for_its_exact_separate_case(instrument, wrong_case):
    manifest, folder = instrument
    report = folder / 'gateway-report.xml'; suite = ET.parse(report).getroot()
    case = next(c for c in suite if c.get('classname') == 'tests.contracts.test_android_instrumentation_abi')
    case.set('name', 'unrelated_case' if wrong_case else 'test_actual_agp_direct_package_release_refuses_missing_core_deployment_profile')
    ET.SubElement(case, 'skipped', message='opt-in actual AGP release guard check')
    report.write_bytes(ET.tostring(suite))
    if wrong_case:
        with pytest.raises(ValueError): judge(manifest, folder)
    else:
        assert len(judge(manifest, folder)['declared_unexecuted']) == 1
