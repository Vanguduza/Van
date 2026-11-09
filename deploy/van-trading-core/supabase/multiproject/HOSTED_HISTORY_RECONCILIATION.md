# Nissan GTR hosted-history reconciliation

## Scope

The existing native ARM64 rehearsal proved that the pinned fresh-install baseline and twelve forward migrations can run against the observed donor platform. It did **not** prove that those files equal the current hosted application's schema, data or migration ledger. This module closes the tooling gap for safely examining that ledger; it does not activate the previously refused live canary, repair history, run migrations or authorize a cutover.

`tools/gtr_history_reconcile.py` has no SQL/SSH/Docker/network execution capability. It hashes local, immutable source inputs, emits one bounded read-only capture query and reviews separately supplied metadata snapshots. Its public CLI accepts no database URL, password, access token, arbitrary SQL or apply/repair operation.

## Exact historical source, not a fabricated current ledger

Source commit: `Vanguduza/Nissan-Gtr-Auto@8131858c7c7479d178cbe9e246f83cb49ed80f5e`.

The pinned manifest retains **173 legacy SQL files, 125 exported-hosted SQL files, and 13 currently active SQL migrations**. All 311 actual SQL files, the baseline manifest and source contract were obtained from the immutable public source and checked against their exact SHA-256 values: **313 files / 7,898,022 bytes**. The 271 curated reconstruction input bindings also agree with the checked files.

Ten version identifiers appear in both legacy and exported-hosted history. Each has two different source-file hashes, despite matching version/name pairs. This is an exact-byte difference, **not proof of a behavioral SQL difference**: formatting or export framing may explain it. Neither copy is discarded or silently chosen. A metadata-only migration-list match is therefore insufficient for content reconciliation.

Migration versions are opaque 14-digit IDs. Some retained names use values such as `20260725270000`, which are not valid wall-clock timestamps. The reviewer deliberately does not reinterpret them as calendar dates or rewrite them to fit a time parser.

The baseline README says the historical directories are not active migration directories. It explicitly forbids blindly applying the fresh-install baseline to a populated hosted database or marking it applied merely to silence history warnings. The reviewer classifies the original histories separately and retains all thirteen active versions as source facts, not SQL automatically approved for execution.

## Capture boundary

Generate a private review bundle with a new 32-character lowercase hexadecimal capture nonce:

```sh
python3 tools/gtr_history_reconcile.py \
  --source-root /absolute/private/pinned-gtr-source \
  --capture-nonce <new-32-hex-nonce> \
  --out /absolute/private/new-history-review
```

The generated `capture-ledger.read-only.sql` must be executed only through an independently authenticated, authorized connection to the active hosted project, `bicyjghgdnzlnjqxzoud`, with errors treated as failures. It declares the expected project ref, but **that literal is not proof of the connection's identity**. Retain the original connection/owner receipt separately. Do not execute it on the retired recovery project `gylrgwqyuiwkyykardwc` or infer the project from the common database name `postgres`.

The query starts a **REPEATABLE READ, READ ONLY** transaction, sets a ten-second statement bound, two-second lock timeout and fifteen-second idle-transaction timeout, and uses the `pg_catalog` search path. An ACCESS SHARE lock prevents ledger DDL changes during the capture. It verifies that the ledger is a regular local table with no RLS and the expected text/text-array fields, refusing a view, foreign table, unexpected schema or row-filtered ledger instead of reporting an empty success.

Only versions, names, statement counts and SHA-256 fingerprints of PostgreSQL's JSONB statement-array representation are returned, along with capture metadata. No stored SQL statements, application rows, user credentials, Auth data or Vault values are returned. A maximum of 10,001 rows is inspected to distinguish the supported 10,000-row bound from truncation. A truncated result is never accepted. The transaction ends with ROLLBACK. The query does not initialize or repair a missing migration table.

## Hashes are not interchangeable

The archive has **raw SQL file SHA-256** values. The collector produces **PostgreSQL JSONB statement-array SHA-256** values, tagged `POSTGRESQL_JSONB_STATEMENT_ARRAY_SHA256_V1`. Those are different representations and must not be compared as though equal. A matching version or filename does not establish statement equivalence.

