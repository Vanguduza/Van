# Document consistency report — Rev1.1

**Result: PASS** · 2026-10-17T11:33:21.427811+00:00

Environment: ChatGPT artifact-packaging container; not a DIAL VM or VAN application environment. These are document/schema/synthetic-reference checks, not VAN application tests.

| Inventory | Count |
|---|---:|
| child packets | 48 |
| parent lineage packets | 76 |
| requirements | 90 |
| unexecuted application test contracts | 180 |
| principal schemas | 18 |
| fixture examples | 12 |
| source entries | 42 |
| document check groups | 43 |
| deliberate document fixture mutations | 64 |

## Checked properties

- PASS — plan DAG, ownership references, coverage and authority declarations
- PASS — all JSON documents parse without nonstandard NaN/Infinity
- PASS — Draft2020-12 schema shape: TrainingJobSpec.schema
- PASS — Draft2020-12 schema shape: EventPositionProposal.schema
- PASS — Draft2020-12 schema shape: PredictionMarketStudySpec.schema
- PASS — Draft2020-12 schema shape: DatasetManifest.schema
- PASS — Draft2020-12 schema shape: PredictionMarketSourceProfile.schema
- PASS — Draft2020-12 schema shape: EventAssetResponse.schema
- PASS — Draft2020-12 schema shape: DeploymentBinding.schema
- PASS — Draft2020-12 schema shape: ArbitrageCandidate.schema
- PASS — Draft2020-12 schema shape: PredictionMarketObservation.schema
- PASS — Draft2020-12 schema shape: ModelArtifactManifest.schema
- PASS — Draft2020-12 schema shape: TargetSpec.schema
- PASS — Draft2020-12 schema shape: ForecastPacket.schema
- PASS — Draft2020-12 schema shape: EventExecutionScenario.schema
- PASS — Draft2020-12 schema shape: PredictionMarketContract.schema
- PASS — Draft2020-12 schema shape: MarketMakingPolicy.schema
- PASS — Draft2020-12 schema shape: FeatureManifest.schema
- PASS — Draft2020-12 schema shape: EventProbabilitySnapshot.schema
- PASS — Draft2020-12 schema shape: QualificationRecord.schema
- PASS — synthetic READY forecast example shape/local semantics
- PASS — synthetic ABSTAINED forecast example shape/local semantics
- PASS — master source IDs resolve
- PASS — human plan includes all packet exit sections
- PASS — human requirement/test contracts include every exact ID
- PASS — research example has no resolved live/paid/market permission
- PASS — parent fingerprint references agree with retrieved material record
- PASS — original obligations, schemas and parent lineage preserved
- PASS — hosted research profile separates procurement, source use and authority
- PASS — four study templates align with research profile and no result is asserted
- PASS — parent delta preserves authority boundary and exact new IDs
- PASS — synthetic PM fixture shape/local semantics: ArbitrageCandidate
- PASS — synthetic PM fixture shape/local semantics: EventAssetResponse
- PASS — synthetic PM fixture shape/local semantics: EventExecutionScenario
- PASS — synthetic PM fixture shape/local semantics: EventPositionProposal
- PASS — synthetic PM fixture shape/local semantics: EventProbabilitySnapshot
- PASS — synthetic PM fixture shape/local semantics: MarketMakingPolicy
- PASS — synthetic PM fixture shape/local semantics: PredictionMarketContract
- PASS — synthetic PM fixture shape/local semantics: PredictionMarketObservation
- PASS — synthetic PM fixture shape/local semantics: PredictionMarketSourceProfile
- PASS — synthetic PM fixture shape/local semantics: PredictionMarketStudySpec
- PASS — all 18 principal schemas and 12 synthetic examples present
- PASS — all deliberate document/fixture mutations detected

## Deliberate faulty documents/fixtures

- DETECTED — dependency cycle
- DETECTED — code detached from F15
- DETECTED — second order sender
- DETECTED — automatic live promotion
- DETECTED — frontend disguised as backend
- DETECTED — missing adversarial test
- DETECTED — duplicate requirement ID
- DETECTED — application test falsely reported PASS
- DETECTED — incomplete independent backend inventory
- DETECTED — missing parent global barrier
- DETECTED — unknown parent unit
- DETECTED — procurement incorrectly gates document/code
- DETECTED — event market given order-sender authority
- DETECTED — hosting asserted to prove operator eligibility
- DETECTED — event research labs made optional
- DETECTED — uncalibrated score advertised as calibrated probability
- DETECTED — NaN output
- DETECTED — future input availability
- DETECTED — expiry before generation
- DETECTED — crossed quantiles
- DETECTED — ready without output
- DETECTED — abstention contains forecast payload
- DETECTED — fixture relabelled live
- DETECTED — forecast injected order quantity
- DETECTED — scenario count without actual artifact
- DETECTED — joint claim without joint artifact
- DETECTED — PM procurement introduced as requirement
- DETECTED — PM purchase authorized
- DETECTED — PM host inferred as operator eligibility
- DETECTED — PM fixture relabelled authorized capture
- DETECTED — PM threshold absent
- DETECTED — PM reviewless exact equivalence
- DETECTED — PM missing opposite bid replaced with ask
- DETECTED — PM wrong complementary ask
- DETECTED — PM sequence gap marked healthy
- DETECTED — PM observation available after decision
- DETECTED — PM negative book quantity
- DETECTED — PM threshold survival increases
- DETECTED — PM exclusive bins do not sum to one
- DETECTED — PM calibrated probability has no calibration
- DETECTED — PM outcome known before expectation frozen
- DETECTED — PM probability change hides contract roll
- DETECTED — PM two-source claim hides duplicate
- DETECTED — PM two-source claim mismatches event
- DETECTED — PM agreement treated as independence
- DETECTED — PM fixture turns on armed eligibility
- DETECTED — PM event probability copied as trade-win probability
- DETECTED — PM response trained in the future
- DETECTED — PM asset probability lacks calibrator
- DETECTED — PM news proposal expands risk
- DETECTED — PM binary EV omits costs
- DETECTED — PM binary maximum loss understated
- DETECTED — PM proposal enables live
- DETECTED — PM study splits individual quotes
- DETECTED — PM study drops exposure-matched control
- DETECTED — PM study claims unrun economic success
- DETECTED — PM cash ignores fee debit
- DETECTED — PM settlement cash released early
- DETECTED — PM price touch guarantees fill
- DETECTED — PM arbitrage has hidden losing state
- DETECTED — PM cross-venue legs assumed atomic
- DETECTED — PM quote cancel releases exposure before confirmation
- DETECTED — PM maker assumes privileges
- DETECTED — PM maker allows live order submission

## Claims not made

Licence procurement or source-use permission, Operator eligibility, Actual provider capture or event-contract trading, Application implementation, Runtime model/service integration, Dataset or model training, Statistical/economic validation, Independent semantic review, Expanded parent DAG qualification, Cryptographic authority validation, Parent F15 or BG-001 issuance, Device acceptance, Live financial permission. All180 application acceptance contracts remain NOT_RUN. No independent gate or financial authority is issued.
