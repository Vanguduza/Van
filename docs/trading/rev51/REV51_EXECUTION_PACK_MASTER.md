# VAN Trading Rev 5.1 — Deterministic Engineering Execution Pack

**Status:** `SPEC_COMPILED / IMPLEMENTATION_READY`  
**Live status:** `NOT CLAIMED`  
**Baseline:** `Vanguduza/Van@6574671a381d48199593fb054f69e30ee7632c70` / PR #49  
**Model hierarchy:** `Fable 5.1 → GPT-6 Astra → Claude Opus 5 → GPT-5.6 Sol`  
**First-pass cognition:** `OFFLINE_EVOLUTION + SHADOW_LIVE`; `LIVE_ADVISORY=DISABLED`

## Governing rule

Implementation agents may choose local algorithms only inside already frozen authority, data, state, failure, verification and owner-truth contracts. No agent may invent a second RiskAuthority, second broker-submit path, silent enum/default, live-affecting tunable, or model-to-order shortcut.

## Existing production spine retained

```text
InstrumentEvaluator[N] → CandidatePool → AccountDecisionCoordinator → IntentFactory
→ fresh RiskSnapshot → RiskAuthority → ExecutionPolicyEngine → ExecutionRouter
→ venue adapter → AccountTradeLifecycle → TCA/review/learning/ledger
```

## Mandatory invariants

- **INV-AUTH-001** — RiskAuthority is the sole live numeric sizer.
- **INV-EXEC-001** — ExecutionRouter is the sole broker order-sending boundary.
- **INV-MODEL-001** — Fable→Astra→Opus→Sol is availability routing; fallback may never relax controls.
- **INV-LIVE-001** — First pass is OFFLINE_EVOLUTION + SHADOW_LIVE; LIVE_ADVISORY is promotion-gated.
- **INV-RISK-001** — No stop widening, averaging down, martingale, leverage override, or mandate escalation.
- **INV-PPC-001** — ProtectedProfitCredit is zero unless guaranteed exit capability is independently certified.
- **INV-LEARN-001** — Every new live-affecting tunable must be classified; unclassified means FORBIDDEN.
- **INV-EVID-001** — Self-asserted completion is insufficient where independent evidence exists.
- **INV-REPLAY-001** — Externally consequential decisions must be causally replayable and version-bound.
- **INV-FAIL-001** — Model/research/measurement failure must not disable deterministic protection or exits.

## Implementation order

`G0 → G0b calendar → G1 contracts/authority → G2 model routing → G3 context/world → G3b measurement → G4 cognition governance → G5 translator/health → G5b route/pretrade → G6 execution qualification → G7 preservation → G7b event episodes → G8 execution/conformal → G9 family/risk → G10 expansion research → G11 expansion shadow → G12 research factory → G13 evolution/protection → G14 owner surfaces → G15 certification`.

## Atomic packet index

