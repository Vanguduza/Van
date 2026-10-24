#!/usr/bin/env python3
import copy
import importlib.util
import pathlib
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("render", ROOT / "tools" / "render.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
DEFAULT = {
  "schema_version":1,
  "target_installation":"/opt/van-trading/supabase",
  "allowed_postgres_service":"db",
  "projects":[{
    "slug":"nissan-gtr",
    "database":"gtr_prod",
    "project_uuid":"53d39b5d-bf19-4cf1-9a5b-0904192d90d1",
    "hostname":"nissan-gtr-api.example.invalid",
    "loopback_port":18081,
    "status":"PLANNED"
  }]
}

class ProjectTests(unittest.TestCase):
    def test_valid(self):
        p=mod.validate(copy.deepcopy(DEFAULT))
        self.assertEqual(p[0]["database"],"gtr_prod")
    def test_vati_cannot_be_admitted(self):
        for field,value in [("slug","vati"),("database","postgres"),("slug","van")]:
            data=copy.deepcopy(DEFAULT)
            data["projects"][0][field]=value
            with self.assertRaises(mod.CandidateError):
                mod.validate(data)
    def test_duplicate_project_identity_refused(self):
        data=copy.deepcopy(DEFAULT)
        extra=copy.deepcopy(data["projects"][0])
        extra["slug"]="goat-prod"
        extra["database"]="goat_prod"
        extra["hostname"]="goat-api.example.invalid"
        extra["loopback_port"]=18082
        data["projects"].append(extra)
        with self.assertRaisesRegex(mod.CandidateError,"DUPLICATE_PROJECT_UUID"):
            mod.validate(data)
    def test_unsafe_hostnames_and_forged_status(self):
        for change in [{"hostname":"x; return 200;"},{"status":"LIVE"},{"hostname":"localhost"},{"loopback_port":5432}]:
            data=copy.deepcopy(DEFAULT)
            data["projects"][0].update(change)
            with self.assertRaises(mod.CandidateError):
                mod.validate(data)
    def test_secret_material_cannot_be_in_manifest(self):
        data=copy.deepcopy(DEFAULT)
        data["projects"][0]["password"]="oops"
        with self.assertRaises(mod.CandidateError):
            mod.validate(data)
    def test_render_additive_only(self):
        p=mod.validate(copy.deepcopy(DEFAULT))
        out=mod.emit_compose(p)
        ng=mod.emit_nginx(p[0])
        self.assertNotIn("db", re.findall(r"^  ([a-z0-9-]+):$", out, flags=re.MULTILINE))
        self.assertNotIn("    container_name:",out)
        self.assertIn("supabase/gotrue:v2.196.0",out)
        self.assertIn("postgrest/postgrest:v14.17",out)
        self.assertIn("supabase/storage-api:v1.74.0",out)
        self.assertIn("127.0.0.1:18081:8080",out)
        self.assertNotIn("0.0.0.0:18081",out)
        self.assertIn("return 503;",ng)
        self.assertIn("tenant-nissan-gtr-auth",ng)
        self.assertIn("tenant-nissan-gtr-rest",ng)
        self.assertIn("tenant-nissan-gtr-storage",ng)
    def test_unknown_root_target_refused(self):
        data=copy.deepcopy(DEFAULT)
        data["target_installation"]="/tmp/supabase"
        with self.assertRaises(mod.CandidateError):
            mod.validate(data)

if __name__=="__main__":
    unittest.main()
