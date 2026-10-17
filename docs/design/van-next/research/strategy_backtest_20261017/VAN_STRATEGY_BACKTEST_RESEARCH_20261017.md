# VAN strategy backtest research — 17 October 2026

**Question (owner):** how strong is VAN's trading system: its forecasting, predictions and strategies?
**Status:** research only. Paper simulation. No broker, account, order or production change. Not a promotion record.

## Answer

The one strategy that could be tested faithfully, **FX-TREND-PULLBACK-01, has no edge after costs**. On EURUSD and GBPUSD it is break-even to slightly negative over 6¾ years. On USDJPY it is slightly positive, but it fails VAN's own validation gate. No strategy is ready to promote.

The research also found **four defects on the live trading path** and **two permanent lockouts**. All of them were reproduced, and they matter more than the strategy result.

**Update, same day (OD-38).** The owner ordered all five fixed. They are fixed in `trading/` on branch `ccr-8f1201e9-w1xm0r` (blueprint §7.4.15), and the study was rerun on the fixed engine with every workaround removed (see [After the fixes](#after-the-fixes-od-38)). The strategy conclusion stands: the trend pullback still has no edge. The London breakout can now be tested, and it loses clearly (−0.26 R and −0.23 R per trade). The governed accounts no longer stop trading for good.

## Method

- **Code:** VAN's own trading engine from `main` at `8eb1889822fc8a83f219977c15340172e16acd91` (`trading/`), run unchanged through its `DecisionCycle`, `RiskAuthority`, execution router and `PaperAdapter`. `harness.py` is the same loop as `vati.backtest.BacktestEngine.run`.
- **Data:** HistData.com 1-minute bid OHLC, via the Hugging Face export `vessel888/histdata_fx_1m`. Licence: "unknown". It was used as a research input only and is not stored in the repository.

  | File | SHA-256 |
  |---|---|
  | `eurusd.parquet` | `3a40d3b1…be4d5` |
  | `gbpusd.parquet` | `badf9117…808b` |
  | `usdjpy.parquet` | `fceedb6f…e8` |

  The data runs from 2000 to 21 March 2025. Dukascopy, the repository's own downloader, refused this environment (connection reset, then HTTP 429).
- **Bars:** H1, 1 July 2018 to 21 March 2025 (about 41,000 bars per pair). The first months are warm-up and also count as trades.
- **Costs:**

  | Pair | Spread | Slippage per side | Round-trip cost passed to the risk check |
  |---|---|---|---|
  | EURUSD | 0.8 pip | 0.2 pip | 1.0 pip |
  | GBPUSD | 1.2 pip | 0.2 pip | 1.2 pip |
  | USDJPY | 1.2 pip, slippage folded in | 0 | 0.8 bp |

- **Scoring:** VAN's own functions in `vati.backtest.metrics` and `vati.validation.policy` (`validation-policy/1.0.0`). The gate requires:
  - DSR probability ≥ 0.95;
  - PBO ≤ 0.10;
  - at least 30 trades;
  - at least 3 walk-forward windows.

  Each calendar year is one window. The strategy has fixed parameters, so nothing was fitted. Trials = 3 (one per pair).

### Deviations from the stock engine

Each deviation was measured before it was used.

| Deviation | Why | Proof that it does not change results |
|---|---|---|
| The cycle sees a trailing 400-bar window, not the full history | `compute_features` recomputes the EMAs over the whole list on every bar (quadratic) | 2,500 EURUSD bars: 80 trades and identical R multiples with the full history and with the 400-bar window (`runs/eq_full.json`, `runs/eq_w400.json`) |
| The per-decision `verify_chain()` is replaced by one full verification at the end (`BT_FAST_CHAIN`) | Finding 1 (below). A 3,000-bar run took 220 s against 27 s for 1,000 bars | 1,500 bars: 48 trades, P&L −186.64, identical decisions both ways (`runs/eq_slow.json`, `runs/eq_fast.json`). The chain verifies `true` at the end of every run |
| `--raw`: consecutive-loss and drawdown-tier lockouts disabled | Finding 5 (below). With them on, every run stopped trading for good (in 2018 or 2021) | Not equivalent by design. This measures the strategy, not the account rules |
| Signal prices aligned to the tick, stop rounded toward entry (`BT_TICK_ALIGN`) | Finding 3 (below) | Removes only the `STOP_WIDER_THAN_APPROVED` refusals |
| USDJPY slippage folded into the spread | Finding 2 (below) | Same cost per side; lets the orders fill |

**Leakage check.** The engine's `peek` mode feeds the next bar in, so the result should change. It does (4,000 EURUSD bars): net −46.2 without peek against −51.4 with peek, 122 trades each. The engine is sensitive to lookahead, and peeking did not improve this strategy.

## Results: FX-TREND-PULLBACK-01 (H1, 2018-07 to 2025-03)

| Pair | Trades | Win rate | Expectancy | Total R | Profit factor | Max drawdown | Net on $10k | Years positive | DSR probability | PBO | Gate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| EURUSD | 1,129 | 49.5% | −0.008 R | −8.9 | 0.99 | 8.4% | −$85 | 4/8 | 0.15 | 0.29 | **FAIL** |
| GBPUSD | 1,126 | 48.8% | −0.007 R | −8.4 | 0.97 | 7.2% | −$289 | 3/8 | 0.16 | 0.29 | **FAIL** |
| USDJPY | 975 | 50.8% | +0.021 R | +20.8 | 1.09 | 2.7% | +$856\* | 5/8 | 0.68 | 0.29 | **FAIL** |

\* The USDJPY dollar P&L uses a fixed conversion of 667 USD per yen unit per lot. The R figures are unaffected.

Expectancy by year, in R:

| Year | EURUSD | GBPUSD | USDJPY |
|---|---|---|---|
| 2018 | −0.047 | +0.064 | −0.003 |
| 2019 | +0.035 | −0.015 | +0.053 |
| 2020 | +0.063 | +0.043 | +0.021 |
| 2021 | −0.072 | −0.106 | +0.064 |
| 2022 | +0.088 | +0.068 | +0.012 |
| 2023 | −0.076 | −0.020 | +0.007 |
| 2024 | −0.067 | −0.048 | −0.008 |
| 2025 Q1 | +0.008 | −0.022 | −0.016 |

**What this means:**
- The rule wins about half the time with a 3-ATR target against a stop of up to 2 ATR. Spread and slippage take the edge to roughly zero.
- No year is consistently positive.
- USDJPY is the best case, but a DSR probability of 0.68 means it is not distinguishable from luck at the policy's 0.95 bar.
- **Not tested:**
  - **FX-LONDON-BREAKOUT-01:** cannot be simulated faithfully (finding 4).
  - **FX-EVENT-DRIFT-01:** there is no historical NFP/CPI/FOMC release calendar in the repository.
  - **GOLD and the ZSE strategies:** remain in `RESEARCH` without data here.

## Findings on the trading system

Each was reproduced in this run. Paths refer to `trading/` on `main`. All five are now fixed (OD-38); see [After the fixes](#after-the-fixes-od-38).

1. **Decisions get slower the longer VAN runs.**
   - `DecisionCycle._risk_store_ok` (`vati/app/cycle.py:183-193`) calls `ledger.verify_chain()` on every risk snapshot. That re-hashes the whole ledger from genesis.
   - The live service builds the same cycle (`vati/app/service.py:204`), and `vati/app/account_service.py:598` does the same.
   - Profile of a 2,000-bar run: 149 of 164 s were spent in `verify_chain`. Run time grew 8× for 3× the bars.
   - **Fix:** verify incrementally from the last verified head.
2. **Slippage caps are absolute price units, so JPY (and likely gold) orders cannot fill.**
   - `LIMIT_AT_TOUCH` caps slippage at `0.0001` (`vati/execution/policy_templates.py:76`; the others are 0.0002 and 0.0005).
   - That is 1 pip on EURUSD but 0.01 pip on USDJPY. With 0.2 pip of slippage, every USDJPY order was refused (`reject_reason="max_slippage"`). The first run had 11,379 approvals and 0 trades.
   - **Fix:** express the caps in pips or ticks per instrument.
3. **Tick rounding can widen an approved stop.** After approval the stop is quantised away from the entry. The pre-trade check then refuses with `STOP_WIDER_THAN_APPROVED` (`vati/execution/pretrade.py:255-260`), for example 0.00526 against an approved 0.005256. That hit 72 London-breakout orders in 3,000 bars. **Fix:** round stops toward the entry, or approve on the quantised prices.
4. **The order type is hard-coded to LIMIT, and the paper simulator fills limits at the requested price.**
   - `DecisionCycle.step` sends `entry_type="LIMIT"` whatever the signal asks for.
   - The London breakout asks for a STOP entry above the range. As a LIMIT it is either refused (`PRICE_OFF_MARKET`, 87 in 3,000 bars) or would buy before the breakout.
   - `PaperAdapter` fills a LIMIT at the requested price whether or not the market traded there (`vati/execution/paper.py:57`). Breakout and passive-limit strategies (ZSE liquidity provision) therefore cannot be backtested faithfully.
   - **Fix:** honour `Signal.entry_type`, and make the paper adapter fill only when the bar's range reaches the price.
5. **Two lockouts are permanent once triggered.**
   - `consecutive_losses` resets only on a win (`vati/app/cycle.py:567`). Once it reaches `max_consecutive_losses` (4), no trade can win, so the strategy never trades again, until a process restart silently resets the in-memory counter to 0.
   - The default drawdown tier at 4% allows only `CERTIFIED_LIVE` strategies (`vati/risk/mandate.py:90-93`). Peak equity is never regained without trades, so a DEMO strategy is blocked indefinitely.
   - In this study, the first stopped trading after 13 trades in 2018, and the second stopped the EURUSD and GBPUSD pullback runs in 2021.
   - These may be intended as circuit breakers that need the owner. If so, the reset path should be an explicit owner action, not a restart.

## Recommendations

1. Fix findings 1–4 on the live path before any strategy is promoted. Each fix needs a negative test (break it on purpose and watch it fail).
2. Decide (owner) whether the lockouts in finding 5 are intended, and give them an explicit, owner-signed reset.
3. Keep FX-TREND-PULLBACK-01 in DEMO. It does not pass VAN's own validation gate. This is the kind of result the continuous development loop (blueprint §7.4.14, OD-37) should produce automatically, and it should send nothing to the owner until a candidate passes.
4. Before judging the London breakout or event drift, fix finding 4 and add a historical release calendar.

## After the fixes (OD-38)

**Engine:** `trading/` at commit `d6c5681` on `ccr-8f1201e9-w1xm0r` (fixes 1–5 plus the two follow-ups: thesis and TCA on a fill from rest, entry type on the live path). Same data, bars, costs, harness loop and scoring as above.

**Workarounds removed:**
- no `BT_FAST_CHAIN`: the ledger is verified on every decision, as in production;
- no `BT_TICK_ALIGN`;
- USDJPY slippage is no longer folded into the spread (0.8 pip spread plus 0.2 pip slippage, the same cost per side);
- governed runs keep every lockout on.

The only deviation left is the 400-bar window (shown equivalent above).

### Each fix, measured

| Fix | Before (`main`) | After | Evidence |
|---|---|---|---|
| 1 Incremental ledger check | 1,500 bars with per-decision verification: 54.0 s (7.0 s with it switched off) | 1,500 bars with per-decision verification: 10.5 s, same 48 trades and identical R multiples. A full 41,000-bar run with verification on completes in 6–12 min (4 runs in parallel), and every chain verifies `true` | `runs/eq_slow.json`, `runs/eq_fast.json`, `runs_after_fixes/eq_fixed_1500_raw_idle.json` |
| 2 Price-relative slippage | Every USDJPY order refused with real slippage | USDJPY fills with 0.2 pip slippage: 976 trades (975 with the old workaround) | `runs_after_fixes/USDJPY_*` |
| 3 Stop rounding | 72 `STOP_WIDER_THAN_APPROVED` in 3,000 London-breakout bars | 0 in all ten full runs, without tick alignment | `decisions` in each run file |
| 4 Entry type and resting orders | London breakout sent as LIMIT; 87 `PRICE_OFF_MARKET` in 3,000 bars | Sent as STOP, rests until price trades through, 0 `PRICE_OFF_MARKET`. STOP fills land a median 0.028 R beyond the trigger (p90 0.082 R; spread plus slippage), so the result is not a fill artefact | `probe_stop_fills.py` |
| 5 Recoverable lockouts | Governed pullback runs stopped for good in 2018 or 2021 | Governed pullback runs trade every year to 2025 (1,117–1,118 trades on EURUSD/GBPUSD, 970 on USDJPY), with 136–257 entries refused during cooldowns | `runs_after_fixes/*_governed.json` |

### FX-TREND-PULLBACK-01 on the fixed engine (lockouts off, 3 trials)

| Pair | Trades | Win rate | Expectancy | Total R | Profit factor | Max drawdown | Net on $10k | Years positive | DSR probability | PBO | Gate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| EURUSD | 1,129 | 49.6% | −0.008 R | −8.5 | 0.99 | 8.4% | −$78 | 4/8 | 0.17 | 0.40 | **FAIL** |
| GBPUSD | 1,123 | 48.7% | −0.009 R | −10.4 | 0.97 | 7.7% | −$346 | 3/8 | 0.15 | 0.40 | **FAIL** |
| USDJPY | 976 | 50.7% | +0.017 R | +16.7 | 1.08 | 3.1% | +$734 | 5/8 | 0.63 | 0.40 | **FAIL** |

These are within a few hundredths of an R of the original study (−0.008, −0.007, +0.021). The workarounds did not change the conclusion. Small differences come from position sizes that now follow unaligned stop distances. PBO moved from 0.29 to 0.40 on three trials; the estimate is coarse with so few trials, and both values fail the 0.10 bar.

### FX-LONDON-BREAKOUT-01, now testable (lockouts off, 2 trials)

| Pair | Trades | Win rate | Expectancy | Total R | Profit factor | Max drawdown | Net on $10k | Years positive | DSR probability | Gate |
|---|---|---|---|---|---|---|---|---|---|---|
| EURUSD | 333 | 35.4% | −0.262 R | −87.3 | 0.15 | 30.8% | −$3,075 | 0/8 | 0.00 | **FAIL** |
| GBPUSD | 314 | 41.1% | −0.233 R | −73.1 | 0.20 | 25.6% | −$2,551 | 0/8 | 0.00 | **FAIL** |

Every year is negative on both pairs. On H1 bars, with these costs, the breakout as written loses about a quarter of its risk per trade. When all five configurations are scored as one trial set, the breakout's very negative Sharpe ratios dominate the trial variance (DSR 0.00 for every run). The two families are therefore scored separately, as in the original study.

### Governed runs (every lockout on)

| Run | Trades | Expectancy | Max drawdown | Traded until | Refused by lockouts |
|---|---|---|---|---|---|
| EURUSD pullback | 1,118 | −0.006 R | 5.8% | 2025-03 | 257 cooldown |
| GBPUSD pullback | 1,117 | −0.003 R | 5.2% | 2025-03 | 154 cooldown |
| USDJPY pullback | 970 | +0.007 R | 4.9% | 2025-03 | 136 cooldown |
| EURUSD breakout | 77 | −0.339 R | 6.0% | 2020-01 | 38 cooldown, then 6,827 at the suspending drawdown tier |
| GBPUSD breakout | 129 | −0.224 R | 6.1% | 2021-08 | 23 cooldown, then 4,682 at the suspending drawdown tier |

- **The pullback runs show the fix working.** Cooldowns pause a losing streak, probation trades at half size, and trading resumes by itself. Compared with lockouts off, the drawdown is lower on EURUSD (5.8% against 8.4%) and GBPUSD (5.2% against 7.7%). On USDJPY it is higher (4.9% against 3.1%), and the run gives up part of its small gain (+0.007 R against +0.017 R): probation's half size after a streak also halves the recovery trades.
- **The breakout runs show the hard stop working.** A strategy that keeps losing reaches the 6% suspending tier and stops. It resumes only through an owner-signed `drawdown-resume`, as §7.4.15 intends. That is the right outcome for a strategy with this result.

### Conclusions after the fixes

1. The trading path now does what the strategies ask: it fills JPY, keeps approved stops, sends STOP orders as STOPs, and verifies the ledger without slowing down.
2. Neither FX strategy has an edge. Keep FX-TREND-PULLBACK-01 in DEMO. FX-LONDON-BREAKOUT-01 should not be promoted. As written it is a clear loser and is the first candidate for the continuous development loop (§7.4.14).
3. Still untested: FX-EVENT-DRIFT-01 (no historical release calendar in the repository) and the gold and ZSE strategies (no data here).

## Reproduce

1. Unpack `trading/` from `main` at `8eb1889` into `van/trading` next to `harness.py`.
2. Put the three parquet files in `data/`.
3. Install `pandas`, `pyarrow` and `pytest`. The harness imports the test owner key from `trading/tests` to sign a paper mandate.
4. Run the original study (engine from `main`):
   ```
   BT_FAST_CHAIN=1 BT_TICK_ALIGN=1 BT_JPY_FOLD=1 python3 -I harness.py --symbol EURUSD --strategy FX-TREND-PULLBACK-01 --raw --out runs/EURUSD_pullback.json
   python3 -I analyze.py runs/*_pullback.json
   ```
5. Run the rerun after the fixes: unpack `trading/` from `d6c5681` instead, and run with no environment flags. Use `--raw` for the strategy measurement and leave it out for the governed run:
   ```
   python3 -I harness.py --symbol EURUSD --strategy FX-LONDON-BREAKOUT-01 --raw --out runs_after_fixes/EURUSD_FX-LONDON-BREAKOUT-01_raw.json
   python3 -I analyze.py runs_after_fixes/*PULLBACK-01_raw.json
   python3 -I analyze.py runs_after_fixes/*BREAKOUT-01_raw.json
   python3 -I probe_stop_fills.py
   ```

Each full run takes about 4–5 minutes. Per-trade outputs are in `runs/` (original) and `runs_after_fixes/`. The scored results are in `RESULTS_TREND_PULLBACK.json`, `RESULTS_AFTER_FIXES_TREND_PULLBACK.json` and `RESULTS_AFTER_FIXES_LONDON_BREAKOUT.json`.
