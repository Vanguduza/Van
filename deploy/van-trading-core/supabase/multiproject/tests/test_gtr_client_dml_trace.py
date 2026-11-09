"""The static ACL tracer must not turn source absence into release authority."""
import copy
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parent
TOOL_DIR=(ROOT.parent/"tools") if (ROOT.parent/"tools"/"gtr_client_dml_trace.py").exists() else ROOT
sys.path.insert(0,str(TOOL_DIR))
import gtr_client_dml_trace as t

def valid_policy():
    entries=[{"table":"stock_item_images","role":"anon","privilege":"SELECT",
              "applicable_policy_names":["stock_item_images_public_read"]}]
    ops=("INSERT","UPDATE","DELETE")
    for i in range(30):
        for op in ops[:3 if i<17 else 2]:
            entries.append({"table":f"t{i:02d}","role":"authenticated",
               "privilege":op,"applicable_policy_names":[f"policy_t{i:02d}"]})
    assert len(entries)==78
    return {
        "schema_version":1,
        "kind":"GTR_READ_ONLY_POLICY_APPLICABLE_MISSING_GRANTS_NOT_RELEASE",
        "hosted_transaction":"REPEATABLE READ READ ONLY",
        "production_change_performed":False,"apply_grants_authorized":False,
        "canary_activation_authorized":False,"policy_applicable_missing_grants":78,
        "grouped":{"authenticated_INSERT":27,"authenticated_UPDATE":27,"authenticated_DELETE":23,"anon_SELECT":1},
        "project_ref":t.PINNED_PROJECT,"source_commit":t.PINNED_SOURCE,"entries":entries
    }

def fake_git(root,*args):
    if args==("rev-parse","HEAD"):return t.PINNED_SOURCE
    if args==("status","--porcelain","--untracked-files=no"):return ""
    if args==("ls-files","--cached"):return "apps/web/lib/app.ts\nscripts/provision-canonical-staff.mjs"
    raise ValueError(args)

