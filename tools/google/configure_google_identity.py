#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from van_gateway.google.mesh import GoogleCapabilityRegistry, GoogleCapabilityState, GoogleIdentityBroker
from van_gateway.storage.db import Store


async def run(args: argparse.Namespace) -> int:
    db_path = args.database_path or os.getenv("VAN_DATABASE_PATH", "backend/data/van_gateway.sqlite3")
    store = Store(db_path)
    await store.migrate()
    registry = GoogleCapabilityRegistry(str(REPO_ROOT / "registries" / "google_capabilities.json"))
    broker = GoogleIdentityBroker(
        store,
        registry,
        ai_plan=args.ai_plan,
        cloud_project_id=args.cloud_project_id or os.getenv("VAN_GOOGLE_CLOUD_PROJECT_ID", ""),
        gemini_runtime_configured=args.gemini_runtime_configured,
        cloud_runtime_configured=args.cloud_runtime_configured,
        consumer_connected_capabilities=",".join(args.configured_capability),
    )
    principal = await broker.register_principal(subject=args.subject, owner_id=args.identity_alias, account_kind=args.account_kind, ai_plan=args.ai_plan)

    for capability_id in args.configured_capability:
        descriptor = registry.get(capability_id)
        if descriptor.identity_alias != args.identity_alias:
            raise SystemExit(f"capability {capability_id} is bound to {descriptor.identity_alias}, not {args.identity_alias}")
        await broker.record_capability_evidence(
            capability_id,
            state=GoogleCapabilityState.CONFIGURED,
            evidence_pointer=f"setup:configured:{capability_id}",
            metadata={"source": "configure_google_identity.py"},
            owner_id=args.identity_alias,
        )

    for pair in args.verified_capability:
        if "=" not in pair:
            raise SystemExit("--verified-capability must be capability_id=evidence_pointer")
        capability_id, evidence_pointer = pair.split("=", 1)
        if not evidence_pointer.startswith(("live://", "hermes://", "receipt://")):
            raise SystemExit(
                f"READY refused for {capability_id}: evidence must start with live://, hermes://, or receipt://"
            )
        descriptor = registry.get(capability_id)
        if descriptor.identity_alias != args.identity_alias:
            raise SystemExit(f"capability {capability_id} is bound to {descriptor.identity_alias}, not {args.identity_alias}")
        await broker.record_capability_evidence(
            capability_id,
            state=GoogleCapabilityState.READY,
            evidence_pointer=evidence_pointer,
            metadata={"source": "configure_google_identity.py", "verified": True},
            owner_id=args.identity_alias,
        )

    print(f"Google identity registered: alias={args.identity_alias}; status={principal.status}; plan={principal.ai_plan}")
    print("Raw Google subject was hashed and was not persisted.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register VAN's canonical owner Google principal and explicit capability evidence.")
    parser.add_argument("--subject", required=True, help="Google stable account subject identifier; stored only as SHA-256.")
    parser.add_argument("--identity-alias", default="owner_google_account", choices=["owner_google_account", "antigravity_worker_account"], help="Logical Google identity binding; raw email is not stored in the repository.")
    parser.add_argument("--account-kind", default="personal", choices=["personal", "workspace", "enterprise"])
    parser.add_argument("--ai-plan", default=os.getenv("VAN_GOOGLE_AI_PLAN", "UNKNOWN"))
    parser.add_argument("--database-path")
    parser.add_argument("--cloud-project-id", default="")
    parser.add_argument("--gemini-runtime-configured", action="store_true")
    parser.add_argument("--cloud-runtime-configured", action="store_true")
    parser.add_argument("--configured-capability", action="append", default=[], help="Capability signed into/configured but not live-certified. Repeatable.")
    parser.add_argument("--verified-capability", action="append", default=[], help="Live-certified capability in capability_id=evidence_pointer form. Repeatable.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
