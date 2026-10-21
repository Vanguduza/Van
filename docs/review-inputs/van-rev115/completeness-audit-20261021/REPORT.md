# VAN whole-product completeness review — 21 October 2026

**Verdict: the blueprint is broad enough to preserve the intended product, but is not yet a complete implementation contract or evidence of a release-ready app.** It is suitable for scoped engineering under its existing gates. The principal issue is uneven specificity: trading/research invariants are detailed, while many assistant, mobile and integration capabilities still depend on materializing service protocols, explicit acceptance oracles and provider bindings.

This is a whole-product review, covering all registered scope rather than only trading and voice. It identifies **16 open findings: eight P0 and eight P1**. These are contract, traceability or qualification findings, not 16 newly reproduced application bugs. P0 blocks the relevant gate/core outcome; P1 must close before affected-unit/final acceptance. Exact priority meanings and required closure evidence are in [FINDINGS.json](FINDINGS.json).

## Scope, provenance and limits

Audited repository: `Vanguduza/Van`, branch `review/van-rev115-20261018`, immutable source/package commit **`172d2143d3e6d2ec4b401376f5ef5a4cf94c7429`**. This includes Rev1.17 and the 21 October readability amendment. `STRUCTURAL_FINDINGS.json` records the inspected input hashes; the package manifest identifies the remaining archived inputs. The report concerns this pinned candidate, not an asserted latest deployment or all later branch changes.

Method: independently enumerate the primary registries and their links; inspect all named feature/service obligations and the active blueprint's domain/lifecycle contracts; compare intended journeys against operation, state, ownership and acceptance detail; review inherited evidence boundaries; check whole-product coverage and produce an actionable closure register. The audit validates cross-references but does not mistake a test ID or shared backend unit for full semantic proof.

Source implementation, installed binaries, current provider configuration, real service connectivity, runtime qualification, profitability and handset acceptance were **not reassessed** in this pass. Existing implementation may be present on other source/deployment heads; this report does not label it all unimplemented. No new application tests, model calls, trades, financial effects, messages to third parties or native acceptance ran. This audit is published alongside the sealed blueprint; it does not rewrite its planned test outcomes or issue certificates.

## Complete inventory

| Inventory | Reviewed count | Interpretation |
|---|---:|---|
| Named Rev2 features | 93 | Historical feature taxonomy, not the complete later capability total |
| Active requirements | 324 | Includes later execution, crypto, research, learning and model obligations |
| Screen/context obligations | 234 | Contexts include sheets, details and overlays; not 234 mandatory top-level screens |
| Legacy owner actions | 349 | Retained individual action obligations |
| Backend logical units | 82 | Ownership boundaries, not 82 required microservices |
| Development units | 131 | Includes 82 backend and 12 backend-verification units |
| Planned application test contracts | 1,610 | All NOT_RUN in this package |
| Original source atoms | 171 | Preserved source obligation inventory |
| Product Truth atoms | 22 | Includes later self-optimization/crypto/lean additions |
| External qualification rows | 82 | Requirement matrix, explicitly not current runtime proof |

The [full feature/screen/service index](FEATURE_SCREEN_SERVICE_INDEX.md) lists every one of the 93 features, 234 contexts and 82 backend units. [INVENTORY.json](INVENTORY.json) retains every requirement, source atom, Product Truth item, legacy action, test and unit for reverse review. A feature without a legacy feature ID is not omitted: later additions are covered through the requirements, service units, contexts and extensions.

Structural results:

- No duplicate IDs or unresolved references in the field sets inspected by `build_inventory.py`.
- All 82 backend units have corresponding external qualification rows and are covered by the 24 overlapping domain review families.
- **22 features lack their declared primary frontend unit in their directly linked feature-test owners.** Shared tests can be legitimate, but explicit delegation/shared exit evidence is needed.
- **349/349 legacy-action tests repeat the action title as their expectation.** This preserves inventory; it does not independently provide test setup or outcome assertions.
- **73/234 contexts have inline historical endpoint references**, representing **185 unique method/path pairs**. The other 161 can inherit shared contracts; neither count proves that current app endpoints exist, are missing or are qualified.
- **82/82 service catalogue rows use prose operation names**, with model names and obligations rather than complete bound operation objects. More detailed specialist schemas exist elsewhere. The required whole-product executable capability bundle remains BE-032's deliverable.

