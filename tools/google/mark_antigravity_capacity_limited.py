#!/usr/bin/env python3
"""Record Antigravity CAPACITY_LIMITED evidence without pretending READY.

Does not mark Workspace/Gemini/Jules as failed. Scope is Antigravity-only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from van_gateway.config import get_settings
from van_gateway.google.mesh import GoogleCapabilityRegistry, GoogleCapabilityState, GoogleIdentityBroker
from van_gateway.storage.db import Store


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", default="live://antigravity/capacity_limited")
    parser.add_argument("--owner-subject", default="", help="optional hashed-principal registration subject")
    args = parser.parse_args()

    settings = get_settings()
    store = Store(settings.database_path)
    await store.migrate()
    registry = GoogleCapabilityRegistry(str(ROOT / "registries" / "google_capabilities.json"))
    broker = GoogleIdentityBroker(store, registry, consumer_connected_capabilities="antigravity,jules")
    if args.owner_subject:
        await broker.register_principal(subject=args.owner_subject)
    await broker.record_capability_evidence(
        "antigravity",
        state=GoogleCapabilityState.CAPACITY_LIMITED,
        evidence_pointer=args.evidence,
        metadata={
            "classification": "CAPACITY_LIMITED",
            "scope": "antigravity_only",
            "note": "Auth and model discovery OK; live generation blocked by provider quota",
            "fallback": "jules",
        },
    )
    status = await broker.capability_status("antigravity")
    print(json.dumps(status.model_dump(), indent=2))
    return 0 if status.state == GoogleCapabilityState.CAPACITY_LIMITED else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
