#!/usr/bin/env python3
"""Source-only, fail-closed trace of GTR client write reachability for ACL review.

This is a STATIC survey: not a deployment authorization, not a proof of runtime
non-reachability, and not an instruction to add or revoke any permission.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import pathlib
import re
import subprocess
import render as artifact_render

PINNED_SOURCE="8131858c7c7479d178cbe9e246f83cb49ed80f5e"
PINNED_PROJECT="bicyjghgdnzlnjqxzoud"
SAFE_NAME=re.compile(r"^[a-z][a-z0-9_]*$")
FROM_CALL=re.compile(r"\.\s*from\s*\(\s*(['\"])([a-z][a-z0-9_]*)\1\s*\)",re.M)
NEXT_METHOD=re.compile(r"\.\s*(select|insert|update|upsert|delete)\s*\(",re.I)
SUFFIXES={".ts",".tsx",".js",".jsx",".mjs",".kt",".kts",".java",".swift",".py",".sql"}
SOURCE_PREFIXES=(
    "apps/web/","apps/android-management/","apps/android-customer/","apps/android-delivery/",
    "apps/catalog-apk/","apps/ios/","supabase/functions/","packages/","bridges/",
    "powersync/","scripts/","services/","catalog/","data-pipeline/"
)
DML={"INSERT","UPDATE","DELETE"}
DML_METHODS={"insert":"INSERT","upsert":"INSERT_OR_UPDATE","update":"UPDATE","delete":"DELETE"}
MAX_SOURCE_BYTES=2*1024*1024
MAX_ITEMS=90
KIND="GTR_SOURCE_LOCKED_CLIENT_DML_STATIC_REVIEW_NOT_ADMISSION_V1"

class SourceTraceError(ValueError):
    pass

def _sha(value:bytes)->str:
    return hashlib.sha256(value).hexdigest()

def _git(root:pathlib.Path,*args:str)->str:
    cmd=["git","-C",str(root),*args]
    proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        timeout=12,check=False)
    if proc.returncode:
        raise SourceTraceError("SOURCE_TREE_GIT_READ_FAILED")
    return proc.stdout.decode("utf-8","strict").strip()

def validate_policy(data:dict)->list[dict]:
    if not isinstance(data,dict) or data.get("project_ref")!=PINNED_PROJECT:
        raise SourceTraceError("EXACT_ACTIVE_PROJECT_BINDING_REQUIRED")
    if data.get("source_commit")!=PINNED_SOURCE:
        raise SourceTraceError("PINNED_SOURCE_BINDING_REQUIRED")
    if (data.get("kind")!="GTR_READ_ONLY_POLICY_APPLICABLE_MISSING_GRANTS_NOT_RELEASE"
        or data.get("schema_version")!=1
        or data.get("hosted_transaction")!="REPEATABLE READ READ ONLY"
        or data.get("production_change_performed") is not False
        or data.get("apply_grants_authorized") is not False
        or data.get("canary_activation_authorized") is not False
        or data.get("policy_applicable_missing_grants")!=78
        or data.get("grouped")!={"authenticated_INSERT":27,"authenticated_UPDATE":27,
                                 "authenticated_DELETE":23,"anon_SELECT":1}):
        raise SourceTraceError("PINNED_READ_ONLY_POLICY_OBSERVATION_REQUIRED")
    entries=data.get("entries")
    if not isinstance(entries,list) or len(entries)!=78 or len(entries)>MAX_ITEMS:
        raise SourceTraceError("EXACT_POLICY_ENTRY_COUNT_REQUIRED")
    seen=set()
    for entry in entries:
        if not isinstance(entry,dict) or set(entry)!={"table","role","privilege","applicable_policy_names"}:
            raise SourceTraceError("EXACT_POLICY_ENTRY_FIELDS_REQUIRED")
        table=entry["table"]
        role=entry["role"]
        op=entry["privilege"]
        policies=entry["applicable_policy_names"]
        if not isinstance(table,str) or not SAFE_NAME.fullmatch(table):
            raise SourceTraceError("POLICY_TABLE_INVALID")
        if role not in ("anon","authenticated") or op not in (*DML,"SELECT"):
            raise SourceTraceError("POLICY_ROLE_OR_OPERATION_INVALID")
        if not isinstance(policies,list) or not policies or not all(isinstance(s,str) and SAFE_NAME.fullmatch(s) for s in policies):
            raise SourceTraceError("EXACT_POLICY_IDENTITY_REQUIRED")
        marker=(table,role,op)
        if marker in seen:raise SourceTraceError("DUPLICATE_POLICY_ENTRY")
        seen.add(marker)
    if sum(x["role"]=="anon" for x in entries)!=1:
        raise SourceTraceError("EXACT_SINGLE_ANON_CASE_REQUIRED")
    if sum(x["role"]=="authenticated" for x in entries)!=77:
        raise SourceTraceError("EXACT_77_AUTHENTICATED_CASES_REQUIRED")
    if next(x for x in entries if x["role"]=="anon")["table"]!="stock_item_images":
        raise SourceTraceError("ANON_STOCK_IMAGE_SOURCE_CASE_REQUIRED")
    if any(x["role"]=="anon" and x["privilege"]!="SELECT" for x in entries):
        raise SourceTraceError("ANON_ONLY_PUBLIC_READ_EXPECTED")
    if any(x["role"]=="authenticated" and x["privilege"] not in DML for x in entries):
        raise SourceTraceError("AUTHENTICATED_WRITE_CASES_ONLY_REQUIRED")
    if len(set(x["table"] for x in entries if x["role"]=="authenticated"))!=30:
        raise SourceTraceError("EXACT_30_AUTHENTICATED_TABLES_REQUIRED")
    return entries

def chain_method(source:str,start:int)->str|None:
    """Deliberately bounded local same-expression search; fail open to UNKNOWN."""
    tail=source[start:start+1800]
    stop=tail.find(";")
    if stop>=0:tail=tail[:stop]
    # A bare blank line is a practical boundary in Kotlin/TS chained calls.
    stop=re.search(r"\n\s*\n",tail)
    if stop:tail=tail[:stop.start()]
    call=NEXT_METHOD.search(tail)
    return None if call is None else call.group(1).lower()

def trace_one(text:str,path:str, tables:set[str])->dict:
    result={name:{"literal_occurrences":0,"direct_calls":[]} for name in tables}
    for name in tables:
        result[name]["literal_occurrences"]=len(re.findall(re.escape(name),text))
    for match in FROM_CALL.finditer(text):
        table=match.group(2)
        if table not in result:continue
        line=text.count("\n",0,match.start())+1
        method=chain_method(text,match.end())
        # A comment-start line is not a direct client call.
        left=text.rfind("\n",0,match.start())+1
        if text[left:match.start()].lstrip().startswith(("//","*","--")):continue
        result[table]["direct_calls"].append({"path":path,"line":line,
            "method":method or "UNKNOWN","operation":DML_METHODS.get(method,"READ" if method=="select" else "UNKNOWN")})
    return result

def scan(root:pathlib.Path,policy:dict)->dict:
    entries=validate_policy(policy)
    root=pathlib.Path(root).absolute()
    if root.is_symlink() or not root.is_dir() or not (root/".git").exists():
        raise SourceTraceError("GIT_WORKTREE_REQUIRED")
    if _git(root,"rev-parse","HEAD")!=PINNED_SOURCE:
        raise SourceTraceError("PINNED_GTR_COMMIT_REQUIRED")
    if _git(root,"status","--porcelain","--untracked-files=no"):
        raise SourceTraceError("DIRTY_SOURCE_REFUSED")
    raw=_git(root,"ls-files","--cached")
    paths=sorted(set(raw.splitlines()))
    wanted=[s for s in paths if s.startswith(SOURCE_PREFIXES) and pathlib.PurePosixPath(s).suffix.lower() in SUFFIXES]
    absent=[s for s in wanted if not (root/s).is_file()]
    if absent:
        # Sparse checkouts must be complete for all claimed scopes.
        raise SourceTraceError("INCOMPLETE_SPARSE_SOURCE_SCOPE")
    by_table={name:{"mentions":0,"literal_source_files":set(),"direct_calls":[]} for name in set(x["table"] for x in entries)}
    digest=hashlib.sha256()
    scanned=0
    for rel in wanted:
        p=root/rel
        if p.is_symlink() or not p.is_file() or p.stat().st_size>MAX_SOURCE_BYTES:
            raise SourceTraceError("UNSAFE_SOURCE_FILE_REFUSED")
        rawdata=p.read_bytes()
        content=rawdata.decode("utf-8","replace")
        digest.update((rel+"\n"+_sha(rawdata)+"\n").encode())
        t=trace_one(content,rel,set(by_table))
        scanned+=1
        for table,r in t.items():
            if r["literal_occurrences"]:
                by_table[table]["mentions"]+=r["literal_occurrences"]
                by_table[table]["literal_source_files"].add(rel)
            by_table[table]["direct_calls"].extend(r["direct_calls"])
    result_rows=[]
    total_server_admin_write=0
    total_other_write=0
    globally_counted_calls=set()
    for e in entries:
        t=by_table[e["table"]]
        direct=[]
        for call in t["direct_calls"]:
            if call["operation"] not in (*DML,"INSERT_OR_UPDATE"):continue
            is_admin=(call["path"]=="scripts/provision-canonical-staff.mjs"
                      and e["table"]=="staff_roles")
            # This exception is validated separately by exact source predicates.
            direct.append({**call,"confirmed_server_admin_provisioner":is_admin})
            call_key=(e["table"],call["path"],call["line"],call["method"])
            if call_key not in globally_counted_calls:
                globally_counted_calls.add(call_key)
                if is_admin:total_server_admin_write+=1
                else:total_other_write+=1
        result_rows.append({
          "table":e["table"],"role":e["role"],"privilege":e["privilege"],
          "policy_names":list(e["applicable_policy_names"]),
          "literal_source_files":len(t["literal_source_files"]),
          "direct_table_call_methods":sorted({c["method"] for c in t["direct_calls"]}),
          "direct_write_calls":direct,
          "classification":"EXPLICIT_WRITE_REQUIRES_MANUAL_ROLE_CHECK" if any(not c["confirmed_server_admin_provisioner"] for c in direct)
             else "ADMIN_SERVER_PROVISIONER_ONLY_WRITE_OBSERVED" if direct
             else "NO_STATIC_DIRECT_WRITE_OBSERVED_NOT_RUNTIME_PROOF",
          "automatic_grant_allowed":False
        })
    # Source provenance of the only observed admin writes: do not equate
    # arbitrary server paths or non-privileged clients with this exact script.
    staff_script=(root/"scripts/provision-canonical-staff.mjs").read_text()
    if total_server_admin_write:
        if not all(s in staff_script for s in (
           "SUPABASE_SECRET_KEY","SUPABASE_SERVICE_ROLE_KEY","createClient(url, secretKey",
           'admin.from("staff_roles")')):
            raise SourceTraceError("PROVISIONER_ADMIN_SOURCE_NOT_PROVED")
    return {
       "schema_version":1,"kind":KIND,
       "source_repository":"Vanguduza/Nissan-Gtr-Auto",
       "source_commit":PINNED_SOURCE,
       "hosted_project_ref":PINNED_PROJECT,
       "source_files_scanned":scanned,
       "source_file_inventory_sha256":digest.hexdigest(),
       "source_scopes":list(SOURCE_PREFIXES),
       "policy_rows_reviewed":len(entries),
       "authenticated_dml_grant_cases":77,
       "authenticated_distinct_tables":len(set(x["table"] for x in entries if x["role"]=="authenticated")),
       "observed_server_admin_direct_write_calls":total_server_admin_write,
       "other_direct_write_calls_observed":total_other_write,
       "grant_cases":result_rows,
       "static_audit_complete_for_tracked_scopes":True,
       "deployed_app_versions_verified":False,
       "dynamic_table_references_resolved":False,
       "external_clients_verified":False,
       "postgrest_routing_verified":False,
       "authorization_to_apply_any_grant":False,
       "live_canary_authorized":False,
       "production_data_or_credential_accessed":False,
       "limitations":[
          "Literal static source inspection cannot prove absence of dynamic SQL, runtime/generated table names or external consumers.",
          "The two identified staff_roles writes use an explicitly authenticated admin-key provisioning script, not an authenticated client grant.",
          "Grant review must consider database RLS predicates, service grants, actual deployed client/API, RPC and backend owner execution.",
          "This report is not approval to copy 77, 78 or 1,735 hosted privileges to the final candidate.",
          "Original refusal of the live canary remains binding."
       ]
    }

def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",required=True,type=pathlib.Path)
    parser.add_argument("--policy-json",required=True,type=pathlib.Path)
    parser.add_argument("--out",required=True,type=pathlib.Path)
    a=parser.parse_args(argv)
    try:
        report=scan(a.source_root,json.loads(a.policy_json.read_text()))
        artifact_render.write_bundle(a.out,{
            "client-write-source-review.json":json.dumps(report,indent=2,sort_keys=True)+"\n"
        })
        print("GTR_CLIENT_DML_STATIC_REVIEW_ONLY",report["source_files_scanned"],
              report["other_direct_write_calls_observed"])
        return 0
    except (OSError,ValueError,subprocess.SubprocessError,artifact_render.CandidateError):
        print("GTR_CLIENT_DML_TRACE_REFUSED")
        return 2

if __name__=="__main__":raise SystemExit(main())
