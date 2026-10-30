# MT5 bridge worker (Windows)

MetaTrader 5 is a Windows program. `van-trading-core` is an ARM64 Linux VM, so the terminal and the
`MetaTrader5` Python package run on a Windows host and this worker exposes the narrow bridge protocol to
the Linux core over **mutual TLS** plus per-request HMAC signatures. The Linux side is
`vati.execution.mt5_bridge` (client) + `vati.execution.transports.mt5_http` (transport).

## Trust model

- TLS server certificate `mt5-worker.crt` and the client certificate `client.crt` are issued by the private
  CA created on `van-trading-core` (`pki/make-bridge-pki.sh`). The worker requires the client certificate.
- Every request is HMAC-SHA256 signed with `bridge.key` (32 random bytes, owner-only ACL). Nonces are
  single-use; `issued_ms` must be within 5 s of worker time.
- The worker refuses: an op outside the contract, an order without `sl`, a stop that widens, a terminal
  whose login, server, currency or demo/live identity differs from the configured alias, and a terminal with trading disabled.
- Broker passwords live only in `password_file`s on the Windows host. They never travel over the bridge.

## Install

1. Install MT5 and log in to the broker account once (demo first).
2. Copy `ca.crt`, `mt5-worker.crt`, `mt5-worker.key` from `/opt/van-trading/secrets/pki` on the Linux core.
3. `powershell -ExecutionPolicy Bypass -File install.ps1`
4. Put the generated `bridge.key` value into the Linux account secrets file
   (`/opt/van-trading/secrets/<alias>.env`: `BRIDGE_SIGNING_KEY=…`, `BRIDGE_CA_FILE=…/pki/ca.crt`,
   `BRIDGE_CLIENT_CERT=…/pki/client.crt`, `BRIDGE_CLIENT_KEY=…/pki/client.key`).
5. Add the account to `worker.json` → `accounts.<alias> = {login, server, currency, demo, password_file}`.
6. On the Linux core: `python -m vati accounts add --alias <alias> --broker MT5 --bridge-url https://<worker-host>:9443 --secrets-file /opt/van-trading/secrets/<alias>.env --server <Broker-Server> --login <login>`.

Where the Windows host lives is the owner's choice (an x86 OCI Windows instance in the same VCN is the
straightforward option; the firewall rule in `install.ps1` admits only `10.0.1.233`).

Each alias must explicitly declare `currency` and a JSON boolean `demo`; older incomplete records refuse until corrected. The worker reads native server and trade mode on every request, preserves explicit terminal permission facts, and serializes login, readback and terminal operations across concurrent aliases. Its login cache includes the server. These are source safeguards; native terminal and deployment qualification remain required.

The Linux factory signs its expected physical account into each request. The worker validates that binding within its terminal lock and acknowledges the native identity it observed. Factory clients preflight this acknowledgement before effectful calls, so an older worker is refused before receiving an entry. Fresh connections use independent nonce namespaces while original signed requests remain protected against replay.

Explicit `OrderCommand.expires_at_ms` deadlines use `order_send_expiring`. The Linux client checks a current `entry_constraints` capability response and signs the unchanged absolute expiry into the request body. The worker requires a valid integer deadline for this operation and checks its own clock after final native reads, immediately before SDK entry. Older workers reject the distinct operation, including a rollback after the capability read. Commands without an explicit deadline retain `order_send`; no new financial deadline default is selected.

These checks depend on the original clock-synchronization and native deployment gates. They do not issue a risk-budget, lease-epoch or broker-acceptance certificate. Android uses the existing backend flow and gains no host/configuration setting.

Replay state now persists in a SQLite file beside the existing signing-key file (`<key filename>.nonces.sqlite3`), with full synchronous commits. Backend profiles can explicitly bind `nonce_store`; an absent persistent binding has no in-memory fallback. The file retains only nonce/timing metadata, using the existing ten-skew-window retention. A durable clock high-water refuses substantial clock rollback before purging history. Store failure or inconsistent replay-clock history refuses admission.

This protects workers sharing that file and process restarts; the nonce claim is separate from the broker's execution outcome. Original uncertain trading effects still require reconciliation. Native deployment, filesystem protections, disk/snapshot recovery and financial risk authority retain their original qualification requirements.

