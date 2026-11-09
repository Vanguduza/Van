"""Deterministic exact-readback tests for isolated GTR ARM64 PostgREST."""
from __future__ import annotations
import copy
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import gtr_postgrest_http_gate as gate

EVIDENCE=ROOT/"evidence/2026-11-09-postgrest-http"
HTTP=EVIDENCE/"postgrest-local-http-result.json"
REPLAY=EVIDENCE/"replay-final-receipt.json"

def sample():
    return json.loads(HTTP.read_text()),json.loads(REPLAY.read_text())

class PostgrestHTTPGateTests(unittest.TestCase):
    def report(self,http=None,replay=None):
        h,r=sample()
        return gate.evaluate(h if http is None else http,r if replay is None else replay)
    def test_real_receipts_have_exact_hashes(self):
        self.assertEqual(gate.digest(HTTP.read_bytes()),gate.HTTP_SHA)
        self.assertEqual(gate.digest(REPLAY.read_bytes()),gate.REPLAY_SHA)
        self.assertEqual(gate.read_exact(HTTP,gate.HTTP_SHA)["success"],True)
    def test_actual_native_http_run_accepted(self):
        r=self.report()
        self.assertEqual(r["http_check_count"],12)
        self.assertTrue(r["anonymous_stock_images_401_to_200_to_401"])
        self.assertTrue(r["original_supabase_containers_preserved"])
    def test_release_never_authorized_even_when_green(self):
        r=self.report()
        for field in (*gate.NO_RELEASE,"original_canary_refusal_resolved",
                      "actual_gtr_user_roles_or_business_data_transferred",
                      "business_function_end_to_end_success_verified"):
            self.assertIs(r[field],False,field)
    def test_source_head_tampering_refused(self):
        h,_=sample();h["source_commit"]="0"*40
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_donor_image_tampering_refused(self):
        h,_=sample();h["original_pg_replay_image"]="sha256:"+"0"*64
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_postgrest_image_tampering_refused(self):
        h,_=sample();h["postgrest_image"]="sha256:"+"0"*64
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_wrong_database_refused(self):
        h,_=sample();h["database"]="postgres"
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_hosted_access_refused(self):
        h,_=sample();h["real_supabase_or_hosted_data_accessed"]=True
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_network_exposure_refused(self):
        h,_=sample();h["host_ports_published"]=True
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_missing_network_isolation_refused(self):
        h,_=sample();h["network_none"]=False
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_saved_token_refused(self):
        h,_=sample();h["credential_or_jwt_saved"]=True
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_unremoved_sidecar_refused(self):
        h,_=sample();h["sidecar_removed"]=False
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_fixture_grant_not_revoked_refused(self):
        h,_=sample();h["fixture_grant_revoked"]=False
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_table_privilege_restoration_missing_refused(self):
        h,_=sample();h["persistent_anon_stock_image_privilege_restored_to_initial_denial"]=False
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_bad_anon_denial_refused(self):
        h,_=sample();h["requests"][1]["status"]=200
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_grant_failed_http_refused(self):
        h,_=sample();h["requests"][-2]["status"]=403
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_revoke_failed_http_refused(self):
        h,_=sample();h["requests"][-1]["status"]=200
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_authentication_role_drift_refused(self):
        h,_=sample();h["requests"][3]["authenticated_synthetic"]=False
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_rpc_missing_endpoint_refused(self):
        h,_=sample();h["requests"][6]["status"]=404
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_rpc_falsely_successful_refused(self):
        h,_=sample();h["requests"][6]["status"]=200
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_direct_dml_denial_removed_refused(self):
        h,_=sample();h["requests"][9]["status"]=201
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_replay_missing_migration_refused(self):
        _,r=sample();r["migration_total"]=12
        with self.assertRaises(gate.HTTPGateError):self.report(replay=r)
    def test_replay_missing_smoke_refused(self):
        _,r=sample();r["smoke_count"]=16
        with self.assertRaises(gate.HTTPGateError):self.report(replay=r)
    def test_replay_donor_modified_refused(self):
        _,r=sample();r["original_containers_preserved"]=False
        with self.assertRaises(gate.HTTPGateError):self.report(replay=r)
    def test_extra_http_receipt_field_refused(self):
        h,_=sample();h["secret"]="untrusted"
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_extra_request_field_refused(self):
        h,_=sample();h["requests"][0]["body"]="unsafe"
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_duplicate_label_refused(self):
        h,_=sample();h["requests"][4]["label"]=h["requests"][0]["label"]
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_path_substitution_refused(self):
        h,_=sample();h["requests"][0]["url_path_only"]="/private/profiles"
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_boolean_as_status_refused(self):
        h,_=sample();h["requests"][0]["status"]=True
        with self.assertRaises(gate.HTTPGateError):self.report(http=h)
    def test_wrong_receipt_digest_refused(self):
        with self.assertRaises(gate.HTTPGateError):gate.read_exact(HTTP,"a"*64)
    def test_non_private_output_refused(self):
        h,r=sample()
        with tempfile.TemporaryDirectory() as d:
            out=pathlib.Path(d)/"receipt"
            # Immutable fixture input may be read regardless of mount, but
            # the safe writer itself must reject second use.
            with patch.object(gate,"HTTP_SHA",gate.digest(HTTP.read_bytes())),patch.object(gate,"REPLAY_SHA",gate.digest(REPLAY.read_bytes())):
                self.assertEqual(gate.main(["--http",str(HTTP),"--replay",str(REPLAY),"--out",str(out)]),0)
                self.assertEqual(out.stat().st_mode & 0o777,0o700)
                self.assertEqual((out/"postgrest-http-admission-blocked.json").stat().st_mode & 0o777,0o600)
                self.assertEqual(gate.main(["--http",str(HTTP),"--replay",str(REPLAY),"--out",str(out)]),2)
    def test_no_remote_executor_in_source(self):
        s=(ROOT/"tools/gtr_postgrest_http_gate.py").read_text()
        for bad in ("subprocess","psycopg","socket.","requests.get(","docker run","docker exec","ssh -","mcp__Supabase__execute_sql"):
            self.assertNotIn(bad,s)

if __name__=="__main__":unittest.main()