class TraceTests(unittest.TestCase):
    def test_exact_policy(self):
        self.assertEqual(len(t.validate_policy(valid_policy())),78)
    def test_reject_wrong_project(self):
        p=valid_policy();p["project_ref"]="different"
        with self.assertRaises(t.SourceTraceError):t.validate_policy(p)
    def test_reject_wrong_source(self):
        p=valid_policy();p["source_commit"]="a"*40
        with self.assertRaises(t.SourceTraceError):t.validate_policy(p)
    def test_reject_missing_policy_entry(self):
        p=valid_policy();p["entries"].pop()
        with self.assertRaises(t.SourceTraceError):t.validate_policy(p)
    def test_reject_policy_entry_extra_field(self):
        p=valid_policy();p["entries"][0]["sql"]="SELECT *"
        with self.assertRaises(t.SourceTraceError):t.validate_policy(p)
    def test_reject_duplicate(self):
        p=valid_policy();p["entries"][0]=p["entries"][1]
        with self.assertRaises(t.SourceTraceError):t.validate_policy(p)
    def test_reject_injected_table(self):
        p=valid_policy();p["entries"][1]["table"]="t00;DROP"
        with self.assertRaises(t.SourceTraceError):t.validate_policy(p)
    def test_reject_wrong_role(self):
        p=valid_policy();p["entries"][1]["role"]="service_role"
        with self.assertRaises(t.SourceTraceError):t.validate_policy(p)
    def test_reject_non_dml_authenticated(self):
        p=valid_policy();p["entries"][1]["privilege"]="SELECT"
        with self.assertRaises(t.SourceTraceError):t.validate_policy(p)
    def test_reject_wrong_table_count(self):
        p=valid_policy()
        for x in p["entries"]:
            if x["table"]=="t29":x["table"]="t28"
        with self.assertRaises(t.SourceTraceError):t.validate_policy(p)
    def test_select_kotlin_multiline(self):
        r=t.trace_one('return client.from("t00")\n  .select(Columns.list("id"))\n  .decodeList<Model>()','apps/android-customer/foo.kt',{"t00"})
        self.assertEqual([x["method"] for x in r["t00"]["direct_calls"]],["select"])
        self.assertEqual(r["t00"]["direct_calls"][0]["operation"],"READ")
    def test_update_js_multiline(self):
        r=t.trace_one('await client\n  .from("t00")\n  .update({v:1})\n  .eq("id",id);','apps/web/lib/foo.ts',{"t00"})
        self.assertEqual(r["t00"]["direct_calls"][0]["operation"],"UPDATE")
    def test_delete_js(self):
        r=t.trace_one('await admin.from("t00").delete().eq("id",x);','scripts/foo.mjs',{"t00"})
        self.assertEqual(r["t00"]["direct_calls"][0]["operation"],"DELETE")
    def test_upsert_js(self):
        r=t.trace_one('await admin.from("t00").upsert({id:1});','scripts/foo.mjs',{"t00"})
        self.assertEqual(r["t00"]["direct_calls"][0]["operation"],"INSERT_OR_UPDATE")
    def test_disconnected_statement_not_mistaken(self):
        r=t.trace_one('client.from("t00").select("id");\nother.delete();','apps/web/lib/foo.ts',{"t00"})
        self.assertEqual(r["t00"]["direct_calls"][0]["operation"],"READ")
    def test_literal_mention_without_call(self):
        r=t.trace_one('const schema = {t00:"table"};', 'packages/types.ts',{"t00"})
        self.assertEqual(r["t00"]["literal_occurrences"],1)
        self.assertEqual(r["t00"]["direct_calls"],[])
    def test_comment_not_a_call(self):
        r=t.trace_one('// .from("t00").delete();','apps/web/lib/foo.ts',{"t00"})
        self.assertEqual(r["t00"]["direct_calls"],[])
    def test_dynamic_not_proven(self):
        r=t.trace_one('const table = "t00";client.from(table).delete();','apps/web/lib/foo.ts',{"t00"})
        self.assertEqual(r["t00"]["direct_calls"],[])
    def test_preserves_line(self):
        r=t.trace_one('let x=1;\nclient.from("t00").insert({id:1});','apps/web/lib/foo.ts',{"t00"})
        self.assertEqual(r["t00"]["direct_calls"][0]["line"],2)
    def fixture(self,path,source='client.from("t00").select("id");'):
        p=pathlib.Path(path);(p/".git").mkdir()
        (p/"apps/web/lib").mkdir(parents=True)
        (p/"scripts").mkdir()
        (p/"apps/web/lib/app.ts").write_text(source)
        (p/"scripts/provision-canonical-staff.mjs").write_text(
            'const secretKey=env.SUPABASE_SECRET_KEY || env.SUPABASE_SERVICE_ROLE_KEY;'
            'const admin=createClient(url, secretKey, {});'
            'admin.from("staff_roles").delete();\nadmin.from("staff_roles").upsert({});')
        return p
    def test_realistic_source_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.fixture(tmp,'client.from("t00").select("id");')
            # Additional literal proof that staff provisioning cannot be
            # interpreted as a session-authenticated client mutation.
            with patch.object(t,"_git",side_effect=fake_git):
                report=t.scan(root,valid_policy())
            self.assertEqual(report["source_files_scanned"],2)
            self.assertEqual(report["authenticated_distinct_tables"],30)
            self.assertEqual(report["observed_server_admin_direct_write_calls"],0)
            self.assertEqual(report["other_direct_write_calls_observed"],0)
            self.assertFalse(report["authorization_to_apply_any_grant"])
            self.assertFalse(report["deployed_app_versions_verified"])
    def test_privileged_provisioning_classified_not_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.fixture(tmp)
            p=valid_policy()
            for row in p["entries"]:
                if row["table"]=="t29":row["table"]="staff_roles"
            with patch.object(t,"_git",side_effect=fake_git):
                report=t.scan(root,p)
            self.assertEqual(report["observed_server_admin_direct_write_calls"],2)
            self.assertEqual(report["other_direct_write_calls_observed"],0)
    def test_actual_client_write_remains_unresolved_not_auto_granted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.fixture(tmp,'client.from("t00").update({v:1});')
            with patch.object(t,"_git",side_effect=fake_git):
                report=t.scan(root,valid_policy())
            self.assertEqual(report["other_direct_write_calls_observed"],1)
            case=next(x for x in report["grant_cases"] if x["table"]=="t00")
            self.assertEqual(case["classification"],"EXPLICIT_WRITE_REQUIRES_MANUAL_ROLE_CHECK")
            self.assertFalse(case["automatic_grant_allowed"])
    def test_dirty_source_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.fixture(tmp)
            def dirty(_root,*args):
                if args[0]=="status":return " M apps/web/lib/app.ts"
                return fake_git(_root,*args)
            with patch.object(t,"_git",side_effect=dirty),self.assertRaisesRegex(t.SourceTraceError,"DIRTY"):
                t.scan(root,valid_policy())
    def test_unmaterialized_tracked_source_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.fixture(tmp)
            (root/"apps/web/lib/app.ts").unlink()
            with patch.object(t,"_git",side_effect=fake_git),self.assertRaisesRegex(t.SourceTraceError,"INCOMPLETE"):
                t.scan(root,valid_policy())
    def test_wrong_git_head_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.fixture(tmp)
            with patch.object(t,"_git",return_value="0"*40),self.assertRaisesRegex(t.SourceTraceError,"PINNED"):
                t.scan(root,valid_policy())
    def test_no_db_or_remote_executor(self):
        s=(TOOL_DIR/"gtr_client_dml_trace.py").read_text()
        for forbidden in ("psycopg","import requests","urllib.request","socket.socket","docker exec",
                          "CREATE ROLE", "GRANT SELECT ON TABLE", "mcp__Supabase__"):
            self.assertNotIn(forbidden,s)
    def test_output_read_only_and_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            src=root/"source";src.mkdir()
            self.fixture(src)
            policy=root/"policy.json";policy.write_text(json.dumps(valid_policy()))
            out=root/"result"
            with patch.object(t,"_git",side_effect=fake_git):
                self.assertEqual(t.main(["--source-root",str(src),"--policy-json",str(policy),"--out",str(out)]),0)
            self.assertEqual(out.stat().st_mode&0o777,0o700)
            self.assertEqual((out/"client-write-source-review.json").stat().st_mode&0o777,0o600)
            with patch.object(t,"_git",side_effect=fake_git):
                self.assertEqual(t.main(["--source-root",str(src),"--policy-json",str(policy),"--out",str(out)]),2)

if __name__=="__main__":unittest.main()
