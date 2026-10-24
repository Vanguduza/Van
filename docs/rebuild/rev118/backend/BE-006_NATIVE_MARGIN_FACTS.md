# Native margin facts and owner readback

Candidate source construction for the existing account/risk/execution features. No whole-unit, production, provider or handset acceptance is issued.

Two original counterexamples failed: missing native margin could still approve a leveraged order, and serialized decimal margin fields replayed as strings and changed the decision. RiskAuthority now refuses missing applicable native margin, malformed/non-finite amounts and negative usage. A real zero commitment has an undefined ratio; no comfortable default or infinite ratio is supplied. Existing platform margin floors remain in force. Cash-equity bounds prevent reported credit-inclusive margin from replenishing risk capacity.

RiskSnapshot carries optional used_margin. Its absence is omitted from serialization and the snapshot identity, preserving legacy snapshot hashes. Existing free_margin and margin_level_pct now deserialize as Decimal too. New observations include actual margin in their sealed snapshot. Original approvals, intents, commands, history and grant checks remain immutable; the current-risk recheck consumes these facts without granting another submission.

The actual MT5 EA and signed Windows worker supply used margin, free margin and margin level in deposit currency/percent. EA read errors or non-finite amounts emit unknown, never zero. Both native adapters preserve decimal text and normalize only the native zero-usage/zero-ratio case to an undefined ratio. Known credit remains excluded from risk equity even when cash-history coverage is unavailable. Unknown credit and the general account-binding/cash-coverage distinction still require further work.

cTrader supplies per-position usedMargin with each position's own moneyDigits. Position observations bracket the native PnL query; changed inputs refuse a combined snapshot. The account's declared SUM, MAX or NET rule is applied per symbol and side. Unknown nonempty-account modes stay unknown. Open API uses MAX=0/SUM=1/NET=2; Algo uses different integers. The implementation follows the documented formulas by name and the vendored Open API enum. Derived free-margin and ratio fields are explicitly labeled as bounds using native margin and cash risk equity, not broker-reported account totals or settled money.

## Existing owner API and Android models

Both actual account-snapshot producers record margin facts, their post-account-read observation clock, calculated risk bounds and execution_authority:false. Existing account/portfolio endpoints expose the original snapshot reference, availability state, basis and clocks. Missing legacy evidence remains UNMEASURED. Bad seals, clocks, joins or invented bounds are unavailable. A native account without a physical scope cannot attach its margin to the active profile.

AccountCard.margin preserves exact decimal strings and Long timestamps in AccountMargin. It distinguishes original figures, explicitly derived bounds, simulation, unavailable evidence and zero usage with no applicable ratio. The existing trading-signal mapper receives the lowest known cash-backed margin ratio instead of a hardcoded null. The DTO remains read-only and always exposes executionAuthority:false. Its source is included in the actual JVM harness; no new frontend, layout or navigation precedes BG-001.

## Executed checks and retained failures

NATIVE_MARGIN_FACTS_SOURCE_20261024.json records215 PostgreSQL/current-risk/funding/identity checks with zero skips,15 authenticated API checks with no source-storage writes,1,336 Kotlin/JUnit checks, and13 deliberate source fault/restored-control pairs. Mutants must fail the expected behavioral assertion with zero setup errors; compilation-only failures are invalid attempts, not caught defects.

The native unknown-outcome/restart file has30 distinct scenarios. Twenty completed successfully before six thread-start failures interrupted the combined run; the remaining ten were reexecuted successfully against a clean PostgreSQL fixture. All30 have an observed passing execution across those batches. The failed/interrupted run and its incomplete synthetic JUnit case remain recorded; no single combined recovery or full trading pass is inferred. Earlier PostgreSQL attempts with fixture and native-thread failures are retained; the final215-case run passes and its database is stopped/removed.

Shared unit fixtures now explicitly report their declared native margin. The delayed native terminal fixture models1,000 deposit units per open position and zero usage when empty. The deposit-oracle fixture states its empty account's zero margin. Original assertions about funding rejection, unknown effects, no replay, native send calls and protective flattening are preserved.

The previous hosted public trading job hit its15-minute budget after88% progress. The next job retains every test and gate, uses a35-minute combined database/trading/voice budget, and prints identities/durations for diagnosis. No pass is inferred from the canceled job. The complete browser source job on10ee9fcd passed all50 selected files, the separately executed root UID case and all10 original firewall controls; its receipt is separate from native host acceptance.

A stale startup diagnostic from2026-10-22 was initially mistaken for current evidence during this pass. The current generator already scopes IDs by account; the existing identity tests pass. No new identity defect or generator change was made.

## Remaining work

At original packet submission the new EA still required actual MetaEditor compilation. The subsequent exact31a726ca receipt NATIVE_METAEDITOR_31a726ca.json records zero errors/warnings, a fresh EX5 and the invalid-source control. Whole committed-source trading/backend qualification, broker-specific stop-out/call modes and thresholds, prospective-order margin estimation, joint funding/order reservations, refreshed native contracts and complete flow-adjusted economics remain open. Independent admission, private-DDS/trusted-main prerequisites, native host identity/services/security/recovery/signing and S24 acceptance remain separate. Subsequent source packets preserve held-funding loss baselines and separate bound native account/credit observations from cash-history coverage; see BE-006_FUNDING_BASELINE_PRESERVATION.md and BE-004_006_NATIVE_ACCOUNT_OBSERVATION.md. Live native qualification and the remaining flow/prospective-margin work are still required.

Primary references: [MQL5 account properties](https://www.mql5.com/en/docs/constants/environment_state/accountinformation), [Python account_info](https://www.mql5.com/en/docs/python_metatrader5/mt5accountinfo_py), [cTrader per-symbol margin calculation](https://help.ctrader.com/ctrader-algo/references/Account/TotalMarginCalculationType/), and the vendored OpenApiModelMessages.proto enum and native monetary field definitions. Exact downloaded source hashes are retained in the receipt.
