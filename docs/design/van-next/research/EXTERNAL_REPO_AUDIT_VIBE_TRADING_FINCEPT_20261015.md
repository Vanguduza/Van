# External repository audit — Vibe-Trading and FinceptTerminal (15 October 2026)

**Purpose:** find features in two public repositories that could improve VAN/VATI analysis or profitability.
**Status:** reference study under DEC-039. Nothing here is adopted. No code was copied, run or installed; both repositories were shallow-cloned read-only into an isolated scratch folder and read. Findings describe abstract patterns to reimplement natively in VAN, each needing its own Feature ID, tests and owner approval. Literal code or dependency adoption needs a separate owner decision and qualification.

## 1. Sources

| Repository | Revision read | Licence | What it is |
|---|---|---|---|
| [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | `29aa084fb7866087c612ddd55ef5449824374e22` (2026-10-15), package version 0.1.16 | MIT | Python research workspace: LLM agent with ~90 finance "skills", multi-agent "swarm" presets, 478-alpha factor zoo, backtest engines per market, broker connectors with paper/live guards, trade-journal analysis ("Shadow Account"), prediction-market data tool. ~2,060 Python files. |
| [Fincept-Corporation/FinceptTerminal](https://github.com/Fincept-Corporation/FinceptTerminal) | `3d8617cae3f13c93874d4bee4fb0f2846e9c83bc` (2026-10-13), release v4.5.1 | **AGPL-3.0 with a dual commercial licence.** The AGPL option is limited to personal, learning and academic use; "any business or internal company use" requires Fincept's commercial licence. | Native C++/Qt desktop terminal with embedded Python. The open build is a monthly-release edition; daily development is on a closed Enterprise build ($15–45/user/month). Analytics are mostly wrappers around established open-source libraries; news service with 59 public RSS feeds and simple signal heuristics; 37 persona/economic/geopolitics LLM agents. |

The marketing claims in the images ("does the same thing as Bloomberg", "AI agents debate before making a move") were not taken at face value. FinceptTerminal's own README says its open build uses "free public feeds, your own API keys"; it has no special data.

## 2. What VAN already does as well or better (no adoption)

| Area | External | VAN/VATI today | Verdict |
|---|---|---|---|
| Backtest overfitting control | Vibe: Monte Carlo, bootstrap, walk-forward | `vati/backtest/metrics.py`: deflated Sharpe, probability of backtest overfitting (CSCV), walk-forward; `vati/validation/policy.py` gates (PBO ≤ 0.10, ≥ 3 walk-forward windows) | VAN is stricter. Only Vibe's trade-sequence bootstrap of drawdowns is a small complementary idea (§3.8). |
| Live order authority | Vibe: mandate file, expiry, halt flag, account binding, paper/live discriminator | Owner-signed ECDSA authority tokens bound to act and subject, single-use, expiring; signed mandate with platform ceilings and hard-forbidden behaviours; Risk Authority; pre-trade gate; kill switch | VAN is stronger. Vibe's "paper vs live as a structural broker property, never a config flag" matches VAN's approach. |
| LLM grounding | Vibe `swarm/grounding.py`: prefetch real prices, forbid citing others | `vati/cognition/context.py`: sealed, versioned, fail-closed compiled context | Equivalent principle; VAN's is replayable. |
| Multi-agent debate | Vibe swarm presets (bull/bear → risk → PM); Fincept 37 persona agents ("Buffett", "Soros") | Models never hold trading authority; `blind_reviewer`, decision exam, attribution | **Anti-pattern for VAN as a decision input.** Debates and personas produce opinions, not evidence. At most a labelled research view. |
| Broker coverage | Vibe: IBKR, Alpaca, OKX/Binance, MT5 (bounded), others; no cTrader, Deriv or ZSE | MT5 bridge, cTrader Open API, Deriv, ZSE owner tickets | Nothing to add for VAN's venues. |

## 3. Candidate features worth reimplementing in VAN

Ranked by expected value to VAN's analysis and profitability.

### 3.1 Owner trading-behaviour diagnostics — high value
**Source pattern:** Vibe `tools/trade_journal_tool.py` profiles a trade journal (holding time, frequency, win rate, profit ratio, drawdown, time-of-day and instrument distribution) and flags four behaviours with severity and numeric evidence: **disposition effect** (closing winners early, holding losers), **overtrading**, **chasing momentum**, **anchoring**.
**Why it matters for VAN:** manual trading (blueprint §7.4) is where the owner's own habits cost money. VAN can compute these from its own ledger (no CSV import needed) and show them on the manual-trade history and review screens, with optional soft guards (for example a warning on the review sheet after a burst of trades, alongside the existing hard limits).
**VAN fit:** new read model over `origin=OWNER_MANUAL` trades; target VAN-NX-027. Native implementation; evidence-backed wording, no scolding.

### 3.2 Owner pattern extraction ("Shadow Account") — high value, with a correction
**Source pattern:** Vibe `shadow_account/` pairs round trips, clusters profitable trades, fits shallow decision trees per cluster, turns them into explicit entry rules, backtests the rules and scans today's bars for matches.
**Why it matters:** it can turn the owner's winning manual style into an explicit candidate strategy, and show "this setup matches your best past trades".
**Correction VAN must make:** the source filters to profitable trades only (`pnl > 0`) before learning, which describes winners without checking how often the same conditions also produced losers. VAN's version must learn on all trades and compare outcomes. The extracted rules then enter VAN's normal validation (deflated Sharpe, PBO, walk-forward) and owner-signed promotion; they never trade live directly. This is consistent with §7.4.10, which keeps manual trades out of automated strategy learning: extraction produces a *proposal*, not training data.

### 3.3 Prediction-market implied probabilities — high value for news and rate decisions
**Source pattern:** Vibe `tools/prediction_market_tool.py` reads Polymarket's public, no-key catalogue and order-book APIs (`gamma-api.polymarket.com`, CLOB price history) and treats the contract price as the market's implied probability. Fincept reads Manifold instead, noting Polymarket is geo-blocked in some places; Manifold is play money and not suitable as evidence.
**Why it matters:** for central-bank decisions, elections and geopolitical events there is often no economists' "consensus" number. A real-money implied probability before the event, and how it moves, gives VAN a market expectation to score surprises against and to feed the history profile (§8.4) and armed plans (§8.10).
**Checks before use:** reachability from `van-trading-core`, terms of use for automated reads, liquidity filters (thin markets are noise), and Kalshi as a second, regulated source to satisfy the two-source rule.

### 3.4 News attention detectors and owner keyword monitors — medium-high value
**Source pattern:** Fincept `NewsSignalDetector` (pure function, sub-millisecond): a category's article **velocity spike** (≥ 5 in the last hour and ≥ 3× the previous hour), **triangulation** (same headline from ≥ 3 sources), keyword spikes. `NewsMonitorService`: user-defined keyword monitors. Fincept deliberately removed a "geo convergence" signal because it grouped by the publisher's location and fired on every refresh — a useful anti-pattern to avoid.
**VAN fit:** add velocity and triangulation as deterministic inputs to story clustering and corroboration (§8.2–§8.3) and as caution triggers alongside the "unexplained move" detector; add owner keyword watchlists to the News screen. Thresholds must be recalibrated on VAN's own feeds.

### 3.5 Curated public RSS list — medium value (context tier only)
Fincept's news service references 59 public RSS feeds. Feeds not in VAN's earlier research include Dow Jones markets and world news (`feeds.a.dj.com`), Bloomberg markets (`feeds.bloomberg.com/markets/news.rss`), FXStreet (`fxstreet.com/rss/news`), Investing.com (`investing.com/rss/news.rss`), Seeking Alpha market currents, OilPrice, Mining.com, CNBC section feeds and the ECB daily reference rates XML. Feed URLs are public facts, not code. Each needs a terms-of-use check and a live probe; all are polled RSS, so they belong in the context and corroboration tier, not the fast trading tier (§8.10).

### 3.6 Look-ahead-proof research harness — medium value
**Source pattern:** Vibe's factor framework bans look-ahead at the operator layer, runs an AST "purity gate" over factor code, has a 300-row look-ahead sentinel test, and cuts network access during tests (`pytest-socket`).
**VAN fit:** add a look-ahead sentinel test and a network kill-switch to VATI's backtest and research test suites; both are cheap and protect every strategy's evidence. Worth adding regardless of the factor zoo.

### 3.7 Factor IC benchmarking (alive / reversed / dead) — medium-low value for VAN today
**Source pattern:** score many cross-sectional factors by information coefficient and information ratio, and classify each as alive, reversed or dead over a period.
**VAN fit:** VAN's universe (FX, metals, indices, a small ZSE/VFEX list) is narrow for cross-sectional factors. Useful mainly for ZSE/VFEX equities once licensed price data exists, and as a decay monitor for existing signals ("is this edge still alive?").

### 3.8 Smaller ideas
- **Correlation regime and "rewiring" score** (Vibe correlation-regime skill, edge density with hysteresis): a descriptive signal of markets moving as one bloc; could inform VATI's `PortfolioDependencyEngine` as a reduce-only input. Medium-low.
- **Trade-sequence bootstrap of drawdowns**: complements VATI's validation with a distribution of drawdowns rather than one path. Low effort.
- **Signed-value report check** (Vibe `report_audit`): verifies that losses stay negative in generated reports. VAN's brief wording checker (§8.6) should include the same test.
- **Durable hypothesis register**: VAN's research missions already cover this; low.

## 4. Licence and dependency notes

- **Vibe-Trading (MIT):** legally permissive, but DEC-039 still applies: patterns may be reimplemented natively; literal code adoption needs an owner-authorised dependency decision.
- **FinceptTerminal (AGPL-3.0 + commercial):** do not run, embed or adopt it in VAN. Its terms restrict the AGPL option to personal/academic use and require a commercial licence for internal company use, and AGPL obligations apply to network services. Its analytics wrap established libraries (portfolio optimisation, volatility pricing, performance statistics, time-series forecasting); if VAN needs any of those, evaluate the underlying library directly through the normal dependency process, not through Fincept.

## 5. Recommended next steps

| # | Feature | Proposed home in the blueprint | Effort |
|---|---|---|---|
| 1 | Owner trading-behaviour diagnostics | §7.4.10 + manual history/review screens (VAN-NX-027) | Small–medium |
| 2 | Owner pattern extraction → candidate strategy via normal validation | New requirement under DU-28; research lab | Medium |
| 3 | Prediction-market implied probabilities (Polymarket + Kalshi) | §8.2 source table, §8.4 history, §8.10 armed plans | Small–medium |
| 4 | News velocity and triangulation detectors; owner keyword watchlists | §8.2–§8.3, News screen | Small |
| 5 | Additional public RSS feeds (after terms check) | §8.2 context tier | Small |
| 6 | Look-ahead sentinel test and network kill-switch in VATI tests | Qualification lane | Small |

None of these is in the blueprint yet; adding them is an owner decision.
