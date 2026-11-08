# DIAL Supabase — one installation, independent database/Auth/API projects

## Hosted-history reconciliation checkpoint

The expanded suite now passes **367 Python tests**. The new pure `tools/gtr_history_reconcile.py` accounts for **173 legacy, 125 exported-hosted and 13 active migrations**, verifying all **313 actual source inputs** and 271 reconstruction bindings against retained hashes. Ten historical version/name pairs have differing raw SQL-file bytes across the two source histories; metadata-only version matching must not silently choose either copy or claim semantic identity.

A **37-check real PostgreSQL rehearsal** demonstrated bounded read-only ledger capture, changed/removed history detection, RLS/view/truncation refusal and no stored-statement disclosure. It used synthetic ledger records in a new unprivileged fixture, not the hosted application. The source files were hashed, not replayed. No current hosted ledger is claimed: an authenticated hosted connection is still unavailable here. See `HOSTED_HISTORY_RECONCILIATION.md`, `QUALIFICATION_HISTORY_2026-11-08.md` and `evidence/2026-11-08-hosted-history/`.

The existing ARM64 migration replay and business SQL results remain separate valid evidence. The new tool cannot execute migrations, repair history, authorize a release or retry the refused canary. Live project activation and Nissan GTR migration remain blocked on their original permissions and independent acceptance requirements.



## Nissan GTR scheduler/migration compatibility checkpoint

The source-locked GTR fresh baseline installs pg_cron per application database, which is incompatible with a single-cluster multi-project layout. `tools/shared_scheduler.py` now separates exactly that extension statement and four schedule registrations, preserving all other baseline bytes, into an inactive central-scheduler candidate. It supplies project-scoped roles, deny-only HBA guards, exact function grants, duplicate-job refusal and database/timezone-bound native registrations. No second PostgreSQL server or scheduler service is added.

**295 Python tests and 56 real PostgreSQL/pg_cron checks passed.** The scheduler test executed synthetic functions in two databases through one real native cron extension. It did not execute GTR business functions or all thirteen migrations. The actual target has cron configured for `postgres` but no extension installed there and background-worker execution off; adoption requires separate original-owner configuration/release qualification, not a guessed live change. See `SHARED_SCHEDULER.md`, `QUALIFICATION_SCHEDULER_2026-11-08.md` and `evidence/2026-11-08-scheduler/`.

**Status: ALL shared native services ran concurrently on one disposable PostgreSQL server. The final integration passed 681 real-service assertions; 245 Python tests, eight Node tests, 26 complete Compose-model checks and 28 canonical-lifecycle checks also passed. No live VAN deployment or Nissan GTR migration has occurred.**

The owner requirement is one existing managed Supabase installation on `van-trading-core`, one PostgreSQL server, and independently functioning application databases and authentication environments. The candidate does not add a PostgreSQL server, VM or complete Supabase stack per project. It adds small project-specific Auth, REST and router services to the existing Compose model and reuses one shared Storage, one shared Realtime and one existing Edge Runtime service. The candidate also reuses the original Supavisor, Studio and Meta services behind one private project-administration gateway. Production rollout, actual operator-issuer integration and full Studio coverage still need qualification.

**REA is optional research support, not an execution or release prerequisite.** The owner authorized direct implementation. No REA investigation result is claimed or needed for the tests below.

## Complete installation integration and guarded lifecycle

The previous component-by-component limitation is now closed for a bounded native HTTP/data-plane workload. Thirteen actual service processes (two Auth/REST/project gateways and one each of Storage, Realtime, Edge, Supavisor, Meta, original Studio and private admin) remained alive concurrently around the SAME PostgreSQL server.

A real authenticated Edge function wrote a row and an object through its own project APIs; Realtime delivered that exact row; Storage, Supavisor and Meta returned the matching data. Concurrent probes preserved the same live process identities. Selected Edge/pooler outages did not take down the other services, did not reroute failed requests, and replaced only the intended process on restart. The synthetic legacy database and existing 768 MiB cgroup cap were preserved. This is a small integration test, not production throughput or simultaneous browser-rendering acceptance.

