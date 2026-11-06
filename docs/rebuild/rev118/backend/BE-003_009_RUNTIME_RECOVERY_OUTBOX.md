# Durable original runtime-recovery dispatch

Candidate source closes the gap between gateway consumption of an exact A4 approval and native enqueue. The existing shared SQLite transaction already saves the public original intent/proof with challenge consumption. The gateway now starts a bounded background dispatcher after storage migration and cancels/awaits it on shutdown. A new process can resume from those durable receipts without another phone POST, a new operation ID, another signature or a refreshed timestamp.

Every attempt checks receipt identity/digest/expiry metadata, the current unrevoked paired device, its exact public-key fingerprint and the archived signature. Enrollment is followed by a fresh device/key read. An authenticated native original-operation read precedes dispatch. A lost successful native acknowledgement is read back rather than sent again. A durable delivery marker is written only after an identity-bound, typed native receipt; marker-write failure leaves the original recoverable. Multiple gateway instances may attempt the same original; the native atomic journal arbitrates. GET routes remain read-only.

Batches and cursor rotation are bounded. An unreadable or foreign-domain receipt does not erase another operation or indefinitely starve later work. Transport/key/storage failures retain the original public receipt and defer. Logs contain counts, not signatures or other approval material. No scheduler opt-in is required for this recovery mechanism.

## Expiry without invented authority or effects

An expired original that **already exists** in the native journal keeps its original REQUESTED/APPLIED/REFUSED outcome. Expiry cannot reclassify a potentially accepted request as no effect.

For an original that has never reached native acceptance, the native journal authenticates the exact signed statement and establishes absence under the same writer transaction that records a terminal refusal. A separate `vati.runtime-control-expired-refusal/1` history record represents only this case. It contains the real original proof and native event reference, phase REFUSED, reason APPROVAL_EXPIRED, zero effect references and `entry_authority_granted: false`. It never enters the actor queue. Clock rollback, retry or key re-registration cannot reopen that original. History validation rejects effect/entry claims, non-refusal phases, fabricated current state or acceptance before the signed expiry. Existing active-approval history remains supported unchanged.

Signature-only verification authenticates immutable history; it does not grant present authority. All active recovery effects still require the full native lifetime, lease, state, current-key and risk checks. No owner signature is renewed or backdated.

A refusal before actor observation cannot assert current latches or risk state. Its `remaining_kill` and `state_ref` are explicitly null. The typed API preserves that uncertainty; callers must fetch a new current state before presenting or approving another recovery. The Android original-operation tracker accepts the matching final no-effect receipt without treating it as entry permission.

## Qualification and remaining work

The source receipt records the actual before/after counterexamples, full affected PostgreSQL run, source fault tests and Android compatibility test. Tests exercise real A4 P256 statements, both authenticated HTTP applications, native journals and a lease-fenced source actor. They do not qualify a deployed host, provider, device biometric, entire programme unit, production provisioning or S24.

Native device-key revocation propagation, coordinator controls, safe account retirement, original provider outcomes, financial finality and the remaining original programme stay open. A revoked device or unavailable current native key is deferred rather than assigned a fabricated no-effect outcome. No new frontend is introduced before BG-001.
