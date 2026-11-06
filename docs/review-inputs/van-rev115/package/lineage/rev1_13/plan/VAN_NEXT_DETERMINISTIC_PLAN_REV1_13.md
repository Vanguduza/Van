# VAN Next — One Deterministic Backend-First Development Plan, Rev 1.13

**Project:** `16f2f43a-8d8b-4f18-a6ac-5bd8df620414` · **Source baseline:** `a39f241b0135cf92cc5a6b9a28af226aa294603d`
**Status:** prepared consolidation candidate. No owner signature, F15, Backend Complete or release authority is issued by this plan. Every unit is FULL and NOT_STARTED until a valid scoped receipt establishes its actual state.

**Active graph:** 131 packets; 82 backend capabilities; 12 backend-verification units. **BG-001:** VAN-PKT-098; **first new UX:** VAN-PKT-099.

## 1. Execution rules

1. Predevelopment PRE-001 → PRE-002 → independent PRE-003 F15 precedes any code-bearing source consolidation or implementation. The current documentary reconciliation is not a claimed signed packet exit.
2. Complete all backend operations, integration and negative/recovery evidence; then independently close BG-001. No new frontend, visual prototype, native design golden, chart/orb renderer, theme or app shell starts beforehand. Old five UI flows are eventual integration scenarios, not early work authorization.
3. Prefer one packet at a time in the generated sequence. Parallel work requires explicit assigned ownership, isolated worktrees and all dependency exits; it never changes stage or gate order.
4. Each packet has its own approved acceptance contract binding exact source/configuration, complete operations, caller/authority/readback, test commands, negative cases, rollback and reviewer. A row in this plan is not itself that signed executable contract.
5. PRE-001–003 use no-application-change preservation inventory checks. BE-001 builds and qualifies the actual parity checker, including an induced failure. Every subsequent implementation exit requires no feature loss, on top of each unit’s own acceptance.
6. Preserve all inherited owner actions, source functions and new feature contracts. A completed showcase, test count or registered URL never substitutes for full effect/recovery proof. Changes to the lock require a new explicit owner-reviewed amendment; no default retirement.
7. Research automation uses standing bounded research grants. Evaluator BE-035 must qualify before economic claims or BE-036 research-loop promotion; all failed experiments remain inspectable. Owner-signed financial/live transitions remain separate.
8. A missing required provider integration or backend defect keeps its gate blocked; unrelated backend work may proceed if dependencies allow. New design revealing a backend omission reopens BG and pauses affected frontend work.
9. F15, BG, native-device qualification and live financial authority are independent evidence states. The plan checker verifies obligations and order; a real receipt verifier must validate issuer, signature, scope, freshness and revocation.

## 2. Immutable inputs for this rendered plan

| Input | SHA-256 |
|---|---|
| `CANONICAL_AUTHORITY.json` | `fd6253848683b46a555e6e7101b1ee046da3ac4ce1ec9ac69bccd8fc6493edca` |
| `plan/DEVELOPMENT_PLAN.json` | `c1549dde7b97f6aaf781230f34f101a8e4b16a87e4920c4b3a310e56effbc670` |
| `traceability/REQUIREMENTS_AND_DU_MAPPING.json` | `703f41e4a5a96f006fcd6b314dd35035599b0d4167266012089ff169cc91d85b` |
| `contracts/BACKEND_SERVICE_CATALOG.json` | `0e86db29e045b89e17759215bbabd7275063f99f5ead5baf2f4f8730e37f7390` |
| `verification/TEST_CONTRACTS.json` | `baf8a713caff8d2bfbde8adeb28b91e017ad4ef5695fe5d1c16b66b85e530e1d` |
| `design/ALL_SURFACE_CONTRACTS.json` | `2b7152fca522a423a44fc4f01b791d25ab72aaf143a17a96f87ebf39119e94ae` |
| `traceability/LEGACY_349_ACTIONS.json` | `4fe9dd0b7050203e0cac8a479c0a21993b890082aed15b28ab85250410c7830d` |
| `traceability/FORECAST_PACKET_CROSSWALK.json` | `135e1690f920427a9e79c1554064ed3a30b29a3af50825b388adccb4f66858b5` |
| `plan/PROPOSED_SCOPE_LOCK.json` | `41b6b01cd2b3bcfa7406f791e4d7d6f9001d772b53444137c431dbf0867cbeb8` |
| `plan/render_plan.py` | `50e994767df66fc852d05b3d4c01ae97a7d4302dd8dca033d669dc7544c79369` |

**Aggregate input digest:** `b2c5de151ec38da9a7716d0bebcc1cfe9a8a09c30aae1de042486b0f6ce73813`. Deterministic canonical JSON of the filename→SHA-256 map, UTF-8; no timestamps in generated output.

## 3. Entire packet sequence

| Packet | Unit | Kind | Complete outcome | Prerequisites |
|---|---|---|---|
| VAN-PKT-001 | PRE-001 | PREDEVELOPMENT | Read-only complete evidence and feature inventory | — |
| VAN-PKT-002 | PRE-002 | PREDEVELOPMENT | Whole-product semantic reconciliation and packet contracts | VAN-PKT-001 |
| VAN-PKT-003 | PRE-003 | PREDEVELOPMENT_GATE | Independent DIAL F0–F15 build-ready certification | VAN-PKT-002 |
| VAN-PKT-004 | BE-001 | BACKEND | Source consolidation and preservation oracle | VAN-PKT-003 |
| VAN-PKT-005 | BE-002 | BACKEND | Device identity, bounded authority and intent fencing | VAN-PKT-004, VAN-PKT-003 |
| VAN-PKT-006 | BE-003 | BACKEND | Durable event, readback and projection infrastructure | VAN-PKT-005, VAN-PKT-003 |
| VAN-PKT-007 | BE-004 | BACKEND | Accounts, broker directory and operation capabilities | VAN-PKT-005, VAN-PKT-006, VAN-PKT-003 |
| VAN-PKT-008 | BE-005 | BACKEND | Broker authentication, credential rotation and health | VAN-PKT-007, VAN-PKT-003 |
| VAN-PKT-009 | BE-006 | BACKEND | Exact funding ledger and flow-adjusted accounting | VAN-PKT-006, VAN-PKT-007, VAN-PKT-003 |
| VAN-PKT-010 | BE-007 | BACKEND | Deposits, withdrawals, transfers and provider rails | VAN-PKT-008, VAN-PKT-009, VAN-PKT-003 |
| VAN-PKT-011 | BE-008 | BACKEND | Instrument identity, market feeds, bars and depth | VAN-PKT-006, VAN-PKT-008, VAN-PKT-003 |
| VAN-PKT-012 | BE-009 | BACKEND | Mandates, risk, sizing and portfolio reservations | VAN-PKT-005, VAN-PKT-009, VAN-PKT-011, VAN-PKT-003 |
| VAN-PKT-013 | BE-010 | BACKEND | Venue execution, canonical orders and reconciliation | VAN-PKT-008, VAN-PKT-011, VAN-PKT-012, VAN-PKT-003 |
| VAN-PKT-014 | BE-011 | BACKEND | Manual trading, adds and management handover | VAN-PKT-012, VAN-PKT-013, VAN-PKT-003 |
| VAN-PKT-015 | BE-012 | BACKEND | Positions, protection, portfolio, history and TCA | VAN-PKT-009, VAN-PKT-013, VAN-PKT-014, VAN-PKT-003 |
| VAN-PKT-016 | BE-014 | BACKEND | News, calendar and source-health ingestion | VAN-PKT-006, VAN-PKT-011, VAN-PKT-003 |
| VAN-PKT-017 | BE-015 | BACKEND | Event analysis, history, analogues and expectations | VAN-PKT-016, VAN-PKT-003 |
| VAN-PKT-018 | BE-018 | BACKEND | Chart data contracts, indicators, drawings and workspaces | VAN-PKT-006, VAN-PKT-011, VAN-PKT-003 |
| VAN-PKT-019 | BE-019 | BACKEND | Historical replay, simulation and isolated practice data | VAN-PKT-011, VAN-PKT-018, VAN-PKT-003 |
| VAN-PKT-020 | BE-020 | BACKEND | Watchlists, persistent alerts and typed screening | VAN-PKT-006, VAN-PKT-011, VAN-PKT-016, VAN-PKT-018, VAN-PKT-003 |
| VAN-PKT-021 | BE-021 | BACKEND | Analyst, chart observations and cross-signal intelligence | VAN-PKT-015, VAN-PKT-017, VAN-PKT-018, VAN-PKT-019, VAN-PKT-003 |
| VAN-PKT-022 | BE-023 | BACKEND | Projects, tasks, missions and truthful workflow graphs | VAN-PKT-005, VAN-PKT-006, VAN-PKT-003 |
| VAN-PKT-023 | BE-024 | BACKEND | Agents, Hermes, Muse and provider-bound interventions | VAN-PKT-005, VAN-PKT-006, VAN-PKT-022, VAN-PKT-003 |
| VAN-PKT-024 | BE-025 | BACKEND | Browser, remote interaction, artifact and share intake | VAN-PKT-005, VAN-PKT-006, VAN-PKT-023, VAN-PKT-003 |
| VAN-PKT-025 | BE-026 | BACKEND | ARTEMIS device tests and independent evidence services | VAN-PKT-005, VAN-PKT-006, VAN-PKT-022, VAN-PKT-024, VAN-PKT-003 |
| VAN-PKT-026 | BE-027 | BACKEND | Memory, knowledge, goals, privacy and erasure | VAN-PKT-005, VAN-PKT-006, VAN-PKT-003 |
| VAN-PKT-027 | BE-028 | BACKEND | Automation, reminders and schedules | VAN-PKT-005, VAN-PKT-006, VAN-PKT-022, VAN-PKT-026, VAN-PKT-003 |
| VAN-PKT-028 | BE-029 | BACKEND | Conversation, voice and speaker-profile services | VAN-PKT-005, VAN-PKT-006, VAN-PKT-026, VAN-PKT-003 |
| VAN-PKT-029 | BE-030 | BACKEND | Attention, notifications, presence and compact summaries | VAN-PKT-006, VAN-PKT-015, VAN-PKT-020, VAN-PKT-022, VAN-PKT-023, VAN-PKT-027, VAN-PKT-028, VAN-PKT-003 |
| VAN-PKT-030 | BE-031 | BACKEND | Connected providers, settings, devices and diagnostics | VAN-PKT-005, VAN-PKT-006, VAN-PKT-008, VAN-PKT-023, VAN-PKT-024, VAN-PKT-028, VAN-PKT-003 |
| VAN-PKT-031 | BE-034 | BACKEND | Development studio, CI/security and evidence-workspace adapters | VAN-PKT-022, VAN-PKT-023, VAN-PKT-024, VAN-PKT-025, VAN-PKT-003 |
| VAN-PKT-032 | BE-035 | BACKEND | Qualified chronological strategy evaluator and simulator oracle | VAN-PKT-006, VAN-PKT-011, VAN-PKT-012, VAN-PKT-013, VAN-PKT-015, VAN-PKT-019, VAN-PKT-003 |
| VAN-PKT-033 | BE-013 | BACKEND | Strategy registry, signed trading modes and qualified edge-consumer contracts | VAN-PKT-012, VAN-PKT-013, VAN-PKT-032, VAN-PKT-003 |
| VAN-PKT-034 | BE-016 | BACKEND | Governed news effects D1–D7 and news strategy lifecycle | VAN-PKT-012, VAN-PKT-015, VAN-PKT-033, VAN-PKT-017, VAN-PKT-003 |
| VAN-PKT-035 | BE-017 | BACKEND | Armed news tickets, readiness and single-use execution | VAN-PKT-005, VAN-PKT-013, VAN-PKT-034, VAN-PKT-003 |
| VAN-PKT-036 | BE-022 | BACKEND | Owner diagnostics, pattern discovery and learning review | VAN-PKT-014, VAN-PKT-033, VAN-PKT-019, VAN-PKT-021, VAN-PKT-003 |
| VAN-PKT-037 | VAN-ML-PKT-004 | BACKEND | Pinned dependencies and isolated research runtime | VAN-PKT-004, VAN-PKT-005, VAN-PKT-006, VAN-PKT-003 |
| VAN-PKT-038 | VAN-ML-PKT-005 | BACKEND | Point-in-time market dataset and universe snapshots | VAN-PKT-004, VAN-PKT-011, VAN-PKT-013, VAN-PKT-003, VAN-PKT-037 |
| VAN-PKT-039 | BE-037 | BACKEND | Chain-aware identity and permitted read-only discovery adapters | VAN-PKT-006, VAN-PKT-011, VAN-PKT-038 |
| VAN-PKT-040 | BE-038 | BACKEND | Complete discovery cohorts and staged deterministic screening | VAN-PKT-039, VAN-PKT-020 |
| VAN-PKT-041 | BE-039 | BACKEND | Solana token capability and uncertainty analyzer | VAN-PKT-039, VAN-PKT-040 |
| VAN-PKT-042 | BE-040 | BACKEND | EVM contract/proxy capability and uncertainty analyzer | VAN-PKT-039, VAN-PKT-040 |
| VAN-PKT-043 | VAN-ML-PKT-006 | BACKEND | Shared feature definitions and Feast parity | VAN-PKT-004, VAN-PKT-006, VAN-PKT-011, VAN-PKT-003, VAN-PKT-038 |
| VAN-PKT-044 | BE-042 | BACKEND | Temporal wallet attribution and holder-flow intelligence | VAN-PKT-041, VAN-PKT-042, VAN-PKT-043 |
| VAN-PKT-045 | VAN-ML-PKT-007 | BACKEND | Targets, executable labels and outcome provenance | VAN-PKT-004, VAN-PKT-011, VAN-PKT-018, VAN-PKT-003, VAN-PKT-038, VAN-PKT-043 |
| VAN-PKT-046 | VAN-ML-PKT-008 | BACKEND | Chronological folds, lookahead and warmup diagnostics | VAN-PKT-004, VAN-PKT-032, VAN-PKT-003, VAN-PKT-043, VAN-PKT-045 |
| VAN-PKT-047 | VAN-ML-PKT-009 | BACKEND | Simulation accounting, intrabar and timing corrections | VAN-PKT-004, VAN-PKT-032, VAN-PKT-003, VAN-PKT-038, VAN-PKT-045 |
| VAN-PKT-048 | BE-041 | BACKEND | State-bound buy/sell simulations and executable quote facts | VAN-PKT-041, VAN-PKT-042, VAN-PKT-013, VAN-PKT-045, VAN-PKT-047 |
| VAN-PKT-049 | VAN-ML-PKT-010 | BACKEND | Account-wide replay and execution-policy parity | VAN-PKT-004, VAN-PKT-015, VAN-PKT-032, VAN-PKT-003, VAN-PKT-046, VAN-PKT-047 |
| VAN-PKT-050 | VAN-ML-PKT-011 | BACKEND | Qlib data, processor and recorder integration | VAN-PKT-004, VAN-PKT-003, VAN-PKT-037, VAN-PKT-043, VAN-PKT-045, VAN-PKT-046 |
| VAN-PKT-051 | VAN-ML-PKT-012 | BACKEND | LightGBM expected-return and net-edge regressors | VAN-PKT-004, VAN-PKT-003, VAN-PKT-049, VAN-PKT-050 |
| VAN-PKT-052 | VAN-ML-PKT-013 | BACKEND | LightGBM setup-event classification | VAN-PKT-004, VAN-PKT-003, VAN-PKT-049, VAN-PKT-050 |
| VAN-PKT-053 | VAN-ML-PKT-014 | BACKEND | LightGBM quantile and grouped ranking adapters | VAN-PKT-004, VAN-PKT-003, VAN-PKT-049, VAN-PKT-050 |
| VAN-PKT-054 | VAN-ML-PKT-015 | BACKEND | Challenger and simple baseline suite | VAN-PKT-004, VAN-PKT-003, VAN-PKT-049, VAN-PKT-050 |
| VAN-PKT-055 | VAN-ML-PKT-016 | BACKEND | NeuralForecast bridge and N-HiTS | VAN-PKT-004, VAN-PKT-003, VAN-PKT-037, VAN-PKT-043, VAN-PKT-045, VAN-PKT-046, VAN-PKT-049 |
| VAN-PKT-056 | VAN-ML-PKT-017 | BACKEND | N-BEATSx contextual forecasts and decomposition | VAN-PKT-004, VAN-PKT-003, VAN-PKT-055 |
| VAN-PKT-057 | VAN-ML-PKT-018 | BACKEND | DeepAR distributional forecasts and retained scenarios | VAN-PKT-004, VAN-PKT-003, VAN-PKT-055 |
| VAN-PKT-058 | VAN-ML-PKT-019 | BACKEND | Contextual and multivariate neural challengers | VAN-PKT-004, VAN-PKT-003, VAN-PKT-055, VAN-PKT-056, VAN-PKT-057 |
| VAN-PKT-059 | VAN-ML-PKT-020 | BACKEND | One calibration and uncertainty-validation boundary | VAN-PKT-004, VAN-PKT-003, VAN-PKT-051, VAN-PKT-052, VAN-PKT-053, VAN-PKT-054, VAN-PKT-055, VAN-PKT-056, VAN-PKT-057, VAN-PKT-058 |
| VAN-PKT-060 | VAN-ML-PKT-021 | BACKEND | Unified Optuna and rolling research studies | VAN-PKT-004, VAN-PKT-003, VAN-PKT-046, VAN-PKT-050, VAN-PKT-054, VAN-PKT-058, VAN-PKT-059 |
| VAN-PKT-061 | VAN-ML-PKT-022 | BACKEND | Safe model artifacts and candidate registry | VAN-PKT-004, VAN-PKT-003, VAN-PKT-037, VAN-PKT-050, VAN-PKT-059, VAN-PKT-060 |
| VAN-PKT-062 | VAN-ML-PKT-023 | BACKEND | Adaptive retraining scheduler and lifecycle | VAN-PKT-004, VAN-PKT-027, VAN-PKT-003, VAN-PKT-060, VAN-PKT-061 |
| VAN-PKT-063 | VAN-ML-PKT-024 | BACKEND | Forecast serving, cache, freshness and novelty gates | VAN-PKT-004, VAN-PKT-003, VAN-PKT-043, VAN-PKT-059, VAN-PKT-061, VAN-PKT-062 |
| VAN-PKT-064 | VAN-ML-PKT-025 | BACKEND | Forecast fusion, arbiter and mode evidence integration | VAN-PKT-004, VAN-PKT-033, VAN-PKT-003, VAN-PKT-049, VAN-PKT-051, VAN-PKT-052, VAN-PKT-053, VAN-PKT-058, VAN-PKT-059, VAN-PKT-063 |
| VAN-PKT-065 | VAN-ML-PKT-026 | BACKEND | Instrument and strategy protection policies | VAN-PKT-004, VAN-PKT-015, VAN-PKT-003, VAN-PKT-049, VAN-PKT-064 |
| VAN-PKT-066 | VAN-ML-PKT-027 | BACKEND | Outcome ledger, drift and proprietary learning data | VAN-PKT-004, VAN-PKT-003, VAN-PKT-045, VAN-PKT-062, VAN-PKT-063, VAN-PKT-064, VAN-PKT-065 |
| VAN-PKT-067 | BE-043 | BACKEND | Finality, reorganization and descendant revalidation | VAN-PKT-039, VAN-PKT-048, VAN-PKT-044, VAN-PKT-063, VAN-PKT-066 |
| VAN-PKT-068 | VAN-ML-PKT-028 | BACKEND | Complete backend APIs and future-screen consumption | VAN-PKT-004, VAN-PKT-021, VAN-PKT-003, VAN-PKT-063, VAN-PKT-064, VAN-PKT-065, VAN-PKT-066 |
| VAN-PKT-069 | VAN-ML-PKT-029 | BACKEND | VM deployment, isolation, recovery and service operations | VAN-PKT-004, VAN-PKT-003, VAN-PKT-061, VAN-PKT-062, VAN-PKT-063, VAN-PKT-068 |
| VAN-PKT-070 | VAN-ML-PKT-037 | BACKEND | Prediction-market scope, VM profiles and source capability contracts | VAN-PKT-004, VAN-PKT-005, VAN-PKT-016, VAN-PKT-003, VAN-PKT-037, VAN-PKT-038 |
| VAN-PKT-071 | VAN-ML-PKT-038 | BACKEND | Kalshi and comparison-provider ingestion, depth and history | VAN-PKT-004, VAN-PKT-006, VAN-PKT-016, VAN-PKT-003, VAN-PKT-070 |
| VAN-PKT-072 | VAN-ML-PKT-039 | BACKEND | Event semantics, settlement and cross-venue equivalence | VAN-PKT-004, VAN-PKT-017, VAN-PKT-003, VAN-PKT-070 |
| VAN-PKT-073 | VAN-ML-PKT-040 | BACKEND | Coherent event distributions, quality and probability features | VAN-PKT-004, VAN-PKT-003, VAN-PKT-043, VAN-PKT-071, VAN-PKT-072 |
| VAN-PKT-074 | VAN-ML-PKT-041 | BACKEND | Event calibration, grouped chronology and frozen surprise | VAN-PKT-004, VAN-PKT-003, VAN-PKT-046, VAN-PKT-059, VAN-PKT-073 |
| VAN-PKT-075 | VAN-ML-PKT-042 | BACKEND | Conditional asset-response models and forecast-stack integration | VAN-PKT-004, VAN-PKT-003, VAN-PKT-051, VAN-PKT-052, VAN-PKT-053, VAN-PKT-056, VAN-PKT-057, VAN-PKT-063, VAN-PKT-064, VAN-PKT-074 |
| VAN-PKT-076 | VAN-ML-PKT-043 | BACKEND | Calibrated event value and bounded position evidence | VAN-PKT-004, VAN-PKT-012, VAN-PKT-034, VAN-PKT-003, VAN-PKT-049, VAN-PKT-064, VAN-PKT-074, VAN-PKT-075 |
| VAN-PKT-077 | VAN-ML-PKT-044 | BACKEND | Execution-realistic prediction-contract replay | VAN-PKT-004, VAN-PKT-003, VAN-PKT-047, VAN-PKT-049, VAN-PKT-071, VAN-PKT-072 |
| VAN-PKT-078 | VAN-ML-PKT-045 | BACKEND | Contract-consistency and non-atomic arbitrage research laboratory | VAN-PKT-004, VAN-PKT-003, VAN-PKT-072, VAN-PKT-073, VAN-PKT-077 |
| VAN-PKT-079 | VAN-ML-PKT-046 | BACKEND | Inventory-aware event market-making research laboratory | VAN-PKT-004, VAN-PKT-003, VAN-PKT-065, VAN-PKT-074, VAN-PKT-077 |
| VAN-PKT-080 | VAN-ML-PKT-047 | BACKEND | Prediction-market incremental-value and prospective study programme | VAN-PKT-004, VAN-PKT-003, VAN-PKT-060, VAN-PKT-066, VAN-PKT-075, VAN-PKT-076, VAN-PKT-077, VAN-PKT-078, VAN-PKT-079 |
| VAN-PKT-081 | BE-036 | BACKEND | Continuous governed strategy-development service and outcome reporting | VAN-PKT-033, VAN-PKT-036, VAN-PKT-027, VAN-PKT-032, VAN-PKT-003, VAN-PKT-060, VAN-PKT-061, VAN-PKT-062, VAN-PKT-064, VAN-PKT-066, VAN-PKT-080 |
| VAN-PKT-082 | BE-044 | BACKEND | Read-only crypto end-to-end research, operations and native consumption contract | VAN-PKT-040, VAN-PKT-048, VAN-PKT-044, VAN-PKT-067, VAN-PKT-021, VAN-PKT-023, VAN-PKT-064, VAN-PKT-068, VAN-PKT-069, VAN-PKT-080 |
| VAN-PKT-083 | VAN-ML-PKT-048 | BACKEND | Prediction-market consumers, operations and complete backend integration | VAN-PKT-004, VAN-PKT-003, VAN-PKT-068, VAN-PKT-069, VAN-PKT-070, VAN-PKT-071, VAN-PKT-072, VAN-PKT-073, VAN-PKT-074, VAN-PKT-075, VAN-PKT-076, VAN-PKT-077, VAN-PKT-078, VAN-PKT-079, VAN-PKT-080 |
| VAN-PKT-084 | BE-032 | BACKEND | Whole-product capability, action and UI-consumption catalog | VAN-PKT-007, VAN-PKT-010, VAN-PKT-015, VAN-PKT-033, VAN-PKT-035, VAN-PKT-018, VAN-PKT-019, VAN-PKT-020, VAN-PKT-021, VAN-PKT-036, VAN-PKT-022, VAN-PKT-023, VAN-PKT-024, VAN-PKT-025, VAN-PKT-026, VAN-PKT-027, VAN-PKT-028, VAN-PKT-029, VAN-PKT-030, VAN-PKT-031, VAN-PKT-081, VAN-PKT-082, VAN-PKT-003, VAN-PKT-068, VAN-PKT-083 |
| VAN-PKT-085 | BE-033 | BACKEND | Backend deployment, recovery, capacity and observability | VAN-PKT-084, VAN-PKT-003 |
| VAN-PKT-086 | BQ-001 | BACKEND_VERIFICATION | Trade/account/market/risk/execution headless end-to-end | VAN-PKT-004, VAN-PKT-005, VAN-PKT-006, VAN-PKT-007, VAN-PKT-008, VAN-PKT-009, VAN-PKT-010, VAN-PKT-011, VAN-PKT-012, VAN-PKT-013, VAN-PKT-014, VAN-PKT-015, VAN-PKT-033, VAN-PKT-016, VAN-PKT-017, VAN-PKT-034, VAN-PKT-035, VAN-PKT-018, VAN-PKT-019, VAN-PKT-020, VAN-PKT-021, VAN-PKT-036, VAN-PKT-022, VAN-PKT-023, VAN-PKT-024, VAN-PKT-025, VAN-PKT-026, VAN-PKT-027, VAN-PKT-028, VAN-PKT-029, VAN-PKT-030, VAN-PKT-084, VAN-PKT-085, VAN-PKT-031, VAN-PKT-032, VAN-PKT-081, VAN-PKT-082, VAN-PKT-037, VAN-PKT-038, VAN-PKT-043, VAN-PKT-045, VAN-PKT-046, VAN-PKT-047, VAN-PKT-049, VAN-PKT-050, VAN-PKT-051, VAN-PKT-052, VAN-PKT-053, VAN-PKT-054, VAN-PKT-055, VAN-PKT-056, VAN-PKT-057, VAN-PKT-058, VAN-PKT-059, VAN-PKT-060, VAN-PKT-061, VAN-PKT-062, VAN-PKT-063, VAN-PKT-064, VAN-PKT-065, VAN-PKT-066, VAN-PKT-068, VAN-PKT-069, VAN-PKT-070, VAN-PKT-071, VAN-PKT-072, VAN-PKT-073, VAN-PKT-074, VAN-PKT-075, VAN-PKT-076, VAN-PKT-077, VAN-PKT-078, VAN-PKT-079, VAN-PKT-080, VAN-PKT-083 |
| VAN-PKT-087 | BQ-002 | BACKEND_VERIFICATION | Provider accounts/funds/settlement and concurrent risk qualification | VAN-PKT-004, VAN-PKT-005, VAN-PKT-006, VAN-PKT-007, VAN-PKT-008, VAN-PKT-009, VAN-PKT-010, VAN-PKT-011, VAN-PKT-012, VAN-PKT-013, VAN-PKT-014, VAN-PKT-015, VAN-PKT-033, VAN-PKT-016, VAN-PKT-017, VAN-PKT-034, VAN-PKT-035, VAN-PKT-018, VAN-PKT-019, VAN-PKT-020, VAN-PKT-021, VAN-PKT-036, VAN-PKT-022, VAN-PKT-023, VAN-PKT-024, VAN-PKT-025, VAN-PKT-026, VAN-PKT-027, VAN-PKT-028, VAN-PKT-029, VAN-PKT-030, VAN-PKT-084, VAN-PKT-085, VAN-PKT-031, VAN-PKT-032, VAN-PKT-081, VAN-PKT-082, VAN-PKT-037, VAN-PKT-038, VAN-PKT-043, VAN-PKT-045, VAN-PKT-046, VAN-PKT-047, VAN-PKT-049, VAN-PKT-050, VAN-PKT-051, VAN-PKT-052, VAN-PKT-053, VAN-PKT-054, VAN-PKT-055, VAN-PKT-056, VAN-PKT-057, VAN-PKT-058, VAN-PKT-059, VAN-PKT-060, VAN-PKT-061, VAN-PKT-062, VAN-PKT-063, VAN-PKT-064, VAN-PKT-065, VAN-PKT-066, VAN-PKT-068, VAN-PKT-069, VAN-PKT-070, VAN-PKT-071, VAN-PKT-072, VAN-PKT-073, VAN-PKT-074, VAN-PKT-075, VAN-PKT-076, VAN-PKT-077, VAN-PKT-078, VAN-PKT-079, VAN-PKT-080, VAN-PKT-083 |
| VAN-PKT-088 | BQ-003 | BACKEND_VERIFICATION | News/history/armed grants/chart-observation headless intelligence | VAN-PKT-004, VAN-PKT-005, VAN-PKT-006, VAN-PKT-007, VAN-PKT-008, VAN-PKT-009, VAN-PKT-010, VAN-PKT-011, VAN-PKT-012, VAN-PKT-013, VAN-PKT-014, VAN-PKT-015, VAN-PKT-033, VAN-PKT-016, VAN-PKT-017, VAN-PKT-034, VAN-PKT-035, VAN-PKT-018, VAN-PKT-019, VAN-PKT-020, VAN-PKT-021, VAN-PKT-036, VAN-PKT-022, VAN-PKT-023, VAN-PKT-024, VAN-PKT-025, VAN-PKT-026, VAN-PKT-027, VAN-PKT-028, VAN-PKT-029, VAN-PKT-030, VAN-PKT-084, VAN-PKT-085, VAN-PKT-031, VAN-PKT-032, VAN-PKT-081, VAN-PKT-082, VAN-PKT-037, VAN-PKT-038, VAN-PKT-043, VAN-PKT-045, VAN-PKT-046, VAN-PKT-047, VAN-PKT-049, VAN-PKT-050, VAN-PKT-051, VAN-PKT-052, VAN-PKT-053, VAN-PKT-054, VAN-PKT-055, VAN-PKT-056, VAN-PKT-057, VAN-PKT-058, VAN-PKT-059, VAN-PKT-060, VAN-PKT-061, VAN-PKT-062, VAN-PKT-063, VAN-PKT-064, VAN-PKT-065, VAN-PKT-066, VAN-PKT-068, VAN-PKT-069, VAN-PKT-070, VAN-PKT-071, VAN-PKT-072, VAN-PKT-073, VAN-PKT-074, VAN-PKT-075, VAN-PKT-076, VAN-PKT-077, VAN-PKT-078, VAN-PKT-079, VAN-PKT-080, VAN-PKT-083 |
| VAN-PKT-089 | BQ-004 | BACKEND_VERIFICATION | Work/agents/Muse/browser/voice/memory/automation service integration | VAN-PKT-004, VAN-PKT-005, VAN-PKT-006, VAN-PKT-007, VAN-PKT-008, VAN-PKT-009, VAN-PKT-010, VAN-PKT-011, VAN-PKT-012, VAN-PKT-013, VAN-PKT-014, VAN-PKT-015, VAN-PKT-033, VAN-PKT-016, VAN-PKT-017, VAN-PKT-034, VAN-PKT-035, VAN-PKT-018, VAN-PKT-019, VAN-PKT-020, VAN-PKT-021, VAN-PKT-036, VAN-PKT-022, VAN-PKT-023, VAN-PKT-024, VAN-PKT-025, VAN-PKT-026, VAN-PKT-027, VAN-PKT-028, VAN-PKT-029, VAN-PKT-030, VAN-PKT-084, VAN-PKT-085, VAN-PKT-031, VAN-PKT-032, VAN-PKT-081, VAN-PKT-082, VAN-PKT-037, VAN-PKT-038, VAN-PKT-043, VAN-PKT-045, VAN-PKT-046, VAN-PKT-047, VAN-PKT-049, VAN-PKT-050, VAN-PKT-051, VAN-PKT-052, VAN-PKT-053, VAN-PKT-054, VAN-PKT-055, VAN-PKT-056, VAN-PKT-057, VAN-PKT-058, VAN-PKT-059, VAN-PKT-060, VAN-PKT-061, VAN-PKT-062, VAN-PKT-063, VAN-PKT-064, VAN-PKT-065, VAN-PKT-066, VAN-PKT-068, VAN-PKT-069, VAN-PKT-070, VAN-PKT-071, VAN-PKT-072, VAN-PKT-073, VAN-PKT-074, VAN-PKT-075, VAN-PKT-076, VAN-PKT-077, VAN-PKT-078, VAN-PKT-079, VAN-PKT-080, VAN-PKT-083 |
| VAN-PKT-090 | BQ-005 | BACKEND_VERIFICATION | Backend privacy, recovery, capacity, restart and source fault injection | VAN-PKT-004, VAN-PKT-005, VAN-PKT-006, VAN-PKT-007, VAN-PKT-008, VAN-PKT-009, VAN-PKT-010, VAN-PKT-011, VAN-PKT-012, VAN-PKT-013, VAN-PKT-014, VAN-PKT-015, VAN-PKT-033, VAN-PKT-016, VAN-PKT-017, VAN-PKT-034, VAN-PKT-035, VAN-PKT-018, VAN-PKT-019, VAN-PKT-020, VAN-PKT-021, VAN-PKT-036, VAN-PKT-022, VAN-PKT-023, VAN-PKT-024, VAN-PKT-025, VAN-PKT-026, VAN-PKT-027, VAN-PKT-028, VAN-PKT-029, VAN-PKT-030, VAN-PKT-084, VAN-PKT-085, VAN-PKT-031, VAN-PKT-032, VAN-PKT-081, VAN-PKT-082, VAN-PKT-037, VAN-PKT-038, VAN-PKT-043, VAN-PKT-045, VAN-PKT-046, VAN-PKT-047, VAN-PKT-049, VAN-PKT-050, VAN-PKT-051, VAN-PKT-052, VAN-PKT-053, VAN-PKT-054, VAN-PKT-055, VAN-PKT-056, VAN-PKT-057, VAN-PKT-058, VAN-PKT-059, VAN-PKT-060, VAN-PKT-061, VAN-PKT-062, VAN-PKT-063, VAN-PKT-064, VAN-PKT-065, VAN-PKT-066, VAN-PKT-068, VAN-PKT-069, VAN-PKT-070, VAN-PKT-071, VAN-PKT-072, VAN-PKT-073, VAN-PKT-074, VAN-PKT-075, VAN-PKT-076, VAN-PKT-077, VAN-PKT-078, VAN-PKT-079, VAN-PKT-080, VAN-PKT-083 |
| VAN-PKT-091 | BQ-008 | BACKEND_VERIFICATION | Independent chain-provider, security and finality qualification | VAN-PKT-039, VAN-PKT-040, VAN-PKT-041, VAN-PKT-042, VAN-PKT-048, VAN-PKT-044, VAN-PKT-067, VAN-PKT-082 |
| VAN-PKT-092 | VAN-ML-PKT-030 | BACKEND_VERIFICATION | Reproducible forecast and economic qualification reports | VAN-PKT-004, VAN-PKT-082, VAN-PKT-003, VAN-PKT-047, VAN-PKT-049, VAN-PKT-059, VAN-PKT-060, VAN-PKT-064, VAN-PKT-065, VAN-PKT-066, VAN-PKT-080, VAN-PKT-083 |
| VAN-PKT-093 | VAN-ML-PKT-031 | BACKEND_VERIFICATION | Prospective shadow and controlled sandbox admission | VAN-PKT-004, VAN-PKT-003, VAN-PKT-068, VAN-PKT-069, VAN-PKT-092 |
| VAN-PKT-094 | BQ-007 | BACKEND_VERIFICATION | Independent Opus remediation, evaluator and signed-risk regression qualification | VAN-PKT-032, VAN-PKT-081, VAN-PKT-092, VAN-PKT-093 |
| VAN-PKT-095 | BQ-009 | BACKEND_VERIFICATION | Independent economics, cohort, evidence and advisory-authority qualification | VAN-PKT-082, VAN-PKT-032, VAN-PKT-081, VAN-PKT-092, VAN-PKT-093 |
| VAN-PKT-096 | VAN-ML-PKT-032 | BACKEND_VERIFICATION | Independent additive backend closure | VAN-PKT-004, VAN-PKT-003, VAN-PKT-037, VAN-PKT-038, VAN-PKT-043, VAN-PKT-045, VAN-PKT-046, VAN-PKT-047, VAN-PKT-049, VAN-PKT-050, VAN-PKT-051, VAN-PKT-052, VAN-PKT-053, VAN-PKT-054, VAN-PKT-055, VAN-PKT-056, VAN-PKT-057, VAN-PKT-058, VAN-PKT-059, VAN-PKT-060, VAN-PKT-061, VAN-PKT-062, VAN-PKT-063, VAN-PKT-064, VAN-PKT-065, VAN-PKT-066, VAN-PKT-068, VAN-PKT-069, VAN-PKT-092, VAN-PKT-093, VAN-PKT-070, VAN-PKT-071, VAN-PKT-072, VAN-PKT-073, VAN-PKT-074, VAN-PKT-075, VAN-PKT-076, VAN-PKT-077, VAN-PKT-078, VAN-PKT-079, VAN-PKT-080, VAN-PKT-083 |
| VAN-PKT-097 | BQ-006 | BACKEND_VERIFICATION | Whole-product backend feature/action/caller and independent Zuul audit | VAN-PKT-086, VAN-PKT-087, VAN-PKT-088, VAN-PKT-089, VAN-PKT-090, VAN-PKT-094, VAN-PKT-091, VAN-PKT-095, VAN-PKT-096 |
| VAN-PKT-098 | BG-001 | BACKEND_GATE | Global Backend Complete / Frontend Entry Certificate | VAN-PKT-004, VAN-PKT-005, VAN-PKT-006, VAN-PKT-007, VAN-PKT-008, VAN-PKT-009, VAN-PKT-010, VAN-PKT-011, VAN-PKT-012, VAN-PKT-013, VAN-PKT-014, VAN-PKT-015, VAN-PKT-033, VAN-PKT-016, VAN-PKT-017, VAN-PKT-034, VAN-PKT-035, VAN-PKT-018, VAN-PKT-019, VAN-PKT-020, VAN-PKT-021, VAN-PKT-036, VAN-PKT-022, VAN-PKT-023, VAN-PKT-024, VAN-PKT-025, VAN-PKT-026, VAN-PKT-027, VAN-PKT-028, VAN-PKT-029, VAN-PKT-030, VAN-PKT-084, VAN-PKT-085, VAN-PKT-031, VAN-PKT-032, VAN-PKT-081, VAN-PKT-039, VAN-PKT-040, VAN-PKT-041, VAN-PKT-042, VAN-PKT-048, VAN-PKT-044, VAN-PKT-067, VAN-PKT-082, VAN-PKT-086, VAN-PKT-087, VAN-PKT-088, VAN-PKT-089, VAN-PKT-090, VAN-PKT-097, VAN-PKT-094, VAN-PKT-091, VAN-PKT-095, VAN-PKT-037, VAN-PKT-038, VAN-PKT-043, VAN-PKT-045, VAN-PKT-046, VAN-PKT-047, VAN-PKT-049, VAN-PKT-050, VAN-PKT-051, VAN-PKT-052, VAN-PKT-053, VAN-PKT-054, VAN-PKT-055, VAN-PKT-056, VAN-PKT-057, VAN-PKT-058, VAN-PKT-059, VAN-PKT-060, VAN-PKT-061, VAN-PKT-062, VAN-PKT-063, VAN-PKT-064, VAN-PKT-065, VAN-PKT-066, VAN-PKT-068, VAN-PKT-069, VAN-PKT-092, VAN-PKT-093, VAN-PKT-096, VAN-PKT-070, VAN-PKT-071, VAN-PKT-072, VAN-PKT-073, VAN-PKT-074, VAN-PKT-075, VAN-PKT-076, VAN-PKT-077, VAN-PKT-078, VAN-PKT-079, VAN-PKT-080, VAN-PKT-083 |
| VAN-PKT-099 | UX-001 | FRONTEND_DESIGN | Full-product information architecture from the complete backend | VAN-PKT-098 |
| VAN-PKT-100 | UX-002 | FRONTEND_DESIGN | Locked dark/light native material and component goldens | VAN-PKT-098, VAN-PKT-099 |
| VAN-PKT-101 | UX-003 | FRONTEND_DESIGN | Every-screen and action design contract acceptance | VAN-PKT-098, VAN-PKT-099, VAN-PKT-100 |
| VAN-PKT-102 | FE-001 | FRONTEND | Native typed ports, reactive client store, offline cache and device plumbing | VAN-PKT-098, VAN-PKT-101 |
| VAN-PKT-103 | FE-002 | FRONTEND | Tactile Spatial components, tokens, isolation and accessibility semantics | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102 |
| VAN-PKT-104 | FE-003 | FRONTEND | Adaptive shell, deep links, shared intakes and full navigation | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103 |
| VAN-PKT-105 | FE-004 | FRONTEND | Home, metallic orb, compact Quick Hub and Attention | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-106 | FE-005 | FRONTEND | Floating VAN, gestures, dock/workboards and lifecycle | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-107 | FE-006 | FRONTEND | Trading Home, Markets, Watchlists, screener and Alerts | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-108 | FE-007 | FRONTEND | Native previews and professional chart renderer/bridge | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-109 | FE-008 | FRONTEND | Indicators, drawings, workspaces, depth and replay controls | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104, VAN-PKT-108 |
| VAN-PKT-110 | FE-009 | FRONTEND | Orders, manual review, positions, protection and handover | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-111 | FE-010 | FRONTEND | Accounts and Funds, provider-hosted flows and receipts | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-112 | FE-011 | FRONTEND | Portfolio, history, statements, TCA and Risk Command Centre | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-113 | FE-012 | FRONTEND | Strategies, trading modes and evidence/promotion views | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-114 | FE-013 | FRONTEND | News, calendar, history profiles and armed news ticket views | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-115 | FE-014 | FRONTEND | Analyst, chart observations, behaviour diagnostics and research | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-116 | FE-015 | FRONTEND | Work, Projects, tasks and live dependency diagrams | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-117 | FE-016 | FRONTEND | Agents, Muse/Hermes interactions and handoff maps | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-118 | FE-017 | FRONTEND | Browser/remote sessions, files, share and provider outcome views | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-119 | FE-018 | FRONTEND | ARTEMIS, development/studio, CI/security and evidence workspaces | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-120 | FE-019 | FRONTEND | Memory, citations, privacy/erasure, learning goals and adaptations | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-121 | FE-020 | FRONTEND | Automation, reminders, standing permissions and schedules | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-122 | FE-021 | FRONTEND | Conversation, voice and speaker consent workflows | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-123 | FE-022 | FRONTEND | Connected, settings, device provisioning, notifications and diagnostics | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104 |
| VAN-PKT-124 | FE-023 | FRONTEND | Native model, strategy-development and prediction-research views | VAN-PKT-098, VAN-PKT-101, VAN-PKT-102, VAN-PKT-103, VAN-PKT-104, VAN-PKT-113, VAN-PKT-114, VAN-PKT-115 |
| VAN-PKT-125 | QA-001 | FINAL_QUALIFICATION | All-feature/surface/action parity and no-loss reverse coverage | VAN-PKT-102, VAN-PKT-103, VAN-PKT-104, VAN-PKT-105, VAN-PKT-106, VAN-PKT-107, VAN-PKT-108, VAN-PKT-109, VAN-PKT-110, VAN-PKT-111, VAN-PKT-112, VAN-PKT-113, VAN-PKT-114, VAN-PKT-115, VAN-PKT-116, VAN-PKT-117, VAN-PKT-118, VAN-PKT-119, VAN-PKT-120, VAN-PKT-121, VAN-PKT-122, VAN-PKT-123, VAN-PKT-124 |
| VAN-PKT-126 | QA-002 | FINAL_QUALIFICATION | Real gateway/provider integration through the new signed app | VAN-PKT-102, VAN-PKT-103, VAN-PKT-104, VAN-PKT-105, VAN-PKT-106, VAN-PKT-107, VAN-PKT-108, VAN-PKT-109, VAN-PKT-110, VAN-PKT-111, VAN-PKT-112, VAN-PKT-113, VAN-PKT-114, VAN-PKT-115, VAN-PKT-116, VAN-PKT-117, VAN-PKT-118, VAN-PKT-119, VAN-PKT-120, VAN-PKT-121, VAN-PKT-122, VAN-PKT-123, VAN-PKT-124 |
| VAN-PKT-127 | QA-003 | FINAL_QUALIFICATION | Cross-domain adversarial security, authority and recovery | VAN-PKT-102, VAN-PKT-103, VAN-PKT-104, VAN-PKT-105, VAN-PKT-106, VAN-PKT-107, VAN-PKT-108, VAN-PKT-109, VAN-PKT-110, VAN-PKT-111, VAN-PKT-112, VAN-PKT-113, VAN-PKT-114, VAN-PKT-115, VAN-PKT-116, VAN-PKT-117, VAN-PKT-118, VAN-PKT-119, VAN-PKT-120, VAN-PKT-121, VAN-PKT-122, VAN-PKT-123, VAN-PKT-124 |
| VAN-PKT-128 | QA-004 | FINAL_QUALIFICATION | Physical S24 performance, thermal, accessibility and both-theme visual acceptance | VAN-PKT-102, VAN-PKT-103, VAN-PKT-104, VAN-PKT-105, VAN-PKT-106, VAN-PKT-107, VAN-PKT-108, VAN-PKT-109, VAN-PKT-110, VAN-PKT-111, VAN-PKT-112, VAN-PKT-113, VAN-PKT-114, VAN-PKT-115, VAN-PKT-116, VAN-PKT-117, VAN-PKT-118, VAN-PKT-119, VAN-PKT-120, VAN-PKT-121, VAN-PKT-122, VAN-PKT-123, VAN-PKT-124 |
| VAN-PKT-129 | QA-005 | FINAL_QUALIFICATION | Independent Zuul, exact APK and whole-product owner acceptance | VAN-PKT-125, VAN-PKT-126, VAN-PKT-127, VAN-PKT-128 |
| VAN-PKT-130 | REL-001 | RELEASE | Controlled signed release and proven rollback | VAN-PKT-129 |
| VAN-PKT-131 | REL-002 | RETIREMENT | Legacy presentation retirement after full parity | VAN-PKT-130 |

