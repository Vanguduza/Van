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

def _packaging_receipt(sha):
    working=ROOT/"visual-authority"/"character-forge"/"09-rive-working"
    if not working.is_dir(): return None
    for path in working.glob("*.receipt.json"):
        try: row=json.loads(path.read_text(encoding="utf-8"))
        except Exception: continue
        if row.get("candidate_sha256")==sha: return row
    return None

def _receipt_problems(sha, stage, manifest, tools):
    row=_packaging_receipt(sha)
    if not row: return [f"{stage} packaging receipt file missing"]
    problems=[]
    layer=find_artifact(manifest,kind="layer_svg")
    if row.get("stage")!=stage: problems.append(f"{stage} receipt stage mismatch")
    if row.get("contract_sha256")!=sha256_file(CONTRACT): problems.append(f"{stage} receipt contract SHA stale")
    if not layer or row.get("svg_sha256")!=layer.get("sha256"): problems.append(f"{stage} receipt layer SHA stale")
    pin=str((((tools.get("critical_path") or {}).get("rive_cli") or {}).get("version")))
    if row.get("authoring_tool")!="rive_cli":
        problems.append(f"{stage} receipt authoring tool is not rive_cli")
    if row.get("authoring_version")!=pin:
        problems.append(f"{stage} receipt Rive CLI version mismatch")
    if not re.fullmatch(r"[0-9a-f]{64}",str(row.get("source_tree_sha256") or "")) or not str(row.get("source_project") or "").startswith("visual-authority/character-forge/09-rive-working/rml/"):
        problems.append(f"{stage} receipt does not bind an RML source project")
    candidate=ROOT/str(row.get("candidate_path") or "")
    if not candidate.is_file() or sha256_file(candidate)!=sha: problems.append(f"{stage} receipt candidate path/hash mismatch")
    return problems

def _rive_android_pin():
    if not GRADLE.is_file(): return None
    m=re.search(r'app\.rive:rive-android:([^"\)]+)',GRADLE.read_text(encoding="utf-8"))
    return m.group(1) if m else None

def m0():
    manifest=load_yaml(); status=load_status(); tools=_yaml(TOOLS); problems=validate_status(status)
    if not status.get("baseline_sha"): problems.append("baseline SHA missing")
    if not manifest.get("owner_confirmed_complete"):
        problems.append("owner source confirmation pending")
    elif not str(manifest.get("owner_confirmation_date") or "").strip():
        problems.append("owner source confirmation date missing")
    sources=manifest.get("sources") or []
    if not sources: problems.append("source set not admitted")
    problems.extend(verify_records(sources))
    pin=(((tools.get("critical_path") or {}).get("rive_android") or {}).get("version"))
    if pin!=_rive_android_pin(): problems.append(f"rive-android pin mismatch: tools={pin!r} gradle={_rive_android_pin()!r}")
    if manifest.get("baseline_sha") != status.get("baseline_sha"):
        problems.append("manifest/status baseline SHA mismatch")
    problems.extend(contract_surface_problems(json.loads(CONTRACT.read_text(encoding="utf-8"))))
    return problems

def m1():
    problems=m0(); manifest=load_yaml(); layer=find_artifact(manifest,kind="layer_svg")
    tools=_yaml(TOOLS)
    if str((((tools.get("critical_path") or {}).get("inkscape") or {}).get("version"))) in {"", "None", "UNPINNED"}:
        problems.append("Inkscape version unpinned")
    if not layer: problems.append("no admitted layer_svg")
    elif verify_records([layer]): problems.append("admitted layer_svg hash mismatch")
    review=((manifest.get("reviews") or {}).get("layer_svg") or {})
    if review.get("verdict")!="PASS":
        problems.append("layer SVG independent/owner review not PASS")
    elif layer and review.get("sha256")!=layer.get("sha256"):
        problems.append("layer SVG review is for a superseded SHA")
    return problems

