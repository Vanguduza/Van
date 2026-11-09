"""Native signed disposable-transaction HTTP review and fail-closed refusals."""
from __future__ import annotations
import json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import gtr_postgrest_stateful_gate as g

E=ROOT/"evidence/2026-11-09-stateful-http"
H=E/"postgrest-local-http-result.json"
R=E/"replay-final-receipt.json"
F=E/"postforward-observer-result.json"

def load():
    return json.loads(H.read_text()),json.loads(R.read_text()),json.loads(F.read_text())
def check(h=None,r=None,f=None):
    old=load()
    return g.evaluate(old[0] if h is None else h,old[1] if r is None else r,old[2] if f is None else f)

class StatefulHTTPGateTests(unittest.TestCase):
    def test_actual_receipts_pass(self):
        j=check()
        self.assertEqual(j["new_stateful_http_checks_passed"],20)
        self.assertTrue(j["three_original_missing_insert_grants_restored_to_denial"])
        self.assertTrue(j["synthetic_customer_own_update_succeeded_and_rolled_back"])
    def test_exact_receipt_hashes(self):
        self.assertEqual(g.seeded.previous.digest(H.read_bytes()),g.HTTP_SHA)
        self.assertEqual(g.seeded.previous.digest(R.read_bytes()),g.REPLAY_SHA)
        self.assertEqual(g.seeded.previous.digest(F.read_bytes()),g.POSTFORWARD_SHA)
    def test_live_release_never_authorized(self):
        j=check()
        for key in ("release_authorized","nissan_gtr_cutover_authorized",
          "live_canary_refusal_resolved","hosted_or_production_database_mutated",
          "automatic_grants_allowed","complete_77_authenticated_grants_reviewed",
          "multi_project_isolation_qualified"):
            self.assertIs(j[key],False,key)
    def test_real_credentials_never_published(self):
        j=check()
        for key in ("business_records_retained","real_user_identifiers_retained",
                    "real_nissan_gtr_user_data_touched"):
            self.assertIs(j[key],False,key)
    def test_src_commit_mismatch(self):
        h,_,_=load();h["source_commit"]="0"*40
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_wrong_db_refused(self):
        h,_,_=load();h["database"]="postgres"
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_unexpected_fields_refused(self):
        h,_,_=load();h["production_token"]="secret"
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_missing_fields_refused(self):
        h,_,_=load();h.pop("stateful_http_checks")
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_wrong_count_refused(self):
        h,_,_=load();h["stateful_http_check_count"]=19
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_boolean_as_count_refused(self):
        h,_,_=load();h["stateful_http_check_count"]=True
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_missing_one_check_refused(self):
        h,_,_=load();h["stateful_http_checks"].pop()
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_extra_request_field_refused(self):
        h,_,_=load();h["stateful_http_checks"][0]["raw_body"]="unsafe"
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_saved_body_refused(self):
        h,_,_=load();h["stateful_response_bodies_or_auth_tokens_saved"]=True
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_one_saved_body_refused(self):
        h,_,_=load();h["stateful_http_checks"][0]["response_body_saved"]=True
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_wrong_grant_flag_refused(self):
        h,_,_=load();h["three_temporary_fixture_insert_grants"]=False
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_unrevoked_fixture_grants_refused(self):
        h,_,_=load();h["three_temporary_fixture_grants_revoked"]=False
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_unverified_final_denial_refused(self):
        h,_,_=load();h["three_fixture_grants_final_denial_verified"]=False
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_missing_transaction_rollback_refused(self):
        h,_,_=load();h["stateful_http_tx_rollback_proven"]=False
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_public_read_regression_refused(self):
        h,_,_=load();h["requests"][1]["status"]=200
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_existing_synthetic_cross_user_regression_refused(self):
        h,_,_=load();h["synthetic_rls_checks"][2]["row_count"]=1
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_missing_rpc_application_error_refused(self):
        h,_,_=load();h["rpc_error_codes"]["auth_rpc_cart_legacy_default"]="PGRST202"
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_missing_original_migration_refused(self):
        _,r,_=load();r["migration_total"]=12
        with self.assertRaises(g.StatefulGateError):check(r=r)
    def test_untested_final_schema_refused(self):
        _,_,f=load();f["counts"]["policies"]=351
        with self.assertRaises(g.StatefulGateError):check(f=f)
    def test_fixture_hosted_network_access_refused(self):
        h,_,_=load();h["real_supabase_or_hosted_data_accessed"]=True
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_disposable_cleanup_refused_if_absent(self):
        h,_,_=load();h["sidecar_removed"]=False
        with self.assertRaises(g.StatefulGateError):check(h=h)
    def test_result_identity_no_other_account_data(self):
        value=json.dumps(check())
        for token in ("@gtr.local","Bearer ey","a0000000-0000-4000","c0000000-0000-4000"):
            self.assertNotIn(token,value)
    def test_no_external_sql_docker_http_executor(self):
        source=(ROOT/"tools/gtr_postgrest_stateful_gate.py").read_text()
        for word in ("subprocess","psycopg","socket.socket","requests.get(","docker run",
                     "docker exec","mcp__Supabase__execute_sql"):
            self.assertNotIn(word,source)
    def test_new_private_bundle_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=pathlib.Path(tmp)/"new-candidate"
            argv=["--http",str(H),"--replay",str(R),"--postforward",str(F),"--out",str(dest)]
            self.assertEqual(g.main(argv),0)
            self.assertEqual(dest.stat().st_mode&0o777,0o700)
            self.assertEqual((dest/"stateful-http-no-release.json").stat().st_mode&0o777,0o600)
            self.assertEqual(g.main(argv),2)
    def test_invalid_digest_refused(self):
        with self.assertRaises(g.seeded.previous.HTTPGateError):
            g.seeded.previous.read_exact(H,"0"*64)

# One independent result-shape refusal per observed stateful request.
for _idx,(_label,_actor,_method,_status,_rows,_code) in enumerate(g.EXPECTED):
    def make_test(index):
        def run(self):
            h,_,_=load()
            target=h["stateful_http_checks"][index]
            target["status"]=999 if target["status"]!=999 else 0
            with self.assertRaises(g.StatefulGateError):
                check(h=h)
        return run
    setattr(StatefulHTTPGateTests,f"test_each_http_status_{_idx:02d}_{_label}",make_test(_idx))

if __name__=="__main__":unittest.main()
