from pathlib import Path
import json
import yaml
from tools.character_forge.gates import evaluate
from tools.character_forge.status import load_status, validate_status
from tools.character_forge.manifest import load_yaml, sha256_file, ROOT

def test_status_vocabulary_and_implications():
    status=load_status()
    assert validate_status(status)==[]
    manifest=load_yaml()
    assert manifest.get("baseline_sha")==status.get("baseline_sha")
    for section in ("core_rig","full_rig","production"):
        record=status.get(section) or {}
        if record.get("emulator_validation")=="PASS":
            assert record.get("ci_run"), f"{section} PASS without CI run"

def test_build_ready_never_precedes_m0():
    status=load_status()
    if status["build_ready"]: assert evaluate("m0").passed

def test_external_asset_state_is_honest_before_release():
    status=load_status()
    source=ROOT/"visual-authority"/"rive"/"van_runtime.riv"
    app=ROOT/"android"/"app"/"src"/"main"/"assets"/"van.riv"
    acceptance=ROOT/"docs"/"character_forge"/"ACCEPTANCE.yaml"
    checklist=ROOT/"docs"/"character_forge"/"DEVICE_CHECKLIST.yaml"
    release=ROOT/"visual-authority"/"rive"/"manifest.json"
    if status.get("rive_asset_ready"):
        assert source.is_file() and app.is_file()
        assert sha256_file(source)==sha256_file(app)
        assert any(a.get("sha256")==sha256_file(source) for a in load_yaml().get("artifacts",[]))
    if status.get("device_qualified"):
        data=yaml.safe_load(checklist.read_text(encoding="utf-8"))
        assert data.get("checks") and all(v=="PASS" for v in data["checks"].values())
    if status.get("owner_accepted"):
        data=yaml.safe_load(acceptance.read_text(encoding="utf-8"))
        assert data.get("final",{}).get("verified") is True
    if status["qual_emb_01"]=="READY":
        assert all(status.get(k) for k in ("rive_authored","rive_contract_ready","rive_runtime_ready","rive_asset_ready","device_qualified","owner_accepted"))
        assert release.is_file()
    else:
        assert status["qual_emb_01"]=="EXTERNAL_ARTEFACT"
