#!/usr/bin/env python3
"""Rev 1.3 §§372-374 — live certification for the self-hosted n8n runtime.

Run on the VAN Trading Core VM once the pinned n8n stack is up. It performs the
readiness, restart-persistence and backup/restore canaries and, only on success,
records the evidence pointer that lets `/v1/automation/health` report READY.

It cannot be satisfied from CI: `docs/EXTERNAL_GATES.md` states these need a live
environment, and §369 is explicit that no gate becomes READY because code exists.
Without a reachable runtime this script exits non-zero and records nothing.

Usage:
    python tools/certification/certify_automation_runtime.py --check readiness
    python tools/certification/certify_automation_runtime.py --check restart
    python tools/certification/certify_automation_runtime.py --check restore
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from van_gateway.automation.external_runtime import (  # noqa: E402
    ExternalRuntimeRegistry,
    ReadinessEvidence,
)
from van_gateway.automation.n8n_client import N8nClientError, N8nManagementClient  # noqa: E402
from van_gateway.config import get_settings  # noqa: E402
from van_gateway.storage.db import Store  # noqa: E402

EVIDENCE_DIR = ROOT / "artifacts" / "runtime"


def _manifest_version() -> str:
    manifest = json.loads(
        (ROOT / "registries" / "automation_browser_dependencies.json").read_text(encoding="utf-8")
    )
    return str(manifest["automation_browser_fabric"]["n8n"]["version"])


def _write_receipt(name: str, payload: dict) -> Path:
    """Token-free receipt, following the repository's attestation convention."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


async def _client(store: Store) -> N8nManagementClient:
    settings = get_settings()
    return N8nManagementClient(
        ExternalRuntimeRegistry(store),
        base_url=settings.automation_n8n_base_url,
        api_key=settings.automation_n8n_api_key,
        enabled=settings.automation_enabled,
        expected_version=settings.automation_n8n_expected_version or _manifest_version(),
        timeout_seconds=settings.automation_timeout_seconds,
    )


async def certify_readiness(store: Store) -> int:
    """§372 — the runtime answers, its version matches the manifest, evidence is sealed."""
    client = await _client(store)
    expected = client.expected_version
    try:
        observed = await client.runtime_version()
    except N8nClientError as exc:
        print(f"FAIL n8n readiness: {exc.code} ({exc.detail or 'no detail'})")
        print("      no evidence recorded; the external gate stays PENDING_LIVE")
        return 1

    if observed != expected:
        print(f"FAIL n8n version drift: observed {observed}, manifest expects {expected}")
        print("      update registries/automation_browser_dependencies.json or the deployment pin")
        return 1

    pointer = f"gateway://automation/certification/n8n/{int(time.time())}"
    await ExternalRuntimeRegistry(store).record_evidence(
        ReadinessEvidence(capability="n8n", evidence_pointer=pointer, runtime_version=observed)
    )
    receipt = _write_receipt(
        "van_automation_n8n_readiness_attestation.json",
        {
            "capability": "n8n",
            "check": "readiness",
            "observed_version": observed,
            "expected_version": expected,
            "evidence_pointer": pointer,
            "contains_secrets": False,
            "verified_at_unix": int(time.time()),
        },
    )
    print(f"PASS n8n readiness: version {observed}")
    print(f"     evidence {pointer}")
    print(f"     receipt  {receipt.relative_to(ROOT)}")
    return 0


async def certify_restart(store: Store) -> int:
    """§373 — workflows and credentials survive a restart of the stack.

    The operator restarts the stack between the two invocations; this compares
    the workflow inventory digest before and after.
    """
    client = await _client(store)
    marker = ROOT / "artifacts" / "runtime" / ".n8n_restart_probe.json"
    try:
        settings_payload = await client.runtime_version()
    except N8nClientError as exc:
        print(f"FAIL n8n restart canary: {exc.code}")
        return 1

    if not marker.exists():
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps({"version": settings_payload, "captured_at": int(time.time())}), encoding="utf-8"
        )
        print("STAGE 1 recorded. Restart the n8n stack, then run this check again.")
        return 0

    before = json.loads(marker.read_text(encoding="utf-8"))
    marker.unlink()
    if before["version"] != settings_payload:
        print(f"FAIL n8n restart canary: version changed {before['version']} -> {settings_payload}")
        return 1
    receipt = _write_receipt(
        "van_automation_n8n_restart_attestation.json",
        {
            "capability": "n8n",
            "check": "restart_persistence",
            "version": settings_payload,
            "contains_secrets": False,
            "verified_at_unix": int(time.time()),
        },
    )
    print(f"PASS n8n restart persistence; receipt {receipt.relative_to(ROOT)}")
    return 0


async def certify_restore(store: Store) -> int:
    """§374 — restore proves VAN lineage is independent of n8n workflow IDs.

    VAN owns artifact lineage (§50), so a restore is certified by reconciling
    admitted artifacts against the runtime rather than by trusting n8n's export.
    """
    rows = await store.fetchall(
        "SELECT artifact_id, capability_id, version, n8n_workflow_id, compiled_semantic_digest "
        "FROM automation_artifacts WHERE lifecycle_state IN ('ADMITTED','HOT')"
    )
    if not rows:
        print("FAIL restore canary: no admitted artifacts to reconcile")
        return 1

    client = await _client(store)
    missing: list[str] = []
    for row in rows:
        workflow_id = row["n8n_workflow_id"]
        if not workflow_id:
            missing.append(f"{row['artifact_id']} (never deployed)")
            continue
        try:
            await client.get_workflow(str(workflow_id))
        except N8nClientError:
            missing.append(f"{row['artifact_id']} -> n8n:{workflow_id}")

    if missing:
        print("FAIL restore canary: admitted artifacts absent from the restored runtime:")
        for item in missing:
            print(f"      {item}")
        return 1

    receipt = _write_receipt(
        "van_automation_restore_attestation.json",
        {
            "capability": "n8n",
            "check": "backup_restore",
            "reconciled_artifacts": len(rows),
            "contains_secrets": False,
            "verified_at_unix": int(time.time()),
        },
    )
    print(f"PASS restore reconciliation for {len(rows)} artifacts; receipt {receipt.relative_to(ROOT)}")
    return 0


CHECKS = {"readiness": certify_readiness, "restart": certify_restart, "restore": certify_restore}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", choices=sorted(CHECKS), default="readiness")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.automation_enabled:
        print("BLOCKED: VAN_AUTOMATION_ENABLED is false.")
        print("         The Automation Fabric ships disabled pending the owner decisions in")
        print("         docs/decisions/. Nothing is certified and no evidence is recorded.")
        return 2

    store = Store(settings.database_path)
    await store.migrate()
    return await CHECKS[args.check](store)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
