# VAN Repository Audit — Infrastructure, Security, Observability, Tests, Dead Code
Branch: claude/van-system-audit-ysgtcd  HEAD: dff38a0
Auditor: infra/security/QA subagent. READ-ONLY. Evidence-first.
Status: IN PROGRESS (appended incrementally)

---

# SCOPE A — INFRASTRUCTURE

## A.1 Production topology (derived from code, not docs)

Two physically separate estates, joined only by outbound HTTP from the gateway to Hermes
and by an MCP shim from Hermes to the trading VM.

### Estate 1 — owner control plane (`dial-hermes-control`, 10.0.0.184)
```
Android device (owner phone)
  │  HTTPS, X-Van-Ingress-Token + device HMAC
  ▼
Cloudflare named tunnel  (cloudflared, token-file auth)
  deploy/systemd/van-cloudflare-tunnel.service:9
  │  plaintext HTTP to loopback
  ▼
uvicorn van_gateway.app:app  127.0.0.1:8787
  deploy/systemd/van-gateway.service:13
  ├── SQLite  data/van_gateway.sqlite3      (backend/van_gateway/config.py:12)
  ├── SQLite  data/vati_ledger.sqlite3      (config.py:21)
  ├── files   data/vati_secrets/            (config.py:25)
  └── egress → Hermes http://127.0.0.1:8642 (config.py:13)
                Exa https://api.exa.ai      (config.py:52)
                n8n http://127.0.0.1:5678   (config.py:61)  [cross-host in prod]
                browser harness :9141 / Stagehand :9140 (config.py:70,72)
                Google OAuth + APIs
                van_commander_url (trading VM, mTLS) (config.py:26-28)
```

### Estate 2 — Oracle trading VM (`van-trading-core`, 10.0.1.233, ARM64 A1.Flex 2 OCPU/12 GB)
```
Internet :80/:443 ──► Caddy (Let's Encrypt)   deploy/van-trading-core/caddy/Caddyfile:1
     ├── /ea/v1/*, /health   → 127.0.0.1:9443  vati-mt5-pull.service   (Caddyfile:4-7)
     └── /automation-webhook{,-test,-wait}/* → 127.0.0.1:5678 n8n      (Caddyfile:9-12)
     └── everything else → 404                                          (Caddyfile:20-22)

admin CIDRs only (10.0.0.123/32, 10.0.0.184/32) ──► :22, :9133
     └── :9133 vati-commander.service (uvicorn TLS, VAN_COMMANDER_BIND=0.0.0.0)
                deploy/van-trading-core/systemd/vati-commander.service:14
                env/van-trading-core.env.example:15

loopback only:
  :9134 vati-vekl.service (node trading/vekl/server.mjs)
  :5678 n8n + :5679 runner broker  (automation/docker-compose.yml:96)
  :3000 supabase-studio, :8000 envoy api-gw, :5432 postgres,
  :5433/:6543 supavisor       (supabase/docker-compose.override.yml:4-21)
  vati-session@<alias>.service — one process per trading account
  
external, not in this repo's runtime: Windows MT5 host running
  deploy/van-trading-core/windows/mt5_worker/mt5_bridge_worker.py (mTLS peer)
  plus the MQL5 EA (deploy/van-trading-core/mql5/VanBridgeEA.mq5) which POLLS
  https://<public host>/ea/v1/<alias>/poll over the public Caddy front.
```

## A.2 Complete env-var inventory — backend/van_gateway/config.py
Pydantic `BaseSettings`, `env_prefix="VAN_"`, `env_file=".env"`, `extra="ignore"` (config.py:9).
`extra="ignore"` means a typo'd `VAN_*` var is silently dropped — no boot-time validation.

| line | var (VAN_ + upper) | default | posture |
|---|---|---|---|
| 12 | DATABASE_PATH | `data/van_gateway.sqlite3` | **relative path** — depends on CWD |
| 13 | HERMES_BASE_URL | `http://127.0.0.1:8642` | plaintext loopback |
| 15 | HERMES_BEARER_TOKEN | `""` | empty = unauthenticated call to Hermes |
| 16 | INTERNAL_CONTROL_TOKEN | `""` | **fail-closed when empty** |
| 17 | INGRESS_TOKEN | `""` | **fail-closed: 503 `ingress_auth_unconfigured`** (app.py:375-376) |
| 18 | DEVICE_SECRET_FERNET_KEY | `""` | empty ⇒ device secrets unencrypted/rejected |
| 21-25 | VATI_LEDGER_PATH / ACCOUNTS_REGISTRY / LAKE_ROOT / REPORTING_CURRENCY / SECRETS_DIR | relative `data/…`, `USD` | relative paths |
| 26-28 | VAN_COMMANDER_URL / _TOKEN_FILE / _CA_FILE | `""` | empty ⇒ trading control plane unreachable |
| 29 | PUBLIC_BASE_URL | `http://127.0.0.1:8787` | used in OAuth redirect construction |
| 30 | VATI_DERIV_APP_ID | `"1089"` | **Deriv's public demo app id**, not VAN's |
| 32 | OWNER_INTENT_MAX_AGE_SECONDS | 86400 | 24h intent reuse window |
| 33 | ATTENTION_BUDGET_PER_HOUR | 12 | |
| 37-39 | GOOGLE_TOKEN_FERNET_KEY / OAUTH_CLIENT_ID / OAUTH_CLIENT_SECRET | `""` | fail-closed |
| 43-47 | GOOGLE_AI_PLAN=`UNKNOWN`, CLOUD_PROJECT_ID, GEMINI/CLOUD_RUNTIME_CONFIGURED=**False**, CONSUMER_CONNECTED_CAPABILITIES | off | |
| 51-54 | EXA_API_KEY, EXA_BASE_URL, **EXA_EGRESS_ENABLED=False**, timeout 20s | OFF | |
| 58-60 | **AUTOMATION_ENABLED=False**, **AUTOMATION_INGRESS_ENABLED=False**, **AUTOMATION_EGRESS_ENABLED=False** | OFF | |
| 61-67 | AUTOMATION_N8N_BASE_URL, API_KEY, EXPECTED_VERSION, GRANT_SIGNING_KEY, GRANT_TTL=300s, TIMEOUT=15s | | |
| 67 | AUTOMATION_MAX_CONCURRENCY | 1 | |
| 69-75 | **BROWSER_ENABLED=False**, harness/Stagehand URLs + expected versions, model provider/name empty | OFF | |
| 80-84 | **VEKL_ENABLED=False**, base_url/session/principal/bearer empty, 8s timeout | OFF | |
| 86-90 | **OBSIDIAN_ENABLED=False**, vault path empty, max 2 MB/file, 20k files, 30s refresh | OFF |
| 92-99 | **NOTEBOOK_ENTERPRISE_ENABLED=False**, project number/location/SA file/token file/upload root, 100 MB cap | OFF |
| 101-107 | **NOTEBOOK_CONSUMER_ENABLED=False**, profile_dir marked *legacy*, secret ref `secretref://browser/google-primary`, headless True | OFF |
| 109 | REQUIRE_HERMES_FOR_MUTATIONS | **True** (fail-closed) | |
| 110 | EVENT_PAGE_SIZE | 100 | |

