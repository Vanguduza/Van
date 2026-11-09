# Nissan GTR — real ARM64 PostgREST error-code and synthetic RLS qualification

**Result:** 13/13 original migrations, 17/17 original business smoke suites, 12/12 prior HTTP role checks and **10/10 new seeded-user HTTP/RLS checks** passed in a disconnected disposable ARM64 PostgreSQL/PostgREST environment. **Production release remains blocked.**

## Provenance and execution scope

Nissan GTR source was locked to `Vanguduza/Nissan-Gtr-Auto@8131858c7c7479d178cbe9e246f83cb49ed80f5e`. The unchanged original ARM64 migration runner executed its thirteen source-locked migrations on the source-verified PostgreSQL donor image `sha256:f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00`. After **the local-development synthetic seed** completed, a separately SHA-verified observer paused the runner and queried a PostgREST v14.17 ARM64 process `sha256:c9dc201e555f5d8e37e7f39cdd4df0229774996e213bfd7de8d10ac609030f2c` sharing **only** the fixture's process/network namespaces.

There was no external network, published port, hosted database connection, real Nissan GTR user data, customer identifier or production secret. The observer generated ephemeral locally signed JWTs for fictional seeded admin, storefront customer A, storefront customer B, and an unseeded outsider. The tokens and raw response bodies were **not saved**. Reported counts refer only to synthetic fixture rows.

The managed native job was `djob_b1e6370a16ee7095206f9f17`. The exact observer SHA-256 is `e0ee7b95e64d077b0ad7efb8eb3c3380e1fedbd972c94b6837aca2091be3a70b`. The observed HTTP JSON receipt SHA-256 is `26c436e208bba8cf7277a2b38e7d4b27eafee87e3b13fd46b8342c9f66b72a18`.

## Actual RPC error classification

The previous four HTTP 400 responses are no longer ambiguous at the PostgREST routing level:

| Invoked HTTP RPC | HTTP | PostgreSQL code | Meaning |
|---|---:|---|---|
| `POST /rpc/create_pos_cart` | 400 | `P0001` | Application exception from deliberately invalid synthetic inputs |
| `POST /rpc/create_hr_role` | 400 | `P0001` | Application exception |
| `POST /rpc/upsert_customer_garage_vehicle` | 400 | `P0001` | Application exception |
| `POST /rpc/upsert_staff_product_page` | 400 | `P0001` | Application exception |

The observer extracted **only the allowlisted machine-readable SQLSTATE/error code**, not the error description or response contents. These are **not** `PGRST202` missing-function or `PGRST203` ambiguous-function errors. Thus, PostgREST resolved the four RPC calls to PostgreSQL application code. PostgreSQL `PREPARE` had already passed sixteen older/newer positional/named argument patterns.

**Not yet proved:** that a valid POS sale, HR onboarding, customer garage update or merchandising write succeeds under a real authorized client. `P0001` is an application-side raised exception, not a successful transaction.

## Real synthetic-user HTTP RLS and RPC checks

These are the ten independently tested, role-bound requests through actual PostgREST. All returned HTTP 200; successful access was determined by whether the response contained the expected synthetic row count.

| Synthetic caller and request | Expected rows | Actual |
|---|---:|---:|
| Customer A reads own profile | 1 | **1** |
| Customer A tries customer B profile | 0 | **0** |
| Customer A tries customer B customer record | 0 | **0** |
| Customer A reads own customer record | 1 | **1** |
| Customer B tries customer A record | 0 | **0** |
| Admin reads customer B record | 1 | **1** |
| Admin reads own staff role | 1 | **1** |
| Customer A tries admin staff role | 0 | **0** |
| Authenticated unseeded outsider tries customer A record | 0 | **0** |
| Admin invokes read-only `GET /rpc/list_catalog_makers` | 0 | **0**, HTTP 200 |

The final row is also an HTTP-level positive RPC response, not just a 400 returned by rejected synthetic business arguments. It demonstrates that the authenticated role can invoke that read-only API and receive a valid result in the fixture.

Separately, the earlier 12-request suite still reproduces `anon` `stock_item_images` read **401 → 200 → 401** during a scoped fixture-only `GRANT SELECT`, followed by explicit `REVOKE` and restoration of the original denial. It retains positive authenticated reads, denied anonymous HR-grade access and denied authenticated direct HR-grade writes.

## Evidence and fail-closed gate

- `evidence/2026-11-09-seeded-rls/postgrest-local-http-result.json`: exact 12 HTTP statuses, four `P0001` codes and ten synthetic row-count results, no bodies/tokens.
- `evidence/2026-11-09-seeded-rls/observer-used.py.txt`: exact original nonproduction observer source, including bounded response reading and cleanup logic.
- `evidence/2026-11-09-seeded-rls/replay-final-receipt.json`: original migration/smoke/cleanup receipt, 13/17 PASS.
- `evidence/2026-11-09-seeded-rls/postforward-observer-result.json`: final schema source and counts.
- `tools/gtr_postgrest_seeded_rls_gate.py`: **offline**, exact-SHA, exact-row-order and original receipt checking; no SQL, network, Docker, migration or release action. It **always refuses production/canary/cutover authority**, even when all checked synthetic tests pass.
- `tests/test_gtr_postgrest_seeded_rls_gate.py`: source, RLS row count, role substitution, wrong SQLSTATE/PGRST error, cleanup, scope and production-refusal regression tests.

The original **11** Supabase production containers were verified to remain running and healthy, the throwaway PostgreSQL and HTTP containers were removed, and no hosted/cloud data were copied or modified.

## Remaining production gates

1. Complete **positive, legitimate state-changing** POS/finance/HR/customer flows with synthetic staff/customer permissions in an isolated transaction-rollback environment; verify actual RLS `WITH CHECK`, trigger and `SECURITY INVOKER/DEFINER` semantics.
2. Complete the 77 authenticated DML permission review, modified function/view definitions and 13 additive policies without blanket GRANT or weakened tenant isolation.
3. Qualify real hosted Auth/session UUIDs, Storage object bytes, Cloudflare R2, Edge/runtime secrets, payment callbacks and four active scheduled jobs with a proven single-writer and reversible cutover.
4. Clear the original **explicitly refused live DIAL canary** through its original admission and signed owner release path. These synthetic results cannot authorize any live deployment or new project endpoint.

**PR #102 must remain draft/unmerged until the independently required live admission, native recovery, Zuul and owner acceptance gates pass.**
