# DIAL Supabase Multi-Project Fabric — additive candidate

Status: **LOCAL SOURCE/ROUTING TESTED; NOT LIVE, NOT REA-QUALIFIED, NOT SUPABASE-RUNTIME-QUALIFIED.**

Owner target: one existing Supabase installation on `van-trading-core`, one PostgreSQL 17 cluster, and separate databases that function as independent Supabase Auth/API projects. No complete duplicated Supabase stacks; preserve the existing VAN/VATI database, credentials and ledger.

## Implemented in this candidate

The offline generator validates project identities and emits project-specific GoTrue, PostgREST, Storage and internal router service declarations for the **existing Compose model**. It creates no database, credential, container, network, DNS record or running service. PostgreSQL and the intended shared infrastructure are not duplicated.

Host routing rejects unknown/foreign hosts and replaces or strips forwarded tenant headers. Unqualified Functions, Realtime and readiness endpoints return HTTP 503. API-key admission, Supabase JWT verification, TLS, DB bootstrap and real isolation are **not proved by the router tests**. The generated router is not a production gateway.

Output is deterministic and written only to a new private directory, without following parent/output symlinks or overwriting files. Every artifact is bound to its manifest by a SHA-256 receipt. Output into active Supabase paths is refused.

## Run local tests and generate review artifacts

From the repository root, with Python 3.10+:

```sh
BASE=deploy/van-trading-core/supabase/multiproject
python3 -m unittest discover -s "$BASE/tests" -v
python3 "$BASE/tools/render.py" validate --manifest "$BASE/projects.rehearsal.json"
WORK=$(mktemp -d)
python3 "$BASE/tools/render.py" render --manifest "$BASE/projects.rehearsal.json" --out "$WORK/candidate"
```

The routing tests use a local Nginx executable and six labelled loopback HTTP stubs, not GoTrue/PostgREST/Storage. They skip when Nginx is unavailable; skipped routing tests are NOT routing qualification. They start only their own temporary local processes and clean them up. Nginx 1.26.3 and Python 3.13.5 were used for the recorded 29-test run; the pinned container images have not been executed.

`projects.rehearsal.json` contains Nissan GTR and a disposable fixture project, with `.invalid` domains. These are test identities, not deployed projects. Do not change `PLANNED` to `LIVE` to bypass validation.

## Deployment gates remain mandatory

1. Complete the five pinned REA investigations through an admitted native runtime; prepared requests and direct source research are not REA results.
2. Obtain real VM CPU/memory/disk/IO/connection inventory and a verified whole-VAN backup/restore drill.
3. Bootstrap separate project databases from the matching Supabase version, without copying VAN's existing `postgres` database. Qualify project-only logins, cluster-global role handling and cross-database CONNECT denial.
4. Prove independent GoTrue users, sessions, signing keys, OAuth configuration, REST/RPC/RLS and Storage behavior using actual services, including cross-project negative tests.
5. Qualify shared Realtime/Edge/Studio/Supavisor integration, API-key admission, TLS, resource limits and recovery before enabling their routes.
6. Include every project overlay in the canonical `vati-supabase.service` Compose model before starting services. The existing `--remove-orphans` launch can remove overlays omitted at boot. This patch does not alter that unit.
7. Qualify Nissan GTR's hosted schema/Auth/Storage/R2/payment migration and rollback, then obtain exact-source Zuul and owner deployment receipts.

See `QUALIFICATION_2026-10-24.md`, `ARCHITECTURE.md`, `INTEGRATION_GATES.md`, `NISSAN_GTR_CUTOVER.md`, `SOURCE_EVIDENCE.md` and `rea-requests.json`.

**No live project has been provisioned. No running VAN service has been changed.**
