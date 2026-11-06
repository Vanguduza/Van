"""Refresh reviewed owner contracts from immutable pre-closure input and real source.

This performs no deployment or provider request. Final qualification is supplied
separately after the parent whole-workspace checks; absent receipts stay pending.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from export_owner_endpoints import export
from registry_sources import (Refresh, digest, load, save, refresh_endpoints, verify_freeze,
                              freeze_files, endpoint_frontend_access, service_endpoint)

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "docs/audit/validation/registry-before-2026-10-08-closure"
ANDROID = "android/app/src/main/java/com/dial/van/"
BACKEND = "backend/van_gateway/"
SURFACES = {
    "OF-MISSION-002": ("van.work.mission", "van.work.mission-control"),
    "OF-DECISION-001": ("van.attention", "van.attention.decision"),
    "OF-MEMORY-002": ("van.memory.privacy", "van.memory.record"),
    "OF-LEARNING-003": ("van.learning.goals",),
    "OF-AUTHORITY-001": ("van.permissions", "van.permissions.grant"),
    "OF-AUTOMATION-001": ("van.automation.library", "van.automation.intent", "van.automation.plan"),
    "OF-BROWSER-001": ("van.browser.interactive", "van.browser.action-plan"),
    "OF-BROWSER-003": ("van.browser.interactive", "van.browser.action-plan"),
    "OF-BROWSER-004": ("van.browser.interactive", "van.browser.downloads"),
    "OF-VOICE-001": ("van.voice.turn",),
    "OF-VOICE-002": ("van.settings.voice", "van.settings.speaker-profile"),
}

# Each anchor is a reviewed production entry. Exact gateway declarations and
# invocations are regenerated independently by RegistrySources.
ENTRIES = {
    ANDROID+"gateway/VanGatewayClient.kt": r"^class VanGatewayClient\(",
    ANDROID+"VanApplication.kt": r"^class VanApplication\b",
    ANDROID+"command/attention/AttentionRoute.kt": r"^fun AttentionRoute\(",
    ANDROID+"command/work/WorkRoute.kt": r"^fun WorkRoute\(",
    ANDROID+"command/work/MissionControls.kt": r"^internal fun MissionControls\(",
    ANDROID+"command/settings/PermissionsRoute.kt": r"^fun PermissionsRoute\(",
    ANDROID+"command/owner/OwnerServiceRoutes.kt": r"^fun AutomationServicesRoute\(",
    ANDROID+"memory/MemoryRoute.kt": r"^fun MemoryRoute\(",
    ANDROID+"memory/UnderstandingRoutes.kt": r"^fun UnderstandingRoute\(",
    ANDROID+"memory/GoalsRoute.kt": r"^fun GoalsRoute\(",
    ANDROID+"memory/MemoryManagement.kt": r"^internal fun MemoryPrivacyDialog\(",
    ANDROID+"browser/BrowserActivity.kt": r"^class BrowserActivity\b",
    ANDROID+"browser/BrowserSessionController.kt": r"^class BrowserSessionController\(",
    ANDROID+"browser/BrowserPhoneActions.kt": r"^class BrowserPhoneActions\(",
    ANDROID+"browser/BrowserTransferClient.kt": r"^class BrowserTransferClient\(",
    ANDROID+"browser/BrowserDownloadsPanel.kt": r"^fun BrowserDownloadsPanel\(",
    ANDROID+"browser/BrowserDownloadReview.kt": r"^object BrowserDownloadReview\b",
    ANDROID+"browser/BrowserFileProvider.kt": r"^object BrowserFileProvider\b",
    ANDROID+"browser/BrowserFileProvidersPanel.kt": r"^fun BrowserFileProvidersPanel\(",
    ANDROID+"voice/VoiceAssetInstaller.kt": r"^object VoiceAssetInstaller\b",
    ANDROID+"voice/EmbeddedVoiceAssetInstaller.kt": r"^object EmbeddedVoiceAssetInstaller\b",
    ANDROID+"voice/OfflineVoiceTurn.kt": r"^class OfflineVoiceTurn\(",
    ANDROID+"voice/SpeakerEnrollmentPanel.kt": r"^fun SpeakerEnrollmentPanel\(",
    ANDROID+"voice/SpeakerEnrollmentManager.kt": r"^class SpeakerEnrollmentManager\(",
    ANDROID+"voice/SpeakerEnrollmentPolicy.kt": r"^object SpeakerEnrollmentPolicy\b",
    ANDROID+"voice/SpeakerProfileStore.kt": r"^class SpeakerProfileStore\(",
    ANDROID+"voice/SherpaSpeakerSimilarity.kt": r"^class SherpaSpeakerSimilarityScorer\(",
    ANDROID+"command/modules/SpeechModule.kt": r"^internal fun SpeechModule\(",
    ANDROID+"command/CommandCentreActivity.kt": r"^class CommandCentreActivity\b",
    ANDROID+"control/VanCommandController.kt": r"^class VanCommandController\(",
    BACKEND+"automation/worker_runtime.py": r"^class AutomationWorkerRuntime:",
    BACKEND+"automation/standing_runner.py": r"^class StandingRunProducer:",
    BACKEND+"app.py": r"^def create_app\(",
}


def cite(file: str, pattern: str) -> dict:
    lines = (ROOT/file).read_text().splitlines()
    found = [n for n, line in enumerate(lines, 1) if re.search(pattern, line)
             and not line.lstrip().startswith(("//", "*"))]
    if len(found) != 1:
        raise RuntimeError((file, pattern, found))
    return {"file": file, "line": found[0], "ref": "WORKSPACE_PATCH",
            "sha256": digest(ROOT/file), "review_scope": "Reviewed current production entry."}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--final-source-manifest", type=Path)
    parser.add_argument("--android-receipt", type=Path)
    args = parser.parse_args()
    if bool(args.final_source_manifest) != bool(args.android_receipt):
        raise ValueError("Supply both final source manifest and Android receipt, or neither")
    endpoint_doc = export()
    schemas = endpoint_doc.pop("schemas")
    endpoints = {(e["method"], e["path"]): e for e in endpoint_doc["endpoints"]}
    features, screens = (load(BASE/(name+".json")) for name in ("owner_features", "owner_screens"))
    by_feature = {row["id"]: row for row in features["features"]}
    by_screen = {row["id"]: row for row in screens["screens"]}

    def ref(method, path, symbol=None):
        real = endpoints[method, path]
        return {"method": method, "path": path, "endpoint_id": real["endpoint_id"],
                "authentication": real["authentication"], "registration": real["registration"],
                "device_proof_required_when_bound": real["device_proof_required_when_bound"],
                "frontend_access": endpoint_frontend_access(real["authentication"]),
                "source_ref": real["source"], "client_function": symbol, "client_symbol": symbol,
                "client_namespace": "VanGatewayClient" if symbol else None,
                "client_source_status": "declared" if symbol else "NO_ANDROID_CLIENT_REQUIRED",
                "client_citations": [], "android_callsites": []}

    def function(fid, suffix, action, citations, routes, gate):
        return {"id": fid+":"+suffix, "owner_action": action,
                "status": "SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED",
                "source_citations": [cite(file, pattern) for file, pattern in citations],
                "endpoint_ids": [endpoints[method, path]["endpoint_id"] for method, path, _ in routes],
                "authority_gate": gate}

    def amend(fid, suffix, action, citations, routes, gate, extra_screens=()):
        feature = by_feature[fid]
        new_function = function(fid, suffix, action, citations, routes, gate)
        new_function["acceptance_contract"] = {
            "happy": "Perform the owner interaction and verify its exact matching independent readback within the stated authority and evidence contract.",
            "error": "Expose the concrete authentication, scope, stale identity, provider or effect refusal; preserve the reviewed input without reporting success.",
            "recovery": "Read the immutable request/record/effect identity after an uncertain reply; repeat only supported exact recovery without broadening authority or repeating an unobserved effect.",
            "device_execution_status": "UNVERIFIED"}
        surface_ids = list(dict.fromkeys([*SURFACES[fid], *extra_screens]))
        for sid in surface_ids:
            if sid not in feature["screen_ids"]:
                feature["screen_ids"].append(sid)
                feature["required_screen_ids"] = copy.deepcopy(feature["screen_ids"])
            if fid not in by_screen[sid]["feature_ids"]:
                by_screen[sid]["feature_ids"].append(fid)
        for row in [feature, *[by_screen[sid] for sid in surface_ids]]:
            functions = row["current_implementation"]["functions"]
            functions[:] = [f for f in functions if f["id"] != new_function["id"]]
            functions.append(copy.deepcopy(new_function))
            for method, path, symbol in routes:
                found = next((e for e in row["endpoint_refs"] if (e["method"], e["path"]) == (method, path)), None)
                if found is None:
                    row["endpoint_refs"].append(ref(method, path, symbol))
                elif symbol:
                    found.update(ref(method, path, symbol))

    def scope(fid, notes, categories=()):
        feature = by_feature[fid]
        for row in [feature, *[by_screen[sid] for sid in feature["screen_ids"]]]:
            row["integration_gaps" if row is feature else "gaps"] = list(notes)
            row["gap_categories"] = list(dict.fromkeys([*categories, "PHYSICAL_ACCEPTANCE"]))
            row["functional_wiring_status"] = ("EXTERNAL_CONTRACT_OR_ASSET_REQUIRED" if "UPSTREAM_CONTRACT_MISSING" in categories else "SOURCE_WIRED_REQUIRES_ACCEPTANCE")
            row["current_coverage_status"] = "implemented"
            row.pop("unsupported_function_contracts", None)
            row["supported_scope_limitations"] = list(notes)

    def hosted(sid, title, fid, component, file, pattern, host, kind="inline_section", activity=False):
        if sid in by_screen:
            return
        template = by_screen["van.memory.privacy" if not activity else "van.browser.downloads"]
        row = copy.deepcopy(template)
        for key in ("historical_source_state", "proposed_route", "unavailable_owner_controls", "missing_presentation_fields"):
            row.pop(key, None)
        row.update(id=sid, title=title, owner_goal=by_feature[fid]["owner_goal"], route=None,
                   interaction_kind=kind, component=component, feature_ids=[fid], endpoint_refs=[],
                   android_callsites=[], owner_endpoint_ids=[], service_endpoint_ids=[], external_endpoint_ids=[],
                   source_citations=[cite(file, pattern)], route_citations=[],
                   current_implementation={"status": "CURRENT_SOURCE_WIRING_REVIEWED_DEVICE_UNVERIFIED",
                                           "source_citations": [cite(file, pattern)], "functions": [], "verification": {}},
                   baseline_coverage_status="missing", baseline_acceptance_states={},
                   baseline_provenance={"scope": "Newly implemented hosted control; absent from the original source inventory."},
                   current_coverage_status="implemented", frontend_integration_status="OWNER_CONTROLS_SOURCE_IMPLEMENTED")
        row.pop("host_route" if activity else "host_activity", None)
        row["host_activity" if activity else "host_route"] = host
        row["actions"], row["information"] = [], []
        by_screen[sid] = row
        screens["screens"].append(row)
        by_feature[fid]["screen_ids"].append(sid)
        by_feature[fid]["required_screen_ids"] = copy.deepcopy(by_feature[fid]["screen_ids"])

    hosted("van.attention.decision", "Exact owner choice and evidence", "OF-DECISION-001", "OwnerDecisionCard",
           ANDROID+"command/attention/OwnerDecisionCard.kt", r"^internal fun OwnerDecisionCard\(", "attention")
    hosted("van.work.mission-control", "Mission dispatch fence and direction receipt", "OF-MISSION-002", "MissionExecutionControls",
           ANDROID+"command/work/MissionExecutionControls.kt", r"^internal fun MissionExecutionControls\(", "work")
    hosted("van.memory.record", "Exact retained record and erasure scope", "OF-MEMORY-002", "DerivedMemoryRecordDialog",
           ANDROID+"memory/DerivedMemoryRecordsSection.kt", r"^private fun DerivedMemoryRecordDialog\(", "memory", "modal")
    hosted("van.permissions.grant", "Exact bounded owner consent", "OF-AUTHORITY-001", "OwnerPermissionGrantSection",
           ANDROID+"command/settings/OwnerPermissionGrantSection.kt", r"^internal fun OwnerPermissionGrantSection\(", "settings/permissions")
    hosted("van.automation.plan", "Automation candidate, admission and exact run evidence", "OF-AUTOMATION-001", "OwnerAutomationPlansSection",
           ANDROID+"command/owner/OwnerAutomationPlansSection.kt", r"^internal fun OwnerAutomationPlansSection\(", "owner/automation")
    hosted("van.browser.action-plan", "Immutable browser effect review and observation", "OF-BROWSER-003", "BrowserActionPlansPanel",
           ANDROID+"browser/BrowserActionPlansPanel.kt", r"^fun BrowserActionPlansPanel\(", "com.dial.van.browser.BrowserActivity", "modal", True)
    hosted("van.browser.file-provider", "Exact owner file destination, admission and result", "OF-BROWSER-004", "BrowserFileProvidersPanel",
           ANDROID+"browser/BrowserFileProvidersPanel.kt", r"^fun BrowserFileProvidersPanel\(", "com.dial.van.browser.BrowserActivity", "modal", True)
    hosted("van.settings.speaker-profile", "Local owner speaker consent, capture and erasure", "OF-VOICE-002", "SpeakerEnrollmentPanel",
           ANDROID+"voice/SpeakerEnrollmentPanel.kt", r"^fun SpeakerEnrollmentPanel\(", "settings/voice")

    command = [("POST", "/v1/commands", "dispatchCommand")]
    record_routes = [("GET", "/v1/context/records", "contextRecords"),
                     ("GET", "/v1/context/records/{store}/{record_id}", "contextRecord")]
    amend("OF-MEMORY-002", "inspect-record", "Inspect paginated exact records, screened fields and declared/observed/inferred provenance",
          [(ANDROID+"memory/DerivedMemoryRecordsSection.kt", r"^internal fun DerivedMemoryRecordsSection\("),
           (BACKEND+"understanding/records.py", r"^class OwnerRecords:")], record_routes,
          "Current hardware-bound owner read; allowlisted store, complete stable identity, bounded page; no mutation or execution grant.")
    amend("OF-MEMORY-002", "export-record", "Copy an independently reread screened bounded representation of the selected exact record",
          [(ANDROID+"memory/DerivedMemoryRecordsSection.kt", r"^private fun DerivedMemoryRecordDialog\(")],
          [("GET", "/v1/context/records/{store}/{record_id}/export", "exportContextRecord")],
          "Exact store/id/revision readback; credentials withheld and content limits disclosed; revision commits to complete stored scope.")
    amend("OF-MEMORY-002", "erase-record", "Review affected record counts and request fresh biometric erasure of precisely that revision",
          [(BACKEND+"context/memory_erasure.py", r"^async def erase_memory\("),
           (ANDROID+"memory/DerivedMemoryRecordsSection.kt", r"^private fun DerivedMemoryRecordDialog\(")],
          [("GET", "/v1/context/records/{store}/{record_id}/erasure-plan", "contextRecordErasurePlan"), *command],
          "Exact memory.erase A4 biometric command binds store/record/revision including existing dependent rows; stale or expanded scope refuses. Terminal command success requires independent captured-identity absence/readback; work/audit are intentionally retained.")
    scope("OF-MEMORY-002", ["Per-record inspection, bounded screened export and exact immutable A4 erasure are supplied for all twelve forgettable stores. New/changed dependencies refuse stale approval; independent readback preserves unrelated rows. Direct DELETE remains refused. Physical privacy, biometric and restart acceptance remains unverified."])

    amend("OF-LEARNING-003", "producer-state", "Inspect actual independent read-time producer status, bounds, timestamps and evidence",
          [(ANDROID+"memory/LearningProducerSection.kt", r"^internal fun LearningProducerSection\("),
           (BACKEND+"learning/observations.py", r"^class ObservedLearning:")],
          [("GET", "/v1/understanding/learning/producers", "learningProducers")],
          "Owner read; READY/NO_DATA/PARTIAL/DEGRADED with unknown counts on failure. No daemon-running or service-readiness claim, and no execution grant.")
    amend("OF-LEARNING-003", "observed-pattern", "Inspect bounded repeated-choice candidates, counterexamples and independent outcome references",
          [(BACKEND+"learning/observations.py", r"^class ObservedLearning:")],
          [("GET", "/v1/understanding/decisions", "decisionHistory")],
          "At least three distinct actual owner observations in the same typed context. Legacy rows need a matching approved owner command; answers match immutable retained source. Missing, malformed, stale or duplicate evidence stays unmeasured; reasons are never guessed.")
    amend("OF-LEARNING-003", "external-comparison", "Compare an exact cited structured source claim with the current matching owner declaration",
          [(BACKEND+"knowledge/evidence.py", r"^class KnowledgeEvidenceStore:"),
           (BACKEND+"learning/observations.py", r"^async def record_external_claim\(")],
          [("GET", "/v1/external-reality", "externalReality")],
          "Atomic actual provider evidence/projection; exact digest and claim/scope match; source trust preserved. At most200 comparisons, stale/missing inputs unmeasured, confidence0 and owner review only; disagreement never rewrites either side.")
    scope("OF-LEARNING-003", ["Observed decision and structured external comparison producers are implemented with deterministic bounded evidence and recovery. Empty/unbound provider feeds remain NO_DATA or PARTIAL; candidates are advisory and neither declarations nor patterns prove future model compliance."], ["EXTERNAL_PROVIDER"])

    amend("OF-DECISION-001", "typed-choice", "Read and answer an exact owner choice with evidence, expiry, note and immutable recovery identity",
          [(ANDROID+"command/attention/OwnerDecisionCard.kt", r"^internal fun OwnerDecisionCard\("),
           (BACKEND+"decisions/service.py", r"^class DecisionService:")],
          [("GET", "/v1/decisions/{decision_id}", "decision"), ("POST", "/v1/decisions/{decision_id}/answer", "answerDecision")],
          "Admitted owner proof, exact decision/revision/choice/request; stale, expired, conflicting or revoked answer refuses. Fresh retained answer readback settles uncertain replies. Answer grants no action authority.")
    scope("OF-DECISION-001", ["Actual typed detail, listed choices, source-labelled references, expiry, immutable answer and recovery are wired. The first authorized answer and its learning fingerprint commit together. A choice is a judgment and does not substitute for cryptographic action approval."])

    control = [("GET", "/v1/missions/{mission_id}/control", "missionControl"),
               ("GET", "/v1/missions/{mission_id}/control/requests/{request_id}", "missionControlRequest")]
    for operation in ("pause", "resume", "direction"):
        amend("OF-MISSION-002", operation, "Request exact mission "+operation+" and independently recover its ordered control receipt",
              [(ANDROID+"command/work/MissionExecutionControls.kt", r"^internal fun MissionExecutionControls\("),
               (BACKEND+"mission/control.py", r"^class MissionExecutionControlService:")],
              [*control, ("POST", "/v1/missions/{mission_id}/"+operation, "writeMissionControl")],
              "Current owner proof, exact request hash/generation, durable dispatch fence and run-bound ordered worker checkpoint. Pause blocks new effects; resume/direction retain existing authority. process_stopped_verified=false and authority_granted=false; already-dispatched work may finish.")
    scope("OF-MISSION-002", ["Durable pause/resume/direction requests, exact recovery and run-bound ordered Hermes checkpoints are implemented. The fence prevents new gateway/browser/automation effects; it does not prove an already running external OS process stopped. Direction applies at the next admitted worker checkpoint without widening authority."], ["DEPLOYMENT"])

    amend("OF-AUTHORITY-001", "grant-exact-consent", "Select a supported action and review bounded exact scope, expiry and maximum uses before A4 approval",
          [(ANDROID+"command/settings/OwnerPermissionGrantSection.kt", r"^internal fun OwnerPermissionGrantSection\("),
           (BACKEND+"capability/owner_permissions.py", r"^async def grant_owner_permission\(")],
          [("GET", "/v1/permissions/contracts", "permissionContracts"), *command],
          "Fresh owner A4 biometric command binds allowlisted action, exact parameters, expiry and use limit. Consent only narrows required gates; service credentials, native action approval and mission fencing remain mandatory.")
    amend("OF-AUTHORITY-001", "inspect-consent-use", "Inspect the exact stored grant and independent use/remaining-scope readback; revoke it explicitly",
          [(ANDROID+"command/settings/OwnerPermissionGrantSection.kt", r"^internal fun PermissionGrantDetailDialog\("),
           (BACKEND+"capability/owner_permissions.py", r"^async def enforce_permission_scope\(")],
          [("GET", "/v1/permissions/grants/{grant_id}", "permissionGrant"), ("POST", "/v1/permissions/{grant_id}/revoke", "revokePermission")],
          "Owner read/revocation; actual enforcement rechecks exact scope, uses, expiry/revocation before each effect. Grant readback alone never proves an action occurred.")
    scope("OF-AUTHORITY-001", ["Exact owner permission creation, inspection/use enforcement and revocation are implemented alongside S0..S4 domain ceilings. Unsupported actions/scopes refuse; consent never creates service authority or removes fresh native approval requirements."])

    automation_routes = [("GET", "/v1/owner/automation/contracts", "automationContracts"),
                         ("POST", "/v1/owner/automation/plans", "proposeAutomationPlan"),
                         ("GET", "/v1/owner/automation/plans", "automationPlans"),
                         ("GET", "/v1/owner/automation/plans/{artifact_id}", "automationPlan"),
                         ("GET", "/v1/owner/automation/requests/{idempotency_key}", "automationPlanRequest")]
    amend("OF-AUTOMATION-001", "owner-plan", "Prepare a bounded typed IR candidate, recover the exact artifact and review its declared deployment limitations",
          [(ANDROID+"command/owner/OwnerAutomationPlansSection.kt", r"^internal fun OwnerAutomationPlansSection\("),
           (BACKEND+"automation/owner_api.py", r"^class OwnerAutomationApi:")], automation_routes,
          "Current owner proof and immutable request hash; candidate creates no standing authority or deployed worker. Supported closed typed contracts only; configuration/input content is data, never a shell or inferred credential.")
    amend("OF-AUTOMATION-001", "bounded-dsl", "Review deterministic supported branches, mappings, preconditions and independent success predicates",
          [(BACKEND+"automation/dsl.py", r"^def evaluate\("), (BACKEND+"automation/dsl.py", r"^def map_fields\(")],
          [("GET", "/v1/owner/automation/contracts", "automationContracts")],
          "Bounded closed JSON DSL; unsupported expressions, cycles, missing variables, ambiguous branches and unsealed capability effects refuse before external effect. Selected branch manifest and exact target readback determine result.")
    amend("OF-AUTOMATION-001", "exact-run", "Request only an admitted immutable artifact with pinned inputs and inspect actual run/step evidence",
          [(ANDROID+"command/owner/OwnerAutomationPlansSection.kt", r"^internal fun OwnerAutomationPlansSection\("),
           (BACKEND+"automation/worker_runtime.py", r"^class AutomationWorkerRuntime:")],
          [("GET", "/v1/owner/automation/runs/{run_id}", "automationRun"), *command],
          "Native admission/execution approval seals artifact/revision/input hash. Current canonical parent/helper manifests, single-use steps and per-target policy apply; permission hints cannot authorize VAN_CAPABILITY writes or arbitrary external writes.")
    scope("OF-AUTOMATION-001", ["Owner candidate/recovery, bounded branches/mappings/predicates and exact admitted run inspection are implemented. Actual n8n helpers, credentials, current manifests and provider canaries must be bound/read back on the authorized host. Unsupported arbitrary code and unsealed external capability writes remain refused by the closed contract."], ["DEPLOYMENT", "EXTERNAL_PROVIDER"])

    plan_routes = [("GET", "/v1/browser/interactive-sessions/{session_id}/action-plans", "browserActionPlans"),
                   ("POST", "/v1/browser/interactive-sessions/{session_id}/action-plans", "createBrowserActionPlan"),
                   ("GET", "/v1/browser/interactive-sessions/{session_id}/action-plans/{plan_id}", "browserActionPlan"),
                   ("POST", "/v1/browser/interactive-sessions/{session_id}/action-plans/{plan_id}/cancel", "cancelBrowserActionPlan")]
    browser_citations = [(ANDROID+"browser/BrowserActionPlansPanel.kt", r"^fun BrowserActionPlansPanel\("),
                         (BACKEND+"browser/action_plans.py", r"^class BrowserActionPlanService:")]
    for fid in ("OF-BROWSER-001", "OF-BROWSER-003"):
        amend(fid, "immutable-effect-plan", "Prepare an actual browser task, review exact click/fill effects and observe the sealed result without re-actuation",
              browser_citations, [*plan_routes, *command],
              "Foreground signed A3 task preparation binds observed hostname, expires within30s and forbids stale replay; draft gives no authority. Current profile_mutation_permitted and gateway_authorized_only contract required. Fresh native A4 biometric seals immutable plan/target/epoch/revision and typed result predicates. Single-use claim precedes dispatch; uncertain effect is observed, never re-actuated.", ("van.browser.interactive",))
        scope(fid, ["Bounded browser mutation plans, click/fill results and exact cancellation fencing are implemented. Current native target/profile/producer and private stream/control hosts must be observed. A draft or successful transport does not prove mutation, closure or provider effect; arbitrary unsealed mutation remains refused."], ["DEPLOYMENT", "EXTERNAL_PROVIDER"])
    amend("OF-BROWSER-004", "native-file-operation", "Inspect native file analysis and exact import operation readbacks, with bound hash/epoch and provider limits",
          [(ANDROID+"browser/BrowserActivity.kt", r"^class BrowserActivity\b"),
           (BACKEND+"browser/interactive_api.py", r"^def build_interactive_router\(")],
          [("GET", "/v1/browser/interactive-sessions/{session_id}/downloads/{download_id}/operations", "browserFileOperations"),
           ("POST", "/v1/browser/interactive-sessions/{session_id}/transfer-grants", "interactiveBrowserTransferGrant")],
          "Exact owner-selected file identity, content hash, purpose, target and current producer epoch. Download/open/analysis/import are separate operations; provider contracts with bound=false/executable=false stay unavailable. Native text analysis does not promote untrusted content to authority.", ("van.browser.interactive", "van.browser.downloads"))
    amend("OF-BROWSER-004", "open-in-van", "Open independently verified selected bytes in VAN's bounded inert native viewer",
          [(ANDROID+"browser/BrowserPhoneActions.kt", r"^class BrowserPhoneActions\("),
           (ANDROID+"browser/BrowserInertFileDialog.kt", r"^fun BrowserInertFileDialog\(")],
          [("POST", "/v1/browser/interactive-sessions/{session_id}/transfer-grants", "interactiveBrowserTransferGrant")],
          "Exact selected download hash/size/target/epoch and verified local bytes; closed safe MIME viewer only. Content is not executed or promoted to authority; temporary preview bytes are deleted when dismissed.")
    amend("OF-BROWSER-004", "external-file-contract", "Read current archive/candidate provider capability, exact admitted destination and unavailable/refused states",
          [(BACKEND+"browser/artifact_admission.py", r"^class OwnerArtifactAdmissionService:"),
           (ANDROID+"browser/BrowserFileProvider.kt", r"^object BrowserFileProvider\b"),
           (ANDROID+"browser/BrowserDownloadsPanel.kt", r"^fun BrowserDownloadsPanel\(")],
          [("GET", "/v1/browser/interactive-sessions/{session_id}/file-provider-contracts", "browserFileProviderContracts")],
          "Current owner/session read. Default UNAVAILABLE; configured is insufficient. The exact attested provider principal, namespace, admission signer and current capability must agree before preparation is offered. Source implementation does not prove the proposed Oracle/VEKL target exists or is production qualified.", ("van.browser.file-provider",))
    provider_requests = [("POST", "/v1/browser/interactive-sessions/{session_id}/file-provider-requests", "createBrowserFileProviderRequest"),
                         ("GET", "/v1/browser/interactive-sessions/{session_id}/file-provider-requests", "browserFileProviderRequests"),
                         ("GET", "/v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}", "browserFileProviderRequest"),
                         ("POST", "/v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/cancel", "cancelBrowserFileProviderRequest")]
    provider_citations = [(ANDROID+"browser/BrowserFileProvidersPanel.kt", r"^fun BrowserFileProvidersPanel\("),
                          (ANDROID+"browser/BrowserFileProvider.kt", r"^object BrowserFileProvider\b"),
                          (BACKEND+"browser/artifact_admission.py", r"^class OwnerArtifactAdmissionService:")]
    amend("OF-BROWSER-004", "provider-draft", "Prepare and independently recover the exact immutable file/destination request before any provider effect",
          provider_citations, provider_requests,
          "Current hardware-bound owner/session, exact source hash/size/producer identity, current qualified destination namespace and bounded deadline. Draft creation grants no provider authority; uncertain replies recover the same idempotency key and digest. Only an unsubmitted DRAFT is offered for fencing in Android.", ("van.browser.file-provider",))
    amend("OF-BROWSER-004", "provider-admission", "Approve the exact file request with fresh native A4 and inspect separately admitted provider claim and persisted-byte evidence",
          provider_citations+[(BACKEND+"auth/provider_transport.py", r"^class ProviderTransportAuthenticator:"),
                              (BACKEND+"authority/descriptor.py", r"^ACTION_REVERSIBILITY:.*=")],
          [*command, ("POST", "/v1/browser/artifact-provider/admissions/{admission_id}/introspect", None),
           ("POST", "/v1/browser/artifact-provider/admissions/{admission_id}/claim", None),
           ("GET", "/v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}", "browserFileProviderRequest")],
          "Irreversible external write; no remote rollback or deletion contract is offered. Native browser.file.provider.submit A4 seals exactly session_id/request_id/request_sha256 with freshness <=30 seconds. Independent provider HTTPS/TLS-verified current certificate pin and exact provider/owner/project authority authorize signed admission introspection and atomic one-use claim; owner or static internal bearer credentials cannot replace them. Exactly one protected write; success requires matching actual claim and independent persisted-byte readback. Unknown effects are read, never re-actuated; untrusted file contents grant no execution or truth promotion.", ("van.browser.file-provider",))
    amend("OF-BROWSER-004", "provider-observation", "Explicitly check an already claimed external byte receipt after an uncertain effect without resubmitting or changing the original outcome",
          [(BACKEND+"browser/artifact_admission.py", r"^    async def observe\(self,\*,session_id,owner_device_id,request_id\):"),
           (ANDROID+"browser/BrowserFileProvider.kt", r"^object BrowserFileProvider\b"),
           (ANDROID+"browser/BrowserFileProvidersPanel.kt", r"^fun BrowserFileProvidersPanel\(")],
          [("GET", "/v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/observation", "browserFileProviderObservation")],
          "Current exact owner/session/request/digest and previously claimed admission within its existing five-minute read-only observation scope. Observe actual independent provider bytes or STILL_UNKNOWN. No renewed write authority, no old canonical UNKNOWN/UNVERIFIABLE promotion, no replacement-fence release and no automatic retry; missing receipt never proves absence.", ("van.browser.file-provider",))
    scope("OF-BROWSER-004", ["Native file inspection, inert preview, bounded analysis and exact readback are wired. Owner provider catalog/draft/recovery, canonical native A4 admission, separate attested mTLS claim/introspection and independently verified byte receipts are implemented. The proposed Oracle/VEKL production target remains unbound/unqualified; defaults are UNAVAILABLE and current capability/bindings must be supplied before owner preparation/execution. Host cleanup and actual phone byte/provider effects still require independent acceptance."], ["DEPLOYMENT", "EXTERNAL_PROVIDER"])
    amend("OF-VOICE-001", "embedded-generic-voice", "Use automatically installed generic local acoustic assets and retain honest engine/fallback readiness without phone configuration",
          [(ANDROID+"voice/VoiceAssetInstaller.kt", r"^object VoiceAssetInstaller\b"),
           (ANDROID+"voice/EmbeddedVoiceAssetInstaller.kt", r"^object EmbeddedVoiceAssetInstaller\b"),
           (ANDROID+"voice/VoiceEdge.kt", r"^class VoiceEdge\("),
           (ANDROID+"VanApplication.kt", r"^class VanApplication\b")], [],
          "Compiled APK manifest pin, streamed exact file size/SHA validation and atomic private-directory publication on IO. Runtime model preparation and actual readiness are separate from declared files; missing/corrupt/unusable models cannot become READY. Bind local models only between owner turns. Generic wake/ASR/TTS/phrase assets provide no enrolled owner speaker identity or action authority; no remote model URL or owner profile is fabricated.")
    amend("OF-VOICE-001", "bounded-local-endpointing", "End the selected local Sherpa recognition turn on actual EnergyVadGate speech/silence or explicit bounded no-speech/maximum-duration state",
          [(ANDROID+"voice/WakeRuntime.kt", r"^class EnergyVadGate\("),
           (ANDROID+"voice/OfflineVoiceTurn.kt", r"^class OfflineVoiceTurn\("),
           (ANDROID+"voice/VoiceInterfaces.kt", r"^class VoiceInputManager\(")], [],
          "Actual bounded PCM/sample-clock EnergyVadGate endpointing when the local Sherpa primary is selected. Unused declared neural VAD is not READY. Current turn/recognizer binding, cancellation and late-final rejection remain required; no acoustic observation proves speaker enrollment, owner identity or permission.")
    amend("OF-VOICE-002", "local-owner-enrollment", "Enroll or replace the exact device-local owner profile using dedicated biometric consent and three actual microphone clips",
          [(ANDROID+"voice/SpeakerEnrollmentPanel.kt", r"^fun SpeakerEnrollmentPanel\("),
           (ANDROID+"voice/SpeakerEnrollmentManager.kt", r"^class SpeakerEnrollmentManager\("),
           (ANDROID+"voice/SpeakerEnrollmentPolicy.kt", r"^object SpeakerEnrollmentPolicy\b"),
           (ANDROID+"voice/SherpaSpeakerSimilarity.kt", r"^class SherpaSpeakerModel private constructor\(")], [],
          "Dedicated one-use hardware-backed strong-biometric signature with van.local-speaker-profile purpose binds operation, exact current fresh remote hardware/approval/device/owner binding, pinned model digest, prior profile revision, nonce and <=30-second consent. Microphone permission and exclusive audio ownership are required. Three bounded 16kHz PCM16 clips must pass real energy/DC/clipping checks and finite consistent native embeddings before normalized encrypted commit/readback. Raw clips remain in memory and are wiped; generic assets, energy checks and speaker similarity grant no command/action authority.")
    amend("OF-VOICE-002", "local-profile-readback", "Read local profile/model readiness and permit revocable similarity evidence only for the exact fresh current owner binding",
          [(ANDROID+"voice/SpeakerEnrollmentPanel.kt", r"^fun SpeakerEnrollmentPanel\("),
           (ANDROID+"voice/SpeakerEnrollmentManager.kt", r"^class SpeakerEnrollmentManager\("),
           (ANDROID+"voice/SpeakerProfileStore.kt", r"^class SpeakerProfileStore\("),
           (ANDROID+"voice/SherpaSpeakerSimilarity.kt", r"^class SherpaSpeakerSimilarityScorer\(")], [],
          "Authenticated encrypted store readback checks closed envelope, model digest, normalized exact-dimension embedding, recorded quality/consent metadata and exact current remote owner binding. Generic model readiness is separate from profile presence. Missing/corrupt/stale/revoked/unbound state makes evidence inconclusive; each score freshly checks the owner binding off the UI thread. Similarity never authenticates a command or replaces native consequential-action approval.")
    amend("OF-VOICE-002", "local-profile-erasure", "Erase precisely the retained encrypted profile after dedicated biometric consent, including when the backend is unreachable",
          [(ANDROID+"voice/SpeakerEnrollmentPanel.kt", r"^fun SpeakerEnrollmentPanel\("),
           (ANDROID+"voice/SpeakerEnrollmentManager.kt", r"^class SpeakerEnrollmentManager\("),
           (ANDROID+"voice/SpeakerEnrollmentPolicy.kt", r"^object SpeakerEnrollmentPolicy\b"),
           (ANDROID+"voice/SpeakerProfileStore.kt", r"^class SpeakerProfileStore\(")], [],
          "Fresh <=30-second one-use REMOVE consent seals the exact authenticated stored revision/model/binding. Offline removal compares genuine local device/hardware/approval key fingerprints without inventing a fresh remote owner principal or binding. Changed local key, revision, expired/malformed signature or replay refuses. Synchronous encrypted removal is independently read back absent and existing scorer revoked; cancellation discards only pending consent/capture and does not erase the previous profile.")
    scope("OF-VOICE-002", ["Local enrollment/replace/readiness/erasure controls and generic native extraction are source implemented. Actual owner capture/profile, speaker discrimination, microphone permissions/audio arbitration, device cryptography and physical acoustic quality remain unverified. Speaker similarity is revocable evidence only; owner speech corrections remain explicit declarations and cannot confer action authority."], ["ACOUSTIC_ASSET_QUALIFICATION"])
    voice_limits = ["Generic APK acoustic delivery, exact integrity/atomic installation, selected local recognition and actual EnergyVadGate endpointing are source implemented. Dedicated actual owner enrollment/replace/readiness/erasure source is supplied; no owner profile or recording has been fabricated. Runtime readiness is observable and separate from acoustic accuracy: native constructors/decode smoke do not qualify wake/ASR/speaker performance. Physical acoustic, model performance and signed owner-release qualification remain pending."]
    for row in [by_feature["OF-VOICE-001"], *[by_screen[sid] for sid in by_feature["OF-VOICE-001"]["screen_ids"]]]:
        row["integration_gaps" if row is by_feature["OF-VOICE-001"] else "gaps"] = list(voice_limits)
        row["supported_scope_limitations"] = list(voice_limits)
        row["gap_categories"] = ["ACOUSTIC_ASSET_QUALIFICATION", "PHYSICAL_ACCEPTANCE"]
        row["functional_wiring_status"] = "SOURCE_WIRED_REQUIRES_ACCEPTANCE"
        row["voice_runtime_contract"] = {"generic_asset_delivery": "COMPILED_APK_MANIFEST_PIN_AND_ATOMIC_IO_INSTALL",
            "local_endpointing": "ACTUAL_ENERGY_VAD_AND_BOUNDED_PCM_TURN", "unused_neural_vad_ready": False,
            "owner_speaker_enrollment_available": True, "owner_embedding_fabricated": False,
            "actual_owner_profile_observed": False, "acoustic_model_accuracy_qualification": "UNVERIFIED",
            "generic_models_grant_owner_identity": False, "physical_acoustic_qualification": "UNVERIFIED"}
    for row in [by_feature["OF-VOICE-002"], *[by_screen[sid] for sid in by_feature["OF-VOICE-002"]["screen_ids"]]]:
        row["speaker_profile_contract"] = {"implementation": "LOCAL_ENROLL_REPLACE_READBACK_ERASE_SOURCE_IMPLEMENTED",
            "consent_purpose": "van.local-speaker-profile", "consent_max_age_ms": 30_000,
            "required_clips": 3, "capture_sample_rate_hz": 16_000, "capture_duration_ms": 3_000,
            "stored_raw_audio": False, "store": "ENCRYPTED_PRIVATE_PROFILE_WITH_EXACT_REVISION_READBACK",
            "enrollment_binding": "FRESH_CURRENT_REMOTE_OWNER_HARDWARE_AND_APPROVAL_KEYS",
            "offline_erasure_binding": "GENUINE_LOCAL_DEVICE_HARDWARE_AND_APPROVAL_KEYS_ONLY",
            "speaker_similarity_grants_action_authority": False, "actual_owner_profile_observed": False,
            "speaker_discrimination_qualification": "UNVERIFIED", "physical_capture_qualification": "UNVERIFIED"}
    for operation in ("pause", "resume", "direction"):
        by_feature["OF-MISSION-002"].setdefault("owner_controls", []).append({
            "id": operation, "ui_status": "SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED",
            "interaction": "Exact generation/request-bound "+operation,
            "endpoint": "/v1/missions/{mission_id}/"+operation,
            "backend_effect": "Durable dispatch fence or ordered direction checkpoint; no wider authority or independently verified OS stop."})
    for row in [by_feature["OF-BROWSER-004"], *[by_screen[sid] for sid in by_feature["OF-BROWSER-004"]["screen_ids"]]]:
        row["functional_wiring_status"] = "EXTERNAL_CONTRACT_OR_ASSET_REQUIRED"
        row["current_coverage_status"] = "partial"
        row["external_provider_contract"] = {"implementation": "CORE_ADMISSION_AND_TYPED_PROVIDER_CONSUMER_SOURCE_IMPLEMENTED", "production_target_bound": False,
                                             "production_target_qualified": False, "owner_execution_available": False,
                                             "default_state": "UNAVAILABLE", "configured_is_qualified": False,
                                             "runtime_execution_contract": "CONDITIONAL_ON_CURRENT_ATTESTED_TARGET_CAPABILITY_AND_NATIVE_A4",
                                             "provider_authentication": "DEDICATED_CURRENT_PINNED_MTLS_AND_SIGNED_EXACT_ADMISSION",
                                             "owner_action": {"action_id": "browser.file.provider.submit", "action_class": "A4",
                                                              "exact_parameters": ["session_id", "request_id", "request_sha256"],
                                                              "max_age_seconds": 30}}
    information = {
        "OF-MISSION-002": ["current dispatch fence/generation", "exact immutable request hash and direction", "run-bound ordered worker acknowledgement", "existing command/action authority", "already-dispatched work may finish; process_stopped_verified=false"],
        "OF-DECISION-001": ["listed stable choices and proposed labels", "exact owner note/revision/expiry", "REFERENCE_ONLY versus RECORDED_EVENT evidence", "immutable answer/recovery identity; grants_action_authority=false"],
        "OF-MEMORY-002": ["privacy-safe stable record identity", "declared/observed/inferred/mixed/unclassified provenance", "screened bounded fields/export", "complete stored-scope revision digest", "affected store counts/dependent identities", "retained work/audit and independent erased-identity readback"],
        "OF-LEARNING-003": ["independent READY/NO_DATA/PARTIAL/DEGRADED producers", "bounded observations/comparisons and unmeasured counts", "timestamps/snapshot digest/source references", "candidate support/counterexamples/unknown outcomes", "original external trust and exact scope disagreement", "advisory inference with no execution grant"],
        "OF-AUTHORITY-001": ["supported action contracts/exact parameter scope", "expiry/max uses and remaining-use enforcement", "fresh native approval/separate service authority", "stored grant/use/revoke readback"],
        "OF-AUTOMATION-001": ["supported closed IR/DSL and deployment requirements", "immutable candidate request/artifact/revision", "pinned admitted helper/parent manifests and inputs", "selected/skipped/refused step receipts", "preconditions/independent target predicates", "actual provider/worker configuration status"],
        "OF-BROWSER-001": ["current native target/hostname/profile/producer epoch", "owner-prepared task/immutable plan", "exact effect parameters/observed predicates", "claimed/uncertain/observed result without re-actuation"],
        "OF-BROWSER-003": ["foreground A3 task preparation", "fresh native biometric A4 plan approval", "current profile_mutation_permitted/gateway_authorized_only posture", "exact click/fill parameters/step observations", "cancellation fence/retained result"],
        "OF-BROWSER-004": ["exact file hash/size/type/producer epoch", "safe inert local preview", "bounded source-labelled native analysis", "exact operation result/recovery", "external provider bound/executable/qualified status; unbound imports unavailable", "immutable provider request/idempotency key/digest/deadline", "current exact provider/owner/project destination", "fresh native A4 challenge and approval state", "actual one-use provider claim and independent persisted-byte receipt", "explicit OBSERVED_EXTERNAL_EFFECT versus STILL_UNKNOWN observation; original canonical outcome/fence retained", "UNKNOWN remains read-only; no content execution or truth promotion"],
        "OF-VOICE-001": ["actual generic bundle/install/runtime readiness", "selected recognition/TTS engine and offline fallback", "actual EnergyVadGate endpointing for local PCM turns", "permission/no-speech/timeout/cancel/late-final states", "declared assets are separate from prepared usable models and acoustic accuracy", "actual owner speaker enrollment controls available; owner profile absent until real capture", "generic models grant no owner identity or action authority"],
        "OF-VOICE-002": ["generic speaker model readiness separate from authenticated profile presence", "current full owner/device/hardware/approval binding", "dedicated local consent operation/revision/model/freshness", "current clip phrase/index/energy quality/progress", "encrypted normalized embedding and retained consent metadata; no stored raw PCM", "inconclusive stale/unbound speaker evidence; no action authority", "exact offline erasure using genuine local keys and absence readback"],
    }
    acceptance = {
        "OF-MISSION-002": {"happy": "Read current generation, submit exact pause/resume/direction and recover the ordered matching receipt; preserve false process-stop/authority flags.", "error": "Stale generation/conflicting request/revoked owner/mismatched worker binding refuses without widening authority.", "offline": "Recover the original immutable request receipt after reconnect; do not duplicate direction or manufacture a fresh generation."},
        "OF-DECISION-001": {"happy": "Read listed choices/evidence/expiry, answer exact revision and independently confirm the retained choice/note/request without an action grant.", "error": "Unknown choice/stale revision/expiry/concurrent conflicting answer refuses with the pending exact input preserved.", "offline": "Recover original decision/request readback; retry only the same supported immutable answer."},
        "OF-MEMORY-002": {"happy": "Inspect screened fields/provenance/export, review affected records and obtain fresh biometric A4 erasure; settle only independent identity absence while unrelated records remain.", "stale": "Changed content/new dependency refuses approved revision; refresh exact plan and obtain new approval.", "error": "Invalid/foreign/missing identity or failed readback stays explicit; transport/zero count alone never proves erasure."},
        "OF-LEARNING-003": {"happy": "Show actual read-time producer status, bounded source evidence and advisory candidates/comparisons, separate from verified truth or authority.", "empty": "NO_DATA means no observations; PARTIAL means incomplete valid evidence; neither means failed reads or proved absence of contradictions.", "error": "One failed producer becomes independently DEGRADED with unknown counts; preserve available other evidence.", "stale": "Expired/malformed sources remain unmeasured; no current preference or external truth is inferred."},
        "OF-AUTHORITY-001": {"happy": "Review allowlisted exact scope/expiry/max uses/native gates, obtain A4 approval and read actual grant/use/revoke result.", "error": "Unsupported/exhausted/expired/revoked scope or absent native/service authority refuses before effect.", "stale": "Old grants cannot bypass current exact per-effect proof/device revocation/mission fencing."},
        "OF-AUTOMATION-001": {"happy": "Read exact candidate/contracts, admit observed immutable deployment and request pinned execution; selected/skipped/refused steps settle only independent target predicates.", "error": "Unsupported expression/ambiguous branch/missing input/precondition/stale artifact/unbound provider refuses visibly before effect.", "offline": "Recover exact request/artifact/run; accepted submission is not completion and uncertain writes never repeat automatically."},
        "OF-BROWSER-001": {"happy": "Prepare target-bound task, review immutable plan, obtain native A4 approval and independently observe every permitted result.", "error": "Changed target/epoch/revision, unlisted effect, spent claim or predicate mismatch refuses without repeating mutation.", "offline": "Recover original plan/effect result; uncertainty never re-actuates click/fill."},
        "OF-BROWSER-003": {"happy": "Native A3/A4 review and control handoff preserve current target/epoch/profile mutation posture; terminal result needs exact observed predicates.", "cancelled": "Cancellation fences remaining starts and retains dispatched/uncertain results; it does not prove an external process stopped.", "offline": "Recover original handoff/plan result; unknown effect stays unknown and never re-actuates."},
        "OF-BROWSER-004": {"happy": "Only selected files leave phone; native preview/analysis requires exact byte/effect readback. Qualified provider execution requires independently recovered immutable draft, exact fresh native A4, separate current attested mTLS atomic claim and independently matching persisted bytes; unbound/unqualified targets stay unavailable.", "error": "MIME/size/hash/epoch, namespace/signer/capability/pin mismatch, stale or spent admission, revoked owner/mission, failed readback or unavailable target preserves exact identity without a provider success claim.", "offline": "Recover the same request/idempotency key/operation and target receipt; explicitly check an already claimed receipt within the existing read-only observation window. OBSERVED_EXTERNAL_EFFECT does not upgrade old canonical UNKNOWN/UNVERIFIABLE or release its replacement fence. Missing receipt remains STILL_UNKNOWN; effects never repeat automatically. Acceptance is insufficient for saved/analyzed or truth-promoted status."},
        "OF-VOICE-001": {"happy": "Automatically verify/install actual generic APK assets, prepare engines and bind only between owner turns; observe actual selected local/offline readiness before wake, bounded recognition and spoken output. Generic models do not establish owner speaker identity.", "error": "Missing/corrupt manifest or model, permission refusal, failed runtime preparation, network-required fallback, no speech and maximum duration remain explicit; unused neural VAD is not READY.", "offline": "Use only currently usable local engines or text fallback. Cold start/restart rechecks exact bundled bytes; failed partial installs never publish or claim READY.", "cancelled": "Cancel the current unsubmitted turn and reject late recognition without changing its provenance; already submitted work retains its mission controls."},
        "OF-VOICE-002": {"happy": "Review the exact local consent, authenticate with strong biometrics, capture three actual usable clips and independently read back the encrypted normalized profile under its fresh current owner/model binding. Dedicated REMOVE consent independently verifies absence; speaker similarity remains evidence only.", "error": "Missing permission/model/current binding, changed key/revision, expired or replayed biometric consent, unusable PCM/inconsistent embeddings, corrupt encrypted data or failed commit/readback stays explicit and inconclusive.", "offline": "Enrollment and scoring require current remote binding; offline backend failure does not fabricate it. Exact privacy removal remains available using actual matching local keys and authenticated stored revision without remote principal invention.", "cancelled": "Cancel consent/capture and reject late samples/results; wipe temporary microphone/vector buffers. Previous profile is retained unless exact fresh REMOVE consent has independently completed."},
    }
    for fid, fields in information.items():
        feature = by_feature[fid]
        for row in [feature, *[by_screen[sid] for sid in SURFACES[fid]]]:
            row["information"] = list(dict.fromkeys([*row["information"], *fields]))
            row.setdefault("historical_pre_oct8_acceptance", copy.deepcopy(row.get("required_acceptance_states", row.get("acceptance_states", {}))))
            if row is feature:
                row["required_acceptance_states"].update(acceptance[fid])
            else:
                for state, expected in acceptance[fid].items():
                    current = row["acceptance_states"].get(state)
                    if isinstance(current, dict):
                        current.update(expected=expected, verification="CURRENT_SOURCE; PHYSICAL_UNVERIFIED")
    # Browser parent carries the union of supported controls and their host limits.
    by_screen["van.browser.interactive"]["gaps"] = list(dict.fromkeys([*by_feature["OF-BROWSER-003"]["integration_gaps"], *by_feature["OF-BROWSER-004"]["integration_gaps"]]))
    by_screen["van.browser.interactive"]["gap_categories"] = ["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]
    by_screen["van.browser.interactive"]["functional_wiring_status"] = "EXTERNAL_CONTRACT_OR_ASSET_REQUIRED"
    by_screen["van.browser.interactive"]["current_coverage_status"] = "partial"
    by_screen["van.browser.downloads"]["unavailable_owner_controls"] = [
        "Production Oracle/VEKL import until its exact target contract, binding and independent host qualification exist."]
    by_screen["van.browser.file-provider"]["information"] = [
        "reviewed file identity/hash/size", "exact provider/owner/project destination", "current target capability/availability",
        "immutable request/digest/idempotency key/deadline", "fresh exact native A4 challenge/biometric outcome",
        "request status and original recovery identity", "actual provider claim and independently observed persisted-byte receipt",
        "explicit read-only observation separate from retained canonical outcome and replacement fence",
        "untrusted file source; no content execution or owner/project truth promotion"]
    by_screen["van.settings.speaker-profile"]["information"] = list(information["OF-VOICE-002"])
    by_screen["van.settings.speaker-profile"]["actions"] = [
        "Enroll owner voice or replace retained profile after dedicated native strong biometric consent",
        "Allow microphone and observe actual current phrase, clip index and sample progress",
        "Cancel pending consent or capture without replacing or erasing the existing profile",
        "Read current model/profile readiness with exact binding and encrypted-store readback",
        "Erase the exact local profile after separate fresh cryptographic consent and verify absence"]
    by_screen["van.settings.speaker-profile"]["test_tags"] = [
        "speaker-enrollment-panel", "speaker-enroll", "speaker-readiness", "speaker-erase",
        "speaker-cancel-capture", "speaker-capture-progress", "speaker-microphone-permission"]

    # Preserve historical evidence before replacing current validation claims.
    all_rows = features["features"] + screens["screens"]
    anchors = load(ROOT/"tools/audit/owner_registry_reviewed_anchors.json")
    def prepare_anchors(value):
        if isinstance(value, dict):
            if {"file", "line", "ref"} <= set(value) and value["ref"] == "WORKSPACE_PATCH":
                pattern = ENTRIES.get(value["file"])
                if value["file"] == ANDROID+"memory/MemoryManagement.kt" and value["line"] < 50:
                    pattern = r"^internal fun FactHistoryDialog\("
                if pattern:
                    anchors[value["file"]+":"+str(value["line"])] = {"pattern": pattern,
                        "review_scope": "Reviewed current module entry; endpoint calls regenerated independently."}
            for key, child in value.items():
                if not key.startswith(("baseline", "historical")):
                    prepare_anchors(child)
        elif isinstance(value, list):
            for child in value:
                prepare_anchors(child)
    prepare_anchors(all_rows)
    refresh = Refresh(anchors)
    refresh.scan_calls(all_rows)
    real_by_id = {e["endpoint_id"]: e for e in endpoint_doc["endpoints"]}
    for row in all_rows:
        old = row["current_implementation"].get("verification")
        if old:
            row["current_implementation"].setdefault("historical_validation", {})["pre_oct8_closure"] = copy.deepcopy(old)
        row["current_implementation"]["verification"] = {
            "android_compile": "PENDING_FINAL_SOURCE_BOUND_VALIDATION",
            "jvm_behavior_tests": "PENDING_FINAL_SOURCE_BOUND_VALIDATION",
            "backend_integration": "PENDING_FINAL_WHOLE_WORKSPACE_VALIDATION",
            "device_live": "UNVERIFIED", "deployment_live": "UNVERIFIED",
            "scope": "Current source review; prior test results remain historical. No production/provider/handset qualification."}
        refresh_endpoints(row, real_by_id, refresh)
        refresh.walk(row)
        row["owner_endpoint_ids"] = [ref["endpoint_id"] for ref in row["endpoint_refs"] if not service_endpoint(ref["authentication"])]
        row["service_endpoint_ids"] = [ref["endpoint_id"] for ref in row["endpoint_refs"] if service_endpoint(ref["authentication"])]
        if row["service_endpoint_ids"]:
            row["service_access_rule"] = "Service-to-service scope only; never put an internal token in Android or use Android to establish an attested provider principal. Owner controls use admitted signed owner paths or safe projections; provider claims require their separate current pinned mTLS identity and exact admission."
        row["live_acceptance"] = "UNVERIFIED_IN_THIS_AUDIT"
        row["acceptance_evidence_status"] = "Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified."
        for function in row["current_implementation"]["functions"]:
            row["actions"] = list(dict.fromkeys([*row["actions"], function["owner_action"]]))
        if not row["information"]:
            row["information"] = copy.deepcopy(by_feature[row["feature_ids"][0]]["information"])
    if refresh.unresolved:
        save(ROOT/"docs/audit/validation/registry-refresh-unresolved-2026-10-08.json", list(refresh.unresolved.values()))
        raise RuntimeError("Unresolved current source citations: "+str(len(refresh.unresolved)))

    # Current source findings supersede old missing-contract labels without
    # deleting their historical description.
    screens.setdefault("historical_oct7_findings", copy.deepcopy(screens["findings"]))
    closed = {"remote-mission-control-contract", "autonomous-browser-mutation-plan", "general-standing-permission-writer", "unsupported-automation-dsl", "unproduced-learning-inference"}
    screens["findings"] = [finding for finding in screens["findings"] if finding["id"] not in closed]
    screens["findings"].append({"id": "external-knowledge-target-unbound", "severity": "qualification-limit",
        "description": "Production external knowledge file provider is unbound/unqualified. Core native A4 admission, separate attested provider authentication and byte/readback consumer implementation do not prove the proposed Oracle/VEKL target exists or is qualified.",
        "current_status": "EXTERNAL_PROVIDER", "citations": [cite(BACKEND+"browser/artifact_provider.py", r"^class OwnerArtifactProvider:"),
            cite(BACKEND+"browser/artifact_admission.py", r"^class OwnerArtifactAdmissionService:"),
            cite(BACKEND+"auth/provider_transport.py", r"^class ProviderTransportAuthenticator:")]})
    refresh.walk(screens)
    if refresh.unresolved:
        raise RuntimeError("Findings require source review")
    captured_files = {file: sha for file, (_, sha) in refresh.cache.items()}
    manifest_path = ROOT/"docs/audit/VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-08.json"
    qualification = {"status": "SOURCE_REVIEWED_FINAL_VALIDATION_PENDING", "physical_cases_executed": 0,
                     "owner_release": False, "deployment_accepted": False,
                     "source_review_manifest": str(manifest_path.relative_to(ROOT)),
                     "android_receipt": None, "android_receipt_sha256": None,
                     "scope": "Reviewed owner contracts and current source declarations; final build/integration and live acceptance remain separate."}
    if args.final_source_manifest:
        frozen = load(args.final_source_manifest)
        verify_freeze(freeze_files(frozen))
        android = load(args.android_receipt)
        if android.get("source_changed_during_final_validation") or not str(android.get("status", "")).endswith("PASS"):
            raise RuntimeError("Final Android receipt is not a stable successful qualification")
        if not android.get("source_files"):
            raise RuntimeError("Final Android receipt lacks its source binding")
        verify_freeze(freeze_files({"files": android["source_files"]}))
        suites = android.get("suites") or [{"name": name, **check} for name, check in android.get("checks", {}).items()
                                           if name in {"jvm", "app_unit"}]
        suites_by_name = {suite["name"]: suite for suite in suites}
        for name in ("jvm", "app_unit"):
            suite = suites_by_name.get(name)
            if not suite or suite.get("tests", 0) <= 0 or suite.get("failures", 0) or suite.get("errors", 0):
                raise RuntimeError("Final Android receipt lacks passing nonempty "+name+" checks")
        qualification.update(status="SOURCE_REVIEWED_LOCAL_VALIDATION_PASSED",
            source_freeze_manifest=str(args.final_source_manifest.relative_to(ROOT)),
            source_freeze_sha256=digest(args.final_source_manifest),
            android_receipt=str(args.android_receipt.relative_to(ROOT)), android_receipt_sha256=digest(args.android_receipt))
        for row in all_rows:
            row["current_implementation"]["verification"].update(
                android_compile="PASSED_CURRENT_SOURCE_BOUND_COMPILE_UNIT_ASSEMBLE_LINT",
                jvm_behavior_tests="PASSED_CURRENT_SOURCE_BOUND_PRODUCTION_HELPERS",
                android_receipt=qualification["android_receipt"],
                android_receipt_sha256=qualification["android_receipt_sha256"],
                jvm_tests_passed=suites_by_name["jvm"]["tests"],
                app_unit_tests_passed=suites_by_name["app_unit"]["tests"],
                scope="Current source-bound local Android build/tests only; parent backend receipt separate. No provider, deployment or handset qualification.")
    review = {"schema_version": 1, "status": "REVIEWED_SOURCE_ONLY", "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "files": captured_files, "physical_cases_executed": 0, "deployment_accepted": False,
              "scope": "Current cited production source; no build, provider, deployment or device qualification."}
    verify_freeze(captured_files)
    save(manifest_path, review)
    qualification["source_review_manifest_sha256"] = digest(manifest_path)
    for document, collection in ((features, "features"), (screens, "screens")):
        document["historical_audit_date"] = document.get("audit_date", "2026-10-07")
        document["audit_date"] = "2026-10-08"
        document["current_source_qualification"] = copy.deepcopy(qualification)
        document["functional_wiring_counts"] = dict(Counter(row["functional_wiring_status"] for row in document[collection]))
        document["current_registry_scope"] = "Current supported source functions, explicit authority/evidence/refusal/recovery contracts and pending external qualification. No universal live-readiness claim."
    screens["screen_count"] = len(screens["screens"])
    screens["runtime_verification"] = "Current source review; final whole-workspace tests and Android/production/provider/handset qualification are separate."
    save(ROOT/"registries/owner_endpoints.json", endpoint_doc)
    save(ROOT/"registries/owner_endpoint_schemas.json", {"components": {"schemas": schemas}})
    save(ROOT/"registries/owner_features.json", features)
    save(ROOT/"registries/owner_screens.json", screens)
    print(json.dumps({"features": len(features["features"]), "screens": len(screens["screens"]),
                      "endpoints": len(endpoints), "schemas": len(schemas), "source_files": len(captured_files),
                      "refreshed_citations": refresh.refreshed, "qualification": qualification["status"]}))


if __name__ == "__main__":
    main()
