"""Anti-gap pass for the Fable remediation mission (docs/audit/van-fable-whole-project-2026-09-21).

Every gap in VAN_CANONICAL_GAP_REGISTER.json was found by reading the tree. This re-reads the
tree for the artefact each closure claims, so the closure report's §13 is a command anyone can
run rather than a paragraph. A check is a file that must exist, a pattern that must (or must
not) appear in it, or a count. Behavioural evidence lives in the test suites this script names
in `SUITES`; it does not re-run them (CI does).

    python tools/audit/fable_anti_gap_check.py            # table, exit 1 on any failure
    python tools/audit/fable_anti_gap_check.py --json     # machine-readable
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# (gap, description, path, pattern or None, must_match, min_count)
Check = tuple[str, str, str, str | None, bool, int]

CHECKS: list[Check] = [
    ("GAP-F-001", "memory.remember executes in the gateway", "backend/van_gateway/command/local_executors.py", r"memory\.remember", True, 1),
    ("GAP-F-001", "memory.decision.record executes in the gateway", "backend/van_gateway/command/local_executors.py", r"memory\.decision\.record", True, 1),
    ("GAP-F-001", "owner facts are re-read before VERIFIED_SUCCESS", "backend/van_gateway/verification/production.py", r"owner-fact-readback", True, 1),
    ("GAP-F-001", "Hermes can propose owner facts", "hermes/mcp/owner_runtime_stdio.mjs", r"context_fact_candidate", True, 1),
    ("GAP-F-001", "Memory screen exists on the device", "android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt", r"fun MemoryRoute", True, 1),
    ("GAP-F-002", "reminder.create executes in the gateway", "backend/van_gateway/command/local_executors.py", r"reminder\.create", True, 1),
    ("GAP-F-002", "reminders persist their source", "backend/van_gateway/storage/db.py", r"MIGRATION_29", True, 1),
    ("GAP-F-002", "Hermes can create reminders", "hermes/mcp/owner_runtime_stdio.mjs", r"reminder_create", True, 1),
    ("GAP-F-002", "device reads reminders", "android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt", r"fun reminders\(", True, 1),
    ("GAP-F-003", "Hermes trading read routes", "backend/van_gateway/runtime_api.py", r'@router\.get\("/trading/', True, 4),
    ("GAP-F-003", "Hermes trading tools", "hermes/mcp/owner_runtime_stdio.mjs", r"trading_", True, 4),
    ("GAP-F-004", "cognition invokers exist", "trading/vati/cognition/invokers.py", r"class (NullInvoker|HttpJsonInvoker|HermesRunInvoker)", True, 3),
    ("GAP-F-004", "read model states an unconfigured invoker honestly", "trading/vati", r"MODEL_INVOKER_UNCONFIGURED", True, 1),
    ("GAP-F-005", "trading.halt executes in the gateway", "backend/van_gateway/command/local_executors.py", r"class TradingHaltExecutor", True, 1),
    ("GAP-F-005", "halt needs the owner-halt authority reference", "backend/van_gateway/command/local_executors.py", r"owner_halt_authority_ref", True, 1),
    ("GAP-F-005", "device mints the owner-halt authority", "android/app/src/main/java/com/dial/van/trading/TradingHaltAuthority.kt", None, True, 1),
    ("GAP-F-006", "Hermes browser initiators", "hermes/mcp/owner_runtime_stdio.mjs", r"browser_task_create|browser_assignment_run", True, 2),
    ("GAP-F-006", "Hermes automation initiators", "hermes/mcp/owner_runtime_stdio.mjs", r"automation_(route|execute|run_status)", True, 3),
    ("GAP-F-007", "degraded catalog is complete", "backend/van_gateway/degraded/registry.py", r"^\s+DegradedCode\.[A-Z_]+:\s*DegradedCapability\(", True, 9),
    ("GAP-F-007", "snapshot tolerates unknown codes", "backend/van_gateway/degraded/registry.py", r"CATALOG\.get\(", True, 1),
    ("GAP-F-008", "learned strategies are read back", "backend/van_gateway/learning/feed.py", r"def strategies_for", True, 1),
    ("GAP-F-008", "canonical context carries permitted strategies", "backend/van_gateway/orchestrator.py", r"permitted_strategies", True, 1),
    ("GAP-F-008", "agent-initiated mutations pass an autonomy gate", "backend/van_gateway/action/service.py", r"autonomy", True, 1),
    ("GAP-F-009", "routers check scoped internal credentials", "backend/van_gateway", r"require_scoped_internal\(", True, 6),
    ("GAP-F-010", "device maps /health.degraded", "android/app/src/main/java/com/dial/van/degraded/DegradedModeStore.kt", r"fun applyGatewayHealth", True, 1),
    ("GAP-F-010", "the bridge is bound in VanApplication", "android/app/src/main/java/com/dial/van/VanApplication.kt", r"bindGatewayHealth", True, 1),
    ("GAP-F-011", "conversation polls to a final outcome", "android/app/src/main/java/com/dial/van/control/VanCommandController.kt", r"pollUnfinishedCommands", True, 1),
    ("GAP-F-011", "device reads command status", "android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt", r"fun commandStatus", True, 1),
    ("GAP-F-011", "spoken completion goes through VoiceEdge", "android/app/src/main/java/com/dial/van/VanApplication.kt", r"VanSpokenAnswer\.speak", True, 1),
    ("GAP-F-012", "embodiment producers exist", "android/app/src/main/java/com/dial/van/visual/VanEmbodimentProducers.kt", None, True, 1),
    ("GAP-F-012", "closed trades reach the device as events", "backend/van_gateway/trading/bridge.py", r"trading\.trade\.closed", True, 1),
    ("GAP-F-013", "speech cue clock is production code", "backend/van_gateway/voice/speech_cues.py", r"class SpeechCueClock", True, 1),
    ("GAP-F-013", "device consumes cue timing", "android/app/src/main/java/com/dial/van/voice/SpeechCueTiming.kt", None, True, 1),
    ("GAP-F-013", "sherpa local TTS runtime constructs OfflineTts", "android/app/src/main/java/com/dial/van/voice/SherpaLocalTtsRuntime.kt", r"OfflineTts\(", True, 1),
    ("GAP-F-013", "sherpa PCM is played through VAN-owned AudioTrack", "android/app/src/main/java/com/dial/van/voice/SherpaLocalTtsRuntime.kt", r"AudioTrack\.Builder", True, 1),
    ("GAP-F-013", "router may select the real sherpa engine", "android/app/src/main/java/com/dial/van/voice/LocalTtsRouter.kt", r"TtsEngineKind\.SHERPA_ONNX", True, 3),
    ("GAP-F-013", "TTS output manager invokes sherpa playback", "android/app/src/main/java/com/dial/van/voice/VoiceInterfaces.kt", r"sherpa\.speak\(", True, 1),
    ("GAP-F-014", "renderer status reaches Settings", "android/app/src/main/java/com/dial/van/command/settings/SettingsRoute.kt", r"lastRendererStatus", True, 1),
    ("GAP-F-015", "contract pins the tool surface", "tests/contracts/test_owner_runtime_mcp_contract.py", r"REQUIRED_TOOLS", True, 1),
    ("GAP-F-016", "stream grant refuses without a host", "backend/van_gateway/browser/interactive_api.py", r"BROWSER_STREAM_UNCONFIGURED", True, 1),
    ("GAP-F-017", "pinned lock exists", "backend/requirements.lock", None, True, 1),
    ("GAP-F-017", "CI installs from the lock", ".github/workflows/van-ci.yml", r"requirements\.lock", True, 1),
    ("GAP-F-018", "production safety gate", "backend/van_gateway/config.py", r"def assert_production_safe", True, 1),
    ("GAP-F-018", "host qualification script", "tools/runtime/qualify_gateway_host.sh", None, True, 1),
    ("GAP-F-019", "context gaps are surfaced, not blocking", "backend/van_gateway/orchestrator.py", r"context_gaps", True, 1),
    ("GAP-F-020", "Google reads are scrubbed", "backend/van_gateway/app.py", r"_scrubbed\(", True, 5),
    ("GAP-F-021", "loopback refused in production", "backend/van_gateway/config.py", r"loopback|127\.0\.0\.1", True, 1),
    ("GAP-F-022", "contracts are a package", "tests/contracts/__init__.py", None, True, 1),
    ("GAP-F-023", "mutation job in CI", ".github/workflows/van-ci.yml", r"^  mutation:", True, 1),
    ("GAP-F-023", "instrumentation job in CI", ".github/workflows/van-ci.yml", r"^  android-instrumentation:", True, 1),
    ("GAP-F-023", "instrumentation tests exist", "android/app/src/androidTest/java/com/dial/van/instrumentation/CommandCentreLaunchTest.kt", None, True, 1),
    ("GAP-F-024", "owner revoke route", "backend/van_gateway/app.py", r"/v1/google/owner-revoke", True, 1),
    ("GAP-F-024", "device can revoke", "android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt", r"fun googleOwnerRevoke", True, 1),
    ("GAP-F-025", "one readiness predicate", "backend/van_gateway/google/mesh.py", r"EXECUTION_READY_STATES", True, 1),
    ("GAP-F-026", "critical durable routing selects Temporal", "backend/van_gateway/automation/router.py", r"ExecutionMedium\.TEMPORAL", True, 2),
    ("GAP-F-026", "gateway exposes the Temporal bridge", "backend/van_gateway/automation/temporal_bridge.py", r"class TemporalAutomationApi", True, 1),
    ("GAP-F-026", "Temporal durable workflow is implemented", "deploy/van-trading-core/temporal/workflows.py", r"class VanDurableWorkflow", True, 1),
    ("GAP-F-026", "Temporal runtime worker is implemented", "deploy/van-trading-core/temporal/runtime.py", r"Worker\(", True, 1),
    ("GAP-F-026", "Hermes can start durable workflows", "hermes/mcp/owner_runtime_stdio.mjs", r"name: 'temporal_start'", True, 1),
    ("GAP-F-027", "overlay state encrypted", "android/app/src/main/java/com/dial/van/overlay/OverlayStateStore.kt", r"EncryptedSharedPreferences\.create", True, 1),
    ("GAP-F-027", "storage policy contract", "tests/contracts/test_android_storage_policy.py", None, True, 1),
    ("GAP-F-028", "follow-ups are scheduled", "backend/van_gateway/app.py", r"proactive\.follow_ups", True, 1),

    # 2026-09-22 post-Fable product reconciliation: these were genuine owner-facing
    # omissions that the original 28-gap register did not count. Keeping them in this
    # executable anti-gap pass prevents a future closure from hiding them behind "zero
    # repository gaps".
    ("PROD-F-001", "owner can snooze an attention item through a durable backend route", "backend/van_gateway/app.py", r'/v1/attention/\{item_id\}/snooze', True, 1),
    ("PROD-F-001", "Android attention UI calls the snooze route", "android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt", r"attentionSnooze", True, 1),
    ("PROD-F-002", "overlay obstruction has a real AccessibilityService producer", "android/app/src/main/java/com/dial/van/overlay/VanObstructionAccessibilityService.kt", r"class VanObstructionAccessibilityService", True, 1),
    ("PROD-F-002", "floating overlay consumes obstruction broadcasts", "android/app/src/main/java/com/dial/van/overlay/FloatingOverlayService.kt", r"ACTION_OBSTRUCTION_STATE", True, 1),
    ("PROD-F-003", "trading history read model emits an R equity curve", "trading/vati/readmodels/active.py", r'equity_curve_r', True, 1),
    ("PROD-F-003", "trading history UI renders backend-owned curve data", "android/app/src/main/java/com/dial/van/trading/ui/HistoryScreen.kt", r"equityCurveR|equity_curve_r", True, 1),
    ("PROD-F-004", "local sherpa TTS constructs a real OfflineTts runtime", "android/app/src/main/java/com/dial/van/voice/SherpaLocalTtsRuntime.kt", r"OfflineTts\(", True, 1),
    ("PROD-F-004", "VoiceEdge gates sherpa selection on runtime self-test", "android/app/src/main/java/com/dial/van/voice/VoiceEdge.kt", r"localTtsRuntimeReady", True, 2),
    ("PROD-F-005", "critical durable work has a gateway Temporal bridge", "backend/van_gateway/automation/temporal_bridge.py", r"class TemporalAutomationApi", True, 1),
    ("PROD-F-005", "self-hosted Temporal is loopback-only and pinned", "deploy/van-trading-core/temporal/docker-compose.yml", r"127\.0\.0\.1:7233:7233", True, 1),
    ("PROD-F-005", "Temporal worker executes VanDurableWorkflow", "deploy/van-trading-core/temporal/runtime.py", r"workflows=\[VanDurableWorkflow\]", True, 1),
]

#: Behavioural evidence per gap: the suites CI runs. Listed so the report can cite them.
SUITES: dict[str, list[str]] = {
    "GAP-F-001": ["backend/tests/test_local_typed_actions.py"],
    "GAP-F-002": ["backend/tests/test_local_typed_actions.py"],
    "GAP-F-003": ["backend/tests/test_runtime_hermes_surface.py", "tests/contracts/test_owner_runtime_mcp_contract.py"],
    "GAP-F-004": ["trading/tests/test_active_trade_e2e.py"],
    "GAP-F-005": ["backend/tests/test_local_typed_actions.py", "backend/tests/test_a4_owner_approval.py"],
    "GAP-F-006": ["tests/contracts/test_owner_runtime_mcp_contract.py"],
    "GAP-F-007": ["backend/tests/test_degraded_catalog_is_exhaustive.py"],
    "GAP-F-008": ["backend/tests/test_learning_read_back.py", "backend/tests/test_action_runtime_autonomy.py"],
    "GAP-F-009": ["backend/tests/test_scoped_internal_control_reaches_routers.py"],
    "GAP-F-010": ["android/verification (GatewayDegradedMappingTest)"],
    "GAP-F-011": ["android/verification (ConversationReducerTest)"],
    "GAP-F-012": ["visual-preview (VanEmbodimentCoverageTest)", "backend/tests/test_trading_event_bridge.py"],
    "GAP-F-013": ["backend/tests/test_speech_sync.py", "android/verification (SpeechCueTimingTest, LocalTtsRouterTest)"],
    "GAP-F-023": ["van-ci mutation job", "van-ci android-instrumentation job"],
    "GAP-F-024": ["backend/tests/test_google_owner_revoke_and_scrub.py"],
    "GAP-F-027": ["tests/contracts/test_android_storage_policy.py"],
    "GAP-F-026": ["backend/tests/test_automation_hot_warm_cold.py", "tests/contracts/test_owner_runtime_mcp_contract.py"],
    "GAP-F-028": ["backend/tests/test_proactive_followups.py"],
    "PROD-F-001": ["backend/tests/test_extra_apis.py"],
    "PROD-F-002": ["android/verification (OnboardingPlanTest, OverlayVisibilityPolicyTest)"],
    "PROD-F-003": ["trading/tests/test_active_trade_e2e.py"],
    "PROD-F-004": ["android/verification/src/test/kotlin/com/dial/van/voice/VoiceAudioTest.kt", "android app compile"],
    "PROD-F-005": ["backend/tests/test_temporal_durable_runtime.py", "backend/tests/test_automation_hot_warm_cold.py"],
}


def _count(path: Path, pattern: str) -> int:
    rx = re.compile(pattern, re.M)
    if path.is_dir():
        return sum(len(rx.findall(p.read_text(encoding="utf-8", errors="replace"))) for p in path.rglob("*") if p.is_file() and p.suffix in {".py", ".kt", ".mjs", ".yml", ".sh"})
    return len(rx.findall(path.read_text(encoding="utf-8", errors="replace")))


def run() -> list[dict]:
    rows = []
    for gap, desc, rel, pattern, must, minimum in CHECKS:
        path = ROOT / rel
        if not path.exists():
            ok = (not must) and pattern is None
            detail = "missing"
        elif pattern is None:
            ok, detail = True, "present"
        else:
            n = _count(path, pattern)
            ok = (n >= max(minimum, 1)) if must else (n == 0)
            detail = f"{n} match(es)"
        rows.append({"gap": gap, "check": desc, "path": rel, "ok": ok, "detail": detail})
    return rows


def main(argv: list[str]) -> int:
    rows = run()
    failed = [r for r in rows if not r["ok"]]
    if "--json" in argv:
        print(json.dumps({"checks": rows, "failed": len(failed), "suites": SUITES}, indent=1))
    else:
        print("| Gap | Check | Path | Result |")
        print("|---|---|---|---|")
        for r in rows:
            print(f"| {r['gap']} | {r['check']} | `{r['path']}` | {'PASS' if r['ok'] else 'FAIL'} ({r['detail']}) |")
        print()
        print(f"{len(rows) - len(failed)}/{len(rows)} checks pass across {len({r['gap'] for r in rows})} gaps.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