## 4. Source-plan reconciliation

The 76 parent Rev1.10 units and all 48 forecast packet obligations are preserved or explicitly merged. Old packet IDs are lookup aliases only. There is one F15, one global frontend-opening BG and one release chain. No child closure can authorize UI.

| Source forecast packet | Canonical unit | Current packet | Disposition |
|---|---|---|---|
| VAN-ML-PKT-001 | PRE-001 | VAN-PKT-001 | MERGED_SAME_OBLIGATION_NO_DUPLICATE_GATE |
| VAN-ML-PKT-002 | PRE-002 | VAN-PKT-002 | MERGED_SAME_OBLIGATION_NO_DUPLICATE_GATE |
| VAN-ML-PKT-003 | PRE-003 | VAN-PKT-003 | MERGED_SAME_OBLIGATION_NO_DUPLICATE_GATE |
| VAN-ML-PKT-004 | VAN-ML-PKT-004 | VAN-PKT-037 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-005 | VAN-ML-PKT-005 | VAN-PKT-038 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-006 | VAN-ML-PKT-006 | VAN-PKT-043 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-037 | VAN-ML-PKT-037 | VAN-PKT-070 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-007 | VAN-ML-PKT-007 | VAN-PKT-045 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-038 | VAN-ML-PKT-038 | VAN-PKT-071 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-039 | VAN-ML-PKT-039 | VAN-PKT-072 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-008 | VAN-ML-PKT-008 | VAN-PKT-046 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-009 | VAN-ML-PKT-009 | VAN-PKT-047 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-040 | VAN-ML-PKT-040 | VAN-PKT-073 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-010 | VAN-ML-PKT-010 | VAN-PKT-049 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-011 | VAN-ML-PKT-011 | VAN-PKT-050 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-012 | VAN-ML-PKT-012 | VAN-PKT-051 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-013 | VAN-ML-PKT-013 | VAN-PKT-052 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-014 | VAN-ML-PKT-014 | VAN-PKT-053 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-015 | VAN-ML-PKT-015 | VAN-PKT-054 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-016 | VAN-ML-PKT-016 | VAN-PKT-055 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-044 | VAN-ML-PKT-044 | VAN-PKT-077 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-017 | VAN-ML-PKT-017 | VAN-PKT-056 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-018 | VAN-ML-PKT-018 | VAN-PKT-057 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-045 | VAN-ML-PKT-045 | VAN-PKT-078 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-019 | VAN-ML-PKT-019 | VAN-PKT-058 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-020 | VAN-ML-PKT-020 | VAN-PKT-059 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-021 | VAN-ML-PKT-021 | VAN-PKT-060 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-041 | VAN-ML-PKT-041 | VAN-PKT-074 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-022 | VAN-ML-PKT-022 | VAN-PKT-061 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-023 | VAN-ML-PKT-023 | VAN-PKT-062 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-024 | VAN-ML-PKT-024 | VAN-PKT-063 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-025 | VAN-ML-PKT-025 | VAN-PKT-064 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-026 | VAN-ML-PKT-026 | VAN-PKT-065 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-042 | VAN-ML-PKT-042 | VAN-PKT-075 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-027 | VAN-ML-PKT-027 | VAN-PKT-066 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-043 | VAN-ML-PKT-043 | VAN-PKT-076 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-046 | VAN-ML-PKT-046 | VAN-PKT-079 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-028 | VAN-ML-PKT-028 | VAN-PKT-068 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-047 | VAN-ML-PKT-047 | VAN-PKT-080 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-029 | VAN-ML-PKT-029 | VAN-PKT-069 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-048 | VAN-ML-PKT-048 | VAN-PKT-083 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-030 | VAN-ML-PKT-030 | VAN-PKT-092 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-031 | VAN-ML-PKT-031 | VAN-PKT-093 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-032 | VAN-ML-PKT-032 | VAN-PKT-096 | ADOPT_FULL_BACKEND_CONTRACT |
| VAN-ML-PKT-033 | BG-001 | VAN-PKT-098 | MERGED_SAME_OBLIGATION_NO_DUPLICATE_GATE |
| VAN-ML-PKT-034 | FE-023 | VAN-PKT-124 | MERGED_SAME_OBLIGATION_NO_DUPLICATE_GATE |
| VAN-ML-PKT-035 | QA-005 | VAN-PKT-129 | MERGED_SAME_OBLIGATION_NO_DUPLICATE_GATE |
| VAN-ML-PKT-036 | REL-001 | VAN-PKT-130 | MERGED_SAME_OBLIGATION_NO_DUPLICATE_GATE |

## 5. Exact per-packet completion contracts

### VAN-PKT-001 — PRE-001: Read-only complete evidence and feature inventory
**Kind/stage:** PREDEVELOPMENT / 0. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** read-only source access and approved packet scope.
**Requirement owners:** VAN-CX-002, VAN-HVA-002, VAN-ML-REQ-001, VAN-NX-071, VAN-NX-BF-015.

**Exit contract:** Frozen source hashes, complete function/branch ledger, classification and provenance. Current instruction permits document/evidence preparation, not a claim that formal packet approval or signature has occurred.

**All deliverables:**
- Revalidate the 66-head inventory and exact feature-bearing blobs; inspect changes since the sealed review rather than assume a branch name implies code.

**Merged obligation VAN-ML-PKT-001:**
- Freeze main and every relevant feature-bearing candidate branch; compare parent Rev1.10 and current source
- Create function-level retain/adapt/replace/extend mapping, existing conformal and feature ownership, provider/asset scope and licence provenance
- Write proposed additive-to-parent requirement and packet patch without modifying signed parent inputs
- Reconcile prediction-market parent §8.2/§8.4/§8.5, VAN-NX-036 and actual NewsIngress/CalendarRecorder owners; keep source observations dated.
- Evidence: Independently reviewed no-loss mapping, source hashes and conflict register
- Evidence: A missing inherited action or PR-only feature must invalidate the proposed merge

**Planned test obligations (all NOT_RUN):**
- `T-NX-071` — No source change; every ledger row classified with provenance
- `T-BF-015` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `VAN-ML-AT-001-P` — Reconcile parent/source/candidate hashes and all touched functions.
- `VAN-ML-AT-001-N` — Remove one inherited action or ignore a selected branch: scope admission fails.
- `T-VAN-CX-002-POS` — Every changed implementation group and historical feature has a source-to-backend-to-screen-to-test chain.
- `T-VAN-CX-002-NEG` — Delete a PR-only action, discard a complete candidate branch without dispositions, or report an inferred effect as observed: reject.
- `T-VAN-CX-002-REC` — Cherry-pick or port bounded accepted changes onto the canonical implementation lineage only after F15 and source admission; keep rollback to exact source.
- `T-HVA-002-POS` — Resolve each overlap using immutable source hashes, caller-level comparison and scoped positive regression evidence in an isolated worktree.
- `T-HVA-002-NEG` — Choose one account_service variant and silently discard a valid Jev, temperament, pending-order or lockout behavior; the preservation oracle fails.
- `T-HVA-002-REC` — If any advertised head changes, retain the prior inventory, invalidate affected source mappings and regenerate only the affected comparison before resuming.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-002 — PRE-002: Whole-product semantic reconciliation and packet contracts
**Kind/stage:** PREDEVELOPMENT / 0. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** PRE-001.
**Requirement owners:** VAN-CX-001, VAN-CX-002, VAN-CX-015, VAN-HVA-001, VAN-HVA-002, VAN-HVA-003, VAN-HVA-032, VAN-ML-REQ-002, VAN-NX-026, VAN-NX-053, VAN-NX-BF-003, VAN-NX-BF-004, VAN-NX-BF-018.

**Exit contract:** 171 atoms,115 contexts,78 surfaces,349 actions,71 inherited requirements and new backend-first clauses all author-reviewed and independently challenged; exact owner decisions and schema/authority contracts resolved where prerequisite.

**All deliverables:**
- Independently admit HVA R01–R12 mappings, separate research-source and implementation evidence namespaces, and all retained requirements before F15.

**Merged obligation VAN-ML-PKT-002:**
- Admit TargetSpecs, cohort/universe definitions, permitted data, validation protocol and research budgets
- Resolve runtime consumers, status/error semantics, numerical boundaries and authority contracts
- Pre-register all required model families, tests, losses, baselines and final holdout access policy
- Apply current no-procurement and Netcup/Oracle owner scope; neither source licence purchases nor direct event-contract eligibility is a prerequisite for adapter/fixture development.
- Evidence: All affected owner decisions identified by exact scope and gate
- Evidence: No unresolved START prerequisite hidden by a default; no application PASS claims

**Planned test obligations (all NOT_RUN):**
- `T-NX-026` — Research-input admission record (`RESEARCH_INPUT_ACCEPTANCE.json`): the 39 REA record IDs and hashes, APK identities, static-only limits and owner acknowledgement; DU-27 supplies the research
- `T-NX-053` — §17 F0; Feature Ledger reconciled with Product Truth; record signed (OQ-05)
- `T-BF-003` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `T-BF-004` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `T-BF-018` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `VAN-ML-AT-002-P` — Admit an internally coherent research profile and signed scope references.
- `VAN-ML-AT-002-N` — An unspecified live budget or data entitlement cannot be filled with a guessed value.
- `T-VAN-CX-001-POS` — The generated graph and its source-scope digest determine one reproducible sequence.
- `T-VAN-CX-001-NEG` — Select the old mixed plan, omit a backend producer, or reclassify a chart renderer as backend: reject.
- `T-VAN-CX-001-REC` — A relevant source, policy or scope amendment invalidates affected receipts and BG-001 without erasing historical evidence.
- `T-VAN-CX-002-POS` — Every changed implementation group and historical feature has a source-to-backend-to-screen-to-test chain.
- `T-VAN-CX-002-NEG` — Delete a PR-only action, discard a complete candidate branch without dispositions, or report an inferred effect as observed: reject.
- `T-VAN-CX-002-REC` — Cherry-pick or port bounded accepted changes onto the canonical implementation lineage only after F15 and source admission; keep rollback to exact source.
- `T-VAN-CX-015-POS` — A pre-signed ticket arms only in its declared readiness envelope and can claim the nonce once.
- `T-VAN-CX-015-NEG` — Empty proof, arbitrary real proof label, proof for another account/event, re-signed weakened allowlist or concurrent duplicate use: reject.
- `T-VAN-CX-015-REC` — Arming and consuming a grant are not a broker fill; unknown submission follows the order reconciler, never a second order.
- `T-HVA-001-POS` — Exercise each required train/export/load/predict or event-laboratory operation through its real registered consumer; record a truthful rejected or inconclusive economic result when appropriate.
- `T-HVA-001-NEG` — Remove DeepAR, a required challenger plugin or an event-research laboratory and attempt complete-backend admission; missing capability must be detected.
- `T-HVA-001-REC` — Restore a previous model package without dropping any mandatory API or laboratory; stale economic permission remains inactive.
- `T-HVA-002-POS` — Resolve each overlap using immutable source hashes, caller-level comparison and scoped positive regression evidence in an isolated worktree.
- `T-HVA-002-NEG` — Choose one account_service variant and silently discard a valid Jev, temperament, pending-order or lockout behavior; the preservation oracle fails.
- `T-HVA-002-REC` — If any advertised head changes, retain the prior inventory, invalidate affected source mappings and regenerate only the affected comparison before resuming.
- `T-HVA-003-POS` — Load known legacy categories with their original schema and retain separate source-quality and implementation states without promotion.
- `T-HVA-003-NEG` — Submit a vendor capability or creator screenshot as E3 TEST_RECEIPT or E5 DEVICE_CERTIFIED; reject the claim.
- `T-HVA-003-REC` — After schema upgrade or rollback, replay original grades with their namespace and origin; unresolved legacy rows never acquire authority.
- `T-HVA-032-POS` — Trace every additive obligation through producer, store, consumer, packet, tests, evidence and eventual owner surface; verify all required backends precede the sole BG.
- `T-HVA-032-NEG` — Open M8 UI after one feed, drop an inherited requirement, silently reuse changed packet numbers or self-issue a gate; reject.
- `T-HVA-032-REC` — Scope changes regenerate signed-input candidates and invalidate affected downstream certificates while preserving all original artefacts and revision-qualified aliases.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-003 — PRE-003: Independent DIAL F0–F15 build-ready certification
**Kind/stage:** PREDEVELOPMENT_GATE / 0. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** PRE-002.
**Requirement owners:** VAN-CX-001, VAN-CX-019, VAN-HVA-032, VAN-ML-REQ-003, VAN-NX-070, VAN-NX-BF-009, VAN-NX-BF-011.

**Exit contract:** Independent verifier issues current project-scoped F15; all preparation blockers closed; owner signature valid. No Android or production readiness claim.

**Merged obligation VAN-ML-PKT-003:**
- Integrate amended requirements into the parent predevelopment evidence and obtain genuine independent F15 for the admitted source/scope
- Register all code-bearing child packets and parent dependency changes
- Evidence: Trusted issuer verifies exact source/scope and owner signature
- Evidence: A generated JSON PASS, hash or this pack checker cannot issue F15

**Planned test obligations (all NOT_RUN):**
- `T-NX-070` — Certificate by an independent verifier; a code-bearing packet whose unit does not depend on DU-31 fails generation (induced)
- `T-BF-009` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `T-BF-011` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `VAN-ML-AT-003-P` — Validate actual external gate receipt with trusted issuer at execution.
- `VAN-ML-AT-003-N` — A local PASS JSON or document hash alone fails entry.
- `T-VAN-CX-001-POS` — The generated graph and its source-scope digest determine one reproducible sequence.
- `T-VAN-CX-001-NEG` — Select the old mixed plan, omit a backend producer, or reclassify a chart renderer as backend: reject.
- `T-VAN-CX-001-REC` — A relevant source, policy or scope amendment invalidates affected receipts and BG-001 without erasing historical evidence.
- `T-VAN-CX-019-POS` — The complete pack rebuilds identically and invalid evidence cannot change readiness.
- `T-VAN-CX-019-NEG` — Edit input and matching local hash, delete a receipt, swap source revision, self-declare signature_valid, or reuse device evidence across builds: block readiness.
- `T-VAN-CX-019-REC` — Record revoked/stale evidence; regenerate affected planning fingerprints and rerun relevant tests without erasing old records.
- `T-HVA-032-POS` — Trace every additive obligation through producer, store, consumer, packet, tests, evidence and eventual owner surface; verify all required backends precede the sole BG.
- `T-HVA-032-NEG` — Open M8 UI after one feed, drop an inherited requirement, silently reuse changed packet numbers or self-issue a gate; reject.
- `T-HVA-032-REC` — Scope changes regenerate signed-input candidates and invalidate affected downstream certificates while preserving all original artefacts and revision-qualified aliases.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-004 — BE-001: Source consolidation and preservation oracle
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** PRE-003.
**Requirement owners:** VAN-CX-002, VAN-HVA-002, VAN-NX-023, VAN-NX-028, VAN-NX-029, VAN-NX-039, VAN-NX-BF-012.

**Exit contract:** admit exact feature-bearing diffs; retain old app unchanged; register every provider caller; construct and falsify parity oracle. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Remove a PR-only action: parity fails; unreviewed duplicate implementation cannot merge

**All deliverables:**
- Reconcile the five account coordinator/service variants by function and contract, preserving PR101 fixes, canon Jev/evidence and signed temperament work. Never wholesale-select the most populated branch.
- Admit PR98/99 mobile/site owner contracts and visual producer roles separately from full backend; prohibit old CSS/Compose inheritance
- Refresh all 66 branch heads, preserve 78/349 owner actions, record exact source identity and independent test

**Planned test obligations (all NOT_RUN):**
- `T-BE-001-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-001-NEG` — Remove a PR-only action: parity fails; unreviewed duplicate implementation cannot merge
- `T-BE-001-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-001-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-001-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-NX-028` — Parity checker fails on an induced omission. Needs: DU-00a, DU-31
- `T-BF-012` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `T-VAN-CX-002-POS` — Every changed implementation group and historical feature has a source-to-backend-to-screen-to-test chain.
- `T-VAN-CX-002-NEG` — Delete a PR-only action, discard a complete candidate branch without dispositions, or report an inferred effect as observed: reject.
- `T-VAN-CX-002-REC` — Cherry-pick or port bounded accepted changes onto the canonical implementation lineage only after F15 and source admission; keep rollback to exact source.
- `T-HVA-002-POS` — Resolve each overlap using immutable source hashes, caller-level comparison and scoped positive regression evidence in an isolated worktree.
- `T-HVA-002-NEG` — Choose one account_service variant and silently discard a valid Jev, temperament, pending-order or lockout behavior; the preservation oracle fails.
- `T-HVA-002-REC` — If any advertised head changes, retain the prior inventory, invalidate affected source mappings and regenerate only the affected comparison before resuming.
- `T-REV113-001` — Function-level admission across 66 branch heads: missing PR98 or PR99 owner feature blocks backend parity

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-005 — BE-002: Device identity, bounded authority and intent fencing
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003.
**Requirement owners:** VAN-CX-009, VAN-CX-015, VAN-NX-007, VAN-NX-021, VAN-NX-023, VAN-NX-029, VAN-NX-039, VAN-NX-077.

**Exit contract:** pair/provision/revoke; validate signed exact intents; issue challenges; expire and fence sessions; protect account and task scopes. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Replayed nonce, cross-device signature, stale mandate or changed arguments refuse before effect

**Planned test obligations (all NOT_RUN):**
- `T-BE-002-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-002-NEG` — Replayed nonce, cross-device signature, stale mandate or changed arguments refuse before effect
- `T-BE-002-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-002-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-002-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-NX-077` — §7.4.15 lockout design; induced: no expiry, legacy top floor, no rebuild, manual counted in the account scope, no probation and unconditional baseline restore each fail a test
- `T-VAN-CX-009-POS` — Restart replays the same locks; independent manual/autonomous cooldown tests coexist with shared all-origin hard-limit tests.
- `T-VAN-CX-009-NEG` — A restart resets losses, a default silently changes a signed policy, a manual entry bypasses total-account drawdown, or an owner reset erases economic loss: reject.
- `T-VAN-CX-009-REC` — A signed reset changes a permission state or risk reference with an audit event, never the immutable economic performance history; unknown policy/collateral blocks new risk.
- `T-VAN-CX-015-POS` — A pre-signed ticket arms only in its declared readiness envelope and can claim the nonce once.
- `T-VAN-CX-015-NEG` — Empty proof, arbitrary real proof label, proof for another account/event, re-signed weakened allowlist or concurrent duplicate use: reject.
- `T-VAN-CX-015-REC` — Arming and consuming a grant are not a broker fill; unknown submission follows the order reconciler, never a second order.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-006 — BE-003: Durable event, readback and projection infrastructure
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-002, PRE-003.
**Requirement owners:** VAN-CX-006, VAN-CX-008, VAN-HVA-003, VAN-NX-021, VAN-NX-023, VAN-NX-029, VAN-NX-039, VAN-NX-040, VAN-NX-073.

**Exit contract:** append events; deduplicate; process outbox; serve cursor snapshots; reconcile uncertain outcomes; redact evidence. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Crash after external submission, duplicate delivery, source-epoch change and out-of-order readback never duplicate an effect

**Planned test obligations (all NOT_RUN):**
- `T-BE-003-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-003-NEG` — Crash after external submission, duplicate delivery, source-epoch change and out-of-order readback never duplicate an effect
- `T-BE-003-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-003-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-003-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-NX-073` — §7.4.15 #1; induced: a tampered new row, a re-chained old row and a deleted row are caught at once; an in-place old-row edit is caught by the next full verification
- `T-VAN-CX-006-POS` — EXPIRED, CANCELLED and REJECTED unfilled orders disappear from working-order totals but remain in historical records; partial positions retain actual exposure.
- `T-VAN-CX-006-NEG` — A stale ACCEPTED receipt after terminal readback must not resurrect Working; duplicate fill/cancel events must not double-count.
- `T-VAN-CX-006-REC` — Snapshot replay produces the same positions, orders, reservations and summaries after restart.
- `T-VAN-CX-008-POS` — New-row work scales with appended records while honest replay matches full verification in SQLite and Postgres.
- `T-VAN-CX-008-NEG` — Tamper, truncate, fork, roll back, replace a ledger or supply a stale checkpoint: fail closed and force full verification. The research always-True monkeypatch is forbidden.
- `T-VAN-CX-008-REC` — Checkpoints are rebuilt or verified after restart; concurrency and interrupted checkpoint writes cannot leave risk operating on untrusted state.
- `T-HVA-003-POS` — Load known legacy categories with their original schema and retain separate source-quality and implementation states without promotion.
- `T-HVA-003-NEG` — Submit a vendor capability or creator screenshot as E3 TEST_RECEIPT or E5 DEVICE_CERTIFIED; reject the claim.
- `T-HVA-003-REC` — After schema upgrade or rollback, replay original grades with their namespace and origin; unresolved legacy rows never acquire authority.
- `T-REV113-002` — Incremental ledger checkpoint hash/replay is monotonic; tamper and truncation fail, no O(n) scan per tick

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-007 — BE-004: Accounts, broker directory and operation capabilities
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-002, BE-003, PRE-003.
**Requirement owners:** VAN-CX-016, VAN-NX-048, VAN-NX-049, VAN-NX-050, VAN-NX-056, VAN-NX-057, VAN-NX-064.

**Exit contract:** discover; create demo; request live application; link; edit local/profile where entitled; restrict; unlink; request remote closure. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Local unlink never reports remote closure; active exposure, unknown funds or stale readback blocks deletion

**Planned test obligations (all NOT_RUN):**
- `T-BE-004-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-004-NEG` — Local unlink never reports remote closure; active exposure, unknown funds or stale readback blocks deletion
- `T-BE-004-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-004-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-004-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-VAN-CX-016-POS` — Deposit/withdrawal/credit/fee and pending-order interleavings reconcile exact money, positions and risk without false P&L.
- `T-VAN-CX-016-NEG` — Redirect settles money, a timeout resubmits, deleting restores secrets, unclassified flow silently improves risk capital, or a withdrawal bypasses concurrent reservations: reject.
- `T-VAN-CX-016-REC` — Rollback never erases financial events; credential cancellation returns RELINK_REQUIRED and broker closure remains independently verified.
- `T-REV113-003` — Investor/read-only and live account capability never inherit trade or payment authority from a linked UI

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-008 — BE-005: Broker authentication, credential rotation and health
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-004, PRE-003.
**Requirement owners:** VAN-CX-016, VAN-NX-048, VAN-NX-049, VAN-NX-050, VAN-NX-056, VAN-NX-057, VAN-NX-064.

**Exit contract:** OAuth start/callback/cancel/recover; discover accounts; rotate and verify secrets; renew; detect migration; QR bridge pairing. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Process death, callback collision, expired token, investor read-only credential and failed swap remain fail closed

**Planned test obligations (all NOT_RUN):**
- `T-BE-005-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-005-NEG` — Process death, callback collision, expired token, investor read-only credential and failed swap remain fail closed
- `T-BE-005-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-005-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-005-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-VAN-CX-016-POS` — Deposit/withdrawal/credit/fee and pending-order interleavings reconcile exact money, positions and risk without false P&L.
- `T-VAN-CX-016-NEG` — Redirect settles money, a timeout resubmits, deleting restores secrets, unclassified flow silently improves risk capital, or a withdrawal bypasses concurrent reservations: reject.
- `T-VAN-CX-016-REC` — Rollback never erases financial events; credential cancellation returns RELINK_REQUIRED and broker closure remains independently verified.
- `T-REV113-004` — Broker OAuth callback survives restart and revocation without replay or leaking secrets

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-009 — BE-006: Exact funding ledger and flow-adjusted accounting
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-003, BE-004, PRE-003.
**Requirement owners:** VAN-CX-009, VAN-CX-016, VAN-NX-051, VAN-NX-059, VAN-NX-077.

**Exit contract:** ingest provider cash movements; classify and reconcile; post reversals; calculate flow-adjusted returns/drawdown; expose statement lineage. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Withdrawals are not losses; deposits do not erase losses; unknown or non-withdrawable credit is not risk capital

**Planned test obligations (all NOT_RUN):**
- `T-BE-006-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-006-NEG` — Withdrawals are not losses; deposits do not erase losses; unknown or non-withdrawable credit is not risk capital
- `T-BE-006-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-006-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-006-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-VAN-CX-009-POS` — Restart replays the same locks; independent manual/autonomous cooldown tests coexist with shared all-origin hard-limit tests.
- `T-VAN-CX-009-NEG` — A restart resets losses, a default silently changes a signed policy, a manual entry bypasses total-account drawdown, or an owner reset erases economic loss: reject.
- `T-VAN-CX-009-REC` — A signed reset changes a permission state or risk reference with an audit event, never the immutable economic performance history; unknown policy/collateral blocks new risk.
- `T-VAN-CX-016-POS` — Deposit/withdrawal/credit/fee and pending-order interleavings reconcile exact money, positions and risk without false P&L.
- `T-VAN-CX-016-NEG` — Redirect settles money, a timeout resubmits, deleting restores secrets, unclassified flow silently improves risk capital, or a withdrawal bypasses concurrent reservations: reject.
- `T-VAN-CX-016-REC` — Rollback never erases financial events; credential cancellation returns RELINK_REQUIRED and broker closure remains independently verified.
- `T-REV113-005` — Deposits and withdrawals are excluded from drawdown and TWR; unclassified provider movements fail closed

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-010 — BE-007: Deposits, withdrawals, transfers and provider rails
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-005, BE-006, PRE-003.
**Requirement owners:** VAN-CX-016, VAN-NX-055.

**Exit contract:** quote; verify beneficiary; approve; reserve; submit; reconcile; settle; compensate; expose hosted handoff with verified origin. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Changed fees need new approval; redirect is not settlement; unknown send never blindly retries; simultaneous withdrawal/order reservations cannot overdraw margin

**Planned test obligations (all NOT_RUN):**
- `T-BE-007-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-007-NEG` — Changed fees need new approval; redirect is not settlement; unknown send never blindly retries; simultaneous withdrawal/order reservations cannot overdraw margin
- `T-BE-007-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-007-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-007-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-VAN-CX-016-POS` — Deposit/withdrawal/credit/fee and pending-order interleavings reconcile exact money, positions and risk without false P&L.
- `T-VAN-CX-016-NEG` — Redirect settles money, a timeout resubmits, deleting restores secrets, unclassified flow silently improves risk capital, or a withdrawal bypasses concurrent reservations: reject.
- `T-VAN-CX-016-REC` — Rollback never erases financial events; credential cancellation returns RELINK_REQUIRED and broker closure remains independently verified.
- `T-REV113-006` — Timed-out funding action is OUTCOME_UNKNOWN, no resubmission; provider settlement only on readback

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-011 — BE-008: Instrument identity, market feeds, bars and depth
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-003, BE-005, PRE-003.
**Requirement owners:** VAN-CX-004, VAN-CX-007, VAN-CX-012, VAN-NX-008, VAN-NX-009, VAN-NX-011, VAN-NX-040, VAN-NX-041, VAN-NX-042, VAN-NX-074, VAN-NX-075.

**Exit contract:** resolve aliases; discover tradable instruments; subscribe once; aggregate bars; revision snapshots; recover gaps; publish genuine depth. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Identical ticker with different contracts cannot collide; stale feed never returns synthetic LIVE; bad sequence triggers snapshot recovery

**Planned test obligations (all NOT_RUN):**
- `T-BE-008-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-008-NEG` — Identical ticker with different contracts cannot collide; stale feed never returns synthetic LIVE; bad sequence triggers snapshot recovery
- `T-BE-008-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-008-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-008-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-NX-074` — §7.4.15 #2; JPY and metals orders fill under normal slippage; slippage beyond the bound is still refused
- `T-NX-075` — §7.4.15 #3; randomised both-direction test; induced widening fails
- `T-VAN-CX-004-POS` — At-touch and gapped quote fixtures preserve the limit in both directions; explicit capped-market fixtures preserve their separate slippage envelope.
- `T-VAN-CX-004-NEG` — The current 1.10000 limit with 0.00010 spread and 0.00002 slippage must never fill a BUY at 1.10007 or a SELL at 1.09993.
- `T-VAN-CX-004-REC` — After a gap, respect limit/stop/stop-limit distinctions; missed fills are not fabricated to preserve historical backtest counts.
- `T-VAN-CX-007-POS` — FX, JPY, metals and alternative broker digit fixtures produce correct bounds from actual contract metadata and remain within the approved loss envelope.
- `T-VAN-CX-007-NEG` — Unknown digits, stale contract revision, a rounded stop beyond risk or below broker distance, or treating an old absolute cap as a new fraction: refuse.
- `T-VAN-CX-007-REC` — Quote or contract changes invalidate the preview; historical mandate/template versions replay with their original units.
- `T-VAN-CX-012-POS` — From permitted raw inputs, a second run reproduces the same bars, sessions, costs and outcomes.
- `T-VAN-CX-012-NEG` — Bid is silently treated as midpoint, fixed EST becomes DST-local time, a bar is used before close or a mirror is unpinned: reject qualifying use.
- `T-VAN-CX-012-REC` — Keep lawful metadata and reproducibility scripts without republishing restricted data; qualifying tests await admitted data while unrelated authorized engineering continues.
- `T-REV113-007` — Instrument tick/pip/multiplier/unit and bid/ask convention validated before risk approval for JPY and gold

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-012 — BE-009: Mandates, risk, sizing and portfolio reservations
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-002, BE-006, BE-008, PRE-003.
**Requirement owners:** VAN-CX-007, VAN-CX-008, VAN-CX-009, VAN-CX-016, VAN-NX-027, VAN-NX-051, VAN-NX-059, VAN-NX-074, VAN-NX-075, VAN-NX-076, VAN-NX-077.

**Exit contract:** verify mandate; calculate stop/size; reserve worst-case pending risk; enforce drawdown, concentration, correlation and margin; deny new entries while allow risk reduction. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. No float monetary sizing; rounding down; competing intents cannot exceed family/account limits; flow adjustment cannot increase absolute available collateral

