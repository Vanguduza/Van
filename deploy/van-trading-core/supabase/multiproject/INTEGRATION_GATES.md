# Qualification and integration contract for generated project overlay

This source is deliberately non-deploying. Rendering does not populate database migrations, generate secrets, register Realtime tenants or configure independent Edge/Studio routes.

## Mandatory admission before a Docker change

1. Read the actual DIAL VM state via qualified owner-only Global DIAL MCP, check host disk/inode/RAM/CPU/PG17 data, and capture immutable verified backups of postgres cluster including VATI. Do not use a local ChatGPT container as a substitute for VM execution.
2. Review project-specific Supabase Auth and Storage migration version versus pinned donor. Create empty DATABASE gtr_prod from template0 (NEVER clone VAN postgres), then reproduce the correct new-database Supabase bootstrap including roles, auth/storage/migration tables, public/extension/search path defaults and schema permissions. Explicitly reject unqualified shared superuser access.
3. CREATE per-project scoped PostgreSQL roles and secrets, REVOKE public CONNECT to tenant database, GRANT minimal role access. Prove project runtime login cannot CONNECT to another tenant DB.
4. Materialize /etc/dial-supabase/projects/<slug>/{auth.env,rest.env,storage.env,nginx.conf} as restricted root-owned secret files, /srv/dial-supabase/projects/<slug>/objects as dedicated storage; never commit secret files.
5. Render and independently review candidate Compose overlay. Reconcile the existing vati-supabase.service's ExecStart/ExecStop and --remove-orphans behavior so the complete service set is part of the SAME canonical Compose model at every boot. Review Linux mounts, SELinux/AppArmor and PG backup/restore.
6. Apply only on a disposable equivalent of VAN Supabase first. Qualify GoTrue REST APIs, PostgREST, Storage, secrets, RLS, immutable tenant key/issuer separation, traffic tests and rollbacks. Do not expose loopback service publicly.
7. Add a trusted frontend project-origin router with TLS, canonical host->project mapping and explicit per-project key validation. Route Realtime only after native tenant registration plus CDC/WAL/fanout isolation tests; route Edge after verified per-function secret isolation and webhook verification.
8. Wire a project-aware Studio/pg-meta controller. Donor Multi-Head code is not freely relicensable for unrestricted SaaS; management UI must respect upstream license and exact project admin authority.
9. Link Nissan GTR repository migration gates and Zuul receipts. Cutover only by approved immutable SHA and controlled data reconciliation.

## Audit receipt requirements

Every action carries target project UUID, DB name, exact source Git SHA, previous/new config hash, owner scoped approval if administrative, broker receipt, preflight proof, RLS/security results, restoration reference, and date. A non-green receipt blocks promotion.

## Not equivalent to full cloud independence

Shared physical Postgres, global roles, cluster WAL, filesystem/VM root and shared services are failure domains. This implementation delivers application/auth/database isolation after runtime qualification, not independent infrastructure availability. Per-project Auth/Rest/Storage run in the SAME Compose installation, which still creates additional lightweight container processes per project.
