import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from mutation import run

#: Every mutation this closure pass relied on, kept so the claim "N mutations caught" can
#: be re-checked rather than believed. Run from backend/:
#:
#:     python3 ../tools/audit/mutation_suite.py
ALL = [
 # --- checkpoint 5: the mission success contract ------------------------------
 (["tests/test_command_success_contract.py", "tests/test_verification_is_performed.py"], [
   ("van_gateway/command/success_contracts.py",
    'postconditions={"kill_switch_active": True, "owner_halt_active": True},',
    'postconditions={"kill_switch_active": True},',
    "C5 drop the owner-halt claim"),
   ("van_gateway/command/mission_link.py",
    "contract_for(resolution) if resolution is not None else SuccessContract()",
    "SuccessContract()", "C5 revert the joint"),
   ("van_gateway/verification/observations.py",
    'raise ValueError(str(status.get("ledger_stale_reason") or "the VATI ledger is stale"))',
    "pass", "C5 accept a stale ledger"),
   ("van_gateway/verification/observations.py", "if _is_absent(exc):", "if True:",
    "C5 unreachable provider reads as a deletion"),
   ("van_gateway/verification/observations.py",
    '"evidence_refs": [f"ledger://kill-switch/{head}"] if active and head else [],',
    '"evidence_refs": [f"ledger://kill-switch/{head}"],',
    "C5 cite evidence on a failed halt"),
 ]),
 # --- checkpoint 6: the computer-use fabric -----------------------------------
 (["tests/test_permissions_computeruse_verifiers.py", "tests/test_automation_health_api.py"], [
   ("van_gateway/computer_use/fabric.py",
    "SURFACE_WORKERS: frozenset[Surface] = frozenset()",
    "SURFACE_WORKERS: frozenset[Surface] = frozenset(Surface)",
    "C6 pretend every surface has a worker"),
   ("van_gateway/computer_use/fabric.py",
    "        if request.surface not in self.workers:", "        if False:",
    "C6 drop the no-worker refusal"),
   ("van_gateway/app.py",
    '"/v1/automation/health", "/v1/browser/health", "/v1/computer-use/health",\n        }:\n            return ControlScope.RUNTIME',
    '"/v1/automation/health", "/v1/browser/health",\n        }:\n            return ControlScope.RUNTIME',
    "C6 health route falls through to device auth"),
 ]),
 # --- checkpoint 7: learning ---------------------------------------------------
 (["tests/test_learning_records_and_bounds.py", "tests/test_ops_backup.py"], [
   ("van_gateway/evolution/radar.py",
    'if CLASS_RANK[ActionClass(str(row["max_action_class"]))] <= ceiling',
    "if True", "C7 offer every strategy regardless of envelope"),
   ("van_gateway/evolution/radar.py",
    'if CLASS_RANK[ActionClass(str(row["max_action_class"]))] < CLASS_RANK[max_action_class]:',
    "if False:", "C7 never raise the recorded ceiling"),
   # C7's original mutation targeted `verified_success=...`, the boolean that P1-LEARN-005
   # replaced. The successor is the classification table, mutated under RC2 below.
   ("van_gateway/learning/feed.py",
    "MissionState.VERIFIED_SUCCESS: StrategyOutcome.SUCCESS,",
    "MissionState.UNVERIFIABLE: StrategyOutcome.SUCCESS,",
    "C7 an unverified mission counts as a strategy success"),
   ("van_gateway/learning/feed.py", "if not sequence:\n            return None",
    "if False:\n            return None", "C7 strategy for a mission that ran nothing"),
   ("van_gateway/app.py",
    '        jobs.append(ScheduledJob(\n            "learning.auto_demote", settings.retention_interval_seconds, _demote_regressions,\n        ))',
    "        pass", "C7 drop the auto-demote job"),
   ("van_gateway/app.py",
    '        shutil.rmtree(workspace, ignore_errors=True)\n        return {\n            "ok": report["ok"],',
    '        return {\n            "ok": report["ok"],', "C7 leave the scratch restore on disk"),
   ("van_gateway/proactive/autonomy.py",
    "MAX_EARNED_LEVEL = AutonomyLevel.S2_PREPARE",
    "MAX_EARNED_LEVEL = AutonomyLevel.S5_MAINTAIN_DOMAIN",
    "C7 raise the earned-autonomy cap to the top"),
   ("van_gateway/learning/feed.py",
    'rows = await self.store.fetchall(\n            "SELECT capability_id FROM mission_activities',
    'await self.store.execute("UPDATE domain_trust SET owner_granted_ceiling = ?", ("S3",))\n'
    '        rows = await self.store.fetchall(\n            "SELECT capability_id FROM mission_activities',
    "C7 a learning module writes an authority table"),
 ]),
 # --- checkpoint 8: owner memory ----------------------------------------------
 (["tests/test_owner_memory_has_a_producer.py"], [
   ("van_gateway/mission/service.py",
    "            await self.learning.record_mission_opened(mission, now_ms=now)",
    "            pass", "C8 stop observing the goal"),
   ("van_gateway/learning/feed.py",
    "if mission.authority_envelope.requires_owner_presence:", "if True:",
    "C8 ordinary use recorded as a decision"),
   ("van_gateway/learning/feed.py", "                inferred_reason=None,",
    '                inferred_reason="the owner usually approves this",',
    "C8 infer a reason the owner never gave"),
   ("van_gateway/mission/service.py",
    "            await self.learning.record_decision_outcome(refreshed, state=refreshed.state)",
    "            pass", "C8 never record the decision outcome"),
   ("van_gateway/understanding/memory.py",
    "\"WHERE status = 'ACTIVE' AND latest_observed_ms < ?\"",
    "\"WHERE status = 'ACTIVE' AND latest_observed_ms >= ?\"",
    "C8 sweep the goals just mentioned"),
   ("van_gateway/app.py",
    '        jobs.append(ScheduledJob(\n            "understanding.mark_stale_intents", settings.retention_interval_seconds,\n            _mark_stale_intents,\n        ))',
    "        pass", "C8 drop the stale-intent sweep"),
 ]),
 # --- review corrections: semantic closure -------------------------------------
 # Every one of these is a counterexample in which the implementation looked green while
 # the owner's requested real-world outcome was false. Four of them describe defects that
 # were shipped and closed before an independent review found them.
 (["tests/test_command_success_contract.py", "tests/test_learning_records_and_bounds.py",
   "tests/test_owner_memory_has_a_producer.py"], [
   ("van_gateway/command/success_contracts.py",
    "    if action_id in _NOTEBOOK_SOURCE_ACTIONS:", "    if False:",
    "RC1 a source mutation falls back to the notebook contract"),
   ("van_gateway/command/success_contracts.py",
    '"sources_absent": [] if must_be_present else names,', '"sources_absent": [],',
    "RC1 a delete stops asserting the sources are gone"),
   ("van_gateway/command/success_contracts.py",
    '"sources_present": names if must_be_present else [],', '"sources_present": [],',
    "RC1 an add stops asserting the sources are there"),
   ("van_gateway/verification/observations.py",
    "            if not _is_absent(exc):\n                raise\n            absent.append(name)",
    "            absent.append(name)",
    "RC1 an unreachable provider reads as a removed source"),
   ("van_gateway/verification/production.py",
    '            raise ValueError(\n                "success contract names no notebook_id and source_names to read back"\n            )',
    "            return await observations.notebook_enterprise_readback(knowledge, str(postconditions.get('notebook_id') or 'x'))",
    "RC1 the source verifier falls back to the weaker notebook observation"),
   ("van_gateway/learning/feed.py",
    "MissionState.CANCELLED: StrategyOutcome.INCONCLUSIVE,",
    "MissionState.CANCELLED: StrategyOutcome.FAILURE,",
    "RC2 an owner cancellation punishes the strategy"),
   ("van_gateway/learning/feed.py",
    "MissionState.UNVERIFIABLE: StrategyOutcome.INCONCLUSIVE,",
    "MissionState.UNVERIFIABLE: StrategyOutcome.FAILURE,",
    "RC2 'VAN does not know' punishes the strategy"),
   ("van_gateway/learning/feed.py",
    "MissionState.BLOCKED_POLICY: StrategyOutcome.INCONCLUSIVE,",
    "MissionState.BLOCKED_POLICY: StrategyOutcome.FAILURE,",
    "RC2 a policy refusal punishes the strategy"),
   ("van_gateway/evolution/radar.py",
    "        if outcome is StrategyOutcome.INCONCLUSIVE:", "        if False:",
    "RC2 inconclusive falls through to failure_count"),
   ("van_gateway/learning/feed.py",
    "MissionState.FAILED: StrategyOutcome.FAILURE,",
    "MissionState.FAILED: StrategyOutcome.INCONCLUSIVE,",
    "RC2 a real failure stops counting"),
   ("van_gateway/understanding/memory.py",
    "        if observations >= self.STANDING_AFTER_OBSERVATIONS:",
    "        if observations >= 1:",
    "RC4 one request becomes a standing goal again"),
   ("van_gateway/understanding/memory.py",
    "            current=IntentHorizon.EPHEMERAL,\n            observations=1,",
    "            current=IntentHorizon.STANDING,\n            observations=1,",
    "RC4 a brand-new goal starts standing"),
   ("van_gateway/understanding/memory.py",
    '            return IntentHorizon.STANDING, "the owner stated this is a standing goal"',
    "            return IntentHorizon.EPHEMERAL, None",
    "RC4 the owner saying so stops counting"),
 ]),
 # --- checkpoint 11: the recovery matrix ---------------------------------------
 (["tests/test_recovery_matrix.py"], [
   ("van_gateway/idempotency/service.py",
    'and now - int(row["updated_at_unix"]) >= STALE_CLAIM_SECONDS', "and True",
    "C11 release a claim the instant it is taken"),
   ("van_gateway/idempotency/service.py",
    'row["status"] == IdempotencyStatus.IN_FLIGHT.value\n                    and row["request_hash"] == req_hash',
    'row["request_hash"] == req_hash', "C11 a COMPLETED answer is retaken as work"),
   ("van_gateway/idempotency/service.py",
    '                    and row["request_hash"] == req_hash\n', "",
    "C11 retake a stale claim under a different request"),
   ("van_gateway/idempotency/service.py",
    "claim_count = claim_count + 1", "claim_count = claim_count",
    "C11 hide that a claim was recovered"),
   ("van_gateway/idempotency/service.py",
    '"UPDATE idempotency SET updated_at_unix = ?, "',
    '"UPDATE idempotency SET created_at_unix = ?, "',
    "C11 do not reset the lease when retaking"),
   ("van_gateway/mission/service.py",
    "        if current in TERMINAL_STATES:", "        if False:",
    "C11 accept a duplicate terminal callback"),
   ("van_gateway/mission/service.py",
    "        if target not in LEGAL_TRANSITIONS[current]:", "        if False:",
    "C11 accept a duplicate non-terminal callback"),
   ("van_gateway/mission/service.py",
    "        if expected is not None and expected is not current:", "        if False:",
    "C11 a racing writer with a stale expectation clobbers the state"),
   ("van_gateway/command/mission_link.py",
    "        if existing is not None:\n            return existing",
    "        if False:\n            return existing",
    "C11 open a second mission for a command that already has one"),
   ("van_gateway/learning/feed.py",
    "ON CONFLICT(outcome_id) DO UPDATE SET", "ON CONFLICT(outcome_id) DO NOTHING -- ",
    "C11 a replayed outcome row duplicates"),
   ("van_gateway/approval/service.py",
    'if int(record.get("expires_at_unix", 0)) <= now:', "if False:",
    "C11 an expired approval challenge can still be signed"),
   ("van_gateway/approval/service.py",
    'if device is None or device["revoked_at_unix"] is not None:', "if device is None:",
    "C11 a revoked device approves an A4 action"),
 ]),
 # --- checkpoint 9: evolution --------------------------------------------------
 (["tests/test_external_reality_and_benchmarks.py"], [
   ("van_gateway/research/exa.py", "            if source.title:", "            if False:",
    "C9 stop recording what sources claim"),
   ("van_gateway/research/exa.py", "                    contradicts_owner_belief=False,",
    "                    contradicts_owner_belief=True,",
    "C9 decide the owner is wrong from a headline"),
   ("van_gateway/research/exa.py", "                    confidence=0.0,",
    "                    confidence=0.9,", "C9 untrusted source looks credible"),
   ("van_gateway/evolution/radar.py",
    "    SUITES_WITH_A_CORPUS: frozenset[str] = frozenset()",
    "    SUITES_WITH_A_CORPUS: frozenset[str] = frozenset(SUITES)",
    "C9 claim every suite has a corpus"),
   ("van_gateway/evolution/radar.py", "            if not record.admissible:", "            if False:",
    "C9 admit a technology with no benchmark"),
 ]),
 # --- checkpoint 13: owner context lifecycle governance -----------------------
 (["tests/test_context_lifecycle_governance.py"], [
   ("van_gateway/context/lifecycle.py", '"truncated": held > len(exported),',
    '"truncated": False,', "C13 hide that the export was cut short"),
   ("van_gateway/context/lifecycle.py", "            stores[entry.table] = {",
    "            if entry.table != \"owner_facts\":\n                continue\n            stores[entry.table] = {",
    "C13 export only the store that was already exportable"),
   ("van_gateway/context/service.py", "                    candidate.supersedes_fact_id,\n",
    "                    None,\n", "C13 drop the fact supersession link again"),
   ("van_gateway/context/service.py",
    "candidate.sensitivity.value, revision, candidate.supersedes_edge_id,",
    "candidate.sensitivity.value, revision, None,",
    "C13 drop the edge supersession link again"),
   ("van_gateway/context/lifecycle.py",
    "                superseded_by_fact_id=replaced_by.get(record.fact_id),",
    "                superseded_by_fact_id=None,",
    "C13 lose the forward direction of the chain"),
   ("van_gateway/context/lifecycle.py",
    "                if r.valid_until_ms is not None and r.superseded_by_fact_id is None",
    "                if r.valid_until_ms is not None",
    "C13 report a correction as a withdrawal"),
   ("van_gateway/context/lifecycle.py",
    "            ORDER BY valid_from_ms DESC, revision DESC", "            ORDER BY rowid ASC",
    "C13 order history by insertion instead of belief"),
   ("van_gateway/context/lifecycle.py",
    "            if loose.state is ReadinessState.CONFLICTED:", "            if False:",
    "C13 stop reporting inference-only contradictions"),
   ("van_gateway/context/lifecycle.py",
    "                    subject=subject, predicate=predicate, scope=scope, allow_inferred=False",
    "                    subject=subject, predicate=predicate, scope=scope, allow_inferred=True",
    "C13 report inference conflicts as blocking"),
   ("van_gateway/context/lifecycle.py", '            "sides": sides,',
    '            "sides": [s["fact_id"] for s in sides],',
    "C13 report ids without the values that disagree"),
   ("van_gateway/app.py",
    '            result="ok", device_id=device_id, capability="context.export",',
    '            result="ok", device_id=device_id, capability="context.read",',
    "C13 bulk read of the owner graph leaves no matching trace"),
 ]),
]

