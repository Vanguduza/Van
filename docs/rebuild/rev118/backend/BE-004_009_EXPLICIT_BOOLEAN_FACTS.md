# Explicit native and policy boolean facts

Candidate source work for BE-004 and BE-009. This changes no policy bound, owner decision, gate or financial activation.

The previous kernel approved an actual paper fill when native verification, connection, reconciliation, clock or store facts contained the string `"false"`. Bridge account readers also converted that string to `True`. The mandate loader converted ambiguous weekend and drawdown settings to permissions. Native order checks and stop acknowledgements had the same coercion defect; a queued stop modification could time out as `REJECTED` and still execute later.

The shared RiskAuthority now requires actual booleans for every declared boolean field of the snapshot, intent, instrument and current-position contracts. It publishes a sealed `INVALID_BOOLEAN_FACT` refusal naming the field. A known halt retains priority, and a refused malformed input does not poison later genuine evaluation of that intent.

Both MT5 account readers reject ambiguous permission/topology facts before coercion. The policy loader and direct-object validation reject ambiguous weekend and drawdown flags. An order check must explicitly confirm `True` before submission. A stop is confirmed only by actual `True`; an unconfirmed filled entry follows the existing protected emergency-close path. A sent modification with a missing or malformed reply remains `UNKNOWN`, preserving reconciliation of the original request. Explicit native `False` retains its existing rejection meaning; this packet does not prove provider finality from an arbitrary negative response.

The new tests exercise the actual kernel, router and paper sender, signed push bridge requests, authenticated EA polling/queue and real delayed queue execution in the local EA simulator. They are source tests, not a connected MetaTrader terminal or handset test. The call-list fixture was corrected to include the existing preliminary account read; the initial two assertion failures and failed full run were investigated before the passing rerun. A drawdown fixture was corrected to include its required final suspending tier before recording the valid old-source producer counterexamples.

Final counts, counterexample hashes, deliberate source faults and restoration proofs are in [the source receipt](../receipts/EXPLICIT_BOOLEAN_FACTS_SOURCE_20261022.json). The canonical 374-case legacy mutation corpus is unchanged. No Android source or frontend is introduced.

The prior OAuth correction also completed its separate broad audit: 6,636 backend/contract passes, 166 explicit skips, zero forbidden runtime-storage accesses and a clean isolated checkout. Its hosted run caught all 374 original mutation cases and ran 18 emulator tests with four existing artwork-mode skips. These qualifications belong to that exact source, not to later edits; retained DDS-key and trusted-main bootstrap failures remain recorded in their hosted receipt.

Remaining work includes full mandate-content authority, consistent original/late financial finality, pending entry reconciliation, physical account identity and safe retirement, and the rest of the original programme. Source checks do not issue native, independent, whole-unit, production, provider, profitability or S24 acceptance.
