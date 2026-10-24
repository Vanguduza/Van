# Candidate single-symbol native startup recovery

The actual `SessionRunner.startup` default now reads durable native history instead of supplying an empty ledger-position list. The existing service acquires its runtime lease before that consumer runs. It reads one current native position snapshot for both reconstruction and reconciliation, checks the actual account alias/currency and a genuine boolean verification fact, and reports unresolved native orders explicitly. An empty restarted paper process can no longer stand in for a flat account when durable open, pending or unknown order evidence exists.

## Original setup before dispatch

`DecisionCycle` publishes a non-secret `ENTRY_CONTEXT` in the existing ledger before calling the actual router. It binds the exact risk decision, account, symbol, strategy/direction, modelled cost, approved risk fraction, session/regime/event state, targets and process flags. This publication itself cannot place an order. An original sealed native command must exist before recovery can associate any exposure with it.

Recovery accepts only a unique matching context available before the first original native command in journal order. A backdated context appended later cannot rewrite the setup. Missing, conflicting, foreign-account or different-decision contexts remain unresolved. The native risk, thesis and cost evidence must also exist for healthy automatic continuation; today's config and P&L sign cannot supply missing historical facts.

## Actual state and protection

The shared native history verifies command/account/venue/correlation/seal/quantity and current position identity. Recovery reconstructs the actual current entry quantity, local protective controller, original thesis and available native health excursions. Current venue stop readback is required for venue protection; software protection uses its durable original contract. Recovery sends no entry, close or replacement order.

A genuine complete restart restores readiness without duplicating an original command. A confirmed native rejection with zero fill is distinct from an accepted pending order or a lost reply after an effect. Pending/unknown states retain their reconciliation block; no timeout, missing process position or empty lookup grants retry authority. A genuinely completed native financial review does not reopen old exposure.

Incomplete historical context retains recoverable native protection while withholding new orders and adaptive setup conclusions. A subsequent genuine close can publish its sourced financial review and risk consequence, but cannot manufacture decision-quality feedback, lessons or experience from a setup whose evidence was lost. This preserves the distinction between an observed P&L result and an evidenced explanation of that result.

## Evidence and remaining contracts

See `receipts/SINGLE_SESSION_RECOVERY_SOURCE_20261022.json` for exact counterexamples, private PostgreSQL suite, restored controls and induced faults. Six original startup assertions failed before implementation. Additional valid counterexamples showed that the string `"false"` was treated as verification and an empty native position ID was adopted; both are refused now. The initial full suite passed2027 before those final controls/guards; the final implementation passes2032 trading tests without skips using actual isolated PostgreSQL and pinned DDS source.

This is BE-002/003/009/010/012 candidate source work. Persistent paper state is not fabricated from old ledger entries. Native pending/late/expiry/fill aggregation and authoritative adjudication, missing TCA gap repair, provable legacy context migration, account/device epochs, physical account uniqueness and safe financial retirement remain original programme obligations. Actual native providers, production, independent admission, signing and handset gates remain separate and unissued.
