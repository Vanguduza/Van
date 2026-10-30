# Whole-product domain and journey review

Audited at `172d2143d3e6d2ec4b401376f5ef5a4cf94c7429`, 21 October 2026. These 24 overlapping review families cover all 82 backend units, including capabilities outside the older 93-feature taxonomy. Each row retains source implementation, live service and handset status as unverified in this pass. Findings refer to `FINDINGS.json` and `REPORT.md`.

## HOME — Home, orb, Quick Hub, Attention and notifications

**Existing specification:** State reducer, severity precedence, compact hub, deep links and notification deduplication are detailed. Source: Part B §§5–6, 11.1, 11.7.

**Positive journey:** A genuine protection or task event creates one scoped Attention item, updates the orb, opens the right subject and records acknowledgement.

**Failure and recovery:** Stale task stream with healthy market stream stays distinguishable; denied notification permission, quiet hours and dismissed previews retain critical in-app incident state; replay does not notify twice.

**Delivery owners:** BE-030; FE-004. **Open findings:** WPC-001, WPC-002, WPC-009, WPC-015.

## BOOTSTRAP — Installation, zero-configuration connection and navigation

**Existing specification:** Signed provisioning and no raw host/token forms are explicit; identity/app-signing continuity is required. Source: Part B §§11.4, 12.1, 14.4, 19.3.

**Positive journey:** Fresh signed install receives/verifies provisioning, enrolls owner/device, connects to the admitted gateway, reads service capabilities and restores an authorized deep link without typing backend configuration.

**Failure and recovery:** Expired provisioning, rotated service certificate/endpoint, lost/replaced/revoked handset, clock skew, unavailable backend and app restore have distinct repair paths; an old device cannot regain authority.

**Delivery owners:** BE-002, BE-003, BE-031; FE-001, FE-003, FE-022. **Open findings:** WPC-004, WPC-001, WPC-013.

## MARKETS — Markets, portfolio summaries, watchlists, screening and alerts

**Existing specification:** Instrument identity, freshness, watchlists and server-side alerts are included. Source: Part B §§7.1–7.3, BE-008/020.

**Positive journey:** Find an instrument, persist a watchlist/screen rule, receive a server-evaluated alert and open the exact venue/instrument with source time.

**Failure and recovery:** Feed gap, delisting, alias collision, market closure, entitlement denial, process death and duplicate alert delivery preserve accurate data and one alert identity.

**Delivery owners:** BE-008, BE-020; FE-006, FE-011. **Open findings:** WPC-001, WPC-002, WPC-008, WPC-009.

## CHART — Charts, indicators, drawings, replay, depth and workspaces

**Existing specification:** Professional chart scope and untrusted bridge boundaries are substantial; replay isolation is explicit. Source: Part B §7 and chart bridge contracts.

**Positive journey:** Save drawings and indicator settings, restore a multi-chart workspace, inspect real order overlays, run isolated replay and submit a typed observation to research.

**Failure and recovery:** Unsupported depth/order types are explicit; reconnect gaps, WebView/native renderer failure, malformed bridge inputs and workspace conflicts preserve instrument precision and never execute from a chart.

**Delivery owners:** BE-018, BE-019; FE-007, FE-008. **Open findings:** WPC-001, WPC-002, WPC-008, WPC-015.

## ORDERS — Manual orders, positions, protection, risk, handover, history and TCA

**Existing specification:** Financial invariants, unknown outcomes, child reservations and ownership transitions are deeply specified. Source: Part A §§5–7, Part B §7.4 and §32.

**Positive journey:** Preview a scoped order, confirm within mandate, receive partial/final fills with protection, hand control between owner and VAN, then reconcile cash and TCA.

**Failure and recovery:** Concurrent spend, partial fill, cancel race, exchange outage, unknown submission, late correction and restart preserve exposure, protection, unique intents and readback.

**Delivery owners:** BE-009, BE-010, BE-011, BE-012; FE-009, FE-011. **Open findings:** WPC-002, WPC-007, WPC-008, WPC-012, WPC-016.

## ACCOUNTS — Accounts, authentication, KYC, funds, payments and statements

**Existing specification:** Local unlink/remote closure, settled funding and provider-hosted flows are explicitly separated. Source: Part B Accounts/Funds requirements; BE-004–007.

**Positive journey:** Link or create an admitted account, validate access, rotate credentials, deposit/withdraw/transfer through the supported flow and reconcile settlement/statement.

