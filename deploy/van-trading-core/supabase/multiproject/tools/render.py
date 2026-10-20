#!/usr/bin/env python3
"""Offline candidate generator for one existing DIAL Supabase Compose installation.

No network, Docker, SQL, VM, credential, or service operations.
Generated project routes intentionally block Edge Functions and Realtime until qualified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
import uuid

ROOT = "/opt/van-trading/supabase"
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{2,30}$")
DB_RE = re.compile(r"^[a-z][a-z0-9_]{2,47}$")
HOST_RE = re.compile(r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])$")
BLOCKED_NAMES = {"van", "vati", "postgres", "supabase", "auth", "rest", "storage", "realtime", "pooler", "studio", "default", "template0", "template1"}
TOP_KEYS = {"schema_version", "target_installation", "allowed_postgres_service", "projects"}
PROJECT_KEYS = {"slug", "database", "project_uuid", "hostname", "loopback_port", "status"}

class CandidateError(ValueError):
    """Fail-closed manifest validation error."""

def validate(data: dict) -> list[dict]:
    if not isinstance(data, dict) or set(data) != TOP_KEYS:
        raise CandidateError("MANIFEST_FIELDS_MISMATCH")
    if data["schema_version"] != 1 or data["target_installation"] != ROOT:
        raise CandidateError("TARGET_INSTALLATION_MISMATCH")
    if data["allowed_postgres_service"] != "db":
        raise CandidateError("POSTGRES_SERVICE_NOT_EXISTING_DB")
    projects = data["projects"]
    if not isinstance(projects, list) or not projects or len(projects) > 32:
        raise CandidateError("INVALID_PROJECT_COUNT")
    used = {k:set() for k in ("slug","database","project_uuid","hostname","loopback_port")}
    for project in projects:
        if not isinstance(project, dict) or set(project) != PROJECT_KEYS:
            raise CandidateError("INVALID_PROJECT_FIELDS")
        slug, database = project["slug"], project["database"]
        if not isinstance(slug,str) or not SLUG_RE.fullmatch(slug) or slug in BLOCKED_NAMES:
            raise CandidateError("INVALID_OR_RESERVED_PROJECT_SLUG")
        if not isinstance(database,str) or not DB_RE.fullmatch(database) or database in BLOCKED_NAMES:
            raise CandidateError("INVALID_OR_RESERVED_DATABASE")
        if not isinstance(project["hostname"],str) or not HOST_RE.fullmatch(project["hostname"]) or "." not in project["hostname"]:
            raise CandidateError("INVALID_PROJECT_HOSTNAME")
        if not isinstance(project["loopback_port"],int) or isinstance(project["loopback_port"],bool) or not 18000 <= project["loopback_port"] <= 18999:
            raise CandidateError("LOOPBACK_PORT_OUT_OF_SAFE_RANGE")
        try:
            parsed_uuid = uuid.UUID(project["project_uuid"])
        except (TypeError, AttributeError, ValueError) as exc:
            raise CandidateError("INVALID_PROJECT_UUID") from exc
        if str(parsed_uuid) != project["project_uuid"] or parsed_uuid.int == 0:
            raise CandidateError("PROJECT_UUID_NON_CANONICAL")
        if project["status"] != "PLANNED":
            raise CandidateError("ONLY_UNDEPLOYED_PLANNED_PROJECTS_ACCEPTED")
        for key in used:
            if project[key] in used[key]:
                raise CandidateError("DUPLICATE_"+key.upper())
            used[key].add(project[key])
    return projects

def q(value: str) -> str:
    return json.dumps(value,ensure_ascii=True)

def emit_compose(projects: list[dict]) -> str:
    out = [
        "# GENERATED CANDIDATE — never deploy without independent qualification.",
        "# This is an overlay to the existing VAN Supabase Compose model, not a new stack.",
        "# Requires exact matching tenant database/schema/roles/key bootstrap first.",
        "# No project secret is included here. All tenant env files are external protected files.",
        "services:",
    ]
    for p in projects:
        slug = p["slug"]
        name = "tenant-"+slug
        base = "/etc/dial-supabase/projects/"+slug
        services = [
          (name+"-auth","supabase/gotrue:v2.196.0","auth.env"),
          (name+"-rest","postgrest/postgrest:v14.17","rest.env"),
          (name+"-storage","supabase/storage-api:v1.74.0","storage.env"),
        ]
        for s, image, env_filename in services:
            out.extend([
                "  "+s+":",
                "    image: "+q(image),
                "    restart: unless-stopped",
                "    depends_on:",
                "      db:",
                "        condition: service_healthy",
                "    env_file:",
                "      - "+q(base+"/"+env_filename),
            ])
            if env_filename == "storage.env":
                out.extend([
                    "    volumes:",
                    "      - "+q("/srv/dial-supabase/projects/"+slug+"/objects:/var/lib/storage"),
                ])
        out.extend([
            "  "+name+"-api:",
            "    image: "+q("nginx:1.27.5-alpine"),
            "    restart: unless-stopped",
            "    depends_on:",
            "      - "+name+"-auth",
            "      - "+name+"-rest",
            "      - "+name+"-storage",
            "    ports:",
            "      - "+q("127.0.0.1:"+str(p["loopback_port"])+":8080"),
            "    volumes:",
            "      - "+q(base+"/nginx.conf:/etc/nginx/conf.d/default.conf:ro"),
        ])
    return "\n".join(out)+"\n"

def emit_nginx(project: dict) -> str:
    name = "tenant-"+project["slug"]
    # Deliberately no public direct ports, functions, realtime, internal Postgres or Studio.
    return "\n".join([
      "# GENERATED PRE-PRODUCTION PROJECT ROUTER. Not a TLS or public gateway.",
      "server {",
      "    listen 8080;",
      "    server_name "+project["hostname"]+";",
      "    server_tokens off;",
      "    client_max_body_size 25m;",
      "    add_header X-Content-Type-Options nosniff always;",
      "    location = /_health { return 200 'candidate-router'; }",
      "    location ^~ /auth/v1/ {",
      "        proxy_set_header Host $host;",
      "        proxy_set_header X-Forwarded-Proto https;",
      "        proxy_pass http://"+name+"-auth:9999/;",
      "    }",
      "    location ^~ /rest/v1/ {",
      "        proxy_set_header Host $host;",
      "        proxy_set_header X-Forwarded-Proto https;",
      "        proxy_pass http://"+name+"-rest:3000/;",
      "    }",
      "    location ^~ /storage/v1/ {",
      "        proxy_set_header Host $host;",
      "        proxy_set_header X-Forwarded-Proto https;",
      "        proxy_pass http://"+name+"-storage:5000/;",
      "    }",
      "    location ^~ /functions/v1/ { return 503; }",
      "    location ^~ /realtime/v1/ { return 503; }",
      "    location / { return 404; }",
      "}",
      "",
    ])

def secret_contract(slug: str, database: str, hostname: str) -> str:
    return "\n".join([
      "# NO CREDENTIALS ARE CREATED HERE. Source real secrets from an approved vault.",
      "# The following separate files MUST be owner-controlled root-readable only (0600).",
      "/etc/dial-supabase/projects/"+slug+"/auth.env",
      "  GOTRUE_DB_DATABASE_URL -> restricted project auth DB login targeting ONLY "+database,
      "  GOTRUE_JWT_SECRET -> project-unique >=32-byte signing secret; never share VAN",
      "  GOTRUE_JWT_ISSUER -> https://"+hostname,
      "  GOTRUE_API_EXTERNAL_URL / GOTRUE_SITE_URL / GOTRUE_URI_ALLOW_LIST",
      "  GOTRUE_SMTP_* / GOTRUE_EXTERNAL_* / signup and hook configuration as applicable",
      "/etc/dial-supabase/projects/"+slug+"/rest.env",
      "  PGRST_DB_URI -> restricted project authenticator login targeting ONLY "+database,
      "  PGRST_DB_SCHEMAS=public,graphql_public (after schema qualification)",
      "  PGRST_DB_ANON_ROLE=anon",
      "  PGRST_JWT_SECRET -> project-unique JWKS/secret that verifies ONLY this project's JWT",
      "/etc/dial-supabase/projects/"+slug+"/storage.env",
      "  DATABASE_URL -> restricted project storage login targeting ONLY "+database,
      "  SERVICE_KEY / ANON_KEY -> project-unique keys, never VAN's",
      "  PGRST_JWT_SECRET -> matching tenant signing secret",
      "  STORAGE_BACKEND=file; FILE_STORAGE_BACKEND_PATH=/var/lib/storage",
      "  IMGPROXY_URL and relevant Supabase storage settings from pinned donor",
      "Mount /srv/dial-supabase/projects/"+slug+"/objects as private project-only storage path.",
      "PG roles, database privileges, Auth/Storage schemas and migrations MUST be provisioned and qualified separately.",
      "GTR cloud data, Auth identities, storage objects and RLS policies are NOT populated by rendering configs.",
      "",
    ])

def load_manifest(path: pathlib.Path) -> tuple[list[dict],bytes]:
    raw = path.read_bytes()
    return validate(json.loads(raw)), raw

def output_manifest(p: list[dict], digest: str) -> str:
    return json.dumps({
       "schema_version":1,"artifact_type":"COMPOSE_CANDIDATE_ONLY",
       "source_manifest_sha256":digest,
       "target_installation":ROOT,
       "projects":[{"slug":v["slug"],"database":v["database"],"loopback_port":v["loopback_port"],"qualified":False} for v in p],
       "functions_enabled":False,"realtime_enabled":False,"production_deploy_authorized":False,
    },sort_keys=True,indent=2)+"\n"

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("validate","render"))
    parser.add_argument("--manifest",type=pathlib.Path,required=True)
    parser.add_argument("--out",type=pathlib.Path)
    args=parser.parse_args(argv)
    try:
        projects,raw=load_manifest(args.manifest)
        digest=hashlib.sha256(raw).hexdigest()
        if args.action=="validate":
            print(json.dumps({"state":"VALIDATED_CANDIDATE_NOT_DEPLOYABLE","manifest_sha256":digest,"projects":[p["slug"] for p in projects]}))
            return 0
        if args.out is None:
            raise CandidateError("OUTPUT_PATH_REQUIRED_FOR_RENDER")
        args.out.mkdir(mode=0o700,parents=True,exist_ok=True)
        (args.out/"projects.overlay.yml").write_text(emit_compose(projects),encoding="utf-8")
        for p in projects:
            (args.out/(p["slug"]+".nginx.conf")).write_text(emit_nginx(p),encoding="utf-8")
            (args.out/(p["slug"]+".required-secrets.txt")).write_text(secret_contract(p["slug"],p["database"],p["hostname"]),encoding="utf-8")
        (args.out/"candidate-receipt.json").write_text(output_manifest(projects,digest),encoding="utf-8")
        print("GENERATED_CANDIDATE_ONLY "+str(args.out))
        return 0
    except (CandidateError,ValueError,KeyError,OSError) as exc:
        print("REFUSED: "+str(exc),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
