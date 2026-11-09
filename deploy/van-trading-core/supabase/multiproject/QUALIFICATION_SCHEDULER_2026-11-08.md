# Real shared scheduler and GTR baseline adaptation qualification

## Result and scope

**295 Python tests passed; 56 real PostgreSQL/pg_cron checks passed.** The Python suite includes 25 new scheduler contract tests. This is not another run of the previous 681-service integrated rehearsal, and those overlapping totals must not be added as a production score.

Execution: ordinary `ubuntu` UID 1000 on `dial-control`, in a new disposable PostgreSQL cluster. The managed runner enforced a 384 MiB memory ceiling and 50% CPU quota. No live database, Docker container, systemd unit, production HBA, application data, credential or canary was modified. The target was queried only through an explicit read-only SQL transaction.

## Native proof

The fixture loaded the genuine PGDG pg_cron package `1.6.8-1.pgdg24.04+2` into an independently extracted private PostgreSQL 17.11 toolchain. No package was installed system-wide and no older test toolchain was overwritten. Downloaded bytes matched the official HTTPS package-index SHA-256; repository signature verification is not asserted.

One central extension dispatched jobs to two application databases through native background workers. Four synthetic functions per database used the original GTR job signatures, including the default date argument. All eight jobs began disabled and produced no effects until explicit test-only activation. They then recorded the exact selected database and restricted session role. No project-local cron extension was installed and a second installation was explicitly rejected.

The native checks covered original project identity, initial NOLOGIN roles, required HBA reject prefix/reload, refusal of role/activation replay, blocked client connections, denied cron-table/scheduling access, exact original schedules, mismatched timezone refusal, duplicated native UPSERT prevention, foreign database CONNECT denial, ungranted table denial, and absence of superuser jobs. An extra private function exposed by PUBLIC EXECUTE caused the grant transaction to refuse and roll back. The legacy fixture's original contents and ACL were unchanged.

Foreign database CONNECT denial in the fixture uses explicit restrictive SQL grants. The live donor still grants PUBLIC CONNECT to its original databases. HBA does not protect native background workers: effective database permissions and protected central registration must be independently reviewed before production, rather than extrapolating that fixture check to the original donor.

## Source adaptation proof

Thirteen active migrations were fetched from immutable Nissan GTR commit `8131858c7c7479d178cbe9e246f83cb49ed80f5e` and checked against their exact Git blobs. The 4,027,262-byte baseline SHA-256 was verified. Only five exact statements were moved out: the pg_cron CREATE EXTENSION and four cron.schedule statements. Reversing the recorded changes reconstructs the original bytes, and all other SQL remains unchanged.

This does **not** prove that the full 4 MB baseline and twelve forwards run against the DIAL donor or match the current hosted migration ledger. Native Auth/Storage versions, pg_net/Vault, source ACL/function owners, real data, R2/payment behavior and rollout history remain open. The original Nissan GTR repository and hosted service were not changed.

## Real target observations

The original `van-trading-core` query showed `cron.database_name=postgres`, `cron.timezone=GMT`, background workers OFF, max-running-jobs 32, superuser-jobs ON, max-worker-processes 8, and no installed pg_cron extension in `postgres`. The proposed background-worker mode therefore requires separately admitted target configuration. No extension or startup setting was created/changed to force a pass. There are still only the original `_supabase` and `postgres` databases.

## Failures, fixes and exact source

The initial 25-test compiler run exposed a quoted empty-search-path serialization error and an assertion that confused `current_setting(..., true)` with active-job registration. Both were fixed while preserving the same restrictions. The first native run passed 38 checks, then failed because pg_cron's alter operation examined the calling superuser when no username was supplied and superuser jobs were disabled. The test now passes each job's exact existing restricted username explicitly for test activation/deactivation; superuser jobs remain disabled. The next native run passed 52 checks. Four further permission/transaction assertions were added, and the final exact source passed 56.

The final managed job was `djob_006721c8b33d6d050b783442`, command SHA-256 `9e6a399da09b9512f591f27cf8b4275183775b4f415673de3347137afad5b062`, terminal exit 0. The failed and intermediate jobs were `djob_1437b21be6c57a6f31f5c0aa` and `djob_f0583bd2046faf9a8f7bdf82`. Original outcomes and source/runtime hashes are retained under `evidence/2026-11-08-scheduler/`.

The final PG process stopped and its temporary files were removed. Any failed private diagnostic fixture is cleaned only after verifying the original operation's completion and absence of its postmaster. The independent cleanup observation distinguishes that from the runner's own flag.

## Disposition

Publish as an inactive, source-bound scheduler/migration candidate on VAN PR #102. Keep the PR draft and the existing live canary refusal intact. The new work does not create a Root/Zuul qualification, authorize applying the generated SQL, enable production jobs or migrate Nissan GTR. It removes a previously unhandled source compatibility gap while preserving the one-installation design.
