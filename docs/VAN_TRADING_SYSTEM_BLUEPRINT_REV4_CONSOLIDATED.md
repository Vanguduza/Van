# VAN Trading System — Consolidated Blueprint, Revision 4

**Status:** active engineering authority for the VAN Adaptive Trading Intelligence (VATI).
**Consolidates:** Rev 2 (canon + development plan), Rev 2.1 (industry integration architecture), Rev 3 (research-grounded
expert-trader decisions + Zimbabwe Stock Exchange module) and the continuous-learning integration review. Those
documents remain in the repository as **provenance**; where they disagree with this document, this document wins.
**Branch / build:** `claude/van-autonomous-trader-r81vyn` · code under `trading/vati`, `trading/vtil`, `backend/van_gateway/trading`.
**Date:** 2026-09-16.

---

## Part A — What VATI is, in one page

VATI is a multi-market, multi-horizon, regime-adaptive trading system whose defining capability is knowing when *not*
to trade. It is not a retail bot, not a fixed-indicator strategy, not a next-candle predictor and not a language model
wired to a broker.

```text
                              OWNER  ── signed mandate, ceilings, promotions, kill-switch clear (A4)
                                │
                              VAN gateway ── /v1/trading/status · /tickets · owner-signed /halt · /tickets/{id}/confirm
                                │
                             HERMES ── profile van · skill trading-intelligence · continuity memory (never evidence)
                                │
        ┌───────────────────────┼─────────────────────────┐
   MARKET BRAIN            RESEARCH BRAIN             RISK BRAIN
   features · regimes      VTIL on DIAL VEKL          mandate · platform ceilings
   Tier-1 events           research priority          portfolio heat · currency legs
   integrity · calendars   candidates (RESEARCH)      drawdown governor · kill switch
        └───────────────────────┼─────────────────────────┘
                     STRATEGY ARBITER → HORIZON ARBITER → META-LABELLER (rules v0)
                          OPPORTUNITY ENGINE  ──►  sealed TradeIntent (never sized)
                                │
              ══════ DETERMINISTIC RISK AUTHORITY ══════   the only sizer; NO_TRADE is a valid outcome
                                │  sealed RiskDecision
                       EXECUTION ROUTER  (refuses without the sealed decision_hash; kill switch; protection)
                   ┌──────────┬─────────────┬───────────────┐
                 Paper     MT5 bridge      Deriv          OWNER_TICKET (ZSE / VFEX)
                                │
        RECONCILE → TCA → TRADE REVIEW → EXPERIENCE ARTIFACT → LEARNING (reduce-only) → VTIL admission
```

**Invariants (never inverted):**

1. Only the deterministic Risk Authority sizes. Every multiplier it accepts is clamped to [0, 1]; lot sizes round
   down or become `NO_TRADE`; a mandate cannot omit a hard-forbidden behaviour; platform ceilings sit beneath the mandate.
2. No model, research output, learning output or Hermes turn sends, sizes, modifies or cancels a broker order.
3. Broker credentials never enter prompts, memory, artifacts or the ledger. Accounts appear as aliases.
4. Mandate, ceilings, promotion, capital steps and kill-switch clear are owner-signed (A4). Forbidden behaviours are A5
   and stay denied even with recorded owner approval.
5. Everything on the decision path is hashed and chained. A decision that cannot be replayed to the same hash is a fault.
6. Learning is continuous; production authority is not. Learning may reduce, demote and propose; it may never promote,
   widen or admit itself.

---

## Part B — Decisions carried into Rev 4

