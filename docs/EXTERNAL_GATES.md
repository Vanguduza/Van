# External certification gates

These require owner credentials, live Google surfaces, provider/runtime access, physical hardware, or environments that repository CI cannot truthfully certify.

Resolved 2026-09-15: the live Hermes `van` profile is installed and certified on `dial-hermes-control`; Sonnet 5 executed a live VAN canary and the core Hermes/DIAL services and delegation suites passed. This is no longer an external gate.

Resolved 2026-09-16: permanent Workspace Desktop OAuth consent is complete, the refresh credential is encrypted in the VAN gateway vault, and live Gmail, Calendar, Drive, People/Contacts and Tasks metadata canaries all returned HTTP 200. `workspace_api` is `READY`. Cloud/Enterprise-only capabilities remain separate.

Resolved 2026-09-16: Stitch live generation is certified independently of Workspace OAuth. The authenticated Google Stitch MCP route returned a real generated screen with screen ID, HTML and image artifacts; VAN records this capability `READY` via a token-free receipt. Broader DIAL visual-acceptance and orchestrated-use proofs remain separate from VAN generation readiness.

Resolved 2026-09-16: the loopback VAN gateway is restart-persistent and the schema-4 owner pairing boundary is live-certified. Pairing tickets are hash-only and single-use; normal client APIs require the outer ingress bearer plus a revocable per-device token; commands additionally require the encrypted per-device HMAC. Both client credentials and HMAC verification survive restart, while device revocation atomically revokes grants and remains denied after a second restart. Token-free evidence is recorded at `artifacts/runtime/van_pairing_v4_live_attestation.json`.

Resolved 2026-09-15: the delegated `antigravity_worker_account` is authenticated in a separate isolated runtime home. Live model discovery and a Gemini 3.8 Flash generation canary passed; no canonical Google/API credential inheritance is permitted. Token-free evidence is recorded at `artifacts/google/antigravity_worker_live_attestation.json`. Antigravity is no longer an external authentication/generation gate.

Resolved 2026-09-15 (workstation): local Project Truth mounts for `van`, `dial`, `dde`, `gtr`, `goat`, and `aeci` resolve via `registries/project_mounts.json` + `tools/projects/sync_project_truth.py` offline cache. Gateway live PUT still requires a running gateway.

Resolved 2026-09-17: the canonical GitHub Actions workflow is live at `.github/workflows/van-ci.yml` and repeatedly certifies backend, Android unit/build/lint, shared geometry, visual rendering and artifact upload. Workflow installation/scope is no longer a production gate.