## Original prospective-margin read

The signed worker now supports `expected_margin`, a read through the native SDK's `order_calc_margin`. It preserves the original product, side, quantity and requested price; validates native increments and representable inputs; brackets the calculation with account/contract observations; and rechecks the unchanged deadline after native I/O. Missing precision, mode, leverage, identity or margin remains unavailable. This read continues when trading permission is disabled and never invokes `order_check` or `order_send`.

The EA source has the corresponding `MARGIN_QUOTE` read with its own advertised capability and an identity-bound 18-field deadline frame. Older or untyped capabilities refuse before enqueue. Expired queued reads never reach the terminal. The core retains native binary64 round-trip metadata and the EA's UTC-second uncertainty interval, then independently checks decimal increments, scope and expiry. A successful queue read is distinct from an entry claim.

Both adapters feed the existing `NativeMarginBook` with an immutable original observation, request identity and account context. SQL restart and lost storage acknowledgement recover the original record without repeating the native read. The isolated estimate excludes existing positions and pending orders; `reservation_amount` remains absent and no reservation, settlement, native qualification or execution grant is issued. Native MetaEditor compilation, actual terminal/provider behavior and deployment still require evidence for the exact modified source. Android configuration remains behind the existing provisioned backend profile.


## Original native instrument terms

The signed worker supports the read-only `symbol_contract` operation with an exact symbol and absolute `deadline_ms`. Both public MT5 adapters return immutable original account-bound metadata. Native loss/profit tick values, tick/quantity rules and base/profit/margin currencies remain separate. An explicit zero loss value is retained as `UNPRICED`; missing/invalid values, a changed account or expiry are unavailable. The legacy `sync_symbols` shape is preserved, with an additional native identity read after SDK access so a terminal account switch cannot retain the old response label.

The EA counterpart is `SYMBOL_CONTRACT`, advertised by `symbol_contract_constraints` with its exact18-field identity/expiry frame. This read is excluded from native entry claims. Old capabilities refuse before enqueue; queued expiry refuses before native handoff. Original binary64 text and the UTC-second uncertainty interval are retained.

`NativeSymbolBook` binds the observation to the existing independently read MT5 account-query journal before a risk decision exists. It preserves original request/queue identity, committed SQL readback, replay, expiry-at-writer, namespace isolation and recovery after lost storage acknowledgement without repeating the native read. It stores small risk-input observations, not a full market feed/catalog in the financial log.

These are original terms from native APIs. Their receipt does not prove a separately timestamped FX conversion, atomic account snapshot, current financial eligibility or risk/portfolio reservation. All qualification/execution flags remain false. The modified EA still requires exact-source native compiler evidence after publication; actual terminal/provider, deployment, signing and handset acceptance remain separate. No production profile or owner address-entry flow is changed.


## Original native quote snapshots

The signed `quote_snapshot` read and EA `QUOTE_SNAPSHOT` retain original bid/ask/last values, native full-tick time, volume fields, subscription/delay facts, account scope and contract terms before/after the read. The EA advertises an exact identity/deadline18-field capability; legacy capabilities and queued expiry refuse before native handoff. Reads do not invoke order checks or sends and remain independent of trading permission.

`Mt5QuoteObservation.snapshot` evaluates the native tick age at the requested current clock. Missing quotes/sides/timestamps, future/inconsistent time, crossed prices, delayed subscriptions, unknown entitlement and stale data retain distinct states. There is no local-time fallback for missing native tick time. A current observed snapshot stays explicitly unqualified. Native full-tick time is not a fabricated individual bid/ask update time; last-trade volume is not lots or genuine market depth.

`NativeQuoteBook` reuses the original-account-query SQL owner with a distinct record kind and unchanged symbol-record compatibility. Historical lookup, independent reopen, expiry and lost-ACK recovery preserve original tick time and cannot freshen data or issue a financial grant. Quote/metadata source tests are separate from native provider, FX/risk eligibility and production qualification. The modified EA requires new exact-source compilation evidence after publication.
### Final cash-backed entry margin

Both SDK and EA entry paths calculate the proposed order's native isolated margin before native handoff. They compare it with the smaller of reported free margin and cash equity minus credit and used margin, retaining the original account currency/precision and scope. Available amounts round down to declared account units; requirements round up. The Python path uses exact rational arithmetic over original native text. The EA uses original 17-digit text and integer-string arithmetic, including large values beyond binary64 integer precision. Neither path sizes a trade or turns a margin read into permission.