| # | Decision | Origin | State in code |
|---|---|---|---|
| B1 | Horizons SCALP (k ≥ 3× cost), INTRADAY, SESSION, OVERNIGHT, SWING, POSITION; **MICRO removed** | Rev 3 D1 | `arbiter/horizon.py`, registry refuses MICRO |
| B2 | Cost Model Authority: `round_trip_cost_pct` on every contract; `EDGE_BELOW_COST` when expected move < 2× cost | Rev 3 D2 | `risk/authority.py`, `market_data/costs.py`, `zse/costs.py` |
| B3 | Edge portfolio: trend/momentum SWING–POSITION; session structure intraday; post-event drift; gold macro; ZSE value rotation / liquidity provision | Rev 3 D3 | six sealed capsules in `trading/strategies/registry` |
| B4 | LLM boundary: research, review, explanation and T2 assessment (TTL, reduce-only) only | Rev 3 D4 | `meta_labeler.py` T2 branch; policy hook A5 |
| B5 | Own deterministic kernel first; NautilusTrader adopted at the Phase 3 donor gate; LEAN as Tier-A validation oracle; no HFT tooling | Rev 3 D5, D9 | `app/cycle.py`, `backtest/engine.py`; stack lock 4.0.0 |
| B6 | Venue adapters in order MT5 bridge → cTrader (later) → Deriv → OANDA (if available); ZSE via OWNER_TICKET | Rev 3 D6, D11 | `execution/mt5_bridge.py`, `deriv.py`, `zse_ticket.py` |
| B7 | Validation gates: deflated Sharpe, PBO (CSCV), walk-forward, one-switch leakage test, cost stress | Rev 3 D7 | `backtest/metrics.py`, `peek` switch |
| B8 | Minimum deterministic stack for M1–M2; institutional profile optional and owner-signed | Rev 3 D9 | `trading/architecture/stack_lock.json` |
| B9 | Prop-firm mandate profile as a `TradingMandate` variant | Rev 3 D10 | mandate schema fields |
| B10 | Three-plane execution chain (VAN RiskGate → kernel RiskEngine → ExecutionClient refuses without decision hash) | Rev 2.1 E.2 | `execution/router.py` (plane 1 + 3 today; plane 2 arrives with Nautilus) |
| B11 | VTIL on borrowed DIAL VEKL infrastructure; a dedicated trading VEKL only if measured need | Rev 2 §6, 2.1 E.4 | `trading/vtil`, probe GREEN |
| B12 | Trading data plane on Van-owned hosts, attached to the DIAL fabric only through the project-binding seam | Rev 2.1 E.7 | topology unchanged |
| B13 | **Learning boundary**: three reduce-only live targets, environment-weighted evidence, ex-ante guard | Rev 4 (this doc) | `trading/vati/learning` |
| B14 | **Owner surface**: ledger-derived status, ticket list, owner-signed halt and ticket confirmation in the existing gateway | Rev 4 (this doc) | `backend/van_gateway/trading` |

---

## Part C — Market brain

**C.1 Data and integrity.** Ticks aggregate to UTC-aligned bars deterministically (`market_data/bars.py`). Every feed
sample passes an integrity monitor (gaps, spread blow-outs, stale quotes, clock skew) that moves the market to
NORMAL → ELEVATED → ABNORMAL → HALTED; ELEVATED halves size, ABNORMAL/HALTED refuse new orders. Session calendars
(`market_data/calendars.py`) know FX sessions and a ZSE calendar whose times remain a live blocker until verified.

**C.2 Features and regimes.** Features are pure functions of the bar window (EMA band, ATR, RSI, swing points,
spread percentile). The regime engine (`intelligence/regimes.py`) combines a trend classifier, a volatility regime and
a CUSUM change-point detector into NORMAL → CAUTION → TRANSITION → NEW_REGIME with hysteresis. `RegimeState.
risk_multiplier()` is ≤ 1; TRANSITION yields WAIT for every FX capsule.

**C.3 Tier-1 events.** The event matrix (`intelligence/events.py`) defines blackout, quiet and drift windows. An
unverified release time fails closed (blackout). Post-event trading is drift, not spike.

**C.4 MarketState.** One sealed object per bar (`state_hash`) carries symbol, session, features, regime, integrity,
event window, quote age and the VTIL `activation_id`. The Opportunity Engine, the Risk Authority and the ledger all
reference the same hash, which is what makes decision replay possible.

---

## Part D — Research brain (VTIL) and strategy lifecycle

**D.1 VTIL.** Trading knowledge is a Van-owned registry in DIAL's VEKL schema (`trading/vtil/registry`), resolved by
DIAL's *unmodified* resolver through mirrored directory names; every resource declares an explicit `selection_purpose`
(minimal-coalition slot law). Admission (`vati/vtil/admission.py`) forbids self-admission and requires validation for
T4 knowledge. A dedicated trading VEKL is created only when a measured retrieval-quality gap justifies it.

