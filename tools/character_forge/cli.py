from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any
import yaml
from .gates import evaluate
from .manifest import ROOT, append_receipt, dump_yaml, find_artifact, load_yaml, rel, sha256_file, source_records, upsert_artifact
from .receipts import now_iso, packaging_receipt, verify_owner_token
from .status import load_status, save_status
from .svg_lint import lint_svg, render_layer_sheet

DOCS=ROOT/"docs"/"character_forge"; TOOLS_PATH=DOCS/"TOOLS.yaml"; ACCEPTANCE_PATH=DOCS/"ACCEPTANCE.yaml"; DEVICE_PATH=DOCS/"DEVICE_CHECKLIST.yaml"
CONTRACT_PATH=ROOT/"visual-authority"/"rive_contract.json"; WORKING_DIR=ROOT/"visual-authority"/"character-forge"/"09-rive-working"; VALIDATION_DIR=ROOT/"visual-authority"/"character-forge"/"10-validation"
ANDROID_TEST_ASSETS=ROOT/"android"/"app"/"src"/"androidTest"/"assets"; ANDROID_DEBUG_ASSETS=ROOT/"android"/"app"/"src"/"debug"/"assets"
SOURCE_RIV=ROOT/"visual-authority"/"rive"/"van_runtime.riv"; APP_RIV=ROOT/"android"/"app"/"src"/"main"/"assets"/"van.riv"
EVIDENCE_DIR=ROOT/"visual-authority"/"character-forge"/"11-device-evidence"
COMPONENT_LEDGER=ROOT/"evidence"/"van-system-audit"/"component_ledger.json"
QUAL_MATRIX=ROOT/"docs"/"audit"/"van-fable-whole-project-2026-09-21"/"VAN_RUNTIME_QUALIFICATION_MATRIX.md"
IDENTITY_DOC=ROOT/"docs"/"VAN_CHARACTER_VISUAL_IDENTITY.md"

def _yaml(path:Path)->dict[str,Any]:
    if not path.is_file(): return {}
    data=yaml.safe_load(path.read_text(encoding="utf-8")); return data if isinstance(data,dict) else {}

