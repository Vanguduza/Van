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
