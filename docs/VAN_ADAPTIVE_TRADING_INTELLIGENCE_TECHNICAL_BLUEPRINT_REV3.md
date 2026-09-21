# VAN Adaptive Trading Intelligence (VATI)
## Technical Blueprint — Revision 3: research-grounded expert trader, with the Zimbabwe Stock Exchange module

> **Status (2026-09-16):** consolidated into `docs/VAN_TRADING_SYSTEM_BLUEPRINT_REV4_CONSOLIDATED.md`, which is now the active authority. This revision is retained as provenance and detailed rationale.


**Revision:** 3.0
**Date:** 2026-09-16
**Status:** Proposed Canonical Architecture / Development Authority Candidate; owner acceptance (A4) makes it locked authority.
**Relationship to earlier revisions:** Rev 3 is built from VAN's own research (corpus: `docs/research/VATI_REV3_RESEARCH_CORPUS.md`), not from the Rev 1 notes or the Rev 2.1 stack proposal. Where Rev 3 agrees with them it says so because the evidence agrees; where it disagrees it says why. Rev 2's Phase 0 code (`trading/vati/risk`), contracts, policy-hook prohibitions and the DIAL VEKL borrow remain in force and are extended here.
**Delivered with this revision:** `trading/vati/zse` (market facts with verification state, cost schedule, ZiG currency regime, liquidity model); `LossModel.ILLIQUID_EQUITY` sizing in the Risk Authority with board-lot rounding, ADV participation cap, liquidity haircut and an edge-versus-cost gate; ZSE sources/resources/task classes in the VTIL registry with a passing DIAL-resolver probe; stack lock 3.0.0 with ZSE data and execution layers; ZSE section in the `trading-intelligence` skill.

---

# Part A — What the evidence says makes an expert, dynamic trader

Twenty-nine claims from the corpus shape Rev 3. The eight that change the architecture:

1. **Cost is the first edge, and the one retail systems lose.** Spreads widen 3–10× in thin sessions and 10–20× in news spikes; most active retail traders pay 50–70% more execution cost than necessary through markup accounts, market orders and wrong-session trading; live EAs "bleed slowly" from slippage on pending entries. An expert system therefore models cost per session-minute and event proximity, prefers passive entries, and refuses any trade whose expected move does not clear a multiple of round-trip cost. Rev 3 makes this a Risk Authority check (`EDGE_BELOW_COST`), not a strategy preference.
2. **Drawdown control is what separates the paid from the unpaid.** Across prop firms, roughly 12% pass a challenge, about 7% ever get paid, 1–3% get paid consistently, and 60–70% of failures are daily or maximum drawdown breaches, not missed targets. The deterministic drawdown ladder, daily loss stop and consistency rules are therefore the load-bearing feature of a profitable system, which Rev 2 already built; Rev 3 adds a **prop-firm mandate profile** so the same governor can run a funded account under its rulebook.
3. **The durable edges are slow.** Trend following has decades of evidence (the SG Trend index constituents are the largest surviving CTAs) but with 15–30% return dispersion between managers in a single year; FX carry, value and momentum exist but show a ~30% out-of-sample decay and technical rules collapse from Sharpe 0.66 to 0.06 after costs. Intraday seasonality is robust but worth basis points per day. So the profit centre of VATI is **SWING and POSITION horizons** with a small, cost-disciplined intraday book; there is **no MICRO horizon** and no high-frequency ambition.
4. **Retail order flow is not a race VAN can win.** Signed flow, imbalance and toxicity are computed by every market maker with co-location; most imbalances are noise. Order flow is context for the meta-labeller and a confirmation feature, never a trigger. Consequently hftbacktest and L3 data are not adopted.
5. **Event trading is about the drift, not the spike.** NFP reactions are frequently V-shaped; the durable move develops 2–3 hours later; benchmark revisions create separate shocks. The event engine trades post-release drift with a mandatory quiet window, and prop-style blackout windows are the default around Tier-1 releases.
6. **Regime detection helps, and lies with confidence.** HMM ensembles improve backtests but rest on Gaussian and Markov assumptions. Regime output is a probability with hysteresis that scales risk down; it never scales risk up and is never sole authority.
7. **Most discoveries are false; LLMs are not signal generators.** The multiple-testing literature (deflated Sharpe, PBO, CPCV) is unambiguous, and the 2026 LLM-agent benchmarks show returns explained by passive exposure, a model that stops trading when tickers are anonymised, and a large sim-to-live gap. In Rev 3 the LLM (Hermes, Sonnet 5) does research synthesis, review, explanation and T2 assessment inputs with TTLs; it never produces an entry, a size or a promotion.
8. **Deriv synthetics have no edge to find.** Community bots run 55–63% win rates on fixed-payout contracts whose payout is below fair odds, and martingale "works until five or six losses". Synthetics stay in OBSERVE. Deriv's value to VAN is its real-market CFDs and its availability to a Zimbabwe-resident owner.

