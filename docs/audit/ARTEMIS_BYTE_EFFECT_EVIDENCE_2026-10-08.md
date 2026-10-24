# Artemis byte effect evidence

This is an exported evidence schema for consistency checking, not a provider or
Artemis wire API. Import never establishes producer authenticity or live
qualification. Live reconciliation must use the actual governed device and
backend/provider receipt producers.

A byte case exports harmless fixture `transfer_bytes` plus exactly one
`byte_effect_readback` JSON artifact. The proof binds case/run, repository/APK
hashes, source input hashes, producer and original source receipt. Its
`correlation` must equal the independently recorded case/readback correlation.
That correlation contains `byte_effects`, keyed by the exact planned normalized
operations. Each entry supplies the expected `session_id`, `target_id`,
`transfer_id`, `producer_session_id` and positive `producer_epoch` generation.
The actual opaque native media epoch is `producer_session_id`; an integer cannot
substitute for it. For provider writes the legacy generation label must equal
the immutable request's actual `profile_generation`.

Every effect must match those expected identities exactly and supply the content
artifact reference, observed digest/length, independent observation and source
receipt reference. Both expected and observed hashes must match the actual
exported bytes. Clipboard bytes additionally require bounded valid UTF-8. Empty
files may be valid; missing exported bytes or unrelated transfer identities are
not valid evidence.

`PROVIDER_WRITE` additionally requires `provider_admission` exported from the
existing VAN records:

- `request`: the exact immutable owner request and its current verified owner
  projection, native source readback, initial effect receipt and two verifier
  receipts. The checker recomputes its immutable hash and compares source
  producer/profile/target/transfer, byte identity and admission identity.
- `command_authority`: the actual owner-command seal, exact three parameters,
  effective A4 approval, current original write freshness and snapshot binding.
  A lower original signed action class does not replace or invalidate the
  canonical effective A4 gate.
- `action_execution` and `mission`: actual `VERIFIED_SUCCESS` records with exact
  command/execution/mission identity, action parameter digest and mission source
  command. An unknown or failed canonical command cannot certify a write.
- `admission_claim`: the actual durable claim ID, immutable claims and consumed
  timestamp. Claim must precede both token and original owner-command expiry;
  unclaimed or expired metadata is insufficient.
- `target_capability`: exact current qualified provider capability whose digest,
  namespace, transport pin and admission semantics match the immutable request.
  VEKL requires its real governed Oracle job and actual canonical candidate.
- `readback_observations`: INITIAL, ACTION and MISSION in that order, each with a
  distinct original source receipt reference, independent observation and digest
  of its corresponding effect/readback receipt. Three copies of one observation
  cannot stand in for three actual reads.

All three receipts must bind exact provider, owner/project namespace,
admission/claim, digest and size, and include independently hashed persisted
bytes. They must keep file authority `UNTRUSTED_OWNER_FILE_EVIDENCE` and report
no execution or owner/project truth promotion. Generic download bytes, a write
reply, or matching metadata alone cannot certify provider submission.

Provider observation remains a separate read action. Finding bytes after a lost
reply does not upgrade the old canonical UNKNOWN/UNVERIFIABLE result or release
the replacement fence. Missing or unavailable evidence remains blocked or
unknown. Unit fixtures for this checker are explicitly synthetic and can produce
only `CONSISTENT_IMPORTED_EVIDENCE`, with live/authenticity flags false.

The importer does not authenticate stage timestamp provenance. It validates the
claimed original write timing and exact broker/case/record correlation; actual
current observer and original source receipt references must establish the
three reads during governed native acceptance. No invented wire timestamp fields
are added to the provider API. Stale or unauthenticated source references cannot
be promoted to live acceptance by this consistency checker.

For local speaker functionality, the broader feature and surface
`backend_readback` supplies connection and owner-binding context. It cannot
prove private on-device profile enrollment, inspection or erasure. The three
dedicated local speaker function cases remain mandatory: each requires
`local_device_readback` with the exact profile, model and operation evidence
validated by `local_speaker_readback_matches`. There is no gateway profile API
that can replace this local witness. Imported metadata still cannot authenticate
its producer or establish live qualification.