**Planned test obligations (all NOT_RUN):**
- `T-BE-009-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-009-NEG` — No float monetary sizing; rounding down; competing intents cannot exceed family/account limits; flow adjustment cannot increase absolute available collateral
- `T-BE-009-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-009-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-009-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-NX-076` — §7.4.15 #4; induced: STOP→LIMIT refused, unsupported type refused, paper limit not filled away from the market; live STOP only after per-venue demo qualification
- `T-VAN-CX-007-POS` — FX, JPY, metals and alternative broker digit fixtures produce correct bounds from actual contract metadata and remain within the approved loss envelope.
- `T-VAN-CX-007-NEG` — Unknown digits, stale contract revision, a rounded stop beyond risk or below broker distance, or treating an old absolute cap as a new fraction: refuse.
- `T-VAN-CX-007-REC` — Quote or contract changes invalidate the preview; historical mandate/template versions replay with their original units.
- `T-VAN-CX-008-POS` — New-row work scales with appended records while honest replay matches full verification in SQLite and Postgres.
- `T-VAN-CX-008-NEG` — Tamper, truncate, fork, roll back, replace a ledger or supply a stale checkpoint: fail closed and force full verification. The research always-True monkeypatch is forbidden.
- `T-VAN-CX-008-REC` — Checkpoints are rebuilt or verified after restart; concurrency and interrupted checkpoint writes cannot leave risk operating on untrusted state.
- `T-VAN-CX-009-POS` — Restart replays the same locks; independent manual/autonomous cooldown tests coexist with shared all-origin hard-limit tests.
- `T-VAN-CX-009-NEG` — A restart resets losses, a default silently changes a signed policy, a manual entry bypasses total-account drawdown, or an owner reset erases economic loss: reject.
- `T-VAN-CX-009-REC` — A signed reset changes a permission state or risk reference with an audit event, never the immutable economic performance history; unknown policy/collateral blocks new risk.
- `T-VAN-CX-016-POS` — Deposit/withdrawal/credit/fee and pending-order interleavings reconcile exact money, positions and risk without false P&L.
- `T-VAN-CX-016-NEG` — Redirect settles money, a timeout resubmits, deleting restores secrets, unclassified flow silently improves risk capital, or a withdrawal bypasses concurrent reservations: reject.
- `T-VAN-CX-016-REC` — Rollback never erases financial events; credential cancellation returns RELINK_REQUIRED and broker closure remains independently verified.
- `T-REV113-008` — Signed lockout and probation settings activate through mandate content; restart and all-origin hard limits consistent

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-013 — BE-010: Venue execution, canonical orders and reconciliation
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-005, BE-008, BE-009, PRE-003.
**Requirement owners:** VAN-CX-003, VAN-CX-004, VAN-CX-005, VAN-CX-006, VAN-CX-007, VAN-NX-010, VAN-NX-027, VAN-NX-045, VAN-NX-061, VAN-NX-062, VAN-NX-074, VAN-NX-075, VAN-NX-076.

**Exit contract:** submit market/limit/stop/stop-limit where available; modify; cancel; read fills; map provider states; reconcile unknowns. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Cancel/fill race keeps broker truth; partial fill retains exposure; atomic request includes stop but protection requires independent readback

**All deliverables:**
- Retain PR101 pending-order progress; close worse-than-limit fills, expiry-policy propagation, pending-stop protection and terminal-order semantics before economic use.
- Strict order types, immediate/resting same submission vocabulary; buy/sell LIMIT not worse than declared price; policy expiry, blackouts and race outcomes observable

**Planned test obligations (all NOT_RUN):**
- `T-BE-010-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-010-NEG` — Cancel/fill race keeps broker truth; partial fill retains exposure; atomic request includes stop but protection requires independent readback
- `T-BE-010-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-010-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-010-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-VAN-CX-003-POS` — A pending fill with a rejected venue stop triggers the same admitted recovery as an immediate fill and updates risk and Attention.
- `T-VAN-CX-003-NEG` — Inject rejected/unknown protection at delayed or partial fill; a local rule alone must not yield CONFIRMED or permit additional risk.
- `T-VAN-CX-003-REC` — Keep protective orders and reservation state through crash; reconcile original receipt/position before any compensating action, with no blind close retry.
- `T-VAN-CX-004-POS` — At-touch and gapped quote fixtures preserve the limit in both directions; explicit capped-market fixtures preserve their separate slippage envelope.
- `T-VAN-CX-004-NEG` — The current 1.10000 limit with 0.00010 spread and 0.00002 slippage must never fill a BUY at 1.10007 or a SELL at 1.09993.
- `T-VAN-CX-004-REC` — After a gap, respect limit/stop/stop-limit distinctions; missed fills are not fabricated to preserve historical backtest counts.
- `T-VAN-CX-005-POS` — A four-hour STOP_ENTRY cannot remain eligible for 24 hours; PRE_BLACKOUT/POST_BLACKOUT moves eligible pending orders into cancellation workflow.
- `T-VAN-CX-005-NEG` — Drop max_wait, substitute a later expiry, or fill an ineligible resting order without reconciliation/Attention: fail.
- `T-VAN-CX-005-REC` — Model cancel/fill and partial-fill races honestly. Reserve full remaining risk until authoritative cancellation/expiry/readback; reconcile a fill that wins the race.
- `T-VAN-CX-006-POS` — EXPIRED, CANCELLED and REJECTED unfilled orders disappear from working-order totals but remain in historical records; partial positions retain actual exposure.
- `T-VAN-CX-006-NEG` — A stale ACCEPTED receipt after terminal readback must not resurrect Working; duplicate fill/cancel events must not double-count.
- `T-VAN-CX-006-REC` — Snapshot replay produces the same positions, orders, reservations and summaries after restart.
- `T-VAN-CX-007-POS` — FX, JPY, metals and alternative broker digit fixtures produce correct bounds from actual contract metadata and remain within the approved loss envelope.
- `T-VAN-CX-007-NEG` — Unknown digits, stale contract revision, a rounded stop beyond risk or below broker distance, or treating an old absolute cap as a new fraction: refuse.
- `T-VAN-CX-007-REC` — Quote or contract changes invalidate the preview; historical mandate/template versions replay with their original units.
- `T-REV113-009` — Buy/sell limit never fills worse than limit; stop trigger differs from limit fill; policy expiry propagated
- `T-REV113-010` — Pending order cancellation racing partial fill preserves authoritative exposure and stop readback

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-014 — BE-011: Manual trading, adds and management handover
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-009, BE-010, PRE-003.
**Requirement owners:** VAN-CX-009, VAN-NX-010, VAN-NX-027, VAN-NX-031, VAN-NX-061, VAN-NX-062, VAN-NX-077.

**Exit contract:** preview/submit manual entry; winning-only add; close/partial; tighten; TP changes; hand to VAN; take back with management epoch. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Winning at approval AND submission; never widen stop; take-back fences future commands and reconciles already-sent commands instead of claiming instant cancellation

**Planned test obligations (all NOT_RUN):**
- `T-BE-011-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-011-NEG` — Winning at approval AND submission; never widen stop; take-back fences future commands and reconciles already-sent commands instead of claiming instant cancellation
- `T-BE-011-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-011-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-011-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-VAN-CX-009-POS` — Restart replays the same locks; independent manual/autonomous cooldown tests coexist with shared all-origin hard-limit tests.
- `T-VAN-CX-009-NEG` — A restart resets losses, a default silently changes a signed policy, a manual entry bypasses total-account drawdown, or an owner reset erases economic loss: reject.
- `T-VAN-CX-009-REC` — A signed reset changes a permission state or risk reference with an audit event, never the immutable economic performance history; unknown policy/collateral blocks new risk.
- `T-REV113-011` — Manual add is winning at approval and submission, account-wide risk reserved; no unprotected entry

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-015 — BE-012: Positions, protection, portfolio, history and TCA
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-006, BE-010, BE-011, PRE-003.
**Requirement owners:** VAN-CX-003, VAN-CX-006, VAN-NX-008, VAN-NX-010, VAN-NX-040, VAN-NX-052, VAN-NX-061, VAN-NX-062, VAN-NX-076.

**Exit contract:** serve canonical positions; protect; build history/statement projections; compute sourced execution cost; report risk current/limit/remaining. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Unconfirmed stop never shown protected; every TCA value has units and benchmark timestamp; demo/live totals never mix

**All deliverables:**
- Common stop readback/reconciliation for immediate and late fills; all partial/rejected/expired/cancel-pending states source-bound

**Planned test obligations (all NOT_RUN):**
- `T-BE-012-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-012-NEG` — Unconfirmed stop never shown protected; every TCA value has units and benchmark timestamp; demo/live totals never mix
- `T-BE-012-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-012-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-012-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-VAN-CX-003-POS` — A pending fill with a rejected venue stop triggers the same admitted recovery as an immediate fill and updates risk and Attention.
- `T-VAN-CX-003-NEG` — Inject rejected/unknown protection at delayed or partial fill; a local rule alone must not yield CONFIRMED or permit additional risk.
- `T-VAN-CX-003-REC` — Keep protective orders and reservation state through crash; reconcile original receipt/position before any compensating action, with no blind close retry.
- `T-VAN-CX-006-POS` — EXPIRED, CANCELLED and REJECTED unfilled orders disappear from working-order totals but remain in historical records; partial positions retain actual exposure.
- `T-VAN-CX-006-NEG` — A stale ACCEPTED receipt after terminal readback must not resurrect Working; duplicate fill/cancel events must not double-count.
- `T-VAN-CX-006-REC` — Snapshot replay produces the same positions, orders, reservations and summaries after restart.
- `T-REV113-012` — Immediate and pending fills share protect/readback/unknown sequence; no fictional working states

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-016 — BE-014: News, calendar and source-health ingestion
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-003, BE-008, PRE-003.
**Requirement owners:** VAN-CX-005, VAN-NX-013, VAN-NX-038.

**Exit contract:** admit feeds; collect scheduled values and headlines; canonicalize identities; track original publisher, entitlements, clocks and source failures. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Syndicated copies count once; preliminary/forecast/revised previous is not actual; unsupported licence or failed feed does not fake coverage

**Planned test obligations (all NOT_RUN):**
- `T-BE-014-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-014-NEG` — Syndicated copies count once; preliminary/forecast/revised previous is not actual; unsupported licence or failed feed does not fake coverage
- `T-BE-014-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-014-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-014-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-NX-038` — Terms check and live probe per feed
- `T-VAN-CX-005-POS` — A four-hour STOP_ENTRY cannot remain eligible for 24 hours; PRE_BLACKOUT/POST_BLACKOUT moves eligible pending orders into cancellation workflow.
- `T-VAN-CX-005-NEG` — Drop max_wait, substitute a later expiry, or fill an ineligible resting order without reconciliation/Attention: fail.
- `T-VAN-CX-005-REC` — Model cancel/fill and partial-fill races honestly. Reserve full remaining risk until authoritative cancellation/expiry/readback; reconcile a fill that wins the race.
- `T-REV113-014` — Two syndicated news copies do not count as two independent releases

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-017 — BE-015: Event analysis, history, analogues and expectations
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-014, PRE-003.
**Requirement owners:** VAN-NX-013, VAN-NX-036, VAN-NX-037.

**Exit contract:** cluster/correct/retract; classify; measure reactions; build history; retrieve analogues; join prediction-market expectations only when admitted. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. No look-ahead; missing market marks stay missing; thin sample cannot become calibrated probability; source corrections invalidate descendants

**Planned test obligations (all NOT_RUN):**
- `T-BE-015-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-015-NEG` — No look-ahead; missing market marks stay missing; thin sample cannot become calibrated probability; source corrections invalidate descendants
- `T-BE-015-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-015-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-015-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-NX-036` — §8.2, §8.4; reachability and terms verified
- `T-NX-037` — §8.3; detectors never trade alone

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-018 — BE-018: Chart data contracts, indicators, drawings and workspaces
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-003, BE-008, PRE-003.
**Requirement owners:** VAN-NX-009, VAN-NX-041, VAN-NX-042, VAN-NX-043.

**Exit contract:** serve chart capability contract; persist indicator instances/drawing anchors/layouts; revise settings; calculate certified server indicators; sync conflicts. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. No rendered pixels as canonical geometry; parameter versions and price/time anchors round-trip; cross-device edit conflict explicit; no server dependency on a new renderer

**Planned test obligations (all NOT_RUN):**
- `T-BE-018-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-018-NEG` — No rendered pixels as canonical geometry; parameter versions and price/time anchors round-trip; cross-device edit conflict explicit; no server dependency on a new renderer
- `T-BE-018-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-018-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-018-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-019 — BE-019: Historical replay, simulation and isolated practice data
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-008, BE-018, PRE-003.
**Requirement owners:** VAN-CX-004, VAN-CX-005, VAN-CX-010, VAN-CX-012, VAN-NX-044, VAN-NX-076.

**Exit contract:** create deterministic replay sessions; step/seek; store paper actions separately; return outcomes and provenance. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Replay cannot resolve an execution route or grant; future bars invisible; reset/seek reproducible; practice never enters live P&L or strategy promotion statistics

**Planned test obligations (all NOT_RUN):**
- `T-BE-019-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-019-NEG` — Replay cannot resolve an execution route or grant; future bars invisible; reset/seek reproducible; practice never enters live P&L or strategy promotion statistics
- `T-BE-019-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-019-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-019-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-VAN-CX-004-POS` — At-touch and gapped quote fixtures preserve the limit in both directions; explicit capped-market fixtures preserve their separate slippage envelope.
- `T-VAN-CX-004-NEG` — The current 1.10000 limit with 0.00010 spread and 0.00002 slippage must never fill a BUY at 1.10007 or a SELL at 1.09993.
- `T-VAN-CX-004-REC` — After a gap, respect limit/stop/stop-limit distinctions; missed fills are not fabricated to preserve historical backtest counts.
- `T-VAN-CX-005-POS` — A four-hour STOP_ENTRY cannot remain eligible for 24 hours; PRE_BLACKOUT/POST_BLACKOUT moves eligible pending orders into cancellation workflow.
- `T-VAN-CX-005-NEG` — Drop max_wait, substitute a later expiry, or fill an ineligible resting order without reconciliation/Attention: fail.
- `T-VAN-CX-005-REC` — Model cancel/fill and partial-fill races honestly. Reserve full remaining risk until authoritative cancellation/expiry/readback; reconcile a fill that wins the race.
- `T-VAN-CX-010-POS` — Known-profit/loss fixtures match analytically specified results and the actual execution adapters' admitted semantics.
- `T-VAN-CX-010-NEG` — Disabling controls, altering quote units or a permissive fill model without a distinct experiment identity invalidates promotion evidence.
- `T-VAN-CX-010-REC` — An evaluator correction invalidates dependent candidate conclusions and schedules reproducible reevaluation; old results remain labeled historical.
- `T-VAN-CX-012-POS` — From permitted raw inputs, a second run reproduces the same bars, sessions, costs and outcomes.
- `T-VAN-CX-012-NEG` — Bid is silently treated as midpoint, fixed EST becomes DST-local time, a bar is used before close or a mirror is unpinned: reject qualifying use.
- `T-VAN-CX-012-REC` — Keep lawful metadata and reproducibility scripts without republishing restricted data; qualifying tests await admitted data while unrelated authorized engineering continues.
- `T-REV113-016` — Simulator refuses same-bar ambiguities or bounds them honestly; bid/ask and order timestamps causal

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-020 — BE-020: Watchlists, persistent alerts and typed screening
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-003, BE-008, BE-014, BE-018, PRE-003.
**Requirement owners:** VAN-NX-008, VAN-NX-011, VAN-NX-047.

**Exit contract:** CRUD lists; evaluate price/indicator/drawing/news alerts on server; pause/restart/delete; scan instruments; emit canonical notifications. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. One trigger identity across devices/restart; stale data cannot trigger a live market fact; alert never trades; scan quotas enforced

**Planned test obligations (all NOT_RUN):**
- `T-BE-020-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-020-NEG` — One trigger identity across devices/restart; stale data cannot trigger a live market fact; alert never trades; scan quotas enforced
- `T-BE-020-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-020-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-020-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-021 — BE-021: Analyst, chart observations and cross-signal intelligence
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-012, BE-015, BE-018, BE-019, PRE-003.
**Requirement owners:** VAN-CX-018, VAN-HVA-027, VAN-HVA-028, VAN-NX-012, VAN-NX-013, VAN-NX-046, VAN-NX-065.

**Exit contract:** ingest consented chart observations and notes; join news/portfolio; generate fact-bound explanations; track contradiction; provide evidence artifacts. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Chart payload injection and model-added numbers rejected; retention/erasure honoured; all contributing revisions recorded; headless producer proves intake before UI exists

**All deliverables:**
- Extend registered trading evidence questions through the existing shared dial-jev consumer; answer quality is not a profitable-trade probability.
- Evidence claims distinguish model probability, analyst confidence, source corroboration and risk authority

**Planned test obligations (all NOT_RUN):**
- `T-BE-021-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-021-NEG` — Chart payload injection and model-added numbers rejected; retention/erasure honoured; all contributing revisions recorded; headless producer proves intake before UI exists
- `T-BE-021-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-021-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-021-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-VAN-CX-018-POS` — Every one of the 90 forecast requirements maps to an active unit and test; all required child backend receipts reach BG-001.
- `T-VAN-CX-018-NEG` — A child F15/BG independently opens UI, Qlib or Freqtrade sends a live order, or a unavailable provider is labeled healthy: reject.
- `T-VAN-CX-018-REC` — Data/model failure yields explicit abstention or unavailable state; no economically qualified model is a permissible result, not permission to omit software.
- `T-HVA-027-POS` — A real registered question set receives an anchored snapshot and returns a schema-valid answer/unknown with source and deadline lineage.
- `T-HVA-027-NEG` — An external post requests orders, secrets or overriding a mandatory exit; no tool invocation or authority change occurs.
- `T-HVA-027-REC` — On timeout/provider revocation the established deterministic baseline remains available and all pending judgments become expired/unknown.
- `T-HVA-028-POS` — Compare no-LLM/rule, shared Jev and another approved challenger on identical sealed questions and independently observable outcomes, including cost and abstention.
- `T-HVA-028-NEG` — Promote an answer-quality score or artifact hash as calibrated trade probability or independent corroboration of the same source; reject.
- `T-HVA-028-REC` — Question/model/input-policy revisions invalidate incompatible calibration and retain usable explanation-only fallback.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-022 — BE-023: Projects, tasks, missions and truthful workflow graphs
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-002, BE-003, PRE-003.
**Requirement owners:** VAN-NX-014, VAN-NX-015.

**Exit contract:** create/read/update permitted tasks; stream mission progress; join stage evidence; compute dependency graph/critical path; expose stable node/edge IDs. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Cycles/orphans/conflicting actors visible; no completion from agent RUNNING; graph drag has no authority; observed task state not fabricated by layout

**Planned test obligations (all NOT_RUN):**
- `T-BE-023-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-023-NEG` — Cycles/orphans/conflicting actors visible; no completion from agent RUNNING; graph drag has no authority; observed task state not fabricated by layout
- `T-BE-023-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-023-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-023-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-REV113-017` — Task graph dependency, agent assignment and handoff provenance never fabricated from missing source

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-023 — BE-024: Agents, Hermes, Muse and provider-bound interventions
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-002, BE-003, BE-023, PRE-003.
**Requirement owners:** VAN-HVA-027, VAN-NX-016, VAN-NX-017.

**Exit contract:** assign/steer/cancel under lease; native conversation protocol; provider-bound allow/deny; reconcile job/task/artifact outcomes. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Expired lease, duplicate allow, late callback and task scope mismatch refuse; GUI click is not success; integration must be real, not an unbound client stub

**Planned test obligations (all NOT_RUN):**
- `T-BE-024-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-024-NEG` — Expired lease, duplicate allow, late callback and task scope mismatch refuse; GUI click is not success; integration must be real, not an unbound client stub
- `T-BE-024-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-024-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-024-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-HVA-027-POS` — A real registered question set receives an anchored snapshot and returns a schema-valid answer/unknown with source and deadline lineage.
- `T-HVA-027-NEG` — An external post requests orders, secrets or overriding a mandatory exit; no tool invocation or authority change occurs.
- `T-HVA-027-REC` — On timeout/provider revocation the established deterministic baseline remains available and all pending judgments become expired/unknown.
- `T-REV113-018` — Muse reattach/owner approval requires fresh provider lease/callback evidence, duplicate click fail closed

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-024 — BE-025: Browser, remote interaction, artifact and share intake
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-002, BE-003, BE-024, PRE-003.
**Requirement owners:** VAN-NX-020, VAN-NX-069.

**Exit contract:** lease session; observe viewport; submit exact plan; upload/download with admission; report action outcome; revoke; bind file destination. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. No broad host command from UI; before/after target changes invalidate intent; file destination substitution denied; retained source content is untrusted data

**Planned test obligations (all NOT_RUN):**
- `T-BE-025-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-025-NEG` — No broad host command from UI; before/after target changes invalidate intent; file destination substitution denied; retained source content is untrusted data
- `T-BE-025-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-025-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-025-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-025 — BE-026: ARTEMIS device tests and independent evidence services
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-002, BE-003, BE-023, BE-025, PRE-003.
**Requirement owners:** VAN-NX-020, VAN-NX-069, VAN-NX-BF-013.

**Exit contract:** enumerate qualified devices; version plans; queue/observe/cancel tests; preserve captures; publish pass/fail/unknown and build IDs. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. An emulator cannot issue S24 acceptance; missing capture means unknown; old APK test cannot certify new build; server protocol testable with existing authorised clients

**Planned test obligations (all NOT_RUN):**
- `T-BE-026-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-026-NEG` — An emulator cannot issue S24 acceptance; missing capture means unknown; old APK test cannot certify new build; server protocol testable with existing authorised clients
- `T-BE-026-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-026-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-026-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-BF-013` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-026 — BE-027: Memory, knowledge, goals, privacy and erasure
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-002, BE-003, PRE-003.
**Requirement owners:** VAN-NX-018, VAN-NX-066, VAN-NX-067, VAN-NX-068.

**Exit contract:** search/correct/retract facts; retain provenance; inspect history; edit goals; review/rollback adaptation; erase scoped records and derivatives. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Deleting source is not model unlearning; revoked context excluded from research; erasure includes caches/derived artifacts or declares verified retention exception

**Planned test obligations (all NOT_RUN):**
- `T-BE-027-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-027-NEG` — Deleting source is not model unlearning; revoked context excluded from research; erasure includes caches/derived artifacts or declares verified retention exception
- `T-BE-027-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-027-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-027-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-027 — BE-028: Automation, reminders and schedules
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-002, BE-003, BE-023, BE-027, PRE-003.
**Requirement owners:** VAN-CX-014, VAN-NX-018, VAN-NX-066, VAN-NX-067, VAN-NX-068, VAN-NX-072.

**Exit contract:** candidate/admit/version workflows; bind standing authority; schedule; report next/last run; execute through domain adapters; retry safely. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Failed run never silently success; timezone/DST/misfire specified; schedules never mint grants; unknown effect reconciled before retry

**Planned test obligations (all NOT_RUN):**
- `T-BE-028-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-028-NEG` — Failed run never silently success; timezone/DST/misfire specified; schedules never mint grants; unknown effect reconciled before retry
- `T-BE-028-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-028-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-028-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-VAN-CX-014-POS` — A weekly run is idempotent by period/strategy/dataset/evaluator; results reproduce and a candidate reaches only permitted next states.
- `T-VAN-CX-014-NEG` — A model edits protected execution/risk paths, repeated runs duplicate studies, a failed candidate becomes a promotion opportunity, or an unsigned candidate trades live: refuse.
- `T-VAN-CX-014-REC` — Resume interrupted jobs from durable checkpoints; outdated evaluations are invalidated, not overwritten; current production champion remains unchanged.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-028 — BE-029: Conversation, voice and speaker-profile services
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-002, BE-003, BE-027, PRE-003.
**Requirement owners:** VAN-NX-006, VAN-NX-020, VAN-NX-069.

**Exit contract:** create turns; stream transcript/audio; interrupt; retain history; manage speaker consent/erase; expose speech and task context. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Mic permission denial propagates; interrupted response not completion; no speaker identity assertion without enrollment; obsolete consent cannot reopen microphone

**Planned test obligations (all NOT_RUN):**
- `T-BE-029-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-029-NEG` — Mic permission denial propagates; interrupted response not completion; no speaker identity assertion without enrollment; obsolete consent cannot reopen microphone
- `T-BE-029-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-029-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-029-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-029 — BE-030: Attention, notifications, presence and compact summaries
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-003, BE-012, BE-020, BE-023, BE-024, BE-028, BE-029, PRE-003.
**Requirement owners:** VAN-NX-004, VAN-NX-005, VAN-NX-006, VAN-NX-007, VAN-NX-063.

**Exit contract:** aggregate typed events; arbitrate severity/freshness; dedupe delivery; persist acknowledgement; project orb semantics and compact hub summaries. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Risk preempts celebration; snooze never clears incident; no state legend or route action executes; stale health never healthy idle; one event per channel identity

**Planned test obligations (all NOT_RUN):**
- `T-BE-030-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-030-NEG` — Risk preempts celebration; snooze never clears incident; no state legend or route action executes; stale health never healthy idle; one event per channel identity
- `T-BE-030-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-030-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-030-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-030 — BE-031: Connected providers, settings, devices and diagnostics
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-002, BE-003, BE-005, BE-024, BE-025, BE-029, PRE-003.
**Requirement owners:** VAN-NX-006, VAN-NX-019.

**Exit contract:** serve provider readiness and scopes; version settings; manage device inventory/provisioning; expose connection correlations; privacy defaults. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Connection health is not action authority; no manual raw host/token forms; no leaked secrets in telemetry; native permission completion deferred to actual OS readback

**Planned test obligations (all NOT_RUN):**
- `T-BE-031-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-031-NEG` — Connection health is not action authority; no manual raw host/token forms; no leaked secrets in telemetry; native permission completion deferred to actual OS readback
- `T-BE-031-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-031-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-031-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-031 — BE-034: Development studio, CI/security and evidence-workspace adapters
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-023, BE-024, BE-025, BE-026, PRE-003.
**Requirement owners:** VAN-NX-020, VAN-NX-069.

**Exit contract:** project/read stage plans; expose design/research/security/CI evidence; admit cinematic/studio workspace candidate APIs and native-control bindings. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. PR98/99 and later candidates are evaluated, not assumed; UI workspace cannot mint build/deploy authority; external partial services block required backend integration

**Planned test obligations (all NOT_RUN):**
- `T-BE-034-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-034-NEG` — PR98/99 and later candidates are evaluated, not assumed; UI workspace cannot mint build/deploy authority; external partial services block required backend integration
- `T-BE-034-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-034-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-034-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-032 — BE-035: Qualified chronological strategy evaluator and simulator oracle
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-003, BE-008, BE-009, BE-010, BE-012, BE-019, PRE-003.
**Requirement owners:** VAN-CX-003, VAN-CX-004, VAN-CX-005, VAN-CX-010, VAN-CX-011, VAN-CX-012, VAN-CX-013, VAN-CX-014, VAN-HVA-006, VAN-NX-072, VAN-NX-076.

**Exit contract:** All VAN-CX-003–013 evaluator obligations; executable matching/chronology fixtures; actual folds and data manifests; deployment-faithful and isolation experiments separated; independent adversarial oracle.

**All deliverables:**
- Preserve all current evaluator corrections: directional intrabar ambiguity, executable timing, limit prices, full cash charges, post-liquidation equity and account-coordinator parity.
- Calendar-year reporting cannot impersonate walk-forward; bid/ask, point-in-time/timezones, no future leakage, intrabar oracle

**Planned test obligations (all NOT_RUN):**
- `T-VAN-CX-003-POS` — A pending fill with a rejected venue stop triggers the same admitted recovery as an immediate fill and updates risk and Attention.
- `T-VAN-CX-003-NEG` — Inject rejected/unknown protection at delayed or partial fill; a local rule alone must not yield CONFIRMED or permit additional risk.
- `T-VAN-CX-003-REC` — Keep protective orders and reservation state through crash; reconcile original receipt/position before any compensating action, with no blind close retry.
- `T-VAN-CX-004-POS` — At-touch and gapped quote fixtures preserve the limit in both directions; explicit capped-market fixtures preserve their separate slippage envelope.
- `T-VAN-CX-004-NEG` — The current 1.10000 limit with 0.00010 spread and 0.00002 slippage must never fill a BUY at 1.10007 or a SELL at 1.09993.
- `T-VAN-CX-004-REC` — After a gap, respect limit/stop/stop-limit distinctions; missed fills are not fabricated to preserve historical backtest counts.
- `T-VAN-CX-005-POS` — A four-hour STOP_ENTRY cannot remain eligible for 24 hours; PRE_BLACKOUT/POST_BLACKOUT moves eligible pending orders into cancellation workflow.
- `T-VAN-CX-005-NEG` — Drop max_wait, substitute a later expiry, or fill an ineligible resting order without reconciliation/Attention: fail.
- `T-VAN-CX-005-REC` — Model cancel/fill and partial-fill races honestly. Reserve full remaining risk until authoritative cancellation/expiry/readback; reconcile a fill that wins the race.
- `T-VAN-CX-010-POS` — Known-profit/loss fixtures match analytically specified results and the actual execution adapters' admitted semantics.
- `T-VAN-CX-010-NEG` — Disabling controls, altering quote units or a permissive fill model without a distinct experiment identity invalidates promotion evidence.
- `T-VAN-CX-010-REC` — An evaluator correction invalidates dependent candidate conclusions and schedules reproducible reevaluation; old results remain labeled historical.
- `T-VAN-CX-011-POS` — Replay of each named chronological fold yields the same pre-cutoff decisions and verified split provenance.
- `T-VAN-CX-011-NEG` — Future-only perturbation changes past decisions, a scaler sees the holdout, or window count is only the count of calendar years: fail.
- `T-VAN-CX-011-REC` — Tainted fold/candidate artifacts cannot be reused as independent promotion evidence; retain audit lineage.
- `T-VAN-CX-012-POS` — From permitted raw inputs, a second run reproduces the same bars, sessions, costs and outcomes.
- `T-VAN-CX-012-NEG` — Bid is silently treated as midpoint, fixed EST becomes DST-local time, a bar is used before close or a mirror is unpinned: reject qualifying use.
- `T-VAN-CX-012-REC` — Keep lawful metadata and reproducibility scripts without republishing restricted data; qualifying tests await admitted data while unrelated authorized engineering continues.
- `T-VAN-CX-013-POS` — Each reported metric identifies the population, formula/version, trial set, uncertainty and selection scope.
- `T-VAN-CX-013-NEG` — A pooled PBO is relabeled pair-specific, losers disappear from trial count, or repeated holdout tuning is called independent: fail promotion.
- `T-VAN-CX-013-REC` — A no-qualified-candidate result is valid; do not search until a cherry-picked pass can be manufactured.
- `T-VAN-CX-014-POS` — A weekly run is idempotent by period/strategy/dataset/evaluator; results reproduce and a candidate reaches only permitted next states.
- `T-VAN-CX-014-NEG` — A model edits protected execution/risk paths, repeated runs duplicate studies, a failed candidate becomes a promotion opportunity, or an unsigned candidate trades live: refuse.
- `T-VAN-CX-014-REC` — Resume interrupted jobs from durable checkpoints; outdated evaluations are invalidated, not overwritten; current production champion remains unchanged.
- `T-BE-035-POS` — All VAN-CX-003–013 evaluator obligations; executable matching/chronology fixtures; actual folds and data manifests; deployment-faithful and isolation experiments separated; independent adversarial oracle. POS evidence required.
- `T-BE-035-NEG` — All VAN-CX-003–013 evaluator obligations; executable matching/chronology fixtures; actual folds and data manifests; deployment-faithful and isolation experiments separated; independent adversarial oracle. NEG evidence required.
- `T-BE-035-REC` — All VAN-CX-003–013 evaluator obligations; executable matching/chronology fixtures; actual folds and data manifests; deployment-faithful and isolation experiments separated; independent adversarial oracle. REC evidence required.
- `T-BE-035-SEC` — All VAN-CX-003–013 evaluator obligations; executable matching/chronology fixtures; actual folds and data manifests; deployment-faithful and isolation experiments separated; independent adversarial oracle. SEC evidence required.
- `T-BE-035-INT` — All VAN-CX-003–013 evaluator obligations; executable matching/chronology fixtures; actual folds and data manifests; deployment-faithful and isolation experiments separated; independent adversarial oracle. INT evidence required.
- `T-HVA-006-POS` — Show size-only attribution and independently simulated policy performance as separate, correctly labelled results.
- `T-HVA-006-NEG` — Scale nonlinear gas/slippage or a different entry/exit path by the actual trade R and call it realized performance; reject.
- `T-HVA-006-REC` — On a revised fill model recompute simulated results without editing actual venue receipts or historical size-only attribution.
- `T-REV113-019` — Future-only mutation leaves past decision unchanged and is detected when future used; folds are genuine

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-033 — BE-013: Strategy registry, signed trading modes and qualified edge-consumer contracts
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-009, BE-010, BE-035, PRE-003.
**Requirement owners:** VAN-CX-009, VAN-CX-014, VAN-CX-018, VAN-HVA-029, VAN-NX-008, VAN-NX-058, VAN-NX-072, VAN-NX-077.

**Exit contract:** list/inspect/promote qualified strategies; produce edge admission evidence; apply Normal/Risky/Aggressive requests; reconcile restart; attribution. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Aggressive without admitted edge refuses; mode never raises signed ceilings; both evidence producer and refusal path must be implemented Economic evidence and mode producers are admitted through BE-035 and the forecast integration; no standalone code default substitutes for a signed policy.

**All deliverables:**
- Do not equate existing AllocatorV1 with calibrated model-weighted ranking. Specify a separately reviewed policy version without adding sizing/reservation authority.
- Tempered modes with signed risk budgets; default code cannot bypass mandate; AGGRESSIVE requires independent edge

**Planned test obligations (all NOT_RUN):**
- `T-BE-013-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-013-NEG` — Aggressive without admitted edge refuses; mode never raises signed ceilings; both evidence producer and refusal path must be implemented
- `T-BE-013-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-013-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-013-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-NX-072` — §7.4.14; induced: a failing candidate never reaches the owner; a passing candidate cannot change live trading without a signed promotion; a protected-path candidate is held; the weekly run is scheduled and replays identically from the ledger
- `T-VAN-CX-009-POS` — Restart replays the same locks; independent manual/autonomous cooldown tests coexist with shared all-origin hard-limit tests.
- `T-VAN-CX-009-NEG` — A restart resets losses, a default silently changes a signed policy, a manual entry bypasses total-account drawdown, or an owner reset erases economic loss: reject.
- `T-VAN-CX-009-REC` — A signed reset changes a permission state or risk reference with an audit event, never the immutable economic performance history; unknown policy/collateral blocks new risk.
- `T-VAN-CX-014-POS` — A weekly run is idempotent by period/strategy/dataset/evaluator; results reproduce and a candidate reaches only permitted next states.
- `T-VAN-CX-014-NEG` — A model edits protected execution/risk paths, repeated runs duplicate studies, a failed candidate becomes a promotion opportunity, or an unsigned candidate trades live: refuse.
- `T-VAN-CX-014-REC` — Resume interrupted jobs from durable checkpoints; outdated evaluations are invalidated, not overwritten; current production champion remains unchanged.
- `T-VAN-CX-018-POS` — Every one of the 90 forecast requirements maps to an active unit and test; all required child backend receipts reach BG-001.
- `T-VAN-CX-018-NEG` — A child F15/BG independently opens UI, Qlib or Freqtrade sends a live order, or a unavailable provider is labeled healthy: reject.
- `T-VAN-CX-018-REC` — Data/model failure yields explicit abstention or unavailable state; no economically qualified model is a permissible result, not permission to omit software.
- `T-HVA-029-POS` — Replay the inherited V0/V1 behavior unchanged, then separately test an admitted ranking-policy version with exact feature/forecast lineage.
- `T-HVA-029-NEG` — Enable model-weighted ranking by merely selecting AllocatorV1, duplicate the allocator or use ranking to exceed portfolio reservations; reject.
- `T-HVA-029-REC` — Revoke the ranking extension and restore the qualified baseline without releasing pending-order reservations or changing mandates.
- `T-REV113-013` — Mode AGGRESSIVE abstains without independent calibrated edge, never increases mandate risk

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-034 — BE-016: Governed news effects D1–D7 and news strategy lifecycle
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-009, BE-012, BE-013, BE-015, PRE-003.
**Requirement owners:** VAN-CX-005, VAN-NX-013, VAN-NX-032.

**Exit contract:** compute shadow decisions; reduce size/timing/rank; preserve VAN-managed positions; validate event strategies; admit per-path promotions. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. D1–D6 cannot increase risk; owner-managed trades get proposals not silent exits; D7 requires strategy evidence; news corrections retract pending eligibility

**Planned test obligations (all NOT_RUN):**
- `T-BE-016-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-016-NEG` — D1–D6 cannot increase risk; owner-managed trades get proposals not silent exits; D7 requires strategy evidence; news corrections retract pending eligibility
- `T-BE-016-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-016-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-016-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-VAN-CX-005-POS` — A four-hour STOP_ENTRY cannot remain eligible for 24 hours; PRE_BLACKOUT/POST_BLACKOUT moves eligible pending orders into cancellation workflow.
- `T-VAN-CX-005-NEG` — Drop max_wait, substitute a later expiry, or fill an ineligible resting order without reconciliation/Attention: fail.
- `T-VAN-CX-005-REC` — Model cancel/fill and partial-fill races honestly. Reserve full remaining risk until authoritative cancellation/expiry/readback; reconcile a fill that wins the race.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-035 — BE-017: Armed news tickets, readiness and single-use execution
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-002, BE-010, BE-016, PRE-003.
**Requirement owners:** VAN-CX-015, VAN-NX-033, VAN-NX-BF-016.

**Exit contract:** prepare/sign/arm/revalidate/disarm/use; persist nonce; record latency; enforce two-source agreement at execution; reconcile submission. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. SIGNED is not readiness; expired/changed policy/account/health disarms; a future release can be armed before actual values arrive, but use cannot precede required agreement

