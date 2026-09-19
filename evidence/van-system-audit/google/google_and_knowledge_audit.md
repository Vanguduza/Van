# VAN — Google + Knowledge integration/identity audit
Repo: /home/user/Van · branch claude/van-system-audit-ysgtcd · HEAD dff38a0 · READ-ONLY audit
Auditor pass: integration & identity. All citations are file:line at this HEAD.

---

## Q2-A. Complete enumeration of `backend/van_gateway/google/transport.py`

Three classes, 158 lines total.

### `GoogleOAuthTokenClient` (transport.py:17-57)
| fn | endpoint | notes |
|---|---|---|
| `access_token(refresh_token)` transport.py:32 | `POST https://oauth2.googleapis.com/token` (transport.py:38-47) | refresh_token grant; raises `google_oauth_refresh_<code>` on >=400 (transport.py:48-49). Constructed only when BOTH `google_oauth_client_id` and `google_oauth_client_secret` settings are set (app.py:198-200) — otherwise `google_oauth=None` and every live call dies at `oauth_refresh_unavailable` (service.py:116-117). |

### `GoogleHttpTransport` (transport.py:60-109) — the only live Workspace code in the repo
| fn | HTTP endpoint | route/command that reaches it |
|---|---|---|
| `gmail_search` transport.py:81 | `GET gmail.googleapis.com/gmail/v1/users/me/messages?q=&maxResults=25` | `GET /v1/google/gmail/search` (app.py:605-614), internal-control-token gated (app.py:607 + app.py:349-350). Not reachable from any owner command. |
| `gmail_draft` transport.py:85 | `POST gmail/v1/users/me/drafts` | **NO ROUTE, NO COMMAND.** `GoogleService.gmail_draft` (service.py:127) is dead code — grep shows no caller outside tests. |
| `gmail_send` transport.py:88 | `POST gmail/v1/users/me/drafts/{draft_id}/send` | `POST /v1/google/gmail/send` (app.py:616-627), A4 + `approved` gate (service.py:131-137). |
| `calendar_agenda` transport.py:91 | `GET www.googleapis.com/calendar/v3/calendars/primary/events?maxResults=20&singleEvents&orderBy=startTime` | the ONLY transport fn on an owner-facing path: brief/daily assembly at app.py:523-525 (guarded on `connected` + calendar scope ok + transport present). Read-only. |
| `calendar_reschedule` transport.py:95 | `PATCH calendar/v3/calendars/primary/events/{event_id}` | **NO ROUTE.** `approved` kwarg has no caller (service.py:143). Dead. |
| `drive_search` transport.py:99 | `GET www.googleapis.com/drive/v3/files` | **NO ROUTE.** Dead. |
| `contacts_resolve` transport.py:103 | `GET people.googleapis.com/v1/people:searchContacts` | **NO ROUTE.** Dead. |
| `tasks_list` transport.py:107 | `GET tasks.googleapis.com/tasks/v1/lists/@default/tasks` | **NO ROUTE.** Dead. |

There is **no** `calendar_insert`/`events.insert`, no `gmail.messages.get` (search returns only `{id,threadId}` stubs — transport.py:83, so mail *content* is never fetched), no Drive file read/create, no Docs/Sheets/Slides/Meet/Chat/Keep/Photos/Maps at all.

### `FakeGoogleTransport` (transport.py:112-158)
Mirrors all 8 methods with canned dicts (`m1/t1`, `d1`, `Supplier call`, `spec.pdf`, `task1`). `requires_access_token = False` (transport.py:121) — this is the switch that makes `GoogleService._api_token` return the *decrypted refresh token itself* as the "token" (service.py:114-115). Constructor fails closed outside pytest unless `VAN_ALLOW_FAKE_GOOGLE_TRANSPORT=1` (transport.py:124-125), but `POST /v1/google/test-transport` (app.py:598-603) hot-swaps it onto a *running* app and simultaneously sets `google.oauth = None` (app.py:602) — a live→fake downgrade at runtime (Q10).

**Verdict Q2-A:** 1 of 8 transport functions (`calendar_agenda`) is reachable from an owner-visible surface; 2 more (`gmail_search`, `gmail_send`) from raw `/v1/google/*` HTTP; 5 are unreachable dead code.

---

## Q4. Attestations in `artifacts/google/` (7 files)

| file | what it actually proves | date | live proof or config note |
|---|---|---|---|
| `hermes_live_attestation.json` | An **operator-authored declaration**: principal subject string `hermes:dial-hermes-control:owner-google` (hashed on import), plan PRO, and 13 capability rows. 12 are `CONFIGURED` with `hermes://…` pointers (= "a credential plane is configured", not "a call succeeded"); only `workspace_api` is `READY` with `live://…/workspace-oauth/canary`. | 2026-09-15 | **Configuration note.** No response bodies, no status codes, no hashes. Authority field cites an owner confirmation + a ledger doc, i.e. human assertion. |
| `van_gateway.import.json` | Receipt that the above was imported into `google_capability_connections` on host `dial-hermes-control`; identical 13 rows; `excluded_until_cloud_setup: [gemini_notebook_enterprise, a2a_adk]`. | (same import) | Import receipt only. |
| `antigravity_worker_live_attestation.json` | Delegated worker identity `antigravity_worker_account`, capability `antigravity` = **READY**, with the strongest live signal in the set: `model_discovery_count: 14`, canary model `gemini-3.8-flash-low`, canary response `VAN_ANTIGRAVITY_SECONDARY_OK`, wrapper sha256, profile doctor PASS. | 2026-09-15 | **Live proof (external host).** But the proof is of a *Hermes-side CLI worker*, not of any VAN gateway code path. |
| `antigravity_worker.import.json` | Import receipt for the above (1 row, READY). | — | receipt |
| `gemini_runtime_auth_attestation.json` | Gemini API key authenticates: `models.list` HTTP 200, 50 models; key named `van-gemini-runtime`, restricted to `generativelanguage.googleapis.com`, stored at `~/.hermes/profiles/van/.env` mode 0600, initial exposed key deleted. **But the inference canary FAILED**: `RESOURCE_EXHAUSTED` / `PREPAID_CREDITS_DEPLETED`, `ready: false`; all 5 families set `CAPACITY_LIMITED`. | 2026-09-17T06:04Z | **Live proof of authN, live disproof of usability.** |
| `gemini_runtime_live_canary.json` | Earlier canary: `inference_completed: false`, `state: AUTH_REQUIRED`, `failure_class: credential_unavailable`. Explicitly records `workspace_oauth_reused: false` and `stitch_access_token_reused: false` — a deliberate credential-plane-isolation assertion. | 2026-09-17T04:06Z | Live negative result. |
| `stitch_live_attestation.json` | The only end-to-end *generation* proof: `@google/stitch-sdk 0.3.5` against `https://stitch.googleapis.com/mcp`, `LIVE_QUALIFIED`, html_sha256 + image_sha256 + candidate/provider evidence hashes, outage fallback passed. Honest negatives: `visual_functional_responsive_acceptance: false`, `orchestrated_unit_execution: false`. | 2026-09-16T21:00Z | **Live proof (external Hermes/MCP runtime)** — again, zero VAN gateway code involved; the gateway has no Stitch client. |

All 7 carry `contains_secrets: false` or equivalent and persist only hashes / env-var *names*.

### Does the registry mark anything READY without evidence?
No — `registries/google_capabilities.json` carries **no state field at all** (only id/family/credential_plane/public_api/intents/fallback/action_classes/identity_alias/notes). State is computed at runtime by `GoogleIdentityBroker.capability_status` (mesh.py:237-269). The registry cannot assert READY.

