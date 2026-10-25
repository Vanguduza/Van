# BE-020: persistent owner market monitors — candidate source

Status: **IN_PROGRESS**. This packet adds real controls, persistence and server evaluation, but does not complete BE-020 or qualify a live provider, new Android UI, F15, BG-001 or handset acceptance. The frozen programme remains 131 units, 324 requirements, 1,610 acceptance identities, 234 contexts and 349 actions.

## Implemented source

Saved screener rules now persist an explicit instrument universe, timeframe and closed level predicates. CRUD uses the same original-operation and revision protocol as other monitor settings. Running a saved rule requires its exact revision and returns the captured rule ID, revision and state hash with the measured rows; a later edit cannot relabel those results. Runs consume the existing durable quota per request and never create a mission, alert or order. Migration 59 preserves all version-58 rule bytes in one transaction and can replay after a lost version marker.

Owner watchlists persist complete venue/environment/API-family/product/account/contract selections, favourites, manual ordering and sort/filter preferences. Matching symbols on different native scopes stay distinct. Saved selections are owner context, not evidence that a native feed has been bound.

The market-row read contract captures an exact saved watchlist revision and hash before source reads. It applies favourites, literal symbol/product/venue search and explicit venue/environment/API-family filters, then the saved ordering and direction. Equal metrics retain owner order; missing metrics remain last in either direction. Closed-bar rows expose exact close, age, source revision/hash and availability. Percentage change means the preceding contiguous bar, with the reference price/time and interval supplied; it is not labelled a daily return or a tick quote. Missing history and a zero reference have distinct states. A closed-bar source supplies no bid/ask spread, so spread remains null with an explicit reason. Source failures, stale/future/mis-scoped observations and clock rollback cannot turn into current values. Reads create no commands, operations, alerts, missions or orders and cannot change saved preferences.

Alert rules support closed-bar price levels/crossings; SMA, EMA, simple-window RSI/ATR, MACD, Bollinger and anchored VWAP measurements; crossings of an immutable level or trend drawing; and literal news keywords with ANY/ALL and declared T1/T2 trust thresholds. News instrument relevance requires an explicitly recorded symbol; no model infers it. Other drawing geometries and tick-price bases are refused rather than silently reinterpreted.

Controls create, replace, pause, explicitly restart and delete rules. Every control binds its request ID to operation, kind, object, expected revision and exact payload. Repeating an original request returns its original minimal receipt, including after later edits or deletion. A changed payload or stale revision conflicts. Delete removes saved names, keywords, drawings and evaluation state; minimal receipts prevent delayed creates from resurrecting them. No rule text is copied to event history.

A service restart preserves the current arm. An explicit owner restart creates a new arm; a level that is still satisfied can trigger in that new arm. A crossing first establishes a qualified baseline and then requires a newer contiguous observation from the same source revision. Duplicate, corrected, out-of-order, gapped, stale, future or differently scoped observations cannot manufacture a crossing. Replacements reset measurement history; a triggered or paused rule remains triggered or paused until explicitly restarted.

The service rechecks freshness after acquiring the write lock, before publishing. A persisted clock high-water mark prevents wall-clock rollback from generating a backdated trigger or being cleared by a rule edit. Invalid clocks are unavailable, never substituted with zero.

Screener requests have a closed typed vocabulary of level predicates, at most 64 distinct instruments and four conditions. An atomic, durable 256-instrument-per-minute owner budget survives service instances and restarts; rollback does not refill it. Reads return explicit unavailable rows with no invented price or age. Each measured row carries its own evaluation time and price age.

## Existing runtime integration

Migration 58 adds owner monitor state, minimal operation receipts, one quota row per owner and an event projection witness to the existing gateway Store. Migration from the actual version-57 migrations and real backup/restore are tested. Schema 59 adds saved-screen rules with an atomic table rebuild; injected SQL failure rolls back the original tables and data, and a missing post-commit version marker can be replayed without losing existing or saved-screen rules.

The existing OpsScheduler registers `trading.market_monitors`. Rule transition, canonical `trading.alert.triggered` event and its projection witness commit in one SQLite transaction through the existing EventBus envelope. There is one event ID per owner/rule/arm, shared by all enrolled devices. Publishing cannot dispatch a command, mission or order.

Attention projection uses that event ID as its dedupe key. A crash or lost acknowledgement after Attention writes can be repaired after restart, even if the owner deleted the rule; repair preserves an acknowledged item. No second device stream, per-device sequence or independent notification store was introduced. OS push/notification delivery still requires Android/device qualification.