- `TRD-REV51-090` / `DU-TRD-090` — **Economic Calendar Recorder** — `vati-calendar.service / `python -m vati calendar-record``
- `TRD-REV51-091` / `DU-TRD-091` — **Trading Model Provider Registry & Quota Scheduler** — `shadow cognition scheduler and offline research/evolution services`
- `TRD-REV51-092` / `DU-TRD-092` — **TradingWorldModel & Persistent Cognition Store** — `cognition projector subscribed to VATI ledger/event stream`
- `TRD-REV51-093` / `DU-TRD-093` — **Versioned Trading Context Compiler** — `cognitive wake handler before every model invocation`
- `TRD-REV51-094` / `DU-TRD-094` — **CognitiveAssessment Contract & Reason Vocabulary** — `ModelRouter result normalizer`
- `TRD-REV51-095` / `DU-TRD-095` — **Blind Reviewer & Reviewer Canary** — `high-impact offline evaluation pipeline`
- `TRD-REV51-096` / `DU-TRD-096` — **Cognitive Budget & Degradation Ladder** — `before every cognition invocation`
- `TRD-REV51-097` / `DU-TRD-097` — **Deterministic Analogue Retrieval** — `context compilation`
- `TRD-REV51-098` / `DU-TRD-098` — **Cognitive Action Translator** — `post-assessment shadow pipeline`
- `TRD-REV51-099` / `DU-TRD-099` — **TradeHealth Engine** — `post-entry lifecycle before scale/new-risk evaluation`
- `TRD-REV51-100` / `DU-TRD-100` — **Deterministic Shadow Book** — `every candidate/open-position decision point eligible for cognition measurement`
- `TRD-REV51-101` / `DU-TRD-101` — **P&L Attribution Engine** — `trade/decision comparison horizon completion`
- `TRD-REV51-102` / `DU-TRD-102` — **VATI Decision Exam** — `CI/release qualification and scheduled cognition evaluation`
- `TRD-REV51-103` / `DU-TRD-103` — **Cognitive Performance Ledger** — `after outcome/attribution horizon completes`
- `TRD-REV51-104` / `DU-TRD-104` — **Symbol / Route / Quantisation Registry** — `account-service startup and periodic route refresh`
- `TRD-REV51-105` / `DU-TRD-105` — **Pre-Trade Control Layer** — `every order-sending TradeIntent, root or child`
- `TRD-REV51-106` / `DU-TRD-106` — **PositionFamily Model** — `AccountTradeLifecycle after every entry/partial/close/reconciliation event`
- `TRD-REV51-107` / `DU-TRD-107` — **PositionRiskEnvelope & Released-Risk Haircut** — `after every family/stop/mark/reconciliation change and before any scale candidate`
- `TRD-REV51-108` / `DU-TRD-108` — **Scale Policy Registry** — `runtime scale-policy lookup`
- `TRD-REV51-109` / `DU-TRD-109` — **Expansion Counterfactual Laboratory** — `offline research CLI/workflow before G11`
- `TRD-REV51-110` / `DU-TRD-110` — **Profit Expansion Engine** — `post-entry lifecycle after urgent preservation actions`
- `TRD-REV51-111` / `DU-TRD-111` — **Loss Containment & Profit Preservation** — `post-entry lifecycle before any scale/new-entry action`
- `TRD-REV51-112` / `DU-TRD-112` — **Event Release Normaliser** — `calendar recorder event consumer`
- `TRD-REV51-113` / `DU-TRD-113` — **Event Surprise / Reaction Engine** — `event release processor + scheduled horizon callbacks`
- `TRD-REV51-114` / `DU-TRD-114` — **MacroEventEpisode Producer** — `event-reaction scheduler when configured horizons finish/expire`
- `TRD-REV51-115` / `DU-TRD-115` — **Venue-Generic Event Registry** — `trading service startup / explicit config reload`
- `TRD-REV51-116` / `DU-TRD-116` — **Execution Style Selector** — `after RiskDecision approval, before ORDER_COMMAND construction`
- `TRD-REV51-117` / `DU-TRD-117` — **Conformal Interval Engine** — `RiskAuthority before final sizing/admission for policies requiring conformal evidence`
- `TRD-REV51-118` / `DU-TRD-118` — **ResearchMission / ResearchPacket Contracts** — `research mission creation and worker completion`
- `TRD-REV51-119` / `DU-TRD-119` — **Fable Research Director** — `offline evolution scheduler and evidence/anomaly triggers`
- `TRD-REV51-120` / `DU-TRD-120` — **Specialist Research Agent Factory** — `mission orchestration loop`
- `TRD-REV51-121` / `DU-TRD-121` — **Research Qualification & Synthesis Join** — `research mission close workflow`
- `TRD-REV51-122` / `DU-TRD-122` — **Research Portfolio Yield Ledger** — `scheduled research portfolio evaluation`
- `TRD-REV51-123` / `DU-TRD-123` — **Strategy Evolution Archive & Harness** — `offline evolution scheduler`
- `TRD-REV51-124` / `DU-TRD-124` — **System Improvement Proposal Engine** — `research synthesis close workflow`
- `TRD-REV51-125` / `DU-TRD-125` — **Proposal Admission Control & Gate Health** — `proposal ingestion`
- `TRD-REV51-126` / `DU-TRD-126` — **Evaluator Protected-Path Enforcement** — `every model-authored candidate/proposal before scoring/merge`
- `TRD-REV51-127` / `DU-TRD-127` — **Growth Optimality Diagnostic** — `offline periodic risk research`
- `TRD-REV51-128` / `DU-TRD-128` — **Rejection Reason Analytics** — `read-model refresh / scheduled aggregation`
- `TRD-REV51-129` / `DU-TRD-129` — **Owner Trading Cognition Read Models** — `GET trading read endpoints`
- `TRD-REV51-130` / `DU-TRD-130` — **Trading Command Centre Surfaces** — `TradingCommandCentreActivity navigation/cards/tabs`
- `TRD-REV51-131` / `DU-TRD-131` — **Semantic Trading Push / Overlay Integration** — `gateway event publication on read-model/trading state transition`
- `TRD-REV51-132` / `DU-TRD-132` — **Model Handoff / Continuity State** — `every Fable→Astra→Opus→Sol transition`
- `TRD-REV51-133` / `DU-TRD-133` — **Rev 5.1 Certification Harness** — `PR CI, Trading Core qualification and release promotion`

## Mechanical verifier

Run `python tools/verify_build_ready.py`. Green certifies specification closure only, not implementation/runtime/live eligibility.
