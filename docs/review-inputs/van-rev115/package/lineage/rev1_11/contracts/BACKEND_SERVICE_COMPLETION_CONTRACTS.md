# Complete backend service obligations — canonical Rev 1.11

**74 logical backend units.** They are ownership/qualification boundaries, not a demand for 74 separately deployed microservices. Reuse admitted existing VAN implementations. Every unit is fully implemented and integrated before BG-001.

## BE-001 — Source consolidation and preservation oracle
**Prerequisites:** PRE-003
**Authority:** VAN source owners plus independent Zuul admission
**Models:** source revisions, adoption ledger, legacy action and endpoint identities

**Complete operations:**
- admit exact feature-bearing diffs
- retain old app unchanged
- register every provider caller
- construct and falsify parity oracle

**Adversarial exit:** Remove a PR-only action: parity fails; unreviewed duplicate implementation cannot merge
**Corrections:** VAN-CX-002

## BE-002 — Device identity, bounded authority and intent fencing
**Prerequisites:** BE-001, PRE-003
**Authority:** VAN gateway security and existing device authority
**Models:** OwnerPrincipal, DeviceBinding, CanonicalIntent, Grant, RevocationEpoch

**Complete operations:**
- pair/provision/revoke
- validate signed exact intents
- issue challenges
- expire and fence sessions
- protect account and task scopes

**Adversarial exit:** Replayed nonce, cross-device signature, stale mandate or changed arguments refuse before effect
**Corrections:** VAN-CX-009, VAN-CX-015

## BE-003 — Durable event, readback and projection infrastructure
**Prerequisites:** BE-002, PRE-003
**Authority:** Owning domain ledger and gateway projections
**Models:** EventEnvelope, IntentId, SourceRevision, ProjectionSnapshot, EffectReceipt

**Complete operations:**
- append events
- deduplicate
- process outbox
- serve cursor snapshots
- reconcile uncertain outcomes
- redact evidence

**Adversarial exit:** Crash after external submission, duplicate delivery, source-epoch change and out-of-order readback never duplicate an effect
**Corrections:** VAN-CX-006, VAN-CX-008

## BE-004 — Accounts, broker directory and operation capabilities
**Prerequisites:** BE-002, BE-003, PRE-003
**Authority:** Broker owns identity; VAN owns link/configuration
**Models:** BrokerIdentity, AccountLink, ProviderCapability, AccountClosureIntent, KYC status reference

**Complete operations:**
- discover
- create demo
- request live application
- link
- edit local/profile where entitled
- restrict
- unlink
- request remote closure

**Adversarial exit:** Local unlink never reports remote closure; active exposure, unknown funds or stale readback blocks deletion
**Corrections:** VAN-CX-016

## BE-005 — Broker authentication, credential rotation and health
**Prerequisites:** BE-004, PRE-003
**Authority:** Broker auth service and protected VAN secret store
**Models:** CredentialRef, OAuthAttempt, SessionEpoch, BrokerHealth, AccountEntitlement

**Complete operations:**
- OAuth start/callback/cancel/recover
- discover accounts
- rotate and verify secrets
- renew
- detect migration
- QR bridge pairing

**Adversarial exit:** Process death, callback collision, expired token, investor read-only credential and failed swap remain fail closed
**Corrections:** VAN-CX-016

## BE-006 — Exact funding ledger and flow-adjusted accounting
**Prerequisites:** BE-003, BE-004, PRE-003
**Authority:** Provider cash history plus deterministic VATI accounting
**Models:** Money, Quantity, Posting, FinancialMovement, ValuationSnapshot, FlowAdjustedRisk

**Complete operations:**
- ingest provider cash movements
- classify and reconcile
- post reversals
- calculate flow-adjusted returns/drawdown
- expose statement lineage

**Adversarial exit:** Withdrawals are not losses; deposits do not erase losses; unknown or non-withdrawable credit is not risk capital
**Corrections:** VAN-CX-009, VAN-CX-016

## BE-007 — Deposits, withdrawals, transfers and provider rails
**Prerequisites:** BE-005, BE-006, PRE-003
**Authority:** Payment provider/custodian and broker; VAN orchestrates
**Models:** PaymentIntent, PaymentQuote, BeneficiaryRef, Reservation, SettlementReceipt

**Complete operations:**
- quote
- verify beneficiary
- approve
- reserve
- submit
- reconcile
- settle
- compensate
- expose hosted handoff with verified origin

**Adversarial exit:** Changed fees need new approval; redirect is not settlement; unknown send never blindly retries; simultaneous withdrawal/order reservations cannot overdraw margin
**Corrections:** VAN-CX-016

## BE-008 — Instrument identity, market feeds, bars and depth
**Prerequisites:** BE-003, BE-005, PRE-003
**Authority:** Licensed/provider market feed adapter
**Models:** InstrumentId, VenueSymbol, TickRule, Bar, Quote, DepthBook, FeedQuality

**Complete operations:**
- resolve aliases
- discover tradable instruments
- subscribe once
- aggregate bars
- revision snapshots
- recover gaps
- publish genuine depth

**Adversarial exit:** Identical ticker with different contracts cannot collide; stale feed never returns synthetic LIVE; bad sequence triggers snapshot recovery
**Corrections:** VAN-CX-004, VAN-CX-007, VAN-CX-012

## BE-009 — Mandates, risk, sizing and portfolio reservations
**Prerequisites:** BE-002, BE-006, BE-008, PRE-003
**Authority:** VATI Risk Authority only
**Models:** MandateDigest, RiskBudget, RiskSnapshot, RiskReservation, StopPolicy

**Complete operations:**
- verify mandate
- calculate stop/size
- reserve worst-case pending risk
- enforce drawdown, concentration, correlation and margin
- deny new entries while allow risk reduction

**Adversarial exit:** No float monetary sizing; rounding down; competing intents cannot exceed family/account limits; flow adjustment cannot increase absolute available collateral
**Corrections:** VAN-CX-007, VAN-CX-008, VAN-CX-009, VAN-CX-016

## BE-010 — Venue execution, canonical orders and reconciliation
**Prerequisites:** BE-005, BE-008, BE-009, PRE-003
**Authority:** VATI router and admitted broker adapters
**Models:** TradeIntent, OrderCommand, PLACED/PARTIAL/FILLED lifecycle, BrokerOrderId, ProtectionState

