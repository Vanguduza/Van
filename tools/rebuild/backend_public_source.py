#!/usr/bin/env python3
"""Public source qualification; never a substitute for required private/native gates."""
from __future__ import annotations
import argparse
import hashlib
import json
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
    "member of the B1 closed set by definition": ("backend.tests.test_jev_no_generic_executor", "tests.test_jev_no_generic_executor"),
    "DDS checkout not present; blob hashes pinned above": ("backend.tests.test_jev_browser_eligibility", "tests.test_jev_browser_eligibility"),
    "no DDS git clone beside this checkout; the CI step verifies the same table itself": ("tests.contracts.test_ci_dds_contract_pin",),
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
        if not any(c.get("classname","")==n or c.get("classname","").startswith(n+".") for n in allowed):
            raise ValueError("unexpected unexecuted case: "+c.get("classname","")+"::"+c.get("name","")+": "+reason)
        skipped.append({"id":c.get("classname","")+"::"+c.get("name",""),"reason":reason})
    return {"status":"PUBLIC_SOURCE_SUBSET_PASS","tests":len(cases),"passed":len(cases)-len(skipped),
        "declared_unexecuted":skipped,"selected_modules":len(expected["selected"]),"separate_modules":expected["separate"],
        "isolated_runtimes":audits,
        "limits":expected["qualification"],"certificates_issued":[]}

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("command",choices=("plan","run","verify"));a.add_argument("--output",type=Path,required=True)
    a.add_argument("--basetemp",type=Path);a.add_argument("--runtime",choices=("gateway","media"))
    args=a.parse_args();args.output.mkdir(exist_ok=True,parents=True)
    manifest=args.output/"selection.json";report=args.output/"report.xml";audit=args.output/"storage-audit.json"
    if args.command=="plan":
        d=plan();manifest.write_text(json.dumps(d,indent=2)+"\n");print({"selected":len(d["selected"]),"separate":len(d["separate"])});return 0
    d=json.loads(manifest.read_text())
    if d!=plan():raise ValueError("selection drifted before source execution")
    if args.command=="run":
        if args.basetemp is None or args.runtime is None:a.error("run requires an isolated --basetemp and --runtime")
        report=args.output/(args.runtime+"-report.xml");audit=args.output/(args.runtime+"-storage-audit.json")
        return subprocess.run([sys.executable,str(ROOT/"tools/rebuild/source_storage_audit.py"),"--report",str(audit),
            *[r["path"] for r in d["selected"] if runtime(r["path"])==args.runtime],"-q","--disable-warnings","--basetemp="+str(args.basetemp),"--junitxml="+str(report)],cwd=ROOT).returncode
    result=verify(d,report,audit);(args.output/"summary.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result,indent=2));return 0

if __name__=="__main__":raise SystemExit(main())