The reviewer can compare two earlier/later captures from the same declared project, database and PostgreSQL version, detecting removed entries or changed statement fingerprints. Null statement arrays remain distinct from empty arrays; missing fingerprints are incomparable, not equal. Snapshot provenance, snapshot freshness and connection identity still need independent custody. Ledger hashes do not prove final schema, table contents, provider behavior or business correctness.

## Review a supplied snapshot

```sh
python3 tools/gtr_history_reconcile.py \
  --source-root /absolute/private/pinned-gtr-source \
  --capture-nonce <nonce-bound-to-current-capture> \
  --snapshot /absolute/private/current-ledger.json \
  --previous /absolute/private/previous-ledger.json \
  --out /absolute/private/new-comparison
```

`--previous` is optional. Inputs must be owner-only regular, single-link files inside owner-only directories, with no parent/file symlinks, duplicate JSON keys, NaN values or oversized documents. The private reader is bounded at 8 MiB. Output uses the existing safe writer: new directory mode 0700, files 0600, no overwrite or active-installation target.

The result reports unknown versions, name drift, distinct source variants sharing a version, absent active markers, unchanged/added/removed/changed prior entries and unsupported context changes. A captured time over one hour old or in the future is flagged. An empty ledger is not proof that the database is empty. A recorded baseline marker is not proof that the baseline was applied correctly.

**Every review keeps `may_apply_baseline`, `may_repair_history`, `may_cutover` and production authorization false.** This is deliberate scope, not an alternative source of release authority. No code here retries the earlier safety-refused activation or guarded-runner transfer.

## What was actually exercised

The expanded suite passed **367 Python tests**, including **45 new history tests**. A real native PostgreSQL 17.11 fixture passed **37 checks** with a restricted observer role and a separate existing sentinel table. It proved metadata-only capture, native read-only write refusal, no-access failure, null/empty distinction, real same-version statement drift detection, removed/duplicate history detection, the 10,001-row truncation boundary, RLS/view/schema refusal and unchanged observer privileges/business sentinel. The fixture had only a private Unix socket, no TCP listener; every process and temporary directory was removed.

The 311 real source SQL files were **hashed, not executed**, in this new test. Historical source inventories are not current hosted observations. The earlier actual ARM64 migration replay and business tests remain separate evidence and were not rerun or relabelled.

## Current limitation and next real input

No authenticated Supabase-hosted administration connection is available in this session. The actual current hosted ledger, hosted schema/ACL snapshot, migration-application outcomes and customer data therefore remain unobserved. The next input is an authenticated read-only capture tied to the active project and original owner, followed by schema/ACL/data reconciliation and restore rehearsal. The new utility does not fill those gaps with guessed records.

The existing live canary refusal, target service promotion, full workload recovery and Nissan GTR cutover remain separate open gates. The original VAN/VATI stack and both hosted projects remain untouched.

## Reference behavior

Supabase's CLI reference documents that `migration list` compares version timestamps and that the remote ledger is `supabase_migrations.schema_migrations`. PostgreSQL 17's transaction documentation describes READ ONLY and REPEATABLE READ. This implementation adds evidence separation rather than invoking migration repair or inferring schema equality from that version list. The exact repository baseline README and manifest remain authoritative source inputs.


## Archived overlapping SQL-body proof (additive, separate from hosted capture)

A later exact-source adjudication established that all ten legacy/hosted-export version/name pairs with different **raw file hashes** have identical SQL bodies after removal of the **two exact hosted export provenance-comment lines and blank separator**, with six pairs additionally differing by exactly one terminal newline byte. No SQL statement, internal whitespace or additional comment was normalized.

This result is reproduced by `tools/gtr_archive_equivalence.py` with strict hash, wrapper, version and filename validation. See `ARCHIVED_MIGRATION_BODY_EQUIVALENCE.md` and `evidence/2026-11-09-gtr-archive-equivalence/` for ten original-hash pairs, source-bound comparison and failure-path tests. **Keep both archived copies and their original raw hashes**; their file-level mismatch remains true.

No **current active hosted migration ledger** has been authenticated or captured by this archival comparison. It must never be used to repair/mark a hosted ledger, authorize canary activation, infer business schema equivalence or permit cutover.
