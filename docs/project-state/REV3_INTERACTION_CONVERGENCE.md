# REV3 S2-07 VAN computer-worker contribution

This is an isolated source candidate for SOURCE011 of the sealed DIAL REV3 programme. It is based on Muse PR95 head `0e825b44f559f44815cc9925f5dcbcaec5d7eb53`, including its newer Android notification, permission, browser approval and BFF changes. It imports only the computer-worker contribution from PR93's qualified source `dfc1557ab99ad8d41cf84714e1bb671e89b045e6`. Neither default branch nor newest commit is treated as release authority.

## Implementation

The existing ComputerInteractionFabric now consumes injected worker_impls. The existing app constructs one fabric and passes that same instance to execution and health. Browser-native workers and browser records remain in their existing owner; no browser operation is routed through a duplicate computer ledger. The terminal worker stays disabled by default and requires its existing image-bound qualification.

PR93's typed operations, worker, durable leases, generation fences, operation API and receipt tables are retained. Only its computer-worker migration SQL is imported: it is migration32 after this candidate's existing Muse migration31. This is a source-branch reconciliation, not permission to apply migration32 to a deployed database from a different schema lineage. The actual deployed PR93 lineage uses schema55; integration/release must reconcile that lineage separately.

Completion now resolves a genuine computer-receipt URI in the native SQL receipt store, verifies the operation, surface, holder, lease ID/generation, unexpired active lease, successful non-truncated output and SHA256 format, and updates the native operation ledger in the same write transaction. Invented strings, missing receipts and receipts from another operation cannot certify completion. Failure after a mutation starts retains OUTCOME_UNKNOWN. Nonzero mutating worker exits also retain uncertainty.

Health reads the same injected worker's actual readiness instead of constructing an empty fabric. It reports the checked-out commit/dirty state separately from fingerprints of the Python methods actually loaded in the process and current source-file bytes. These are runtime observations; qualified_source remains null. No checkout hash, code fingerprint, nonempty reference or mock receipt is promoted into native qualification.

## Authority and preservation

Owner job `steer-35df6e85-7844-494c-a7b4-5752e613b686` authorizes the complete REV3 programme, including S2-07's VAN contribution. The genuine append-only Project Truth records in this branch carry the DIAL programme authority. They do not claim one-time VAN checker adoption, historical authorization or production acceptance. The existing VAN Project Truth protocol, canonical manifest, locked authorities, Muse code and all unrelated source paths remain preserved.

## Evidence and remaining work

The prior Muse candidate rejected worker_impls with TypeError; the candidate binds a real injected worker. Pinned PR93 accepted an invented receipt string; the repaired candidate refuses it. The final selected source passes 144 interaction cases: worker receipts/readiness, browser fabric, takeover/downloads, interactive routes and Muse. The migration case upgrades a real isolated SQLite database from Muse31 to computer32, preserving and advancing the existing Muse event cursor. Worker doubles remain explicitly bounded source fixtures. Their output is source evidence, not image, external provider or live gateway qualification.

The registered VAN root route to 10.77.0.4 currently times out. Live browser/terminal start, attach, transfers, cancellation, cold start/restart and selected-source runtime readback remain pending. No service, provider, network/VPN configuration or deployed database is changed. S2-07-T01..T04 and independent exact-source review remain open; SOURCE012 S3-07 is not advanced by this contribution.