`tools/compose_lifecycle.py` now binds both startup and shutdown of the existing `vati-supabase.service` to the same complete Compose/project/env model, with checksum guards and original-unit/source checks. The compiler never applies the drop-in, changes systemd or grants Root authority. The actual systemd parser and checksum verifier accepted correct private inputs and refused missing/tampered ones. See `CANONICAL_LIFECYCLE.md` for the original-owner release contract.

Current evidence: `QUALIFICATION_INSTALLATION_2026-11-05.md` and `evidence/2026-11-05-installation/`. This supersedes earlier guide statements that all components had only separate native coverage; earlier dated qualification files remain accurate historical records. The real target architecture, images, credentials, operator issuer, off-host recovery and Nissan GTR migration remain unqualified. Counts overlap and must not be added across milestones.

## Actual target recovery checkpoint

The real ARM64 `van-trading-core` donor now has an encrypted, off-host-verified pre-migration snapshot. A network-isolated native restore passed 17 checks; canonical SHA-256 comparisons matched all 57 application tables and role password verifiers. Original containers remained healthy and unrestarted, and a temporary local replication HBA rule was restored exactly. Verified temporary plaintext copies were removed; encrypted copies and separate-host decryption custody remain.

**The live canary command was refused before execution. No new project databases or services were created, and Nissan GTR was not migrated.** See `TARGET_RECOVERY_2026-11-08.md` and `evidence/2026-11-08-target-recovery/`. This is a real target recovery proof, not an active multi-project deployment or release admission.

## Implemented and demonstrated

`tools/bootstrap.py` generates a private, staged bootstrap bundle for fresh project databases. Each project has unique database logins, SCRAM password verifiers, an Auth schema, signing secret, API credentials and gateway configuration. GoTrue performs its real upstream Auth migrations; the code does not imitate its user/session tables. REST keeps standard `anon`, `authenticated`, `service_role` policies and adds an exact project-issuer check.

The native rehearsal creates two synthetic projects in one temporary PostgreSQL cluster, with real Auth, REST and Nginx processes. It exercises independent same-email identities, passwords, refresh sessions, user/service JWTs, RLS ownership, API keys, database login permissions, host/header routing and concurrent requests. The original third fixture database's contents and ACL remain unchanged. See `QUALIFICATION_2026-11-04.md` and the non-secret evidence directory for exact results.

This is stronger than the retained 24 October test suite, which checked Nginx against labelled HTTP stubs only. Neither test is a production-deployment receipt.

## Project recovery milestone

`tools/recovery.py` now captures a real snapshot-bound logical database backup, validates project/cluster identity and externally retained hashes, and generates only fresh quarantined restore targets. It never applies a restore or overwrites a live database. Verified archive bytes are sealed against modification before they can be supplied to pg_restore.

The explicit `tests/rehearse_recovery.py` extends the core rehearsal: restore into a fresh same-server database, compare fixture data/ownership/effective ACLs/RLS, recover Auth credentials and sessions, keep the neighbour usable, and prove both pools reconnect after a shared PostgreSQL restart. Run it with the same arguments as `rehearse_native.py`, using a new report path.

See `RECOVERY.md`, `QUALIFICATION_RECOVERY_2026-11-04.md` and `evidence/2026-11-04-recovery/`. The current capture/readback limits are 256 MiB and 120 seconds; larger production databases require separately admitted custody/resources. Logical archives contain sensitive Auth data and are not encrypted by this candidate. Off-host encryption, cluster roles/secrets, object storage, WAL/PITR and production-volume recovery remain separate requirements. Restoring old Auth state requires explicit revoked-session/password-change reconciliation before reopening traffic.

## Shared Storage milestone

`tools/shared_storage.py` extends the same installation with **one upstream multi-tenant Storage service**, using project metadata schemas and a small registry database on the existing PostgreSQL server. No per-project Storage stack or new PostgreSQL server is added. The staged compiler preserves explicit original native tenant/bucket/mount mappings, verifies project credentials, prepares scoped logins/HBA, and supplies project gateways plus an exact-source legacy Envoy route candidate.

