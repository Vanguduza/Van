from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, subprocess, sys, xml.etree.ElementTree as ET

ROOT = Path("/workspace/Van")
OUT = ROOT / "docs/audit/validation"
FREEZE = OUT / "van-production-source-freeze-2026-10-08.json"
ANDROID = OUT / "android-owner-controls-final-receipt-2026-10-08-r2.json"
EXTERNAL = Path("/workspace/dial-development-system/agent-system/orchestration/android-testing-mcp.mjs")
STEM = sys.argv[1]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def snapshot(frozen):
    paths = set(frozen)
    roots = ["tests", "backend/tests", "services", "trading/tests", "trading/tests_canonical",
             "android/verification/src/test", "android/app/src/test", "registries", "tools/audit", "tools/certification",
             "docs/audit/van-whole-project-2026-09-21", "docs/audit/van-fable-whole-project-2026-09-21"]
    ignored = {"build", ".gradle", "__pycache__", ".pytest_cache", ".git", "artifacts", "receipts", "generated"}
    extensions = {".py", ".kt", ".java", ".json", ".mjs", ".js", ".yaml", ".yml", ".toml", ".sql", ".md", ".xml", ".sh", ".kts"}
    for base in roots:
        for path in (ROOT / base).rglob("*"):
            if path.is_file() and path.suffix in extensions and not (set(path.parts) & ignored):
                paths.add(path.relative_to(ROOT).as_posix())
    for path in (ROOT / "docs").rglob("*"):
        if path.is_file() and path.suffix in extensions and "audit" not in path.parts and not (set(path.parts) & ignored):
            paths.add(path.relative_to(ROOT).as_posix())
    paths.update([str(FREEZE.relative_to(ROOT)), str(ANDROID.relative_to(ROOT)),
        "docs/audit/VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-08.json",
        "docs/audit/VAN_ARTEMIS_ACCEPTANCE_PLAN_2026-10-08.json", "docs/audit/OWNER_FRONTEND_REGISTRY_GUIDE.md",
        "docs/audit/OWNER_FRONTEND_CONTRACT.html"])
    return {p: digest(ROOT / p) for p in sorted(paths)}

freeze_sha = digest(FREEZE)
frozen = json.loads(FREEZE.read_text())["files"]
changed = [p for p,h in frozen.items() if not (ROOT/p).is_file() or digest(ROOT/p) != h]
assert not changed, changed
qualification = json.loads((ROOT/"registries/owner_features.json").read_text())["current_source_qualification"]
assert qualification["status"] == "SOURCE_REVIEWED_LOCAL_VALIDATION_PASSED", qualification
assert freeze_sha in json.dumps(qualification), qualification
assert digest(ANDROID) in json.dumps(qualification), qualification
before = {"schema_version":1, "created_at_utc":datetime.now(timezone.utc).isoformat(),
    "scope":"Current frozen production plus test/registry/endpoint-helper inputs and immutable final qualification; moving receipt outputs excluded.",
    "files":snapshot(frozen), "external_files":{str(EXTERNAL):digest(EXTERNAL)},
    "production_manifest_sha256":freeze_sha, "android_receipt_sha256":digest(ANDROID)}
before_path = OUT/(STEM+"-before.json")
before_path.write_text(json.dumps(before,indent=2)+"\n")
command = ["/workspace/.onboarding/van-venv/bin/python", "-m", "pytest", "tests/contracts", "-q", "--junitxml="+str(OUT/(STEM+".xml"))]
environment = dict(os.environ, PYTHONPATH="backend:trading:.")
started = datetime.now(timezone.utc).isoformat()
with (OUT/(STEM+".log")).open("w") as log:
    code = subprocess.call(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
after_files = snapshot(frozen)
changed = sorted(p for p in before["files"].keys() | after_files.keys() if before["files"].get(p) != after_files.get(p))
external_changed = digest(EXTERNAL) != before["external_files"][str(EXTERNAL)]
after = {"schema_version":1, "created_at_utc":datetime.now(timezone.utc).isoformat(),
    "files":after_files, "external_files":{str(EXTERNAL):digest(EXTERNAL)}, "changed":changed,
    "external_changed":external_changed}
after_path = OUT/(STEM+"-after.json")
after_path.write_text(json.dumps(after,indent=2)+"\n")
suites = list(ET.parse(OUT/(STEM+".xml")).getroot().iter("testsuite"))
counts = {k:sum(int(s.attrib.get(k,"0")) for s in suites) for k in ["tests","failures","errors","skipped"]}
receipt = {"schema_version":1, "suite":"contracts", "selection":["tests/contracts"], "command":command,
    "started_at_utc":started, "finished_at_utc":datetime.now(timezone.utc).isoformat(),
    "exit_code":code, "counts":counts, "passed":counts["tests"]-counts["failures"]-counts["errors"]-counts["skipped"],
    "qualification":"LOCAL_FROZEN_CONTRACTS_PASS" if code == 0 and not changed and not external_changed else "FAILED_OR_INPUTS_CHANGED",
    "source_unchanged_during_test":not changed and not external_changed, "changed_inputs":changed,
    "external_changed":external_changed, "input_files":len(before["files"]), "external_input_files":1,
    "production_manifest_sha256":freeze_sha, "android_receipt_sha256":before["android_receipt_sha256"],
    "before_snapshot":str(before_path.relative_to(ROOT)), "before_snapshot_sha256":digest(before_path),
    "after_snapshot":str(after_path.relative_to(ROOT)), "after_snapshot_sha256":digest(after_path),
    "log":str((OUT/(STEM+".log")).relative_to(ROOT)), "log_sha256":digest(OUT/(STEM+".log")),
    "junit":str((OUT/(STEM+".xml")).relative_to(ROOT)), "junit_sha256":digest(OUT/(STEM+".xml")),
    "physical_android_cases_executed":0, "deployment_accepted":False, "provider_live_effects_accepted":False}
(OUT/(STEM+"-result.json")).write_text(json.dumps(receipt,indent=2)+"\n")
print(json.dumps(receipt))
print("\n".join((OUT/(STEM+".log")).read_text().splitlines()[-15:]))
sys.exit(code or bool(changed) or external_changed)