**Planned test obligations (all NOT_RUN):**
- `T-BE-017-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-017-NEG` — SIGNED is not readiness; expired/changed policy/account/health disarms; a future release can be armed before actual values arrive, but use cannot precede required agreement
- `T-BE-017-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-017-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-017-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-BF-016` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `T-VAN-CX-015-POS` — A pre-signed ticket arms only in its declared readiness envelope and can claim the nonce once.
- `T-VAN-CX-015-NEG` — Empty proof, arbitrary real proof label, proof for another account/event, re-signed weakened allowlist or concurrent duplicate use: reject.
- `T-VAN-CX-015-REC` — Arming and consuming a grant are not a broker fill; unknown submission follows the order reconciler, never a second order.
- `T-REV113-015` — News ticket requires signed prior approval + exact arming window + dual source and one-use nonce

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-036 — BE-022: Owner diagnostics, pattern discovery and learning review
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-011, BE-013, BE-019, BE-021, PRE-003.
**Requirement owners:** VAN-CX-014, VAN-NX-034, VAN-NX-035, VAN-NX-072.

**Exit contract:** analyse all manual trades; display soft behaviour findings; extract entry-time features; validate new candidates; track counterfactuals. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. Post-entry holding duration is outcome metadata, not an entry feature; losing trades retained; insufficient sample no assertion; candidate never automatically promoted Loss diagnostics use all-trade and opportunity denominators. Predictive deterioration and input drift are different states.

**Planned test obligations (all NOT_RUN):**
- `T-BE-022-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-022-NEG` — Post-entry holding duration is outcome metadata, not an entry feature; losing trades retained; insufficient sample no assertion; candidate never automatically promoted
- `T-BE-022-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-022-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-022-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-VAN-CX-014-POS` — A weekly run is idempotent by period/strategy/dataset/evaluator; results reproduce and a candidate reaches only permitted next states.
- `T-VAN-CX-014-NEG` — A model edits protected execution/risk paths, repeated runs duplicate studies, a failed candidate becomes a promotion opportunity, or an unsigned candidate trades live: refuse.
- `T-VAN-CX-014-REC` — Resume interrupted jobs from durable checkpoints; outdated evaluations are invalidated, not overwritten; current production champion remains unchanged.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-037 — VAN-ML-PKT-004: Pinned dependencies and isolated research runtime
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-002, BE-003, PRE-003.
**Requirement owners:** VAN-ML-REQ-004.

**Exit contract:** Actual train/export/load smoke with locked upstream libraries on an authorized VM; Import-boundary tests reject heavy model imports and broker credentials in the T0 runtime

**All deliverables:**
- Lock Qlib, LightGBM, NeuralForecast, XGBoost, Optuna, Feast/MLflow and transitive dependencies by tested version/hash
- Build separate CPU research/inference environments, wheel/architecture matrix, resource and network policy
- Register worker bootstrap, SBOM and safe model-parser compatibility

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-004-P` — Train/export/load a small actual locked model on authorized infrastructure.
- `VAN-ML-AT-004-N` — Unsupported wheel/architecture or missing quota blocks job admission.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-038 — VAN-ML-PKT-005: Point-in-time market dataset and universe snapshots
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-008, BE-010, PRE-003, VAN-ML-PKT-004.
**Requirement owners:** VAN-HVA-012, VAN-ML-REQ-005, VAN-ML-REQ-006, VAN-ML-REQ-007.

**Exit contract:** Replay a revision, delisting and late release: past snapshot remains unchanged; Reject cross-venue collisions, incomplete bars and unknown-use entitlements

**All deliverables:**
- Implement immutable source vintages, availability clocks, calendars, instrument identity and point-in-time universe
- Join licensed market/news/expectation features without revised-future leakage; distinguish observed and reconstructed availability
- Materialize versioned Parquet research snapshots from the existing data owners
- Domain datasets retain all discovered/rejected/missing/migrated candidates through BE-038/044 joins, without blocking generic dataset development on an unavailable crypto source.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-005-P` — Late-arriving release stays absent until its observed availability cutoff.
- `VAN-ML-AT-005-N` — Replace vintage data with revised future values: dataset validation fails.
- `VAN-ML-AT-006-P` — Reproduce an historical cohort including subsequently delisted instruments.
- `VAN-ML-AT-006-N` — Present-day universe or cross-venue ticker collision is detected.
- `VAN-ML-AT-007-P` — DST, holiday and missing-bar fixtures preserve correct cutoff/horizon semantics.
- `VAN-ML-AT-007-N` — Partial current candle or fabricated forward-filled tradability cannot enter fit.
- `T-HVA-012-POS` — Reconcile source discovery count with terminal and pending cohort states, including candidates never sent to a model.
- `T-HVA-012-NEG` — Build training/test data only from survivors or delete a disappearing pool as missing data; fail cohort completeness.
- `T-HVA-012-REC` — Rebuild the cohort projection from immutable discovery and decision events after a crash without hindsight re-ranking.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-039 — BE-037: Chain-aware identity and permitted read-only discovery adapters
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-003, BE-008, VAN-ML-PKT-005.
**Requirement owners:** VAN-HVA-004, VAN-HVA-008, VAN-HVA-009, VAN-HVA-010, VAN-HVA-011.

**Exit contract:** Complete all stated operations in the existing owners. Documented provider record → existing acquisition/data store → cohort and security analyzers. Verify a real registered positive caller/readback, negative and recovery paths under exact source/provider scope. Reject conflicting identifiers, private endpoints, unapproved methods and invented source-use rights. No fixture substitutes for required real provider integration, and no research result grants financial authority.

**All deliverables:**
- Validate chain/network/address identity and independent pool/router records; preserve raw IDs and migrations.
- Register bounded discovery/RPC/indexer adapters using permitted existing access; document exact methods and operation allowlists.
- Persist source availability, state anchors, cursors, quotas, retention and disabled-provider readbacks.
- No chain source adoption without capability/terms/access and authority isolation

**Planned test obligations (all NOT_RUN):**
- `T-HVA-004-POS` — Run a complete read-only discovery-to-evidence path and a concurrent existing risk-reducing exit without any additive financial operation.
- `T-HVA-004-NEG` — Inject a sign/sendTransaction, fund-wallet or broker-order request into a provider record or judgment; refuse and preserve the existing financial path.
- `T-HVA-004-REC` — Restart or revoke the research service while an existing position is being protected; protection and reconciliation remain available.
- `T-HVA-008-POS` — Round-trip multiple address representations through the correct chain adapter and retain two different contracts with one display ticker.
- `T-HVA-008-NEG` — Lowercase a case-sensitive address, confuse network identifiers, or treat a malformed address as valid; reject or quarantine.
- `T-HVA-008-REC` — A codec version change triggers a reviewed migration preserving old aliases and links without merging distinct assets.
- `T-HVA-009-POS` — Track one asset across two pools and a migration with separate quote, liquidity and first-seen histories.
- `T-HVA-009-NEG` — Sum duplicated liquidity across routed hops or reassign an old quote to a new pool; reject the economics.
- `T-HVA-009-REC` — Reorg or rollback of a migration invalidates affected route descendants and preserves original token identity.
- `T-HVA-010-POS` — Exercise a permitted provider contract and separately show a disabled/unavailable provider with a precise missing-evidence state.
- `T-HVA-010-NEG` — Treat Netcup/Oracle placement or unauthenticated reachability as unrestricted rights or funded trading eligibility; reject that inference.
- `T-HVA-010-REC` — A permission expiry disables new affected acquisition and serving, preserves audit records according to applicable retention and leaves unrelated work runnable.
- `T-HVA-011-POS` — Capture and replay successful documented discovery/read calls with exact cursor, hash, latency and source availability.
- `T-HVA-011-NEG` — Inject redirects to a private endpoint, oversized payload, malicious instructions, quota flood or an order-bearing method; refuse without expanding scope.
- `T-HVA-011-REC` — Resume from a durable cursor after outage and deduplicate retried source records without losing the observed cohort.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-040 — BE-038: Complete discovery cohorts and staged deterministic screening
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-037, BE-020.
**Requirement owners:** VAN-HVA-012, VAN-HVA-013, VAN-HVA-014, VAN-HVA-023, VAN-HVA-024.

**Exit contract:** Complete all stated operations in the existing owners. Discovery adapters → immutable cohort/stage events → screening, datasets and read models. Verify a real registered positive caller/readback, negative and recovery paths under exact source/provider scope. Survivor-only training, string truthiness, missing young-asset windows and duplicate discoveries must fail. No fixture substitutes for required real provider integration, and no research result grants financial authority.

**All deliverables:**
- Archive all discovered candidates before filters; persist every stage decision, reject, unknown and expiry.
- Implement cheap-to-expensive screening with one-survivor invariants, typed unknown normalization and empirical rule versions.
- Use existing scheduling with durable bounded queues, cause-specific rechecks and negative-cache invalidation.

**Planned test obligations (all NOT_RUN):**
- `T-HVA-012-POS` — Reconcile source discovery count with terminal and pending cohort states, including candidates never sent to a model.
- `T-HVA-012-NEG` — Build training/test data only from survivors or delete a disappearing pool as missing data; fail cohort completeness.
- `T-HVA-012-REC` — Rebuild the cohort projection from immutable discovery and decision events after a crash without hindsight re-ranking.
- `T-HVA-013-POS` — One eligible survivor receives all remaining checks and can still end NO_TRADE; typed yes/no/unknown inputs give stable outcomes.
- `T-HVA-013-NEG` — Use string no as true, skip remaining checks for one survivor, or replace missing data with zero; reject.
- `T-HVA-013-REC` — A rule-version update rechecks affected candidates from retained facts and does not overwrite prior decisions.
- `T-HVA-014-POS` — Recheck a changed security/route state immediately while leaving unchanged rejected candidates within their valid cooldown.
- `T-HVA-014-NEG` — Keep a previous rejection forever after a changed authority, or requeue without bounds on each duplicate event; detect.
- `T-HVA-014-REC` — Restart reconstructs queues and rejection expiry without duplicate jobs or lost source leases.
- `T-HVA-023-POS` — Evaluate a newly discovered asset using only available history and return unknown for an unsupported growth/rate claim.
- `T-HVA-023-NEG` — Divide by a fabricated previous volume or label an unobserved route exit as zero loss; fail.
- `T-HVA-023-REC` — As history matures, create a new eligible feature/label version without retroactively improving prior predictions.
- `T-HVA-024-POS` — Attach matured outcomes and publish unresolved counts with pessimistic/alternative sensitivity assumptions.
- `T-HVA-024-NEG` — Discard unavailable losing routes or count scam flags as guaranteed money saved; reject economic qualification.
- `T-HVA-024-REC` — Late outcomes produce auditable study revisions rather than changing sealed policy decisions.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-041 — BE-039: Solana token capability and uncertainty analyzer
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-037, BE-038.
**Requirement owners:** VAN-HVA-015.

**Exit contract:** Complete all stated operations in the existing owners. Read-only Solana observations → security finding store → screening, route analysis and feature research. Verify a real registered positive caller/readback, negative and recovery paths under exact source/provider scope. Unsupported extensions, active/revoked authority parsing, lag and changed program state cannot yield SAFE_TO_BUY. No fixture substitutes for required real provider integration, and no research result grants financial authority.

**All deliverables:**
- Distinguish supported SPL Token and Token-2022 capabilities with explicit parser/program versions.
- Inspect authority, transfer-fee/hook/delegate/extension evidence and technical account roles without transactions.
- Emit factual REJECT/INVESTIGATE/NO_HARD_BLOCK findings, unsupported/unknown states and anchored provenance.

**Planned test obligations (all NOT_RUN):**
- `T-HVA-015-POS` — Evaluate versioned fixtures with revoked/active/unknown authorities, technical accounts and relevant extension combinations.
- `T-HVA-015-NEG` — Treat an unparsed extension as harmless or a missing authority as proven revoked; refuse a clear verdict.
- `T-HVA-015-REC` — After changed program/authority or source lag, invalidate affected security descendants and issue a fresh state-bound result.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-042 — BE-040: EVM contract/proxy capability and uncertainty analyzer
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-037, BE-038.
**Requirement owners:** VAN-HVA-016.

**Exit contract:** Complete all stated operations in the existing owners. Read-only EVM observations → security finding store → screening and sell simulation. Verify a real registered positive caller/readback, negative and recovery paths under exact source/provider scope. Changed proxy implementations, misleading verified shells and unsupported dynamic restrictions must not be treated safe. No fixture substitutes for required real provider integration, and no research result grants financial authority.

**All deliverables:**
- Inspect chain-qualified code/proxy/implementation/admin state with source and state hashes.
- Evaluate transfer/mint/blacklist/tax/max-transaction and liquidity-removal capabilities through supported read-only evidence.
- Retain code-verification uncertainty and state-dependent restrictions; no signing or broadcast operations.

**Planned test obligations (all NOT_RUN):**
- `T-HVA-016-POS` — Evaluate actual code/state fixtures for proxy upgrades, owner controls and transfer constraints with precise factual reasons.
- `T-HVA-016-NEG` — Trust a verified proxy shell while ignoring its changed implementation or state-dependent sell restriction; detect.
- `T-HVA-016-REC` — Implementation/code/state change invalidates dependent findings and simulations while retaining pre-change evidence.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-043 — VAN-ML-PKT-006: Shared feature definitions and Feast parity
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-003, BE-008, PRE-003, VAN-ML-PKT-005.
**Requirement owners:** VAN-CX-012, VAN-ML-REQ-008, VAN-ML-REQ-009, VAN-ML-REQ-010.

**Exit contract:** Offline/online values and units match within declared tolerances; Shift peer data, change column order or fit a scaler on validation: qualification fails

**All deliverables:**
- Extend existing FeatureRegistry and feature contracts; compile offline/online transformations from one version
- Implement lag/timeframe/peer expansion, fold-fitted preprocessing and aligned row masks
- Integrate scoped Feast feature views/materialization and deterministic local inference snapshots

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-008-P` — Replay identical snapshot through training and serving transforms.
- `VAN-ML-AT-008-N` — Permute a feature column or change unit while keeping old manifest: reject.
- `VAN-ML-AT-009-P` — Apply a declared row filter and verify row IDs across features, targets and weights.
- `VAN-ML-AT-009-N` — Validation-fitted scaler or independent target-row filtering fails.
- `VAN-ML-AT-010-P` — Version added peer/lag features and compare their incremental contribution.
- `VAN-ML-AT-010-N` — A negative feature shift or asynchronous future peer close fails prefix tests.
- `T-VAN-CX-012-POS` — From permitted raw inputs, a second run reproduces the same bars, sessions, costs and outcomes.
- `T-VAN-CX-012-NEG` — Bid is silently treated as midpoint, fixed EST becomes DST-local time, a bar is used before close or a mirror is unpinned: reject qualifying use.
- `T-VAN-CX-012-REC` — Keep lawful metadata and reproducibility scripts without republishing restricted data; qualifying tests await admitted data while unrelated authorized engineering continues.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-044 — BE-042: Temporal wallet attribution and holder-flow intelligence
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-039, BE-040, VAN-ML-PKT-006.
**Requirement owners:** VAN-HVA-020, VAN-HVA-021, VAN-HVA-022, VAN-HVA-023.

**Exit contract:** Complete all stated operations in the existing owners. Anchored chain observations → historical wallet/role snapshots → feature pipelines and screening research. Verify a real registered positive caller/readback, negative and recovery paths under exact source/provider scope. AMM-as-insider, router-as-buy, common-funding-as-proof and impossible young-token ratios are rejected. No fixture substitutes for required real provider integration, and no research result grants financial authority.

**All deliverables:**
- Persist comparable time-indexed holdings, transfers, supply and technical-role evidence.
- Retain raw and adjusted concentration plus uncertain funding/ownership clusters; deduplicate transaction-level routes.
- Produce growth/flow/manipulation research features with coverage and missingness, never narratives from a single snapshot.

**Planned test obligations (all NOT_RUN):**
- `T-HVA-020-POS` — Compute changes across anchored snapshots while retaining the raw source series and coverage interval.
- `T-HVA-020-NEG` — Infer accumulation or holder growth from one snapshot or compare unequal source scopes without disclosure; abstain.
- `T-HVA-020-REC` — A late/backfilled observation changes a new analytical version only; it does not appear in an earlier decision-time dataset.
- `T-HVA-021-POS` — Explain raw and adjusted concentration with every role exclusion and uncertainty interval traceable to source evidence.
- `T-HVA-021-NEG` — Flag an AMM vault as an insider solely because it holds over a threshold or silently erase uncertain accounts; fail.
- `T-HVA-021-REC` — Role reassignment triggers a versioned feature recomputation and reevaluation of affected decisions, not historical fact mutation.
- `T-HVA-022-POS` — Reconstruct a routed transfer and an actual buy without double-counting intermediate hops, retaining clustering assumptions.
- `T-HVA-022-NEG` — Classify every transfer as a purchase or common funding as conclusive common ownership; reject the assertion.
- `T-HVA-022-REC` — Replay updated decoders and labels under a new transform version, preserving the original episode references.
- `T-HVA-023-POS` — Evaluate a newly discovered asset using only available history and return unknown for an unsupported growth/rate claim.
- `T-HVA-023-NEG` — Divide by a fabricated previous volume or label an unobserved route exit as zero loss; fail.
- `T-HVA-023-REC` — As history matures, create a new eligible feature/label version without retroactively improving prior predictions.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-045 — VAN-ML-PKT-007: Targets, executable labels and outcome provenance
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-008, BE-018, PRE-003, VAN-ML-PKT-005, VAN-ML-PKT-006.
**Requirement owners:** VAN-HVA-005, VAN-HVA-007, VAN-HVA-023, VAN-HVA-024, VAN-ML-REQ-011, VAN-ML-REQ-012, VAN-ML-REQ-013.

**Exit contract:** Labels cannot mature before horizon/outcome availability; Gross/net/cost conventions reconcile; future holding duration cannot become an entry feature

**All deliverables:**
- Build returns, setup-event, ranking, realized-volatility, cost and excursion targets with explicit label intervals
- Keep market observations, actual fills, synthetic controls, practice and counterfactual outcomes in separate namespaces
- Preserve candidate sampling, rejection reason and censoring to expose selection bias
- Separate terminal return, strategy outcome, adverse excursion, stop touch and fill targets; distinguish observed quotes from modeled cost distributions.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-011-P` — Build an executable horizon label only after all required observations mature.
- `VAN-ML-AT-011-N` — Post-entry holding duration presented as a known entry feature is rejected.
- `VAN-ML-AT-012-P` — Build explicitly separated actual and counterfactual cohort reports.
- `VAN-ML-AT-012-N` — A practice record promoted to live outcome provenance fails.
- `VAN-ML-AT-013-P` — Compare labels against independent hand calculations for admitted instrument classes.
- `VAN-ML-AT-013-N` — Double cost deduction or invalid distribution support is detected.
- `T-HVA-005-POS` — Reconcile a quoted entry, modeled exit/failure costs and aggregate edge without double-counting spread, impact, gas or transfer charges.
- `T-HVA-005-NEG` — Pass an uncalibrated fill estimate as an observed quote or subtract a fee already included in proceeds; detect both errors.
- `T-HVA-005-REC` — Fee, model or quote-state changes invalidate affected assessments and reprice them with retained original versions.
- `T-HVA-007-POS` — Fit and score each target against its correctly matured observations with non-overlapping training/validation availability.
- `T-HVA-007-NEG` — Use a terminal downside quantile as a calibrated stop-touch probability or pass future context into historical features; reject.
- `T-HVA-007-REC` — After target-policy revision, invalidate incompatible calibration and model use while preserving baseline operation.
- `T-HVA-023-POS` — Evaluate a newly discovered asset using only available history and return unknown for an unsupported growth/rate claim.
- `T-HVA-023-NEG` — Divide by a fabricated previous volume or label an unobserved route exit as zero loss; fail.
- `T-HVA-023-REC` — As history matures, create a new eligible feature/label version without retroactively improving prior predictions.
- `T-HVA-024-POS` — Attach matured outcomes and publish unresolved counts with pessimistic/alternative sensitivity assumptions.
- `T-HVA-024-NEG` — Discard unavailable losing routes or count scam flags as guaranteed money saved; reject economic qualification.
- `T-HVA-024-REC` — Late outcomes produce auditable study revisions rather than changing sealed policy decisions.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-046 — VAN-ML-PKT-008: Chronological folds, lookahead and warmup diagnostics
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-035, PRE-003, VAN-ML-PKT-006, VAN-ML-PKT-007.
**Requirement owners:** VAN-CX-011, VAN-ML-REQ-014, VAN-ML-REQ-015, VAN-ML-REQ-016.

**Exit contract:** Leakage, full-data normalization, random splits and future exogenous values are detected; Overlapping horizons do not inflate independent sample counts

**All deliverables:**
- Implement FoldPlan with interval purging, cohort-coherent cutoffs, calibration slices and embargo policy
- Build full-versus-prefix and positive-poison diagnostics inspired by Freqtrade
- Measure indicator/model feature convergence versus warmup and cache identity

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-014-P` — Demonstrate disjoint information intervals while retaining lawful historical context.
- `VAN-ML-AT-014-N` — Random time splits or labels extending through validation boundary fail.
- `VAN-ML-AT-015-P` — A causal strategy is stable at identical cutoff after sufficient warmup.
- `VAN-ML-AT-015-N` — Leaked future field, centered rolling window or full-data statistic changes prefix result.
- `VAN-ML-AT-016-P` — A single final evaluation references the frozen study census.
- `VAN-ML-AT-016-N` — Second tuning pass on observed holdout without a new untouched period is blocked.
- `T-VAN-CX-011-POS` — Replay of each named chronological fold yields the same pre-cutoff decisions and verified split provenance.
- `T-VAN-CX-011-NEG` — Future-only perturbation changes past decisions, a scaler sees the holdout, or window count is only the count of calendar years: fail.
- `T-VAN-CX-011-REC` — Tainted fold/candidate artifacts cannot be reused as independent promotion evidence; retain audit lineage.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-047 — VAN-ML-PKT-009: Simulation accounting, intrabar and timing corrections
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-035, PRE-003, VAN-ML-PKT-005, VAN-ML-PKT-007.
**Requirement owners:** VAN-HVA-018, VAN-ML-REQ-017, VAN-ML-REQ-018, VAN-ML-REQ-019.

**Exit contract:** Long/short both-hit, gap-stop, same-close latency, funding boundary and partial-fill cases reconcile; Closed-trade metrics and pre-flatten final equity cannot certify economic performance

**All deliverables:**
- Reproduce and close scoped main-source findings; implement observed intrabar ordering or explicit uncertainty bounds
- Debit commission, financing, borrow/roll and conversion costs exactly once alongside fill spread/slippage
- Produce post-liquidation MTM equity, drawdown and cash-flow-neutral performance with pending risk

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-017-P` — Both stop and target touched: long and short and mixed portfolio ambiguity are explicit.
- `VAN-ML-AT-017-N` — Independent contradictory paths presented as one portfolio market history fail.
- `VAN-ML-AT-018-P` — Commission, funding, gap and final close reconcile to ledger cash and MTM.
- `VAN-ML-AT-018-N` — Risk cost estimate substituted for P&L deductions or pre-flatten final equity fails.
- `VAN-ML-AT-019-P` — Deposit changes collateral but not historical trading return; open loss appears in MTM drawdown.
- `VAN-ML-AT-019-N` — Deposit erases loss, withdrawal is labelled trading loss or closed-only DD certifies exposure: fail.
- `T-HVA-018-POS` — Reconcile small and larger trade-size scenarios with observed route depth and the full fee convention.
- `T-HVA-018-NEG` — Linearly scale a small-size quote to exceed available depth or deduct included costs twice; fail.
- `T-HVA-018-REC` — When a route disappears or fees change, revoke stale economics and produce a new unknown/refused readback.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-048 — BE-041: State-bound buy/sell simulations and executable quote facts
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-039, BE-040, BE-010, VAN-ML-PKT-007, VAN-ML-PKT-009.
**Requirement owners:** VAN-HVA-005, VAN-HVA-017, VAN-HVA-018.

**Exit contract:** Complete all stated operations in the existing owners. Anchored route facts and simulations → existing economics evidence store → candidate research and evaluation. Verify a real registered positive caller/readback, negative and recovery paths under exact source/provider scope. Buy-only success, changed transfer tax, worse-than-limit fill assumptions, disappearing liquidity and nonlinear costs must fail. No fixture substitutes for required real provider integration, and no research result grants financial authority.

**All deliverables:**
- Record independent buy/sell read-only simulation outcomes, route, amount, caller assumptions and state/finality.
- Measure executable depth and cost conventions at several declared sizes; separate quotes from future cost/fill models.
- Join to existing net-edge and TCA/label contracts with no double counting; invalid/unknown exitability remains research-only.

**Planned test obligations (all NOT_RUN):**
- `T-HVA-005-POS` — Reconcile a quoted entry, modeled exit/failure costs and aggregate edge without double-counting spread, impact, gas or transfer charges.
- `T-HVA-005-NEG` — Pass an uncalibrated fill estimate as an observed quote or subtract a fee already included in proceeds; detect both errors.
- `T-HVA-005-REC` — Fee, model or quote-state changes invalidate affected assessments and reprice them with retained original versions.
- `T-HVA-017-POS` — Produce separate state-bound buy/sell outcomes, executable quantities and explicit failure reasons for a reversible route.
- `T-HVA-017-NEG` — Buy succeeds but sell reverts, transfers are taxed unexpectedly or simulation state is stale; no viable sellability assertion.
- `T-HVA-017-REC` — Changed router/contract/pool state invalidates the result and all affected economic descendants before any reuse.
- `T-HVA-018-POS` — Reconcile small and larger trade-size scenarios with observed route depth and the full fee convention.
- `T-HVA-018-NEG` — Linearly scale a small-size quote to exceed available depth or deduct included costs twice; fail.
- `T-HVA-018-REC` — When a route disappears or fees change, revoke stale economics and produce a new unknown/refused readback.
- `T-REV113-021` — DEX buy/sell economics are exact, gas/fee/slippage/route-sensitive; unknown sellability abstains

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-049 — VAN-ML-PKT-010: Account-wide replay and execution-policy parity
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-012, BE-035, PRE-003, VAN-ML-PKT-008, VAN-ML-PKT-009.
**Requirement owners:** VAN-HVA-006, VAN-HVA-025, VAN-ML-REQ-020, VAN-ML-REQ-021.

**Exit contract:** Concurrent orders/cancel-fill races and capital contention have equivalent risk decisions; Zero-trade replay does not stand in for exercised approval, rejection and protection paths

**All deliverables:**
- Replay through the shared account coordinator/risk/reservation/route policy, not only independent single-symbol cycles
- Build comparable event streams, symbol calendars, margin and instrument specifications
- Provide independent oracle export and documented comparator differences; no second live sender
- Replay both whole-policy accounts independently, with nonlinear fees/liquidity, changed trade paths, cash and margin; retain size-only attribution as its separately labelled existing view.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-020-P` — Concurrent candidates contend for the same simulated risk/capital budget.
- `VAN-ML-AT-020-N` — Independent symbol backtests summed as a feasible portfolio result fail.
- `VAN-ML-AT-021-P` — Approval, reduction, rejection, expiry and protection paths are all replayed.
- `VAN-ML-AT-021-N` — Zero checked decisions reported as full successful decision coverage fail.
- `T-HVA-006-POS` — Show size-only attribution and independently simulated policy performance as separate, correctly labelled results.
- `T-HVA-006-NEG` — Scale nonlinear gas/slippage or a different entry/exit path by the actual trade R and call it realized performance; reject.
- `T-HVA-006-REC` — On a revised fill model recompute simulated results without editing actual venue receipts or historical size-only attribution.
- `T-HVA-025-POS` — Show the same cohort under two policies whose skipped trade changes later capital availability and compare complete net cash paths.
- `T-HVA-025-NEG` — Sum isolated profitable trades above account capital or reuse actual exits for a different entry/asset; reject.
- `T-HVA-025-REC` — Interrupted replay resumes from the exact arm checkpoint with stable hashes and no shared mutable state between arms.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-050 — VAN-ML-PKT-011: Qlib data, processor and recorder integration
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-004, VAN-ML-PKT-006, VAN-ML-PKT-007, VAN-ML-PKT-008.
**Requirement owners:** VAN-ML-REQ-022.

**Exit contract:** DK_L/DK_I separation, train-only processor fitting and prediction index identity verified; Qlib default execution path and unrestricted YAML imports are rejected

**All deliverables:**
- Implement VanQlibDataLoader and fold-scoped DataHandlerLP/DatasetH adapter over VAN-owned snapshots
- Register T3 training tasks and explicit Qlib Recorder/MLflow run binding
- Use model APIs only; disable Qlib execution/exchange and default equity-region semantics in VAN runtime

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-022-P` — Compare indexed predictions and train-only preprocessing against the source dataset.
- `VAN-ML-AT-022-N` — Qlib regional exchange defaults or dynamic unapproved YAML classes fail startup.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-051 — VAN-ML-PKT-012: LightGBM expected-return and net-edge regressors
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-010, VAN-ML-PKT-011.
**Requirement owners:** VAN-ML-REQ-023.

**Exit contract:** Reproducible fixed-environment fits; native export/import numerical equivalence; Data/feature order mismatch and net-cost double subtraction fail tests

**All deliverables:**
- Train horizon/cohort-specific regression baselines with explicit cost conventions and objective semantics
- Export native Booster plus feature/target/preprocessor manifests
- Implement out-of-fold predictions, stopping, uncertainty comparison and diagnostic explanations

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-023-P` — Fit/infer/reload under fixed environment and compare predictions.
- `VAN-ML-AT-023-N` — Feature-order, objective, target or cost-basis mismatch rejects the artifact.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-052 — VAN-ML-PKT-013: LightGBM setup-event classification
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-010, VAN-ML-PKT-011.
**Requirement owners:** VAN-ML-REQ-024.

**Exit contract:** Class score is not called win probability until packet020 calibration passes; Unmatured labels, resampling bias and leaked outcome fields fail

**All deliverables:**
- Implement binary event targets and raw-probability output with defined censor/tie behavior
- Create disjoint calibration handoff, imbalance controls and reliability metadata
- Compare against event base rate and existing rules on the same candidate population

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-024-P` — Evaluate raw output against base rates on the same candidate population.
- `VAN-ML-AT-024-N` — Class weighting/resampling output advertised as calibrated probability fails.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-053 — VAN-ML-PKT-014: LightGBM quantile and grouped ranking adapters
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-010, VAN-ML-PKT-011.
**Requirement owners:** VAN-ML-REQ-025, VAN-ML-REQ-026.

**Exit contract:** Stock LGBModel wrapper is not used with unsupported loss values; Negative regression labels passed as rank relevance and cross-date groups are rejected

**All deliverables:**
- Implement VAN-owned Qlib-compatible/direct-LightGBM adapters for quantile and ranking objectives
- Train explicit alpha/horizon quantiles and grouped cutoff/universe ranking with integer relevance rules
- Validate quantile order, group contiguity and units; rank score remains ordinal

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-025-P` — Fit requested alpha models and validate ordered quantiles on evaluation data.
- `VAN-ML-AT-025-N` — Pass quantile into stock Qlib LGBModel loss, or accept crossed quantiles without handling: fail.
- `VAN-ML-AT-026-P` — Verify group sizes/ordering sum to rows and rank metrics use the same cohort.
- `VAN-ML-AT-026-N` — Continuous negative return labels or cross-time query group leak are rejected.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-054 — VAN-ML-PKT-015: Challenger and simple baseline suite
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-010, VAN-ML-PKT-011.
**Requirement owners:** VAN-ML-REQ-027.

**Exit contract:** Every mandatory task has a meaningful naive and incumbent comparison; Different horizons, price units, sample windows or costs cannot be compared as like-for-like

**All deliverables:**
- Integrate XGBoost as a comparable tabular challenger and linear/logistic/persistence/ranking baselines
- Include HAR-style realized-volatility and authorized GARCH implementations with identical data cutoffs
- Version each baseline and preserve failed/no-skill results

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-027-P` — Report matched loss, cost and coverage comparisons with sample counts.
- `VAN-ML-AT-027-N` — Compare different horizons or omit a stronger simple baseline to claim victory: fail.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-055 — VAN-ML-PKT-016: NeuralForecast bridge and N-HiTS
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-004, VAN-ML-PKT-006, VAN-ML-PKT-007, VAN-ML-PKT-008, VAN-ML-PKT-010.
**Requirement owners:** VAN-ML-REQ-028, VAN-ML-REQ-029.

**Exit contract:** Actual locked-library training/inference on admitted data; Calendar gaps, unavailable future values and scaler refits at prediction fail

**All deliverables:**
- Implement canonical unique_id/ds/y and historical/future/static exogenous mapping
- Integrate NHITS multi-horizon training, native validation and fold-scoped scaling
- Capture native outputs and learned preprocessing in the shared experiment/artifact contract

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-028-P` — Round-trip aligned panel data and verify output identity and dimensions.
- `VAN-ML-AT-028-N` — Duplicate timestamps, unseen cohort semantics or predictor-time scaler refit fail.
- `VAN-ML-AT-029-P` — Execute train/export/reload/infer/evaluate on admitted real historical data.
- `VAN-ML-AT-029-N` — An import-only plugin or canned forecast cannot close this requirement.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-056 — VAN-ML-PKT-017: N-BEATSx contextual forecasts and decomposition
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-016.
**Requirement owners:** VAN-ML-REQ-030.

**Exit contract:** Actual contextual prediction and decomposition round trip; Explanations cannot claim causal drivers or invent contributions for an unsupported configuration

**All deliverables:**
- Implement NBEATSx model plugin and valid exogenous capabilities
- Expose trend/seasonality/exogenous decomposition only when the chosen architecture supports it
- Measure contextual ablation and explanatory output stability

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-030-P` — Ablate contextual covariates and compare forecast/decomposition before and after reload.
- `VAN-ML-AT-030-N` — Future actual releases, unavailable decomposition or fabricated causal labels fail.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-057 — VAN-ML-PKT-018: DeepAR distributional forecasts and retained scenarios
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-016.
**Requirement owners:** VAN-ML-REQ-031.

**Exit contract:** Distribution support and raw-path dimensions verified with a real model; Averaged trajectories cannot masquerade as samples; independent assets cannot claim joint portfolio coverage

**All deliverables:**
- Integrate DeepAR distribution loss, target-domain checks and pinned RNG/sample manifests
- Retain individual trajectories through a tested adapter, or expose UNSUPPORTED_RAW_PATHS for a pinned API while implementing the documented retained-path adapter before closure
- Keep marginal intervals separate from temporal and cross-asset joint-scenario claims

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-031-P` — Compare raw sample tensor, aggregation and original-domain output calculations.
- `VAN-ML-AT-031-N` — A mean path or independently sampled marginal quantiles labelled joint scenarios fails.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-058 — VAN-ML-PKT-019: Contextual and multivariate neural challengers
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018.
**Requirement owners:** VAN-HVA-001, VAN-ML-REQ-032.

**Exit contract:** Do not infer support from constructor argument names alone; Global shared weights are not labelled joint dependence, and invalid capabilities fail before training

**All deliverables:**
- Provide usable research plugins for TFT, PatchTST and iTransformer with capability introspection and target compatibility
- Bound cross-market cohorts, missing histories, architecture-specific exogenous support and compute budgets
- Test each admitted plugin in training/export/load/inference; economic admission remains conditional

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-032-P` — Each plugin completes actual train/export/load/infer and reports unsupported inputs before fit.
- `VAN-ML-AT-032-N` — Constructor field presence alone used as proof of exogenous support fails.
- `T-HVA-001-POS` — Exercise each required train/export/load/predict or event-laboratory operation through its real registered consumer; record a truthful rejected or inconclusive economic result when appropriate.
- `T-HVA-001-NEG` — Remove DeepAR, a required challenger plugin or an event-research laboratory and attempt complete-backend admission; missing capability must be detected.
- `T-HVA-001-REC` — Restore a previous model package without dropping any mandatory API or laboratory; stale economic permission remains inactive.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-059 — VAN-ML-PKT-020: One calibration and uncertainty-validation boundary
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-015, VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-019.
**Requirement owners:** VAN-CX-013, VAN-HVA-007, VAN-HVA-028, VAN-ML-REQ-033, VAN-ML-REQ-034, VAN-ML-REQ-035.

**Exit contract:** Calibration/test separation and stale/mismatched residual refusal verified; Nine residuals or nominal coverage alone cannot establish reliable trading confidence

