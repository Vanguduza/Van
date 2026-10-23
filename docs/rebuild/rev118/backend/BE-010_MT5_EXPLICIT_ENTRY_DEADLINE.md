# Explicit MT5 command deadline

`OrderCommand.expires_at_ms` existed in the core but the bridge omitted it. A command could reach the native SDK after its explicit expiry while still fitting the transport freshness window. The corrected baseline reproduces fifteen missing-contract failures and preserves the existing non-deadline positive control.

The client rejects malformed or expired deadlines before an RPC, checks current native capability, includes the unchanged absolute expiry in the HMAC-signed body and checks again after the read-only order precheck. It retains the original transport issue time. The worker validates the signed integer deadline after final native reads, immediately before SDK dispatch.

Deadline-bound entries use `order_send_expiring`. An old worker refuses this operation, including a rollback between capability read and dispatch; the client never falls back to the unbounded operation. The typed operation also refuses a missing deadline. Commands without an explicit deadline keep their existing operation and do not gain a newly selected financial timeout.

Source checks cover current native-clock expiry, delayed read-only precheck, delayed send-time quote, malformed values, missing/legacy capability, rollback, the unchanged non-deadline flow and the actual HTTPS/JSON/HMAC transport against a fixture terminal SDK. Clock synchronization remains an original deployment/activation obligation. This change does not issue lease-epoch or financial risk-budget authority.

Seven deliberate faults are detected after passing controls. The first native-expiry mutation survived because the quote delay occurred during the read-only precheck, where the client already refused it. The corrected oracle delays the second quote, after the client's final check, and detects the native fault. The initial survivor remains recorded. Full trading tests use actual isolated PostgreSQL and pinned DDS source; cleanup and source hashes are retained in the receipt.

The adjacent source-test storage guard now instruments path-based writable opens and rename/delete/link operations as well as SQLite/directory events. Fourteen planted filesystem attempts are refused while valid reads and temporary writes remain functional. Twenty DIAL boundary/API cases pass under the guard. It is Python test instrumentation, with explicit limitations; it is not a host sandbox or production qualification.

These are candidate source milestones. All original programme units, frontend gates, provider finality, native review and handset obligations remain.