**D.2 Capsules.** A strategy is a sealed JSON `StrategyCapsule` (instruments, horizons, eligible/forbidden regimes,
data granularity, required features, entry/invalidation refs, stop/target model, risk limits, execution model, event
rules, training/validation periods, cost-model ref, state, evidence refs, approval signature). Promotion advances one
state at a time and requires an owner signature (A4); live promotion requires evidence refs; demotion never requires a
signature. SCALP cannot certify on bars.

```text
RESEARCH → BACKTEST → VALIDATION → DEMO → SHADOW → LIMITED_LIVE → CERTIFIED_LIVE
                       (demotion at any time: DEGRADED · SHADOW · SUSPENDED · RETIRED)
```

**D.3 Curriculum.** A capsule cannot be promoted past the stage it has passed (Part L.8): quiet sessions → standard
intraday → high volatility → Tier-1 events → cross-market divergence → regime transitions → abnormal liquidity →
broker disruption / failure injection.

**D.4 Research priority.** Losses, decay, regime change, missed opportunities, execution inefficiency and broker
degradation become `ResearchTask`s scored deterministically by economic value × tractability; tool value meta-learns
within [0.1, 1.5]. Hermes, Deep Research and NotebookLM consume the queue; their output re-enters only through VTIL
admission as research packets.

---

## Part E — Opportunity engine

For each active capsule the **Strategy Arbiter** checks state, instrument, regime labels, event window and integrity;
the strategy implementation emits a `Signal` or nothing; the **Horizon Arbiter** confirms the horizon's cost multiple
and quote freshness; the **Meta-labeller v0** (deterministic rules, `RULES_V0_UNCALIBRATED`) emits TRADE / REDUCE_SIZE /
WAIT / SKIP with five multipliers, each ≤ 1: regime, volatility, liquidity (incl. the **learned broker liquidity cap**),
event risk and confidence (incl. **capsule health**). A fresh T2 assessment can only reduce. The best surviving signal
becomes a sealed `TradeIntent` that carries no size. ZSE signals take the ZSE branch: liquidity from thin trading days,
regime from the ZiG premium regime, no FX microstructure penalties.

---

## Part F — Deterministic Risk Authority (the only sizer)

Delivered in `trading/vati/risk` and unchanged in principle since Rev 2 §27:

- `TradingMandate` (versioned, expiring, owner-signed; forbidden list must cover `HARD_FORBIDDEN_BEHAVIOURS`);
  `PlatformCeilings` beneath it; drawdown tiers; authorization modes OBSERVE → ADVISOR → DEMO_TRADER → SHADOW_TRADER →
  LIMITED_LIVE → AUTONOMOUS_LIVE (HALTED at any time).
- Loss models: `STOP_DISTANCE` (FX/CFD), `FULL_STAKE` (fixed-payout contracts), `ILLIQUID_EQUITY` (ZSE/VFEX: software
  stop + liquidity haircut, board-lot round-down, ≤ 10 % ADV participation, long-only).
- Fixed evaluation order; every check fails closed; `evaluate_safe` turns any exception into `AUTHORITY_FAULT`;
  the decision is sealed (`decision_hash`) with its inputs so the ledger can replay it.
- Portfolio heat with currency-leg netting; consecutive-loss and position-count limits; stale-data, unverified-account,
  disconnected-broker, reconciliation, clock-sync and integrity gates; `EDGE_BELOW_COST`.
- Kill switch latches on fourteen triggers (incl. `OWNER_HALT`) and clears only with an owner signature.

Evidence discipline: seeded property fuzz (P1–P8) and `trading/tools/induce_gate_failures.py`, which breaks each gate
deliberately and proves the fuzz or a backstop catches it (13/13).

---

## Part G — Execution, protection, reconciliation, review

- **Router** (`execution/router.py`): verifies the intent against the sealed decision and the mandate, refuses on kill
  switch, builds one `OrderCommand` with the protective stop in the same request, logs command and receipt, trips
  `STOP_REJECTED` → flatten when a venue accepts an entry without its stop, and routes ZSE to OWNER_TICKET.
- **Adapters**: Paper (deterministic fills, fault injection, marks), MT5 bridge client (HMAC-signed, nonce/replay/skew
  checks, fail-closed without transport), Deriv (contract family → loss model, synthetic refusal), OwnerTicket (VAN never
  automates ZSE Direct / C-Trade).
