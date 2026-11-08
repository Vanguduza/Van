"""Preserve exact archived SQL; adjudicate only known export metadata differences."""
import copy
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/"tools"))
import gtr_archive_equivalence as eq
import gtr_history_reconcile as history

def digest(b):return hashlib.sha256(b).hexdigest()
V="20260905104822"
N="commerce_integrity_v1"
SQL=b"SELECT 1;\n"

def sample(*,version=V,name=N,body=SQL,final_lf=False):
    hosted=eq.hosted_export_wrapper(version,name)+body+(b"\n" if final_lf else b"")
    return hosted,body

def compare(hosted,legacy,*,version=V,name=N):
    return eq.compare_pair(version,name,hosted,legacy,digest(hosted),digest(legacy))

def catalog_data():
    groups={"legacy":[],"hosted_archive":[],"active":[]}
    data={}
    variants={}
    overlaps=[]
    for i in range(10):
        ver="2026090510"+str(4822+i).zfill(4)
        name="history_entry_"+str(i)
        legacy=f"SELECT {i};\n".encode()
        hosted=eq.hosted_export_wrapper(ver,name)+legacy+(b"\n" if i>=4 else b"")
        pl=f"supabase/migration-history/legacy/{ver}_{name}.sql"
        ph=f"supabase/live-history/{ver}_{name}.sql"
        for family,path,body in (("legacy",pl,legacy),("hosted_archive",ph,hosted)):
            groups[family].append({"path":path,"version":ver,"name":name,
               "source_file_sha256":digest(body),"bytes":len(body),"family":family})
            data[path]=body
        overlaps.append(ver)
        variants[ver]=sorted([digest(legacy),digest(hosted)])
    catalog={"commit":history.GTR_COMMIT,"manifest_sha256":history.MANIFEST_SHA,
        "cross_family_version_overlap":overlaps,
        "cross_family_content_variants":variants,"histories":groups}
    return catalog,data

