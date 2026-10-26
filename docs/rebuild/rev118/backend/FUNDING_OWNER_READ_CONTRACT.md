# Funding fields for the existing account and portfolio screens

Applies to `van.trading.accounts` (feature `OF-TRADING-003`) and the existing portfolio/overview surface in [the screen registry](OWNER_FRONTEND_SCREEN_REGISTRY.md). This is additive backend/Android SDK wiring. The original screen/feature registry is preserved; new frontend work remains behind BG-001.

The paired-owner routes are `GET /v1/trading/accounts` and `GET /v1/trading/portfolio`. Their account rows now include:

| Field | Meaning |
| --- | --- |
| `performance_state` | Native performance is `UNMEASURED`; paper marks are explicitly simulated. |
| `day_pnl`, `week_pnl`, `drawdown_pct` | Null for native accounts until cash-flow-neutral performance can be reconstructed from qualified inputs. A deposit is not profit. |
| `raw_equity_change` | Separately labeled day/week differences and drawdown from raw equity; includes capital flows and is not a trading return. |
| `funding.state`, `reason` | `PENDING`, `OBSERVED`, `UNAVAILABLE`, `CONFLICT`, `UNSUPPORTED` or `UNMEASURED`, with the actual source reason. `OBSERVED` describes native records, not profitability or spendable funds. |
| `funding.return_qualification` | `NOT_ISSUED`. Current raw observations cannot establish a historical return. |
| `funding.scope_hash`, `native_mark` | Provider, realm, native account/deposit asset/currency and the original current mark, optional bonuses, registration time and native balance version. Missing values remain null. |
| `funding.snapshot_ref`, `statement_ref` | Original hash-chained observation identities. Retry preserves the original statement and availability. |
| `funding.coverage_windows`, `catch_up_state`, `collector_state` | Actual recorded query windows and asynchronous collection status. A read window is not a certificate of economic reconciliation. |
| `funding.movements` | At most 100 original native movements with exact amount strings, native IDs, original statement refs and versioned classifications. Provider notes are excluded. |
| `funding.movement_count`, `movements_truncated` | Full observed count and explicit bounded-preview indicator. This preview is not a complete export or paging API. |
| `funding.conflicts` | References to changed provider history and the original observations. Original data is retained; no automatic financial restatement is implied. |
| `funding.execution_authority` | Always false. These read routes cannot approve, reserve, submit or retry a financial transfer. |
| `funding.financial_movements` | Additive, read-only exact posting projection from the original cTrader SQL cash statements. `NO_DATA`, `PENDING`, `CONFLICT`, `UNAVAILABLE`, `UNKNOWN`, `UNSUPPORTED` and `SOURCE_POSTED_NOT_SETTLEMENT_OR_RISK_ADMISSION` remain distinct. Original/posted/pending counts are present only when read successfully; an unavailable read is not an empty ledger. |
| `funding.financial_movements.movements` | At most 100 current read-model records containing original publication receipts and versioned financial movements. Each amount uses string `minor_units`, integer `scale`, currency and native asset identity. Native IDs remain strings. Posting state distinguishes observed cash, restricted-credit memorandum and unresolved suspense. Source/receipt/projection clocks and original statement/row references are preserved. |
| `funding.financial_movements.current_original_source_verified` | Current verification of original observation lineage only. Historical completion does not imply a currently conflict-free source. Settlement qualification remains `NOT_ISSUED`, risk-capital qualification and execution authority remain false. MT5 retains `UNSUPPORTED` for this exact projection. |

Financial display must keep unknown/unavailable/pending/conflict distinct from an observed empty cash window. Do not calculate profit from balance or equity differences. Do not sum a missing account PnL as zero. A native profile change produces stale/unavailable data until the current identity is observed. Restricted broker credit, converted bonuses, negative-balance support, rebates, account charges and IB income retain their economic categories and must not be presented together as proven trading alpha.

Android `FundingObservation` and `NativeCashMovement`, attached to `AccountCard`, preserve ID and monetary strings. Values above 2^53 are not converted to floating-point IDs. Existing clients remain compatible with the additive fields. The screen redesign, full cash-history export, source-normalized performance displays and actual provider/device acceptance remain under the canonical programme.


## Native deal and period evidence

`funding.native_deals` exposes `state`, `deal_count`, `deals_truncated`, `coverage_windows`, `conflicts` and at most100 original financial deal rows. Each row retains original statement, observation and receipt references/times, exact native identifiers, signed commission and optional close details. An absent optional fee/version is null. This preview is not a complete trade export.

`funding.period` separates `balance_state` from performance `state`. Balance reconciliation uses native balance versions and post-operation balances; trade-cost settlement qualification remains `NOT_ISSUED`. `baseline_ref`, `closing_ref`, `evidence_refs`, interval and coverage state identify the actual inputs. `knowledge_through_received_ms` with `LATEST_OBSERVED_HISTORY_NOT_AS_KNOWN_AT_TRADE_TIME` is latest-observed evidence, not an as-known-at-decision replay.

`funding.period.valuation_snapshots` is null until original baseline and covered closing marks are available. When present, `baseline` and `closing` retain their exact source references, native marks, separate credits, native balance versions and event/observation/receipt clocks. `cash_balance`, `net_equity` and present credit values use string minor units, integer stored decimal scales and native asset identities. Stored scale is not settlement precision, and missing credit remains null. Complete holdings valuation, risk-capital qualification and execution authority remain false; settlement qualification remains `NOT_ISSUED`. This additive detail does not qualify historical flow valuations or activate risk after deposits. Existing Android parsers retain their original period fields; typed consumption of these new details remains part of later Android wiring.

When reconciliation succeeds, `cash_neutral_net_account_pnl` removes external capital from native net mark changes. `separate_business_income_or_expense` and `net_account_pnl_excluding_capital_and_separate_business` distinguish IB/management income. These dollar values do not establish settled trade profitability. Missing balance evidence leaves these values null. External capital without historical normalized net-equity valuations leaves percentage `performance` null even when balance is reconciled. With no external capital, measured marked-account return and sampled drawdown retain their explicit return/drawdown bases and `NOT_ISSUED` qualification.

`NativeBalancePeriod`, `NativeDealLedger` and `NativeDealObservation` extend the existing Android account parser. Monetary quantities and native IDs stay exact strings; availability uses exact integer parsing. Missing data never becomes zero profit or an observed empty history. Existing legacy native day/week PnL and risk baselines are not activated by this read model.


## Trade admission and request outcomes

Existing sealed risk decisions retain the funding fence explanation in their original snapshot `preservation_reason` and decision `reason_detail`; held new risk uses `PRESERVATION_BLOCK`. Capital changes, uncovered versions and missing accounting must not appear as a cleared loss limit. The read-only period report is not dispatch authority. Source risk captures include broker-read latency in quote age and record the resulting decision time. Owner-ticket drafting remains explicitly `OWNER_TICKET_DRAFT_ONLY_NO_NATIVE_SUBMISSION`; an accepted draft is not a broker fill or a funding certificate. Dispatch-time revalidation and joint reservations remain under construction.