Env vars read **outside** `Settings` (invisible to the above, no defaults documented):
- `backend/van_gateway/automation/policy.py:303` — `VAN_BROWSER_SEMANTIC_MAX_TIER` default `"L5"`.
- `backend/van_gateway/google/transport.py:124` — `VAN_ALLOW_FAKE_GOOGLE_TRANSPORT` and `PYTEST_CURRENT_TEST` (see B.4).
- `trading/commander/app.py:49-60` — 12 `VAN_COMMANDER_*` / `VAN_VEKL_*` / `VAN_SECRETS` vars with **absolute production defaults** (`/opt/van-trading/...`), plus `VAN_COMMANDER_AUTOCREATE` (app.py:309) which decides whether the ASGI app object even exists.
- `trading/commander/accounts.py:165,275` — `VAN_MT5_PULL_QUEUE` (default `:memory:` — a silent data-loss default), `VAN_PUBLIC_HOST`.
- `trading/vati/accounts/registry.py:162` — arbitrary env-var credential indirection.

## A.3 Single points of failure
1. **One SQLite file, one host, no replica, no backup.** `data/van_gateway.sqlite3` holds
   devices, audit chain, approvals, events, missions, Google refresh tokens, context graph.
   No backup job exists anywhere in `deploy/`, `tools/`, or systemd. Loss of the VM = loss
   of all owner state and the entire audit chain.
2. **Cloudflare named tunnel is the only ingress path.** `van-cloudflare-tunnel.service`
   `Requires=van-gateway.service` (line 4) — a gateway restart failure takes the tunnel down
   too; `Restart=always` on the tunnel but only `on-failure` on the gateway (`van-gateway.service:14`).
   There is no fallback ingress (no Tailscale, no LAN listener, no direct IP).
3. **cloudflared has no pinned version and `--no-autoupdate`** (`van-cloudflare-tunnel.service:9`)
   — the binary at `%h/bin/cloudflared` is installed out of band and never updated. Undocumented
   dependency: nothing in the repo installs it (`install_van_cloudflare_tunnel.sh:19` only *checks*).
4. **Hermes is an unversioned, unhealth-checked hard dependency.** `require_hermes_for_mutations=True`
   (config.py:109) means every mutation fails when Hermes is down. `van-gateway.service:3` only
   has `After=hermes-gateway.service`, no `Requires`, and `hermes_bearer_token` defaults empty.
5. **Bridge PKI expires silently.** `pki/make-bridge-pki.sh:11` `DAYS=825`, CA 3650 days, and
   `issue()` at line 19 returns early if `$name.crt` exists — so re-running bootstrap **never
   renews**. No expiry monitoring in `qualify.sh`. At day 825 commander mTLS and the MT5 worker
   link both break with no warning.
6. **Trading VM is single-instance and rebuilt by a script with hardcoded OCIDs/IPs**
   (`oci/rebuild-van-trading-core.py:6-13`: `PRIVATE_IP='10.0.1.233'`, `ADMIN_IP`, `HERMES_IP`,
   `VEKL_IP`, a full instance OCID, and `ADMIN_KEY=~/.ssh/node-admin-to-trading`).
7. **n8n, Supabase and the browser runtime all run on one 2-OCPU/12 GB ARM VM**
   alongside every `vati-session@` trading process. Memory limits sum to ~3 g (Postgres) +
   1.5 g (n8n) + 1 g + 0.5 g = over half the box before any trading session starts.

## A.4 Ingress / public exposure
- **Public, unauthenticated at the edge:** `https://$VAN_PUBLIC_HOST/ea/v1/*` and `/health`
  (`Caddyfile:4-7`). Auth is app-level HMAC with a nonce table — `trading/vati/execution/mt5_pull.py:56`
  (`nonces` table), `nonce_fresh()` line ~95, `SKEW_S=60` line 39. That part is genuinely
  replay-protected. But `/health` is world-readable and Caddy applies **no rate limiting**, so the
  HMAC verify path is an unauthenticated CPU oracle open to the internet.
- **Public n8n webhooks:** `Caddyfile:9-12` proxies three webhook prefixes straight to n8n with
  no edge auth, no allowlist, no rate limit. Whether a given webhook requires a credential is a
  per-workflow choice inside n8n, i.e. **not enforced by infrastructure**.
- Caddy sets HSTS/nosniff/Referrer-Policy (`Caddyfile:14-18`) but **no CSP, no frame-options,
  no `X-Robots-Tag`**, and no request-size limit.
- **Commander binds 0.0.0.0:9133** (`env/van-trading-core.env.example:15`). It is TLS-protected
  and firewalled to two /32s by ufw (`bootstrap.sh:228-229`) and the OCI image firewall
  (`oci/harden-oracle-image-firewall.sh:40-41`). Defense is entirely firewall; bind address is
  the wrong default. Note also `uvicorn --ssl-certfile` with **no `--ssl-ca-certs`/client-cert
  requirement** in `vati-commander.service:14` — so the "mTLS" seam described in
  `pki/make-bridge-pki.sh:3` is **not actually enforced server-side**; only a bearer token is.
- Gateway listens plaintext on 127.0.0.1:8787 (`van-gateway.service:13`) — correct, but it means
  anything else on that host (any user process) can reach it; the only gate is the ingress token.

## A.5 Credential duplication and handling
- `VAN_INTERNAL_CONTROL_TOKEN` lives in `~/.config/van/gateway.env`, is read by the gateway,
  by `tools/runtime/create_van_pairing_ticket.py:37`, by `tools/google/certify_knowledge_runtime.py:59`,
  and must also be configured in Hermes' MCP config by
  `tools/hermes/register_owner_runtime_mcp.sh`. One static value, ≥4 copies, **no rotation path**.
- `VAN_INGRESS_TOKEN` is generated once (`install_van_gateway_service.sh:43-55`) and must be
  copied into the Android app; regeneration is not idempotent-safe (the `grep -Eq '.{32,}'`
  guard means an existing short token is silently replaced, breaking the device).
