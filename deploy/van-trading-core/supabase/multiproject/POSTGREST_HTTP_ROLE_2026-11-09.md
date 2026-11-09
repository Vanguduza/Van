# Nissan GTR — real ARM64 PostgREST HTTP role qualification

**Disposition:** 12/12 local HTTP checks passed on an isolated synthetic-data PostgreSQL 17.6. **No production canary admission or Nissan GTR cutover.**

## Test source and execution boundary

- Pinned Nissan GTR source: `Vanguduza/Nissan-Gtr-Auto@8131858c7c7479d178cbe9e246f83cb49ed80f5e`.
- Original successful 13-migration ARM64 replay runner (unmodified), exact PostgreSQL donor image `sha256:f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00`.
- Actual installed **PostgREST 14.17 ARM64** image `sha256:c9dc201e555f5d8e37e7f39cdd4df0229774996e213bfd7de8d10ac609030f2c`. No new image pulled or new Supabase installation deployed.
- The second observer ran on `van-trading-core` under managed nonproduction job `djob_128d2261593fef08d9868708`. It paused the original replay runner immediately after migration 13; the actual PostgREST sidecar shared **only the disposable PostgreSQL container's network and PID namespaces**. Both used no external network, zero published host ports and a disposable `gtr_replay` database.
- PostgREST used the existing donor `authenticator` role over an in-fixture UNIX socket, local-only HTTP port 3199, cryptographically random **synthetic** JWT secret, and `db-tx-end=rollback`. No production credentials, user data, payment details or Edge/R2 secrets were provided. All response bodies were discarded by the test client; only bounded HTTP status codes were retained.
- Observer source `observer-used.py.txt` SHA-256 `def0d944c70a10541787bb9e0d8d9200753fce1f2def1c9a8b3fe3de74971dcb`. Native HTTP receipt SHA-256 `2e96a96db61e889cb815696f5fa078cc75b67789c7afb24298513da039258a01`.

## Actual HTTP responses

| Call | Synthetic role | Status | Qualification |
|---|---|---:|---|
| `GET /daily_exchange_rates?select=*&limit=0` | anon | 200 | Public read available |
| `GET /stock_item_images?select=id&limit=0` before correction | anon | **401** | Missing direct read grant reproduced |
| Same product-image GET | authenticated | 200 | Authenticated read available |
| `GET /hr_grades?select=id&limit=0` | authenticated | 200 | Existing authenticated read remains available |
| Same HR-grade GET | anon | **401** | Anonymous HR-grade request denied |
| `POST /rpc/create_pos_cart` with synthetic invalid arguments | authenticated | 400 | Route did not report a missing endpoint; business success **not established** |
| `POST /rpc/create_hr_role` with synthetic invalid arguments | authenticated | 400 | Same limitation |
| `POST /rpc/upsert_customer_garage_vehicle` with no GTR user | authenticated | 400 | Same limitation |
| `POST /rpc/upsert_staff_product_page` with synthetic invalid arguments | authenticated | 400 | Same limitation |
| `POST /hr_grades` direct write with synthetic data | authenticated | **403** | Restricted direct write enforced |
| Same anonymous image GET after one disposable fixture `GRANT SELECT` | anon | **200** | Narrow correction restores intended API access |
| Same anonymous image GET after disposable fixture `REVOKE SELECT` | anon | **401** | Original denial restored |

**Do not label the four HTTP 400 results successful RPC business execution.** The observer discarded response bodies, so SQLSTATE/error-code classification and exact internal function paths remain unproved. PostgreSQL `PREPARE` previously passed 16 call forms, and these four HTTP POSTs demonstrate that PostgREST reaches error/validation handling rather than a missing-route response. A dedicated synthetic-data HTTP functional test remains necessary.

**Public product-image permission gap is proven at the HTTP layer.** The original RLS policy permits anonymous SELECT, but the final candidate omits the table-level `anon` SELECT grant. In this test, exactly one grant was committed **only to disposable `gtr_replay`**, checked over real PostgREST HTTP, then revoked in the disposable database and the initial denial verified. Both original live Supabase and the hosted Nissan GTR database were untouched.

## Native replay and cleanup evidence

The original **13/13 Nissan GTR migrations** and **17/17 original business smoke suites** passed in this same disposable replay. The separate observer captured the postforward schema, and the original runner independently checked preserved original containers. On readback:
- **All eleven** original managed Supabase containers retained their identities and start times.
- **Zero** disposable `dial.gtr.schema-replay` PostgreSQL or `dial.gtr.http-replay` PostgREST containers remained.
- **Zero** production database writes, production port publications or hosted data copies occurred.
- The synthetic JWT secret and signed bearer token were never published or retained.

The **first** local HTTP attempt did not reach ready state. It cleaned up both temporary containers and changed no production state. The follow-on test aligned the PostgREST sidecar's unprivileged UID:GID with the PostgreSQL fixture's UID:GID to permit access to the isolated UNIX socket through the shared PID namespace. The second test passed; evidence preserves the failed first attempt rather than relabeling it as green.

## Permanent deterministic admission guard

`tools/gtr_postgrest_http_gate.py` reads the exact SHA-pinned native HTTP and replay receipts, requires all twelve expected endpoint/role/status observations, a preserved and cleaned-up original 13-migration/17-smoke run, and fails on missing/changed fields, JWT retention, network exposure, production writes, unremoved sidecars or unrevoked fixture permissions. Its output **always denies production activation, migration-history repair and cutover**, including on a green test. `tests/test_gtr_postgrest_http_gate.py` includes failure-case regressions and reads these same committed receipts.

## Still open before real deployment

The **77 authenticated DML grant gaps** across 30 tables remain intentionality/compatibility reviews; earlier static caller traces found no direct session-authenticated DML in the pinned source, but dynamic/older/external consumers remain unverified. Direct-grant and `SECURITY INVOKER/DEFINER` boundary tests with synthetic authorized/unauthorized users are required for the affected business workflows. Also unresolved: exact function behavior changes, `v_master_stock` view parity, 13 added policies, real Auth/Storage/R2/payment data recovery, four hosted cron jobs with single-writer cutover, ARM64 complete shared-service routing, TLS and revocation.

The original **live-canary execution refusal remains unresolved**, and this HTTP rehearsal must not be repurposed to bypass it. **PR #102 stays draft and unmerged.**