## Domain review

All twelve registry domain labels are included. The following 24 review families also cover shared infrastructure and later features that would be missed by auditing only the historical 93-feature list. Each family has a specific positive journey, adverse/recovery journey, existing specification evidence, owners and open findings in [DOMAIN_JOURNEYS.md](DOMAIN_JOURNEYS.md) and [DOMAIN_REVIEW.json](DOMAIN_REVIEW.json).

| Review family | Existing specification and remaining concern |
|---|---|
| Home, orb, Quick Hub, Attention and notifications | State reducer, severity precedence, compact hub, deep links and notification deduplication are detailed. Open: WPC-001, WPC-002, WPC-009, WPC-015. |
| Installation, zero-configuration connection and navigation | Signed provisioning and no raw host/token forms are explicit; identity/app-signing continuity is required. Open: WPC-004, WPC-001, WPC-013. |
| Markets, portfolio summaries, watchlists, screening and alerts | Instrument identity, freshness, watchlists and server-side alerts are included. Open: WPC-001, WPC-002, WPC-008, WPC-009. |
| Charts, indicators, drawings, replay, depth and workspaces | Professional chart scope and untrusted bridge boundaries are substantial; replay isolation is explicit. Open: WPC-001, WPC-002, WPC-008, WPC-015. |
| Manual orders, positions, protection, risk, handover, history and TCA | Financial invariants, unknown outcomes, child reservations and ownership transitions are deeply specified. Open: WPC-002, WPC-007, WPC-008, WPC-012, WPC-016. |
| Accounts, authentication, KYC, funds, payments and statements | Local unlink/remote closure, settled funding and provider-hosted flows are explicitly separated. Open: WPC-008, WPC-001, WPC-002, WPC-012. |
| Strategies, trading modes and policy promotion | Operational adaptation and separately authorized policy evolution are well distinguished. Open: WPC-007, WPC-001, WPC-002, WPC-016. |
| Forecasting, models, self-improvement and economic experiments | Targets, temporal validation, calibration, chance controls, Jev/model budgets, independent evaluation and positive feedback proof are detailed. Open: WPC-007, WPC-008, WPC-012, WPC-016. |
| News, calendar, analyst, event impact and armed tickets | Citations, source contradictions, event timing and bounded D1–D7 influence are explicit. Open: WPC-008, WPC-001, WPC-002, WPC-007. |
| Prediction-market information, probability and research laboratories | Event identity, calibration, non-atomic arbitrage and market-making laboratories are retained as research scope. Open: WPC-008, WPC-007, WPC-001, WPC-016. |
| Centralized-exchange spot crypto execution | Actual spot execution is distinct from read-only chain research and derivatives. Open: WPC-008, WPC-007, WPC-012, WPC-016. |
| Chain discovery, security, wallets and executable-economics research | Full cohorts, chain-specific identity, sellability uncertainty, finality and read-only boundaries are detailed. Open: WPC-008, WPC-007, WPC-001, WPC-016. |
| Projects, tasks, missions, graphs, progress and approvals | Stable node/edge IDs, meaningful progress, accessible list and lease-aware actions are well described. Open: WPC-001, WPC-002, WPC-010, WPC-003. |
| Agents, Hermes, Muse, Jev and provider-bound interventions | Native ownership, provider approvals and independent work/task/artifact outcomes are explicit. Open: WPC-001, WPC-010, WPC-008, WPC-002. |
| Development studio, design/research workspaces, CI and security | Evidence/workspace adapters and source-candidate admission are preserved, but largely specified at capability level. Open: WPC-001, WPC-010, WPC-008, WPC-002. |
| Conversation, speech input/output and speaker consent | Turns, transcript/audio streaming, interruption, history and consent exist as obligations; detailed turn/audio protocol remains to be materialized. Open: WPC-005, WPC-003, WPC-001, WPC-014. |
| Floating assistant, workboards, gestures and Android lifecycle | Tap/double-tap/long-press, drag/dock/minimize/restore, workboard and lifecycle preservation are explicit. Open: WPC-006, WPC-005, WPC-015, WPC-002. |
| Memory, knowledge, research, privacy, goals and adaptations | Fact provenance, corrections, retraction, erasure exceptions and adaptation review are represented. Open: WPC-011, WPC-001, WPC-002, WPC-014. |
| Automation, reminders, schedules and standing consent | Candidate/admitted versions, DST/misfire and unknown-effect reconciliation are required. Open: WPC-003, WPC-010, WPC-001, WPC-002. |
| Browser, remote devices, files, artifacts and share intake | Session leases, observed targets, file destinations and untrusted source content are explicit. Open: WPC-010, WPC-014, WPC-001, WPC-002. |
| ARTEMIS tests, devices, captures and evidence | Real device/build identity and pass/fail/unknown are clearly required. Open: WPC-003, WPC-010, WPC-016. |
| Connected services, permissions, devices, diagnostics and preferences | Provider health versus authority, signed provisioning, notification/voice preferences and redaction are specified. Open: WPC-004, WPC-008, WPC-009, WPC-014. |
| Whole-app navigation, accessibility, themes and device performance | Both themes, 234 contexts, reduced motion, scale, process death and S24 checks are explicit. Open: WPC-002, WPC-009, WPC-015, WPC-016. |
| Security, data durability, deployment, migration, release and recovery | Exact source admission, signed intents, outbox/reconciliation, recovery and global backend gate are mandatory. Open: WPC-001, WPC-004, WPC-012, WPC-013, WPC-014, WPC-016. |

