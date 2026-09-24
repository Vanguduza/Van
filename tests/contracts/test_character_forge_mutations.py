from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from tools.character_forge import cli, gates, manifest as manifest_module, receipts
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
            else "#8d5524" if name in {"face", "neck"}
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


def test_rive_cli_receipt_can_stage_and_reach_m2_positive_path(monkeypatch, tmp_path: Path):
    root = tmp_path
    working = root / "visual-authority" / "character-forge" / "09-rive-working"
    working.mkdir(parents=True)
    candidate = working / "van_core.riv"
    candidate.write_bytes(b"RIVE" * 512)
    project = working / "rml" / "van"
    project.mkdir(parents=True)
    (project / "scene.rml").write_text("<Artboard name=\"Van\"/>\n", encoding="utf-8")

    contract = root / "visual-authority" / "rive_contract.json"
    contract.parent.mkdir(parents=True, exist_ok=True)
    contract.write_text('{"artboard":"Van","state_machine":"VanRuntime"}\n', encoding="utf-8")

    test_assets = root / "androidTest" / "assets"
    debug_assets = root / "debug" / "assets"
    layer_sha = "a" * 64
    manifest = {
        "artifacts": [
            {
                "artifact_id": f"layer_svg:{layer_sha}",
                "kind": "layer_svg",
                "path": "visual-authority/character-forge/van_layers.svg",
                "sha256": layer_sha,
                "stage": "vector",
                "promotion": "CANDIDATE",
            }
        ],
        "receipts": [],
        "reviews": {},
    }
    status = {
        "performance": {"max_janky_percent": 5.0},
        "core_rig": {
            "candidate_sha256": None,
            "emulator_validation": "NOT_RUN",
            "ci_run": None,
            "owner_verdict": "NONE",
        },
        "full_rig": {
            "candidate_sha256": None,
            "emulator_validation": "NOT_RUN",
            "ci_run": None,
            "reviewed": "NONE",
        },
        "current_stage": "vector",
        "next_action": "",
    }
    tools = {"critical_path": {"rive_cli": {"version": "0.1.0"}}}

    monkeypatch.setattr(manifest_module, "ROOT", root)
    monkeypatch.setattr(receipts, "ROOT", root)
    monkeypatch.setattr(cli, "ROOT", root)
    monkeypatch.setattr(cli, "WORKING_DIR", working)
    monkeypatch.setattr(cli, "RML_ROOT", working / "rml")
    monkeypatch.setattr(cli, "CONTRACT_PATH", contract)
    monkeypatch.setattr(cli, "ANDROID_TEST_ASSETS", test_assets)
    monkeypatch.setattr(cli, "ANDROID_DEBUG_ASSETS", debug_assets)
    monkeypatch.setattr(cli, "load_yaml", lambda: manifest)
    monkeypatch.setattr(cli, "load_status", lambda: status)
    monkeypatch.setattr(cli, "_yaml", lambda _path: tools)
    monkeypatch.setattr(cli, "_save", lambda _manifest, _status: None)

    assert cli.main([
        "--actor", "test",
        "rive", "receipt",
        "--candidate", str(candidate),
        "--stage", "core_rig",
        "--authoring-version", "0.1.0",
        "--rive-file-id", "local:test",
        "--rive-revision", "1",
        "--svg-sha", layer_sha,
        "--source-project", str(project),
        "--artist", "test",
    ]) == 0

    assert cli.main([
        "--actor", "test",
        "rive", "stage-candidate", str(candidate),
        "--stage", "core_rig",
    ]) == 0

    candidate_sha = sha256_file(candidate)
    assert status["core_rig"]["candidate_sha256"] == candidate_sha
    assert sha256_file(test_assets / "van_candidate.riv") == candidate_sha
    assert sha256_file(debug_assets / "van_candidate.riv") == candidate_sha

    status["core_rig"].update(
        {
            "emulator_validation": "PASS",
            "ci_run": "https://github.com/Vanguduza/Van/actions/runs/123",
            "owner_verdict": "PASS",
        }
    )
    baseline = root / "visual-authority" / "character-forge" / "11-device-evidence" / "core_baseline"
    baseline.mkdir(parents=True)
    (baseline / "idle.png").write_bytes(b"PNG")

    monkeypatch.setattr(gates, "ROOT", root)
    monkeypatch.setattr(gates, "CONTRACT", contract)
    monkeypatch.setattr(gates, "m1", lambda: [])
    monkeypatch.setattr(gates, "load_yaml", lambda: manifest)
    monkeypatch.setattr(gates, "load_status", lambda: status)
    monkeypatch.setattr(gates, "_yaml", lambda _path: tools)

    assert gates._receipt_problems(candidate_sha, "core_rig", manifest, tools) == []
    assert gates.m2() == []


