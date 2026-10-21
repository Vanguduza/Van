> Rev1.18 mandatory refinement: `contracts/whole_product/ARCHITECTURE_REV118.md`, typed protocol records, complete action/context bindings and `verification/EFFECTIVE_TEST_CONTRACTS_REV118.json` govern execution. All exact runtime registrations and independent receipts must be materialized before BG-001.

> Rev1.12: complete inherited contracts retained; new mandatory domain obligations below. The machine catalogue and plan are active.

# Backend-to-Experience Contract Bundle — Rev 1.11

This bundle is completed in BE-032 and accepted at BG-001. It is not a server-generated UI framework: the backend reports capabilities and state; a separately designed native frontend controls composition under locked design authority.

## Stable context identity

Every context carries project/owner scope, selected account ID (never inferred from aggregate ALL), canonical instrument and venue, source epoch/revision, event/received time, validity/freshness, permission revision and an explicit authoritative outcome. Use opaque IDs, exact quantities, currency and unit type. Display-rounded numbers never re-enter risk calculations.

## Required per-capability contract

`capability_id`, `owner_requirement_refs`, `domain_owner`, `purpose`, `allowed_contexts`, `read_operations`, `effect_operations`, `inputs`, `outputs`, `validation`, `authorization`, `state_machine_ref`, `persistence`, `idempotency_scope`, `receipt_lookup`, `recovery`, `rate_limit`, `source_age_rules`, `provider_support`, `version`, `deprecation`, `tests`, `source_binding`, `runtime_proof_refs`.

Every effect operation declares preview, argument digest, exact owner/device proof where required, eligibility read, domain execution, idempotency/outbox and reconciliation lookup. Neither a model nor renderer can call raw broker or infrastructure commands.

## Required per-action presentation data

`action_id`, `capability_id`, `subject_ref`, `context_digest`, `classification NAVIGATE|READ|DRAFT|OWNER_EFFECT`, `eligibility AVAILABLE|REVIEW_REQUIRED|STALE|NOT_SUPPORTED|UNKNOWN`, reason code and short text, exact proposed effect, source time, visible units, semantic warning, expected state transitions and cancellation semantics. The app cannot enable a financial action simply because its control was rendered.

The server supplies stable semantic keys and verified facts, not HTML/JavaScript that can mint grants or a compulsory grid of every internal field. UI text is generated from approved templates or checked facts. Security metadata, hashes and low-level request bodies stay in expandable evidence surfaces, not Home.

## Snapshot and event contract

Use `source_id`, `stream_id`, `epoch`, `sequence`, `event_id`, `occurred_at`, `received_at`, `snapshot_revision`, `subject_id`, `payload_schema`, `freshness`, `correlation_id` and `authority_effect`. A reconnect obtains a versioned snapshot and subsequent ordered events. Duplicates do not animate again or submit again. A cursor gap or incomparable epoch does not merge old and new truth.

Trading and work domains keep independent revisions. A global badge cannot claim all sources LIVE because market prices are fresh while positions or task ownership are stale. Tick coalescing may reduce redraw frequency, never drop meaningful order, approval or ledger transitions.

## Native versus backend ownership

| Concern | Complete in backend phase | Complete after BG-001 |
|---|---|---|
| Chart | Instrument/bar/provenance APIs; canonical settings/drawings/indicator models; bridge schema; research intake; replay namespace | Renderer, crosshair/gesture/surface lifecycle, native/web host, local viewport/store and accessible controls |
| Orb | Orthogonal presence sources, severity reducer policy, freshness, canonical attention/briefing projections | Metallic render, motion, hit targets, Home composition, compact popup and accessible captions |
| Tasks | Authoritative graph, assignments, stage progress, handoff/lease events and actions | Spatial layout/gestures, node selection, mini-map, list alternative and tactile hierarchy |
| Accounts/funds | Full identity/auth/quote/approval/operation/reconciliation/capability services | Native forms, verified provider handoff chrome, receipt/detail/protection UI |
| Voice/device | Server protocol, policy, stored consent, existing qualified device adapter interface and test vectors | New Android mic/overlay/notification/provisioning UX and exact S24 permission/lifecycle proof |
| Muse/browser | Real scoped job/session/approval broker with provider readback | Native conversation/control panel and viewport touch interaction |