These families encompass Home/Attention, Trading, Charts, Orders, Accounts/Funds, News/Intelligence, forecasting and prediction research, both crypto execution and read-only chain research, Work/Projects/Tasks, agents/Hermes/Muse/Jev, Studio/CI/security, conversation and voice, Floating VAN, Memory/Knowledge, Automation/Reminders, browser/remote/files/share, ARTEMIS, Connected/Permissions/Settings, native Android and operational infrastructure.

## Findings and required closure

### WPC-001 — P0: The complete executable consumer catalogue is still a deliverable

**Observed:** All 82 service rows express operations as prose strings. Only 73/234 contexts carry inline historical endpoint references (185 distinct method/path pairs). The remaining 161 are not evidence of missing routes: contracts can be inherited through shared services. However, an exact current action-to-operation/schema/error/readback/consumer binding cannot be inferred from the aggregate catalogue.

**Evidence:** `contracts/BACKEND_SERVICE_CATALOG.json: services[*].operations`; `contracts/BACKEND_TO_FRONTEND_CONSUMPTION_CONTRACT.md: Required per-capability contract`; `design/ALL_SURFACE_CONTRACTS.json: endpoints and required_backend_catalog_fields`.

**Required closure:** Publish one versioned native capability/action bundle with stable operation IDs; protocol/handler identity appropriate to each operation; input/output/error schemas; permissions; state transitions; idempotency; recovery lookup; exact source/consumer registration and evidence. Join every feature/context/action without inventing endpoints.

**Acceptance:** Each required action resolves to a real registered producer and client; success, refusal, unknown and recovery have independently observed postconditions. A missing binding blocks BG-001.

**Owners:** BE-032, BE-003, BQ-006. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

### WPC-002 — P0: Inventory preservation does not yet provide executable per-action acceptance

**Observed:** All 349 legacy-action tests have expectation equal to the action title. There are also 34 repetitions each of generic backend positive, restart, authority and producer/consumer expectations. Detailed domain requirements may supply semantics, but these entries do not independently state the full stimulus and observable result.

