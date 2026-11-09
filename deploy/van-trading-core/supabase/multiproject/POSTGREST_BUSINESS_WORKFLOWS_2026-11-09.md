# Nissan GTR — positive HTTP business workflows on ARM64

The existing candidate completed 23 new real PostgREST RPC requests and 16 database invariant checks in a disconnected, disposable ARM64 database. All 13 original migrations, 17 original business SQL smoke suites and the earlier 42 HTTP checks also passed in this run. No application grant, production database, live service or hosted customer data was changed.

## What is now demonstrated

| Workflow | Actual outcome |
|---|---|
| POS sale as sales-only cashier | Created cart, added three units at $48.25, selected published vehicle, parked/resumed, opened/attached till and reserved checkout |
| Manual split settlement | $100 cash + $44.75 bank posted one invoice and two payment-entry legs |
| Retries | Checkout returned the original order; settlement returned the same invoice and same payment entries; stock remained seven from the original ten units |
| Accounting | All journal entries balance; an unpaid reservation has no invoice; cashier direct journal posting remains denied |
| Negative POS checks | Customer cannot add a cart line; unpublished vehicle, $200 over-tender and unverified EcoCash tender rejected with P0001 |
| HR | Administrator created a role while direct authenticated INSERT on hr_roles remained denied; customer role creation rejected |
| Garage | Customer created and partially updated their vehicle; another customer's attempt was denied; original chassis/model identity retained |
| Merchandising | Admin updated product pricing; customer update denied and $48.25 price retained |
| Privileges | Effective authenticated INSERT/UPDATE/DELETE privilege fingerprint unchanged across every public ordinary/partitioned table |

## Execution and transaction boundary

Native managed job `djob_6d2dab1b18fa9242fb789390` succeeded with exit zero on `van-trading-core`. PostgreSQL 17.6 and PostgREST 14.17 used the same exact ARM64 images and unchanged original replay runner as the previous checkpoint. Nissan GTR source remains `8131858c7c7479d178cbe9e246f83cb49ed80f5e`; candidate parent is `8d55570a0d0fd713f2508025da65fba0e39c7948`.

The new test module independently checks the exact temporary DB image/user/mount/attempt label and sidecar network/PID/label bindings. The database has network mode `none`; the sidecar shares only that disposable namespace and publishes no host ports. It cannot reach external payment or notification providers.

Unlike the previous single-request rollback tests, these positive workflows require state to survive between requests. The private sidecar uses `PGRST_DB_TX_END=rollback-allow-override`; only the new business calls send `Prefer: tx=commit`, and each successful response must acknowledge `Preference-Applied: tx=commit`. The earlier 42 checks retain default rollback semantics. Committed synthetic state exists only inside this disposable database, which was subsequently destroyed. This is database destruction after a workflow, not a claim that all new HTTP calls were rolled back individually.

The exact test source, observer, sanitized HTTP results, original replay receipt and console are retained in `evidence/2026-11-09-business-http/`. The module is also installed as `tests/business_http_probe.py` for reuse by the isolated replay observer. It has no production installer or credential discovery. Synthetic JWTs are passed privately to curl via stdin; response bodies and tokens are not retained in evidence.

The original runner independently verified all eleven live Supabase containers were still healthy with their original IDs/start times and removed the temporary database. The sidecar cleanup succeeded. An additional direct readback found zero replay/HTTP containers and all eleven original healthy services.

## Storage cleanup

Removed 807,553,399 logical bytes of completed synthetic replay data from eight old attempts, after validating each retained result reported its container removed and no current Docker mount referenced the data. Every result/log/source file remains. Removed cached package downloads with `apt-get clean`. Available root disk increased from approximately 3.1 GB to 3.9 GB (94% to 92% used). Existing images are all in use; no application image or Docker volume was pruned.

## Remaining production work

These results establish positive HTTP business behavior under existing grants for the exercised paths. They do not justify restoring the 77 historical authenticated write grants, establish all 30 affected tables' workflows, or prove old/dynamic external clients. They also do not prove HR employee onboarding/payroll or provider-mediated payment settlement.

Real GoTrue login/issuer isolation, shared-service ARM64 coexistence, hosted rows/Auth/Storage/R2/Edge/provider-secret recovery, four hosted cron jobs, coordinated active-writer rollback and exact release/Zuul admission remain outstanding. Real external payments were not made. The prior explicit live-canary safety refusal is retained; this fixture is not a retry of that operation and grants no release authority.

The exposed estate deployment recipes were independently read on 9 November; none is a Supabase release recipe. Generic Root connectivity does not supply a missing Supabase release acceptance. PR #102 must remain draft and unmerged until those outstanding gates are satisfied.
