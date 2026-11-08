# Nissan GTR hosted preservation and central scheduler crosscheck

Read-only authenticated Supabase project: `bicyjghgdnzlnjqxzoud` (Nissan GTR Auto). Observations from 9 November 2026; no SQL data, Auth identifiers, cron commands, secret values or object contents are retained here.

## Current active scheduled jobs

| Hosted job | Hosted schedule | Hosted database | Active |
|---|---|---|---|
| `approval-alerts-sweep-v1` | `*/5 * * * *` | `postgres` | Yes |
| `commerce-expire-checkouts-v1` | `*/2 * * * *` | `postgres` | Yes |
| `customer-suspension-sweep-v1` | `10 2 * * *` | `postgres` | Yes |
| `morning-summary-v1` | `0 5 * * *` | `postgres` | Yes |

These are exactly the four categories previously separated by the candidate shared-scheduler adapter, but this name/schedule comparison does **not** establish identical SQL commands, function definitions, privileges, timezone, execution behavior or active customer data. The source adaptation was tested against synthetic scheduled functions. The hosted cron commands were **not** exported or executed.

**Critical cutover invariant:** do not leave these four jobs active on hosted production while enabling equivalent effectful jobs on DIAL. Choose one writer/worker authority; rehearse freeze, pending-job handling, resume and rollback with payment/notification idempotency checks. Do not disable or reschedule any hosted job until an explicitly admitted cutover.

## Auth and Storage preservation

The hosted database currently reports **one Auth user, one identity, one session and one refresh token**. Session and token values were not read. Re-authentication/re-key and user UUID linkage require explicit staging validation.

Supabase Storage has **ten buckets**. Only `catalog-diagrams` currently has stored objects (**seven**); the other nine buckets have zero stored objects at capture. Empty buckets still require their bucket configuration, permissions and RLS policy behavior to be preserved. External Cloudflare R2 catalog data is outside this Supabase Storage count and must be independently inventoried.

There are **212 application tables** across `public` (210) and `private` (2), 306 public policies, two public views and 693 public functions. These live observations must not be conflated with the *pre-forward-migration* 212-table/341-policy/769-function baseline fixture evidence; the comparison stages differ and are not yet normalized into an exact final-schema diff.

## Unchanged constraints

The active hosted ledger has 157 entries, all mapped by version/name to the pinned archive (125 hosted-export + 32 additional legacy archive). No consolidated 13-migration version is applied to hosted production. Full schema/row and function-definition equivalence, object checksums, R2 content, provider secrets and payment end-to-end remain open.

No hosted data or DIAL production service was changed. The previously refused DIAL canary activation remains blocked; this report does not authorize its replay, migration application or cutover.