### Fresh DB: READY or UNVERIFIED?
**Neither — a fresh DB yields AUTH_REQUIRED / UNAVAILABLE, and READY is unreachable without an import.** Confirmed by reading mesh.py:242-269:
1. `_evidence()` returns None (empty `google_capability_connections`), so the derived branch runs (mesh.py:252-266).
2. Derived states are only ever `CONFIGURED`, `AUTH_REQUIRED` or `UNAVAILABLE` — **`READY` is never derivable** (mesh.py:253-266). READY exists only as a stored evidence row.
3. Then the principal gate (mesh.py:267-268): with no `google_principal` row, any CONFIGURED/READY is demoted to `UNVERIFIED` / `canonical_google_principal_not_registered`. The same demotion applies to *stored* evidence (mesh.py:247-249).
So: fresh gateway → `workspace_api` = AUTH_REQUIRED (`workspace_oauth_not_connected`), consumer_session caps = AUTH_REQUIRED (`owner_google_session_not_certified`), gemini_runtime/cloud caps = UNAVAILABLE (`credential_plane_unavailable`) — matching the other auditor's observation. In production READY arrives only via `record_capability_evidence(state=READY)` (mesh.py:209-232), which sets `verified_at_unix` (mesh.py:217) and is driven by `tools/google/import_hermes_google_attestation.py` reading the JSON files above. **Nothing in the gateway can promote a capability to READY by observing a real call.**

---

## Q1. The four credential planes — kept separate, and how well

The repo names four planes explicitly as an enum: `GoogleCredentialPlane` = `workspace_oauth | gemini_runtime | cloud_service | consumer_session` (mesh.py:18-22). That maps almost exactly onto the question's (a)-(d), with `cloud_service` as a fifth.

### (a) Owner Google account *authentication* (identity, not data access)
- **Storage:** only a **SHA-256 hash of a subject string** — `GoogleIdentityBroker.hash_subject` (mesh.py:180-182), written to `google_principal.subject_hash` by `register_principal` (mesh.py:184-201). No email, no token, no raw subject. The attestations confirm this (`antigravity_worker_live_attestation.json` notes "Raw email, OAuth code, tokens and cookies are intentionally not persisted").
- **Refresh / revocation / reauth:** none. There is no expiry on `google_principal`; status is a permanent `'VERIFIED_OWNER_ACCOUNT'` literal baked into the INSERT (mesh.py:191). Re-registering overwrites. There is **no unregister/revoke path for the principal at all** — grep finds no DELETE on `google_principal`.
- **Least privilege:** the principal is a gate, not a grant: with no row, every capability collapses to UNVERIFIED (mesh.py:247-249, 267-268). Delegated identities are whitelisted per capability and the registry *refuses to load* if a capability names an identity not in its allow-list (mesh.py:138-142) — `antigravity_worker_account` may hold only `antigravity`, with `owner_authority/workspace_access/credential_inheritance/project_truth_authority` all false (registry `identity_policy`).
- **Failure behaviour:** fail-closed (UNVERIFIED), never fail-open.
- **Multi-device:** irrelevant — the principal is per-gateway-DB, keyed by `owner_id`. Each gateway install has its own hash and its own evidence table; nothing syncs. Owner *devices* are a separate plane entirely (`auth/service.py`, per-device Fernet-encrypted HMAC secrets at auth/service.py:131, 198).

### (b) Workspace data/API authorization — the OAuth scopes
Exactly eight, hard-coded and enforced as an allow-list (`NARROW_SCOPES`, service.py:14-23):
```
gmail.readonly · gmail.compose · gmail.send · calendar
drive.metadata.readonly · drive.readonly · contacts.readonly · tasks
```
- **Enforcement:** `store_refresh_token` rejects any scope outside the list with `scope_not_allowed:<scope>` **before** encrypting (service.py:77-79). This is a real, non-bypassable narrowing at the vault boundary. The same list is what the CLI requests (`tools/google/authorize_workspace_oauth.py:158`, with `access_type=offline`, `prompt=consent`).
- **Least-privilege assessment:** mostly good, two exceptions. `https://www.googleapis.com/auth/calendar` is **full read/write on all calendars** while the only calendar code paths are one read (`calendar_agenda`) and one unreachable PATCH — `calendar.events` or even `calendar.readonly` would cover everything implemented. And `drive.readonly` (full file *content*) is requested alongside `drive.metadata.readonly` although `drive_search` only ever asks for `files(id,name,mimeType,modifiedTime)` (transport.py:100) — pure metadata. **Two scopes are broader than any code in the repo uses.** See Q10.
- **Storage:** the refresh token is Fernet-encrypted into `google_connections.encrypted_refresh_token` (service.py:73-89). The Fernet key comes from settings `google_token_fernet_key` (config.py:37) — env/`.env`, not in the DB. Note the key derivation at service.py:45-47: if the supplied key is not a valid Fernet key it silently falls back to `Fernet(b64(sha256(key)))`, and the `except` clause is `(ValueError, InvalidToken, Exception)` — a bare-Exception catch that makes *any* string a usable key. This is a deliberate convenience that also means a typo'd key yields a *different working vault* rather than an error (see Q10).
- **Refresh:** `GoogleOAuthTokenClient.access_token` exchanges the refresh token for a short-lived access token on **every single API call** (service.py:111-120 → transport.py:32) — no access-token cache anywhere. Correct for secrecy, wasteful and a rate-limit risk under load.
- **Revocation:** `revoke()` (service.py:91-93) sets `status='revoked'` and blanks the ciphertext locally. It does **not** call `https://oauth2.googleapis.com/revoke` — the grant stays live at Google. Local-only revocation.
- **Reauth:** re-run `tools/google/authorize_workspace_oauth.py prepare|exchange`; PKCE (RFC 7636), state file owner-only 0600 under `~/.local/state/van/`, code not persisted, client JSON copied 0600 (tool lines 70-114).
- **Failure behaviour:** `GoogleAuthError("not_connected")` / `oauth_refresh_unavailable` / `token_corrupt` → HTTP 503 at the route (app.py:613-614); `status()` degrades to `GOOGLE_TOKEN_EXPIRED` / `GOOGLE_PARTIAL` / `GOOGLE_OAUTH_CLIENT_UNCONFIGURED` (service.py:52-71).
- **Multi-device:** single `owner_id='owner'` row; the vault lives in the gateway DB, so a second gateway host is a second independent grant. Owner devices never see the token.

### (c) Model-runtime authorization (Gemini API key)
- **There is NO Gemini key in the gateway at all.** No `GEMINI_API_KEY`/`GOOGLE_API_KEY` setting exists in `backend/van_gateway/config.py`, and no gateway code calls `generativelanguage.googleapis.com`. The gateway's entire knowledge of this plane is one boolean, `google_gemini_runtime_configured` (config.py:45), fed into the broker (app.py:208) and used once, to turn `gemini_runtime` capabilities CONFIGURED (mesh.py:258-259).
- The actual key lives **outside the repo**, in Hermes: `~/.hermes/profiles/van/.env`, mode 0600, display name `van-gemini-runtime`, restricted to `generativelanguage.googleapis.com` (`gemini_runtime_auth_attestation.json`). That is good hygiene, but it is hygiene VAN cannot verify or enforce — the gateway takes a boolean on trust.
- **Refresh/revocation/reauth:** out of scope for the gateway; an API key has no refresh. Rotation is a manual Hermes-side action; the attestation records `initial_exposed_key_deleted: true`, i.e. a rotation already happened after an exposure.
- **Failure behaviour:** the attestation itself is the failure record — `RESOURCE_EXHAUSTED / PREPAID_CREDITS_DEPLETED`. Notably the gateway has **no way to learn this**: the boolean stays true, so `/v1/google/mesh` would still report gemini CONFIGURED while every inference fails. Liveness and configuredness are not connected.