The real test converted a synthetic single-tenant service without moving its original objects or changing its keys. Both projects then passed actual upload/download/list/update/delete, owner-RLS, signed/public URL, wrong-project token, header-spoofing and shared-service restart checks. A local object-restoration drill preserved bytes and extended metadata and left the neighbour's objects unchanged. This is not a coordinated production database-plus-object backup.

See `SHARED_STORAGE.md`, `QUALIFICATION_STORAGE_2026-11-04.md` and `evidence/2026-11-04-storage/`. `tests/rehearse_storage.py` needs the explicit pinned upstream Storage source and Node paths; `tests/check_storage_compose.py` evaluates only a synthetic effective Compose model, without contacting the Docker daemon. The 245-check Storage run includes the 101-check core, not the separate 157-check recovery drill; do not add overlapping check counts.

## Shared Realtime milestone

`tools/shared_realtime.py` extends the existing Supabase installation with **one native Realtime v2.152.0 process** and a small separate Realtime tenant-registry database inside the **same PostgreSQL server**. An exact-source patch scopes upstream's Broadcast replication-slot names to the project tenant, avoiding collisions between separate databases in one PostgreSQL cluster. The native test exercised private WebSocket joins, PostgreSQL-change subscriptions, cross-project denial, broadcast, presence, slot cleanup, shared-service restart, Storage and REST RLS preservation.

The exact current candidate passed **164 tests, 345 real-service checks and 18 effective Compose/model checks**. These overlap with earlier Auth/REST/Storage checks and should not be summed with the previous milestones. All native tests ran against temporary local services, not VAN production; the Compose checks used an invalid placeholder for the yet-to-be-built derivative Realtime image.

See `SHARED_REALTIME.md`, `QUALIFICATION_REALTIME_2026-11-04.md`, `evidence/2026-11-04-realtime/`, `tests/rehearse_shared_fabric.py` and `tests/check_realtime_compose.py`. The existing single-tenant donor routing and credentials require separate real-host review before activation; the existing Compose `--remove-orphans` boot model must be reconciled.

## Edge Functions milestone (separate native rehearsal)

`tools/shared_edge.py` and `edge/main/index.ts` adapt the existing **single** Supabase Edge Runtime service to serve separate projects with immutable function definitions, independently verified JWTs, explicit per-function permissions, per-project gateways and worker time/CPU/concurrency limits. No second server or Edge stack is introduced. The original `functions` service and mounts are retained in the Compose model. See `SHARED_EDGE.md`, `QUALIFICATION_EDGE_2026-11-04.md`, and `evidence/2026-11-04-edge/`.

A real isolated Edge runtime passed **209 native checks**; the expanded complete source suite passed **185 unit tests** and **16 effective Compose-model checks**. The separate previously published 345-check Storage/Realtime integrated rehearsal remains valid. The later complete-installation rehearsal now runs Storage, Realtime, Edge, Supavisor, Meta and Studio HTTP concurrently; this earlier Edge count remains a separate overlapping checkpoint. The Edge image is pinned to a verified amd64 digest but must be qualified separately for the actual target architecture. Synthetic functions are not Nissan GTR business functions.

## Shared pooler and project-aware administration milestone

`tools/shared_pooler.py` reuses one native Supavisor registry and its original Vault key; it generates distinct project SQL credentials, bounded pools and HBA rules without reseeding or replacing the existing registry. Both transaction and session pooling passed actual database and negative cross-project tests. Native tenant PUT is an UPSERT, and real deployment must retain the original owner lease, absent-record/readback and unknown-outcome reconciliation.

`tools/shared_admin.py` and `admin/` implement one private verifier/routing gateway before the existing Studio and Postgres Meta. It derives connections from server-side project scope rather than browser-supplied credentials, rejects unqualified APIs rather than falling back to the original default database, and does not create a new identity issuer. Basic real Studio browser selection, table listing, table click and reading different rows in the two databases passed. Actual issuer login, full Studio feature coverage and seamless same-tab project switching are not claimed.