- **Protection**: stops only tighten (break-even, trailing, time stop).
- **Reconciliation** classes MATCH, VENUE_PARTIAL_CLOSE, VENUE_STOP_HIT, OWNER_OVERRIDE, ORPHAN_*, STOP_MISSING gate new
  orders; the session runner refuses to start on an orphan.
- **TCA** per fill (spread, slippage, delay, fees, implementation shortfall, cost ratio vs model).
- **Trade review** outcome classes GOOD_WIN, GOOD_LOSS, BAD_WIN, BAD_LOSS, EXECUTION_FAILURE, DATA_FAILURE,
  RISK_FAILURE, **BROKER_FAILURE**, **UNKNOWN**, with polarity POSITIVE / ANTI_PATTERN; every review is proposed to VTIL,
  never admitted by itself.

---

## Part H — Decision cycle, backtest-to-live parity, ledger

One class, `DecisionCycle`, runs both backtests (Paper adapter over historical bars) and live sessions (real adapter
over a feed): VERIFY DATA → MARKET STATE → OPPORTUNITY → RISK AUTHORITY → ROUTER → PROTECT → marks → RECONCILE → TCA →
REVIEW → **LEARN** → VTIL PROPOSE. Parity is a property of the code, not a hope.

The hash-chained SQLite ledger (`core/ledger.py`, PostgreSQL at Phase 4) stores every event with three clocks;
`verify_chain` and `replay_decisions` re-run the Risk Authority on stored inputs and compare hashes. The backtest
engine reports expectancy, drawdown, per-trade Sharpe, deflated Sharpe, PBO via CSCV and walk-forward splits, and has a
one-switch leakage test (`peek`) that must change the result.

---

## Part I — Zimbabwe Stock Exchange / VFEX module (VATI-ZSE)

Carried from Rev 3 Part D without change of intent; implemented in `trading/vati/zse`:

- **Market facts with verification state.** T+3 settlement, board lot 100, Day/GTC-30 orders, ±15 %/±20 % circuit
  breakers, 10 % index cool-off, Capizar ATS, ZiG since 8 April 2024, parallel-premium regimes, Econet delisting effect,
  2020 closure. Session times, CGWT rate and foreign limits are **CONFLICTING/UNVERIFIED** across sources;
  `MarketSpec.live_blockers()` blocks any live mandate until a broker verifies them (`python -m vati zse-facts`).
- **Costs** with holding-period capital-gains withholding; **currency regime** classifier ANCHORED → ELEVATED → STRESSED →
  DISORDERLY (DISORDERLY = SKIP); **liquidity** haircut and ADV participation cap.
- **Strategies** ZSE-VALUE-ROTATION and ZSE-LIQUIDITY-PROVISION as SWING/POSITION capsules under `ILLIQUID_EQUITY`.
- **Execution** OWNER_TICKET (owner enters the approved ticket; VAN reconciles from CSD holdings and contract notes),
  BROKER_INSTRUCTION (owner-approved), DMA (institutional, later). The gateway records confirmations (Part K).
- **Study mode** before trade: counter knowledge base, calendar, regime history, analogue engine, VTIL registry growth.

Feature plan VATI-ZSE-F001…F006 (Rev 3 D.8) stands; F001 (broker verification of the conflicting facts) is the gate
for anything live.

---

## Part J — Stack lock and deployment topology

`trading/architecture/stack_lock.json` (revision 4.0.0, tested) locks one tool per layer with licence class,
adoption phase and **build status**: the VAN-owned kernel, hash-chained ledger, CSV bar loader, metrics exposition,
ZSE market data and OWNER_TICKET execution are built; MT5/Deriv adapter contracts are built with fail-closed transports;
Nautilus, LEAN, Parquet, PostgreSQL, Feast, MLflow, Redpanda, QuestDB, Temporal, ArcticDB, OpenBB, Qlib, Optuna and
Databento are pinned only at their adoption gate with Context7/official release facts. Verified so far:
nautilus_trader 1.231.0 (LGPL-3.0-or-later, Python ≥ 3.12; VAN runs 3.11 today, so adoption waits for the runtime step).

Topology is Rev 2.1 E.7: `vati-core` (Linux) + `vati-mt5-worker` (Windows, isolated VLAN) for M1; optional `vati-data`
for M2; attachment to the DIAL fabric only via project binding. The DIAL Oracle estate is a control plane and cannot
host the trading data plane. No dial-new change is requested by Rev 4.

