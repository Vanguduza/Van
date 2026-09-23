"""Binds a CI instrumentation run's *outcome* to the exact Rive bytes it validated.

`van-ci.yml` hashes the staged candidate / production asset before the emulator runs. That
proves which bytes were checked out, not what `RiveContractTest` concluded about them. This
module reads the JUnit XML the connected-test task wrote and emits `van_validation.json`:
mode, SHAs, run identity and a per-test outcome, with a single machine-derived `result`.
`cli rive record-validation` refuses a PASS this file does not itself state.

Standard library only: it runs on the bare instrumentation runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SCHEMA_VERSION = 1
TEST_CLASS = "com.dial.van.instrumentation.RiveContractTest"
ALL_TESTS = (
    "contractSurfaceMatches",
    "coreInputsDriveTheRig",
    "everyStateAndActionRenders",
    "mandatoryCombinations",
    "invalidInputsDegradeSafely",
    "artboardIsTransparentOnThreeBackgrounds",
    "identityColourFamilies",
    "idleSoakFrameStats",
    "brokenAssetFallsBack",
)
# RiveContractTest assumes these away in core mode (`FULL_OR_PRODUCTION_ONLY`); any other skip
# with an asset present means a case silently did not run.
CORE_ONLY_SKIPS = frozenset({"everyStateAndActionRenders", "mandatoryCombinations", "idleSoakFrameStats"})
CANDIDATE = Path("android/app/src/androidTest/assets/van_candidate.riv")
FORGE_MODE = Path("android/app/src/androidTest/assets/forge_mode.txt")
PRODUCTION = Path("android/app/src/main/assets/van.riv")


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def detect_mode(root: Path) -> str:
    """Mirrors RiveContractTest.rigOrSkip(): a staged candidate wins over the production asset."""
    if (root / CANDIDATE).is_file():
        text = (root / FORGE_MODE).read_text(encoding="utf-8").strip() if (root / FORGE_MODE).is_file() else "core"
        return "full" if text == "full" else "core"
    if (root / PRODUCTION).is_file():
        return "production"
    return "NO_RIVE_ASSET"


def read_outcomes(results_dir: Path) -> dict[str, str]:
    """Per-test outcome (`passed|failed|error|skipped`) for RiveContractTest across every JUnit
    file. A test reported more than once keeps its worst outcome."""
    rank = {"passed": 0, "skipped": 1, "failed": 2, "error": 3}
    outcomes: dict[str, str] = {}
    for xml in sorted(results_dir.rglob("*.xml")) if results_dir.is_dir() else []:
        try:
            root = ET.parse(xml).getroot()
        except ET.ParseError:
            continue
        for case in root.iter("testcase"):
            if case.attrib.get("classname") != TEST_CLASS:
                continue
            name = case.attrib.get("name", "")
            children = {child.tag for child in case}
            outcome = "error" if "error" in children else "failed" if "failure" in children else "skipped" if "skipped" in children else "passed"
            if rank[outcome] >= rank[outcomes.get(name, "passed")] or name not in outcomes:
                outcomes[name] = outcome
    return outcomes


def evaluate(mode: str, outcomes: dict[str, str]) -> tuple[str, list[str]]:
    if mode == "NO_RIVE_ASSET":
        return "NO_RIVE_ASSET", []
    if not outcomes:
        return "NOT_RUN", ["no RiveContractTest results were produced"]
    reasons = []
    for name in ALL_TESTS:
        outcome = outcomes.get(name)
        if outcome is None:
            reasons.append(f"{name}: missing from results")
        elif outcome in {"failed", "error"}:
            reasons.append(f"{name}: {outcome}")
        elif outcome == "skipped" and not (mode == "core" and name in CORE_ONLY_SKIPS):
            reasons.append(f"{name}: skipped with a {mode} asset present")
    return ("FAIL" if reasons else "PASS"), reasons


def summarise(root: Path, results_dir: Path, env: dict[str, str]) -> dict:
    mode = detect_mode(root)
    outcomes = read_outcomes(results_dir)
    result, reasons = evaluate(mode, outcomes)
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "candidate_sha256": _sha256(root / CANDIDATE),
        "production_sha256": _sha256(root / PRODUCTION),
        "github": {
            "repository": env.get("GITHUB_REPOSITORY", ""),
            "run_id": env.get("GITHUB_RUN_ID", ""),
            "run_attempt": env.get("GITHUB_RUN_ATTEMPT", ""),
            "sha": env.get("GITHUB_SHA", ""),
        },
        "tests": {name: outcomes.get(name, "missing") for name in ALL_TESTS},
        "result": result,
        "reasons": reasons,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="character-forge-ci-binding")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("summarise", help="write van_validation.json from JUnit results")
    p.add_argument("--results", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("gate", help="fail when an asset is present and its validation is not PASS")
    p.add_argument("--binding", required=True)
    args = parser.parse_args(argv)
    if args.command == "summarise":
        summary = summarise(Path.cwd(), Path(args.results), dict(os.environ))
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"mode": summary["mode"], "result": summary["result"], "reasons": summary["reasons"]}))
        return 0
    path = Path(args.binding)
    if not path.is_file():
        # No binding at all (the instrumentation runner died before uploading). Only a tree with
        # no Rive asset may pass without one; with an asset present, silence is not a PASS.
        if detect_mode(Path.cwd()) == "NO_RIVE_ASSET":
            print("character-forge gate: NO_RIVE_ASSET and no binding uploaded; nothing to validate")
            return 0
        print(f"character-forge gate: Rive asset present but validation binding missing: {path}", file=sys.stderr)
        return 1
    summary = json.loads(path.read_text(encoding="utf-8"))
    if summary.get("mode") == "NO_RIVE_ASSET":
        print("character-forge gate: NO_RIVE_ASSET (nothing staged or shipped; nothing to validate)")
        return 0
    if summary.get("result") != "PASS":
        print(f"character-forge gate: {summary.get('mode')} asset present but validation is {summary.get('result')}", file=sys.stderr)
        for reason in summary.get("reasons") or []:
            print(f"- {reason}", file=sys.stderr)
        return 1
    print(f"character-forge gate: {summary['mode']} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