The final isolated run passed **248 real native/API/browser assertions**; the source suites passed **224 Python tests and eight Node admission tests**, with **26 complete Compose-model checks**. Browser phases used separate fresh sessions and stopped the earlier fixture pooler/Auth/REST processes to remain inside the existing memory budget. This is not a simultaneous all-services native load test. See `SHARED_MANAGEMENT.md`, `QUALIFICATION_MANAGEMENT_2026-11-04.md` and `evidence/2026-11-04-management/`.

## Nissan GTR ARM64 SQL replay checkpoint

The actual thirteen source-locked Nissan GTR migrations now pass against a fresh, network-isolated ARM64 PostgreSQL 17.6 fixture using the live donor's real Auth/Storage schemas. The baseline matches all 212 tables, 769 function definitions/capabilities, 341 policies, 5,136 relation-grant entries, two views and three private-schema privileges; all seventeen upstream database business smoke suites pass after the forward migrations. The full Python suite now passes 322 tests.

This is actual native SQL compatibility, **not a live second-project activation or hosted-data migration**. Ordinary application definitions retained their intended owner; the exact native Auth/Storage owner-only sections were executed separately. The new pure `tools/gtr_migration_plan.py` prepares those source-locked contexts and guards the exact target database but does not execute SQL or grant deployment authority. Its newer guarded wrapper has source/unit proof; the completed native runner and the later refused transfer are distinguished in `QUALIFICATION_GTR_SCHEMA_2026-11-08.md` and `evidence/2026-11-08-gtr-arm64-replay/`.

## Archived GTR history-body reconciliation

Ten legacy/hosted-export migration pairs with distinct raw file hashes contain the exact same SQL bodies after removal of the two *precisely known* hosted provenance comments and, for six pairs, one terminal LF. The original source hashes are retained and no arbitrary SQL content is normalized. See `ARCHIVED_MIGRATION_BODY_EQUIVALENCE.md` and `evidence/2026-11-09-gtr-archive-equivalence/`. **The current active hosted ledger and real customer/business data remain unverified**, and no canary activation or migration history repair is authorized.

## Mandatory database boundary

PostgreSQL role names are cluster-wide. Reusing the standard Supabase API roles preserves source RLS compatibility, but an existing database may grant `CONNECT` to `PUBLIC`. Merely withholding an explicit grant from a new login would not exclude that login.

Consequently the generated roles begin **NOLOGIN**. An exact `pg_hba.conf` prefix allows each project login only into its own database from approved private CIDRs and rejects that login on every other database and Unix socket. Existing rules follow the prefix. The activation SQL requires the exact parsed first-match rules, a reload observation and quarantined nonprivileged roles before enabling login. It does not alter the legacy databases' grants or existing global API roles.

**Do not enable these logins or start project services without this HBA boundary.** The bundle is not a permission to change a running cluster. Production adoption requires whole-instance backups, owner admission, a reviewed HBA placement and actual cross-project connection tests. Restrict and monitor subsequent HBA changes.

## Run offline tests

From the repository root, Python 3.10+ on Linux:

```sh
BASE=deploy/van-trading-core/supabase/multiproject
python3 -m unittest discover -s "$BASE/tests" -v
```

The four older routing tests use a local Nginx binary and skip if it is absent. A skip is not qualification. The new `tests/rehearse_native.py` is explicit and never runs against a supplied production database.

## Reproduce the native rehearsal

Stage checksum-verified upstream binaries in an isolated non-root workspace; versions and acquisition hashes are recorded in `tests/rehearsal-binaries.lock.json`. No root, Docker socket, existing database endpoint or production credential is needed. Package extraction is not a system installation. Paths below must point at those staged binaries:

```sh
python3 "$BASE/tests/rehearse_native.py" \
  --pg-bin /absolute/staged/postgresql/17/bin \
  --pg-lib /absolute/staged/lib \
  --auth-bin /absolute/staged/auth/auth \
  --rest-bin /absolute/staged/postgrest/postgrest \
  --nginx /absolute/staged/nginx \
  --report /absolute/private/new-rehearsal-result.json
```

