# Current account risk at dispatch

Candidate construction for BE-006 and the existing risk/execution units. This is a source component, not unit acceptance or permission to trade. The frozen package and all existing feature/screen identities remain unchanged.

The original approval is preserved. Before a command can consume its key, both actual single-symbol and account runtimes obtain a new RiskSnapshot through their existing native snapshot producers. A separate RiskAuthority calculator uses the same exact mandate, platform ceilings and conformal gate; it neither resets the original authority's consumed proposal key nor creates a second submission permission. New exposure, loss, margin, preservation, reconciliation, storage, clock, quote and halt facts can refuse the original command. A smaller current size limit refuses the already built command; a higher limit never enlarges it.

The router accepts strictly typed current facts and the original post-read observation time, not a boolean approval. Missing native facts, a foreign account, unavailable provider, backward/future/bool clocks, malformed inputs and unbound decisions refuse before publishing an order. Isolated legacy paper and owner-ticket callers can omit the callback; actual application runtimes wire it. Other adapters cannot silently fall back to the old approval.

Native reads remain outside the financial journal writer. A short atomic journal transaction records RISK_REVALIDATION, bound to the immutable original decision, command, account, intent, mandate and fresh snapshot. Its execution_authority is false. Identical retries after a lost transaction reply retain the same proof and its original availability. A failed evidence write leaves the command unsent and its key unspent. Current halt, lease, grant lifetime, quote age, route and quantisation controls run again after the read; protective exits remain separate.

## Existing Android and API contract

The existing authenticated `GET /v1/trading/trades` and `GET /v1/trading/trades/{id}` expose `current_risk` on their existing rows. The detail timeline records `RISK_RECHECK`. A held original approval appears in potential trades as `RISK_RECHECK_REFUSED`, with the actual current reason. These are read models, never actions.

`current_risk.state` is UNMEASURED, UNAVAILABLE, SUFFICIENT or REFUSED. A measured observation carries proof_ref, original_decision_hash, original_command_hash, decision_hash, observed_at_ms, received_at_ms, current_size_limit, original_command_quantity and the current reason. SUFFICIENT describes only that original observation; it grants no future command. Missing original evidence never becomes sufficient. The read model checks the event producer and seal, fresh decision and snapshot seals, account/intent/mandate join, observation clocks and state consistency.

The existing TradeBookParser and TradeDetail parsing preserve this object through CurrentAccountRisk. Decimal quantities remain strings and timestamps use exact Long parsing. Missing evidence is UNMEASURED; malformed or authority-claiming evidence is UNAVAILABLE. The DTO has no sender and its executionAuthority is always false. No new screen, navigation or redesign precedes BG-001.

## Executed evidence and limits

The original actual single-service counterexample failed twice: an account changing during lease acquisition could still send the old approved quantity. The valid larger-budget control passed. The smaller-budget fixture uses explicit simulated capital so the change exceeds the instrument's lot step; it does not demand a refusal for unchanged quantisation that still fits.

The receipt CURRENT_ACCOUNT_RISK_SOURCE_20261024.json records the final isolated PostgreSQL run, broad execution/recovery cases, owner trade/detail projections, API cases and eight deliberate source fault/restored-control pairs. Bad current observations, newly reported exposure/holds, provider errors, journal failures, a lost durable-commit reply, exact command/proof joins, native-read clock provenance and unchanged original proposal-key consumption are exercised.

All1,333 Kotlin/JUnit cases passed using direct Kotlin2.0.21 delta compilation and the original verified Gradle runtime, unchanged compiled test classes and source-verified original test resources. The original Gradle invocation failed before compilation on this container's native thread limit. The first direct launcher omitted certificate resources and failed one original test; adding the unchanged test resources produced1,333 passes with zero skips. These are retained separately; no successful Gradle or full Android build is inferred.

Whole-suite qualification follows on the committed source. The native unknown-margin gate and complete native margin supply, joint funding/order reservations, refreshed native contract observations, full flow-adjusted economics and the remaining backend work are still open. Native deployment/security/recovery/signing, private-DDS/trusted-main prerequisites and S24 acceptance remain separate. No F15, BG-001, unit, profitability, provider or handset certificate is issued.

The exact committed b82cca20 full run stopped at the original five-failure limit after995passes: two standalone native Boolean-receipt fixtures omitted the new current-facts/RiskAuthority contract, and three cases failed native subprocess/PostgreSQL fork creation. The fixture helper now supplies exact fixture observations to the real authority; all original test functions are AST-identical, including send/flatten call assertions. The combined46 current-risk/native-receipt cases pass with zero skips. FULL_TRADING_SOURCE_b82cca20_FAILED.json preserves the original failed run and correction; no whole-suite pass is inferred.
