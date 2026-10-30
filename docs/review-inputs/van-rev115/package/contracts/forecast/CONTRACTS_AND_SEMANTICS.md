# Typed Contracts and Semantic Validation Duties

Revision 1.0. These are proposed backend interchange contracts. They are not already registered VAN routes, production validators or independent approval records.

## 1. Validation order

The production implementation must validate bounded byte size and parse only the admitted format; verify schema/version; resolve scope/permission; validate referenced immutable artifacts; check all semantic identities/clocks/domains; verify trusted independent receipts where required; evaluate current policy/epoch; then expose a read-only record or execute the permitted existing-domain action. A hash or valid JSON object never skips any of those steps.

The included JSON schemas are strict about named fields and reject additional properties. They deliberately do not accept order quantities, broker credentials, stop-widening directives or arbitrary executable code. The actual existing risk/execution contracts remain outside their authority. An unknown schema version returns a typed incompatibility rather than a best-effort guess.

## 2. Record-by-record contract

| Record | Author / owner | Required consumer | Principal semantic checks |
|---|---|---|---|
| DatasetManifest | VAN data/research snapshot builder | All research providers | Every source entitlement valid for the requested use; actual availability no later than cutoff; canonical cohort/universe/calendar identity; bytes and row IDs match; corrected research distinct from as-observed |
| TargetSpec | Admitted research target registry | Label builder, model adapter, evaluator, arbiter | Horizon, units, price/payoff, cost basis, censoring, domain and label-maturity rules are coherent; feature computation cannot call target-only future operations |
| FeatureManifest | Existing feature registry/transform producer | Qlib/NF bridge and inference | Ordered types/units match; fit window is fold-local; feature roles have appropriate availability; row mask aligns X/y/weights; categorical vocabulary and source dependency versions are exact |
| TrainingJobSpec | Existing study/workflow owner | Isolated authorized research worker | Scope/authorization/resource admissions current; all snapshots immutable; provider/model capabilities match; budget nonzero and bounded; no automatic live promotion |
| ModelArtifactManifest | Research export worker | Safe artifact loader and independent reviewer | Native serialization is supported; exact source/environment/feature/target/transform identities; actual file bytes/dimensions verified; export/load parity; no broker keys or arbitrary code |
| ForecastPacket | Bounded ForecastService | Existing arbiter and owner projections | All temporal and identity relationships valid; each output matches target units/capability; calibration and sample interpretation truthful; live use permission evaluated externally |
| QualificationRecord | Independent evaluation pipeline, with trusted receipt produced separately | Existing model/strategy admission | Actual report evidence, appropriate metrics, sample adequacy, trial census and original scope verified; user-authored result strings never substitute for trusted issuer proof |
| DeploymentBinding | Existing approved-use control | ForecastService and decision snapshot reader | Exact artifact and feature/calibration/fusion/strategy/account compatibility; atomic epoch; current independent evidence and owner authority; no implicit alias resolution |

Opaque IDs and content hashes reference actual objects. The production resolver must reject a well-formed reference that does not exist, has changed, is out of scope or is revoked. Metadata is not proof of content.

## 3. Forecast semantics

`status=READY` indicates a structurally available forecast within a declared use scope. It does not indicate a permitted order or certified economic value. `scope.environment=FIXTURE` identifies synthetic examples and must never be admitted into research-market evidence, shadow economic results or live bindings.

For a ready forecast, at least one supported output is present. For an abstention, `payload=null` and at least one reason code is required. A missing output is not zero. Numeric outputs must be finite; ordinary JSON parsers may accept nonstandard NaN/Infinity, so this requires an explicit check in addition to schema validation.

Temporal requirements include:

- `train_label_available_cutoff <= input_cutoff <= generated_at < expires_at`.
- `max_input_available_at <= input_cutoff`; static/future calendar inputs obey their source-vintage availability, not their scheduled event times.
- The actual current time, source time and model/calibration age are checked against independent per-scope policies at consumption. A syntactically future expiry cannot override revoked evidence or bad market data.
- Model training and calibration windows do not overlap prohibited evaluation periods. This cannot be established from ForecastPacket alone; validate the referenced study/artifact manifests.

Quantile alpha levels are unique, increasing and inside(0,1). Values must respect the declared monotonicity policy; any correction is a versioned transform with evaluation. Raw event probability and calibrated event probability have different fields and both require the named event semantics. A calibrated probability additionally needs valid calibration artifact/evidence and scope-appropriate calibration state. An ordinal rank score is not transformed into a probability by changing its label.

