from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((ROOT / "visual-authority" / "rive_contract.json").read_text(encoding="utf-8"))


def test_rive_contract_input_names_locked():
    names = [i["name"] for i in CONTRACT["inputs"]]
    assert names == [
        "state",
        "speaking",
        "listening",
        "attention_x",
        "attention_y",
        "mouth_open",
        "urgency",
        "viseme",
        "action_code",
    ]


def test_durable_states_complete():
    expected = {
        "OFFLINE",
        "CONNECTING",
        "IDLE",
        "ATTENTIVE",
        "LISTENING",
        "THINKING",
        "SEARCHING",
        "WORKING",
        "DELEGATING",
        "SPEAKING",
        "WAITING",
        "WAITING_FOR_OWNER",
        "DEGRADED",
        "WARNING",
        "ERROR",
        "SUCCESS",
        "URGENT",
        "SLEEPING",
    }
    assert set(CONTRACT["durable_states"]) == expected


def test_finite_actions_complete():
    expected = {
        "HELLO_WAVE",
        "ACK_NOD",
        "POINT_LEFT",
        "POINT_RIGHT",
        "POINT_UP",
        "POINT_DOWN",
        "POINT_TARGET",
        "CELEBRATE",
        "CAUTION",
        "CONFIRM",
        "SHRUG",
        "PRESENT_CARD",
        "OPEN_PANEL",
        "CLOSE_PANEL",
    }
    assert set(CONTRACT["finite_actions"]) == expected


def test_identity_forbids_dark_hair_and_robot():
    forbid = set(CONTRACT["identity_lock"]["forbid"])
    assert "dark_hair" in forbid
    assert "generic_robot" in forbid


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_character_forge_asset_hash_contract_when_present():
    manifest_path = ROOT / "docs" / "character_forge" / "MANIFEST.yaml"
    source = ROOT / "visual-authority" / "rive" / "van_runtime.riv"
    shipped = ROOT / "android" / "app" / "src" / "main" / "assets" / "van.riv"
    sha_file = ROOT / "visual-authority" / "rive" / "van_runtime.sha256"

    if source.exists():
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        source_sha = _sha256(source)
        assert any(
            artifact.get("sha256") == source_sha and artifact.get("kind") == "riv_accepted"
            for artifact in manifest.get("artifacts", [])
        )
        assert sha_file.is_file()
        assert sha_file.read_text(encoding="utf-8").strip() == source_sha

    if shipped.exists():
        assert source.is_file()
        assert _sha256(shipped) == _sha256(source)
