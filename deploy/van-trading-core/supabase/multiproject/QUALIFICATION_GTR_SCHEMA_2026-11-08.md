# Actual GTR source replay on the ARM64 donor image

## Completed result

**All thirteen source-locked Nissan GTR migrations applied; all seventeen upstream SQL business smoke suites passed.** The baseline reproduced every entry in its original contract: **212 tables (210 public + 2 private), 769 function definitions and role capabilities, 341 RLS policies, 5,136 relation-permission entries, two view definitions/options and three private-schema access checks**. All categories matched exactly. No relaxed or normalized acceptance rule was used.

The expanded Python source suite passed **322 tests**, with zero failures/errors/skips; 27 are new migration-context/contract regressions. A separate source-only check generated all thirteen guarded plans and reversed their context wrappers back to the exact source bodies (apart from the five previously documented central-cron changes). That newer guarded plan is not claimed as the executed native runner.

## Actual environment, not a simulated platform

The successful native job was `djob_68ba52d46c5bb3d20b47851b` on `van-trading-core`, using the already-installed **ARM64 Supabase PostgreSQL 17.6** image `sha256:f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00`.

A fresh temporary container used ordinary PostgreSQL UID/GID 100:101, a read-only image, dropped Linux capabilities, no-new-privileges, 512 MiB memory, 0.5 CPU and 128 PIDs. Its only writable persistent mount was a newly created fixture directory; `/tmp` was a bounded tmpfs. Docker networking was **none**, with no published port or mounted production data/key volume. A separate temporary server here is a verification fixture, not a second installed Supabase stack.

The live donor was used only for read-only schema/catalog export. The fixture restored actual native `auth` and `storage` DDL from that donor, along with non-secret role attributes, memberships and explicitly selected role defaults. No donor rows, password verifiers, Auth credentials, Vault keys or business records were copied. The observed donor services were Auth 2.196.0 and Storage 1.74.0; their schemas had 77 and 70 migration entries respectively. No Auth/Storage HTTP service was started by this SQL replay.

Native pgcrypto, uuid-ossp, pg_net and Vault extensions were used. `pg_net` was preloaded because the real extension requires it; the container had no external network. Cron execution was disabled, and the application's four schedules were not installed or activated. This cannot send a real payment, SMS, email, webhook or R2 request.

## Exact source and execution context

Inputs are the thirteen checked-in migrations at `Vanguduza/Nissan-Gtr-Auto` commit `8131858c7c7479d178cbe9e246f83cb49ed80f5e`, 4,139,260 bytes, bound by the previously committed SHA-256 source lock. The 4,027,262-byte baseline was adapted only by the existing five-edit scheduler splitter: one pg_cron installation directive and four schedule statements were separated. All application SQL bodies, function definitions, policies and data declarations remain intact. The Nissan GTR repository was not modified.

The donor's ordinary `postgres` SQL role is not a superuser and does not own native Storage tables. An initial unmodified-role replay correctly refused `CREATE POLICY` on `storage.objects`. The successful fixture therefore used the real platform-owner context only for two exact source regions: the baseline's native Auth hook/Storage policies/bucket metadata, and the staff self-service migration's employee-photo bucket/policies. Application definitions ran under `postgres`, not a newly privileged application login. No permanent platform-role membership was granted and no native Auth/Storage table owner was reassigned.

`tools/gtr_migration_plan.py` now prepares those exact source-bound contexts and additionally refuses default/system database targets. Its output requires the specified fresh target database and the original `supabase_admin` platform context. It does not connect to a database, discover credentials, create a role, grant execution permission or resolve a refused operation.

**Evidence distinction:** the successful native job used the recorded fixture runner in `runner-used.py.txt` and `contract-reader-used.py.txt`. A subsequent attempt to transfer a reusable guarded refactor was safety-refused before execution. It was not retried, disguised or redirected. Target readback confirmed that neither the new runner nor the new compiler was copied there. The unexecuted refactor is retained privately outside the tracked source; the published pure compiler has unit and source-body-reversal proof, not a new native execution receipt. Recorded runner hashes were read back after the successful job; this is not a Root-signed source-admission claim.

## Native checks and business coverage

The baseline contract was compared before applying its twelve forward migrations, using PostgreSQL's actual definitions, effective role capabilities, policies, persistence/RLS flags and pretty-printed view definitions. All thirteen migrations then completed successfully. Their application changes are validated by the upstream critical smoke suites, not by incorrectly expecting the pre-forward baseline contract to remain unchanged.

The original local-development seed was loaded only into the isolated fixture to create synthetic users and records. The seventeen source-pinned suites cover baseline/Storage policy contracts, RLS, finance, inventory, POS discovery and vehicle context, customer garages, hidden/popular products, vehicle artwork, payment settlement, web/POS sale flow, retained posting workflows, staff self-service, payroll, merchandising and overview behavior. External provider APIs, browser/mobile clients and live commerce were not exercised.

The upstream verifier's own fixture handling was retained: test identity helpers moved to temporary schemas with scoped grants, and each suite was wrapped in BEGIN/ROLLBACK. These are database business-function tests with synthetic data, not a customer-data import, full web/mobile end-to-end test or a verified live financial settlement.

## Failures retained and corrected without weakening product policies

1. The first fixture omitted pg_net from preloaded libraries; native extension creation refused. Only the disposable server's preload configuration was corrected.
2. Running the baseline under the non-owner `postgres` role refused Storage policy DDL; the two exact native-owner regions were separated rather than granting broader privileges or changing table owners.
3. The initial comparison read `relkind` instead of the contract's `relpersistence`, and used non-pretty view output. Reading the correct catalog fields reproduced all original contract values exactly.
4. The first seed attempt lacked the donor's native `extensions` search path. Explicitly allow-listed, non-secret donor role settings were restored; source seed/functions were not rewritten.
5. Native and source-publishing attempts remain separate. A blocked code-transfer command did not execute; no successful native result is attributed to that unexecuted refactor. Two read-only evidence-collection scripting errors were corrected without repeating a production effect.

All earlier native failures remain FAIL in `attempts.json`; only `attempt-c1c5e608df/result.json` is the successful source replay.

## Preservation and cleanup

Every temporary container was removed. Independent readback confirmed that all eleven original Supabase containers retained their IDs and start times and remained healthy, and the live cluster still had only `_supabase` and `postgres`. No application database, public endpoint, HBA change, service restart, cron job or systemd drop-in was deployed.

After verifying container absence and each recorded attempt identity, only this operation's five temporary data directories were removed. Source inputs and non-secret diagnostics remain available for review. No original mounted database, Storage directory, encrypted backup or unrelated process was removed. This is normal fixture cleanup, not certified secure erasure.

## Retained evidence and remaining gates

`evidence/2026-11-08-gtr-arm64-replay/` contains the native result, exact baseline comparison, donor schema observation hash, input/test hashes, original failed outcomes, actual runner text, cleanup/readback, source-only plan check, 322-test output and source/evidence manifest. No native schema dump, data directory, fixture Auth password, SQL connection credential or provider secret is committed.

This closes **fresh GTR SQL compatibility against the observed ARM64 donor schemas** under explicitly separated migration-owner contexts. It does not reconcile the current hosted migration ledger or migrate hosted users/data. Real hosted backup/history comparison, operator-admitted live canary, per-project runtime role/HBA isolation, production images/lifecycle, real Auth/providers/rotation, active-writer recovery and reversible GTR cutover remain required. The original live-canary refusal remains unresolved. Keep PR #102 draft.
