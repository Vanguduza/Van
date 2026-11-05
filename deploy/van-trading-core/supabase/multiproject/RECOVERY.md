# Project logical backup and recovery — one existing Supabase installation

## Implemented boundary

`tools/recovery.py` captures one project database into a private PostgreSQL custom archive, verifies its integrity, and generates a **fresh-database restore plan**. It has no `restore`, `apply`, `drop`, `rename`, service restart or routing-switch command. Actual production effects remain with the existing admitted DIAL owner/Root execution path.

The independent project databases remain inside one PostgreSQL server. A recovery destination is another temporary/quarantined database on that same server, not an additional Supabase installation. The completed rehearsal proves the database/Auth/REST recovery core; it does not qualify a production cutover.

## Capture

The operator must supply a reviewed project manifest, exact project slug, pinned PostgreSQL executables and a private endpoint configuration. An independently observed PostgreSQL cluster system identifier is mandatory. The connection never comes from an application request.

The new bootstrap stores a recovery marker in `dial_private.project_identity`, owned by the existing `postgres` administrator. Public API roles have no access to it. This marker is an identity check, not a new authority registry: a privileged schema/database administrator can still change database contents, and the source must be trusted.

Capture holds a real `REPEATABLE READ READ ONLY` transaction and exports its PostgreSQL snapshot. Project UUID, database name, issuer and cluster system identifier are read in that transaction and checked against the request. `pg_dump --snapshot` captures the same snapshot, including real Auth tables, application data, functions, policies and grants. The exporter stays alive until dumping completes.

The capture writes only a new private output directory (0700, files 0600), first records an incomplete intent, and publishes `manifest.json` only after successful dumping, snapshot completion, hashing and file flush. Failure retains private diagnostics and incomplete output, without a successful backup manifest or automatic retry. New capture paths are required; prior archives are never overwritten.

The current implementation deliberately bounds capture to **120 seconds and 256 MiB**. Those are prototype operation/resource limits, not capacity claims for Nissan GTR. A larger source requires an independently qualified durable immutable-artifact route and an approved resource budget; do not bypass the limit or represent a partial dump as a backup.

The endpoint JSON schema is:

```json
{
  "host": "127.0.0.1",
  "port": 5432,
  "user": "reviewed_backup_principal",
  "passfile": "/absolute/private/backup.pgpass",
  "system_identifier": "INDEPENDENTLY_OBSERVED_NUMERIC_CLUSTER_ID",
  "sslmode": "disable"
}
```

This is a schema example, not deployable configuration. Host/port/user must identify the reviewed database endpoint, and the principal must possess the required backup and observation rights. `disable` is accepted only for loopback or a local Unix socket. Remote connections require `verify-full` and a correctly provisioned trust configuration. Keep the configuration and passfile in operator-owned private directories; no inline password/DSN field is accepted. Do not give application logins administrative backup privileges.

```sh
BASE=deploy/van-trading-core/supabase/multiproject
python3 "$BASE/tools/recovery.py" capture \
  --manifest /absolute/reviewed/projects.json --project nissan-gtr \
  --endpoint /absolute/private/backup-endpoint.json \
  --pg-bin /absolute/pinned/postgresql/17/bin \
  --source-revision EXACT_40_CHARACTER_SOURCE_COMMIT \
  --out /absolute/private/new-backup-directory
```

An isolated extracted runtime can also supply an absolute `--library-path`. This does not install libraries. Credentials and archive contents are never printed. The returned manifest digest must be retained independently in the existing protected audit/backup store; a digest kept only next to an editable archive is not a trust anchor.

## Verification and restore planning

```sh
python3 "$BASE/tools/recovery.py" verify \
  --manifest /absolute/reviewed/projects.json --project nissan-gtr \
  --bundle /absolute/private/existing-backup \
  --manifest-sha256 INDEPENDENTLY_RETAINED_SHA256

python3 "$BASE/tools/recovery.py" plan \
  --manifest /absolute/reviewed/projects.json --project nissan-gtr \
  --bundle /absolute/private/existing-backup \
  --manifest-sha256 INDEPENDENTLY_RETAINED_SHA256 \
  --target dial_restore_0123456789abcdef \
  --out /absolute/private/new-reviewed-plan
```

