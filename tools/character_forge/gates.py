from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml
from .manifest import ROOT, find_artifact, load_yaml, sha256_file, verify_records
from .status import load_status, validate_status

DOCS=ROOT/"docs"/"character_forge"; TOOLS=DOCS/"TOOLS.yaml"; ACCEPTANCE=DOCS/"ACCEPTANCE.yaml"; DEVICE=DOCS/"DEVICE_CHECKLIST.yaml"
CONTRACT=ROOT/"visual-authority"/"rive_contract.json"; SOURCE_RIV=ROOT/"visual-authority"/"rive"/"van_runtime.riv"; APP_RIV=ROOT/"android"/"app"/"src"/"main"/"assets"/"van.riv"
RELEASE_MANIFEST=ROOT/"visual-authority"/"rive"/"manifest.json"; GRADLE=ROOT/"android"/"app"/"build.gradle.kts"

@dataclass(frozen=True)
class GateResult:
    gate:str; passed:bool; reasons:tuple[str,...]

def _yaml(path:Path)->dict[str,Any]:
    if not path.is_file(): return {}
    data=yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data,dict) else {}

def contract_surface_problems(contract:dict[str,Any])->list[str]:
    problems=[]
    if contract.get("artboard")!="Van": problems.append("artboard must be Van")
    if contract.get("state_machine")!="VanRuntime": problems.append("state_machine must be VanRuntime")
    if [i.get("name") for i in contract.get("inputs") or []] != ["state","speaking","listening","attention_x","attention_y","mouth_open","urgency","viseme","action_code"]: problems.append("public input surface drift")
    if contract.get("triggers") != ["point","ack","celebrate","warning","wave","shrug","present","panel"]: problems.append("trigger surface drift")
    states=contract.get("durable_states") or {}; actions=contract.get("finite_actions") or {}
    if set(states.values())!=set(range(18)) or len(states)!=18: problems.append("durable state surface drift")
    if set(actions.values())!=set(range(1,15)) or len(actions)!=14: problems.append("finite action surface drift")
    return problems

def _rive_android_pin():
    if not GRADLE.is_file(): return None
    m=re.search(r'app\.rive:rive-android:([^"\)]+)',GRADLE.read_text(encoding="utf-8"))
    return m.group(1) if m else None

def m0():
    manifest=load_yaml(); status=load_status(); tools=_yaml(TOOLS); problems=validate_status(status)
    if not status.get("baseline_sha"): problems.append("baseline SHA missing")
    if not manifest.get("owner_confirmed_complete"): problems.append("owner source confirmation pending")
    sources=manifest.get("sources") or []
    if not sources: problems.append("source set not admitted")
    problems.extend(verify_records(sources))
    pin=(((tools.get("critical_path") or {}).get("rive_android") or {}).get("version"))
    if pin!=_rive_android_pin(): problems.append(f"rive-android pin mismatch: tools={pin!r} gradle={_rive_android_pin()!r}")
    problems.extend(contract_surface_problems(json.loads(CONTRACT.read_text(encoding="utf-8"))))
    return problems

def m1():
    problems=m0(); manifest=load_yaml(); layer=find_artifact(manifest,kind="layer_svg")
    if not layer: problems.append("no admitted layer_svg")
    elif verify_records([layer]): problems.append("admitted layer_svg hash mismatch")
    review=((manifest.get("reviews") or {}).get("layer_svg") or {})
    if review.get("verdict")!="PASS": problems.append("layer SVG independent/owner review not PASS")
    return problems

def m2():
    problems=m1(); status=load_status(); core=status.get("core_rig") or {}; manifest=load_yaml()
    if core.get("emulator_validation")!="PASS": problems.append("core emulator validation not PASS")
    if core.get("owner_verdict")!="PASS": problems.append("core owner verdict not PASS")
    if not core.get("ci_run"): problems.append("core CI run missing")
    sha=core.get("candidate_sha256")
    if not sha or not find_artifact(manifest,kind="riv_candidate",sha256=sha): problems.append("core candidate not recorded")
    if sha and not any(r.get("command")=="rive receipt" and sha in (r.get("outputs") or []) for r in manifest.get("receipts") or []): problems.append("core packaging receipt missing")
    return problems

def m3():
    problems=m2(); status=load_status(); full=status.get("full_rig") or {}; manifest=load_yaml()
    if full.get("emulator_validation")!="PASS": problems.append("full emulator validation not PASS")
    if full.get("reviewed")!="PASS": problems.append("full independent review not PASS")
    if not full.get("ci_run"): problems.append("full CI run missing")
    sha=full.get("candidate_sha256")
    if not sha or not find_artifact(manifest,kind="riv_candidate",sha256=sha): problems.append("full candidate not recorded")
    return problems

def _device_complete(device):
    checks=device.get("checks") or {}
    return bool(checks) and all(v=="PASS" for v in checks.values()) and bool((device.get("device") or {}).get("rive_sha256"))

def m4():
    problems=m3()
    if not SOURCE_RIV.is_file() or not APP_RIV.is_file(): return problems+["integrated Rive asset missing"]
    source_sha=sha256_file(SOURCE_RIV); app_sha=sha256_file(APP_RIV)
    if source_sha!=app_sha: problems.append("source and shipped Rive bytes differ")
    device=_yaml(DEVICE)
    if not _device_complete(device): problems.append("S24 device checklist incomplete")
    elif (device.get("device") or {}).get("rive_sha256")!=source_sha: problems.append("device checklist Rive SHA differs")
    acceptance=_yaml(ACCEPTANCE).get("final")
    if not isinstance(acceptance,dict) or not acceptance.get("verified"): problems.append("verified final owner acceptance missing")
    elif acceptance.get("subject")!=f"sha256:{source_sha}": problems.append("owner acceptance subject differs from integrated asset")
    return problems

def m5():
    problems=m4(); status=load_status()
    if not RELEASE_MANIFEST.is_file(): problems.append("release manifest missing")
    else:
        release=json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))
        if APP_RIV.is_file() and release.get("rive_sha256")!=sha256_file(APP_RIV): problems.append("release manifest Rive SHA differs")
    if status.get("qual_emb_01")!="READY": problems.append("QUAL-EMB-01 not READY")
    return problems

GATES={"m0":m0,"m1":m1,"m2":m2,"m3":m3,"m4":m4,"m5":m5}
def evaluate(name:str)->GateResult:
    if name not in GATES: raise ValueError(f"unknown gate {name}")
    reasons=tuple(dict.fromkeys(GATES[name]()))
    return GateResult(name,not reasons,reasons)
