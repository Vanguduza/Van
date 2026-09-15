#!/usr/bin/env python3
"""Import Hermes-hosted Google authentication evidence into the Van gateway mesh.

Fail closed:
- refuses READY claims without an explicit evidence pointer
- never writes raw Google subjects/tokens into the database (subject is hashed)
- does not invent Cloud/Enterprise capabilities omitted from the attestation
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from van_gateway.google.mesh import GoogleCapabilityRegistry, GoogleCapabilityState, GoogleIdentityBroker
from van_gateway.storage.db import Store

DEFAULT_ATTESTATION = ROOT / "artifacts" / "google" / "hermes_live_attestation.json"
ALLOWED_STATES = {
    GoogleCapabilityState.CONFIGURED,
    GoogleCapabilityState.CAPACITY_LIMITED,
    GoogleCapabilityState.RATE_LIMITED,
    GoogleCapabilityState.DEGRADED,
    GoogleCapabilityState.AUTH_REQUIRED,
    GoogleCapabilityState.UNAVAILABLE,
    GoogleCapabilityState.READY,
}


async def import_attestation(path: Path, database_path: str) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if int(raw.get("schema_version", 0)) < 1:
        raise SystemExit("attestation schema_version required")
    principal = raw.get("principal") or {}
    subject = str(principal.get("subject") or "").strip()
    if not subject:
        raise SystemExit("attestation principal.subject required")

    store = Store(database_path)
    await store.migrate()
    flags = raw.get("flags") or {}
    consumer = flags.get("consumer_connected_capabilities") or []
    if isinstance(consumer, str):
        consumer_csv = consumer
    else:
        consumer_csv = ",".join(str(x) for x in consumer)

    registry = GoogleCapabilityRegistry(str(ROOT / "registries" / "google_capabilities.json"))
    identity_alias = str(raw.get("identity_alias") or registry.default_identity)
    if identity_alias != registry.default_identity and identity_alias not in registry.delegated_identities:
        raise SystemExit(f"unknown identity_alias:{identity_alias}")
    broker = GoogleIdentityBroker(
        store,
        registry,
        ai_plan=str(principal.get("ai_plan") or "UNKNOWN"),
        cloud_project_id=str(flags.get("cloud_project_id") or ""),
        gemini_runtime_configured=bool(flags.get("gemini_runtime_configured")),
        cloud_runtime_configured=bool(flags.get("cloud_runtime_configured")),
        consumer_connected_capabilities=consumer_csv,
    )
    await broker.register_principal(
        subject=subject,
        owner_id=identity_alias,
        account_kind=str(principal.get("account_kind") or "personal"),
        ai_plan=str(principal.get("ai_plan") or "UNKNOWN"),
    )

    recorded: list[dict] = []
    for item in raw.get("capabilities") or []:
        capability_id = str(item["id"])
        descriptor = registry.get(capability_id)
        if descriptor.identity_alias != identity_alias:
            raise SystemExit(
                f"capability {capability_id} is bound to {descriptor.identity_alias}, not attestation identity {identity_alias}"
            )
        state = GoogleCapabilityState(str(item["state"]))
        if state not in ALLOWED_STATES:
            raise SystemExit(f"unsupported state for {capability_id}: {state}")
        evidence = str(item.get("evidence") or "").strip()
        if not evidence:
            raise SystemExit(f"evidence required for {capability_id}")
        if state == GoogleCapabilityState.READY and not evidence.startswith(("live://", "hermes://", "receipt://")):
            raise SystemExit(f"READY requires live/hermes/receipt evidence for {capability_id}")
        metadata = dict(item.get("metadata") or {})
        metadata.update(
            {
                "source": "import_hermes_google_attestation.py",
                "attestation_path": str(path.as_posix()),
                "host": raw.get("host"),
                "attested_at": raw.get("attested_at"),
            }
        )
        await broker.record_capability_evidence(
            capability_id,
            state=state,
            evidence_pointer=evidence,
            metadata=metadata,
            owner_id=identity_alias,
        )
        status = await broker.capability_status(capability_id, owner_id=identity_alias)
        recorded.append({"capability_id": capability_id, "state": status.state.value, "evidence": status.evidence_pointer})

    mesh = await broker.mesh_status(owner_id=identity_alias)
    return {
        "ok": True,
        "host": raw.get("host"),
        "identity_alias": identity_alias,
        "principal_registered": mesh["principal"]["registered"],
        "recorded": recorded,
        "excluded_until_cloud_setup": raw.get("excluded_until_cloud_setup") or [],
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Import Hermes Google auth attestation into Van mesh DB")
    parser.add_argument("--attestation", type=Path, default=DEFAULT_ATTESTATION)
    parser.add_argument(
        "--database-path",
        default=str(ROOT / "artifacts" / "google" / "van_gateway.sqlite3"),
    )
    args = parser.parse_args()
    if not args.attestation.exists():
        print(f"FAIL attestation_missing:{args.attestation}", file=sys.stderr)
        return 2
    Path(args.database_path).parent.mkdir(parents=True, exist_ok=True)
    result = await import_attestation(args.attestation, args.database_path)
    out = Path(args.database_path).with_suffix(".import.json")
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
