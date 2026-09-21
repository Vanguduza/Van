from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED = (
    "docs/trading/rev51/REV51_EXECUTION_PACK_MASTER.md",
    "docs/trading/rev51/REV51_REPOSITORY_CLOSURE.md",
    "docs/trading/rev51/packets.json",
    "tools/certification/rev51_harness.py",
    "tools/verify_build_ready.py",
    "trading/tests/test_rev51_certification.py",
    "trading/tests/test_rev51_execution_conformal.py",
    "trading/vati/execution/router.py",
    "trading/vati/risk/authority.py",
    "backend/van_gateway/session/service.py",
    "backend/van_gateway/trading/strategies.py",
    "android/app/src/main/java/com/dial/van/session/VanHermesSessionManager.kt",
    "android/app/src/main/java/com/dial/van/trading/StrategyPromotionProtocol.kt",
    "services/browser_control_agent/server.py",
    "deploy/van-browser-stream/qualify.sh",
    "evidence/van-system-audit/production_acceptance.json",
    "tests/contracts/test_closure_record_is_current.py",
)


def test_canonical_tree_sentinels_survive_integration_merges():
    missing = [p for p in REQUIRED if not (ROOT / p).is_file()]
    assert missing == []


def test_rev51_test_surface_did_not_collapse():
    tests = list((ROOT / "trading/tests").glob("test_rev51_*.py"))
    assert len(tests) >= 15