Unknown native requirements, cash facts, precision or scope refuse before dispatch. `NATIVE_CASH_MARGIN_UNAVAILABLE` and `NATIVE_CASH_MARGIN_INSUFFICIENT` remain distinct in the original reply and rejection reason. Explicit zero native margin can proceed with positive cash capacity and all existing authority checks. The final guard rechecks cash, identity, permissions and the original deadline; margin calculation cannot renew authority. Tightening protection and closing retain their existing risk-reduction paths.

This final check does not implement shared all-origin reservations, fee/fill-price contingency, post-entry margin floors, full contract/FX migration or economic finality. Those remain required under the core Risk Authority and existing financial owners. Unchanged legacy frame shapes do not qualify an old peer that lacks this source. Actual deployment/admission and native/provider/device qualification remain separate.

Source arithmetic qualification additionally requires **g++ with C++17** (available on the hosted Ubuntu source worker). `tests/rebuild/test_mt5_cash_unit_source.py` compiles the exact EA integer-string functions with an explicit API shim and compares them against an independent Python Fraction oracle. This is source arithmetic execution, not MetaTrader execution. The actual changed EA still requires its own official MetaEditor compilation and subsequent real terminal qualification.

The final entry fence also preserves the existing RiskAuthority 200% cash-backed
margin minimum after adding the original proposed isolated requirement to native
committed margin. It compares exact scaled integer bounds: cash equity rounds
down, credit/committed/proposed margin round up, and equality refuses entry.
Original-before, after-calculation and final native facts cannot renew a weaker
original budget. `NATIVE_CASH_MARGIN_FLOOR` is distinct from insufficient free
cash and unavailable facts. Explicit zero requirement on positive cash remains
supported; protective tightening and closing retain their existing controls.

This is a refusal fence derived from the existing risk owner, without new sizing
or financial authority. Source checks bind both native constants to the current
RiskAuthority minimum. The 200% value remains an inherited starting floor, not a
measured optimum or profitability claim. Stricter current policy remains with
RiskAuthority. A changed policy/native source cohort needs independent
qualification. Isolated proposed margin is not an atomic native portfolio margin
snapshot or a shared reservation. Fill-price/fee contingencies, transactional
all-origin reservations, native working-order reconciliation and economic
finality still require their complete qualification.

When committed native margin is positive, the lower original broker-reported
margin level remains binding as well. Its absence is unavailable evidence.
Both native paths retain the original reported-level × used-margin product;
used margin below one currency minor unit is not rounded to zero before that
product. The SDK uses exact Fraction; the EA compares original decimal mantissas
and exponents with integer-string multiplication. This retains the stricter
reported bound without inventing a new percentage precision or native capital.
The percentage-derived constraint remains an exact ratio; it is not rounded a
second time into a spendable cash balance. Both native transports therefore keep
strictly above-floor reported observations eligible under the unchanged guard,
while equality and lower observations refuse. Actual cash and monetary margin
commitments retain their original conservative unit rounding.

## Recorded entry charges and cost availability

The candidate worker can attach `recorded_entry_charges` with schema
`van.mt5.recorded-entry-charges/1` to a protected filled/partial result. It reads
the exact returned deal through the Python SDK's **order-ticket** history
filter, checks its order, stable position identifier, native position ticket,
symbol, side, entry type and filled volume, and retains native commission/fee
cash components with the observed account identity. The core requires its
registered identity and the matching original result before deriving a recorded
cost. Explicit zero is measured data; absent or mismatched fields remain null.

This is an immediate entry-deal observation, not complete fees, a fee schedule,
native sign qualification, settlement or financial authority. Deferred
daily/monthly commission, financing, later fills/charges and closing costs need
their original reconciliation owners. Optional cost reads are skipped when the
native stop is unconfirmed so they cannot delay protective recovery. A known
fill with unavailable costs stays a known fill, with a durable receipt-bound
unavailable-cost fact and no numeric TCA. Old sealed receipts are not rewritten.

Native/provider qualification, deployment and terminal acceptance remain
required. This source packet does not install a worker or qualify an account.
