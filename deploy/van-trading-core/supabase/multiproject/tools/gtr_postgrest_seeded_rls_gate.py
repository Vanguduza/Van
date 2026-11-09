#!/usr/bin/env python3
"""SHA-locked, offline validation of synthetic Nissan GTR PostgREST/RLS receipts.

Reads only three exact nonsecret test receipts. Never connects to Supabase,
opens a socket, launches Docker, executes SQL, or authorizes production release.
"""
from __future__ import annotations

import argparse
import json
import pathlib

import gtr_postgrest_http_gate as previous
import render as artifact_writer

KIND="GTR_ARM64_SYNTHETIC_AUTH_RLS_HTTP_REVIEW_NOT_PRODUCTION_ADMISSION_V1"
EXPECTED_HTTP_SHA="26c436e208bba8cf7277a2b38e7d4b27eafee87e3b13fd46b8342c9f66b72a18"
EXPECTED_REPLAY_SHA="1ac085b0d837ca958102eaa99ff13b1e55892a2923a9b88e6b9fd8c0bb6ce2d0"
EXPECTED_POSTFORWARD_SHA="17752b6d1d91d360d645d1dc888fd24dfb0dae51a291f4d49af77adc807d8a4b"
EXPECTED_OBSERVER_SHA="e0ee7b95e64d077b0ad7efb8eb3c3380e1fedbd972c94b6837aca2091be3a70b"
EXTRA_HTTP_FIELDS={
    "rpc_error_codes","synthetic_rls_checks","synthetic_rls_check_count",
    "synthetic_role_ids_stored","real_business_user_data_touched"
}
EXTRA_POSTFORWARD_FIELDS={
    "schema_version","scope","source_commit","image_sha256",
    "runner_sha256","reader_sha256","table_policy_function_scope",
    "postforward_migrations","counts","identity_digests","sanitized_snapshot_sha256",
    "read_only_sql","network_access","production_sql_writes",
    "hosted_connector_access","canary_activation_attempted",
    "postforward_run_passed","source_sql_or_user_data_exported"
}
EXPECTED_RLS=[
    ("customer_own_profile","customer_a",200,1),
    ("customer_other_profile_denied","customer_a",200,0),
    ("customer_other_customer_denied","customer_a",200,0),
    ("customer_own_customer","customer_a",200,1),
    ("other_customer_sees_no_first_customer","customer_b",200,0),
    ("admin_can_see_customer_b","admin",200,1),
    ("admin_can_see_own_role","admin",200,1),
    ("customer_cannot_see_admin_role","customer_a",200,0),
    ("unseeded_cannot_see_customer","outsider",200,0),
    ("positive_auth_catalog_rpc","admin",200,0)
]
EXPECTED_RPCS=frozenset({
    "auth_rpc_cart_legacy_default",
    "auth_rpc_hr_legacy_defaults",
    "auth_rpc_garage_legacy_defaults",
    "auth_rpc_staff_legacy_defaults"
})
class SeededRLSReviewError(ValueError):
    pass

