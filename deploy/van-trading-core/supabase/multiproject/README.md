# DIAL Supabase Multi-Project Fabric — additive candidate

Status: **SOURCE CANDIDATE ONLY — NOT LIVE / NOT REA-QUALIFIED / NOT PRODUCTION-QUALIFIED**.
Owner target: one EXISTING Supabase installation on van-trading-core, one PostgreSQL 17 cluster, separate PostgreSQL databases that expose independent Supabase Auth/REST/Storage projects. NO extra complete Supabase Docker stacks and NO change to VATI trading ledger.

## What this package does

- Pins independently reviewed open-source candidate revisions and ships exact REA investigation requests (not fabricated REA results).
- Provides a deterministic dependency-free project manifest validator and Compose/router renderer.
- Adds only GoTrue, PostgREST, Storage and an internal routing process per project **to the current Compose project**. PostgreSQL/Studio/Realtime/Edge runtime/Supavisor remain shared in the intended final design.
- Emits loopback-only canary gateway endpoints, and intentionally refuses unqualified Realtime and Functions routes (HTTP 503).
- Never creates DBs, credentials, containers, Docker networks, privileges, DNS or processes by itself.
- Does NOT patch the active VAN Compose, service unit or proxy; those are future gate-controlled integration changes.

## Commands: code generation and offline tests ONLY

    python3 -m unittest discover -s deploy/van-trading-core/supabase/multiproject/tests -v
    python3 deploy/van-trading-core/supabase/multiproject/tools/render.py validate --manifest deploy/van-trading-core/supabase/multiproject/projects.example.json
    python3 deploy/van-trading-core/supabase/multiproject/tools/render.py render --manifest deploy/van-trading-core/supabase/multiproject/projects.example.json --out /tmp/dial-supabase-candidate

DO NOT invoke Docker Compose with this candidate until all documents' hard gates have been met, a compatible per-project bootstrap is proved and the existing vati-supabase.service launch is extended atomically. That unit currently uses --remove-orphans; launching extra services before amending the full configured Compose model risks destroying the extra containers at next restart.

## Required production gates

1. REA static source investigations with genuine native receipts and qualified provider; source review alone is not REA output.
2. Fresh qualified VM and Compose inventory (including memory, disk, subnet, backups and production transaction load).
3. Immutable whole-VAN physical backup and tested restoration; VATI invariants and trading services green.
4. Database-per-project bootstrap from matching PostgreSQL/Supabase image, no copying VAN's VATI schema; unique unprivileged DB login roles and CONNECT denial for other tenants; per-project GoTrue migrations.
5. Project Auth/REST/Storage isolated and backed by schema, role, RLS and negative cross-project tests.
6. Shared Realtime, Edge, Supavisor, Storage and Studio integrations qualified per project before enabling routes.
7. Nissan GTR hosted schema/auth/data/storage/R2/payment continuity and rollback qualified.
8. Zuul admission + exact SHAs + signed immutable deploy receipt + runtime verification.

See ARCHITECTURE.md, NISSAN_GTR_CUTOVER.md, SOURCE_EVIDENCE.md and rea-requests.json.

No project is currently provisioned by this package. No running VM or service was changed.
