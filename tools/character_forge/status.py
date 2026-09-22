from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STATUS_PATH = ROOT / "docs" / "character_forge" / "STATUS.json"
STAGES = ("admission", "vector", "core_rig", "full_rig", "integrated", "certified", "released")
VALIDATION = ("NOT_RUN", "PASS", "FAIL")
CORE_VERDICTS = ("NONE", "PASS", "REVISE", "REJECT")
REVIEWS = ("NONE", "PASS", "FAIL")

def load_status(path: Path = STATUS_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("STATUS.json must contain an object")
    return data

def save_status(data: dict[str, Any], path: Path = STATUS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)

def validate_status(data: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if data.get("current_stage") not in STAGES: problems.append("current_stage is invalid")
    if (data.get("core_rig") or {}).get("emulator_validation") not in VALIDATION: problems.append("core_rig.emulator_validation is invalid")
    if (data.get("core_rig") or {}).get("owner_verdict") not in CORE_VERDICTS: problems.append("core_rig.owner_verdict is invalid")
    if (data.get("full_rig") or {}).get("emulator_validation") not in VALIDATION: problems.append("full_rig.emulator_validation is invalid")
    if (data.get("full_rig") or {}).get("reviewed") not in REVIEWS: problems.append("full_rig.reviewed is invalid")
    if data.get("qual_emb_01") not in ("EXTERNAL_ARTEFACT", "READY"): problems.append("qual_emb_01 is invalid")
    if data.get("owner_accepted") and not data.get("rive_asset_ready"): problems.append("owner_accepted implies rive_asset_ready")
    if data.get("device_qualified") and not data.get("rive_asset_ready"): problems.append("device_qualified implies rive_asset_ready")
    if data.get("qual_emb_01") == "READY":
        for key in ("rive_authored", "rive_contract_ready", "rive_runtime_ready", "rive_asset_ready", "device_qualified", "owner_accepted"):
            if not data.get(key): problems.append(f"qual_emb_01 READY requires {key}")
    return problems