def validate(http:dict,replay:dict,postforward:dict)->dict:
    if not isinstance(http,dict) or set(http)!=(previous.REQUIRED_HTTP_FIELDS | EXTRA_HTTP_FIELDS):
        raise SeededRLSReviewError("EXACT_EXTENDED_HTTP_RECEIPT_FIELDS_REQUIRED")
    if http["synthetic_role_ids_stored"] is not False or http["real_business_user_data_touched"] is not False:
        raise SeededRLSReviewError("REAL_OR_PERSISTED_USER_IDENTIFIERS_REFUSED")
    if http["synthetic_rls_check_count"]!=len(EXPECTED_RLS) or type(http["synthetic_rls_check_count"]) is not int:
        raise SeededRLSReviewError("TEN_SYNTHETIC_RLS_CHECKS_REQUIRED")
    checks=http["synthetic_rls_checks"]
    if not isinstance(checks,list) or len(checks)!=len(EXPECTED_RLS):
        raise SeededRLSReviewError("MISSING_OR_EXTRA_RLS_CHECKS")
    for i,(label,role,status,rows) in enumerate(EXPECTED_RLS):
        c=checks[i]
        if not isinstance(c,dict) or set(c)!={
            "label","http_status","row_count","synthetic_role","body_or_real_identifier_retained"
        }:
            raise SeededRLSReviewError("EXACT_RLS_RESULT_SHAPE_REQUIRED")
        if (c["label"]!=label or c["synthetic_role"]!=role or
            type(c["http_status"]) is not int or c["http_status"]!=status or
            type(c["row_count"]) is not int or c["row_count"]!=rows or
            c["body_or_real_identifier_retained"] is not False):
            raise SeededRLSReviewError("SYNTHETIC_CROSS_USER_RLS_BEHAVIOR_CHANGED_"+label)
    codes=http["rpc_error_codes"]
    if not isinstance(codes,dict) or set(codes)!=EXPECTED_RPCS:
        raise SeededRLSReviewError("EXACT_FOUR_RPC_CODES_REQUIRED")
    if not all(code=="P0001" for code in codes.values()):
        raise SeededRLSReviewError("RPC_NOT_PG_APPLICATION_EXCEPTION_OR_ROUTING_CHANGED")
    base={k:http[k] for k in previous.REQUIRED_HTTP_FIELDS}
    try:baseline=previous.evaluate(base,replay)
    except previous.HTTPGateError as exc:
        raise SeededRLSReviewError("PREVIOUS_HTTP_ROLE_GATE_REFUSED") from exc
    if not isinstance(postforward,dict) or set(postforward)!=EXTRA_POSTFORWARD_FIELDS:
        raise SeededRLSReviewError("POSTFORWARD_METADATA_SCOPE_REQUIRED")
    if (postforward["schema_version"]!=1 or
        postforward["scope"]!="NETWORK_ISOLATED_POSTFORWARD_ARM64_GTR_NOT_PRODUCTION" or
        postforward["source_commit"]!=previous.GTR_COMMIT or
        postforward["image_sha256"]!=previous.PG_IMAGE or
        postforward["postforward_migrations"]!=13 or
        postforward["read_only_sql"] is not True or
        postforward["network_access"] is not False or
        postforward["production_sql_writes"] is not False or
        postforward["canary_activation_attempted"] is not False or
        postforward["source_sql_or_user_data_exported"] is not False or
        postforward["hosted_connector_access"] is not False):
        raise SeededRLSReviewError("POSTFORWARD_SAFETY_OR_SOURCE_REFUSED")
    counts=postforward["counts"]
    if not isinstance(counts,dict) or counts!={"functions":793,"policies":350,
        "private_usage":3,"relation_grants":5136,"tables":212,"views":2}:
        raise SeededRLSReviewError("POSTFORWARD_SCHEMA_DRIFT")
    return {
        "schema_version":1,"kind":KIND,
        "source_commit":previous.GTR_COMMIT,
        "postgrest_image_sha256":previous.REST_IMAGE,
        "postgres_image_sha256":previous.PG_IMAGE,
        "observer_sha256":EXPECTED_OBSERVER_SHA,
        "http_receipt_sha256":EXPECTED_HTTP_SHA,
        "replay_receipt_sha256":EXPECTED_REPLAY_SHA,
        "postforward_receipt_sha256":EXPECTED_POSTFORWARD_SHA,
        "original_native_13_migrations_passed":True,
        "original_business_smoke_suites_passed":17,
        "local_arm64_postgrest_http_role_checks_passed":baseline["http_check_count"],
        "four_invalid_rpc_post_requests_resolved_as_application_exceptions":{
            "count":len(codes),"error_code":"P0001",
            "all_rpc_business_outcomes_verified":False
        },
        "synthetic_rls_checks_passed":len(checks),
        "synthetic_rls_records_retained":False,
        "customer_a_own_profile_row_count":1,
        "customer_a_other_profile_row_count":0,
        "customer_a_own_customer_row_count":1,
        "customer_a_other_customer_row_count":0,
        "customer_b_cannot_see_customer_a":True,
        "admin_can_see_seeded_customer_b":True,
        "customer_cannot_see_admin_role":True,
        "unseeded_caller_cannot_see_seeded_customer":True,
        "authenticated_catalog_read_rpc_http_200":True,
        "anonymous_stock_item_image_401_200_401_reversible":True,
        "disposable_fixture_only":True,
        "postgrest_sidecar_removed":True,
        "original_supabase_containers_preserved":True,
        "real_hosted_customer_data_or_keys_accessed":False,
        "production_writes":False,
        "real_nissan_gtr_traffic_migrated":False,
        "realtime_api_auth_storage_r2_payment_cron_all_qualified":False,
        "separate_live_canary_refusal_resolved":False,
        "nissan_gtr_cutover_authorized":False,
        "production_deployment_authorized":False,
        "all_77_authenticated_dml_privileges_reviewed":False,
        "limitations":[
            "P0001 is a real PostgreSQL application exception for deliberately invalid inputs, not a successful financial or POS operation.",
            "Ten RLS and one read-only RPC assertions use local seeded fictional users, not production identities or sessions.",
            "Read-only PostgREST positive paths do not validate stateful writes or the 77 DML grant differences.",
            "No external connectivity, provider callbacks, Storage/R2 object bytes, Auth tokens or live migration were exercised.",
            "The original safety-refused canary action remains blocked and cannot be bypassed by this evidence."
        ]
    }

def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http",type=pathlib.Path,required=True)
    parser.add_argument("--replay",type=pathlib.Path,required=True)
    parser.add_argument("--postforward",type=pathlib.Path,required=True)
    parser.add_argument("--out",type=pathlib.Path,required=True)
    a=parser.parse_args(argv)
    try:
        http=previous.read_exact(a.http,EXPECTED_HTTP_SHA)
        replay=previous.read_exact(a.replay,EXPECTED_REPLAY_SHA)
        postforward=previous.read_exact(a.postforward,EXPECTED_POSTFORWARD_SHA)
        report=validate(http,replay,postforward)
        artifact_writer.write_bundle(a.out,{"rls-role-gates-no-release.json":json.dumps(report,indent=2,sort_keys=True)+"\n"})
        print("POSTGREST_SYNTHETIC_RLS_GREEN_PRODUCTION_RELEASE_BLOCKED")
        return 0
    except (previous.HTTPGateError,SeededRLSReviewError,OSError,artifact_writer.CandidateError):
        print("POSTGREST_RLS_EVIDENCE_INVALID_RELEASE_BLOCKED")
        return 2

if __name__=="__main__":
    raise SystemExit(main())