**Complete operations:**
- submit market/limit/stop/stop-limit where available
- modify
- cancel
- read fills
- map provider states
- reconcile unknowns

**Adversarial exit:** Cancel/fill race keeps broker truth; partial fill retains exposure; atomic request includes stop but protection requires independent readback
**Corrections:** VAN-CX-003, VAN-CX-004, VAN-CX-005, VAN-CX-006, VAN-CX-007

## BE-011 — Manual trading, adds and management handover
**Prerequisites:** BE-009, BE-010, PRE-003
**Authority:** Owner intent through unchanged VATI risk/router
**Models:** ManualPreview, PositionFamily, ScalePolicy, ManagementLease, OwnerOverride

**Complete operations:**
- preview/submit manual entry
- winning-only add
- close/partial
- tighten
- TP changes
- hand to VAN
- take back with management epoch

**Adversarial exit:** Winning at approval AND submission; never widen stop; take-back fences future commands and reconciles already-sent commands instead of claiming instant cancellation
**Corrections:** VAN-CX-009

## BE-012 — Positions, protection, portfolio, history and TCA
**Prerequisites:** BE-006, BE-010, BE-011, PRE-003
**Authority:** VATI protection/lifecycle plus broker readback
**Models:** PositionProjection, ProtectionReceipt, ExecutionQuality, AccountPortfolio, Statement

**Complete operations:**
- serve canonical positions
- protect
- build history/statement projections
- compute sourced execution cost
- report risk current/limit/remaining

**Adversarial exit:** Unconfirmed stop never shown protected; every TCA value has units and benchmark timestamp; demo/live totals never mix
**Corrections:** VAN-CX-003, VAN-CX-006

## BE-013 — Strategies, trading modes and independent edge evidence
**Prerequisites:** BE-009, BE-010, BE-035, PRE-003
**Authority:** Signed mandate plus VATI strategy qualification
**Models:** StrategyVersion, TemperamentMandate, EdgeEvidence, PromotionRecord

**Complete operations:**
- list/inspect/promote qualified strategies
- produce edge admission evidence
- apply Normal/Risky/Aggressive requests
- reconcile restart
- attribution

**Adversarial exit:** Aggressive without admitted edge refuses; mode never raises signed ceilings; both evidence producer and refusal path must be implemented
**Corrections:** VAN-CX-009, VAN-CX-014, VAN-CX-018

## BE-014 — News, calendar and source-health ingestion
**Prerequisites:** BE-003, BE-008, PRE-003
**Authority:** News/Calendar adapters and immutable event ledger
**Models:** SourceLicense, CalendarVintage, StoryCluster, SourceHealth

**Complete operations:**
- admit feeds
- collect scheduled values and headlines
- canonicalize identities
- track original publisher, entitlements, clocks and source failures

**Adversarial exit:** Syndicated copies count once; preliminary/forecast/revised previous is not actual; unsupported licence or failed feed does not fake coverage
**Corrections:** VAN-CX-005

## BE-015 — Event analysis, history, analogues and expectations
**Prerequisites:** BE-014, PRE-003
**Authority:** Deterministic event research; bounded model proposes labels only
**Models:** EventEpisode, HistoryProfile, Novelty, AnalogueSet, ExpectationVintage

**Complete operations:**
- cluster/correct/retract
- classify
- measure reactions
- build history
- retrieve analogues
- join prediction-market expectations only when admitted

**Adversarial exit:** No look-ahead; missing market marks stay missing; thin sample cannot become calibrated probability; source corrections invalidate descendants
**Corrections:** all canonical source/proof/authority invariants

## BE-016 — Governed news effects D1–D7 and news strategy lifecycle
**Prerequisites:** BE-009, BE-012, BE-013, BE-015, PRE-003
**Authority:** VATI event/risk/lifecycle authority, not LLM
**Models:** NewsEffect, EventStrategy, PathPromotion, ShadowComparison

**Complete operations:**
- compute shadow decisions
- reduce size/timing/rank
- preserve VAN-managed positions
- validate event strategies
- admit per-path promotions

**Adversarial exit:** D1–D6 cannot increase risk; owner-managed trades get proposals not silent exits; D7 requires strategy evidence; news corrections retract pending eligibility
**Corrections:** VAN-CX-005

## BE-017 — Armed news tickets, readiness and single-use execution
**Prerequisites:** BE-002, BE-010, BE-016, PRE-003
**Authority:** Device-signed bounded grant and VATI
**Models:** NewsArmedTicketGrant, ArmingReadiness, EventInstance, PolicyDigest, ConsumedNonce

**Complete operations:**
- prepare/sign/arm/revalidate/disarm/use
- persist nonce
- record latency
- enforce two-source agreement at execution
- reconcile submission

**Adversarial exit:** SIGNED is not readiness; expired/changed policy/account/health disarms; a future release can be armed before actual values arrive, but use cannot precede required agreement
**Corrections:** VAN-CX-015

## BE-018 — Chart data contracts, indicators, drawings and workspaces
**Prerequisites:** BE-003, BE-008, PRE-003
**Authority:** Chart domain persistence; VATI owns certified indicators
**Models:** ChartCapability, IndicatorInstance, DrawingRecord, WorkspaceRevision

**Complete operations:**
- serve chart capability contract
- persist indicator instances/drawing anchors/layouts
- revise settings
- calculate certified server indicators
- sync conflicts

**Adversarial exit:** No rendered pixels as canonical geometry; parameter versions and price/time anchors round-trip; cross-device edit conflict explicit; no server dependency on a new renderer
**Corrections:** all canonical source/proof/authority invariants

## BE-019 — Historical replay, simulation and isolated practice data
**Prerequisites:** BE-008, BE-018, PRE-003
**Authority:** Isolated replay namespace with no live order capability
**Models:** ReplaySession, DataVintage, SimulationAction, PracticeOutcome

**Complete operations:**
- create deterministic replay sessions
- step/seek
- store paper actions separately
- return outcomes and provenance

**Adversarial exit:** Replay cannot resolve an execution route or grant; future bars invisible; reset/seek reproducible; practice never enters live P&L or strategy promotion statistics
**Corrections:** VAN-CX-004, VAN-CX-005, VAN-CX-010, VAN-CX-012