Global gateway ingress, current device-token, mTLS consistency and bound-device proof middleware cover the new routes. Owner mutation bodies do not choose an owner or device principal. Reads and typed errors carry no-store headers.

## Frontend contracts

All operations are under `/v1/trading/monitors`; OpenAPI provides closed request, response and error schemas.

| Contract | Methods |
| --- | --- |
| Capabilities and limits | GET /capabilities |
| Original control receipt | GET /operations/{request_id} |
| Watchlists | GET/POST /watchlists; GET/PUT/DELETE /watchlists/{object_id} |
| Watchlist market rows | POST /watchlists/{object_id}/market |
| Alerts | GET/POST /alerts; GET/PUT/DELETE /alerts/{object_id} |
| Alert controls | POST /alerts/{object_id}/pause; POST /alerts/{object_id}/restart |
| Saved screener rules | GET/POST /screen-rules; GET/PUT/DELETE /screen-rules/{object_id}; POST /screen-rules/{object_id}/run |
| Typed level scan | POST /screen |

DELETE and control operations carry `request_id` and `expected_revision`. The original receipt endpoint is the recovery path for uncertain responses. Conflict, unknown object/receipt, capacity, quota, invalid input, corrupt state and uncertain write outcomes remain distinct. Scans consume quota per request, including retries and unavailable data; they are read operations, not idempotent control commands. Market-row reads require `expected_revision`, accept a timeframe, maximum age and bounded filters, and return the captured list revision and hash. They read at most the 128 saved entries, make no native subscription and do not consume the screener quota.

Existing registry groups/surfaces receive additive backend contract bindings to VNX-F-TRADE-03, VNX-F-TRADE-04 and VNX-F-CHART-11 and their planned market/alert/screener contexts. Original functions, surface identities and historical qualifications remain intact. No redesigned screen or new Android consumer is claimed.

## Measurement and source boundaries

EMA and MACD use exact rational intermediate values and an explicit final Decimal conversion with precision 80. This prevents a mathematically zero histogram from becoming a positive alert through rounding cancellation. SMA/Bollinger/VWAP use Decimal arithmetic; simple-window RSI/ATR reuse the existing VATI feature definitions. These are an identified source calculation profile, not a claim of independently certified chart/indicator equivalence. Computed values are finite decimal strings, with exponent notation allowed for very small results; price and anchor inputs retain exact fixed-decimal syntax.

The source adapter reads the actual existing NEWS_HEADLINE ledger, including publisher-declared trust, content hash, explicit symbols, publication and receipt times. It considers the last 500 recorded headlines. Missing/malformed/untrusted/future/stale records cannot become live facts. A headline is a recorded report, not corroborated truth or trading permission.

The current symbol/timeframe bar lake does **not** prove venue, environment, account and native product identity. The default technical source therefore returns an explicit unavailable hold. A private server-source protocol validates full identity, revision, closed contiguous bars and availability; fixture producers exercise it in tests. There is no HTTP market-fact injection endpoint. Fixture identity-bound observations do not qualify a live producer.

## Remaining obligations retained

- BE-008/014: qualified native market/news producer readback, full instrument/entitlement binding, current source health and availability. No inference from a symbol or a VENUE label.
- BE-018/020: independently qualified indicator semantics and live tick-price alert bases; native quote/spread/session-change producers for watchlist rows and dynamic candidate/exposure/news/near-alert lists. Closed-bar row projection, search and explicit identity-group filters are implemented in source.
- BE-020: provider integration/failure/recovery and native postconditions beyond the recorded-ledger source path.
- BE-029/032: voice and canonical typed-command/action-catalog consumption of monitor controls. The current interface is the paired-owner REST contract.
- FE-006/007/013 and BE-030: Android consumer, exact chart/review deep links, orb/Attention presentation, actual OS notification dedupe, accessibility and S24 Artemis evidence. Alerts never authorize a trade.
- Canonical admission, independent review and all unit/gate acceptance dependencies remain unissued.

## Verification scope

The receipt records every executed run and retained failure. Actual SQLite tests cover original operations, migration, backup/restore, atomic event rollback, concurrent evaluation fencing, lost commit acknowledgements, quota persistence, real ledger news and Attention recovery. Deterministic fixtures cover exact calculations and stale/future/correction/scope refusals.

Scoped HTTP checks use the real application startup, auth, storage, middleware and routes. They disable the optional periodic scheduler through its supported setting, leave unrelated native recovery/revocation actor loops idle, and invoke the actual registered monitor job directly. They verify owner CRUD, real device signatures and one event across two real paired gateway identities. This scope does not substitute for full unisolated startup, native DIAL actors, live providers or physical Android.
