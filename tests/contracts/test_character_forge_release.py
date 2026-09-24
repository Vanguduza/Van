import json
from pathlib import Path
import yaml
from tools.character_forge.manifest import sha256_file
from tools.character_forge.status import load_status
ROOT=Path(__file__).resolve().parents[2]; SOURCE=ROOT/"visual-authority"/"rive"/"van_runtime.riv"; SHIPPED=ROOT/"android"/"app"/"src"/"main"/"assets"/"van.riv"; RELEASE=ROOT/"visual-authority"/"rive"/"manifest.json"; ACCEPTANCE=ROOT/"docs"/"character_forge"/"ACCEPTANCE.yaml"; CONTRACT=ROOT/"visual-authority"/"rive_contract.json"; IDENTITY=ROOT/"docs"/"VAN_CHARACTER_VISUAL_IDENTITY.md"; MATRIX=ROOT/"docs"/"VAN_VISUAL_ACCEPTANCE_MATRIX.md"; IDENTITY_LOCK=ROOT/"visual-authority"/"character-forge"/"00-source"/"asset-pack"/"APPROVED_IDENTITY_LOCK.yaml"

def test_shipped_asset_matches_source_when_present():
    if not SOURCE.exists() and not SHIPPED.exists(): return
    assert SOURCE.is_file() and SHIPPED.is_file()
    assert sha256_file(SOURCE)==sha256_file(SHIPPED)

def test_release_requires_acceptance_receipt():
    status=load_status()
    if not RELEASE.is_file():
        assert status["qual_emb_01"]!="READY"; return
    release=json.loads(RELEASE.read_text(encoding="utf-8")); acceptance=yaml.safe_load(ACCEPTANCE.read_text(encoding="utf-8"))["final"]
    assert acceptance["verified"] is True
    assert acceptance["subject"]=="sha256:"+release["rive_sha256"]
    assert sha256_file(SHIPPED)==release["rive_sha256"]

    assert acceptance["contract_sha256"]==sha256_file(CONTRACT)==release["contract_sha256"]
    assert acceptance["identity_spec_sha256"]==sha256_file(IDENTITY)==release["identity_spec_sha256"]
    assert acceptance["visual_acceptance_matrix_sha256"]==sha256_file(MATRIX)==release["visual_acceptance_matrix_sha256"]
    assert acceptance["identity_lock_sha256"]==sha256_file(IDENTITY_LOCK)==release["identity_lock_sha256"]