| Gate | Prerequisite | Repo-side readiness |
|---|---|---|
| Canonical owner Google principal | Hermes-authenticated owner Google account | hashed principal registration + Hermes attestation import |
| Google Workspace OAuth live | permanent Desktop OAuth + owner consent | READY — encrypted refresh credential installed; Gmail/Calendar/Drive/Contacts/Tasks live canaries all HTTP 200 |
| Gemini runtime | dedicated Google-account-owned API/runtime credential + inference credits | CAPACITY_LIMITED — restricted `van-gemini-runtime` key installed; Hermes reports `gemini: logged in`; authenticated model discovery returned HTTP 200 / 50 models; `gemini-3.6-flash` inference returned `RESOURCE_EXHAUSTED` because prepaid credits are depleted. Receipt: `artifacts/google/gemini_runtime_auth_attestation.json` |
| Gemini Live | authenticated Gemini runtime credential + live endpoint canary | CAPACITY_LIMITED — shared credential is authenticated and a bidi Live model is discoverable; live generation not promoted while project prepaid credits are depleted |
| Deep Research | authenticated Gemini runtime credential + quota canary | CAPACITY_LIMITED — Deep Research models are visible through authenticated discovery; execution awaits restored project prepaid credits |
| Gemini Notebook personal | owner Google session in the managed Browser Fabric profile + Harness/Stagehand canary | Rev 3.1 consumer bridge now routes through Browser Harness + Stagehand with grounded ask/note readback and no direct runtime Playwright/cookie export; READY requires live Browser Fabric profile + provider canary evidence |
| Gemini Notebook Enterprise | eligible Cloud/Enterprise setup + service identity/token canary | Rev 3.1 official API lifecycle/readback adapter implemented; still EXTERNAL until Cloud plane is configured and live-certified |
| VEKL knowledge source | DDE/VEKL mission endpoint + bounded VAN principal/session credential | Rev 3.1 read-only evidence adapter implemented; READY requires a live mission projection canary |
| Obsidian owner knowledge | owner-selected vault mounted on gateway host | Rev 3.1 bounded incremental index/query implemented with secret exclusion; READY requires live vault index/query certification |
| Stitch | Google Cloud Stitch MCP credential plane | READY — authenticated live `generate_screen_from_text` canary passed; token-free receipt: `artifacts/google/stitch_live_attestation.json` |
| Mixboard / Flow / AI Studio / Workspace Studio | owner Google session on Hermes | consumer capabilities CONFIGURED via attestation; per-capability live canary still required |
| Jules | owner Google sign-in on Hermes | CONFIGURED via attestation; READY needs live worker receipt |
| Nano Banana / Veo | authenticated Gemini runtime credential + quota canary | CAPACITY_LIMITED — image and Veo models are visible through authenticated discovery; generation awaits restored project prepaid credits |
| Google ADK/A2A | owner-administered Cloud/runtime | still EXTERNAL (cloud plane) |
| Android owner gateway authentication | ingress bearer + revocable device token + enrolled device HMAC | LIVE-CERTIFIED on schema 4 — single-use pairing, hash-only device token persistence, restart continuity, atomic revoke, and post-restart denial all passed |
| Stable public HTTPS ingress | named Cloudflare Tunnel token + stable hostname | EXTERNAL — fail-closed installer/service ready; `trycloudflare.com` is rejected for production |
| Physical Samsung device | USB device + permissions | `tools/certification/device_cert_probe.py` + `docs/DEVICE_ACCEPTANCE_CHECKLIST.md` |
| Local voice model bundles / owner speaker profile | trained Hey Van KWS bundle + local second-pass ASR bundle + speaker-embedding model and owner reference embedding installed on the S24 | REPO_COMPLETE / EXTERNAL_ARTEFACT — sherpa-onnx 1.13.8 is exact-pinned; KWS, second-pass ASR and speaker scorers are implemented behind checksum-confined app-private manifests and fail closed when assets are absent. Physical false-positive/latency/accuracy and owner-enrollment evidence remain device gates. |
| Artist `.riv` | Rive editor | contract + Canvas fallback + handoff |
| Owner visual acceptance | owner review | acceptance matrix |
| Signed production release | production keystore | Gradle wiring + `android/keystore.properties.example` |

## Automation & Browser Fabric gates

Owner adoption is already recorded: n8n, Stagehand and Browser Harness decision records are `SIGNED`/approved on 2026-09-18, and the Automation & Browser security-policy amendment is `OWNER_APPROVED` and applied. Approval authorizes the architecture; it does **not** certify a live runtime.