### (d) Consumer session (NotebookLM browser profile)
- **Storage: nothing in VAN.** The gateway holds only `profile_alias` (default `authenticated_owner`) and `profile_secret_ref` (default `secretref://browser/google-primary`) — config.py:103-104. Cookies live in a Chromium persistent profile owned by a separate OS user (`van-browser`, dir 0700 at `/var/lib/van-trading/browser/profiles`, bootstrap-browser-runtime.sh:24).
- **Secret indirection is enforced in code:** `HttpBrowserHarnessAdapter.fill_ref` refuses any value that is not a `secretref://` URI (adapters.py:170-172) — the credential value never transits the gateway process.
- **Refresh/reauth:** manual, interactive: `tools/google/bootstrap_notebook_consumer.py --login` opens Chromium, waits on `input()`, and detects sign-out by URL `accounts.google.` or a "Sign in" control. Runtime detection of expiry is the same string check (`notebook.py:735-736` → `notebook_consumer_session_auth_required`) plus a Stagehand `auth_required` boolean (notebook.py:876-886 → `CONSUMER_SESSION_AUTH_REQUIRED`).
- **Revocation:** none in-repo. Revoking means deleting the profile directory or revoking the session at Google.
- **Least privilege: this is the weakest plane by construction.** A Google *web session cookie* is not scopable — it carries the owner's full Google identity (Gmail, Drive, everything), and the only thing limiting blast radius is the browser policy's domain allow-list (`config/browser/domains.yaml`) and `NotebookConsumerProvider.DOMAIN = "notebooklm.google.com"` (notebook.py:582). Compare: the OAuth plane is narrowed to 8 scopes; this plane is narrowed only by a URL check.
- **Multi-device:** single named profile on a single host; no sync, no second-device story.

### (e) `cloud_service` (Notebook Enterprise, Stitch, A2A/ADK)
`CloudAccessTokenProvider` (notebook.py:49-127): either a short-lived **access-token file** (re-read every call, never cached — notebook.py:83-90) or a **service-account JSON** whose private key is used to self-sign an RS256 JWT bearer assertion exchanged at `oauth2.googleapis.com/token` for scope `cloud-platform` (notebook.py:91-127). `cloud-platform` is the broadest Google Cloud scope there is — least privilege is not attempted here. Both files are unconfigured by default (config.py:95-96) so this plane is inert.

### Cross-plane isolation — the good part
Isolation is asserted structurally in three places: the registry refuses invalid identity bindings at load (mesh.py:138-142); `record_capability_evidence` raises `google_identity_binding_mismatch` if an owner_id is passed that isn't the descriptor's alias (mesh.py:212-213); `capability_status` returns POLICY_BLOCKED for the same (mesh.py:240-241). And the canary artifact explicitly records the negative: `workspace_oauth_reused: false`, `stitch_access_token_reused: false` (`gemini_runtime_live_canary.json`). No code path in the gateway reads a credential from one plane and uses it in another.

---

## Q3. The Google router (control.py / mesh.py)

- **control.py is 21 lines**: `verify_internal_control` (control.py:12-21), a constant-time HMAC compare of the `X-Van-Internal-Token` header, failing closed when unconfigured (control.py:18-19). That is the entire "control plane" module. It is reused far beyond Google — `runtime_api.py:114-119` wraps it for every `/v1/runtime/*` route, including all knowledge routes.
- **Action classes:** A1-A5 from `van_gateway.models.ActionClass`. The router's gates, in order (mesh.py:286-294): A5 → `denied` unconditionally; A4 without `owner_approved` → `approval_required`; A3/A4 without `grant_id` → `degraded/GOOGLE_CAPABILITY_UNAVAILABLE`; A3/A4 with a `project_id` but no `truth_sha` → `degraded/STALE_PROJECT_TRUTH`. Per-capability `action_classes` further filter candidates (mesh.py:309-310) — e.g. only `workspace_api`/`workspace_studio` declare A4.
- **Deterministic selection:** `candidates_for_intent` (mesh.py:154-155) is a plain membership test over registry `intents`, then each candidate's declared `fallback` is appended once (mesh.py:298-306); the first candidate whose state is in `USABLE_STATES = {READY, CONFIGURED}` (mesh.py:280) wins. Registry order is insertion order from the JSON, so selection is fully deterministic and has **no model in the loop** — the docstring says so ("Deterministic planner only; Hermes owns actual agent execution", mesh.py:278).
- **Readiness states:** 10 values (mesh.py:25-35). Only READY and CONFIGURED are usable; `CAPACITY_LIMITED`/`RATE_LIMITED` on `antigravity` specifically are surfaced as the degraded code `ANTIGRAVITY_CAPACITY_LIMITED` (mesh.py:318-322, 336-340) — a hard-coded, single-capability special case.
- **What "planning" produces:** a row in `google_jobs` with status `'PLANNED'` and a SHA-256 `input_hash` over the canonicalised request (mesh.py:354-362), plus `record_artifact` which writes a provider artifact that is **forbidden from being OWNER_SIGNED** (mesh.py:369-370) and defaults to `trust=UNTRUSTED, validation_state=PENDING` (mesh.py:96-98).
- **Wiring — the decisive answer:** the router is **not on the owner command path at all.** `/v1/commands` → `Orchestrator.handle` (app.py:508-512) never touches `google_router`; grep for `google_router` finds it only in `app.py:240, 277, 660, 665, 678`, all under `/v1/google/jobs/*`, all `require_internal_control`. So: **`/v1/google/*` + internal-token job planning only.** An owner phone cannot cause a Google capability to be routed; only a Hermes-side process holding the machine token can, and even then the result is a *plan row*, never an execution.
- **Consequence:** the router plans jobs for 16 capabilities, and the gateway can execute **zero** of them. Every `planned` decision ends with `reason="deterministic capability route selected; Hermes must execute the job"` (mesh.py:330).

---

## Q5. Prompt scrubbing — where credentials are (and are not) kept out of prompts

1. **`GoogleService.scrub_for_prompt`** (service.py:161-165) filters a 12-name blocklist: `access_token, refresh_token, authorization, token, encrypted_refresh_token, client_secret, api_key, cookie, session_cookie` (+ case-folding). **It has zero production callers** — grep finds it referenced only in `backend/tests/test_extra_apis.py:147` and `backend/tests/test_gateway.py:236`. It is a tested utility that nothing in the request path invokes. It is also shallow: a nested `{"headers": {"Authorization": ...}}` passes straight through, since the comprehension only inspects top-level keys.
2. **What actually protects prompts is structural, not scrubbing.** The Hermes metadata assembled at orchestrator.py:499-520 is an explicit allow-list of fields (command_id, device_id, action_class, canonical_context, typed_resolution, …). No Google payload, no token, and no `google.status()` output is placed in it. `client_context` is passed but stamped `"client_context_authoritative": False` (orchestrator.py:517). Because the *only* live Google read that reaches an owner surface is `calendar_agenda` → the briefing (app.py:523-525), and the briefing is a response to the device rather than a prompt to Hermes, Google content never enters a prompt via the gateway.
3. **Credential-shaped values never leave their module:** the decrypted refresh token exists only inside `_api_token`'s local scope (service.py:111-120) and is passed positionally to a transport method; `FakeGoogleTransport` records only `token[:4]` (transport.py:129). Browser secrets are `secretref://` handles, resolved inside the worker (adapters.py:170-172). The Gemini key is never in the gateway's address space.
4. **Obsidian is the one place owner content becomes model-adjacent, and it is scrubbed at ingest, not at prompt time:** `_SECRET_PATTERNS` (obsidian.py:30-35) match api/access/refresh-token/client_secret/password assignments, `sk-…` keys, `bearer <blob>`, and OTP-with-digits; plus a `van_sensitivity: secret|credential` frontmatter opt-out (obsidian.py:160-166). A blocked document is stored with `body_text=''`, empty tags/links/frontmatter and a `blocked_reason` (obsidian.py:233, 243-245), and is deleted from FTS (obsidian.py:248-249) and excluded from every query (`blocked_reason IS NULL`, obsidian.py:282, 290). This is the strongest scrubbing in the repo.
5. **Gaps.** (i) Blocking is whole-document: one matching line suppresses an entire note, so the incentive is to weaken the patterns. (ii) The patterns are a denylist — a bare 40-char secret on its own line is indexed. (iii) `snippet=body[:8000]` (obsidian.py:324) puts up to 8 KB of owner note text into `knowledge_evidence` for any caller of `/v1/runtime/knowledge/obsidian/query`. (iv) `scrub_for_prompt` being dead means there is no defence-in-depth if a future caller *does* put a Google payload in metadata.

