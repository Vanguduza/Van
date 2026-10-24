"""Same-host lease arbitration in the existing SQLite authority file.

This is for paper and non-sending runtimes. Real venue entry requires the
shared PostgreSQL store; a local file is never advertised as a cross-host fence.
"""
from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3

from vati.app.account_lease import AccountLease, LeaseStoreUnavailable
from vati.core.file_lock import exclusive_state_lock


class SQLiteLeaseStore:
    def __init__(self, path):
        if str(path) == ':memory:':
            raise LeaseStoreUnavailable('runtime lease needs a persistent authority file')
        self.path = Path(path).resolve()
        self.closed = False
        try:
            with self._connect() as db:
                db.execute('''CREATE TABLE IF NOT EXISTS account_runtime_leases (
                    account_alias TEXT PRIMARY KEY, holder_instance_id TEXT NOT NULL,
                    lease_epoch INTEGER NOT NULL, acquired_at_ms INTEGER NOT NULL,
                    heartbeat_at_ms INTEGER NOT NULL, expires_at_ms INTEGER NOT NULL,
                    software_version TEXT NOT NULL, git_sha TEXT NOT NULL)''')
        except sqlite3.Error:
            raise LeaseStoreUnavailable('local runtime authority store is unavailable') from None

    @contextmanager
    def _connect(self):
        if self.closed:
            raise LeaseStoreUnavailable('local runtime authority store is closed')
        db = sqlite3.connect(str(self.path), timeout=5, isolation_level=None)
        try:
            yield db
        finally:
            db.close()

    def _guard_path(self, alias):
        if not isinstance(alias, str) or not re.fullmatch(r'[a-z0-9_]{3,32}', alias):
            raise LeaseStoreUnavailable('invalid runtime account alias')
        return self.path.with_name(self.path.name+'.runtime-lease.'+alias)

    @staticmethod
    def _read(db, alias):
        row = db.execute('''SELECT account_alias, holder_instance_id, lease_epoch,
            acquired_at_ms, heartbeat_at_ms, expires_at_ms, software_version, git_sha
            FROM account_runtime_leases WHERE account_alias=?''', (alias,)).fetchone()
        if row is None:
            return None
        if row[0] != alias or not isinstance(row[1], str) or not row[1] or any(
            type(value) is not int or value < 0 for value in row[2:6]
        ) or row[2] < 1:
            raise LeaseStoreUnavailable('local runtime lease is malformed')
        return AccountLease(*row)

    def read(self, alias):
        try:
            with exclusive_state_lock(self._guard_path(alias)), self._connect() as db:
                return self._read(db, alias)
        except (sqlite3.Error, OSError):
            raise LeaseStoreUnavailable('local runtime lease cannot be read') from None

    def write_if(self, expected, new):
        try:
            with exclusive_state_lock(self._guard_path(new.account_alias)), self._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if self._read(db, new.account_alias) != expected:
                    db.rollback()
                    return False
                db.execute('''INSERT INTO account_runtime_leases VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(account_alias) DO UPDATE SET holder_instance_id=excluded.holder_instance_id,
                    lease_epoch=excluded.lease_epoch, acquired_at_ms=excluded.acquired_at_ms,
                    heartbeat_at_ms=excluded.heartbeat_at_ms, expires_at_ms=excluded.expires_at_ms,
                    software_version=excluded.software_version, git_sha=excluded.git_sha''',
                    (new.account_alias,new.holder_instance_id,new.lease_epoch,new.acquired_at_ms,
                     new.heartbeat_at_ms,new.expires_at_ms,new.software_version,new.git_sha))
                db.commit()
                return True
        except (sqlite3.Error, OSError):
            raise LeaseStoreUnavailable('local runtime lease cannot be written') from None

    @contextmanager
    def submission_guard(self, alias):
        # Every lease writer takes this same kernel fence. No SQLite write
        # transaction spans adapter I/O: the router must append to this ledger
        # during submission without deadlocking a second database connection.
        lock = exclusive_state_lock(self._guard_path(alias))
        try:
            lock.__enter__()
        except OSError:
            raise LeaseStoreUnavailable('local runtime submission authority is unavailable') from None
        try:
            try:
                with self._connect() as db:
                    current = self._read(db, alias)
            except (sqlite3.Error, OSError):
                raise LeaseStoreUnavailable('local runtime submission authority is unavailable') from None
            yield current
        finally:
            # Preserve a provider exception raised inside the guarded body.
            lock.__exit__(None, None, None)

    def close(self):
        self.closed = True
