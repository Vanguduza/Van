from __future__ import annotations

import json
from pathlib import Path

import yaml

from .manifest import ROOT, sha256_file
from .svg_lint import COLOR_GROUPS, REQUIRED_GROUPS

PACK = ROOT / "visual-authority" / "character-forge" / "00-source" / "asset-pack"
V3 = ROOT / "visual-authority" / "character-forge" / "00-source" / "production-v3"
CANONICAL_BLOB_SHA = "fc18bbe0b91e5b85d8cf8211314a69cb90b8bc0b"


def _yaml(name: str):
    return yaml.safe_load((PACK / name).read_text(encoding="utf-8"))


def validate() -> list[str]:
    problems: list[str] = []
    contract = json.loads((ROOT / "visual-authority" / "rive_contract.json").read_text(encoding="utf-8"))
    identity = _yaml("APPROVED_IDENTITY_LOCK.yaml")
    manifest = _yaml("ASSET_PACK_MANIFEST.yaml")
    layers = _yaml("LAYER_SPEC.yaml")
    rig = _yaml("RIG_SPEC.yaml")
    matrix = _yaml("STATE_ACTION_MATRIX.yaml")
    aura = _yaml("AURA_HANDOFF_SPEC.yaml")
    deny = _yaml("LEGACY_ASSET_DENYLIST.yaml")
    master_policy = yaml.safe_load((V3 / "MASTER_PROVENANCE.yaml").read_text(encoding="utf-8"))
    master_spec = yaml.safe_load((V3 / "HIGHRES_MASTER_SPEC.yaml").read_text(encoding="utf-8"))
    topology = yaml.safe_load((V3 / "TOPOLOGY_BUDGETS.yaml").read_text(encoding="utf-8"))
    gpu_lane = yaml.safe_load((V3 / "GPU_LANE.yaml").read_text(encoding="utf-8"))
    artwork_manifest_path = V3 / "ARTWORK_MANIFEST.yaml"
    provenance_graph_path = V3 / "PROVENANCE_GRAPH.yaml"
    artwork_manifest = yaml.safe_load(artwork_manifest_path.read_text(encoding="utf-8")) if artwork_manifest_path.is_file() else {}
    provenance_graph = yaml.safe_load(provenance_graph_path.read_text(encoding="utf-8")) if provenance_graph_path.is_file() else {}

    primary = manifest["authority"]["primary_visual"]["path"]
    if primary != "visual-authority/assets/pack/owner_board_visual_authority.png":
        problems.append("PRIMARY_VISUAL_DRIFT")
    if not (ROOT / primary).is_file():
        problems.append("PRIMARY_VISUAL_MISSING")
    if manifest["authority"]["primary_visual"].get("git_blob_sha") != CANONICAL_BLOB_SHA:
        problems.append("PRIMARY_VISUAL_BLOB_DRIFT")

    if rig["artboard"] != contract["artboard"]:
        problems.append("ARTBOARD_DRIFT")
    if rig["state_machine"] != contract["state_machine"]:
        problems.append("STATE_MACHINE_DRIFT")
    if rig["public_surface"]["inputs"] != contract["inputs"]:
        problems.append("PUBLIC_INPUT_DRIFT")
    if rig["public_surface"]["triggers"] != contract["triggers"]:
        problems.append("TRIGGER_DRIFT")

    state_codes = {name: row["code"] for name, row in matrix["states"].items()}
    action_codes = {name: row["code"] for name, row in matrix["actions"].items()}
    if state_codes != contract["durable_states"]:
        problems.append("STATE_CODE_DRIFT")
    if action_codes != contract["finite_actions"]:
        problems.append("ACTION_CODE_DRIFT")

    if tuple(layers["required_root_groups"]) != REQUIRED_GROUPS:
        problems.append("SVG_GROUP_DRIFT")
    if COLOR_GROUPS.get("hand_l") != "neutral" or COLOR_GROUPS.get("hand_r") != "neutral":
        problems.append("GLOVE_LINTER_DRIFT")
    if layers["identity_roles"]["hand_l"] != "black_technical_glove":
        problems.append("LEFT_GLOVE_DRIFT")
    if layers["identity_roles"]["hand_r"] != "black_technical_glove":
        problems.append("RIGHT_GLOVE_DRIFT")
    forbidden_groups = set(layers.get("explicitly_forbidden_groups") or [])
    if "headband" not in forbidden_groups or "extra_headband" not in forbidden_groups:
        problems.append("HEADBAND_NOT_FORBIDDEN")

    lock = contract["identity_lock"]
    expected = identity["identity"]
    checks = {
        "hair": expected["hair"]["form"],
        "skin": expected["skin"]["family"],
        "eyes": "blue",
        "visor": expected["visor"]["family"],
        "jacket": expected["clothing"]["jacket"],
        "underlayer": "charcoal_technical",
        "accents": "dial_cyan",
        "companion": expected["companion"]["type"],
    }
    for key, value in checks.items():
        if lock.get(key) != value:
            problems.append(f"IDENTITY_CONTRACT_DRIFT:{key}")
    if lock.get("headband") != "forbidden":
        problems.append("HEADBAND_CONTRACT_DRIFT")
    if lock.get("gloves") != "black_technical":
        problems.append("GLOVE_CONTRACT_DRIFT")
    if lock.get("skin_token") != "#B8853C" or expected["skin"].get("canonical_token") != "#B8853C":
        problems.append("SKIN_TOKEN_DRIFT")

    if int(manifest.get("schema_version") or 0) < 3:
        problems.append("ASSET_PACK_SCHEMA_NOT_V3")
    v3 = manifest.get("production_v3") or {}
    for rel in (
        "visual-authority/character-forge/00-source/production-v3/MASTER_PROVENANCE.yaml",
        "visual-authority/character-forge/00-source/production-v3/HIGHRES_MASTER_SPEC.yaml",
        "visual-authority/character-forge/00-source/production-v3/SEE_THROUGH_LAYER_MAP.yaml",
        "visual-authority/character-forge/00-source/production-v3/TOPOLOGY_BUDGETS.yaml",
        "visual-authority/character-forge/00-source/production-v3/RIG_IR_SCHEMA.json",
        "visual-authority/character-forge/00-source/production-v3/RIVE_MAPPING.yaml",
        "visual-authority/character-forge/00-source/production-v3/GPU_LANE.yaml",
        "visual-authority/character-forge/00-source/production-v3/ARTWORK_MANIFEST.yaml",
        "visual-authority/character-forge/00-source/production-v3/PROVENANCE_GRAPH.yaml",
    ):
        if not (ROOT / rel).is_file():
            problems.append(f"V3_AUTHORITY_MISSING:{rel}")
    if (master_policy.get("source_authority") or {}).get("git_blob_sha") != CANONICAL_BLOB_SHA:
        problems.append("MASTER_SOURCE_BLOB_DRIFT")
    if (master_policy.get("source_authority") or {}).get("declared_skin_token") != "#B8853C":
        problems.append("MASTER_SKIN_TOKEN_DRIFT")
    if ((master_spec.get("identity") or {}).get("skin_token")) != "#B8853C":
        problems.append("HIGHRES_SPEC_SKIN_TOKEN_DRIFT")
    if int(((topology.get("policy") or {}).get("hard_total_paths")) or 0) != 1200:
        problems.append("TOPOLOGY_HARD_CEILING_DRIFT")
    if ((gpu_lane.get("gpu_worker") or {}).get("source_tool") or {}).get("commit") != "7f139bb25c46a0c8ac720d95ddab185fcda5451c":
        problems.append("SEE_THROUGH_PIN_DRIFT")
    if (gpu_lane.get("stretchy_studio") or {}).get("commit") != "24a83a27ba43e43e9d2e3de5e33994594e6199c2":
        problems.append("STRETCHY_PIN_DRIFT")
    reference = master_policy.get("exact_derived_reference") or {}
    reference_path = ROOT / str(reference.get("path") or "")
    receipt_path = ROOT / str(reference.get("receipt") or "")
    if not reference_path.is_file() or sha256_file(reference_path) != reference.get("sha256"):
        problems.append("EXACT_REFERENCE_HASH_DRIFT")
    if not receipt_path.is_file():
        problems.append("EXACT_REFERENCE_RECEIPT_MISSING")
    else:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("output_sha256") != reference.get("sha256"):
            problems.append("EXACT_REFERENCE_RECEIPT_OUTPUT_DRIFT")
        if receipt.get("source_git_blob_sha") != CANONICAL_BLOB_SHA:
            problems.append("EXACT_REFERENCE_RECEIPT_SOURCE_DRIFT")
        if receipt.get("source_sha256") != sha256_file(ROOT / primary):
            problems.append("EXACT_REFERENCE_SOURCE_HASH_DRIFT")
        if receipt.get("adds_new_identity_detail") is not False:
            problems.append("EXACT_REFERENCE_INVENTION_FLAG_DRIFT")

    approved_path = ROOT / "visual-authority" / "character-forge" / "01-master-approved" / "van_master_highres.png"
    approved = master_policy.get("approved_master") or {}
    if approved_path.exists() and (not approved.get("sha256") or approved.get("status") != "OWNER_APPROVED"):
        problems.append("APPROVED_MASTER_PRESENT_WITHOUT_BOUND_AUTHORITY")
    if approved.get("status") != "OWNER_APPROVED":
        problems.append("APPROVED_MASTER_STATUS_DRIFT")
    if not approved_path.is_file():
        problems.append("APPROVED_MASTER_MISSING")
    elif sha256_file(approved_path) != approved.get("sha256"):
        problems.append("APPROVED_MASTER_HASH_DRIFT")

    approval_path = ROOT / str(approved.get("approval_record") or "")
    if not approval_path.is_file():
        problems.append("APPROVED_MASTER_APPROVAL_MISSING")
    else:
        approval = yaml.safe_load(approval_path.read_text(encoding="utf-8")) or {}
        if approval.get("decision") != "APPROVE" or approval.get("authority") != "owner":
            problems.append("APPROVED_MASTER_OWNER_DECISION_DRIFT")
        if approval.get("candidate_sha256") != approved.get("sha256"):
            problems.append("APPROVED_MASTER_APPROVAL_HASH_DRIFT")
        if approval.get("canonical_source_git_blob_sha") != CANONICAL_BLOB_SHA:
            problems.append("APPROVED_MASTER_APPROVAL_SOURCE_DRIFT")
        if approval.get("identity_lock_sha256") != sha256_file(PACK / "APPROVED_IDENTITY_LOCK.yaml"):
            problems.append("APPROVED_MASTER_APPROVAL_IDENTITY_LOCK_DRIFT")

    if manifest.get("status") != "PRODUCTION_V3_ARTWORK_HASH_LOCKED_PRE_M1":
        problems.append("ASSET_PACK_STATUS_DRIFT")
    artwork_cfg = (manifest.get("production_v3") or {}).get("artwork") or {}
    if artwork_cfg.get("manifest") != "visual-authority/character-forge/00-source/production-v3/ARTWORK_MANIFEST.yaml":
        problems.append("ARTWORK_MANIFEST_REFERENCE_DRIFT")
    if artwork_cfg.get("provenance_graph") != "visual-authority/character-forge/00-source/production-v3/PROVENANCE_GRAPH.yaml":
        problems.append("PROVENANCE_GRAPH_REFERENCE_DRIFT")

    if not artwork_manifest:
        problems.append("ARTWORK_MANIFEST_MISSING")
    else:
        selected = artwork_manifest.get("selected_master") or {}
        if selected.get("sha256") != approved.get("sha256"):
            problems.append("ARTWORK_SELECTED_MASTER_HASH_DRIFT")
        if selected.get("path") != "visual-authority/character-forge/01-master-approved/van_master_highres.png":
            problems.append("ARTWORK_SELECTED_MASTER_PATH_DRIFT")
        seen_ids = set()
        for row in artwork_manifest.get("assets") or []:
            asset_id = str(row.get("id") or "")
            if not asset_id:
                problems.append("ARTWORK_ASSET_ID_MISSING")
                continue
            if asset_id in seen_ids:
                problems.append(f"ARTWORK_DUPLICATE_ID:{asset_id}")
            seen_ids.add(asset_id)
            rel = str(row.get("path") or "")
            path = ROOT / rel
            if not path.is_file():
                problems.append(f"ARTWORK_MISSING:{asset_id}")
                continue
            expected_sha = str(row.get("sha256") or "")
            if not expected_sha or sha256_file(path) != expected_sha:
                problems.append(f"ARTWORK_HASH_DRIFT:{asset_id}")
        required_refs = {
            "expression_reference",
            "viseme_reference",
            "glove_gesture_reference",
            "state_action_reference",
            "aura_reference",
        }
        if not required_refs.issubset(seen_ids):
            problems.append("ARTWORK_SUPPORTING_SET_INCOMPLETE")
        for row in artwork_manifest.get("assets") or []:
            if row.get("id") in required_refs:
                if row.get("admission_class") != "GENERATIVE_REFERENCE_ONLY":
                    problems.append(f"ARTWORK_REFERENCE_CLASS_DRIFT:{row.get('id')}")
                if row.get("identity_authority") is not False:
                    problems.append(f"ARTWORK_REFERENCE_IDENTITY_AUTHORITY_DRIFT:{row.get('id')}")

    if not provenance_graph:
        problems.append("PROVENANCE_GRAPH_MISSING")
    else:
        nodes = provenance_graph.get("nodes") or {}
        approved_node = nodes.get("approved_master") or {}
        if approved_node.get("sha256") != approved.get("sha256"):
            problems.append("PROVENANCE_APPROVED_MASTER_HASH_DRIFT")
        if "approved_master_is_the_only_high_resolution_rigging_geometry_authority" not in set(provenance_graph.get("invariants") or []):
            problems.append("PROVENANCE_MASTER_AUTHORITY_INVARIANT_MISSING")
        for node_name in ("expression_reference","viseme_reference","glove_reference","state_action_reference","aura_reference"):
            if (nodes.get(node_name) or {}).get("type") != "SUPPORTING_REFERENCE_ONLY":
                problems.append(f"PROVENANCE_REFERENCE_TYPE_DRIFT:{node_name}")

    if rig["artboard_policy"]["aura_in_rive_forbidden"] is not True:
        problems.append("RIVE_AURA_BOUNDARY_DRIFT")
    if aura["ownership"] != "ANDROID_NATIVE":
        problems.append("AURA_OWNERSHIP_DRIFT")

    for rel in deny["paths"]:
        if (ROOT / rel).exists():
            problems.append(f"DENYLISTED_ASSET_PRESENT:{rel}")

    serialized = yaml.safe_dump(manifest, sort_keys=False)
    for token in ("owner_visual_lock_sheet.jpg", "visual-authority/assets/derived/", "visual-authority/assets/turnaround.png"):
        if token in serialized:
            problems.append(f"LEGACY_SOURCE_REFERENCED:{token}")

    return sorted(set(problems))


def main() -> int:
    problems = validate()
    if problems:
        for item in problems:
            print(f"FAIL {item}")
        return 1
    print("APPROVED_ASSET_PACK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
