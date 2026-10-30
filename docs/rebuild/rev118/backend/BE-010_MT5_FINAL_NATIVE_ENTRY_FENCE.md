# Final native MT5 entry check

The worker checked signed request age, physical account and permissions before calling the terminal adapter. Native symbol, quote and exposure reads could then block. Four source counterexamples changed request age, account/server, trading permission or connection during a native quote read and still reached the SDK's entry call. A fifth counterexample covers time spent in the final native account read.

The production worker now supplies a private dispatch guard to `Terminal.order_send`. The terminal invokes it after request construction and native netting checks, immediately before `MetaTrader5.order_send`. It rereads the configured physical account and native permission/connection state, then checks the original signed issue time after that read. A failed check returns a zero-volume rejection before any SDK entry effect.

The guard is a server-side callable, not a serialized request field or Android setting. Existing authentication, nonce handling, the worker's terminal lock and the narrow HMAC/mTLS protocol remain in use. Native source tests include the genuine current-request positive control and the existing HTTPS/mTLS exchange. The custom terminal used by the alias-concurrency test now implements the same final callback boundary before its simulated effect.

This enforces the existing signed transport freshness window at the final SDK boundary. It does not implement the original programme's complete command deadline, lease-epoch or financial risk-budget envelopes, and separate native reads are not an atomic broker snapshot. Those original producer, activation and qualification obligations remain.

The receipt records reproduced failures, focused and full isolated-PostgreSQL source results, five assertion-detected faults with passing controls, restored source hashes and cleanup. These are candidate BE-010 milestones; no Windows terminal execution, real broker order, complete unit or handset acceptance is claimed.
