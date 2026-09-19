from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

from van_gateway.storage.db import Store


#: Chain anchor for the first audit row.
GENESIS_HASH = "0" * 64


class AuditService:
    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def _normalize_evidence(value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Preserve established audit keys while retaining richer Rev 3.1 evidence.

        Rev 3.1 records Project Truth as a nested object so provenance stays
        explicit. Older acceptance/evidence consumers already depend on the
        top-level ``truth_sha``/``repo_sha`` fields, so the audit boundary keeps
        both representations rather than forcing callers to fork the schema.
        """
        if value is None:
            return None
        normalized = dict(value)
        project_truth = normalized.get("project_truth")
        if isinstance(project_truth, dict):
            if "truth_sha" in project_truth:
                normalized.setdefault("truth_sha", project_truth.get("truth_sha"))
            if "repo_sha" in project_truth:
                normalized.setdefault("repo_sha", project_truth.get("repo_sha"))
        return normalized

    async def record(
        self,
        *,
        result: str,
        command_id: str | None = None,
        device_id: str | None = None,
        project_id: str | None = None,
        capability: str | None = None,
        approval: str | None = None,
        model_delegate: str | None = None,
        tool: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        failure_reason: str | None = None,
        evidence_pointer: str | None = None,
    ) -> str:
        audit_id = str(uuid.uuid4())
        normalized_before = self._normalize_evidence(before)
        normalized_after = self._normalize_evidence(after)
        created = int(time.time())
        before_json = Store.dumps(normalized_before) if normalized_before is not None else None
        after_json = Store.dumps(normalized_after) if normalized_after is not None else None

        # P1-SEC-006: the owner-authority audit log was a flat table with a random UUID,
        # no ordering and no linkage, so rows could be inserted, altered or deleted
        # undetectably. The VATI trading ledger already had a verifiable chain. Sequence
        # allocation and hashing happen inside one immediate transaction so concurrent
        # writers cannot fork the chain.
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                cur = await db.execute(
                    "SELECT chain_seq, entry_hash FROM audit "
                    "WHERE chain_seq IS NOT NULL ORDER BY chain_seq DESC LIMIT 1"
                )
                tip = await cur.fetchone()
                seq = (int(tip["chain_seq"]) + 1) if tip else 1
                prev_hash = str(tip["entry_hash"]) if tip else GENESIS_HASH
                entry_hash = self.entry_digest(
                    seq=seq,
                    prev_hash=prev_hash,
                    audit_id=audit_id,
                    command_id=command_id,
                    device_id=device_id,
                    result=result,
                    failure_reason=failure_reason,
                    before_json=before_json,
                    after_json=after_json,
                    created_at_unix=created,
                )
                await db.execute(
                    """
                    INSERT INTO audit(
                      id, command_id, device_id, project_id, capability, approval, model_delegate, tool,
                      before_json, after_json, result, failure_reason, evidence_pointer, created_at_unix,
                      chain_seq, prev_hash, entry_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        audit_id, command_id, device_id, project_id, capability, approval,
                        model_delegate, tool, before_json, after_json, result, failure_reason,
                        evidence_pointer, created, seq, prev_hash, entry_hash,
                    ),
                )
            except BaseException:
                await db.rollback()
                raise
            await db.commit()
        return audit_id

    @staticmethod
    def entry_digest(
        *,
        seq: int,
        prev_hash: str,
        audit_id: str,
        command_id: str | None,
        device_id: str | None,
        result: str,
        failure_reason: str | None,
        before_json: str | None,
        after_json: str | None,
        created_at_unix: int,
    ) -> str:
        """Hash covering the fields that make an audit row meaningful.

        Deliberately includes `prev_hash`, so altering any earlier row invalidates every
        row after it rather than only its own.
        """
        payload = "|".join(
            [
                str(seq), prev_hash, audit_id, command_id or "", device_id or "",
                result, failure_reason or "", before_json or "", after_json or "",
                str(created_at_unix),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def chain_anchor(self) -> dict[str, Any] | None:
        """The latest retention anchor, if the log has ever been prefix-pruned.

        P3-OPS-001: the audit table could not have a retention policy while
        `verify_chain` insisted the surviving chain started at sequence 1 from the
        genesis hash. The anchor records where a prune stopped, so the remaining
        rows stay verifiable and the prune itself stays visible.
        """
        rows = await self.store.fetchall(
            "SELECT anchor_seq, anchor_hash, pruned_rows, created_at_unix "
            "FROM audit_chain_anchors ORDER BY anchor_seq DESC LIMIT 1"
        )
        return dict(rows[0]) if rows else None

    async def verify_chain(self) -> dict[str, Any]:
        """Recompute the chain and report the first row that does not reconcile.

        Returns ``{"ok": bool, "checked": int, "broken_at": int | None, "reason": str | None}``.
        """
        rows = await self.store.fetchall(
            "SELECT id, command_id, device_id, result, failure_reason, before_json, after_json, "
            "created_at_unix, chain_seq, prev_hash, entry_hash FROM audit "
            "WHERE chain_seq IS NOT NULL ORDER BY chain_seq ASC"
        )
        anchor = await self.chain_anchor()
        expected_prev = str(anchor["anchor_hash"]) if anchor else GENESIS_HASH
        expected_seq = (int(anchor["anchor_seq"]) + 1) if anchor else 1
        first_seq = expected_seq
        for row in rows:
            seq = int(row["chain_seq"])
            if seq != expected_seq:
                return {"ok": False, "checked": expected_seq - first_seq, "broken_at": seq,
                        "reason": f"sequence gap: expected {expected_seq}, found {seq}"}
            if str(row["prev_hash"]) != expected_prev:
                return {"ok": False, "checked": expected_seq - first_seq, "broken_at": seq,
                        "reason": "prev_hash does not match the previous entry"}
            recomputed = self.entry_digest(
                seq=seq,
                prev_hash=str(row["prev_hash"]),
                audit_id=str(row["id"]),
                command_id=row["command_id"],
                device_id=row["device_id"],
                result=str(row["result"]),
                failure_reason=row["failure_reason"],
                before_json=row["before_json"],
                after_json=row["after_json"],
                created_at_unix=int(row["created_at_unix"]),
            )
            if recomputed != str(row["entry_hash"]):
                return {"ok": False, "checked": expected_seq - first_seq, "broken_at": seq,
                        "reason": "entry contents do not match its recorded hash"}
            expected_prev = str(row["entry_hash"])
            expected_seq += 1
        return {
            "ok": True,
            "checked": expected_seq - first_seq,
            "broken_at": None,
            "reason": None,
            "anchor_seq": int(anchor["anchor_seq"]) if anchor else None,
            "pruned_rows": int(anchor["pruned_rows"]) if anchor else 0,
        }
