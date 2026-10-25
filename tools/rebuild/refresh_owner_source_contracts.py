#!/usr/bin/env python3
"""Bounded derived-contract refresh from the preserved pre-refresh registry.

No new UI or live qualification. --check recomputes without writing. --apply
refuses unexpected current registry edits rather than replacing owner changes.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.audit.export_owner_endpoints import export

INPUT = "9f61e09f57ae0ea48614bf5ee75a4f19360941f4"
CITATION_BASE = "b02075f327ea8180ab6d269eba358cf8c5479878"
RECEIPT = "docs/rebuild/rev118/backend/OWNER_REGISTRY_SOURCE_REFRESH_20261022.json"
GENERATION = "docs/rebuild/rev118/backend/OWNER_REGISTRY_GENERATION.json"
LEGACY_GENERATION = "c36d6a21bea1618707e353912d3f5b9508eca5ba"
REGISTRIES = frozenset("registries/"+name+".json" for name in (
    "owner_endpoints", "owner_endpoint_schemas", "owner_features", "owner_screens"))
REVIEWED_CITATION_REPLACEMENTS = {
    ("android/app/src/main/java/com/dial/van/trading/ui/AccountOnboardingScreen.kt",
     "                val outcome = runCatching { app.gatewayClient.tradingAccountAction(action, args, proof) }"):
     "                val outcome = runCatching { app.gatewayClient.tradingAccountAction(action, args, proof, approvedIssuedAt) }",
}


def git_file(ref, path):
    return subprocess.run(["git", "show", ref+":"+path], cwd=ROOT, check=True, capture_output=True).stdout


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, indent=2)+"\n").encode()


def approved_preimage(path, current, read=git_file):
    """Accept reviewed originals or an intact committed generation, never local edits."""
    if path not in REGISTRIES:
        return False
    for ref in (INPUT, LEGACY_GENERATION):
        try:
            if current == read(ref, path):
                return True
        except subprocess.CalledProcessError:
            pass
    try:
        record = json.loads(read("HEAD", GENERATION))
        if (record.get("schema") != "van.rebuild.owner-registry-generation/1"
            or set(record.get("outputs", {})) != REGISTRIES
            or record.get("source_receipt_sha256") != sha(read("HEAD", RECEIPT))):
            return False
        # Validate the entire generation before accepting any of its files.
        committed = {p: read("HEAD", p) for p in REGISTRIES}
        if any(sha(data) != record["outputs"][p] for p, data in committed.items()):
            return False
        return current == committed[path]
    except (subprocess.CalledProcessError, ValueError, KeyError, TypeError):
        return False


def build(read=None):
    # A caller may supply real immutable Git-object reads without a child process.
    # All citation and generation/preimage checks still run against those bytes.
    read = git_file if read is None else read
    endpoint_doc = export()
    schemas = endpoint_doc.pop("schemas")
    endpoints = {r["endpoint_id"]: r for r in endpoint_doc["endpoints"]}
    changes, sources = {}, {}

    def walk(value):
        if isinstance(value, dict):
            if value.get("ref") == "WORKSPACE_PATCH" and {"file", "line"} <= value.keys():
                file = value["file"]
                data = (ROOT/file).read_bytes()
                sources[file] = sha(data)
                if value.get("sha256") != sha(data):
                    old = read(CITATION_BASE, file)
                    if sha(old) != value.get("sha256"):
                        raise ValueError("Unreviewed citation source: "+file)
                    anchor = old.decode().splitlines()[value["line"]-1]
                    current_anchor = REVIEWED_CITATION_REPLACEMENTS.get((file, anchor), anchor)
                    lines = data.decode().splitlines()
                    matches = [i+1 for i, line in enumerate(lines) if line == current_anchor]
                    if len(matches) != 1:
                        raise ValueError("Changed/non-unique citation requires review: "+file+":"+str(value["line"]))
                    key = file+":"+str(value["line"])
                    changes[key] = {"file": file, "old_line": value["line"], "new_line": matches[0],
                        "old_sha256": value.get("sha256"), "new_sha256": sha(data), "exact_anchor": anchor}
                    if current_anchor != anchor:
                        changes[key].update(reviewed_replacement_anchor=current_anchor,
                            reason="Preserve the exact timestamp used in the existing owner approval, including biometric delay")
                    value.update(line=matches[0], sha256=sha(data))
            if "endpoint_id" in value and "source_ref" in value:
                value["source_ref"] = endpoints[value["endpoint_id"]]["source"]
            for key, child in value.items():
                if not key.startswith(("baseline", "historical")):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    documents = {name: json.loads(read(INPUT, "registries/"+name+".json"))
                 for name in ("owner_features", "owner_screens")}
    preserved = {}
    for name, document in documents.items():
        rows = document["features" if name == "owner_features" else "screens"]
        preserved[name] = {"rows": len(rows), "function_ids": [f["id"] for r in rows
            for f in r["current_implementation"]["functions"]]}
        walk(rows)
    browser = next(r for r in documents["owner_features"]["features"] if r["id"] == "OF-BROWSER-001")
    endpoint = next(r for r in endpoint_doc["endpoints"] if r["path"].endswith("/{task_id}/resume-contract"))
    browser.setdefault("backend_contract_extensions", []).append({
        "action_id": "browser.task.resume", "endpoint_id": endpoint["endpoint_id"],
        "source_status": "BACKEND_SOURCE_TESTED_ANDROID_CONSUMER_PENDING",
        "approval_path": "POST /v1/commands", "authority": "FRESH_EXACT_OWNER_A4",
        "scope": "One continuation of the same waiting task; advisory decisions grant no authority",
        "specification": "docs/rebuild/rev118/backend/BE-025_BROWSER_CONTINUATION.md",
        "new_ui_implemented": False, "live_qualified": False})
    voice = next(r for r in documents["owner_features"]["features"] if r["id"] == "OF-VOICE-001")
    mission_feature = next(r for r in documents["owner_features"]["features"] if r["id"] == "OF-MISSION-001")
    mission_screen = next(r for r in documents["owner_screens"]["screens"] if r["id"] == "van.work.mission")
    graph_endpoint = next(r for r in endpoint_doc["endpoints"] if r["path"] == "/v1/missions/{mission_id}/graph")
    graph_extension = {
        "method": "GET", "path": graph_endpoint["path"], "endpoint_id": graph_endpoint["endpoint_id"],
        "source_ref": graph_endpoint["source"], "authentication": graph_endpoint["authentication"],
        "source_status": "CANDIDATE_BACKEND_SOURCE_ANDROID_CONSUMER_PENDING",
        "authority": "OWNER_READ_ONLY_GRAPH_GRANTS_NO_EXECUTION_AUTHORITY",
        "scope": "One durable mission snapshot: stable activity and dependency identities, owner-visible stage evidence, observed executor outcomes, explicit cycles/orphans/conflicting executor claims. Critical path is dependency count only; no invented duration or verified success. Payload limits refuse rather than omit work.",
        "specification": "docs/rebuild/rev118/backend/BE-023_MISSION_DEPENDENCY_GRAPH.md",
        "new_ui_implemented": False, "live_qualified": False,
    }
    for row in (mission_feature, mission_screen):
        row.setdefault("backend_contract_extensions", []).append(copy.deepcopy(graph_extension))
    native_action = next(r for r in endpoint_doc["endpoints"] if r["path"] == "/v1/dial-dev/actions/{action_id}")
    native_recovery = {
        "method": "GET", "path": native_action["path"], "endpoint_id": native_action["endpoint_id"],
        "source_ref": native_action["source"], "authentication": native_action["authentication"],
        "source_status": "CANDIDATE_BACKEND_AND_EXISTING_ANDROID_CONTROL_RECOVERY_SOURCE_NATIVE_ACCEPTANCE_PENDING",
        "client_namespace": "VanGatewayClient.dialDev", "client_function": "action/reconcileAction",
        "client_original_operations": "com.dial.van.dialdev.DialDevOriginalOperations",
        "authority": "OWNER_READ_ORIGINAL_NATIVE_CONTROL_NO_DISPATCH_OR_TASK_SUCCESS_GRANT",
        "scope": "Exact original action read beyond recent lists; encrypted prepared request retains parameters/revision/key across restart. Reads never POST. Changed instructions, malformed/foreign/stale facts and uncertain native control errors cannot replace an original. APPLIED is a control outcome, not task success.",
        "specification": "docs/rebuild/rev118/backend/BE-003_024_DIAL_ORIGINAL_CONTROL_RECOVERY.md",
        "new_ui_implemented": False, "existing_android_repair": True, "live_qualified": False,
    }
    native_rows = [next(r for r in documents["owner_features"]["features"] if r["id"] == "OF-DEV-001")]
    native_rows += [r for r in documents["owner_screens"]["screens"] if r["id"] in {
        "van.work.dev.home", "van.work.dev.plan", "van.work.dev.task", "van.work.dev.workspace"}]
    for row in native_rows:
        row.setdefault("backend_contract_extensions", []).append(copy.deepcopy(native_recovery))
    reminder_feature = next(r for r in documents["owner_features"]["features"] if r["id"] == "OF-REMINDER-001")
    reminder_screen = next(r for r in documents["owner_screens"]["screens"] if r["id"] == "van.reminders.manage")
    for endpoint in endpoint_doc["endpoints"]:
        if not endpoint["path"].startswith("/v1/reminders"):
            continue
        extension = {
            "method": endpoint["method"], "path": endpoint["path"], "endpoint_id": endpoint["endpoint_id"],
            "source_ref": endpoint["source"], "authentication": endpoint["authentication"],
            "source_status": "CANDIDATE_BACKEND_SOURCE_EXISTING_ANDROID_FLOW_ACCEPTANCE_PENDING",
            "authority": "EXISTING_REMINDER_SCOPE_NO_NEW_EXECUTION_OR_FINANCIAL_GRANT",
            "scope": "Original request-bound idempotency, atomic follow-ups with project/source retained, terminal-state conflicts and recoverable server publication. Attention preserves owner acknowledgement under concurrent reports.",
            "publication_scope": "SERVER_EVENT_AND_ATTENTION_PERSISTENCE_ONLY",
            "time_contract": "Relative elapsed time; explicit UTC default; supplied local wall times require one unique instant. No inferred handset timezone or owner DST preference.",
            "specification": "docs/rebuild/rev118/backend/BE-028_030_REMINDER_PUBLICATION.md",
            "new_ui_implemented": False, "live_qualified": False,
        }
        for row in (reminder_feature, reminder_screen):
            row.setdefault("backend_contract_extensions", []).append(copy.deepcopy(extension))
    accounts = next(r for r in documents["owner_features"]["features"] if r["id"] == "OF-TRADING-003")
    account_screen = next(r for r in documents["owner_screens"]["screens"] if r["id"] == "van.trading.accounts.add")
    recovery_feature = next(r for r in documents['owner_features']['features'] if r['id'] == 'OF-TRADING-005')
    recovery_screen = next(r for r in documents['owner_screens']['screens'] if r['id'] == 'van.trading.halt')
    recovery_clients = {
        '/v1/trading/runtime/recovery/catalog':'tradingRuntimeRecoveryCatalog',
        '/v1/trading/runtime/recovery/state':'tradingRuntimeRecoveryState',
        '/v1/trading/runtime/recovery/challenge':'tradingRuntimeRecoveryChallenge',
        '/v1/trading/runtime/recovery/request':'tradingRuntimeRecoveryRequest',
        '/v1/trading/runtime/recovery/operations/{operation_id}':'tradingRuntimeRecoveryOperation',
    }
    for endpoint in endpoint_doc['endpoints']:
        if not endpoint['path'].startswith('/v1/trading/runtime/recovery/'):
            continue
        client_file = 'android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt'
        client_data = (ROOT/client_file).read_bytes()
        client_lines = [i+1 for i,line in enumerate(client_data.decode().splitlines())
                        if 'suspend fun '+recovery_clients[endpoint['path']]+'(' in line]
        if len(client_lines) != 1:
            raise ValueError('Runtime recovery client source is missing or ambiguous: '+endpoint['path'])
        sources[client_file] = sha(client_data)
        extension = {
            'method':endpoint['method'], 'path':endpoint['path'], 'endpoint_id':endpoint['endpoint_id'],
            'client_source_ref':{'file':client_file, 'line':client_lines[0], 'sha256':sha(client_data), 'ref':'WORKSPACE_PATCH'},
            'source_ref':endpoint['source'], 'authentication':endpoint['authentication'],
            'device_proof_required_when_bound':endpoint['device_proof_required_when_bound'],
            'source_status':'CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_CONSUMER_PENDING',
            'client_namespace':'VanGatewayClient', 'client_function':recovery_clients[endpoint['path']],
            'client_protocol':'com.dial.van.trading.RuntimeRecoveryProtocol',
            'client_original_operations':'com.dial.van.trading.RuntimeRecoveryOperations',
            'client_specification':'docs/rebuild/rev118/backend/BE-003_009_RUNTIME_RECOVERY_ANDROID_CLIENT.md',
            'authority':'CURRENT_PAIRED_OWNER_DEVICE_EXACT_A4_ACCOUNT_SESSION_LEASE_AND_RISK_STATE',
            'scope':'Single-session and multi-instrument account kill clear, loss-scope reset and drawdown rebaseline. The native account actor publishes its opaque session identity; symbol/contract configuration and lease changes invalidate an old review. Original approval ID and durable public proof survive uncertain dispatch. Reads never dispatch. APPLIED is not blanket entry authority; all other holds, unresolved original orders, profile and final native fences remain.',
            'supported_runtimes':['single-session','account'],
            'account_runtime_specification':'docs/rebuild/rev118/backend/BE-003_009_ACCOUNT_RUNTIME_RECOVERY.md',
            'specification':'docs/rebuild/rev118/backend/BE-003_009_RUNTIME_RECOVERY.md',
            'new_ui_implemented':False, 'live_qualified':False}
        for row in (recovery_feature, recovery_screen):
            row.setdefault('backend_contract_extensions', []).append(copy.deepcopy(extension))
    operation_endpoint = next(r for r in endpoint_doc["endpoints"] if r["path"] == "/v1/trading/accounts/operations/{operation_id}")
    operation_extension = {
        "method": "GET", "path": operation_endpoint["path"], "endpoint_id": operation_endpoint["endpoint_id"],
        "source_status": "CANDIDATE_SOURCE_ANDROID_REPAIR_NATIVE_ACCEPTANCE_PENDING",
        "client_namespace": "VanGatewayClient", "client_function": "tradingAccountOperation",
        "source_ref": operation_endpoint["source"], "authentication": operation_endpoint["authentication"],
        "device_proof_required_when_bound": operation_endpoint["device_proof_required_when_bound"],
        "authority": "READ_ORIGINAL_DEVICE_OWNED_ACCOUNT_OUTCOME_NO_EXECUTION_OR_CREDENTIAL_EXPORT",
        "scope": "Native journal for account_upsert/account_credentials/account_remove/mt5_ea_issue_key; original non-secret operation identity survives Android restart; absence and incomplete effects stay UNKNOWN",
        "specification": "docs/rebuild/rev118/backend/BE-003_004_005_NATIVE_ACCOUNT_OPERATIONS.md",
        "new_ui_implemented": False, "existing_android_repair": True, "live_qualified": False,
    }
    for row in (accounts, account_screen):
        row.setdefault("backend_contract_extensions", []).append(copy.deepcopy(operation_extension))
    catalogue = next(r for r in endpoint_doc["endpoints"] if r["path"] == "/v1/trading/accounts/catalog")
    account_controls = {
        "method": "GET", "path": catalogue["path"], "endpoint_id": catalogue["endpoint_id"],
        "source_status": "CANDIDATE_SOURCE_ANDROID_REPAIR_NATIVE_ACCEPTANCE_PENDING",
        "client_namespace": "VanGatewayClient", "client_function": "tradingAccountCatalog",
        "source_ref": catalogue["source"], "authentication": catalogue["authentication"],
        "device_proof_required_when_bound": catalogue["device_proof_required_when_bound"],
        "authority": "READ_FIELD_CONTRACTS_ONLY_NO_APPROVAL_OR_ACCOUNT_EFFECT",
        "scope": "Exact existing action fields, credential-key names, approval and original-result capabilities. Partial account edits preserve omitted settings. Generic edits require native resolved before/after review bound to the biometric proof and checked again by the native writer.",
        "specification": "docs/rebuild/rev118/backend/BE-002_004_005_ACCOUNT_UPDATE_REVIEW.md",
        "new_ui_implemented": False, "existing_android_repair": True, "live_qualified": False,
    }
    for row in (accounts, account_screen):
        row.setdefault("backend_contract_extensions", []).append(copy.deepcopy(account_controls))
    account_fact_targets = [accounts] + [r for r in documents['owner_screens']['screens']
        if accounts['id'] in r.get('feature_ids', [])]
    if len(account_fact_targets) == 1:
        raise ValueError('Native account facts have no existing account surface')
    fact_schema = 'trading/vati/contracts/schemas/native_account_observation.schema.json'
    fact_client = 'android/app/src/main/java/com/dial/van/trading/NativeAccountObservation.kt'
    for path in (fact_schema, fact_client):
        sources[path] = sha((ROOT/path).read_bytes())
    for path, client in [('/v1/trading/accounts', 'tradingAccounts'), ('/v1/trading/portfolio', 'tradingPortfolio')]:
        endpoint = next(r for r in endpoint_doc['endpoints'] if (r['method'], r['path']) == ('GET', path))
        extension = {'method':'GET', 'path':path, 'endpoint_id':endpoint['endpoint_id'],
            'client_namespace':'VanGatewayClient', 'client_function':client,
            'source_ref':endpoint['source'], 'authentication':endpoint['authentication'],
            'device_proof_required_when_bound':endpoint['device_proof_required_when_bound'],
            'source_status':'CANDIDATE_NATIVE_FACTS_ANDROID_DTO_SOURCE_TESTED',
            'authority':'READ_ORIGINAL_NATIVE_ACCOUNT_FACTS_NO_ORDER_OR_SETTLEMENT_AUTHORITY',
            'scope':'native_account_observation preserves current physical identity, original equity/balance/credit, credit-excluded risk valuation or explicit unknown/liability, source/read clocks and original snapshot references independently of cash-history coverage. Invalid evidence or changed profiles withhold financial values. Exact Kotlin decimal text and 64-bit identity/clock parsing; existing AccountCard DTO only, no new UI. Response schema: '+fact_schema,
            'response_schema':fact_schema, 'response_schema_sha256':sources[fact_schema],
            'android_dto':fact_client, 'android_dto_sha256':sources[fact_client],
            'specification':'docs/rebuild/rev118/backend/BE-004_006_NATIVE_ACCOUNT_OBSERVATION.md',
            'new_ui_implemented':False, 'live_qualified':False}
        for row in account_fact_targets:
            row.setdefault('backend_contract_extensions', []).append(copy.deepcopy(extension))
    accounts['information'].append('Original physical-account/valuation facts, credit qualification and exact observation clocks remain distinct from cash-history coverage, settled funds and execution permission.')
    voice_clients = {
        ("POST", "/v1/voice/responses"): "openSpokenResult",
        ("GET", "/v1/voice/streams/{stream_id}"): "speechStream",
        ("POST", "/v1/voice/streams/{stream_id}/cursors"): "reportSpeechCursors",
        ("POST", "/v1/voice/streams/{stream_id}/interrupt"): "interruptSpeech",
    }
    for key, client in voice_clients.items():
        endpoint = next(r for r in endpoint_doc["endpoints"] if (r["method"], r["path"]) == key)
        voice.setdefault("backend_contract_extensions", []).append({
            "method": key[0], "path": key[1], "endpoint_id": endpoint["endpoint_id"],
            "source_status": "CANDIDATE_SOURCE_TESTED_NATIVE_ACCEPTANCE_PENDING",
            "client_namespace": "VanGatewayClient", "client_function": client,
            "source_ref": endpoint["source"], "authentication": endpoint["authentication"],
            "device_proof_required_when_bound": endpoint["device_proof_required_when_bound"],
            "authority": "READ_EXISTING_OWNED_RESULT_ONLY_NO_WORK_DISPATCH",
            "scope": "Exact result reference and playback request; actual heard cursor; local-first interruption; current owner voice context",
            "specification": "docs/rebuild/rev118/backend/BE-029_AUTHENTICATED_SPEECH_DELIVERY.md",
            "new_ui_implemented": False, "live_qualified": False,
        })
    history = next(r for r in endpoint_doc["endpoints"] if
        (r["method"], r["path"]) == ("GET", "/v1/conversations/{thread_id}/messages"))
    conversation_history = {
        "method": "GET", "path": history["path"], "endpoint_id": history["endpoint_id"],
        "source_ref": history["source"], "authentication": history["authentication"],
        "device_proof_required_when_bound": history["device_proof_required_when_bound"],
        "client_namespace": "VanGatewayClient", "client_function": "convergenceThreadMessages",
        "source_status": "CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_PAGING_CONSUMER_PENDING",
        "authority": "READ_THREAD_CONTEXT_ONLY_NO_EXECUTION_OR_APPROVAL_AUTHORITY",
        "scope": "Latest bounded history with total count, has_more and next_before_message_id. Older pages use a message identity scoped to this thread; invalid, deleted and foreign cursors are refused. Equal-time messages are paged exactly once in chronological order. Atomic message/draft/follow-up writes and original projection scope preserve current owner thread state. Late canonical replies may complete archived history without reopening it. Follow-up promotion supplies a fresh owner prompt and never dispatches a command.",
        "specification": "docs/rebuild/rev118/backend/BE-003_029_CONVERSATION_STATE_INTEGRITY.md",
        "new_ui_implemented": False, "live_qualified": False,
    }
    conversation_rows = [next(r for r in documents["owner_features"]["features"] if r["id"] == "OF-COMMAND-001")]
    conversation_rows += [r for r in documents["owner_screens"]["screens"] if r["id"] in {
        "van.work", "van.floating", "van.voice.turn"}]
    for row in conversation_rows:
        row.setdefault("backend_contract_extensions", []).append(copy.deepcopy(conversation_history))
    chart_feature = next(r for r in documents["owner_features"]["features"] if r["id"] == "OF-TRADING-002")
    chart_screen = next(r for r in documents["owner_screens"]["screens"] if r["id"] == "van.trading.positions.detail")
    for endpoint in endpoint_doc["endpoints"]:
        if not endpoint["path"].startswith("/v1/trading/charts/"):
            continue
        extension = {
            "method": endpoint["method"], "path": endpoint["path"], "endpoint_id": endpoint["endpoint_id"],
            "source_ref": endpoint["source"], "authentication": endpoint["authentication"],
            "device_proof_required_when_bound": endpoint["device_proof_required_when_bound"],
            "source_status": "CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING",
            "authority": "OWNER_CHART_CONFIGURATION_ONLY_NO_ORDER_OR_CERTIFICATION_AUTHORITY",
            "canonical_units": ["BE-003", "BE-018"],
            "planned_feature_refs": ["VNX-F-CHART-02", "VNX-F-CHART-04", "VNX-F-CHART-05", "VNX-F-CHART-06", "VNX-F-CHART-09"],
            "scope": "Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed.",
            "specification": "docs/rebuild/rev118/backend/BE-003_018_CHART_WORKSPACES.md",
            "new_ui_implemented": False, "live_qualified": False,
        }
        for row in (chart_feature, chart_screen):
            row.setdefault("backend_contract_extensions", []).append(copy.deepcopy(extension))
    monitor_rows = [chart_feature]
    monitor_rows += [r for r in documents["owner_screens"]["screens"] if r["id"] in {
        "van.trading", "van.trading.positions.detail"}]
    for endpoint in endpoint_doc["endpoints"]:
        if not endpoint["path"].startswith("/v1/trading/monitors/"):
            continue
        extension = {
            "method": endpoint["method"], "path": endpoint["path"], "endpoint_id": endpoint["endpoint_id"],
            "source_ref": endpoint["source"], "authentication": endpoint["authentication"],
            "device_proof_required_when_bound": endpoint["device_proof_required_when_bound"],
            "source_status": "CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING",
            "authority": "OWNER_MONITOR_CONFIGURATION_AND_READ_ONLY_OBSERVATIONS_ALERTS_NEVER_TRADE",
            "canonical_units": ["BE-003", "BE-020"],
            "planned_feature_refs": ["VNX-F-TRADE-03", "VNX-F-TRADE-04", "VNX-F-CHART-11"],
            "planned_context_refs": ["van.next.trading.markets", "van.next.trading.alerts", "van.next.trading.screener"],
            "scope": "Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas. Saved selections do not prove native feed binding. A symbol-only bar lake cannot trigger a live technical fact. No order path exists.",
            "remaining": ["Full qualified native feed and quote binding", "Tick-price alerts and live row projections", "Dynamic watchlists", "Provider and Android consumer qualification"],
            "specification": "docs/rebuild/rev118/backend/BE-020_MARKET_MONITORS.md",
            "new_ui_implemented": False, "live_qualified": False,
        }
        for row in monitor_rows:
            row.setdefault("backend_contract_extensions", []).append(copy.deepcopy(extension))
    receipt = {"scope": "BOUNDED_SOURCE_REFERENCE_REFRESH_NOT_FULL_PRODUCT_REVIEW",
        "input_registry_commit": INPUT, "citation_source_commit": CITATION_BASE,
        "preserved_identity_sets": preserved, "citation_changes": changes,
        "current_cited_source_sha256": sources, "endpoint_count": len(endpoints),
        "schema_count": len(schemas), "physical_cases_executed": 0,
        "owner_release": False, "deployment_accepted": False}
    encoded_receipt = encode(receipt)
    for document in documents.values():
        previous = copy.deepcopy(document["current_source_qualification"])
        document.setdefault("historical_source_qualifications", {})["pre_rev118_autonomous_refresh"] = previous
        document["current_source_qualification"].update(
            status="SOURCE_REVIEWED_FINAL_VALIDATION_PENDING", source_review_manifest=RECEIPT,
            source_review_manifest_sha256=sha(encoded_receipt), android_receipt=None, android_receipt_sha256=None,
            scope="Bounded current source-citation/endpoint refresh; previous reviews retained. Whole-product, Android, deployment/provider and handset qualifications remain separate.")
        document["current_audit_note"] = "22 October candidate source-reference refresh. No historical receipt is promoted to current product or handset acceptance."
    result = {"registries/owner_endpoints.json": encode(endpoint_doc),
              "registries/owner_endpoint_schemas.json": encode({"components": {"schemas": schemas}}),
              RECEIPT: encoded_receipt}
    for name, document in documents.items():
        result["registries/"+name+".json"] = encode(document)
    result[GENERATION] = encode({"schema": "van.rebuild.owner-registry-generation/1",
        "source_receipt_sha256": sha(encoded_receipt),
        "outputs": {p: sha(result[p]) for p in sorted(REGISTRIES)},
        "qualification": "Derived source inventory only; no owner/native/admission signature."})
    return result


def main(read=None):
    read = git_file if read is None else read
    if sys.argv[1:] not in (["--check"], ["--apply"]):
        raise SystemExit("Use --check or --apply")
    outputs = build(read=read)
    changed = [p for p, data in outputs.items() if not (ROOT/p).is_file() or (ROOT/p).read_bytes() != data]
    if sys.argv[1] == "--apply":
        for path in changed:
            if path.startswith("registries/") and not approved_preimage(path, (ROOT/path).read_bytes(), read=read):
                raise ValueError("Unexpected registry edits require review: "+path)
            if not path.startswith("registries/") and (ROOT/path).exists():
                try:
                    old = read("HEAD", path)
                except subprocess.CalledProcessError:
                    old = None
                if (ROOT/path).read_bytes() != old:
                    raise ValueError("Unexpected generated-receipt edits require review: "+path)
        for path, data in outputs.items():
            (ROOT/path).parent.mkdir(parents=True, exist_ok=True)
            (ROOT/path).write_bytes(data)
    print(json.dumps({"changed": changed, "applied": sys.argv[1] == "--apply",
        "scope": "SOURCE_CONTRACTS_ONLY"}, indent=2))
    return int(bool(changed) and sys.argv[1] == "--check")


if __name__ == "__main__":
    raise SystemExit(main())
