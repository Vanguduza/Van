# MT5 result identity and delivery boundary

A native poll previously could finalize a queued original command before any consumer had received it. The same path converted booleans, fractional numbers and decimal strings into another command's integer identity. These were authenticated transport messages, but authentication did not establish that the referenced work had been delivered.

The native queue now completes only a `TAKEN` command for the exact authenticated alias. Result IDs must be positive signed-64-bit JSON integers. The poll handler passes the original ID to that check; it does not reinterpret another type as an integer. Undelivered, malformed, overflowing or foreign identities leave the original outcome unresolved. The normal delivery path still claims the queued command atomically before returning it to a consumer.

A correctly delivered original result remains readable and idempotent. A later conflicting result cannot replace it. This preserves existing unknown-effect behavior, account/credential admission, native command seals and fill validation. It does not turn a first dispatcher acknowledgement into financial finality or implement later fill/correction updates; those retain their original obligations.

The source receipt preserves four original failing cases and a successful delivered-result control, the final affected MT5 protocol/factory/independent-consumer tests, an overflowing-ID control, and three introduced regressions with passing baselines and exact source restoration. No broker execution, MQL compilation, whole-unit, production, profitability or handset acceptance is issued.