---

## Part K — Owner surface (gateway), Hermes and policy

**K.1 Gateway** (`backend/van_gateway/trading`), reading the VATI ledger (`VAN_VATI_LEDGER_PATH`):

| Route | Class | Effect |
|---|---|---|
| `GET /v1/trading/status` | A1 | chain verification, counts by kind, active kill-switch triggers, open tickets, last event; sets/clears `TRADING_LEDGER_UNAVAILABLE` |
| `GET /v1/trading/tickets?status=` | A1 | OWNER_TICKET events paired with confirmations |
| `GET /v1/trading/trades?view=&limit=` | A1 | past / current / potential trades with confidence scores (K.4) |
| `POST /v1/trading/halt` | A4 | internal control token **and** `owner_signature_ref`; appends `KILL_SWITCH{OWNER_HALT}`; audited |
| `POST /v1/trading/tickets/{id}/confirm` | A4 | token + signature + fill/qty/contract note; once per OPEN ticket; qty ≤ ticket; audited |

The service exposes no method that could create, size, modify or cancel an order (tested by name).

**K.4 Trade preview on the floating overlay.** The overlay's working surface gains a `TRADES` mode (rail action
"Trades", Van stays on the glass edge) with three on-demand tabs read from `GET /v1/trading/trades?view=`:

| Tab | Source in the ledger | Row shows |
|---|---|---|
| Past | intents with a `TRADE_REVIEW` | symbol, direction, R multiple, P&L, outcome class, exit reason, first lesson |
| Current | approved intents with an entry receipt and no review | state (OPEN / WORKING / AWAITING_OWNER_TICKET), approved size, fill, protective stop (loud when unconfirmed), owner ticket status |
| Potential | latest `OPPORTUNITY_ASSESSMENT` per symbol (every candidate that produced a signal) plus Risk Authority / router refusals from the last day of ledger time | label (TRADE / REDUCE_SIZE / WAIT / SKIP / REJECTED:<code>), entry, stop, edge multiple, first reason |

Every row carries a **confidence score** (`vati.arbiter.confidence`): the product of the five reduce-only rule
multipliers the meta-labeller emitted for that trade × learned capsule health, clamped to [0, 1], banded HIGH ≥ 0.75,
MEDIUM ≥ 0.50, LOW ≥ 0.25, MINIMAL. It is labelled `RULES_V0_UNCALIBRATED`, it ranks and explains, and it never sizes:
sizes come only from the Risk Authority. The trade book is a read model (`vati/app/tradebook.py`); the gateway
service and the Android client expose no call that could place, size, modify or cancel a trade, and both are tested
for that by name. Data is fetched on open, tab change and refresh, never polled; a missing ledger or unreachable
gateway shows as such rather than as an empty book.

**K.2 Hermes.** Profile `van` lists the `trading-intelligence` skill; SOUL.md carries the trading-authority section;
the skill's "Operating the built system" and "Continuous learning" sections tell Hermes to answer status from the ledger,
explain tickets without confirming them, recommend halts without sending them, and narrate learning reports without
computing or inventing them.

**K.3 Policy hook** (`hermes/policy/van_policy_hook.py`). A5 patterns cover the Rev 2 §39 list plus the learning set
(`learning_engine_writes_mandate`, `learning_widens_risk`, `learning_raises_multiplier`, `auto_promote_strategy`,
`self_admit_knowledge`, `broker_credentials_in_memory`, `memory_as_evidence`). Protected surfaces include the Risk
Authority, mandates, kill switch, ledger, strategy registry, platform ceilings and `trading/vati/learning/boundary`.

---

## Part L — Continuous learning, memory and research (new in Rev 4)

**L.1 Principle.** Learning is continuous; production authority is not. The integration Rev 1 document described
*what* to learn from correctly and *where learning may act* too loosely (see the provenance record under
`docs/archive/`). Rev 4 keeps every learning source and adds a hard boundary, quantified evidence provenance and an
ex-ante guard, then wires the result into the shared decision cycle.

**L.2 Learning boundary** (`learning/boundary.py`). Exactly three live-affecting targets, all reduce-only:

