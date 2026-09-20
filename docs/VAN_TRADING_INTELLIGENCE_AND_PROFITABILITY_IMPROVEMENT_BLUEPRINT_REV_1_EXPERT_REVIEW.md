# Expert review — VAN Trading Intelligence & Profitability Improvement Blueprint Rev 1

**Status:** Review. Not an authority document; it amends nothing.
**Reviewed document:** `VAN_TRADING_INTELLIGENCE_AND_PROFITABILITY_IMPROVEMENT_BLUEPRINT_REV_1.md` (65 sections + appendix, 3043 lines), supplied by the owner.
**Derived from:** `docs/VAN_TRADING_PROFITABILITY_ENHANCEMENT_PROPOSAL_REV_1.md` Rev 1.2.
**Repository state considered:** `main` @ `66e4e42` (`0.5.0-dev`, `SCHEMA_VERSION = 26`, `stack_lock.json` revision `5.2.0`).
**Reviewed at:** 2026-09-20.

## Verdict

This is the best-sourced document in this series. Every claim I sampled from §3's eighteen-point baseline is
accurate, and several are accurate to the field:

- `stack_lock.json` revision is exactly `5.2.0`, with `single_order_sender`, `single_sizer` and
  `single_transactional_authority` as described, and NautilusTrader named canonical;
- `DecisionCycle` is one instrument, `SessionConfig` carries one `symbol`, `SessionLock` exists by that name;
- `TradeIntent.correlation_multiplier` reaches the Risk Authority and is never populated;
- `deflated_sharpe()` returns a probability through `_norm_cdf`, and DSR/PBO are referenced only by tests;
- `required_features` is declared and unenforced; `MarketState`/`FeatureVector` carry no timeframe;
- the lake stores `M1/M5/M15/H1/H4/D1` and `lake_bar_source(...)` already takes a `timeframe` argument;
- TCA already feeds `BrokerExecutionProfile` and reduce-only `broker_liquidity`;
- strategy targets survive via `OpportunityAssessment.targets` (P1-TRADE-007);
- all five authority subjects §2.2 warns against duplicating exist, and Rev 5 owns the trading ones;
- `RiskAuthority.evaluate_safe` exists; `SessionService.build` and `cmd_serve` exist as §46 and §64 name them.

§2.1's refusal to self-admit authority, §47's counterexample matrix, §48's mutation list, §63's
baseline-preservation gates and §64's evidence manifest are the strongest parts, and I would not change them.

Three findings are blocking. All three are places where the document is internally consistent but collides with
a repository constraint it did not check. None requires re-architecting.

---

## Blocking findings

### B1 — §33 places trading truth in the wrong store, and the stack lock rejects it

§33 opens *"Baseline schema is 26"*. Schema 26 is `backend/van_gateway/storage/db.py` — the **VAN Gateway
SQLite** store. It then lists sixteen new tables, of which most are trading-domain decision truth:

```text
account_runtime_leases · candidate_opportunities · allocation_epochs
allocation_decisions · allocation_episodes · portfolio_dependency_snapshots
execution_policy_decisions · capital_budget_proposals
```

But `trading/architecture/stack_lock.json` declares:

```json
"single_transactional_authority": "PostgreSQL (SQLite in Phases 0-3)"
```

and `trading/vati/core/ledger_pg.py` already implements the hash-chained trading ledger on that store, with
`supabase/init/01_vati_ledger.sql.tpl` giving role `vati` no UPDATE/DELETE on `vati.events`.

Putting allocation, candidate, lease and capital-proposal truth into the gateway's SQLite creates a **second
transactional authority for trading** — the condition `trading/tests/test_stack_lock.py` exists to reject, and
the one §62 lists among the things that must be preserved (*"one transactional authority truth"*).

§33 must state, per table, which store owns it. My reading of the existing split: the gateway SQLite holds
owner-surface read models and gateway concerns; everything on the candidate → allocation → intent → decision
chain belongs on the VATI transactional authority alongside `vati.events`.

### B2 — The distributed lease in §13 cannot do what its own counterexample requires

§13 adds `account_runtime_leases` as a *"transactional cross-host lease"*, with this counterexample:

> Second VM starts same alias and its local flock succeeds. The distributed lease must still block order
> authority.