**Failure and recovery:** Observe-only access, KYC restriction, expired hosted callback, duplicate transfer, disputed/returned payment and open exposure prevent false success or unsafe closure.

**Delivery owners:** BE-004, BE-005, BE-006, BE-007; FE-010, FE-011. **Open findings:** WPC-008, WPC-001, WPC-002, WPC-012.

## STRATEGIES — Strategies, trading modes and policy promotion

**Existing specification:** Operational adaptation and separately authorized policy evolution are well distinguished. Source: Part A §§2, 6, 9; Part B trading mode contracts.

**Positive journey:** Inspect strategy evidence, select an admitted mode, authorize an exact policy change and verify active consumer/version and current risk bounds.

**Failure and recovery:** Inconclusive edge, revoked mandate, changed candidate, active old-version parent, drift and rollback preserve existing protections and qualified fallback.

**Delivery owners:** BE-013, BE-036; FE-012. **Open findings:** WPC-007, WPC-001, WPC-002, WPC-016.

## LEARNING — Forecasting, models, self-improvement and economic experiments

**Existing specification:** Targets, temporal validation, calibration, chance controls, Jev/model budgets, independent evaluation and positive feedback proof are detailed. Source: Part A §§8–10; forecast contracts and research experiment register.

**Positive journey:** Seal a full opportunity cohort, diagnose outcomes with uncertainty, evaluate a candidate after full costs, qualify it, observe a changed later decision and reproduce that decision from retained evidence.

**Failure and recovery:** Contamination, future-data leakage, sparse cohorts, model alias change, interrupted budget settlement, corrected labels and drift yield explicit ineligible/inconclusive states and qualified fallback.

**Delivery owners:** BE-035, BE-036, VAN-ML-PKT-004, VAN-ML-PKT-005, VAN-ML-PKT-006, VAN-ML-PKT-007, VAN-ML-PKT-008, VAN-ML-PKT-009, VAN-ML-PKT-010, VAN-ML-PKT-011, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-015, VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-019, VAN-ML-PKT-020, VAN-ML-PKT-021, VAN-ML-PKT-022, VAN-ML-PKT-023, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-026, VAN-ML-PKT-027, VAN-ML-PKT-028, VAN-ML-PKT-029; FE-012, FE-014, FE-023. **Open findings:** WPC-007, WPC-008, WPC-012, WPC-016.

## NEWS — News, calendar, analyst, event impact and armed tickets

**Existing specification:** Citations, source contradictions, event timing and bounded D1–D7 influence are explicit. Source: Part B §8; news readiness amendment.

**Positive journey:** Read a sourced event analysis, inspect affected holdings, obtain a grounded analyst answer, and arm an eligible exact news ticket whose actual outcome is reconciled.

**Failure and recovery:** Duplicate/revised stories, bad timestamps, unavailable source, contradictory facts, late release and expired single-use ticket cannot create fabricated certainty or repeated trading.

**Delivery owners:** BE-014, BE-015, BE-016, BE-017, BE-021, BE-022; FE-013, FE-014. **Open findings:** WPC-008, WPC-001, WPC-002, WPC-007.

## PREDICTION — Prediction-market information, probability and research laboratories

**Existing specification:** Event identity, calibration, non-atomic arbitrage and market-making laboratories are retained as research scope. Source: Part B forecast/prediction integration; forecast contract files.

**Positive journey:** Capture a time-qualified event distribution and evaluate its incremental asset/research value, preserving settlement and fee assumptions in the report.

**Failure and recovery:** Void/disputed resolution, source disagreement, absent liquidity, stale quotes and non-atomic fills fail the appropriate research claim; no lab creates live order authority.

**Delivery owners:** VAN-ML-PKT-037, VAN-ML-PKT-038, VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-041, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046, VAN-ML-PKT-047, VAN-ML-PKT-048; FE-023. **Open findings:** WPC-008, WPC-007, WPC-001, WPC-016.

## CRYPTO_TRADE — Centralized-exchange spot crypto execution

**Existing specification:** Actual spot execution is distinct from read-only chain research and derivatives. Source: Part A §11; VAN-CRYPTO-001–014.

**Positive journey:** Use the admitted venue/account/instrument, satisfy size/precision filters, trade spot and reconcile asset inventory, protection and fees in their true currencies.

**Failure and recovery:** Book gap, rate limit, nonce/clock issue, stop support mismatch, fee asset shortage and dead-man cancellation preserve truthful exposure and recovery priority.

**Delivery owners:** BE-004, BE-005, BE-008, BE-009, BE-010, BE-012; FE-009, FE-010, FE-011. **Open findings:** WPC-008, WPC-007, WPC-012, WPC-016.

