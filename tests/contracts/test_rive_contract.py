from __future__ import annotations

import json
from pathlib import Path


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
