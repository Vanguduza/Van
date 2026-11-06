The previously skipped PostgreSQL ledger test passed against actual PostgreSQL 17.11: **1 passed, 0 skipped, 0 failures**. It exercised chain parity with SQLite, filtered reads, invalid event rejection, a second connection extending the same chain, and stored-payload tampering detection using the current ledger source.

PostgreSQL server/client 17.11, libpq 17.11, and psycopg 3.2.6 were downloaded over HTTPS from Debian 13's archive. Package hashes were checked against its already signature-verified package index, then packages were extracted under `/workspace/.onboarding/browser-parser/postgres-root` with `dpkg-deb -x`. No package scripts, global installation, privileges, or shared database were used. Existing system libraries satisfied the native dependencies.

The fixture initialized a private temporary database as uid 1000, supplied the `vati` schema before testing the ledger, and bound only to a measured-free loopback port. `VATI_TEST_PG_DSN` selected only this fixture. A 15-second statement timeout bounded accidental hangs. Afterwards, `pg_ctl stop` succeeded, status returned 3 (no server running), and the temporary database was removed.

The JSON receipt contains exact setup/test/stop commands, binary and test-input hashes, package trust metadata, and JUnit outcomes. XML, pytest output, database log, archive signature transcript, and fixture source are retained beside it. To rerun using the verified packages in this prepared workspace:

```bash
python docs/audit/validation/postgres-ledger-real-fixture-2026-10-07-fixture.py
```

This proves the selected ledger behavior against a real isolated database. Production authentication, grants, networking, deployment, host readiness, and handset acceptance remain outside this fixture. Production source, registry hashes, and main qualification receipts were unchanged.
