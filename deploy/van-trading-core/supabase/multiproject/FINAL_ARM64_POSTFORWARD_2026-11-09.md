# Nissan GTR final ARM64 schema — isolated real replay and hosted compatibility gate

**State: REHEARSAL GREEN; HOSTED PARITY BLOCKED; PRODUCTION UNCHANGED.**

## Provenance and isolation

The original hash-verified ARM64 PostgreSQL 17.6 replay runner (`11c80c443789437ac5fd4515d07008c37221774f6f2350fd4d4deda9b2055c41`), original contract reader (`1c2ad1b487394d1a0e4ea8fded5b119799bc76bde444db3d6148874ae07928e5`) and 13 exact Nissan GTR migrations from source `8131858c7c7479d178cbe9e246f83cb49ed80f5e` were reused **unmodified** on `van-trading-core`. The previous refusal of a *different guarded runner transfer* was not retried, disguised, or bypassed.

A separate, source-hashed **read-only observer** captured metadata immediately after the last migration completed, before the test runner proceeded through its smoke suites. Its script is retained under `evidence/2026-11-09-postforward-arm64/observer-used.py.txt`, SHA-256 `3d0d85503fc5b99d33f847801a8b92babee51e278399673118a517e970a1db2b`. This observer never connects to hosted Supabase, production VAN, or the network.

The disposable ARM64 PostgreSQL container had network mode `none`, no published ports, UID:GID 100:101, 512 MiB container limit, one newly created fixture-only mount, and actual original donor image `sha256:f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00`.

The managed test job `djob_8545e6f4c4d8a43be3a9a104` completed successfully:
- **13/13** original SQL migrations, **17/17** original business smoke suites.
- Source-lock hashes matched all inputs.
- Original **11 Supabase containers** preserved with their identities and start times.
- Temporary fixture container removed, zero `dial.gtr.schema-replay` containers retained.
- No production SQL writes, no live canary, no cron worker activation, no project deployment.

The post-migration capture is not a baseline estimate; it is the schema observed **after all thirteen migrations**. `postforward-observer-result.json` records the six source-bound scope digests; the full sanitized fingerprint file remains owner-private on the VM with SHA-256 `dd13643eafe8746e00167ffe15420ac097dcb4e048cfb897c81f13cda3702526`, mode 0600. It contains **no SQL bodies, customer rows, tokens or credentials** and was not published here.

## Exact hosted comparison — same scopes and search path

The active Nissan GTR hosted project `bicyjghgdnzlnjqxzoud` was queried only with read-only, repeatable-read catalog queries. `SET LOCAL search_path=public,extensions` matched the original contract reader to avoid spurious type/definition formatting drift. Both databases are PostgreSQL 17.6. The tables, policies, functions, view and role privileges were compared by stable identity and definition/predicate fingerprints, not by rough table counts.

| Scope | Current hosted | Isolated post-forward ARM64 | Result |
|---|---:|---:|---|
| Application tables (`public` + `private`) | 212 | 212 | **All identities/RLS/persistence match** |
| Views | 2 | 2 | One unchanged, `public.v_master_stock` definition fingerprint differs |
| Functions | 760 | 793 | **756 shared, 37 target-only, 4 hosted-only** |
| RLS policies (`public` + `private` + `storage`) | 337 | 350 | **All 337 shared policies match; 13 new only** |
| Permission checks | 5,136 | 5,136 | **1,735 hosted-only effective privileges** |
| Private schema USAGE checks | 3 | 3 | All match |

The canonical table JSONB fingerprint matches in both places: `f73595546fac72bb35237098757fdff0ced1fd3ea4a05f4d2a16cdbaaabf1d85`. The private-schema usage fingerprint matches `a483066c5a6e05c420ecc1e47232e0fe3bd5e376c9d207b4558a5eee36ea2859`. View `public.product_review_aggregates` matches; both hosted and target views retain `security_invoker=true`.