## BE-020 — Watchlists, persistent alerts and typed screening
**Prerequisites:** BE-003, BE-008, BE-014, BE-018, PRE-003
**Authority:** Persistent market/alert services
**Models:** Watchlist, ScreenerQuery, AlertRule, AlertEventId

**Complete operations:**
- CRUD lists
- evaluate price/indicator/drawing/news alerts on server
- pause/restart/delete
- scan instruments
- emit canonical notifications

**Adversarial exit:** One trigger identity across devices/restart; stale data cannot trigger a live market fact; alert never trades; scan quotas enforced
**Corrections:** all canonical source/proof/authority invariants

## BE-021 — Analyst, chart observations and cross-signal intelligence
**Prerequisites:** BE-012, BE-015, BE-018, BE-019, PRE-003
**Authority:** VAN/JEV/research read lane; no execution grant
**Models:** ChartObservation, ResearchObservation, CrossSignalPacket, AnalystFacts

**Complete operations:**
- ingest consented chart observations and notes
- join news/portfolio
- generate fact-bound explanations
- track contradiction
- provide evidence artifacts

**Adversarial exit:** Chart payload injection and model-added numbers rejected; retention/erasure honoured; all contributing revisions recorded; headless producer proves intake before UI exists
**Corrections:** VAN-CX-018

## BE-022 — Owner diagnostics, pattern discovery and learning review
**Prerequisites:** BE-011, BE-013, BE-019, BE-021, PRE-003
**Authority:** Research/learning pipeline separate from existing strategy training
**Models:** ManualTradeDataset, BehaviourFinding, PatternCandidate, ValidationReport

**Complete operations:**
- analyse all manual trades
- display soft behaviour findings
- extract entry-time features
- validate new candidates
- track counterfactuals

**Adversarial exit:** Post-entry holding duration is outcome metadata, not an entry feature; losing trades retained; insufficient sample no assertion; candidate never automatically promoted
**Corrections:** VAN-CX-014

## BE-023 — Projects, tasks, missions and truthful workflow graphs
**Prerequisites:** BE-002, BE-003, PRE-003
**Authority:** DIAL/Work Tracker/mission owners via typed adapters
**Models:** ProjectFlowSnapshot, TaskRecord, StageExit, GraphRevision, MissionIntent

**Complete operations:**
- create/read/update permitted tasks
- stream mission progress
- join stage evidence
- compute dependency graph/critical path
- expose stable node/edge IDs

**Adversarial exit:** Cycles/orphans/conflicting actors visible; no completion from agent RUNNING; graph drag has no authority; observed task state not fabricated by layout
**Corrections:** all canonical source/proof/authority invariants

## BE-024 — Agents, Hermes, Muse and provider-bound interventions
**Prerequisites:** BE-002, BE-003, BE-023, PRE-003
**Authority:** Qualified external worker/provider owns action; VAN projects it
**Models:** AgentAssignment, HandoffEvent, ProviderApproval, WorkspaceLease, JobReceipt

**Complete operations:**
- assign/steer/cancel under lease
- native conversation protocol
- provider-bound allow/deny
- reconcile job/task/artifact outcomes

**Adversarial exit:** Expired lease, duplicate allow, late callback and task scope mismatch refuse; GUI click is not success; integration must be real, not an unbound client stub
**Corrections:** all canonical source/proof/authority invariants

## BE-025 — Browser, remote interaction, artifact and share intake
**Prerequisites:** BE-002, BE-003, BE-024, PRE-003
**Authority:** Browser/device provider with exact owner scope
**Models:** BrowserSession, EffectPlan, ObservedTarget, ArtifactAdmission, ShareContext

**Complete operations:**
- lease session
- observe viewport
- submit exact plan
- upload/download with admission
- report action outcome
- revoke
- bind file destination

**Adversarial exit:** No broad host command from UI; before/after target changes invalidate intent; file destination substitution denied; retained source content is untrusted data
**Corrections:** all canonical source/proof/authority invariants

## BE-026 — ARTEMIS device tests and independent evidence services
**Prerequisites:** BE-002, BE-003, BE-023, BE-025, PRE-003
**Authority:** ARTEMIS and independent verification producer
**Models:** DeviceReadiness, TestPlan, TestAttempt, CaptureRef, VerificationReceipt

**Complete operations:**
- enumerate qualified devices
- version plans
- queue/observe/cancel tests
- preserve captures
- publish pass/fail/unknown and build IDs

**Adversarial exit:** An emulator cannot issue S24 acceptance; missing capture means unknown; old APK test cannot certify new build; server protocol testable with existing authorised clients
**Corrections:** all canonical source/proof/authority invariants

## BE-027 — Memory, knowledge, goals, privacy and erasure
**Prerequisites:** BE-002, BE-003, PRE-003
**Authority:** Memory/knowledge source owners and privacy policy
**Models:** MemoryRecord, SourceCitation, GoalVersion, Consent, ErasureReceipt

**Complete operations:**
- search/correct/retract facts
- retain provenance
- inspect history
- edit goals
- review/rollback adaptation
- erase scoped records and derivatives

**Adversarial exit:** Deleting source is not model unlearning; revoked context excluded from research; erasure includes caches/derived artifacts or declares verified retention exception
**Corrections:** all canonical source/proof/authority invariants

## BE-028 — Automation, reminders and schedules
**Prerequisites:** BE-002, BE-003, BE-023, BE-027, PRE-003
**Authority:** Automation scheduler plus owning effect services
**Models:** AutomationVersion, Schedule, RunAttempt, StandingConsent, OutcomeReceipt

**Complete operations:**
- candidate/admit/version workflows
- bind standing authority
- schedule
- report next/last run
- execute through domain adapters
- retry safely

**Adversarial exit:** Failed run never silently success; timezone/DST/misfire specified; schedules never mint grants; unknown effect reconciled before retry
**Corrections:** VAN-CX-014

## BE-029 — Conversation, voice and speaker-profile services
**Prerequisites:** BE-002, BE-003, BE-027, PRE-003
**Authority:** Voice/conversation pipeline with OS/device consent boundary
**Models:** ConversationTurn, VoiceSession, SpeakerProfileRef, ConsentEpoch

**Complete operations:**
- create turns
- stream transcript/audio
- interrupt
- retain history
- manage speaker consent/erase
- expose speech and task context