**Verdict Q5: no credential can reach prompt metadata today — but by construction (nothing forwards Google data) rather than by the scrubber, which is unwired.**

---

## Q7. VEKL and Obsidian

### VEKL — read-only evidence adapter (`knowledge/vekl.py`, 216 lines)
- **Endpoint:** exactly one — `GET {base_url}/v1/missions/{mission_id}/vekl` (vekl.py:92, 101). Nothing else; no writes, no other path. Declared as a contract in status details, `"endpoint_contract": "/v1/missions/{mission_id}/vekl"` (vekl.py:71).
- **Auth:** three headers — `X-Session-Id`, `X-Principal-Id`, and an optional `Authorization: Bearer <token>` (vekl.py:77-85), from settings `vekl_session_id / vekl_principal_id / vekl_bearer_token` (config.py:80-83). The bearer is a plain settings string — **not** Fernet-vaulted, unlike the Google refresh token. It is held in memory on `self._bearer_token` and only ever written into a request header.
- **Returned shape:** an arbitrary JSON object, which the adapter *flattens* to at most 4096 `(dotted.path, stringified value)` leaves (vekl.py:127-148), lexically scores them against the query (path-token hit ×5, value-token ×2, substring bonuses ×8/×4 — vekl.py:154-169), and persists the top N as evidence rows with `source_ref = vekl://mission/{id}#{path}` and `SourceTrust.VERIFIED_SYSTEM` (vekl.py:185-195). Returns `VeklQueryResult` with an `evidence_pointer` `gateway://knowledge/vekl/{query_id}`.
- **Is a live endpoint configured anywhere?** **No.** `vekl_enabled: bool = False` and `vekl_base_url: str = ""` (config.py:79-80), and there is no `.env`, deploy file, or test that sets a real host — the deploy config carries only `VAN_VEKL_WORKER_HOST` (empty, filled at bootstrap) for a *different* subsystem. A separate VEKL **server** does exist in this repo at `trading/vekl/server.mjs`, but nothing points the gateway adapter at it and its route surface is not verified here to match `/v1/missions/{id}/vekl`. So the adapter is a correctly-written client to an endpoint this deployment never dials: `status()` returns DISABLED (vekl.py:56-57).
- **Robustness (genuinely good):** 429/5xx retried with exponential backoff up to `read_retries` (vekl.py:102-104), 403 → `vekl_scope_or_source_denied`, 404 → `vekl_mission_not_found`, connect/timeout → `vekl_upstream_unavailable` (vekl.py:105-121). `certify()` refuses to mark READY if the canary returns no evidence (vekl.py:207-210).

### Obsidian — what is indexed, exclusion, query method
- **Indexed:** every `*.md` under the configured vault, recursively (`root.rglob("*.md")`, obsidian.py:184). Per document: title (frontmatter `title` → first `# ` heading → filename stem, obsidian.py:149-157), full `body_text`, tags (frontmatter + inline `#tag`, obsidian.py:132-141), links (`[[wikilink]]` + `[md](target)`, obsidian.py:143-147), parsed frontmatter, mtime_ns/size for incremental skip (obsidian.py:208-212), and a SHA-256 content digest.
- **Hardening:** symlinks are skipped (obsidian.py:197-199); paths that escape the resolved root raise and are counted blocked (obsidian.py:191-196); files over `max_file_bytes` are `FILE_TOO_LARGE`; non-UTF-8 is `UNREADABLE_UTF8`; a `max_files` ceiling aborts the whole index (obsidian.py:185-186). Deletions are soft (`deleted_at_unix_ms`) and purge the FTS row (obsidian.py:253-262). The whole index runs under an `asyncio.Lock` (obsidian.py:183).
- **Secret exclusion:** as in Q5 — frontmatter sensitivity + 4 regexes, whole-document suppression, body blanked, FTS row deleted. `status()` advertises `"secret_content_indexed": False` (obsidian.py:96) and `KnowledgeRuntime.status()` advertises `"secret_content_admitted": False` (service.py:128).
- **Query method: yes, FTS5.** A virtual table `obsidian_fts(document_id UNINDEXED, title, body_text, tags, links)` with `unicode61 remove_diacritics 2` (schema.py:98-101), created inside a try/except so a SQLite build without FTS5 degrades gracefully (`fts_enabled=False`, schema.py:104-105). Queries build an `OR` of up to 24 quoted tokens and rank with `bm25(obsidian_fts, 0.0, 8.0, 2.0, 4.0, 2.0)` — title weighted 8, links 4, tags/body 2, doc_id 0 (obsidian.py:276-286). **Fallback:** on any FTS exception it silently falls back to a full table scan with set-intersection scoring (obsidian.py:287-300) and reports `fts_used=False` — correct, but note the bare `except Exception: pass` (obsidian.py:287-288) hides real FTS errors.
- **Default state:** `obsidian_enabled=False`, `obsidian_vault_path=""` (config.py:86-87) → DISABLED on a fresh gateway.

### Who decides WHEN to query VEKL?
**Nothing in this repo.** There is no scheduler, no retrieval policy, no automatic call. The only in-process caller of `KnowledgeRuntime.query_vekl` is the HTTP route `POST /v1/runtime/knowledge/vekl/query` (runtime_api.py:240-246), which requires the internal control token. The orchestrator never calls it; `Orchestrator.handle` compiles a context snapshot with an **empty** requirements list and no knowledge evidence (`self.context.compile_snapshot(req.command_id, [], …)`, orchestrator.py:403-408). `knowledge_evidence_refs` exists as a snapshot field (runtime_api.py:54, 218) but the orchestrator never populates it. So the decision to query VEKL — or Obsidian, or NotebookLM — is made **entirely by Hermes prose** (`hermes/profile/van/AGENTS.md`, `hermes/skills/*/SKILL.md`), calling back in over the internal token. The gateway is a library of retrieval endpoints with no retrieval policy of its own.
---

## Q2-B. Real workflows, product by product

First the decisive structural fact that governs all of them: **`Orchestrator.handle` never executes anything.** It verifies the device signature, resolves the typed command, applies A4/expiry/no-stale-replay/truth gates, seals a `CommandAuthorityRecord` (orchestrator.py:440-459) and then hands the raw text plus an allow-listed metadata dict to `hermes.create_run` (orchestrator.py:497-521). Execution can only happen if an **external Hermes process** calls back in over `X-Van-Internal-Token`. The gateway's own MCP surface for Hermes (`hermes/mcp/owner_runtime_stdio.mjs:51-93`) exposes **20 tools, none of which touch Gmail, Drive, Calendar, Contacts or Tasks** — the Google tools there are `notebook_enterprise_recent/get`, `notebook_consumer_ask`, and `knowledge_action_execute`.

