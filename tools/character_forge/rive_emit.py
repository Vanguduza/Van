from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .rig_ir import require_valid_rig_ir


def build_rive_authoring_plan(rig: dict[str, Any]) -> dict[str, Any]:
    """Create a deterministic, version-neutral authoring plan.

    Exact RML object names are intentionally not guessed here. The VM-side adapter must query
    `rive schema --json` for the pinned CLI and bind this plan to the discovered schema before
    writing scene.rml. Unsupported objects fail closed.
    """
    require_valid_rig_ir(rig)
    return {
        "schema_version": 1,
        "artboard": "Van",
        "state_machine": "VanRuntime",
        "source_master_sha256": rig["source_master_sha256"],
        "steps": [
            {"op": "create_bone", "payload": bone} for bone in rig["bones"]
        ] + [
            {"op": "create_mesh", "payload": mesh} for mesh in rig["meshes"]
        ] + [
            {"op": "set_draw_order", "parts": rig["draw_order"]},
            {"op": "create_constraints", "items": rig["constraints"]},
            {"op": "bind_public_contract", "path": "visual-authority/rive_contract.json"},
        ],
        "forbidden": ["aura", "halo", "body_field", "full_concentric_ring"],
        "unsupported_policy": "FAIL_CLOSED",
    }


def write_rive_authoring_plan(rig: dict[str, Any], output: Path) -> dict[str, Any]:
    plan = build_rive_authoring_plan(rig)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return plan
