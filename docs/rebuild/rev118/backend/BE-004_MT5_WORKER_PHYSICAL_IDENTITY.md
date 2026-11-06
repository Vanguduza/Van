# MT5 worker physical identity and serialized dispatch

Candidate worker source only. Tests run the real Python worker and its mTLS/HMAC transport with an injected terminal model; they do not connect to a financial provider.

Five original counterexamples showed that a signed request could send when the native server, currency or demo/live identity differed from the worker's configured alias, when permission was a truthy string, or when a cached login number was reused for a different server. Two positive controls already passed. A further correctly observed worker counterexample sent after login delayed the request beyond the signed time window; a client-side skew exception after that effect could not undo it.

The worker now requires a complete typed login/server/currency/demo profile before opening credentials. It preserves native server, trade mode and permission facts, verifies the complete physical identity on each request, and refuses missing, contest or ambiguous trade modes. Its login cache includes the server. Explicitly disabled trading still permits an identity-verified account read, while sending remains refused.

One terminal lock covers alias selection, native identity readback and the entire terminal operation. A coordinated two-alias test verifies that one request cannot switch the other's terminal between readback and sending. The signed entry time window is checked again immediately before dispatch, after waiting for login and the lock. Existing stop-tightening, protective-stop, HMAC replay, certificate and transport assertions remain.

Worker profile instructions now require explicit currency and a JSON boolean demo flag. Old incomplete profiles refuse until corrected by the host operator. No handset gateway or Hermes configuration is introduced.

The receipt records 45 focused passing controls, eight caught source faults after passing controls, restored bytes, rebuild checks and the full trading result. Native provider/terminal qualification remains separate. Linux registry-to-worker identity binding, pull-EA identity and numeric precision, complete original-command receipts, lease/epoch/deadline envelopes, physical migration and provider cash/fee finality remain original obligations; this repair does not claim to complete them.
