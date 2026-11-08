# Hosted Nissan GTR versus ARM64 baseline — exact table and grant contract

**Status:** read-only schema comparison, **not final migration acceptance**. Hosted project `bicyjghgdnzlnjqxzoud` was accessed through the authenticated Supabase connector. Baseline source is the pinned `supabase/baseline/source-contract.json` from `Vanguduza/Nissan-Gtr-Auto@8131858c7c7479d178cbe9e246f83cb49ed80f5e`, previously tested against the actual donor ARM64 PostgreSQL 17.6 image. This baseline contract was captured **before** twelve forward migrations; it must not be represented as the fully migrated final-state contract.

## Exact table identity comparison

The hosted read-only query used `pg_class` / `pg_namespace` for `public` and `private` ordinary and partitioned tables, ordered by schema and table name. Each line was encoded as `schema|table|rls_enabled|persistence`; the corresponding pinned baseline rows were serialized with exactly the same order, separators and boolean representation. No table data was queried.

| Identity property | Hosted live | Pinned ARM64 baseline |
|---|---:|---:|
| Table identities | 212 | 212 |
| Table identity SHA-256 | `086902b51d92e16fe697800c120e543fbb1ff6d26c76300db85184a8ac1b7fdb` | Same |
| Table name SHA-256 | `2b71149c221c0202678c4af52dfbe8a6144bfeaa6a713264cb7cc876451b31ec` | Same |
| Private schema USAGE grant SHA-256 (anon, authenticated, service_role) | `6b2d2ca1e27f9259fe10f181d743a8f5272acc252d65f37305a06ef16523ef66` | Same |

**This proves equality of these selected metadata fields, not columns, indexes, constraints, triggers, complete policy definitions or row contents.**

## Role/table privilege divergence

For each `public` / `private` table and view, the contract checks `anon`, `authenticated` and `service_role` against SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER and MAINTAIN.

Both sides have **5,136** ordered checks, but the resulting privilege matrices differ:

- Pinned ARM64 baseline matrix SHA-256: `7c27f5f235abda0dd7aba86dd18123e86c5dcad20bbfe6326d5485cf2b6358ad`.
- Active hosted matrix SHA-256: `ea17f0f25211f443b83937433befc5f947e6bb1647a21a49682b2505d2935979`.

| Granted operation | Baseline anon | Hosted anon | Baseline authenticated | Hosted authenticated |
|---|---:|---:|---:|---:|
| SELECT | 2 | 130 | 175 | 175 |
| INSERT | 0 | 107 | 65 | 125 |
| UPDATE | 0 | 107 | 59 | 123 |
| DELETE | 0 | 107 | 59 | 126 |
| MAINTAIN | 0 | 141 | 0 | 168 |

The hosted `service_role` grants also differ: it has 211 grants for INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER/MAINTAIN, compared with 160/158/157/54/54/54/54 in the baseline. Both have SELECT on 212 relations.

**Interpretation:** Differences in ACLs are real, but may reflect the twelve forward migrations, current hosted Supabase platform defaults or role-specific decisions. They are **not** by themselves evidence of unauthorized row access, because RLS remains enabled on all 210 public tables and the authorization predicates must be checked separately. In particular, no automatic grant/revoke remediation is authorized from this report.

## Other observed source inventories

- Hosted public/private tables: 210/2, with all 210 public tables RLS enabled.
- Hosted public policies: 306; pinned *pre-forward* baseline contract: 341 policies (including selected Storage policies). **Not directly comparable scopes or stages.**
- Hosted public functions: 693; pinned baseline public/private functions: 769. **Not directly comparable scopes or stages.**
- Hosted Supabase Storage: ten buckets, seven objects, all seven in `catalog-diagrams`.
- Hosted Auth: one user, one identity, one session, one refresh token.
- Hosted cron: four active jobs with matching names and schedules to the central scheduler adapter; commands and side effects remain unqualified.
- Hosted migration ledger: 157 live versions; 125 in retained hosted archive and 32 in pinned legacy archive, zero unknown versions/name conflicts. None of the thirteen new baseline/forward versions are applied on hosted production.

## Next gates

1. **Create a final-state ARM64 contract after all 13 migrations**, then compare exactly the same table/column/index/constraint, view, function definition, RLS predicate, role-grant and policy scopes against live hosted. Report every difference with source/role context, without applying any migration to the hosted project.
2. Review public/anon and authenticated ACLs together with RLS predicates and exposed API schemas; avoid interpreting grants alone as an access-control verdict.
3. Inventory the seven actual Storage object bytes and R2 catalog separately with checksums and protected credentials, and validate Auth, payment, provider hooks and four cron jobs in staging.
4. Preserve existing VAN/VATI data, use **one PostgreSQL server**, and require independent ARM64 release admission. The earlier live-canary operation was explicitly refused and has not been retried or bypassed.

**No hosted SQL statement bodies, customer rows, API secrets or credentials were exported; no hosted database, VM, Supabase service, cron job or storage object was changed.**