## Headless consumer acceptance before frontend

For every action, exercise the genuine registered gateway contract from an isolated authorized test client. Validate exact scope, messages, real dependent services, positive/refusal/unknown outcomes and readback. Unit tests and fake endpoints remain development aids, never the sole integration evidence. Headless tests must not skip authentication because the mobile signing UI is not built; use an already qualified signing/test authority whose scope excludes live effects where not approved.

Include complete contract data for every feature, not just five representative flows. Representative flows are risk-discovery probes in BQ; they cannot certify untested sibling capabilities.

## Consolidated model/research/execution extensions

Every target screen resolves against the same completed BE-032 catalogue. The additional model registry, calibrated expectations, candidate trial history, source/evaluator qualification, risk-policy activation and pending-order recovery contexts are declared in ALL_SURFACE_CONTRACTS.json. Model scores, event-market probabilities and DSR/PBO statistics have different semantics and labels; none can directly create a trade. Global hard risk covers all origins, while discretionary and autonomous cooldown scopes are displayed distinctly. Order submission, venue working, fill, protection confirmation and terminal cancellation/expiry remain different states.


## 30. Integrated high-value trading intelligence and read-only crypto research

### 30.1 Current owner direction, revision and scope

The owner instruction **“Proceed according to your recommendations”**, following the comparative review of the uploaded High-Value Trading Adoptions Rev1.0, authorizes preparation and integration of the reviewed specification changes. This revision records that scope direction. It does not manufacture an owner cryptographic signature, independent F15/BG certificate, model-promotion decision or financial mandate. The current deliverable is an owner-directed integrated specification candidate; application implementation starts only through the existing admitted packet and F15 process.

The uploaded proposal is retained unchanged as provenance. Its corrected technical companion is `research/HIGH_VALUE_TRADING_INTELLIGENCE_INTEGRATED_REV1_1.md`. It has **no independent executable schedule**. The canonical specification is this master plus its machine contracts; `plan/DEVELOPMENT_PLAN.json` is the sole schedule. Source-qualified unit IDs remain stable; the generated `VAN-PKT-*` sequence is revision-qualified and its complete Rev1.11-to-Rev1.12 mapping is included. A cached old packet number must never silently resolve to a different unit.

All 205 inherited requirements—including all 90 forecasting requirements and 20 corrective contracts—remain intact. Required Qlib, LightGBM, FreqAI-inspired mechanisms, NeuralForecast models and challenger integrations, calibration, artifact handling and prediction-market laboratories are **engineering obligations**, not optional software contingent on an early profitable result. Economic admission of their outputs remains conditional on evidence. A correct integration can report `NO_QUALIFIED_MODEL`, `REJECTED` or `INCONCLUSIVE`; a missing integration cannot use those labels to claim engineering completion.

Netcup/Oracle remain the intended compute environment. This revision adds no new data-licence purchase, paid subscription, venue account registration, funded wallet, transaction signing, trading venue or capital increase. Existing permitted access may be used; code, schemas, fixtures and unrelated dependency-ready work proceed without procurement. An unavailable required provider is recorded precisely and cannot be replaced by a synthetic success or waived to open global BG-001. Hosting location, source permissions and operator/account eligibility remain separate recorded properties.

### 30.2 Source reconciliation that must precede implementation

The preceding review inventoried all 66 advertised branch heads at 63 distinct commits, with 4,634 union paths. Its supported-text pass scanned 3,680 unique UTF-8 blobs and excluded 26 size/encoding candidates. It was a complete head-tree inventory and bounded content/import scan, **not** universal semantic qualification. A current Global DIAL read refreshed the advertised heads and found no changes. Both observations are identified by exact request and artifact references in the source register; implementation must refresh them again before any source merge.

