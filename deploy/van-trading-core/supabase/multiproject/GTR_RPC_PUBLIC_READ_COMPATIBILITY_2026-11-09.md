# Nissan GTR — targeted RPC and Data API grant compatibility

**Status:** evidence-backed source-only candidate; production and DIAL live canary remain blocked. Pinned Nissan GTR source commit `8131858c7c7479d178cbe9e246f83cb49ed80f5e`. This is a continuation of [FINAL_ARM64_POSTFORWARD_2026-11-09.md](FINAL_ARM64_POSTFORWARD_2026-11-09.md), not a second Supabase installation or a hosted migration.

## Four legacy RPC signatures — 16 non-effectful ARM64 checks pass

A new disposable network-isolated ARM64 PostgreSQL 17.6 replay on `van-trading-core` applied the exact original **13 Nissan GTR migrations** and passed **17 original business smoke suites**, retaining all eleven original healthy Supabase containers and removing the temporary container.

A separate read-only observer used PostgreSQL `PREPARE` (never `EXECUTE`) to resolve **16 positional and named-argument call patterns** across `create_pos_cart`, `create_hr_role`, `upsert_customer_garage_vehicle`, `upsert_staff_product_page`. **All 16 succeeded.** The extra parameters in newer signatures are defaultable; the old source signatures need not be recreated simply to satisfy these tested SQL calls.

**Limits:** SQL statement preparation validates PostgreSQL name/type/default resolution, **not PostgREST/RPC HTTP routing**, role/session authorization, mobile client compatibility, or runtime business effects. These still need checks before final cutover. No hosted/production code or client function was invoked.

The original replay runner and its image/source inputs were unmodified. Native job `djob_2cc02582babcb1c9b96d40a3` verified resolution. The later native job `djob_0e458d2cd5ef9ad117d6416e` repeated and passed the 16 checks during the targeted public-read experiment. Both kept production unchanged. The newer observer code, native receipts and hashes are preserved in `evidence/2026-11-09-rpc-public-read/`.

## Policy-aware privilege classification

The previous post-forward comparison identified **1,735 effective hosted table/view privileges absent from the fresh GTR candidate**, across 188 relations; none were added. **These must not be mass granted or revoked.**

A fresh authenticated **READ ONLY/REPEATABLE READ** hosted inspection compared 210 public tables and 306 public RLS policies against the isolated final ARM64 role/access metadata. Among public-table SELECT/INSERT/UPDATE/DELETE, hosted has 446 `anon` and 185 `authenticated` effective grants missing from the candidate. Of these **631**, only **78** have a matching, applicable hosted public RLS policy for that role and command: **1 anon SELECT, 27 authenticated INSERT, 27 authenticated UPDATE, 23 authenticated DELETE**.

This is **a conservative potential functionality shortlist**, not a proof that the remaining 553 grant losses are harmless. A role-level RLS policy may still have restrictive `USING`/`WITH CHECK` predicates, and application service/SECURITY DEFINER execution paths need independent evaluation. The exact 78 role/table/operation/policy references are saved without predicate SQL or user data in `evidence/2026-11-09-rpc-public-read/policy-applicable-grant-losses.json`.

### Verified high-confidence defect: public product image read

- Hosted `public.stock_item_images` is RLS-enabled and grants `anon` SELECT.
- Its source-locked `stock_item_images_public_read` policy explicitly permits `anon` SELECT with `USING (true)`; the final candidate retains that exact policy but **lacks the table-level `anon` SELECT grant**.
- The pinned web application directly queries `.from("stock_item_images").select(...)` in `apps/web/lib/catalog-product.ts` and `apps/web/lib/staff-product-pages.ts`. The source also labels product photography as public merchandising data.
- In isolated `gtr_replay`, a **single** `GRANT SELECT ON TABLE public.stock_item_images TO anon` restored the missing effective privilege, and **ROLLBACK restored the original denial**. Exact existing table ownership, RLS and policy preconditions were checked. No other role/table or persistent database state changed.

`tools/gtr_public_read_plan.py` generates a **source-only, owner-review candidate** for this one explicit privilege. It refuses active platform database names `postgres` and `_supabase`, requires a named separate project database, exact table/role/owner and public-read RLS policy, outputs to a private new directory via the repository's safe writer and contains **no executor**. Twelve regression/refusal unit tests passed. The generator's reference to the pinned GTR commit is a declared source binding, not a fresh download or byte-verification operation.

**Do not apply this SQL automatically.** Rendering is not signed deployment admission. The original live canary refusal still requires resolution by its original authority before any actual GTR database activation. The test transaction is not the same as approving or applying the rendered production candidate.

## Next gates

1. Determine whether the **77 authenticated policy-applicable DML permission losses** are genuine client workflow regressions or intentional isolation/hardening. Evaluate actual web/Android/POS caller patterns and negative RLS tests. Only then propose separately reviewed, narrowly scoped grants.
2. Test the four default-compatible RPC patterns through real authenticated PostgREST/Auth roles and API routing in **nonproduction**. No claim of HTTP parity from PREPARE alone.
3. Qualify remaining function-body text differences, 13 new RLS policies and `v_master_stock`; preserve actual data, one Auth identity/session, seven Storage objects, Cloudflare R2, payment hooks and four active hosted cron jobs.
4. Require original DIAL canary admission, exact-head CI/Zuul, single-stack ARM64 co-existence and full reversible cutover evidence.

**No production Supabase, Nissan GTR hosted database, live user session, payment provider, Storage object, cron job or existing VAN/VATI data was changed.**
