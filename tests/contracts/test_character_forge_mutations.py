from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from tools.character_forge import gates
from tools.character_forge.gates import contract_surface_problems
from tools.character_forge.manifest import load_yaml, sha256_file
from tools.character_forge.status import load_status, validate_status
from tools.character_forge.svg_lint import REQUIRED_GROUPS, lint_svg

BASE = {
    "artboard": "Van",
    "state_machine": "VanRuntime",
    "inputs": [
        {"name": "state"},
        {"name": "speaking"},
        {"name": "listening"},
        {"name": "attention_x"},
        {"name": "attention_y"},
        {"name": "mouth_open"},
        {"name": "urgency"},
        {"name": "viseme"},
        {"name": "action_code"},
    ],
    "triggers": ["point", "ack", "celebrate", "warning", "wave", "shrug", "present", "panel"],
    "durable_states": {f"S{i}": i for i in range(18)},
    "finite_actions": {f"A{i}": i for i in range(1, 15)},
}


def test_contract_guard_rejects_removed_state():
    mutated = deepcopy(BASE)
    mutated["durable_states"].pop("S17")
    assert "durable state surface drift" in contract_surface_problems(mutated)


def test_contract_guard_rejects_renamed_input():
    mutated = deepcopy(BASE)
    mutated["inputs"][3]["name"] = "attentionX"
    assert "public input surface drift" in contract_surface_problems(mutated)


def test_contract_guard_rejects_artboard_case_drift():
    mutated = deepcopy(BASE)
    mutated["artboard"] = "VAN"
    assert "artboard must be Van" in contract_surface_problems(mutated)


def test_contract_guard_rejects_removed_action():
    mutated = deepcopy(BASE)
    mutated["finite_actions"].pop("A14")
    assert "finite action surface drift" in contract_surface_problems(mutated)


def test_contract_guard_rejects_missing_trigger():
    mutated = deepcopy(BASE)
    mutated["triggers"].pop()
    assert "trigger surface drift" in contract_surface_problems(mutated)


def test_mutated_baseline_sha_is_rejected_by_m0(monkeypatch):
    status = deepcopy(load_status())
    manifest = deepcopy(load_yaml())
    status["baseline_sha"] = "0" * 40
    monkeypatch.setattr(gates, "load_status", lambda: status)
    monkeypatch.setattr(gates, "load_yaml", lambda: manifest)
    assert "manifest/status baseline SHA mismatch" in gates.m0()


def test_pass_without_instrumentation_run_is_invalid():
    status = deepcopy(load_status())
    status["core_rig"]["emulator_validation"] = "PASS"
    status["core_rig"]["ci_run"] = None
    assert "core_rig PASS requires ci_run" in validate_status(status)


def _svg(groups: list[str], *, hair: str = "#eeeeee") -> str:
    body = []
    for name in groups:
        fill = (
            hair if name == "hair"
            else "#00bcd4" if name in {"visor_lens", "orb_core"}
            else "#2196f3" if name in {"eye_l", "eye_r"}
            else "#8d5524" if name in {"face", "neck", "hand_l", "hand_r"}
            else "#222222"
        )
        body.append(
            f'<g id="{name}"><path fill="{fill}" d="M 10 10 L 90 10 L 90 90 Z"/></g>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        + "".join(body)
        + "</svg>"
    )


def test_mutation_drop_required_svg_group_is_rejected(tmp_path: Path):
    svg = tmp_path / "missing-hair.svg"
    svg.write_text(_svg(list(REQUIRED_GROUPS)[1:]), encoding="utf-8")
    assert "MISSING_GROUP:hair" in lint_svg(svg, require_geometry=False).findings


def test_mutation_dark_hair_is_rejected(tmp_path: Path):
    svg = tmp_path / "dark-hair.svg"
    svg.write_text(_svg(list(REQUIRED_GROUPS), hair="#111111"), encoding="utf-8")
    assert any(
        problem.startswith("PALETTE_OUTSIDE_LOCK:hair:")
        for problem in lint_svg(svg, require_geometry=False).findings
    )