Scenarios require actual individually retained samples, count, sampler policy and artifact identity. A within-series trajectory model may say `TEMPORAL_WITHIN_SERIES`; it may not say `JOINT_COHORT` without explicitly validated joint generation/dependence evidence. No scenario artifact means no positive scenario count. Do not infer barrier probabilities from terminal quantiles or sum quantiles to claim aggregate portfolio risk.

## 4. Additional production records to implement

The eight included schemas cover the principal interchange. The following records are also mandatory behavior described in the master and packet contracts; their repository schemas must be completed during packet002 and code qualification. Their absence from this portable schema sample is not permission to omit them.

**FoldPlan:** dataset/target identity, chronological fold IDs, train/validation/calibration/test boundaries, label information intervals, purge/embargo procedure and units, historical-context policy, refit schedule, peer/cohort synchronization, final holdout access log, processor fitting boundaries and frozen study protocol digest.

**CalibrationArtifact:** method/configuration, exact model/feature/target/transform bindings, cohort/horizon, residual/outcome availability cutoff, alpha/event definition, score transformation, fitted parameters/native safe bytes, nominal versus empirical coverage/reliability, dependence/sample adequacy and expiry/revocation. A refit requires renewed binding.

**OutcomeObservation:** original immutable forecast ID, actual event/decision/intent/order/fill references where present, actual/counterfactual/practice classification, target maturity, source times, currency/unit/cost treatment, censoring/missing status, revisions and entitlement/consent lineage. Unexecuted opportunities do not acquire real fill facts.

**ModelUseProposal / IndependentEdgeEvidence:** exact model, calibration, fusion, strategy, instrument/account scope, horizon, use policy, economic study, prospective observations, risk/noninterference evidence and proposed expiry. The existing trusted admission path verifies actual evidence and creates permission separately.

**Feature/ProviderCapability:** model-specific accepted target families, variable roles, missing-data/grid policies, supported output/serialization/explanation types, maximum sizes/compute and real compatibility test references. An adapter must fail early for unsupported combinations, not silently drop a feature.

**JobAttempt / ResourceAdmission / ArtifactPublication:** existing durable scheduler/lease contracts extended with snapshot digests, resource limits, attempt and supersession IDs, checkpoint, state, output size, actual environment, cancellation/lost-response reconciliation and publication idempotency.

**ForecastActionContract:** capability, actual gateway route, owner/context scope, input/output versions, availability, permission revision, canonical intent digest for effects, replay/idempotency and independent outcome lookup, error catalogue, cancellation, retention and UI projection semantics.

These records must reuse existing VAN schema owners where equivalent structures already exist. They are not invitations to add duplicate stores or a parallel grant format.

## 5. Model-provider protocol

Implement equivalent typed methods in the admitted repository language/API:

```text
describe_capabilities() -> ProviderCapability
validate_spec(TrainingJobSpec, DatasetManifest, TargetSpec, FoldPlan) -> ValidationReport
fit(ValidatedJob, bounded_cancellation_context) -> CandidateModelArtifact
predict(AdmittedArtifact, FeatureSnapshot, ForecastRequest) -> ForecastPacket
export(CandidateModelArtifact) -> SafeArtifactManifest
load(VerifiedLocalArtifact, ExpectedCompatibility) -> LoadedReadOnlyModel
explain(LoadedReadOnlyModel, ExactForecastInput) -> ExplanationArtifact | Unsupported
```

The worker receives a resolved trusted plugin ID, not a Python import string from arbitrary user input. Qlib-compatible regression/binary tasks can delegate to its standard LightGBM wrapper. Quantile/ranking adapters call the actual supported LightGBM objective with correct grouping/labels and log into the shared recorder. NeuralForecast plugins use native APIs behind the same external contracts; do not force unsupported inputs or return types merely to imitate the stock Qlib wrapper.

All scientific code must retain the row/time/target identity. A provider that returns an array without the original prediction index cannot be safely joined back by assumed row position.

## 6. Fixture examples and checker boundary

`examples/ForecastPacket.fixture.ready.json` and `.abstained.json` contain synthetic data with explicit FIXTURE identity. They are schema examples only; the numeric bands are not a financial forecast. They intentionally have no trusted model artifact, actual calibration or live promotion.

The document checker exercises selected shape and local cross-field semantics against these fixtures. It does not resolve real artifacts, verify cryptographic signatures, query a live registry, fit any model or test any VAN gateway. The acceptance contracts remain NOT_RUN. The production semantic validators and all additional record schemas remain implementation work under the mandatory packets.


