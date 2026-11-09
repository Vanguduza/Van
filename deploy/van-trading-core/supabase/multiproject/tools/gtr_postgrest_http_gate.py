#!/usr/bin/env python3
"""Fail-closed readback of pinned Nissan GTR ARM64 PostgREST HTTP evidence.

Only consumes immutable JSON receipts from disposable offline fixtures. This
module has no database, HTTP, SSH, Docker or production-execution capability.
No possible evidence status can grant a live canary or cutover authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re

import render as artifacts

GTR_COMMIT="8131858c7c7479d178cbe9e246f83cb49ed80f5e"
PG_IMAGE="sha256:f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00"
REST_IMAGE="sha256:c9dc201e555f5d8e37e7f39cdd4df0229774996e213bfd7de8d10ac609030f2c"
HTTP_SHA="2e96a96db61e889cb815696f5fa078cc75b67789c7afb24298513da039258a01"
REPLAY_SHA="1ac085b0d837ca958102eaa99ff13b1e55892a2923a9b88e6b9fd8c0bb6ce2d0"
OBSERVER_SHA="def0d944c70a10541787bb9e0d8d9200753fce1f2def1c9a8b3fe3de74971dcb"
KIND="GTR_ARM64_POSTGREST_HTTP_ROLE_GATE_NOT_PRODUCTION_ADMISSION"
NO_RELEASE=("production_deployed","live_canary_authorized","hosted_migrations_applied","nissan_cutover_authorized")
REQUIRED_HTTP_FIELDS={
  "schema_version","kind","source_commit","original_pg_replay_image","postgrest_image",
  "database","network_none","postgrest_network_shared_only_with_fixture",
  "host_ports_published","real_supabase_or_hosted_data_accessed",
  "jwt_from_cryptographically_random_synthetic_secret","credential_or_jwt_saved",
  "production_writes","requests","success","ready","fixture_only_grant_test",
  "fixture_grant_revoked","persistent_anon_stock_image_privilege_restored_to_initial_denial",
  "all_http_results","sidecar_removed"
}
REQUIRED_REQUEST_FIELDS={
    "label","method","authenticated_synthetic","status","url_path_only"
}
REQUIRED_REPLAY_FIELDS={
    "runner_returncode","runner_state","migration_total","all_migrations_passed",
    "smoke_count","all_smokes_passed","original_containers_preserved",
    "temporary_container_removed","capture_completed","capture_failure",
    "result_success","new_fixture_data_only"
}
# Exact observations from the original source and no-network, no-port fixture.
# They are a reproducible receipt, not a universal response status contract.
EXPECTED=[
 ("anon_public_exchange_rate","GET",False,"/daily_exchange_rates",200),
 ("anon_stock_images_before","GET",False,"/stock_item_images",401),
 ("auth_stock_images_read","GET",True,"/stock_item_images",200),
 ("auth_hr_grades_read","GET",True,"/hr_grades",200),
 ("anon_hr_grades_denied","GET",False,"/hr_grades",401),
 ("auth_rpc_cart_legacy_default","POST",True,"/rpc/create_pos_cart",400),
 ("auth_rpc_hr_legacy_defaults","POST",True,"/rpc/create_hr_role",400),
 ("auth_rpc_garage_legacy_defaults","POST",True,"/rpc/upsert_customer_garage_vehicle",400),
 ("auth_rpc_staff_legacy_defaults","POST",True,"/rpc/upsert_staff_product_page",400),
 ("auth_hr_grades_direct_insert_denied","POST",True,"/hr_grades",403),
 ("anon_stock_images_after_fixture_grant","GET",False,"/stock_item_images",200),
 ("anon_stock_images_after_fixture_revoke","GET",False,"/stock_item_images",401)
]
class HTTPGateError(ValueError):
    pass

def digest(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def read_exact(path:pathlib.Path,expected:str,max_bytes=16384)->dict:
    if not path.is_absolute() or ".." in path.parts or path.is_symlink() or not path.is_file():
        raise HTTPGateError("PRIVATE_ABSOLUTE_RECEIPT_PATH_REQUIRED")
    if path.stat().st_size>max_bytes or path.stat().st_size<=0:
        raise HTTPGateError("RECEIPT_SIZE_REFUSED")
    raw=path.read_bytes()
    if digest(raw)!=expected:
        raise HTTPGateError("SOURCE_RECEIPT_SHA_CHANGED")
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise HTTPGateError("DUPLICATE_JSON_KEYS")
            d[k]=v
        return d
    try:
        return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _x: (_ for _ in ()).throw(HTTPGateError("NONFINITE_JSON_REFUSED")))
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:
        raise HTTPGateError("RECEIPT_PARSE_FAILED") from exc

def evaluate(http:dict,replay:dict)->dict:
    if not isinstance(http,dict) or set(http)!=REQUIRED_HTTP_FIELDS:
        raise HTTPGateError("EXACT_HTTP_FIELDS_REQUIRED")
    if http["kind"]!="GTR_REAL_LOCAL_POSTGREST_ARM64_HTTP_REHEARSAL_NOT_PRODUCTION" or type(http["schema_version"]) is not int or http["schema_version"]!=1:
        raise HTTPGateError("EXACT_HTTP_KIND_REQUIRED")
    if http["source_commit"]!=GTR_COMMIT or http["original_pg_replay_image"]!=PG_IMAGE or http["postgrest_image"]!=REST_IMAGE:
        raise HTTPGateError("EXACT_SOURCE_AND_IMAGES_REQUIRED")
    if http["database"]!="gtr_replay":
        raise HTTPGateError("ONLY_DISPOSABLE_DB_ALLOWED")
    expected_true=(
        "network_none","postgrest_network_shared_only_with_fixture",
        "jwt_from_cryptographically_random_synthetic_secret","success","ready",
        "fixture_only_grant_test","fixture_grant_revoked",
        "persistent_anon_stock_image_privilege_restored_to_initial_denial",
        "all_http_results","sidecar_removed"
    )
    expected_false=("host_ports_published","real_supabase_or_hosted_data_accessed",
        "credential_or_jwt_saved","production_writes")
    if any(http[k] is not True for k in expected_true) or any(http[k] is not False for k in expected_false):
        raise HTTPGateError("OFFLINE_SAFETY_OR_CLEANUP_FAILED")
    req=http["requests"]
    if not isinstance(req,list) or len(req)!=len(EXPECTED):
        raise HTTPGateError("EXACT_TWELVE_HTTP_CHECKS_REQUIRED")
    result=[]
    for i,(label,method,auth,url,status) in enumerate(EXPECTED):
        row=req[i]
        if not isinstance(row,dict) or set(row)!=REQUIRED_REQUEST_FIELDS:
            raise HTTPGateError("HTTP_REQUEST_PROVENANCE_FIELDS_REQUIRED")
        if (row["label"]!=label or row["method"]!=method
            or row["authenticated_synthetic"] is not auth or row["url_path_only"]!=url
            or type(row["status"]) is not int or row["status"]!=status):
            raise HTTPGateError("HTTP_BEHAVIOR_OR_ROLE_CHANGED")
        result.append({"name":label,"status":status,"synthetic_authenticated":auth})
    if not isinstance(replay,dict) or set(replay)!=REQUIRED_REPLAY_FIELDS:
        raise HTTPGateError("EXACT_REPLAY_FIELDS_REQUIRED")
    for k in ("all_migrations_passed","all_smokes_passed","original_containers_preserved",
              "temporary_container_removed","capture_completed","result_success","new_fixture_data_only"):
        if replay[k] is not True:raise HTTPGateError("ORIGINAL_REPLAY_GATE_NOT_GREEN")
    if (type(replay["runner_returncode"]) is not int or replay["runner_returncode"]!=0
        or replay["runner_state"]!="PASS" or replay["capture_failure"] is not None
        or type(replay["migration_total"]) is not int or replay["migration_total"]!=13
        or type(replay["smoke_count"]) is not int or replay["smoke_count"]!=17):
        raise HTTPGateError("POSTFORWARD_RUN_NOT_GREEN")
    return {
      "schema_version":1,"kind":KIND,
      "source_commit":GTR_COMMIT,
      "pg_image":PG_IMAGE,"postgrest_image":REST_IMAGE,
      "http_receipt_sha256":HTTP_SHA,"replay_receipt_sha256":REPLAY_SHA,
      "observer_sha256":OBSERVER_SHA,
      "http_checks":result,"http_check_count":len(result),
      "full_13_migration_replay_pass":True,"business_smoke_suite_count":17,
      "no_production_or_hosted_changes":True,
      "original_supabase_containers_preserved":True,
      "fixture_pg_and_sidecar_removed":True,
      "anonymous_stock_images_401_to_200_to_401":True,
      "synthetic_authenticated_request_pass":True,
      "four_rpc_routes_returned_400_validation_errors":True,
      "negative_authenticated_direct_insert_denied_403":True,
      "business_function_end_to_end_success_verified":False,
      "postgrest_error_body_codes_verified":False,
      "actual_gtr_user_roles_or_business_data_transferred":False,
      "original_canary_refusal_resolved":False,
      "production_deployed":False,"live_canary_authorized":False,
      "hosted_migrations_applied":False,"nissan_cutover_authorized":False,
      "critical_limits":[
        "HTTP 400 is NOT evidence of a successful business transaction or exact SQLSTATE without response error-code capture.",
        "Only a disposable, zero-external-network ARM64 fixture, one synthetic JWT, and recorded endpoints were tested.",
        "The grant/revoke experiment committed changes solely in the disposable fixture; the fixture and sidecar were removed.",
        "No JWT, password, database row, private object, real customer or payment input is retained.",
        "The 77 authenticated DML privilege differences are NOT automatically approved by these HTTP tests.",
        "No result bypasses the earlier live canary refusal or signed owner production admission."
      ]
    }

def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--http",type=pathlib.Path,required=True)
    p.add_argument("--replay",type=pathlib.Path,required=True)
    p.add_argument("--out",type=pathlib.Path,required=True)
    args=p.parse_args(argv)
    try:
        http=read_exact(args.http,HTTP_SHA)
        replay=read_exact(args.replay,REPLAY_SHA)
        report=evaluate(http,replay)
        artifacts.write_bundle(args.out,{"postgrest-http-admission-blocked.json":json.dumps(report,indent=2,sort_keys=True)+"\n"})
        print("POSTGREST_ISOLATED_HTTP_GREEN_PRODUCTION_ADMISSION_BLOCKED")
        return 0
    except (HTTPGateError,OSError,artifacts.CandidateError):
        print("POSTGREST_HTTP_EVIDENCE_INVALID_RELEASE_BLOCKED")
        return 2

if __name__=="__main__":
    raise SystemExit(main())