| Product | Production code that does a useful owner action | Reached by | Classification |
|---|---|---|---|
| **Gmail** | `gmail_search` (metadata IDs only — transport.py:81-83) and `gmail_send` of a **pre-existing draft** (transport.py:88). There is no `messages.get`, so VAN can never read a subject or body; there is no route for `gmail_draft`, so VAN can never create the draft it would send. **You cannot send mail with this code** — `gmail_send` requires a `draft_id` only a human or another tool could have made. | internal-token HTTP only (app.py:605, 616) | IMPLEMENTED_BUT_ISOLATED, and functionally incomplete |
| **Calendar** | `calendar_agenda` — read next 20 primary-calendar events. This is **the only Google API call on an owner-visible path**: `GET /v1/briefing` → app.py:523-525. `calendar_reschedule` exists but has no route. **There is no event-creation code anywhere** — no `events.insert`, no POST to calendar. "Create a calendar event" is unimplementable. | owner device via `/v1/briefing` (read) | PARTIAL (read-only) |
| **Drive** | `drive_search` returns `id,name,mimeType,modifiedTime` (transport.py:99-101). No route, no MCP tool, no command. No file read, no upload, no create. | nothing | IMPLEMENTED_BUT_ISOLATED |
| **Contacts** | `contacts_resolve` → `people:searchContacts` (transport.py:103-105). No route. | nothing | IMPLEMENTED_BUT_ISOLATED |
| **Tasks** | `tasks_list` → `@default` list (transport.py:107-109). No route. No task creation. | nothing | IMPLEMENTED_BUT_ISOLATED |
| **NotebookLM personal (consumer)** | `NotebookConsumerProvider.create_note` (notebook.py:828-1021) and `.ask` (notebook.py:738-812) — genuinely full logic: idempotency ledger, pre-read, act, post-read verification, sealed browser evidence. But every effect is an HTTP POST to `http://127.0.0.1:9141` / `:9140`, and **those two servers do not exist in this repo** (see Q6). | `knowledge.execute_authorized_action` (service.py:216-227) via `/v1/runtime/knowledge/actions/execute` | PARTIAL — complete orchestration, absent runtime |
| **Notebook Enterprise** | The most complete real integration: `create_notebook` POST `/notebooks`, `add_sources` POST `…/sources:batchCreate`, resumable `_upload_file` to `/upload/v1alpha/…`, `_wait_source_complete` polling, `delete_notebook` POST `/notebooks:batchDelete`, `delete_sources` POST `…/sources:batchDelete`, plus `get_notebook`/`listRecentlyViewed` reads — all against `https://{location}-discoveryengine.googleapis.com/v1alpha/projects/{n}/locations/{loc}` (notebook.py:211-212, 258-263, 306, 361-388, 443, 502, 538). Every mutation does a read-back before claiming success. | 4 of the 5 in-process actions; MCP `notebook_enterprise_*` | IMPLEMENTED (disabled by default, credentials unconfigured) |
| **Gemini / Deep Research / Gemini Live** | **No gateway code whatsoever.** Registry rows + one boolean (`google_gemini_runtime_configured`). No client, no model name, no endpoint. Everything is Hermes-side prose (`hermes/providers/gemini.md`). | nothing | ABSENT (registry-only) |
| **Stitch** | No gateway code. Registry row + a live attestation produced by an external `@google/stitch-sdk` run. | nothing | ABSENT in gateway; E2E_VERIFIED externally |
| **Mixboard** | Registry row only. Not even an attestation of its own (it appears as CONFIGURED in the bulk import). | nothing | ABSENT |
| **Antigravity** | The only thing in-repo is a **25-line bash wrapper**, `hermes/profile/van/bin/antigravity-worker`, which is actually the sharpest piece of isolation engineering in the audit: it repoints `HOME`/`XDG_*` at a 0700 per-identity dir and `unset`s `GOOGLE_API_KEY GEMINI_API_KEY GOOGLE_APPLICATION_CREDENTIALS CLOUDSDK_CONFIG GOOGLE_CLOUD_PROJECT GOOGLE_CLOUD_PROJECT_ID` before exec (lines 17-25). Credential-plane separation enforced by process environment. No gateway code. | nothing (Hermes shell) | ABSENT in gateway; the wrapper is IMPLEMENTED |
| **Jules** | Registry row only. | nothing | ABSENT |
| **Veo / Nano Banana / Flow** | Registry rows only; model names appear as strings in `gemini_runtime_auth_attestation.json`. | nothing | ABSENT |
| **ADK / A2A** (`a2a_adk`) | Registry row only, and explicitly `excluded_until_cloud_setup` in both attestation files. | nothing | ABSENT |
| **AI Studio, Workspace Studio** | Registry rows only. `workspace_studio` is reachable as a *routing fallback* for `workspace_operation` (mesh.py:304-306) — i.e. the planner can select a capability with no implementation at all. | router only | ABSENT |

**Products with NO gateway code at all beyond a registry entry — 13 of 16:** `gemini`, `gemini_live`, `deep_research`, `mixboard`, `stitch`, `antigravity`, `jules`, `workspace_studio`, `nano_banana`, `veo`, `flow`, `ai_studio`, `a2a_adk`. Only `workspace_api` (via `GoogleService`/`GoogleHttpTransport`), `gemini_notebook` (via `NotebookConsumerProvider`) and `gemini_notebook_enterprise` (via `NotebookEnterpriseProvider`) have implementation.

### Traced workflow #1 — Calendar agenda (the only owner-reachable live Google call)
`GET /v1/briefing` (app.py:516) → `google.status()` → gate on `connected and services["calendar"]=="ok" and transport is not None` (app.py:523) → `GoogleService.calendar_agenda` (service.py:139-141) → `_api_token` → `_refresh_token` decrypts the Fernet blob from `google_connections` (service.py:95-104) → `GoogleOAuthTokenClient.access_token` POSTs the refresh grant (transport.py:38-47) → `GoogleHttpTransport.calendar_agenda` GETs `calendar/v3/calendars/primary/events` with `Bearer` (transport.py:91-93) → items handed to `briefing.build(calendar_items=…)`. On `GoogleAuthError` the briefing degrades with `GOOGLE_TOKEN_EXPIRED` rather than failing (app.py:526-527). **This path is real and complete.** Note `mail_items` is hard-coded `None` (app.py:522) and never populated.

### Traced workflow #2 — Notebook Enterprise create (the most complete mutation)
Hermes MCP `action_begin` → `/v1/runtime/actions/begin` (runtime_api.py:332) → `CommandAuthorityService.authorize_action` re-checks principal/turn/snapshot/expiry/device-revocation and enforces `typed_parameter_constraints` (authority.py:104-129) → `ActionRuntime.begin` → AUTHORIZED. Then MCP `knowledge_action_execute` → `/v1/runtime/knowledge/actions/execute` → `execute_authorized_action` (service.py:190) verifies the action is one of 5, the status is AUTHORIZED/RETRYABLE, and `digest_parameters(parameters) == execution.parameters_digest` (service.py:212-213) → `create_enterprise_notebook` → `NotebookOperationStore.begin` dedupes on `idempotency_key` (UNIQUE, schema.py:72) → POST `/notebooks` → read-back → `VERIFIED_SUCCESS` → `mark_submitted` → `mark_verifying` → `actions.verify(...)` (service.py:262-273). A submission timeout becomes `CONFLICTED_STATE`, never a retry (tested). **This is a properly engineered mutation pipeline; it is simply pointed at credentials nobody has configured.**

---

## Q6. «Create a NotebookLM notebook for this project» — link-by-link

**Link 0 — the phrase does not resolve.** `TypedCommandResolver.NOTE_PATTERNS` (resolver.py:86-89) requires the literal token `note` followed by a space: `…(?:notebooklm|notebook lm) note(?: (?:named|called))? (?P<title>.+)$`. The input "create a notebooklm **notebook** for this project" fails — after `note` comes `book`, not a space. It falls through to `ResolutionMode` non-exact, so the gateway forwards the raw text to Hermes with no typed action. **And there is no action for creating a consumer notebook at all** — the five executable actions are note-create (inside an existing notebook) and four *enterprise* notebook operations (registry.py:25-77). Creating a personal NotebookLM *notebook* is not implemented anywhere in this repo.

Taking instead the phrase that does work — **«create a notebooklm note Dial Health»** — here is every link:

| # | Link | State |
|---|---|---|
| 1 | Device signs a `CommandRequest`; `/v1/commands` checks `device_id` identity match (app.py:510-511) and the middleware's ingress+device tokens (app.py:371-386). | **IMPLEMENTED** |
| 2 | `resolver.resolve` → `action_id=google.notebook.note.create`, `parameters={"title": "dial health"}`, `rule_id=notebooklm.note.create.v1` (resolver.py:128-140). Note the text is **casefolded** first (resolver.py:117), so the sealed title is lowercase. | **IMPLEMENTED** (lossy) |
| 3 | A3 gates: project truth required if `project_id` set; context snapshot sealed; `CommandAuthorityRecord` written with `typed_parameter_constraints={"title": "dial health"}` (orchestrator.py:448-449, 459). | **IMPLEMENTED** |
| 4 | Orchestrator dispatches to Hermes and **returns**. It does not call `action_begin`. | **IMPLEMENTED — and this is the hand-off point** |
| 5 | Hermes (external) calls MCP `action_begin` → `/v1/runtime/actions/begin`, supplying `notebook_id` itself. Authority only checks that the sealed `{"title": …}` is a **subset** of the submitted parameters (authority.py:127-129). **`notebook_id` is unconstrained by owner authority — Hermes picks which notebook the owner's note lands in.** | **IMPLEMENTED, with a real authority gap** |
| 6 | Hermes calls MCP `knowledge_action_execute` → `execute_authorized_action` → digest match → `mark_executing` → `create_consumer_note` (service.py:214-227). | **IMPLEMENTED** |
| 7 | `create_note`: idempotency ledger `begin` (notebook.py:836-848); `_open_task` registers the profile, creates a `BrowserTask` at `AutonomyTier.L4_STAGEHAND_ACT` with `action_class=A3, mutating=True`, and acquires a `PageLease` (notebook.py:850-856, 665-689). | **IMPLEMENTED** |
| 8 | `_navigate` → `harness.navigate(task, https://notebooklm.google.com/notebook/{id})` = `POST {harness_base_url}/navigate`; then `/page_info`; if the URL contains `accounts.google.` → `notebook_consumer_session_auth_required` (notebook.py:724-736). | **CONTRACT ONLY — needs a server on 127.0.0.1:9141** |
| 9 | Pre-read: `stagehand.extract(…exact_title_exists, auth_required…)` = `POST {stagehand_base_url}/extract` (notebook.py:861-872). Pre-existing title without prior submission → `VERIFICATION_FAILED / PREEXISTING_NOTE_AMBIGUOUS` (notebook.py:888-900) — refuses to claim someone else's note. | **CONTRACT ONLY — 127.0.0.1:9140** |
| 10 | Submit: `stagehand.act(kind="notebook_create_note", title, body)` = `POST /act`; ledger → `SUBMITTED` with `submitted_by_operation=True` (notebook.py:913-935). | **CONTRACT ONLY** |
| 11 | Read-back: second `extract` for `exact_title_visible`; false → `VERIFICATION_FAILED / NOTE_READBACK_FAILED` (notebook.py:936-961). | **CONTRACT ONLY** |
| 12 | `_seal_browser_evidence` + `evidence.persist` (`SourceTrust.VERIFIED_SYSTEM`, scope `google-notebook`) + ledger `VERIFIED_SUCCESS` with pointer `google://notebook-consumer/{nb}/note/{title}` (notebook.py:963-1003). | **IMPLEMENTED** (given 8-11) |
| 13 | Back in `execute_authorized_action`: `mark_submitted` → `mark_verifying` → `actions.verify(success=True, …)` → execution `VERIFIED_SUCCESS` (service.py:262-273). | **IMPLEMENTED** |

**The external runtime that does not exist.** `HttpBrowserHarnessAdapter` and `StagehandAdapter` are thin HTTP clients (`_PrivateWorkerClient._call` POSTs JSON to a path — adapters.py:92-103) pointed at `browser_harness_base_url=http://127.0.0.1:9141` and `browser_stagehand_base_url=http://127.0.0.1:9140` (config.py:70-72). The only deployment asset for those ports is `deploy/van-trading-core/browser/bootstrap-browser-runtime.sh`, which installs `@browserbasehq/stagehand@4.1.0` + `@playwright/test@1.63.0` + Chromium, verifies the pins, and then writes a manifest whose own field says:
```json
"stagehand_bind": "127.0.0.1:9140", "harness_bind": "127.0.0.1:9141",
"service_state": "ENVIRONMENT_PREPARED_NOT_IMPLEMENTED"
```
(bootstrap-browser-runtime.sh:62-76). There is **no server source** for either port anywhere in the tree — the only `.mjs`/`.ts` files are the MCP stdio bridges and the unrelated `trading/vekl/server.mjs`. **Confirmed: the consumer NotebookLM path is complete down to the HTTP boundary and then stops at two ports nothing listens on.** Defaults keep it honest: `browser_enabled=False`, `notebook_consumer_enabled=False`, `browser_stagehand_model_provider=""` — and `StagehandAdapter.configured` requires a model provider *and* name (adapters.py:230-233), so it is UNCONFIGURED out of the box and `_require_transport` raises `notebook_consumer_browser_fabric_unconfigured` (notebook.py:649-652).

**Real or contract-only?** The routing *through* Browser Fabric is real code with real policy (profile registration, leases, autonomy tiers, `secretref://`-only fills, payment-refusal assertions at adapters.py:268-271). The Fabric itself is contract-only.

---

## Q8. Test results — `python3 -m pytest` (VAN_DATABASE_PATH under scratchpad)

All five files pass: **36 passed in 7.85s**, no failures, no skips, no warnings surfaced.

| file | count | what it actually asserts |
|---|---|---|
| `test_google_mesh.py` | **14** | Schema v16 migration; subject is hashed not stored (64 hex, ≠ raw — :32-39); consumer capability is UNVERIFIED until the principal registers (:50-57); `antigravity` is bound to the delegated alias and `jules` is not (:61-74); routing is deterministic and persists a `PLANNED` job with a 64-char input hash (:92-100); A3 without truth → STALE_PROJECT_TRUTH, A4 without approval → approval_required (:104-112); declared fallback selection (:116-121); A3 without grant → degraded (:125-130); provider artifacts can never be OWNER_SIGNED (:134-143); **the one transport test uses hand-written `OAuthSpy`/`LiveSpyTransport` doubles** to prove the refresh token is exchanged and only the *access* token reaches the transport (:145-162); settings keep planes separate (:165-171); `verify_internal_control` fails closed (:174). |
| `test_workspace_oauth_tool.py` | **4** | Desktop-app client shape required; installed client and pending-state files are 0600 and the consent URL carries `access_type=offline`, `prompt=consent`, `code_challenge_method=S256`, loopback redirect, and **exactly `NARROW_SCOPES`** (:38-60); PKCE state mismatch rejected (:63); runtime env file is 0600 and contains the Fernet key + DB path (:72-86). No network. |
| `test_hermes_google_attestation.py` | **3** | The importer writes the declared states into `google_capability_connections` and registers the principal; the delegated antigravity attestation records exactly one READY row; **a canonical attestation that tries to claim a delegated capability is rejected** (:74). Pure DB/file, no Google contact. |
| `test_knowledge_runtime.py` | **9** | VEKL bounded read + canary certification via **`httpx.MockTransport`** (:55-80); Obsidian secret exclusion + deletion tracking against a real tmp vault — the only test touching a real filesystem (:100); Notebook Enterprise create idempotency/read-back, batch sources + guarded upload, submission timeout → CONFLICTED, delete timeout → CONFLICTED, all via **`httpx.MockTransport`** (:135-337); consumer provider **fails closed** with no Browser Fabric (:221-229); the VERIFIED_SUCCESS path — **`runtime.create_consumer_note` is monkey-patched with `fake_create`** (:252-259), so no adapter runs — plus a genuine parameter-swap rejection (:264-277); pre-existing-title refusal using **hand-written `Harness`/`Stagehand` stub classes** (:338-376). |
| `test_rev31_runtime_wiring.py` | **6** | Every `/v1/runtime/*` route 401s without device auth and 403s with a wrong internal token (:89-112); v2 signature binds voice provenance and the sealed snapshot into Hermes metadata, with `client_context_authoritative=False` (:116-202); bad signature denied; project command binds truth+repo SHA into `live_state_refs` (:252-313); context-seal failure blocks dispatch entirely and Hermes observes nothing (:317-374); device revocation revokes a non-terminal `google.notebook.note.create` execution (:378-408); **knowledge routes are internal-only and a fresh gateway reports all four providers `DISABLED`** with obsidian query → 503 `obsidian_disabled` (:412-453). |

