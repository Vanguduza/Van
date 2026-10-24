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

Financial display must keep unknown/unavailable/pending/conflict distinct from an observed empty cash window. Do not calculate profit from balance or equity differences. Do not sum a missing account PnL as zero. A native profile change produces stale/unavailable data until the current identity is observed. Restricted broker credit, converted bonuses, negative-balance support, rebates, account charges and IB income retain their economic categories and must not be presented together as proven trading alpha.

Android `FundingObservation` and `NativeCashMovement`, attached to `AccountCard`, preserve ID and monetary strings. Values above 2^53 are not converted to floating-point IDs. Existing clients remain compatible with the additive fields. The screen redesign, full cash-history export, source-normalized performance displays and actual provider/device acceptance remain under the canonical programme.