The operative source conclusions are:

* Keep PR101/`a39f241b…` resting-order, ledger, rounding and recoverable-lockout improvements, but close the already specified execution/simulator defects before using economic results for admission. A positive distant-limit control demonstrates that pending support exists; worse-than-limit fills remain a separate defect.
* Reconcile canon/PR93 shared Jev consumers, typed learning evidence and temperament changes with the PR92 and cognitive-fabric contribution sets at the **function and caller** level. Account service and coordinator had five distinct variants in the reviewed heads. Neither largest commit count nor newest branch name establishes a complete implementation.
* Reuse the shared `dial-jev` service and existing gateway/cognition clients. Existing infrastructure is not evidence that a new token-vetting question set has predictive value.
* Existing `AllocatorV1` is a deterministic quality/edge-floor extension that continues to exclude uncalibrated confidence. It is not an already implemented calibrated-model policy. Any further ranking policy needs a separately versioned contract and tests under that same owner.
* No production imports of the named forecast libraries, implementing prediction-market adapters or concrete token-security analyzers were established in the scanned source. This is a dated tracked-source observation, not proof about uncommitted work or external services.

BE-001 must merge only independently reviewed compatible changes and prove retained callers, authority checks, state migrations and negative paths. The documentation update does not merge these branches or certify them. The existing main and protected working sources remain unchanged by this pack.

### 30.3 One owner for each mechanism

The eight new logical backend capabilities extend existing services rather than mandate eight new microservices. The service catalogue identifies producer → durable state → consumer and the exact governing unit for each.

| Mechanism | Existing owner to extend | Forbidden substitute |
|---|---|---|
| Identity, quotes, source availability and state anchors | Market-data, acquisition and event/provenance services | A parallel ungoverned data lake |
| Features and targets | Shared definitions, point-in-time datasets, Feast parity and TargetSpec | Crypto-only labels that evade chronology |
| Research/training | Existing Qlib/LightGBM/NeuralForecast/Optuna workflow | A second training scheduler or registry |
| Calibration and artifact lifecycle | Existing calibration boundary and MLflow integration | A new conflicting confidence service |
| Candidate selection | Existing opportunity arbiter and versioned allocator | Agent-owned sizing or capital reservations |
| Risk and order submission | Existing RiskAuthority, account coordinator and ExecutionRouter | New wallet, exchange sender or position book |
| Judgment | Shared `dial-jev` through registered VAN consumers | Standalone Jev trading service or credential plane |
| Evaluation | Qualified simulator, experiment ledger and account-wide replay | Scaled actual-R used for different hypothetical trades |
| Owner interaction | Existing gateway/capability catalogue and post-BG native surfaces | Early dashboard or low-trust order buttons |

Broad “T2” terminology in the upload does not move every forecast into a remote slow call. Heavy training, public RPC/indexers, source extraction and remote judgments remain asynchronous outside T0. The bounded local ForecastService produces prepared results with freshness and applicability controls. T0 neither imports the research dependency stack nor synchronously calls an indexer, remote judge or artifact registry.

### 30.4 Evidence namespaces and maturity dimensions

The upload's E1–E5 publication-quality scale and the parent E0–E6 implementation-evidence scale are different namespaces. Preserve their provenance, but never merge them into an ambiguous `evidence_grade` value.

| Source classification | Meaning | What it does not prove |
|---|---|---|
| `RS1_PRIMARY_TRANSACTIONAL` | Primary or transactionally verifiable source | Correct VAN implementation |
| `RS2_PUBLISHED_REPRODUCIBLE` | Published technical result or reproducible study | VAN-specific profit |
| `RS3_VENDOR_CAPABILITY` | Vendor-supported interface/capability | Software test, deployment or alpha |
| `RS4_SELF_REPORTED` | Self-reported performance | Independent financial verification |
| `RS5_UNVERIFIED_CREATOR` | Unverified creator/video claim | Android certification or trading edge |
| `SYNTHETIC_FIXTURE` | Authored test data | Real provider observation |

