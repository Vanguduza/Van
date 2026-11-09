# Independent project database/Auth/API rehearsal — 4 November 2026

## Result

**49 tests passed, no failures/errors/skips. 101 real-service integration checks passed.**

This is a genuine execution milestone, not a complete production deployment: a disposable PostgreSQL 17 cluster hosted two independent project databases, with real Supabase Auth 2.196.0 and PostgREST 14.17 processes, reached through real per-project Nginx gateways. No labelled HTTP stubs were used in the 101-check native rehearsal. The 49-test suite includes the retained four stub-routing tests, labelled as such.

The work continues VAN PR #102 from immutable parent `62827134d7de41692b0dbd043e4f497a6beb1834`. All technical changes are confined to `deploy/van-trading-core/supabase/multiproject/`. No main branch merge, live VAN database write, running Supabase restart, firewall change or Nissan GTR cutover occurred.

## Actual execution venue and versions

The connected Remote Desktop Commander executed the tests as ordinary user UID 1000 on `dial-control`. Test databases, credentials, binaries and processes were private and separate from the active installation. No sudo, Docker socket or system package installation was used. Downloaded packages were extracted into the new scratch workspace.

| Component | Tested version / scope |
|---|---|
| PostgreSQL server and client | PGDG 17.11, amd64, separate temporary data directory |
| libpq | PGDG 18.6 shared library extracted only for the test processes |
| Supabase Auth / GoTrue | Official v2.196.0 native release, packaged upstream migrations |
| PostgREST | Official v14.17 Linux static amd64 release |
| Nginx | Ubuntu 1.24.0 native package, non-root private configuration |
| Database topology | One server, two project databases and one synthetic legacy database |
| API processes | One Auth, REST and loopback gateway per project |

Archive acquisition URLs and SHA-256 values are retained in `tests/rehearsal-binaries.lock.json`. Auth and PostgREST release digests matched the official HTTPS release metadata. PGDG package bytes matched the HTTPS package index. Cryptographic release-attestation verification is not claimed. Runtime executable and source file hashes are in the final native result.

This is **not** a test of the actual `supabase/postgres:17.6.1.136` donor container, ARM64 deployment, or the generated `nginx:1.27.5-alpine` image. Those remain target qualification work. No deployed binaries were upgraded.

## What the real checks establish

- Both projects were bootstrapped from empty `template0` databases without copying an existing application's data.
- Unique Auth, REST and migration login credentials were created; roles had no cluster superuser, create-role, create-database, replication or RLS-bypass privileges.
- Roles remained NOLOGIN until the exact generated first-match HBA prefix was installed and reloaded. Activating without the prefix failed. Repeating activation or creating the same bootstrap again failed rather than overwriting state.
- Each project login connected to its own DB. Attempts to use that same login against the other project, the `postgres` DB and the synthetic legacy database were rejected by HBA. The REST login could not become the fixture administrator.
- Both real GoTrue instances completed their upstream Auth migrations. The same email address produced independent user UUIDs and password credentials in each project.
- Real password login, token refresh, Auth administration and PostgREST database requests worked within the correct project.
- Each project contained two actual Auth users. Row-level security exposed only the requesting user's rows and rejected writing a row for the other existing user. A project service-role token could access both rows inside its project, not another project's APIs.
- Wrong-project user JWTs, service-role JWTs, API keys, passwords and refresh tokens were denied. Correctly signed JWTs with the wrong issuer or audience were also denied.
- An ordinary user could not use Auth administration; the `auth` schema could not be selected through the REST exposed-schema header.
- Unknown/foreign Host and spoofed project/forwarding headers did not select another database. Forty concurrent requests continued to return only the selected project's rows.
- Missing/invalid API keys failed. Unqualified Storage, Realtime, Edge, readiness and OAuth callback endpoints stayed HTTP 503.
- The separate synthetic legacy database's sentinel row and database ACL were unchanged. This proves fixture preservation only, not production VAN preservation under deployment.
- All processes created by the successful rehearsal were stopped; the temporary data directory was removed. The final report records cleanup completion.

## Important implementation boundary

Standard Supabase API roles are cluster-wide, and existing databases may grant CONNECT to PUBLIC. Merely granting CONNECT on a new project database does not remove a new login's access to an older database. The solution therefore retains the canonical API roles for RLS compatibility and **requires an explicit first-match HBA allow/deny boundary for each new login**. Production changes must retain and verify all prior HBA behavior for existing services. No existing global role or legacy database ACL is changed by the generator.

The candidate creates staged private SQL/configuration artifacts; it has no apply/start/restart operation. Operators must use the existing admitted DIAL deployment/Root owner to apply reviewed changes. The generated private bundle contains genuine secrets and must never be committed, placed in public evidence or sent to a model.

## Defects found and fixed by the actual runs

The first native trial reached 19 successful database checks, then Auth migration correctly rejected the synthetic cluster because its canonical `postgres` role was absent. The test now supplies that non-login fixture role, and production generation explicitly checks that the donor role exists rather than silently creating it.

Subsequent actual Nginx configuration tests exposed map and variable hash bucket sizing for full JWT API keys. The generator now specifies adequate buckets. Test gateways use per-project processes, fixed issued API keys and private non-root buffering paths.

Running the old file-output tests on the locked-down host exposed that listing `/` is denied to the ordinary user, although path traversal is allowed. The safe writer now uses Linux O_PATH for ancestor traversal, retaining no-symlink checks, and opens only the verified private final parent for fsync. A new search-only-ancestor regression passes; existing traversal/symlink/overwrite refusal tests remain green.

The initial attempts are retained as failed outcomes in the private work journal; only the final exact-source run establishes the passing evidence. Failed fixture processes were also cleaned up. No failure was converted into success or skipped.

## Evidence

- `evidence/2026-11-04/native-result.json`: 101 checks, executable hashes, source hashes, cleanup status and explicit exclusions.
- `evidence/2026-11-04/native-run.txt`: corresponding passing native assertions.
- `evidence/2026-11-04/unit-tests.txt`: 49 tests, zero skips/failures/errors.
- `evidence/2026-11-04/source-manifest.json`: exact source SHA-256 values, parent revision, evidence hashes and validation commands.
- `tests/rehearsal-binaries.lock.json`: native package acquisition identities.

These are actual host observations through Remote Desktop Commander, **not** Root-signed Native admission or Zuul release receipts. The evidence does not claim runtime `GREEN` for the live Supabase installation.

## Remaining deployment gates

The direct DIAL VM check returned expired Owner ingress metadata. The legitimate new qualification challenge was observed but still required exact Root confirmation; that does not grant privileged execution. No fallback was used to mutate `van-trading-core`.

Live VAN capacity/versions, off-host backup and restore, actual donor/container/architecture compatibility, canonical Compose boot-model integration, network/TLS/CORS/rate limits, provider-specific Auth flows, API-key rotation, Storage, Realtime, Edge, Supavisor and Studio are not yet qualified. OAuth/MFA/SMTP, persistent restart/recovery, GTR data/history/integrations, financial invariants and reversible cutover still require independent tests and approved deployment evidence.

REA was not used. Its investigation remains optional and does not block this implementation. The existing REA request files remain historical research inputs, not a release gate.

**Disposition: API/Auth/database core demonstrated in isolation; keep PR #102 draft pending the remaining production gates.**
