"""Explicit privileged migration of a verified, unambiguous legacy chain.

Runtime startup never calls this. The native deployment operator supplies the
privileged connection after settling the affected baseline and migration. Hash
bodies, event IDs, sequence numbers and existing head values remain unchanged.
"""
from vati.core.ledger import GENESIS, LedgerError, _check_row
from vati.core.ledger_pg import require_scoped_schema


def migrate_legacy_scope(connection, *, apply=False):
    """Check, or atomically migrate, the canonical legacy vati.events layout.

    Equal/multiple populated heads, corrupt bodies, incomplete schemas and
    uncertain ownership refuse migration. No rows are assigned by account-name
    guesses. The caller must use a fresh connection, without an outer writer.
    """
    if type(apply) is not bool:
        raise ValueError("migration apply must be explicit")
    with connection.transaction():
        with connection.cursor() as cursor:
            if not apply:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
            cursor.execute("SELECT to_regclass('vati.events'), to_regclass('vati.chain_head')")
            tables = cursor.fetchone()
            if tables == (None, None):
                return {"status":"SCHEMA_ABSENT", "events":0, "changed":False}
            if None in tables:
                raise LedgerError("partial legacy ledger schema; native review required")
            if apply:
                # Same lock order as writers: chain head, then event rows.
                cursor.execute("LOCK TABLE vati.chain_head, vati.events IN ACCESS EXCLUSIVE MODE")
            cursor.execute("SELECT 1 FROM information_schema.columns WHERE table_schema = 'vati' AND table_name = 'events' AND column_name = 'ledger'")
            if cursor.fetchone() is not None:
                require_scoped_schema(cursor)
                return {"status":"ALREADY_SCOPED", "changed":False}
            cursor.execute("SELECT ledger, chain_hash, seq FROM vati.chain_head ORDER BY ledger")
            heads = cursor.fetchall()
            active = [row for row in heads if row[1] != GENESIS or row[2] != 0]
            cursor.execute("SELECT event_hash, prev_hash, chain_hash, payload_json, kind, producer, correlation_id, event_time_ms, received_time_ms, decision_time_ms, schema_version, seq FROM vati.events ORDER BY seq")
            rows = cursor.fetchall()
            if rows and len(active) != 1:
                raise LedgerError("legacy scope is ambiguous: expected exactly one populated head; native review required")
            if not rows and active:
                raise LedgerError("legacy chain head has no events; native review required")
            previous = GENESIS
            try:
                for row in rows:
                    if not _check_row(previous, row):
                        raise LedgerError("legacy hash chain is corrupt; native review required")
                    previous = row[2]
            except (KeyError, TypeError, ValueError) as exc:
                raise LedgerError("legacy event cannot be verified; native review required") from exc
            scope = active[0][0] if rows else None
            if rows and (active[0][1] != previous or active[0][2] != rows[-1][11]):
                raise LedgerError("legacy head does not match verified history; native review required")
            if scope is not None and (not isinstance(scope, str) or not scope.strip() or len(scope) > 128):
                raise LedgerError("legacy ledger scope identity is invalid")
            report = {"status":"READY" if not apply else "MIGRATED", "events":len(rows),
                "scope":scope, "verified_head":previous, "changed":apply}
            if not apply:
                return report
            cursor.execute("ALTER TABLE vati.events ADD COLUMN ledger TEXT")
            if rows:
                cursor.execute("UPDATE vati.events SET ledger = %s", (scope,))
            cursor.execute("ALTER TABLE vati.events ALTER COLUMN ledger SET NOT NULL")
            cursor.execute("ALTER TABLE vati.events DROP CONSTRAINT IF EXISTS events_chain_hash_key")
            cursor.execute("ALTER TABLE vati.events ADD CONSTRAINT events_ledger_chain_hash_key UNIQUE(ledger, chain_hash)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_vati_events_ledger_corr ON vati.events(ledger, correlation_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_vati_events_ledger_kind ON vati.events(ledger, kind)")
            require_scoped_schema(cursor)
            cursor.execute("SELECT event_hash, prev_hash, chain_hash, payload_json, kind, producer, correlation_id, event_time_ms, received_time_ms, decision_time_ms, schema_version, seq FROM vati.events ORDER BY seq")
            if cursor.fetchall() != rows:
                raise LedgerError("migration changed immutable event history")
            cursor.execute("SELECT ledger, chain_hash, seq FROM vati.chain_head ORDER BY ledger")
            if cursor.fetchall() != heads:
                raise LedgerError("migration changed original chain heads")
            return report