`implementation_evidence_level` retains the parent's E0 OWNER_REFERENCE through E6 OWNER_VISUALLY_ACCEPTED values, plus `SPEC_ONLY` where no implementation proof exists. Legacy grade conversion requires the original source schema. Ambiguous historical rows remain unresolved. A schema, hash or registry alias by itself grants no authority.

Record engineering state, source integration/access state, economic-use qualification and live authorization separately. A defensive veto can qualify on independently measured defensive value without positive alpha, but must also account for false rejection and must never block a mandatory protective exit. Offline fixture tests do not qualify a live source, and an inaccessible source does not mean the rest of the code cannot be completed.

### 30.5 Canonical discovery identity and the complete cohort

Canonical asset identity is `(chain_namespace, network_id, canonical_token_address)`, produced by a chain-specific validated codec and linked to the raw representation. Display names and tickers are never keys. Pool and router identities are independent and chain-qualified. A token can have multiple pools; migration changes the pool relationship and liquidity history, not the token's identity.

Do not use one universal lowercase/string-normalization function. The chain adapter must validate its address encoding and decoded identity, preserve versioned normalization rules and reject malformed or unsupported identities. Tests include duplicate tickers, chain/network collisions, multiple pools and migrations.

Persist discovery **before** the survivor funnel. Every source observation has raw hash, source/cursor identity, availability time and block/slot anchor where applicable. Retain investigated, rejected, unknown, expired, delisted, unreachable and migrated candidates. Queues are bounded and source-quota-aware; negative results bind their reason, source/rule/state version and expiry. A meaningful state or rule change can invalidate a rejection before its timer expires. Restart restores the queue from durable state without duplicate jobs.

The funnel preserves D0–D6 from the donor concept: identity/discovery, inexpensive numerical checks, contract capabilities, attribution, temporal flow, optional typed context, and executable economics. Those are logical stages under existing owners, not seven new trading agents. Exactly one survivor still receives every remaining hard gate, `NO_TRADE` remains valid, strings such as `"no"` are explicitly normalized, and creator example thresholds never become VAN defaults without measured false-positive/false-negative evidence.

### 30.6 Discrete chain-security analyzers

**Solana capability:** distinguish supported SPL Token and Token-2022 observations. Inspect mint/freeze authority and applicable transfer fees, hooks, delegates and other supported extensions. Bind results to the program/parser revision, slot, source and finality policy. An unrecognized extension or missing state is UNKNOWN, not benign. Technical pool/vault/burn roles must be evidenced before they affect concentration.

**EVM capability:** bind code, proxy and implementation identity to the chain and state observed. Inspect applicable upgrade/admin powers, transfer limits/taxes, mint/blacklist and liquidity-removal controls through supported read-only evidence. A verified proxy shell does not establish the behavior of a changed implementation. Unverified code increases uncertainty; it does not establish fraud or safety.

Both analyzers produce factual `ChainSecurityFinding` records and uncertainty-bearing features. Their verdict vocabulary is `REJECT`, `INVESTIGATE`, `NO_HARD_BLOCK`; **NO_HARD_BLOCK is not SAFE_TO_BUY**. Findings state evidence coverage, unsupported checks, observation time and expiry. A finding can inform research or a separately qualified restrictive consumer, but cannot grant a route, sign a transaction or overrule risk-reducing operations.

### 30.7 Sellability and executable economics

Buy and sell checks are independent. Where supported, run read-only simulations against the stated chain/router/contract/pool state at the declared quantity, with caller assumptions, gas/fee conventions and finality recorded. Success proves only the stated simulation result at that state. It does not promise that a later sell will execute, survive changed taxes or obtain the same liquidity.

