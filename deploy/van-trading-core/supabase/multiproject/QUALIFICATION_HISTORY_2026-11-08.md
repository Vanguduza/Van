# GTR history reconciliation — isolated qualification

**Final result: 367 Python tests passed, 37 native PostgreSQL capture/reconciliation checks passed.** No failures/errors/skips in the final source suite. This continues immutable parent `927f7e374261e6de750b2db36fedfdf6205574e2` on the existing draft Supabase PR #102.

## Completed

A non-deploying history reconciliation utility now verifies the pinned Nissan GTR baseline provenance, retains legacy/exported-hosted/current histories separately, emits a bounded read-only ledger query and compares supplied captures without a database connection or credential. Forty-five new unit tests cover scope, input/output custody, source digests, retired-project refusal, opaque IDs, duplicate/truncated/invalid data, conflicting hashes and content uncertainty.

All **313 actual input files (311 SQL + manifest + source contract), 7,898,022 bytes**, matched their retained source SHA-256 values. The catalog contains **173 legacy, 125 exported-hosted and 13 active migrations**, with **271 curated reconstruction bindings**. All ten overlapping historical version IDs have distinct raw SQL hashes; this is not a finding of semantic SQL inequality. Existing source files and the Nissan GTR repository were not modified.

The actual capture query ran against a **new disposable PostgreSQL 17.11** instance as a restricted observer, with no production/cloud endpoint accepted. It returned one metadata-only JSON result under READ ONLY/REPEATABLE READ and did not expose stored statement text. It detected mutation/deletion/duplicates in synthetic fixture ledger rows; refused unavailable or changed column definitions, RLS filtering and views; rejected a real truncated 10,001-row capture; and preserved the fixture's business sentinel and observer's unprivileged role.

The new source is pure offline tooling. The native runner is an explicit fresh-fixture test, not the previously refused production-canary or guarded ARM64 migration runner. It neither repeats nor substitutes for either refused action.

## Execution and provenance

Source execution used ordinary UID1000 on `dial-control` through authorized TetherBound, with staged PG17 binaries and a private Unix socket, no network listener, Docker daemon, system package installation or raised host resource cap. Public source acquisition was a bounded 256-MiB, 50%-CPU managed job. Its original job identity and command digest are retained in the evidence. Source acquisition was not a Supabase Cloud login or query.

The original unchanged stage-1 native run passed 34 assertions; the source-content-variant extension passed 35; the final real-table/RLS/schema-stability guards passed 37. These are successive source revisions, not failures or summed assertions. All original results are recorded as such. The earlier scheduler/source-migration tests are preserved separately.

## Evidence

`evidence/2026-11-08-hosted-history/` retains the actual source acquisition receipt, source-only catalog/summary, exact generated capture query, final 367-test log, 37-check native result/log, attempt/source hashes and independent cleanup observations. No actual hosted ledger, raw stored SQL, customer row, password, provider token or backup key was committed.

The generated query contains an expected-project assertion and correlation nonce, neither of which independently proves the connected database's project. The reviewer deliberately never claims authenticated hosted identity, SQL/schema equivalence, repair approval, target admission or migration completion. Hashes provide exact content identity, not authority.

## Not done

No current hosted Supabase ledger or schema was read because no authenticated hosted connection is available. No migration repair, reset, baseline marker insertion, production canary, application-data transfer, provider call, payment operation, GTR/retired-project deletion or service restart was performed. No new project database or endpoint was deployed on `van-trading-core`.

Matching all thirteen source migration versions would still not prove a populated hosted schema/data match. A fresh authenticated hosted capture, full schema/ACL/data comparison and reversible recovery/cutover remain mandatory. Keep PR #102 draft and preserve the original live activation refusal.
