# VAN/VATI Rev1.14 independent technical review → proposed Rev1.15

The recommended architecture is the existing VATI account authority, router and durable ledger extended with a finite parent/child supervisor and a versioned evidence reducer. Research uses the existing job/artifact owners; Jev remains a shared advisory service outside the critical protection path. Android consumes backend state and exact owner actions after the sole BG-001. No additional mandatory service, trading authority or truth store is justified.

This review found concrete contract and source gaps, and revised the specification and single plan. It did **not** implement VAN, merge source, execute a trading backtest, qualify a provider or issue F15/BG. All 1,544 application acceptance contracts are NOT_RUN. Source observations and documentary arithmetic do not establish profit.

## Priority findings

| ID | Priority / taxonomy | Exact evidence | Consequence and selected correction |
|---|---|---|---|
| R01 | P1 OPEN_GAP | Rev1.14 SO-CHILD transitions; probes DOC-EDGE-* | OUTCOME_UNKNOWN has no direct cancelled/expired recovery and cancel-request timeout has no unknown edge. Add authenticated recovery, retain partial fills/protection and release only reconciled unused reservation. VAN-RV-001. |
| R02 | P1 OPEN_GAP | verify_rev114.py state_checks; DOC-DISPATCH-POLICY returns **no findings** after removing POLICY_QUALIFIED with file identity checks off | Byte integrity is not semantic guard coverage. Require current qualified policy at dispatch and run independent mutations with locks resealed. VAN-RV-002. |
| R03 | P1 OPEN_GAP | CryptoVenueProfile zero tick/step and MATURE null cost records validate against supplied schema | Reject these simple contradictions in v2 record shape. Native resolvers still establish authenticity, scope, freshness and cross-record arithmetic. VAN-RV-002. |
| R04 | P1 OPEN_GAP | verify_rev114.py fixture_model; DOC-STALE-REVISION | Arrival after correction can replace newer parent contribution: example choice A at cursor 7 becomes B at cursor 8 solely from stale revision. Version precedence and conflict quarantine are explicit; actual durability still requires production integration. VAN-RV-003. |
| R05 | P1 CONTRADICTORY_IMPLEMENTATION | Opus a39f241b, trading/vati/execution/tca.py:compute_tca; cycle.py:434; SRC-TCA-DECOMPOSITION | Buy decision/arrival 100, submitted/fill 99, spread 2, qty 1: source arithmetic gives +1; direct fill-reference cost is −1 before fees. Preserve correct real units and prove decomposition, not an extra spread charge. VAN-RV-004. |
| R06 | P1 OPEN_GAP | Focus §5 gross/net wording; SPEC-GROSS-FEE | One gross unit filled minus 0.01 base fee is 0.99 inventory, not permission to buy another 0.01. Gross order budget and multi-asset accounting are separate. VAN-RV-004. |
| R07 | P1 CONTRADICTORY_IMPLEMENTATION | Opus style_selector.py:ExecutionStyleSelector._slice; SRC-SLICE-CAP | Qty 200 / depth 10 / cap .25 / max 8 yields 25-unit slices against 2.5 cap (10×). Count clamping cannot relax joint constraints. VAN-RV-005. This is a hand-derived source counterexample, not an executed router test. |
| R08 | P1 PARTIAL_IMPLEMENTATION | Opus policy.py:select/observe and cycle/account service; expanded caller receipts | Existing useful learning hooks are not proof of execution-policy feedback. No production ExecutionPolicyEngine.observe caller was established in inspected Opus/canon caller paths. Urgent `filtered or scored`, insertion-order fallback and mixed-median expected-cost defects remain. Complete actual consumer and later-selection causal test. VAN-RV-006 and retained VAN-SO-005…008/021. |
| R09 | P1 CONTRADICTORY_IMPLEMENTATION | Fetched review branch cbd059cf versus Opus a39f241b and canon dfc1557a | Newer review-input source is not a complete runtime baseline. Preserve Opus execution/ledger/lockouts and canon Jev/typed evidence/modes plus PR-only Muse/owner controls by function/caller. VAN-RV-006. |
| R10 | P1 OPEN_GAP | Historical strategy harness.run/load_bars, source report Method/Deviations, source TCA | Fixed JPY conversion, bid interpretation, selected OHLC path, raw/governed differences, short-window equivalence and calendar-year/peek checks limit inference. Earlier “no edge” is a scoped result, not a universal conclusion. Qualify evaluator before design optimization. VAN-RV-007. |
| R11 | P1 RUNTIME_CERTIFICATION_REQUIRED | CryptoVenueProfile and runtime qualification matrix | No eligible selected CEX target with matching, settlement and required protection proof is established. Static mocks and read-only success cannot close mandatory spot integration. VAN-RV-008. |
| R12 | P2 OPEN_GAP | SO-BINDING / SO-CANDIDATE lifecycle tables | Explicit expiry/preactivation revocation and failed/cancelled prospective branches were incomplete. Add durable transitions; no revoked fallback resurrection or grant-required continuation just to stop work. VAN-RV-002. |

