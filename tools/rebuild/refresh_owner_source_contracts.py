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


def build():
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
                    old = git_file(CITATION_BASE, file)
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

    documents = {name: json.loads(git_file(INPUT, "registries/"+name+".json"))
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
    accounts = next(r for r in documents["owner_features"]["features"] if r["id"] == "OF-TRADING-003")
    account_screen = next(r for r in documents["owner_screens"]["screens"] if r["id"] == "van.trading.accounts.add")
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


def main():
    if sys.argv[1:] not in (["--check"], ["--apply"]):
        raise SystemExit("Use --check or --apply")
    outputs = build()
    changed = [p for p, data in outputs.items() if not (ROOT/p).is_file() or (ROOT/p).read_bytes() != data]
    if sys.argv[1] == "--apply":
        for path in changed:
            if path.startswith("registries/") and not approved_preimage(path, (ROOT/path).read_bytes()):
                raise ValueError("Unexpected registry edits require review: "+path)
            if not path.startswith("registries/") and (ROOT/path).exists():
                try:
                    old = git_file("HEAD", path)
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