| Target | Effect in the live path | Ceiling |
|---|---|---|
| `CAPSULE_HEALTH` | meta-labeller confidence cap; SKIP below 0.55; automatic demotion to DEGRADED (pre-live) or SHADOW (live) after a sustained breach | multiplier ≤ 1 |
| `REGIME_PROBABILITY` | regime multiplier cap | ≤ 1 |
| `BROKER_PROFILE` | per-symbol liquidity cap from the learned broker execution profile; SUSPENDED = 0 | ≤ 1 |

Any adjustment needs ≥ 30 environment-weighted samples and must cite artifact hashes. Mandate, platform ceilings,
capsule logic or state promotion, instrument list, credentials, leverage, risk/execution policy and production model
alias are forbidden targets: the boundary raises, the policy hook denies, and the boundary module is a protected surface.

**L.3 Evidence provenance.** Weight by environment: LIVE / LIMITED_LIVE 1.0, SHADOW 0.7, DEMO 0.5, REPLAY / BACKTEST
0.3, COUNTERFACTUAL 0.2. Execution facts (spread, slippage, fills, rejections) from BACKTEST / REPLAY / COUNTERFACTUAL
weigh **0**: only real venues teach execution.

**L.4 Knowledge objects** (`learning/episodes.py`): `ExperienceEpisode` (assembled from the chained events of one
intent and written back as `TRADE_EXPERIENCE_ARTIFACT`), `MissedOpportunityEpisode`, `CounterfactualResult`,
`MacroEventEpisode`; all sealed, all `PROPOSED` until VTIL admission.

**L.5 Capsule health** (`learning/health.py`): expectancy vs certified, process compliance, cost ratio and regime fit,
environment-weighted over a rolling window, with a `sustain` count before any recommendation. Demotion is automatic;
recovery and promotion never are.

**L.6 Broker learning** (`learning/broker.py`): from TCA to CERTIFIED / DEGRADED / EVENT_LIMITED / NO_SCALPING /
SUSPENDED and a liquidity multiplier the meta-labeller can only apply downward.

**L.7 Missed opportunities and counterfactuals.** Validity of a rejected setup is judged from its frozen ex-ante
snapshot hash (required; hindsight cannot rewrite the decision); the later path only scores the outcome over the
setup's own horizon window; a Risk Authority rejection is `GOOD_NO_TRADE` by definition. Counterfactuals are six
predefined variants on the same bar path, labelled `SIMULATED_EVIDENCE_NOT_CAUSAL` and aggregated only at capsule level.

**L.8 Evolution and curriculum.** Losing episodes cluster by context; a cluster with enough weighted evidence proposes a
versioned candidate capsule in RESEARCH (parent preserved, `supersedes` recorded). Candidates take the owner-signed
promotion path and the eight curriculum gates in order.

**L.9 Cycle integration.** `DecisionCycle` calls `LearningHooks.on_tca` after an entry fill and `on_review` after a close;
episodes are logged, health and broker profiles observed, and only `LearningBoundary`-checked adjustments reach the
meta-labeller or the registry (with a `CAPSULE_STATE` event, `authority: AUTOMATIC_DEMOTION_ONLY`).

**L.10 Reports and memory.** Daily / weekly / monthly reports are computed from the ledger (`learning/cycles.py`):
decisions, rejections, outcomes, net P&L, no-trade share, health, demotion recommendations, broker states, kill-switch
events, tickets, what changed, what to avoid, research needed. Hermes narrates them. Hermes persistent memory is a
continuity layer (`learning/memory_bridge.py`): `trading` namespace only, TTL per kind, credential-shaped text refused,
evidence citable only by 64-hex artifact hash, `authority = CONTINUITY_ONLY_NOT_EVIDENCE`.

---

## Part M — Development plan (state and next gates)