Separate three records:

1. **ExecutableQuoteFacts:** observed side, quantity, currency, executable quoted cash/depth, provider/route and state anchor, availability/expiry and fee-inclusion components. No projected exit cash or fill probability is permitted in this facts record.
2. **ExecutionEconomicsForecast:** modeled exit proceeds, execution/failure costs or fill probabilities, with explicit target, horizon, artifact/transform/calibration lineage and applicability. A probability requires its precise observable event; an amount forecast does not masquerade as a probability.
3. **NetEdgeAssessment:** a derived economic calculation referencing the exact facts and forecast versions, uncertainty and cost convention. It identifies included costs to prevent double-counting.

For quantity `q` and horizon `h`, a cash-consistent research estimate is expected executable exit proceeds minus entry cash and any costs not already included. Compare it with the strategy's preregistered materiality/uncertainty floor and independent risk eligibility. Depth, slippage, transfer costs, gas and failure costs need not scale linearly with size. A small quote cannot be extrapolated into free liquidity at a larger quantity.

The existing evaluator repairs remain upstream: limit-price semantics, effective expiry propagation, pending-fill protection, canonical order state, terminal liquidation cash, commissions/financing, intrabar ambiguity and full-account risk competition. Do not call the new economics qualified merely because a cost estimate is used to screen candidates. The simulated cash ledger must actually charge the appropriate costs. All DEX trade outcomes remain hypothetical here; there is no new signing wallet or execution client.

### 30.8 Temporal wallets, attribution and reorganization

Persist comparable anchored snapshots of holdings, supply, transfers, liquidity and role labels. Compute changes only between observations with compatible coverage. A single snapshot cannot establish growth or accumulation. A routed transfer is not automatically a genuine purchase; common funding is not conclusive common ownership.

Retain raw concentration and separately derived role-adjusted concentration with every exclusion explained. Proven technical pool/vault/router/burn accounts can be treated appropriately without deleting the raw history. Attribution is uncertainty-bearing. Heuristic clusters must retain assumptions, evidence and revision; legitimate airdrops/OTC/internal transfers must appear in negative controls.

Young assets need explicit lookback coverage. Missing preceding windows remain unknown instead of receiving a fabricated denominator. Deduplication uses the chain's transaction/log/instruction identity under the relevant adapter. Disappearing pools, source lag and unobservable exits are retained as censoring/missingness, not zero loss or an excuse to delete a cohort row.

Maintain transitive provenance from source/state → facts → features → forecasts → study/consumer. Reorganizations, corrected observations, changed authority/implementation and pool migrations produce versioned invalidation batches. Every affected cached result loses eligibility before reuse. Revalidation is idempotent and checkpointed; a crash must not leave a stale descendant ready. Historical observations and decisions remain immutable, while new analytical versions record the correction. Finality policy itself is versioned and cannot silently upgrade an observation.

### 30.9 Matched opportunities and account-level evaluation

The existing cognitive shadow book remains a **same-trade, size-only attribution view** under its declared proportional assumptions. `actual_R × multiplier` is not an independently observed hypothetical trade, a different path's own-risk R, or a faithful treatment of nonlinear costs. Preserve that useful limited view; do not stretch its claims.

Use the existing experiment and account-replay services for changed discovery, selection, timing, route or exit policy. Seal the decision opportunities, universe, feature/quote versions, both arm decisions, unresolved rows and simulator assumptions before outcomes mature. Each arm maintains its own account state, pending orders, reservations, cash, risk and later opportunity eligibility. Skipping a trade changes future opportunity cost. Summing unconstrained single-instrument simulations does not produce a feasible portfolio.

