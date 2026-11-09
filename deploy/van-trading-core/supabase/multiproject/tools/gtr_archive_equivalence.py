#!/usr/bin/env python3
"""Read-only, exact-byte adjudication of GTR archived migration export wrappers.

Never executes archived SQL or connects to any PostgreSQL/hosted database.
Only the ten pinned legacy/hosted overlaps are admissible. Do not treat
archive equality as current hosted schema, ledger, or data equivalence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import re
import gtr_history_reconcile as history
import render

OVERLAP_COUNT = 10
VERSION = re.compile(r"^[0-9]{14}$")
NAME = re.compile(r"^[a-z0-9_]+$")
WRAPPER_LABEL = "supabase/live-history/README.md"
KIND = "GTR_ARCHIVE_WRAPPER_BODY_EQUALITY_V1"

class ArchivedBodyError(ValueError):
    pass

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def hosted_export_wrapper(version: str, name: str) -> bytes:
    if not isinstance(version,str) or not VERSION.fullmatch(version):
        raise ArchivedBodyError("ARCHIVE_VERSION_INVALID")
    if not isinstance(name,str) or not NAME.fullmatch(name):
        raise ArchivedBodyError("ARCHIVE_NAME_INVALID")
    return (
        "-- Exported from the hosted project's supabase_migrations.schema_migrations "
        f"({version} {name}).\n"
        f"-- Source of record for what production ran; see {WRAPPER_LABEL}.\n\n"
    ).encode("utf-8")

def compare_pair(version: str, name: str, hosted: bytes, legacy: bytes, hosted_sha: str, legacy_sha: str) -> dict:
    """Strictly remove one known export header and, if present, one final LF."""
    if not all(isinstance(x,bytes) for x in (hosted,legacy)):
        raise ArchivedBodyError("ARCHIVED_SQL_BYTES_REQUIRED")
    if not all(isinstance(x,str) and re.fullmatch(r"[a-f0-9]{64}",x) for x in (hosted_sha,legacy_sha)):
        raise ArchivedBodyError("EXACT_SOURCE_SHA256_REQUIRED")
    if sha(hosted) != hosted_sha or sha(legacy) != legacy_sha:
        raise ArchivedBodyError("ARCHIVED_SQL_DIGEST_CHANGED")
    wrapper = hosted_export_wrapper(version,name)
    if not hosted.startswith(wrapper):
        raise ArchivedBodyError("EXACT_HOSTED_EXPORT_WRAPPER_REQUIRED")
    body = hosted[len(wrapper):]
    if body == legacy:
        classification = "EXACT_BODY_AFTER_KNOWN_EXPORT_WRAPPER"
        extra_final_lf = False
    elif body == legacy + b"\n":
        classification = "EXACT_BODY_AFTER_KNOWN_WRAPPER_AND_ONE_FINAL_LF"
        extra_final_lf = True
    else:
        raise ArchivedBodyError("ARCHIVED_SQL_BODY_DIVERGED")
    if not body or not legacy:
        raise ArchivedBodyError("ARCHIVED_SQL_EMPTY_REFUSED")
    return {
        "version":version,
        "name":name,
        "classification":classification,
        "known_header_sha256":sha(wrapper),
        "hosted_source_sha256":hosted_sha,
        "legacy_source_sha256":legacy_sha,
        "normalized_body_sha256":sha(legacy),
        "hosted_bytes":len(hosted),
        "legacy_bytes":len(legacy),
        "wrapper_bytes":len(wrapper),
        "extra_final_lf":extra_final_lf,
        "original_source_files_preserved":True
    }

def resolve(root: pathlib.Path) -> dict:
    catalog = history.source_catalog(root)
    if catalog.get("commit") != history.GTR_COMMIT:
        raise ArchivedBodyError("PINNED_SOURCE_COMMIT_REQUIRED")
    overlaps=catalog.get("cross_family_version_overlap")
    if not isinstance(overlaps,list) or len(overlaps)!=OVERLAP_COUNT or len(set(overlaps))!=OVERLAP_COUNT:
        raise ArchivedBodyError("EXACT_TEN_OVERLAPS_REQUIRED")
    variants=catalog.get("cross_family_content_variants")
    if not isinstance(variants,dict) or set(variants)!=set(overlaps):
        raise ArchivedBodyError("EXACT_VARIANT_SET_REQUIRED")
    groups=catalog.get("histories")
    if not isinstance(groups,dict):raise ArchivedBodyError("PINNED_HISTORY_GROUPS_REQUIRED")
    indexed={}
    for family in ("hosted_archive","legacy"):
        indexed[family]={row["version"]:row for row in groups[family]}
    records=[]
    for version in sorted(overlaps):
        hosted=indexed["hosted_archive"].get(version)
        legacy=indexed["legacy"].get(version)
        if not hosted or not legacy or hosted["name"]!=legacy["name"]:
            raise ArchivedBodyError("OVERLAP_NAME_OR_FAMILY_DRIFT")
        if sorted((hosted["source_file_sha256"],legacy["source_file_sha256"])) != variants[version]:
            raise ArchivedBodyError("PINNED_VARIANT_DIGEST_SET_CHANGED")
        hosted_bytes=history.public_source(root,hosted["path"],hosted["source_file_sha256"])
        legacy_bytes=history.public_source(root,legacy["path"],legacy["source_file_sha256"])
        record=compare_pair(version,hosted["name"],hosted_bytes,legacy_bytes,
                            hosted["source_file_sha256"],legacy["source_file_sha256"])
        records.append(record)
    exact=sum(x["classification"]=="EXACT_BODY_AFTER_KNOWN_EXPORT_WRAPPER" for x in records)
    normalized=sum(x["extra_final_lf"] for x in records)
    if exact!=4 or normalized!=6:
        raise ArchivedBodyError("PINNED_ARCHIVE_WRAPPER_CLASSIFICATION_CHANGED")
    return {
        "schema_version":1,"kind":KIND,
        "source_repository":"Vanguduza/Nissan-Gtr-Auto",
        "source_commit":history.GTR_COMMIT,
        "source_manifest_sha256":catalog["manifest_sha256"],
        "overlap_count":OVERLAP_COUNT,
        "exact_wrapper_only":exact,
        "wrapper_plus_one_final_lf":normalized,
        "remaining_archived_body_differences":0,
        "records":records,
        "independent_current_hosted_ledger_observed":False,
        "sql_executed":False,
        "may_repair_hosted_history":False,
        "may_apply_migrations":False,
        "may_activate_canary":False,
        "may_cutover":False,
        "production_deploy_authorized":False,
        "limits":[
            "One exact known provenance wrapper, not arbitrary SQL comments, is removed.",
            "At most one terminal LF is tolerated, never internal whitespace or SQL changes.",
            "Archive source equivalence does not prove the current hosted migration ledger, schema, customers, functions, or business behavior.",
            "The original archived files, source digests and both families remain retained.",
            "The prior live-canary safety refusal is unchanged. This code cannot execute SQL, route around that refusal, or authorize a release."
        ]
    }

def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",type=pathlib.Path,required=True)
    parser.add_argument("--out",type=pathlib.Path,required=True)
    args=parser.parse_args(argv)
    try:
        report=resolve(args.source_root)
        render.write_bundle(args.out,{"archived-body-equality.json":json.dumps(report,sort_keys=True,indent=2)+"\n"})
        print("ARCHIVED_SQL_BODY_EQUIVALENCE_VERIFIED_NOT_HOSTED_CAPTURE")
        return 0
    except (ValueError,TypeError,KeyError,OSError,render.CandidateError):
        print("REFUSED_ARCHIVED_SQL_EQUIVALENCE")
        return 2

if __name__=="__main__":raise SystemExit(main())
