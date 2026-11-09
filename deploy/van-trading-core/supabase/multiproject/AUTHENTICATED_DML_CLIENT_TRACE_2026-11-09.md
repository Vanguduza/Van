# Nissan GTR — authenticated DML access source trace

**Result: no new authenticated-role table grants admitted.** This review determines what is supported by pinned source evidence, not what deployed mobile clients or external integrations necessarily do.

## Immutable inputs

- **Active hosted project:** `bicyjghgdnzlnjqxzoud`, accessed through the authenticated Supabase connector, with read-only database metadata queries only.
- **Exact source tree:** `Vanguduza/Nissan-Gtr-Auto@8131858c7c7479d178cbe9e246f83cb49ed80f5e` in a separate sparse checkout. Git HEAD was checked against the pinned commit; no tracked source was modified.
- **Source permission receipt:** `evidence/2026-11-09-rpc-public-read/policy-applicable-grant-losses.json` in this PR, with **78** potential policy-applicable missing role permissions: **one anon SELECT** and **77 authenticated DML** entries.
- The **77 authenticated cases cover 30 distinct public tables**: 27 INSERT, 27 UPDATE and 23 DELETE. A matching RLS policy is evidence of a permitted *row-level pathway* if the role also has the required SQL privilege, not proof of an active/legitimate direct client write.

## Pinned caller scan

`tools/gtr_client_dml_trace.py` verifies the source Git HEAD, source cleanliness, tracked/materialized source completeness for the enumerated application/service scopes, exact project/source permission receipt, row identity counts, role/command grammar, policy bindings and non-release status. It statically scanned **1,291 tracked source files** across web, Android, iOS, Edge Functions, shared packages, integration bridges, services and supporting pipeline scripts.

The literal-table client query scan found **no direct INSERT/UPDATE/UPSERT/DELETE calls from a user-session client against the 30 affected tables** in those scanned files. It found **two explicit write call sites against `staff_roles`**—one DELETE and one UPSERT—in `scripts/provision-canonical-staff.mjs`. The script uses a server-side Supabase secret/service-role key and an admin `createClient`, and is a privileged staff-provisioning script, **not evidence that a normal authenticated client needs direct table write permissions**.

The 78-item source-trace report classifies **75 cases with no static direct write call** and the **three `staff_roles` permission cases with those two administrative call sites**. It deliberately sets `automatic_grant_allowed=false` for every item. It does not execute, render, recommend or apply any grant.

Existing clients instead show numerous direct SELECTs and `.rpc(...)` calls. Examples include finance/account balances, HR grades/roles/onboarding, POS quotations and catalogue hierarchy. These client calls may depend on function execution grants and the correct function security context, so they require authenticated PostgREST testing rather than blanket table-grant restoration.

## Hosted invoker-function references

A second bounded **READ ONLY/REPEATABLE READ** query inspected hosted PostgreSQL function metadata without invoking the functions or returning SQL function bodies. A text-only search of `pg_get_functiondef` against the **30** table names found:

| Metric | Count |
|---|---:|
| Tables mentioned by one or more function definitions | 28 |
| Tables with references from authenticated-executable invoker functions | 10 |

Examples include catalogue lookups and finance guard/approval helpers. A textual function reference **does not establish** whether a function performs writes, whether a branch is reachable, whether the caller needs a direct table permission or whether dynamic SQL/cross-function execution exists. This review does not classify those ten tables as safe.

The provider response is retained as *metadata-only* in `evidence/2026-11-09-authenticated-dml-trace/hosted-invoker-review.json`. No SQL body, customer record, token, password or provider secret is published.

## Why no bulk GRANT should proceed

The post-forward ARM64 final schema is intentionally narrower than hosted production in **1,735 effective relation privileges**, of which the earlier policy-aware filter produced **77 authenticated DML candidate gaps**. The pinned source search did not show direct session-authenticated writes that would justify granting all 77.

**Absence of a static literal-table caller is not proof of absence of a caller.** The scanner does not prove behavior for dynamic table names, native SQL clients, stored-procedure/trigger chains, older mobile deployments, Edge security contexts, external integrations or live RPC HTTP routing. Likewise, a row-level policy does not grant SQL table access. We must preserve both existing functionality and isolation, avoiding accidental expansion of authenticated/public privileges.

The only separately tested narrow permission fix remains `stock_item_images` **anon SELECT**, where actual pinned client source uses a direct table query and an existing `anon` RLS policy authorizes public read. That fix exists only as a production-inactive candidate, verified inside a throwaway ARM64 database and rolled back. Do not apply it until the separate original canary admission and release rules are satisfied.

## Reproducibility and controls

- `tools/gtr_client_dml_trace.py`: source-locked **static-only** reviewer, no PostgreSQL/HTTP/SSH/VM deployment executor.
- `tests/test_gtr_client_dml_trace.py`: **27** passing regression and refusal tests for source identity, incomplete sparse checkout, invalid ACL input, JS/Kotlin direct calls, dynamic references and non-release guarantees.
- **Complete exact-head candidate Python suite: 452 tests, four optional skips, zero failures or errors**, after adding the 27 new source-trace tests. Two pre-existing test harnesses (`test_gtr_final_schema_gate.py` and `test_gtr_public_read_plan.py`) had wrongly read source files from `tests/` rather than `tools/`; the regression tests now locate the canonical `tools/` files and pass in a clean checkout.
- Original 13-migration ARM64/17-business-smoke evidence, hosted ledger reconciliation and prior exact 337-of-337 RLS-policy comparison remain separately retained.

**Next admission work:** reproduce RPC and representative authenticated user workflows via nonproduction PostgREST/Auth; check function invoker/definer and table privileges on real caller paths; validate known deployments, then classify each of the 77 as intentionally restrictive, function-mediated, or a true missing direct privilege. No change to production SQL, DIAL containers, the four hosted cron jobs or actual user/Storage/R2 records. The earlier DIAL canary activation refusal remains in force. PR stays draft and unmerged.