def _write_yaml(path:Path,data:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(yaml.safe_dump(data,sort_keys=False,allow_unicode=True),encoding="utf-8")

def _git_head()->str: return subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()

def _receipt(command:str,inputs:list[str],outputs:list[str],actor:str|None=None,reason:str|None=None):
    row={"command":command,"actor":actor or os.environ.get("USER") or "unknown","inputs":inputs,"outputs":outputs,"timestamp":now_iso()}
    if reason: row["reason"]=reason
    return row

def _pinned_tool(name:str)->str:
    return str((((_yaml(TOOLS_PATH).get("critical_path") or {}).get(name) or {}).get("version")) or "")

def _inkscape_version()->str:
    raw=subprocess.check_output(["inkscape","--version"],text=True).strip()
    parts=raw.split()
    if len(parts)<2: raise RuntimeError(f"unparseable Inkscape version: {raw}")
    return parts[1]

def _save(manifest,status): dump_yaml(manifest); save_status(status)

def cmd_status(args):
    data=load_status(); print(json.dumps(data,indent=2) if args.json else yaml.safe_dump(data,sort_keys=False)); return 0

def cmd_source_admit(args):
    manifest=load_yaml(); status=load_status(); records=source_records()
    old={(x.get("path"),x.get("sha256")) for x in manifest.get("sources") or []}; new={(x.get("path"),x.get("sha256")) for x in records}
    if old==new:
        print("NO_CHANGE"); return 0
    manifest["sources"]=records
    if old != new and manifest.get("owner_confirmed_complete"):
        manifest["owner_confirmed_complete"]=False
        manifest["owner_confirmation_date"]=None
    if not status.get("baseline_sha"): status["baseline_sha"]=_git_head()
    manifest["baseline_sha"]=status["baseline_sha"]; status["current_stage"]="admission"; status["build_ready"]=False
    status["blockers"]=["OWNER_SOURCE_CONFIRMATION_PENDING","RIVE_CLI_UNPINNED","LAYER_ARTIFACT_MISSING","RIVE_ASSET_MISSING","S24_DEVICE_GATES_NOT_RUN"]
    status["next_action"]="Owner reviews MANIFEST.yaml source set and sets owner_confirmed_complete: true with owner_confirmation_date"
    append_receipt(manifest,_receipt("source admit",sorted(f"{p}:{s}" for p,s in old),sorted(f"{p}:{s}" for p,s in new),args.actor)); _save(manifest,status)
    print("NO_CHANGE" if old==new else f"admitted {len(records)} source files"); return 0

def cmd_vectors_lint(args):
    report=lint_svg(Path(args.svg),require_geometry=not args.no_geometry); print(json.dumps(report.as_dict(),indent=2)); return 0 if report.ok else 1

def cmd_vectors_admit(args):
    svg=Path(args.svg).resolve(); report=lint_svg(svg,require_geometry=True)
    if not report.ok: print(json.dumps(report.as_dict(),indent=2)); return 1
    pinned=_pinned_tool("inkscape")
    if pinned in {"","None","UNPINNED"}:
        print("refused: Inkscape must be pinned in TOOLS.yaml",file=sys.stderr); return 1
    try: actual=_inkscape_version()
    except Exception as exc:
        print(f"refused: could not determine Inkscape version: {exc}",file=sys.stderr); return 1
    if actual!=pinned:
        print(f"refused: Inkscape {actual!r} does not equal pinned {pinned!r}",file=sys.stderr); return 1
    manifest=load_yaml(); status=load_status(); sha=sha256_file(svg)
    current=find_artifact(manifest,kind="layer_svg")
    output=VALIDATION_DIR/"layer_sheet.png"
    if current and current.get("sha256")==sha and current.get("inkscape_version")==pinned and output.is_file():
        print("NO_CHANGE"); return 0
    for previous in manifest.get("artifacts") or []:
        if previous.get("kind")=="layer_svg" and previous.get("sha256")!=sha:
            previous["promotion"]="SUPERSEDED"
    upsert_artifact(manifest,{"artifact_id":f"layer_svg:{sha}","kind":"layer_svg","path":rel(svg),"sha256":sha,"stage":"vector","promotion":"CANDIDATE","produced_by":f"artist:{args.artist}","inputs":[r["artifact_id"] for r in manifest.get("sources") or []],"lint":report.as_dict(),"inkscape_version":pinned})
    manifest.setdefault("reviews",{}).pop("layer_svg",None)
    render_layer_sheet(svg,output)
    latest=find_artifact(manifest,kind="layer_svg"); latest["layer_sheet_sha256"]=sha256_file(output)
    append_receipt(manifest,_receipt("vectors admit",[sha],[sha256_file(output)],args.actor,"lint-clean SVG rendered with pinned Inkscape"))
    status["current_stage"]="vector"; status["next_action"]="Independent reviewer/owner records MANIFEST.yaml reviews.layer_svg verdict PASS"; _save(manifest,status); return 0

def _infer_stage(path,explicit):
    if explicit: return explicit
    name=path.name.lower()
    if "core" in name:return "core_rig"
    if "full" in name:return "full_rig"
    raise ValueError("cannot infer stage")

def cmd_tools_import_lock(args):
    lock_path=Path(args.path).resolve()
    if not lock_path.is_file():
        print(f"refused: toolchain lock missing: {lock_path}",file=sys.stderr); return 1
    lock=json.loads(lock_path.read_text(encoding="utf-8"))
    repo_sha=str(lock.get("repository_sha") or "")
    if repo_sha and repo_sha != _git_head():
        print(f"refused: toolchain lock repository SHA {repo_sha} differs from HEAD {_git_head()}",file=sys.stderr); return 1
    rive_version=str(((lock.get("rive_cli") or {}).get("version") or "")).strip()
    inkscape_version=str(((lock.get("inkscape") or {}).get("version") or "")).strip()
    if not rive_version or rive_version in {"UNPINNED","version-command-unavailable"} or not inkscape_version:
        print("refused: toolchain lock lacks a qualified Rive CLI/Inkscape version",file=sys.stderr); return 1
    tools=_yaml(TOOLS_PATH)
    tools.setdefault("critical_path",{}).setdefault("rive_cli",{})["version"]=rive_version
    tools.setdefault("critical_path",{}).setdefault("inkscape",{})["version"]=inkscape_version
    _write_yaml(TOOLS_PATH,tools)
    status=load_status()
    status["blockers"]=[b for b in status.get("blockers",[]) if b!="RIVE_CLI_UNPINNED"]
    status["next_action"]="Run source admission/owner confirmation if pending, then proceed to M1/M2 with the pinned Netcup toolchain."
    manifest=load_yaml()
    append_receipt(
        manifest,
        _receipt(
            "tools import-lock",
            [sha256_file(lock_path),repo_sha],
            [f"rive_cli={rive_version}",f"inkscape={inkscape_version}"],
            args.actor,
            "Qualified Netcup authoring toolchain imported into repository authority",
        ),
    )
    _save(manifest,status)
    return 0

def cmd_rive_receipt(args):
    candidate=Path(args.candidate).resolve(); stage=_infer_stage(candidate,args.stage); manifest=load_yaml(); layer=find_artifact(manifest,kind="layer_svg")
    try: candidate.relative_to(WORKING_DIR.resolve())
    except ValueError:
        print("refused: Rive candidate must be under visual-authority/character-forge/09-rive-working",file=sys.stderr); return 1
    if not layer or args.svg_sha!=layer.get("sha256"): print("refused: svg-sha is not the admitted layer artifact",file=sys.stderr); return 1
    pinned=str((((_yaml(TOOLS_PATH).get("critical_path") or {}).get("rive_cli") or {}).get("version")))
    if pinned in {"", "None", "UNPINNED"} or args.authoring_version != pinned:
        print(f"refused: Rive CLI version {args.authoring_version!r} does not equal pinned version {pinned!r}",file=sys.stderr); return 1
    contract_sha=sha256_file(CONTRACT_PATH)
    WORKING_DIR.mkdir(parents=True,exist_ok=True); path=WORKING_DIR/f"{candidate.stem}.receipt.json"
    expected_static={"candidate_sha256":sha256_file(candidate),"candidate_path":rel(candidate),"stage":stage,"authoring_tool":"rive_cli","authoring_version":args.authoring_version,"rive_file_id":args.rive_file_id,"rive_revision":args.rive_revision,"svg_sha256":args.svg_sha,"contract_sha256":contract_sha,"artist":args.artist,"notes":args.notes or ""}
    if path.is_file():
        existing=json.loads(path.read_text(encoding="utf-8"))
        if all(existing.get(k)==v for k,v in expected_static.items()):
            print("NO_CHANGE"); return 0
    receipt=packaging_receipt(candidate=candidate,stage=stage,authoring_tool="rive_cli",authoring_version=args.authoring_version,rive_file_id=args.rive_file_id,rive_revision=args.rive_revision,svg_sha=args.svg_sha,contract_sha=contract_sha,artist=args.artist,notes=args.notes or "")
    path.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    append_receipt(manifest,_receipt("rive receipt",[args.svg_sha,receipt["contract_sha256"]],[receipt["candidate_sha256"]],args.actor))
    status=load_status(); status["next_action"]=f"python -m tools.character_forge.cli rive stage-candidate {rel(candidate)} --stage {stage}"
    _save(manifest,status); print(path.relative_to(ROOT)); return 0

def _receipt_for_candidate(candidate):
    sha=sha256_file(candidate)
    for path in WORKING_DIR.glob("*.receipt.json"):
        try:data=json.loads(path.read_text(encoding="utf-8"))
        except Exception:continue
        if data.get("candidate_sha256")==sha:return data
    return None

def cmd_rive_stage(args):
    candidate=Path(args.riv).resolve()
    if not candidate.is_file() or candidate.stat().st_size<1024: print("refused: candidate missing or smaller than 1024 bytes",file=sys.stderr); return 1
    receipt=_receipt_for_candidate(candidate); stage=args.stage
    if not receipt or receipt.get("stage")!=stage: print("refused: matching packaging receipt missing",file=sys.stderr); return 1
    if receipt.get("candidate_path")!=rel(candidate): print("refused: receipt belongs to another candidate path",file=sys.stderr); return 1
    if receipt.get("contract_sha256")!=sha256_file(CONTRACT_PATH): print("refused: contract changed after Rive export",file=sys.stderr); return 1
    layer=find_artifact(load_yaml(),kind="layer_svg")
    if not layer or receipt.get("svg_sha256")!=layer.get("sha256"): print("refused: receipt references a superseded layer SVG",file=sys.stderr); return 1
    if receipt.get("authoring_tool")!="rive_cli": print("refused: receipt authoring tool is not rive_cli",file=sys.stderr); return 1
    if receipt.get("authoring_version")!=_pinned_tool("rive_cli"): print("refused: receipt Rive CLI version no longer matches TOOLS.yaml",file=sys.stderr); return 1
    sha=sha256_file(candidate); mode="core" if stage=="core_rig" else "full"; threshold={"max_janky_percent":float((load_status().get("performance") or {}).get("max_janky_percent",5.0))}
    current_status=load_status(); key="core_rig" if stage=="core_rig" else "full_rig"
    staged=[ANDROID_TEST_ASSETS/"van_candidate.riv",ANDROID_DEBUG_ASSETS/"van_candidate.riv"]
    if current_status.get(key,{}).get("candidate_sha256")==sha and all(p.is_file() and sha256_file(p)==sha for p in staged):
        print("NO_CHANGE"); return 0
    if stage=="full_rig":
        m2=evaluate("m2")
        if not m2.passed:
            print("refused: M2 is not green\n- "+"\n- ".join(m2.reasons),file=sys.stderr); return 1
        baseline=EVIDENCE_DIR/"core_baseline"
        if not baseline.is_dir() or not list(baseline.glob("*.png")):
            print("refused: full rig cannot be staged before M2 core baseline evidence exists",file=sys.stderr); return 1
        test_baseline=ANDROID_TEST_ASSETS/"core_baseline"
        if test_baseline.exists(): shutil.rmtree(test_baseline)
        shutil.copytree(baseline,test_baseline)
    for target in (ANDROID_TEST_ASSETS,ANDROID_DEBUG_ASSETS):
        target.mkdir(parents=True,exist_ok=True); shutil.copyfile(candidate,target/"van_candidate.riv"); shutil.copyfile(CONTRACT_PATH,target/"rive_contract.json")
        (target/"forge_mode.txt").write_text(mode+"\n",encoding="utf-8"); (target/"forge_thresholds.json").write_text(json.dumps(threshold,indent=2)+"\n",encoding="utf-8")
    manifest=load_yaml(); upsert_artifact(manifest,{"artifact_id":f"riv_candidate:{sha}","kind":"riv_candidate","path":rel(candidate),"sha256":sha,"stage":stage,"promotion":"CANDIDATE","produced_by":f"artist:{receipt.get('artist')}","inputs":[f"layer_svg:{receipt.get('svg_sha256')}",f"source:{receipt.get('contract_sha256')}"]})
    append_receipt(manifest,_receipt("rive stage-candidate",[sha],[sha],args.actor)); status=load_status(); status["current_stage"]=stage; key="core_rig" if stage=="core_rig" else "full_rig"; status[key]["candidate_sha256"]=sha; status[key]["emulator_validation"]="NOT_RUN"; status[key]["ci_run"]=None
    if stage=="core_rig":status[key]["owner_verdict"]="NONE"
    else:status[key]["reviewed"]="NONE"
    status["next_action"]="Push candidate and record android-instrumentation CI evidence for this exact SHA"; _save(manifest,status); return 0

def cmd_gate(args):
    result=evaluate(args.gate); status=load_status()
    if args.gate=="m0":
        prior=bool(status.get("build_ready")); status["build_ready"]=result.passed
        if prior!=result.passed:
            manifest=load_yaml()
            append_receipt(
                manifest,
                _receipt(
                    "gate m0",
                    [str(status.get("baseline_sha") or "")]+[str(r.get("sha256") or "") for r in manifest.get("sources") or []],
                    [f"BUILD_READY={str(result.passed).lower()}"],
                    args.actor,
                    "M0 gate transition recorded from the evaluated repository evidence",
                ),
            )
            _save(manifest,status)
        else:
            save_status(status)
    else:
        save_status(status)
    print(json.dumps({"gate":result.gate,"passed":result.passed,"reasons":list(result.reasons)},indent=2) if args.json else (f"{result.gate}: PASS" if result.passed else f"{result.gate}: FAIL\n- "+"\n- ".join(result.reasons))); return 0 if result.passed else 1

def cmd_record_validation(args):
    status=load_status(); manifest=load_yaml(); run=str(args.ci_run or "").strip()
    if not run.startswith(("https://github.com/","http://github.com/")):
        print("refused: --ci-run must be a GitHub Actions run URL",file=sys.stderr); return 2
    if args.stage in {"core_rig","full_rig"}:
        record=status[args.stage]; expected=record.get("candidate_sha256")
        if not expected or args.candidate_sha != expected:
            print("refused: candidate SHA does not equal the staged candidate",file=sys.stderr); return 1
        previous=(manifest.get("ci_evidence") or {}).get(expected) or {}
        baseline_ready=bool(list((EVIDENCE_DIR/"core_baseline").glob("*.png")))
        if record.get("emulator_validation")==args.result and record.get("ci_run")==run and previous.get("result")==args.result and (args.stage!="core_rig" or args.result!="PASS" or baseline_ready):
            print("NO_CHANGE"); return 0
        record["emulator_validation"]=args.result; record["ci_run"]=run
        manifest.setdefault("ci_evidence",{})[expected]={"stage":args.stage,"result":args.result,"ci_run":run,"recorded_at":now_iso()}
        if args.stage=="core_rig" and args.result=="PASS":
            if not args.evidence_dir:
                print("refused: core PASS requires --evidence-dir from the CI screenshot artifact",file=sys.stderr); return 2
            source=Path(args.evidence_dir).resolve()
            pngs=list(source.rglob("*.png")) if source.is_dir() else []
            if not pngs:
                print("refused: no PNG core evidence found",file=sys.stderr); return 1
            baseline=EVIDENCE_DIR/"core_baseline"
            if baseline.exists(): shutil.rmtree(baseline)
            baseline.mkdir(parents=True,exist_ok=True)
            for path in pngs:
                shutil.copyfile(path,baseline/path.name)
            status["next_action"]="Owner views the exact core candidate on the S24 and records the core verdict"
        elif args.stage=="full_rig" and args.result=="PASS":
            status["next_action"]="Independent reviewer records full-rig PASS"
    else:
        if not SOURCE_RIV.is_file() or not APP_RIV.is_file() or sha256_file(SOURCE_RIV)!=sha256_file(APP_RIV):
            print("refused: production validation requires byte-identical integrated assets",file=sys.stderr); return 1
        sha=sha256_file(APP_RIV)
        prod=status.get("production") or {}; prior=(manifest.get("ci_evidence") or {}).get(sha) or {}
        if prod.get("emulator_validation")==args.result and prod.get("ci_run")==run and prod.get("rive_sha256")==sha and prior.get("stage")=="production" and prior.get("result")==args.result:
            print("NO_CHANGE"); return 0
        status["production"]={"emulator_validation":args.result,"ci_run":run,"rive_sha256":sha}
        manifest.setdefault("ci_evidence",{})[sha]={"stage":"production","result":args.result,"ci_run":run,"recorded_at":now_iso()}
        status["next_action"]="Complete S24 DEVICE_CHECKLIST.yaml and owner biometric acceptance" if args.result=="PASS" else "Fix production validation failure"
        expected=sha
    append_receipt(
        manifest,
        _receipt(
            "record validation",
            [str(expected),run],
            [f"{args.stage}={args.result}"],
            args.actor,
            "CI validation result bound to the exact candidate/production SHA",
        ),
    )
    _save(manifest,status); return 0

def cmd_review(args):
    manifest=load_yaml(); status=load_status()
    if args.target=="layer":
        layer=find_artifact(manifest,kind="layer_svg")
        if not layer: print("refused: no admitted layer SVG",file=sys.stderr); return 1
        row={"sha256":layer["sha256"],"reviewed_by":args.reviewer,"date":args.date,"verdict":args.verdict,"notes":args.notes or ""}
        if (manifest.get("reviews") or {}).get("layer_svg")==row: print("NO_CHANGE"); return 0
        manifest.setdefault("reviews",{})["layer_svg"]=row
        status["next_action"]="Build the M2 core rig" if args.verdict=="PASS" else "Artist revises the layer SVG"
    else:
        sha=(status.get("full_rig") or {}).get("candidate_sha256")
        if not sha or (status.get("full_rig") or {}).get("emulator_validation")!="PASS":
            print("refused: full review requires a full candidate with emulator PASS",file=sys.stderr); return 1
        row={"sha256":sha,"reviewed_by":args.reviewer,"date":args.date,"verdict":args.verdict,"notes":args.notes or ""}
        if (manifest.get("reviews") or {}).get("full_rig")==row and status["full_rig"].get("reviewed")==args.verdict: print("NO_CHANGE"); return 0
        manifest.setdefault("reviews",{})["full_rig"]=row
        status["full_rig"]["reviewed"]=args.verdict
        status["next_action"]="python -m tools.character_forge.cli gate m3" if args.verdict=="PASS" else "Artist revises the full rig"
    review_sha=row["sha256"]
    append_receipt(
        manifest,
        _receipt(
            f"review {args.target}",
            [review_sha],
            [args.verdict],
            args.actor,
            f"review by {args.reviewer} on {args.date}",
        ),
    )
    _save(manifest,status); return 0

def cmd_confirm_source(args):
    if not args.confirm_complete:
        print("refused: owner confirmation requires --confirm-complete",file=sys.stderr); return 2
    manifest=load_yaml()
    if not manifest.get("sources"):
        print("refused: run source admit before owner confirmation",file=sys.stderr); return 1
    if manifest.get("owner_confirmed_complete") and manifest.get("owner_confirmation_date")==args.date:
        print("NO_CHANGE"); return 0
    manifest["owner_confirmed_complete"]=True; manifest["owner_confirmation_date"]=args.date
    append_receipt(manifest,_receipt("owner confirm-source",[r["sha256"] for r in manifest["sources"]],["OWNER_CONFIRMED_COMPLETE"],args.actor))
    status=load_status(); status["next_action"]="python -m tools.character_forge.cli gate m0"
    _save(manifest,status)
    return 0

def cmd_core_verdict(args):
    status=load_status(); core=status.get("core_rig") or {}
    if not core.get("candidate_sha256") or not args.ci_run: print("refused: staged core candidate and --ci-run required",file=sys.stderr); return 1
    if core.get("emulator_validation")=="NOT_RUN" or core.get("ci_run")!=args.ci_run:
        print("refused: core verdict must reference the recorded emulator-validation CI run",file=sys.stderr); return 1
    if args.verdict=="PASS" and core.get("emulator_validation")!="PASS":
        print("refused: owner PASS cannot outrank a failed emulator validation",file=sys.stderr); return 1
    acceptance=_yaml(ACCEPTANCE_PATH); existing=acceptance.get("core_rig") or {}
    if existing.get("candidate_sha256")==core["candidate_sha256"] and existing.get("verdict")==args.verdict and existing.get("notes","")== (args.notes or "") and existing.get("ci_run")==args.ci_run:
        print("NO_CHANGE"); return 0
    acceptance["core_rig"]={"candidate_sha256":core["candidate_sha256"],"verdict":args.verdict,"notes":args.notes or "","ci_run":args.ci_run,"recorded_at":now_iso()}; _write_yaml(ACCEPTANCE_PATH,acceptance)
    core["ci_run"]=args.ci_run; core["owner_verdict"]=args.verdict; status["core_rig"]=core; status["next_action"]="Complete full rig" if args.verdict=="PASS" else "Artist revises core rig"
    manifest=load_yaml()
    append_receipt(
        manifest,
        _receipt(
            "owner record-core-verdict",
            [core["candidate_sha256"],args.ci_run],
            [args.verdict],
            args.actor,
            "owner core verdict bound to the already-recorded emulator CI evidence",
        ),
    )
    _save(manifest,status); return 0

def cmd_integrate(args):
    candidate=Path(args.candidate).resolve(); status=load_status(); full=status.get("full_rig") or {}
    m3=evaluate("m3")
    if not m3.passed: print("refused: M3 is not green\n- "+"\n- ".join(m3.reasons),file=sys.stderr); return 1
    sha=sha256_file(candidate)
    if sha!=full.get("candidate_sha256"): print("refused: candidate SHA differs from validated full-rig candidate",file=sys.stderr); return 1
    manifest=load_yaml()
    already=find_artifact(manifest,kind="riv_accepted",sha256=sha)
    if already and SOURCE_RIV.is_file() and APP_RIV.is_file() and sha256_file(SOURCE_RIV)==sha and sha256_file(APP_RIV)==sha and status.get("rive_asset_ready"):
        print("NO_CHANGE"); return 0
    SOURCE_RIV.parent.mkdir(parents=True,exist_ok=True); APP_RIV.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(candidate,SOURCE_RIV); shutil.copyfile(candidate,APP_RIV); (SOURCE_RIV.parent/"van_runtime.sha256").write_text(sha+"\n",encoding="utf-8")
    upsert_artifact(manifest,{"artifact_id":f"riv_accepted:{sha}","kind":"riv_accepted","path":rel(SOURCE_RIV),"sha256":sha,"stage":"integrated","promotion":"REVIEWED","produced_by":"cli:android integrate","inputs":[f"riv_candidate:{sha}"]}); append_receipt(manifest,_receipt("android integrate",[sha],[sha,sha],args.actor,"M3 green; exact emulator-validated full-rig candidate integrated byte-identically"))
    for path in (ANDROID_TEST_ASSETS/"van_candidate.riv",ANDROID_TEST_ASSETS/"forge_mode.txt",ANDROID_DEBUG_ASSETS/"van_candidate.riv",ANDROID_DEBUG_ASSETS/"forge_mode.txt"):
        if path.exists(): path.unlink()
    status["current_stage"]="integrated"; status["rive_authored"]=True; status["rive_asset_ready"]=True
    status["production"]={"emulator_validation":"NOT_RUN","ci_run":None,"rive_sha256":sha}
    status["next_action"]="Push and record production-mode android-instrumentation validation"; _save(manifest,status); return 0

def _fetch_gateway_acceptance(url):
    headers={}; ingress=os.environ.get("VAN_INGRESS_TOKEN",""); device=os.environ.get("VAN_DEVICE_TOKEN","")
    if ingress:headers["X-Van-Ingress-Token"]=ingress
    if device:headers["X-Van-Device-Token"]=device
    with urllib.request.urlopen(urllib.request.Request(url.rstrip("/")+"/v1/visual/acceptance",headers=headers),timeout=15) as response:return json.loads(response.read().decode("utf-8"))

def cmd_record_acceptance(args):
    if not APP_RIV.is_file() or not SOURCE_RIV.is_file(): print("refused: integrated Rive asset missing",file=sys.stderr); return 1
    sha=sha256_file(APP_RIV)
    if sha!=sha256_file(SOURCE_RIV): print("refused: source and app Rive differ",file=sys.stderr); return 1
    subject=f"sha256:{sha}"
    if args.from_gateway:
        if not args.gateway_url:return 2
        record=_fetch_gateway_acceptance(args.gateway_url)
        if record.get("rive_sha256")!=sha or record.get("subject")!=subject or not record.get("verified"): print("refused: gateway record does not verify this asset",file=sys.stderr); return 1
        final=dict(record); final["verified_by"]="gateway"
    else:
        if not args.token or not args.device_public_key:return 2
        verified=verify_owner_token(args.token,Path(args.device_public_key).read_text(encoding="utf-8"),act="visual-accept",subject=subject)
        final={"token":args.token,"rive_sha256":sha,"subject":subject,"key_id":verified["key_id"],"verified":True,"verified_by":"local","verified_at":now_iso()}
    acceptance=_yaml(ACCEPTANCE_PATH)
    if acceptance.get("final")==final and load_status().get("owner_accepted"):
        print("NO_CHANGE"); return 0
    acceptance["final"]=final; _write_yaml(ACCEPTANCE_PATH,acceptance); status=load_status(); status["owner_accepted"]=True; status["current_stage"]="certified"; status["next_action"]="python -m tools.character_forge.cli gate m4"
    manifest=load_yaml()
    append_receipt(
        manifest,
        _receipt(
            "owner record-acceptance",
            [sha,str(final.get("key_id") or ""),str(final.get("verified_by") or "")],
            ["OWNER_ACCEPTED"],
            args.actor,
            "verified visual-accept authority imported without copying the credential into the manifest receipt",
        ),
    )
    _save(manifest,status); return 0


def _update_release_truth(sha, status):
    if QUAL_MATRIX.is_file():
        lines=QUAL_MATRIX.read_text(encoding="utf-8").splitlines()
        for index,line in enumerate(lines):
            if line.startswith("| QUAL-EMB-01 |"):
                lines[index]=f"| QUAL-EMB-01 | Authored `van.riv` conforming to `visual-authority/rive_contract.json` | Character Forge M5 released; SHA-256 `{sha}` | READY | Requalify on Rive runtime/identity-contract change | `visual-authority/rive/manifest.json`; `docs/character_forge/DEVICE_CHECKLIST.yaml`; `docs/character_forge/ACCEPTANCE.yaml` |"
                break
        QUAL_MATRIX.write_text("\n".join(lines)+"\n",encoding="utf-8")
    if IDENTITY_DOC.is_file():
        text=IDENTITY_DOC.read_text(encoding="utf-8")
        start=text.index("### Rive status")
        end=text.index("### Interim Canvas character",start)
        replacement=f"""### Rive status

The authored `van.riv` artboard is **RELEASED** through Character Forge Rev 2.
Exact SHA-256: `{sha}`. The release authority and provenance are
`visual-authority/rive/manifest.json`; changing the bytes requires a new Character Forge
acceptance and release.

"""
        IDENTITY_DOC.write_text(text[:start]+replacement+text[end:],encoding="utf-8")
    if COMPONENT_LEDGER.is_file():
        ledger=json.loads(COMPONENT_LEDGER.read_text(encoding="utf-8"))
        rows=ledger.get("components",[])
        rive=next((row for row in rows if row.get("component")=="Rive embodiment"),None)
        if rive is not None:
            rive.update({
                "maturity_class":"INTEGRATED",
                "rationale":f"Character Forge M5 released exact owner-accepted asset {sha}.",
                "producer":"visual-authority/rive/van_runtime.riv",
                "consumer":"android/app/src/main/java/com/dial/van/visual/VanRiveAvatar.kt",
                "production_caller":"android/app/src/main/java/com/dial/van/visual/VanVisualRuntime.kt",
                "tests":["tests/contracts/test_character_forge_release.py","android/app/src/androidTest/java/com/dial/van/instrumentation/RiveContractTest.kt"],
                "runtime_evidence":[status["production"]["ci_run"],"docs/character_forge/DEVICE_CHECKLIST.yaml","docs/character_forge/ACCEPTANCE.yaml"],
                "owner_facing_projection":"Settings > Character renderer status and owner acceptance",
                "terminal_state":"INTEGRATED_AND_EVIDENCED",
            })
        additions=[
            {
                "component":"Character Forge deterministic release plane",
                "path":"tools/character_forge/cli.py","maturity_class":"INTEGRATED","disposition":"COMPLETE",
                "rationale":"M0-M5 provenance, gating and exact-SHA release plane.",
                "remediation_gate":"GATE 11","producer":"tools/character_forge/cli.py",
                "consumer":"van-ci.yml and release operator","production_caller":"tools/character_forge/cli.py",
                "tests":["tests/contracts/test_character_forge_manifest.py","tests/contracts/test_character_forge_status.py","tests/contracts/test_character_forge_release.py","tests/contracts/test_character_forge_mutations.py"],
                "runtime_evidence":[status["production"]["ci_run"]],"owner_facing_projection":"docs/character_forge/STATUS.json",
                "terminal_state":"INTEGRATED_AND_EVIDENCED"
            },
            {
                "component":"Character Forge owner visual acceptance",
                "path":"backend/van_gateway/visual/acceptance.py","maturity_class":"INTEGRATED","disposition":"COMPLETE",
                "rationale":"Biometric owner authority binds the exact Rive SHA to device/APK evidence.",
                "remediation_gate":"GATE 11","producer":"android/app/src/main/java/com/dial/van/visual/VanCharacterAcceptance.kt",
                "consumer":"backend/van_gateway/visual/acceptance.py","production_caller":"backend/van_gateway/app.py",
                "tests":["backend/tests/test_visual_acceptance.py","tests/contracts/test_character_forge_release.py"],
                "runtime_evidence":["docs/character_forge/ACCEPTANCE.yaml","docs/character_forge/DEVICE_CHECKLIST.yaml"],
                "owner_facing_projection":"Settings > Character > Accept this character asset",
                "terminal_state":"INTEGRATED_AND_EVIDENCED"
            }
        ]
        for addition in additions:
            existing=next((row for row in rows if row.get("component")==addition["component"]),None)
            if existing is None:
                addition["n"]=max([int(row.get("n",0)) for row in rows] or [0])+1
                rows.append(addition)
            else:
                existing.update(addition)
        ledger["components"]=rows; ledger["component_count"]=len(rows)
        COMPONENT_LEDGER.write_text(json.dumps(ledger,indent=2)+"\n",encoding="utf-8")


def cmd_release(args):
    pre=evaluate("m4")
    if not pre.passed: print("refused: M4 is not green\n- "+"\n- ".join(pre.reasons),file=sys.stderr); return 1
    sha=sha256_file(APP_RIV); tools=_yaml(TOOLS_PATH); status=load_status()
    release_path=SOURCE_RIV.parent/"manifest.json"
    if release_path.is_file() and status.get("qual_emb_01")=="READY":
        existing=json.loads(release_path.read_text(encoding="utf-8"))
        if existing.get("rive_sha256")==sha and existing.get("contract_sha256")==sha256_file(CONTRACT_PATH):
            print("NO_CHANGE"); return 0
    release={"asset":rel(APP_RIV),"source_asset":rel(SOURCE_RIV),"artboard":"Van","state_machine":"VanRuntime","git_sha":_git_head(),"rive_sha256":sha,"contract_sha256":sha256_file(CONTRACT_PATH),"visual_authority_revision":"2.3","rive_android":str((((tools.get("critical_path") or {}).get("rive_android") or {}).get("version"))),"rive_authoring_tool":"rive_cli","rive_authoring_version":str((((tools.get("critical_path") or {}).get("rive_cli") or {}).get("version"))),"emulator_validation_run":(status.get("production") or {}).get("ci_run"),"device_checklist":rel(DEVICE_PATH),"acceptance":rel(ACCEPTANCE_PATH)+"#final","released_at":now_iso()}
    release_path.write_text(json.dumps(release,indent=2)+"\n",encoding="utf-8"); manifest=load_yaml(); artifact=find_artifact(manifest,kind="riv_accepted",sha256=sha)
    if artifact:artifact["promotion"]="RELEASED"; artifact["stage"]="released"
    append_receipt(manifest,_receipt("release promote",[sha],[sha256_file(release_path)],args.actor,"M4 green; exact owner-accepted, S24-qualified production asset promoted")); status.update({"current_stage":"released","device_qualified":True,"owner_accepted":True,"rive_authored":True,"rive_asset_ready":True,"qual_emb_01":"READY","blockers":[],"next_action":"Commit the release outputs and require van-ci green on that commit"})
    _update_release_truth(sha,status); _save(manifest,status); return 0

def _parser():
    parser=argparse.ArgumentParser(prog="character-forge"); parser.add_argument("--actor",default=None); sub=parser.add_subparsers(dest="group",required=True)
    p=sub.add_parser("status"); p.add_argument("--json",action="store_true"); p.set_defaults(func=cmd_status)
    tools_cmd=sub.add_parser("tools").add_subparsers(dest="command",required=True); p=tools_cmd.add_parser("import-lock"); p.add_argument("--path",required=True); p.set_defaults(func=cmd_tools_import_lock)
    source=sub.add_parser("source").add_subparsers(dest="command",required=True); p=source.add_parser("admit"); p.set_defaults(func=cmd_source_admit)
    vectors=sub.add_parser("vectors").add_subparsers(dest="command",required=True); p=vectors.add_parser("lint"); p.add_argument("svg"); p.add_argument("--no-geometry",action="store_true",help=argparse.SUPPRESS); p.set_defaults(func=cmd_vectors_lint); p=vectors.add_parser("admit"); p.add_argument("svg"); p.add_argument("--artist",required=True); p.set_defaults(func=cmd_vectors_admit)
    rive=sub.add_parser("rive").add_subparsers(dest="command",required=True); p=rive.add_parser("receipt"); p.add_argument("--candidate",required=True); p.add_argument("--stage",choices=["core_rig","full_rig"]); p.add_argument("--authoring-version",required=True); p.add_argument("--rive-file-id",required=True); p.add_argument("--rive-revision",required=True); p.add_argument("--svg-sha",required=True); p.add_argument("--artist",required=True); p.add_argument("--notes"); p.set_defaults(func=cmd_rive_receipt); p=rive.add_parser("stage-candidate"); p.add_argument("riv"); p.add_argument("--stage",choices=["core_rig","full_rig"],required=True); p.set_defaults(func=cmd_rive_stage)
    p=rive.add_parser("record-validation"); p.add_argument("--stage",choices=["core_rig","full_rig","production"],required=True); p.add_argument("--result",choices=["PASS","FAIL"],required=True); p.add_argument("--ci-run",required=True); p.add_argument("--candidate-sha"); p.add_argument("--evidence-dir"); p.set_defaults(func=cmd_record_validation)
    review=sub.add_parser("review").add_subparsers(dest="command",required=True); p=review.add_parser("record"); p.add_argument("--target",choices=["layer","full"],required=True); p.add_argument("--verdict",choices=["PASS","FAIL"],required=True); p.add_argument("--reviewer",required=True); p.add_argument("--date",required=True); p.add_argument("--notes"); p.set_defaults(func=cmd_review)
    p=sub.add_parser("gate"); p.add_argument("gate",choices=["m0","m1","m2","m3","m4","m5"]); p.add_argument("--json",action="store_true"); p.set_defaults(func=cmd_gate)
    owner=sub.add_parser("owner").add_subparsers(dest="command",required=True); p=owner.add_parser("confirm-source"); p.add_argument("--confirm-complete",action="store_true"); p.add_argument("--date",required=True); p.set_defaults(func=cmd_confirm_source); p=owner.add_parser("record-core-verdict"); p.add_argument("--verdict",choices=["PASS","REVISE","REJECT"],required=True); p.add_argument("--notes"); p.add_argument("--ci-run",required=True); p.set_defaults(func=cmd_core_verdict); p=owner.add_parser("record-acceptance"); p.add_argument("--from-gateway",action="store_true"); p.add_argument("--gateway-url"); p.add_argument("--token"); p.add_argument("--device-public-key"); p.set_defaults(func=cmd_record_acceptance)
    android=sub.add_parser("android").add_subparsers(dest="command",required=True); p=android.add_parser("integrate"); p.add_argument("--candidate",required=True); p.set_defaults(func=cmd_integrate)
    release=sub.add_parser("release").add_subparsers(dest="command",required=True); p=release.add_parser("promote"); p.set_defaults(func=cmd_release)
    return parser

def main(argv=None): args=_parser().parse_args(argv); return int(args.func(args))
if __name__=="__main__": raise SystemExit(main())