| Gate | Required proof | Repo-side readiness |
|---|---|---|
| n8n self-hosted runtime | pinned local instance + PostgreSQL + task runner + restart canary | PENDING_LIVE — hardened self-hosted deployment/bootstrap exists; gateway remains fail-closed until live certification |
| n8n workflow generation | novel goal → IR → compile → local create → synthetic execution → HOT reuse | PENDING_LIVE — deterministic compiler/validator/admission and tests exist; live n8n execution proof required |
| n8n security | security audit and trust-boundary proof | PENDING_LIVE — repository controls exist; live host audit required |
| n8n backup/restore | isolated restore with matching encryption key | PENDING_LIVE — repository tooling exists; restore drill required |
| Automation webhook ingress | signed event + replay rejection + verified intake | PENDING_LIVE — signed ingress path implemented; live trigger proof required |
| Standing automation | owner-derived standing authority + bounded run + verified result | PENDING_LIVE — durable authority/grant path implemented; live scheduled/event execution proof required |
| Browser Harness | pinned private worker + deterministic navigation/action + evidence pointer | REPO_COMPLETE / PENDING_LIVE — loopback Harness worker, pinned browser-harness 0.1.13, systemd/bootstrap/health gate and gateway adapter are implemented; live Trading Core canary required |
| Stagehand local semantic browser | private local/CDP worker + observe/extract/act canary under Hermes assignment | REPO_COMPLETE / PENDING_LIVE — private Stagehand 4.1.0 worker, systemd/bootstrap, shared Harness-owned CDP handoff and bounded HybridBrowserWorker are implemented; direct Stagehand agent loops are refused; live worker/model canary required |
| Browser authenticated profile | managed owner profile survives restart without secret export and identity is verified | PENDING_LIVE — profile alias/lease/secretref architecture implemented; owner authentication + restart identity proof required |
| Browser boundary escalation | live task exceeds scope → WAITING_FOR_OWNER → Android decision → scoped authorization → same task resumes | REPO_COMPLETE / PENDING_LIVE — durable escalation and scoped-resume code/tests implemented; live worker/device proof required |
| NotebookLM consumer via Browser Fabric | authenticated managed profile + grounded ask + A3 note create/readback | REPO_COMPLETE / PENDING_LIVE — direct runtime Playwright removed; Browser Harness + Stagehand provider path implemented; live profile/runtime canary required |
| Browser prompt-injection containment | adversarial live page cannot widen authority or leak secrets | PENDING_LIVE — synthetic policy tests exist; live adversarial canary required |
| Trading Core isolation | maximum certified automation/browser load preserves VATI safety envelope | PENDING_LIVE — measured host load test required |
| Browser→automation optimization | discovered stable API shadow-compares before route promotion | PENDING_LIVE — promotion architecture exists; live evidence required |

Rules: code or configuration alone never means READY; runtime evidence must be token-free and contain no browser secrets; n8n/Stagehand/Harness success is not owner-visible completion without gateway verification; payment execution remains outside automated browser/automation authority.

## Google certification rules

1. `CONFIGURED` is **not** `READY`.
2. Consumer Google sessions may not be certified by cookie presence alone.
3. `READY` requires an evidence pointer recorded through the Google identity broker.
4. No raw Google email, cookie, OAuth token, API key, or service-account private material is stored in the capability registry or artifact provenance.
5. Workspace OAuth, Gemini runtime, Cloud/service identity and consumer sessions must remain separate credential planes. Explicit delegated identities are allowed only for their bound capabilities and may not inherit owner authority or credentials.
6. Missing or unverified capability must return an explicit degraded/auth-required state; never simulate success.
7. Hermes-hosted authentication is recorded as attestation evidence; it does not copy tokens into Van.

## Physical device checklist

Install, provisioning, overlay, notification listener, mic, TTS, biometric, drag/dock, rotation, process kill, Doze, reboot, offline queue, reconnect, secret notification, barge-in, share-to-VAN routing, Google capability status display, Rive failure → Candidate B art → Canvas, reduced motion, wake word, Candidate B embodiment, flame aura, trading aura on the overlay. The rows and their evidence are in `docs/DEVICE_ACCEPTANCE_CHECKLIST.md`; the run order and prerequisites are in `docs/PHYSICAL_TEST_RUNBOOK.md`.

## Android production gateway ingress

Repository and host-side closure require the VAN gateway itself to remain loopback-only on `dial-hermes-control`. Android release builds must receive `VAN_GATEWAY_BASE_URL` as a stable `https://` endpoint; release assembly fails closed when it is absent or insecure.

