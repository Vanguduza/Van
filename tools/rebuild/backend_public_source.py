#!/usr/bin/env python3
"""Public source qualification; never a substitute for required private/native gates."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import uuid
import subprocess
import sys
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = {"tests/contracts/test_artemis_acceptance_plan.py", "tests/contracts/test_artemis_usb_acceptance.py"}
FIREWALL = "tests/contracts/test_van_browser_core_firewall.py"
ROOTS = ("backend/tests", "tests/contracts", "hermes/policy/tests", "tests/hermes", "services")
ALLOWED_SKIPS = {
    "member of the B1 closed set by definition": (("backend/tests/test_jev_no_generic_executor.py", "test_no_fabric_or_generic_operation_survives_the_b1_validator"),),
    "DDS checkout not present; blob hashes pinned above": (("backend/tests/test_jev_browser_eligibility.py", "test_vendored_dds_files_are_the_audited_blobs"),),
    "no DDS git clone beside this checkout; the CI step verifies the same table itself": (("tests/contracts/test_ci_dds_contract_pin.py", "test_recorded_blobs_are_the_pinned_dds_blobs_when_dds_is_present"),),
    "opt-in actual AGP release guard check": (("tests/contracts/test_android_instrumentation_abi.py", "test_actual_agp_direct_package_release_refuses_missing_core_deployment_profile"),),
    "opt-in actual AGP signing guard check": (("tests/contracts/test_android_production_target.py", "test_actual_agp_valid_target_still_refuses_missing_production_signing"),),
}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def plan(root=ROOT):
    files=sorted({p.relative_to(root).as_posix() for folder in ROOTS for p in (root/folder).rglob("test_*.py")})
    browser={p.relative_to(root).as_posix() for pattern in ("test_browser*.py", "test_harness*.py") for p in (root/"backend/tests").glob(pattern)}
    selected=[];separate=[]
    for path in files:
        reason=("PINNED_PRIVATE_DDS_SOURCE_REQUIRED" if path in PRIVATE else
                "SEPARATE_COMPLETE_BROWSER_SOURCE_JOB" if path in browser else
                "SEPARATE_PRIVILEGED_NAMESPACE_SOURCE_JOB" if path==FIREWALL else None)
        row={"path":path,"sha256":digest(root/path)}
        (separate if reason else selected).append(row|({"reason":reason} if reason else {}))
    if not PRIVATE.issubset(files) or FIREWALL not in files or not selected:
        raise ValueError("source qualification inventory is incomplete")
    return {"schema":"van.public-backend-source-selection/1","selected":selected,"separate":separate,
        "qualification":"SOURCE_SUBSET_ONLY; private DDS, deployed hosts/devices and original required backend gate remain separate"}

def modules(path, stems):
    full=path.removesuffix(".py").replace("/", ".")
    names={full,full.removeprefix("backend.")}
    stem=Path(path).stem
    if stems[stem]==1:names.add(stem)
    return names

def runtime(path):
    return "media" if path.startswith("services/") else "gateway"

def verify(manifest, report, audit, root=ROOT):
    expected=plan(root)
    if manifest!=expected:raise ValueError("selection or source bytes drifted")
    stems=Counter(Path(r["path"]).stem for r in expected["selected"])
    cases=[]
    audits={}
    for group in ("gateway", "media"):
        group_report=Path(report).with_name(group+"-report.xml")
        group_audit=Path(audit).with_name(group+"-storage-audit.json")
        group_cases=list(ET.parse(group_report).getroot().iter("testcase"))
        group_names=set().union(*(modules(r["path"], stems)
            for r in expected["selected"] if runtime(r["path"])==group))
        if not group_cases or any(not any(c.get("classname","")==n or c.get("classname","").startswith(n+".") for n in group_names) for c in group_cases):
            raise ValueError("missing or foreign cases in isolated runtime: "+group)
        if json.loads(group_audit.read_text())["forbidden_events"]:
            raise ValueError("source-storage audit rejected writes: "+group)
        audits[group]={"junit_sha256":digest(group_report),"storage_audit_sha256":digest(group_audit),"tests":len(group_cases)}
        cases.extend(group_cases)
    if not cases or any(c.find("failure") is not None or c.find("error") is not None for c in cases):
        raise ValueError("source cases missing, failed or errored")
    for row in expected["selected"]:
        names=modules(row["path"],stems)
        if not any(any(c.get("classname","")==n or c.get("classname","").startswith(n+".") for n in names) for c in cases):
            raise ValueError("selected module has no executed cases: "+row["path"])
    all_names=set().union(*(modules(r["path"],stems) for r in expected["selected"]))
    if any(not any(c.get("classname","")==n or c.get("classname","").startswith(n+".") for n in all_names) for c in cases):
        raise ValueError("reported case is outside the selected public source scope")
    skipped=[]
    for c in cases:
        skip=c.find("skipped")
        if skip is None:continue
        reason=skip.get("message","");allowed=ALLOWED_SKIPS.get(reason,())
        if not any((c.get('name')==test or c.get('name','').startswith(test+'[')) and
            any(c.get("classname","")==n or c.get("classname","").startswith(n+".") for n in modules(path,stems)) for path,test in allowed):
            raise ValueError("unexpected unexecuted case: "+c.get("classname","")+"::"+c.get("name","")+": "+reason)
        skipped.append({"id":c.get("classname","")+"::"+c.get("name",""),"reason":reason})
    return {"status":"PUBLIC_SOURCE_SUBSET_PASS","tests":len(cases),"passed":len(cases)-len(skipped),
        "declared_unexecuted":skipped,"selected_modules":len(expected["selected"]),"separate_modules":expected["separate"],
        "isolated_runtimes":audits,
        "limits":expected["qualification"],"certificates_issued":[]}

def instrument_run(args):
    """One isolated runtime/process, with exact collection and phase evidence."""
    if args.basetemp is None or args.runtime is None or not args.expected_commit:
        raise ValueError("node evidence requires runtime, owned basetemp and expected exact commit")
    if os.environ.get("PYTEST_ADDOPTS") or os.environ.get("PYTEST_PLUGINS"):
        raise ValueError("inherited pytest selection/plugin overrides are not canonical source scope")
    if args.shards != (4 if args.runtime == "gateway" else 1):
        raise ValueError("gateway requires four workers; isolated media requires one")
    if not 0 <= args.shard_index < args.shards:
        raise ValueError("invalid shard index")
    if any((args.output/name).exists() for name in ("run.json", "terminal.json", "phases.jsonl", "report.xml", "storage-audit.json", "generated-bytecode.json")):
        raise ValueError("fresh evidence folder required; preserve original run artifacts")
    sys.path.insert(0, str(ROOT))
    sys.dont_write_bytecode = True
    from tools.rebuild import public_source_shards as evidence
    evidence.import_path_identity(ROOT)
    if any(os.environ.get(k) for k in ("PYTHONHOME", "PYTHONUSERBASE", "PYTHONSTARTUP", "PYTHONINSPECT", "PYTHONOPTIMIZE")):
        raise ValueError("ambient Python startup/import overrides are forbidden")
    source_before = evidence.source_identity(ROOT, args.expected_commit)
    environment_before = evidence.environment_identity(args.runtime)
    execution_id = str(uuid.uuid4())
    selection = plan()
    manifest = args.output / "selection.json"
    if manifest.exists() and json.loads(manifest.read_text()) != selection:
        raise ValueError("selection drifted before node collection/execution")
    manifest.write_text(json.dumps(selection, indent=2) + "\n")
    selected = [r["path"] for r in selection["selected"] if runtime(r["path"]) == args.runtime]
    cmd = [sys.executable, "-B", "-s", str(ROOT/"tools/rebuild/source_storage_audit.py"),
        "--report", str(args.output/"storage-audit.json"), *selected, "-q", "--disable-warnings",
        "-c", str(ROOT/"pytest.ini"), "--rootdir="+str(ROOT), "--confcutdir="+str(ROOT),
        *[arg for plugin in evidence.EXPLICIT_PLUGINS[args.runtime] for arg in ("-p", plugin)],
        "--basetemp="+str(args.basetemp), "-p", "tools.rebuild.public_source_shards",
        "--van-source-output="+str(args.output.resolve()), "--van-source-root="+str(ROOT),
        "--van-source-execution-id="+execution_id, "--van-source-runtime="+args.runtime, "--van-source-expected-commit="+args.expected_commit,
        "--van-source-shards="+str(args.shards), "--van-source-index="+str(args.shard_index),
        "--van-source-costs="+str(ROOT/"tools/rebuild/backend_public_source_costs.json")]
    collecting = args.command == "collect"
    cmd += ["--collect-only"] if collecting else ["--junitxml="+str(args.output/"report.xml")]
    receipt = {"expected_commit": args.expected_commit, "execution_id": execution_id, "command": cmd,
        "source_before": source_before, "environment_before": environment_before,
        "workflow_run": {"id": os.environ.get("GITHUB_RUN_ID"),
                         "attempt": os.environ.get("GITHUB_RUN_ATTEMPT")},
        "terminal": False}
    receipt_path = args.output/"run.json"
    receipt_path.write_text(json.dumps(receipt, indent=2)+"\n")
    result = subprocess.run(cmd, cwd=ROOT, env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                                              "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"})
    try:
        outputs = evidence.archive_generated_bytecode(ROOT, args.expected_commit, source_before, args.output)
        child_state = evidence.read_json(args.output/"terminal.json")
        evidence.require(child_state.get("generated_cache_candidates") == outputs,
                         "child/parent generated-cache observation differs")
        receipt["generated_cache_outputs"] = outputs
        receipt.update(source_after=evidence.source_identity(ROOT, args.expected_commit),
            environment_after=evidence.environment_identity(args.runtime))
    except Exception as exc:
        receipt["parent_observation_error"] = {"type": type(exc).__name__, "message": str(exc)}
    receipt.update(terminal=True, exit=result.returncode,
        artifact_sha256={name: digest(args.output/name) for name in
            ("terminal.json", "phases.jsonl", "storage-audit.json", "generated-bytecode.json", *(() if collecting else ("report.xml",)))
            if (args.output/name).is_file()})
    receipt_path.write_text(json.dumps(receipt, indent=2)+"\n")
    return result.returncode or int(bool(receipt.get("parent_observation_error")))

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("command",choices=("plan","run","verify","collect","run-shard","verify-shards"));a.add_argument("--output",type=Path,required=True)
    a.add_argument("--basetemp",type=Path);a.add_argument("--runtime",choices=("gateway","media"))
    a.add_argument("--expected-commit");a.add_argument("--shards",type=int,default=4)
    a.add_argument("--shard-index",type=int,default=0)
    a.add_argument("--job-result",choices=("success","failure","cancelled","skipped"))
    args=a.parse_args();args.output.mkdir(exist_ok=True,parents=True)
    manifest=args.output/"selection.json";report=args.output/"report.xml";audit=args.output/"storage-audit.json"
    if args.command=="plan":
        d=plan();manifest.write_text(json.dumps(d,indent=2)+"\n");print({"selected":len(d["selected"]),"separate":len(d["separate"])});return 0
    if args.command in {"collect", "run-shard"}:
        return instrument_run(args)
    if args.command == "verify-shards":
        if not args.expected_commit or not args.job_result:
            a.error("verify-shards requires expected commit and actual prerequisite job result")
        sys.path.insert(0, str(ROOT))
        from tools.rebuild.public_source_shards import verify_shards
        result = verify_shards(args.output, args.expected_commit, args.job_result,
            root=ROOT, shard_count=args.shards)
        (args.output/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps(result,indent=2));return 0
    d=json.loads(manifest.read_text())
    if d!=plan():raise ValueError("selection drifted before source execution")
    if args.command=="run":
        if args.basetemp is None or args.runtime is None:a.error("run requires an isolated --basetemp and --runtime")
        report=args.output/(args.runtime+"-report.xml");audit=args.output/(args.runtime+"-storage-audit.json")
        return subprocess.run([sys.executable,str(ROOT/"tools/rebuild/source_storage_audit.py"),"--report",str(audit),
            *[r["path"] for r in d["selected"] if runtime(r["path"])==args.runtime],"-q","--disable-warnings","--basetemp="+str(args.basetemp),"--junitxml="+str(report)],cwd=ROOT).returncode
    result=verify(d,report,audit);(args.output/"summary.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result,indent=2));return 0

if __name__=="__main__":raise SystemExit(main())
