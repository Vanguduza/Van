#!/usr/bin/env python3
"""Build the VAN Next predevelopment evidence pack (OD-31, V19-A08).

1. Refuses to run unless every input file is identical to the committed HEAD,
   so the pack is bound to one commit.
2. Runs every preparation check and records the command, exit code and full
   output as a receipt.
3. Writes EVIDENCE_MANIFEST.json with the SHA-256 of every input and receipt,
   and lists what is deliberately absent and why.
4. Writes a deterministic zip that keeps the docs/design/van-next layout, so
   the same commands can be rerun from the unzipped copy.

It does not issue or imply F15; that is an independent verifier's act (DU-31).
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # docs/design/van-next
RECEIPTS = HERE / "receipts"
MANIFEST = HERE / "EVIDENCE_MANIFEST.json"
ZIP = HERE / "VAN_NEXT_PREDEV_EVIDENCE_PACK_REV1_9A.zip"

INPUTS = [
    "VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_9A_20261016.md",
    "VAN_NEXT_OWNER_DECISIONS_REV1.md",
    "VAN_NEXT_BLUEPRINT_FREEZE_LIST_REV1_9A.md",
    "VAN_78_SURFACE_PRESERVATION_MATRIX_REV1_2_20261015.md",
    "VAN_78_SURFACE_PRESERVATION_MATRIX_REV1_2_20261015.csv",
    "VAN_78_SURFACE_PRESERVATION_MATRIX_REV1_2_20261015.json",
    "plan/generate_plan.py",
    "plan/VAN_NEXT_DEVELOPMENT_PLAN_REV1.md",
    "plan/VAN_NEXT_DEVELOPMENT_PLAN_REV1.json",
    "plan/PLAN_INPUT_PROVENANCE.json",
    "contracts/check_state_machines.py",
    "contracts/VAN_STATE_MACHINES_REV1_9.json",
    "contracts/STATE_MACHINES.json",
    "contracts/ACCOUNTS_FUNDS_TECHNICAL_CONTRACT.md",
    "contracts/FUNDING_INTENT.schema.json",
    "contracts/README.md",
    "crosswalk/README.md",
    "crosswalk/REV2_18_PRODUCT_TRUTH_CROSSWALK_REV1_9.csv",
    "crosswalk/REV2_93_FEATURE_CROSSWALK_REV1_9.csv",
    "crosswalk/REV2_171_ATOM_SEED_UNREVIEWED.csv",
    "research/VAN_NEXT_REV18_INDEPENDENT_AUDIT_RESPONSE_20261015.md",
    "research/VAN_NEXT_REV19_FOLLOWUP_AUDIT_RESPONSE_20261016.md",
]

CHECKS = [
    ("plan_check", ["plan/generate_plan.py", "--check"]),
    ("plan_selftest", ["plan/generate_plan.py", "--selftest"]),
    ("state_machines_check", ["contracts/check_state_machines.py"]),
    ("state_machines_on_pack_original", ["contracts/check_state_machines.py", "contracts/STATE_MACHINES.json"]),
    ("state_machines_selftest", ["contracts/check_state_machines.py", "--selftest"]),
]

ABSENT_BY_DESIGN = {
    "signed VAN_NEXT_OWNER_DECISIONS_REV1.md": "Owner signature pending (OQ-05, B3). The included record is unsigned.",
    "Feature Ledger (VAN_NEXT_FUNCTIONAL_PRESERVATION_LEDGER_REV1.csv)": "Produced by PKT-001 (DU-00a).",
    "171-atom / 115-context admitted mapping": "Produced by PKT-002 (DU-01); only the unreviewed seed is included.",
    "RESEARCH_INPUT_ACCEPTANCE.json (39 REA records)": "Produced by PKT-002 (DU-01), VAN-NX-026.",
    "F15 certificate and independent verifier receipts": "Issued only by an independent verifier at PKT-003 (DU-31). NOT_ISSUED.",
    "Runtime, device and provider receipts": "Post-implementation artifact states (§17.1); none exist before development.",
}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def main() -> int:
    # git pathspecs are relative to the working directory (ROOT), so pass INPUTS as they are.
    dirty = git("status", "--porcelain", "--untracked-files=all", "--", *INPUTS)
    if dirty:
        print("REFUSED: inputs differ from the committed HEAD:\n" + dirty)
        return 2
    for p in INPUTS:
        if not (ROOT / p).is_file():
            print(f"REFUSED: missing input {p}")
            return 2
    commit = git("rev-parse", "HEAD")
    RECEIPTS.mkdir(exist_ok=True)
    receipts = {}
    for name, args in CHECKS:
        r = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)
        body = f"$ cd docs/design/van-next && python3 {' '.join(args)}\nexit={r.returncode}\n\n{r.stdout}{r.stderr}"
        out = RECEIPTS / f"{name}.txt"
        out.write_text(body)
        receipts[name] = {"command": f"python3 {' '.join(args)}", "exit": r.returncode,
                          "receipt": f"evidence/receipts/{name}.txt", "sha256": sha(out)}
    expected = {"plan_check": 0, "plan_selftest": 0, "state_machines_check": 0,
                "state_machines_on_pack_original": 1, "state_machines_selftest": 0}
    mismatched = {k: v["exit"] for k, v in receipts.items() if v["exit"] != expected[k]}
    manifest = {
        "schema": "van-next-predev-evidence/1.0",
        "status": "PREPARATION_EVIDENCE_ONLY",
        "f15_forensic_build_ready": "NOT_ISSUED",
        "source_repository": "Vanguduza/Van",
        "source_commit": commit,
        "source_root": "docs/design/van-next",
        "python": platform.python_version(),
        "builder_sha256": sha(Path(__file__)),
        "inputs": {p: sha(ROOT / p) for p in INPUTS},
        "receipts": receipts,
        "expected_exit_codes": expected,
        "all_exit_codes_as_expected": not mismatched,
        "absent_by_design": ABSENT_BY_DESIGN,
        "rerun": "Unzip, cd into the unzipped root, then run each receipt's command; outputs must match the receipts.",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n")
    files = sorted(set(INPUTS) | {"evidence/build_evidence_pack.py", "evidence/EVIDENCE_MANIFEST.json"}
                   | {f"evidence/receipts/{n}.txt" for n, _ in CHECKS})
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            info = zipfile.ZipInfo(f, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, (ROOT / f).read_bytes())
    print(f"commit {commit[:12]}; {len(INPUTS)} inputs; receipts {list(receipts)}; "
          f"exit codes as expected: {not mismatched}; zip sha256 {sha(ZIP)}")
    return 0 if not mismatched else 1


if __name__ == "__main__":
    sys.exit(main())
