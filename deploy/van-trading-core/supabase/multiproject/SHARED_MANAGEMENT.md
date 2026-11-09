# Shared Supavisor and project-aware Studio administration

## Architecture and authority

This extends the owner's existing **one Supabase installation and one PostgreSQL server** design. The candidate reuses **one Supavisor, one upstream Studio and one Postgres Meta service**. It adds one small private project-administration gateway, not a Studio stack per project. The gateway verifies an existing operator issuer's public key and maps that verified identity to explicit project permissions. It does not issue Owner credentials, create an identity provider or replace DIAL's existing execution authority.

The application runtime remains separate: per-project database/Auth/REST identities, shared Storage, Realtime and Edge. Pooler SQL credentials are trusted backend credentials; project administration is a separate operator interface. Neither is an end-user Supabase Auth JWT or an automatic exemption from RLS.

**The implementation is an isolated tested source candidate, not a live VAN deployment or full Studio feature certification.** Actual target inventory, original configuration, owner admission, complete startup integration and migration gates remain mandatory.

## Supavisor: one native pooler with separate database identities

The source is pinned to Supavisor **2.9.12**, commit `e8719d9ac5a43604c46d2d9e15bb34c76dea8f12`. `tools/shared_pooler.py` generates private inputs for the original Supavisor registry, new project runtime roles and bounded tenant pools. The existing `_supabase` registry and Vault encryption key must be explicitly retained. No default tenant is reseeded; the proposed command removes the donor's unconditional `pooler.exs` reseed step while preserving its original service, ports and mounts.

Each project receives a unique `_pool` login and a separate `_admin` login. Both begin NOLOGIN, have no cluster superuser/create-role/create-database/replication/RLS-bypass attributes, and are subject to connection, statement and idle-transaction limits. The pool login receives only reviewed application grants. The admin login inherits its own project's schema owner, not `postgres` or another project's owner. The initial candidate does not grant unrestricted Auth-schema administration.

The complete first-match HBA prefix permits each new login only into its own project database and rejects other database/socket access before old permissive rules can apply. Activation requires exact parsed rules, a reload observation and quarantined roles. Existing project Auth/REST grants and old database ACLs are preserved.

Real native tests cover session and transaction pooling, declared database/username binding, foreign password and startup-database selection, unauthorized roles, concurrent requests, bounded physical backend connections, restart and continued direct REST access. The registry management key is independent from every project's service-role key.

### Native API caveats that must not be hidden

Supavisor's management `PUT /api/tenants/{id}` is an **UPSERT**. The staged packet accurately records that behavior. It requires an existing original-owner exclusive lease, an absent-record readback and reconciliation of an unknown original outcome; the generator does not execute PUT, create authority or implement an unsafe automatic retry. Never overwrite a live tenant by replaying a prepared candidate.

The authorized native response can contain database passwords. The adapter's `safe_readback` emits only a project-bound redacted receipt. Raw management responses, registry content and Vault credentials must never be sent to a public UI, model, repository or ordinary logs.

Production tenant defaults require TLS and a reviewed upstream CA with peer verification. The disposable native fixture explicitly disables TLS only for its private loopback connection. Native TLS behavior, target certificates and any existing insecure donor port remain separate deployment gates. The tested OCI digest is linux/amd64; no ARM64 runtime claim is made.

## Studio and Meta: route by verified project, not browser credentials

The actual unchanged Studio image is `2026.09.07-sha-7996410`; Postgres Meta is **0.99.0**, source `f380cc5be21edef4e77d9838c732d1f20af0b3c0`. Upstream self-hosted Studio defaults several routes to one `postgres` database. Simply selecting another project in its UI would not change that authority. The gateway therefore implements explicit project catalogue, profile, database selection, metadata and SQL routes, and refuses unsupported APIs instead of falling back to that default database.

`tools/shared_admin.py` compiles the private registry and one gateway overlay. `admin/server.mjs` validates the exact registry hash, private file mode and shape, then accepts finite Ed25519 operator JWTs from the configured existing issuer/audience. It stores only the issuer's public verifier, never an issuer signing key. Claims do not create project membership: operator-to-project scope and query permissions are explicitly configured on the server. Token lifetime is bounded to ten minutes. The fixture uses an ephemeral synthetic issuer; **actual DIAL/IdP login, revocation and key rotation remain unqualified**.

Browser requests cannot choose a connection using `pg`, `x-connection-encrypted`, tenant or forwarded-host headers. The gateway derives the correct database credential from its private project map and creates the exact encrypted connection envelope expected by native Postgres Meta. The deployed service must keep Meta and Studio private behind the gateway; retaining a loopback Studio port is not permission to expose it publicly.

The public project view contains no database password or usable connection string. A displayed database-health field is computed from a real, bounded query confirming the expected database and role; it does not imply production platform acceptance. A native Studio role dropdown can still display its upstream default label `postgres`; the tested actual SQL principal remains the restricted project `_admin` role. Broader role impersonation and privileged Studio panels are not implemented by this label.

Supported paths include the scoped catalogue, native table/schema/column/policy/type/view/index metadata and authorized SQL. Requests containing an unqualified database connection override or asking to disable statement timeouts are refused. Unknown API routes return 501; Auth/Storage/Edge/Realtime administration panels, provider integrations and secrets pages are not silently routed to VAN's original project.

### Browser and request protections

The gateway accepts a verified `__Host-dial-admin` secure HttpOnly cookie or a Bearer token; it does not issue either. Cookie writes require exact same-origin validation. A separate private key protects process-health checks. UI static files use their own bounded queue so page assets do not exhaust SQL-query admission. Next.js static assets are permitted, but unqualified `/_next/data` routes cannot bypass API routing.

