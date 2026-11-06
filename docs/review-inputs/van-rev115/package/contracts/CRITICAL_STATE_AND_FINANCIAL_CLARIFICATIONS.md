# Technical Corrections and Unresolved Authority Boundaries — retained Rev 1.10 clarifications, operative within Rev 1.11

These are specification clarifications derived from the audit, not a live trading-policy grant. Existing owner decisions and signed mandates still govern. PRE-002 must reconcile any substantive remaining policy conflict before the affected backend unit starts.

## 1. Armed ticket readiness is not event confirmation

Proposed minimum `SIGNED → ARMED` readiness proof: verified owner/device signature, canonical grant digest, permitted pre-arm time window, correct event instance, active account/mandate, current stop/execution-policy revisions, healthy required feed connections, unused nonce, and no revocation or conflicting arming. Store the readiness snapshot and expiry. **Do not require the future actual release values before arming**, which would destroy the intended pre-armed feature.

`ARMED → USED` additionally requires the actual event/time conditions, both required independent sources delivered and agreeing where OD-13/OD-24 applies, fresh quote/spread/risk, current account/mandate/policy, and atomic nonce claim tied to a durable intent. Source-health deterioration or scope drift disarms/requires fresh validation. A signed but not ready ticket is displayed as signed/not armed, not executable.

The inherited approved transition list is archived by exact parent source. Adding this stronger readiness proof requires a separately proposed amended transition/guard lock and its owner/independent admission; it must not silently repin a signed parent file. BQ-003 must mutate each readiness element and observe failure. The source text's official-first exception for unscheduled headlines must be reconciled explicitly against its two-source acceptance tests: until resolved, **do not authorize single-source execution**.

## 2. Pending orders and protection

An order request includes its protective stop; that does not guarantee every venue accepted a stop or every later fill remains protected. Protection states are `REQUESTED`, `BROKER_CONFIRMED` and `UNCONFIRMED/UNKNOWN`, with source revision and exact position. Recovery re-reads, re-attaches where admitted, and invokes the authorized risk-reduction fallback at its deadline. Network failure prevents a success claim; a deadline schedules/escalates a bounded action rather than guaranteeing it succeeded within seconds.

Risk reservations cover resting and simultaneous sibling orders. Cancellation or modification can lose a race with a fill; the broker event wins and is reconciled. A take-back increments the management epoch and fences new automatic actions, but any already-sent action is reconciled rather than represented as magically cancelled. The final owner-visible status states which operations remain in flight.

## 3. Full monetary units and flow adjustment

Money, fees, collateral and executed quantities use integer minor units or declared decimal scale and currency/contract identity; conversions use authoritative timestamped rates and explicit rounding. Risk sizing includes contract value, price distance, quote/account conversion and venue steps—never a universal lots = currency risk / raw price-distance shortcut.

A deposit or withdrawal is an external cash flow, not P&L. Adopt a specified, tested flow-adjusted performance method. For a unitized baseline, a verified external flow at valuation NAV issues/redeems units at that NAV; trading return comes from NAV changes, not unit count. Alternatively use correctly timed subperiod returns. The accounting policy must define valuation ordering, simultaneous trade fills/fees, credits, reversals, transfers, negative or zero capital and unresolved flows. Synthetic examples are test fixtures, not account reports.

Removing cash should not fabricate a trading loss, but it can legitimately reduce collateral and increase exposure relative to remaining capital. Therefore tests distinguish flow-neutral performance from margin/risk eligibility: a withdrawal that would under-margin open exposure is refused; flow-adjusted historical drawdown does not grant spendable cash. Deposits never erase prior trading losses. Non-withdrawable credit is not risk capital by default. Unknown movements are quarantined for reconciliation, not guessed.

## 4. Effective-once effects under uncertainty

“Exactly once” is the intended business invariant, not an assertion that a network offers universal exactly-once delivery. Persist intent and outbox atomically before external send; bind stable provider idempotency where supported; claim/record outcome; reconcile on timeout before any retry; deduplicate callbacks; preserve reversals as compensating events. Unsupported provider idempotency demands a verified reconciliation protocol. If outcome cannot be determined, keep `OUTCOME_UNKNOWN` and block duplicate risk rather than falsely report success.

Withdrawal approval binds beneficiary digest, currency, amount, fees/net, quote revision, expiry and owner/account identity. Server-side transactional reservations must serialize competing withdrawal/order usage. A callback redirect or HTTP200 is not provider settlement. Transfers require separate debit and credit confirmation and partial/unknown recovery.

## 5. Learning and observations

Manual trade outcome records may include realized holding duration. Entry-time pattern extraction may not use that future value as an entry feature; only a predeclared planned horizon known at decision time is allowed. Split chronological datasets, poison future observations and block network calls in deterministic research tests. Winners and losers both remain. Diagnostic findings are descriptive; candidate strategy extraction does not promote an existing strategy or mint a grant.

## 6. Closed versus pending facts

The source file-availability gap for the pinned PR93 snapshot is closed; its causal semantic review is not. Selected MT5/TradingView account methods have been inspected; no competitor runtime or provider funding semantics were proven. Existing chart/account spike branches remain unqualified candidates. No prepared hash list is an owner signature. F15 and BG-001 remain `NOT_ISSUED` until independent evidence and real authority establish otherwise.

## Machine-readable readiness amendment

`NEWS_ARMING_READINESS_AMENDMENT_REV1_10.json` contains the exact proposed `SIGNED → ARMED` proof set, typed issuer/field definitions, preserved use proofs and explicit meaning of USED. It does not require future actual values before arming. It is not an owner-signed replacement of the parent guard list. `verification/verify_news_readiness.py` checks that the proposal has no missing or shortcut readiness guards; it cannot attest actual signatures or market inputs.
