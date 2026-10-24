# One-installation DIAL Supabase Multi-Project Architecture

## Hard invariants

- Reuse the already deployed /opt/van-trading/supabase installation on van-trading-core. One Supabase Postgres 17.6 cluster, one resource/accounting/backup infrastructure, one top-level Docker Compose model. An application must NOT receive its own independent Docker Compose Supabase **stack**, PG server, Studio, Realtime, image proxy, connection pooler or management plane.
- Give each application a distinct PostgreSQL DATABASE, immutable project/tenant UUID, external API origin, JWT keys, GoTrue Auth users/sessions/provider configuration, per-project PostgREST connection/keys, limited database logins, separate Storage backing path/tenant, function namespace, backup and restore unit.
- Per-project GoTrue and PostgREST service PROCESSES are necessary in the initial implementation because the pinned standard versions use one database URL and JWT issuer per process. These are lightweight service containers in the SAME Compose installation, NOT full duplicated stacks. A single-process multi-DB Auth/REST system would require an independently validated fork; do not assert it exists in the existing images.
- Per-project Storage service in initial candidate to guarantee isolated functionality. Long-term shared multi-tenant Storage may be adopted from the Gustavo architecture only after runtime tests prove tenant-aware DB and object routing and fail-closed JWT/key validation.
- VAN/VATI stays on its existing postgres database and restricted VATI ledger schema; never rename its live database, reinitialize the donor, replace the Envoy routes, rotate VAN JWT credentials or expose the loopback ports publicly in the initial build.
- Separate database != separate physical resources. CPU, PostgreSQL roles, filesystem, replication WAL, root, backups and the shared containers remain common failure domains. Provide quotas and whole-cluster DR plus per-project logical restore.

## Logical traffic

App -> TLS front door -> verified project origin -> project router.
Project router -> Auth (GoTrue with unique DSN+signing) -> PostgreSQL/project_db/auth.
Project router -> REST (PostgREST with unique DSN+JWT verification) -> PostgreSQL/project_db/public, other whitelisted schemas with RLS.
Project router -> dedicated Storage API with project DB and storage namespace (candidate) -> file/S3; shared after tenant mode qualification.
Project router -> shared Realtime using tenant registry and tenant JWT (DISABLED until qualified).
Project router -> shared Edge runtime with scoped project ID, namespace, JWT, Vault and gateway authorizer (DISABLED until qualified).
Shared Studio/pg-meta -> permissioned project selection; administrative metadata MUST NOT become public API.
Shared Supavisor -> tenant/DB registration and tightly bounded project connection pools.

## REA donor decisions, independently source-verified (not REA receipts)

1. GustavoMartins123/supabase-multitenant: PRIMARY ARCHITECTURAL DONOR. One cluster, per-project GoTrue/PostgREST/Nginx, tenant-aware Realtime/Supavisor/Storage, single Studio, project control-plane/host-agent. Adapt the concepts, never run its setup.sh over the live VAN installation.
2. arunrajiah/supafleet: DATABASE and per-project JWT/DSN/proxy provisioning concepts. Its tenant Compose stack and per-project Storage process remain optional design references.
3. flamingrubberduck/supabase-studio-multi-head: unified Studio/project UI, metadata and backup UX. EMBEDDED mode only creates another Postgres DB and DOES NOT make GoTrue/PostgREST independently talk to it. Its non-standard sustainable-use license has restrictions; do not copy fork code without an approved licensing decision.
4. supabase-multitenant/supabase-multitenant: explicit exclusion from target runtime because each project launches a full Supabase stack; management UX research only.
5. M7MMAD-OMAR/sbarbase: additional evidence-backed management, quotas, key isolation, bootstrap and acceptance ideas; status reports production acceptance open. This is not a drop-in existing VAN modification.

## One cluster, independent database isolation