**Evidence:** `verification/TEST_CONTRACTS.json: T-LAC-001…349, T-SURFACE-*, T-BE-*`; `traceability/LEGACY_349_ACTIONS.json`.

**Required closure:** Expand existing test identities with exact preconditions, input, operation/context binding, oracle, failure reason and restart/retry postcondition. Retain every legacy action and existing test identity; reusable harnesses must enumerate every bound case.

**Acceptance:** Traceable results cover every required action and state family; altering the postcondition or pointing a test at a sibling action causes the relevant acceptance to fail.

**Owners:** BQ-006, UX-003, QA-001. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

### WPC-003 — P1: 22 feature tests omit their declared primary frontend owner

**Observed:** Example: VNX-F-PRESENCE-03 declares FE-021 but its direct test belongs only to FE-017. ARTEMIS declares FE-018/test FE-017; Automation declares FE-020/test FE-019. Some of the 22 may be intentional shared delivery; this is an unclosed ownership/delegation relationship, not proof of missing implementation.

**Evidence:** `traceability/REV2_93_FEATURE_CROSSWALK.json: primary_frontend_unit/test_ids`; `verification/TEST_CONTRACTS.json: unit/additional_units`; `STRUCTURAL_FINDINGS.json: feature_primary_test_owner_mismatches`.

**Required closure:** For each listed mismatch record accountable primary and supporting owners, add the primary to the applicable test binding or document and test explicit delegation. Align VNX-S-PRESENCE-05 (FE-005) with its voice feature owner and shared floating-shell responsibilities.

**Acceptance:** Every feature primary has a reviewed acceptance obligation in the generated plan or an explicit delegation with shared exit evidence; no feature is certified solely by an unrelated unit.

**Owners:** UX-003, BQ-006, QA-001. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

### WPC-004 — P0: Zero-configuration bootstrap needs an executable identity and recovery protocol

**Observed:** Signed provisioning, pairing/revocation and absence of manual host/token fields are specified. The whole-product acceptance set still needs a bound bootstrap/update/re-enrollment path with exact freshness, trust and failure semantics for the deployed Android identity and service route.

**Evidence:** `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_17_20261018.md: Part B §§11.4,12.1,14.4,19.3`; `contracts/BACKEND_SERVICE_CATALOG.json: BE-002/031`; `design/ALL_SURFACE_CONTRACTS.json: van.onboarding/van.provisioning/van.devices.provision`.

**Required closure:** Bind first-install delivery, trust root, envelope lifetime, owner/device enrollment, endpoint/certificate rotation, device replacement/revocation, clock error, offline start and reinstall/restore to typed outcomes and actual signed-build scenarios. Preserve one owner enrollment flow without manual backend settings.

**Acceptance:** A fresh S24 installation reaches the intended authorized services without host/port/token entry; expired/replayed provisioning refuses; rotation and recovery work without reviving a revoked device.

**Owners:** BE-002, BE-031, FE-001, FE-022, QA-002. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

### WPC-005 — P0: Conversation and spoken responses need a complete turn/audio contract

**Observed:** Voice is already included: streaming transcript/audio, interruption, history and speaker consent are explicit. The active entries do not supply a complete typed sequence for partial/final recognition, turn revision, command acceptance, audio playback, interruption and verified action completion, or a measurable conversation latency/quality budget.

**Evidence:** `contracts/BACKEND_SERVICE_CATALOG.json: BE-029`; `verification/TEST_CONTRACTS.json: T-BE-029-POS/NEG/REC, T-FEATURE-PRESENCE-03`; `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_17_20261018.md: Part B §§10–11`.

**Required closure:** Define session/turn/audio sequence identity, partial/final transcript and correction rules, intent ambiguity handling, TTS completion/cancellation, barge-in, text fallback, language/number pronunciation, provider failure, scoped context, redacted retention and measurable acceptance budgets. Decide supported activation modes explicitly; do not assume always-on wake word. Voice identity alone cannot replace effect authorization.