## CHAIN — Chain discovery, security, wallets and executable-economics research

**Existing specification:** Full cohorts, chain-specific identity, sellability uncertainty, finality and read-only boundaries are detailed. Source: Part B §30; high_value schemas and contracts.

**Positive journey:** Inspect a discovered asset, state-bound security analysis, independent buy/sell quotes, wallet attribution and matched-cohort economics with citations.

**Failure and recovery:** Reorganization, unsupported extension/proxy, unavailable sell path, incomplete holdings and censored exit remain explicit unknowns and invalidate dependent evidence.

**Delivery owners:** BE-037, BE-038, BE-039, BE-040, BE-041, BE-042, BE-043, BE-044; FE-014, FE-023. **Open findings:** WPC-008, WPC-007, WPC-001, WPC-016.

## WORK — Projects, tasks, missions, graphs, progress and approvals

**Existing specification:** Stable node/edge IDs, meaningful progress, accessible list and lease-aware actions are well described. Source: Part B §9; BE-023.

**Positive journey:** Create or update a permitted task, inspect its dependency graph, resolve a blocker, review evidence and observe authoritative verified completion.

**Failure and recovery:** Cycle, stale revision, concurrent edit, failed review, missing handoff and lost cancellation response never fabricate progress or dispatch twice; reconcile original task/job.

**Delivery owners:** BE-023; FE-015. **Open findings:** WPC-001, WPC-002, WPC-010, WPC-003.

## AGENTS — Agents, Hermes, Muse, Jev and provider-bound interventions

**Existing specification:** Native ownership, provider approvals and independent work/task/artifact outcomes are explicit. Source: Part B §9.6; BE-024; shared Jev clauses.

**Positive journey:** Observe a real assignment, steer the exact permitted job, answer its bound approval and inspect its native outcome/artifact.

**Failure and recovery:** Expired lease, late callback, worker replacement, provider outage and revoked capability retain native identities and enforce current scopes.

**Delivery owners:** BE-024; FE-016. **Open findings:** WPC-001, WPC-010, WPC-008, WPC-002.

## STUDIO — Development studio, design/research workspaces, CI and security

**Existing specification:** Evidence/workspace adapters and source-candidate admission are preserved, but largely specified at capability level. Source: BE-034; Part B §11.5 and studio contexts.

**Positive journey:** Open a real source/workspace artifact, inspect CI/security/design evidence, request an authorized native action and verify its exact build/source outcome.

**Failure and recovery:** Wrong branch/artifact, stale review, unavailable plugin and failed build remain distinct; a workspace control cannot imply deployment or mint authority.

**Delivery owners:** BE-034; FE-018. **Open findings:** WPC-001, WPC-010, WPC-008, WPC-002.

## VOICE — Conversation, speech input/output and speaker consent

**Existing specification:** Turns, transcript/audio streaming, interruption, history and consent exist as obligations; detailed turn/audio protocol remains to be materialized. Source: Part B §§10–11; BE-029; VNX-F-PRESENCE-03.

**Positive journey:** Speak a scoped request, inspect corrected interpretation, receive an intelligible spoken answer, follow up, interrupt playback and obtain a verified spoken effect result when applicable.

**Failure and recovery:** Ambiguous account/amount, ASR correction, TTS failure, Bluetooth/audio-focus change, phone call, interruption, timeout, reconnection and revoked mic consent preserve one turn/command and a usable text path.

**Delivery owners:** BE-029; FE-021. **Open findings:** WPC-005, WPC-003, WPC-001, WPC-014.

## FLOATING — Floating assistant, workboards, gestures and Android lifecycle

**Existing specification:** Tap/double-tap/long-press, drag/dock/minimize/restore, workboard and lifecycle preservation are explicit. Source: Part B §10.

**Positive journey:** Open and move the assistant without obstructing another app, switch to conversation/work/trades and restore the correct state after process recreation.

**Failure and recovery:** Overlay denial, locked screen, service restart restriction, keyboard collision, occlusion, battery saver and dismissed state use documented OS-compatible recovery without hidden mic capture.

**Delivery owners:** BE-029, BE-030, BE-031; FE-005. **Open findings:** WPC-006, WPC-005, WPC-015, WPC-002.

## MEMORY — Memory, knowledge, research, privacy, goals and adaptations

**Existing specification:** Fact provenance, corrections, retraction, erasure exceptions and adaptation review are represented. Source: Part B §11.3; BE-027.

