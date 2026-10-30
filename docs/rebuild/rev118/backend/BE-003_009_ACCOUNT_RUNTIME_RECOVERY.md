# Signed recovery for the multi-instrument account runtime

The existing Android recovery data layer and five gateway endpoints now serve both single-session and multi-instrument account actors. The catalog reports `single-session-and-account`. Native account heartbeats publish the same recovery-state schema and an opaque `session_id`; the app obtains that identity from backend observations. No handset host address, service credential, new screen or separate recovery API is introduced.

## One actor and one original operation

`AccountRecoveryView` references the actual account service, lifecycle, governor, ledger, positions and protection. The existing recovery actor and journal perform signature, exact state, original-operation, lease, expiry and native precondition checks. They append the domain effect and terminal outcome in the same PostgreSQL transaction. Lost commit acknowledgements reconcile that original operation. An exception before commit leaves the request pending and rolls back its effect. Neither path submits or resubmits a trade.

The account session identity binds its account, current holder/lease epoch, complete configured instrument specifications, native contracts, software-stop mode and activation. Renewing the same lease or polling does not invalidate an unchanged review. A different actor, epoch or instrument configuration requires a new review. Existing profile and authority-source bindings remain part of the state reference. Private filesystem paths are not frontend configuration.

Owner halts are folded through the shared account-scoped history reducer. A foreign account's halt does not stop this account. A bare `cleared` boolean or another account's clear cannot release an owner halt. An applied signed clear names its original causes and clears only its approved trigger. Clearing a global cause for one account does not release it for another. Other risk latches, losses, protection and pending work remain intact.

## Current authority and idle operation

Account service passes renew their native lease even without a new bar. Allocation still renews and checks its own lease, and the router retains its final submission fence. Loss of the native lease cannot become entry permission. Standalone component-only bar processing has no recovery actor or financial authority.

Recovery uses the same issuer-file lock as enrollment, revocation and standing-policy submission. Its lock order is lease, issuer, then ledger. Key retirement cannot acknowledge completion between current-key verification and committing that key's approved effect. Equivalent PEM encodings remain the same public key. This control neither revives a retired financial policy nor converts an archived signature into current permission.

## Native order uncertainty

An empty venue position list is insufficient to establish a healthy account. Account review and risk snapshots also fold the original native command and authenticated receipt history. Missing results, partial or unknown outcomes, conflicts, invalid quantities and invalid fill prices retain uncertainty. A later zero-quantity refusal cannot erase a positive partial fill. Both recovery eligibility and new-entry reconciliation retain that hold.

A genuine original zero-effect readback can resolve that order uncertainty. Releasing a separate owner halt still requires a fresh exact approval. It does not replay an earlier refused operation or send the command again. Native provider finality, corrections, cash/fee facts and automatic original-fill reconciliation remain their original execution obligations; a control-state recovery is not proof that those were completed.

## Source evidence

`receipts/ACCOUNT_RUNTIME_RECOVERY_SOURCE_20261023.json` preserves the original failures, fixture corrections, actual PostgreSQL rollback/acknowledgement-loss cases, the paired-gateway/P256/signed-Commander/account-actor round trip over in-process transport, affected and full source tests, and deliberately introduced regressions with restored source. The frontend registry describes the two supported runtimes and the existing Android clients.

All 131 original development units, 324 requirements, 1,610 acceptance identities, 234 contexts, 349 owner actions and 93 planned features remain. Source tests issue no whole-unit, independent, native-host, provider, production, profitability, hardware-biometric, signing or S24 acceptance. BG-001 and the original activation gates remain unchanged.
