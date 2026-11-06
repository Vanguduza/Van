# cTrader and Deriv original entry deadlines

Candidate BE-004/BE-006 source correction, continuing the MT5 original-lifetime packet. No formal unit or native acceptance is issued.

Three before-change native-wire probes reproduce entries after expiry: cTrader while acquiring its send lock, and Deriv during native authorization or proposal handling. The router now supplies its original mandate/quote bound to these concrete native adapters as well as MT5. The controlled cTrader router test uses the real RiskAuthority and native framed transport; current requests execute once and stale requests do not write.

The transports expose a bounded entry primitive. cTrader checks after connection, serialization and acquiring the native send lock, immediately before sendall. Deriv checks after its operation lock, owner/account entry scope, connection, current token authorization and serialization, immediately before websocket send. The primitive rejects mixed or nonentry operations. Strict integer deadlines and current clocks reject booleans, malformed values, unavailable clocks and expired grants. A legacy transport cannot silently discard an explicitly supplied bound. Original unbounded component calls and protective operations keep their established behavior.

EntryNotSent identifies a refusal known to occur before the financial write. Once bytes may have been written, lost replies retain their original uncertainty and reconciliation requirement. Current time after an actual write cannot erase a genuine fill. This local guard cannot prove that a broker received or executed a request before expiry, and it does not cancel an already accepted order.

PROVIDER_ORIGINAL_ENTRY_DEADLINE_SOURCE_20261024.json retains three original failures, forty-one reviewed controls and seven semantic fault/restored pairs on the final source. A first Deriv fault survived because the test delayed authorization before the proposal rather than reauthorization inside buy. The strengthened oracle invalidates the token fingerprint after proposal, proves a second authorization occurred inside buy, and rejects the subsequent financial write after expiry. The initial survivor remains in the receipt.

The broader local attempt records 187 passes and one concurrency setup failure: this container could not start the second thread in an existing account-mutation test. A distinct retry could not start the first thread. No complete broader-suite pass is claimed. An earlier 137-case focused run passed before the final closed-operation additions. All original test files and assertions remain unchanged by this packet. Fresh hosted full trading qualification is still required.

The preceding MT5 EA was compiled by actual MetaEditor 5.0.0.6283 with zero errors and zero warnings, producing a fresh binary. Its deliberate invalid-source control produced four errors and no binary. Exact source and binary hashes are in NATIVE_METAEDITOR_3444ca5b.json; this is compilation evidence, not terminal account or broker execution.

Deriv native funding and economics, receipt availability clocks, setup lifetimes, margin/reservations and remaining backend features are separate unfinished work. No new API route, Android screen or blueprint-package change is introduced.