For each new project (e.g. gtr_prod):
- Check current pg_dumpall globals, server extensions, physical backup and target version.
- Build a tested project bootstrap that initializes Supabase-owned Auth/Storage roles/schemas/migrations for exactly the NEW DB, not the default VAN database. Do not clone the postgres database: it contains VATI state.
- PostgreSQL roles are cluster-global. Deny CONNECT on each project DB to PUBLIC; mint project-only LOGIN roles (Auth, PostgREST authenticator, Storage, migrate/backup). No per-project service may possess a PostgreSQL superuser or global donor password.
- JWT roles (anon/authenticated/service_role) are global role names; tenant separation depends on per-project JWT issuer/signature AND the project-specific unprivileged PostgREST connection AND least-privilege database grants. Do not grant each project's login CONNECT to unrelated DBs.
- Preserve auth.uid() and source RLS policy semantics, rewrite storage ownership binding, and prove absence of SECURITY DEFINER/search_path grants that cross boundaries.
- Enforce separate OAuth callbacks, SMTP sender, sign-up policy, JWT/KID key rotation and password/refresh-token cutover policy.
- One service_role token MUST NOT work at another project's REST/Storage/Edge/Auth administrative endpoints.

## Gateway and routing security

- Never trust a user-supplied X-Tenant-ID or X-Forwarded-Host. Bind tenant from the validated TLS project origin or signed internal route config; strip conflicting inbound tenant and identity headers.
- For project root /auth/v1 -> matching Auth only; /rest/v1 -> matching PostgREST only; /storage/v1 -> matching Storage only.
- Shared functions and realtime require a native tenant registration, independent JWT verification, tenant-scoped object/function ownership and negative tests BEFORE routes are enabled.
- Each project is subject to rate and burst controls for Auth/REST, connection quotas and a distinct vulnerability/abuse telemetry stream. Shared Envoy CORS configuration must be tightened before production.
- No public PostgreSQL, Studio, Docker socket, Supavisor administration, Meta or host-agent endpoint.

## Native management and authority

The control plane holds PROJECT(id,technical_name,origin,pg_db,auth_key_version,realtime_tenant,storage_tenant,state,source_sha,migration_version,backup_ref), exclusive project operations and immutable receipts. It must integrate through DIAL owner grants and Zuul/admission; not an unfenced Docker socket write path. Lifecycle transitions:
REGISTERED -> PREFLIGHT_PASSED -> DB_BOOTSTRAPPED -> API_AUTH_QUALIFIED -> STORAGE_QUALIFIED -> REALTIME_EDGE_QUALIFIED -> APP_E2E_QUALIFIED -> CUTOVER_APPROVED -> LIVE.
Rollback must restore project data without reverting unrelated VAN state.

All candidate code generation is read-only with respect to the running VM. Its generated configs are not authorized for deployment by their existence.

## Deterministic runtime qualification matrix

A. Resource: prove free memory/CPU disk IOPS, WAL sizing, PG connection budgets and identity of target VM.
B. Core isolation: create GTR and fixture test projects, verify database/schema migrations, per-DB grants, and unchanged VAN/VATI state.
C. Auth: signup/login/OTP/recovery/OAuth/redirects/MFA/refresh/revocation; attempt GTR token, admin token, refresh token against VAN and fixture projects; all rejected.
D. REST/RLS: cross-project keys, JWTs, RPCs, SECURITY DEFINER, views and SQL role escalation rejected; no cross-database access via credentials.
E. Storage: buckets/objects/upload/download/signed URL per project, negative cross-project and expired URL tests.
F. Realtime: cross-project publish/subscribe/topic and CDC slots rejected; no excessive replication/connection impact.
G. Edge: webhook HMAC, per-function JWT, secret vault, SSRF, cross-project invocation, no leakage of process-global secrets.
H. Migration: restore source DB including exact auth rows, constraints, extensions, policies, triggers, grants, jobs, Supabase migrations and app data; compare hashes/counts and authorization outcomes.
I. Operations: project logical backup/restore, cluster physical backup/PITR, RPO/RTO drill, credential rotation, schema forward/rollback, workload spike, cross-project noisy-neighbour/fault isolation, upgrading one project without data loss.
J. Deployment: exact Git SHA, signature, Zul qualification and immutable owner-authorized deployment receipt. No promotion on green placeholder tests.

## Critical boot integration

Existing vati-supabase.service starts Docker Compose using TWO yaml files and --remove-orphans. Project overlays MUST be included in its canonical boot model prior to starting them, OR the composition and lifecycle must be restructured with an explicitly compatible qualified supervisor. Running generated tenant containers directly without a boot fix can cause their removal during subsequent unit start. Do not edit this unit in unqualified state.