def _receipted_candidate(monkeypatch, tmp_path: Path):
    """A pinned, receipted core candidate built from a real RML project, ready to stage."""
    root = tmp_path
    working = root / "visual-authority" / "character-forge" / "09-rive-working"
    project = working / "rml" / "van"
    project.mkdir(parents=True)
    (project / "scene.rml").write_text("<Artboard name=\"Van\"/>\n", encoding="utf-8")
    candidate = working / "van_core_1.riv"
    candidate.write_bytes(b"RIVE" * 512)
    contract = root / "visual-authority" / "rive_contract.json"
    contract.write_text("{}\n", encoding="utf-8")
    layer_sha = "a" * 64
    manifest = {"artifacts": [{"kind": "layer_svg", "sha256": layer_sha, "path": "x.svg"}], "receipts": [], "reviews": {}}
    status = {"performance": {}, "core_rig": {"candidate_sha256": None, "emulator_validation": "NOT_RUN", "ci_run": None, "owner_verdict": "NONE"},
              "full_rig": {"candidate_sha256": None, "emulator_validation": "NOT_RUN", "ci_run": None, "reviewed": "NONE"}}
    for module in (manifest_module, receipts, cli):
        monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(cli, "WORKING_DIR", working)
    monkeypatch.setattr(cli, "RML_ROOT", working / "rml")
    monkeypatch.setattr(cli, "CONTRACT_PATH", contract)
    monkeypatch.setattr(cli, "ANDROID_TEST_ASSETS", root / "androidTest" / "assets")
    monkeypatch.setattr(cli, "ANDROID_DEBUG_ASSETS", root / "debug" / "assets")
    monkeypatch.setattr(cli, "load_yaml", lambda: manifest)
    monkeypatch.setattr(cli, "load_status", lambda: status)
    monkeypatch.setattr(cli, "_yaml", lambda _path: {"critical_path": {"rive_cli": {"version": "1.1.1"}}})
    monkeypatch.setattr(cli, "_save", lambda _m, _s: None)
    return candidate, project, layer_sha


def test_receipt_refuses_rml_project_outside_the_jail(monkeypatch, tmp_path: Path):
    candidate, _, layer_sha = _receipted_candidate(monkeypatch, tmp_path)
    stray = tmp_path / "elsewhere"
    stray.mkdir()
    (stray / "scene.rml").write_text("x", encoding="utf-8")
    assert cli.main(["rive", "receipt", "--candidate", str(candidate), "--stage", "core_rig", "--authoring-version", "1.1.1",
                     "--rive-file-id", "LOCAL", "--rive-revision", "LOCAL", "--svg-sha", layer_sha,
                     "--source-project", str(stray), "--artist", "t"]) == 1


def test_mutation_rml_source_edited_after_receipt_blocks_staging(monkeypatch, tmp_path: Path):
    candidate, project, layer_sha = _receipted_candidate(monkeypatch, tmp_path)
    assert cli.main(["rive", "receipt", "--candidate", str(candidate), "--stage", "core_rig", "--authoring-version", "1.1.1",
                     "--rive-file-id", "LOCAL", "--rive-revision", "LOCAL", "--svg-sha", layer_sha,
                     "--source-project", str(project), "--artist", "t"]) == 0
    (project / "scene.rml").write_text("<Artboard name=\"Van\"><Edited/></Artboard>\n", encoding="utf-8")
    assert cli.main(["rive", "stage-candidate", str(candidate), "--stage", "core_rig"]) == 1


def test_source_tree_digest_ignores_build_products_but_not_source(tmp_path: Path):
    from tools.character_forge.manifest import source_tree_sha256
    project = tmp_path / "van"
    project.mkdir()
    (project / "scene.rml").write_text("a", encoding="utf-8")
    first, count = source_tree_sha256(project)
    (project / "van.riv").write_bytes(b"built")
    (project / "screenshots").mkdir()
    (project / "screenshots" / "idle.png").write_bytes(b"png")
    assert source_tree_sha256(project) == (first, count)
    (project / "scene.rml").write_text("b", encoding="utf-8")
    assert source_tree_sha256(project)[0] != first


def test_gate_rejects_receipt_without_rml_source_binding(monkeypatch, tmp_path: Path):
    import json
    working = tmp_path / "visual-authority" / "character-forge" / "09-rive-working"
    working.mkdir(parents=True)
    candidate = working / "c.riv"
    candidate.write_bytes(b"R" * 2048)
    sha = sha256_file(candidate)
    contract = tmp_path / "contract.json"
    contract.write_text("{}", encoding="utf-8")
    (working / "c.receipt.json").write_text(json.dumps({
        "candidate_sha256": sha, "candidate_path": "visual-authority/character-forge/09-rive-working/c.riv",
        "stage": "core_rig", "authoring_tool": "rive_cli", "authoring_version": "1.1.1",
        "svg_sha256": "a" * 64, "contract_sha256": sha256_file(contract)}), encoding="utf-8")
    monkeypatch.setattr(gates, "ROOT", tmp_path)
    monkeypatch.setattr(gates, "CONTRACT", contract)
    problems = gates._receipt_problems(sha, "core_rig", {"artifacts": [{"kind": "layer_svg", "sha256": "a" * 64}]},
                                       {"critical_path": {"rive_cli": {"version": "1.1.1"}}})
    assert "core_rig receipt does not bind an RML source project" in problems


