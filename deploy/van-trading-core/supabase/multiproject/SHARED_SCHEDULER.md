# Shared scheduling for independent Supabase project databases

## Why this migration step is necessary

The exact Nissan GTR baseline at commit `8131858c7c7479d178cbe9e246f83cb49ed80f5e` installs `pg_cron` in the application database and registers four recurring jobs there. Upstream pg_cron permits only one extension installation per PostgreSQL cluster; jobs for other databases use `cron.schedule_in_database`. A direct replay into a second project database therefore cannot preserve the required single-cluster topology.

Reuse the existing server's canonical cron database, rather than adding another PostgreSQL server or scheduler. `tools/shared_scheduler.py` supplies a source-locked fresh-install adaptation, restricted job roles and **inactive** central registrations. It does not execute SQL, start processes, connect to a target or authorize deployment. The earlier refused live canary remains refused; this source work does not replay it.

## Exact source custody

The pinned GTR baseline is `supabase/migrations/20261102080000_reconciled_erp_baseline.sql`, 4,027,262 bytes, SHA-256 `2502826ee08e67d7bcee3f7bdacdc31d944ccbb1bf9c3d86090b79b938ea016c`. The compiler accepts that exact byte sequence only. It removes one exact pg_cron extension directive and relocates four exact cron registration directives into a separate central-database SQL file. Reversing those five documented edits reconstructs the original baseline byte-for-byte. All other SQL, functions, tables, policies, grants, reference records and the existing fresh-install guard remain unchanged.

The original Nissan GTR repository is not edited. No migration ledger is marked as applied. The generated adaptation is a derived deployment artifact, not a replacement upstream history. All thirteen current migration file identities and their immutable source commit are retained in the evidence. The remaining twelve forward files are not transformed; their actual execution remains unqualified.

| Original job | Schedule preserved | Target function signature |
|---|---|---|
| approval-alerts-sweep-v1 | `*/5 * * * *` | `private.sweep_approval_alerts()` |
| commerce-expire-checkouts-v1 | `*/2 * * * *` | `private.expire_commerce_checkouts_internal()` |
| customer-suspension-sweep-v1 | `10 2 * * *` | `private.sweep_customer_suspensions()` |
| morning-summary-v1 | `0 5 * * *` | `private.send_morning_summaries(date)` |

The last function has a default date argument, so the no-argument scheduled call is valid but the EXECUTE grant must use the actual `(date)` signature. The compiler does not shift times between GMT and Africa/Harare; it binds an explicitly observed cron timezone and refuses a mismatched control database or timezone.

## Role, control-plane and duplicate-work protection

Each project receives a UUID-namespaced scheduler role and job names. A new role starts NOLOGIN, with no password, no superuser/create-role/create-database/replication/BYPASSRLS attributes and no inherited membership. It gets CONNECT only explicitly to its own project database and EXECUTE on the four reviewed private functions. Grants verify project identity, SECURITY DEFINER status, integer result and an empty search path. If adding private-schema USAGE would expose another unreviewed function through an existing PUBLIC EXECUTE grant, the transaction refuses and rolls back.

The tested candidate uses native pg_cron background workers. Roles are enabled for that engine only after the exact first-match HBA prefix rejects all their local/TCP client logins and a reload is observed. PostgreSQL LOGIN is required by pg_cron even for background-worker jobs; these roles have no password and are not application API principals. **Background workers do not authenticate through HBA.** Protected control-plane registration, exact database selection, effective SQL CONNECT permissions and reviewed function authority remain essential. A compromised central superuser is outside this tenant-isolation boundary.

Registration locks the native cron table in a transaction, checks every intended job name for collisions across roles, and refuses existing records before calling the upstream function. This is needed because native named scheduling is an UPSERT. It does not overwrite, unschedule or reconcile an unknown outcome automatically. The observed database, role, command, schedule and `active=false` are checked after each registration before committing. No job-activation SQL is supplied.

The runtime job role has no cron-schema USAGE or scheduling API access. The original privileged owner remains the only proposed registration authority. The code issues no credentials or owner qualification.

## Actual target observation — not yet configured for this candidate

A read-only query of the original ARM64 donor found `cron.database_name=postgres`, `cron.timezone=GMT`, `cron.use_background_workers=off`, `cron.max_running_jobs=32`, `cron.enable_superuser_jobs=on`, and `max_worker_processes=8`. The original `postgres` database did **not** have a pg_cron extension installed. The launcher/settings are configured, but that is not an installed, working project scheduler.

The candidate does not automatically install the missing extension or change the global engine. Adopting the background-worker path requires a separately admitted installation/configuration and worker-capacity decision, potentially a server restart. Alternatively, a password-authenticated libpq path that preserves the current engine would need its own implementation and native qualification; it is not claimed by these tests. No global donor setting, existing job or process was changed.

Native tests used a fresh non-root PostgreSQL 17.11 server with pg_cron package `1.6.8-1.pgdg24.04+2` and SQL extension version `1.6`. That is real upstream pg_cron, not a stub, but it is not the actual target ARM64 package or full Nissan GTR business runtime.

## Generate review artifacts only

Supply a one-project manifest and the exact pinned source baseline:

```sh
python3 tools/shared_scheduler.py \
  --manifest /private/single-gtr-project.json \
  --baseline /private/source/20261102080000_reconciled_erp_baseline.sql \
  --cron-database postgres --cron-timezone GMT \
  --out /private/new-scheduler-candidate
```

The new output directory is mode 0700; files are mode 0600. Existing output paths and unpinned source bytes are refused. The baseline file remains fresh-install-only and must never be applied to the original VAN `postgres` database or a populated Nissan GTR schema. The role-enable SQL is not a release receipt; neither it nor the inactive registration may be applied to production without independent original-owner admission.

## What was genuinely verified

The isolated native test used one newly initialized PostgreSQL server, one central pg_cron extension, two separate synthetic application databases and a legacy sentinel. It proved eight uniquely named jobs (four per project), inactive registration, rejection of a second extension installation, role/HBA guards, no unauthorized scheduler manipulation, refusal of duplicate registration without changes, and real native job dispatch under the exact expected role/database.

For execution testing only, synthetic functions with the four original signatures recorded their database and session identity. Their schedules were temporarily accelerated to one-second intervals inside the disposable fixture, then disabled. These are **not** executions of Nissan GTR's financial, notification or customer-suspension business logic. The actual upstream baseline was hash-checked and reversibly adapted, not fully loaded or executed.

The entire Python suite passed 295 tests, including 25 new scheduler contracts. The new real pg_cron fixture passed 56 checks. Original failed attempts are retained. All test processes and temporary database contents were cleaned up; production remains unchanged.

## Migration prerequisites still open

The source baseline's recorded native reconstruction used Auth 2.197.0 and Storage 1.79.36, while the observed DIAL donor uses Auth 2.196.0 and Storage 1.74.0. This is a compatibility item, not proof either direction. Its pg_net, Vault/key custody, native Storage policies, Auth hooks, SECURITY DEFINER ownership, source-history reconciliation and all thirteen SQL migrations still require a complete target-version rehearsal. Real hosted schema/data, R2 assets and payment state were not accessed.

Upstream references: the pg_cron README and `v1.6.8/src/job_metadata.c` document the single extension, cross-database API, LOGIN requirement, background workers and named-job UPSERT. Source URLs and hashes are retained with the evidence; this document does not substitute for actual target admission.
