# DIAL Supabase — one installation, independent database/Auth/API projects

**Status: 157 real-service checks and 79 tests passed, including per-project logical backup/restore and shared-server restart recovery. Not deployed to VAN and not a complete production Supabase release.**

The owner requirement is one existing managed Supabase installation on `van-trading-core`, one PostgreSQL server, and independently functioning application databases and authentication environments. The candidate does not add a PostgreSQL server, VM or complete Supabase stack per project. It adds small project-specific Auth, REST and router services to the existing Compose model; other services remain separate qualification work.

**REA is optional research support, not an execution or release prerequisite.** The owner authorized direct implementation. No REA investigation result is claimed or needed for the tests below.

## Implemented and demonstrated

`tools/bootstrap.py` generates a private, staged bootstrap bundle for fresh project databases. Each project has unique database logins, SCRAM password verifiers, an Auth schema, signing secret, API credentials and gateway configuration. GoTrue performs its real upstream Auth migrations; the code does not imitate its user/session tables. REST keeps standard `anon`, `authenticated`, `service_role` policies and adds an exact project-issuer check.

The native rehearsal creates two synthetic projects in one temporary PostgreSQL cluster, with real Auth, REST and Nginx processes. It exercises independent same-email identities, passwords, refresh sessions, user/service JWTs, RLS ownership, API keys, database login permissions, host/header routing and concurrent requests. The original third fixture database's contents and ACL remain unchanged. See `QUALIFICATION_2026-11-04.md` and the non-secret evidence directory for exact results.

This is stronger than the retained 24 October test suite, which checked Nginx against labelled HTTP stubs only. Neither test is a production-deployment receipt.

## Project recovery milestone

`tools/recovery.py` now captures a real snapshot-bound logical database backup, validates project/cluster identity and externally retained hashes, and generates only fresh quarantined restore targets. It never applies a restore or overwrites a live database. Verified archive bytes are sealed against modification before they can be supplied to pg_restore.

The explicit `tests/rehearse_recovery.py` extends the core rehearsal: restore into a fresh same-server database, compare fixture data/ownership/effective ACLs/RLS, recover Auth credentials and sessions, keep the neighbour usable, and prove both pools reconnect after a shared PostgreSQL restart. Run it with the same arguments as `rehearse_native.py`, using a new report path.

See `RECOVERY.md`, `QUALIFICATION_RECOVERY_2026-11-04.md` and `evidence/2026-11-04-recovery/`. The current capture/readback limits are 256 MiB and 120 seconds; larger production databases require separately admitted custody/resources. Logical archives contain sensitive Auth data and are not encrypted by this candidate. Off-host encryption, cluster roles/secrets, object storage, WAL/PITR and production-volume recovery remain separate requirements. Restoring old Auth state requires explicit revoked-session/password-change reconciliation before reopening traffic.

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
6. Complete real TLS/CORS/rate-limit checks, key rotation, SMTP/OTP/OAuth/MFA, resource and recovery tests; qualify shared Storage, Realtime, Edge Functions, Supavisor and project-aware Studio independently.
7. Rehearse Nissan GTR schema/history/Auth/Storage/R2/payment migration and rollback, obtain exact-source release/deployment evidence, then perform a controlled cutover.

## Deliberately not claimed

Production VAN capacity/runtime access was not verified in this change. The DIAL estate check was blocked by expired owner-ingress metadata; the legitimate qualification challenge was observed but did not complete Root confirmation. Tests ran through the connected Commander as an unprivileged user on `dial-control`, not through a Root-signed VAN deployment.

The native rehearsal uses PostgreSQL 17.11 on amd64, Auth 2.196.0, PostgREST 14.17 and Nginx 1.24.0. The repository donor PostgreSQL image and target architecture, plus the generated Nginx 1.27.5-alpine container, require separate qualification. Existing production binaries were not replaced or upgraded.

Storage, Realtime, Edge Functions, readiness and unqualified OAuth/SAML/verification callback routes return HTTP 503 in the new candidate. No public signup or email autoconfirm is enabled. Studio, Supavisor, Storage, TLS/browser CORS, OAuth/MFA/SMTP, production-scale/off-host recovery, ARM64 and Nissan GTR business-flow qualification remain open.

**No live project has been provisioned on `van-trading-core`; Nissan GTR has not been migrated.**