`deploy/van-trading-core/README.md:21` records the authority store as:

| Supabase (PostgreSQL 17, …) | `vati-supabase.service` | **loopback only** |

A second VM cannot reach the lease store at all. §13's own fallback — *"If transactional lease store is
unavailable, no new orders are admitted"* — means that VM fails closed. The outcome is right; the mechanism is
not the one being specified. Two consequences the blueprint must state:

1. **Today the counterexample passes for the wrong reason.** A test asserting it would be vacuous — it proves
   unreachability, not lease arbitration. §48's mutation `remove lease_epoch fence` would survive.
2. **The property inverts the moment Postgres is exposed beyond loopback**, which is precisely the topology in
   which a cross-host lease is needed.

Make reachability an asserted precondition of the lease design, and make the test distinguish *refused by
lease* from *refused because the store was unreachable*. Until Postgres is reachable cross-host, classify the
distributed lease honestly as `EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE` under §44's own rule rather than as a
working control.

### B3 — Allocator V0 ranks on a number whose contract does not contemplate this use

`trading/vati/arbiter/confidence.py:5-7` states the confidence score is:

> a *display and ranking* signal for the owner: it is labelled uncalibrated, it never sizes a trade, and it
> never feeds the Risk Authority.

§15 specifies Allocator V0 ranking on *"cost multiple, confidence score, regime multiplier, freshness and
dependency penalty"*. Under §15's sequential shared-heat procedure, ranking decides **which candidate reaches
the Risk Authority first**, and therefore which consumes scarce capacity — candidate #2 can be rejected
precisely because #1 took it.

So an uncalibrated score now materially determines which trade happens. It still does not size, and it is not
an *input* to the Risk Authority — but it selects the Risk Authority's input. §28's *"No statistical model may
directly raise live risk"* is satisfied literally while opening exactly the indirect path §65 rule 9 tells
implementers to hunt for.

"Ranking" in `confidence.py` plainly means ranking for owner display. Ranking for capital allocation is a
different act with a different consequence, and the document should not inherit the permission silently.
Two acceptable resolutions:

- **(a)** state explicitly that allocation ranking is an admitted use of an uncalibrated score, with the
  reasoning, and add it to `confidence.py`'s docstring so the two cannot drift; or
- **(b)** restrict Allocator V0 to deterministic non-confidence inputs — cost multiple, freshness, regime
  eligibility, dependency penalty — and defer confidence-weighted ranking to Allocator V1 behind §28's
  calibration gate.

(b) is more consistent with the rest of the document, and §15 already separates V0 from V1 on exactly this
axis.

---

## Significant findings

### S1 — §32 nearly doubles a closed enum on an append-only ledger, and hedges on whether it does

`EventKind` is a closed `str, Enum` with 23 members. §32 proposes ~20 more, then hedges: *"Add typed event
kinds **or equivalent payloads**"*. Pick one. On the Postgres ledger, role `vati` cannot UPDATE or DELETE
events, so a kind admitted and later renamed is permanent.

Separately, several proposed kinds are per-symbol-per-bar — `TIMEFRAME_MARKET_STATE`,
`MULTITIMEFRAME_MARKET_STATE`, `FEATURE_CONTRACT_VERDICT`, `CANDIDATE_OPPORTUNITY`, `CONFLUENCE_STATE`. At
four timeframes × N symbols × every bar these will dominate ledger volume and change its retention profile.
§57 says *"do not duplicate full market datasets into the ledger"*, which is the right instinct but is stated
about datasets, not about per-bar state events. State the rule the browser programme states as ADR-RB-008:
durable state *changes* are persisted; recomputable per-bar state is referenced by hash, not stored.

### S2 — `CandidateOpportunity` re-creates the exact surface of P1-TRADE-007

§63.8 correctly requires the candidate split to carry the exact target tuple, citing the regression where the
decision cycle *"used to throw these away and re-derive a single target from `expected_gross_move_pct`"*.

But §11.2 gives `CandidateOpportunity` **both** `targets: tuple[Decimal, ...]` **and**
`expected_gross_move_pct: Decimal | None`. Carrying both reinstates the precise condition the fix removed —
an `IntentFactory` implementer has both fields in hand and only a comment to tell them which wins.

Add a named test: `IntentFactory` never reads `expected_gross_move_pct` when `targets` is non-empty, with a
mutation that swaps the precedence and must be killed.

