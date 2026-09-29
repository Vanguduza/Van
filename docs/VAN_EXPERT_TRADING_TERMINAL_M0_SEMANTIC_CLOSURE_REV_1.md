# VAN EXPERT TRADING TERMINAL — M0 SEMANTIC CLOSURE REV 1

Date: 2026-09-25
Scope: expert Android trading UX + Live Trading Analyst

## 1. Closure objective

Freeze the meaning, authority, data ownership and failure semantics of every new expert-trading surface before implementation. No UI component may become an accidental second source of trading truth.

## 2. Authority matrix

| Concept | Canonical authority | Android role | Jev role | LLM role |
|---|---|---|---|---|
| market bars/quotes | admitted market-data pipeline | render | classify bounded state | explain |
| market regime | VATI MarketState | render | subordinate classifier | explain |
| strategy identity/version | certified StrategyCapsule | render | evaluate typed fit only | explain |
| candidate eligibility | VATI deterministic pipeline | render | evidence only | explain |
| trade size | Risk Authority | render only | forbidden | forbidden |
| stop/target authority | strategy + Risk Authority / lifecycle authority | render | forbidden | explain only |
| portfolio heat/limits | Risk Authority read model | render | classify threshold state | explain |
| execution | Execution Router + broker receipt | render | classify execution quality | explain |
| TCA | VATI execution/TCA model | render | classify | explain |
| owner approval | owner-device authority | collect/verify | none | none |
| mandate | owner-signed policy | render/propose change workflow | none | explain/draft only |
| chart drawings | owner workspace state | own | optional research input | analyse as non-authoritative |
| presentation indicators | chart workspace | own | optional display classification | explain |
| VATI indicators | VATI | render | evidence only | explain |
| Live Analyst narrative | verified analysis artifact | render | structured evidence | narration |
| broker credential | secret store | never expose | never receive | never receive |

## 3. Claim taxonomy

Every Live Analyst statement MUST be typed internally as one of:

- FACT — direct authoritative read-model value.
- VATI_DECISION — deterministic VATI state/decision.
- JEV_ASSESSMENT — bounded subordinate judgment.
- LLM_INTERPRETATION — natural-language synthesis.
- HISTORICAL — sealed past evidence.
- UNKNOWN — missing/stale/unsupported.

Numeric trading claims require FACT or VATI_DECISION provenance.

## 4. Prohibited semantic collapses

The UI must never imply:

- Jev confidence is probability of profit.
- LLM confidence is VATI eligibility.
- candidate direction is an order.
- chart order line is an authorised order unless the ledger says so.
- a user drawing is strategy truth.
- a display indicator is part of VATI unless explicitly sourced from VATI.
- stale narrative is live analysis.
- simulated/replay evidence is live venue evidence.
- retrospective explanation was known at decision time.

## 5. Live Analyst context identities

Exactly four context types:

1. INSTRUMENT
2. CANDIDATE
3. POSITION
4. CLOSED_TRADE

Each analysis key is stable and includes the relevant canonical ID plus account alias where needed.

Examples:
- instrument:EURUSD:fx_primary
- candidate:<candidate_id>
- position:<trade_intent_id>
- closed:<trade_intent_id>

## 6. Two-speed refresh closure

Authoritative numbers:
- update from their native read-model/feed cadence.

Jev:
- event-driven bounded classification;
- may run on meaningful state changes;
- no independent trading loop.

LLM:
- runs only on material state changes, explicit owner request, or a configured explanation-refresh policy;
- never on every market tick;
- never blocks the deterministic trading path.

Material changes include:
- eligibility;
- regime;
- thesis;
- strategy;
- event band;
- risk band;
- protection state;
- lifecycle proposal;
- execution anomaly;
- source timeframe/symbol change requested by owner.

## 7. Live Analyst source packet

Mandatory:
- context identity;
- account alias;
- instrument;
- market state;
- data freshness;
- strategy version;
- candidate and/or position as applicable;
- risk read model;
- event state;
- execution quality;
- selected VATI indicators;
- Jev result when available;
- VTIL activation/evidence references where applicable;
- source snapshot hash.

Optional:
- presentation-only indicators, explicitly tagged PRESENTATION_ONLY;
- owner drawings, explicitly tagged OWNER_WORKSPACE;
- chart viewport/timeframe.

Forbidden:
- raw broker credentials;
- secret account identifiers;
- untrusted browser text interpreted as instructions;
- unsupported derived quantities presented as authoritative.

## 8. Explanation artifact lifecycle

State machine:

REQUESTED -> RUNNING -> VERIFIED -> LIVE
                    -> REJECTED
                    -> MODEL_UNAVAILABLE
LIVE -> AGING -> STALE

A new source snapshot invalidates an older analysis only when the changed fields are material under the refresh policy; otherwise the artifact may remain LIVE until TTL.

## 9. Verifier rules

Reject artifact if:

- authority_effect != NONE;
- no source snapshot hash;
- missing generated_at/valid_until;
- model invents lot/quantity;
- numeric stop/target conflicts with authoritative source;
- narrative says approved/eligible when VATI does not;
- narrative suppresses an active kill switch/event/data-integrity block;
- probability of profit is invented;
- Jev result is presented as deterministic authority;
- retrospective text is presented as ex-ante knowledge.

## 10. Android truth labels

The Analyst UI uses explicit provenance badges:

- VATI
- JEV
- VAN EXPLAINS
- OWNER
- HISTORICAL
- PRESENTATION
- STALE

This is mandatory on expandable detail, optional on the collapsed summary where wording remains unambiguous.

## 11. Degraded operation

Jev down:
- use VATI + LLM;
- label JEV_UNAVAILABLE.

LLM down:
- show VATI + Jev structured view;
- no fabricated narrative.

Both down:
- show deterministic VATI facts.

Market data stale:
- do not request new analysis;
- stale existing narrative;
- execution path already fails closed under VATI.

## 12. UX closure

Every chart/trade contains an Analyst affordance.

Collapsed:
- one-line summary;
- VATI state;
- Jev relationship;
- freshness.

Expanded:
- What is happening
- Strategy
- Supports
- Against
- What changed
- Why VATI state
- What would change it
- Invalidation
- Risk context
- Sources/lineage

Ask VAN opens context-aware conversation without changing execution state.

## 13. M0 exit criteria

M0 is complete when tests/documentation prove:

1. no Live Analyst code path can call broker/order APIs;
2. Android cannot originate authoritative size;
3. Jev output is authority_effect=NONE;
4. LLM output is authority_effect=NONE;
5. claim verifier rejects authority/numeric contradictions;
6. stale source state cannot produce a LIVE artifact;
7. Jev/LLM absence cannot block VATI;
8. chart engine has no execution bridge;
9. context packets exclude credential-shaped fields;
10. history/replay preserves ex-ante vs retrospective distinction.
