"""CF-D-09 — the raster layer set's path through M1: admission, review and the gate.

These run without the imaging stack: the lint is replaced by a stub so what is tested is the
authority around it. Nothing is admitted without the owner decision, from outside the clean
lane, or past a failing lint; the author cannot review their own set; one layer artifact is
live at a time; and M1 reads the review for the exact SHA that was admitted.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.character_forge import cli, gates, manifest as manifest_module

DECISION = {"id": "CF-D-09", "status": "ADOPTED"}


def _report(ok: bool = True):
    findings = [] if ok else ["RECOMPOSITE_NOT_EXACT:12"]
    return SimpleNamespace(ok=ok, findings=findings, as_dict=lambda: {"ok": ok, "findings": findings})


@pytest.fixture
def forge(monkeypatch, tmp_path: Path):
    clean = tmp_path / "visual-authority" / "character-forge" / "06-raster-clean"
    lane = clean / "candidate_b_front"
    lane.mkdir(parents=True)
    (lane / "01_hair.png").write_bytes(b"png")
    (lane / "LAYERS.json").write_text(json.dumps({"layers": [{"name": "hair", "sha256": "b" * 64}, {"name": "brow_l", "empty": True}]}), encoding="utf-8")
    manifest = {"decisions": [dict(DECISION)], "artifacts": [], "reviews": {}, "receipts": [], "sources": []}
    status = {"current_stage": "admission"}
    for module in (manifest_module, cli):
        monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "RASTER_CLEAN_DIR", clean)
    monkeypatch.setattr(cli, "load_yaml", lambda: manifest)
    monkeypatch.setattr(cli, "load_status", lambda: status)
    monkeypatch.setattr(cli, "_save", lambda *_: None)
    monkeypatch.setattr(cli, "_raster_lint", lambda _d: _report(True))
    return SimpleNamespace(manifest=manifest, status=status, lane=lane, root=tmp_path)


def test_admission_needs_the_owner_decision(forge) -> None:
    forge.manifest["decisions"] = [{"id": "CF-D-09", "status": "PROPOSED"}]
    assert cli.main(["layers", "admit", str(forge.lane), "--artist", "rig-artist"]) == 1
    assert not forge.manifest["artifacts"]


def test_admission_only_from_the_clean_lane(forge) -> None:
    lane = forge.root / "visual-authority" / "character-forge" / "04-raster-layers" / "candidate_b_front"
    lane.mkdir(parents=True)
    (lane / "LAYERS.json").write_text("{}", encoding="utf-8")
    assert cli.main(["layers", "admit", str(lane), "--artist", "rig-artist"]) == 1
    assert not forge.manifest["artifacts"]


def test_a_failing_lint_refuses_admission(forge, monkeypatch) -> None:
    monkeypatch.setattr(cli, "_raster_lint", lambda _d: _report(False))
    assert cli.main(["layers", "admit", str(forge.lane), "--artist", "rig-artist"]) == 1
    assert not forge.manifest["artifacts"]


def test_admission_records_the_set_and_supersedes_the_vector_layer(forge) -> None:
    forge.manifest["artifacts"].append({"kind": "layer_svg", "sha256": "a" * 64, "path": "x.svg", "promotion": "CANDIDATE"})
    forge.manifest["reviews"]["layer_raster_set"] = {"sha256": "old", "verdict": "PASS"}
    assert cli.main(["layers", "admit", str(forge.lane), "--artist", "rig-artist"]) == 0
    live = gates.admitted_layer(forge.manifest)
    assert live["kind"] == "layer_raster_set" and live["decision"] == "CF-D-09"
    assert live["path"] == "visual-authority/character-forge/06-raster-clean/candidate_b_front/LAYERS.json"
    assert live["layer_files"] == {"hair": "b" * 64}
    assert forge.manifest["artifacts"][0]["promotion"] == "SUPERSEDED"
    assert "layer_raster_set" not in forge.manifest["reviews"]
    assert forge.manifest["receipts"][-1]["command"] == "layers admit"
    assert "LAYER_ARTIFACT_MISSING" not in forge.status["blockers"]
    assert cli.main(["layers", "admit", str(forge.lane), "--artist", "rig-artist"]) == 0  # NO_CHANGE


def test_withdrawing_the_decision_withdraws_the_raster_set(forge) -> None:
    assert cli.main(["layers", "admit", str(forge.lane), "--artist", "rig-artist"]) == 0
    forge.manifest["decisions"] = []
    assert gates.admitted_layer(forge.manifest) is None


def test_the_author_and_commander_cannot_review_the_set(forge) -> None:
    args = ["review", "record", "--target", "raster", "--verdict", "PASS", "--date", "2026-09-25"]
    assert cli.main(args + ["--reviewer", "reviewer"]) == 1  # nothing admitted yet
    assert cli.main(["layers", "admit", str(forge.lane), "--artist", "rig-artist"]) == 0
    assert cli.main(args + ["--reviewer", "Rig-Artist"]) == 1
    assert cli.main(["--actor", "commander"] + args + ["--reviewer", "someone-else"]) == 1
    assert "layer_raster_set" not in forge.manifest["reviews"]
    assert cli.main(args + ["--reviewer", "independent-reviewer"]) == 0
    row = forge.manifest["reviews"]["layer_raster_set"]
    assert row["verdict"] == "PASS" and row["sha256"] == gates.admitted_layer(forge.manifest)["sha256"]


def _m1(monkeypatch, manifest, *, lint_findings=()):
    monkeypatch.setattr(gates, "m0", lambda: [])
    monkeypatch.setattr(gates, "load_yaml", lambda: manifest)
    monkeypatch.setattr(gates, "_yaml", lambda _p: {"critical_path": {"inkscape": {"version": "UNPINNED"}}})
    monkeypatch.setattr(gates, "verify_records", lambda _r: [])
    monkeypatch.setattr(gates, "_raster_problems", lambda _l: [f"admitted raster layer set fails lint: {f}" for f in lint_findings])
    return gates.m1()


def test_m1_passes_on_a_reviewed_raster_set_without_inkscape(monkeypatch) -> None:
    sha = "c" * 64
    manifest = {"decisions": [DECISION], "artifacts": [{"kind": "layer_raster_set", "sha256": sha, "path": "x/LAYERS.json"}],
                "reviews": {"layer_raster_set": {"sha256": sha, "verdict": "PASS"}}}
    assert _m1(monkeypatch, manifest) == []
    manifest["reviews"]["layer_raster_set"]["sha256"] = "d" * 64
    assert _m1(monkeypatch, manifest) == ["raster layer set review is for a superseded SHA"]
    manifest["reviews"]["layer_raster_set"]["sha256"] = sha
    assert _m1(monkeypatch, manifest, lint_findings=["EMPTY_LAYER:hair"]) == ["admitted raster layer set fails lint: EMPTY_LAYER:hair"]
    # A vector review does not stand in for the raster set's.
    manifest["reviews"] = {"layer_svg": {"sha256": sha, "verdict": "PASS"}}
    assert _m1(monkeypatch, manifest) == ["raster layer set independent/owner review not PASS"]


def test_m1_without_the_decision_does_not_see_the_raster_set(monkeypatch) -> None:
    sha = "c" * 64
    manifest = {"decisions": [], "artifacts": [{"kind": "layer_raster_set", "sha256": sha, "path": "x/LAYERS.json"}],
                "reviews": {"layer_raster_set": {"sha256": sha, "verdict": "PASS"}}}
    problems = _m1(monkeypatch, manifest)
    assert "no admitted layer_svg (or layer_raster_set under CF-D-09)" in problems


def test_receipts_bind_to_the_admitted_raster_set() -> None:
    sha = "c" * 64
    manifest = {"decisions": [DECISION], "artifacts": [{"kind": "layer_svg", "sha256": "a" * 64, "promotion": "SUPERSEDED"},
                                                        {"kind": "layer_raster_set", "sha256": sha}]}
    assert gates.admitted_layer(manifest)["sha256"] == sha
