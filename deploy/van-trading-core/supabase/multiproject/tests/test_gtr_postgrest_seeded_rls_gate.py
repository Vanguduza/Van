"""Source-bound refusal cases for the real synthetic-user PostgREST RLS run."""
from __future__ import annotations
import copy,json,pathlib,sys,tempfile,unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import gtr_postgrest_seeded_rls_gate as gate

EVI=ROOT/"evidence/2026-11-09-seeded-rls"
HTTP=EVI/"postgrest-local-http-result.json"
REPLAY=EVI/"replay-final-receipt.json"
POSTFORWARD=EVI/"postforward-observer-result.json"

def load():
    return (json.loads(HTTP.read_text()),json.loads(REPLAY.read_text()),
            json.loads(POSTFORWARD.read_text()))

def analyze(http=None,replay=None,postforward=None):
    x,y,z=load()
    return gate.validate(x if http is None else http,
                         y if replay is None else replay,
                         z if postforward is None else postforward)

class SeededRLSGateTests(unittest.TestCase):
    def test_exact_native_receipt_shas(self):
        self.assertEqual(gate.previous.digest(HTTP.read_bytes()),gate.EXPECTED_HTTP_SHA)
        self.assertEqual(gate.previous.digest(REPLAY.read_bytes()),gate.EXPECTED_REPLAY_SHA)
        self.assertEqual(gate.previous.digest(POSTFORWARD.read_bytes()),gate.EXPECTED_POSTFORWARD_SHA)
    def test_original_native_run_is_green(self):
        j=analyze()
        self.assertEqual(j["original_native_13_migrations_passed"],True)
        self.assertEqual(j["local_arm64_postgrest_http_role_checks_passed"],12)
        self.assertEqual(j["synthetic_rls_checks_passed"],10)
        self.assertEqual(j["four_invalid_rpc_post_requests_resolved_as_application_exceptions"]["error_code"],"P0001")
    def test_business_financial_success_not_claimed(self):
        j=analyze()
        self.assertFalse(j["four_invalid_rpc_post_requests_resolved_as_application_exceptions"]["all_rpc_business_outcomes_verified"])
        self.assertFalse(j["realtime_api_auth_storage_r2_payment_cron_all_qualified"])
        self.assertFalse(j["all_77_authenticated_dml_privileges_reviewed"])
    def test_all_releases_remain_refused(self):
        j=analyze()
        for k in ("separate_live_canary_refusal_resolved","production_deployment_authorized","nissan_gtr_cutover_authorized","real_nissan_gtr_traffic_migrated","real_hosted_customer_data_or_keys_accessed","production_writes"):
            self.assertIs(j[k],False)
    def test_four_code_names_bound(self):
        http,*_=load()
        self.assertEqual(set(http["rpc_error_codes"]),gate.EXPECTED_RPCS)
    def test_pgrst_missing_rpc_detected(self):
        http,*_=load()
        http["rpc_error_codes"]["auth_rpc_cart_legacy_default"]="PGRST202"
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_ambiguous_rpc_detected(self):
        http,*_=load()
        http["rpc_error_codes"]["auth_rpc_garage_legacy_defaults"]="PGRST203"
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_missing_rpc_entry_refused(self):
        http,*_=load();http["rpc_error_codes"].pop("auth_rpc_staff_legacy_defaults")
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_extra_rpc_entry_refused(self):
        http,*_=load();http["rpc_error_codes"]["future_rpc"]="P0001"
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_extra_capture_field_refused(self):
        http,*_=load();http["production_key"]="not allowed"
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_missing_capture_field_refused(self):
        http,*_=load();http.pop("synthetic_role_ids_stored")
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_no_real_user_data_accepted(self):
        http,*_=load();http["real_business_user_data_touched"]=True
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_no_stored_user_id_accepted(self):
        http,*_=load();http["synthetic_role_ids_stored"]=True
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_rls_check_count_refused_when_missing(self):
        http,*_=load();http["synthetic_rls_checks"].pop()
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_rls_count_boolean_refused(self):
        http,*_=load();http["synthetic_rls_check_count"]=True
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_rls_row_count_boolean_refused(self):
        http,*_=load();http["synthetic_rls_checks"][0]["row_count"]=True
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_rls_role_flip_refused(self):
        http,*_=load();http["synthetic_rls_checks"][0]["synthetic_role"]="admin"
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_other_customer_data_leak_refused(self):
        http,*_=load();http["synthetic_rls_checks"][2]["row_count"]=1
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_missing_own_customer_refused(self):
        http,*_=load();http["synthetic_rls_checks"][3]["row_count"]=0
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_customer_sees_admin_role_refused(self):
        http,*_=load();http["synthetic_rls_checks"][7]["row_count"]=1
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_admin_unable_to_read_seeded_customer_refused(self):
        http,*_=load();http["synthetic_rls_checks"][5]["row_count"]=0
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_unseeded_account_sees_customer_refused(self):
        http,*_=load();http["synthetic_rls_checks"][8]["row_count"]=1
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_positive_rpc_not_exposed_refused(self):
        http,*_=load();http["synthetic_rls_checks"][9]["http_status"]=404
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_one_rls_result_with_body_retained_refused(self):
        http,*_=load();http["synthetic_rls_checks"][0]["body_or_real_identifier_retained"]=True
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_extra_rls_result_field_refused(self):
        http,*_=load();http["synthetic_rls_checks"][0]["raw_user_email"]="redacted"
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_reordered_checks_refused(self):
        http,*_=load()
        http["synthetic_rls_checks"][0],http["synthetic_rls_checks"][1]=http["synthetic_rls_checks"][1],http["synthetic_rls_checks"][0]
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_old_http_denial_regression_refused(self):
        http,*_=load();http["requests"][1]["status"]=200
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_old_anon_grant_regression_refused(self):
        http,*_=load();http["requests"][10]["status"]=403
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_cleanup_failure_refused(self):
        http,*_=load();http["sidecar_removed"]=False
        with self.assertRaises(gate.SeededRLSReviewError):analyze(http=http)
    def test_replay_failure_refused(self):
        _,replay,_=load();replay["smoke_count"]=16
        with self.assertRaises(gate.SeededRLSReviewError):analyze(replay=replay)
    def test_source_changed_refused(self):
        _,_,post=load();post["source_commit"]="0"*40
        with self.assertRaises(gate.SeededRLSReviewError):analyze(postforward=post)
    def test_final_schema_changed_refused(self):
        _,_,post=load();post["counts"]["functions"]=794
        with self.assertRaises(gate.SeededRLSReviewError):analyze(postforward=post)
    def test_schema_forward_not_exact_refused(self):
        _,_,post=load();post["postforward_migrations"]=12
        with self.assertRaises(gate.SeededRLSReviewError):analyze(postforward=post)
    def test_observer_hosted_access_refused(self):
        _,_,post=load();post["hosted_connector_access"]=True
        with self.assertRaises(gate.SeededRLSReviewError):analyze(postforward=post)
    def test_observer_network_refused(self):
        _,_,post=load();post["network_access"]=True
        with self.assertRaises(gate.SeededRLSReviewError):analyze(postforward=post)
    def test_fixture_production_write_refused(self):
        _,_,post=load();post["production_sql_writes"]=True
        with self.assertRaises(gate.SeededRLSReviewError):analyze(postforward=post)
    def test_no_executor_capabilities(self):
        s=(ROOT/"tools/gtr_postgrest_seeded_rls_gate.py").read_text()
        for bad in ("subprocess","psycopg","socket.socket","requests.get(","docker exec","docker run","ssh -","mcp__Supabase__execute_sql"):
            self.assertNotIn(bad,s)
    def test_exact_receipt_gate_output_private_new_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=pathlib.Path(tmp)/"gate"
            self.assertEqual(gate.main(["--http",str(HTTP),"--replay",str(REPLAY),
                    "--postforward",str(POSTFORWARD),"--out",str(out)]),0)
            self.assertEqual(out.stat().st_mode & 0o777,0o700)
            self.assertEqual((out/"rls-role-gates-no-release.json").stat().st_mode & 0o777,0o600)
            self.assertEqual(gate.main(["--http",str(HTTP),"--replay",str(REPLAY),
                    "--postforward",str(POSTFORWARD),"--out",str(out)]),2)
    def test_modified_digest_refused(self):
        with self.assertRaises(gate.previous.HTTPGateError):
            gate.previous.read_exact(HTTP,"0"*64)
    def test_report_contains_no_user_identifiers(self):
        j=analyze()
        s=json.dumps(j)
        for marker in ("a0000000-0000-4000","c0000000-0000-4000","@gtr.local","Bearer "):
            self.assertNotIn(marker,s)

if __name__=="__main__":unittest.main()