Planning refuses the source database, another registered project, protected database names and arbitrary target names. The new target must not exist. It is created with connections disabled while PUBLIC privileges are revoked, then made available to the separately authorized administrative restore operation—not to application logins.

The plan requires a fresh same-cluster target with the correct database owner, no application objects/functions/types or additional extensions, and no unexpected CONNECT/CREATE grants. A nonempty or publicly connectable target is refused. The existing project HBA rules reject runtime logins to this new database until a separately reviewed switch.

Immediately before a restore, the existing owner must independently authorize the exact archive, target, scope and command. `verified_archive()` checks the externally retained manifest digest, project identity, archive size and content hash. It copies those verified bytes into a **sealed Linux memfd**; write, grow and shrink are prohibited. The restore must consume that descriptor, not reopen a pathname. Replacing or editing the original archive after verification cannot change the verified input. Capture/verification do not manufacture Root signatures or deployment authority.

The plan uses `pg_restore --exit-on-error --single-transaction` with the exact new database. It intentionally omits `--clean`, `--create`, `--no-owner` and `--no-acl`: do not delete a live database or silently discard ownership/access controls. Review the source SQL and retain independently admitted provenance before execution. PostgreSQL warns that restoration can execute code chosen by source object owners; a matching hash alone does not make an untrusted dump safe.

## Separate obligations that the logical archive does not satisfy

A database archive is not a whole-cluster recovery system. PostgreSQL roles and their passwords, signing/API secrets, service configuration, TLS/SMTP/OAuth configuration, Storage/R2 object bytes and the owner/admission records require separate protected backup custody. The plan assumes the same existing cluster roles and independently retained project secrets. A different cluster needs explicit role/bootstrap qualification first.

The archive contains sensitive Auth state, including password hashes and session data. Filesystem permissions are **not encryption**. Encrypted off-host copies, independent key custody, retention schedules, tamper-evident publication, restore drills at production scale, WAL/PITR and disaster recovery remain open. No backup schedule was installed by this work.

Restoring Auth rewinds identity and session state to the selected snapshot. It may resurrect a session revoked after that snapshot. The production recovery decision must explicitly address post-backup revocations, deleted users, password changes and signing-key versions. Forced reauthentication/revocation or project-only rekeying may be required before reopening traffic. Passing the fixture's preserved-session test does not authorize reopening stale sessions.

## Recovery activation and rollback

The rehearsal stopped only the selected project's Auth/REST processes, verified no source sessions remained, restored into a fresh database, compared all fixture tables and effective privileges, then explicitly switched that project's HBA/DSNs. Its original database was retained. The neighbouring project continued to read/write, and cross-project denials remained effective.

That fixture switch is not a production orchestrator. Production requires an exclusive original operation/lease, all writers and workers fenced, final-delta reconciliation, original source/target identity checks, verified HBA reload, exact secret/config versions, durable receipts, endpoint checks, and explicit rollback accounting. Restoring an old snapshot is not a zero-data-loss migration. After new writes, pointing back at an older source without reconciliation is unsafe.

A shared PostgreSQL restart is a **shared outage**, even with separate project databases. The test proves automatic connection-pool recovery and preserved state after restart; it does not provide independent high availability or an RTO/RPO service guarantee.

## Evidence and official reference

See `QUALIFICATION_RECOVERY_2026-11-04.md` and `evidence/2026-11-04-recovery/` for exact tested bytes and results. The archive and its private Auth contents are not committed.

PostgreSQL 17 official documentation:
- https://www.postgresql.org/docs/17/app-pgdump.html — consistent snapshots and single-database logical dumps.
- https://www.postgresql.org/docs/17/app-pgrestore.html — trusted-source warning, transaction/error behavior and fresh-target restores.
- https://www.postgresql.org/docs/17/app-pg-dumpall.html — cluster-global objects such as roles are separate from individual database dumps.