**Fake/stub inventory:** `httpx.MockTransport` (VEKL + all Enterprise tests), hand-written `OAuthSpy`/`LiveSpyTransport`/`Harness`/`Stagehand` classes, one monkey-patched provider method, and `FakeGoogleTransport` elsewhere in the suite. **Not one of the 36 tests makes a network call to Google.** The suite proves policy, state machines, idempotency and isolation — exactly what it claims in the docs ("Repository completion cannot fabricate Google account consent or live provider state", GOOGLE_INTELLIGENCE_MESH.md:445-447) — and proves nothing about live provider behaviour.

---

## Q9. Classification

**Google capabilities (registry order):**

| capability | class | one-line reason |
|---|---|---|
| `gemini` | ABSENT | registry row + one boolean; no client, no endpoint, no model call in the gateway |
| `gemini_live` | ABSENT | as above; perception surface exists only in docs |
| `deep_research` | ABSENT | as above; routable (`test_google_mesh.py:92-100` plans a job for it) but unexecutable |
| `gemini_notebook` | PARTIAL | full create/ask/verify logic (notebook.py:574-1021) terminating at two unimplemented loopback ports |
| `gemini_notebook_enterprise` | IMPLEMENTED (isolated) | complete discoveryengine v1alpha CRUD + read-back + idempotency, disabled and uncredentialed by default |
| `mixboard` | ABSENT | registry row only |
| `stitch` | ABSENT in gateway / E2E_VERIFIED externally | no gateway code; `stitch_live_attestation.json` is a real SDK+MCP generation receipt with artifact hashes |
| `antigravity` | ABSENT in gateway / IMPLEMENTED as a wrapper | `bin/antigravity-worker` enforces identity isolation by env; the gateway has no Antigravity code |
| `jules` | ABSENT | registry row only |
| `workspace_api` | IMPLEMENTED_BUT_ISOLATED | 8 transport fns, 1 reachable from an owner surface, 5 with no route at all |
| `workspace_studio` | ABSENT | registry row only, yet selectable as the `workspace_api` fallback (mesh.py:304-306) |
| `nano_banana` | ABSENT | registry row only |
| `veo` | ABSENT | registry row only |
| `flow` | ABSENT | registry row only |
| `ai_studio` | ABSENT | registry row only |
| `a2a_adk` | ABSENT | registry row only; excluded from both attestation imports |

**Knowledge providers:**

| provider | class | reason |
|---|---|---|
| VEKL | IMPLEMENTED_BUT_ISOLATED | real, retry-hardened HTTP client (vekl.py:87-125) for an endpoint no config in this repo supplies; DISABLED by default |
| Obsidian | INTEGRATED | fully self-contained — real filesystem indexing, FTS5 + bm25, secret exclusion, soft deletes; needs only `obsidian_enabled=1` + a vault path. The only provider with no external dependency. |
| Notebook Enterprise | IMPLEMENTED (isolated) | complete API surface incl. resumable upload and delete read-back; needs a Cloud project + service account |
| Notebook Consumer | PARTIAL | orchestration/evidence/idempotency complete; both transport ports unimplemented (`ENVIRONMENT_PREPARED_NOT_IMPLEMENTED`) |

**E2E_VERIFIED against a live Google product: nothing, from the gateway.** The two genuine live receipts (Stitch generation, Antigravity model discovery + canary) were produced by external Hermes-side runtimes.

---

## Q10. Security

### 1. Token leakage paths — none found reaching a prompt or a device
- Decrypted refresh token lives only in `_api_token`'s locals (service.py:111-120); never logged, never returned, never in `GoogleConnectionStatus` (which carries only scope strings).
- `google_connections.encrypted_refresh_token` is Fernet ciphertext; the key is env-only (config.py:37).
- Hermes metadata is an explicit allow-list (orchestrator.py:499-520) containing no Google payload.
- Browser secrets are `secretref://` handles refused unless prefixed (adapters.py:170-172).
- `FakeGoogleTransport` truncates to `token[:4]` (transport.py:129).
- Attestations persist hashes, env-var *names* and `contains_secrets: false`.
- `CommandAuthorityService.export_public` strips `device_id` (authority.py:134-140).
**Residual:** `vekl_bearer_token` is an ordinary settings string sent as an `Authorization` header (vekl.py:83-84) — not vaulted like the Google token, an inconsistency rather than a leak. And `scrub_for_prompt` (service.py:161-165) — the named defence — has **no production caller** and is shallow (top-level keys only), so it would not help if a payload ever were forwarded.

### 2. Scope creep
- **Real, mild, and in the request itself.** `NARROW_SCOPES` requests `auth/calendar` (full read/write, all calendars) when only one read and one dead PATCH exist, and `auth/drive.readonly` (full file content) when `drive_search` asks only for metadata fields (transport.py:100) and `drive.metadata.readonly` is already in the list. Two scopes exceed every code path in the repo. Because the same list is used both to *request* consent (tool line 158) and to *validate* storage (service.py:77-79), tightening it is a one-line change with no other effect.
- `gmail.compose` is requested and `gmail_draft` implemented, but unreachable — an unused write scope on a live grant.
- `CloudAccessTokenProvider` requests `cloud-platform` (notebook.py:58) — the broadest Cloud scope; `discoveryengine` would suffice.
- **Router-side creep is well-controlled:** per-capability `action_classes` are enforced (mesh.py:309-310) and only the two workspace capabilities may reach A4.

### 3. Credential-plane collapse risk
Structurally well defended — registry load-time validation (mesh.py:138-142), write-time mismatch rejection (mesh.py:212-213), read-time POLICY_BLOCKED (mesh.py:240-241), an `env`-clearing wrapper for the delegated identity (`antigravity-worker`:24), and an explicit non-reuse assertion in the canary artifact. Four residual risks:
1. **`POST /v1/google/test-transport` (app.py:598-603) is a live→fake downgrade on a running process.** `FakeGoogleTransport.__init__` refuses outside pytest without `VAN_ALLOW_FAKE_GOOGLE_TRANSPORT=1` (transport.py:124-125), which blunts it — but anyone holding the internal control token can also set `google.oauth = None` (app.py:602), permanently breaking live Workspace calls until restart. A test hook mutating production state deserves to be behind a settings flag as well as the env guard.
2. **The Fernet key fallback swallows everything** (service.py:45-47): `except (ValueError, InvalidToken, Exception)` then derives a key from `sha256(key)`. A typo'd or truncated key does not fail — it silently yields a *different* working vault, so previously stored tokens become `token_corrupt` and a fresh grant is written under the wrong key. Fail-closed would be safer.
3. **`revoke()` is local-only** (service.py:91-93): no call to Google's revoke endpoint, so a compromised-then-"revoked" refresh token stays valid at Google indefinitely.
4. **Consumer-session plane is unscopable by nature** — one Google cookie jar with full account authority, bounded only by a domain string (notebook.py:582) and browser policy. If the Fabric is ever implemented, this becomes the highest-value target in the system.

### 4. Can Gmail/Drive content ever become an instruction on a command path?
**No — today, structurally impossible, for a stack of independent reasons.**
1. Gmail content is never fetched: `gmail_search` returns only `{id, threadId}` (transport.py:81-83) and no `messages.get` exists. Drive content is never fetched either — `drive_search` requests a metadata `fields` mask (transport.py:100).
2. Nothing writes Google output into the command path: `/v1/briefing` (the only owner-visible consumer of a Google read) returns to the device; `mail_items` is hard-coded `None` (app.py:522).
3. Hermes metadata is an allow-list with no Google data (orchestrator.py:499-520).
4. The single execution entry point accepts 5 fixed action IDs and requires an exact parameter digest match against a previously sealed authority (service.py:200-213) — no free-form instruction can enter.
5. Even if content did arrive, `ContentTrust.UNTRUSTED` text is scanned for `INJECTION_MARKERS` and mutations are rejected as `rejected_untrusted` (orchestrator.py:335-346).
**Future risk to note:** point 5 is a keyword denylist, so it is the weakest of the five. The moment anyone implements `messages.get` or Drive content export, layers 1-3 disappear at once and the only remaining barriers are the digest gate (4) and that denylist. The evidence plane already models this correctly — `SourceTrust.TRUSTED_OWNER_FILE` for Obsidian vs `VERIFIED_SYSTEM` for VEKL (obsidian.py:321, vekl.py:190) — so the trust vocabulary to do it right exists; it just has no Google content to label yet.

