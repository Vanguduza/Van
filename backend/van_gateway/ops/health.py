"""The operational facts that are not metrics, in the shape the alert rules read.

Gate 11's exit criterion is that *"a production operator can determine what VAN
is doing, why it failed, recover it, restore its data and verify service health
without reading SQLite manually."* Metrics answer the first two. The rest —
is the scheduler alive, when did it last succeed, how long has the PKI got, is
there a backup and how old is it — are facts about the deployment, not counters,
and they are what this module collects.

`ops_facts()` returns a flat `{name: number}` mapping because that is exactly
what `alerts.Signals` consumes: a threshold rule should not have to know whether
its input came from a histogram or a certificate.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from van_gateway.ops import pki
from van_gateway.ops.backup import MANIFEST_NAME, read_manifest

#: A backup older than this is not a backup you would want to restore from.
BACKUP_MAX_AGE_SECONDS = 36 * 3600


def latest_backup(backup_root: str | Path | None) -> dict[str, Any]:
    """The newest verifiable backup under `backup_root`, or an honest absence.

    "No backup directory configured" and "backups are configured and stale" are
    reported differently. The first is a deployment that has not been finished;
    the second is one that is failing. Collapsing them would page for the wrong
    thing in both cases.
    """
    if backup_root is None:
        return {"configured": False, "present": False, "age_seconds": None,
                "created_at_unix": None, "path": None}
    root = Path(backup_root)
    if not root.is_dir():
        return {"configured": True, "present": False, "age_seconds": None,
                "created_at_unix": None, "path": str(root)}
    newest: tuple[int, Path] | None = None
    for candidate in root.iterdir():
        if not (candidate / MANIFEST_NAME).exists():
            continue
        try:
            manifest = read_manifest(candidate)
        except Exception:  # noqa: BLE001 - an unreadable manifest is simply not a backup
            continue
        if newest is None or manifest.created_at_unix > newest[0]:
            newest = (manifest.created_at_unix, candidate)
    if newest is None:
        return {"configured": True, "present": False, "age_seconds": None,
                "created_at_unix": None, "path": str(root)}
    created, path = newest
    return {
        "configured": True,
        "present": True,
        "created_at_unix": created,
        "age_seconds": max(int(time.time()) - created, 0),
        "path": str(path),
    }


async def collect(
    *,
    scheduler: Any | None = None,
    pki_dir: str | None = None,
    backup_root: str | None = None,
) -> dict[str, Any]:
    """Everything an operator needs that is not a counter."""
    return {
        "scheduler": (await scheduler.status()) if scheduler is not None else {"running": False},
        "pki": pki.scan(pki_dir) if pki_dir else {"present": False, "days_remaining": None},
        "backup": latest_backup(backup_root),
    }


def ops_facts(health: dict[str, Any]) -> dict[str, float]:
    """Flatten the parts the alert rules threshold on.

    A fact is omitted rather than defaulted when it is not knowable: a rule that
    reads a missing fact does not fire, which is the correct behaviour for a
    deployment that does not have that thing at all.
    """
    facts: dict[str, float] = {}
    days = health.get("pki", {}).get("days_remaining")
    if days is not None:
        facts["pki_days_remaining"] = float(days)
    backup = health.get("backup", {})
    if backup.get("configured"):
        age = backup.get("age_seconds")
        facts["backup_age_within_policy"] = float(
            1 if (age is not None and age <= BACKUP_MAX_AGE_SECONDS) else 0
        )
    return facts


__all__ = ["BACKUP_MAX_AGE_SECONDS", "collect", "latest_backup", "ops_facts"]
