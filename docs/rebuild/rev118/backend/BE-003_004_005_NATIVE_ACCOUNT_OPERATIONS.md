# Candidate native account-operation recovery

The existing owner onboarding path now keeps original operation identity across a lost native reply or Android restart. This is candidate source work for BE-002/003/004/005, not unit admission, safe account retirement, broker acceptance or a release.

## Actual producer and consumers

For `account_upsert`, `account_credentials`, `account_remove` and `mt5_ea_issue_key`, the gateway consumes the real device-bound A4 proof once and forwards its non-secret operation identity, original expiry and exact request binding through the existing Local or signed Commander control. The native constructor binds the existing VATI ledger. Missing operation context is refused on both actual ingress paths; direct native handler calls remain internal test seams.

The writer holds the existing alias operation fence, checks the original account resource version and commits an `ACCOUNT_OPERATION` claim before a registry or credential effect. The ledger records the actor, request digest, original resource version, authority reference, target and sealed predecessor. No credential argument values or signing-key exports are journalled. Completion and claim publication use the existing SQLite/PostgreSQL atomic ledger scope; no ledger transaction spans the handler.

Only a handler refusal before the first native effect marker can become `REFUSED`. An interrupted process leaves `IN_FLIGHT`; failed or uncertain completion becomes `UNKNOWN`. Neither state expires into permission to repeat. Other account-control mutation paths, including provider links, check the same unresolved alias fence. A different alias remains independently usable. Original actor, request, authority and resource bindings cannot be reassigned to an existing operation ID.

Confirmed original results can be read after expiry or configuration changes without running the handler or rebasing onto today's account record. A failed commit acknowledgement reads an already committed completion. MT5 recovery confirms the original key issue using public metadata; it does not retain an export, issue another key or claim the historical key is today's credential.

## Wire and existing Android repair

`GET /v1/trading/accounts/operations/{operation_id}` uses the currently authenticated paired device, never a device ID supplied in a query. It returns a typed original outcome and native event reference. Unreadable or absent native evidence stays `UNKNOWN`; absence is not proof that a delayed request can never arrive. Lost replies, malformed/misbound Commander responses and backend transport errors cannot become an ordinary pre-effect refusal. Action approvals remain one-use.

The challenge response now returns its original `issued_at_unix`. Existing Android onboarding sends that exact timestamp after biometric approval, fixing the earlier challenge/action timestamp drift. It durably saves only operation ID, action, device ID and alias in the existing encrypted preferences before network dispatch. Failed durable writes prevent dispatch; restart retains the original identity. Pending changes offer **Check original result**, with no send retry. Only a matching authenticated confirmed outcome clears the saved identity. Unknown, unreadable, conflicting and incomplete results retain it. Recovery never stores argument values, approval signatures or credential exports.

This repairs the existing onboarding/error path. It introduces no frontend redesign before BG-001. The original feature, screen, function and authority identities remain; the owner registry adds a source contract extension for the readback endpoint.

## Evidence

See `receipts/NATIVE_ACCOUNT_OPERATIONS_SOURCE_20261022.json` for exact source/log hashes and current test totals. The full trading suite passes **1,956 tests without skips** using private PostgreSQL and the pinned DDS checkout. Actual native SQLite consumers, signed gateway/Commander requests, paired-device biometric proofs, child-process death, lost replies and nine induced faults are exercised. Separate native processes contend for one target on both SQLite and PostgreSQL; only one claim is admitted. Android JVM/build/lint results are source evidence; hosted emulator and physical S24 results remain separate.

The original nine-fault run has a passing control, rejects all nine faults and restores its source bytes/journal. Final follow-up checks also exercise wrong-command native replies and the explicit unavailable-export presentation.

## Remaining programme work

- The other provider effects (email/account creation, token exchange and native OAuth link leg) still need their own native operation/finality producers. Existing gateway OAuth recovery is a separate component.
- The native unresolved scope is an alias, not a proven physical broker-account identity across aliases, processes and hosts. Registry/CLI/legacy writers, shared runtime leases and every entry/protection consumer still need their canonical admission/migration work.
- `account_remove` is still not proven safe with exposure, pending orders, unknown money, leases or retention obligations. No production activation or account-removal safety is authorized by this packet.
- Explicit native adjudication and authoritative cancellation/not-dispatched evidence remain required. No timeout, empty lookup, new approval or local preference deletion is an adjudicator. A pre-dispatch failure with no durable native outcome can therefore remain pending rather than invite an unsafe retry.
- Completed records are historical confirmations, not proof the owner saw the reply or that a credential is still current. Cross-device recovery/epoch migration and full resolved owner-review presentation remain separate contracts.
- Full-chain validation currently costs proportional to ledger history. Production latency and contention qualification, bounded projections and native storage deployment remain required.
- Original independent/native gates, owner policy decisions, real providers, signing, deployment and Artemis/S24 acceptance are retained. This packet creates none of those receipts.