### 5. Other observations
- **Auth surface is consistent and fail-closed**: `verify_internal_control` rejects when unconfigured (control.py:18-19); the ingress middleware 503s without a configured ingress token and 401s on mismatch (app.py:374-378); all constant-time comparisons (`hmac.compare_digest`).
- **`/v1/google/status`, `/v1/google/mesh`, `/v1/google/capabilities` are NOT internal-token routes** (absent from app.py:348-356) — an authenticated owner device can read them. They expose scope lists, capability states and evidence pointers, but no secrets. Acceptable; worth knowing.
- **Honest self-reporting throughout**: `service_state: ENVIRONMENT_PREPARED_NOT_IMPLEMENTED`, `inference_canary.ready: false`, `excluded_until_cloud_setup`, `broader_provider_acceptance: {…: false}`, `"CONFIGURED does not mean READY"` (GOOGLE_INTELLIGENCE_MESH.md:37). This repo does not overclaim in its artifacts. The overclaiming, where it exists, is in the *skills*: `hermes/skills/google-workspace/SKILL.md:27` instructs Hermes to "Request bounded read via gateway tool/MCP" for Gmail/Calendar/Drive — but `hermes/mcp/owner_runtime_stdio.mjs:51-70` exposes **no such tool**. A Hermes run following that skill has no way to comply.

---

## Appendix A. Complete Google/knowledge route inventory and its auth gate

Two independent credentials exist at ingress (app.py:359-390): `X-Van-Ingress-Token` + `X-Van-Device-Token` (owner device), and `X-Van-Internal-Token` (machine/Hermes). `internal_control_route` (app.py:348-357) lets the internal token *bypass* the device check for named paths; the handlers then re-verify it.

| route | file:line | gate | reaches Google? |
|---|---|---|---|
| `POST /v1/commands` | app.py:508 | device signature + ingress | no — dispatches to Hermes |
| `GET /v1/briefing` | app.py:515 | ingress + device | **yes** — `calendar_agenda` |
| `GET /health` | app.py:397 | ingress only | yes (status/mesh reads, no API call) |
| `POST /v1/google/test-transport` | app.py:598 | internal | swaps transport |
| `GET /v1/google/gmail/search` | app.py:605 | internal | **yes** |
| `POST /v1/google/gmail/send` | app.py:616 | internal + A4 `approved` | **yes** |
| `GET /v1/google/status` | app.py:629 | ingress + device | no API call |
| `POST /v1/google/connect` | app.py:633 | internal | writes the vault |
| `POST /v1/google/revoke` | app.py:642 | internal | local only |
| `GET /v1/google/mesh` · `/capabilities` | app.py:648, 652 | ingress + device | no |
| `POST /v1/google/jobs/plan` | app.py:657 | internal | plan row only |
| `GET /v1/google/jobs/{id}` · `POST …/artifacts` | app.py:662, 670 | internal | no |
| `POST /v1/runtime/resolve` | runtime_api.py:161 | internal | no (preview only) |
| `/v1/runtime/knowledge/vekl/{query,certify-canary}` | runtime_api.py:240, 248 | internal | VEKL host |
| `/v1/runtime/knowledge/obsidian/{query,index,certify}` | runtime_api.py:256, 264, 272 | internal | local FS |
| `/v1/runtime/knowledge/notebook/enterprise/*` | runtime_api.py:280-301 | internal | **discoveryengine** |
| `/v1/runtime/knowledge/notebook/consumer/{ask,certify}` | runtime_api.py:305, 313 | internal | Browser Fabric |
| `POST /v1/runtime/knowledge/actions/execute` | runtime_api.py:321 | internal | the 5 actions |
| `/v1/runtime/actions/{begin,submitted,verify,{id}}` | runtime_api.py:332-397 | internal | no |

**Every mutating Google surface in the gateway is behind the machine token, not the owner device.** The owner device can reach exactly two Google-touching routes, both read-only (`/v1/briefing`, `/v1/google/status`-family).

---

## Appendix B. Build-gap ledger — what is missing between "designed" and "works"

Ordered by how much is already built behind the gap.

1. **Browser Harness + Stagehand HTTP servers (ports 9141/9140).** Blocks the entire consumer NotebookLM capability and, by extension, `mixboard`/`flow`/`workspace_studio` if they ever route through the Fabric. Everything above the HTTP boundary is written and tested against stubs. The deployment bootstrap already pins and installs the dependencies and admits `ENVIRONMENT_PREPARED_NOT_IMPLEMENTED`. *Highest build-value-per-line in the repo.*
2. **A Cloud project + service account for Notebook Enterprise.** No code needed at all — `notebook_enterprise_enabled`, `_project_number`, and one of `_service_account_file`/`_access_token_file` (config.py:92-99). A complete CRUD implementation is sitting idle behind four settings.
3. **A VEKL base URL.** Same: `vekl_enabled` + `vekl_base_url` + session/principal IDs. A candidate server exists in-tree (`trading/vekl/server.mjs`) but its route contract vs `/v1/missions/{id}/vekl` is unverified.
4. **Obsidian is one setting away from working** (`obsidian_enabled` + `obsidian_vault_path`) and needs no external process whatsoever.
5. **Gmail read is one function away from useful** — `messages.get` (or `format=metadata`) would turn `gmail_search`'s ID list into something a briefing could show. Note this is also the change that would open the untrusted-content path discussed in Q10.4, so it should land together with content labelling.
6. **Calendar write does not exist** — `events.insert` is unwritten, though the `auth/calendar` scope to do it is already being requested.
7. **Routes for `drive_search`, `contacts_resolve`, `tasks_list`, `gmail_draft`, `calendar_reschedule`** — five implemented transport functions with no caller. Either expose them (with MCP tools so the `google-workspace` skill can actually comply) or delete them; keeping live-credentialed dead code is the worse of the three options.
8. **MCP tools for Workspace.** `hermes/mcp/owner_runtime_stdio.mjs` would need Gmail/Calendar/Drive entries before any Workspace skill instruction is executable.
9. **No gateway path can ever mark a capability READY from observed behaviour.** READY comes only from `record_capability_evidence` driven by an import tool. A live-canary loop inside the gateway (the `certify_*` pattern the knowledge providers already use — vekl.py:207, obsidian.py:334, and `authorize_workspace_oauth.py certify`) is the missing generalisation.
10. **`scrub_for_prompt` should be wired or removed** (service.py:161) — a tested, uncalled security function is a false sense of coverage.

---

## Closing assessment

This is a **control plane without an execution plane, and it is unusually honest about it.** The identity model (hashed principal, per-capability identity binding validated at three layers, four isolated credential planes, env-scrubbed delegated worker), the action model (sealed command authority, parameter digests, read-back verification, idempotency ledgers, conflicted-not-retried timeouts), and the evidence model (source trust, provenance, never-OWNER_SIGNED provider artifacts) are all real, tested and better than the integrations they govern.

What is missing is almost entirely *the other side of an HTTP boundary*: two loopback ports with no server, a Gemini key the gateway only knows as a boolean, a Cloud project that was never created, and a VEKL host that was never configured. Of 16 registered Google capabilities, 13 have no gateway code at all; of 8 Workspace transport functions, 1 is reachable by the owner; of 4 knowledge providers, 1 (Obsidian) can work with no external dependency.

The one place where the gap could become a *safety* problem rather than a *completeness* problem is Q10.4: Gmail and Drive content cannot become instructions today because that content is never fetched. That is a property of an unfinished integration, not of a designed barrier — and the barrier that would remain (a keyword denylist at orchestrator.py:335-346) is the weakest control in a system whose other controls are strong. The trust vocabulary to fix it properly already exists in the evidence layer.