Venue reality for the owner (Zimbabwe resident): Interactive Brokers refuses Zimbabwe residents; MT5 brokers (Exness, HFM, XM, FP Markets, Eightcap, AvaTrade, FBS) and Deriv accept them; FP Markets also offers cTrader; OANDA's v20 API is the best-documented FX API but its availability must be checked. Retail forex trading is legal in Zimbabwe under RBZ exchange control; there are no locally licensed forex brokers.

# Part B — Rev 3 decisions (independent of the earlier notes)

| # | Decision | Evidence basis | Differs from Rev 2.1 notes? |
|---|---|---|---|
| D1 | Horizons: SCALP (cost-gated, k ≥ 3), INTRADAY, SESSION, OVERNIGHT, SWING, POSITION. **MICRO removed.** | A.3, A.4 | Yes: notes implied full microstructure stack |
| D2 | **Cost Model Authority**: every `SymbolContract` carries `round_trip_cost_pct` (session-aware for FX); the Risk Authority rejects `expected_gross_move_pct < 2 × cost`. | A.1 | New |
| D3 | Edge portfolio: (a) trend/momentum at SWING/POSITION across FX, gold, indices; (b) session-structure intraday (London/NY structure, spread-aware); (c) post-event drift; (d) carry/rates as a filter, not a trigger; (e) gold macro (real yields, USD); (f) **ZSE/VFEX fundamental, liquidity-premium and currency-regime strategies** (Part D). | A.3, A.5 | Adds ZSE |
| D4 | LLM role narrowed to research, review, explanation, T2 assessment with TTL and calibration; no entry/size/promotion. | A.7 | Stronger than notes |
| D5 | Kernel: NautilusTrader (event-driven, Rust core, deterministic). Research sweeps: vectorbt. Validation oracle: LEAN for Tier-A capsules only. **hftbacktest not adopted.** | corpus §1 | Agrees on Nautilus/LEAN; drops HFT tooling |
| D6 | Venue adapters, in order: (1) MT5 via Windows worker (broker availability); (2) cTrader Open API as the Linux-native alternative where the broker offers it (FP Markets); (3) Deriv real-market CFDs; (4) OANDA v20 if available to the owner. The community `mt5-connector` is a reference donor, not a dependency. | corpus §1 | Adds cTrader/OANDA path |
| D7 | Validation gates: dsr_probability >= 0.95, PBO ≤ 0.10 (CPCV), a one-switch decision-time leakage test, cost stress at 2×, LEAN reproduction for Tier-A. | A.7 | Same as Rev 2 §26, now with leakage switch |
| D8 | Data: Dukascopy + TrueFX tick history for FX/gold backtests; venue feed for execution truth; Databento only at Phase 10 for index/gold futures reference. | corpus §1 | Simpler than notes |
| D9 | **Minimum deterministic stack** for M1–M2: Nautilus + PostgreSQL + Parquet + OpenTelemetry/Prometheus/Grafana. Feast, MLflow, Redpanda, QuestDB, Temporal, ArcticDB are an optional "institutional profile" adopted only on a measured need (ledger replay latency, feature skew incidents, workflow failures), each with an owner-signed decision. | single-owner scale; licence classes | Yes: notes made them canonical |
| D10 | Prop-firm mandate profile: daily loss, max/trailing drawdown, consistency cap, news blackout, banned tactics, minimum trading days, encoded as a `TradingMandate` variant. | A.2 | New |
| D11 | Zimbabwe Stock Exchange and VFEX are first-class venues with their own loss model, cost schedule, currency regime and execution channels. | corpus §3 | New |