**Adversarial exit:** Mic permission denial propagates; interrupted response not completion; no speaker identity assertion without enrollment; obsolete consent cannot reopen microphone
**Corrections:** all canonical source/proof/authority invariants

## BE-030 — Attention, notifications, presence and compact summaries
**Prerequisites:** BE-003, BE-012, BE-020, BE-023, BE-024, BE-028, BE-029, PRE-003
**Authority:** Shared owner projection from authoritative sources
**Models:** OrbInputs, OrbProjection, AttentionItem, NotificationPolicy, SmartBrief

**Complete operations:**
- aggregate typed events
- arbitrate severity/freshness
- dedupe delivery
- persist acknowledgement
- project orb semantics and compact hub summaries

**Adversarial exit:** Risk preempts celebration; snooze never clears incident; no state legend or route action executes; stale health never healthy idle; one event per channel identity
**Corrections:** all canonical source/proof/authority invariants

## BE-031 — Connected providers, settings, devices and diagnostics
**Prerequisites:** BE-002, BE-003, BE-005, BE-024, BE-025, BE-029, PRE-003
**Authority:** VAN settings/device service plus qualified providers
**Models:** ProviderReadiness, SettingVersion, DeviceScope, DiagnosticSnapshot

**Complete operations:**
- serve provider readiness and scopes
- version settings
- manage device inventory/provisioning
- expose connection correlations
- privacy defaults

**Adversarial exit:** Connection health is not action authority; no manual raw host/token forms; no leaked secrets in telemetry; native permission completion deferred to actual OS readback
**Corrections:** all canonical source/proof/authority invariants

## BE-032 — Whole-product capability, action and UI-consumption catalog
**Prerequisites:** BE-004, BE-007, BE-012, BE-013, BE-017, BE-018, BE-019, BE-020, BE-021, BE-022, BE-023, BE-024, BE-025, BE-026, BE-027, BE-028, BE-029, BE-030, BE-031, BE-034, BE-036, PRE-003, VAN-ML-PKT-028, VAN-ML-PKT-048
**Authority:** Each domain owns facts; catalog aggregates without gaining authority
**Models:** CapabilityCatalog, ActionContract, ScreenDataContract, CompatibilityVersion

**Complete operations:**
- publish complete versioned capability inventory
- bind every action to input/state/error/authority/readback
- expose display projections and navigable subjects

**Adversarial exit:** No required feature missing or hidden by unsupported label; every read/write contract has a genuine caller harness and known error set; catalog cannot send arbitrary frontend code
**Corrections:** VAN-CX-006, VAN-CX-017, VAN-CX-018

## BE-033 — Backend deployment, recovery, capacity and observability
**Prerequisites:** BE-032, PRE-003
**Authority:** DIAL/Zuul qualified deployment and service operators
**Models:** BackendRelease, MigrationReceipt, BackupManifest, SLOReport, RecoveryPlan

**Complete operations:**
- build reproducible service artifacts
- configure staging
- restore backups
- migrate schema
- prove rollback
- quotas
- bounded queues
- alert health

**Adversarial exit:** No production credentials in preparation; restart does not replay effects; resource pressure backpressure not data loss; rollback retains newer financial ledger safely
**Corrections:** VAN-CX-008

## BE-034 — Development studio, CI/security and evidence-workspace adapters
**Prerequisites:** BE-023, BE-024, BE-025, BE-026, PRE-003
**Authority:** DDS/qualified studio and control providers remain independent owners
**Models:** WorkspaceProjection, DesignArtifactRef, CIReceipt, SecurityReview, NativeControlIntent

**Complete operations:**
- project/read stage plans
- expose design/research/security/CI evidence
- admit cinematic/studio workspace candidate APIs and native-control bindings

**Adversarial exit:** PR98/99 and later candidates are evaluated, not assumed; UI workspace cannot mint build/deploy authority; external partial services block required backend integration
**Corrections:** all canonical source/proof/authority invariants

## BE-035 — Qualified chronological strategy evaluator and simulator oracle
**Prerequisites:** BE-003, BE-008, BE-009, BE-010, BE-012, BE-019, PRE-003
**Authority:** VATI research coordinator; risk and order ownership unchanged; independent qualification and exact owner promotion
**Models:** Versioned dataset/evaluator/study/candidate/promotion/experiment manifests; deterministic run and trial identities

**Complete operations:**
- Protection parity for immediate and pending fills
- Limit-price invariants and explicit order semantics
- Pending-order expiry and event-policy propagation
- Qualified chronological evaluator before automated strategy development
- Leakage-proof chronology and genuine walk-forward records
- Immutable dataset, quote, calendar and cost provenance
- Complete trial ledger and honest statistical interpretation
- Governed weekly strategy-development lifecycle

**Adversarial exit:** All VAN-CX-003–013 evaluator obligations; executable matching/chronology fixtures; actual folds and data manifests; deployment-faithful and isolation experiments separated; independent adversarial oracle.
**Corrections:** VAN-CX-003, VAN-CX-004, VAN-CX-005, VAN-CX-010, VAN-CX-011, VAN-CX-012, VAN-CX-013, VAN-CX-014

## BE-036 — Continuous governed strategy-development service and outcome reporting
**Prerequisites:** BE-013, BE-022, BE-028, BE-035, PRE-003, VAN-ML-PKT-021, VAN-ML-PKT-022, VAN-ML-PKT-023, VAN-ML-PKT-025, VAN-ML-PKT-027, VAN-ML-PKT-047
**Authority:** VATI research coordinator; risk and order ownership unchanged; independent qualification and exact owner promotion
**Models:** Versioned dataset/evaluator/study/candidate/promotion/experiment manifests; deterministic run and trial identities

**Complete operations:**
- Qualified chronological evaluator before automated strategy development
- Leakage-proof chronology and genuine walk-forward records
- Complete trial ledger and honest statistical interpretation
- Governed weekly strategy-development lifecycle

**Adversarial exit:** OD-37 automatic offline review/candidate/evaluation under bounded research grants; complete experiment lineage; exact owner promotion and admitted demotion; qualified evaluator dependency; no qualified candidate is a truthful result.
**Corrections:** VAN-CX-010, VAN-CX-011, VAN-CX-013, VAN-CX-014

