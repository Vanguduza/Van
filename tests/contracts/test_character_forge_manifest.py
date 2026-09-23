from tools.character_forge.manifest import load_yaml, verify_records
from tools.character_forge.status import load_status

def test_character_forge_manifest_is_truthful():
    manifest=load_yaml(); status=load_status(); sources=manifest.get("sources") or []; artifacts=manifest.get("artifacts") or []
    assert verify_records(sources+artifacts)==[]
    if not sources:
        assert manifest.get("owner_confirmed_complete") is False
        assert status["build_ready"] is False

def test_owner_confirmation_cannot_exist_without_sources():
    manifest=load_yaml()
    if manifest.get("owner_confirmed_complete"):
        assert manifest.get("sources")
        assert manifest.get("owner_confirmation_date")

def test_admitted_source_set_has_no_unlisted_file():
    from tools.character_forge.manifest import iter_source_files, rel
    manifest = load_yaml()
    sources = manifest.get("sources") or []
    if not sources:
        return
    listed = {record["path"] for record in sources}
    actual = {rel(path) for path in iter_source_files()}
    assert listed == actual

def test_latest_artifact_lookup_prefers_newest():
    from tools.character_forge.manifest import find_artifact
    manifest={"artifacts":[
        {"kind":"layer_svg","sha256":"old"},
        {"kind":"layer_svg","sha256":"new"},
    ]}
    assert find_artifact(manifest,kind="layer_svg")["sha256"]=="new"


def test_every_state_changing_character_forge_command_records_provenance():
    import inspect
    from tools.character_forge import cli

    mutators = (
        cli.cmd_source_admit,
        cli.cmd_tools_import_lock,
        cli.cmd_vectors_admit,
        cli.cmd_rive_receipt,
        cli.cmd_rive_stage,
        cli.cmd_gate,
        cli.cmd_record_validation,
        cli.cmd_review,
        cli.cmd_confirm_source,
        cli.cmd_core_verdict,
        cli.cmd_integrate,
        cli.cmd_record_acceptance,
        cli.cmd_release,
    )
    missing = [
        fn.__name__
        for fn in mutators
        if "append_receipt" not in inspect.getsource(fn)
    ]
    assert missing == [], f"state-changing commands without manifest receipts: {missing}"


def test_rev2_canon_uses_rive_cli_not_editor_as_m2_authority():
    from pathlib import Path
    from tools.character_forge.manifest import ROOT

    pack = (ROOT / "docs" / "character_forge" / "VAN_CHARACTER_FORGE_DEVELOPMENT_PACK_REV_2.md").read_text(encoding="utf-8")
    tools = (ROOT / "docs" / "character_forge" / "TOOLS.yaml").read_text(encoding="utf-8")

    assert "CF-D-02 | **Rev 2.1 amendment:** the pinned Linux x86_64 Rive CLI" in pack
    assert "rive_cli:" in tools
    assert "review_lanes:" in tools
    critical = tools.split("review_lanes:", 1)[0]
    assert "rive_editor:" not in critical
