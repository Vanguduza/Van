from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "tools/runtime/install_van_gateway_service.sh"


def test_gateway_runtime_stages_browser_policy_governance_and_certification():
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'cp -a "$ROOT/config" "$STAGE/config"' in text
    assert 'cp -a "$ROOT/docs/decisions" "$STAGE/docs/decisions"' in text
    assert 'cp -a "$ROOT/tools/certification" "$STAGE/tools/certification"' in text


def test_gateway_runtime_keeps_decision_artifacts_in_runtime_root():
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'install -d "$STAGE/docs" "$STAGE/tools"' in text
    assert '$STAGE/backend/docs' not in text
