# Durable native MT5 replay admission

The worker kept used nonces only in memory. Two independent workers, or a restarted process, could accept the same still-fresh signed request and execute the fixture SDK twice. Both counterexamples reproduced through the existing HMAC request and native worker path; the restart case uses separate Python processes and an independently counted SDK-effect file.

Replay admission now uses one SQLite transaction over nonce identity, expiry cleanup and a durable clock high-water. Only one worker using the same file can claim a nonce. Full synchronous commit precedes entry into the terminal operation. The original ten-skew-window cache retention remains bounded; clock rollback cannot make purged envelopes fresh again. Corrupt or missing clock data with existing history, store lock/failure and lost commit acknowledgement fail closed.

The default file derives from the existing backend signing-key profile. Programmatic profiles must bind persistent state; there is no silent in-memory production fallback. Nonce identifiers are stored as text to preserve the client's unsigned 128-bit namespace. The client renews its random namespace before its 32-bit local sequence overflows. Malformed request/header types and non-ASCII signatures produce typed refusals before SDK access.

No request body, broker password, signing key or financial result is retained in this cache. A nonce claim is not evidence that an order executed or did not execute. Uncertain original broker effects still use the existing reconciliation and financial fences. The source checks cover shared-file workers, process restart and observed corruption/clock cases; they do not certify arbitrary filesystem rollback, multiple unshared host stores, Windows deployment or a broker outcome.

The source receipt includes 91 focused tests, the complete actual-PostgreSQL trading run, eight passing controls with eight assertion-detected faults, source restoration and cleanup. Existing provider, independent, production and handset gates remain. No new frontend or Android configuration is introduced.