Everything in Rev 2 that the evidence supports stays: owner mandate as grant, [0,1] multipliers, venue round-down sizing, currency-leg netting, two-plane kill switch, unprotected-position block, VTIL on DIAL VEKL infrastructure, three-plane execution chain.

# Part C — Architecture deltas

## C.1 Cost Model Authority
`round_trip_cost_pct` on the contract is computed by the venue adapter from spread curve (by session-minute and event proximity), commission, expected slippage (volatility- and size-conditioned) and financing for the intended holding period; for ZSE/VFEX from `vati.zse.costs` including capital-gains withholding by holding period. The Risk Authority refuses an intent whose declared `expected_gross_move_pct` is below twice that cost. Strategies that cannot state an expected move are ineligible for LIMITED_LIVE.

## C.2 Prop-firm mandate profile
A `TradingMandate` with `max_daily_loss`, `max_weekly_drawdown` and a `consistency_cap` (largest day ≤ 30% of period profit), `tier1_event_policy: flat`, `weekend_hold_allowed: false`, and forbidden behaviours extended with `latency_arbitrage`, `tick_scalping`, `copy_trading`. The drawdown governor already halts at the mandate limit; the profile only changes numbers. Trailing-drawdown firms are modelled by tying `peak_equity` to the firm's high-water definition.

## C.3 Event engine
Tier-1 events carry a blackout (default 5 minutes before, 15 after), a quiet window before drift entry (default 45 minutes), and a drift-eligibility test (post-release move must be confirmed by 2-year yield direction for USD events). Spike-fade strategies are research-only until they pass the leakage switch and cost stress.

## C.4 LLM boundary (formalised)
Allowed outputs: research packets, confidence matrices, trade reviews, mandate proposals, natural-language explanations, T2 assessment fields (`regime_view`, `event_risk_view`, `disagreement`) with TTL ≤ 15 minutes for INTRADAY and ≤ 60 minutes for SESSION+. Forbidden: any numeric size, any order, any capsule state change, any change to a fact marked VERIFIED. The policy hook's `llm_broker_order` and `direct_broker_order` A5 patterns enforce the last two.

## C.5 Minimum deterministic stack (M1–M2)
```text
vati-core (Linux, Python 3.12): Nautilus TradingNode + VAN RiskGate + adapters (Deriv, cTrader) + MT5 bridge client
vati-mt5-worker (Windows): MetaTrader5 + terminal, mTLS
PostgreSQL (event ledger, mandates, capsules, decisions, receipts)  ·  Parquet lake (ParquetDataCatalog)
OpenTelemetry → Prometheus → Grafana
VTIL: borrowed DIAL VEKL resolver + Van registry (trading/vtil)
```
Institutional profile (optional, owner-signed): Feast, MLflow, Redpanda, QuestDB, Temporal, ArcticDB, LEAN runner, Databento.

# Part D — VATI-ZSE: study and trade the Zimbabwe Stock Exchange

## D.1 What the market is (facts with verification state)
Two exchanges matter: the **ZSE** (ZiG-denominated since 8 April 2024; ZWL retired 31 August 2024) and the **VFEX** (USD-denominated, offshore settlement allowed, regulator moved to the Victoria Falls IFSC on 5 May 2026, larger than the ZSE by market cap since H1 2026). **FINSEC** is an alternative platform reachable through C-Trade. The ZSE runs InfoTech's Capizar ATS (central order book since 6 July 2015); brokers' Capizar OMS exposes FIX. Settlement is T+3 through the Chengetedzai CSD; the board lot is 100 shares; orders are Day or GTC (30 calendar days). Per-counter circuit breakers are ±15% (price above one unit) and ±20% (below), with a 30-minute market cool-off on a 10% index move. Retail access is through ZSE Direct, C-Trade or a licensed stockbroker; **no retail API exists**.