def _configure_m4_fixture(
    monkeypatch,
    tmp_path: Path,
    *,
    app_bytes: bytes | None = None,
    acceptance: dict | None = None,
    qual_ready: bool = False,
):
    source = tmp_path / "van_runtime.riv"
    shipped = tmp_path / "van.riv"
    source.write_bytes(b"RIVE" * 1024)
    shipped.write_bytes(source.read_bytes() if app_bytes is None else app_bytes)
    source_sha = sha256_file(source)

    status = deepcopy(load_status())
    status.update(
        {
            "rive_authored": True,
            "rive_asset_ready": True,
            "device_qualified": qual_ready,
            "owner_accepted": qual_ready,
            "qual_emb_01": "READY" if qual_ready else "EXTERNAL_ARTEFACT",
        }
    )
    status["production"] = {
        "emulator_validation": "PASS",
        "ci_run": "https://github.com/Vanguduza/Van/actions/runs/1",
        "rive_sha256": source_sha,
    }

    device = tmp_path / "DEVICE_CHECKLIST.yaml"
    device.write_text(
        yaml.safe_dump(
            {
                "device": {
                    "model": "SM-S928B",
                    "android_build": "test-build",
                    "apk_sha256": "b" * 64,
                    "rive_sha256": source_sha,
                    "checked_at": "2026-09-22T00:00:00Z",
                },
                "checks": {"renderer_rive_active": "PASS"},
                "thermal_note": "stable",
                "evidence": {"renderer_rive_active": "clip://renderer"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    acceptance_path = tmp_path / "ACCEPTANCE.yaml"
    acceptance_path.write_text(
        yaml.safe_dump({"core_rig": None, "final": acceptance}, sort_keys=False),
        encoding="utf-8",
    )

    release = tmp_path / "manifest.json"
    release.write_text(
        '{"rive_sha256":"' + source_sha + '"}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(gates, "m3", lambda: [])
    monkeypatch.setattr(gates, "load_status", lambda: status)
    monkeypatch.setattr(gates, "SOURCE_RIV", source)
    monkeypatch.setattr(gates, "APP_RIV", shipped)
    monkeypatch.setattr(gates, "DEVICE", device)
    monkeypatch.setattr(gates, "ACCEPTANCE", acceptance_path)
    monkeypatch.setattr(gates, "RELEASE_MANIFEST", release)
    return source_sha, status


def test_mutation_delete_final_acceptance_fails_m4(monkeypatch, tmp_path: Path):
    _configure_m4_fixture(monkeypatch, tmp_path, acceptance=None)
    assert "verified final owner acceptance missing" in gates.m4()


def test_mutation_change_accepted_rive_bytes_fails_release_gate(monkeypatch, tmp_path: Path):
    source_sha, _ = _configure_m4_fixture(
        monkeypatch,
        tmp_path,
        app_bytes=b"MUTATED" * 1024,
        acceptance={
            "verified": True,
            "act": "visual-accept",
            "subject": "placeholder",
        },
        qual_ready=True,
    )
    acceptance_path = gates.ACCEPTANCE
    acceptance_path.write_text(
        yaml.safe_dump(
            {
                "core_rig": None,
                "final": {
                    "verified": True,
                    "act": "visual-accept",
                    "subject": f"sha256:{source_sha}",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    problems = gates.m5()
    assert "source and shipped Rive bytes differ" in problems
    assert "release manifest Rive SHA differs" in problems


def test_unreceipted_candidate_is_not_stageable(monkeypatch, tmp_path: Path):
    from tools.character_forge import cli

    monkeypatch.setattr(cli, "WORKING_DIR", tmp_path)
    candidate = tmp_path / "unreceipted_core.riv"
    candidate.write_bytes(b"x" * 2048)
    assert cli.main(["rive", "stage-candidate", str(candidate), "--stage", "core_rig"]) == 1