class ArchivedEquivalenceTests(unittest.TestCase):
    def test_exact_pinned_provenance_template(self):
        expected=(f"-- Exported from the hosted project's supabase_migrations.schema_migrations ({V} {N}).\n"
          "-- Source of record for what production ran; see supabase/live-history/README.md.\n\n").encode()
        self.assertEqual(eq.hosted_export_wrapper(V,N),expected)
    def test_exact_body_after_wrapper(self):
        hosted,legacy=sample()
        record=compare(hosted,legacy)
        self.assertFalse(record["extra_final_lf"])
        self.assertEqual(record["normalized_body_sha256"],digest(SQL))
        self.assertEqual(record["classification"],"EXACT_BODY_AFTER_KNOWN_EXPORT_WRAPPER")
    def test_one_final_lf_tolerated_but_exactly_one(self):
        hosted,legacy=sample(final_lf=True)
        self.assertTrue(compare(hosted,legacy)["extra_final_lf"])
        with self.assertRaisesRegex(eq.ArchivedBodyError,"BODY_DIVERGED"):
            compare(hosted+b"\n",legacy)
    def test_internal_whitespace_change_refused(self):
        hosted,legacy=sample(body=b"SELECT  1;\n")
        with self.assertRaisesRegex(eq.ArchivedBodyError,"BODY_DIVERGED"):
            compare(hosted,SQL)
    def test_changed_sql_semicolon_refused(self):
        hosted,_=sample(body=b"SELECT 2;\n")
        with self.assertRaises(eq.ArchivedBodyError):compare(hosted,SQL)
    def test_arbitrary_comments_must_not_be_removed(self):
        hosted,legacy=sample(body=b"-- extra\n"+SQL)
        with self.assertRaisesRegex(eq.ArchivedBodyError,"BODY_DIVERGED"):
            compare(hosted,legacy[len(b"-- extra\n"):])
    def test_renamed_export_identity_refused(self):
        hosted,legacy=sample()
        for ver,name in (("20260905104823",N),(V,"alternate_name")):
            with self.subTest(ver=ver,name=name),self.assertRaisesRegex(eq.ArchivedBodyError,"WRAPPER"):
                compare(hosted,legacy,version=ver,name=name)
    def test_wrapper_requires_exact_lines(self):
        hosted,legacy=sample()
        bad=hosted.replace(b"Source of record",b"Source record",1)
        with self.assertRaisesRegex(eq.ArchivedBodyError,"WRAPPER"):
            compare(bad,legacy)
    def test_crlf_cannot_be_silently_normalized(self):
        hosted,_=sample(body=b"SELECT 1;\r\n")
        with self.assertRaises(eq.ArchivedBodyError):compare(hosted,SQL)
    def test_stale_source_sha_refused(self):
        hosted,legacy=sample()
        with self.assertRaisesRegex(eq.ArchivedBodyError,"DIGEST_CHANGED"):
            eq.compare_pair(V,N,hosted,legacy,"0"*64,digest(legacy))
    def test_bad_name_or_version_refused(self):
        for v,n in (("2026-09-05",N),(V,"name;drop"),(V,"Name"),(V,"")):
            with self.subTest(v=v,n=n),self.assertRaises(eq.ArchivedBodyError):eq.hosted_export_wrapper(v,n)
    def test_non_bytes_and_empty_refused(self):
        with self.assertRaises(eq.ArchivedBodyError):eq.compare_pair(V,N,"text",SQL,"0"*64,digest(SQL))
        header=eq.hosted_export_wrapper(V,N)
        with self.assertRaisesRegex(eq.ArchivedBodyError,"EMPTY"):
            compare(header,b"")
    def test_catalog_reconciles_only_ten_pinned_pairs(self):
        catalog,data=catalog_data()
        with patch.object(history,"source_catalog",return_value=catalog),patch.object(history,"public_source",side_effect=lambda _,path,sha: data[path]):
            report=eq.resolve(pathlib.Path("/synthetic/fixed"))
        self.assertEqual(report["overlap_count"],10)
        self.assertEqual(report["exact_wrapper_only"],4)
        self.assertEqual(report["wrapper_plus_one_final_lf"],6)
        self.assertFalse(report["independent_current_hosted_ledger_observed"])
        self.assertFalse(report["production_deploy_authorized"])
        self.assertFalse(report["may_repair_hosted_history"])
        self.assertEqual(len(report["records"]),10)
    def test_catalog_different_source_count_refused(self):
        catalog,data=catalog_data()
        catalog["cross_family_version_overlap"].pop()
        with patch.object(history,"source_catalog",return_value=catalog),self.assertRaisesRegex(eq.ArchivedBodyError,"EXACT_TEN"):
            eq.resolve(pathlib.Path("/synthetic/fixed"))
    def test_catalog_incorrect_digest_set_refused(self):
        catalog,data=catalog_data()
        first=catalog["cross_family_version_overlap"][0]
        catalog["cross_family_content_variants"][first]=["0"*64,"1"*64]
        with patch.object(history,"source_catalog",return_value=catalog),self.assertRaisesRegex(eq.ArchivedBodyError,"VARIANT_DIGEST"):
            eq.resolve(pathlib.Path("/synthetic/fixed"))
    def test_catalog_name_conflict_refused(self):
        catalog,data=catalog_data()
        catalog["histories"]["legacy"][0]["name"]="different"
        with patch.object(history,"source_catalog",return_value=catalog),self.assertRaisesRegex(eq.ArchivedBodyError,"NAME_OR_FAMILY"):
            eq.resolve(pathlib.Path("/synthetic/fixed"))
    def test_catalog_modified_verified_body_refused(self):
        catalog,data=catalog_data()
        original=catalog["histories"]["hosted_archive"][0]["path"]
        data[original]=data[original].replace(b"SELECT 0",b"SELECT 3")
        with patch.object(history,"source_catalog",return_value=catalog),patch.object(history,"public_source",side_effect=lambda _,path,sha:data[path]),self.assertRaisesRegex(eq.ArchivedBodyError,"DIGEST_CHANGED"):
            eq.resolve(pathlib.Path("/synthetic/fixed"))
    def test_not_treat_current_hosted_ledger_as_observed(self):
        catalog,data=catalog_data()
        with patch.object(history,"source_catalog",return_value=catalog),patch.object(history,"public_source",side_effect=lambda _,path,sha:data[path]):
            report=eq.resolve(pathlib.Path("/synthetic/fixed"))
        self.assertNotIn("CURRENT_HOSTED_VERIFIED",json.dumps(report))
        self.assertFalse(report["may_apply_migrations"])
        self.assertFalse(report["may_activate_canary"])
        self.assertFalse(report["may_cutover"])
    def test_safe_new_private_output_no_overwrite(self):
        catalog,data=catalog_data()
        with tempfile.TemporaryDirectory() as d:
            output=pathlib.Path(d)/"candidate"
            with patch.object(history,"source_catalog",return_value=catalog),patch.object(history,"public_source",side_effect=lambda _,path,sha:data[path]),redirect_stdout(io.StringIO()) as out:
                self.assertEqual(eq.main(["--source-root","/synthetic/fixed","--out",str(output)]),0)
            self.assertEqual(output.stat().st_mode & 0o777,0o700)
            self.assertTrue(all(x.stat().st_mode & 0o777==0o600 for x in output.iterdir()))
            self.assertNotIn("SELECT",out.getvalue())
            with patch.object(history,"source_catalog",return_value=catalog),patch.object(history,"public_source",side_effect=lambda _,path,sha:data[path]),redirect_stdout(io.StringIO()):
                self.assertEqual(eq.main(["--source-root","/synthetic/fixed","--out",str(output)]),2)
    def test_cli_failed_proof_never_writes_partial(self):
        catalog,data=catalog_data()
        v=catalog["cross_family_version_overlap"][7]
        hosted=next(x for x in catalog["histories"]["hosted_archive"] if x["version"]==v)
        data[hosted["path"]]=data[hosted["path"]]+b";"
        with tempfile.TemporaryDirectory() as d:
            output=pathlib.Path(d)/"candidate"
            with patch.object(history,"source_catalog",return_value=catalog),patch.object(history,"public_source",side_effect=lambda _,path,sha:data[path]),redirect_stdout(io.StringIO()):
                self.assertEqual(eq.main(["--source-root","/synthetic/fixed","--out",str(output)]),2)
            self.assertFalse(output.exists())

if __name__=="__main__":unittest.main()