**Acceptance:** Positive conversations and action readback run through real speech providers; ambiguous amounts/accounts require resolution; late audio/recognition cannot restart a cancelled turn or duplicate a command; spoken done follows verified effect, not transcript receipt.

**Owners:** BE-029, BE-002, BE-003, FE-021, BQ-004. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

### WPC-006 — P1: Floating and voice lifecycle need a declared Android support matrix

**Observed:** OS permission/lifecycle preservation is required, but the release needs exact supported Android/One UI behaviour and evidence for background/locked screen, overlay, microphone, notification and audio-route restrictions. A generic persistent-assistant promise does not settle those platform cases.

**Evidence:** `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_17_20261018.md: Part B §10.4`; `contracts/BACKEND_TO_FRONTEND_CONSUMPTION_CONTRACT.md: Voice/device ownership`; `plan/DEVELOPMENT_PLAN.json: FE-005/021, QA-004`.

**Required closure:** Publish supported activation/foreground/background modes and fallbacks; test Bluetooth/headset changes, audio-focus loss/call, denied/revoked permission, foreground-service limits, reboot, battery saver, process death and owner dismissal on the supported S24 OS.

**Acceptance:** Each supported mode has actual OS readback; unsupported background behaviour is clearly surfaced with an accessible supported alternative and no silent recording.

**Owners:** FE-005, FE-021, FE-022, QA-004. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

### WPC-007 — P0: Strong trading specifications still need source repairs and economic proof

**Observed:** Prior pinned-source reviews/probes identify execution/TCA/slicing and model-qualification/blind-review/budget isolation work. This audit does not reassert those defects against newly deployed code. All six economic experiment templates remain NOT_RUN; a detailed learning specification is not demonstrated positive net contribution.

**Evidence:** `research/REV117_MODEL_AND_PROFITABILITY_REVIEW.md`; `evidence/rev117/source_probes.json`; `research/PROFITABILITY_EXPERIMENTS.json`; `review/INDEPENDENT_AUDIT.md`.

**Required closure:** Reconcile each source finding at the implementation head, qualify the evaluator first, run registered full-cohort/cost/risk experiments with protected confirmation, and retain inconclusive/negative results. Demonstrate both actual outcome-to-later-decision loops and rollback.

**Acceptance:** Exact source tests establish repairs, and independent evidence supports each promoted policy/model at its declared scope. No profitability label follows solely from model capability or winning trades.

**Owners:** BE-010, BE-012, BE-035, BE-036, BQ-007, BQ-009. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

### WPC-008 — P0: Provider capability and entitlement remain external dependencies

**Observed:** The matrix contains all 82 backend units but explicitly says PREDEVELOPMENT_MATRIX_NOT_RUNTIME_PROOF. Current provider support, permitted accounts, feeds, speech access, execution/funding rails and research licences are not established by these rows.

**Evidence:** `verification/RUNTIME_EXTERNAL_QUALIFICATION_MATRIX.json: status/capabilities`; `contracts/BACKEND_SERVICE_CATALOG.json: BE-004–008,014,024–029,034 and forecast providers`.

**Required closure:** For each required provider-operation pair bind actual account scope, entitlement, environment, source/API version, support/degradation states, rate/fee limits and qualified receipt. Select first execution/voice/data targets within existing authority; preserve all broader feature obligations or declare a separate approved scope amendment.

**Acceptance:** Required integrations have current permitted positive and refusal paths. Unsupported is a truthful state, not a way to count a required feature as complete; hosted fallback is tested where allowed.

**Owners:** BE-004, BE-005, BE-031, BE-032, BQ-002, BQ-004, BQ-006. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

### WPC-009 — P1: Notification and cross-surface state policy needs a complete delivery matrix

**Observed:** Canonical event identity, dedupe, quiet hours and critical-risk precedence exist. Their combinations across orb, Attention, Android notification, Floating VAN and spoken output still need explicit policy/acceptance rows, especially privacy while locked and denied OS delivery.