## VAN-ML-PKT-004 — Pinned dependencies and isolated research runtime
**Prerequisites:** BE-001, BE-002, BE-003, PRE-003
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Lock Qlib, LightGBM, NeuralForecast, XGBoost, Optuna, Feast/MLflow and transitive dependencies by tested version/hash
- Build separate CPU research/inference environments, wheel/architecture matrix, resource and network policy
- Register worker bootstrap, SBOM and safe model-parser compatibility

**Adversarial exit:** Actual train/export/load smoke with locked upstream libraries on an authorized VM; Import-boundary tests reject heavy model imports and broker credentials in the T0 runtime
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-005 — Point-in-time market dataset and universe snapshots
**Prerequisites:** BE-001, BE-008, BE-010, PRE-003, VAN-ML-PKT-004
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement immutable source vintages, availability clocks, calendars, instrument identity and point-in-time universe
- Join licensed market/news/expectation features without revised-future leakage; distinguish observed and reconstructed availability
- Materialize versioned Parquet research snapshots from the existing data owners

**Adversarial exit:** Replay a revision, delisting and late release: past snapshot remains unchanged; Reject cross-venue collisions, incomplete bars and unknown-use entitlements
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-006 — Shared feature definitions and Feast parity
**Prerequisites:** BE-001, BE-003, BE-008, PRE-003, VAN-ML-PKT-005
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Extend existing FeatureRegistry and feature contracts; compile offline/online transformations from one version
- Implement lag/timeframe/peer expansion, fold-fitted preprocessing and aligned row masks
- Integrate scoped Feast feature views/materialization and deterministic local inference snapshots

**Adversarial exit:** Offline/online values and units match within declared tolerances; Shift peer data, change column order or fit a scaler on validation: qualification fails
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-007 — Targets, executable labels and outcome provenance
**Prerequisites:** BE-001, BE-008, BE-018, PRE-003, VAN-ML-PKT-005, VAN-ML-PKT-006
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Build returns, setup-event, ranking, realized-volatility, cost and excursion targets with explicit label intervals
- Keep market observations, actual fills, synthetic controls, practice and counterfactual outcomes in separate namespaces
- Preserve candidate sampling, rejection reason and censoring to expose selection bias

**Adversarial exit:** Labels cannot mature before horizon/outcome availability; Gross/net/cost conventions reconcile; future holding duration cannot become an entry feature
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-008 — Chronological folds, lookahead and warmup diagnostics
**Prerequisites:** BE-001, BE-035, PRE-003, VAN-ML-PKT-006, VAN-ML-PKT-007
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement FoldPlan with interval purging, cohort-coherent cutoffs, calibration slices and embargo policy
- Build full-versus-prefix and positive-poison diagnostics inspired by Freqtrade
- Measure indicator/model feature convergence versus warmup and cache identity

**Adversarial exit:** Leakage, full-data normalization, random splits and future exogenous values are detected; Overlapping horizons do not inflate independent sample counts
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-009 — Simulation accounting, intrabar and timing corrections
**Prerequisites:** BE-001, BE-035, PRE-003, VAN-ML-PKT-005, VAN-ML-PKT-007
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Reproduce and close scoped main-source findings; implement observed intrabar ordering or explicit uncertainty bounds
- Debit commission, financing, borrow/roll and conversion costs exactly once alongside fill spread/slippage
- Produce post-liquidation MTM equity, drawdown and cash-flow-neutral performance with pending risk

**Adversarial exit:** Long/short both-hit, gap-stop, same-close latency, funding boundary and partial-fill cases reconcile; Closed-trade metrics and pre-flatten final equity cannot certify economic performance
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-010 — Account-wide replay and execution-policy parity
**Prerequisites:** BE-001, BE-012, BE-035, PRE-003, VAN-ML-PKT-008, VAN-ML-PKT-009
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Replay through the shared account coordinator/risk/reservation/route policy, not only independent single-symbol cycles
- Build comparable event streams, symbol calendars, margin and instrument specifications
- Provide independent oracle export and documented comparator differences; no second live sender

**Adversarial exit:** Concurrent orders/cancel-fill races and capital contention have equivalent risk decisions; Zero-trade replay does not stand in for exercised approval, rejection and protection paths
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-011 — Qlib data, processor and recorder integration
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-004, VAN-ML-PKT-006, VAN-ML-PKT-007, VAN-ML-PKT-008
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement VanQlibDataLoader and fold-scoped DataHandlerLP/DatasetH adapter over VAN-owned snapshots
- Register T3 training tasks and explicit Qlib Recorder/MLflow run binding
- Use model APIs only; disable Qlib execution/exchange and default equity-region semantics in VAN runtime

**Adversarial exit:** DK_L/DK_I separation, train-only processor fitting and prediction index identity verified; Qlib default execution path and unrestricted YAML imports are rejected
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-012 — LightGBM expected-return and net-edge regressors
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-010, VAN-ML-PKT-011
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Train horizon/cohort-specific regression baselines with explicit cost conventions and objective semantics
- Export native Booster plus feature/target/preprocessor manifests
- Implement out-of-fold predictions, stopping, uncertainty comparison and diagnostic explanations

**Adversarial exit:** Reproducible fixed-environment fits; native export/import numerical equivalence; Data/feature order mismatch and net-cost double subtraction fail tests
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-013 — LightGBM setup-event classification
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-010, VAN-ML-PKT-011
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement binary event targets and raw-probability output with defined censor/tie behavior
- Create disjoint calibration handoff, imbalance controls and reliability metadata
- Compare against event base rate and existing rules on the same candidate population

**Adversarial exit:** Class score is not called win probability until packet020 calibration passes; Unmatured labels, resampling bias and leaked outcome fields fail
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-014 — LightGBM quantile and grouped ranking adapters
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-010, VAN-ML-PKT-011
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement VAN-owned Qlib-compatible/direct-LightGBM adapters for quantile and ranking objectives
- Train explicit alpha/horizon quantiles and grouped cutoff/universe ranking with integer relevance rules
- Validate quantile order, group contiguity and units; rank score remains ordinal

**Adversarial exit:** Stock LGBModel wrapper is not used with unsupported loss values; Negative regression labels passed as rank relevance and cross-date groups are rejected
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-015 — Challenger and simple baseline suite
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-010, VAN-ML-PKT-011
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Integrate XGBoost as a comparable tabular challenger and linear/logistic/persistence/ranking baselines
- Include HAR-style realized-volatility and authorized GARCH implementations with identical data cutoffs
- Version each baseline and preserve failed/no-skill results

