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
   ("van_gateway/mission/service.py",
    "verified_success=refreshed.state is MissionState.VERIFIED_SUCCESS,",
    "verified_success=True,", "C7 unverified mission counts as a success"),
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
]

survivors = []
for tests, mutations in ALL:
    print(f"\n### {tests}")
    survivors += run(mutations, tests)
print("\n================ SURVIVORS ================")
print("\n".join(survivors) or "none")