### S3 — `curriculum.py` becomes a third copy of the DSR threshold

§5.1 rightly says thresholds live in `trading/vati/validation/policy.py`, *"not scattered literals"*. It does
not address the literal that exists today:

```python
# trading/vati/learning/curriculum.py:21
CurriculumStage(1, ..., "expectancy ≥ 0.2R, PBO ≤ 0.10, DSR > 0.95 on backtest", ...)
```

That string is human-readable stage description rather than an enforced gate — but it is currently the **only
place in the repository carrying the correct threshold**, and once `policy.py` is canonical it becomes a third
copy that can drift. Source it from the policy object or state that it is documentation.

### S4 — Only one phase is marked as needing owner adoption; the others should say they do not

§53 Phase 11 correctly notes it *"requires explicit owner adoption because it introduces differentiated
strategy ceilings."* No other phase says either way. Given §2.2's Mode A / Mode B framing, an implementer could
reasonably read Phase 3 — certificates gating promotion — as an authority change requiring A4. It is not: it
strengthens an existing owner-signed gate rather than relocating authority. Saying so per phase prevents an
unnecessary approval cycle, and makes Phase 11's requirement stand out as the genuine one.

### S5 — Minor: §3 claim 3 is correct but reads as a stronger guarantee than it is

*"`SessionLock` enforces one live process per account alias on one host."* Accurate. `process_lock.py`'s own
docstring is more precise and worth quoting into §13, because it pre-states B2's problem:

> it is per-host, so it does not stop a second VM running the same alias, and it is advisory, so it binds only
> processes that ask. Both are acceptable here because the thing being prevented is an operator starting
> `serve` twice, not an adversary.

The existing code already knows its own limit. §13 should cite it rather than restate it.

---

## What this blueprint gets right

**§47's counterexample matrix** is the single most valuable section. *"Allocator: ranking logged, first-arriving
candidate still bypasses allocator into Risk Authority"* and *"Dependency engine: snapshot exists but
`correlation_multiplier` remains 1"* are the two failure modes most likely to actually occur, named before a
line is written.

**§48's mutation list** is concrete and each entry is killable. `treat missing covariance as zero dependency`
and `treat favorable risk-rejected candidate as allocator regret` are subtle and correct.

**§63's baseline-preservation gates.** Explicitly protecting PR #48's closures — owner authority verification,
live snapshot safety flags, margin gates, halt durability, restart-safe idempotency, live learning
reachability, target survival, ledger truth, T0 isolation — rather than assuming a refactor preserves them, is
the right instinct and is rare.

**§64's evidence manifest template** is usable as written: producer and consumer with path *and* symbol, a
runtime join with observations, a named mutation with its result, and `falsified_by`. That is what the
component ledger's five non-null fields actually need.

**§2.1.** *"It SHALL NOT be added to `owning_documents` merely because implementation cites it."* Correct, and
the Mode A / Mode B split gives the owner a real choice rather than a fait accompli.

**§59 and Appendix A.** Framing DSR, PBO, volatility-managed portfolios and the BIS FX structure evidence as
motivating hypotheses that *"do not override VATI validation or owner authority"* is the correct epistemic
posture, and the Moreira–Muir caveat (*"not evidence that a specific VATI capsule benefits"*) is exactly the
sentence that keeps a citation from becoming an argument.

**§62's closing directive** — that VAN may become more intelligent about where edge exists but *"may not turn
that intelligence into additional live authority by itself"* — states the invariant this whole programme
exists to preserve.

---

## Recommended disposition

1. Close **B1** by assigning each §33 table to a named store, with the candidate→allocation→intent chain on the
   VATI transactional authority.
2. Close **B2** by stating the reachability precondition, splitting the test's two refusal reasons, and
   classifying the cross-host lease honestly until Postgres is reachable cross-host.
3. Close **B3** by taking option (b) — deterministic Allocator V0, confidence-weighted ranking deferred to V1
   behind the calibration gate.
4. **S1**–**S4** are closable inside the document. S5 is a citation.
5. Leave §47, §48, §63, §64, §2.1, §59 and §62 untouched.

The phase order is sound and the dependency DAG in §54 is correct. With B1–B3 closed, this is implementable as
written.
