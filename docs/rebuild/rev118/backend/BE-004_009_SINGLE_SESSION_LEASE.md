# Candidate single-symbol runtime authority

The one-symbol production service now uses account runtime leases and a final submission guard, matching the existing account coordinator's shared authority boundary. Four constructor/control counterexamples were reproduced: missing router fencing, venue entry admitted with local storage, and owner halt/process stop arriving after the early check but still allowing a genuine strategy entry.

## Native wiring

`SessionService.build` binds the registered account to the existing PostgreSQL lease store whenever authority is shared. Venue-sending modes require shared PostgreSQL before native adapter construction. Paper simulation and non-sending observation retain a persistent local path through `SQLiteLeaseStore` in the existing SQLite authority file; this is explicitly a same-host fence.

Each constructed service has a distinct native holder identity. It acquires before the existing startup routine, renews on each loop and supplies its current epoch to the actual `DecisionCycle` router call. Router admission checks shared ownership; the final guard holds native arbitration through submission. Current renewal permission, process-stop state, mandate mode and published owner halt are checked again after acquiring that guard. A control arriving during acquisition blocks the adapter call. Heartbeats check current ownership rather than reporting cached permission.

The SQLite store uses the shared kernel alias lock for all lease readers/writers. Its submission guard holds that arbitration lock without a SQLite write transaction across adapter I/O: the router can append to the same authority file during submission. Native provider exceptions propagate unchanged through the public runtime guard. PostgreSQL retains its existing row-lock submission guard.

The PostgreSQL first-insert CAS also handles an absent-row race. `SELECT FOR UPDATE` cannot lock a row that does not exist; `INSERT ... ON CONFLICT DO NOTHING RETURNING` distinguishes a genuine competing admission from storage unreachability. Two actual PostgreSQL processes force both absent reads before insertion and confirm one grant plus one healthy refusal.

Runtime shutdown and startup failure release only their own lease, with cleanup in `finally`. Epochs remain persisted across release/reacquisition. A refusing peer cannot release the current holder. Owner halt is preserved after a temporary store failure. Read-only venue observation remains available, and existing protective paths are retained.

## Source evidence and preserved failures

`receipts/SINGLE_SESSION_LEASE_SOURCE_20261022.json` records exact source and test hashes. Tests exercise actual service construction/startup, separate native processes on SQLite/PostgreSQL, an eligible strategy reaching the real router, ownership changes, late halt/stop, guarded ledger writes and native exception identity. Seven induced faults are assertion-detected after a valid control; original source bytes are restored.

The first full trading run retained one failure: an older test manually attached a runner without invoking the native constructor. That fixture now uses the real registry, persistent authority file and `build`, while retaining its original unbound-history refusal/readback assertions. The next intermediate run passed 1,966 tests; the final receipt separately records validation after the late halt/stop fix.

An initial mutation targeted the inner store context, which does not receive the provider exception because the public runtime guard releases it with `__exit__(None, None, None)`. That neutral change survived and remains recorded. The corrected fault targets the actual public guard body; it is detected. Initial fixture/signature errors are retained separately from the four valid counterexamples and never counted as their proof.

## Remaining original contracts

This fences an account alias, not a proven physical broker identity shared by multiple aliases. Provider identity/provisioning, native policy/epoch admission, safe alias migration and retirement with exposure, orders, unknown money, active leases and retention obligations remain required. Single-symbol startup still needs its separate complete position-state restoration work; this lease packet does not certify it.

Already admitted effects retain their existing confirmation/unknown/reconciliation rules. No cancellation, flatness, broker finality or profitability assertion is added. Production latency/contention, current host deployment, independent gates, signed profiles and physical S24/Artemis acceptance remain separate. The frozen Rev1.18 package, original programme, financial limits, Android visuals and frontend gate are preserved.
