# Deterministic funding report rendering

Status: source-tested component; BE-006 remains IN_PROGRESS. No economic, risk, native, provider, unit or production qualification is issued.

The same original valuations, 3 to 4 with no external flows, produced different 80-digit return strings under unrelated ambient Decimal rounding settings. Inexact/Rounded traps also raised exceptions for valid repeating returns, and a caller's small exponent limit overflowed valid native-sized money. Nine actual regression failures are retained alongside the original fifteen passing economic controls.

Unitization calculations continue using exact fractions. Only report rendering now creates an explicit Decimal context: 80 significant digits, ROUND_HALF_EVEN, fixed exponent limits, clean flags and the standard invalid-operation/division-by-zero/overflow traps. It does not inherit caller precision, rounding, flags, traps or exponent limits. Caller settings remain intact. Normal default outputs, policy version, input/source references, marked-account interpretation and every measured/unmeasured/refusal state are preserved. Execution authority remains false.

All 24 focused controls passed after correction. The final selection executed 219 original funding, native cash, balance, reconciliation, runtime and risk-fence cases against actual isolated PostgreSQL, with zero skips or storage-audit violations, matching final runtime/test hashes and independent confirmation that the owned fixture was removed. Counts overlap. The first fixture attempt timed out during readiness before any test executed; its cleanup and absence receipt are retained. The successful retry records its initial probe timeout and then actual readiness. No functional assertion was weakened.

Owner/frontend contracts show no drift. Evidence belongs to `receipts/FUNDING_REPORT_CONTEXT_SOURCE_20261026.json` and `ci/funding_rounding_20261026/`. Parent 6698a9df's separately verified hosted forecast/Parquet success does not qualify later report-renderer changes.

This correction does not complete funding postings, reversals, shared outgoing collateral, flow-adjusted risk qualification or BE-007 payment rails. Current source/account observations and percentage performance retain their existing qualification states. Unknown or non-withdrawable credit is not risk capital, and deposits cannot clear economic loss history. Remaining canonical backend work and independent/native/owner/production/economic/Artemis-S24 gates remain open.
