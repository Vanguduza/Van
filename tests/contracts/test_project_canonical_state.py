from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "PROJECT_CANONICAL_STATE.json"


def load_state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def test_project_canonical_state_exists_and_names_repo():
    state = load_state()
    assert state["schema_version"] == 2
    assert state["repository"] == "Vanguduza/Van"
    assert state["canonical_state"]["canonical_integration_branch"] == "main"


def test_locked_authorities_exist():
    state = load_state()
    missing = [path for path in state["canonical_state"]["locked_authorities"] if not (ROOT / path).is_file()]
    assert not missing, f"Missing locked authorities: {missing}"


def test_required_bootstrap_ancestor_is_declared():
    state = load_state()
    required = state["canonical_state"]["required_ancestors"]
    assert required == ["66f6c6ef0d8cc2289dc7a851746194148405b10d"]
    assert all(len(sha) == 40 for sha in required)


def test_dev_release_remains_blocked():
    state = load_state()
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert version.endswith("-dev")
    assert state["canonical_state"]["release_blocked"] is True