Tag hypothetical outcomes `SIMULATED_COUNTERFACTUAL`. Forward paper results and actual venue outcomes retain their own evidence classes. Paired replay estimates **incremental policy performance under its stated assumptions**; it does not identify a causal effect simply because two policies were simulated. Use prespecified event/time/asset-cluster-aware resampling, exposure-matched and simple-calendar controls, all losing trials and sequential-testing rules. Report net cash/R, coverage, abstention, false rejection, unresolved outcomes, risk, drawdown, costs and operational overhead.

The upload's proposed positive lower-95%-confidence-bound rule becomes a candidate setting within the **one** versioned validation policy, not another admission service. Materiality, sample adequacy, clustering, multiplicity and stopping rules must be locked before results. Preserve existing DSR/PBO and other applicable gates; do not overwrite them with a convenient scalar. Inadequate evidence produces INCONCLUSIVE.

### 30.10 Targets, Qlib/LightGBM and NeuralForecast integration

Use the already required model adapters rather than separate crypto-only models by default. New features and targets flow through the common point-in-time dataset, feature/target specification, Qlib study, LightGBM/NeuralForecast integration, Optuna trial record, calibration and MLflow artifact lineage.

Terminal return, after-cost strategy result, maximum adverse excursion, stop touch and fill probability are distinct targets. They differ in path dependence, horizon, label maturity and censoring. A lower terminal-return quantile cannot be relabelled a calibrated probability of hitting a protective stop. Model output probabilities, ranking scores, attribution confidence and Jev answer quality are likewise not interchangeable.

Maintain the full NeuralForecast engineering scope from §28, including direct model integration, retained temporal scenarios, contextual challengers and secure persistence. Evaluate added wallet/security/liquidity features first against the appropriate simple and tabular baselines. Economic rejection of a domain experiment does not remove the underlying model capability from the required programme.

Preserve prediction-market contract semantics, grouped calibration, asset-response models, execution replay, arbitrage and market-making research. A07's probability-context ablation is an experiment within that programme, not a replacement for it. Cross-venue agreement is not independent corroboration; shared sources across models cannot be counted as multiple independent signals.

### 30.11 Jev question sets and qualified ranking

Use the actual shared `dial-jev` consumer and existing exact evidence resolver. Registered question sets must be narrow and falsifiable—for example, whether two supplied identifiers conflict, whether a documented claim is supported, or whether the provided observations are temporally comparable. Include unknown/unanswered, question-set version, snapshot/input hash, provider/model identity, deadline, cost and expiry. No private credentials or prompt-supplied broker instructions enter the model context.

Run rule/no-LLM, Jev and any approved challenger on the same sealed case set. Measure correct/incorrect/unknown answers, false rejection, genuinely observable label calibration, cost and incremental policy value. Answer quality does not imply a profitable-trade probability. A new domain question set needs its own evaluation even when transport and existing attention/browser questions are already implemented.

The current AllocatorV1 continues unchanged as the inherited baseline. A model-informed ranking amendment must have a new explicit policy/version and qualified input contract at the **same** owner. It may select among otherwise eligible candidates; it does not size, widen risk, reserve cash independently or turn a high model score into a second mandate. Revocation restores the qualified baseline while preserving pending-order reservations.

### 30.12 Serving, recovery and determinism

Prepared forecasts/judgments carry exact state, transform, target, model, calibration, source availability and expiry. Incompatible, non-finite, stale, revoked or reorganized inputs cannot become current evidence. The positive valid path must be exercised as well as all refusal paths; a permanently unbound producer is not an implemented integration.

Keep four different reproducibility claims distinct: exact canonical replay of persisted evidence; repeatable fixed-seed inference in a pinned environment; declared cross-device numeric tolerance; and stochastic retraining reproducibility assessed statistically. No promise of byte-identical neural/GPU training follows merely from a frozen dataset. Record actual environment, configuration and tolerance rather than weakening deterministic risk-decision replay.