## Revision 1.1 prediction-market contracts

Ten additional principal schemas and synthetic examples are provided. All carry authority NONE. Research can suggest quantities for valuation or a fraction for analysis, but these are not authoritative `TradeIntent` sizing fields. No record or fixture enables an event order sender.

| Schema | Required binding/interpretation |
|---|---|
| PredictionMarketSourceProfile | Host and actual region separate from operator/account eligibility and allowed source uses; procurement false is not permission true |
| PredictionMarketContract | Exact event, proposition, comparator/range, units, official vintage, rounding, close/resolution/void/dispute and payout |
| PredictionMarketObservation | Proper clocks, market/rules digest, sequence state, exact YES/NO bid ladders and opposite-side asks |
| EventProbabilitySnapshot | Event and estimator meaning, raw probabilities, optional independently calibrated probabilities, bin/threshold coherence, tails, source relation and frozen cutoff |
| EventAssetResponse | Separate asset/target/horizon response-model identity, available inputs and no direct copying of event probability |
| EventPositionProposal | Explicit external-asset or binary-research use, existing authorities, news path, costs, payout, EV and maximum loss |
| PredictionMarketStudySpec | Frozen actual protocol identity, grouped chronology, baseline controls, full-account replay and separate live promotion |
| EventExecutionScenario | Book granularity, queue/fee references, cancel semantics, cash arithmetic and settlement timing |
| ArbitrageCandidate | Reviewed exact/complement relation, payoff states and exceptions, non-atomic legs and separate/currency-aware cash |
| MarketMakingPolicy | Inventory/outlay, conditional-on-fill value, pending-cancel reserves, event pause, queue assumptions and absent live order submission |

### Limits of the schemas and fixtures

The fixtures are all `FIXTURE`, include synthetic references and have no real independent calibration or authority. The local checker verifies selected cross-field arithmetic and chronology on these examples only. A string such as `review_ref` or `permission_ref` is not proof the review/permission exists. Production validators must resolve trusted records, verify signatures where required, bind actual environment/scope and reject fabricated references.

The schema's event-position monetary fields support both external-asset proposals and binary analysis; only the binary settlement fixture is used for the supplied expected-payout calculation. The actual production validator must apply the distinct target/loss/cost rules to each use scope. Early-exit EV cannot be validated with final-outcome payout arithmetic. For multi-position nonlinearity, return/payoff vectors and explicit state/currency/cash models are required in bound scenario artifacts.

The arbitrage fixture intentionally enumerates only YES/NO states for an explicitly synthetic no-void proposition. Real void, dispute, cancellation and unlike-currency cases must be added from reviewed actual rules; a two-state fixture cannot certify a real cross-venue hedge. Its positive minimum payoff is conditional on the stated assumptions and completed acquisitions, not guaranteed implementation profit.

The market-making fixture is a policy-contract example, not a quote optimizer or fitted arrival model. Concrete application implementations and their 180 acceptance contracts remain to be built and run. The same applies to fixture cash/fee formulas: the example $1.68 fee is an illustrative input, not a live schedule.

### Mandatory production semantic validations

Validate exact provider/market/event/rules versions; receive/available/decision chronology; first-official-release vintage; complete book snapshot and sequence chain; decimal/tick/quantity limits; complementary executable prices and depth. Check that derived histories never splice different events without explicit maturity/roll semantics.

Validate exhaustive bins versus overlapping thresholds, monotonic survival and calibrated-probability provenance. Check that source names/underlying events match their actual observations; count independent information lineages rather than aliases. Preserve armed minimum-two-source/tolerance policy without assuming statistical independence. A source/quality/calibration problem remains structured missing evidence, not a neutral price or zero risk.

Validate response-model task, cohort, horizon, calibration and out-of-fold lineage. D1–D6 never authorize greater risk; D7 cannot act without its actual strategy/owner grants. Monetary arithmetic uses exact conventions and no doubled spread/fees. Pending orders/cancels and unresolved settlements retain obligations until authoritative readback. Event price, calibrated event probability, conditional asset probability, expected profit and financial permission remain separate types.

`EventProbabilitySnapshot.armed_eligible` is an eligibility readback, never an execution grant. The schema allows a real independently verified consumer to report eligibility with `armed_eligibility_evidence_ref`; the portable synthetic example stays false. A producer cannot assert true on its own. Existing parent arming, source matching, liquidity, time and owner checks still execute, including the mandatory positive sandbox path.