**Evidence:** `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_17_20261018.md: Part B §§5,11.7,13`; `contracts/BACKEND_SERVICE_CATALOG.json: BE-030/031`.

**Required closure:** Specify per-channel eligibility, criticality, lock-screen masking, quiet hours, acknowledgement/snooze distinction, expiry and delivery failure. Reconcile Android permission/DND constraints with reliable in-app critical state rather than promising to bypass the OS.

**Acceptance:** One event remains one incident across channels; revoked/expired actions cannot execute from old notifications; critical state remains visible even when OS delivery is blocked.

**Owners:** BE-030, BE-031, FE-004, FE-005, FE-021, FE-022. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

### WPC-010 — P1: Work, agents, browser, automation and studio require operation-level lifecycle tables

**Observed:** Native identities, leases, cancellation, truthful progress, provider approvals and artifact evidence are present as rules. Per-operation conflicts, timeout/unknown reconciliation, asynchronous callbacks and partial workflow compensation must still be bound to specific native APIs and tests.

**Evidence:** `contracts/BACKEND_SERVICE_CATALOG.json: BE-023–026,028,034`; `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_17_20261018.md: Part B §§9,11.5–11.6`.

**Required closure:** Provide transition tables for create/update/steer/pause/resume/cancel/retry and approvals, with expected revision, native operation/attempt identity, callback correlation, lease/fence, timeout and reconciliation. Explicitly define DST/misfire/overlap policy and safe file transfer retries.

**Acceptance:** Concurrent edits and late callbacks cannot overwrite newer state; unknown effects reconcile original operations; cancellation of a UI request never falsely reports native work cancelled.

**Owners:** BE-023, BE-024, BE-025, BE-026, BE-028, BE-034, BQ-004. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

### WPC-011 — P1: Privacy and erasure need a verifiable store-by-store lifecycle

**Observed:** Erasure, derivative caches, exceptions and distinction from model unlearning are explicit. The physical store/processor retention graph and deletion/restore evidence are not provided by the service catalogue.

**Evidence:** `contracts/BACKEND_SERVICE_CATALOG.json: BE-027/029`; `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_17_20261018.md: Part B §11.3`; `contracts/self_optimization/MODEL_USE_CONTRACT.json`.

**Required closure:** Map source, transcript/audio, embeddings/index, cached summaries, provider retention, artifacts, telemetry and backups to policy, owner and deletion/expiry receipts. Preserve necessary audit exceptions explicitly; prevent restored backups from reviving withdrawn context.

**Acceptance:** A scoped erasure is traceable through each applicable store/processor and re-index/restore path; inaccessible or retained exceptions remain disclosed rather than reported as deleted.

**Owners:** BE-027, BE-029, BE-033, BQ-005. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

### WPC-012 — P1: Recovery and capacity obligations need measurable operational budgets

**Observed:** There are candidate navigation/chart targets and qualitative recovery/capacity requirements. End-to-end availability, voice latency, event freshness, restore RPO/RTO, queue/disk limits and research-versus-protection saturation require deployed-topology budgets and failure thresholds.

**Evidence:** `contracts/BACKEND_SERVICE_CATALOG.json: BE-033`; `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_17_20261018.md: Part B §15.1`; `verification/RUNTIME_EXTERNAL_QUALIFICATION_MATRIX.json`.

**Required closure:** Set workload-specific budgets and measurement protocols before qualification; define overload/backpressure, alert ownership, retention, restore procedure, maintenance behaviour and acceptable data loss per domain. Preserve urgent financial reconciliation independently of research load.

**Acceptance:** Representative load, dependency outage and restore drills meet the declared budgets or visibly degrade within policy; success is not inferred from an open port or healthy process.

**Owners:** BE-003, BE-029, BE-033, BQ-005, QA-004. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

### WPC-013 — P0: Signed app identity, upgrade and rollback need exact-build evidence