**All deliverables:**
- Extend existing vati.risk.conformal through separate forecast calibration producers and source-bound buckets
- Implement probability calibration, quantile evaluation, optional conformalized intervals and realized coverage monitoring
- Bind residuals to model/target/cohort/horizon and invalidate on refit; correct guarantee language
- Apply one existing calibration policy with distinct target/model/horizon/state bindings; no source grade or judgment confidence can substitute.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-033-P` — Old deterministic conformal consumers retain semantics and new buckets enforce identity.
- `VAN-ML-AT-033-N` — New library calibration silently replaces existing risk policy or raises size: fail.
- `VAN-ML-AT-034-P` — Evaluate reliability, Brier/log loss or quantile coverage by horizon/cohort with uncertainty.
- `VAN-ML-AT-034-N` — Nominal coverage or mathematical minimum residual count used as economic qualification fails.
- `VAN-ML-AT-035-P` — Refit invalidates the old calibrator; inverse-transform uncertainty is checked.
- `VAN-ML-AT-035-N` — Sum marginal quantiles or exponentiate log-mean as arithmetic expectation without correction: fail.
- `T-VAN-CX-013-POS` — Each reported metric identifies the population, formula/version, trial set, uncertainty and selection scope.
- `T-VAN-CX-013-NEG` — A pooled PBO is relabeled pair-specific, losers disappear from trial count, or repeated holdout tuning is called independent: fail promotion.
- `T-VAN-CX-013-REC` — A no-qualified-candidate result is valid; do not search until a cherry-picked pass can be manufactured.
- `T-HVA-007-POS` — Fit and score each target against its correctly matured observations with non-overlapping training/validation availability.
- `T-HVA-007-NEG` — Use a terminal downside quantile as a calibrated stop-touch probability or pass future context into historical features; reject.
- `T-HVA-007-REC` — After target-policy revision, invalidate incompatible calibration and model use while preserving baseline operation.
- `T-HVA-028-POS` — Compare no-LLM/rule, shared Jev and another approved challenger on identical sealed questions and independently observable outcomes, including cost and abstention.
- `T-HVA-028-NEG` — Promote an answer-quality score or artifact hash as calibrated trade probability or independent corroboration of the same source; reject.
- `T-HVA-028-REC` — Question/model/input-policy revisions invalidate incompatible calibration and retain usable explanation-only fallback.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-060 — VAN-ML-PKT-021: Unified Optuna and rolling research studies
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-008, VAN-ML-PKT-011, VAN-ML-PKT-015, VAN-ML-PKT-019, VAN-ML-PKT-020.
**Requirement owners:** VAN-CX-011, VAN-CX-013, VAN-HVA-026, VAN-ML-REQ-036.

**Exit contract:** Search cannot observe final holdout or mutate live aliases; Repeat study from snapshot and detect data, target, trial-count and environment changes

**All deliverables:**
- Use one study/budget/trial ledger for Qlib, native LightGBM and NeuralForecast candidates
- Implement bounded neural Auto/Optuna adapter, nested temporal selection and independent final holdout
- Preserve all tried configurations, early/pruned failures and comparison lineage

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-036-P` — Pause/resume a study and retain failed/pruned trial history and immutable inputs.
- `VAN-ML-AT-036-N` — Parallel untracked studies or direct writes to live model binding fail.
- `T-VAN-CX-011-POS` — Replay of each named chronological fold yields the same pre-cutoff decisions and verified split provenance.
- `T-VAN-CX-011-NEG` — Future-only perturbation changes past decisions, a scaler sees the holdout, or window count is only the count of calendar years: fail.
- `T-VAN-CX-011-REC` — Tainted fold/candidate artifacts cannot be reused as independent promotion evidence; retain audit lineage.
- `T-VAN-CX-013-POS` — Each reported metric identifies the population, formula/version, trial set, uncertainty and selection scope.
- `T-VAN-CX-013-NEG` — A pooled PBO is relabeled pair-specific, losers disappear from trial count, or repeated holdout tuning is called independent: fail promotion.
- `T-VAN-CX-013-REC` — A no-qualified-candidate result is valid; do not search until a cherry-picked pass can be manufactured.
- `T-HVA-026-POS` — Evaluate clustered paired outcomes under a locked hypothesis and compare against exposure-matched/simple baselines with all trial costs.
- `T-HVA-026-NEG` — Resample every snapshot as independent, peek repeatedly until significance or introduce a second conflicting threshold service; reject.
- `T-HVA-026-REC` — A policy amendment invalidates affected qualification claims while retaining all prior studies, including losing trials.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-061 — VAN-ML-PKT-022: Safe model artifacts and candidate registry
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-004, VAN-ML-PKT-011, VAN-ML-PKT-020, VAN-ML-PKT-021.
**Requirement owners:** VAN-ML-REQ-037, VAN-ML-REQ-038.

**Exit contract:** No untrusted pickle, unapproved dynamic imports or unchecked remote model URI; Changing registry alias cannot change admitted runtime model without a valid binding

**All deliverables:**
- Implement native Booster and safe neural artifact formats with verified source/configuration/manifests
- Connect MLflow versions/runs and immutable VAN admission records; aliases remain advisory
- Implement atomic stage transitions, CAS deployment binding and rollback compatibility

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-037-P` — Corrupted/tampered model is rejected before deserialization and fallback is recorded.
- `VAN-ML-AT-037-N` — Untrusted pickle, arbitrary import or unchecked remote URI fails.
- `VAN-ML-AT-038-P` — Admit an exact version through independently verified binding and CAS epoch.
- `VAN-ML-AT-038-N` — Alias swap or attacker-authored certificate leaves active model unchanged.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-062 — VAN-ML-PKT-023: Adaptive retraining scheduler and lifecycle
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-028, PRE-003, VAN-ML-PKT-021, VAN-ML-PKT-022.
**Requirement owners:** VAN-ML-REQ-039, VAN-ML-REQ-040.

**Exit contract:** Kill/restart trainer and duplicate trigger produce no duplicate publication; Old model remains only while valid; training completion never means approved deployment

**All deliverables:**
- Implement FreqAI-inspired retraining cadence, drift-triggered jobs, expiry and per-scope queues
- Use existing durable workflow/scheduler owner, bounded retries, resumable checkpoints and worker leases
- Finish candidate fits without automatic promotion; prioritize inference/protection over training

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-039-P` — Restart at each job state and recover without duplicate model publication.
- `VAN-ML-AT-039-N` — Training finished marks model live or expired model used while waiting: fail.
- `VAN-ML-AT-040-P` — Burst retraining requests produce bounded pending work and measured noninterference.
- `VAN-ML-AT-040-N` — Heavy study admitted using stale capacity or no budget is refused.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-063 — VAN-ML-PKT-024: Forecast serving, cache, freshness and novelty gates
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-006, VAN-ML-PKT-020, VAN-ML-PKT-022, VAN-ML-PKT-023.
**Requirement owners:** VAN-HVA-030, VAN-ML-REQ-041, VAN-ML-REQ-042, VAN-ML-REQ-043.

**Exit contract:** Timeout, corrupt model, OOD, stale feed, changed feature order and queue saturation return truthful abstention; No synchronous network/model load can enter T0 risk or protection

**All deliverables:**
- Implement typed bounded ForecastService and immutable cache keys tied to actual material inputs
- Add model/data/calibration freshness, schema validation, DI-style novelty and optional SVM/DBSCAN/PCA ablations
- Persist accepted and abstained outputs with explicit reason and identity; no order fields

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-041-P` — Authenticated caller receives correct horizon/scalar/quantile identities.
- `VAN-ML-AT-041-N` — NaN, Infinity, wrong account/venue, order quantity or executable instruction fails.
- `VAN-ML-AT-042-P` — Old-but-freshly-served model and new prediction over stale data both fail as appropriate.
- `VAN-ML-AT-042-N` — Novelty score labelled probability or tail observations silently deleted to improve metrics: fail.
- `VAN-ML-AT-043-P` — Service timeout returns bounded abstention and protection continues.
- `VAN-ML-AT-043-N` — Cache reused after target/model/feature/adjustment revision is rejected.
- `T-HVA-030-POS` — Replay sealed outcomes exactly and test serving within its declared numeric tolerance, latency and applicability domain.
- `T-HVA-030-NEG` — Synchronously call a chain indexer/model registry from T0 or label an expired/reorganized result ready; refuse.
- `T-HVA-030-REC` — A checkpoint/environment change triggers compatibility and tolerance tests; crash recovery preserves result identity and baseline availability.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-064 — VAN-ML-PKT-025: Forecast fusion, arbiter and mode evidence integration
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-013, PRE-003, VAN-ML-PKT-010, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-019, VAN-ML-PKT-020, VAN-ML-PKT-024.
**Requirement owners:** VAN-HVA-027, VAN-HVA-028, VAN-HVA-029, VAN-ML-REQ-044, VAN-ML-REQ-045, VAN-ML-REQ-046.

**Exit contract:** Model disagreement, duplicate-signal confidence, missing edge and mid-cycle model change are handled; Arbiter output still requires new TradeIntent, RiskSnapshot, RiskAuthority and sole router

**All deliverables:**
- Join forecasts into existing OpportunityEngine/MetaLabeler and account coordinator through versioned evidence inputs
- Train fusion only on OOF predictions, measure redundancy, preserve baseline fallback policies
- Bind independent economic admission producer to Normal/Risky/Aggressive use; never modify signed ceilings

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-044-P` — Ablate each model and compare against strongest single incumbent on matched outcomes.
- `VAN-ML-AT-044-N` — Duplicated correlated signals counted as independent confirmation fail.
- `VAN-ML-AT-045-P` — Every consequential decision retains exact mandate/risk/intent/route receipt.
- `VAN-ML-AT-045-N` — Forecast tries to widen stop, raise ceilings, submit order or alter funds: reject.
- `VAN-ML-AT-046-P` — Sandbox admission and refusal both execute through genuine consumer paths.
- `VAN-ML-AT-046-N` — Aggressive solely on model confidence, unbound evidence or wrong environment fails.
- `T-HVA-027-POS` — A real registered question set receives an anchored snapshot and returns a schema-valid answer/unknown with source and deadline lineage.
- `T-HVA-027-NEG` — An external post requests orders, secrets or overriding a mandatory exit; no tool invocation or authority change occurs.
- `T-HVA-027-REC` — On timeout/provider revocation the established deterministic baseline remains available and all pending judgments become expired/unknown.
- `T-HVA-028-POS` — Compare no-LLM/rule, shared Jev and another approved challenger on identical sealed questions and independently observable outcomes, including cost and abstention.
- `T-HVA-028-NEG` — Promote an answer-quality score or artifact hash as calibrated trade probability or independent corroboration of the same source; reject.
- `T-HVA-028-REC` — Question/model/input-policy revisions invalidate incompatible calibration and retain usable explanation-only fallback.
- `T-HVA-029-POS` — Replay the inherited V0/V1 behavior unchanged, then separately test an admitted ranking-policy version with exact feature/forecast lineage.
- `T-HVA-029-NEG` — Enable model-weighted ranking by merely selecting AllocatorV1, duplicate the allocator or use ranking to exceed portfolio reservations; reject.
- `T-HVA-029-REC` — Revoke the ranking extension and restore the qualified baseline without releasing pending-order reservations or changing mandates.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-065 — VAN-ML-PKT-026: Instrument and strategy protection policies
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-012, PRE-003, VAN-ML-PKT-010, VAN-ML-PKT-025.
**Requirement owners:** VAN-ML-REQ-047.

**Exit contract:** Partial fills do not multiply loss counts; restarts cannot erase locks; All entry blocks preserve authorized reductions, stop protection and manual control ownership

**All deliverables:**
- Add native cooldown, stop-loss streak and low-profit suppression proposals inspired by Freqtrade
- Reuse existing drawdown/kill/health controls and resolve overlapping suppression deterministically
- Persist per-account/environment/strategy/instrument/direction state and reasons

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-047-P` — Deduplicated losses, persistent locks and defined session expiry reproduce after restart.
- `VAN-ML-AT-047-N` — Protection suppresses authorized exits, counts fills as separate trades or resets on restart: fail.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-066 — VAN-ML-PKT-027: Outcome ledger, drift and proprietary learning data
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-007, VAN-ML-PKT-023, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-026.
**Requirement owners:** VAN-HVA-024, VAN-HVA-025, VAN-ML-REQ-048, VAN-ML-REQ-049.

**Exit contract:** Deletion/correction invalidates affected derived models without pretending unlearning; Feature drift triggers candidate work or abstention, never unilateral risk expansion

**All deliverables:**
- Persist input-to-forecast-to-decision-to-outcome attribution and counterfactual separation
- Connect existing drift/health/replay and observed broker costs to candidate retraining requests
- Implement privacy/retention/correction invalidation, consented manual-trade datasets and no-survivor bias
- Retain full discovery cohorts, delayed/censored outcomes and transitive invalidation lineage; no synthetic receipt may enter realized performance.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-048-P` — A rejected candidate remains in analysis with counterfactual status and missing actual fills.
- `VAN-ML-AT-048-N` — Only profitable executed candidates retained or paper outcomes relabelled real fails.
- `VAN-ML-AT-049-P` — Trace a revoked manual-data source to features, models, caches and public projections.
- `VAN-ML-AT-049-N` — Delete a row and claim model unlearning or keep revoked model active: fail.
- `T-HVA-024-POS` — Attach matured outcomes and publish unresolved counts with pessimistic/alternative sensitivity assumptions.
- `T-HVA-024-NEG` — Discard unavailable losing routes or count scam flags as guaranteed money saved; reject economic qualification.
- `T-HVA-024-REC` — Late outcomes produce auditable study revisions rather than changing sealed policy decisions.
- `T-HVA-025-POS` — Show the same cohort under two policies whose skipped trade changes later capital availability and compare complete net cash paths.
- `T-HVA-025-NEG` — Sum isolated profitable trades above account capital or reuse actual exits for a different entry/asset; reject.
- `T-HVA-025-REC` — Interrupted replay resumes from the exact arm checkpoint with stable hashes and no shared mutable state between arms.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-067 — BE-043: Finality, reorganization and descendant revalidation
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-037, BE-041, BE-042, VAN-ML-PKT-024, VAN-ML-PKT-027.
**Requirement owners:** VAN-HVA-009, VAN-HVA-019, VAN-HVA-030.

**Exit contract:** Complete all stated operations in the existing owners. Changed source/state → durable invalidation/revalidation ledger → caches, datasets, models and experiment consumers. Verify a real registered positive caller/readback, negative and recovery paths under exact source/provider scope. A stale descendant, half-complete invalidation after crash, silent finality upgrade or changed-history dataset must fail. No fixture substitutes for required real provider integration, and no research result grants financial authority.

**All deliverables:**
- Maintain transitive source→fact→feature→forecast→experiment dependency references and explicit finality policies.
- Process source correction, chain reorg, pool migration and contract changes as versioned invalidation events.
- Block stale descendant consumption, replay revalidation safely and preserve all prior evidence without hindsight edits.

**Planned test obligations (all NOT_RUN):**
- `T-HVA-009-POS` — Track one asset across two pools and a migration with separate quote, liquidity and first-seen histories.
- `T-HVA-009-NEG` — Sum duplicated liquidity across routed hops or reassign an old quote to a new pool; reject the economics.
- `T-HVA-009-REC` — Reorg or rollback of a migration invalidates affected route descendants and preserves original token identity.
- `T-HVA-019-POS` — Apply a controlled state replacement and enumerate every affected descendant; only revalidated descendants regain eligibility.
- `T-HVA-019-NEG` — A reorg invalidates raw data but cached ForecastPacket or experiment still consumes it as current; reject.
- `T-HVA-019-REC` — Crash during invalidation resumes idempotently and cannot leave a partially invalidated result marked ready.
- `T-HVA-030-POS` — Replay sealed outcomes exactly and test serving within its declared numeric tolerance, latency and applicability domain.
- `T-HVA-030-NEG` — Synchronously call a chain indexer/model registry from T0 or label an expired/reorganized result ready; refuse.
- `T-HVA-030-REC` — A checkpoint/environment change triggers compatibility and tolerance tests; crash recovery preserves result identity and baseline availability.
- `T-REV113-022` — Chain reorg invalidates dependent token and wallet observations and qualified rank outputs

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-068 — VAN-ML-PKT-028: Complete backend APIs and future-screen consumption
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-021, PRE-003, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-026, VAN-ML-PKT-027.
**Requirement owners:** VAN-ML-REQ-050, VAN-ML-REQ-051.

**Exit contract:** Real authenticated headless caller exercises every registered operation; Uncalibrated scores never exposed as win probabilities; hidden unsupported flags cannot omit required functions

**All deliverables:**
- Extend genuine gateway operations for forecasts, experiments, diagnostics, proposals, retraining and receipts
- Publish complete typed states/actions/eligibility/readback, cancellation and source-age contract
- Map all forecast features to existing Trading/Analyst/Strategy/Risk/Settings/Work surfaces without new frontend code

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-050-P` — Headless owner-scoped caller executes each operation and reads durable outcome.
- `VAN-ML-AT-050-N` — Only a unit function, fake API or missing cancel/readback cannot close backend capability.
- `VAN-ML-AT-051-P` — Projection identifies calibration population, sample, horizon, expiry and limitations.
- `VAN-ML-AT-051-N` — Uncalibrated certainty, neural explanation as causality or stale band as current fails.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-069 — VAN-ML-PKT-029: VM deployment, isolation, recovery and service operations
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-022, VAN-ML-PKT-023, VAN-ML-PKT-024, VAN-ML-PKT-028.
**Requirement owners:** VAN-ML-REQ-052, VAN-ML-REQ-053.

**Exit contract:** Kill/pressure/full-disk/mismatched build and lost-receipt drills with actual services; T0 deadline/protection noninterference and immutable ledger survival independently measured

**All deliverables:**
- Build approved VM service manifests with isolated users/quotas/secrets/network and capacity admission
- Exercise install, migration, backup/restore, rollback, model hot-swap and telemetry retention
- Use Global DIAL and Zuul routes; do not run on forbidden desktop or silently substitute local compute

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-052-P` — Actual staged services survive restart, backup/restore and compatible rollback.
- `VAN-ML-AT-052-N` — Forbidden desktop/local substitution, broker keys in trainer or stale-source receipt fails.
- `VAN-ML-AT-053-P` — Overload, disk full and unavailable registry produce recorded safe backpressure.
- `VAN-ML-AT-053-N` — Unbounded threads/logs/cache, exposed secrets or unmeasured T0 starvation fails.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-070 — VAN-ML-PKT-037: Prediction-market scope, VM profiles and source capability contracts
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-002, BE-014, PRE-003, VAN-ML-PKT-004, VAN-ML-PKT-005.
**Requirement owners:** VAN-HVA-010, VAN-ML-REQ-061, VAN-ML-REQ-062.

**Exit contract:** Positive adapter/replay calls and explicit source-unavailable readback through actual services; source access unresolved must not become a coding prerequisite.; No country-spoofing, proxy workaround, account creation, trade credential requirement or inferred live permission.

**All deliverables:**
- Implement reusable source/provider contracts with separate technical reachability, allowed data uses, observed terms reference and acquisition mode; no licence-purchase workflow or external spending.
- Provide Netcup and Oracle worker profiles, actual region/host metadata and Global DIAL placement; distinguish operator/account eligibility from machine location.
- Deliver a no-network fixture/replay path and real read-only adapter path using existing source permissions where established; unavailable access affects that source, never erases other engineering scope.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-061-P` — Build and select both VM deployment profiles with explicit source/capability states and no payment workflow.
- `VAN-ML-AT-061-N` — Changing execution_host to a permitted region must not set operator eligibility, purchase approval or source-use permission.
- `VAN-ML-AT-062-P` — Exercise full positive synthetic ingest-to-evidence flow with purchases disabled and explicit NOT_LIVE data labels.
- `VAN-ML-AT-062-N` — Do not require a purchased licence to run synthetic tests; do not relabel unknown source-use rights as an admitted real-data capture.
- `T-HVA-010-POS` — Exercise a permitted provider contract and separately show a disabled/unavailable provider with a precise missing-evidence state.
- `T-HVA-010-NEG` — Treat Netcup/Oracle placement or unauthenticated reachability as unrestricted rights or funded trading eligibility; reject that inference.
- `T-HVA-010-REC` — A permission expiry disables new affected acquisition and serving, preserves audit records according to applicable retention and leaves unrelated work runnable.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-071 — VAN-ML-PKT-038: Kalshi and comparison-provider ingestion, depth and history
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-003, BE-014, PRE-003, VAN-ML-PKT-037.
**Requirement owners:** VAN-ML-REQ-063, VAN-ML-REQ-064, VAN-ML-REQ-065, VAN-ML-REQ-066.

**Exit contract:** Contract-compatible positive integration plus pagination, archive handoff, reconnect, duplicate and precision counterexamples.; Any genuine provider capture has explicit permission/method and timing provenance; fixtures never count as historical/live captures.

**All deliverables:**
- Implement versioned REST pagination, public metadata/books/trades and historical-boundary reconciliation plus authenticated read-only stream support where available.
- Normalize exact fixed-point YES/NO bids; derive opposite asks, book depth and quote-quality metadata without float cash arithmetic.
- Persist idempotent events with provider time, received time, available_at, source revision and gap/late-message state; stream gaps force resnapshot before usability.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-063-P` — Read complete paged synthetic and authorized-provider datasets with method/endpoint and schema version receipts.
- `VAN-ML-AT-063-N` — Injected order endpoint, redirect to credential host, unbounded paging or HTTP429 hot retry must be refused.
- `VAN-ML-AT-064-P` — Union live/historical responses under overlap and moving boundaries with stable IDs and complete provenance.
- `VAN-ML-AT-064-N` — Dropped page or single shared archive cutoff cannot be silently accepted; reconstructed time cannot masquerade as actual availability.
- `VAN-ML-AT-065-P` — For YES bid0.42 and NO bid0.56 obtain YES ask0.44 and NO ask0.58 with correct quantities.
- `VAN-ML-AT-065-N` — Treating YES last trade as executable ask or performing currency calculations through rounded binary floats fails the contract.
- `VAN-ML-AT-066-P` — Replay snapshot/deltas, duplicate and restart; regain READY only after a consistent new snapshot.
- `VAN-ML-AT-066-N` — Out-of-order delta, missing sequence or stale cached depth must not continue providing usable liquidity.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-072 — VAN-ML-PKT-039: Event semantics, settlement and cross-venue equivalence
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-015, PRE-003, VAN-ML-PKT-037.
**Requirement owners:** VAN-ML-REQ-067, VAN-ML-REQ-068.

**Exit contract:** Same-title/different-rule, initial/revised-release, strict/inclusive threshold and settlement-delay cases produce distinct identities.; Positive exact/complement mapping is usable in research with reviewed evidence; unresolved mapping is explicit, not a permanent empty implementation.

**All deliverables:**
- Add versioned event-contract definitions: exact proposition, units, comparator, thresholds, time window, timezone, official source/vintage, rounding, resolution, cancellation and dispute rules.
- Implement contract relation graph and reviewed exact/complement/overlap/non-equivalent mappings; semantic proposals from models cannot certify equivalence.
- Keep event occurrence, official publication, trade close and settlement as distinct states/clocks; corrected or cancelled outcomes create new versions and invalidation edges.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-067-P` — Resolve two reviewed identical propositions and explicit complement relation into a shared event mapping.
- `VAN-ML-AT-067-N` — Same headline with different rounding, observation date or revised-value rules cannot be treated as identical.
- `VAN-ML-AT-068-P` — Process an official release, later correction and delayed settlement without rewriting issued forecasts or prematurely crediting cash.
- `VAN-ML-AT-068-N` — Event happened or market closed cannot be used as proof that a payout is final or funds are available.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-073 — VAN-ML-PKT-040: Coherent event distributions, quality and probability features
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-006, VAN-ML-PKT-038, VAN-ML-PKT-039.
**Requirement owners:** VAN-ML-REQ-069, VAN-ML-REQ-070, VAN-ML-REQ-071, VAN-ML-REQ-073.

**Exit contract:** Finite coherent full distributions, correctly differenced threshold masses, explicit unavailable/partial distributions and deterministic same-input outputs.; Low-depth/outdated/crossed or mismatched books cannot become confident features through averaging or silent normalization.

**All deliverables:**
- Implement binary, mutually exclusive outcome and threshold distribution builders; explicit raw versus adjusted estimates, monotonicity, missing bins and open-tail policies.
- Register probability levels/changes, entropy, tail mass, dispersion, consensus differences, spread/depth and freshness as distinct features; fit all transforms on permitted history.
- Prevent artificial jumps at contract roll; compare aligned maturity/proposition only; preserve Kalshi/Polymarket agreement as consistency, not independent-probability multiplication.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-069-P` — Forecast features remain stable when a next-meeting display rolls to a different underlying event.
- `VAN-ML-AT-069-N` — Subtracting different event contracts and reporting the difference as same-event repricing fails validation.
- `VAN-ML-AT-070-P` — Convert decreasing threshold probabilities into disjoint masses; retain raw and adjusted distributions and tail assumptions.
- `VAN-ML-AT-070-N` — Summing overlapping threshold probabilities, silently normalizing missing bins or inventing a tail midpoint is rejected.
- `VAN-ML-AT-071-P` — Produce mid/interval estimates only from valid two-sided books and admit eligible liquidity cohorts.
- `VAN-ML-AT-071-N` — Volume-only confidence, stale last trades, crossed books or empty levels cannot become high-confidence event probabilities.
- `VAN-ML-AT-073-P` — Two fresh comparable sources pass consistency; single-source research remains explicitly SINGLE_SOURCE and cannot arm the inherited dual-source path.
- `VAN-ML-AT-073-N` — Duplicate syndication, mismatched contract horizons or two models reading one feed cannot count as independent confirmations.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-074 — VAN-ML-PKT-041: Event calibration, grouped chronology and frozen surprise
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-008, VAN-ML-PKT-020, VAN-ML-PKT-040.
**Requirement owners:** VAN-ML-REQ-072, VAN-ML-REQ-074, VAN-ML-REQ-075.

**Exit contract:** Positive matured-label/calibration workflow and real producer binding through existing service.; Post-release input, correlated snapshots split randomly, unsupported probability claims and stale calibration fail qualification.

**All deliverables:**
- Extend existing calibration by event family, horizon and liquidity cohort; retain market-implied values separately from calibrated physical-event probabilities.
- Freeze admissible pre-release expectations and calculate surprise only once the correct official release becomes available; preserve every later revision separately.
- Group training/calibration/testing by underlying event and aligned cross-market folds; report event-effective sample size, proper scores and concentration, not inflated quote counts.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-072-P` — Issue immutable expectation snapshot then calculate a versioned surprise when official information arrives.
- `VAN-ML-AT-072-N` — Replacing the pre-release distribution with a post-release price or corrected value fails the lookahead sentinel.
- `VAN-ML-AT-074-P` — Evaluate raw and calibrated proper scores on later whole-event holdouts with recorded sample adequacy.
- `VAN-ML-AT-074-N` — Randomly splitting snapshots of the same event or pooling unrelated categories to conceal macro miscalibration fails admission.
- `VAN-ML-AT-075-P` — Expose raw and calibrated event probabilities with compatible calibrator lineage and explicit event definition.
- `VAN-ML-AT-075-N` — Copy event probability to trade win probability or label an uncalibrated market price CALIBRATED without evidence is refused.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-075 — VAN-ML-PKT-042: Conditional asset-response models and forecast-stack integration
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-041.
**Requirement owners:** VAN-ML-REQ-076, VAN-ML-REQ-077.

**Exit contract:** Actual fitted-model export/load/inference on adequate permitted research data with predictions joined to exact available event snapshots.; Event probability cannot be copied into asset-direction or trade-win probability; incapable NF configurations reject unsupported exogenous fields.

**All deliverables:**
- Join point-in-time event features into existing Qlib tabular tasks and model-supported NeuralForecast historical exogenous inputs; future probability trajectories are never known covariates.
- Implement conditional asset-response targets for returns, volatility, adverse excursion and trade quality by instrument/horizon/session, with simple market/calendar baselines.
- Use out-of-fold predictions in fusion, measure incremental information beyond price/news/consensus inputs and preserve shared-source dependencies across model families.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-076-P` — Fit/export/reload each selected provider on an adequate causal synthetic/allowed cohort and reproduce held-out predictions.
- `VAN-ML-AT-076-N` — Future event prices, unsupported exogenous flags or cross-fold scaler/calibrator fits fail before model publication.
- `VAN-ML-AT-077-P` — Demonstrate a conditional response bundle with matched labels/units and a complete with/without-event ablation report.
- `VAN-ML-AT-077-N` — Treat a rate-cut probability as gold-up probability or use in-sample learner predictions to qualify fusion is rejected.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-076 — VAN-ML-PKT-043: Calibrated event value and bounded position evidence
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-009, BE-016, PRE-003, VAN-ML-PKT-010, VAN-ML-PKT-025, VAN-ML-PKT-041, VAN-ML-PKT-042.
**Requirement owners:** VAN-ML-REQ-078, VAN-ML-REQ-079, VAN-ML-REQ-080.

**Exit contract:** Positive admitted sandbox evidence consumed by risk evaluation and negative stale/unknown/wrong-use cases, with exact source and independent receipt bindings.; No live event-contract adapter is registered; event-risk proposals cannot raise existing news multipliers or treat stop distance as maximum binary loss.

**All deliverables:**
- Implement external-asset evidence integration through inherited D1–D7 policies and preserve manual-position ownership, no stop widening, calendar blackouts and two-source armed expectations.
- Implement sandbox binary-contract value calculations for held-to-settlement and exit-before-settlement strategies with explicit depth/fees/currency/capital lockup; probabilities must be independently calibrated.
- Implement maximum-loss/event-family portfolio stress and constrained Kelly-style research comparisons; output only bounded proposals, never final authority, actual order instructions or self-promotion.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-078-P` — Exercise permitted reduce/defer/template/rank actions plus separately admitted sandbox D7 with correct source and owner bindings.
- `VAN-ML-AT-078-N` — Raise news multiplier above1, shorten blackout, widen stop, touch owner-managed position or bypass two-source arming: refuse.
- `VAN-ML-AT-079-P` — Reference fixtures reconcile depth-aware entry cost and final/early-exit value in exact currency units.
- `VAN-ML-AT-079-N` — Use midpoint instead of ask, omit fees, double-charge embedded spread or reuse purchase price as independent success probability: fail.
- `VAN-ML-AT-080-P` — Compare risk-constrained proposals against existing account/event limits and explicit worst-case payoff scenarios.
- `VAN-ML-AT-080-N` — Assume a protective stop caps binary loss, net incompatible contracts, infer joint independence or emit a live order quantity from the forecaster: refuse.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-077 — VAN-ML-PKT-044: Execution-realistic prediction-contract replay
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-009, VAN-ML-PKT-010, VAN-ML-PKT-038, VAN-ML-PKT-039.
**Requirement owners:** VAN-HVA-005, VAN-ML-REQ-081, VAN-ML-REQ-082.

**Exit contract:** Deterministic accounting identities and counterexamples for touch-not-fill, queue loss, partial fill/cancel races, settlement delay and fee fragmentation.; External-asset evaluation uses the actual destination broker model instead of charging hypothetical Kalshi trades.

**All deliverables:**
- Extend the existing replay adapter family with decimal cash, depth/partial-fill logic, order activation/cancel timing, queue uncertainty and trade/bid/ask distinction.
- Bind versioned per-series/per-account fee precision and accumulator semantics; include settlement/dispute/cancel outcomes, venue cash reservations, financing and conversion costs where applicable.
- Keep all positions on one coherent event/book path and reconcile final liquidation/settlement equity; sparse history returns evidence limitations rather than guaranteed maker fills.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-081-P` — Fragmented fill and single-fill fixtures reconcile cash, fees, inventory and final settlement under the configured policy.
- `VAN-ML-AT-081-N` — Applying one timeless fee constant, cancelling debit on unknown state or crediting unsettled cash fails accounting.
- `VAN-ML-AT-082-P` — Replay a partial fill followed by cancellation and delayed acknowledgement on one consistent book path.
- `VAN-ML-AT-082-N` — Touch-equals-fill, cancel-request-equals-cancelled, candles-prove-queue or zero-latency post-announcement entry cannot qualify.
- `T-HVA-005-POS` — Reconcile a quoted entry, modeled exit/failure costs and aggregate edge without double-counting spread, impact, gas or transfer charges.
- `T-HVA-005-NEG` — Pass an uncalibrated fill estimate as an observed quote or subtract a fee already included in proceeds; detect both errors.
- `T-HVA-005-REC` — Fee, model or quote-state changes invalidate affected assessments and reprice them with retained original versions.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-078 — VAN-ML-PKT-045: Contract-consistency and non-atomic arbitrage research laboratory
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-044.
**Requirement owners:** VAN-ML-REQ-083, VAN-ML-REQ-084.

**Exit contract:** Positive synthetic hedged-payoff case and near-match false-arbitrage/one-leg-failure cases with source-bound research reports.; No new arbitrage order sender; cashflows and margin do not assume default-free settlement or fabricate a USD-stablecoin equivalence.

**All deliverables:**
- Implement candidate discovery and exact payoff-state matrices for complementary and related contracts; title embeddings only shortlist candidates.
- Compute worst-case payout/net margin at executable quantities across success/void/cancel/dispute states; separate conditional payoff hedge from guaranteed real execution.
- Simulate venue-specific cash, collateral/currency haircut, settlement delay, partial first-leg fill, failed hedge and feasible unwind; do not assume cross-exchange atomicity or transferable immediate collateral.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-083-P` — Produce a positive synthetic complementary payout matrix and a separately named executable-margin estimate.
- `VAN-ML-AT-083-N` — Different source/vintage, omitted void state, unequal hedge quantity or negative state payout must defeat an arbitrage assertion.
- `VAN-ML-AT-084-P` — Simulate both-filled and first-leg-only outcomes with bounded loss and explicit cash reservation/readback.
- `VAN-ML-AT-084-N` — Unfilled hedge assumed complete, stablecoin treated as guaranteed USD or delayed settlement capital instantly reused fails.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-079 — VAN-ML-PKT-046: Inventory-aware event market-making research laboratory
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-026, VAN-ML-PKT-041, VAN-ML-PKT-044.
**Requirement owners:** VAN-ML-REQ-085, VAN-ML-REQ-086.

**Exit contract:** Positive simulated quoting/fill/inventory roundtrip and adverse-selection/cancel-race/queue-loss stress evidence.; Conditional value uses outcomes after actual modeled fills; unconditional spread capture or touched quotes do not qualify profitability.

**All deliverables:**
- Implement bounded inventory-aware two-sided quoting simulations with jump risk, time-to-event, event-family exposure, toxicity and fill-conditional expected value.
- Compare no-quote, fixed-spread and inventory-aware policies; measure queue dependence, inventory age, markout at several horizons, fee/rebate assumptions and cancel effectiveness.
- Implement research stop/quote-reduction on stale/gapped books and official-release risk; simulate pending cancels and retain exposure until confirmed. No spoofing/wash-trade logic or assumed special market-maker privileges.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-085-P` — Exercise fixed and inventory-skew policies on the same synthetic stream with exact inventory and fill-conditional markout.
- `VAN-ML-AT-085-N` — A profitable unconditional midpoint forecast or assumed privileged queue/rate treatment cannot prove maker profitability.
- `VAN-ML-AT-086-P` — Bad book/official-release state prevents new quotes; pending cancels remain reserved until confirmed and restart restores exposure.
- `VAN-ML-AT-086-N` — Spoofing/wash-trade policy, removed reservation before cancellation, unbounded quote loops or continued healthy status after a gap: refuse.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-080 — VAN-ML-PKT-047: Prediction-market incremental-value and prospective study programme
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-021, VAN-ML-PKT-027, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046.
**Requirement owners:** VAN-ML-REQ-087, VAN-ML-REQ-088.

**Exit contract:** Actual comparison/report pipelines with positive and deliberately no-edge fixtures; actual market claims require permitted untouched and prospective observations.; Fewer trades or reduced capital alone cannot be advertised as superior intelligence; insufficient independent events remains inconclusive.