Facts that could not be verified from primary sources at build time and are therefore **CONFLICTING/UNVERIFIED** in `trading/vati/zse/market.py`, which refuses a live mandate until they are VERIFIED with the broker: session times (10:00–15:00 vs 09:00–12:30 vs 09:00–13:00 vs 09:00–15:30), foreign-ownership limits (40%/10% vs 49%/15%), the CGWT rate (1%, 2%, or 4%/1.5% by holding period), stop-order support (assumed none) and short selling (assumed none).

## D.2 Why the ZSE is different, and what that does to the design
- **It is thin.** Econet's delisting on 31 March 2026 removed about a third of market cap and the most traded counter; April turnover fell 84%; on 3 September 2026 only 27 counters traded in 103 deals. A single print can gap through a software stop. Hence `LossModel.ILLIQUID_EQUITY`: maximum loss = stop fraction **plus** a liquidity haircut (half the median spread, a thin-trading penalty rising as fewer of the last 20 sessions traded, floored at one circuit band when fewer than half traded), shares rounded down to board lots and capped at 10% of 20-day ADV. An unknown ADV is `NO_TRADE`.
- **It is expensive.** Buy-side costs are 1.693%; sell-side 1.443% plus CGWT. At the punitive 4% short-hold rate the round trip is over 7% and the breakeven move above 7.5%; at 1.5% (≥ 270 days) it is about 4.4%. `vati.zse.costs` defaults to the punitive rate so expectancy is never flattered, and the Risk Authority's edge-versus-cost gate makes short-hold ZSE trading structurally ineligible unless the expected move is large. This is the single most important ZSE finding: **the ZSE is a position market, not a trading market.**
- **It is a currency instrument.** The ZiG-priced index rose 28% while the ZiG slid in August–September 2024 and 160% from its April 2024 rebase; the parallel premium peaked at 137.84% before the 27 September 2024 devaluation and sat near 20–35% through 2026. `vati.zse.currency` classifies the regime (ANCHORED < 10%, ELEVATED 10–35%, STRESSED 35–80%, DISORDERLY ≥ 80% or a step devaluation) and values every position in USD at both rates, sizing on the worse. DISORDERLY blocks new ZSE risk; STRESSED restricts to currency-regime strategies; VFEX (USD) is the natural hedge leg.
- **It can close.** The ZSE was shut by the Finance Ministry from 28 June to 3 August 2020 and fungibility of dual-listed shares was suspended; Old Mutual and PPC remain suspended. Exchange-closure and settlement-failure are first-class eventualities with runbooks: positions marked `FROZEN`, risk counted at full circuit-band loss, no netting against FX.
- **It is regulated by exchange control.** Non-resident purchases must be funded by inward transfer and repatriation is via authorised dealers, not automatic; insider-trading law exists with weak enforcement. Compliance facts live in the VTIL registry (`ref.rbz.exchange-control`, `ref.seczim.securities-dealers`) and are cited in every ZSE assessment.

## D.3 Data
| Need | Source | Tier | Cadence |
|---|---|---|---|
| Daily OHLC, volume, value, deals per counter; indices | broker/ZSE daily price sheets (PDF), africanfinancials (ZWG cents), Mansa/mystocks.africa APIs | T1/T2 | end of day |
| Historical seed | CC0 archive of price sheets 2020-01-11 → 2025-06-16 (63 counters) | T2 | one-off, then own capture |
| Company fundamentals, results, circulars, dividends | africanfinancials documents, ZSE announcements/RSS, Mansa fundamentals | T1/T2 | as published |
| ZiG official rate, MPS, exchange-control notices | RBZ | T1 | daily |
| Parallel rate | ZimRate/ZimPriceCheck-style trackers, press | T4 | daily, discovery only, corroborated by two trackers |
| CPI/inflation | ZIMSTAT | T1 | monthly |
| Calendar | results season, dividend dates, AGMs, index reviews, MPS dates, ZIMSTAT releases, VFEX migrations/listings | T1/T2 | maintained |