**Observed:** The blueprint preserves com.dial.van, signing/pairing continuity and compatible rollback. These requirements remain unverified for the eventual rebuilt app and current backend/store versions.

**Evidence:** `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_17_20261018.md: Part B §§12.1,19.3`; `plan/DEVELOPMENT_PLAN.json: QA-002/005 and release/retirement units`.

**Required closure:** Bind signing identity, APK digest, provisioning schema, backend version compatibility, migrations, OS permissions, encrypted stores and app links to install/upgrade/rollback tests. Test rollback against newer financial data and revocations; retirement follows full parity acceptance.

**Acceptance:** The actual signed release installs/upgrades without orphaning owner/device state; incompatible versions refuse safely; rollback never restores obsolete authority or loses financial truth.

**Owners:** BE-002, BE-033, FE-001, QA-002, QA-005. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

### WPC-014 — P1: Cross-domain security needs an explicit adversarial surface matrix

**Observed:** Scope, signed intents, untrusted chart/browser content, privacy and model prompt-injection boundaries are specified. Each ingress/egress and consequential command still needs exact attack fixtures and source-bound enforcement evidence.

**Evidence:** `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_17_20261018.md: Part B §§14,18`; `contracts/BACKEND_SERVICE_CATALOG.json: BE-002/025/027/029`; `plan/DEVELOPMENT_PLAN.json: BQ-005,QA-003`.

**Required closure:** Cover forged/replayed intents, changed confirmation arguments, cross-account/project queries, malicious shares/documents/web content, transcript ambiguity, token leakage in logs/captures, expired sessions and restored revocations. Bind denial to the actual domain owner.

**Acceptance:** Negative tests fail at authoritative boundaries and leave correct receipts/state; display checks or sanitized screenshots alone cannot certify authorization.

**Owners:** BE-002, BE-025, BE-027, BE-029, BQ-005, QA-003. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

### WPC-015 — P1: Readability, navigation and performance remain rendered-device obligations

**Observed:** All 234 contexts inherit readability requirements, and 80 opaque colour pairs passed static arithmetic. There is no resulting proof of gradients/compositing, actual glyphs, TalkBack, large text, sunlight, battery/thermal or process-death behaviour.

**Evidence:** `design/DARK_THEME_READABILITY_AMENDMENT_20261021.md`; `evidence/rev117/theme_readability_20261021.json`; `design/ALL_SURFACE_CONTRACTS.json`; `plan/DEVELOPMENT_PLAN.json: QA-004`.

**Required closure:** Create exact-build component/state goldens and complete context/action acceptance, including both themes, 200% font scaling, focus, reduced motion, landscape/split screen, low brightness/sunlight and pending-action recovery.

**Acceptance:** Actual S24 receipts and accessibility/performance evidence certify the declared context/state matrix; visual degradation preserves essential controls and financial values.

**Owners:** UX-002, UX-003, FE-002, QA-004. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

### WPC-016 — P0: No document result currently establishes full implementation or release acceptance

**Observed:** All 1,610 application contracts are NOT_RUN. Native source admission/F15, BG and final owner/device acceptance are separate from successful document verification. Source implementation may exist elsewhere; this audit has not requalified it.

**Evidence:** `verification/TEST_CONTRACTS.json: all execution_state values`; `verification/F15_CERTIFICATE.json`; `verification/BACKEND_COMPLETE_CERTIFICATE.json`; `plan/DEVELOPMENT_PLAN.json: global gates`.

**Required closure:** Keep an exact-source acceptance ledger across every feature/action/requirement/provider; reconcile source fixes first, qualify all backend capabilities before frontend gate, then run complete signed-app and S24 acceptance. Representative journeys discover risks but cannot certify untested siblings.

**Acceptance:** Current source/config/provider/build receipts support every applicable obligation and required independent/native gate. No counter, schema checker, simulator or emulator is relabelled as complete product/device evidence.