**All deliverables:**
- Implement four frozen studies: pre-event risk, surprise interpretation, volatility and opportunity ranking, all paired against the same incumbent and exposure-matched/simple controls.
- Include dependency-aware uncertainty, trial census, event counts, publication/acquisition/execution lag tests, shuffled/lagged controls, full-account accounting and operating costs.
- Deliver prospective forecast sealing, outcome maturation and per-use decisions QUALIFIED/REJECTED/INCONCLUSIVE/UNAVAILABLE; useful context is not automatically trading edge.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-087-P` — Produce all four complete study contracts, reports and explicit no-edge/inconclusive paths with full-account outcomes.
- `VAN-ML-AT-087-N` — Claim improvement solely from fewer trades, dropped missed winners, favourable period selection or ignored source/compute cost: fail.
- `VAN-ML-AT-088-P` — Mature future outcomes against sealed forecasts and report effective events, uncertainty, concentration and cost-adjusted utility.
- `VAN-ML-AT-088-N` — Repeated quotes as independent trials, post-release resealing, future correction leakage or fixed-days-as-sufficient rule fails qualification.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-081 — BE-036: Continuous governed strategy-development service and outcome reporting
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-013, BE-022, BE-028, BE-035, PRE-003, VAN-ML-PKT-021, VAN-ML-PKT-022, VAN-ML-PKT-023, VAN-ML-PKT-025, VAN-ML-PKT-027, VAN-ML-PKT-047.
**Requirement owners:** VAN-CX-010, VAN-CX-011, VAN-CX-013, VAN-CX-014, VAN-NX-072.

**Exit contract:** OD-37 automatic offline review/candidate/evaluation under bounded research grants; complete experiment lineage; exact owner promotion and admitted demotion; qualified evaluator dependency; no qualified candidate is a truthful result.

**All deliverables:**
- Candidate proposals from both winners and losers, complete experiments; no autonomous live promotion

**Planned test obligations (all NOT_RUN):**
- `T-VAN-CX-010-POS` — Known-profit/loss fixtures match analytically specified results and the actual execution adapters' admitted semantics.
- `T-VAN-CX-010-NEG` — Disabling controls, altering quote units or a permissive fill model without a distinct experiment identity invalidates promotion evidence.
- `T-VAN-CX-010-REC` — An evaluator correction invalidates dependent candidate conclusions and schedules reproducible reevaluation; old results remain labeled historical.
- `T-VAN-CX-011-POS` — Replay of each named chronological fold yields the same pre-cutoff decisions and verified split provenance.
- `T-VAN-CX-011-NEG` — Future-only perturbation changes past decisions, a scaler sees the holdout, or window count is only the count of calendar years: fail.
- `T-VAN-CX-011-REC` — Tainted fold/candidate artifacts cannot be reused as independent promotion evidence; retain audit lineage.
- `T-VAN-CX-013-POS` — Each reported metric identifies the population, formula/version, trial set, uncertainty and selection scope.
- `T-VAN-CX-013-NEG` — A pooled PBO is relabeled pair-specific, losers disappear from trial count, or repeated holdout tuning is called independent: fail promotion.
- `T-VAN-CX-013-REC` — A no-qualified-candidate result is valid; do not search until a cherry-picked pass can be manufactured.
- `T-VAN-CX-014-POS` — A weekly run is idempotent by period/strategy/dataset/evaluator; results reproduce and a candidate reaches only permitted next states.
- `T-VAN-CX-014-NEG` — A model edits protected execution/risk paths, repeated runs duplicate studies, a failed candidate becomes a promotion opportunity, or an unsigned candidate trades live: refuse.
- `T-VAN-CX-014-REC` — Resume interrupted jobs from durable checkpoints; outdated evaluations are invalidated, not overwritten; current production champion remains unchanged.
- `T-BE-036-POS` — OD-37 automatic offline review/candidate/evaluation under bounded research grants; complete experiment lineage; exact owner promotion and admitted demotion; qualified evaluator dependency; no qualified candidate is a truthful result. POS evidence required.
- `T-BE-036-NEG` — OD-37 automatic offline review/candidate/evaluation under bounded research grants; complete experiment lineage; exact owner promotion and admitted demotion; qualified evaluator dependency; no qualified candidate is a truthful result. NEG evidence required.
- `T-BE-036-REC` — OD-37 automatic offline review/candidate/evaluation under bounded research grants; complete experiment lineage; exact owner promotion and admitted demotion; qualified evaluator dependency; no qualified candidate is a truthful result. REC evidence required.
- `T-BE-036-SEC` — OD-37 automatic offline review/candidate/evaluation under bounded research grants; complete experiment lineage; exact owner promotion and admitted demotion; qualified evaluator dependency; no qualified candidate is a truthful result. SEC evidence required.
- `T-BE-036-INT` — OD-37 automatic offline review/candidate/evaluation under bounded research grants; complete experiment lineage; exact owner promotion and admitted demotion; qualified evaluator dependency; no qualified candidate is a truthful result. INT evidence required.
- `T-REV113-020` — Weekly research run logs losing and winning evidence and every failed trial; no candidate can self-promote

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-082 — BE-044: Read-only crypto end-to-end research, operations and native consumption contract
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-038, BE-041, BE-042, BE-043, BE-021, BE-024, VAN-ML-PKT-025, VAN-ML-PKT-028, VAN-ML-PKT-029, VAN-ML-PKT-047.
**Requirement owners:** VAN-HVA-004, VAN-HVA-011, VAN-HVA-014, VAN-HVA-031, VAN-HVA-032.

**Exit contract:** Complete all stated operations in the existing owners. All domain/evaluation services → existing gateway/catalogue and model registry → research and later FE-023 contexts. Verify a real registered positive caller/readback, negative and recovery paths under exact source/provider scope. Fixture-as-live, duplicate financial authority, unsafe judgment, uncalibrated ranking, early UI or missing real caller prevents closure. No fixture substitutes for required real provider integration, and no research result grants financial authority.

**All deliverables:**
- Integrate all new domain producers into existing LightGBM/NeuralForecast/Optuna/MLflow and matched-opportunity research owners; preserve separate generic and domain validations.
- Extend registered shared Jev question sets and exact evidence resolution; no new Jev deployment or authority.
- Publish authenticated headless funnel/cost/wallet/quote/experiment/status readbacks, quotas, retention, recovery and disabled-provider behavior.
- Exercise valid success, negative, interruption, revoke and rollback paths on the DIAL topology with source-bound real integration receipts where required.
- All read-only chain research matched to qualified backend and eventual frontend consumer; no signing or trading route

**Planned test obligations (all NOT_RUN):**
- `T-HVA-004-POS` — Run a complete read-only discovery-to-evidence path and a concurrent existing risk-reducing exit without any additive financial operation.
- `T-HVA-004-NEG` — Inject a sign/sendTransaction, fund-wallet or broker-order request into a provider record or judgment; refuse and preserve the existing financial path.
- `T-HVA-004-REC` — Restart or revoke the research service while an existing position is being protected; protection and reconciliation remain available.
- `T-HVA-011-POS` — Capture and replay successful documented discovery/read calls with exact cursor, hash, latency and source availability.
- `T-HVA-011-NEG` — Inject redirects to a private endpoint, oversized payload, malicious instructions, quota flood or an order-bearing method; refuse without expanding scope.
- `T-HVA-011-REC` — Resume from a durable cursor after outage and deduplicate retried source records without losing the observed cohort.
- `T-HVA-014-POS` — Recheck a changed security/route state immediately while leaving unchanged rejected candidates within their valid cooldown.
- `T-HVA-014-NEG` — Keep a previous rejection forever after a changed authority, or requeue without bounds on each duplicate event; detect.
- `T-HVA-014-REC` — Restart reconstructs queues and rejection expiry without duplicate jobs or lost source leases.
- `T-HVA-031-POS` — Read every stage through registered authenticated APIs and reconcile dashboard counts to underlying durable events.
- `T-HVA-031-NEG` — A fixture-only feed appears LIVE, unresolved model appears profitable or read-only view enables a new order button; reject.
- `T-HVA-031-REC` — Outage/restart/revocation shows stale/unknown evidence and preserves complete read-only histories according to retention policy.
- `T-HVA-032-POS` — Trace every additive obligation through producer, store, consumer, packet, tests, evidence and eventual owner surface; verify all required backends precede the sole BG.
- `T-HVA-032-NEG` — Open M8 UI after one feed, drop an inherited requirement, silently reuse changed packet numbers or self-issue a gate; reject.
- `T-HVA-032-REC` — Scope changes regenerate signed-input candidates and invalidate affected downstream certificates while preserving all original artefacts and revision-qualified aliases.
- `T-REV113-023` — Read-only chain research cannot produce an order, secret request, wallet signing or fictitious safety label

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-083 — VAN-ML-PKT-048: Prediction-market consumers, operations and complete backend integration
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-028, VAN-ML-PKT-029, VAN-ML-PKT-037, VAN-ML-PKT-038, VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-041, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046, VAN-ML-PKT-047.
**Requirement owners:** VAN-CX-018, VAN-HVA-001, VAN-ML-REQ-089, VAN-ML-REQ-090.

**Exit contract:** Headless real-service positive/recovery/error readbacks; all new requirements join independent packet032 closure and parent033/BG-001.; No background order enablement, licence purchase, new account, cloud bill, fixture-to-live promotion or false full-provider-ready claim.

**All deliverables:**
- Wire all data, probability, comparison, research-lab and evidence states into existing APIs, capability catalogue, alerts, logs and later-screen contracts; no early frontend.
- Exercise Netcup/Oracle host profiles, endpoint changes, stream gaps, source revocation, disk/backlog pressure, restart, duplicate/unknown publication and schema rollback with no T0/provider network coupling.
- Provide honest per-source integration state and no-procurement development path; all mandatory backend/parent obligations remain visible and source-specific real-data gates cannot be replaced by fixtures.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-089-P` — Headless actual gateway and worker readback handles ready, absent, stale, disputed, rejected, inconclusive and unknown without fake controls.
- `VAN-ML-AT-089-N` — Dense new Home dashboard, backend-only schema with no real caller, or active trade control on research-only evidence cannot pass closure.
- `VAN-ML-AT-090-P` — Kill/restart adapter, lose registry/source, fill disk, change schema and revoke inputs; valid unrelated strategies/protection continue within their policy.
- `VAN-ML-AT-090-N` — Fixture success relabelled provider-ready, additive-only gate unlocking frontend, source failure disabling exits or unexpected external payment: fail.
- `T-VAN-CX-018-POS` — Every one of the 90 forecast requirements maps to an active unit and test; all required child backend receipts reach BG-001.
- `T-VAN-CX-018-NEG` — A child F15/BG independently opens UI, Qlib or Freqtrade sends a live order, or a unavailable provider is labeled healthy: reject.
- `T-VAN-CX-018-REC` — Data/model failure yields explicit abstention or unavailable state; no economically qualified model is a permissible result, not permission to omit software.
- `T-HVA-001-POS` — Exercise each required train/export/load/predict or event-laboratory operation through its real registered consumer; record a truthful rejected or inconclusive economic result when appropriate.
- `T-HVA-001-NEG` — Remove DeepAR, a required challenger plugin or an event-research laboratory and attempt complete-backend admission; missing capability must be detected.
- `T-HVA-001-REC` — Restore a previous model package without dropping any mandatory API or laboratory; stale economic permission remains inactive.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-084 — BE-032: Whole-product capability, action and UI-consumption catalog
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-004, BE-007, BE-012, BE-013, BE-017, BE-018, BE-019, BE-020, BE-021, BE-022, BE-023, BE-024, BE-025, BE-026, BE-027, BE-028, BE-029, BE-030, BE-031, BE-034, BE-036, BE-044, PRE-003, VAN-ML-PKT-028, VAN-ML-PKT-048.
**Requirement owners:** VAN-CX-006, VAN-CX-017, VAN-CX-018, VAN-HVA-031, VAN-HVA-032, VAN-NX-003, VAN-NX-005, VAN-NX-008, VAN-NX-063, VAN-NX-BF-006.

**Exit contract:** publish complete versioned capability inventory; bind every action to input/state/error/authority/readback; expose display projections and navigable subjects. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. No required feature missing or hidden by unsupported label; every read/write contract has a genuine caller harness and known error set; catalog cannot send arbitrary frontend code

**All deliverables:**
- Include every new read-only domain capability and actual unavailable/provider/runtime states in the existing capability catalogue.
- Publish *full* consumer catalogue of 234 contexts with per-action authority/receipt/stale/unknown states before BG; no fixture-only readiness

**Planned test obligations (all NOT_RUN):**
- `T-BE-032-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-032-NEG` — No required feature missing or hidden by unsupported label; every read/write contract has a genuine caller harness and known error set; catalog cannot send arbitrary frontend code
- `T-BE-032-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-032-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-032-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-BF-006` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `T-VAN-CX-006-POS` — EXPIRED, CANCELLED and REJECTED unfilled orders disappear from working-order totals but remain in historical records; partial positions retain actual exposure.
- `T-VAN-CX-006-NEG` — A stale ACCEPTED receipt after terminal readback must not resurrect Working; duplicate fill/cancel events must not double-count.
- `T-VAN-CX-006-REC` — Snapshot replay produces the same positions, orders, reservations and summaries after restart.
- `T-VAN-CX-017-POS` — Every mapped owner action and new capability has one traceable caller and appropriate screen/sheet/dialog outcome.
- `T-VAN-CX-017-NEG` — A visually complete screen lacks its source or any backend is unfinished; BG-001 and frontend entry refuse.
- `T-VAN-CX-017-REC` — A newly discovered missing backend capability reopens its backend unit and invalidates affected BG/UX proof before front-end compensation.
- `T-VAN-CX-018-POS` — Every one of the 90 forecast requirements maps to an active unit and test; all required child backend receipts reach BG-001.
- `T-VAN-CX-018-NEG` — A child F15/BG independently opens UI, Qlib or Freqtrade sends a live order, or a unavailable provider is labeled healthy: reject.
- `T-VAN-CX-018-REC` — Data/model failure yields explicit abstention or unavailable state; no economically qualified model is a permissible result, not permission to omit software.
- `T-HVA-031-POS` — Read every stage through registered authenticated APIs and reconcile dashboard counts to underlying durable events.
- `T-HVA-031-NEG` — A fixture-only feed appears LIVE, unresolved model appears profitable or read-only view enables a new order button; reject.
- `T-HVA-031-REC` — Outage/restart/revocation shows stale/unknown evidence and preserves complete read-only histories according to retention policy.
- `T-HVA-032-POS` — Trace every additive obligation through producer, store, consumer, packet, tests, evidence and eventual owner surface; verify all required backends precede the sole BG.
- `T-HVA-032-NEG` — Open M8 UI after one feed, drop an inherited requirement, silently reuse changed packet numbers or self-issue a gate; reject.
- `T-HVA-032-REC` — Scope changes regenerate signed-input candidates and invalidate affected downstream certificates while preserving all original artefacts and revision-qualified aliases.
- `T-REV113-024` — 234 surface read models sourced from complete admitted backend; status UNKNOWN when producer missing

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-085 — BE-033: Backend deployment, recovery, capacity and observability
**Kind/stage:** BACKEND / 1. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-032, PRE-003.
**Requirement owners:** VAN-CX-008, VAN-HVA-031, VAN-NX-021, VAN-NX-022, VAN-NX-060, VAN-NX-073.

**Exit contract:** build reproducible service artifacts; configure staging; restore backups; migrate schema; prove rollback; quotas; bounded queues; alert health. Complete real service integration, failure/recovery, migration, source-bound positive/negative and provider tests. No production credentials in preparation; restart does not replay effects; resource pressure backpressure not data loss; rollback retains newer financial ledger safely

**All deliverables:**
- Service lifecycle, deploy rollback, maintenance readback, queue and memory pressure, fail-closed source health

**Planned test obligations (all NOT_RUN):**
- `T-BE-033-POS` — Exercise every declared operation through actual service registration and independently read its result.
- `T-BE-033-NEG` — No production credentials in preparation; restart does not replay effects; resource pressure backpressure not data loss; rollback retains newer financial ledger safely
- `T-BE-033-REC` — Crash/restart and lost-response recovery retains durable intent and does not duplicate effects.
- `T-BE-033-SEC` — Wrong owner/account/device/grant and expired/revoked context refuse; logs and projections redact secrets.
- `T-BE-033-INT` — Producer-to-consumer contract works against complete dependent services and admitted provider sandbox; no stub at certification.
- `T-VAN-CX-008-POS` — New-row work scales with appended records while honest replay matches full verification in SQLite and Postgres.
- `T-VAN-CX-008-NEG` — Tamper, truncate, fork, roll back, replace a ledger or supply a stale checkpoint: fail closed and force full verification. The research always-True monkeypatch is forbidden.
- `T-VAN-CX-008-REC` — Checkpoints are rebuilt or verified after restart; concurrency and interrupted checkpoint writes cannot leave risk operating on untrusted state.
- `T-HVA-031-POS` — Read every stage through registered authenticated APIs and reconcile dashboard counts to underlying durable events.
- `T-HVA-031-NEG` — A fixture-only feed appears LIVE, unresolved model appears profitable or read-only view enables a new order button; reject.
- `T-HVA-031-REC` — Outage/restart/revocation shows stale/unknown evidence and preserves complete read-only histories according to retention policy.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-086 — BQ-001: Trade/account/market/risk/execution headless end-to-end
**Kind/stage:** BACKEND_VERIFICATION / 2. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-002, BE-003, BE-004, BE-005, BE-006, BE-007, BE-008, BE-009, BE-010, BE-011, BE-012, BE-013, BE-014, BE-015, BE-016, BE-017, BE-018, BE-019, BE-020, BE-021, BE-022, BE-023, BE-024, BE-025, BE-026, BE-027, BE-028, BE-029, BE-030, BE-031, BE-032, BE-033, BE-034, BE-035, BE-036, BE-044, VAN-ML-PKT-004, VAN-ML-PKT-005, VAN-ML-PKT-006, VAN-ML-PKT-007, VAN-ML-PKT-008, VAN-ML-PKT-009, VAN-ML-PKT-010, VAN-ML-PKT-011, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-015, VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-019, VAN-ML-PKT-020, VAN-ML-PKT-021, VAN-ML-PKT-022, VAN-ML-PKT-023, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-026, VAN-ML-PKT-027, VAN-ML-PKT-028, VAN-ML-PKT-029, VAN-ML-PKT-037, VAN-ML-PKT-038, VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-041, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046, VAN-ML-PKT-047, VAN-ML-PKT-048.
**Requirement owners:** integration/qualification evidence for every dependent required capability.

**Exit contract:** No required backend feature partial; verified provider or service outcomes, ledger state and fault-injection receipts; exact source/artifact/config identity. Headless harness is not new UI. No synthetic success.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-087 — BQ-002: Provider accounts/funds/settlement and concurrent risk qualification
**Kind/stage:** BACKEND_VERIFICATION / 2. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-002, BE-003, BE-004, BE-005, BE-006, BE-007, BE-008, BE-009, BE-010, BE-011, BE-012, BE-013, BE-014, BE-015, BE-016, BE-017, BE-018, BE-019, BE-020, BE-021, BE-022, BE-023, BE-024, BE-025, BE-026, BE-027, BE-028, BE-029, BE-030, BE-031, BE-032, BE-033, BE-034, BE-035, BE-036, BE-044, VAN-ML-PKT-004, VAN-ML-PKT-005, VAN-ML-PKT-006, VAN-ML-PKT-007, VAN-ML-PKT-008, VAN-ML-PKT-009, VAN-ML-PKT-010, VAN-ML-PKT-011, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-015, VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-019, VAN-ML-PKT-020, VAN-ML-PKT-021, VAN-ML-PKT-022, VAN-ML-PKT-023, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-026, VAN-ML-PKT-027, VAN-ML-PKT-028, VAN-ML-PKT-029, VAN-ML-PKT-037, VAN-ML-PKT-038, VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-041, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046, VAN-ML-PKT-047, VAN-ML-PKT-048.
**Requirement owners:** VAN-NX-BF-017.

**Exit contract:** No required backend feature partial; verified provider or service outcomes, ledger state and fault-injection receipts; exact source/artifact/config identity. Headless harness is not new UI. No synthetic success.

**Planned test obligations (all NOT_RUN):**
- `T-BF-017` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-088 — BQ-003: News/history/armed grants/chart-observation headless intelligence
**Kind/stage:** BACKEND_VERIFICATION / 2. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-002, BE-003, BE-004, BE-005, BE-006, BE-007, BE-008, BE-009, BE-010, BE-011, BE-012, BE-013, BE-014, BE-015, BE-016, BE-017, BE-018, BE-019, BE-020, BE-021, BE-022, BE-023, BE-024, BE-025, BE-026, BE-027, BE-028, BE-029, BE-030, BE-031, BE-032, BE-033, BE-034, BE-035, BE-036, BE-044, VAN-ML-PKT-004, VAN-ML-PKT-005, VAN-ML-PKT-006, VAN-ML-PKT-007, VAN-ML-PKT-008, VAN-ML-PKT-009, VAN-ML-PKT-010, VAN-ML-PKT-011, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-015, VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-019, VAN-ML-PKT-020, VAN-ML-PKT-021, VAN-ML-PKT-022, VAN-ML-PKT-023, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-026, VAN-ML-PKT-027, VAN-ML-PKT-028, VAN-ML-PKT-029, VAN-ML-PKT-037, VAN-ML-PKT-038, VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-041, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046, VAN-ML-PKT-047, VAN-ML-PKT-048.
**Requirement owners:** integration/qualification evidence for every dependent required capability.

**Exit contract:** No required backend feature partial; verified provider or service outcomes, ledger state and fault-injection receipts; exact source/artifact/config identity. Headless harness is not new UI. No synthetic success.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-089 — BQ-004: Work/agents/Muse/browser/voice/memory/automation service integration
**Kind/stage:** BACKEND_VERIFICATION / 2. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-002, BE-003, BE-004, BE-005, BE-006, BE-007, BE-008, BE-009, BE-010, BE-011, BE-012, BE-013, BE-014, BE-015, BE-016, BE-017, BE-018, BE-019, BE-020, BE-021, BE-022, BE-023, BE-024, BE-025, BE-026, BE-027, BE-028, BE-029, BE-030, BE-031, BE-032, BE-033, BE-034, BE-035, BE-036, BE-044, VAN-ML-PKT-004, VAN-ML-PKT-005, VAN-ML-PKT-006, VAN-ML-PKT-007, VAN-ML-PKT-008, VAN-ML-PKT-009, VAN-ML-PKT-010, VAN-ML-PKT-011, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-015, VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-019, VAN-ML-PKT-020, VAN-ML-PKT-021, VAN-ML-PKT-022, VAN-ML-PKT-023, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-026, VAN-ML-PKT-027, VAN-ML-PKT-028, VAN-ML-PKT-029, VAN-ML-PKT-037, VAN-ML-PKT-038, VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-041, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046, VAN-ML-PKT-047, VAN-ML-PKT-048.
**Requirement owners:** integration/qualification evidence for every dependent required capability.

**Exit contract:** No required backend feature partial; verified provider or service outcomes, ledger state and fault-injection receipts; exact source/artifact/config identity. Headless harness is not new UI. No synthetic success.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-090 — BQ-005: Backend privacy, recovery, capacity, restart and source fault injection
**Kind/stage:** BACKEND_VERIFICATION / 2. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-002, BE-003, BE-004, BE-005, BE-006, BE-007, BE-008, BE-009, BE-010, BE-011, BE-012, BE-013, BE-014, BE-015, BE-016, BE-017, BE-018, BE-019, BE-020, BE-021, BE-022, BE-023, BE-024, BE-025, BE-026, BE-027, BE-028, BE-029, BE-030, BE-031, BE-032, BE-033, BE-034, BE-035, BE-036, BE-044, VAN-ML-PKT-004, VAN-ML-PKT-005, VAN-ML-PKT-006, VAN-ML-PKT-007, VAN-ML-PKT-008, VAN-ML-PKT-009, VAN-ML-PKT-010, VAN-ML-PKT-011, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-015, VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-019, VAN-ML-PKT-020, VAN-ML-PKT-021, VAN-ML-PKT-022, VAN-ML-PKT-023, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-026, VAN-ML-PKT-027, VAN-ML-PKT-028, VAN-ML-PKT-029, VAN-ML-PKT-037, VAN-ML-PKT-038, VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-041, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046, VAN-ML-PKT-047, VAN-ML-PKT-048.
**Requirement owners:** VAN-NX-021, VAN-NX-022, VAN-NX-060.

**Exit contract:** No required backend feature partial; verified provider or service outcomes, ledger state and fault-injection receipts; exact source/artifact/config identity. Headless harness is not new UI. No synthetic success.

**Planned test obligations (all NOT_RUN):**
- `T-NX-021` — Negative/pathological tests
- `T-NX-022` — Physical jank/battery/TalkBack tests
- `T-NX-060` — §15.1; device cases on the S24

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-091 — BQ-008: Independent chain-provider, security and finality qualification
**Kind/stage:** BACKEND_VERIFICATION / 2. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-037, BE-038, BE-039, BE-040, BE-041, BE-042, BE-043, BE-044.
**Requirement owners:** VAN-HVA-008, VAN-HVA-009, VAN-HVA-010, VAN-HVA-011, VAN-HVA-012, VAN-HVA-013, VAN-HVA-014, VAN-HVA-015, VAN-HVA-016, VAN-HVA-017, VAN-HVA-019, VAN-HVA-020, VAN-HVA-021, VAN-HVA-022, VAN-HVA-023, VAN-HVA-031, VAN-HVA-032.

**Exit contract:** Independent source-bound review of all listed obligations and actual positive/adversarial/recovery receipts. No author self-certification, document-only substitution, waived provider capability, automatic economic promotion or new financial permission.

**All deliverables:**
- Verify documented permitted read-only provider calls and source state, all chain analyzers and versioned histories.
- Prove end-to-end identity, complete cohort, security/sellability and invalidation behavior with no signing/custody path.
- Reproduce meaningful failure, restart, quota, source-revocation and reorg cases on actual qualified DIAL topology; absent mandatory external integration remains blocked.

**Planned test obligations (all NOT_RUN):**
- `T-HVA-008-POS` — Round-trip multiple address representations through the correct chain adapter and retain two different contracts with one display ticker.
- `T-HVA-008-NEG` — Lowercase a case-sensitive address, confuse network identifiers, or treat a malformed address as valid; reject or quarantine.
- `T-HVA-008-REC` — A codec version change triggers a reviewed migration preserving old aliases and links without merging distinct assets.
- `T-HVA-009-POS` — Track one asset across two pools and a migration with separate quote, liquidity and first-seen histories.
- `T-HVA-009-NEG` — Sum duplicated liquidity across routed hops or reassign an old quote to a new pool; reject the economics.
- `T-HVA-009-REC` — Reorg or rollback of a migration invalidates affected route descendants and preserves original token identity.
- `T-HVA-010-POS` — Exercise a permitted provider contract and separately show a disabled/unavailable provider with a precise missing-evidence state.
- `T-HVA-010-NEG` — Treat Netcup/Oracle placement or unauthenticated reachability as unrestricted rights or funded trading eligibility; reject that inference.
- `T-HVA-010-REC` — A permission expiry disables new affected acquisition and serving, preserves audit records according to applicable retention and leaves unrelated work runnable.
- `T-HVA-011-POS` — Capture and replay successful documented discovery/read calls with exact cursor, hash, latency and source availability.
- `T-HVA-011-NEG` — Inject redirects to a private endpoint, oversized payload, malicious instructions, quota flood or an order-bearing method; refuse without expanding scope.
- `T-HVA-011-REC` — Resume from a durable cursor after outage and deduplicate retried source records without losing the observed cohort.
- `T-HVA-012-POS` — Reconcile source discovery count with terminal and pending cohort states, including candidates never sent to a model.
- `T-HVA-012-NEG` — Build training/test data only from survivors or delete a disappearing pool as missing data; fail cohort completeness.
- `T-HVA-012-REC` — Rebuild the cohort projection from immutable discovery and decision events after a crash without hindsight re-ranking.
- `T-HVA-013-POS` — One eligible survivor receives all remaining checks and can still end NO_TRADE; typed yes/no/unknown inputs give stable outcomes.
- `T-HVA-013-NEG` — Use string no as true, skip remaining checks for one survivor, or replace missing data with zero; reject.
- `T-HVA-013-REC` — A rule-version update rechecks affected candidates from retained facts and does not overwrite prior decisions.
- `T-HVA-014-POS` — Recheck a changed security/route state immediately while leaving unchanged rejected candidates within their valid cooldown.
- `T-HVA-014-NEG` — Keep a previous rejection forever after a changed authority, or requeue without bounds on each duplicate event; detect.
- `T-HVA-014-REC` — Restart reconstructs queues and rejection expiry without duplicate jobs or lost source leases.
- `T-HVA-015-POS` — Evaluate versioned fixtures with revoked/active/unknown authorities, technical accounts and relevant extension combinations.
- `T-HVA-015-NEG` — Treat an unparsed extension as harmless or a missing authority as proven revoked; refuse a clear verdict.
- `T-HVA-015-REC` — After changed program/authority or source lag, invalidate affected security descendants and issue a fresh state-bound result.
- `T-HVA-016-POS` — Evaluate actual code/state fixtures for proxy upgrades, owner controls and transfer constraints with precise factual reasons.
- `T-HVA-016-NEG` — Trust a verified proxy shell while ignoring its changed implementation or state-dependent sell restriction; detect.
- `T-HVA-016-REC` — Implementation/code/state change invalidates dependent findings and simulations while retaining pre-change evidence.
- `T-HVA-017-POS` — Produce separate state-bound buy/sell outcomes, executable quantities and explicit failure reasons for a reversible route.
- `T-HVA-017-NEG` — Buy succeeds but sell reverts, transfers are taxed unexpectedly or simulation state is stale; no viable sellability assertion.
- `T-HVA-017-REC` — Changed router/contract/pool state invalidates the result and all affected economic descendants before any reuse.
- `T-HVA-019-POS` — Apply a controlled state replacement and enumerate every affected descendant; only revalidated descendants regain eligibility.
- `T-HVA-019-NEG` — A reorg invalidates raw data but cached ForecastPacket or experiment still consumes it as current; reject.
- `T-HVA-019-REC` — Crash during invalidation resumes idempotently and cannot leave a partially invalidated result marked ready.
- `T-HVA-020-POS` — Compute changes across anchored snapshots while retaining the raw source series and coverage interval.
- `T-HVA-020-NEG` — Infer accumulation or holder growth from one snapshot or compare unequal source scopes without disclosure; abstain.
- `T-HVA-020-REC` — A late/backfilled observation changes a new analytical version only; it does not appear in an earlier decision-time dataset.
- `T-HVA-021-POS` — Explain raw and adjusted concentration with every role exclusion and uncertainty interval traceable to source evidence.
- `T-HVA-021-NEG` — Flag an AMM vault as an insider solely because it holds over a threshold or silently erase uncertain accounts; fail.
- `T-HVA-021-REC` — Role reassignment triggers a versioned feature recomputation and reevaluation of affected decisions, not historical fact mutation.
- `T-HVA-022-POS` — Reconstruct a routed transfer and an actual buy without double-counting intermediate hops, retaining clustering assumptions.
- `T-HVA-022-NEG` — Classify every transfer as a purchase or common funding as conclusive common ownership; reject the assertion.
- `T-HVA-022-REC` — Replay updated decoders and labels under a new transform version, preserving the original episode references.
- `T-HVA-023-POS` — Evaluate a newly discovered asset using only available history and return unknown for an unsupported growth/rate claim.
- `T-HVA-023-NEG` — Divide by a fabricated previous volume or label an unobserved route exit as zero loss; fail.
- `T-HVA-023-REC` — As history matures, create a new eligible feature/label version without retroactively improving prior predictions.
- `T-HVA-031-POS` — Read every stage through registered authenticated APIs and reconcile dashboard counts to underlying durable events.
- `T-HVA-031-NEG` — A fixture-only feed appears LIVE, unresolved model appears profitable or read-only view enables a new order button; reject.
- `T-HVA-031-REC` — Outage/restart/revocation shows stale/unknown evidence and preserves complete read-only histories according to retention policy.
- `T-HVA-032-POS` — Trace every additive obligation through producer, store, consumer, packet, tests, evidence and eventual owner surface; verify all required backends precede the sole BG.
- `T-HVA-032-NEG` — Open M8 UI after one feed, drop an inherited requirement, silently reuse changed packet numbers or self-issue a gate; reject.
- `T-HVA-032-REC` — Scope changes regenerate signed-input candidates and invalidate affected downstream certificates while preserving all original artefacts and revision-qualified aliases.
- `T-REV113-026` — Chain provider unavailable/revoked stale proof blocks BG without blocking isolated unrelated research

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-092 — VAN-ML-PKT-030: Reproducible forecast and economic qualification reports
**Kind/stage:** BACKEND_VERIFICATION / 2. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-044, PRE-003, VAN-ML-PKT-009, VAN-ML-PKT-010, VAN-ML-PKT-020, VAN-ML-PKT-021, VAN-ML-PKT-025, VAN-ML-PKT-026, VAN-ML-PKT-027, VAN-ML-PKT-047, VAN-ML-PKT-048.
**Requirement owners:** VAN-HVA-026, VAN-ML-REQ-054.

**Exit contract:** Positive, negative and no-edge reporting pathways all exercised; No raw accuracy, favorable chart, in-sample fit or historic literature metric certifies VAN alpha

**All deliverables:**
- Execute matched baseline/ablation/cost-stress/rank/return/volatility/calibration studies
- Build source-bound certificates from actual outputs, effective sample sizes and uncertainty; report rejected/inconclusive cases honestly
- Independently reproduce selected results and attach immutable artifact/dataset/config evidence
- Require domain-cohort studies and dependence-aware materiality/sample/multiple-testing analysis; no unversioned competing 95-percent policy gate.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-054-P` — Recompute metrics from immutable prediction/outcome files independently.
- `VAN-ML-AT-054-N` — Literature returns, arbitrary accuracy threshold or in-sample results used as VAN proof fail.
- `T-HVA-026-POS` — Evaluate clustered paired outcomes under a locked hypothesis and compare against exposure-matched/simple baselines with all trial costs.
- `T-HVA-026-NEG` — Resample every snapshot as independent, peek repeatedly until significance or introduce a second conflicting threshold service; reject.
- `T-HVA-026-REC` — A policy amendment invalidates affected qualification claims while retaining all prior studies, including losing trials.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-093 — VAN-ML-PKT-031: Prospective shadow and controlled sandbox admission
**Kind/stage:** BACKEND_VERIFICATION / 2. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-028, VAN-ML-PKT-029, VAN-ML-PKT-030.
**Requirement owners:** VAN-ML-REQ-055.

**Exit contract:** Same gateway/service path supplies genuine scoped receipts before BG; A fixture-approved model cannot enter a live binding; real-paper evidence is not booked as live profit

**All deliverables:**
- Exercise real incoming-data shadow recording and full sandbox train-to-inference-to-arbiter-to-paper lifecycle
- Test trusted sandbox admission, revocation, fallback and rollbacks without live financial authority
- Implement continuing prospective economic review windows and no-edge terminal decisions
- Include prediction-market per-source integration and frozen prospective expectations; source-unavailable cannot be reported as an actual Kalshi data qualification.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-055-P` — Fit, serve, evaluate, sandbox-admit, revoke and reject through genuine services.
- `VAN-ML-AT-055-N` — Only refusal stubs or a synthetic approval promoted to live cannot pass.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-094 — BQ-007: Independent Opus remediation, evaluator and signed-risk regression qualification
**Kind/stage:** BACKEND_VERIFICATION / 2. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-035, BE-036, VAN-ML-PKT-030, VAN-ML-PKT-031.
**Requirement owners:** VAN-CX-019, VAN-NX-072, VAN-NX-073, VAN-NX-074, VAN-NX-075, VAN-NX-076, VAN-NX-077.

**Exit contract:** Prove each source defect fails on its original counterexample and passes only on admitted correction; compare retained source suites and independent oracles; all runtime-policy activation fields bind the approved mandate; skip differences explained.

**Planned test obligations (all NOT_RUN):**
- `T-VAN-CX-019-POS` — The complete pack rebuilds identically and invalid evidence cannot change readiness.
- `T-VAN-CX-019-NEG` — Edit input and matching local hash, delete a receipt, swap source revision, self-declare signature_valid, or reuse device evidence across builds: block readiness.
- `T-VAN-CX-019-REC` — Record revoked/stale evidence; regenerate affected planning fingerprints and rerun relevant tests without erasing old records.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-095 — BQ-009: Independent economics, cohort, evidence and advisory-authority qualification
**Kind/stage:** BACKEND_VERIFICATION / 2. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-044, BE-035, BE-036, VAN-ML-PKT-030, VAN-ML-PKT-031.
**Requirement owners:** VAN-HVA-003, VAN-HVA-004, VAN-HVA-005, VAN-HVA-006, VAN-HVA-007, VAN-HVA-012, VAN-HVA-018, VAN-HVA-019, VAN-HVA-024, VAN-HVA-025, VAN-HVA-026, VAN-HVA-027, VAN-HVA-028, VAN-HVA-029, VAN-HVA-030, VAN-HVA-031, VAN-HVA-032.

**Exit contract:** Independent source-bound review of all listed obligations and actual positive/adversarial/recovery receipts. No author self-certification, document-only substitution, waived provider capability, automatic economic promotion or new financial permission.

**All deliverables:**
- Independently verify fact/forecast/edge separation, nonlinear account replay, target calibration and statistical policy.
- Reconcile all discovery outcomes and false-positive costs; prove no simulated result is promoted to a realized venue fact.
- Exercise existing Jev/evidence/allocator contracts, decline cases and mandatory exits; no new order authority or early frontend.
- Challenge selection bias, zero-cost simulator assumptions, calibration, early promotions and false confidence

**Planned test obligations (all NOT_RUN):**
- `T-HVA-003-POS` — Load known legacy categories with their original schema and retain separate source-quality and implementation states without promotion.
- `T-HVA-003-NEG` — Submit a vendor capability or creator screenshot as E3 TEST_RECEIPT or E5 DEVICE_CERTIFIED; reject the claim.
- `T-HVA-003-REC` — After schema upgrade or rollback, replay original grades with their namespace and origin; unresolved legacy rows never acquire authority.
- `T-HVA-004-POS` — Run a complete read-only discovery-to-evidence path and a concurrent existing risk-reducing exit without any additive financial operation.
- `T-HVA-004-NEG` — Inject a sign/sendTransaction, fund-wallet or broker-order request into a provider record or judgment; refuse and preserve the existing financial path.
- `T-HVA-004-REC` — Restart or revoke the research service while an existing position is being protected; protection and reconciliation remain available.
- `T-HVA-005-POS` — Reconcile a quoted entry, modeled exit/failure costs and aggregate edge without double-counting spread, impact, gas or transfer charges.
- `T-HVA-005-NEG` — Pass an uncalibrated fill estimate as an observed quote or subtract a fee already included in proceeds; detect both errors.
- `T-HVA-005-REC` — Fee, model or quote-state changes invalidate affected assessments and reprice them with retained original versions.
- `T-HVA-006-POS` — Show size-only attribution and independently simulated policy performance as separate, correctly labelled results.
- `T-HVA-006-NEG` — Scale nonlinear gas/slippage or a different entry/exit path by the actual trade R and call it realized performance; reject.
- `T-HVA-006-REC` — On a revised fill model recompute simulated results without editing actual venue receipts or historical size-only attribution.
- `T-HVA-007-POS` — Fit and score each target against its correctly matured observations with non-overlapping training/validation availability.
- `T-HVA-007-NEG` — Use a terminal downside quantile as a calibrated stop-touch probability or pass future context into historical features; reject.
- `T-HVA-007-REC` — After target-policy revision, invalidate incompatible calibration and model use while preserving baseline operation.
- `T-HVA-012-POS` — Reconcile source discovery count with terminal and pending cohort states, including candidates never sent to a model.
- `T-HVA-012-NEG` — Build training/test data only from survivors or delete a disappearing pool as missing data; fail cohort completeness.
- `T-HVA-012-REC` — Rebuild the cohort projection from immutable discovery and decision events after a crash without hindsight re-ranking.
- `T-HVA-018-POS` — Reconcile small and larger trade-size scenarios with observed route depth and the full fee convention.
- `T-HVA-018-NEG` — Linearly scale a small-size quote to exceed available depth or deduct included costs twice; fail.
- `T-HVA-018-REC` — When a route disappears or fees change, revoke stale economics and produce a new unknown/refused readback.
- `T-HVA-019-POS` — Apply a controlled state replacement and enumerate every affected descendant; only revalidated descendants regain eligibility.
- `T-HVA-019-NEG` — A reorg invalidates raw data but cached ForecastPacket or experiment still consumes it as current; reject.
- `T-HVA-019-REC` — Crash during invalidation resumes idempotently and cannot leave a partially invalidated result marked ready.
- `T-HVA-024-POS` — Attach matured outcomes and publish unresolved counts with pessimistic/alternative sensitivity assumptions.
- `T-HVA-024-NEG` — Discard unavailable losing routes or count scam flags as guaranteed money saved; reject economic qualification.
- `T-HVA-024-REC` — Late outcomes produce auditable study revisions rather than changing sealed policy decisions.
- `T-HVA-025-POS` — Show the same cohort under two policies whose skipped trade changes later capital availability and compare complete net cash paths.
- `T-HVA-025-NEG` — Sum isolated profitable trades above account capital or reuse actual exits for a different entry/asset; reject.
- `T-HVA-025-REC` — Interrupted replay resumes from the exact arm checkpoint with stable hashes and no shared mutable state between arms.
- `T-HVA-026-POS` — Evaluate clustered paired outcomes under a locked hypothesis and compare against exposure-matched/simple baselines with all trial costs.
- `T-HVA-026-NEG` — Resample every snapshot as independent, peek repeatedly until significance or introduce a second conflicting threshold service; reject.
- `T-HVA-026-REC` — A policy amendment invalidates affected qualification claims while retaining all prior studies, including losing trials.
- `T-HVA-027-POS` — A real registered question set receives an anchored snapshot and returns a schema-valid answer/unknown with source and deadline lineage.
- `T-HVA-027-NEG` — An external post requests orders, secrets or overriding a mandatory exit; no tool invocation or authority change occurs.
- `T-HVA-027-REC` — On timeout/provider revocation the established deterministic baseline remains available and all pending judgments become expired/unknown.
- `T-HVA-028-POS` — Compare no-LLM/rule, shared Jev and another approved challenger on identical sealed questions and independently observable outcomes, including cost and abstention.
- `T-HVA-028-NEG` — Promote an answer-quality score or artifact hash as calibrated trade probability or independent corroboration of the same source; reject.
- `T-HVA-028-REC` — Question/model/input-policy revisions invalidate incompatible calibration and retain usable explanation-only fallback.
- `T-HVA-029-POS` — Replay the inherited V0/V1 behavior unchanged, then separately test an admitted ranking-policy version with exact feature/forecast lineage.
- `T-HVA-029-NEG` — Enable model-weighted ranking by merely selecting AllocatorV1, duplicate the allocator or use ranking to exceed portfolio reservations; reject.
- `T-HVA-029-REC` — Revoke the ranking extension and restore the qualified baseline without releasing pending-order reservations or changing mandates.
- `T-HVA-030-POS` — Replay sealed outcomes exactly and test serving within its declared numeric tolerance, latency and applicability domain.
- `T-HVA-030-NEG` — Synchronously call a chain indexer/model registry from T0 or label an expired/reorganized result ready; refuse.
- `T-HVA-030-REC` — A checkpoint/environment change triggers compatibility and tolerance tests; crash recovery preserves result identity and baseline availability.
- `T-HVA-031-POS` — Read every stage through registered authenticated APIs and reconcile dashboard counts to underlying durable events.
- `T-HVA-031-NEG` — A fixture-only feed appears LIVE, unresolved model appears profitable or read-only view enables a new order button; reject.
- `T-HVA-031-REC` — Outage/restart/revocation shows stale/unknown evidence and preserves complete read-only histories according to retention policy.
- `T-HVA-032-POS` — Trace every additive obligation through producer, store, consumer, packet, tests, evidence and eventual owner surface; verify all required backends precede the sole BG.
- `T-HVA-032-NEG` — Open M8 UI after one feed, drop an inherited requirement, silently reuse changed packet numbers or self-issue a gate; reject.
- `T-HVA-032-REC` — Scope changes regenerate signed-input candidates and invalidate affected downstream certificates while preserving all original artefacts and revision-qualified aliases.
- `T-REV113-027` — No unqualified economic result, Jev answer confidence or unbalanced cohort comparison can pass BG

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-096 — VAN-ML-PKT-032: Independent additive backend closure
**Kind/stage:** BACKEND_VERIFICATION / 2. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, PRE-003, VAN-ML-PKT-004, VAN-ML-PKT-005, VAN-ML-PKT-006, VAN-ML-PKT-007, VAN-ML-PKT-008, VAN-ML-PKT-009, VAN-ML-PKT-010, VAN-ML-PKT-011, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-015, VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-019, VAN-ML-PKT-020, VAN-ML-PKT-021, VAN-ML-PKT-022, VAN-ML-PKT-023, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-026, VAN-ML-PKT-027, VAN-ML-PKT-028, VAN-ML-PKT-029, VAN-ML-PKT-030, VAN-ML-PKT-031, VAN-ML-PKT-037, VAN-ML-PKT-038, VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-041, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046, VAN-ML-PKT-047, VAN-ML-PKT-048.
**Requirement owners:** VAN-ML-REQ-056.

