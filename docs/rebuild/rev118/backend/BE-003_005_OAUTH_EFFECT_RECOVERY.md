# BE-003/005 candidate: durable OAuth callback and account-link effects

The actual existing OAuth producer and account-action consumer now journal a claim before token exchange or local linking. This is an additive effect table in the gateway's existing Store, with encrypted confirmations. It is not a new financial ledger, service or authorization source. Original programme identities and gates are retained; no unit completion is issued.

## Confirmed defects and resulting behavior

Three initial gateway failures demonstrated repeated code exchange on an exact callback retry, replacement of accepted credentials by a conflicting callback, and loss of the link result after consumption of its pending state. Exact requests now return their saved result. Different requests against the same state refuse. An in-flight or unknown code/target cannot be bypassed by creating another state. The same alias remains fenced when its previous link outcome is unknown.

Pending material and completion receipts are committed together; successful consumption and its receipt are one transaction. An exception after commit reads the saved confirmation instead of repeating the effect. Unknown outcomes retain their tombstone and do not become retryable on a timer, restart or new callback. An actual child-process exit after a committed claim is covered: the next process reports an unconfirmed outcome and makes no second provider call. Native target adjudication remains a separate required capability; a software cache is not proof that an external effect did not happen.

The synchronous control transport runs off the request event loop. Source tests hold a token exchange in progress while owner polling continues, reject a concurrent duplicate, cancel the coroutine while its external thread may still finish, and verify the durable unknown outcome. Local activity tracking prevents an abandoned claim from being called currently in progress merely because its worker ID matches.

## Bound material, receipts and owner information

Two additional real failures demonstrated that valid ciphertext could be copied between states/links. New encrypted authorization material binds its state, broker and creation time. Encrypted receipt envelopes bind their version, state, operation, request digest, broker and device owner. Another flow's ciphertext cannot supply credentials or a confirmation. Old unreadable/unbound material refuses explicitly rather than becoming a fresh or adopted grant.

Incomplete provider material and mismatched native account receipts stay unconfirmed. The actual native local handler is exercised for account linking and file readback; provider token exchanges in these tests are isolated responses. Neither registration nor a matching callback qualifies broker identity, financial readiness, credentials or production connectivity.

The existing account-action endpoint now documents a typed 409 response with `effect_state` (`REFUSED` or `UNKNOWN`) and `reconciliation_required`. An unknown original operation is audited as unknown; a newly blocked request remains refused while signalling that the prior effect needs reconciliation. The public callback HTML also distinguishes refusal from an unconfirmed outcome. This prevents an ambiguous effect from being reported as a definite failure.

## Validation boundaries

Exact hashes and results are in `../receipts/OAUTH_EFFECT_RECOVERY_SOURCE_20261022.json`. Real encrypted SQLite storage, actual gateway/device/A4 paths, native local configuration writes, independent readers, injected atomic-write faults, a real abrupt process exit and bounded concurrent operations are covered. Six custom mutations remove redundant replay guards, bypass an unknown target, split the transaction, block the event loop, or transplant encrypted state/receipts. Every baseline must pass before the induced defects count; source is restored afterward. The original 374 mutation identities and 383 edits are preserved.

An initial new test fixture incorrectly used the default local account paths. Its five synthetic untracked files were content-verified and removed; the committed database and owner files were unchanged. The fixture now binds account/secret storage to its private test directory. The subsequent audited selection refuses checkout `data/` storage and records zero violations. No fixture credentials or generated registry were committed.

The prior frozen `b1ab08bd` full source audit completed 6,584 passed / 166 explicit skips, seven warnings, zero forbidden checkout storage writes and a clean checkout. Hosted `c4e0e7b3` again passes all 374 legacy mutants and 18 native emulator tests (four existing core-artwork skips), PostgreSQL 26/26 and voice source 117/117; public trading has 1,824 passed plus the explicit private-DDS skip. Exact receipts preserve the tested tree and all outcomes.

## Continuing work

This packet covers stateful OAuth callback/link effects. Direct non-OAuth account/broker actions still need the complete native operation and readback protocol. Native profile/environment/read-only attestation, verified credential replacement, resource-version fencing, exposure/funds/lease-safe unlink, native unknown-effect adjudication and policy-based retention/erasure remain required in the original programme. No uncertain tombstone is automatically expired here. Account linking is not remote broker account creation or closure. No live provider, financial permission, independent admission, production deployment, release, physical S24, acoustic or Artemis acceptance is claimed.
