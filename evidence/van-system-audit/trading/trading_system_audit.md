# VAN Trading System Audit — read-only, evidence-first
Repo: /home/user/Van  branch: claude/van-system-audit-ysgtcd  HEAD: dff38a0
Auditor: trading-systems / risk-architecture
Status: IN PROGRESS (appended incrementally)

---

## Q1. TOPOLOGY — the actual dependency graph

### 1.1 The real spine (one process, one account alias)

`python -m vati serve --account <alias>` (trading/vati/__main__.py) →
`SessionService.build()` (trading/vati/app/service.py:122) →
`SessionRunner` (trading/vati/app/runner.py:21) →
`DecisionCycle.step()` (trading/vati/app/cycle.py:127).

The cycle is the ONLY place where the chain is assembled end to end:

| Link | Code | Verdict |
|---|---|---|
| bars → market state | cycle.py:131 `build_market_state(...)` → trading/vati/intelligence/market_state.py:? | REAL (pure functions over Bar lists) |
| market state → strategies/arbiter | cycle.py:137 `self.engine.assess(...)` → trading/vati/arbiter/opportunity.py | REAL |
| arbiter → TradeIntent | trading/vati/arbiter/opportunity.py (`oa.intent`), cycle.py:141-143 | REAL |
| intent → Risk Authority | cycle.py:145 `self.authority.evaluate_safe(intent, snap)` | REAL |
| decision → Execution Router | cycle.py:158-160 `self.router.execute(...)` | REAL |
| router → venue adapter | trading/vati/execution/router.py:81 `adapter.submit(cmd, now_ms=now_ms)` | REAL |
| adapter → broker | see Q5 — transports exist as code; none is live-attested |
| everything → ledger | trading/vati/core/ledger.py (sqlite) / ledger_pg.py (Postgres) | REAL |
| ledger → commander | trading/commander/app.py:123-125 `open_ledger(st.ledger)` | REAL (read-only + 1 write: halt) |
| ledger → VAN gateway | backend/van_gateway/trading/service.py:63-68 `_open()` opens the ledger **directly** | REAL but see Q7 — it is the gateway's OWN path, not the commander |
| gateway → Android | backend/van_gateway/app.py:770-878 (`/v1/trading/*`) | REAL routes |
| trade state → VAN visual/experience layer | **nothing** | ABSENT — see Q4 |

### 1.2 Market-data feeds
- trading/vati/market_data/feeds/lake.py — `BarLake`, a local parquet/CSV-ish bar store. REAL but a *store*, not a live feed.
- trading/vati/market_data/feeds/csv_source.py (43 lines) — file reader. REAL, offline.
- trading/vati/market_data/feeds/dukascopy.py (91 lines) — HTTP tick downloader. REAL code, batch/historical, not a live tick stream.
- trading/vati/execution/ctrader/feed.py (23 lines) — the only *streaming* price feed, and it is 23 lines.
- `SessionService` only ever gets bars from `lake_bar_source` (service.py:231-235), i.e. **a file on disk**. There is no wiring from any live feed into the running session. The "feed → intelligence" link is therefore: file → cycle.

### 1.3 Commander is NOT in the order path
`trading/commander/app.py:28` COMMANDS = status, ledger_status, services, restart_service, tail_log, run_backtest, vekl_resolve, halt, doctor, accounts (+ account onboarding commands).
There is no order/trade command. The commander's only write to the trading plane is `cmd_halt` (app.py:225-237), which appends a KILL_SWITCH event. Confirms: commander cannot place an order.