Rules: no scraping of ZSE Direct or C-Trade; display sites (afx.kwayisi) are read for cross-checks only; every price sheet is hashed and stored in the Parquet lake with its source; ZWL-era history (before 8 April 2024) is converted at 2498.7242 and flagged `PRE_ZIG` so no strategy trains across the rebase without explicit intent.

## D.4 Study mode (before any trade)
VATI-ZSE ships as a **research notebook first**: a VTIL-backed knowledge base of every listed counter (sector, free float, ADV, spread, dividend history, USD-IFRS financials, VFEX migration status), a regime-tagged history (dollarised 2009–2019, RTGS 2019–2020, closure 2020, ZWL hyperinflation 2020–2024, ZiG 2024–), an event calendar, and an analogue engine over past currency episodes. Hermes's `trading-intelligence` skill answers owner questions from this base with sources and verification states. Study mode is the default mandate mode (`OBSERVE`/`ADVISOR`) for at least one full results season before `LIMITED_LIVE`.

## D.5 Strategy families (all SWING/POSITION; each must clear the cost gate)
1. **Currency-regime rotation**: allocate between ZSE (ZiG), VFEX (USD) and USD cash on the premium regime and its trend; the ZSE leg is a currency hedge in ELEVATED, reduced in STRESSED, closed in DISORDERLY.
2. **Value/quality on USD-IFRS**: screen on USD-reported earnings, book value, dividend cover and free-float liquidity; hold ≥ 270 days to reach the lower CGWT tier.
3. **Liquidity-premium provision**: patient bid-side limit orders (GTC 30 days) in liquid counters when the spread and thin-trading penalty are wide, sized by ADV; never chase.
4. **Dividend capture with withholding maths**: 10% WHT (5% non-resident on VFEX), IMTT on transfers; only where the after-tax yield beats the round-trip cost within the holding window.
5. **Corporate-action events**: rights issues, VFEX migrations (SeedCo, Innscor, Simbisa, Padenga, National Foods, Axia precedents), delistings (Econet 2026), index reviews, REIT/ETF listings; long-only, event-window bounded.
6. **Post-results drift**: thin markets incorporate results slowly; test against the weak-form-efficiency evidence with the leakage switch before any promotion.
7. **ETF/REIT NAV discount**: Cass Saddle, Datvest, Morgan & Co ETFs and Tigere/Revitus/Eagle/Pfuma REITs versus published NAV, liquidity-adjusted.

Excluded by evidence: intraday ZSE trading (no real-time feed for retail, cost ≥ 4%), short selling (none), leverage (none), any strategy trained across the 2024 rebase without a PRE_ZIG flag.

## D.6 Execution channels
| Channel | Who sends | Action class | When |
|---|---|---|---|
| `OWNER_TICKET` | owner enters the Risk-Authority-approved ticket on ZSE Direct / C-Trade; VAN reconciles from CSD holdings and contract notes | A4 (per ticket) | default |
| `BROKER_INSTRUCTION` | owner-approved instruction to a licensed stockbroker (email/WhatsApp), VAN drafts and logs it | A4 (per instruction) | larger or VFEX orders |
| `DMA` | FIX via a broker's Capizar OMS | A3 under mandate | institutional option, later phase |

VAN never automates the retail apps and never contacts a broker without the owner's per-instruction approval. Every ticket carries the sealed `decision_hash`; reconciliation compares CSD holdings to the ledger after T+3 and raises `OWNER_OVERRIDE` or `SETTLEMENT_FAIL` events.