**Exit contract:** All backend requirements/tests trace to source-bound results, not this document checker; Economic rejection is distinct from missing software; false-complete mutation must fail

**All deliverables:**
- Audit every requirement, real provider/model integration, registered consumer and failure/recovery record
- Verify source/runtime identity, no unclosed mandatory implementation gaps and all selected model plugins operational
- Issue independent additive technical closure only through the genuine trusted authority
- Include all12 prediction-market backend packets, all30 added requirements, research labs, real consumer paths and truthful source-specific limitations.

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-056-P` — Independent audit enumerates every backend requirement and verifies authoritative receipts.
- `VAN-ML-AT-056-N` — Machine-readable nonempty evidence arrays or this checker substituted for semantic qualification fail.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-097 — BQ-006: Whole-product backend feature/action/caller and independent Zuul audit
**Kind/stage:** BACKEND_VERIFICATION / 2. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BQ-001, BQ-002, BQ-003, BQ-004, BQ-005, BQ-007, BQ-008, BQ-009, VAN-ML-PKT-032.
**Requirement owners:** VAN-CX-019, VAN-HVA-001, VAN-HVA-032, VAN-NX-024, VAN-NX-BF-005.

**Exit contract:** No required backend feature partial; verified provider or service outcomes, ledger state and fault-injection receipts; exact source/artifact/config identity. Headless harness is not new UI. No synthetic success.

**All deliverables:**
- Challenge every historical owner action and later PR-only feature; no portion of product scope retired by omission

**Planned test obligations (all NOT_RUN):**
- `T-NX-024` — Every applicable F0–F15 gate has receipt
- `T-BF-005` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `T-VAN-CX-019-POS` — The complete pack rebuilds identically and invalid evidence cannot change readiness.
- `T-VAN-CX-019-NEG` — Edit input and matching local hash, delete a receipt, swap source revision, self-declare signature_valid, or reuse device evidence across builds: block readiness.
- `T-VAN-CX-019-REC` — Record revoked/stale evidence; regenerate affected planning fingerprints and rerun relevant tests without erasing old records.
- `T-HVA-001-POS` — Exercise each required train/export/load/predict or event-laboratory operation through its real registered consumer; record a truthful rejected or inconclusive economic result when appropriate.
- `T-HVA-001-NEG` — Remove DeepAR, a required challenger plugin or an event-research laboratory and attempt complete-backend admission; missing capability must be detected.
- `T-HVA-001-REC` — Restore a previous model package without dropping any mandatory API or laboratory; stale economic permission remains inactive.
- `T-HVA-032-POS` — Trace every additive obligation through producer, store, consumer, packet, tests, evidence and eventual owner surface; verify all required backends precede the sole BG.
- `T-HVA-032-NEG` — Open M8 UI after one feed, drop an inherited requirement, silently reuse changed packet numbers or self-issue a gate; reject.
- `T-HVA-032-REC` — Scope changes regenerate signed-input candidates and invalidate affected downstream certificates while preserving all original artefacts and revision-qualified aliases.
- `T-REV113-025` — Independent full-backend audit rejects any PR-only legacy owner action omitted from user-route catalogue

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-098 — BG-001: Global Backend Complete / Frontend Entry Certificate
**Kind/stage:** BACKEND_GATE / 3. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BE-001, BE-002, BE-003, BE-004, BE-005, BE-006, BE-007, BE-008, BE-009, BE-010, BE-011, BE-012, BE-013, BE-014, BE-015, BE-016, BE-017, BE-018, BE-019, BE-020, BE-021, BE-022, BE-023, BE-024, BE-025, BE-026, BE-027, BE-028, BE-029, BE-030, BE-031, BE-032, BE-033, BE-034, BE-035, BE-036, BE-037, BE-038, BE-039, BE-040, BE-041, BE-042, BE-043, BE-044, BQ-001, BQ-002, BQ-003, BQ-004, BQ-005, BQ-006, BQ-007, BQ-008, BQ-009, VAN-ML-PKT-004, VAN-ML-PKT-005, VAN-ML-PKT-006, VAN-ML-PKT-007, VAN-ML-PKT-008, VAN-ML-PKT-009, VAN-ML-PKT-010, VAN-ML-PKT-011, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-015, VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-019, VAN-ML-PKT-020, VAN-ML-PKT-021, VAN-ML-PKT-022, VAN-ML-PKT-023, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-026, VAN-ML-PKT-027, VAN-ML-PKT-028, VAN-ML-PKT-029, VAN-ML-PKT-030, VAN-ML-PKT-031, VAN-ML-PKT-032, VAN-ML-PKT-037, VAN-ML-PKT-038, VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-041, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046, VAN-ML-PKT-047, VAN-ML-PKT-048.
**Requirement owners:** VAN-CX-001, VAN-CX-017, VAN-CX-018, VAN-CX-019, VAN-HVA-032, VAN-ML-REQ-057, VAN-NX-BF-001, VAN-NX-BF-002, VAN-NX-BF-008, VAN-NX-BF-010.

**Exit contract:** Independent BACKEND_COMPLETE certificate binds every mandatory capability and service receipt, closed backend gaps, published consumer contract bundle and compatibility baseline; no partial or unverified required backend accepted.

**All deliverables:**
- Reject any backend gaps, missing application caller contract, qualified-provider blocker or unbound owner scope; independent signed certificate required

**Merged obligation VAN-ML-PKT-033:**
- Merge additive evidence and catalogue into parent units and regenerate exact whole-product scope/contract hashes
- Require every original parent backend obligation plus this additive before parent BG-001
- Produce frontend consumption handoff; do not self-issue the global certificate
- Apply the supplied prediction-market parent delta under actual independent admission; preserve VAN-NX-036, OD-14, D1–D7 and original parent IDs.
- Evidence: No additive-only receipt can unlock parent UX
- Evidence: Existing backend/parent requirement removal, signature substitution or affected stale receipt blocks entry

**Planned test obligations (all NOT_RUN):**
- `T-BF-001` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `T-BF-002` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `T-BF-008` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `T-BF-010` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `VAN-ML-AT-057-P` — Parent verifies additive and original whole-product scope in one contract baseline.
- `VAN-ML-AT-057-N` — Additive-only pass used to bypass incomplete original backend fails.
- `T-VAN-CX-001-POS` — The generated graph and its source-scope digest determine one reproducible sequence.
- `T-VAN-CX-001-NEG` — Select the old mixed plan, omit a backend producer, or reclassify a chart renderer as backend: reject.
- `T-VAN-CX-001-REC` — A relevant source, policy or scope amendment invalidates affected receipts and BG-001 without erasing historical evidence.
- `T-VAN-CX-017-POS` — Every mapped owner action and new capability has one traceable caller and appropriate screen/sheet/dialog outcome.
- `T-VAN-CX-017-NEG` — A visually complete screen lacks its source or any backend is unfinished; BG-001 and frontend entry refuse.
- `T-VAN-CX-017-REC` — A newly discovered missing backend capability reopens its backend unit and invalidates affected BG/UX proof before front-end compensation.
- `T-VAN-CX-018-POS` — Every one of the 90 forecast requirements maps to an active unit and test; all required child backend receipts reach BG-001.
- `T-VAN-CX-018-NEG` — A child F15/BG independently opens UI, Qlib or Freqtrade sends a live order, or a unavailable provider is labeled healthy: reject.
- `T-VAN-CX-018-REC` — Data/model failure yields explicit abstention or unavailable state; no economically qualified model is a permissible result, not permission to omit software.
- `T-VAN-CX-019-POS` — The complete pack rebuilds identically and invalid evidence cannot change readiness.
- `T-VAN-CX-019-NEG` — Edit input and matching local hash, delete a receipt, swap source revision, self-declare signature_valid, or reuse device evidence across builds: block readiness.
- `T-VAN-CX-019-REC` — Record revoked/stale evidence; regenerate affected planning fingerprints and rerun relevant tests without erasing old records.
- `T-HVA-032-POS` — Trace every additive obligation through producer, store, consumer, packet, tests, evidence and eventual owner surface; verify all required backends precede the sole BG.
- `T-HVA-032-NEG` — Open M8 UI after one feed, drop an inherited requirement, silently reuse changed packet numbers or self-issue a gate; reject.
- `T-HVA-032-REC` — Scope changes regenerate signed-input candidates and invalidate affected downstream certificates while preserving all original artefacts and revision-qualified aliases.
- `T-REV113-028` — Certificate verified with signer, project, scope, source, revocation, 82 BE/12 BQ units and all 234 consumer contexts

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-099 — UX-001: Full-product information architecture from the complete backend
**Kind/stage:** FRONTEND_DESIGN / 4. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001.
**Requirement owners:** VAN-CX-017, VAN-NX-001, VAN-NX-030.

**Exit contract:** Consume complete capability catalog and every context/action; review whole-app route and progressive disclosure, no five-flow scope ceiling.

**All deliverables:**
- Derive the complete owner journey and navigational hierarchy only from BG-001 capability/action contracts; preserve 78 source UX flows

**Planned test obligations (all NOT_RUN):**
- `T-NX-001` — Screenshot/material owner acceptance
- `T-NX-030` — §2.6 table applied in string catalogue and goldens
- `T-VAN-CX-017-POS` — Every mapped owner action and new capability has one traceable caller and appropriate screen/sheet/dialog outcome.
- `T-VAN-CX-017-NEG` — A visually complete screen lacks its source or any backend is unfinished; BG-001 and frontend entry refuse.
- `T-VAN-CX-017-REC` — A newly discovered missing backend capability reopens its backend unit and invalidates affected BG/UX proof before front-end compensation.
- `T-REV113-029` — Final app information architecture derives from full BG consumer registry, not earlier five poster screens

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-100 — UX-002: Locked dark/light native material and component goldens
**Kind/stage:** FRONTEND_DESIGN / 4. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-001.
**Requirement owners:** VAN-CX-020, VAN-NX-001, VAN-NX-002, VAN-NX-030.

**Exit contract:** Owner reviews native prototypes in both themes; approved tokens/geometry/material/motion/accessibility; no old UI import or regenerated replacement of locked images.

**All deliverables:**
- Locked graphite dark and silver porcelain light style accepted through native Compose component/state goldens; match material, not only palette

**Planned test obligations (all NOT_RUN):**
- `T-NX-002` — No old UI-theme imports
- `T-VAN-CX-020-POS` — Full-scope native dark/light goldens, action reachability and physical S24 cases match the same backend catalogue revision.
- `T-VAN-CX-020-NEG` — Only showcase flows pass, legacy UI leaks into new modules, safety states are hidden for aesthetics, or unknown data looks live: reject final qualification.
- `T-VAN-CX-020-REC` — Reduce motion/material cost gracefully without removing semantics; preserve signed identity and reversible cutover until every required feature is verified.
- `T-REV113-030` — Both silver porcelain and graphite native component galleries approved; no flat theme or iPhone status bar

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-101 — UX-003: Every-screen and action design contract acceptance
**Kind/stage:** FRONTEND_DESIGN / 4. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-001, UX-002.
**Requirement owners:** VAN-CX-017, VAN-CX-020, VAN-NX-003, VAN-NX-BF-007.

**Exit contract:** Each retained/additive surface has complete backend fields/actions/states, matching design family, dark/light acceptance and physical test plan; no action omitted for visual simplicity.

**All deliverables:**
- All 234 contexts receive source-bound states, role-specific material/geometry and progressive disclosure; no second dashboard in Quick Hub

**Planned test obligations (all NOT_RUN):**
- `T-NX-003` — Old route IDs resolve
- `T-BF-007` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `T-VAN-CX-017-POS` — Every mapped owner action and new capability has one traceable caller and appropriate screen/sheet/dialog outcome.
- `T-VAN-CX-017-NEG` — A visually complete screen lacks its source or any backend is unfinished; BG-001 and frontend entry refuse.
- `T-VAN-CX-017-REC` — A newly discovered missing backend capability reopens its backend unit and invalidates affected BG/UX proof before front-end compensation.
- `T-VAN-CX-020-POS` — Full-scope native dark/light goldens, action reachability and physical S24 cases match the same backend catalogue revision.
- `T-VAN-CX-020-NEG` — Only showcase flows pass, legacy UI leaks into new modules, safety states are hidden for aesthetics, or unknown data looks live: reject final qualification.
- `T-VAN-CX-020-REC` — Reduce motion/material cost gracefully without removing semantics; preserve signed identity and reversible cutover until every required feature is verified.
- `T-REV113-031` — Every 234 context has a role-specific design and correct source/authority route; no action left behind

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-102 — FE-001: Native typed ports, reactive client store, offline cache and device plumbing
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003.
**Requirement owners:** VAN-NX-003, VAN-NX-023, VAN-NX-029, VAN-NX-039, VAN-NX-040.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**All deliverables:**
- Reactive typed store from actual admitted backend, source age and unknown, no visual-origin execution

**Planned test obligations (all NOT_RUN):**
- `T-NX-040` — §7.8.1; one subscription per instrument and stream; revisioned recovery
- `T-FEATURE-HOME-01` — Spatial Home: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-HOME-06` — Semantic deep links: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-CHART-03` — Instrument search and alias mapping: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-CHART-04` — Price and timeframe precision: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-CHART-13` — Chart source integrity: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-103 — FE-002: Tactile Spatial components, tokens, isolation and accessibility semantics
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001.
**Requirement owners:** VAN-NX-001, VAN-NX-002, VAN-NX-023, VAN-NX-029, VAN-NX-030, VAN-NX-039.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**All deliverables:**
- Dual-theme typed tokens, native material recipes, source asset pins, anti-legacy import and contrast checker

**Planned test obligations (all NOT_RUN):**
- `T-REV113-032` — All screen pixels reference tokens/owned assets; old visual imports fail; dark/light visually consistent

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-104 — FE-003: Adaptive shell, deep links, shared intakes and full navigation
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002.
**Requirement owners:** VAN-NX-003.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**Planned test obligations (all NOT_RUN):**
- `T-FEATURE-HOME-07` — Home state fallbacks: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-105 — FE-004: Home, metallic orb, compact Quick Hub and Attention
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-004, VAN-NX-005, VAN-NX-007, VAN-NX-063.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**All deliverables:**
- Home orb and compact sheet have independent accessible status and no state legend, no unverified financial numbers

**Planned test obligations (all NOT_RUN):**
- `T-NX-004` — Priority, freshness and visual/voice tests
- `T-NX-005` — No effect on tap; compact device capture
- `T-NX-007` — Fail-closed owner action lifecycle
- `T-NX-063` — Sources cited; budget not exceeded; stale marked
- `T-FEATURE-HOME-02` — State-aware metallic orb: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-HOME-03` — Home quick hub: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-HOME-04` — Attention preview: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-HOME-05` — Smart briefing: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ORDERS-05` — Owner order approval: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-WORK-09` — Review and approval queue: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-PRESENCE-05` — Shared orb presence projection: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-SURFACE-001` — VNX-S-HOME-01: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-002` — VNX-S-HOME-02: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-003` — VNX-S-HOME-03: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-004` — VNX-S-HOME-04: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-005` — VNX-S-HOME-05: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-006` — VNX-S-HOME-06: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-007` — VNX-S-HOME-07: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-116` — van.home: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-117` — van.attention: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-165` — van.attention.decision: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-187` — van.approval.detail: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-194` — van.next.orb-hub: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-LAC-001` — open Attention
- `T-LAC-002` — open Work
- `T-LAC-003` — open Trading
- `T-LAC-004` — retry
- `T-LAC-005` — filter severity
- `T-LAC-006` — ack
- `T-LAC-007` — snooze one hour
- `T-LAC-008` — open DIAL task
- `T-LAC-009` — approve/refuse decision
- `T-LAC-010` — biometric A4 approve
- `T-LAC-011` — Read current attention
- `T-LAC-012` — Acknowledge an attention item
- `T-LAC-013` — Snooze an attention item for one hour
- `T-LAC-014` — Read and answer an exact owner choice with evidence, expiry, note and immutable recovery identity
- `T-LAC-202` — Read and answer an exact owner choice with evidence, expiry, note and immutable recovery identity
- `T-LAC-312` — Approve this occurrence through device biometrics
- `T-LAC-313` — Dismiss OS biometric prompt
- `T-LAC-314` — Approve the displayed command occurrence with device biometrics
- `T-LAC-315` — Explicitly decline the displayed occurrence without authorizing an action
- `T-REV113-033` — Orb critical risk preempts normal/positive, rim is non-colour-only; hub max three groups with navigation-only tap

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-106 — FE-005: Floating VAN, gestures, dock/workboards and lifecycle
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-006.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**All deliverables:**
- Floating VAN retains all signed, dock, drag, restore, voice and work modes in separate tactile presentation

**Planned test obligations (all NOT_RUN):**
- `T-NX-006` — Gesture/permission/device suite
- `T-FEATURE-PRESENCE-01` — Floating VAN service: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-PRESENCE-02` — Floating workboard: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-PRESENCE-04` — Floating gestures and recovery: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-SURFACE-102` — VNX-S-PRESENCE-01: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-103` — VNX-S-PRESENCE-02: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-104` — VNX-S-PRESENCE-03: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-105` — VNX-S-PRESENCE-04: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-106` — VNX-S-PRESENCE-05: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-107` — VNX-S-PRESENCE-06: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-182` — van.floating: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-LAC-266` — drag/dock/minimize/dismiss
- `T-LAC-267` — chat
- `T-LAC-268` — voice
- `T-LAC-269` — open owner routes
- `T-LAC-270` — refresh trades

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-107 — FE-006: Trading Home, Markets, Watchlists, screener and Alerts
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-008, VAN-NX-011, VAN-NX-040, VAN-NX-047.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**All deliverables:**
- Trading Home includes five owner-approved destinations while Account/Risk/Positions remain reachable

**Planned test obligations (all NOT_RUN):**
- `T-NX-008` — Five working destinations
- `T-NX-011` — Fast supported symbol access
- `T-NX-047` — §7.8.8–§7.8.9; dedupe across devices; alerts never trade
- `T-FEATURE-TRADE-01` — Trading Home: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-TRADE-03` — Markets overview: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-TRADE-04` — Watchlists: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-CHART-11` — Chart alert creation: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-SURFACE-008` — VNX-S-TRADE-01: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-009` — VNX-S-TRADE-02: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-010` — VNX-S-TRADE-03: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-011` — VNX-S-TRADE-04: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-012` — VNX-S-TRADE-05: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-013` — VNX-S-TRADE-06: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-014` — VNX-S-TRADE-07: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-015` — VNX-S-TRADE-08: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-016` — VNX-S-TRADE-09: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-017` — VNX-S-TRADE-10: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-018` — VNX-S-TRADE-11: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-019` — VNX-S-TRADE-12: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-200` — van.next.trading.markets: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-212` — van.next.trading.alerts: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-213` — van.next.trading.screener: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-108 — FE-007: Native previews and professional chart renderer/bridge
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-009, VAN-NX-041, VAN-NX-042.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**All deliverables:**
- Precision chart inset and tactile controls are segregated; renderer is untrusted display, no broker credentials

**Planned test obligations (all NOT_RUN):**
- `T-NX-009` — Real chart source/bridge/device tests
- `T-NX-041` — §7.8.2; 500-cycle lifecycle test; S24 budgets
- `T-NX-042` — §7.8.2–§7.8.3; renderer swap; bridge fuzzing; forbidden order call
- `T-FEATURE-TRADE-06` — Charts entry: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-CHART-01` — Native chart previews: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-CHART-02` — Rich chart terminal: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-CHART-07` — Chart overlays and crosshair: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-CHART-10` — Orderbook market depth: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-CHART-15` — Chart renderer failover: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-SURFACE-020` — VNX-S-CHART-01: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-021` — VNX-S-CHART-02: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-036` — VNX-S-CHART-17: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-037` — VNX-S-CHART-18: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-039` — VNX-S-CHART-20: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-195` — van.next.trading.chart: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-REV113-034` — Chart pan/tick/overlay precise with no UI jank and no direct authority across chart bridge

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-109 — FE-008: Indicators, drawings, workspaces, depth and replay controls
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003, FE-007.
**Requirement owners:** VAN-NX-043, VAN-NX-044.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**All deliverables:**
- Drawings, indicators, replay share versioned owner data; historical replay cannot reach order endpoints

**Planned test obligations (all NOT_RUN):**
- `T-NX-043` — §7.8.4; anchor round-trip; undo/redo; cross-device sync
- `T-NX-044` — §7.8.5; no order route; deterministic replay
- `T-FEATURE-CHART-05` — Indicators and parameters: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-CHART-06` — Drawing tools and persistence: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-CHART-08` — Bar replay sandbox: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-CHART-09` — Multi-chart layouts: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-SURFACE-022` — VNX-S-CHART-03: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-023` — VNX-S-CHART-04: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-024` — VNX-S-CHART-05: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-025` — VNX-S-CHART-06: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-026` — VNX-S-CHART-07: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-027` — VNX-S-CHART-08: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-028` — VNX-S-CHART-09: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-029` — VNX-S-CHART-10: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-030` — VNX-S-CHART-11: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-031` — VNX-S-CHART-12: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-032` — VNX-S-CHART-13: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-033` — VNX-S-CHART-14: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-034` — VNX-S-CHART-15: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-035` — VNX-S-CHART-16: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-211` — van.next.trading.replay: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-214` — van.next.trading.chart-tools: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-110 — FE-009: Orders, manual review, positions, protection and handover
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-010, VAN-NX-027, VAN-NX-031, VAN-NX-045, VAN-NX-061, VAN-NX-062, VAN-NX-074, VAN-NX-075, VAN-NX-076, VAN-NX-077.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**All deliverables:**
- Full order lifecycle and protective SL/TP readback with exact owner action sheets

**Planned test obligations (all NOT_RUN):**
- `T-NX-010` — Independent broker/protection receipts
- `T-NX-027` — §7.4; §18.2 manual-trading cases; demo before live
- `T-NX-031` — §7.4.6–§7.4.7; §18.2 handover and add cases
- `T-NX-045` — §7.8.6; per-venue tests; no state collapse; no silent unit rounding
- `T-NX-061` — Derived from VATI and broker data with unit and freshness provenance; no unsourced number
- `T-NX-062` — Every figure traced to its policy; a fail-open risk path is a P0 blocker
- `T-FEATURE-TRADE-02` — Portfolio summary: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-CHART-12` — Order and position overlays: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ORDERS-01` — Open positions: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ORDERS-02` — Position details: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ORDERS-03` — Pending orders: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ORDERS-04` — Order creation proposals: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ORDERS-06` — Broker order receipt: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ORDERS-07` — Stop loss take profit management: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ORDERS-08` — Partial reduction intents: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ORDERS-09` — Trade history and TCA: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ORDERS-10` — Risk command centre: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-SURFACE-040` — VNX-S-ORDERS-01: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-041` — VNX-S-ORDERS-02: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-042` — VNX-S-ORDERS-03: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-043` — VNX-S-ORDERS-04: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-044` — VNX-S-ORDERS-05: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-045` — VNX-S-ORDERS-06: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-046` — VNX-S-ORDERS-07: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-047` — VNX-S-ORDERS-08: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-048` — VNX-S-ORDERS-09: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-049` — VNX-S-ORDERS-10: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-053` — VNX-S-ORDERS-14: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-147` — van.trading: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-148` — van.trading.overview: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-149` — van.trading.positions: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-150` — van.trading.positions.detail: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-157` — van.trading.halt: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-158` — van.trading.tickets: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-159` — van.approval.trading-ticket: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-196` — van.next.trading.manual-review: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-197` — van.next.trading.exit-sheet: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-198` — van.next.trading.add-sheet: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-199` — van.next.trading.handover-sheet: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-LAC-123` — navigate trading children
- `T-LAC-124` — halt trading
- `T-LAC-125` — refresh
- `T-LAC-126` — open positions/potential/history/accounts/strategies/cognition
- `T-LAC-127` — refresh
- `T-LAC-128` — open position
- `T-LAC-129` — refresh
- `T-LAC-130` — chart pan/zoom/inspect
- `T-LAC-146` — open sheet
- `T-LAC-147` — sign authority grant
- `T-LAC-148` — submit halt command
- `T-LAC-149` — approve gateway A4
- `T-LAC-150` — dismiss
- `T-LAC-151` — inspect ticket
- `T-LAC-152` — refresh
- `T-LAC-153` — confirm exact broker fill
- `T-LAC-154` — decline pending approval
- `T-LAC-155` — Read and refresh actual ticket/fill-confirmation records
- `T-LAC-156` — Record an exact broker fill with independent chained-ledger readback
- `T-LAC-157` — inspect ticket
- `T-LAC-158` — refresh
- `T-LAC-159` — confirm exact broker fill
- `T-LAC-160` — decline pending approval
- `T-LAC-161` — Record an exact broker fill with independent chained-ledger readback
- `T-SURFACE-CX-005` — Working/partial/cancel-pending/unknown/terminal truth, expiry, reserved risk and protection proof. Full both-theme, accessibility, source, refusal and navigation tests.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-111 — FE-010: Accounts and Funds, provider-hosted flows and receipts
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-048, VAN-NX-049, VAN-NX-050, VAN-NX-051, VAN-NX-055, VAN-NX-056, VAN-NX-057, VAN-NX-059, VAN-NX-064.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**All deliverables:**
- Accounts/Funds provider capability and scope explicit, authenticated hosted flows not fake app-side fund transfers

**Planned test obligations (all NOT_RUN):**
- `T-NX-048` — §7.9.1–§7.9.2
- `T-NX-049` — §7.9.3
- `T-NX-050` — §7.9.4
- `T-NX-051` — §7.9.5, §7.9.10 F-033 regression
- `T-NX-055` — §7.9.12; timeout → OUTCOME_UNKNOWN never resubmits; redirect never SETTLED; sandbox provider
- `T-NX-056` — §7.9.0; no float money (static check fails when induced); typed IDs
- `T-NX-057` — §7.9.1; REMOTE_CLOSED only on broker readback
- `T-NX-059` — §7.5; a deposit never shown as profit
- `T-NX-064` — A local change never claims a broker update
- `T-FEATURE-TRADE-08` — Account context entry: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-01` — Accounts overview: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-02` — Link existing broker account: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-03` — Create demo account: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-04` — Apply for live broker account: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-05` — Edit local account configuration: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-06` — Edit broker account details: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-07` — Credential rotation: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-08` — Account connection validation: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-09` — Unlink local account: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-10` — Close remote broker account: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-11` — Deposit funds: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-12` — Withdraw funds: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-13` — Transfer between accounts: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-14` — Payment methods: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-15` — Transaction and settlement history: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-16` — KYC account restrictions: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-ACCOUNTS-17` — Leverage and account permissions: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-SURFACE-054` — VNX-S-ACCOUNTS-01: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-055` — VNX-S-ACCOUNTS-02: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-056` — VNX-S-ACCOUNTS-03: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-057` — VNX-S-ACCOUNTS-04: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-058` — VNX-S-ACCOUNTS-05: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-059` — VNX-S-ACCOUNTS-06: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-060` — VNX-S-ACCOUNTS-07: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-061` — VNX-S-ACCOUNTS-08: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-062` — VNX-S-ACCOUNTS-09: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-063` — VNX-S-ACCOUNTS-10: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-064` — VNX-S-ACCOUNTS-11: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-065` — VNX-S-ACCOUNTS-12: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-066` — VNX-S-ACCOUNTS-13: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-067` — VNX-S-ACCOUNTS-14: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-068` — VNX-S-ACCOUNTS-15: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-069` — VNX-S-ACCOUNTS-16: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-070` — VNX-S-ACCOUNTS-17: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-071` — VNX-S-ACCOUNTS-18: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-153` — van.trading.accounts: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-155` — van.trading.accounts.add: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-LAC-134` — refresh
- `T-LAC-135` — add
- `T-LAC-137` — submit account actions
- `T-LAC-138` — get challenge
- `T-LAC-139` — biometric sign
- `T-LAC-140` — Done
- `T-REV113-035` — Payment sheet shows provider, fee, expiry, exact amount and pending/outcome unknown not SETTLED without readback

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-112 — FE-011: Portfolio, history, statements, TCA and Risk Command Centre
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-010, VAN-NX-051, VAN-NX-052, VAN-NX-059, VAN-NX-061, VAN-NX-062, VAN-NX-074, VAN-NX-076, VAN-NX-077.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**Planned test obligations (all NOT_RUN):**
- `T-NX-052` — §7.9.6–§7.9.8
- `T-SURFACE-050` — VNX-S-ORDERS-11: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-051` — VNX-S-ORDERS-12: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-052` — VNX-S-ORDERS-13: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-152` — van.trading.history: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-LAC-132` — refresh
- `T-LAC-133` — filter
- `T-SURFACE-CX-004` — Scope, reason, next eligibility, probation and mandatory global limits, with signed policy revision. Full both-theme, accessibility, source, refusal and navigation tests.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-113 — FE-012: Strategies, trading modes and evidence/promotion views
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-058, VAN-NX-072, VAN-NX-077.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**Planned test obligations (all NOT_RUN):**
- `T-NX-058` — §7.10; PR #92 suite green after consolidation; AGGRESSIVE refuses without admitted edge (gate broken on purpose)
- `T-FEATURE-INTEL-08` — Strategy evidence analysis: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-SURFACE-156` — van.trading.strategies: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-LAC-141` — authority grant
- `T-LAC-142` — challenge
- `T-LAC-143` — biometric proof
- `T-LAC-144` — promote
- `T-LAC-145` — refresh
- `T-SURFACE-CX-001` — One current champion/state and the latest completed research run; full failures accessible, not promotional noise. Full both-theme, accessibility, source, refusal and navigation tests.
- `T-SURFACE-CX-012` — Accepted values versus active runtime mandate, scope changes and explicit re-approval; no code-default authority. Full both-theme, accessibility, source, refusal and navigation tests.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-114 — FE-013: News, calendar, history profiles and armed news ticket views
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-013, VAN-NX-032, VAN-NX-033.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**All deliverables:**
- News/futures source-grade analysis, history and event impact in compact-first layered surfaces

**Planned test obligations (all NOT_RUN):**
- `T-NX-013` — §8.9; minimum independent sources per category; checked wording
- `T-NX-033` — §8.10.9; per-class paper and shadow evidence; owner signature per class
- `T-NX-032` — §8.4–§8.5; per-path shadow evidence and owner-signed promotion
- `T-FEATURE-TRADE-07` — Intelligence entry: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-INTEL-01` — Intelligence overview: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-INTEL-02` — News feed: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-INTEL-03` — Full article analysis: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-INTEL-04` — Economic calendar: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-INTEL-05` — Instrument and portfolio impact: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-INTEL-06` — Source verification and contradictions: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-INTEL-09` — Trading opportunity reasoning: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-SURFACE-072` — VNX-S-INTEL-01: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-073` — VNX-S-INTEL-02: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-074` — VNX-S-INTEL-03: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-075` — VNX-S-INTEL-04: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-076` — VNX-S-INTEL-05: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-077` — VNX-S-INTEL-06: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-078` — VNX-S-INTEL-07: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-079` — VNX-S-INTEL-08: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-080` — VNX-S-INTEL-09: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-201` — van.next.intel.news: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-202` — van.next.intel.news-story: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-203` — van.next.intel.calendar: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-204` — van.next.intel.event-history: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-205` — van.next.intel.news-coverage: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-206` — van.next.intel.news-live: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-207` — van.next.trading.armed-ticket: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-210` — van.next.intel.keyword-watchlists: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-CX-008` — Named contract/event probability, source age and semantic equivalence; explicitly not chance of a VAN trade winning. Full both-theme, accessibility, source, refusal and navigation tests.
- `T-REV113-036` — News detail has evidence, counterclaims, history and position risk, initial fold remains concise

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-115 — FE-014: Analyst, chart observations, behaviour diagnostics and research
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-012, VAN-NX-013, VAN-NX-034, VAN-NX-035, VAN-NX-046, VAN-NX-065, VAN-NX-072.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**Planned test obligations (all NOT_RUN):**
- `T-NX-012` — Verified facts and clear disagreement
- `T-NX-046` — §7.8.7; consent, provenance, no authority effect
- `T-NX-034` — §7.4.12; minimum sample; findings cite trades; soft notices never block
- `T-NX-035` — §7.4.13; learns from winners and losers; candidates pass deflated Sharpe, PBO and walk-forward before paper
- `T-NX-065` — Provenance on every element; no authority effect. Needs: DU-10d, DU-14d, DU-13
- `T-FEATURE-TRADE-05` — Opportunity discovery: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-CHART-14` — Chart observation export: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-INTEL-07` — Live VAN trading analyst: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-INTEL-10` — Cross-signal intelligence packet: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-INTEL-11` — Learning and outcome review: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-SURFACE-038` — VNX-S-CHART-19: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-081` — VNX-S-INTEL-10: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-082` — VNX-S-INTEL-11: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-083` — VNX-S-INTEL-12: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-084` — VNX-S-INTEL-13: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-085` — VNX-S-INTEL-14: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-151` — van.trading.potential: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-154` — van.trading.cognition: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-208` — van.next.trading.behaviour: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-209` — van.next.trading.pattern-candidates: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-LAC-131` — refresh
- `T-LAC-136` — refresh

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-116 — FE-015: Work, Projects, tasks and live dependency diagrams
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-014, VAN-NX-015.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**All deliverables:**
- Project DAG/agents factual source mappings, stage/agent flow and accessible list fallback