**Policy safety:** Every one of the **337** common policies has identical permissive/restrictive mode, roles, command and SHA-256 of `USING`/`WITH CHECK` expressions; zero existing hosted policies are missing or changed. The **13 additions** are four payroll/finance visibility policies and nine Storage policies for employee photos and vehicle artwork. Additions require explicit acceptance; they do not by themselves prove secure access.

**Function compatibility:** Of the **756** shared identities, **303** match all captured function-definition and execute-grant fields. Of the other **453**, **418** have a changed `md5(pg_get_functiondef())` fingerprint and **131** have changed `EXECUTE` permissions (overlapping sets). These are **textual hashes**, not proof of 418 behavioral defects. The target has **37 additional function signatures** and lacks **four hosted signatures**. Missing old signatures include `create_pos_cart(uuid,uuid,currency_code)` and earlier versions of `create_hr_role`, `upsert_customer_garage_vehicle` and `upsert_staff_product_page`. Those changes may require client/API compatibility shims, not blind restoration.

Among shared function identities the final candidate has **78 fewer `anon` EXECUTE grants**, **58 fewer `authenticated` grants** and **99 fewer `service_role` grants**; one authenticated grant is new. Not all those functions are client-callable Data API endpoints; assess source ownership, function body, RLS, intended policy-helper access and actual callers before changing permissions.

**Table/view access compatibility:** Effective relation-role checks are identical in **176 of 642** relation-role rows. **466** rows differ, spanning **188 relations** and **1,735 individual privileges** present in hosted but not the candidate; **zero** candidate-only effective grants were found. By role: `anon` 590, `authenticated` 359, `service_role` 786 hosted-only. This is a cutover **compatibility blocker**, not a recommendation to grant 1,735 permissions indiscriminately or to revoke production permissions. RLS, provider defaults and actual reachable endpoints must be reviewed together.

## Fail-closed comparator

`tools/gtr_final_schema_gate.py` compares independently supplied, sanitized hosted and post-forward metadata. It checks exact six scopes; schema-object identities and sort order; mandatory definition/predicate fingerprints; allowed role vectors; no duplicate identities; valid boolean access fields; and empty zero-argument function signatures. It rejects missing scopes, unexpected raw SQL columns, unsorted/duplicate rows and incomplete metadata. It has no SQL, SSH, network, Docker, migration or deployment executor.

It returns exact per-identity additions, omissions, definition/predicate/ACL drift and **release authority always false**. The tool was tested with **26 passing unit tests**, and the **real 793-function/350-policy/642-role-row** isolated final-state snapshot was passed to its validator on the ARM64 host. Separately, the existing source test suite passed **415 tests, four skips**; do not represent those skipped optional cases as executed.

Even a future exact hash match does not prove Auth, Storage object bytes, Cloudflare R2, Edge, payment provider, data, 4 scheduled jobs, live client behavior, rollback, or ownership/secret custody. The migration decision must be explicit, with a separate signed admission, tested data restore and verified single-writer cutover.

## Next hard gates

1. Review the 4 missing signatures and changed business/payment/customer functions against actual clients; retain compatible RPC versions or explicitly migrate callers. Analyze the 418 definition-fingerprint changes for meaningful differences, not just formatting.
2. Reconcile all 1,735 hosted-only effective relation permissions and shared-function EXECUTE differences against tenant boundaries, policies and DIAL API/Auth issuer setup. Require negative cross-project tests.
3. Qualify the 13 new RLS policies, one changed view, native Edge/Storage/Auth/cron behavior, and restore **actual** hosted data to independent staging under approved custody.
4. Original refused DIAL live-canary activation must be cleared by its own admission authority. No fallback executor, altered operation or read-only connector can authorize a replay.
5. Keep PR #102 **draft**, await exact-head CI/Zuul/independent review and owner-signed reversible release acceptance.

**This report does not authorize production changes or cutover.**
