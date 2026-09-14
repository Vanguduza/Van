#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from van_gateway.config import Settings
from van_gateway.google.mesh import GoogleCapabilityRegistry, GoogleIdentityBroker
from van_gateway.storage.db import Store


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    store = Store(args.database_path or settings.database_path)
    await store.migrate()
    registry = GoogleCapabilityRegistry(str(REPO_ROOT / "registries" / "google_capabilities.json"))
    broker = GoogleIdentityBroker(
        store,
        registry,
        ai_plan=settings.google_ai_plan,
        cloud_project_id=settings.google_cloud_project_id,
        gemini_runtime_configured=settings.google_gemini_runtime_configured,
        cloud_runtime_configured=settings.google_cloud_runtime_configured,
        consumer_connected_capabilities=settings.google_consumer_connected_capabilities,
    )
    mesh = await broker.mesh_status()
    print(json.dumps(mesh, indent=2, default=str))

    if not mesh["principal"]["registered"]:
        print("FAIL: canonical Google principal is not registered.", file=sys.stderr)
        return 2

    by_id = {item["capability_id"]: item for item in mesh["capabilities"]}
    failed = []
    for capability_id in args.require_ready:
        item = by_id.get(capability_id)
        if item is None or item["state"] != "READY":
            failed.append(capability_id)
    for capability_id in args.require_usable:
        item = by_id.get(capability_id)
        if item is None or item["state"] not in {"READY", "CONFIGURED"}:
            failed.append(capability_id)

    if failed:
        print("FAIL: capability gates not met: " + ", ".join(sorted(set(failed))), file=sys.stderr)
        return 3
    print("PASS: requested Google mesh certification gates satisfied.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail-closed certification check for VAN Google Intelligence Mesh.")
    parser.add_argument("--database-path")
    parser.add_argument("--require-ready", action="append", default=[], help="Capability that must have live READY evidence.")
    parser.add_argument("--require-usable", action="append", default=[], help="Capability that may be READY or CONFIGURED.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
