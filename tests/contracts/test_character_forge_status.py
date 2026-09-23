from pathlib import Path
import json
import yaml
from tools.character_forge.gates import evaluate
from tools.character_forge.status import load_status, validate_status
from tools.character_forge.manifest import load_yaml, sha256_file, ROOT

def test_status_vocabulary_and_implications():
    status=load_status()
    assert validate_status(status)==[]
    manifest=load_yaml()
    assert manifest.get("baseline_sha")==status.get("baseline_sha")
    for section in ("core_rig","full_rig","production"):
        record=status.get(section) or {}
        if record.get("emulator_validation")=="PASS":
            assert record.get("ci_run"), f"{section} PASS without CI run"

def test_build_ready_never_precedes_m0():
    status=load_status()
    if status["build_ready"]: assert evaluate("m0").passed

def test_external_asset_state_is_honest_before_release():
    status=load_status()
    source=ROOT/"visual-authority"/"rive"/"van_runtime.riv"
    app=ROOT/"android"/"app"/"src"/"main"/"assets"/"van.riv"
    acceptance=ROOT/"docs"/"character_forge"/"ACCEPTANCE.yaml"
    checklist=ROOT/"docs"/"character_forge"/"DEVICE_CHECKLIST.yaml"
    release=ROOT/"visual-authority"/"rive"/"manifest.json"
    if status.get("rive_asset_ready"):
        assert source.is_file() and app.is_file()
        assert sha256_file(source)==sha256_file(app)
        assert any(a.get("sha256")==sha256_file(source) for a in load_yaml().get("artifacts",[]))
    if status.get("device_qualified"):
        data=yaml.safe_load(checklist.read_text(encoding="utf-8"))
        assert data.get("checks") and all(v=="PASS" for v in data["checks"].values())
        identity=data.get("device") or {}
        assert all(identity.get(key) for key in ("model","android_build","apk_sha256","rive_sha256","checked_at"))
        evidence=data.get("evidence") or {}
        assert all(evidence.get(name) for name in data["checks"])
    if status.get("owner_accepted"):
        data=yaml.safe_load(acceptance.read_text(encoding="utf-8"))
        assert data.get("final",{}).get("verified") is True
    if status["qual_emb_01"]=="READY":
        assert all(status.get(k) for k in ("rive_authored","rive_contract_ready","rive_runtime_ready","rive_asset_ready","device_qualified","owner_accepted"))
        assert release.is_file()
    else:
        assert status["qual_emb_01"]=="EXTERNAL_ARTEFACT"


def test_m2_refuses_unpinned_rive_cli(monkeypatch):
    from tools.character_forge import gates

    monkeypatch.setattr(gates, "m1", lambda: [])
    monkeypatch.setattr(gates, "load_status", lambda: {
        "core_rig": {
            "candidate_sha256": None,
            "emulator_validation": "NOT_RUN",
            "ci_run": None,
            "owner_verdict": "NONE",
        }
    })
    monkeypatch.setattr(gates, "load_yaml", lambda: {"artifacts": [], "receipts": []})
    monkeypatch.setattr(
        gates,
        "_yaml",
        lambda _path: {"critical_path": {"rive_cli": {"version": "UNPINNED"}}},
    )
    assert "Rive CLI authoring version is not pinned" in gates.m2()