- Supabase: `generate-env.sh:22-28` regenerates **only 15 keys**. The donor demo values for
  `PG_META_CRYPTO_KEY`, `REALTIME_DB_ENC_KEY=supabaserealtime`, `S3_PROTOCOL_ACCESS_KEY_ID`/`_SECRET`,
  `MINIO_ROOT_PASSWORD=secret1234`, `SMTP_PASS=fake_mail_password` survive into the production
  `.env` (see `supabase/env.example:63,67,75,86,89,190,290`). Also `FUNCTIONS_VERIFY_JWT=false`
  (`env.example:305`).
- Bridge PKI private keys are copied by hand to a Windows host (`bootstrap.sh:242`) — no
  enrollment protocol, no revocation, no CRL/OCSP (the CA is created with `cRLSign` at
  `make-bridge-pki.sh:15` but no CRL is ever published).
- Commander/VEKL tokens are `openssl rand -hex 32` files (`bootstrap.sh:129-130`), never rotated.

## A.6 Unbounded storage / retention — **the single largest operational gap**
Repo-wide search for retention, prune, vacuum, purge, logrotate found exactly **one** retention
control in the entire system:
- `deploy/van-trading-core/automation/docker-compose.yml:64-66` — n8n
  `EXECUTIONS_DATA_PRUNE=true`, `MAX_AGE=168h`, `PRUNE_MAX_COUNT=10000`.

Everything else grows without bound:
- Gateway SQLite: audit chain, events table, missions, mission_events, attention, context
  facts/edges. The only `DELETE`s found are **functional** (TTL on OAuth pending state
  `trading/accounts.py:111`, idempotency/approval key expiry `approval/service.py:149,204`,
  `command/authority.py:85`, FTS reindexing `knowledge/obsidian.py:172,249,262`,
  mission rebinding `mission/binding.py:235-238`). **No audit or event retention at all.**
- `/var/log/van-trading` (`VAN_COMMANDER_LOG_DIR`) — **no logrotate config anywhere in the repo**.
- `/var/lib/van-trading/heartbeats/*.json`, `/var/lib/van-trading/lake`, `/var/lib/van-trading/backtests`,
  `bootstrap-<STAMP>.json` written on every bootstrap run (`bootstrap.sh:240`) — never cleaned.
- `/var/lib/van-trading/mt5-pull.sqlite` `commands` table: rows are marked `DONE`
  (`mt5_pull.py:complete`) but **never deleted**; only the `nonces` table self-prunes
  (`mt5_pull.py:nonce_fresh`). Every trade ever routed accumulates forever.
- `$STATE_ROOT/runtime.previous` kept for one generation (`install_van_gateway_service.sh:69-72`) —
  a rollback path, but the only one.

## A.7 Backups, monitoring, recovery
- **Backups: none.** The word appears only for Hermes MCP config files
  (`deploy/van-trading-core/hermes/register-commander-mcp.sh:68-69`,
  `tools/hermes/register_owner_runtime_mcp.sh:130-132`) and in the *name* of a canary in
  `tools/certification/certify_automation_runtime.py:5`. No Postgres dump, no SQLite backup,
  no volume snapshot, no restic/borg, no OCI boot-volume backup policy.
- **Monitoring: pull-only and manual.** `qualify.sh` is a one-shot report run by hand
  (`bootstrap.sh:246` tells the operator to run it). Nothing schedules it — no timer unit, no cron.
  `N8N_METRICS=true` (`automation/docker-compose.yml:72`) exposes a Prometheus endpoint that
  **nothing scrapes**. No alerting, no uptime check, no notification on unit failure.
- **Recovery paths that exist:** `runtime.previous` (gateway code only),
  `rules.v4.van-original` (`harden-oracle-image-firewall.sh:23`), Hermes-config `.van-bak-<stamp>`,
  `oci/rebuild-van-trading-core.py` (full VM rebuild — destroys all local state),
  `python -m vati replay-verify` (`degraded/registry.py:117`).
- **Recovery paths that do not exist:** gateway DB restore, Supabase/Postgres restore, device
  re-pairing after DB loss, PKI rotation, ingress-token rotation, Cloudflare tunnel failover.