P1 denotes a blocker for the affected implementation/economic acceptance, not a claim about current live loss. The decimal regex suspicion was rejected: 0.001 and 12.50 validate and an invalid backslash form does not. The raw positive control is retained.

## Scope and evidence

The supplied archive SHA-256 is `f12020bd852d2c3a6f8f8ee237f4cf7a3dba7665762d05f984f0eae271f4dc37`; all 377 manifest members matched. ZIP traversal/symlink/duplicate checks and CRC checks passed. The exact parent archive is bundled, including its earlier lineage. Hashes establish identity, not owner authenticity.

All seven supplied documentary commands passed: renderer, core checker, adversarial checker, package checker and news/forecast/high-value selftests. Independent probes challenge semantics and source arithmetic; their raw inputs/results/script are under `evidence/rev115/`. No result is labelled an application test. The parent selftest's catch-any-exception behavior is tightened so checker crashes no longer count as successful detection.

HTTPS Git refreshed 67 branch heads and 101 PR heads; the fetched snapshot contains 121 distinct head commits. Head-tree inventory is complete for those refs. The review materializes 211 selected source files with hashes and Python symbol locations, plus bounded caller searches and preservation decisions. It is **not a semantic review of every file in every head**. PR-only refs are included, but Git refs do not identify open/closed/merged PR state. The live advertised and fetched head receipts are separate; changes between them must not be concealed. A failed abbreviated review-branch lookup was corrected using the exact fetched ref; the authoritative fetched review head is cbd059cfb1ddfb80766bdebc2c74d3b25302a992.

Current DDS master source was fetched at b9cdb03c9d05335b0509e1cb16adaecb4dd9f075, including DIAL-FFDRM-R1 and PRD-DDP-R2. The user explicitly authorized Global DIAL. The callable tool inventory still contained no Global DIAL/Commander or discovery tool; the environment had no configured DIAL-related variable binding, and repository .mcp.json supplied local stdio definitions rather than an enrolled Global DIAL connection. This is a session capability limit, not missing owner permission. Native project UUID, current deployed source, live runtime gate and independent admission could not be refreshed through DIAL.

The packaged project UUID is retained as supplied, not newly attested. Historical tests/VM receipts remain dated to their own source. No VM, infrastructure, application or financial change was made.

## Selected architecture and acceptance

1. Existing ingestion preserves source identity, availability time, product units and authenticated fact history.
2. One account owner serializes cash/inventory reservations and RiskAuthority decisions for manual and automatic objectives.
3. One finite parent supervisor selects among feasible approved methods, works children through the existing router and preserves lifetime budgets, ownership epochs and uncertain exposure.
4. Actual adapter facts flow through reconciliation/protection and economic measurement. A registered durable reducer commits revision contribution, cursor and immutable snapshot atomically.
5. A later eligible decision consumes that exact snapshot under the approved update rule. No per-trade reapproval is needed inside a valid operational grant. Restart reproduces the decision; unchanged selection is valid when supported.
6. Existing bounded research workers consume mature cohorts, register all trials and build immutable candidates. Qualified evaluator → independent comparison → prospective evidence → authenticated promotion → atomic binding is required for policy evolution.
7. Optional Jev/model diagnostics are asynchronous. A model cannot extend risk, discard fills or become an order/protection dependency. Keep required model integrations and event laboratories even if no economic challenger qualifies.
8. Gateway exposes exact state, freshness, eligibility, reason, operation identity and receipt to existing contexts. All 82 backend and 12 verifier units finish before BG-001; all new native UI follows it.

The common causal acceptance must fail if the real outcome subscription is removed. Test actual process crashes around transaction/outbox boundaries, cancellations racing fills, stale revisions, wrong environment, forged promotion, missing real-provider proof and revoked fallback recovery. A fixture calling observe directly does not establish production reachability.

## Remaining gates and honest limits

PRE-001/PRE-002 still need native project identity, current PR state and independent full feature/caller admission. PRE-003 alone may issue F15 through its actual independent authority. Provider/account eligibility and permitted real matching access remain unresolved; this review does not create or fund accounts. BE-035 evaluator qualification precedes any new economic optimization claim. All implementation, provider acceptance, backend gate and later S24/Artemis testing remain work for the single generated plan.

No new historical experiment was run: the evaluator has unresolved semantics, a licensed immutable market dataset and complete experiment census are not established here, and no admitted DIAL research job was available. The REA portable archive contains competitor/interface evidence, not the required price parquet datasets. There are no fabricated per-opportunity/order/account results. `review/EVALUATION_PROTOCOL.md` states exactly how those outputs must be produced once prerequisites close.
