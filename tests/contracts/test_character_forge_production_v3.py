from __future__ import annotations

from pathlib import Path
import json
import struct
import subprocess
import yaml

from tools.character_forge import master as master_module
from tools.character_forge.master import png_dimensions, stage_master, approve_master
from tools.character_forge.provenance import classify_layer, production_admissible
from tools.character_forge.rig_ir import validate_rig_ir
from tools.character_forge.spine_import import import_spine_json
from tools.character_forge.svg_lint import REQUIRED_GROUPS, lint_svg
from tools.character_forge.layer_map import map_layer_names
from tools.character_forge.gpu_jobs import build_see_through_job, canonical_job_sha256


ROOT = Path(__file__).resolve().parents[2]


def _minimal_rig(provenance="DERIVED_VISIBLE"):
    return {
        "schema_version": 1,
        "source_master_sha256": "a" * 64,
        "toolchain": {},
        "bones": [
            {"id":"root","name":"root","parent":None,"x":0.0,"y":0.0,"rotation":0.0,"scale_x":1.0,"scale_y":1.0}
        ],
        "meshes": [
            {
                "part":"face",
                "vertices":[[0.0,0.0],[1.0,0.0],[0.0,1.0]],
                "triangles":[[0,1,2]],
                "weights":[
                    [{"bone":"root","weight":1.0}],
                    [{"bone":"root","weight":1.0}],
                    [{"bone":"root","weight":1.0}],
                ],
                "provenance":provenance,
                "approved_occlusion_receipt":None,
            }
        ],
        "draw_order":["face"],
        "constraints":[],
        "animations":{},
        "provenance":{},
    }


def test_v3_provenance_fail_closed():
    assert classify_layer({"part":"face","provenance":"DERIVED_VISIBLE"}).ok
    assert production_admissible({"part":"face","provenance":"DERIVED_VISIBLE"})
    report=classify_layer({"part":"hair_back","provenance":"INFERRED_OCCLUSION"})
    assert not report.ok
    assert any(x.code=="INFERRED_OCCLUSION_REQUIRES_OWNER_APPROVAL" for x in report.findings)
    report=classify_layer({"part":"face","provenance":"GENERATIVE_VISIBLE"})
    assert not report.ok
    assert any(x.code=="GENERATIVE_VISIBLE_FORBIDDEN" for x in report.findings)


def test_rig_ir_accepts_supported_minimum_and_rejects_generated_visible():
    assert validate_rig_ir(_minimal_rig()).ok
    report=validate_rig_ir(_minimal_rig("GENERATIVE_VISIBLE"))
    assert not report.ok
    assert any("GENERATIVE_VISIBLE_FORBIDDEN" in p for p in report.problems)


def test_spine_4_mesh_import_is_normalized_into_rig_ir():
    payload={
        "skeleton":{"spine":"4.1.24"},
        "bones":[{"name":"root"}],
        "slots":[{"name":"face_slot","bone":"root"}],
        "skins":[{
            "name":"default",
            "attachments":{
                "face_slot":{
                    "face":{
                        "type":"mesh",
                        "uvs":[0,0,1,0,0,1],
                        "vertices":[0,0,1,0,0,1],
                        "triangles":[0,1,2],
                    }
                }
            },
        }],
    }
    rig=import_spine_json(
        payload,
        source_master_sha256="b"*64,
        part_provenance={"face":{"provenance":"DERIVED_VISIBLE"}},
    )
    assert validate_rig_ir(rig).ok
    assert rig["meshes"][0]["weights"][0]==[{"bone":"root","weight":1.0}]


def _svg(groups, *, hair_paths=1):
    rows=[]
    for name in groups:
        fill=(
            "#eeeeee" if name=="hair"
            else "#00bcd4" if name in {"visor_lens","orb_core"}
            else "#2196f3" if name in {"eye_l","eye_r"}
            else "#8d5524" if name in {"face","neck"}
            else "#222222"
        )
        count=hair_paths if name=="hair" else 1
        paths="".join(f'<path fill="{fill}" d="M 10 10 L 90 10 L 90 90 Z"/>' for _ in range(count))
        rows.append(f'<g id="{name}">{paths}</g>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'+"".join(rows)+"</svg>"


def test_per_part_topology_budget_blocks_overtraced_hair(tmp_path):
    svg=tmp_path/"overtrace.svg"
    svg.write_text(_svg(list(REQUIRED_GROUPS),hair_paths=91),encoding="utf-8")
    report=lint_svg(svg,require_geometry=False)
    assert "GROUP_PATH_BUDGET_EXCEEDED:hair:91>90" in report.findings


def _fake_png(path:Path,width:int,height:int):
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+struct.pack(">I",13)+b"IHDR"+struct.pack(">II",width,height)+b"\x08\x06\x00\x00\x00")