def m2():
    problems=m1(); status=load_status(); core=status.get("core_rig") or {}; manifest=load_yaml()
    tools=_yaml(TOOLS)
    rive_cli=str((((tools.get("critical_path") or {}).get("rive_cli") or {}).get("version")))
    if rive_cli in {"", "None", "UNPINNED"}:
        problems.append("Rive CLI authoring version is not pinned")
    if core.get("emulator_validation")!="PASS": problems.append("core emulator validation not PASS")
    if core.get("owner_verdict")!="PASS": problems.append("core owner verdict not PASS")
    if not core.get("ci_run"): problems.append("core CI run missing")
    sha=core.get("candidate_sha256")
    if not sha or not find_artifact(manifest,kind="riv_candidate",sha256=sha): problems.append("core candidate not recorded")
    if sha:
        if not any(r.get("command")=="rive receipt" and sha in (r.get("outputs") or []) for r in manifest.get("receipts") or []): problems.append("core packaging receipt missing")
        problems.extend(_receipt_problems(sha,"core_rig",manifest,tools))
    baseline=ROOT/"visual-authority"/"character-forge"/"11-device-evidence"/"core_baseline"
    if core.get("emulator_validation")=="PASS" and not list(baseline.glob("*.png")):
        problems.append("core baseline evidence missing")
    return problems

def m3():
    problems=m2(); status=load_status(); full=status.get("full_rig") or {}; manifest=load_yaml(); tools=_yaml(TOOLS)
    if full.get("emulator_validation")!="PASS": problems.append("full emulator validation not PASS")
    if full.get("reviewed")!="PASS": problems.append("full independent review not PASS")
    if not full.get("ci_run"): problems.append("full CI run missing")
    sha=full.get("candidate_sha256")
    if not sha or not find_artifact(manifest,kind="riv_candidate",sha256=sha):
        problems.append("full candidate not recorded")
    else:
        problems.extend(_receipt_problems(sha,"full_rig",manifest,tools))
    review=((manifest.get("reviews") or {}).get("full_rig") or {})
    if sha and review.get("verdict")=="PASS" and review.get("sha256")!=sha:
        problems.append("full-rig review is for a superseded SHA")
    return problems

def _device_complete(device):
    checks=device.get("checks") or {}
    identity=device.get("device") or {}
    evidence=device.get("evidence") or {}
    required_identity=("model","android_build","apk_sha256","rive_sha256","checked_at")
    return (
        bool(checks)
        and all(v=="PASS" for v in checks.values())
        and all(str(identity.get(key) or "").strip() for key in required_identity)
        and isinstance(evidence,dict)
        and all(str(evidence.get(name) or "").strip() for name in checks)
    )

def m4():
    problems=m3(); status=load_status()
    production=status.get("production") or {}
    if production.get("emulator_validation")!="PASS": problems.append("production emulator validation not PASS")
    if not production.get("ci_run"): problems.append("production CI run missing")
    if not SOURCE_RIV.is_file() or not APP_RIV.is_file(): return problems+["integrated Rive asset missing"]
    source_sha=sha256_file(SOURCE_RIV); app_sha=sha256_file(APP_RIV)
    if production.get("rive_sha256")!=source_sha: problems.append("production validation SHA differs from integrated asset")
    if source_sha!=app_sha: problems.append("source and shipped Rive bytes differ")
    device=_yaml(DEVICE)
    if not _device_complete(device): problems.append("S24 device checklist incomplete")
    if not str(device.get("thermal_note") or "").strip(): problems.append("S24 thermal note missing")
    elif (device.get("device") or {}).get("rive_sha256")!=source_sha: problems.append("device checklist Rive SHA differs")
    acceptance=_yaml(ACCEPTANCE).get("final")
    if not isinstance(acceptance,dict) or not acceptance.get("verified"):
        problems.append("verified final owner acceptance missing")
    else:
        if acceptance.get("act") not in (None,"visual-accept"): problems.append("owner acceptance act is not visual-accept")
        if acceptance.get("subject")!=f"sha256:{source_sha}":
            problems.append("owner acceptance subject differs from integrated asset")
        checklist_identity=device.get("device") or {}
        if acceptance.get("apk_sha256") and acceptance.get("apk_sha256")!=checklist_identity.get("apk_sha256"):
            problems.append("owner acceptance APK SHA differs from S24 checklist")
        if acceptance.get("device_model") and acceptance.get("device_model")!=checklist_identity.get("model"):
            problems.append("owner acceptance device model differs from S24 checklist")
        if acceptance.get("android_build") and acceptance.get("android_build")!=checklist_identity.get("android_build"):
            problems.append("owner acceptance Android build differs from S24 checklist")
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
