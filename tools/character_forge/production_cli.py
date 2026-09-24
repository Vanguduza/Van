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
from .layer_map import map_layer_names
from .gpu_jobs import build_see_through_job, canonical_job_sha256, sha256_file as gpu_sha256_file


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


def cmd_layers_map(args) -> int:
    try:
        names=_json(Path(args.names))
        if not isinstance(names,list) or not all(isinstance(x,str) for x in names):
            raise ValueError("names file must contain a JSON array of strings")
        result=map_layer_names(names)
        output=Path(args.output)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(yaml.safe_dump(result,sort_keys=False),encoding="utf-8")
    except Exception as exc:
        print(f"refused: {exc}",file=sys.stderr)
        return 1
    print(output)
    return 0 if result.get("ok") else 1


def cmd_gpu_job(args) -> int:
    try:
        weight_hashes={}
        weight_lock_sha=None
        if args.weight_lock:
            lock_path=Path(args.weight_lock)
            lock=_yaml(lock_path)
            if args.mode!="trial" and lock.get("status")!="CLEARED":
                raise ValueError("production GPU job requires a CLEARED weight lock")
            models=lock.get("models") or []
            for row in models:
                name=str(row.get("name") or "").strip()
                digest=str(row.get("sha256") or "").strip()
                if name and digest:
                    weight_hashes[name]=digest
            weight_lock_sha=gpu_sha256_file(lock_path)
        job=build_see_through_job(
            source=Path(args.source),
            master_sha256=args.master_sha,
            code_commit=args.code_commit,
            mode=args.mode,
            resolution=args.resolution,
            weight_hashes=weight_hashes,
        )
        if weight_lock_sha:
            job["weight_lock_sha256"]=weight_lock_sha
        job["job_sha256"]=canonical_job_sha256(job)
        output=Path(args.output)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(job,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    except Exception as exc:
        print(f"refused: {exc}",file=sys.stderr)
        return 1
    print(output)
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

    layers = group.add_parser("layers").add_subparsers(dest="command", required=True)
    p = layers.add_parser("map")
    p.add_argument("--names", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_layers_map)

    gpu = group.add_parser("gpu").add_subparsers(dest="command", required=True)
    p = gpu.add_parser("job")
    p.add_argument("--source", required=True)
    p.add_argument("--master-sha", required=True)
    p.add_argument("--code-commit", default="7f139bb25c46a0c8ac720d95ddab185fcda5451c")
    p.add_argument("--mode", choices=["full_precision","group_offload","nf4_quantized","trial"], default="trial")
    p.add_argument("--resolution", type=int, default=1280)
    p.add_argument("--weight-lock")
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_gpu_job)

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
