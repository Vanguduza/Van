# Native propagation of paired owner-device key revocation

Candidate source extends the existing internal device-enrolment revocation route. It does not expose that internal credential to Android or agents, add a new screen, mint owner authority or assert deployed acceptance.

## Durable local and native outcomes

The gateway atomically records the original public native-revocation identity with device/grant revocation. A failed receipt write rolls both back. Repeated local revocation preserves the first timestamp and original target. Legacy devices whose public-key metadata cannot identify a native key are still revoked locally; native completion remains pending, never invented.

Local privileged actions and client certificates are revoked before potentially slow native delivery. The response reports the local outcome separately from `native_authority_revocation`: PENDING, APPLIED or UNKNOWN. APPLIED requires a strict, target-matching native acknowledgement with an inactive key and durable registry/tombstone references. Unreadable cached evidence is not promoted to success. Public replies contain fingerprints and outcome references, not key material, signatures or credentials.

A background dispatcher starts after storage migration and is cancelled/awaited on shutdown. It replays the same durable operation after process death or a lost native acknowledgement. Batches and a persisted rotating cursor prevent an invalid old row from starving later revocations. The original record is retained through uncertainty. `GET /v1/devices/{device_id}/revocations/{operation_id}` observes its persisted outcome under the same dedicated enrolment scope; it never dispatches, reenrolls or changes a key. Wrong targets/unknown IDs are 404, malformed IDs 422, and corrupt history 503. A shared runtime/agent token cannot use this administration route. Native success followed by a failed gateway marker write is retried idempotently; a verified native outcome is distinct from that local bookkeeping failure.

## Native key registry

The new `owner_authority_revoke` command is restricted to the dedicated authenticated van-gateway principal and hidden from agents/MCP. It checks a closed target, P256 fingerprint and deterministic device/key operation identity. It removes the target public key under every registered alias and atomically persists a permanent revocation tombstone with owner-only file permissions, file/directory synchronization and exact readback. Unrelated owner keys are preserved. Enrollment of the same key preserves existing policy aliases and compares decoded key material rather than PEM line endings. A retained tombstone also excludes a later restored alias for that revoked public key. Repeated attempts, including separate devices sharing one key, remain idempotent.

Enrollment and revocation use the same reentrant cross-process state-file lock and resolved file identity. A stale or competing enrollment cannot overwrite a tombstone or resurrect an acknowledged revoked key. A malformed tombstone history or a registry writable by other users is refused. Existing flat/`keys` registries are read compatibly; writes retain revocation history.

Commander instances reload configured key registries when verifying current owner authority, preserving the existing one-time consumption set. The runtime recovery actor independently reads current keys before an effect. Archived signatures remain available for truthful original-operation history; they do not restore current authority.

## Binding the actor to its authority source

A fresh native recovery profile binds the canonical owner-key registry identity as well as the current physical account/profile permission. Commander refuses a review from an actor using a different authority source. Changing that source after approval changes the exact state reference and causes refusal. This is an opaque profile hash; no native file configuration is placed in the Android interaction flow. Older pending reviews that lack this binding require a fresh review; their signed statement is never rewritten.

This mechanism revokes the paired device key for native owner-controlled acts. It does not re-sign an independent financial mandate, assume a standing grant is the same credential, manufacture provider effects or remove protective position management. Broader standing-policy retirement and deferred provider execution remain their original contracts.

## Source evidence and limits

The receipt retains the four original counterexamples, the later local-action ordering and two authority-source mismatch counterexamples, positive controls, concurrent writer/readback tests, private authenticated transport/error tests, induced regressions and the actual affected/full source suites.

All original 131 units, 324 requirements, 1,610 acceptance identities, 234 contexts, 349 owner actions and 93 planned features remain unchanged. No complete unit, native identity/provisioning, real provider, production, hardware biometric or S24 acceptance is issued by these source tests. The current frontend registry will report the typed partial native outcome; Android consumption of this internal administration surface must use the existing admitted owner-control boundary, never an internal bearer.