The externally reachable API uses layered client authority. `VAN_INGRESS_TOKEN` / `X-Van-Ingress-Token` is the outer transport bearer. Except for ingress-only `/health`, normal Android API calls also require a revocable per-device access token. Device command execution additionally requires the enrolled per-device HMAC secret. New devices can obtain these credentials only through a short-lived single-use pairing ticket issued by the internal control plane. Privileged Hermes control routes retain their separate internal-control credential and that credential is not accepted as a general external bearer.

A volatile `trycloudflare.com` quick tunnel is not production authority. Repo-side named-tunnel tooling is provided by `deploy/systemd/van-cloudflare-tunnel.service` and `tools/runtime/install_van_cloudflare_tunnel.sh`; the installer rejects quick-tunnel hostnames and requires an authenticated public `/health` canary before success. The remaining external routing gate is provisioning a named Cloudflare Tunnel token and stable hostname mapped to `http://127.0.0.1:8787`. This gate does not affect Workspace OAuth durability or live Google READY certification.
## Remote Browser (Rev 1.5) gates

The Remote Browser's Gateway half is implemented and tested in the repository. Nothing below
is certified, and three of these are gates no amount of repository work can close.

The distinction this section exists to keep: **the code is written and the outcome is
unproven** is not the same claim as **the code is absent**, and neither is the same as
**certified**. The programme's per-row state is in
`docs/project-state/REMOTE_BROWSER_IMPLEMENTATION_MATRIX.json`; this table is the subset that
needs something outside the repository.