The runner creates one new loopback-only temporary cluster, uses random temporary credentials, starts only its own processes and stops them before returning. Success removes the private temporary database; failure retains private diagnostic files after cleanup. Reports omit passwords, signing keys and tokens. The source hashes must remain unchanged throughout the run.

## Generate an operator-review bundle, without deployment

```sh
WORK=$(mktemp -d)
python3 "$BASE/tools/bootstrap.py" \
  --manifest "$BASE/projects.rehearsal.json" \
  --client-cidr 127.0.0.1/32 \
  --out "$WORK/private-bootstrap"
```

Use the reviewed actual Docker-network CIDR for a future target, not the loopback fixture example. Output is a new directory with mode 0700 and files mode 0600. It contains real randomly generated credentials: **never commit or distribute the bundle, env files or generated Nginx config.** The generator has no apply/start/restart operation. Repeated generation creates different credentials; do not replace an existing project's credentials by regenerating a bundle.

`projects.rehearsal.json` contains `.invalid` hostnames and synthetic project UUIDs. These are examples, not provisioned production identities. The separate original `tools/render.py` is retained for historical candidate comparison; do not combine its unqualified Storage overlay with the new API/Auth-only overlay.

## Staged production adoption — still unperformed

1. Verify VAN host and running donor versions, workload/connection budgets, existing roles, HBA and service model. Back up and restore the whole existing VAN/VATI cluster off-host.
2. Review and admit exact source. Apply the new roles as NOLOGIN; create fresh project DBs from `template0`, then the scoped schemas. Never clone or restore over VAN's `postgres` DB. Existing names fail rather than being overwritten; interrupted work must be reconciled before retry.
3. Prepend only the reviewed new-login HBA rules while preserving existing rules, reload and verify. Activate the exact quarantined logins. Run independent negative connection tests against VAN and the other projects.
4. Start only the project Auth services privately, let the pinned upstream migrations finish, apply the post-migration helpers, then start REST and the API-key-aware gateways. Preserve current global API roles. Production changes must use the existing qualified owner/Root mechanism.
5. Include all overlay files in the canonical `vati-supabase.service` startup/stop model before enabling project services; its existing `--remove-orphans` invocation must not remove the new services on restart.
6. Complete real TLS/CORS/rate-limit checks, key rotation, SMTP/OTP/OAuth/MFA, resource and recovery tests; qualify shared Storage, Realtime and Edge Runtime on the actual donor VM, plus the actual Supavisor registry and project-aware Studio/operator-identity integration independently.
7. Rehearse Nissan GTR schema/history/Auth/Storage/R2/payment migration and rollback, obtain exact-source release/deployment evidence, then perform a controlled cutover.

## Deliberately not claimed

Production VAN capacity/runtime access was not verified in this change. The DIAL estate check was blocked by expired owner-ingress metadata; the legitimate qualification challenge was observed but did not complete Root confirmation. Tests ran through the connected Commander as an unprivileged user on `dial-control`, not through a Root-signed VAN deployment.

The native rehearsal uses PostgreSQL 17.11 on amd64, Auth 2.196.0, PostgREST 14.17 and Nginx 1.24.0. The repository donor PostgreSQL image and target architecture, plus the generated Nginx 1.27.5-alpine container, require separate qualification. Existing production binaries were not replaced or upgraded.

The core bootstrap keeps Storage, Realtime and Functions routes closed until each separately qualified shared-service integration is applied. Readiness and unqualified OAuth/SAML/verification callback routes remain HTTP 503. No public signup or email autoconfirm is enabled. Studio, Supavisor, actual VAN Storage activation, TLS/browser CORS, OAuth/MFA/SMTP, production-scale/off-host recovery, ARM64 and Nissan GTR business-flow qualification remain open.

**No live project has been provisioned on `van-trading-core`; Nissan GTR has not been migrated.**