**Adversarial exit:** Every mandatory task has a meaningful naive and incumbent comparison; Different horizons, price units, sample windows or costs cannot be compared as like-for-like
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-016 — NeuralForecast bridge and N-HiTS
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-004, VAN-ML-PKT-006, VAN-ML-PKT-007, VAN-ML-PKT-008, VAN-ML-PKT-010
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement canonical unique_id/ds/y and historical/future/static exogenous mapping
- Integrate NHITS multi-horizon training, native validation and fold-scoped scaling
- Capture native outputs and learned preprocessing in the shared experiment/artifact contract

**Adversarial exit:** Actual locked-library training/inference on admitted data; Calendar gaps, unavailable future values and scaler refits at prediction fail
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-017 — N-BEATSx contextual forecasts and decomposition
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-016
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement NBEATSx model plugin and valid exogenous capabilities
- Expose trend/seasonality/exogenous decomposition only when the chosen architecture supports it
- Measure contextual ablation and explanatory output stability

**Adversarial exit:** Actual contextual prediction and decomposition round trip; Explanations cannot claim causal drivers or invent contributions for an unsupported configuration
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-018 — DeepAR distributional forecasts and retained scenarios
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-016
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Integrate DeepAR distribution loss, target-domain checks and pinned RNG/sample manifests
- Retain individual trajectories through a tested adapter, or expose UNSUPPORTED_RAW_PATHS for a pinned API while implementing the documented retained-path adapter before closure
- Keep marginal intervals separate from temporal and cross-asset joint-scenario claims

**Adversarial exit:** Distribution support and raw-path dimensions verified with a real model; Averaged trajectories cannot masquerade as samples; independent assets cannot claim joint portfolio coverage
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-019 — Contextual and multivariate neural challengers
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Provide usable research plugins for TFT, PatchTST and iTransformer with capability introspection and target compatibility
- Bound cross-market cohorts, missing histories, architecture-specific exogenous support and compute budgets
- Test each admitted plugin in training/export/load/inference; economic admission remains conditional

**Adversarial exit:** Do not infer support from constructor argument names alone; Global shared weights are not labelled joint dependence, and invalid capabilities fail before training
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-020 — One calibration and uncertainty-validation boundary
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-015, VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-019
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Extend existing vati.risk.conformal through separate forecast calibration producers and source-bound buckets
- Implement probability calibration, quantile evaluation, optional conformalized intervals and realized coverage monitoring
- Bind residuals to model/target/cohort/horizon and invalidate on refit; correct guarantee language

**Adversarial exit:** Calibration/test separation and stale/mismatched residual refusal verified; Nine residuals or nominal coverage alone cannot establish reliable trading confidence
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-021 — Unified Optuna and rolling research studies
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-008, VAN-ML-PKT-011, VAN-ML-PKT-015, VAN-ML-PKT-019, VAN-ML-PKT-020
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Use one study/budget/trial ledger for Qlib, native LightGBM and NeuralForecast candidates
- Implement bounded neural Auto/Optuna adapter, nested temporal selection and independent final holdout
- Preserve all tried configurations, early/pruned failures and comparison lineage

**Adversarial exit:** Search cannot observe final holdout or mutate live aliases; Repeat study from snapshot and detect data, target, trial-count and environment changes
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-022 — Safe model artifacts and candidate registry
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-004, VAN-ML-PKT-011, VAN-ML-PKT-020, VAN-ML-PKT-021
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement native Booster and safe neural artifact formats with verified source/configuration/manifests
- Connect MLflow versions/runs and immutable VAN admission records; aliases remain advisory
- Implement atomic stage transitions, CAS deployment binding and rollback compatibility

**Adversarial exit:** No untrusted pickle, unapproved dynamic imports or unchecked remote model URI; Changing registry alias cannot change admitted runtime model without a valid binding
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-023 — Adaptive retraining scheduler and lifecycle
**Prerequisites:** BE-001, BE-028, PRE-003, VAN-ML-PKT-021, VAN-ML-PKT-022
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement FreqAI-inspired retraining cadence, drift-triggered jobs, expiry and per-scope queues
- Use existing durable workflow/scheduler owner, bounded retries, resumable checkpoints and worker leases
- Finish candidate fits without automatic promotion; prioritize inference/protection over training

**Adversarial exit:** Kill/restart trainer and duplicate trigger produce no duplicate publication; Old model remains only while valid; training completion never means approved deployment
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-024 — Forecast serving, cache, freshness and novelty gates
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-006, VAN-ML-PKT-020, VAN-ML-PKT-022, VAN-ML-PKT-023
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement typed bounded ForecastService and immutable cache keys tied to actual material inputs
- Add model/data/calibration freshness, schema validation, DI-style novelty and optional SVM/DBSCAN/PCA ablations
- Persist accepted and abstained outputs with explicit reason and identity; no order fields

**Adversarial exit:** Timeout, corrupt model, OOD, stale feed, changed feature order and queue saturation return truthful abstention; No synchronous network/model load can enter T0 risk or protection
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-025 — Forecast fusion, arbiter and mode evidence integration
**Prerequisites:** BE-001, BE-013, PRE-003, VAN-ML-PKT-010, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-019, VAN-ML-PKT-020, VAN-ML-PKT-024
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Join forecasts into existing OpportunityEngine/MetaLabeler and account coordinator through versioned evidence inputs
- Train fusion only on OOF predictions, measure redundancy, preserve baseline fallback policies
- Bind independent economic admission producer to Normal/Risky/Aggressive use; never modify signed ceilings

**Adversarial exit:** Model disagreement, duplicate-signal confidence, missing edge and mid-cycle model change are handled; Arbiter output still requires new TradeIntent, RiskSnapshot, RiskAuthority and sole router
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-026 — Instrument and strategy protection policies
**Prerequisites:** BE-001, BE-012, PRE-003, VAN-ML-PKT-010, VAN-ML-PKT-025
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Add native cooldown, stop-loss streak and low-profit suppression proposals inspired by Freqtrade
- Reuse existing drawdown/kill/health controls and resolve overlapping suppression deterministically
- Persist per-account/environment/strategy/instrument/direction state and reasons

