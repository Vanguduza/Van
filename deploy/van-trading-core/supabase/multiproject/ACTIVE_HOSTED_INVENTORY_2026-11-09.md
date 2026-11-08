# Active Nissan GTR Supabase — authenticated read-only inventory (9 November 2026)

**Live project verified:** Supabase connector reports `Nissan GTR Auto`, ref `bicyjghgdnzlnjqxzoud`, status **ACTIVE_HEALTHY**, managed PostgreSQL **17.6.1.166**. The retired project `gylrgwqyuiwkyykardwc` was not queried or altered.

## Migration ledger comparison

| Live migration fact | Verified result |
|---|---:|
| Current hosted records | **157** |
| Found in previously exported hosted archive | **125** |
| Additional records present in pinned legacy-source archive | **32** |
| Unrecognized version IDs | **0** |
| Previously archived hosted records missing live | **0** |
| Version/name conflicts | **0** |
| New consolidated baseline/forward migration IDs already applied to host | **0** |

The connected database was queried using a bounded **read-only, repeatable-read transaction**, with an actual `supabase_migrations.schema_migrations` base-table lock, a typed-column/RLS guard, and no return of stored SQL statement content. The capture reported 157 of 157 non-null statement-array fingerprints, was not truncated, and retained nonce `f3b0e14688ce4a30be85c920dea41767` at `2026-11-08T22:40:41.98013Z`. Supabase `list_migrations` independently returned the same 157 version/name records. The comparison used the pinned archived-source catalog from `Vanguduza/Nissan-Gtr-Auto@8131858c7c7479d178cbe9e246f83cb49ed80f5e`.

**New conclusion:** every live migration version/name is represented in source; the earlier 125-file hosted export was **incomplete**, not a complete current hosted ledger. The 32 omitted entries are in the pinned legacy archive. Source-body equivalence for ten duplicated legacy/hosted-export pairs is addressed separately in `ARCHIVED_MIGRATION_BODY_EQUIVALENCE.md`.

**Important:** concordant migration version/name entries and their fingerprints **do not prove** current schema/body/data equivalence. The hosted statement-array fingerprint format differs from original raw SQL file checksums; do not pretend they are equal.

## Real data and operational dependencies

The read-only source inventory returned **210 public tables, all with RLS enabled**, 306 public RLS policies, two public views, 693 public functions, one replication publication, **one Auth user**, **ten Storage buckets**, **seven Storage objects** and **31 deployed Edge Functions**. Installed extensions include `pg_cron`, `pg_net`, `supabase_vault`, `pgcrypto`, `pg_stat_statements` and `uuid-ossp`.

Supabase's security advisor produced **28 informational `rls_enabled_no_policy` findings**. RLS without a policy can intentionally deny access. Review their intended consumers and privileges before classifying them as defects or modifying policies. See [Supabase linter reference](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy).

These counts are a *baseline inventory*, not a complete or synchronized backup. Existing Auth, refresh sessions, object bytes, external Cloudflare R2, hosted Edge secrets, payment/webhook providers and actual business data must be independently preserved and reconciled before any migration.

## Decisions and release gates

- Keep **the single installed Supabase stack and PostgreSQL server** on `van-trading-core`; introduce independent project databases/Auth/API identities, shared remaining services.
- Do **not** apply the 13 new source migrations to populated hosted production or mark them as applied. Staging must compare complete canonical schema, grants, RLS, functions, actual table data and functional outcomes first.
- Do **not** copy or purge Auth sessions, Storage bytes, R2/catalog, payments or hosted cron and webhook dependencies without verified migration and rollback.
- The previously refused live DIAL canary activation remains blocked and is not reattempted through this connector or another route. Root signed identity checks are separate from deployment authority.
- Keep PR #102 **draft/unmerged** and require signed release, target ARM64 service qualification, strong recovery and separate acceptance before moving production traffic.

**No hosted or DIAL production mutations occurred during these observations.** The companion JSON receipt contains counts and metadata only; no user records, migration statement bodies, access tokens or connection secrets are committed.