def test_highres_master_is_candidate_until_exact_owner_approval(monkeypatch,tmp_path):
    canonical=tmp_path/"canonical.png"
    identity=tmp_path/"identity.yaml"
    policy=tmp_path/"policy.yaml"
    candidate=tmp_path/"candidate.png"
    approved=tmp_path/"approved.png"
    _fake_png(canonical,1536,1024)
    _fake_png(candidate,3072,2048)
    identity.write_text("status: LOCKED\n",encoding="utf-8")
    policy.write_text(yaml.safe_dump({
        "source_authority":{"git_blob_sha":"fc18bbe0b91e5b85d8cf8211314a69cb90b8bc0b"},
        "candidate":{"minimum_short_edge_px":2048},
    }),encoding="utf-8")
    monkeypatch.setattr(master_module,"CANONICAL",canonical)
    monkeypatch.setattr(master_module,"IDENTITY_LOCK",identity)
    monkeypatch.setattr(master_module,"POLICY",policy)
    monkeypatch.setattr(master_module,"ROOT",tmp_path)
    monkeypatch.setattr(master_module,"APPROVED",approved)

    staged=stage_master(candidate)
    assert staged["status"]=="CANDIDATE_NOT_AUTHORITY"
    assert png_dimensions(candidate)==(3072,2048)

    approval=tmp_path/"approval.yaml"
    approval.write_text(yaml.safe_dump({
        "decision":"APPROVE",
        "authority":"owner",
        "candidate_sha256":staged["candidate_sha256"],
        "canonical_source_git_blob_sha":staged["canonical_source_git_blob_sha"],
        "identity_lock_sha256":staged["identity_lock_sha256"],
    }),encoding="utf-8")
    result=approve_master(candidate,approval)
    assert result["status"]=="OWNER_APPROVED_MASTER"
    assert approved.read_bytes()==candidate.read_bytes()


def test_v3_source_policy_preserves_explicit_board_skin_token():
    policy=yaml.safe_load((ROOT/"visual-authority"/"character-forge"/"00-source"/"production-v3"/"MASTER_PROVENANCE.yaml").read_text(encoding="utf-8"))
    assert policy["source_authority"]["declared_skin_token"]=="#AF6A53"


def test_bootstraps_pin_sources_and_do_not_silently_admit_model_weights():
    controller=(ROOT/"deploy"/"character-forge"/"bootstrap-production-v3.sh").read_text(encoding="utf-8")
    gpu=(ROOT/"deploy"/"character-forge"/"bootstrap-gpu-worker-v3.sh").read_text(encoding="utf-8")
    assert "7f139bb25c46a0c8ac720d95ddab185fcda5451c" in controller
    assert "24a83a27ba43e43e9d2e3de5e33994594e6199c2" in controller
    assert "BLOCKED_PENDING_LICENSE_AND_HASH_LOCK" in controller
    assert 'status")!="CLEARED"' in gpu
    assert "nvidia-smi" in gpu


def test_semantic_layer_mapping_is_fail_closed_on_unknown_or_ambiguous_names(tmp_path):
    mapping=ROOT/"visual-authority"/"character-forge"/"00-source"/"production-v3"/"SEE_THROUGH_LAYER_MAP.yaml"
    ok=map_layer_names(["hair","face","visor","jacket"],mapping)
    assert ok["ok"] is True
    assert {row["semantic"] for row in ok["mapped"]}=={"hair","face","visor","jacket"}

    bad=map_layer_names(["mystery_part"],mapping)
    assert bad["ok"] is False
    assert bad["unmapped"]==["mystery_part"]


def test_gpu_job_requires_weight_hashes_outside_trial(tmp_path):
    source=tmp_path/"master.png"
    _fake_png(source,3072,2048)
    trial=build_see_through_job(
        source=source,
        master_sha256="a"*64,
        code_commit="7f139bb25c46a0c8ac720d95ddab185fcda5451c",
        mode="trial",
        resolution=1280,
        weight_hashes={},
    )
    assert trial["output_policy"]["hidden_generated"]=="INFERRED_OCCLUSION"
    assert len(canonical_job_sha256(trial))==64

    import pytest
    with pytest.raises(ValueError,match="requires weight hashes"):
        build_see_through_job(
            source=source,
            master_sha256="a"*64,
            code_commit="7f139bb25c46a0c8ac720d95ddab185fcda5451c",
            mode="full_precision",
            resolution=1280,
            weight_hashes={},
        )


def test_controller_bootstrap_installs_cli_wrapper_and_pins_proposal_tools():
    controller=(ROOT/"deploy"/"character-forge"/"bootstrap-production-v3.sh").read_text(encoding="utf-8")
    assert "/usr/local/bin/van-character-forge-v3" in controller
    assert "git -C \"$target\" checkout --detach \"$commit\"" in controller
    assert "BLOCKED_PENDING_LICENSE_AND_HASH_LOCK" in controller


def test_v3_bootstrap_shell_syntax():
    for rel in (
        "deploy/character-forge/bootstrap-production-v3.sh",
        "deploy/character-forge/bootstrap-gpu-worker-v3.sh",
        "deploy/character-forge/bootstrap-netcup-authoring.sh",
    ):
        result=subprocess.run(["bash","-n",str(ROOT/rel)],capture_output=True,text=True)
        assert result.returncode==0, result.stderr
