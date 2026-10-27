#!/usr/bin/env python3
"""Index the unchanged programme and inherited source; issue no acceptance.

Full contracts stay at their canonical locations. Their hashes, identities and
owner edges prevent an abbreviated work list from silently replacing scope.
Historical source classifications are discovery leads, not implementation proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "docs/review-inputs/van-rev115/package"
PACKAGE_TREE = "ac0226a22a95f51642cfeb37b3709b40f7cacf10"
OUTPUT = "docs/rebuild/rev118/SOURCE_WORKMAP.json"
INPUTS = {
    "plan": PACKAGE + "/plan/DEVELOPMENT_PLAN.json",
    "requirements": PACKAGE + "/traceability/REQUIREMENTS_AND_DU_MAPPING.json",
    "acceptance": PACKAGE + "/verification/EFFECTIVE_TEST_CONTRACTS_REV118.json",
    "contexts": PACKAGE + "/design/ALL_SURFACE_CONTRACTS.json",
    "actions": PACKAGE + "/traceability/LEGACY_349_ACTIONS.json",
    "planned_features": PACKAGE + "/reference/REV2_FEATURE_REGISTRY.json",
    "source_features": "registries/owner_features.json",
    "source_surfaces": "registries/owner_screens.json",
    "inherited_source": "docs/rebuild/rev118/pre001/SOURCE_CLASSIFICATION.json",
}
COUNTS = {"units": 131, "backend_units": 82, "backend_verification_units": 12,
          "requirements": 324, "acceptance": 1610, "contexts": 234,
          "actions": 349, "planned_features": 93, "source_features": 42,
          "source_functions": 105, "source_surfaces": 78}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def index(rows, name):
    result = {r["id"]: r for r in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate " + name + " identity")
    return result


def build(root=ROOT):
    data = {key: json.loads((root / path).read_text()) for key, path in INPUTS.items()}
    plan = data["plan"]
    units = index(plan["units"], "unit")
    inventories = {
        "requirements": data["requirements"]["requirements"],
        "acceptance": data["acceptance"]["tests"],
        "contexts": data["contexts"]["surfaces"],
        "actions": data["actions"]["actions"],
        "planned_features": data["planned_features"]["features"],
        "source_features": data["source_features"]["features"],
        "source_surfaces": data["source_surfaces"]["screens"],
    }
    inventories["source_functions"] = [f for row in inventories["source_features"]
        for f in row.get("current_implementation", {}).get("functions", [])]
    for key, rows in inventories.items():
        index(rows, key)
        if len(rows) != COUNTS[key]:
            raise ValueError("original scope count changed: " + key)
    if (len(units) != COUNTS["units"]
            or len(plan["required_backend_ids"]) != COUNTS["backend_units"]
            or len(plan["required_backend_verification_ids"]) != COUNTS["backend_verification_units"]):
        raise ValueError("original programme unit scope changed")
    requirements = {r["id"] for r in inventories["requirements"]}
    acceptance = {r["id"] for r in inventories["acceptance"]}
    owners = plan["requirement_ownership"]
    if set(owners) - units.keys():
        raise ValueError("unknown requirement owner")
    if {r for rows in owners.values() for r in rows} != requirements:
        raise ValueError("unowned or unknown requirement")
    if {t for u in units.values() for t in u["acceptance_test_ids"]} != acceptance:
        raise ValueError("unowned or unknown acceptance contract")
    seen = set()
    source = data["inherited_source"]["rows"]
    work = []
    for unit in plan["units"]:
        uid = unit["id"]
        if not set(unit["dependencies"]) <= seen:
            raise ValueError("canonical dependency order violated: " + uid)
        seen.add(uid)
        candidates = sorted({r["path"] for r in source if uid in r["units"]})
        work.append({
            "id": uid, "title": unit["title"], "kind": unit["kind"],
            "dependencies": unit["dependencies"],
            "full_unit_contract_sha256": digest(unit),
            "requirement_ids": owners.get(uid, []),
            "acceptance_ids": unit["acceptance_test_ids"],
            "context_ids": [r["id"] for r in inventories["contexts"]
                if uid in r.get("backend_units", []) + r.get("frontend_units", [])],
            "owner_action_ids": [r["id"] for r in inventories["actions"]
                if uid in r.get("backend_units", []) + r.get("frontend_units", [])],
            "inherited_source_candidates": candidates,
            "source_inspection": "REQUIRED_AT_WORKFLOW_START_NOT_A_MISSING_CODE_CLAIM",
            "unit_acceptance": "NOT_ISSUED",
        })
    # Hash the entire original row, including states, errors, controls,
    # assertions, privacy and recovery semantics, rather than just its title.
    identities = {key: {r["id"]: digest(r) for r in rows}
                  for key, rows in inventories.items()}
    return {
        "schema": "van.rebuild.source-workmap/1",
        "meaning": "Execution index subordinate to the frozen plan. No new roadmap, authority, feature retirement or acceptance. Full source/wiring/provider/independent/device evidence remains required.",
        "canonical_package_tree": PACKAGE_TREE,
        "counts": COUNTS,
        "inputs": {key: {"path": path, "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()}
                   for key, path in INPUTS.items()},
        "identity_contract_hashes": identities,
        "units": work,
        "implementation_record": "docs/rebuild/rev118/CANDIDATE_SOURCE_PROGRESS.json",
        "execution_method": "docs/rebuild/rev118/BUILD_EXECUTION_PLAN.md",
    }


def check_document(actual, expected):
    if actual != expected:
        raise ValueError("workmap differs from original identities, full contract hashes, dependency edges or source index; regenerate and review the actual change")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD:" + PACKAGE], cwd=ROOT, text=True).strip()
    if tree != PACKAGE_TREE:
        raise ValueError("frozen package tree differs from the original")
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", PACKAGE],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    expected = build()
    if args.apply:
        (ROOT / OUTPUT).write_text(json.dumps(expected, indent=2, ensure_ascii=False) + "\n")
    else:
        check_document(json.loads((ROOT / OUTPUT).read_text()), expected)
    print(json.dumps({"workmap": OUTPUT, "counts": COUNTS,
                      "result": "SOURCE_SCOPE_INDEX_CONSISTENT", "acceptance_issued": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
