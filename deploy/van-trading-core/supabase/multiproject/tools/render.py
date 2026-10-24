#!/usr/bin/env python3
"""Offline candidate generator for one existing DIAL Supabase Compose installation.

No network, Docker, SQL, VM, credential, or service operations.
Generated project routes intentionally block Edge Functions and Realtime until qualified.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import pathlib
import re
import sys
import uuid
import stat

ROOT = "/opt/van-trading/supabase"
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{2,30}$")
DB_RE = re.compile(r"^[a-z][a-z0-9_]{2,47}$")
HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
BLOCKED_NAMES = {"van", "vati", "postgres", "supabase", "auth", "rest", "storage", "realtime", "pooler", "studio", "default", "template0", "template1"}
TOP_KEYS = {"schema_version", "target_installation", "allowed_postgres_service", "projects"}
PROJECT_KEYS = {"slug", "database", "project_uuid", "hostname", "loopback_port", "status"}

class CandidateError(ValueError):
    """Fail-closed manifest validation error."""

def check_hostname(hostname: str) -> None:
    if not isinstance(hostname, str) or not 3 <= len(hostname) <= 253:
        raise CandidateError("INVALID_PROJECT_HOSTNAME")
    labels = hostname.split(".")
    if len(labels) < 2 or any(not HOST_LABEL_RE.fullmatch(label) for label in labels):
        raise CandidateError("INVALID_PROJECT_HOSTNAME")
    if labels[-1].isdigit() or labels[-1] == "localhost":
        raise CandidateError("INVALID_PROJECT_HOSTNAME")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return
    raise CandidateError("PROJECT_HOSTNAME_MUST_NOT_BE_IP")

def validate(data: dict) -> list[dict]:
    if not isinstance(data, dict) or set(data) != TOP_KEYS:
        raise CandidateError("MANIFEST_FIELDS_MISMATCH")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["target_installation"] != ROOT:
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
        check_hostname(project["hostname"])
        if not isinstance(project["loopback_port"],int) or isinstance(project["loopback_port"],bool) or not 18000 <= project["loopback_port"] <= 18999:
            raise CandidateError("LOOPBACK_PORT_OUT_OF_SAFE_RANGE")
        if not isinstance(project["project_uuid"], str):
            raise CandidateError("INVALID_PROJECT_UUID")
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
    return sorted((dict(p) for p in projects), key=lambda p: p["slug"])

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
                "    security_opt: [\"no-new-privileges:true\"]",
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
            "    security_opt: [\"no-new-privileges:true\"]",
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
    """Candidate routing only; NOT API-key/JWT authorization or TLS termination."""
    name = "tenant-" + project["slug"]
    host = project["hostname"]
    check_hostname(host)
    host_pattern = "^" + re.escape(host) + "(?::[0-9]{1,5})?$"
    lines = [
        "# CANDIDATE ONLY: upstream stubs/credentials have not qualified Supabase.",
        "# The upstream TLS/Envoy admission owner must validate API keys and quotas.",
        "server { listen 8080 default_server; server_name _; return 421; }",
        "server {",
        "    listen 8080;",
        "    server_name " + host + ";",
        "    if ($http_host !~* \"" + host_pattern + "\") { return 421; }",
        "    server_tokens off;",
        "    client_max_body_size 25m;",
        "    add_header X-Content-Type-Options nosniff always;",
        "    location = /_health { return 503 'UNQUALIFIED_CANDIDATE'; }",
    ]
    for prefix, suffix, port in (("auth", "auth", 9999), ("rest", "rest", 3000), ("storage", "storage", 5000)):
        lines.extend([
            "    location ^~ /" + prefix + "/v1/ {",
            "        proxy_set_header Host " + host + ";",
            "        proxy_set_header X-Forwarded-Host " + host + ";",
            "        proxy_set_header X-Forwarded-Proto https;",
            "        proxy_set_header X-Forwarded-Port 443;",
            "        proxy_set_header X-Forwarded-For $remote_addr;",
            "        proxy_set_header X-Real-IP $remote_addr;",
            "        proxy_set_header Forwarded \"\";",
            "        proxy_set_header X-Tenant-ID \"\";",
            "        proxy_set_header X-Project-ID \"\";",
            "        proxy_set_header X-Forwarded-Prefix /" + prefix + "/v1;",
            "        proxy_set_header X-Forwarded-Path \"\";",
            "        proxy_set_header X-Dial-Project-ID " + project["project_uuid"] + ";",
            "        proxy_connect_timeout 5s;",
            "        proxy_read_timeout 30s;",
            "        proxy_pass http://" + name + "-" + suffix + ":" + str(port) + "/;",
            "    }",
        ])
    lines.extend([
        "    location ^~ /functions/v1/ { return 503; }",
        "    location ^~ /realtime/v1/ { return 503; }",
        "    location / { return 404; }",
        "}", "",
    ])
    return "\n".join(lines)

def secret_contract(slug: str, database: str, hostname: str) -> str:
    return "\n".join([
      "# NO CREDENTIALS ARE CREATED HERE. Source real secrets from an approved vault.",
      "# The following separate files MUST be owner-controlled root-readable only (0600).",
      "/etc/dial-supabase/projects/"+slug+"/auth.env",
      "  GOTRUE_DB_DATABASE_URL -> restricted project auth DB login targeting ONLY "+database,
      "  GOTRUE_JWT_SECRET -> project-unique >=32-byte signing secret; never share VAN",
      "  GOTRUE_JWT_ISSUER -> https://"+hostname+"/auth/v1",
      "  API_EXTERNAL_URL -> https://"+hostname+"/auth/v1",
      "  GOTRUE_API_HOST=0.0.0.0; GOTRUE_API_PORT=9999; GOTRUE_DB_DRIVER=postgres",
      "  GOTRUE_SITE_URL / GOTRUE_URI_ALLOW_LIST -> project-specific site/redirect allow-list",
      "  GOTRUE_SMTP_* / GOTRUE_EXTERNAL_* / signup and hook configuration as applicable",
      "/etc/dial-supabase/projects/"+slug+"/rest.env",
      "  PGRST_DB_URI -> restricted project authenticator login targeting ONLY "+database,
      "  PGRST_DB_SCHEMAS=public,graphql_public (after schema qualification)",
      "  PGRST_DB_ANON_ROLE=anon",
      "  PGRST_JWT_SECRET -> project-unique JWKS/secret that verifies ONLY this project's JWT",
      "/etc/dial-supabase/projects/"+slug+"/storage.env",
      "  DATABASE_URL -> restricted project storage login targeting ONLY "+database,
      "  SERVICE_KEY / ANON_KEY -> project-unique keys, never VAN's",
      "  AUTH_JWT_SECRET -> matching project signing secret (or qualified JWT_JWKS)",
      "  POSTGREST_URL=http://tenant-"+slug+"-rest:3000",
      "  STORAGE_PUBLIC_URL=https://"+hostname,
      "  TENANT_ID -> immutable project UUID; GLOBAL_S3_BUCKET -> project-only namespace",
      "  STORAGE_BACKEND=file; FILE_STORAGE_BACKEND_PATH=/var/lib/storage",
      "  ENABLE_IMAGE_TRANSFORMATION=false until shared imgproxy project access is qualified",
      "Mount /srv/dial-supabase/projects/"+slug+"/objects as private project-only storage path.",
      "PG roles, database privileges, Auth/Storage schemas and migrations MUST be provisioned and qualified separately.",
      "GTR cloud data, Auth identities, storage objects and RLS policies are NOT populated by rendering configs.",
      "",
    ])

def unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CandidateError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def load_manifest(path: pathlib.Path) -> tuple[list[dict], bytes]:
    with path.open("rb") as handle:
        raw = handle.read(1048577)
    if len(raw) > 1048576:
        raise CandidateError("MANIFEST_TOO_LARGE")
    try:
        data = json.loads(raw, object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateError("MANIFEST_INVALID_JSON") from exc
    return validate(data), raw


def write_bundle(out: pathlib.Path, artifacts: dict[str, str]) -> None:
    """Write a NEW private directory. Receipt is last; no overwriting or symlinks.

    Linux directory FDs pin every traversed parent. The operator must own the
    output parent; this is an offline artifact writer, never an installer.
    """
    if not out.is_absolute() or ".." in out.parts or out.name in ("", "."):
        raise CandidateError("OUTPUT_ABSOLUTE_NEW_PATH_REQUIRED")
    for protected in (ROOT, "/etc/dial-supabase", "/srv/dial-supabase"):
        if out == pathlib.Path(protected) or pathlib.Path(protected) in out.parents:
            raise CandidateError("OUTPUT_MUST_NOT_BE_ACTIVE_INSTALLATION")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent_fd = os.open("/", flags)
    output_fd = None
    written = []
    created = False
    try:
        for component in out.parts[1:-1]:
            next_fd = os.open(component, flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = next_fd
        parent_stat = os.fstat(parent_fd)
        if parent_stat.st_uid != os.geteuid():
            raise CandidateError("OUTPUT_PARENT_MUST_BE_OPERATOR_OWNED")
        if parent_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise CandidateError("OUTPUT_PARENT_MUST_BE_PRIVATE")
        try:
            os.mkdir(out.name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError as exc:
            raise CandidateError("OUTPUT_ALREADY_EXISTS") from exc
        created = True
        output_fd = os.open(out.name, flags, dir_fd=parent_fd)
        for name, text in artifacts.items():
            if pathlib.Path(name).name != name:
                raise CandidateError("ARTIFACT_FILENAME_INVALID")
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=output_fd)
            written.append(name)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
        os.fsync(output_fd)
        os.fsync(parent_fd)
    except BaseException:
        if output_fd is not None:
            for name in reversed(written):
                os.unlink(name, dir_fd=output_fd)
        if created:
            os.rmdir(out.name, dir_fd=parent_fd)
        raise
    finally:
        if output_fd is not None:
            os.close(output_fd)
        os.close(parent_fd)

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
        artifacts = {"projects.overlay.yml": emit_compose(projects)}
        for p in projects:
            artifacts[p["slug"]+".nginx.conf"] = emit_nginx(p)
            artifacts[p["slug"]+".required-secrets.txt"] = secret_contract(p["slug"],p["database"],p["hostname"])
        receipt = json.loads(output_manifest(projects,digest))
        receipt["artifact_sha256"] = {name: hashlib.sha256(text.encode()).hexdigest() for name,text in artifacts.items()}
        receipt["readiness"] = "UNQUALIFIED_CANDIDATE"
        artifacts["candidate-receipt.json"] = json.dumps(receipt,sort_keys=True,indent=2)+"\n"
        write_bundle(args.out, artifacts)
        print("GENERATED_CANDIDATE_ONLY "+str(args.out))
        return 0
    except (CandidateError,ValueError,KeyError,OSError,TypeError) as exc:
        print("REFUSED: " + (str(exc) if isinstance(exc, CandidateError) else type(exc).__name__), file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