#: Mutations against files outside backend/ — the workflow, the Gradle scripts — checked by
#: contract tests that run from the repository root. Kept separate rather than folded into
#: ALL because both the mutation root and pytest's working directory differ.
ROOT_LEVEL = [
 # --- checkpoint 12: the APK leaves CI ----------------------------------------
 (["tests/contracts/test_the_apk_leaves_ci.py",
   "tests/contracts/test_ci_workflow_is_what_it_claims.py"], [
   (".github/workflows/van-ci.yml",
    """      - name: Upload debug APK
        uses: actions/upload-artifact@v4
        with:
          name: van-debug-apk
          path: android/app/build/outputs/apk/debug/*.apk
          if-no-files-found: error
""", "", "C12 drop the APK upload entirely"),
   (".github/workflows/van-ci.yml", "if-no-files-found: error\n      - name: Shared visual",
    "if-no-files-found: warn\n      - name: Shared visual",
    "C12 publish an empty artefact instead of failing"),
   (".github/workflows/van-ci.yml", "path: android/app/build/outputs/apk/debug/*.apk",
    "path: android/app/build/outputs/apk/release/*.apk",
    "C12 point the upload at a variant the build never assembles"),
   (".github/workflows/van-ci.yml",
    "./gradlew :app:testDebugUnitTest :app:assembleDebug :app:lintDebug",
    "./gradlew :app:testDebugUnitTest :app:lintDebug",
    "C12 stop assembling the APK but keep uploading it"),
   ("android/settings.gradle.kts", 'include(":app")', 'include(":application")',
    "C12 rename the module out from under the artifact path"),
   ("android/app/build.gradle.kts", 'id("com.android.application")',
    'id("com.android.library")', "C12 a module that emits an AAR, not an APK"),
 ]),
]

ROOT = pathlib.Path(__file__).resolve().parents[2]

survivors = []
for tests, mutations in ALL:
    print(f"\n### {tests}")
    survivors += run(mutations, tests)
for tests, mutations in ROOT_LEVEL:
    print(f"\n### {tests}")
    survivors += run(mutations, tests, root=ROOT, cwd=ROOT)
print("\n================ SURVIVORS ================")
print("\n".join(survivors) or "none")