def test_toolchain_import_rejects_placeholder_rive_version(monkeypatch, tmp_path):
    from argparse import Namespace
    from tools.character_forge import cli

    lock = tmp_path / "toolchain.lock.json"
    lock.write_text(
        '{"repository_sha":"1111111111111111111111111111111111111111",'
        '"rive_cli":{"version":"version-command-unavailable"},'
        '"inkscape":{"version":"Inkscape 1.4"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_git_head", lambda: "1111111111111111111111111111111111111111")
    writes = []
    monkeypatch.setattr(cli, "_write_yaml", lambda *args, **kwargs: writes.append(args))

    assert cli.cmd_tools_import_lock(Namespace(path=str(lock), actor="test")) == 1
    assert writes == []


def test_validation_binding_requires_exact_sha(tmp_path):
    from tools.character_forge import cli

    evidence = tmp_path / "binding"
    evidence.mkdir()
    proof = evidence / "van_candidate.sha256"
    expected = "ab" * 32
    proof.write_text(expected + "\n", encoding="utf-8")

    bound, proof_sha, root = cli._validation_binding(evidence, "van_candidate.sha256")
    assert bound == expected
    assert len(proof_sha) == 64
    assert root == evidence.resolve()


def test_validation_binding_rejects_no_asset_sentinel(tmp_path):
    from tools.character_forge import cli
    import pytest

    evidence = tmp_path / "binding"
    evidence.mkdir()
    (evidence / "van_candidate.sha256").write_text("NO_RIVE_ASSET\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not contain a SHA-256"):
        cli._validation_binding(evidence, "van_candidate.sha256")


def _write_lock(tmp_path, **overrides):
    lock = {
        "repository_sha": "1" * 40,
        "rive_cli": {"version": "1.1.1", "archive_sha256": "41684e9d99fea98e01c2c155e07ec985130b95b640410dc0fbe4ca30c271a7d5"},
        "inkscape": {"version": "Inkscape 1.2.2 (b0a8486541, 2022-12-01)"},
    }
    lock.update(overrides)
    path = tmp_path / "toolchain.lock.json"
    path.write_text(json.dumps(lock), encoding="utf-8")
    return path


def _capture_tools(monkeypatch, cli):
    written = {}
    monkeypatch.setattr(cli, "_git_head", lambda: "1" * 40)
    monkeypatch.setattr(cli, "_yaml", lambda _path: {"critical_path": {}})
    monkeypatch.setattr(cli, "_write_yaml", lambda _path, data: written.update(data))
    monkeypatch.setattr(cli, "load_status", lambda: {"blockers": []})
    monkeypatch.setattr(cli, "load_yaml", lambda: {"receipts": []})
    monkeypatch.setattr(cli, "_save", lambda *_: None)
    return written


def test_bootstrap_inkscape_lock_pins_the_version_vectors_admit_observes(monkeypatch, tmp_path):
    """CF-OPUS-002: the bootstrap records `Inkscape 1.2.2 (hash, date)`; the pin must be the
    bare version `_inkscape_version()` reads, or M1 `vectors admit` can never pass."""
    from argparse import Namespace
    from tools.character_forge import cli

    written = _capture_tools(monkeypatch, cli)
    assert cli.cmd_tools_import_lock(Namespace(path=str(_write_lock(tmp_path)), actor="test")) == 0
    assert written["critical_path"]["inkscape"]["version"] == "1.2.2"
    assert cli.normalize_inkscape_version("Inkscape 1.2.2 (b0a8486541, 2022-12-01)") == "1.2.2"


def test_toolchain_import_requires_exact_repository_sha(monkeypatch, tmp_path):
    from argparse import Namespace
    from tools.character_forge import cli

    written = _capture_tools(monkeypatch, cli)
    for bad in ("", "abc", "2" * 40):
        path = _write_lock(tmp_path, repository_sha=bad)
        assert cli.cmd_tools_import_lock(Namespace(path=str(path), actor="test")) == 1
    assert written == {}


def test_toolchain_import_refuses_unpinned_rive_release(monkeypatch, tmp_path):
    from argparse import Namespace
    from tools.character_forge import cli

    written = _capture_tools(monkeypatch, cli)
    for rive in ({"version": "1.2.0", "archive_sha256": "41684e9d99fea98e01c2c155e07ec985130b95b640410dc0fbe4ca30c271a7d5"},
                 {"version": "1.1.1", "archive_sha256": "0" * 64}):
        path = _write_lock(tmp_path, rive_cli=rive)
        assert cli.cmd_tools_import_lock(Namespace(path=str(path), actor="test")) == 1
    assert written == {}


def test_blockers_are_derived_from_truth_not_a_stale_list(monkeypatch):
    from tools.character_forge import cli

    monkeypatch.setattr(cli, "_pinned_tool", lambda name: "1.1.1" if name == "rive_cli" else "1.2.2")
    blockers = cli._current_blockers({"sources": [{"path": "x"}], "artifacts": []}, {})
    assert "RIVE_CLI_UNPINNED" not in blockers
    assert "SOURCE_SET_NOT_ADMITTED" not in blockers
    assert "OWNER_SOURCE_CONFIRMATION_PENDING" in blockers