**Adversarial exit:** Partial fills do not multiply loss counts; restarts cannot erase locks; All entry blocks preserve authorized reductions, stop protection and manual control ownership
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-027 — Outcome ledger, drift and proprietary learning data
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-007, VAN-ML-PKT-023, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-026
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Persist input-to-forecast-to-decision-to-outcome attribution and counterfactual separation
- Connect existing drift/health/replay and observed broker costs to candidate retraining requests
- Implement privacy/retention/correction invalidation, consented manual-trade datasets and no-survivor bias

**Adversarial exit:** Deletion/correction invalidates affected derived models without pretending unlearning; Feature drift triggers candidate work or abstention, never unilateral risk expansion
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-028 — Complete backend APIs and future-screen consumption
**Prerequisites:** BE-001, BE-021, PRE-003, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-026, VAN-ML-PKT-027
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Extend genuine gateway operations for forecasts, experiments, diagnostics, proposals, retraining and receipts
- Publish complete typed states/actions/eligibility/readback, cancellation and source-age contract
- Map all forecast features to existing Trading/Analyst/Strategy/Risk/Settings/Work surfaces without new frontend code

**Adversarial exit:** Real authenticated headless caller exercises every registered operation; Uncalibrated scores never exposed as win probabilities; hidden unsupported flags cannot omit required functions
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-029 — VM deployment, isolation, recovery and service operations
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-022, VAN-ML-PKT-023, VAN-ML-PKT-024, VAN-ML-PKT-028
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Build approved VM service manifests with isolated users/quotas/secrets/network and capacity admission
- Exercise install, migration, backup/restore, rollback, model hot-swap and telemetry retention
- Use Global DIAL and Zuul routes; do not run on forbidden desktop or silently substitute local compute

**Adversarial exit:** Kill/pressure/full-disk/mismatched build and lost-receipt drills with actual services; T0 deadline/protection noninterference and immutable ledger survival independently measured
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-037 — Prediction-market scope, VM profiles and source capability contracts
**Prerequisites:** BE-001, BE-002, BE-014, PRE-003, VAN-ML-PKT-004, VAN-ML-PKT-005
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement reusable source/provider contracts with separate technical reachability, allowed data uses, observed terms reference and acquisition mode; no licence-purchase workflow or external spending.
- Provide Netcup and Oracle worker profiles, actual region/host metadata and Global DIAL placement; distinguish operator/account eligibility from machine location.
- Deliver a no-network fixture/replay path and real read-only adapter path using existing source permissions where established; unavailable access affects that source, never erases other engineering scope.

**Adversarial exit:** Positive adapter/replay calls and explicit source-unavailable readback through actual services; source access unresolved must not become a coding prerequisite.; No country-spoofing, proxy workaround, account creation, trade credential requirement or inferred live permission.
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-038 — Kalshi and comparison-provider ingestion, depth and history
**Prerequisites:** BE-001, BE-003, BE-014, PRE-003, VAN-ML-PKT-037
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement versioned REST pagination, public metadata/books/trades and historical-boundary reconciliation plus authenticated read-only stream support where available.
- Normalize exact fixed-point YES/NO bids; derive opposite asks, book depth and quote-quality metadata without float cash arithmetic.
- Persist idempotent events with provider time, received time, available_at, source revision and gap/late-message state; stream gaps force resnapshot before usability.

**Adversarial exit:** Contract-compatible positive integration plus pagination, archive handoff, reconnect, duplicate and precision counterexamples.; Any genuine provider capture has explicit permission/method and timing provenance; fixtures never count as historical/live captures.
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-039 — Event semantics, settlement and cross-venue equivalence
**Prerequisites:** BE-001, BE-015, PRE-003, VAN-ML-PKT-037
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Add versioned event-contract definitions: exact proposition, units, comparator, thresholds, time window, timezone, official source/vintage, rounding, resolution, cancellation and dispute rules.
- Implement contract relation graph and reviewed exact/complement/overlap/non-equivalent mappings; semantic proposals from models cannot certify equivalence.
- Keep event occurrence, official publication, trade close and settlement as distinct states/clocks; corrected or cancelled outcomes create new versions and invalidation edges.

**Adversarial exit:** Same-title/different-rule, initial/revised-release, strict/inclusive threshold and settlement-delay cases produce distinct identities.; Positive exact/complement mapping is usable in research with reviewed evidence; unresolved mapping is explicit, not a permanent empty implementation.
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-040 — Coherent event distributions, quality and probability features
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-006, VAN-ML-PKT-038, VAN-ML-PKT-039
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement binary, mutually exclusive outcome and threshold distribution builders; explicit raw versus adjusted estimates, monotonicity, missing bins and open-tail policies.
- Register probability levels/changes, entropy, tail mass, dispersion, consensus differences, spread/depth and freshness as distinct features; fit all transforms on permitted history.
- Prevent artificial jumps at contract roll; compare aligned maturity/proposition only; preserve Kalshi/Polymarket agreement as consistency, not independent-probability multiplication.

**Adversarial exit:** Finite coherent full distributions, correctly differenced threshold masses, explicit unavailable/partial distributions and deterministic same-input outputs.; Low-depth/outdated/crossed or mismatched books cannot become confident features through averaging or silent normalization.
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-041 — Event calibration, grouped chronology and frozen surprise
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-008, VAN-ML-PKT-020, VAN-ML-PKT-040
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Extend existing calibration by event family, horizon and liquidity cohort; retain market-implied values separately from calibrated physical-event probabilities.
- Freeze admissible pre-release expectations and calculate surprise only once the correct official release becomes available; preserve every later revision separately.
- Group training/calibration/testing by underlying event and aligned cross-market folds; report event-effective sample size, proper scores and concentration, not inflated quote counts.

**Adversarial exit:** Positive matured-label/calibration workflow and real producer binding through existing service.; Post-release input, correlated snapshots split randomly, unsupported probability claims and stale calibration fail qualification.
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-042 — Conditional asset-response models and forecast-stack integration
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-041
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Join point-in-time event features into existing Qlib tabular tasks and model-supported NeuralForecast historical exogenous inputs; future probability trajectories are never known covariates.
- Implement conditional asset-response targets for returns, volatility, adverse excursion and trade quality by instrument/horizon/session, with simple market/calendar baselines.
- Use out-of-fold predictions in fusion, measure incremental information beyond price/news/consensus inputs and preserve shared-source dependencies across model families.