Outages, indexer lag, quota exhaustion, delayed results and interrupted revalidation must have bounded behavior and a truthful read model. Research unavailability cannot disable mandatory protective exits. Rolling back a model or data adapter does not resurrect revoked calibration or incompatible state. Retention and provider-use rules are enforced independently from audit immutability claims; record policy-governed deletions and reference invalidation where retention requires it.

### 30.13 Headless operations and post-BG owner surfaces

BE-044 completes the real producer/store/consumer joins, and BE-032/033 include their catalogue, isolation, capacity, observability, recovery and retention behavior. API/read-model construction is backend work. **No new native UI is authorized before the sole global BG-001**, even if one feed is already healthy.

The six new context obligations are progressive-disclosure views within the existing Trading/Research/Analyst/Work/Settings navigation, not six mandatory global pages: discovery funnel; state-bound security finding; wallet/flow evidence; sellability and economics; matched-cohort report; and typed judgment trace. Each retains native accessibility, offline/stale/unknown states, dark/light tactile design and evidence drill-down. They introduce no order, signing or funding action.

Counts reconcile total observed, rejected by reason, investigated, eligible, economically assessed, paper-simulated and actually filled **only where that evidence exists**. Research-only crypto can correctly show zero actual fills. Fixture, delayed, simulated, shadow and observed classes are visible from provenance, not from the appearance of a chart. No simplified green “safe token” badge is permitted.

### 30.14 Dependency integration and complete acceptance

New BE-037–044 are logical capabilities in the existing plan. Existing BE-001/003/010/013/021/024/032/033/035 and forecast dataset, target, calibration, serving and evaluation units receive additive contracts rather than duplicate siblings. BQ-008 verifies chain/source/finality end-to-end behavior; BQ-009 verifies full-cohort economics, evidence semantics, judgment/ranking and authority separation. Both feed BQ-006 and the sole global BG-001. All old units and their original exit obligations remain.

The added requirements and their positive, adverse and recovery contracts are machine-readable. Every requirement maps to existing/new unit owners, a producer and durable state, downstream consumer, planned evidence and eventual owner context where appropriate. All application acceptance records remain NOT_RUN in this documentation delivery; document mutations and synthetic schema checks cannot change those states.

Legacy M0–M9 and G0–G6 are explanatory crosswalk aliases. Their old ordering, reduced optional scope and M8 single-feed entry condition have no authority. The application runner must bind `(plan_revision, scope_digest, unit_id)`; old `VAN-PKT-*` numbers are resolved only through the revision-qualified crosswalk, never by positional coincidence.

### 30.15 No-loss and correction closure

Preserve all original requirement text, existing corrective contracts, 18 Product Truth atoms, 93 earlier features, 171 source atoms, 349 historical owner actions and the locked visual bytes. Original source/test documents remain lineage. Changed plan dependencies, prepared locks and source mappings are explicit revision deltas, not forged updates to signed inputs. The package includes a byte-preservation report and old-to-new schedule map.

The review's R01–R12 concerns are closed **at the specification level** by linked amendments, schemas, owner mappings and tests. The associated application defects and integrations remain open until actual implementation and appropriate receipts. Previously reproduced paper-limit/expiry counterexamples are retained as evidence and regression requirements; this revision does not claim to have fixed their code.

### 30.16 Implementation entry and exclusions

The next executable programme remains PRE-001 source/feature reconciliation, PRE-002 independent semantic/contract review, then PRE-003 F15 with the required exact owner trust binding. Updating the document and passing its checks is not a substitute for those exits. Once admitted, dependency-ready backend source consolidation and implementation proceeds on the authorized DIAL VM topology; no physical desktop or silent alternative runtime is part of the plan.

Existing Zuul admission and typed Global DIAL deployment remain the routes. No new GitHub Actions deployment authority, hosted tunnel, IAM, firewall, credential, paid account or broad infrastructure repair is included. Release and model/strategy live admission remain separate. The desired result is a fully implemented, honestly evaluated capability—not an obligation to claim profitable forecasting or fabricate unavailable integration evidence.
