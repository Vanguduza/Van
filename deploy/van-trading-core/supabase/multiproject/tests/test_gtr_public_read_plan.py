"""Fail-closed unit checks for the source-only GTR public-read plan."""
import pathlib,sys,unittest,tempfile,json,hashlib
from unittest.mock import patch
ROOT=pathlib.Path(__file__).parent
TOOLS=ROOT.parent/"tools"
sys.path.insert(0,str(TOOLS))
import gtr_public_read_plan as g

class PublicReadPlanTests(unittest.TestCase):
    def test_single_exact_grant(self):
        sql=g.render("nissan_gtr")
        self.assertEqual(sql.count("GRANT SELECT ON TABLE public.stock_item_images TO anon;"),1)
        self.assertEqual(sql.count("\nGRANT "),1)
        self.assertNotIn("\nREVOKE ",sql)
        self.assertNotIn("\nCREATE ",sql)
        self.assertNotIn("\nDROP ",sql)
        self.assertNotIn("\nDELETE ",sql)
    def test_reject_original_database(self):
        for name in ("postgres","_supabase","supabase","template0","template1","gtr_replay_backup"):
            with self.subTest(name=name),self.assertRaises(g.GrantPlanError):g.render(name)
    def test_unsafe_identifier_refused(self):
        for name in ("",None,"foo;DROP DATABASE postgres","nissan-gtr","UPPER","a"*64,"a.b"," a","$dollar","a' OR 1=1"):
            with self.subTest(name=name),self.assertRaises(g.GrantPlanError):g.render(name)
    def test_explicit_project_binding(self):
        a=g.render("gtr_replay")
        self.assertIn("current_database() <> 'gtr_replay'",a)
        self.assertIn("current_user <> 'postgres'",a)
        self.assertIn("SET LOCAL search_path=pg_catalog",a)
    def test_rls_policy_guard(self):
        s=g.render("nissan_gtr")
        for text in ("c.relrowsecurity","p.policyname='stock_item_images_public_read'","p.cmd='SELECT'",
                     "'anon'=ANY(p.roles)","p.qual='true'","p.with_check IS NULL"):
            self.assertIn(text,s)
    def test_transactional(self):
        s=g.render("nissan_gtr")
        self.assertIn("\nBEGIN;\n",s)
        self.assertTrue(s.endswith("COMMIT;\n"))
        self.assertLess(s.index("BEGIN;"),s.index("GRANT SELECT"))
    def test_review_not_authorized(self):
        m=g.manifest("nissan_gtr")
        for p in ("production_sql_executed","release_admitted","canary_authorized",
                  "migration_history_repair_authorized","nissan_gtr_cutover_authorized"):
            self.assertFalse(m[p],p)
        self.assertEqual(m["privileges"],["SELECT"])
        self.assertEqual(m["tables_affected"],["public.stock_item_images"])
    def test_source_binding(self):
        self.assertEqual(g.manifest("nissan_gtr")["declared_source_commit"],"8131858c7c7479d178cbe9e246f83cb49ed80f5e")
        self.assertFalse(g.manifest("nissan_gtr")["source_bytes_verified_by_compiler"])
    def test_sql_digest(self):
        m=g.manifest("nissan_gtr")
        self.assertEqual(m["candidate_sql_sha256"],hashlib.sha256(g.render("nissan_gtr").encode()).hexdigest())
    def test_new_output_private(self):
        with tempfile.TemporaryDirectory() as d:
            parent=pathlib.Path(d)
            with self.assertRaises(g.GrantPlanError):
                g.render("_supabase")
            p=parent/"candidate"
            self.assertEqual(g.main(["--project-database","nissan_gtr","--out",str(p)]),0)
            self.assertEqual(p.stat().st_mode&0o777,0o700)
            self.assertEqual((p/"candidate-not-admitted.sql").stat().st_mode&0o777,0o600)
            self.assertEqual((p/"candidate-manifest.json").stat().st_mode&0o777,0o600)
            self.assertEqual(g.main(["--project-database","nissan_gtr","--out",str(p)]),2)
    def test_active_installation_output_refused(self):
        self.assertEqual(g.main(["--project-database","nissan_gtr","--out","/etc/dial-supabase/example"] ),2)
    def test_no_executor_in_module(self):
        s=(TOOLS/"gtr_public_read_plan.py").read_text()
        for marker in ("subprocess","psycopg","supabase.execute","docker exec","os.system","curl ","ssh "):
            self.assertNotIn(marker,s)

if __name__=="__main__":unittest.main()