### 1.4 "Examples" / scaffolding in the graph
- trading/examples/mandate.fx_primary.example.json:46 — `"owner_signature_ref": "sig:owner-device:REPLACE_WITH_DEVICE_SIGNATURE_REF"` — the only shipped mandate is a placeholder.
- trading/strategies/registry/*.json — 6 capsules; these are real registry records consumed by CapsuleRegistry.
- trading/architecture/proposed/automation_browser_fabric_layers.json — explicitly `proposed/`.

---

## Q2. RISK AUTHORITY

### 2.1 Where it is
`trading/vati/risk/authority.py:93` `class RiskAuthority`, `evaluate()` at :137, `evaluate_safe()` at :127.
13 ordered, fail-closed gates (kill switch → account identity → mandate/mode →
duplicate intent → platform health → instrument/strategy eligibility → event/weekend →
loss limits & drawdown → position counts → risk clamp → edge-vs-cost → sizing →
post-trade heat/currency legs → final invariant re-check).
Every outcome is sealed with a SHA-256 `decision_hash` (authority.py:120-124).
`evaluate_safe` turns any internal exception into `REJECTED / AUTHORITY_FAULT` (authority.py:133-134).

### 2.2 Can anything reach a broker without it? — enumeration

**Every order-submission entry point:**
| `submit()` implementation | file:line |
|---|---|
| `VenueAdapter.submit` (protocol) | trading/vati/execution/base.py:116 |
| `OwnerTicketAdapter.submit` (ZSE) | trading/vati/execution/zse_ticket.py:60 |
| `Mt5PullAdapter.submit` | trading/vati/execution/mt5_pull.py:170 |
| `PaperAdapter.submit` | trading/vati/execution/paper.py:51 |
| `Mt5BridgeAdapter.submit` | trading/vati/execution/mt5_bridge.py:89 |
| `DerivAdapter.submit` | trading/vati/execution/deriv.py:81 |
| `CtraderAdapter.submit` | trading/vati/execution/ctrader/adapter.py:143 |

**Callers of any `.submit(...)` in non-test code: exactly one** —
`trading/vati/execution/router.py:81`. (Verified by `grep -rn "\.submit(" trading/ backend/ --include=*.py`;
all other hits are in trading/tests/*.)

**Callers of `ExecutionRouter.execute` in non-test code: exactly one** —
`trading/vati/app/cycle.py:159`, which is reached only after
`decision = self.authority.evaluate_safe(intent, snap)` at cycle.py:145 and an
early return on `Decision.REJECTED` at cycle.py:148-149.

**Router's own independent re-verification (defence in depth), router.py:50-74:**
- kill switch halted → refuse (:50)
- decision belongs to this intent (:52)
- decision is APPROVED/REDUCED (:54)
- `recompute_decision_hash(decision) != decision.decision_hash` → refuse (:56) — a forged or edited decision cannot be used
- decision's mandate_id/version must match the mandate handed in (:58)
- mandate must be order-sending (:60)
- idempotency key replay, seeded from the ledger at construction (:41, :62)
- venue adapter must exist and heartbeat (:64-71)
- stop-distance order without a protective stop → refuse (:73)

**Commander:** trading/commander/app.py:28 — no order command exists; the only mutating
trading command is `halt` (:225). MCP tool list further hides credential commands (:281).
**Gateway:** backend/van_gateway/trading/service.py — docstring :1-5 "never creates, sizes,
modifies or cancels an order"; the only writes are `halt` (:214) and `confirm_ticket` (:228).
**Model/LLM:** no LLM client anywhere in trading/ (grep for anthropic|openai|llm|gpt returns only
comments). The one model-shaped input is `MetaLabeler.t2` (trading/vati/arbiter/meta_labeler.py:96-101),
and it is **reduce-only**: disagreement can force WAIT or shrink the confidence multiplier, never raise it.

**VERDICT: no model, UI, commander or gateway path can send a broker order without the Risk
Authority.** The order path is a single funnel: cycle.py:145 → :159 → router.py:81.

### 2.3 Owner-signed mandate verification — **P0 WEAKNESS**
`trading/vati/risk/mandate.py:156-157`:
```python
if not str(data["owner_signature_ref"]).strip():
    raise MandateError("mandate is unsigned (owner_signature_ref empty)")
```
That is the **entire** verification. There is no signature algorithm, no public key, no
authority record lookup, no revocation check anywhere in the repo. The same
non-empty-string-is-a-signature pattern repeats at:
- `KillSwitch.clear` — trading/vati/risk/governor.py:51-53
- `SessionRunner.owner_halt` — trading/vati/app/runner.py:55-57
- `CapsuleRegistry.promote` — trading/vati/strategies/capsule.py:101-102
- commander `cmd_halt` — trading/commander/app.py:226-228
- gateway `_require_signature` — backend/van_gateway/trading/service.py:208-212

Consequence: anyone who can write the session config JSON (or reach the gateway's
internal-token endpoint) can mint a mandate that the Risk Authority treats as owner-signed,
subject only to `PlatformCeilings` (mandate.py:60-70, max 2%/trade, 6% heat, 5% daily,
10% weekly). Ceilings are the real last line of defence, not the signature.
Also `intent.owner_authority` is a literal `"MANDATE"` string set by the engine itself
(trading/vati/arbiter/opportunity.py:86) and checked as a string at authority.py:161 — decorative.

### 2.4 NO_TRADE outcome
Real and first-class. `OpportunityEngine.assess` returns `decision="NO_TRADE"` (or `"WAIT"`)
with `intent=None` (trading/vati/arbiter/opportunity.py:72-77); `DecisionCycle.step` returns a
`CycleResult` and logs `OPPORTUNITY_ASSESSMENT` without ever touching the authority
(cycle.py:139-142). `CycleResult.decision` vocabulary is documented at cycle.py:64:
`NO_TRADE | WAIT | SKIP | REJECTED:<code> | APPROVED | REDUCED | ROUTER_REFUSED`.
Warmup also yields NO_TRADE (cycle.py:129-130).

### 2.5 Kill switch
`trading/vati/risk/governor.py:39-59` — latching set, `halted` = any trigger active,
`clear()` requires a (string) owner signature. Trips are wired at:
- router venue heartbeat failure → `VENUE_DISCONNECT` (router.py:69)
- unconfirmed protective stop after a fill → flatten + `STOP_REJECTED` (router.py:85-91)
- startup: unverified account, disconnected venue, failed reconciliation (runner.py:31-37)
- owner halt (runner.py:58)
- gateway/commander append a `KILL_SWITCH OWNER_HALT` ledger event; the running service
  picks it up on the **next loop** via `_observe_owner_halt` (service.py:174-185).
**Gap:** the halt is asynchronous and polled at `poll_seconds` (default 5.0, service.py:60).
Between the owner pressing halt and the next `step_once`, a bar can close and an order can
be sent. There is no synchronous channel from gateway/commander to a running session.
**Gap 2:** `_observe_owner_halt` only scans events with `ev.event_time_ms >= self._started_ms`
(service.py:181) — a halt recorded *before* the session started is ignored, so restarting the
service silently clears an owner halt. `restart_service` is an exposed commander command
(trading/commander/app.py:97).

### 2.6 Duplicate execution / idempotency
Three independent layers:
1. `RiskAuthority._seen_keys` — in-process set, checked at authority.py:165, added at :326.
2. `ExecutionRouter._seen` — **seeded from the ledger** at router.py:41
   (`{e.payload["idempotency_key"] for e in ledger.iter(EventKind.ORDER_COMMAND)}`), so it
   survives a process restart. Checked at :62.
3. Adapter-level: `Mt5PullAdapter` and the Windows worker key on the command hash (see Q5).
The key itself is deterministic: `canonical_hash({"seed": f"{session_id}:{state.as_of_ms}", "decision": decision_hash})[:32]`
(trading/vati/arbiter/opportunity.py:83). Because `session_id` embeds a start timestamp
(service.py:137), a **restarted session re-deriving the same signal on the same bar produces a
different idempotency key** — layer 2 will not catch it. Layer 2 only protects against replay
of the *identical* key.

### 2.7 Stale market state
- `RiskSnapshot.data_fresh` → rejection `STALE_DATA` (authority.py:169-170), derived from
  `quote_age_ms` vs `max_quote_age_ms` (default 5000 ms, cycle.py:52).
- `HorizonArbiter` also consumes `state.quote_age_ms` (opportunity.py:56).
- `SessionService.step_once` classifies LIVE/DELAYED/STALE from bar age and emits
  `MARKET_DATA_HEALTH` (service.py:201-203). **But**: when the state is DELAYED or STALE it
  still calls `on_bar` (service.py:204); it merely passes an older `last_quote_ms`, relying on
  the authority's STALE_DATA gate. It never stops the cycle itself.

### 2.8 Races and hardcoded snapshot fields — **P0 OBSERVATION**
`DecisionCycle.snapshot()` (cycle.py:109-119) builds the RiskSnapshot the authority judges.
Three of the authority's "platform health" gates are **hardcoded to pass**:
```
cycle.py:118   reconciliation_ok=True, ... risk_store_ok=True,
cycle.py:119   tier1_event_blackout_active=False,
```
So `RECONCILIATION_FAILED` (authority.py:173), `RISK_STORE_UNAVAILABLE` (:177) and
`EVENT_BLACKOUT` (:197) can never fire in the live path — they are only reachable from tests
that construct a snapshot by hand. Startup reconciliation is checked once in
`SessionRunner.startup` (runner.py:35-37); there is no per-bar reconciliation.
`market_integrity` is `self.integrity` (cycle.py:88) which is initialised to `NORMAL` and
never written by any code in trading/ — so `MARKET_INTEGRITY` (authority.py:179) and the
`MARKET_ELEVATED_HALF_SIZE` reduction (authority.py:240) are also dead in the live path.

Other race/ordering notes:
- `snapshot()` is taken **after** the signal is produced (cycle.py:131 → :144), so the
  decision is made against a fresher account state than the market state it was derived from.
  Acceptable, but the two hashes in the ledger are not from the same instant.
- Single-threaded per account process; `_seen_keys`/`_seen` are plain sets with no lock. Two
  `serve` processes for the same alias would not see each other's in-memory sets, only the
  ledger-seeded router set. Nothing prevents two processes for one alias (heartbeat file would
  collide, but that is advisory only — service.py:152).
- cycle.py:150-153 contains dead code (`sig_targets = ()`, `for c in oa.candidates: pass`);
  targets are re-derived from `expected_gross_move_pct` rather than from the winning signal
  (cycle.py:155-157), so the strategy's own target is silently discarded.

---

## Q3. ACCOUNTS

### 3.1 Multi-account abstraction
`trading/vati/accounts/registry.py`:
- `BrokerKind` (:27-34): MT5 (Windows worker, push/mTLS), MT5_EA (MQL5 pull bridge), DERIV,
  CTRADER, PAPER, ZSE_OWNER_TICKET.
- `Account` (:48-100): alias, broker, mode, currency, server, login, venue, bridge_url,
  `credential_ref`, demo, enabled, `mandate_ref`.
- `Account.validate` (:65-82) refuses credential-shaped fields (:74-80) and refuses a live
  non-demo account without a `mandate_ref` (:81-82).
- `router_venue` (:84-86) maps broker → venue key.
- `safety_identity` (:94-100) → PAPER | READ ONLY | DEMO | LIVE.
- `credentials()` (:157-168) resolves secrets from an env var or a **0600, caller-owned**
  secrets file (`load_secret_file` :103-120). Registry itself never stores a secret.
- `public()` (:88-92) strips the credential to `{"kind": "env"|"file"|"none"}`.

`SessionService` is **one process per account alias** (service.py:1-9), and it refuses to start
when the mandate's alias or live/demo identity disagrees with the account record
(service.py:126-132). That is a real, meaningful cross-check.

### 3.2 Signed onboarding
`backend/van_gateway/trading/accounts.py`:
- `canonical_action` (:40-41) = `"trading-account"|device_id|issued_at|action|sha256(canonical_args)`;
  the gateway verifies an HMAC over this with the enrolled device secret (route at
  backend/van_gateway/app.py:811-858), `MAX_AGE_S = 300` (:31).
- Two backends: `LocalAccountControl` (:55-65, same handlers in-process) and
  `CommanderAccountControl` (:68-96, signed HTTPS to the trading VM commander using
  `commander.auth.sign_headers`).
- OAuth (Deriv, cTrader) flows through `OAuthPending` (:100-132) — Fernet-encrypted,
  900 s TTL, deleted on link (`consume`).
- The commander refuses these credential-bearing commands when `requested_by` is an agent
  (trading/commander/app.py:32-33, :295-297) and never lists them as MCP tools (:281).
**This onboarding signature IS cryptographically verified** (unlike the owner *mandate*
signature, Q2.3). Two different notions of "signed" coexist in this system.

### 3.3 Account state (balance / equity / margin)
- Source of truth: `VenueAdapter.sync_account()` → `AccountState(account_alias, equity,
  balance, currency, verified, hedging_mode, server_time_unix_ms)` — trading/vati/execution/base.py:93-101.
- **There is no `margin` / `free_margin` / `margin_level` field anywhere.** `grep -rn "margin"
  trading/` returns only `hedging_mode`. Margin is not modelled, not read from the broker,
  and not shown to the owner. Risk is stop-distance based only.
- Published once per bar as an `ACCOUNT_SNAPSHOT` ledger event
  (trading/vati/app/service.py:154-164), carrying equity, balance, currency, verified,
  connected, server_offset_ms, open_positions, peak/day/week equity, kill switch, mode.

### 3.4 How it reaches Android
ledger ACCOUNT_SNAPSHOT → `vati.app.portfolio.account_states` (trading/vati/app/portfolio.py:41-63)
→ `TradingService.accounts()` / `.portfolio()` (backend/van_gateway/trading/service.py:102-105, 93-100)
→ `GET /v1/trading/accounts` / `/v1/trading/portfolio` (backend/van_gateway/app.py:785-787, 781-783)
→ `TradingRepository.accounts()/portfolio()` (android/.../trading/TradingRepository.kt:19,22)
→ `AccountCard` (android/.../trading/TradingModels.kt:55-66) with equity, balance, floatingPnl,
dayPnl, drawdown, connection state, killSwitch, lastSyncMs, safety identity.
`connection_state` is `NEVER_SYNCED` when no snapshot exists (portfolio.py:61), which the app
renders as a named `DataState` (TradingModels.kt:37-42) rather than a blank — good.

---

## Q4. TRADE STATE → VAN EXPERIENCE  **(headline: the chain breaks at the gateway)**

### 4.1 Is there a formal classified trade/market state?
**Yes, inside trading/.** It is rich and well-formed:
- `MARKET_STATE` events carrying regime (trend/vol/phase), session, integrity, event window,
  `minutes_to_next_event`, `quote_age_ms`, features — trading/vati/app/cycle.py:134,
  built at trading/vati/intelligence/market_state.py.
- `OPPORTUNITY_ASSESSMENT` with decision ∈ TRADE|REDUCE_SIZE|WAIT|SKIP|NO_TRADE (cycle.py:139).
- `RISK_DECISION` with APPROVED|REDUCED|REJECTED + reason code (cycle.py:146).
- `CycleResult.decision` vocabulary at cycle.py:64.
- `MARKET_DATA_HEALTH` LIVE|DELAYED|STALE|NO_DATA (service.py:194, :202-203).
- 23 ledger event kinds at trading/vati/core/events.py:13-36.

### 4.2 Is it emitted as an *event* for the experience layer?
**No.** Every one of those is an append to the hash-chained ledger
(trading/vati/core/ledger.py / ledger_pg.py). Nothing publishes them onto a bus, a websocket,
a webhook or the gateway's own event stream.
- The gateway has an event replay surface — `GET /v1/events` (backend/van_gateway/app.py:742-747,
  `events.replay(device_id, after_seq)`) — and **no trading code writes to it**.
  `grep -rn "events.append\|events.publish" backend/van_gateway/trading/` → nothing.
- The only trading→gateway push is `degraded.set(DegradedCode.TRADING_LEDGER_UNAVAILABLE, ...)`
  (backend/van_gateway/app.py:753-767), and that only fires when someone *polls*
  `/v1/trading/status`. It is a health flag, not a trade state.
- Android is therefore **pull-only**: `TradingRepository` (android/.../trading/TradingRepository.kt:12-26)
  has 7 `suspend fun`s, all plain request/response. No stream, no subscription.

### 4.3 Is there any visual-state mapping?
`grep -rniE "aura|visual|presence|semantic_state|VanLiveVisualState"`:
- **trading/ → 0 hits.** (The only "experience" hits are `TRADE_EXPERIENCE_ARTIFACT`, a
  *learning* artifact, e.g. trading/vati/core/events.py:28, trading/vati/learning/episodes.py:42.)
- **backend/van_gateway/ → 0 hits** for aura/visual/semantic_state. The only `presence` hits are
  `requires_owner_presence` in the capability layer (backend/van_gateway/capability/models.py:124,
  registry.py:308-311) — unrelated to trading.
- **android/ → VanLiveVisualState exists** (android/.../visual/VanLiveVisualState.kt:17) and is
  driven from `VanGatewayClient` on *dispatch/approval* outcomes
  (android/.../gateway/VanGatewayClient.kt:419-459) — i.e. from the **command/approval** plane,
  never from trading data.
- The trading screen does use the visual system, but from a *generic* cue:
  `android/.../trading/TradingCommandCentreActivity.kt:78-81` —
  `val cue = VanPresence.cue(degraded)` … `VanPresence.visualState(cue)`. The input is the
  gateway's **degraded-code set**, not portfolio heat, not kill-switch state, not a trade outcome.

### 4.4 The closest thing that exists
`trading/vati/app/portfolio.py:115-124` `_van_summary(st, ds)` — builds an English sentence
("EURUSD: up trend, normal volatility, phase …; session LONDON; integrity NORMAL; data DELAYED.")
and ships it as `van_summary` in `/v1/trading/market-state` (portfolio.py:111). Android parses it
into `MarketStateCard.summary` (android/.../trading/TradingModels.kt:94). **That is prose for a
card, not a semantic state token.** There is no enum, no severity, no mapping table.

### 4.5 Exactly where the chain breaks
```
cycle.py:134/139/146  MARKET_STATE / OPPORTUNITY_ASSESSMENT / RISK_DECISION
        ↓ ledger append (trading/vati/core/ledger.py)                      ✅ real
service.py:93-130     TradingService read models (portfolio/market_state/risk/trades)  ✅ real
        ↓
app.py:770-878        GET /v1/trading/{status,portfolio,accounts,market-state,risk,trades,bars,tickets}  ✅ real
        ↓  ❌ BREAK #1: no event/push. Nothing writes to /v1/events; Android must poll.
        ↓  ❌ BREAK #2: no classification. The payload is numbers + prose; no semantic_state,
        ↓              no severity, no aura/visual token is ever computed server-side.
TradingRepository.kt  7 polling calls → data classes                     ✅ real
        ↓  ❌ BREAK #3: no mapping. TradingModels.kt has SafetyIdentity(:29) and DataState(:37)
        ↓              colour enums for *badges*, but nothing feeds VanLiveVisualState.
VanLiveVisualState.kt driven only by VanGatewayClient dispatch outcomes (:419-459)
```
**Verdict: trade state → VAN experience/visual state is ABSENT.** A kill switch tripping, a
position going 3R against the owner, or a REJECTED:MAX_DAILY_LOSS produces no change in VAN's
presence, aura or ambient state. The trading data reaches a *screen the owner must open*, and
stops there.

---

## Q5. EXECUTION TRANSPORTS

### 5.1 MT5 — two distinct routes, both implemented in code

**Route A — push / Windows worker (`BrokerKind.MT5`)**
- Core client: `Mt5BridgeClient` / `Mt5BridgeAdapter` — trading/vati/execution/mt5_bridge.py:35-111.
- Protocol: narrow op allowlist `OPS` (mt5_bridge.py:19) = sync_account, sync_symbols,
  order_check, order_send, positions, orders, history, modify_sl_tp, close. Each request is an
  HMAC-SHA256 over canonical JSON of `{op, nonce, issued_ms, body}` (`sign`, :42-44). The client
  checks the response echoes `nonce` and `worker_time_ms` within `max_skew_ms=5000` (:58-61).
- Transport: `Mt5HttpTransport` — trading/vati/execution/transports/mt5_http.py:26-56.
  POST `https://<worker>:9443/bridge/v1/call`, **mTLS**: refuses non-https (:29-30), refuses a
  missing CA file (:31-32), `check_hostname = True`, TLS ≥ 1.2, client cert loaded (:34-38).
- Worker: deploy/van-trading-core/windows/mt5_worker/mt5_bridge_worker.py (279 lines) +
  install.ps1. PKI generated by deploy/van-trading-core/pki/make-bridge-pki.sh.
- Fail-closed: `Mt5BridgeClient.call` raises `VenueUnavailable` with no transport (:52-53).
- Order safety: refuses to submit without a protective stop (`mt5_bridge.py:90-91`), and
  always does `order_check` before `order_send` (:95-98).

**Route B — pull / MQL5 EA, Windows-free (`BrokerKind.MT5_EA`)**
- EA: deploy/van-trading-core/mql5/VanBridgeEA.mq5 (192 lines). Real MQL5: `OnInit` refuses a
  signing key < 32 chars and a non-https BridgeUrl (:38-39); HMAC-SHA256 implemented by hand
  per RFC 2104 (:65-70); `EventSetMillisecondTimer(PollMs)` default **1000 ms polling** (:28, :41).
- Server side: `create_pull_app` — trading/vati/execution/mt5_pull.py:206+;
  `POST /ea/v1/{alias}/poll`, headers X-Van-Ts / X-Van-Nonce / X-Van-Signature,
  `SKEW_S = 60` (:39), per-alias nonce table in SQLite (:55).
- Queue: `BridgeQueue` over SQLite WAL shared by two processes (mt5_pull.py:45-56); ops
  restricted to `("ORDER_SEND", "MODIFY_SL", "CLOSE")` (:38) and enforced on enqueue (:58-60).
- Safety: refuses order without SL (:174-175); `modify_stop` **refuses to widen a stop**
  (:191-193); a timed-out EA reply returns status `UNKNOWN` with "reconcile before retrying"
  (:182-183) rather than assuming a reject.
- Staleness: `heartbeat` is false unless the EA's state is < `STATE_FRESH_MS = 30_000` old (:40, :165-168).
- systemd: deploy/van-trading-core/systemd/vati-mt5-pull.service.

### 5.2 Deriv
- Adapter: trading/vati/execution/deriv.py:41-103. Speaks the real Deriv JSON API
  (`authorize`, `portfolio`, `ping`, `proposal`, `buy`, `contract_update`, `sell`).
- Transport: `DerivWebSocketTransport` — trading/vati/execution/transports/deriv_ws.py:28+,
  real `wss://ws.derivws.com/websockets/v3?app_id=…` with `req_id` correlation and a reader thread.
- Token hygiene: the adapter carries a literal `PLACEHOLDER = "<token-from-vault-never-in-prompt>"`
  (deriv.py:56, deriv_ws.py:22) which the transport substitutes at connect time — deliberate so
  a token can never appear in a prompt, log or ledger. Good pattern.
- Policy: synthetic indices are refused unless `allow_synthetics` (deriv.py:82-83), citing
  "Rev 3 A.8 OBSERVE only".
- Fail-closed with no transport (:50-51).

### 5.3 cTrader
- Transport: trading/vati/execution/ctrader/transport.py:35+ — real framed TLS
  (4-byte BE length + ProtoMessage) to demo/live.ctraderapi.com:5035, reader thread,
  clientMsgId correlation, 10 s heartbeat.
- Proto: 4 `.proto` files vendored **unmodified** from spotware/openapi-proto-messages with
  SHA-256 per file — trading/vati/execution/ctrader/proto/PROVENANCE.json
  (`"modification": "NONE — parsed at import by vati.execution.ctrader.protoschema; no protoc,
  no generated code"`). `protoschema.py` (256 lines) is a hand-rolled .proto parser + wire codec.
- Adapter: ctrader/adapter.py:143 `submit` — MARKET order carries `relativeStopLoss` in the same
  request so "stop in the same request" holds (adapter.py docstring :1-7); stops only tighten.
- OAuth: ctrader/oauth.py (55 lines), wired into gateway onboarding.
- Feed: ctrader/feed.py — `trendbars()`, 23 lines. This is the only streaming/pullable price
  source bound to a live broker, and it is not wired into `SessionService` (which uses `BarLake`).

### 5.4 Other adapters
- `PaperAdapter` — trading/vati/execution/paper.py (110 lines). SIMULATED by design; fills
  against bars. This is what backtests and `BrokerKind.PAPER` accounts use.
- `OwnerTicketAdapter` (ZSE/VFEX) — trading/vati/execution/zse_ticket.py:60. Emits a human
  `OWNER_TICKET` for the owner to place with a broker; status `ACCEPTED`/channel `OWNER_TICKET`
  (router.py:96-97). Honest human-in-the-loop, not automated execution.

### 5.5 The live attestation — what it certifies and what it does NOT
`artifacts/runtime/van_trading_core_reconciliation_live_attestation.json`
(`observed_at_utc` 2026-09-18T06:22:58Z, `certified_commit` **54ee68fe** = "Fix Trading Core
Caddy bootstrap validation (#34)", an ancestor of the audited HEAD dff38a0).

**It certifies (infrastructure only):**
- repository reconciliation: PR 32 merged, PR 34 merged, PR 29 closed, WIP lineages in main.
- `qualification.status = "GREEN"`, `required_failures: 0`, automation fabric green,
  Supabase runtime green, firewall green, Caddy active, public TLS green.
- `ledger_backend: "PostgresLedger"`, `ledger_chain_ok: true`.
- services active: vati_vekl, vati_commander, vati_automation, vati_supabase, docker, caddy.
- runtime component versions: n8n 2.39.7, nautilus_trader 1.231.0, Stagehand 4.1.0,
  Playwright 1.63.0, Temporal 1.33.0.

**It explicitly does NOT certify (the `non_required_amber` rows, verbatim):**
1. `"no session heartbeats yet because no trading account is enabled"`
2. `"MT5 is external to the ARM64 Trading Core and runs on the Windows bridge worker"`

Row 1 is decisive: **no trading account is enabled, therefore no `vati serve` session has ever
run on this host.** No DecisionCycle has stepped, no RiskAuthority has evaluated a live intent,
no adapter has connected to a broker, no order has been sent. `ledger_chain_ok: true` is the
chain integrity of an (effectively empty) ledger, not proof of trading.
Row 2 means the MT5 path was not exercised from this host at all.
`firstboot_marker.present: false` with `accepted_as_blocker: false` (the node was resumed
in place rather than rebuilt from firstboot).
`contains_secrets: false`.

**Nothing in this repository attests a single live broker order on any venue.**
No transport has a recorded live round-trip. All transport confidence is test-level (Q9).

---

## Q6. LEARNING / VEKL / ZSE

### 6.1 Continuous learning — real algorithm, but NOT wired into the live service
The learning package (trading/vati/learning/, 13 modules, ~940 lines) is genuinely implemented:
`episodes.py` (ExperienceEpisode sealed with a hash, `episode_from_ledger` :139-171),
`health.py` (StrategyHealthTracker), `broker.py` (BrokerLearner execution profiles),
`evolution.py` (failure clustering → candidate capsule), `counterfactual.py`, `missed.py`,
`curriculum.py`, `priority.py`, `cycles.py` (daily/weekly/monthly reports from the ledger),
`memory_bridge.py`.

**Wiring gap:** `DecisionCycle.__init__` accepts `learning: Optional[LearningHooks] = None`
(trading/vati/app/cycle.py:73) and every learning effect is guarded by
`if self.learning is not None` (cycle.py:170, :203).
- `BacktestEngine` passes it through (trading/vati/backtest/engine.py:49, :59).
- **`SessionService.build()` does NOT** — trading/vati/app/service.py:143 constructs
  `DecisionCycle(...)` with no `learning=` argument.
⇒ In the live/serve path, learning is **completely inert**. It only runs in backtests.

### 6.2 Can learning change risk parameters without owner sign-off? — **NO, and it is well designed**
`trading/vati/learning/boundary.py`:
- Exactly three permitted live targets (`LiveTarget`, :22-25): CAPSULE_HEALTH,
  REGIME_PROBABILITY, BROKER_PROFILE.
- `FORBIDDEN_TARGETS` (:28) explicitly includes MANDATE, PLATFORM_CEILINGS, CAPSULE_LOGIC,
  CAPSULE_STATE_PROMOTION, INSTRUMENT_LIST, BROKER_CREDENTIALS, LEVERAGE, RISK_POLICY,
  EXECUTION_POLICY, PRODUCTION_MODEL_ALIAS.
- `LearningBoundary.check` (:44-58): multiplier must be in [0,1] (**reduce-only**, :48-49);
  only capsule health may demote (:50-51); demotion targets are DEGRADED|SHADOW|SUSPENDED and
  *"promotion is never a learning output"* (:52-53); ≥ 30 environment-weighted samples (:42, :54-55);
  must cite evidence artifact hashes (:56-57).
- `attempt()` (:60-63) is an explicit refusal path for anything else.
- The only live write-backs in the cycle are `engine.m.capsule_health[...]` and
  `engine.m.broker_liquidity[...]` (cycle.py:216, :172) plus a **demotion only**
  (cycle.py:218-225, logged as `"authority": "AUTOMATIC_DEMOTION_ONLY"`).
- Promotion requires an owner signature ref (trading/vati/strategies/capsule.py:95-105), and a
  learning-proposed candidate is created with `"state": "RESEARCH"` and
  `"approval_signature_ref": None` (trading/vati/learning/evolution.py:66-70).
**Verdict: learning cannot widen risk.** (Caveat: the "owner signature" is again only a
non-empty string — Q2.3.)

### 6.3 Trading VEKL
trading/vekl/server.mjs (129 lines) + trading/vekl/vendor/dial/ (6 modules, vendored
byte-for-byte with trading/vekl/vendor/dial/PROVENANCE.json) + trading/vtil/registry/ (4 JSON
registries). A real Node HTTP service, loopback-only, `VEKL_PORT=9134`, persists activation
records with deterministic activation ids. systemd unit deploy/van-trading-core/systemd/vati-vekl.service.
Reached from the commander via `cmd_vekl` (trading/commander/app.py:216-223) and checked by
`cmd_status`/`cmd_doctor`. It is an **engineering-knowledge resolver, not a trading learner** —
it never touches market data, strategies or risk. `activation_id` flows into MarketState
(cycle.py:132) but its default is the literal `"vtil-act-unresolved"` (cycle.py:56).

### 6.4 ZSE
trading/vati/zse/ (350 lines over 5 modules): market spec, transaction-cost schedule,
currency-regime classifier, liquidity model. Docstring (trading/vati/zse/__init__.py:1-6):
"No network access, no broker access… an UNVERIFIED fact may not drive a live order
(see MarketSpec.assert_live_ready)". Two ZSE strategies exist
(trading/vati/strategies/zse_liquidity_provision.py, zse_value_rotation.py) with registry
capsules. Execution is the human `OwnerTicketAdapter`. This is a **deterministic model, not a
live loop** — and it is honest about that.

---

## Q7. LEDGER

### 7.1 Two byte-compatible backends
- SQLite: trading/vati/core/ledger.py (137 lines). WAL, `events` table with
  `event_hash/prev_hash/chain_hash`, indexes on correlation_id and kind.
- Postgres: trading/vati/core/ledger_pg.py (162 lines). Append serialised by
  `SELECT chain_hash FROM vati.chain_head WHERE ledger = %s FOR UPDATE` (:56) so two writers
  cannot fork the chain. `autocommit = False`, rollback on error (:68-70).
- `open_ledger(spec)` (:155-161) picks by DSN prefix.
- Chain: `chain = sha256(prev + event_hash)`; `verify_chain()` recomputes every event body hash,
  every prev link and every chain link and finally compares to the stored head
  (ledger_pg.py:111-126). `replay_decisions()` (:128-143) re-runs the Risk Authority over the
  stored inputs and compares decision hashes — **deterministic decision replay is a real feature**
  (CLI: `python -m vati replay-verify`, trading/vati/__main__.py:70-75).

### 7.2 Supabase schema — append-only is enforced at the DB
deploy/van-trading-core/supabase/init/01_vati_ledger.sql.tpl:
```
REVOKE UPDATE, DELETE, TRUNCATE ON vati.events FROM vati;
GRANT SELECT, INSERT ON vati.events TO vati;
GRANT SELECT, INSERT, UPDATE ON vati.chain_head TO vati;
```
The runtime role can insert and read events but **cannot update or delete them**. The schema is
provisioned by a privileged reconciler; ledger_pg.py:17-18 notes "Runtime deliberately has no
CREATE privilege on the database" (though `__init__` still issues `cur.execute(SCHEMA)` at :46,
which is a no-op under that grant but would raise if privileges were ever tightened differently).

### 7.3 Reconcile script
deploy/van-trading-core/supabase/reconcile_vati_ledger.py — idempotent role creation
(`build_sql` :22-35 rewrites the canonical `CREATE ROLE` into a `DO $$ IF NOT EXISTS` block and
`ALTER ROLE … PASSWORD`), then rewrites `VAN_COMMANDER_LEDGER=postgres://vati:…@127.0.0.1:5432/postgres`
into the core env file atomically preserving mode (:37-55). It refuses to run if the canonical
role statement is missing from the template (:23-24). Tested by trading/tests/test_vati_ledger_reconcile.py
and trading/tests/test_supabase_bootstrap_boundary.py.

### 7.4 **Is the VAN gateway reading the live ledger or its own sqlite? — its own, by default.**
`backend/van_gateway/config.py:21`:
```python
vati_ledger_path: str = "data/vati_ledger.sqlite3"
```
`backend/van_gateway/app.py:182-187` constructs `TradingService(settings.vati_ledger_path, …)`.
`TradingService._open()` (backend/van_gateway/trading/service.py:63-68) opens a `PostgresLedger`
only if the path starts with `postgres://`/`postgresql://`, otherwise a **local SQLite file**.
`available()` (:60-61) simply tests `Path(self.ledger_path).is_file()`.

So out of the box the gateway reads a **separate, local, empty sqlite file on the gateway host**,
while the trading VM writes to Supabase Postgres (`VAN_COMMANDER_LEDGER=postgres://vati@127.0.0.1:5432`
per the reconcile script, and the attestation's `ledger_backend: "PostgresLedger"`).
There is **no code path that makes the gateway talk to the commander for ledger reads** — the
commander is used only for account-control actions (`CommanderAccountControl`,
backend/van_gateway/trading/accounts.py:68-96). Connecting the two requires an operator to set
`vati_ledger_path` to the trading VM's Postgres DSN *and* to expose that Postgres to the gateway
host. Nothing in deploy/ does this. The default configuration therefore produces a gateway that
reports `ledger_available: false` / `TRADING_LEDGER_UNAVAILABLE` forever.

---

## Q8. GATEWAY TRADING API

### 8.1 Routes (backend/van_gateway/app.py)
| Route | Line | Auth | Source |
|---|---|---|---|
| `GET /v1/trading/status` | :770 | device middleware | ledger chain + counts + kill switch |
| `GET /v1/trading/trades?view=&limit=` | :774 | device | `vati.app.tradebook.build_trade_book` |
| `GET /v1/trading/portfolio` | :781 | device | `vati.app.portfolio.portfolio` |
| `GET /v1/trading/accounts` | :785 | device | ACCOUNT_SNAPSHOT + registry |
| `GET /v1/trading/market-state?symbol=` | :789 | device | MARKET_STATE + OPPORTUNITY_ASSESSMENT |
| `GET /v1/trading/risk` | :793 | device | latest RISK_DECISION |
| `GET /v1/trading/trades/{id}` | :797 | device | trade detail + timeline + chart |
| `GET /v1/trading/bars` | :804 | device | `BarLake` on disk |
| `GET /v1/trading/tickets` | :876 | device | OWNER_TICKET events |
| `POST /v1/trading/accounts/action` | :811 | **device HMAC signature** | commander or local handlers |
| `GET /v1/trading/oauth/{broker}/callback` | :860 | unauthenticated (:363 exempt) | OAuth redirect |
| `POST /v1/trading/halt` | :880 | `require_internal_control(x_van_internal_token)` | writes KILL_SWITCH |
| `POST /v1/trading/tickets/{id}/confirm` | :902 | `require_internal_control` | writes OWNER_TICKET |

### 8.2 Data source — **ledger file, not live commander HTTP, not fixtures**
Every read goes through `TradingService._with_ledger` → `self._open()` →
`Ledger(self.ledger_path)` (backend/van_gateway/trading/service.py:63-90). There is **no HTTP
call to the commander for any read**, and there are no fixture/demo payloads in service.py.
The data is genuinely ledger-derived — it is just derived from *whichever* ledger the gateway is
pointed at, which by default is its own empty sqlite (Q7.4).
Bars come from the on-disk `BarLake` (`self._lake()`, :77-81), not from the ledger.

### 8.3 What Android gets
- **positions / history / potential trades**: `/v1/trading/trades` → `TradeBookParser` →
  `TradeRow`; `/v1/trading/portfolio` carries `open_positions`, `recent_trades`,
  `potential_trades` (trading/vati/app/portfolio.py:86).
- **risk**: `/v1/trading/risk` → `RiskView` (android/.../trading/TradingModels.kt:109-115) with
  portfolioHeat, drawdownFromPeak, limits, killSwitch, consecutiveLosses, concentration by
  symbol/currency/direction, per-position risk.
- **reasoning**: `TradeDetail` (TradingModels.kt:158-163) carries `reasonCode`, `multipliers`,
  `timeline` (TimelineEntry with per-event hash), `interpretation`, `lessons`, `decisionHash`,
  `marketSnapshotHash`. `MarketStateCard.summary` carries the `van_summary` prose
  (trading/vati/app/portfolio.py:115-124).
- **chart bars**: `/v1/trading/bars` → `BarSeries` with `provenance` and an explicit
  `isSimulated` flag (TradingModels.kt:141-142).
- **alerts**: **none.** There is no alert route, no notification, no push. Kill-switch state is
  only a field the app must fetch.

### 8.4 When the trading host is unreachable
Three distinct, honest degradation layers — this part is well built:
1. `TradingService.available()` false → every read returns a typed empty shape with
   `ledger_available: False` (service.py:96-97, :109, :113, :126, :134-135, :193-197); writes
   raise `FileNotFoundError` → HTTP 503 (app.py:890-891, :919-920).
2. `_trading_status_payload` catches any exception, sets
   `DegradedCode.TRADING_LEDGER_UNAVAILABLE` and returns `{"ledger_available": false, "error": …,
   "degraded": [...]}` (backend/van_gateway/app.py:749-767).
3. Android: `TradingRepository.load` maps a throw to
   `Loaded.Unavailable("Gateway unreachable: …")` (android/.../trading/TradingRepository.kt:13-17);
   `connection_state` is `NEVER_SYNCED` (trading/vati/app/portfolio.py:61) and `DataState`
   is a colour-carrying enum (TradingModels.kt:37-42).
**Nothing fabricates data when the host is down.** That is a genuine strength.
Note however: "trading host unreachable" is not actually detectable here, because the gateway
never contacts the trading host for reads — it only detects "my local ledger file is missing or
unreadable". A *stale* ledger (trading VM dead, file still present) would be reported as
`ledger_available: true` with old data; the only staleness signal is `last_event_ms`
(service.py:153) and per-account `last_sync_ms`, neither of which is thresholded server-side.

---

## Q9. TESTS

Run confirmed locally: `cd trading && python3 -m pytest tests -q` → **251 passed, 2 skipped, 24s**.

### 9.1 Classification (28 files, 199 test functions)
**A. Pure-logic / property (strongest tier — these genuinely prove the risk contract)**
- test_authority.py (18) — every rejection code, ordering, fail-closed.
- test_authority_properties.py (2) — property-based invariants over the authority.
- test_mandate.py (9) — ceilings, unsigned rejection, hard-forbidden list.
- test_sizing.py (9), test_heat_governor.py (5), test_zse_module.py (13),
  test_intelligence.py (6), test_contract_schemas.py (7, JSON-Schema conformance),
  test_strategies_arbiter.py (8), test_core_and_market_data.py (9).

**B. In-process integration with fakes/doubles**
- test_execution.py (11) — router + PaperAdapter/fake adapters.
- test_ctrader.py (5) — a fake socket; includes a **hand-verified wire-bytes codec test** (:21),
  which is unusually good evidence for a protocol implementation.
- test_mt5_pull.py (4), test_mt5_worker.py (2) — FastAPI TestClient + a real local HTTPS server.
- test_commander.py (5), test_commander_accounts.py (4), test_tradebook.py (3),
  test_portfolio_views.py (2), test_learning.py (15).

**C. Infrastructure / deployment**
- test_infra_live.py (10), test_supabase_bootstrap_boundary.py (3),
  test_vati_ledger_reconcile.py (5), test_oci_trading_topology_bootstrap.py (4),
  test_stack_lock.py (7), test_n8n_provisioner.py (1),
  test_automation_browser_stack_proposal.py (11), test_vtil_borrow.py (2).

**D. Backtest / end-to-end-in-a-box**
- test_backtest_runner_cli.py (7) — full DecisionCycle over PaperAdapter.

**Backend:** backend/tests/test_trading_api.py (624 backend tests total pass).

### 9.2 Synthetic data that could be mistaken for live proof — **YES, flag this**
`synthetic_bars()` — trading/tests/test_backtest_runner_cli.py:28-36 — generates a
deterministic price series *shaped so the pullback strategy gets chances*
(docstring :29: "Several trend legs with pullbacks and a reversal, so the pullback strategy
gets chances"). It is imported by test_learning.py:10, test_tradebook.py:8 and
test_infra_live.py:18.

Consequences to be precise about:
- **test_infra_live.py is named "live" but is not live.** Its docstring says "Rev 5 live-ready
  infrastructure" (:1). It runs a local HTTPS server, a local websocket server and synthetic
  bars. `test_session_service_runs_paper_account_from_lake_and_logs_portfolio_truth` (:306)
  writes `provenance="SYNTHETIC"` bars into a BarLake (:310) and runs the whole service over a
  **PAPER** account. This is the closest thing to E2E in the repo, and it touches no broker.
- Any backtest P&L, win rate or "trades ≥ 1" assertion derived from `synthetic_bars()`
  (test_backtest_runner_cli.py:54, :62, :76; test_learning.py:186, :247, :257, :271;
  test_tradebook.py:33) is a **property of the generator**, not a market result.
- Mitigations the codebase does deploy, and they are good: the BarLake stores an explicit
  `provenance` string, the gateway surfaces it, and Android exposes
  `BarSeries.isSimulated = provenance.all { it == "SYNTHETIC" }`
  (android/.../trading/TradingModels.kt:141-142). The honesty is carried all the way to the UI.

### 9.3 The two skips matter
```
SKIPPED tests/test_infra_live.py:54 : local PostgreSQL not reachable
SKIPPED tests/test_vtil_borrow.py:36: dial-new checkout not available (set DIAL_REPO)
```
The skipped one is `test_postgres_ledger_matches_sqlite_chain_and_detects_tampering`
(test_infra_live.py:55). **The Postgres ledger — the backend the production attestation says is
in use (`"ledger_backend": "PostgresLedger"`) — is untested in the default CI run.**
The 251-pass figure covers the SQLite ledger only.

### 9.4 Failure-injection tests for broker/transport faults — **yes, and they are good**
- `test_router_refuses_tampered_or_rejected_decisions` (test_execution.py:46) — tampered
  decision hash, REJECTED decision, wrong mandate, non-order-sending mode.
- `test_router_flattens_when_stop_rejected_and_trips_kill_switch` (test_execution.py:66).
- `test_router_disconnect_trips_kill_switch` (test_execution.py:79).
- `test_mt5_bridge_fails_closed_and_signs` (test_execution.py:150).
- `test_adapter_fails_closed_until_the_ea_reports` (test_mt5_pull.py:79) — EA silence.
- `test_signature_nonce_skew_and_unknown_alias` (test_mt5_pull.py:93) and
  `test_worker_verifies_signature_nonce_skew_and_serves_the_contract` (test_mt5_worker.py:68) —
  replay, forged signature, unknown op, clock skew.
- `test_bad_credentials_and_disconnect_fail_closed` (test_ctrader.py:173).
- `test_mt5_http_transport_requires_tls_and_round_trips_signed_requests` (test_infra_live.py:131)
  and a full mTLS round trip (test_mt5_worker.py:122).
- `test_bar_lake_hashes_slices_and_refuses_tampered_bytes` (test_infra_live.py:258).
**Missing:** partial fills, requotes/slippage rejection loops, duplicate broker fill for one
command, broker reporting a position VATI has no record of *during* a session (only at
startup), and any test that a session survives a mid-flight ledger write failure.

---

## Q10. CLASSIFICATION

| Component | Class | Evidence |
|---|---|---|
| **Risk Authority** | **IMPLEMENTED_BUT_ISOLATED** (logic is INTEGRATED into the cycle; never exercised against a real venue) | trading/vati/risk/authority.py:93-343; sole gate at cycle.py:145; 20 dedicated tests; but 3 of its health gates are hardcoded to pass by the live snapshot (cycle.py:118-119) and no live session has run (attestation `non_required_amber[0]`) |
| **Decision cycle** | **SIMULATED** (proven end-to-end only over PaperAdapter + synthetic bars) | trading/vati/app/cycle.py:127-173; exercised by test_backtest_runner_cli.py and test_infra_live.py:306 over a PAPER account |
| **MT5 bridge (push/Windows)** | **IMPLEMENTED_BUT_ISOLATED** | trading/vati/execution/mt5_bridge.py + transports/mt5_http.py + deploy/.../windows/mt5_worker/; full mTLS round trip tested (test_mt5_worker.py:122); attestation says MT5 is external and unexercised |
| **MT5 pull bridge (MQL5 EA)** | **IMPLEMENTED_BUT_ISOLATED** | trading/vati/execution/mt5_pull.py + deploy/van-trading-core/mql5/VanBridgeEA.mq5; server side tested end-to-end (test_mt5_pull.py:102); the EA itself has no automated test |
| **Deriv transport** | **IMPLEMENTED_BUT_ISOLATED** | trading/vati/execution/deriv.py + transports/deriv_ws.py; tested against a real local websocket server (test_infra_live.py:217) but never against Deriv |
| **cTrader transport** | **IMPLEMENTED_BUT_ISOLATED** | ctrader/transport.py, protoschema.py, adapter.py; hand-verified wire bytes (test_ctrader.py:21); never connected to ctraderapi.com |
| **ZSE owner-ticket "transport"** | **PARTIAL by design** (human in the loop) | trading/vati/execution/zse_ticket.py:60; confirmation route backend/van_gateway/app.py:902 |
| **Account registry** | **INTEGRATED** | trading/vati/accounts/registry.py; used by service.py:124, commander app.py:258-263, gateway service.py:70-75; signed onboarding backend/van_gateway/trading/accounts.py |
| **Ledger (SQLite)** | **INTEGRATED** | trading/vati/core/ledger.py; every component writes it; verify + replay tested |
| **Ledger (Postgres/Supabase)** | **IMPLEMENTED_BUT_ISOLATED** | trading/vati/core/ledger_pg.py + deploy/.../01_vati_ledger.sql.tpl; its only test is SKIPPED in the default run (test_infra_live.py:54) |
| **Commander** | **INTEGRATED** | trading/commander/app.py; HMAC auth (auth.py), systemd unit, MCP shim, attestation `services.vati_commander: "active"` |
| **Trading VEKL** | **INTEGRATED** (but orthogonal to trading) | trading/vekl/server.mjs; `services.vati_vekl: "active"` in the attestation |
| **Learning** | **IMPLEMENTED_BUT_ISOLATED** | trading/vati/learning/*; wired into BacktestEngine (backtest/engine.py:59) and **not** into SessionService (service.py:143) |
| **Gateway trading API** | **PARTIAL** | backend/van_gateway/app.py:770-928 routes are real and tested; but the default `vati_ledger_path` points at a local sqlite that nothing writes (config.py:21) |
| **Trade-state → VAN semantic/visual state** | **ABSENT** | zero hits for aura/visual/semantic_state in trading/ and backend/; see Q4.5 |
| **Owner-signed mandate verification** | **STUB** | trading/vati/risk/mandate.py:156-157 — non-empty string only |
| **Live market-data feed → session** | **ABSENT** | `SessionService` reads only `lake_bar_source` (service.py:231-235); no feed writes the lake during a session |

Nothing in the trading plane reaches **E2E_VERIFIED**. The single blocker is stated by the
system's own attestation: `"no session heartbeats yet because no trading account is enabled"`.

---

## Q11. STUBS / MARKERS / P0 SAFETY OBSERVATIONS

### 11.1 Explicit markers (there are very few — the code is not padded with TODOs)
- trading/examples/mandate.fx_primary.example.json:46 — `"sig:owner-device:REPLACE_WITH_DEVICE_SIGNATURE_REF"` (the only shipped mandate).
- trading/vati/execution/transports/deriv_ws.py:22 / deriv.py:56 — `PLACEHOLDER = "<token-from-vault-never-in-prompt>"` (intentional, substituted at connect: deriv_ws.py:67).
- trading/vati/app/cycle.py:56 — `activation_id: str = "vtil-act-unresolved"` default.
- trading/architecture/proposed/automation_browser_fabric_layers.json — `proposed/` namespace.
- trading/vati/app/cycle.py:150-153 — dead code (`sig_targets = ()`, `for c in oa.candidates: pass`).
- No `TODO`, `FIXME`, `NotImplementedError` or `raise NotImplemented` anywhere in trading/.

### 11.2 P0 safety observations

**P0-1 — "Owner-signed" is a non-empty string everywhere.**
mandate.py:156-157, governor.py:51-53, runner.py:55-57, capsule.py:101-102,
commander/app.py:226-228, backend/van_gateway/trading/service.py:208-212.
No key, no verification, no authority record. Anyone with write access to a session config or
the gateway's internal token can mint a mandate up to `PlatformCeilings` (2% per trade, 6%
portfolio heat) and it will be honoured as owner authority. `requested_by` on the commander is
also client-supplied (commander/app.py:90) and is what gates the agent-hidden commands (:295).

**P0-2 — The live RiskSnapshot hardcodes three safety flags to "healthy".**
trading/vati/app/cycle.py:118-119: `reconciliation_ok=True`, `risk_store_ok=True`,
`tier1_event_blackout_active=False`. The authority's `RECONCILIATION_FAILED` (authority.py:173),
`RISK_STORE_UNAVAILABLE` (:177) and `EVENT_BLACKOUT` (:197) gates are therefore **unreachable in
the live path**. Reconciliation is checked once at startup (runner.py:35-37) and never again;
a broker position appearing mid-session is not detected. Similarly `self.integrity` (cycle.py:88)
is never written, so `MARKET_INTEGRITY` (:179) and the elevated half-size rule (:240) are dead.

**P0-3 — Owner halt is asynchronous, polled, and lost on restart.**
Gateway/commander only append a KILL_SWITCH event (service.py:222, commander/app.py:233).
The session observes it on its next loop, up to `poll_seconds` (default 5.0) later
(trading/vati/app/service.py:60, :191). Worse, `_observe_owner_halt` filters
`ev.event_time_ms >= self._started_ms` (service.py:181) — **restarting the session discards an
active owner halt**, and `restart_service` is an exposed commander command
(trading/commander/app.py:97, :184-190).

**P0-4 — Gateway reads the wrong ledger by default.**
`vati_ledger_path = "data/vati_ledger.sqlite3"` (backend/van_gateway/config.py:21) while the
trading VM writes to Supabase Postgres. Nothing in deploy/ reconciles the two. The owner's app
would show an empty, always-degraded trading surface — or, if a stale local file existed,
**old data presented as current** (only `last_event_ms` hints, and it is not thresholded).

**P0-5 — Idempotency key is session-scoped.**
`canonical_hash({"seed": f"{session_id}:{state.as_of_ms}", …})` (arbiter/opportunity.py:83) with
`session_id = f"{alias}:{symbol}:{clock()}"` (service.py:137). A crash-and-restart on the same
bar produces a **different** idempotency key, so neither `RiskAuthority._seen_keys`
(authority.py:165) nor the ledger-seeded `ExecutionRouter._seen` (router.py:41) will block a
duplicate order for the same signal. Nothing prevents two `serve` processes for one alias.

**P0-6 — No margin model.** `AccountState` (execution/base.py:93-101) has equity and balance
only; there is no margin, free margin or margin-level field anywhere in trading/. A
stop-distance-sized position can still be rejected or liquidated by a broker on margin, and the
Risk Authority has no visibility of it.

**P0-7 — Strategy targets are discarded.** cycle.py:150-157 throws away the winning signal's
target and re-derives a single target from `expected_gross_move_pct`. Combined with the dead
loop at :151-152 this looks like unfinished work sitting in the live order path.

**P0-8 — Learning is silently inert in production.** `SessionService.build()` does not pass
`learning=` (service.py:143), so capsule-health demotion, broker-liquidity learning and
TRADE_EXPERIENCE_ARTIFACT emission — all the self-protective feedback — exist only in backtests.

### 11.3 Things that are genuinely strong (for balance)
- Sealed, hash-recomputable RiskDecision + router refusal on hash mismatch (router.py:56).
- Ledger append-only enforced at the database grant level (01_vati_ledger.sql.tpl).
- Deterministic decision replay (`replay_decisions`, ledger_pg.py:128-143).
- Learning boundary: reduce-only, demote-only, evidence-required, 30-sample minimum (boundary.py:41-58).
- No LLM anywhere in the order path; `trading.vati.submit_order` declared A4 and structurally
  never-routable in registries/capabilities.json:256 (`never_routable_reason`: "VATI retains
  exclusive trading-execution authority… structurally unroutable so the generic fabric cannot
  reach it as a side channel"), matching hermes/skills/trading-intelligence/SKILL.md invariant 1.
- Credentials never in the registry, 0600+owner-checked secrets files (accounts/registry.py:103-120),
  agent requesters refused credential commands (commander/app.py:295-297).
- Synthetic-data provenance carried all the way to the Android UI (TradingModels.kt:141-142).
- Degradation is typed and honest at every layer; nothing fabricates data when the source is down.