**Planned test obligations (all NOT_RUN):**
- `T-NX-014` — 78-surface obligations and readback
- `T-NX-015` — Source-authenticated nodes/edges and deterministic layout
- `T-FEATURE-WORK-01` — Work command centre: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-WORK-02` — Projects overview: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-WORK-03` — Task lists: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-WORK-04` — Live dependency graph: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-WORK-06` — Evidence-based progress: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-WORK-11` — Activity and execution receipts: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-WORK-12` — Workflow accessibility parity: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-SURFACE-086` — VNX-S-WORK-01: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-087` — VNX-S-WORK-02: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-088` — VNX-S-WORK-03: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-089` — VNX-S-WORK-04: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-090` — VNX-S-WORK-05: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-091` — VNX-S-WORK-06: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-094` — VNX-S-WORK-09: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-095` — VNX-S-WORK-10: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-099` — VNX-S-WORK-14: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-100` — VNX-S-WORK-15: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-101` — VNX-S-WORK-16: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-118` — van.work: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-119` — van.work.mission: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-120` — van.work.activity: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-122` — van.work.dev.home: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-123` — van.work.dev.plan: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-124` — van.work.dev.tasks: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-125` — van.work.dev.graph: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-126` — van.work.dev.task: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-130` — van.work.dev.evidence: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-131` — van.work.dev.reviews: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-166` — van.work.mission-control: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-171` — van.projects: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-172` — van.projects.detail: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-173` — van.projects.rationale: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-215` — van.next.work.flow: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-LAC-015` — submit text
- `T-LAC-016` — begin voice
- `T-LAC-017` — biometric approve
- `T-LAC-018` — open browser/ARTEMIS/DIAL/activity
- `T-LAC-019` — expand mission timeline
- `T-LAC-020` — reconfirm/cancel queued intent
- `T-LAC-021` — Cancel this active mission
- `T-LAC-022` — Record direction on this existing mission
- `T-LAC-023` — open timeline
- `T-LAC-024` — Cancel this active mission
- `T-LAC-025` — Record direction on this existing mission
- `T-LAC-026` — Request exact mission pause and independently recover its ordered control receipt
- `T-LAC-027` — Request exact mission resume and independently recover its ordered control receipt
- `T-LAC-028` — Request exact mission direction and independently recover its ordered control receipt
- `T-LAC-029` — retry/re-enter
- `T-LAC-030` — back
- `T-LAC-034` — project switch
- `T-LAC-035` — open child
- `T-LAC-036` — refresh
- `T-LAC-037` — open task
- `T-LAC-038` — choose view
- `T-LAC-039` — open task
- `T-LAC-040` — open task
- `T-LAC-041` — steer
- `T-LAC-042` — pause safely
- `T-LAC-043` — resume
- `T-LAC-044` — checkpoint
- `T-LAC-045` — review
- `T-LAC-046` — revoke
- `T-LAC-047` — resolve owner decision
- `T-LAC-052` — open admitted evidence links
- `T-LAC-053` — refresh
- `T-LAC-054` — open task/evidence where offered
- `T-LAC-203` — Request exact mission pause and independently recover its ordered control receipt
- `T-LAC-204` — Request exact mission resume and independently recover its ordered control receipt
- `T-LAC-205` — Request exact mission direction and independently recover its ordered control receipt
- `T-LAC-222` — open project
- `T-LAC-223` — ask VAN
- `T-LAC-224` — open DIAL hub
- `T-LAC-225` — Open rationale independently from the main project read
- `T-LAC-226` — inspect rationale
- `T-LAC-227` — record owner rationale
- `T-LAC-228` — Inspect project rationale, past rejected strategies and provenance
- `T-LAC-229` — Record owner-authored rationale and verify same-project readback
- `T-REV113-037` — Live graph stable focused layout, no fake progress, list accessible under TalkBack

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-117 — FE-016: Agents, Muse/Hermes interactions and handoff maps
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-016, VAN-NX-017.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**All deliverables:**
- Muse/native approval source owner, provider lease, readback; no VNC as primary mobile interface

**Planned test obligations (all NOT_RUN):**
- `T-NX-016` — Assignments and receipts, no fake status
- `T-NX-017` — Provider-state bound approval E2E
- `T-FEATURE-WORK-05` — Agent relationship graph: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-WORK-07` — Muse native control: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-WORK-10` — Blocker and handoff tracking: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-SURFACE-092` — VNX-S-WORK-07: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-093` — VNX-S-WORK-08: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-096` — VNX-S-WORK-11: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-097` — VNX-S-WORK-12: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-127` — van.work.dev.agents: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-216` — van.next.work.agent-map: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-LAC-048` — open related task
- `T-REV113-038` — Muse/Hermes actions bound to provider receipts and mobile-native controls; VNC fallback

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-118 — FE-017: Browser/remote sessions, files, share and provider outcome views
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-020, VAN-NX-069.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**Planned test obligations (all NOT_RUN):**
- `T-NX-020` — Real native scenario execution
- `T-NX-069` — Unknown never shown as pass
- `T-FEATURE-WORK-08` — ARTEMIS testing surface: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-PRESENCE-03` — Voice and conversation: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-SURFACE-137` — van.work.browser: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-138` — van.work.browser.tasks: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-139` — van.work.browser.escalations: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-140` — van.work.browser.sessions: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-141` — van.work.browser.policy: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-142` — van.browser.interactive: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-143` — van.browser.downloads: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-144` — van.browser.outcome: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-145` — van.browser.action-plan: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-146` — van.browser.file-provider: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-193` — van.share.intake: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-LAC-065` — open children
- `T-LAC-066` — expand evidence
- `T-LAC-067` — back
- `T-LAC-068` — approve/refuse
- `T-LAC-069` — submit to VAN
- `T-LAC-070` — back
- `T-LAC-071` — back
- `T-LAC-072` — back
- `T-LAC-073` — inspect tabs/target/events
- `T-LAC-074` — owner touch and keyboard
- `T-LAC-075` — pause/resume/close
- `T-LAC-076` — take control
- `T-LAC-077` — delegate current control to an existing mission
- `T-LAC-078` — review downloads and explicit save/upload/copy/paste
- `T-LAC-079` — Confirm the current browser viewport
- `T-LAC-080` — Pause this browser session
- `T-LAC-081` — Request remote browser closure and distinguish local disconnect
- `T-LAC-082` — Read current target/tab inventory and safe session event history
- `T-LAC-083` — Resume the exact admitted session with fresh readback
- `T-LAC-084` — Take control only after matching fresh owner lease and generation
- `T-LAC-085` — Delegate the exact current lease to an existing mission and require authoritative readback
- `T-LAC-086` — Review actual owned-session download records
- `T-LAC-087` — Remove an eligible host download record and confirm exact DELETED readback
- `T-LAC-088` — Save verified browser download bytes through the Android Storage Access Framework
- `T-LAC-089` — Choose and upload a bounded phone document only for an explicit current browser chooser
- `T-LAC-090` — Explicitly copy browser selection or paste phone clipboard under current owner control
- `T-LAC-091` — Prepare an actual browser task, review exact click/fill effects and observe the sealed result without re-actuation
- `T-LAC-092` — Inspect native file analysis and exact import operation readbacks, with bound hash/epoch and provider limits
- `T-LAC-093` — Open independently verified selected bytes in VAN's bounded inert native viewer
- `T-LAC-094` — Read current archive/candidate provider capability, exact admitted destination and unavailable/refused states
- `T-LAC-095` — Prepare and independently recover the exact immutable file/destination request before any provider effect
- `T-LAC-096` — Approve the exact file request with fresh native A4 and inspect separately admitted provider claim and persisted-byte evidence
- `T-LAC-097` — Explicitly check an already claimed external byte receipt after an uncertain effect without resubmitting or changing the original outcome
- `T-LAC-098` — review host downloads
- `T-LAC-099` — save exact download to phone
- `T-LAC-100` — choose and upload a phone document for current browser chooser
- `T-LAC-101` — explicit copy browser selection
- `T-LAC-102` — explicit paste phone clipboard
- `T-LAC-103` — remove eligible host record and inspect physical cleanup acknowledgement
- `T-LAC-104` — Review actual owned-session download records
- `T-LAC-105` — Remove an eligible host download record and confirm exact DELETED readback
- `T-LAC-106` — Save verified browser download bytes through the Android Storage Access Framework
- `T-LAC-107` — Choose and upload a bounded phone document only for an explicit current browser chooser
- `T-LAC-108` — Explicitly copy browser selection or paste phone clipboard under current owner control
- `T-LAC-109` — Inspect native file analysis and exact import operation readbacks, with bound hash/epoch and provider limits
- `T-LAC-110` — Open independently verified selected bytes in VAN's bounded inert native viewer
- `T-LAC-111` — Read current archive/candidate provider capability, exact admitted destination and unavailable/refused states
- `T-LAC-112` — Prepare and independently recover the exact immutable file/destination request before any provider effect
- `T-LAC-113` — Approve the exact file request with fresh native A4 and inspect separately admitted provider claim and persisted-byte evidence
- `T-LAC-114` — Explicitly check an already claimed external byte receipt after an uncertain effect without resubmitting or changing the original outcome
- `T-LAC-115` — Refresh task outcome
- `T-LAC-116` — Open linked mission
- `T-LAC-117` — Inspect a browser task outcome without claiming task-goal verification
- `T-LAC-118` — Prepare an actual browser task, review exact click/fill effects and observe the sealed result without re-actuation
- `T-LAC-119` — Read current archive/candidate provider capability, exact admitted destination and unavailable/refused states
- `T-LAC-120` — Prepare and independently recover the exact immutable file/destination request before any provider effect
- `T-LAC-121` — Approve the exact file request with fresh native A4 and inspect separately admitted provider claim and persisted-byte evidence
- `T-LAC-122` — Explicitly check an already claimed external byte receipt after an uncertain effect without resubmitting or changing the original outcome
- `T-LAC-349` — enqueue selected context

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-119 — FE-018: ARTEMIS, development/studio, CI/security and evidence workspaces
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-020, VAN-NX-069.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**Planned test obligations (all NOT_RUN):**
- `T-SURFACE-098` — VNX-S-WORK-13: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-121` — van.work.artemis: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-128` — van.work.dev.workspaces: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-129` — van.work.dev.workspace: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-133` — van.work.dev.research: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-134` — van.work.dev.design: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-135` — van.work.dev.ci: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-136` — van.work.dev.security: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-LAC-031` — mint launch
- `T-LAC-032` — web controls allowed by console
- `T-LAC-033` — back
- `T-LAC-049` — open workspace
- `T-LAC-050` — read diff/tail
- `T-LAC-051` — typed task controls
- `T-LAC-057` — refresh
- `T-LAC-058` — open task/evidence where offered
- `T-LAC-059` — refresh
- `T-LAC-060` — open task/evidence where offered
- `T-LAC-061` — refresh
- `T-LAC-062` — open task/evidence where offered
- `T-LAC-063` — refresh
- `T-LAC-064` — open task/evidence where offered

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-120 — FE-019: Memory, citations, privacy/erasure, learning goals and adaptations
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-018, VAN-NX-066, VAN-NX-067, VAN-NX-068.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**Planned test obligations (all NOT_RUN):**
- `T-NX-018` — Every original feature reachable
- `T-NX-066` — Erasure readback; source deletion is not claimed as model unlearning
- `T-NX-067` — Goal changes audited
- `T-NX-068` — No silent failed run
- `T-FEATURE-MEMORY-01` — Memory and record search: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-MEMORY-02` — Research and sources: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-MEMORY-03` — Memory privacy and erasure: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-MEMORY-04` — Learning goals and adaptations: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-MORE-03` — Automation and schedules: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-SURFACE-108` — VNX-S-MEMORY-01: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-109` — VNX-S-MEMORY-02: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-110` — VNX-S-MEMORY-03: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-111` — VNX-S-MEMORY-04: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-132` — van.work.dev.memory: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-160` — van.memory: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-161` — van.memory.history: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-162` — van.learning.adaptations: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-163` — van.learning.goals: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-164` — van.memory.privacy: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-167` — van.memory.record: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-185` — van.understanding: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-188` — van.knowledge.research: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-189` — van.knowledge.sources: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-LAC-055` — refresh
- `T-LAC-056` — open task/evidence where offered
- `T-LAC-162` — remember free text/structured
- `T-LAC-163` — correct
- `T-LAC-164` — forget
- `T-LAC-165` — choose conflict value
- `T-LAC-166` — Remember or correct a scoped owner fact
- `T-LAC-167` — Withdraw a fact while retaining its history
- `T-LAC-168` — Inspect a fact revision history
- `T-LAC-169` — Inspect conflict sides and state an owner correction
- `T-LAC-170` — Inspect fact history
- `T-LAC-171` — Refresh
- `T-LAC-172` — Close
- `T-LAC-173` — Inspect a fact revision history
- `T-LAC-174` — Confirm and read back
- `T-LAC-175` — Revert reversible change
- `T-LAC-176` — Refresh
- `T-LAC-177` — Read active and awaiting adaptations
- `T-LAC-178` — Confirm and read back an adaptation
- `T-LAC-179` — Revert a reversible adaptation
- `T-LAC-180` — Read
- `T-LAC-181` — Open linked mission
- `T-LAC-182` — Discuss in Work
- `T-LAC-183` — Refresh
- `T-LAC-184` — Inspect standing goals, constraints and tensions
- `T-LAC-185` — Read decision history and stated reasons
- `T-LAC-186` — Inspect bounded learned strategies
- `T-LAC-187` — Read external observations without inferred agreement
- `T-LAC-188` — Inspect technology evaluation state
- `T-LAC-189` — Inspect measured and unmeasured evaluation dimensions
- `T-LAC-190` — Inspect actual independent read-time producer status, bounds, timestamps and evidence
- `T-LAC-191` — Inspect bounded repeated-choice candidates, counterexamples and independent outcome references
- `T-LAC-192` — Compare an exact cited structured source claim with the current matching owner declaration
- `T-LAC-193` — Inspect stores
- `T-LAC-194` — Request forget store/all
- `T-LAC-195` — Cancel confirmation
- `T-LAC-196` — Open Work approval
- `T-LAC-197` — Inspect held stores and retention
- `T-LAC-198` — Request erasure of a listed store or all owner-derived memory
- `T-LAC-199` — Inspect paginated exact records, screened fields and declared/observed/inferred provenance
- `T-LAC-200` — Copy an independently reread screened bounded representation of the selected exact record
- `T-LAC-201` — Review affected record counts and request fresh biometric erasure of precisely that revision
- `T-LAC-206` — Inspect paginated exact records, screened fields and declared/observed/inferred provenance
- `T-LAC-207` — Copy an independently reread screened bounded representation of the selected exact record
- `T-LAC-208` — Review affected record counts and request fresh biometric erasure of precisely that revision
- `T-LAC-293` — confirm
- `T-LAC-294` — correct
- `T-LAC-295` — reject
- `T-LAC-296` — define or edit a scoped vocabulary term
- `T-LAC-297` — set an explicit domain collaboration instruction
- `T-LAC-298` — Inspect assertions, evidence, vocabulary and communication calibration
- `T-LAC-299` — Confirm an assertion
- `T-LAC-300` — Correct and supersede an assertion
- `T-LAC-301` — Reject an assertion
- `T-LAC-302` — Define or edit a scoped shared term with exact committed definition and owner provenance readback
- `T-LAC-303` — Record or edit an explicit domain collaboration instruction with matching owner-authored readback
- `T-LAC-316` — ask through command controller
- `T-LAC-317` — inspect citations
- `T-LAC-318` — inspect readiness
- `T-LAC-319` — request declared notebook mutation
- `T-LAC-320` — Inspect owner-safe research records
- `T-LAC-321` — Submit only an advertised exact owner command
- `T-LAC-322` — Inspect provider evidence, query citations and operations
- `T-LAC-323` — ask through command controller
- `T-LAC-324` — inspect citations
- `T-LAC-325` — inspect readiness
- `T-LAC-326` — request declared notebook mutation
- `T-LAC-327` — Inspect provider evidence, query citations and operations

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-121 — FE-020: Automation, reminders, standing permissions and schedules
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-018, VAN-NX-066, VAN-NX-067, VAN-NX-068.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**Planned test obligations (all NOT_RUN):**
- `T-SURFACE-169` — van.automation.plan: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-186` — van.reminders.manage: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-190` — van.automation.library: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-191` — van.automation.intent: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-LAC-211` — Prepare a bounded typed IR candidate, recover the exact artifact and review its declared deployment limitations
- `T-LAC-212` — Review deterministic supported branches, mappings, preconditions and independent success predicates
- `T-LAC-213` — Request only an admitted immutable artifact with pinned inputs and inspect actual run/step evidence
- `T-LAC-304` — Create
- `T-LAC-305` — Resolve
- `T-LAC-306` — Cancel
- `T-LAC-307` — Refresh
- `T-LAC-308` — Read open reminders
- `T-LAC-309` — Create a reminder with explicit due time
- `T-LAC-310` — Resolve a reminder
- `T-LAC-311` — Cancel a reminder
- `T-LAC-328` — request automation through controller
- `T-LAC-329` — inspect run/evidence
- `T-LAC-330` — disable standing intent through supported owner command
- `T-LAC-331` — Inspect owner-safe automation records
- `T-LAC-332` — Submit only an advertised exact owner command
- `T-LAC-333` — Prepare a bounded typed IR candidate, recover the exact artifact and review its declared deployment limitations
- `T-LAC-334` — Review deterministic supported branches, mappings, preconditions and independent success predicates
- `T-LAC-335` — Request only an admitted immutable artifact with pinned inputs and inspect actual run/step evidence
- `T-LAC-336` — request automation through controller
- `T-LAC-337` — inspect run/evidence
- `T-LAC-338` — disable standing intent through supported owner command
- `T-LAC-339` — Inspect owner-safe automation records
- `T-LAC-340` — Submit only an advertised exact owner command
- `T-LAC-341` — Prepare a bounded typed IR candidate, recover the exact artifact and review its declared deployment limitations
- `T-LAC-342` — Review deterministic supported branches, mappings, preconditions and independent success predicates
- `T-LAC-343` — Request only an admitted immutable artifact with pinned inputs and inspect actual run/step evidence

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-122 — FE-021: Conversation, voice and speaker consent workflows
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-006, VAN-NX-020, VAN-NX-069.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**Planned test obligations (all NOT_RUN):**
- `T-SURFACE-170` — van.settings.speaker-profile: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-179` — van.settings.voice: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-180` — van.voice.turn: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-LAC-214` — Enroll owner voice or replace retained profile after dedicated native strong biometric consent
- `T-LAC-215` — Allow microphone and observe actual current phrase, clip index and sample progress
- `T-LAC-216` — Cancel pending consent or capture without replacing or erasing the existing profile
- `T-LAC-217` — Read current model/profile readiness with exact binding and encrypted-store readback
- `T-LAC-218` — Erase the exact local profile after separate fresh cryptographic consent and verify absence
- `T-LAC-219` — Enroll or replace the exact device-local owner profile using dedicated biometric consent and three actual microphone clips
- `T-LAC-220` — Read local profile/model readiness and permit revocable similarity evidence only for the exact fresh current owner binding
- `T-LAC-221` — Erase precisely the retained encrypted profile after dedicated biometric consent, including when the backend is unreachable
- `T-LAC-249` — recordCorrection
- `T-LAC-250` — pinTerm
- `T-LAC-251` — choose context
- `T-LAC-252` — back
- `T-LAC-253` — Enroll or replace the exact device-local owner profile using dedicated biometric consent and three actual microphone clips
- `T-LAC-254` — Read local profile/model readiness and permit revocable similarity evidence only for the exact fresh current owner binding
- `T-LAC-255` — Erase precisely the retained encrypted profile after dedicated biometric consent, including when the backend is unreachable
- `T-LAC-256` — beginOwnerTurn
- `T-LAC-257` — Cancel unsubmitted speech and reject late recognition results
- `T-LAC-258` — Keep the same owner envelope and acknowledgment boundary on authenticated POST/SSE fallback
- `T-LAC-259` — Use automatically installed generic local acoustic assets and retain honest engine/fallback readiness without phone configuration
- `T-LAC-260` — End the selected local Sherpa recognition turn on actual EnergyVadGate speech/silence or explicit bounded no-speech/maximum-duration state

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-123 — FE-022: Connected, settings, device provisioning, notifications and diagnostics
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003.
**Requirement owners:** VAN-NX-019, VAN-NX-073.

**Exit contract:** Complete all mapped actions and states against qualified backend, source-bound contract and UI tests, no fake data, both-theme golden capture, accessibility and restoration. Final physical certificate issued only in QA.

**Planned test obligations (all NOT_RUN):**
- `T-NX-019` — Physical owner-device/OS tests
- `T-FEATURE-MORE-01` — Connected services: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-MORE-02` — Permissions and device authority: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-FEATURE-MORE-04` — Settings diagnostics appearance: every permitted state/action reaches its backend outcome, denial and recovery; both-theme visual proof.
- `T-SURFACE-112` — VNX-S-MORE-01: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-113` — VNX-S-MORE-02: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-114` — VNX-S-MORE-03: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-115` — VNX-S-MORE-04: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-168` — van.permissions.grant: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-174` — van.connected: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-175` — van.settings: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-176` — van.diagnostics: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-177` — van.onboarding: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-178` — van.provisioning: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-181` — van.settings.notifications: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-183` — van.permissions: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-184` — van.autonomy: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-SURFACE-192` — van.devices.provision: complete screen/context semantics, all source actions, both themes, large text, privacy, stale/error, process death and deep-link restoration.
- `T-LAC-209` — Select a supported action and review bounded exact scope, expiry and maximum uses before A4 approval
- `T-LAC-210` — Inspect the exact stored grant and independent use/remaining-scope readback; revoke it explicitly
- `T-LAC-230` — revoke Google with confirmation
- `T-LAC-231` — retry
- `T-LAC-232` — floating start/stop
- `T-LAC-233` — Android accessibility settings
- `T-LAC-234` — restore subsystem
- `T-LAC-235` — accept asset with biometric
- `T-LAC-236` — debug candidate preview
- `T-LAC-237` — open voice/notifications
- `T-LAC-238` — inspect trace/evidence
- `T-LAC-239` — copy redacted diagnostic receipt
- `T-LAC-240` — retry supported request
- `T-LAC-241` — Inspect owner-safe settings records
- `T-LAC-242` — open Android settings
- `T-LAC-243` — grant microphone
- `T-LAC-244` — continue to Command Centre
- `T-LAC-245` — installer invokes explicit Activity with signed envelope
- `T-LAC-246` — validate signature, expiry and replay
- `T-LAC-247` — pair and bind hardware identity on application scope
- `T-LAC-248` — finish intake Activity immediately
- `T-LAC-261` — toggle quiet
- `T-LAC-262` — start/end +1h
- `T-LAC-263` — normal/priority/mute
- `T-LAC-264` — mute package by name
- `T-LAC-265` — Review and change explicit policy for apps actually observed
- `T-LAC-271` — inspect grant
- `T-LAC-272` — revoke grant
- `T-LAC-273` — inspect authority descriptor and readiness
- `T-LAC-274` — select supported domain and S0..S4 owner ceiling
- `T-LAC-275` — review and biometrically approve exact sealed ceiling change
- `T-LAC-276` — Inspect standing permissions
- `T-LAC-277` — Withdraw this standing permission
- `T-LAC-278` — Inspect earned, owner and effective autonomy ceilings
- `T-LAC-279` — Inspect action gates
- `T-LAC-280` — Inspect automatic capability readiness
- `T-LAC-281` — Choose a supported domain and owner autonomy ceiling, then approve the exact sealed change with biometrics
- `T-LAC-282` — Select a supported action and review bounded exact scope, expiry and maximum uses before A4 approval
- `T-LAC-283` — Inspect the exact stored grant and independent use/remaining-scope readback; revoke it explicitly
- `T-LAC-284` — inspect grant
- `T-LAC-285` — revoke grant
- `T-LAC-286` — inspect authority descriptor and readiness
- `T-LAC-287` — select supported domain and S0..S4 owner ceiling
- `T-LAC-288` — review and biometrically approve exact sealed ceiling change
- `T-LAC-289` — Inspect earned, owner and effective autonomy ceilings
- `T-LAC-290` — Inspect action gates
- `T-LAC-291` — Inspect automatic capability readiness
- `T-LAC-292` — Choose a supported domain and owner autonomy ceiling, then approve the exact sealed change with biometrics
- `T-LAC-344` — apply signed provisioning payload
- `T-LAC-345` — pair/bind
- `T-LAC-346` — grant Android permissions
- `T-LAC-347` — run readiness check
- `T-LAC-348` — re-enroll through supported installer flow
- `T-SURFACE-CX-010` — Actual source availability, evidence age and missing permission; procurement is not silently initiated. Full both-theme, accessibility, source, refusal and navigation tests.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-124 — FE-023: Native model, strategy-development and prediction-research views
**Kind/stage:** FRONTEND / 5. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** BG-001, UX-003, FE-001, FE-002, FE-003, FE-012, FE-013, FE-014.
**Requirement owners:** VAN-CX-020, VAN-HVA-006, VAN-HVA-031, VAN-HVA-032, VAN-ML-REQ-058, VAN-NX-072.

**Exit contract:** All model/research contexts, candidate registry, trial reports, source health and calibrated expectation views consume the complete backend catalogue; no research view can grant execution.

**All deliverables:**
- After BG-001 only, implement the six new context/detail projections within existing navigation, in both locked themes. No new global tab, wallet or trade button.
- Research chain/model surfaces read-only, clear candidate/abstention/evidence and opportunity cost

**Merged obligation VAN-ML-PKT-034:**
- After current BG and parent UX acceptance, implement every mapped projection/control in the locked two-theme design
- Deliver context-specific uncertainty, source age, model/strategy distinction, experiment and review flows
- No dashboards on Home by default, no mobile training or broker authority in charts
- Complete News/Event context, probability/source-age, frozen expectation, research payoff/quote diagnostics and per-use evidence readbacks without enabling live event-contract trading.
- Evidence: Both-theme/state/action parity, accessibility, lifecycle and offline restoration
- Evidence: Model version changes and stale bands never leave an enabled misleading action

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-058-P` — Both themes, offline/restoration, cancellation and accessibility retain all mapped actions.
- `VAN-ML-AT-058-N` — Crowded Home, hidden required capability or UI-coded domain rule fails.
- `T-VAN-CX-020-POS` — Full-scope native dark/light goldens, action reachability and physical S24 cases match the same backend catalogue revision.
- `T-VAN-CX-020-NEG` — Only showcase flows pass, legacy UI leaks into new modules, safety states are hidden for aesthetics, or unknown data looks live: reject final qualification.
- `T-VAN-CX-020-REC` — Reduce motion/material cost gracefully without removing semantics; preserve signed identity and reversible cutover until every required feature is verified.
- `T-SURFACE-CX-002` — Candidate delta, qualifying evaluation and explicit uncertainty; no one-tap live grant hidden in a card. Full both-theme, accessibility, source, refusal and navigation tests.
- `T-SURFACE-CX-003` — A concise run outcome with filterable exact trial lineage, including failures and protected-path proposals. Full both-theme, accessibility, source, refusal and navigation tests.
- `T-SURFACE-CX-006` — Model identity, target, data age, eligibility and abstention; no fake win probability. Full both-theme, accessibility, source, refusal and navigation tests.
- `T-SURFACE-CX-007` — Observed target calibration, coverage and regime limitations with exact evaluator source. Full both-theme, accessibility, source, refusal and navigation tests.
- `T-SURFACE-CX-009` — Valuation, arbitrage and inventory study results in an unmistakable research context; no live order affordance. Full both-theme, accessibility, source, refusal and navigation tests.
- `T-SURFACE-CX-011` — Exact evaluator version, known limitations and invalidated dependent candidates; old results visibly historical. Full both-theme, accessibility, source, refusal and navigation tests.
- `T-CTX-HVA-DISCOVERY` — Show observed/rejected/unknown/research-eligible counts with source age; unfold candidate evidence, no trading CTA. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-CTX-HVA-SECURITY` — Show REJECT/INVESTIGATE/NO_HARD_BLOCK, affected state and concrete reasons. No safe-to-buy badge. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-CTX-HVA-WALLET` — Show raw versus adjusted holdings, time interval, source roles and uncertainty; no ownership certainty from heuristics. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-CTX-HVA-SELLABILITY` — Show buy/sell simulation distinction, quote size/state/expiry and observed versus modeled costs. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-CTX-HVA-COHORT` — Show same-universe arms, distinct cash paths, uncertainty, rejected/censored cases and cost assumptions; never simulated as realized. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-CTX-HVA-JUDGMENT` — Show registered question, supplied evidence, abstention and answer-quality semantics, with no hard-filter or exit override. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-REV113-039` — Research surface shows abstention, data age, failed experiment lineage; no model progress as trade authority

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-125 — QA-001: All-feature/surface/action parity and no-loss reverse coverage
**Kind/stage:** FINAL_QUALIFICATION / 6. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** FE-001, FE-002, FE-003, FE-004, FE-005, FE-006, FE-007, FE-008, FE-009, FE-010, FE-011, FE-012, FE-013, FE-014, FE-015, FE-016, FE-017, FE-018, FE-019, FE-020, FE-021, FE-022, FE-023.
**Requirement owners:** VAN-CX-020, VAN-NX-023, VAN-NX-024, VAN-NX-029, VAN-NX-039, VAN-NX-BF-014.

**Exit contract:** Every applicable acceptance receipt current and exact-source; independently reviewed; actual S24 where required. No feature removed or shortened to make tests pass.

**Planned test obligations (all NOT_RUN):**
- `T-NX-023` — Static lint + route/feature bijection
- `T-NX-039` — Both proven to fail when deliberately broken
- `T-NX-029` — Legacy import fails compilation; banned-word and literal-style lints fail when induced
- `T-BF-014` — Named test rejects a violating plan or evidence set; independently verified per referenced unit.
- `T-VAN-CX-020-POS` — Full-scope native dark/light goldens, action reachability and physical S24 cases match the same backend catalogue revision.
- `T-VAN-CX-020-NEG` — Only showcase flows pass, legacy UI leaks into new modules, safety states are hidden for aesthetics, or unknown data looks live: reject final qualification.
- `T-VAN-CX-020-REC` — Reduce motion/material cost gracefully without removing semantics; preserve signed identity and reversible cutover until every required feature is verified.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-126 — QA-002: Real gateway/provider integration through the new signed app
**Kind/stage:** FINAL_QUALIFICATION / 6. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** FE-001, FE-002, FE-003, FE-004, FE-005, FE-006, FE-007, FE-008, FE-009, FE-010, FE-011, FE-012, FE-013, FE-014, FE-015, FE-016, FE-017, FE-018, FE-019, FE-020, FE-021, FE-022, FE-023.
**Requirement owners:** VAN-NX-024.

**Exit contract:** Every applicable acceptance receipt current and exact-source; independently reviewed; actual S24 where required. No feature removed or shortened to make tests pass.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-127 — QA-003: Cross-domain adversarial security, authority and recovery
**Kind/stage:** FINAL_QUALIFICATION / 6. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** FE-001, FE-002, FE-003, FE-004, FE-005, FE-006, FE-007, FE-008, FE-009, FE-010, FE-011, FE-012, FE-013, FE-014, FE-015, FE-016, FE-017, FE-018, FE-019, FE-020, FE-021, FE-022, FE-023.
**Requirement owners:** VAN-NX-021, VAN-NX-024.

**Exit contract:** Every applicable acceptance receipt current and exact-source; independently reviewed; actual S24 where required. No feature removed or shortened to make tests pass.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-128 — QA-004: Physical S24 performance, thermal, accessibility and both-theme visual acceptance
**Kind/stage:** FINAL_QUALIFICATION / 6. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** FE-001, FE-002, FE-003, FE-004, FE-005, FE-006, FE-007, FE-008, FE-009, FE-010, FE-011, FE-012, FE-013, FE-014, FE-015, FE-016, FE-017, FE-018, FE-019, FE-020, FE-021, FE-022, FE-023.
**Requirement owners:** VAN-CX-020, VAN-NX-022, VAN-NX-024, VAN-NX-025, VAN-NX-060.

**Exit contract:** Every applicable acceptance receipt current and exact-source; independently reviewed; actual S24 where required. No feature removed or shortened to make tests pass.

**All deliverables:**
- Both themes and all material variants S24 owner-reviewed, TalkBack, thermal, frame and battery

**Planned test obligations (all NOT_RUN):**
- `T-NX-025` — Owner on-device decision, immutable APK
- `T-VAN-CX-020-POS` — Full-scope native dark/light goldens, action reachability and physical S24 cases match the same backend catalogue revision.
- `T-VAN-CX-020-NEG` — Only showcase flows pass, legacy UI leaks into new modules, safety states are hidden for aesthetics, or unknown data looks live: reject final qualification.
- `T-VAN-CX-020-REC` — Reduce motion/material cost gracefully without removing semantics; preserve signed identity and reversible cutover until every required feature is verified.
- `T-CTX-HVA-DISCOVERY` — Show observed/rejected/unknown/research-eligible counts with source age; unfold candidate evidence, no trading CTA. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-CTX-HVA-SECURITY` — Show REJECT/INVESTIGATE/NO_HARD_BLOCK, affected state and concrete reasons. No safe-to-buy badge. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-CTX-HVA-WALLET` — Show raw versus adjusted holdings, time interval, source roles and uncertainty; no ownership certainty from heuristics. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-CTX-HVA-SELLABILITY` — Show buy/sell simulation distinction, quote size/state/expiry and observed versus modeled costs. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-CTX-HVA-COHORT` — Show same-universe arms, distinct cash paths, uncertainty, rejected/censored cases and cost assumptions; never simulated as realized. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-CTX-HVA-JUDGMENT` — Show registered question, supplied evidence, abstention and answer-quality semantics, with no hard-filter or exit override. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-REV113-040` — S24 under load: orb and chart smooth enough, no flat theme, 200% text reflows and notification outcomes precise

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-129 — QA-005: Independent Zuul, exact APK and whole-product owner acceptance
**Kind/stage:** FINAL_QUALIFICATION / 6. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** QA-001, QA-002, QA-003, QA-004.
**Requirement owners:** VAN-CX-019, VAN-ML-REQ-059, VAN-NX-024, VAN-NX-025.

**Exit contract:** Every applicable acceptance receipt current and exact-source; independently reviewed; actual S24 where required. No feature removed or shortened to make tests pass.

**All deliverables:**
- Independent no-feature-loss acceptance, original action preservation, receipts not screenshots

**Merged obligation VAN-ML-PKT-035:**
- Run actual signed-app/gateway/provider round trips, physical S24 performance and accessibility acceptance
- Verify original and additive action coverage, telemetry privacy and all recovery cases
- Obtain independent owner acceptance without replacing parent evidence
- Evidence: Physical device evidence cannot be substituted by emulator or headless tests
- Evidence: Removing any inherited or additive action fails coverage

**Planned test obligations (all NOT_RUN):**
- `VAN-ML-AT-059-P` — Physical lifecycle/performance/privacy and independent whole-product acceptance are recorded.
- `VAN-ML-AT-059-N` — Emulator screenshot or backend contract proof offered as S24 acceptance fails.
- `T-VAN-CX-019-POS` — The complete pack rebuilds identically and invalid evidence cannot change readiness.
- `T-VAN-CX-019-NEG` — Edit input and matching local hash, delete a receipt, swap source revision, self-declare signature_valid, or reuse device evidence across builds: block readiness.
- `T-VAN-CX-019-REC` — Record revoked/stale evidence; regenerate affected planning fingerprints and rerun relevant tests without erasing old records.
- `T-CTX-HVA-DISCOVERY` — Show observed/rejected/unknown/research-eligible counts with source age; unfold candidate evidence, no trading CTA. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-CTX-HVA-SECURITY` — Show REJECT/INVESTIGATE/NO_HARD_BLOCK, affected state and concrete reasons. No safe-to-buy badge. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-CTX-HVA-WALLET` — Show raw versus adjusted holdings, time interval, source roles and uncertainty; no ownership certainty from heuristics. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-CTX-HVA-SELLABILITY` — Show buy/sell simulation distinction, quote size/state/expiry and observed versus modeled costs. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-CTX-HVA-COHORT` — Show same-universe arms, distinct cash paths, uncertainty, rejected/censored cases and cost assumptions; never simulated as realized. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-CTX-HVA-JUDGMENT` — Show registered question, supplied evidence, abstention and answer-quality semantics, with no hard-filter or exit override. Exercise both themes, accessible labels, unavailable/reorg states, navigation/restoration and prove no financial action from this read-only context.
- `T-REV113-041` — Independent full app acceptance tests every old action and new owner feature; both themes signed

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-130 — REL-001: Controlled signed release and proven rollback
**Kind/stage:** RELEASE / 7. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** QA-005.
**Requirement owners:** VAN-ML-REQ-060, VAN-NX-054.

**Exit contract:** Owner release authorization; same admitted app identity; staged safe rollout; rollback preserves stores and outstanding intents; no implicit network/provider mutation.

**Merged obligation VAN-ML-PKT-036:**
- Release only exact accepted software under owner-approved rollout and proven rollback
- Promote each economically qualified model/strategy/account/horizon separately using live mandate and prospective evidence
- Retire old presentation only after whole-product parity; retain evidence and qualified baseline fallback
- Evidence: Software release does not auto-enable new trading risk
- Evidence: Rejected/inconclusive models remain available for research, disabled for consequential influence

**Planned test obligations (all NOT_RUN):**
- `T-NX-054` — §19.1 P5–P6; signed APK, tested rollback; retirement only after full parity, with its own negative tests
- `VAN-ML-AT-060-P` — A released app can honestly show a rejected model with zero live influence.
- `VAN-ML-AT-060-N` — Install success enables trading, retrospective gate weakens, or rollback deletes ledger history: fail.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

### VAN-PKT-131 — REL-002: Legacy presentation retirement after full parity
**Kind/stage:** RETIREMENT / 8. **Required completion:** FULL. **Actual implementation state:** NOT_STARTED.
**Entry prerequisites:** REL-001.
**Requirement owners:** VAN-NX-054.

**Exit contract:** Separate owner-approved retirement review; all retained behaviours reached in new app; remove only old presentation, retain functional services and evidence.

**Receipt and rollback:** Record exact source/config/dependency hashes, executed commands, source/provider/device identities, independent result, exception/skip justification, and rollback/recovery proof. Never mark a packet complete by changing this file’s status.

## 6. Owner decisions and signed activation

OQ-21 values are accepted by OD-39 and are not reopened. Their runtime policy binding and activation still require the exact signed mandate. Current owner questions remain in the source record until resolved; unavailable or stale signatures cannot be replaced by code defaults.

| ID | State | Question |
|---|---|---|
| OQ-01 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | Manual per-strategy budget |
| OQ-02 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | ATR stop policy per instrument class |
| OQ-03 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | Manual demo acceptance period |
| OQ-05 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | Exact product/lock signature for formal predevelopment |
| OQ-06 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | Licensed news/calendar provider selection |
| OQ-07 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | Automated missing-stop reattach versus immediate flatten policy |
| OQ-08 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | Promote each news path from shadow |
| OQ-09 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | No direct news risk increase; resolve signed final policy |
| OQ-11 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | Feed bundle and authorized budget |
| OQ-12 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | Event strategies, budget, daily cap and first classes |
| OQ-13 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | Behaviour notice wording and calibration |
| OQ-14 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | Native versus qualified web chart renderer, measured after BG-001; existing spike unqualified and not evidence of completed native UI. |
| OQ-15 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | Owner-approved deletion/archive/retention grace: source record recommends 30 days while older text said 7; no implicit value chosen. |
| OQ-16 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | Portfolio reporting currency |
| OQ-17 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | Simulated replay practice actions scope |
| OQ-18 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | Premature accounts branch disposition |
| OQ-19 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | First admitted funding provider rail and sandbox authority |
| OQ-20 | UNRESOLVED_IN_SOURCE_NO_OWNER_SIGNATURE_INFERRED | Temperament percentages and evidence thresholds for live |
| OQ-21 | VALUES_ACCEPTED_OD39_NOT_RUNTIME_ACTIVATION | 24h cooldown; 0.5 probation; >2 cooldowns/7d escalation; retain stated scopes under OD-38/39 |

## 7. Completion does not imply profitability

A properly functioning strategy/model evaluator may find no qualified live candidate. Retain that truthful result; it is not grounds to thin the required research software or promote a weak strategy. No live financial action, new provider subscription or network change is authorized by this specification.
