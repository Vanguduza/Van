# Source-level adoption evidence (NOT an REA run)

REA dispatch was attempted through connected Global DIAL MCP but refused as ROOT_INGRESS_FORWARD_TOOL_NOT_ALLOWED. The dedicated dial_investigation_submit/status/result/reinvestigate tools are declared in Vanguduza/dial-development-system/agent-system/orchestration/sea/rea-investigation-port.mjs but are not available to this ChatGPT connector session. No native REA receipts are claimed here.

## Pinned sources checked 2026-10-20

- GustavoMartins123/supabase-multitenant at b38071fc93361c8f91e8032af798dcb7fadef4a1, Apache-2.0. Source docs/00-architecture.md and README: one PostgreSQL cluster, shared Realtime/Storage/Supavisor/Edge/Meta, per-project Auth/Rest/Nginx. Prefer architecture and tests, NOT direct setup.sh on a live VAN VM. Storage global tenant modifications require qualification.
- arunrajiah/supafleet at f41443b15be3ab4dac70b38d7b9e02007af85337, MIT. Source README and docs/architecture.md: shared DB server, per tenant DB and Auth/Rest/Storage, distinct JWT. Adopt database provisioning and scoped key contract. Reject wholesale Compose stack creation.
- flamingrubberduck/supabase-studio-multi-head at f88e4b4e6ba2f331ab1b2466cf7d120aaf9d47a2, Sustainable Use License 1.1. Source apps/studio/lib/api/self-hosted/embeddedOrchestrator.ts: embedded project CREATE DATABASE + pg-meta only, shared default Kong/Auth/PostgREST cannot automatically switch DBs. Adopt UI ideas only after license review.
- supabase-multitenant/supabase-multitenant at 92457a517bec281286963d6ab29d89275c350420, MIT. Source README: each project creates full Supabase stack, incompatible with one-install requirement, UX reference only.
- M7MMAD-OMAR/sbarbase at 84fcea3b59bba8fa160aae1e559bedc2a4b57c2b, Apache-2.0. Source README: central project/env console, shared DB, independent auth/rest. Production acceptance reports open; donor for acceptance and event/backup UX only.
- Vanguduza/Van existing production-definition commit 8eb1889822fc8a83f219977c15340172e16acd91: deploy/van-trading-core/supabase/docker-compose.yml defines one PG17, Envoy, GoTrue, PostgREST, Realtime, Storage, Meta, Edge, Studio, Supavisor; systemd/vati-supabase.service includes --remove-orphans; reconcile_vati_ledger.py defines restricted VATI ledger role in default postgres DB.
- Vanguduza/dial-development-system agent-system/registries/REA_RESOURCE_MANIFEST.json: pinned rea-agents 6.5.0 SHA256 531717a06e92ca651aab52691190f916fac044272c01f875e22c5e293218e699. Host/provider native_qualified false in pinned manifest: declaration is not runtime qualification.

## REA research acceptance before implementation promotion

Each result must bind exact repository commit and content hashes, static SOURCE analysis kind, native owner/lease, pinned rea-agents provider, legitimate isolation proof and original receipt. Submit one per source, inspect status and result without duplicate submission. Preserve unknowns; REA graphs are untrusted input, not code quality or correctness proof. Independently confirm key architecture claims against actual source code and disposable integration fixtures.

## Why per-project Auth/Rest is non-optional initially

Existing VAN donor uses GOTRUE_DB_DATABASE_URL with ONE POSTGRES_DB and PGRST_DB_URI with ONE POSTGRES_DB; JWT issuer/secret are instance-scoped environment variables. Another DB selected in Studio will NOT redirect these services. Functional independent Supabase API/Auth projects require a per-project process (within the same installed Compose project) or a separately verified upstream multi-DB fork with request-scoped configuration and native signed tenant routing. Favor the small proven process model before taking upstream-fork security risks.