Database work has four active slots globally and two per operator, with bounded pending queues and deadlines. Queuing happens before execution and is not a retry. Abort removes pending work; an active slot remains owned until its original handler settles. Releasing it twice cannot create capacity. No failed or unknown SQL operation is automatically replayed.

These bounds are not a complete hostile-SQL resource policy. Trusted project administrators can execute SQL with their own database privileges; PostgreSQL catalog names remain cluster-wide, and some session settings may be adjustable. Production query cancellation, resource governance, auditing and reconciliation of uncertain effects need independent qualification. This is application/database isolation, not independent VM security or high availability.

## Actual qualification and its boundaries

The rehearsal uses real PostgreSQL 17.11, Supavisor 2.9.12, Auth 2.196.0, PostgREST 14.17, Postgres Meta 0.99.0 and the original compiled Studio server. It runs non-root on `dial-control` in a new disposable database cluster. A test-only, exact-source in-memory amendment binds Supavisor's original network listeners to loopback; it changes no pooling/authentication logic and does not modify the retained upstream release files. This is not a production derivative-image qualification.

The native browser is a staged Firefox 142.0.1 driven by pinned Playwright Core 1.56.1. The browser selects the real project, renders the unmodified Studio table editor, clicks `admin_fixture` and reads different fixture rows in each database. Each project gets a separate fresh browser process to remain within the existing host memory limit. No cgroup budget is changed, and this does **not** establish seamless same-tab project switching.

The fixture's pooler/Auth/REST/project routers are tested first, then stopped before the browser phase to limit memory; PostgreSQL, Meta, Studio, the admin gateway and test TLS proxy remain. Thus the browser checks are in the same sequential fixture, not proof that every shared service can operate together under production load.

Host Chrome failed its explicit sandbox launch because its native helper was not qualified. No chmod, root change or sandbox-disable workaround was applied. Firefox ran without explicit sandbox-disable flags; host namespace restrictions remain, and a complete browser-sandbox certification is not claimed. Only official staged UI code, synthetic users/data and the exact loopback HTTPS test origin were allowed. The self-signed test certificate and ignored test TLS errors are not production TLS approval.

See `QUALIFICATION_MANAGEMENT_2026-11-04.md` and retained evidence for exact final counts, executable/source hashes and failed-attempt lineage. Earlier test passes are not relabelled as proof of later source.

## Deployment model and operator sequence

The full model checker composes core project services, Storage, Realtime, Edge, Supavisor and the admin gateway with the exact existing donor definition. It preserves one PostgreSQL service, all original services, original Studio/Meta settings, the Storage mount, original pooler registry/Vault/ports and the existing loopback Studio binding. The new admin gateway is non-root, read-only, uses a private read-only registry mount and publishes no host port. Its image and the patched Realtime image remain unbuilt placeholders in the effective-model test.

The admin image recipe pins a Node 22.23.2 multi-architecture base index, installs only its locked dependencies and excludes private registry files, environment files and local node_modules from its build context. The actual image has not been built or target-qualified. Owner-approved numeric UID/GID and matching 0600 mounted-registry ownership are mandatory; do not assume the live host uses UID 1000.

Before deployment: observe the live original stack and resource budgets; back up and restore original data, roles, keys, tenant registries and objects; admit target-compatible images and immutable config; qualify the existing operator issuer; reconcile the complete systemd/Compose start and stop model including `--remove-orphans`; and test the actual target's negative isolation, TLS, lifecycle and rollback. Do not overwrite an existing tenant, recreate its registry or rotate a Vault key as a shortcut.

The prior all-shared-services configuration composition is not a simultaneous native end-to-end run. Coordinated encrypted off-host recovery, production Auth providers, full Studio functions, tenant lifecycle orchestration and Nissan GTR schema/history/Auth/Storage/R2/payment migration still require work. REA remains optional research.

## Reproduction

From the repository root, with privately staged binaries and source:

```sh
BASE=deploy/van-trading-core/supabase/multiproject
python3 -m unittest discover -s "$BASE/tests" -v
node --test "$BASE/admin/admission.test.mjs"
python3 "$BASE/tests/check_management_compose.py" \
  --repo /private/source \
  --donor-ref 7e8a5d7ec12ecb391e8af19b1de4af53b03988b9 \
  --upstream-schema /private/realtime-source/priv/repo/tenant_db_dump_17.sql \
  --report /private/new-model-result.json
```

`tests/rehearse_pooler.py` and `tests/rehearse_admin.py` require the exact existing native-fixture arguments plus explicit staged `DIAL_REHEARSAL_POOLER_RELEASE`, `DIAL_REHEARSAL_POOLER_LIB`, `DIAL_REHEARSAL_ADMIN_NODE`, `DIAL_REHEARSAL_META_SOURCE`, `DIAL_REHEARSAL_STUDIO_ROOT` and optional qualified browser driver/cache. They never accept an existing production database endpoint. Generated private bundles must not be committed, logged or shared.

## Complete simultaneous installation checkpoint

The newer `QUALIFICATION_INSTALLATION_2026-11-05.md` records 681 passing real assertions with every shared service and both projects' Auth/REST/gateways simultaneously alive on one private PostgreSQL server. It includes exact cross-service data flow, bounded concurrency and selected failure isolation. The canonical lifecycle candidate passed native systemd/integrity checks without being installed. This supersedes earlier *separate-only service coverage* limitations in this guide, but NOT the limitations on production deployment, original operator issuer, target images, advanced/full-browser Studio usage, actual-volume/off-host recovery or Nissan GTR migration. No production or cgroup-policy changes occurred.