## D.7 Risk specifics
`ILLIQUID_EQUITY` positions count `shares × (stop distance + price × haircut)` in portfolio heat; ZiG and USD legs are tracked separately and the ZiG leg is additionally valued at the parallel rate; `max_positions_per_instrument` 1; per-counter ADV participation 10%; total ZSE book limited by a `max_illiquid_book_pct` mandate field (proposed default 25% of equity); weekend and closure risk always on. Kill-switch triggers added: `EXCHANGE_CLOSED`, `SETTLEMENT_FAIL`, `CURRENCY_DISORDERLY`.

## D.8 Feature plan
| Feature | Scope | Gate |
|---|---|---|
| VATI-ZSE-F001 | market facts verified with broker (session times, limits, CGWT, stop/short rules); `MarketSpec` moves fields to VERIFIED with source and date | `ZSE_SPEC.live_blockers()` empty |
| VATI-ZSE-F002 | data ingestion: price-sheet parser, Mansa/mystocks adapter, africanfinancials documents, RBZ/ZIMSTAT, parallel-rate corroboration; Parquet lake with PRE_ZIG flag | replay of 2020–2025 archive hashes identical; a ZWL-era row cannot enter a ZiG-era feature without the flag |
| VATI-ZSE-F003 | study notebook: counter knowledge base, calendar, regime history, analogue engine, VTIL registry growth (≥ 40 resources) | DIAL-resolver probe ≥ 8 ZSE golden cases green |
| VATI-ZSE-F004 | strategies 1–7 as capsules in RESEARCH → BACKTEST with cost gate, leakage switch, DSR/PBO | every capsule states expected move ≥ 2 × cost |
| VATI-ZSE-F005 | execution channels OWNER_TICKET and BROKER_INSTRUCTION with reconciliation and runbooks (closure, settlement fail, devaluation day) | induced failure: a ticket without a decision hash is refused; a closure event freezes and counts full-band risk |
| VATI-ZSE-F006 | LIMITED_LIVE on ZSE/VFEX under a study-season-complete mandate | one results season in ADVISOR with reviewed tickets |

# Part E — Evidence for Rev 3

```text
$ python3 -m pytest trading -q                                   → 138 passed  (full Van suite: 248 passed)
$ DIAL_REPO=../dial-new node trading/vtil/tools/resolve_probe.mjs → GREEN, 5/5 cases (VT-005 = ZSE study task)
   VT-005 classes ['ZSE_MARKET_RULES','ZSE_COMPLIANCE','ZIG_CURRENCY_REGIME','ZSE_MARKET_DATA']
          selected van.trading.rules.rev2-canon, ref.rbz.exchange-control, ref.zse.currency-rebasing-2024,
                   ref.zse.trading-procedures, community.zim.parallel-rate-trackers (corroboration only),
                   ref.vfex.investor-faq, ref.seczim.securities-dealers, ref.data.zse-daily-pricesheets-archive
$ python3 trading/tools/induce_gate_failures.py                   → 13/13 probes behaved as expected
   (the first run after the loss-model change aborted because the probe's import-line edit target had changed;
    the probe was repaired and re-run before this line was written — commit b0ffa81's message overstated this and
    the suite count; the correcting commit is the one that carries this text)
```

Worked ZSE sizing (test `test_illiquid_equity_sizing_reference`): equity ZiG 1 000 000, 0.5% risk = ZiG 5 000; entry 25.00, software stop 22.50 (10%), haircut 3% → per-share risk 3.25 → 1 538 raw → **1 500 shares** (15 board lots), risk ZiG 4 875. With ADV 12 345 the same intent is capped at 1 200 shares. A SHORT is refused (`SYMBOL_TRADE_MODE`); an intent expecting a 5% move is refused against a 7.14% round trip (`EDGE_BELOW_COST`).

What Rev 3 does not claim: no ZSE data has been ingested; no strategy has been backtested; the cost schedule's CGWT rate and the session times are unverified; VFEX rules are largely assumed from ZSE; no broker relationship exists; nothing here has traded.
