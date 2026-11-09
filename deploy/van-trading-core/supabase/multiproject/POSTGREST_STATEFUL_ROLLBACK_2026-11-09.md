# Nissan GTR — reversible synthetic state-changing HTTP/RLS qualification

**Result:** 20/20 additional HTTP checks passed for customer, HR, POS and finance operations in an **isolated, no-external-network ARM64 PostgreSQL/PostgREST fixture**. The original 13 migrations, 17 original business smokes, 12 baseline HTTP role checks and ten synthetic customer-profile/RLS checks also passed.

This is **evidence of controlled transaction and authorization behavior**, **not production deployment authorization** and not proof of successful real payment or customer workflows.

## Native provenance and execution boundaries

- Pinned Nissan GTR migrations: `Vanguduza/Nissan-Gtr-Auto@8131858c7c7479d178cbe9e246f83cb49ed80f5e`.
- Exact unchanged original replay runner SHA-256: `11c80c443789437ac5fd4515d07008c37221774f6f2350fd4d4deda9b2055c41`; actual native PostgreSQL 17.6 ARM64 donor image `sha256:f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00`.
- Installed PostgREST 14.17 ARM64 sidecar image `sha256:c9dc201e555f5d8e37e7f39cdd4df0229774996e213bfd7de8d10ac609030f2c`, shared **only** the temporary database's PID/network namespace. No host HTTP ports, external network, hosted data, real JWTs, service-role keys, payment calls or customer records.
- The PostgREST `PGRST_DB_TX_END=rollback` setting was in effect for every HTTP request, and each test explicitly read back that the synthetic write was not persisted. The documented PostgREST 14 behavior for `db-tx-end=rollback` is to roll back every transaction: https://postgrest.org/en/v14/references/configuration.html.
- Source of synthetic identities: the original Nissan GTR **local-development-only seed** installed in the disposable database, with fictional admin/finance/storefront users. No production identity was used.
- Managed native job: `djob_a60aa666cc1d43126e0aa155`, **succeeded**. Test observer SHA-256 `c28387622503e0be4a2f6a153dcb2284fd71673484f8229b9335f8aead1fee4a`; additional transactional test module SHA-256 `edef8440e5eebbc8e26c46ba2b92ada14dead58d49e05c5d39b5d4ae093d800e`.

## Real HTTP state-changing test outcomes

| Test family | Exact observed outcome | Implication |
|---|---|---|
| Customer owns a row | `PATCH /customers` returns **200**, one row under customer A | Existing direct `authenticated` UPDATE privilege and own-row RLS permit expected update |
| Rollback | Following `GET /customers` returns the **original** synthetic display name | HTTP mutation was not persisted |
| Cross-customer update | Customer A PATCH against customer B returns **200**, **zero rows** | RLS filters the other customer's row rather than changing it |
| Peer remains unchanged | Customer B can still GET their original synthetic row | No cross-customer data change |
| HR grade, POS operator pin, finance threshold INSERT before test grant | All **403 / SQLSTATE 42501** for seeded administrator | Candidate currently withholds direct INSERT despite matching RLS policies |
| Same three inserts with narrowly scoped, *disposable-only* INSERT grants | All **201**, one returned row for seeded administrator | Authorized row-level paths become functional when table grants exist |
| Read-after-write for each | All **200**, **zero rows** | All three successful HTTP inserts were rolled back |
| Cross-role unauthorized inserts | All **403 / 42501** for customer A (HR/POS) or finance user (admin-only finance threshold) | RLS continues to enforce row/role separation after the temporary table grant |
| Revoke the three temporary test grants | Same admin inserts return **403 / 42501** | Original direct SQL privilege restrictions restored |
| Final SQL privilege readback | All three roles denied INSERT | Fixture-only GRANTs were revoked and the test DB was destroyed |

**Exactly 20 new HTTP checks** were recorded with label, synthetic caller name, status, returned-row count, PostgreSQL error code and cleanup indicators. Response bodies, names, JWTs and fixture record IDs are not retained.

The three tested missing direct INSERT rights were:
- `authenticated INSERT` on `public.hr_grades`: controlled by an admin-only `hr_grades_write` RLS policy.
- `authenticated INSERT` on `public.pos_operator_popular_pins`: controlled by `pos_operator_popular_pins_own_write`, requiring row `user_id = auth.uid()`.
- `authenticated INSERT` on `public.finance_requisition_thresholds`: controlled by `finance_req_thresholds_write`, requiring the admin role; a seeded finance user was denied.

**These are illustrative tests of three among the previously identified 77 authenticated DML privilege differences, not a recommendation to restore all three in production.** Actual deployed callers, security policy, functionality needs and release authority must be reconciled before any targeted grant is proposed for production.

The previously confirmed `anon SELECT` gap for `stock_item_images` remains separately proven by reversible **401 → 200 → 401** PostgREST behavior and unchanged source RLS. The four legacy RPCs again resolved to application exceptions `P0001` for deliberately invalid inputs. Those checks do **not** prove positive POS sale settlement or payment flows.

## Test cleanup and verification

On completion:
- **13/13 original migrations** and **17/17 original native business smoke suites** passed.
- **12 prior HTTP role checks**, **10 synthetic row-level read/isolation checks**, **20 new write/isolation/rollback checks** passed.
- All **11 original Supabase production containers remained healthy and unchanged**, with zero disposable PostgreSQL and zero disposable PostgREST containers retained.
- The temporary fixture-only INSERT grants were expressly revoked, with SQL privilege denial rechecked before destroying the test DB.
- No existing VAN/VATI production service or hosted Nissan GTR database was changed. No business data, token, password, user identifier or live payment was copied.

The SHA-bound receipts, test observer and transactional module are under `evidence/2026-11-09-stateful-http/`. `tools/gtr_postgrest_stateful_gate.py` is a non-executing, source-bound evidence checker that rejects altered HTTP observations, absent rollback or cleanup, cross-user authorization regressions, unknown source images and any attempted release claim. It **always** returns production/canary/cutover admission as false, even for a green test. `tests/test_gtr_postgrest_stateful_gate.py` contains targeted pass/fail and per-request mutation-detection tests.

## Next production gates

1. Review the actual web/mobile/POS/HR/finance client call paths and tenant security impact before granting any of the **77 authenticated DML** privileges; the three fixture tests do not establish business necessity.
2. Qualify exact API/RPC function behavior for real **synthetic** POS sales, payment settlement and HR onboarding without real payment or notification providers. Resolve 418 changed textual function fingerprints, four changed signatures, one view and 13 additional RLS policies.
3. Complete real hosted data/roles/Auth/session/Storage/R2 backups and recovery, Edge function/provider secret custody, four active hosted scheduler jobs, issuer isolation and coherent shared-service ARM64 deployment.
4. Resolve the earlier **explicit live-canary execution refusal only with the original owner admission authority**. No test-side GRANT or direct VM access authorizes live activation or Nissan GTR cutover.

**PR #102 remains draft/unmerged until real native Zuul/Project Truth and signed production gates pass.**