**Positive journey:** Retrieve a cited fact, correct it, change a goal, review or roll back an adaptation and erase the specified retained scope with verified readback.

**Failure and recovery:** Conflicting facts, stale index, cross-project query, revoked source, derived cache and retained backup cannot silently revive erased material or equate deletion with model unlearning.

**Delivery owners:** BE-027; FE-019. **Open findings:** WPC-011, WPC-001, WPC-002, WPC-014.

## AUTOMATION — Automation, reminders, schedules and standing consent

**Existing specification:** Candidate/admitted versions, DST/misfire and unknown-effect reconciliation are required. Source: Part B §11.6; BE-028; VAN-CX-014.

**Positive journey:** Admit a scoped workflow, set a schedule/reminder, observe next/last run, pause or revoke it and inspect per-step durable outcomes.

**Failure and recovery:** DST transition, clock jump, overlapping run, missed schedule, consent expiry and timeout after effect use explicit policies and reconcile before retry.

**Delivery owners:** BE-028; FE-020. **Open findings:** WPC-003, WPC-010, WPC-001, WPC-002.

## REMOTE — Browser, remote devices, files, artifacts and share intake

**Existing specification:** Session leases, observed targets, file destinations and untrusted source content are explicit. Source: Part B §11.5; BE-025.

**Positive journey:** Open an admitted session, observe the target, execute an exact permitted interaction, import/export an allowed artifact and verify destination/outcome.

**Failure and recovery:** Navigation changes target, stale viewport, interrupted upload, malicious content, oversized file, revoked lease and unknown click outcome require bounded recovery and original-operation lookup.

**Delivery owners:** BE-025; FE-017. **Open findings:** WPC-010, WPC-014, WPC-001, WPC-002.

## ARTEMIS — ARTEMIS tests, devices, captures and evidence

**Existing specification:** Real device/build identity and pass/fail/unknown are clearly required. Source: BE-026; VNX-F-WORK-08; QA-004/005.

**Positive journey:** Choose an admitted device and exact APK, run/cancel a plan, inspect captures and independently resolve the test attempt outcome.

**Failure and recovery:** Device disconnect, missing capture, wrong APK, attempt restart and stale result remain unknown/failed rather than physical-device acceptance.

**Delivery owners:** BE-026; FE-018. **Open findings:** WPC-003, WPC-010, WPC-016.

## SETTINGS — Connected services, permissions, devices, diagnostics and preferences

**Existing specification:** Provider health versus authority, signed provisioning, notification/voice preferences and redaction are specified. Source: Part B §11.4; BE-031.

**Positive journey:** Inspect per-service readiness/scopes, change permitted preferences, revoke a device/consent and export scoped redacted diagnostics.

**Failure and recovery:** Healthy transport with unavailable action, pending Android permission, stale setting revision and expired enrollment remain distinct; recovery preserves privacy choices.

**Delivery owners:** BE-002, BE-031; FE-022. **Open findings:** WPC-004, WPC-008, WPC-009, WPC-014.

## MOBILE — Whole-app navigation, accessibility, themes and device performance

**Existing specification:** Both themes, 234 contexts, reduced motion, scale, process death and S24 checks are explicit. Source: Part B §§12, 15, 34.1; 21 October readability amendment.

**Positive journey:** Navigate every accepted context/action in both themes with large text/TalkBack, recover back-stack and pending references after process death, and keep critical controls readable.

**Failure and recovery:** Malformed/expired deep link, low memory, no network, slow render, theme switch and visual effect degradation preserve state and access to required controls.

**Delivery owners:** BE-030, BE-032; FE-001, FE-002, FE-003. **Open findings:** WPC-002, WPC-009, WPC-015, WPC-016.

## OPERATIONS — Security, data durability, deployment, migration, release and recovery

**Existing specification:** Exact source admission, signed intents, outbox/reconciliation, recovery and global backend gate are mandatory. Source: Part B §§13–14, 19, 22–23; BE-033.

**Positive journey:** Deploy a pinned release, migrate and restore state, connect the signed app, observe domain health, rotate credentials and verify a compatible rollback.

**Failure and recovery:** Crash after dispatch, backup/ledger inconsistency, revoked signing authority, schema incompatibility, resource exhaustion and restore of old consent must preserve financial truth and current revocations.

**Delivery owners:** BE-001, BE-002, BE-003, BE-032, BE-033; FE-001, FE-022. **Open findings:** WPC-001, WPC-004, WPC-012, WPC-013, WPC-014, WPC-016.