## A.8 CI
`.github/workflows/van-ci.yml` — 2 jobs, no matrix, no caching, no dependency pinning
(`pip install -r requirements.txt` at line 22 with no hash pinning / lockfile).
- Backend job runs `backend` pytest, `tests/contracts`, `hermes/policy/tests`, `tests/hermes`,
  two trading test files (lines 33) — **`tests/scenarios` and the rest of `trading/tests` are
  never run in CI** (lead's baseline: 251 trading tests exist; CI runs 2 files).
- Lines 48-64 are a genuinely good fail-closed proof: certification scripts must exit 2.
- `tools/ci/github-actions-ci.yml` is a **stale duplicate** of the workflow (missing the policy,
  automation, browser, fail-closed and latency steps) installed by
  `tools/ci/install_github_workflow.py` — drift hazard: installing it silently downgrades CI.
- No SAST, no dependency audit, no secret scanning, no container image scanning, no SBOM step
  (an `artifacts/release/sbom.cdx.json` is committed but nothing in CI regenerates or verifies it).
- No Android instrumentation tests (`:app:testDebugUnitTest` only, line 93) — no emulator job.

---

# SCOPE B — SECURITY THREAT MODEL

## B.1 Owner authentication — the layers that actually exist
Three independent layers on the normal Android path, all verified in
`backend/van_gateway/app.py:360-388`:
1. `X-Van-Ingress-Token` — one static, high-entropy, shared bearer. Compared with
   `hmac.compare_digest` (app.py:378). **Fail-closed**: 503 when unset (app.py:375-376).
2. `X-Van-Device-Token` — per-device, revocable; only its SHA-256 is stored
   (`auth/service.py:182-189`).
3. Per-command HMAC-SHA256 over a canonical string, key = per-device secret encrypted at
   rest with a dedicated Fernet key (`auth/service.py:51-67, 250-259`).
Plus, for A4 only: an ECDSA-P256 biometric-bound Keystore signature over a one-time
server-issued challenge (`approval/service.py:28-40`).

Routes that bypass layer 1+2 entirely:
- `POST /v1/devices/pair` (app.py:361-362) — reachable from the public tunnel by anyone.
  Gated only by a single-use hashed pairing ticket with 60-3600 s TTL (`auth/service.py:96`).
- `GET /v1/trading/oauth/*/callback` (app.py:363-364) — unauthenticated by design (OAuth
  redirect), so the `state` parameter is the only anti-CSRF; TTL enforced at
  `trading/accounts.py:111`.

### B.1.1 — no lockout, no rate limit, no brute-force control anywhere
There is no failed-attempt counter, no exponential backoff, no IP throttle and no Caddy/
Cloudflare rate-limit rule for `/v1/devices/pair`, the ingress token, the device token, the
A4 approval challenge or the MT5 `/ea/v1/*` HMAC. A tunnel-reachable attacker gets unlimited
attempts. **Highest-severity gap in the auth design.**

### B.1.2 — enrollment grants are effectively permanent
`auth/service.py:167` and `:208` both mint the enrollment capability grant with
`expires_at_unix = now + 10*365*24*3600` — a **ten-year** owner grant. Nothing renews or
re-attests it. Revocation works (`auth/service.py:216-231`) but is the only expiry path.

## B.2 Replay — **the command `nonce` is signed but never stored or checked**
`canonical_command_v2` covers `nonce` (`auth/service.py:299,326`) and the orchestrator passes
it through (`orchestrator.py:135`), but a repo-wide search for a command-nonce store finds
**nothing**: the only nonce tables are `automation_run_nonces`
(`storage/db.py:530`, consumed atomically at `automation/grants.py:269-301`) and the MT5
bridge `nonces` table (`trading/vati/execution/mt5_pull.py:56`). There is **no
`command_nonces` table and no uniqueness check on `CommandRequest.nonce`.**

Command replay is therefore defended only by:
- the idempotency key (`orchestrator.py:78`), and
- three time windows: explicit `expires_at_unix` (orchestrator.py:159), typed-action
  `max_age_seconds` (orchestrator.py:167), and the global 24 h `owner_intent_max_age_seconds`
  (orchestrator.py:176, default `config.py:32`), tightened to ≤60 s only when the client
  sets `no_stale_replay` (orchestrator.py:308-311).

**And the idempotency check is not atomic.** `IdempotencyService.begin`
(`idempotency/service.py:36-54`) does a `SELECT` on one connection and then an `INSERT` on
another, with **no transaction and no `BEGIN IMMEDIATE`**. Combined with the known storage
design (a fresh aiosqlite connection per query, no WAL, no `busy_timeout`), two concurrent
identical signed commands can both see `row is None` and both proceed to execute.
Contrast `auth/service.py:102` and `:138`, which *do* use `BEGIN IMMEDIATE` — so the pattern
was known and simply not applied here. **A captured A1-A3 command can be replayed for double
execution inside its validity window.**

## B.3 Prompt injection — recorded, mostly not obeyed, but detection is a substring blocklist
Three separate, divergent hardcoded marker lists:
- `orchestrator.py:27-33` — 6 markers, command text.
- `browser/policy.py:49-55` — 13 markers, page DOM/extraction.
- `automation/events.py:76-81` — 13 markers, inbound external events.
All are lowercase substring matches. Any paraphrase, unicode homoglyph, base64, or
non-English phrasing passes. They are detection theatre; the real defence is architectural.

**The architectural defence is sound and worth crediting:** page content can never raise the
action class (`browser/policy.py:178-181` clamps `proposed_action_class` to the task ceiling),
secrets in observations cause a hard refusal rather than redaction (`browser/policy.py:145-150`),
and a subagent cannot create a VAN command or extend its own budget (`browser/subagent.py`).

**But the command-level rejection is client-opt-in.** `orchestrator.py:334` runs the injection
check only `if req.context_trust == ContentTrust.UNTRUSTED`. `context_trust` is a field on
`CommandRequest` with default `ContentTrust.CONVERSATION` (`models.py:123`), set by the
Android client. It is inside the v2 signature so it cannot be flipped in transit — but a
compromised or simply lazy client can label attacker-supplied text as `CONVERSATION` and the
gateway never inspects it. Nothing server-side ever derives trust from the content's origin.

**Dead branch:** `browser/subagent.py:232` aborts on `InjectionAssessment.CONFIRMED_INJECTION`,
but `assess_injection` (`browser/policy.py:152-158`) can only ever return `SUSPECTED_INJECTION`
or `NONE_DETECTED`. The only producer of `CONFIRMED_INJECTION` in the whole repo is a test
(`backend/tests/test_browser_subagent.py:273`). In production that abort never fires.

## B.4 Confused deputy — Hermes MCP + the single internal control token
`internal_control_route()` (app.py:304-357) marks a large privileged surface as
Hermes-only: all `/v1/runtime/*`, all `/v1/automation/*`, non-GET `/v1/browser/*`,
`PUT /v1/projects/*/truth`, device enroll / pairing-ticket / revoke, `POST /v1/trading/halt`,
trading ticket confirm, and six `/v1/google/*` routes including `test-transport`.
All 17+ handler-level calls to `require_internal_control` (app.py:443…908, plus
`automation/api.py:193…565`) compare against **one static `VAN_INTERNAL_CONTROL_TOKEN`**.
- No per-caller identity, no scoping, no expiry, no rotation, no audit of *which* principal
  used it. Device enrollment, device revocation, Project Truth injection, Google connect/revoke
  and the trading halt all share one credential.
- The token is duplicated into Hermes' MCP config, two CLI tools and an env file (see A.5).
  Any Hermes skill, any MCP server Hermes loads, and anything that can read
  `~/.config/van/gateway.env` obtains **full gateway root**. That is the confused-deputy
  exposure: Hermes is driven by model output, and Hermes holds the root credential.
- Middleware note: when the internal token check fails, control **falls through** to the
  ingress+device path (app.py:367-371 has no `else: 403`). Privileged routes are saved only
  by the handler-level re-check. Any future route added under an internal-control prefix that
  forgets `require_internal_control` becomes owner-device reachable. Latent footgun.

`POST /v1/google/test-transport` (app.py:598-603) does swap the live transport
(`google.transport = FakeGoogleTransport(); google.oauth = None`) with no undo route and no
environment guard at the route. The construction guard at `google/transport.py:124` means
that outside pytest, without `VAN_ALLOW_FAKE_GOOGLE_TRANSPORT=1`, the constructor raises
`RuntimeError` — so in production it **fails closed but as an unhandled 500** (no try/except
at app.py:601), leaking a traceback. Lower severity than it first appears, but the route
should not exist on the production app at all.

## B.5 Privilege escalation, cross-project contamination, stale credentials
- `resolver.stronger_class` (orchestrator.py:153) can only *raise* the action class from the
  signed value — correct direction. A5 is an unconditional deny (orchestrator.py:198-206).
- A4 requires `ResolutionMode.EXACT_ACTION` before a challenge is even issued
  (orchestrator.py:210-226) — a genuinely strong control.
- Project isolation is enforced through `ProjectRouter.load_truth` + a truth-SHA gate for
  A3/A4 (orchestrator.py:363-379). Cross-project contamination is guarded by requiring
  current Project Truth, not by a per-project credential boundary — a compromised gateway
  reaches every project.
- Context poisoning is guarded: `context/service.py:79` and `:300` refuse to let
  `UNTRUSTED_EXTERNAL`/`MODEL_DERIVED` candidates take high authority. Good.
- **Stale credentials:** nothing expires. Ingress token: no rotation. Internal control token:
  no rotation. Device HMAC secrets: no rotation. Enrollment grants: 10 years. Bridge PKI:
  825 days with no renewal (A.3 #5). Commander/VEKL tokens: never rotated. Google refresh
  tokens are encrypted at rest (`config.py:37`) but there is no re-consent cadence.

## B.6 False execution reports
`AuditService.record` (`audit/service.py:34-77`) is a **plain INSERT into a flat table**
(`storage/db.py:75-90`): `id` is a random UUID4, and there is **no `prev_hash`, no chain
hash, no signature, no sequence**. Anyone with write access to the SQLite file can insert,
alter or delete audit rows undetectably. Contrast the VATI trading ledger, which *does* have a
verifiable chain (`trading/service.py:138` `verify_chain()`, `:224,:255` `event_hash`/
`chain_hash`). **The owner-authority audit log is not tamper-evident; the trading ledger is.**
This directly contradicts the system's positioning of audit as a protected surface
(`hermes/policy/van_policy_hook.py:23` lists `audit`/`audit_log` as PROTECTED_SURFACES).

Positive: the orchestrator records a denial/expiry/degraded audit row on **every** rejection
path before returning, so refusals are not silent.

## B.7 Android-side: overlay, microphone, and voice spoofing
Manifest (`android/app/src/main/AndroidManifest.xml:4-16, 51-64`) requests
`RECORD_AUDIO`, `SYSTEM_ALERT_WINDOW`, `FOREGROUND_SERVICE_SPECIAL_USE`,
`USE_BIOMETRIC`, `RECEIVE_BOOT_COMPLETED`, registers a `RecognitionService`, a
`FloatingOverlayService` and a `VanNotificationListenerService`.

**There is no speaker verification anywhere in this repository.** A repo-wide search for
`speaker`, `voiceprint`, `voice enroll` returns zero hits outside this finding. Consequences:
- Anything audible to the phone can issue a command. The wake path
  (`android/app/src/main/java/com/dial/van/voice/WakeRuntime.kt`) and
  `VoiceInputManager` (`voice/VoiceInterfaces.kt:57-60`) produce a transcript with no
  claim about *who* spoke.
- `speech_evidence_ref` is a **synthesized string, not evidence**:
  `android/app/src/main/java/com/dial/van/voice/VoiceRecognitionModels.kt:92`
  `val speechEvidenceRef: String = "android://voice/$turnId"`. No audio hash, no confidence,
  no enrollment reference. It is faithfully carried into the HMAC (`auth/service.py:329`) and
  into audit (`orchestrator.py:516`) where it creates a **false impression of voice provenance**.
- The gateway never branches on `OriginChannel.VOICE`. The only `origin_channel` comparison in
  the entire backend is `orchestrator.py:68`, checking `== OriginChannel.UI` for the legacy-v1
  default check. A VOICE command and a UI command are treated identically.
- **The one real mitigation** is that A4 (destructive / send-as-owner / payment) requires a
  fresh biometric Keystore signature (`approval/service.py`, orchestrator.py:280-303). So a
  voice-spoofing attacker within earshot can reach **A1, A2 and A3 — including bounded writes —
  but not A4.** Given A3 is "bounded write", that is still a meaningful unauthenticated
  write primitive for anyone near the phone or able to play audio at it.
- Overlay (`SYSTEM_ALERT_WINDOW`) is used by VAN itself; there is no
  `setHideOverlayWindows`/`FLAG_SECURE`-style protection on the biometric approval surface,
  so a *hostile* overlay from another app could tapjack the A4 confirmation. No mitigation found.

## B.8 Hardcoded secrets — repo-wide sweep (shape/location only, no values reproduced)
Sweep over `*.py *.kt *.js *.mjs *.ts *.json *.yaml *.yml *.sh *.ps1` for
`key|secret|token|password|bearer` assigned a ≥16-char literal, plus JWT / PEM / `AKIA` /
`sk-` / `ghp_` shapes. **No live credential found.** Hits classified:
- `deploy/van-trading-core/supabase/env.example:35,36` — the well-known **public Supabase
  demo JWTs** (`ANON_KEY`, `SERVICE_ROLE_KEY`). Regenerated by `generate-env.sh:23`. Benign
  as shipped, but see A.5: the *other* donor demo secrets on lines 63, 67, 75, 86, 89, 190,
  290 are **not** regenerated and will reach production `.env` verbatim.
- `trading/tests/test_n8n_provisioner.py:10`, `backend/tests/test_a4_owner_approval.py:152`,
  `backend/tests/test_trading_api.py:196`, `backend/tests/test_rev31_runtime_wiring.py:414`,
  `backend/tests/test_permissions_computeruse_verifiers.py:57`,
  `backend/tests/test_owner_runtime.py:236` — obvious test fixtures / negative-detection
  corpora. Correct.
- `android/.../VanGatewayClient.kt:528` — a SharedPreferences **key name**, not a value.
- `tests/contracts/test_automation_browser_governance.py:241` — a detector's own pattern list.

`.gitignore` coverage is good and specific: `.env`, `.env.*` with `!.env.example`, `*.pem`,
`*.p12`, `*.jks`, `keystore.properties`, `google-oauth-client.json`, `gemini.env`,
`artifacts/google/*.sqlite3`, `artifacts/local/`, `*.log`. Gaps: no `*.key`, no `*.crt`,
no `*.token`, no `id_rsa`, no `*.kdbx`, no `secrets/` directory rule — the bridge PKI writes
`ca.key`, `commander.key`, `client.key` (`pki/make-bridge-pki.sh:15,20`) which would be
committed if ever generated inside the tree (`OUT` defaults outside the tree, so currently safe).

`artifacts/` leakage check: attestation JSONs contain hostnames (`dial-hermes-control`), git
commit SHAs, capability states, bind addresses and boolean assertions — **no token values, no
emails, no private IPs**. `artifacts/release/provenance.json` is hashes only. Clean.
`oci/rebuild-van-trading-core.py:6-8` does commit internal private IPs and a full instance
**OCID** — not a secret, but unnecessary infrastructure disclosure in a public repo.

## B.9 Tool-argument poisoning / malicious document content
- Automation: `ExternalEventIngestor` (`automation/events.py:83-125`) bounds payloads at
  256 KiB, dedupes, verifies provider HMAC with a ±5-minute skew window
  (`verify_provider_signature`, line ~117), and labels everything
  `UNTRUSTED_EXTERNAL` (`events.py:34`). Ingress is default-off (`config.py:59`). Good.
- Browser: `assert_no_secrets` refuses rather than redacts (`browser/policy.py:145-150`) and
  regex-scans for api-key/bearer/`sk-`/OTP shapes (`browser/policy.py:40-45`). Good.
- Payments: `computer_use/fabric.py:212-221` forces `POLICY_FORBIDDEN` when
  `payment_suspected or injection_suspected`. Matches `docs/SECURITY_POLICY.md:34-40`.
- Gap: nothing equivalent guards Google/Gmail/Drive *document* content on its way into a
  Hermes prompt. `SECURITY_POLICY.md:90` asserts email/Drive content is "labeled untrusted
  external data", but the only enforcement found is `google/mesh.py:97,368`
  (`trust: str = "UNTRUSTED"` as a default on an artifact record) — a label on a stored row,
  not a filter on a prompt path.

---

# SCOPE C — OBSERVABILITY

## C.1 The headline: there is no application logging at all
```
grep -rn "import logging" --include=*.py backend/ trading/ hermes/ tools/   →  0 hits
grep -rn "print("  --include=*.py backend/van_gateway/                     →  0 hits
```
The entire Python codebase — gateway, trading, Hermes policy, tooling — contains **zero
`logging` imports, zero loggers, zero print statements, no structlog, no OpenTelemetry, no
Prometheus client**. Nothing is structured, nothing is levelled, nothing is correlated.

What actually reaches a log file:
- uvicorn's own default access/error log via journald for `van-gateway.service`
  (`deploy/systemd/van-gateway.service:13` — no `--log-config`, no `--access-log` tuning).
- `vati-commander.service:14` and `vati-mt5-pull.service:13` explicitly set
  `--log-level warning` / `log_level='warning'`, i.e. **access logs are suppressed** on the
  trading plane. There is no request log for the commander API or the MT5 bridge.
- `VAN_COMMANDER_LOG_DIR=/var/log/van-trading` is configured
  (`trading/commander/app.py:52`, `env/van-trading-core.env.example:10`) but nothing in the
  Python writes to it; and, as noted in A.6, there is no logrotate for it either.

Consequence: a production incident on the gateway leaves **no diagnostic trail other than the
SQLite `audit` table**. There is no way to see a stack trace, a slow query, a retry, an
upstream timeout, or a rejected request's headers.

## C.2 The audit table is the only real trace, and it is shallow
`audit/service.py:34-77` writes one flat row per outcome with these correlation handles:
`command_id`, `device_id`, `project_id`, `capability`, `approval`, `model_delegate`, `tool`,
`before_json`, `after_json`, `result`, `failure_reason`, `evidence_pointer`.
- It records **outcomes, not spans**: no start/end, no duration, no parent.
- No `turn_id` column, no `mission_id`, no `run_id`, no `assignment_id`, no `trace_id`.
- Not tamper-evident (see B.6).
- No retention (see A.6) — it grows forever, and it is the same SQLite file that serves
  every live request.

## C.3 Correlation identifiers exist but do not span the chain
Four different, unjoined identifier families:
| id | minted in | reaches |
|---|---|---|
| `command_id` / `idempotency_key` | Android → `models.py` | orchestrator, audit |
| `turn_id` | Android voice/UI | orchestrator (`orchestrator.py`), approvals (`approval/service.py`), browser assignments (`browser/subagent.py`), standing intents (`command/standing.py`) — **but not the audit table** |
| `run_id` / `grant_id` / `nonce_hash` | `automation/grants.py:179-198` | automation dispatch + n8n |
| `correlation_id` | `trading/service.py`, VATI ledger | trading ledger only (`test_trading_api.py:118`) |

So the intended chain **command → mission → browser task → Hermes run** breaks in at least
three places:
1. **command → audit**: `turn_id` is never persisted to `audit`, so two commands in one voice
   turn cannot be grouped after the fact.
2. **gateway → Hermes**: `HermesBridge` carries no trace header; a Hermes run cannot be tied
   back to a `command_id` except by timestamp correlation.
3. **gateway → n8n / browser worker**: the run grant carries `command_id`
   (`automation/grants.py:184`) — this is the **one link that is done correctly** — but n8n's
   own execution log is a separate Postgres database with a 168-hour retention
   (`automation/docker-compose.yml:65`), so the far end of that link expires in a week.
4. **gateway ↔ trading**: the VATI ledger has its own `correlation_id` and hash chain; there
   is no shared identifier with the gateway audit row beyond what an operator eyeballs.

## C.4 Event bus — a polled SQLite table, no push, no fan-out
`events/bus.py:9-56`. `publish` is a plain `INSERT` (line 17); `replay` is a `SELECT … WHERE
seq > ? LIMIT page_size` plus a per-device cursor upsert (lines 24-46). No SSE, no websocket,
no FCM, no long-poll, no notification. Only **two producers exist in the whole backend**:
- `app.py:569` — `decision.escalated`
- `app.py:703` — `attention.upserted`
The `events` table has no retention and no index beyond the `seq` PK (`storage/db.py:92-95`),
and `replay` signals truncation only by `len(events) == page_size` (bus.py:46) — a device
that falls more than `page_size` behind must poll repeatedly with no backpressure signal.
`DegradedCode` for this exists (`degraded/registry.py:82`: *"Run paginated replay from seq 0
and acknowledge reset"*), which tells you the failure mode was anticipated but not solved.

## C.5 Metrics — defined, collected in-process, exported nowhere
- `trading/vati/observability/metrics.py:1-47` — a stdlib counter/gauge registry with
  Prometheus text exposition (`exposition()`, line 33). Line 2 says it plainly:
  *"OpenTelemetry export is added at adoption."* **Nothing serves `exposition()` over HTTP.**
  A `grep` for a `/metrics` route returns nothing. The metrics die with the process.
- `backend/van_gateway/automation/telemetry.py` — `RunTiming` with compile/dispatch/execution/
  external-wait/verification phases and a `van_overhead_ms` property (lines 35-68). Well
  designed, persisted to SQLite, **never exported and never alerted on**.
- `N8N_METRICS: "true"` (`automation/docker-compose.yml:72`) exposes a real Prometheus
  endpoint on 127.0.0.1:5678 that **nothing scrapes** — there is no Prometheus, no
  Grafana, no agent, no scrape config anywhere in `deploy/`.

## C.6 Health and heartbeats — pull-only, manual
- `GET /health` on the gateway (`app.py:397`) aggregates Hermes health. Probed by the
  installers (`install_van_gateway_service.sh:82-104`) and presumably by Cloudflare. No
  alert fires on failure.
- Trading sessions write JSON heartbeat files (`trading/vati/app/cycle.py:114` →
  `/var/lib/van-trading/heartbeats/*.json`) read back by `commander/app.py:127-170` and
  age-checked at `qualify.sh:44` (stale > 300 s ⇒ AMBER, and AMBER is **non-required**, so
  `qualify.sh` still exits 0 with every trading session dead).
- `qualify.sh` is the closest thing to monitoring and it is a manual one-shot (A.7).

## C.7 What a developer can and cannot trace end to end
**Can trace:**
- A single command's authority decision: `audit` rows keyed by `command_id` give signed vs
  effective action class, resolver rule, approval state, truth SHA and failure reason
  (`orchestrator.py:352-366`). This part is genuinely good.
- An automation run from command to n8n execution, for 7 days, via
  `run_id`/`grant_id`/`command_id` on `automation_run_nonces` (`storage/db.py:530`).
- The trading ledger's own hash chain (`trading/service.py:138`).

**Cannot trace:**
- Anything about *why* a request was slow, retried or failed at the transport layer — no logs.
- A voice turn across multiple commands — `turn_id` is not in `audit`.
- A gateway command into the Hermes run that served it — no propagated trace id.
- A browser task's steps after the fact — `SubagentStep` records only an
  `observation_digest` (`browser/subagent.py:238-245`), not the observation.
- Any cross-host request (gateway → commander → MT5 bridge → EA): three hops, three
  independent id spaces, two of them with access logging switched off.

---

# SCOPE D — TESTS

Counts below are **test function definitions** (`def test_` / `@Test`), not collected cases;
parametrisation expands 826 Python defs into the lead's measured 983 collected cases
(624 backend + 108 contracts/hermes/scenarios + 251 trading).

Totals: **826 Python test functions across 81 files**, **141 Kotlin `@Test` across 26 files**.

## D.1 Classification by suite

### backend/tests — 44 files, 626 test defs
| class | files | defs | notes |
|---|---|---|---|
| unit (pure logic, no ASGI) | test_timeparse(2), test_typed_command_resolver(9), test_speech_sync(3), test_context_graph(4), test_relationship_calibration(10), test_capability_registry(28), test_automation_compiler(37), test_automation_hot_warm_cold(28), test_epistemics_context_understanding(30), test_mission_core(18) | ~169 | |
| integration (in-process ASGI + SQLite tmp) | test_gateway(13), test_extra_apis(9), test_automation_api(27), test_browser_api(17), test_mission_binding_api(19), test_automation_health_api(7), test_context_admission_api(2), test_runtime_resolver_api(2), test_rev31_runtime_wiring(6), test_trading_api(8), test_google_mesh(14), test_owner_runtime(9), test_knowledge_runtime(9), test_workspace_oauth_tool(4), test_proactive_evolution_eval(23), test_automation_operations(22), test_automation_dispatch(10) | ~201 | |
| **security** | test_pairing_security(7), test_a4_owner_approval(1), test_device_auth_persistence(3), test_command_authority_constraints(1), test_project_isolation_audit(8), test_payment_boundary(24), test_automation_security_contracts(33), test_browser_escalation_boundary(13), test_permissions_computeruse_verifiers(17), test_standing_automation_authority(14), test_automation_run_grants(16) | **137** | strongest area |
| contract/schema | test_hermes_bridge(2), test_hermes_google_attestation(3), test_context_snapshot_lineage(1), test_context_retrieval(5) | 11 | |
| failure-injection | scattered within the above (Hermes-down, n8n 500, expired grant) — **no dedicated suite** | ~15 | |
| performance | **0 dedicated tests.** The only latency work is `tools/benchmark_context_retrieval.py` invoked by CI (`.github/workflows/van-ci.yml:65-73`) which records numbers but **asserts no threshold** | 0 | |
| resilience | none as a class | 0 | |
| E2E (real processes/network) | **0** | 0 | |

### tests/ — 8 files, 63 defs
- contract: `test_project_canonical_state`(4), `test_rive_contract`(4),
  `test_owner_runtime_mcp_contract`(5), `test_android_dashboard_navigation`(3),
  `test_project_mount_isolation`(3), `test_automation_browser_governance`(18 — security-contract).
- `tests/hermes/test_profile_layout.py`(18) — filesystem-layout contract.
- `tests/scenarios/test_acceptance_scenarios.py`(8) — see D.3.

### trading/tests — 29 files, 251 collected
- unit/property: `test_sizing`(9), `test_authority`(18), `test_authority_properties`(2),
  `test_heat_governor`(5), `test_mandate`(9), `test_learning`(15), `test_strategies_arbiter`(8),
  `test_intelligence`(6), `test_zse_module`(13), `test_portfolio_views`(2), `test_tradebook`(3),
  `test_core_and_market_data`(9), `test_vtil_borrow`(2), `test_contract_schemas`(7).
- integration w/ fakes: `test_execution`(11, `FakeMt`/`FakeCtrader`/`FakeDeriv`),
  `test_mt5_pull`(4), `test_mt5_worker`(2), `test_ctrader`(5), `test_commander`(5),
  `test_commander_accounts`(4), `test_backtest_runner_cli`(7).
- **infrastructure-as-code contract** (a real strength, rarely seen):
  `test_infra_live`(10 — spins a local `HTTPServer`+`ssl` in-process, not a live VM),
  `test_oci_trading_topology_bootstrap`(4), `test_stack_lock`(7),
  `test_supabase_bootstrap_boundary`(3), `test_vati_ledger_reconcile`(5),
  `test_n8n_provisioner`(1), `test_automation_browser_stack_proposal`(11).

### hermes/policy/tests — 1 file, 20 defs — all **security** (policy-hook deny/approval matrix).

### android/app/src/test — 24 files, 129 `@Test`
- **screenshot-visual / geometry**: 12 files, 68 tests
  (`VanSceneIdentityTest`12, `VanPresenceTest`10, `VanPresenceFrameTest`9, `RiveContractTest`6,
  `VanVisualRuntimeTest`6, `VanAuraEnvelopeTest`5, `VanFieldGeometryTest`4, `VanFieldRev3Test`4,
  `VanCharacterMotionTest`4, `VanWindFieldMotionTest`4, `VanEffectPolicyTest`3,
  `VanCharacterOpacityTest`1) — **more than half of all Android tests are visual geometry.**
- voice policy (unit): `WakeRuntimeTest`6, `VoiceSecondPassTest`6, `VoiceRecognitionPolicyTest`6 = 18.
- overlay (unit): `VanOverlayChromeTest`4, `VanOverlayInteractionTest`5 = 9.
- trading UI/model (unit): `TradeBookTest`6, `ChartGeometryTest`4, `AccountOnboardingTest`3,
  `TradingModelsTest`3 = 16.
- other: `MissionSurfaceTest`11, `EncryptedCommandQueueLogicTest`5, `DegradedModeStoreTest`2.

### android/visual-preview/src/test — 2 files, 12 `@Test`
`VanPreviewRenderTest`6, `VanAcceptanceGateTest`6 — **screenshot-visual**; these render the
committed PNGs under `artifacts/release/preview/` from shipping geometry.

### **instrumentation: ZERO**
`find android -type d -name androidTest -o -name screenshotTest` → **no results**.
There is no Espresso/UIAutomator/Compose-UI test, no emulator job in CI
(`van-ci.yml:93` runs `:app:testDebugUnitTest` only). **Nothing ever exercises the real
Android runtime**: no overlay window, no biometric prompt, no `SpeechRecognizer`, no
`NotificationListenerService`, no boot receiver, no permission flow.

## D.2 External services — all mocked, none exercised live
| external | how faked | where |
|---|---|---|
| Hermes | `monkeypatch.setattr(app.state.orchestrator.hermes, "health"/"create_run", …)` | 14 backend test files; `tests/scenarios/test_acceptance_scenarios.py:38-45` |
| Google | `FakeGoogleTransport` (a **production class**, `google/transport.py:112`) | `test_google_mesh`, `test_workspace_oauth_tool`, `/v1/google/test-transport` |
| n8n | `httpx.MockTransport` | `test_automation_dispatch.py:56-68`, `test_automation_hot_warm_cold`, `test_payment_boundary` |
| browser harness / Stagehand | `httpx.MockTransport` handlers | `test_browser_fabric.py:253,349` |
| brokers (MT5 / cTrader / Deriv) | `FakeMt`, `FakeCtrader`, `FakeDeriv`, `_FakeDerivSocket` | `trading/tests/test_execution.py`, `test_ctrader.py` |
| Exa / NotebookLM / VEKL | `httpx.MockTransport` | `test_owner_runtime.py:209`, `test_knowledge_runtime.py:80-326` |
| Postgres / Supabase | local in-process `HTTPServer` + SQLite fallback | `trading/tests/test_infra_live.py` |

**Every external boundary is mocked, as expected — and that is the finding.** There is no
integration environment, no docker-compose test harness, no contract-verification against a
recorded real response, and nothing anywhere asserts that a mock still matches the real API's
shape. `FakeGoogleTransport` living in production code (`google/transport.py`) rather than in
`tests/` is the clearest symptom.

## D.3 `tests/scenarios/test_acceptance_scenarios.py` — **in-process with fakes, not E2E**
Docstring line 3 claims *"End-to-end scenario certification tests (repository-side)."*
The mechanics (lines 36-59):
- `ASGITransport(app=app)` — the FastAPI app is called **in the same Python process**. No
  socket, no uvicorn, no tunnel, no Caddy, no TLS.
- `monkeypatch.setattr(..., "health", fake_health)` and `"create_run", fake_run` (lines 39-45) —
  **Hermes is replaced by two three-line stubs** that always return `{"ok": True}` /
  `{"id": "run-scenario", "status": "accepted"}`.
- Devices are paired by calling `app.state.auth.pair_device(...)` directly (lines 50-57), i.e.
  the HTTP pairing route and the Android client are both bypassed.
- Tokens are literals set by the fixture (`_env`, lines 24-30).
It is a **useful in-process integration suite and a mislabelled one.** Nothing it asserts
would catch a tunnel misconfiguration, a TLS failure, an Android serialisation mismatch, a
real Hermes contract change, or an ordering problem under concurrency.

Scenario coverage is also **sparse and non-contiguous**: the file defines scenarios
1, 2, 10/11, 12, 14, 15, 17, 17b (lines 90, 101, 133, 143, 157, 172, 190, 207).
**Scenarios 3-9, 13 and 16 do not exist** — the numbering openly advertises the gap.

## D.4 Owner journeys with NO automated validation
1. **voice → command → execution → verification** — NONE end to end. The voice half
   (`WakeRuntimeTest`, `VoiceSecondPassTest`) tests pure scoring functions; the command half
   (`test_gateway`) starts from a JSON body. Nothing joins them, and there is no test at all
   for `speech_evidence_ref` being meaningful.
2. **trading state → aura** — `VanAuraEnvelopeTest` tests the envelope math from a synthetic
   input; `test_trading_api` tests the API. **No test drives a trading state change through
   to the visual state.**
3. **Google action E2E** — every Google test runs against `FakeGoogleTransport`. No recorded
   real response, no OAuth round trip, no token-refresh-under-expiry test.
4. **Hermes delegation round trip** — `test_hermes_bridge.py` has **2 tests**. Both use a
   stub. Nothing validates the Hermes request/response contract, the `van` profile's skill
   surface, or what happens when Hermes returns a malformed run.
5. **Offline queue replay on device** — `EncryptedCommandQueueLogicTest`(5) tests queue
   *logic* in a JVM unit test. No test replays a queued command against the gateway, and
   nothing validates the interaction between the 24 h `owner_intent_max_age_seconds`
   (`config.py:32`) and a device that was offline overnight. `test_scenario_10_11` asserts
   only that a 25-hour-old command expires.
6. **Overlay lifecycle** — `VanOverlayChromeTest`/`VanOverlayInteractionTest` test geometry
   and state reduction. **No instrumentation test**, so service start/stop, permission
   revocation mid-session, boot restart (`OverlayRecoveryReceiver.kt`), and behaviour under
   another app's overlay are entirely unvalidated.
7. **Multi-turn conversation** — no test anywhere passes a second command with the same
   `turn_id`, or validates context carry-over between turns.
8. (Additional) **Device revocation while a command is in flight**, **concurrent duplicate
   idempotency keys** (the race at B.2), **DB corruption/restart recovery beyond
   `test_device_auth_persistence`(3)**, and **tunnel/ingress failure** are all untested.

## D.5 CI coverage vs. suite size
`van-ci.yml` runs: backend (all), `tests/contracts`, `hermes/policy/tests`, `tests/hermes`,
and exactly **two** trading files (`van-ci.yml:33`). Therefore:
- `tests/scenarios/test_acceptance_scenarios.py` — the file named "acceptance" — **never runs in CI.**
- ~233 of 251 trading tests **never run in CI**, including every risk-authority,
  mandate, sizing, execution and ledger test.