| Phase | Scope | State |
|---|---|---|
| 0 | Canon, Risk Authority, contracts, policy, skill | done (Rev 2) |
| A | Canonical hashing, event envelope, chained ledger, calendars, integrity, bars, FX costs, metrics | done |
| B | Features, regime engine, Tier-1 event matrix, MarketState | done |
| C | Capsule registry, five strategies, arbiters, rule meta-labeller, opportunity engine | done |
| D | Router, Paper / OwnerTicket / MT5-bridge / Deriv adapters, protection, reconciliation, TCA, review, VTIL admission | done |
| E | Shared decision cycle, backtest engine with DSR/PBO/walk-forward and leakage switch, session runner, CLI | done |
| F | Continuous learning engine + boundary wired into the cycle; gateway trading surface; learning A5 patterns | done |
| G | Trade book read model with confidence scores; overlay TRADES mode (past / current / potential) | done (Android build unverified in this container: no SDK; Kotlin logic compiled and tested with kotlinc) |
| 1 | Parquet lake + historical tick ingestion (Dukascopy / TrueFX); real-data backtests for the FX capsules | next |
| 2 | VTIL registry growth (≥ 40 resources), ≥ 8 ZSE golden cases | next |
| 3 | NautilusTrader donor gate (Python 3.12 runtime step, Context7 version facts), plane-2 RiskEngine | gated |
| 4 | PostgreSQL ledger; live MT5 bridge worker on `vati-mt5-worker` with mTLS | gated |
| 5–6 | Demo trading on MT5 / Deriv adapters with transport; failure-injection curriculum stage 8 | gated |
| ZSE-F001 | broker verification of session times, CGWT, foreign limits, stop/short rules | owner action |
| LIMITED_LIVE | owner-signed mandate; curriculum stages 1–7 passed; Claude/independent security review | A4 |

Rules for advancing: fresh tests and probes recorded in the evidence part; no phase marked complete from inspection;
no dependency pinned before its adoption gate.

---

## Part N — Evidence for Rev 4 (commands and outputs, 2026-09-16)

```text
$ python3 -m pytest -q                       # repository root: trading + backend + hermes policy + profile layout
317 passed in 16.80s

$ python3 -m pytest trading -q
194 passed in 14.80s

$ python3 -m pytest hermes/policy/tests -q
46 passed in 0.06s

$ python3 -m pytest backend/tests/test_trading_api.py -q
5 passed in 0.69s

$ python3 trading/tools/induce_gate_failures.py | tail -1
13/13 probes behaved as expected

$ node trading/vtil/tools/resolve_probe.mjs | tail -2
  "status": "GREEN"

$ PYTHONPATH=trading python3 -m vati zse-facts | head -1
== ZSE: live blockers = ['currency', 'timezone', 'session_open', 'session_close', 'settlement_days', 'board_lot',
   'counter_circuit_breaker', 'short_selling_allowed', 'stop_orders_supported', 'order_validity']
```

Induced failures for the learning boundary (a gate whose failure has not been induced is not known to work):

```text
# widen the clamp from > 1 to > 2 in trading/vati/learning/boundary.py, then
$ python3 -m pytest trading/tests/test_learning.py -q -k boundary
FAILED trading/tests/test_learning.py::test_boundary_accepts_only_reduce_only_adjustments_on_three_targets
1 failed, 10 deselected
# restore → 1 passed
```

Learning-in-the-loop evidence (from `test_learning.py`): a backtest with hooks writes one `TRADE_EXPERIENCE_ARTIFACT`
per closed trade, produces **no** live adjustment (0.3 × trades < 30 weighted samples) and identical metrics to the
same backtest without hooks; with 35 pre-seeded live process-breach observations per capsule, each capsule is demoted to
DEGRADED on its first close (`CAPSULE_STATE`, `AUTOMATIC_DEMOTION_ONLY`), the arbiter reports "not active" thereafter,
and the ledger chain and decision replay stay intact.

Module inventory (`trading/vati`): core 250 · market_data 334 · intelligence 409 · strategies 395 · arbiter 280 ·
risk 1273 · execution 946 · learning 939 · backtest 230 · app 289 · vtil 90 · zse 350 · observability 49 lines;
tests 15 files / 1983 lines.

---

## Part O — Supersession

- `docs/VAN_ADAPTIVE_TRADING_INTELLIGENCE_TECHNICAL_BLUEPRINT_REV2.md` (Rev 2 / 2.1) and `..._REV3.md` remain as
  provenance and detailed rationale; their decisions are carried here unless this document says otherwise.
- `docs/archive/VAN_ADAPTIVE_TRADING_INTELLIGENCE_TECHNICAL_BLUEPRINT_REV1.md` and
  `docs/archive/VAN_VATI_CONTINUOUS_LEARNING_MEMORY_RESEARCH_INTEGRATION_REV1_PROVENANCE.md` are provenance only.
- `docs/research/VATI_REV3_RESEARCH_CORPUS.md` remains the research corpus with verification states.