def test_mutation_non_hex_palette_encodings_cannot_hide_dark_hair(tmp_path: Path):
    for label, node in (
        ("rgb", '<path fill="rgb(17,17,17)" d="M 10 10 L 90 10 L 90 90 Z"/>'),
        ("named", '<path fill="black" d="M 10 10 L 90 10 L 90 90 Z"/>'),
        ("gradient", '<path fill="url(#dark)" d="M 10 10 L 90 10 L 90 90 Z"/>'),
    ):
        text = _svg(list(REQUIRED_GROUPS)).replace(
            '<g id="hair"><path fill="#eeeeee" d="M 10 10 L 90 10 L 90 90 Z"/></g>',
            f'<g id="hair">{node}</g>',
        ).replace(
            'viewBox="0 0 100 100">',
            'viewBox="0 0 100 100"><defs><linearGradient id="dark"><stop offset="0" stop-color="#101010"/>'
            '<stop offset="1" stop-color="#050505"/></linearGradient></defs>',
        )
        svg = tmp_path / f"{label}.svg"
        svg.write_text(text, encoding="utf-8")
        findings = lint_svg(svg, require_geometry=False).findings
        assert any(f.startswith("PALETTE_OUTSIDE_LOCK:hair:") for f in findings), label


def test_unparseable_colour_in_locked_group_is_refused_not_skipped(tmp_path: Path):
    text = _svg(list(REQUIRED_GROUPS)).replace(
        '<g id="hair"><path fill="#eeeeee"', '<g id="hair"><path fill="hsl(0, 0%, 5%)"')
    svg = tmp_path / "hsl.svg"
    svg.write_text(text, encoding="utf-8")
    assert any(f.startswith("UNVERIFIABLE_COLOR:hair:") for f in lint_svg(svg, require_geometry=False).findings)


def test_silver_hair_in_rgb_notation_is_still_admitted(tmp_path: Path):
    text = _svg(list(REQUIRED_GROUPS)).replace('<g id="hair"><path fill="#eeeeee"', '<g id="hair"><path fill="rgb(232,235,240)"')
    svg = tmp_path / "rgb-silver.svg"
    svg.write_text(text, encoding="utf-8")
    assert not [f for f in lint_svg(svg, require_geometry=False).findings if ":hair:" in f]


def test_mutation_emulator_or_other_handset_cannot_satisfy_s24_checklist():
    for model in ("sdk_gphone64_x86_64", "SM-S918B", "Pixel 8"):
        assert any("is not a Galaxy S24 Ultra" in p for p in gates._device_problems({"device": {"model": model}}))
    assert gates._device_problems({"device": {"model": "SM-S928B"}}) == []


def test_mutation_label_instead_of_evidence_file_fails_s24_checklist(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(gates, "ROOT", tmp_path)
    evidence = tmp_path / gates.DEVICE_EVIDENCE_ROOT / "renderer.png"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b"PNG")
    ok = {"device": {"model": "SM-S928B"}, "evidence": {"renderer_rive_active": gates.DEVICE_EVIDENCE_ROOT + "renderer.png"}}
    assert gates._device_problems(ok) == []
    for ref in ("clip://renderer", "PASS", gates.DEVICE_EVIDENCE_ROOT + "missing.mp4", gates.DEVICE_EVIDENCE_ROOT + "../../../etc/passwd"):
        bad = {"device": {"model": "SM-S928B"}, "evidence": {"renderer_rive_active": ref}}
        assert gates._device_problems(bad), ref


def _review_fixture(monkeypatch, *, layer_author="artist:vector-agent"):
    manifest = {"artifacts": [{"kind": "layer_svg", "sha256": "a" * 64, "produced_by": layer_author}], "reviews": {}, "receipts": []}
    status = {"full_rig": {}}
    monkeypatch.setattr(cli, "load_yaml", lambda: manifest)
    monkeypatch.setattr(cli, "load_status", lambda: status)
    monkeypatch.setattr(cli, "_save", lambda *_: None)
    return manifest


def test_mutation_author_cannot_review_own_layer_svg(monkeypatch):
    manifest = _review_fixture(monkeypatch)
    args = ["review", "record", "--target", "layer", "--verdict", "PASS", "--date", "2026-09-23"]
    assert cli.main(args + ["--reviewer", "Vector-Agent"]) == 1
    assert cli.main(["--actor", "commander"] + args + ["--reviewer", "someone-else"]) == 1
    assert "layer_svg" not in manifest["reviews"]
    assert cli.main(args + ["--reviewer", "independent-reviewer"]) == 0
    assert manifest["reviews"]["layer_svg"]["verdict"] == "PASS"
