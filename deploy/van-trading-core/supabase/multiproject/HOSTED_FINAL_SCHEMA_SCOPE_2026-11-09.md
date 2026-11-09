# Nissan GTR — exact hosted final-schema comparison checkpoint

**Disposition: partially verified, final-state equality not yet established.** The active connected hosted project `bicyjghgdnzlnjqxzoud` remains unchanged. This checkpoint uses read-only catalog queries and the immutable ARM64 donor source contract. The retained donor contract is a **pre-forward** baseline; do not label it the final result of the thirteen-migration replay.

## Same-scope hosted counts

A single read-only query using the same relation/function/policy schema filters as `evidence/2026-11-08-gtr-arm64-replay/contract-reader-used.py.txt` established:

| Metadata scope | Hosted live | Pinned pre-forward ARM64 baseline |
|---|---:|---:|
| `public` and `private` tables | **212** | **212** |
| `public` and `private` views | **2** | **2** |
| `public` and `private` ordinary functions | **760** | **769** |
| `public`, `private`, `storage` RLS policies | **337** | **341** |
| Relation privilege checks | **5,136** | **5,136** |

The exact table identity SHA-256 (schema, name, RLS and persistence) matches both sides: `086902b51d92e16fe697800c120e543fbb1ff6d26c76300db85184a8ac1b7fdb`. Private-schema USAGE for `anon`, `authenticated` and `service_role` also matches. The 5,136 relation permission checks have different resulting privilege values: hosted `ea17f0f25211f443b83937433befc5f947e6bb1647a21a49682b2505d2935979`, pinned pre-forward `7c27f5f235abda0dd7aba86dd18123e86c5dcad20bbfe6326d5485cf2b6358ad`.

**Interpretation:** nine fewer same-scope functions and four fewer same-scope policies in hosted production compared with the pre-forward baseline. The 12 forward migrations are expected to change the final state. These differences are not yet a precise final-state diff, and should **not** be automatically repaired or used to infer an application defect. Comparing `public` only against `public/private/storage` would produce an invalid count.

## Current live operational preservation

- 157 live migration versions; all map to pinned source by version/name (125 retained hosted-export and 32 legacy-source-only), none of 13 consolidated baseline/forward versions marked applied.
- 210 `public` tables RLS enabled, plus two `private` tables.
- 10 Storage buckets and seven objects, all in `catalog-diagrams`.
- One Auth user, one identity, one session, one refresh token.
- Four active `pg_cron` jobs: `approval-alerts-sweep-v1` every five minutes; `commerce-expire-checkouts-v1` every two minutes; `customer-suspension-sweep-v1` at 02:10; `morning-summary-v1` at 05:00, as represented by their cron expressions. No commands or provider credentials were exported.
- 31 deployed Edge Functions. Cloudflare R2 and provider-specific data are not included in these Supabase counts.

## Next exact green gates

1. Re-run or extend the **already admitted isolated** ARM64 replay through the original authorized test route to capture **after all 13 migrations**, using the same `pg_catalog`/RLS/ACL snapshot reader and independent source locks. No production container, service, role, HBA or database may be touched. Do not replay the previously refused canary or the refused runner transfer.
2. Compare identity/definition-level differences for functions (schema/name/identity args, function-body hash, role execute), RLS policies (including `storage`), views, tables and grants. Use a single pinned snapshot version for each stage. Do not automatically rewrite hosted grants to match the fresh baseline.
3. Separately preserve full business table data, Auth UUID/session handling, Storage object bytes and R2 catalogs, cron and Edge provider dependencies. Demonstrate reversible staging and one authoritative writer.
4. Clear the original live-canary safety refusal through its admission authority, qualify target ARM64 services and obtain a signed production release before any project activation or cutover.

**No hosted database data, migration ledger, cron job, Auth user, Storage object, service, role or key was modified by this comparison.** This report is not a production migration approval.
