# Project recovery and restart qualification — 4 November 2026

## Verified result

**79 tests passed with zero failures/errors/skips. 157 real-service checks passed.**

This advances the existing single-installation Supabase candidate from the 101-check Auth/API core to an actual per-project logical backup, fresh-database restore and restart drill. It continues PR #102 from `58e7040342bfd7137fb9227d9709fd4287172574`; it is not a production deployment or a new Supabase stack.

The 157 native checks include the original 101 database/Auth/REST assertions plus 56 recovery and restart assertions. The 79-test suite includes the prior tests and 30 recovery contract tests; four of the retained tests intentionally use labelled HTTP stubs. The separate 157-check drill uses real PostgreSQL, GoTrue, PostgREST, Nginx, pg_dump and pg_restore.

## Execution and preservation

Execution was on `dial-control`, ordinary user UID 1000, in the existing isolated candidate workspace. The test created a new private temporary PostgreSQL 17 cluster with two independent project databases and a synthetic legacy database. It never connected to production VAN/VATI or Nissan GTR Cloud.

Native versions remained PostgreSQL 17.11, Auth 2.196.0, PostgREST 14.17 and Nginx 1.24.0, on amd64. Existing package provenance remains in `tests/rehearsal-binaries.lock.json`; additional pg_dump/pg_restore/psql executable hashes are in the native report. No root elevation, system package installation, Docker socket use, firewall change, live service restart, branch merge or production cutover occurred.

All processes created by the successful run were stopped. Its temporary databases, passwords, JWTs and logical archive were removed after verified cleanup. Earlier failed attempts also completed process cleanup; their non-secret failure records are retained and private fixture data is removed separately. No archive containing Auth data is committed.

## Demonstrated recovery behavior

The selected project's Auth and REST services were stopped while a neighbouring project remained available for a real API read. Restarting the selected services retained the original user UUID and password login; the neighbour's full fixture database fingerprint was unchanged.

The selected project was then quiesced for backup. A real read-only repeatable-read transaction observed its UUID, issuer, database and PostgreSQL cluster system identifier and exported a snapshot. pg_dump used that exact snapshot. The backup was private and completed only after archive verification and durable manifest publication. A wrong-cluster observation failed without a completed backup manifest.

Verification rejected another project's identity, the wrong manifest digest and a byte-corrupted actual PostgreSQL archive. The verified restore input is copied to an immutable sealed Linux descriptor; unit tests proved that editing the source archive cannot change that descriptor and that writes/truncation to it fail. The implementation bounds capture and verified readback to 256 MiB and capture time to 120 seconds; larger production sources need a separately qualified immutable custody route and budget.

Restore planning refused all active/protected databases. A new quarantined database was created from template0 with connections disabled while PUBLIC access was revoked. Preflight verified the exact cluster, target, owner, emptiness and restrictive grants. Existing-target replay, a table-obstructed target, a function-only target and a publicly connectable target were refused. Both projects' application logins were unable to connect to the quarantine database.

A real pg_restore completed with exit-on-error and single-transaction semantics, without clean/create/owner-stripping/ACL-stripping flags. The test compared every fixture table's row count and content digest, effective table ownership and ACLs, and public RLS policies against the backup source. They matched. The source database was untouched by the restore and retained afterward.

The neighbour successfully wrote data while recovery proceeded. Only after checks passed did the disposable test change the selected project's HBA destination and Auth/REST DSNs. The restored Auth refresh session, original user UUID, password login and REST/RLS behavior worked. Foreign JWTs were still rejected. New project logins to the retired source DB were refused; its data remained available to the isolated fixture administrator. The neighbour's write survived the switch.

Finally, the temporary shared PostgreSQL server was restarted. Both real connection pools recovered without recreating databases; each project's API and password login worked, the cross-project HBA boundary persisted, and the synthetic legacy data and ACL remained unchanged. **This proves restart recovery, not independent availability: a shared PostgreSQL restart is a shared outage.**

## Failures preserved and corrected

The first attempt passed 133 checks, restored successfully, and failed the comparison because PostgreSQL can represent the same default table ACL as NULL or as an explicit owner-only ACL. The comparator was corrected to compare `aclexplode(coalesce(relacl,acldefault(...)))`, not textual storage representation. No runtime grants or restored data were changed to make the comparison pass.

The second attempt passed 149 checks but the restart harness timed out because the restarted server inherited the captured subprocess output pipe. The harness now directs restarted PostgreSQL output to its own private log using pg_ctl's `-l` option. This is a harness correction, not a production service restart or an extended Root deadline. A subsequent complete run passed 156 checks, followed by the final bounded-archive/function-target tests and the 157-check pass.

All failed runs retained their actual failure and cleanup status. None was relabelled as successful or excluded from the failure summary.

## Source and evidence

- `tools/recovery.py`: real read-only logical capture, scoped archive verification, sealed restore input and non-executing fresh-target plan.
- `tools/bootstrap.py`: administrator-owned project recovery identity marker; API roles denied marker access.
- `tests/rehearse_recovery.py`: real recovery/restart extension to the existing disposable harness.
- `tests/test_recovery.py`: 30 contract tests, including tamper, symlink/hardlink/private-mode, bounded stream, timeout and no-apply boundaries.
- `evidence/2026-11-04-recovery/native-result.json`: all 157 checks, exact native/source hashes, cleanup and exclusions.
- `evidence/2026-11-04-recovery/native-run.txt` and `unit-tests.txt`: complete recorded passing outputs.
- `evidence/2026-11-04-recovery/source-manifest.json`: tested source/evidence identities and validation commands.
- `evidence/2026-11-04-recovery/attempts.json`: non-secret history of earlier outcomes.

These are actual non-root remote-host observations, not Root-signed Native admission, independent review or exact-source Zuul acceptance. Historical evidence from the earlier checkpoint remains unchanged.

## Production gaps still open

The live VAN administrative check initially returned `ROOT_INGRESS_RECORD_EXPIRED`. The legitimate qualification challenge reached `LIVE_CALL_OBSERVED` but still required Root confirmation; the later read-only estate status call timed out. Neither grants deployment authority. No privileged production route was bypassed.

Production still needs fresh target-VM access/capacity evidence, actual donor/container/architecture qualification, canonical Compose startup integration, encrypted off-host backups and restore at actual data volume, WAL/PITR, and explicit custody of cluster roles, project secrets, configuration and object storage. Logical dumps do not contain those entire external dependencies.

The new backup files are private but not encrypted, and the temporary archive was deleted after the drill. No scheduler, persistent backup service, automatic production restore or automatic routing switch was installed. The manifest digest must be retained outside the editable bundle by the existing protected owner/audit mechanism. Trusted-source review is still required because restored SQL can execute source-defined code.

Auth recovery rewinds session/password state. Production must address post-backup password changes, deleted users and token revocations, and may need project-only rekeying or forced reauthentication before reopening. The successful preserved-session test is not permission to resurrect revoked sessions.

Storage, Realtime, Edge Functions, Studio, Supavisor, TLS/CORS/quotas, provider Auth flows and the actual Nissan GTR migration/business-flow/rollback rehearsal remain open. REA remains optional research.

**Disposition: per-project logical recovery and restart behavior demonstrated in isolation; keep PR #102 draft and production unchanged.**