**Owners:** BQ-006, BG-001, QA-001, QA-002, QA-003, QA-004, QA-005. **Status:** OPEN_AT_AUDITED_BLUEPRINT.

## Required per-feature completion record

A completed feature must have a record tying its stable feature/requirement/context/action IDs to:

1. The owner goal, permitted actors, source of truth and exact producer/consumer.
2. A versioned operation or local interaction contract with input/output/error types and display semantics. Local-only navigation need not acquire a fictitious HTTP endpoint.
3. Success postconditions and independent readback; a request acknowledged, job accepted, command applied and effect verified are different outcomes.
4. Applicable loading/empty/offline/stale/denied/error/partial/unknown/cancel/recovery states, including whether controls remain usable.
5. Scope, consent, expiry, revision/concurrency and idempotency/reconciliation rules for effects; explicit non-applicability for read-only operations.
6. State persistence, retention/privacy, process death, reconnect, upgrade and revocation behaviour.
7. Real provider support, source/configuration/build identities, operational budgets and supported Android modes.
8. Existing acceptance IDs expanded with actual inputs, oracles and receipts, accountable unit and independent verification. Reusable fixtures may reduce implementation work, but do not eliminate the per-feature/state coverage obligation.
9. Owner-facing screen and, where supported, voice behaviour; meaningful accessible alternatives and honest spoken/visual status.
10. Separate statuses for source implementation, tests, integration, deployment, live connection, qualification and owner/device acceptance. A single green status cannot stand in for all ten.

## Recommended closure sequence within the existing plan

1. **Reconcile ownership and acceptance definitions.** Resolve the 22 feature/test-primary mismatches, preserve the existing graph, and turn generic action labels into specific oracles. Confirm current source admission against the pinned candidates before applying existing source-fix requirements.
2. **Materialize the whole backend contract bundle.** Each domain owns its exact operations and recovery tables; BE-032 aggregates them. Complete device/bootstrap, voice, workflow, privacy and data-lifecycle contracts alongside trading and research. Bind providers and budgets rather than inventing routes or capacities.
3. **Qualify all backend families headlessly.** Exercise real allowed dependencies, permissions, concurrent changes, unknown effects, fault injection and restart. Include every required operation; do not use a few demonstrations to waive siblings. The existing 12 backend-verification units and sole BG-001 remain the gates.
4. **Implement the complete native experience after BG-001.** Use the existing 234-context registry, paired design authority, typed consumer contracts and all 23 frontend units. Voice, floating lifecycle, settings/provisioning and accessible alternatives have explicit owners alongside trading surfaces.
5. **Run signed-app, S24 and release acceptance.** Validate complete feature/action parity, OS modes, speech/audio routes, real service connections, both themes, lifecycle, security, resource budgets, upgrade and compatible rollback. ARTEMIS evidence binds actual device, APK and test attempt.
6. **Qualify economic claims separately.** Repair/qualify the evaluator, complete registered research experiments, observe later decision changes and assess costs/risk/uncertainty prospectively within separately authorized trading bounds. Engineering completeness does not establish profitability.

The work is already represented in the existing scope and unit ownership. Most findings require making existing obligations concrete and proving them, rather than adding more product features or another service layer. If an operation cannot be supported by an admitted provider, record the exact dependency and retain the requirement until a legitimate implementation or explicit scope decision resolves it.

## Audit verification and reproduction

Run `python3 -B build_inventory.py` from this directory to regenerate the machine inventory and index against the adjacent package. Run `python3 -B verify_audit.py` to validate all audit references, complete backend/domain coverage, preserved baseline input hashes, finding ownership and negative controls. The checker validates the audit's structure and arithmetic; it does not independently certify the prose judgments or product implementation. `AUDIT_CHECKS.json` records commands and documentary results.

The audited package ZIP and its receipt remain the 21 October readability delivery. This report is a separate review artifact, so the package's NOT_RUN application states and unsigned/native gate boundaries remain accurate. Later fixes should reference these findings and record exact implementation and acceptance evidence before closing them.
