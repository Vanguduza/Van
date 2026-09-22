# VAN runtime qualification matrix (Fable whole-project audit)

Audited commit `0067d55071342b963293d0724f5a1604d233d105`, 2026-09-21.

This matrix separates **repository completeness** (what the code at this commit implements and what its tests prove in-process) from **live qualification** (what only a real host, device, provider or credential can prove). Nothing here is promoted on repository evidence. Where a live attestation exists in `artifacts/` it is cited; where the repository claims a live result without a token-free receipt, that is stated.

Vocabulary for the "Live state" column: `LIVE_CERTIFIED` (token-free receipt in repo), `PENDING_LIVE` (repo complete, no receipt), `CAPACITY_LIMITED`, `EXTERNAL` (infrastructure absent), `DEVICE` (needs the S24), `OWNER_DEPLOYMENT` (owner decision/key needed), `NOT_APPLICABLE_UNTIL_GAP_CLOSED` (a repository gap must close before live proof is meaningful).

| ID | Dependency | Repository status | Live state | Evidence required to promote | Existing receipt |
|---|---|---|---|---|---|
| QUAL-HERMES-01 | Hermes API server contract `POST /p/van/v1/runs`, `GET /p/van/health`, `/v1/capabilities` (hermes/bridge.py:26-94) | Gateway side complete; contract is gateway-assumed, no Hermes-side spec in repo | PENDING_LIVE | A live gateway command producing a Hermes run id, recorded token-free (run id, HTTP status, dispatch_ms) | None. `docs/PRODUCTION_ACCEPTANCE_LEDGER.md:92-115` certifies the profile and a model turn, not the run API |
| QUAL-HERMES-02 | Hermes invokes the owner-runtime MCP shim (`van_owner_runtime`, 30 tools) and calls `mission_result` | Shim + routes complete; `tests/contracts/test_owner_runtime_mcp_contract` runs the shim as a subprocess | PENDING_LIVE (REC-P2-010 re-qualification pending) | One live run whose `POST /v1/runtime/missions/result` arrives from the Hermes process and moves a mission RUNNING→VERIFYING; a Google read (`google_calendar_agenda`) invoked by Hermes | None |
| QUAL-HERMES-03 | Hermes dereferences `canonical_context.fact_ids` via `context_*` tools | Routes complete; kernel has no producer (GAP-F-001) | NOT_APPLICABLE_UNTIL_GAP_CLOSED | After GAP-F-001: a run whose lexical/graph query returns the owner fact named in the command | None |
| QUAL-HERMES-04 | Hermes de-duplicates `/v1/runs` on `metadata.idempotency_key` after a lost response | Gateway marks idempotency FAILED and allows resend | PENDING_LIVE | Timeout-after-accept canary: second submission yields one run | None |
| QUAL-HERMES-05 | Hermes runtime loads `policy/van_policy_hook.py:evaluate` before tool execution | Hook + 20 tests; installer stages files | PENDING_LIVE | Live A5 refusal and A4 approval prompt observed from the Hermes side | `doctor_van_profile.sh` passed 2026-09-15 (file presence only) |
| QUAL-AND-01 | Physical Samsung S24 Ultra: overlay, boot recovery, Doze, notification listener, share sheet, biometric, process kill, reconnect | Repo complete (`docs/DEVICE_ACCEPTANCE_CHECKLIST.md`, `tools/certification/device_cert_probe.py`) | DEVICE | Checklist run on the device with probe output committed token-free | None |
| QUAL-AND-02 | Signed release build with `VAN_GATEWAY_BASE_URL` https, production keystore, connectivity trust anchor; owner-device provisioning handover | `assembleRelease` fails closed without them; `tools/provisioning/provision_owner_device.py` | OWNER_DEPLOYMENT | Release APK signing identity + provisioning payload consumed once | None (debug APK leaves CI) |
| QUAL-AND-03 | Stable public HTTPS ingress (named Cloudflare Tunnel) | Installer refuses quick tunnels | EXTERNAL | Authenticated public `/health` canary on the named hostname | `artifacts/runtime/van_ingress_live_attestation.json` (loopback + restart/revocation certified; tunnel not) |
| QUAL-VOI-01 | Hey-Van KWS bundle, local second-pass ASR bundle, speaker embedding model + owner enrolment | sherpa-onnx 1.13.8 pinned; fail closed without assets | DEVICE + EXTERNAL_ARTEFACT | False-positive rate, latency, owner enrolment evidence on device | None |
| QUAL-VOI-02 | Local TTS engine (sherpa) | Not implemented (GAP-F-013); Android TTS is the only engine | NOT_APPLICABLE_UNTIL_GAP_CLOSED | — | — |
| QUAL-EMB-01 | Authored `van.riv` conforming to `visual-authority/rive_contract.json` | Runtime + contract + Canvas fallback complete; no asset | EXTERNAL_ARTEFACT | Asset checksum recorded; contract test loads it; owner visual acceptance matrix signed | None |
| QUAL-GOO-01 | Google Workspace OAuth (Gmail, Calendar, Drive, Contacts, Tasks) | Complete | LIVE_CERTIFIED (workspace_api READY) | Periodic re-canary after token rotation | `artifacts/google/*` attestations; ledger 2026-09-16 HTTP 200 canaries |
| QUAL-GOO-02 | Gemini runtime / Live / Deep Research / Nano Banana / Veo | Registry + attestation import only (executor=hermes) | CAPACITY_LIMITED | Prepaid credits restored; per-capability live receipt | `artifacts/google/gemini_runtime_auth_attestation.json` |
| QUAL-GOO-03 | Stitch | Registry + receipt | LIVE_CERTIFIED | — | `artifacts/google/stitch_live_attestation.json` |
| QUAL-GOO-04 | Antigravity delegated worker | Registry + receipt | LIVE_CERTIFIED (generation), CAPACITY rules apply | — | `artifacts/google/antigravity_worker_live_attestation.json` |
| QUAL-GOO-05 | Mixboard / Flow / AI Studio / Workspace Studio / Jules / ADK-A2A | Registry only; three have `executor: null` | EXTERNAL / CONFIGURED | Per-capability live canary through Hermes | attestation flags only |
| QUAL-GOO-06 | Gemini Notebook Enterprise (official API) | `knowledge/notebook.py` complete, default off | EXTERNAL (Cloud plane) | Enterprise project configured; `certify_knowledge_runtime.py` canary | None |
| QUAL-GOO-07 | NotebookLM consumer via Browser Fabric | Complete, routes through Harness+Stagehand | PENDING_LIVE | Managed profile + grounded ask readback canary | None |
| QUAL-KNW-01 | VEKL evidence endpoint; Obsidian vault; Exa research key | Adapters complete, all default off | PENDING_LIVE / EXTERNAL | `tools/google/certify_knowledge_runtime.py` and `/v1/runtime/research/certify-canary` receipts | None |
| QUAL-BRW-01 | Browser Harness private worker (browser-harness 0.1.13) on Trading Core | `deploy/van-trading-core/browser/harness_service.py` + systemd | PENDING_LIVE | Health gate + navigation canary via `tools/certification/certify_browser_fabric.py` | None |
| QUAL-BRW-02 | Stagehand 4.1.0 private worker with model credential; adversarial injection canary | Complete; direct agent loop refused | PENDING_LIVE | observe/extract/act canary; adversarial page cannot widen authority | None |
| QUAL-BRW-03 | Browser Stream Host (Chromium, media pipeline, signalling, control agent mTLS, encrypted profile volume) | `deploy/van-browser-stream/*`, `services/browser_control_agent` complete; no host | EXTERNAL | `tools/certification/certify_browser_stream_host.py` canary; first frame drawn on S24; RB-117 exposure GREEN | None |
| QUAL-BRW-04 | Owner-authenticated managed browser profile survives restart | Alias/lease/secretref complete | PENDING_LIVE | Restart identity proof | None |
| QUAL-AUT-01 | n8n self-hosted runtime (pinned, Postgres, task runner), signed webhook ingress, standing automation | `deploy/van-trading-core/automation/*` + gateway complete | PENDING_LIVE | Live create/execute/HOT reuse canary; signed event + replay rejection; restore drill | None |
| QUAL-AUT-02 | Temporal durable execution | Not built (stack-lock phase 11) | EXTERNAL / DELIBERATE_SCOPE | Adoption decision | — |
| QUAL-TRD-01 | Live market feed into `vati-session@` (bar lake, MT5 pull, Deriv WS) | Complete; simulated provenance labelled | PENDING_LIVE | Session runs against a live feed with `provenance != SIMULATED_OR_UNKNOWN` | `evidence/van-system-audit/TRADING_POSTGRES_RUNTIME_QUALIFICATION_20260920.md` (Postgres ledger) |
| QUAL-TRD-02 | Broker execution: MT5 bridge worker + VanBridgeEA, Deriv, cTrader | Complete (grep-verified single submit caller) | PENDING_LIVE (demo first) | DEMO fill → SHADOW → LIMITED_LIVE per Rev 5.1 harness (`LIVE_ELIGIBLE` currently false) | `tools/certification/rev51_harness.py --check`: SPEC_CLOSED true, RUNTIME/SHADOW/LIVE false |
| QUAL-TRD-03 | Owner authority key enrolled in `registries/owner_authority_keys.json` on van-trading-core (mandate-admit, owner-halt, capsule-promote, ticket-confirm) | Verifier complete; registry empty by design | OWNER_DEPLOYMENT | Key id present; signed mandate admitted; halt act verified | None |
| QUAL-TRD-04 | Exact-SHA Trading Core deployment | `rebuild`/`bootstrap`/`qualify` complete | LIVE (2026-09-21 closure) | `qualify.sh` GREEN citing the SHA | `docs/audit/van-whole-project-2026-09-21/21_GAP_REGISTER.json` REC-P2-011 |
| QUAL-TRD-05 | Model provider credentials + invoker for VATI shadow cognition | No injection point (GAP-F-004) | NOT_APPLICABLE_UNTIL_GAP_CLOSED | — | — |
| QUAL-TRD-06 | Economic calendar sources (two agreeing providers) | Recorder complete | PENDING_LIVE | `vati-calendar.timer` runs producing VERIFIED rows | None |
| QUAL-OPS-01 | Gateway systemd service on `dial-hermes-control`, loopback bind, restart persistence | Complete | LIVE_CERTIFIED (loopback) | — | `artifacts/runtime/van_ingress_live_attestation.json` |
| QUAL-OPS-02 | Gateway backup/restore drill on the live host | `tools/ops/backup.py drill` | PENDING_LIVE | Drill output committed token-free | None |
| QUAL-OPS-03 | Backend dependency lock reproducibility | Floating pins (GAP-F-017) | NOT_APPLICABLE_UNTIL_GAP_CLOSED | Lock hash in release metadata | — |

## Counts

- External/runtime gates listed: **33**.
- Live-certified with a token-free receipt in the repository: **5** (QUAL-GOO-01, GOO-03, GOO-04, TRD-04, OPS-01).
- Pending live proof with repository work complete: **19**.
- Blocked on a repository gap before live proof is meaningful: **4** (QUAL-HERMES-03, VOI-02, TRD-05, OPS-03).
- Device / owner-deployment / external artefact: **5** (AND-01, AND-02, VOI-01, EMB-01, TRD-03).

## Rules applied

1. `CONFIGURED` is not `READY` (docs/EXTERNAL_GATES.md). A registry entry, attestation flag or adapter is never live evidence.
2. A live receipt must be token-free and name the certified commit; receipts predating a later interface change (the MCP shim, REC-P2-010) do not carry forward.
3. Repository gaps are never hidden behind an external gate: the four `NOT_APPLICABLE_UNTIL_GAP_CLOSED` rows point at `VAN_CANONICAL_GAP_REGISTER.md`.
