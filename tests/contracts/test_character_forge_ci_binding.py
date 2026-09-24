"""CI outcome binding: a recorded validation must be what RiveContractTest concluded about
these exact bytes in this exact run — never a typed PASS over a bare SHA file."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.character_forge import ci_binding, cli
from tools.character_forge.manifest import sha256_file

CLASS = ci_binding.TEST_CLASS


def _junit(path: Path, outcomes: dict[str, str]) -> None:
    cases = []
    for name, outcome in outcomes.items():
        body = {"failed": "<failure message='x'/>", "error": "<error message='x'/>", "skipped": "<skipped/>"}.get(outcome, "")
        cases.append(f'<testcase classname="{CLASS}" name="{name}">{body}</testcase>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<testsuite>" + "".join(cases) + "</testsuite>", encoding="utf-8")


def _all(outcome: str = "passed") -> dict[str, str]:
    return {name: outcome for name in ci_binding.ALL_TESTS}


def test_core_mode_allows_only_the_declared_full_only_skips():
    outcomes = _all()
    for name in ci_binding.CORE_ONLY_SKIPS:
        outcomes[name] = "skipped"
    assert ci_binding.evaluate("core", outcomes) == ("PASS", [])
    assert ci_binding.evaluate("full", outcomes)[0] == "FAIL"
    full = _all(); full["productionAvatarPathKeepsRive"] = "skipped"
    assert ci_binding.evaluate("full", full) == ("PASS", [])
    assert ci_binding.evaluate("production", full)[0] == "FAIL"


def test_unexpected_skip_missing_case_or_failure_fails():
    for mutate in ({"contractSurfaceMatches": "skipped"}, {"identityColourFamilies": "failed"}, {"brokenAssetFallsBack": "error"}):
        outcomes = _all(); outcomes.update(mutate)
        assert ci_binding.evaluate("production", outcomes)[0] == "FAIL"
    outcomes = _all(); outcomes.pop("idleSoakFrameStats")
    assert ci_binding.evaluate("full", outcomes)[0] == "FAIL"
    assert ci_binding.evaluate("full", {})[0] == "NOT_RUN"


def test_summary_reads_junit_and_hashes_the_staged_candidate(tmp_path: Path):
    assets = tmp_path / "android/app/src/androidTest/assets"
    assets.mkdir(parents=True)
    (assets / "van_candidate.riv").write_bytes(b"R" * 2048)
    (assets / "forge_mode.txt").write_text("full\n", encoding="utf-8")
    outcomes = _all(); outcomes["productionAvatarPathKeepsRive"] = "skipped"
    _junit(tmp_path / "results" / "TEST-device.xml", outcomes)
    summary = ci_binding.summarise(tmp_path, tmp_path / "results", {"GITHUB_RUN_ID": "77", "GITHUB_SHA": "a" * 40})
    assert summary["mode"] == "full" and summary["result"] == "PASS"
    assert summary["candidate_sha256"] == sha256_file(assets / "van_candidate.riv")
    assert summary["github"]["run_id"] == "77"


def test_ci_gate_blocks_a_present_asset_that_did_not_pass(tmp_path: Path):
    binding = tmp_path / "van_validation.json"
    binding.write_text(json.dumps({"mode": "production", "result": "FAIL", "reasons": ["x"]}), encoding="utf-8")
    assert ci_binding.main(["gate", "--binding", str(binding)]) == 1
    binding.write_text(json.dumps({"mode": "NO_RIVE_ASSET", "result": "NO_RIVE_ASSET"}), encoding="utf-8")
    assert ci_binding.main(["gate", "--binding", str(binding)]) == 0


def test_missing_binding_passes_only_when_the_tree_has_no_asset(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert ci_binding.main(["gate", "--binding", str(tmp_path / "absent.json")]) == 0
    shipped = tmp_path / "android/app/src/main/assets/van.riv"
    shipped.parent.mkdir(parents=True)
    shipped.write_bytes(b"R" * 2048)
    assert ci_binding.main(["gate", "--binding", str(tmp_path / "absent.json")]) == 1


@pytest.fixture
def staged_repo(tmp_path: Path, monkeypatch):
    """A real git repository whose HEAD commit carries a staged core candidate."""
    repo = tmp_path / "repo"
    assets = repo / "android/app/src/androidTest/assets"
    assets.mkdir(parents=True)
    candidate = assets / "van_candidate.riv"
    candidate.write_bytes(b"CANDIDATE" * 300)
    git = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
    git("init", "-q"); git("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "stage")
    commit = git("rev-parse", "HEAD")
    sha = sha256_file(candidate)
    status = {"core_rig": {"candidate_sha256": sha, "emulator_validation": "NOT_RUN", "ci_run": None, "owner_verdict": "NONE"},
              "full_rig": {}, "production": {}}
    manifest = {"receipts": [], "ci_evidence": {}}
    saved = {}
    monkeypatch.setattr(cli, "ROOT", repo)
    monkeypatch.setattr(cli, "EVIDENCE_DIR", repo / "evidence")
    monkeypatch.setattr(cli, "load_status", lambda: status)
    monkeypatch.setattr(cli, "load_yaml", lambda: manifest)
    monkeypatch.setattr(cli, "_save", lambda m, s: saved.update(manifest=m, status=s))
    return {"repo": repo, "sha": sha, "commit": commit, "status": status, "saved": saved, "tmp": tmp_path}


def _evidence(root: Path, *, sha: str, commit: str, run_id: str = "4242", result: str = "PASS", mode: str = "core",
              with_outcome: bool = True, frames: bool = True) -> Path:
    evidence = root / "evidence-download"
    (evidence / "binding").mkdir(parents=True, exist_ok=True)
    (evidence / "binding" / "van_candidate.sha256").write_text(sha + "\n", encoding="utf-8")
    if with_outcome:
        (evidence / "binding" / "van_validation.json").write_text(json.dumps({
            "mode": mode, "candidate_sha256": sha, "result": result, "reasons": [] if result == "PASS" else ["x: failed"],
            "github": {"run_id": run_id, "sha": commit}, "tests": {}}), encoding="utf-8")
    if frames:
        (evidence / "shots" / "rive" / "core").mkdir(parents=True, exist_ok=True)
        (evidence / "shots" / "rive" / "core" / "core-state-2.png").write_bytes(b"PNG")
        (evidence / "shots" / "other").mkdir(parents=True, exist_ok=True)
        (evidence / "shots" / "other" / "unrelated.png").write_bytes(b"PNG")
    return evidence


def _record(ctx, evidence: Path, *, result: str = "PASS", run_id: str = "4242") -> int:
    return cli.main(["rive", "record-validation", "--stage", "core_rig", "--result", result,
                     "--ci-run", f"https://github.com/Vanguduza/Van/actions/runs/{run_id}",
                     "--candidate-sha", ctx["sha"], "--evidence-dir", str(evidence)])


def test_bound_pass_is_recorded_with_commit_and_only_core_frames(staged_repo):
    ctx = staged_repo
    assert _record(ctx, _evidence(ctx["tmp"], sha=ctx["sha"], commit=ctx["commit"])) == 0
    assert ctx["status"]["core_rig"]["emulator_validation"] == "PASS"
    assert ctx["saved"]["manifest"]["ci_evidence"][ctx["sha"]]["validated_commit"] == ctx["commit"]
    baseline = sorted(p.name for p in (ctx["repo"] / "evidence" / "core_baseline").iterdir())
    assert baseline == ["core-state-2.png"]


def test_mutation_fake_evidence_dir_with_only_a_sha_file_is_refused(staged_repo):
    ctx = staged_repo
    assert _record(ctx, _evidence(ctx["tmp"], sha=ctx["sha"], commit=ctx["commit"], with_outcome=False)) == 1
    assert ctx["status"]["core_rig"]["emulator_validation"] == "NOT_RUN"


def test_mutation_typed_pass_over_a_failed_run_is_refused(staged_repo):
    ctx = staged_repo
    assert _record(ctx, _evidence(ctx["tmp"], sha=ctx["sha"], commit=ctx["commit"], result="FAIL")) == 1
    assert ctx["status"]["core_rig"]["emulator_validation"] == "NOT_RUN"


def test_mutation_evidence_from_another_run_is_refused(staged_repo):
    ctx = staged_repo
    assert _record(ctx, _evidence(ctx["tmp"], sha=ctx["sha"], commit=ctx["commit"], run_id="1"), run_id="4242") == 1


def test_mutation_wrong_mode_is_refused(staged_repo):
    ctx = staged_repo
    assert _record(ctx, _evidence(ctx["tmp"], sha=ctx["sha"], commit=ctx["commit"], mode="full")) == 1


def test_mutation_commit_not_carrying_the_bytes_is_refused(staged_repo):
    ctx = staged_repo
    assert _record(ctx, _evidence(ctx["tmp"], sha=ctx["sha"], commit="f" * 40)) == 1
