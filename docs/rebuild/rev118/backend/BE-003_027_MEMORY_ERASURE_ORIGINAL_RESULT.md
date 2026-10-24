# Original owner-memory erasure result

The approved erasure service executed again when called with the same command identity. A retry could delete owner facts created after the original erase, replace its witness, and increment the context revision again. Two signed-owner counterexamples reproduced the repeated deletion and witness loss; the broader ten-case baseline produced eight failures and two positive controls.

Inside the existing SQLite transaction, erasure now checks the sealed owner command, exact store/record scope and active device, then reads an existing committed witness before considering any new deletion. A matching original returns its original counts without rewriting the witness, invalidating context again or deleting later facts. Exact-record recovery does not require the already erased row to exist.

An expired command can read its existing original receipt through this internal recovery path; it gains no new deletion authority. New erasures still require fresh exact approval, active-device and expiry checks. A revoked device cannot use the erasure executor to read its original receipt. The ordinary independently authenticated owner-read and command paths retain their own current authorization checks.

Witness schema, scope, identity hashes, primary-key columns, counts and context-revision transition must be valid. A malformed or foreign witness refuses another erase. Legacy witnesses without the added device field remain readable only through their original sealed device authority and exact original scope. They are not rewritten as new evidence.

Recovery of the original effect is distinct from the current contents of the store. Later memory may make the current bulk-erasure readback nonempty; this change does not claim that such memory is absent. The owner can issue a separate fresh approved command to erase it.

Verification covers actual signed A4 commands, independent SQLite post-state, duplicate concurrent execution, committed effect with a lost domain reply, later memory preservation, exact-record recovery, expiry, revoked devices, damaged witnesses, legacy evidence and a separately approved new erasure. Five meaningful faults are caught after passing controls, with source restored. The first test setup omitted the existing fixture's environment binding and failed at pairing; that attempt is retained separately and is not a product counterexample.

This is a BE-003/027 source milestone. Audit/mission retention, the original allowlisted memory scope and all 131 programme units remain unchanged. No new frontend or complete privacy, independent, production or handset qualification is issued.
