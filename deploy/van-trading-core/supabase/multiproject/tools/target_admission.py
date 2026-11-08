#!/usr/bin/env python3
"""Evaluate *non-secret*, read-only target facts. Never deploy or grant authority.

Only derived observations are reported. The source deliberately contains no
SSH/Docker/psql execution code, credential handling, canary creation, role DDL,
or ability to approve a previously refused operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

class SnapshotError(ValueError):
    pass

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
EXPECTED_DONOR = {
    "base_git_blob": "a37d39dc7c797b0487a8342855dda3cd1e66e0aa",
    "override_git_blob": "2507bbece5cd5a56ca27258a18f37adad867bbc9",
    "unit_sha256": "ebadc3c846ace0bbfb85e4a7b72635c7f40b09c52ed8e1c8daa8677057598a14",
}
EXPECTED_ORIGINAL_DBS = {"_supabase", "postgres"}
EXPECTED_PRODUCT_SOURCE_SHA = "e62c0f0948b1d0c8778deee3a4460bc378a003eb"
EXPECTED_VERIFIED_BACKUP_SHA = "e6f4147d9c994d220e12664cacf311935f54f9de0a8b2f87ea1c23c0eb42f0ff"
EXPECTED_API_ROLES = {
    "anon": {"login": False, "superuser": False, "bypassrls": False, "membership_count": 0},
    "authenticated": {"login": False, "superuser": False, "bypassrls": False, "membership_count": 0},
    "service_role": {"login": False, "superuser": False, "bypassrls": True, "membership_count": 0},
}
GROUP_KEYS = {
    "target": {"hostname", "architecture", "free_root_bytes", "available_memory_kib", "compose_project", "compose_containers", "healthy_containers", "canary_container_count", "systemd_active", "base_git_blob", "override_git_blob", "unit_sha256", "original_images_arm64"},
    "postgres": {"server_version_num", "database_names", "max_connections", "connections_observed", "wal_level", "max_replication_slots", "used_replication_slots", "role_collision_count", "database_collision_count", "api_roles", "execution_role", "privileges"},
    "backup": {"target_cipher_sha256", "offhost_cipher_sha256", "verified_restore", "verified_table_count", "captured_cluster_backup"},
    "governance": {"source_sha", "proposed_project_count", "original_canary_execution_refused", "refusal_reconciled_with_authority", "production_release_receipt_present", "required_slot_reserve", "candidate_arm64_images_qualified", "canonical_lifecycle_installed", "full_target_service_coexistence_tested"},
}
EXECUTION_PRIV_KEYS = {"is_superuser", "can_set_log_statement", "can_set_log_min_error_statement", "can_set_log_parameter_max_length", "can_read_hba_rules"}
REQUIRED_KEYS = {"schema_version", "observation_class", *GROUP_KEYS.keys()}


def strict_keys(value: object, keys: set[str], context: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise SnapshotError("INCOMPLETE_OR_UNEXPECTED_" + context)
    return value


def type_integer(value: object, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise SnapshotError("INVALID_INTEGER_FACT")
    return value


def type_bool(value: object) -> bool:
    if type(value) is not bool:
        raise SnapshotError("INVALID_BOOLEAN_FACT")
    return value


def evaluate(facts: object) -> dict:
    f = strict_keys(facts, REQUIRED_KEYS, "SNAPSHOT")
    if type(f["schema_version"]) is not int or f["schema_version"] != 1 or f["observation_class"] != "UNTRUSTED_NONSECRET_READ_ONLY_FACTS":
        raise SnapshotError("UNTRUSTED_OBSERVATIONS_REQUIRED")
    t = strict_keys(f["target"], GROUP_KEYS["target"], "TARGET")
    p = strict_keys(f["postgres"], GROUP_KEYS["postgres"], "POSTGRES")
    b = strict_keys(f["backup"], GROUP_KEYS["backup"], "BACKUP")
    g = strict_keys(f["governance"], GROUP_KEYS["governance"], "GOVERNANCE")
    priv = strict_keys(p["privileges"], EXECUTION_PRIV_KEYS, "PRIVILEGES")
    roles = strict_keys(p["api_roles"], set(EXPECTED_API_ROLES), "API_ROLE_SET")
    for key, val in t.items():
        if key in {"systemd_active", "original_images_arm64"}: type_bool(val)
        elif key in {"free_root_bytes", "available_memory_kib", "compose_containers", "healthy_containers", "canary_container_count"}: type_integer(val)
    for key in ("max_connections", "connections_observed", "max_replication_slots", "used_replication_slots", "role_collision_count", "database_collision_count"):
        type_integer(p[key])
    for k in priv: type_bool(priv[k])
    if type(p["server_version_num"]) is not int or not 170000 <= p["server_version_num"] <= 179999:  # rejected by gate, not malformed fact
        if type(p["server_version_num"]) is not int: raise SnapshotError("INVALID_SERVER_VERSION")
    if not isinstance(p["database_names"], list) or not all(isinstance(x, str) and x for x in p["database_names"]) or len(set(p["database_names"])) != len(p["database_names"]):
        raise SnapshotError("INVALID_DATABASE_NAME_OBSERVATIONS")
    for role, expected in EXPECTED_API_ROLES.items():
        entry = strict_keys(roles[role], set(expected), "ROLE_" + role.upper())
        for k, value in entry.items():
            if k == "membership_count": type_integer(value)
            else: type_bool(value)
    for key in ("verified_restore", "captured_cluster_backup"): type_bool(b[key])
    for key in ("original_canary_execution_refused", "refusal_reconciled_with_authority", "production_release_receipt_present", "candidate_arm64_images_qualified", "canonical_lifecycle_installed", "full_target_service_coexistence_tested"): type_bool(g[key])
    type_integer(g["proposed_project_count"], 1)
    type_integer(g["required_slot_reserve"], 2)
    type_integer(b["verified_table_count"])
    if (not isinstance(g["source_sha"], str) or not SHA40.fullmatch(g["source_sha"]) or
        not isinstance(b["target_cipher_sha256"], str) or not SHA64.fullmatch(b["target_cipher_sha256"]) or
        not isinstance(b["offhost_cipher_sha256"], str) or not SHA64.fullmatch(b["offhost_cipher_sha256"])):
        raise SnapshotError("INVALID_SOURCE_OR_CIPHERTEXT_IDENTITY")
    if not isinstance(p["execution_role"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", p["execution_role"]):
        raise SnapshotError("INVALID_EXECUTION_IDENTITY")

    checks: dict[str, bool] = {}
    checks["exact_tested_product_source"] = g["source_sha"] == EXPECTED_PRODUCT_SOURCE_SHA
    checks["target_name_and_cpu"] = t["hostname"] == "van-trading-core" and t["architecture"] in ("aarch64", "arm64")
    checks["exact_original_compose_and_unit"] = all(t[k] == v for k, v in EXPECTED_DONOR.items())
    checks["existing_compose_healthy"] = t["systemd_active"] and t["compose_project"] == "supabase" and t["compose_containers"] == 11 and t["healthy_containers"] == 11
    checks["original_database_set_preserved"] = set(p["database_names"]) == EXPECTED_ORIGINAL_DBS and t["canary_container_count"] == 0
    checks["no_namespace_collisions"] = p["role_collision_count"] == 0 and p["database_collision_count"] == 0
    checks["pg17_supported"] = 170000 <= p["server_version_num"] <= 179999
    checks["standard_api_roles_match"] = roles == EXPECTED_API_ROLES
    checks["existing_image_architecture_matches"] = t["original_images_arm64"]
    checks["backup_verified_and_available_offhost"] = (b["captured_cluster_backup"] and b["verified_restore"] and b["verified_table_count"] >= 57 and b["target_cipher_sha256"] == b["offhost_cipher_sha256"] == EXPECTED_VERIFIED_BACKUP_SHA)
    checks["auth_rest_candidate_disk_floor"] = t["free_root_bytes"] >= 2 * 1024**3
    checks["auth_rest_candidate_memory_floor"] = t["available_memory_kib"] >= 2 * 1024**2
    checks["db_connection_capacity_nonnegative"] = p["max_connections"] >= 50 and p["connections_observed"] < p["max_connections"]
    checks["bootstrap_privilege_and_hba_visibility"] = all(priv.values())
    checks["no_live_canary_refusal_remaining"] = not g["original_canary_execution_refused"] or g["refusal_reconciled_with_authority"]
    # For Realtime 2 native temporary slots per project, reserve at least two
    # extra cluster slots for existing/repair traffic. This is a policy gate,
    # not a claim that current production requires exactly this allocation.
    needed_slots = 2 * g["proposed_project_count"] + g["required_slot_reserve"]
    checks["realtime_slot_reserve"] = p["wal_level"] == "logical" and p["max_replication_slots"] >= p["used_replication_slots"] + needed_slots
    checks["candidate_arm64_images_admitted"] = g["candidate_arm64_images_qualified"]
    checks["canonical_lifecycle_installed"] = g["canonical_lifecycle_installed"]
    checks["real_target_full_service_coexistence"] = g["full_target_service_coexistence_tested"]
    checks["operator_release_receipt"] = g["production_release_receipt_present"]

    canary_keys = ("exact_tested_product_source", "target_name_and_cpu", "exact_original_compose_and_unit", "existing_compose_healthy", "original_database_set_preserved", "no_namespace_collisions", "pg17_supported", "standard_api_roles_match", "existing_image_architecture_matches", "backup_verified_and_available_offhost", "auth_rest_candidate_disk_floor", "auth_rest_candidate_memory_floor", "db_connection_capacity_nonnegative", "bootstrap_privilege_and_hba_visibility", "no_live_canary_refusal_remaining", "operator_release_receipt")
    canary_blockers = [k for k in canary_keys if not checks[k]]
    full_blockers = [k for k, passed in checks.items() if not passed]
    return {
        "schema_version": 1,
        "kind": "READ_ONLY_MULTIPROJECT_PREFLIGHT_NOT_QUALIFICATION",
        "source_product_sha": g["source_sha"],
        "project_count": g["proposed_project_count"],
        "required_realtime_slots_with_reserve": needed_slots,
        "actual_replication_slots_max": p["max_replication_slots"],
        "checks": checks,
        "auth_rest_canary_blockers": canary_blockers,
        "full_service_blockers": full_blockers,
        "canary_technically_ready": not canary_blockers,
        "full_service_technically_ready": not full_blockers,
        "canary_activation_authorized": False,
        "release_authorized": False,
        "production_effects": False,
        "interpretation": "These are untrusted read-only facts, not signed admission. Previous refused operations must be independently reconciled by their original authority, never rerouted or replayed.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if not args.out.is_absolute() or args.out.exists() or args.out.is_symlink():
            raise SnapshotError("NEW_ABSOLUTE_REPORT_REQUIRED")
        if args.snapshot.is_symlink() or not args.snapshot.is_file() or args.snapshot.stat().st_size > 65536:
            raise SnapshotError("BOUNDED_REGULAR_SNAPSHOT_REQUIRED")
        with args.snapshot.open("r", encoding="utf-8") as f:
            raw = json.load(f, parse_constant=lambda x: (_ for _ in ()).throw(SnapshotError("JSON_CONSTANT_REFUSED")))
        result = evaluate(raw)
        fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(result, output, sort_keys=True, indent=2)
            output.write("\n")
        print("READ_ONLY_MULTIPROJECT_PREFLIGHT_BLOCKED=" + str(bool(result["full_service_blockers"])) .lower())
        return 0
    except (SnapshotError, ValueError, TypeError, KeyError, OSError, json.JSONDecodeError):
        print("READ_ONLY_MULTIPROJECT_PREFLIGHT_REFUSED")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
