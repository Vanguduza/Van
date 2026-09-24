from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import yaml

from .master import approve_master, stage_master
from .rig_ir import validate_rig_ir
from .spine_import import import_spine_json
from .rive_emit import write_rive_authoring_plan


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _yaml(path: Path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def cmd_master_stage(args) -> int:
    try:
        receipt = stage_master(Path(args.candidate), receipt_path=Path(args.receipt))
    except Exception as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(yaml.safe_dump(receipt, sort_keys=False), end="")
    return 0


def cmd_master_approve(args) -> int:
    try:
        result = approve_master(Path(args.candidate), Path(args.approval))
    except Exception as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(yaml.safe_dump(result, sort_keys=False), end="")
    return 0


def cmd_rig_validate(args) -> int:
    report = validate_rig_ir(_json(Path(args.input)))
    print(json.dumps({"ok": report.ok, "problems": list(report.problems)}, indent=2))
    return 0 if report.ok else 1


def cmd_spine_import(args) -> int:
    try:
        payload = _json(Path(args.input))
        provenance = _yaml(Path(args.provenance))
        part_provenance = provenance.get("parts") or {}
        rig = import_spine_json(
            payload,
            source_master_sha256=args.master_sha,
            part_provenance=part_provenance,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(rig, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


def cmd_rive_plan(args) -> int:
    try:
        rig = _json(Path(args.input))
        write_rive_authoring_plan(rig, Path(args.output))
    except Exception as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(args.output)
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="van-character-forge-v3")
    group = root.add_subparsers(dest="group", required=True)

    master = group.add_parser("master").add_subparsers(dest="command", required=True)
    p = master.add_parser("stage")
    p.add_argument("--candidate", required=True)
    p.add_argument("--receipt", required=True)
    p.set_defaults(func=cmd_master_stage)
    p = master.add_parser("approve")
    p.add_argument("--candidate", required=True)
    p.add_argument("--approval", required=True)
    p.set_defaults(func=cmd_master_approve)

    rig = group.add_parser("rig").add_subparsers(dest="command", required=True)
    p = rig.add_parser("validate")
    p.add_argument("--input", required=True)
    p.set_defaults(func=cmd_rig_validate)
    p = rig.add_parser("import-spine")
    p.add_argument("--input", required=True)
    p.add_argument("--provenance", required=True)
    p.add_argument("--master-sha", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_spine_import)
    p = rig.add_parser("rive-plan")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_rive_plan)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
