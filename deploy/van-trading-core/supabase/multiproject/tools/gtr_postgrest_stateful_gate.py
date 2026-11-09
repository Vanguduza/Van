#!/usr/bin/env python3
"""Check SHA-pinned disposable GTR HTTP write/RLS receipts, never release them.

This module has no SQL, socket, database or deployment functions. Even a
perfectly matching receipt cannot authorize a canary, grants or production.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import gtr_postgrest_seeded_rls_gate as seeded
import render as artifacts

HTTP_SHA="2afa1ce7268c0e3b2044b710840940b0c6b61ae4c3f89a84a306c82de7f812cd"
REPLAY_SHA="1ac085b0d837ca958102eaa99ff13b1e55892a2923a9b88e6b9fd8c0bb6ce2d0"
POSTFORWARD_SHA="17752b6d1d91d360d645d1dc888fd24dfb0dae51a291f4d49af77adc807d8a4b"
OBSERVER_SHA="c28387622503e0be4a2f6a153dcb2284fd71673484f8229b9335f8aead1fee4a"
MODULE_SHA="edef8440e5eebbc8e26c46ba2b92ada14dead58d49e05c5d39b5d4ae093d800e"
KIND="GTR_ARM64_STATEFUL_SYNTHETIC_HTTP_ROLLBACK_NOT_PRODUCTION_V1"
EXTRA=frozenset({
 "stateful_http_checks","stateful_http_check_count","stateful_http_tx_rollback_proven",
 "stateful_response_bodies_or_auth_tokens_saved",
 "three_temporary_fixture_insert_grants","three_temporary_fixture_grants_revoked",
 "three_fixture_grants_final_denial_verified"
})
# Exact ordering, status, HTTP role, and result count from the disposable run.
EXPECTED=(
 ("customer_before","customer_a","GET",200,1,None),
 ("customer_own_update_rollback","customer_a","PATCH",200,1,None),
 ("customer_after_http_rollback","customer_a","GET",200,1,None),
 ("customer_cross_update_no_rows","customer_a","PATCH",200,0,None),
 ("other_customer_unmodified","customer_b","GET",200,1,None),
 ("hr_grade_initial_dml_denied","admin","POST",403,None,"42501"),
 ("pos_pin_initial_dml_denied","admin","POST",403,None,"42501"),
 ("finance_threshold_initial_dml_denied","admin","POST",403,None,"42501"),
 ("hr_grade_admin_post_nonpersistent","admin","POST",201,1,None),
 ("hr_grade_not_persisted","admin","GET",200,0,None),
 ("hr_grade_unauthorized_denied","customer_a","POST",403,None,"42501"),
 ("pos_pin_admin_post_nonpersistent","admin","POST",201,1,None),
 ("pos_pin_not_persisted","admin","GET",200,0,None),
 ("pos_pin_unauthorized_denied","customer_a","POST",403,None,"42501"),
 ("finance_threshold_admin_post_nonpersistent","admin","POST",201,1,None),
 ("finance_threshold_not_persisted","admin","GET",200,0,None),
 ("finance_threshold_unauthorized_denied","finance","POST",403,None,"42501"),
 ("hr_grade_post_revoke_denied","admin","POST",403,None,"42501"),
 ("pos_pin_post_revoke_denied","admin","POST",403,None,"42501"),
 ("finance_threshold_post_revoke_denied","admin","POST",403,None,"42501")
)
FIELDS=frozenset({"actor","label","method","status","rows","sqlstate",
                  "response_body_saved","synthetic_fixture_only"})
class StatefulGateError(ValueError):pass

def evaluate(http,replay,forward):
    if not isinstance(http,dict) or set(http)!=(seeded.previous.REQUIRED_HTTP_FIELDS|seeded.EXTRA_HTTP_FIELDS|EXTRA):
        raise StatefulGateError("EXACT_EXTENDED_HTTP_FIELDS_REQUIRED")
    if (type(http["stateful_http_check_count"]) is not int or
            http["stateful_http_check_count"]!=len(EXPECTED)):
        raise StatefulGateError("EXACT_TWENTY_WRITE_CHECKS_REQUIRED")
    if any(http[k] is not True for k in (
        "stateful_http_tx_rollback_proven",
        "three_temporary_fixture_insert_grants",
        "three_temporary_fixture_grants_revoked",
        "three_fixture_grants_final_denial_verified"
    )) or http["stateful_response_bodies_or_auth_tokens_saved"] is not False:
        raise StatefulGateError("ISOLATED_GRANT_ROLLBACK_OR_DATA_CUSTODY_FAILED")
    checks=http["stateful_http_checks"]
    if not isinstance(checks,list) or len(checks)!=len(EXPECTED):
        raise StatefulGateError("MISSING_WRITE_CHECKS")
    for i,(label,actor,method,status,rows,sqlstate) in enumerate(EXPECTED):
        c=checks[i]
        if not isinstance(c,dict) or set(c)!=FIELDS:
            raise StatefulGateError("EXACT_WRITE_CHECK_FIELDS_REQUIRED")
        if (c["label"]!=label or c["actor"]!=actor or c["method"]!=method
            or type(c["status"]) is not int or c["status"]!=status
            or (c["rows"] is not None and type(c["rows"]) is not int)
            or c["rows"]!=rows or c["sqlstate"]!=sqlstate
            or c["response_body_saved"] is not False
            or c["synthetic_fixture_only"] is not True):
            raise StatefulGateError("SYNTHETIC_WRITE_BEHAVIOR_CHANGED_"+label)
    prior={k:http[k] for k in (seeded.previous.REQUIRED_HTTP_FIELDS|seeded.EXTRA_HTTP_FIELDS)}
    try:base=seeded.validate(prior,replay,forward)
    except (seeded.SeededRLSReviewError,seeded.previous.HTTPGateError) as e:
        raise StatefulGateError("PREVIOUS_REAL_RLS_AND_RPC_GATES_FAILED") from e
    if base["synthetic_rls_checks_passed"]!=10 or base["local_arm64_postgrest_http_role_checks_passed"]!=12:
        raise StatefulGateError("PREVIOUS_TEST_COUNTS_CHANGED")
    if (base["production_deployment_authorized"] is not False or
        base["separate_live_canary_refusal_resolved"] is not False):
        raise StatefulGateError("PREVIOUS_PRODUCTION_AUTHORITY_FAILURE")
    return {
      "schema_version":1,"kind":KIND,
      "source_commit":seeded.previous.GTR_COMMIT,
      "postgres_arm64_image":seeded.previous.PG_IMAGE,
      "postgrest_arm64_image":seeded.previous.REST_IMAGE,
      "source_bound_http_receipt_sha256":HTTP_SHA,
      "source_bound_replay_receipt_sha256":REPLAY_SHA,
      "source_bound_postforward_receipt_sha256":POSTFORWARD_SHA,
      "observer_source_sha256":OBSERVER_SHA,
      "transactional_test_module_sha256":MODULE_SHA,
      "original_migrations_passed":13,"original_business_smokes_passed":17,
      "prior_role_http_checks_passed":12,"prior_synthetic_rls_http_checks_passed":10,
      "new_stateful_http_checks_passed":len(checks),
      "synthetic_customer_own_update_succeeded_and_rolled_back":True,
      "synthetic_cross_customer_update_denied_or_filtered":True,
      "three_staff_pos_finance_writes_with_temporary_fixture_grants_succeeded":True,
      "three_unauthorized_rls_writes_denied_with_42501":True,
      "three_original_missing_insert_grants_restored_to_denial":True,
      "business_records_retained":False,"real_user_identifiers_retained":False,
      "original_supabase_containers_preserved":True,
      "temporary_postgres_and_postgrest_containers_removed":True,
      "hosted_or_production_database_mutated":False,
      "real_nissan_gtr_user_data_touched":False,
      "complete_77_authenticated_grants_reviewed":False,
      "automatic_grants_allowed":False,
      "multi_project_isolation_qualified":False,
      "live_canary_refusal_resolved":False,
      "release_authorized":False,"nissan_gtr_cutover_authorized":False,
      "limits":[
        "Synthetic writes exercised a rollback-only local PostgREST, not real commercial transactions.",
        "Three scoped GRANT INSERT changes were made only to a throwaway test database and explicitly revoked.",
        "Reproducing a role's SQL INSERT access does not justify a production GRANT or bypass RLS policy review.",
        "Actual app-client OAuth/Auth, Edge, Storage/R2, payments, hosted cron and data backups are not verified.",
        "Earlier explicit live-canary safety refusal and owner-signed release gates remain binding."
      ]
    }

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--http",type=Path,required=True)
    p.add_argument("--replay",type=Path,required=True)
    p.add_argument("--postforward",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        h=seeded.previous.read_exact(a.http,HTTP_SHA)
        r=seeded.previous.read_exact(a.replay,REPLAY_SHA)
        f=seeded.previous.read_exact(a.postforward,POSTFORWARD_SHA)
        result=evaluate(h,r,f)
        artifacts.write_bundle(a.out,{
            "stateful-http-no-release.json":json.dumps(result,sort_keys=True,indent=2)+"\n"})
        print("GTR_STATEFUL_DISPOSABLE_HTTP_GREEN_LIVE_RELEASE_BLOCKED")
        return 0
    except (OSError,ValueError,artifacts.CandidateError):
        print("GTR_STATEFUL_HTTP_EVIDENCE_INVALID_LIVE_RELEASE_BLOCKED")
        return 2

if __name__=="__main__":raise SystemExit(main())
