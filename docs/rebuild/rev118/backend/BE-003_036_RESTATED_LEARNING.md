# BE-003/009/010/012/036 candidate: native parent economics and restated learning

This implements a candidate portion of Rev1.18 section 8.3 and the original development units. The admitted package, 131 unit identities, dependencies, owner authority and acceptance registry are unchanged. No independent gate, unit completion, production activation or profitability claim is issued.

## Actual production consumers

Both existing runtime constructors already bind learning to native account/environment evidence. Their close hooks and cold replay now construct `RestatedTradeProjection`; periodic heartbeats and account snapshots catch up later analytical publications. Existing `GET /v1/trading/accounts` and `/v1/trading/portfolio` carry the account snapshot's `restated_learning` and `learning_history_issue`. This is an extension of existing owner readback, with no new UI or action authority. The account projection reports its original journal hash, publication time and recorded-snapshot freshness, and refuses another account/cohort or a claimed selection authority.

The real paper adapter, approved native money-risk record and account close producer are exercised together. A complete parent, including multiple reductions, contributes once. Native approved money risk is reconstructed from its sealed decision and exact snapshot; a changed active stop or consumer-configured equity cannot change its denominator. Currency and environment must match native settlement evidence. PnL sign remains labelled a proxy, not causal validation of a trading setup.

## Parent cash and unresolved financial history

The previous PnL reader used only the last reported close row; two real paper reductions reproduced a reported -114 against actual parent cash of -28. Paper rows now explicitly identify execution cash deltas with stable local close IDs; all parent deltas are summed, exact repeats deduplicated, and recorded fees/carry applied once. Different payloads for one identity, mixed snapshot/delta semantics, missing identities or mixed bases remain unknown. Unlabelled historical parent snapshots retain their historical last-snapshot convention; they are not blindly summed. Invalid reduction quantities cannot alter cash or positions.

Both actual close paths preserve loss history and latch reconciliation when money is unknown. This does not interrupt protective exits. The independent risk-snapshot refusal survives a cleared kill switch; cold recovery refuses explicit unknown economic records instead of folding their display placeholder as a settled outcome. Analytical revisions have a separate event kind and cannot become a second financial close or clear a financial fence. The existing loss governor already left a zero-PnL streak unchanged; the demonstrated defect was the missing unknown-money fence, not a proven zero-reset defect.

## Replay views and atomic persistence

Original review version 5.2 records explicit revision zero, native maturity and money provenance. `TRADE_REVIEW_REVISION` is a separate native-producer-only analytical channel. Source revision and predecessor digest determine replacement; journal position measures publication availability, never venue ordering. A revision subtracts its old parent contribution before adding the replacement. Exact duplicates and later-published older revisions do not create independent samples. Equal-revision conflicts or a missing/incompatible predecessor quarantine that parent. `AS_DECIDED` retains the original contribution while `RESTATED_ANALYSIS` changes.

Applied references, parent contributions, aggregate state and consumed journal cursor share one sealed snapshot. Its immutable history and current pointer commit atomically in the existing SQLite/PostgreSQL ledger database under the journal writer lock. PostgreSQL uses the logical ledger namespace as well as account, environment, population, code version and numerical precision. No extra financial ledger, order writer, host grant or external service is introduced. Compare-and-swap prevents a stale consumer from overwriting progress, including during cache recovery. A lost commit response loads the committed version and does not add a second contribution.

A damaged cache rebuilds only from a verified native journal, retaining old checkpoint history. Corrupt source refuses reconstruction. The explicit 16 MiB snapshot capacity fails visibly and fences new risk through the existing learning recovery issue; it does not truncate observations or restart with a healthy empty state. Performance/retention qualification of a large history remains outstanding.

## Evidence and limits

See `../receipts/RESTATED_LEARNING_SOURCE_20261022.json` for exact source hashes, full real-PostgreSQL trading run, gateway endpoint tests and induced failures. Source tests cover actual paper producer/close/replay/readback, revision conflict/maturity/currency, original-view preservation, cold connection, namespace isolation and all three storage crash windows. Correction records in those tests are explicitly native-envelope source fixtures.

Only deterministic paper currently supplies the new finality labels. Real MT5/Deriv/CEX/provider settlement and correction identity, authoritative resolution of conflicting native revisions, larger population/policy/epoch semantics, long-history capacity and independent qualified positive adaptation remain work in these same canonical units. Unsupported providers stay maturity-pending; neither a finite number nor an LLM explanation grants finality or policy authority. This reducer is analysis-only and cannot change risk, a mandate, a strategy, an order or an adaptive policy.

## Native voice checkpoint retained

Hosted source `2fb3c8c6` / run `39772893692` tests a merge tree identical to that source. Instrumentation collected 22 tests: 18 passed, zero failed, four existing core-artwork skips. Both real offline answer and cancellation/replacement cases passed through pinned native VITS synthesis and application playback completion. All 374 original mutation identities were detected; PostgreSQL/public trading/117 voice-source checks pass. The workflow still fails on the unprovisioned private DDS CI key and absent trusted-main bootstrap checker. Neither is bypassed.

The previous `9e05f602` native run was cancelled by CI concurrency when `2fb3c8c6` was pushed; it has no completed native result. Earlier actual failures remain in their receipts. Emulator evidence is separate from physical S24, Artemis, acoustics, production connectivity, signing and release acceptance.
