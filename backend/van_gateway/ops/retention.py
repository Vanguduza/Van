"""A retention class for every table, and a prune that honours it.

P3-OPS-001: a repository-wide search for retention, prune, vacuum or purge found
exactly one setting in the whole system — n8n's own 168-hour execution
retention. Everything the gateway writes grew forever, in the same SQLite file
that serves live requests, on a phone-adjacent host.

The policy is expressed as a **class per table** rather than a number per table.
A list of seventy hand-chosen day counts is a list of seventy opinions nobody can
review; six classes with stated meanings can be argued about, and a new table
then has to be assigned to one. `test_retention.py` reads the live schema and
fails if any table is unassigned, so the policy cannot silently fall behind the
schema — which is how the one n8n setting ended up being the only one.

Two classes never delete, and say why rather than being omitted:

* `OWNER_STATE` is the owner's own record of their life and work. The system does
  not get to decide it has expired. Deletion of owner state is the owner's, via
  `context/forget.py`.
* `AUTHORITY_RECORD` is the hash-chained audit log. It is pruned, but only as a
  whole prefix and only with an anchor written first, so `verify_chain` still
  reconciles afterwards — see `prune_audit_prefix`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from van_gateway.storage.db import Store

DAY_MS = 86_400_000
DAY_S = 86_400


class RetentionClass(str, Enum):
    #: The owner's record of their own life and work. Only the owner deletes it.
    OWNER_STATE = "OWNER_STATE"
    #: The tamper-evident authority log. Prefix-pruned with an anchor, never edited.
    AUTHORITY_RECORD = "AUTHORITY_RECORD"
    #: What VAN relied on when it claimed something happened. Outlives the claim.
    EVIDENCE = "EVIDENCE"
    #: Numbers about how the system behaved. Useful in aggregate, not individually.
    TELEMETRY = "TELEMETRY"
    #: Single-use or short-lived: nonces, tickets, in-flight markers.
    EPHEMERAL = "EPHEMERAL"
    #: Rebuildable from a source of truth elsewhere.
    DERIVED = "DERIVED"
    #: Deleted when its parent row is deleted, never by age of its own.
    CHILD = "CHILD"


#: Days each class is kept. `None` means the class is never pruned by age.
RETENTION_DAYS: dict[RetentionClass, int | None] = {
    RetentionClass.OWNER_STATE: None,
    #: Two years. Long enough that any dispute about what VAN was authorised to do
    #: is still answerable; short enough that the chain does not grow without end.
    RetentionClass.AUTHORITY_RECORD: 730,
    RetentionClass.EVIDENCE: 365,
    RetentionClass.TELEMETRY: 90,
    RetentionClass.EPHEMERAL: 7,
    RetentionClass.DERIVED: 30,
    RetentionClass.CHILD: None,
}


class TimeUnit(str, Enum):
    MS = "ms"
    SECONDS = "s"


@dataclass(frozen=True)
class TablePolicy:
    table: str
    retention: RetentionClass
    #: The column that says how old a row is. Required for a pruned class.
    column: str | None = None
    unit: TimeUnit = TimeUnit.MS
    #: Why this table is in this class, when the answer is not obvious.
    note: str = ""
    #: For CHILD tables: the column that points at the parent, and the parent table.
    parent: tuple[str, str] | None = None


def _p(table, retention, column=None, unit=TimeUnit.MS, note="", parent=None):
    return TablePolicy(table=table, retention=retention, column=column, unit=unit,
                       note=note, parent=parent)


_OWNER = RetentionClass.OWNER_STATE
_EV = RetentionClass.EVIDENCE
_TEL = RetentionClass.TELEMETRY
_EPH = RetentionClass.EPHEMERAL
_DER = RetentionClass.DERIVED
_CHILD = RetentionClass.CHILD

POLICIES: tuple[TablePolicy, ...] = (
    # ---- the authority log -------------------------------------------------
    _p("audit", RetentionClass.AUTHORITY_RECORD, "created_at_unix", TimeUnit.SECONDS,
       "Hash-chained. Pruned only as an anchored prefix; see prune_audit_prefix."),

    # ---- the owner's own state ---------------------------------------------
    _p("devices", _OWNER, note="Revoking a device is the owner's act, not a timer's."),
    _p("missions", _OWNER, note="The durable record of what the owner asked for."),
    _p("reminders", _OWNER),
    _p("attention", _OWNER, note="A dismissed item is dismissed by the owner, not aged out."),
    _p("decisions", _OWNER),
    _p("owner_facts", _OWNER, note="Superseded revisions are the fact's history, not litter."),
    _p("owner_context_edges", _OWNER),
    _p("owner_cognitive_model", _OWNER),
    _p("shared_vocabulary", _OWNER),
    _p("strategic_memory", _OWNER),
    _p("symbiotic_growth", _OWNER),
    _p("cognitive_complement_map", _OWNER),
    _p("domain_trust", _OWNER, note="How much authority the owner has delegated, by domain."),
    _p("proactive_policies", _OWNER),
    _p("permission_grants", _OWNER, note="Expiry is enforced at use; the grant's history stays."),
    _p("capability_grants", _OWNER),
    _p("google_connections", _OWNER),
    _p("google_principal", _OWNER),
    _p("google_capability_connections", _OWNER),
    _p("browser_profiles", _OWNER, note="A logged-in profile is an owner credential."),
    _p("browser_scope_authorizations", _OWNER, note="What the owner let the browser touch."),
    _p("standing_automation_authorities", _OWNER),
    _p("automation_standing_intents", _OWNER),
    _p("intent_nodes", _OWNER),
    _p("intent_edges", _OWNER),
    _p("intent_missions", _OWNER),
    _p("schema_migrations", _OWNER, note="The database's own history. Deleting it loses the schema's provenance."),
    _p("runtime_meta", _OWNER),
    _p("project_truth_cache", _OWNER, note="Small, keyed by project; a stale row is replaced, not accumulated."),
    _p("action_definitions", _OWNER, note="The declared action catalogue, not a log."),
    _p("capability_registry", _OWNER, note="Declarations. Withdrawal is recorded, not deleted."),
    _p("sqlite_sequence", _OWNER, note="SQLite's own AUTOINCREMENT bookkeeping."),

    # ---- evidence -----------------------------------------------------------
    _p("action_executions", _EV, "updated_at_unix_ms"),
    _p("research_evidence", _EV, "retrieved_at_unix_ms"),
    _p("browser_evidence", _EV, "created_at_ms"),
    _p("reasoning_assessments", _EV, "created_at_ms"),
    _p("premise_assessments", _EV, "created_at_ms"),
    _p("assumption_ledger", _EV, "updated_at_ms"),
    _p("decision_fingerprints", _EV, "updated_at_ms"),
    _p("learning_outcomes", _EV, "recorded_at_ms"),
    _p("external_reality", _EV, "observed_at_ms"),
    _p("computer_operations", _EV, "started_at_ms"),
    _p("google_artifacts", _EV, "created_at_unix", TimeUnit.SECONDS),
    _p("automation_artifacts", _EV, "created_at_ms"),
    _p("automation_repairs", _EV, "created_at_ms"),
    _p("automation_dead_letter", _EV, "created_at_ms"),
    _p("browser_escalations", _EV, "created_at_ms"),
    _p("context_snapshots", _EV, "compiled_at_ms",
       note="What VAN knew when it acted. Prunes with the execution it justified."),

    # ---- telemetry ----------------------------------------------------------
    _p("automation_run_telemetry", _TEL, "recorded_at_ms"),
    _p("automation_generation_telemetry", _TEL, "recorded_at_ms"),
    _p("automation_workflow_health", _TEL, "updated_at_ms"),
    _p("automation_runs", _TEL, "updated_at_ms"),
    _p("browser_tasks", _TEL, "updated_at_ms"),
    _p("capability_route_decisions", _TEL, "decided_at_ms"),
    _p("benchmark_runs", _TEL, "created_at_ms"),
    _p("eval_runs", _TEL, "created_at_ms"),
    _p("execution_strategies", _TEL, "updated_at_ms"),
    _p("technology_capabilities", _TEL, "updated_at_ms"),
    _p("automation_capabilities", _TEL, "updated_at_ms"),
    _p("google_jobs", _TEL, "updated_at_unix", TimeUnit.SECONDS),
    _p("attention_candidates", _TEL, "created_at_ms"),
    _p("automation_external_events", _TEL, "received_at_ms"),

    # ---- ephemeral ----------------------------------------------------------
    _p("command_nonces", _EPH, "consumed_at_unix", TimeUnit.SECONDS,
       "Seven days is far longer than any command's replay window, so pruning "
       "can never make a replayed command look fresh."),
    _p("automation_run_nonces", _EPH, "issued_at_ms"),
    _p("pairing_tickets", _EPH, "created_at_unix", TimeUnit.SECONDS),
    _p("idempotency", _EPH, "updated_at_unix", TimeUnit.SECONDS,
       "Retained well past any client's retry horizon; an idempotency record that "
       "outlives its request is only holding a result nobody will ask for again."),

    # ---- derived ------------------------------------------------------------
    _p("events", _DER, "created_at_unix", TimeUnit.SECONDS,
       "Rebuildable from missions and audit; a device that has been offline for a "
       "month refetches state rather than replaying a month of events."),
    _p("event_cursors", _DER, "updated_at_unix", TimeUnit.SECONDS),

    # ---- operations' own records --------------------------------------------
    _p("audit_chain_anchors", _OWNER,
       note="Proof of how much audit log was pruned. Deleting it would hide the prune."),
    _p("notification_suppressions", _OWNER,
       note="A dismissal is the owner's decision; it expires by its own "
            "suppressed_until, not by a retention sweep."),
    _p("scheduler_runs", _TEL, "run_at_unix", TimeUnit.SECONDS),

    # ---- children -----------------------------------------------------------
    _p("mission_events", _CHILD, parent=("mission_id", "missions")),
    _p("mission_activities", _CHILD, parent=("mission_id", "missions")),
    _p("action_receipts", _CHILD, parent=("execution_id", "action_executions")),
)

BY_TABLE: dict[str, TablePolicy] = {policy.table: policy for policy in POLICIES}


class RetentionPolicyError(ValueError):
    pass


def _validate() -> None:
    for policy in POLICIES:
        days = RETENTION_DAYS[policy.retention]
        if days is not None and policy.retention is not RetentionClass.CHILD:
            if not policy.column:
                raise RetentionPolicyError(f"{policy.table} is pruned by age but names no column")
        if policy.retention is RetentionClass.CHILD and policy.parent is None:
            raise RetentionPolicyError(f"{policy.table} is a CHILD table but names no parent")


_validate()


@dataclass(frozen=True)
class PruneResult:
    table: str
    deleted: int
    cutoff: int
    retention: RetentionClass


class RetentionService:
    """Applies the policy. Reports what it deleted; never reports what it skipped as deleted."""

    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def cutoff_for(policy: TablePolicy, now_ms: int) -> int | None:
        days = RETENTION_DAYS[policy.retention]
        if days is None or policy.column is None:
            return None
        if policy.unit is TimeUnit.SECONDS:
            return int(now_ms / 1000) - days * DAY_S
        return now_ms - days * DAY_MS

    async def prune(self, *, now_ms: int | None = None,
                    tables: tuple[str, ...] | None = None) -> list[PruneResult]:
        """Delete everything past its class's horizon.

        Audit is excluded here and handled by `prune_audit_prefix`, because a
        `DELETE ... WHERE created_at_unix < ?` on a hash-chained table is exactly
        the operation that silently breaks the chain.
        """
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        results: list[PruneResult] = []
        selected = [
            p for p in POLICIES
            if (tables is None or p.table in tables)
            and p.retention not in (RetentionClass.AUTHORITY_RECORD, RetentionClass.CHILD)
        ]
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                for policy in selected:
                    cutoff = self.cutoff_for(policy, now_ms)
                    if cutoff is None:
                        continue
                    cursor = await db.execute(
                        f"DELETE FROM {policy.table} WHERE {policy.column} IS NOT NULL "
                        f"AND {policy.column} < ?",
                        (cutoff,),
                    )
                    results.append(PruneResult(
                        table=policy.table, deleted=int(cursor.rowcount or 0),
                        cutoff=cutoff, retention=policy.retention,
                    ))
                # CHILD rows go with their parents, in the same transaction, so a
                # prune can never leave an activity pointing at a mission that is gone.
                for policy in POLICIES:
                    if policy.retention is not RetentionClass.CHILD or policy.parent is None:
                        continue
                    if tables is not None and policy.table not in tables:
                        continue
                    column, parent = policy.parent
                    parent_key = BY_TABLE[parent]
                    cursor = await db.execute(
                        f"DELETE FROM {policy.table} WHERE {column} NOT IN "
                        f"(SELECT {_PRIMARY_KEY[parent]} FROM {parent})",
                    )
                    results.append(PruneResult(
                        table=policy.table, deleted=int(cursor.rowcount or 0),
                        cutoff=0, retention=parent_key.retention,
                    ))
            except BaseException:
                await db.rollback()
                raise
            await db.commit()
        return results

    async def prune_audit_prefix(self, *, now_ms: int | None = None) -> dict[str, Any]:
        """Prune the oldest audit rows, leaving an anchor the chain verifies from.

        A hash chain cannot be pruned in the middle and cannot be pruned from the
        end. It *can* be pruned from the start, provided the verifier is told
        where the remaining chain begins and what hash it must link back to. That
        is the anchor: one row recording the sequence number and entry hash of the
        last pruned entry. `verify_chain` starts from the anchor when one exists,
        so a pruned log is still tamper-evident for everything it still holds —
        and the anchor itself proves how much was pruned.
        """
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        policy = BY_TABLE["audit"]
        cutoff = self.cutoff_for(policy, now_ms)
        assert cutoff is not None  # AUTHORITY_RECORD has a horizon and a column
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                cursor = await db.execute(
                    "SELECT chain_seq, entry_hash FROM audit "
                    "WHERE chain_seq IS NOT NULL AND created_at_unix < ? "
                    "ORDER BY chain_seq DESC LIMIT 1",
                    (cutoff,),
                )
                tip = await cursor.fetchone()
                if tip is None:
                    await db.commit()
                    return {"pruned": 0, "anchor_seq": None, "cutoff": cutoff}
                anchor_seq = int(tip["chain_seq"])
                anchor_hash = str(tip["entry_hash"])
                deleted = await db.execute(
                    "DELETE FROM audit WHERE chain_seq IS NOT NULL AND chain_seq <= ?",
                    (anchor_seq,),
                )
                await db.execute(
                    "INSERT INTO audit_chain_anchors(anchor_seq, anchor_hash, pruned_rows, "
                    "created_at_unix) VALUES (?, ?, ?, ?)",
                    (anchor_seq, anchor_hash, int(deleted.rowcount or 0), int(now_ms / 1000)),
                )
            except BaseException:
                await db.rollback()
                raise
            await db.commit()
        return {"pruned": int(deleted.rowcount or 0), "anchor_seq": anchor_seq,
                "anchor_hash": anchor_hash, "cutoff": cutoff}


#: Primary keys for the CHILD orphan sweep. Listed rather than introspected so a
#: table renamed out from under this module fails loudly instead of matching nothing.
_PRIMARY_KEY = {
    "missions": "mission_id",
    "action_executions": "execution_id",
}


__all__ = [
    "BY_TABLE", "POLICIES", "RETENTION_DAYS", "PruneResult", "RetentionClass",
    "RetentionPolicyError", "RetentionService", "TablePolicy", "TimeUnit",
]