**Adversarial exit:** Actual fitted-model export/load/inference on adequate permitted research data with predictions joined to exact available event snapshots.; Event probability cannot be copied into asset-direction or trade-win probability; incapable NF configurations reject unsupported exogenous fields.
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-043 — Calibrated event value and bounded position evidence
**Prerequisites:** BE-001, BE-009, BE-016, PRE-003, VAN-ML-PKT-010, VAN-ML-PKT-025, VAN-ML-PKT-041, VAN-ML-PKT-042
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement external-asset evidence integration through inherited D1–D7 policies and preserve manual-position ownership, no stop widening, calendar blackouts and two-source armed expectations.
- Implement sandbox binary-contract value calculations for held-to-settlement and exit-before-settlement strategies with explicit depth/fees/currency/capital lockup; probabilities must be independently calibrated.
- Implement maximum-loss/event-family portfolio stress and constrained Kelly-style research comparisons; output only bounded proposals, never final authority, actual order instructions or self-promotion.

**Adversarial exit:** Positive admitted sandbox evidence consumed by risk evaluation and negative stale/unknown/wrong-use cases, with exact source and independent receipt bindings.; No live event-contract adapter is registered; event-risk proposals cannot raise existing news multipliers or treat stop distance as maximum binary loss.
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-044 — Execution-realistic prediction-contract replay
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-009, VAN-ML-PKT-010, VAN-ML-PKT-038, VAN-ML-PKT-039
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Extend the existing replay adapter family with decimal cash, depth/partial-fill logic, order activation/cancel timing, queue uncertainty and trade/bid/ask distinction.
- Bind versioned per-series/per-account fee precision and accumulator semantics; include settlement/dispute/cancel outcomes, venue cash reservations, financing and conversion costs where applicable.
- Keep all positions on one coherent event/book path and reconcile final liquidation/settlement equity; sparse history returns evidence limitations rather than guaranteed maker fills.

**Adversarial exit:** Deterministic accounting identities and counterexamples for touch-not-fill, queue loss, partial fill/cancel races, settlement delay and fee fragmentation.; External-asset evaluation uses the actual destination broker model instead of charging hypothetical Kalshi trades.
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-045 — Contract-consistency and non-atomic arbitrage research laboratory
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-044
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement candidate discovery and exact payoff-state matrices for complementary and related contracts; title embeddings only shortlist candidates.
- Compute worst-case payout/net margin at executable quantities across success/void/cancel/dispute states; separate conditional payoff hedge from guaranteed real execution.
- Simulate venue-specific cash, collateral/currency haircut, settlement delay, partial first-leg fill, failed hedge and feasible unwind; do not assume cross-exchange atomicity or transferable immediate collateral.

**Adversarial exit:** Positive synthetic hedged-payoff case and near-match false-arbitrage/one-leg-failure cases with source-bound research reports.; No new arbitrage order sender; cashflows and margin do not assume default-free settlement or fabricate a USD-stablecoin equivalence.
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-046 — Inventory-aware event market-making research laboratory
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-026, VAN-ML-PKT-041, VAN-ML-PKT-044
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement bounded inventory-aware two-sided quoting simulations with jump risk, time-to-event, event-family exposure, toxicity and fill-conditional expected value.
- Compare no-quote, fixed-spread and inventory-aware policies; measure queue dependence, inventory age, markout at several horizons, fee/rebate assumptions and cancel effectiveness.
- Implement research stop/quote-reduction on stale/gapped books and official-release risk; simulate pending cancels and retain exposure until confirmed. No spoofing/wash-trade logic or assumed special market-maker privileges.

**Adversarial exit:** Positive simulated quoting/fill/inventory roundtrip and adverse-selection/cancel-race/queue-loss stress evidence.; Conditional value uses outcomes after actual modeled fills; unconditional spread capture or touched quotes do not qualify profitability.
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-047 — Prediction-market incremental-value and prospective study programme
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-021, VAN-ML-PKT-027, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Implement four frozen studies: pre-event risk, surprise interpretation, volatility and opportunity ranking, all paired against the same incumbent and exposure-matched/simple controls.
- Include dependency-aware uncertainty, trial census, event counts, publication/acquisition/execution lag tests, shuffled/lagged controls, full-account accounting and operating costs.
- Deliver prospective forecast sealing, outcome maturation and per-use decisions QUALIFIED/REJECTED/INCONCLUSIVE/UNAVAILABLE; useful context is not automatically trading edge.

**Adversarial exit:** Actual comparison/report pipelines with positive and deliberately no-edge fixtures; actual market claims require permitted untouched and prospective observations.; Fewer trades or reduced capital alone cannot be advertised as superior intelligence; insufficient independent events remains inconclusive.
**Corrections:** all canonical source/proof/authority invariants

## VAN-ML-PKT-048 — Prediction-market consumers, operations and complete backend integration
**Prerequisites:** BE-001, PRE-003, VAN-ML-PKT-028, VAN-ML-PKT-029, VAN-ML-PKT-037, VAN-ML-PKT-038, VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-041, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046, VAN-ML-PKT-047
**Authority:** Read-only research/forecast evidence; VATI remains sole risk and order authority
**Models:** Source forecast schema set in contracts/forecast; exact producer/consumer bindings in plan and source crosswalk

**Complete operations:**
- Wire all data, probability, comparison, research-lab and evidence states into existing APIs, capability catalogue, alerts, logs and later-screen contracts; no early frontend.
- Exercise Netcup/Oracle host profiles, endpoint changes, stream gaps, source revocation, disk/backlog pressure, restart, duplicate/unknown publication and schema rollback with no T0/provider network coupling.
- Provide honest per-source integration state and no-procurement development path; all mandatory backend/parent obligations remain visible and source-specific real-data gates cannot be replaced by fixtures.

**Adversarial exit:** Headless real-service positive/recovery/error readbacks; all new requirements join independent packet032 closure and parent033/BG-001.; No background order enablement, licence purchase, new account, cloud bill, fixture-to-live promotion or false full-provider-ready claim.
**Corrections:** all canonical source/proof/authority invariants