| Gate | Required proof | Repo-side readiness |
|---|---|---|
| Browser Stream Host (RB-002/RB-010) | a provisioned dual-homed host running Chromium, the media pipeline and the signalling endpoint, answering a real SDP offer | EXTERNAL — no host exists. The device negotiates against `browser_stream_signal_url`, which is empty by default; an empty setting means the interactive routes are not mounted at all rather than handing the phone an endpoint that does not answer. |
| WebRTC media path (RB-019/RB-020/RB-121) | an owner S24 Ultra negotiating H.264 with that host and drawing frames | EXTERNAL + DEVICE — the Android client, both data channels and the renderer are written and reached from the owner surface. Not one frame has been drawn anywhere: WebRTC needs a peer. |
| Android build of the Remote Browser surface | `:app:assembleDebug` and `:app:lintDebug` green with the WebRTC and okhttp dependencies | CI-ONLY — the Android Gradle Plugin cannot be fetched in the audit container, so CI is the only authority that compiles any of this. The dependency versions are pinned to digests measured from the artefacts and checked against the build by `tests/contracts/test_remote_browser_dependencies.py`. |
| S24 key attestation (RB-120) | a real S24 Ultra producing an attestation chain the gateway's parser accepts, at StrongBox security level | DEVICE — the parser, the policy and the enforcement are implemented and tested against the structures Android documents, including the high-tag-number DER forms that a naive reader silently never finds. Whether a real handset emits a chain this accepts has never been observed. |
| Second-device refusal canary (RB-112) | a second phone, with a valid paired device token, refused on an owner mutation | DEVICE — enforced and tested in-process: once any device is bound, every other device is refused. The canary is the same claim against real hardware. |
| Signed connectivity provisioning (RB-121) | a release build carrying `VAN_CONNECTIVITY_TRUSTED_KEYS` and a gateway publishing a signed manifest | OWNER_DEPLOYMENT — the verifier, the registry and the rotation refusal are implemented and executed in the JVM harness, and since RB-121 the release build *refuses to be produced* without an anchor rather than shipping one that applies no manifest. One parser now serves both readers: the provisioning intake was written with its own, which read the `kid=PEM` string as JSON and would have reported every correctly configured release APK as unprovisionable — with every test green. |
| Route diversity (RB-070) | two independently reachable ingress paths | EXTERNAL — there is one ingress, and both halves say so rather than rounding up: the device declares one `routeId` for both carriers, the supervisor reports `SINGLE_PATH`, and the owner-readable string is "Connected" rather than "Connected, with a spare route". |
| Browser Control Agent private path (RB-115/RB-116) | a private VCN, issued client certificates, and a call from Trading Core that the agent admits | REPO_COMPLETE / EXTERNAL — the narrow contract, its six authority checks and the mTLS server context exist and are executed. Thirteen mutations, thirteen caught. What has never happened: a real TLS handshake, in either direction. |
| Raw CDP exposure proof (RB-117) | `qualify.sh` returning GREEN on a real host, having connected to the debugging port on every global address | REPO_COMPLETE / EXTERNAL — the Chromium unit pins `--remote-debugging-address=127.0.0.1` and the CDP client refuses any endpoint that is not a loopback literal. The exposure check itself needs a host with interfaces to scan, and it reports UNKNOWN (which fails) rather than GREEN when it cannot scan them. |
| Stream-host profile volume (RB-118) | an encrypted block device attached only to the Stream Host | OWNER_DEPLOYMENT — §13.5 option A is chosen and reasoned. `bootstrap.sh` refuses to run without a block device rather than falling back to a directory, and `qualify.sh` reports RED for a mount that is not dm-crypt. |
| Stream-host readiness certification (RB-046) | one of the three canaries in `tools/certification/certify_browser_stream_host.py` passing against a live host, which is what writes `browser_stream_host` readiness evidence | REPO_COMPLETE / EXTERNAL — this gate is load-bearing rather than documentary: `browser.interactive.session` is declared `EXTERNAL_RUNTIME` against that probe, so until a canary has run, **binding a browser session to a Mission is refused** and the refusal names the missing evidence. §23.2's manual browsing is unaffected. The three canaries, the wire protocol they speak and the contract test that stops the Gateway from ever writing that evidence itself all exist and are executed; no host has answered a handshake. |
| Owner-S24 provisioning (RB-108/RB-109/RB-111) | an `adb`-connected S24 Ultra, a release APK and a Gateway holding the connectivity signing key | REPO_COMPLETE / DEVICE — the two forms §0D.2 forbids are gone and cannot come back: `baseUrl`'s setter and `pairThisDevice` are private, and the guard reads shape rather than wording so a rebuild that dropped the labels still fails. `tools/provisioning/provision_owner_device.py` asks the Gateway for one signed, single-use, ten-minute payload and hands it over; the credential never touches the installer's disk. What has never happened is the handover itself. |
| Release build binding (RB-111/RB-121) | a production keystore the owner holds, and a connectivity signing key | OWNER_DEPLOYMENT — `assembleRelease` now refuses three things it used to allow: a plain-http gateway, the per-machine Android debug signing key, and an empty `VAN_CONNECTIVITY_TRUSTED_KEYS`. The last is the one worth naming: a release with no trust anchor installs, opens and waits for an installer it can never accept, with nothing anywhere saying why. |
| §38 red-team matrix (RB-052) | a Browser Stream Host, a carrier handover and a physical handset for nine of the seventy-two scenarios | REPO_COMPLETE / EXTERNAL — 63 `PASS`, 9 `BLOCKED_EXTERNAL` (recounted from the register 2026-09-24), none `assumed`, in `evidence/van-system-audit/red_team_register.json`. Every `PASS` cites a runnable pytest node id and all 197 cited Python tests were executed. A `PASS` means the repository can demonstrate the refusal, not that a live Remote Browser has been attacked and survived. |
| §43 production acceptance (RB-058) | everything in this table, plus measurement on real hardware | REPO_COMPLETE / EXTERNAL — `evidence/van-system-audit/production_acceptance.json` carries §43's one hundred and four requirements: 59 repository-proven, 38 blocked external, 7 owner-deployment (as `tools/ci/production_acceptance.py` reports on 2026-09-24). The verdict is recomputed from the rows by `tools/ci/production_acceptance.py`, so the ledger cannot say `PRODUCTION_ACCEPTED` while a single row says otherwise. |
| Interactive profile lease under load (RB-050) | the authenticated owner profile held by an interactive session while Hermes wants it | PENDING_LIVE — the lease, the holder kinds and the 409 are implemented and tested; the contention is real only with a real host. |
