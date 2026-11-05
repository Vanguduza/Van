# Shared Realtime — single Supabase installation

## Goal and state

Continue the owner's **one existing Supabase installation and one PostgreSQL server** requirement. The tested candidate adds **one shared Realtime 2.152.0 service**, a small tenant-registry database in that same server and per-project database-scoped runtime credentials. It retains the existing Auth, PostgREST, Storage and donor services, and does not create a Realtime container or PostgreSQL server for each project.

**Implemented and tested in isolated native execution; not deployed, merged or qualified on `van-trading-core`.** See `QUALIFICATION_REALTIME_2026-11-04.md` and `evidence/2026-11-04-realtime/`.

## Source-bound upstream correction

The official upstream Realtime source is pinned to tag **v2.152.0**, commit `c8b27c7a37a5c60fee5b5a11632231d8e2c0a8c9`. Its broadcast replication-slot name is not sufficiently namespaced for two independent PostgreSQL databases sharing one cluster: replication-slot identifiers are cluster-wide.

`tools/patch_realtime.py` checks the exact original `replication_connection.ex` SHA-256 `8bf4a4a66683e6ae3348234d24551a6d06fef0059364335017fcb043b6236c5a` and produces an immutable tenant-aware amendment. Both runtime call sites use a bounded hashed slot identifier including the native tenant scope; unqualified source drift fails closed. The generated source SHA-256 is `246686ac944ac3a342d34527d0de38e2b2bdce290bbe2156ade23e898025c81d`.

`realtime-image/Dockerfile` and `compile_patch.exs` describe a derivative image build with the upstream image pinned by digest and fixed original/changed module hashes. The Docker build needs the source generated from that **exact** original revision; the generated file is not committed. The Dockerfile uses build-only placeholders and does not connect to live databases. **No admitted production derivative image was built, signed, deployed or tested on ARM64**; the real native tests executed a privately staged patched release as an ordinary user.

## Implementation and guards

`tools/shared_realtime.py` generates staged scoped PostgreSQL role/schema/HBA artifacts, a tenant registry on the existing server, the shared-service environment, tenant registration payloads, project-specific gateways and a limited overlay of the **existing** Realtime Compose service. It has no SQL execution, service restart, tenant overwrite, credential-exfiltration or production deployment command.

Project database and Realtime registry logins begin `NOLOGIN`. The exact first-match HBA prefix adds only scoped Realtime access alongside the already qualified Auth/REST/Storage access, and must be observed/reloaded before any new role is activated. All original VAN project ACLs and role identities remain protected. Project JWT keys and signing identities are checked against exact project scope; a caller-supplied hostname or tenant header cannot grant another project's access.

The shared Realtime API has a distinct management identity. Ordinary project service-role keys do not confer tenant-management authority. The gateway binds the expected native tenant host and project API key; unsolicited/foreign names, fake forwarding headers, foreign JWTs and unauthorized private channels are refused. Application-public channels remain closed in the candidate until independently qualified. Private room policy is enforced by the real upstream service and database rules. Management routes are not exposed on the project gateway.

Tenant registration is create-only. If a tenant, schema, database, native slot, or registration already exists, reconcile its actual original state before acting. Do not regenerate keys, rename original tenant identities, replay uncertain changes or restart VAN trading services to make a test pass.

## Isolated qualification

Real native checks used one disposable PostgreSQL 17.11 server, two project databases, separate Auth 2.196.0 and PostgREST 14.17 processes, one shared Storage v1.74.0 process, one shared patched Realtime v2.152.0 release, and per-project private gateways. A synthetic legacy database remained unchanged.

The combined integration ran **345 passing real-service checks**, including private WebSocket join, per-tenant `postgres_changes` observation, broadcast and presence, cross-project message denial, foreign header/token refusal, temporary replication-slot lifecycle, service restart, Storage signed-object access and REST RLS preservation while Realtime remained active. These 345 checks include previously covered core and Storage checks; do not add earlier milestone counts as independent observations.

The separate unit suite passed **164 tests**, with no failures, errors or skips. `docker compose config` passed **18 effective-model checks** using a deliberately invalid derivative-image placeholder. This parser test did not start Docker containers.

### Reproduce in an isolated non-root workspace

```sh
BASE=deploy/van-trading-core/supabase/multiproject
python3 -m unittest discover -s "$BASE/tests" -v
python3 "$BASE/tests/check_realtime_compose.py" \
  --repo /private/current-source \
  --donor-ref 96c5c6d34edcc79b3d7f6f156bed0f789f26c800 \
  --upstream-schema /private/pinned/realtime-source/priv/repo/tenant_db_dump_17.sql \
  --report /private/new-compose-report.json

DIAL_REHEARSAL_REALTIME_RELEASE=/private/patched-release \
DIAL_REHEARSAL_REALTIME_LIB=/private/staged-native-libs \
DIAL_REHEARSAL_WEBSOCKET_LIB=/private/websocket-library \
DIAL_REHEARSAL_STORAGE_NODE=/private/node24/bin/node \
DIAL_REHEARSAL_STORAGE_SOURCE=/private/pinned-storage-source \
python3 "$BASE/tests/rehearse_shared_fabric.py" \
  --pg-bin /private/postgresql17/bin \
  --pg-lib /private/pg-libs \
  --auth-bin /private/auth \
  --rest-bin /private/postgrest \
  --nginx /private/nginx \
  --report /private/new-native-report.json
```

The native runner only creates temporary loopback processes and databases; it never accepts a production database endpoint. The exact source, runtime and evidence digests are retained in the corresponding qualification record.

## Production qualification still required

Verify the actual VAN donor image and CPU architecture, the current Realtime schema and existing native tenant records, slots, user/role privileges, source-verified derivative image, and the original shared deployment and rollback authority. The official production image on ARM64 remains untested; the Compose overlay's image is deliberately a non-runnable test placeholder until reviewed replacement.

Admit and load **one complete canonical Compose configuration** across `vati-supabase.service` start/stop before enabling overlays; the existing `--remove-orphans` must not remove legitimate project services. Realtime's tenant registry and temporary-slot privileges must be coordinated with the existing PostgreSQL cluster and Storage tenant map, not blindly reinitialized.

Qualify real production CDC at load, publication/replication privileges, WAL pressure, session leases, channel quotas, reconnect/recovery, TLS/WebSocket ingress, browser SDK compatibility, rate limits and issuer/key rotation. A shared Realtime process is a common outage/trust domain; the tests do not imply independent service high availability.

**Edge Functions, project-aware Studio, Supavisor, coordinated off-host data/object backups and Nissan GTR migration remain open.** No production data or services were changed, and REA is not a blocker.
