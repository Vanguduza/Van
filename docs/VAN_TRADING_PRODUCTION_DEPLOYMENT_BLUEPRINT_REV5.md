# VAN Trading System — Production Deployment Blueprint, Revision 5

**Status:** active engineering authority for deployment, live-readiness and the Trading Command Center.
**Builds on:** `docs/VAN_TRADING_SYSTEM_BLUEPRINT_REV4_CONSOLIDATED.md` (system design, Parts A–O stay authoritative);
`docs/archive/VAN_TRADING_COMMAND_CENTER_BLUEPRINT_REV_1.md` (owner product/UX contract for the dashboard, provenance).
**Owner direction (2026-09-16):** build all infrastructure required for live production so that MT5 or Deriv accounts
can be plugged in when ready; market data arrives when demo testing starts; test with internet data where possible;
bootstrap the dedicated `van-trading-core` VM (MT5, Python 3.12, a local Desktop-Commander-style Hermes subordinate,
local Supabase, a complete trading VEKL, future NautilusTrader, Market Brain, Risk Authority, NFP/Event Engine,
Execution Router, Deriv adapter, MT5 bridge); add a visually pleasing trading dashboard to the Van Command Centre app
with screens for trades, their charts and details.
**Branch / builds:** `claude/van-autonomous-trader-r81vyn`, builds H (infrastructure), I (deployment), J (Command Center), K (cTrader + MT5 pull bridge), L (in-app account onboarding).
**Owner direction (2026-09-16, later):** no Windows machine is available; use routes 1 (cTrader Open API) and 4 (MQL5 pull-bridge EA); accounts are configured from the Android trading dashboard, including creating new Deriv/cTrader accounts, never through CLI commands.

---

## Part A — Estate topology

```text
 dial-hermes-control 10.0.0.184           van-trading-core 10.0.1.233 (A1.Flex 2 OCPU/12 GB, Ubuntu 24.04 ARM64)      Windows MT5 worker (owner's host)
 ┌───────────────────────────┐            ┌────────────────────────────────────────────────────────────────────┐    ┌─────────────────────────────┐
 │ Hermes profile van        │  HTTPS     │ vati-commander :9133   typed commands, HMAC + nonce, TLS            │    │ MetaTrader 5 terminal        │
 │  mcp_servers.             │──HMAC────► │ vati-vekl      :9134   dedicated trading VEKL (loopback)            │    │ mt5_bridge_worker :9443      │
 │  van_trading_commander    │            │ vati-session@<alias>   DecisionCycle per account (paper/MT5/Deriv)   │◄──►│  mTLS server, HMAC, SL-only  │
 │  (stdio shim)             │            │ vati-supabase          PostgreSQL 17 authority store (loopback)      │mTLS│  tighten-only stops          │
 └───────────────────────────┘            │ bar lake (gzip CSV + sha256 manifest), heartbeats, audit             │    └─────────────────────────────┘
                                          │ outbound: Deriv wss, Dukascopy https, PyPI/apt at bootstrap only     │
 VAN gateway (existing, owner device)     └────────────────────────────────────────────────────────────────────┘
   /v1/trading/* read models ──────────────► ledger (postgres:// or sqlite), account registry, lake
```

Rules carried from Rev 4 Part J: the DIAL Oracle estate stays a control plane; the trading data plane lives only on
Van-owned hosts; attachment to DIAL is the project-binding seam (here: the Hermes subordinate MCP). No dial-new change.

**MetaTrader 5 cannot run on the ARM64 VM.** MT5 is a Windows x86-64 program; Wine-on-ARM emulation is not a
production trading substrate. The design therefore keeps the terminal and the `MetaTrader5` Python package on a
Windows host (an x86 OCI Windows instance in the same VCN is the straightforward choice) and puts only the mTLS
bridge *client* on `van-trading-core`. `bootstrap.sh` records this instead of pretending.

---

## Part B — Accounts: plugged in from the Van app

Accounts are added, linked, verified and removed on the phone (Trading Command Center → Accounts → **+ Add
account**), never with CLI commands. Each action is gated by the owner biometric (A4), signed with the enrolled
device secret over the exact argument bytes (`AccountOnboarding.sign` ≡ gateway `canonical_action`, cross-checked by
a shared test vector), audited with secrets redacted, and forwarded by the gateway to the trading VM's commander
(`account_upsert`, `account_credentials`, `account_verify`, `account_remove`, `deriv_verify_email`,
`deriv_create_demo`, `deriv_oauth_link`, `ctrader_discover`, `ctrader_oauth_exchange`, `ctrader_link`,
`mt5_ea_issue_key`). The VM writes only the non-secret registry and the alias' 0600 secrets file; credentials never
persist on the phone or the gateway, and OAuth tokens in flight live in an encrypted 15-minute pending row.

| Broker | In-app flows | Where the secret lives |
|---|---|---|
| Deriv | Sign in with Deriv (OAuth → pick account), paste an API token, **create a new demo account** (email code → password → residence, via `new_account_virtual`) | `DERIV_API_TOKEN` on the VM |
| cTrader | Application credentials once; sign in with cTrader ID (OAuth → discovered ctid accounts → pick); or paste playground tokens | `CTRADER_*` on the VM |
| MT5 via Expert Advisor | Register login/server; Van issues the EA signing key once; verify the EA is polling | `BRIDGE_SIGNING_KEY` on the VM; MT5 password only in the terminal |
| Paper | Alias + currency | none |

A real (non-demo) account links as READ ONLY (`OBSERVE`) until an owner-signed mandate raises its mode.

### B.1 Registry model (unchanged underneath)

`vati.accounts.AccountRegistry` (`/opt/van-trading/config/accounts.json`) holds **non-secret** records: alias, broker
kind (`MT5 | DERIV | PAPER | ZSE_OWNER_TICKET`), mode, currency, server/login identifiers, bridge URL, demo flag,
mandate reference and a *credential reference* (env var name or a 0600 secrets file). The registry refuses a
credential-shaped field, a live record without a mandate reference and a secrets file with loose permissions.
`python -m vati accounts add|list|remove|verify` is the owner CLI; `verify` prints key names, never values.

Safety identity (blueprint §9) is derived, not typed: PAPER, DEMO, LIVE, READ ONLY. The session service refuses to
start when the mandate's mode or account alias disagrees with the account record.

| Broker | Secrets file keys | Transport |
|---|---|---|
| Deriv | `DERIV_API_TOKEN` | `DerivWebSocketTransport` → `wss://ws.derivws.com/websockets/v3?app_id=<server>`; token injected at `authorize` only |
| MT5 | `BRIDGE_SIGNING_KEY`, `BRIDGE_CA_FILE`, `BRIDGE_CLIENT_CERT`, `BRIDGE_CLIENT_KEY` | `Mt5HttpTransport` (https only, pinned CA, client certificate) → Windows worker |
| Paper | none | in-process `PaperAdapter` |
| ZSE | none | `OwnerTicketAdapter` (owner enters tickets; gateway records confirmations) |

---

## Part C — Ledger on the transactional authority store

`vati.core.ledger_pg.PostgresLedger` implements the SQLite `Ledger` API on PostgreSQL with byte-identical chain
hashes: `append` locks the chain head row, so two writers cannot fork; `verify_chain` re-derives every hash and
checks the head; tampering with a stored payload is detected. `open_ledger(spec)` picks the backend from the DSN.
The Supabase init SQL creates role `vati` with INSERT/SELECT on `vati.events` and no UPDATE/DELETE: the ledger is
append-only at the database, not only by convention.

---

## Part D — Live transports: cTrader (route 1), MT5 pull bridge (route 4), Deriv, Windows worker

- **cTrader Open API** (`vati.execution.ctrader`): the official `.proto` files are vendored with provenance and parsed
  at import into a schema-driven codec (no protoc); framed TLS to `demo|live.ctraderapi.com:5035` with clientMsgId
  correlation, heartbeats and an event queue; app + account auth; symbols with lot-size volume conversion; MARKET
  orders carry `relativeStopLoss` in the same request (absolute SL is not accepted on MARKET by the API), LIMIT orders
  carry absolute SL; tighten-only SL amend; close; spots and trendbars. Tested against a fake cTrader speaking the same
  codec. Linux-native: nothing to host beyond the VM.
- **MT5 pull bridge** (`vati.execution.mt5_pull` + `deploy/van-trading-core/mql5/VanBridgeEA.mq5`): the EA runs in any
  MT5 terminal (MetaQuotes VPS after migration, broker VPS, desktop) and polls `https://<public-host>/ea/v1/<alias>/poll`
  every second with HMAC-SHA256 (implemented in MQL5) over timestamp, nonce, alias and body hash, reporting account and
  positions and executing pipe-delimited commands (`ORDER_SEND` with SL required, `MODIFY_SL` tighten-only, `CLOSE`).
  The session-side adapter fails closed when the EA snapshot is older than 30 s and times out as UNKNOWN. Caddy fronts
  the pull service with a Let's Encrypt certificate because `WebRequest` trusts only the system store.
  Honest constraint: compiling/attaching the EA needs a terminal once (MetaEditor); the mobile apps cannot.
- **Deriv** and the **Windows worker** as before (Part D of the previous text follows).

### D.0 Previous text

- **Deriv**: one socket, `req_id` correlation, out-of-order frames tolerated, API errors returned as data so the
  adapter emits a REJECTED receipt (never an exception on the order path), reconnect on failure, `DerivMarketFeed`
  for candles/ticks/active symbols. Tested against an in-memory Deriv and a real `websockets` server.
- **MT5**: `Mt5HttpTransport` refuses plaintext and a missing CA, presents the client certificate; the Windows worker
  (`deploy/van-trading-core/windows/mt5_worker`) requires that certificate (mTLS), verifies HMAC + nonce + 5 s skew,
  binds the alias to the terminal login, refuses orders without SL, refuses stop widening, refuses when the terminal
  has trading disabled, and never logs request bodies. The full path client → TLS → worker is tested in the repo.
- Two adapter defects were found by these tests and fixed: reads signed with `issued_ms = 0` (any real worker rejects
  it as skew) and the worker's rejection reason being dropped.

---

## Part E — Market data

- **Bar lake** (`vati.market_data.feeds.lake`): gzip CSV slices per symbol/timeframe with a sha256 manifest; reads
  verify bytes and return the slice hashes consumed, so a backtest can name its data. Parquet is the Phase 1 pyarrow
  gate; the manifest does not change.
- **Sources**: Dukascopy tick history (`.bi5` codec verified by round trip; zero-based month URL; FX week hours),
  Deriv history (unauthenticated with an app id), CSV import. `python -m vati lake dukascopy|import-csv|list`.
- **Internet reachability from this build container**: Dukascopy, Deriv, Stooq, Yahoo and Frankfurter were all
  blocked by the container's egress policy, so downloads were verified against exact-format fixtures rather than
  live bytes. On the VM the same commands run against the real hosts; `qualify.sh` reports what it could fetch.
- **Data truth**: every session loop writes `MARKET_DATA_HEALTH` (LIVE / DELAYED / STALE / NO_DATA) and every
  read model carries it; the Command Center never shows stale data as current (blueprint §46).

---

## Part F — Session service (NFP/Event Engine, Market Brain, Risk Authority, Router, adapters)

python -m vati serve --config /opt/van-trading/config/sessions/<alias>.json keeps the proven single-symbol DecisionCycle compatibility path. When the same signed account configuration names additional instruments, vati serve instead constructs one AccountCoordinatorService for the account alias so fresh candidates from all configured symbols compete before Risk Authority admission. The account runtime requires the shared PostgreSQL VATI authority store and a cross-host lease; it never falls back to process-local arbitration. The single-symbol path performs startup reconciliation, then per closed bar: MARKET_STATE → OPPORTUNITY → RISK AUTHORITY → ROUTER → PROTECT
→ RECONCILE → TCA → REVIEW → LEARN, plus `ACCOUNT_SNAPSHOT` and a heartbeat file each loop. The Tier-1 calendar
(`vati.intelligence.calendar_feed`) loads an owner or vendor file; an event is live-eligible only with two independent
sources, otherwise the matrix fails closed (whole pre-window is blackout). An `OWNER_HALT` written by the gateway or
the commander is observed on the next loop: new orders stop, venue stops stay. SIGTERM is graceful.

---

## Part G — Dedicated trading VEKL

`trading/vekl/server.mjs` runs DIAL's resolver code vendored byte-for-byte (`vendor/dial/PROVENANCE.json`, DIAL commit
`fa7c655`) against the Van trading registry, on loopback :9134, and persists every resolution as an activation
record with a deterministic `activation_id` (hash of policy version, resolver version, selected ids, registry
fingerprint and donor commit). A modified vendored file is refused at start. Hermes reaches it through the commander's
`vekl_resolve`; sessions cite the activation id in `MarketState`. DIAL's vekl-worker is no longer on the trading path.

---

## Part H — Hermes subordinate: the trading commander

`trading/commander` is the local "Desktop Commander" analogue for the trading VM, built as DIAL's local MCP plane
prescribes: a *subordinate capability, never a second authority*, and **not a shell**. Ten typed commands
(`status, ledger_status, services, restart_service, tail_log, run_backtest, vekl_resolve, halt, doctor, accounts`),
HMAC-signed requests bound to timestamp, nonce, method, path and body hash; allowlisted systemd units; secret
redaction on log tails; backtests confined to the data directory; `halt` requires an owner signature reference (A4)
and only appends a ledger event. `mcp_stdio.mjs` is the MCP shim Hermes spawns (`mcp_servers.van_trading_commander`);
`deploy/van-trading-core/hermes/register-commander-mcp.sh` splices that block into the live Hermes config without
touching another byte.

**Agent boundary for credentials.** The eleven account-onboarding commands (`account_upsert … mt5_ea_issue_key`)
exist on the same commander but are reachable only from the gateway's device-signed onboarding path. They are
omitted from `/v1/tools` (so Hermes never sees them as MCP tools; the shim refuses names it has not listed) and
the command route returns 403 when the requester is an agent (`hermes`, `sol`, `sonnet`, `codex`, `model`…), with
the refusal audited. A broker credential therefore has no route into a model prompt or tool call
(`test_credential_commands_are_hidden_from_agents_but_open_to_the_gateway`, and the stdio test's 403 case).

---

## Part I — Trading Command Center (Android)

Screens: **Overview** (account scope chips, balance/equity/floating/today/heat/drawdown tiles, chart with data-state
and SIMULATED badges, Van Market State with the animated embodiment and per-symbol summaries, open positions,
potential trades, recent trades, accounts, quick access), **Trades** (Past / Current / Potential), **Trade workspace**
(chart with entry/stop/target/exit levels, risk and reward zones and entry/exit markers; size, risk, R:R, P&L, R,
outcome; deterministic timeline from the ledger; Van's interpretation and review lessons; evidence hashes and
multipliers), **Instrument workspace** (timeframes, market context, indicators, setups and positions on the symbol),
**Risk Center** (heat utilisation against the mandate ceiling, drawdown, daily/weekly, concentration by instrument and
currency leg, position risk, mandate limits), **Accounts** (safety identity, connection state, equity, day P&L, kill
switch). Entry points: Command Centre button, overlay Trades panel (tap a row → trade workspace).

Design obligations kept from the owner's blueprint: one contextual system on shared trading objects; account scope
always visible; LIVE / DEMO / PAPER / READ ONLY on every account surface; data truth badges; confidence explicitly
labelled as an uncalibrated rule score; nothing fabricated (empty and unavailable states are explicit); no order path
anywhere in the app. Pure-Kotlin models and chart geometry are unit-tested off-device; the Compose screens could not be
compiled in this container (no Android SDK, Google Maven blocked) and are the first thing to build on a workstation.

---

## Part J — Evidence (2026-09-16, updated after builds K–L and the stack-lock/agent-boundary fix)

```text
$ python3 -m pytest -q                       355 passed (PostgreSQL ledger tests on a real PostgreSQL 16)
$ node --test trading/vekl/test/server.test.mjs          3 passed
$ node --test trading/commander/test/mcp_stdio.test.mjs  1 passed  (tool list = 10; account_credentials → 403)
$ python3 -m pytest trading/tests/test_stack_lock.py     7 passed  (ctrader_execution added to the sender/T0 sets;
                                                          an extra sender on event_backbone was induced and refused)
$ kotlinc + JUnit: AccountOnboardingTest, TradeBookTest, TradingModelsTest, ChartGeometryTest   16 passed
   (AccountOnboardingTest checks the device signature against a vector computed by the gateway's own code)
cTrader: codec against hand-verified wire bytes; adapter, OAuth, discovery against a fake cTrader over the same codec
MT5 pull: adapter ↔ shared queue ↔ signed pull server ↔ simulated Expert Advisor (replay, skew, key, alias refusals)
Onboarding: commander commands with injected Deriv/cTrader endpoints; gateway route with signature tampering, stale
actions, Deriv demo creation, OAuth link (tokens encrypted at rest, consumed after link), MT5-EA key issue
```

### J.0 Earlier evidence

```text
$ python3 -m pytest -q                       340 passed
$ node --test trading/vekl/test/server.test.mjs          3 passed
$ node --test trading/commander/test/mcp_stdio.test.mjs  1 passed  (spawns the real commander under uvicorn)
$ kotlinc + JUnit: TradeBookTest, TradingModelsTest, ChartGeometryTest   13 passed
$ bash deploy/van-trading-core/bootstrap.sh --dry-run    full plan printed; every script passes bash -n
$ deploy/van-trading-core/supabase/generate-env.sh       demo secrets replaced; anon/service JWTs decode to their roles
$ deploy/van-trading-core/pki/make-bridge-pki.sh         CA + commander/mt5-worker/client certs; openssl verify OK
$ deploy/van-trading-core/hermes/register-commander-mcp.sh   splice verified on a commented YAML; idempotent; backup taken
PostgreSQL ledger tests ran against a real PostgreSQL 16 in the container (VATI_TEST_PG_DSN).
```

Induced failures kept: nonce replay, wrong signing key, wrong CA, missing client certificate, widened stop, order
without SL, mandate/account mismatch, stale feed, tampered lake slice, tampered ledger row, modified vendored resolver,
rogue order sender in the stack lock, agent requester on a credential command (boundary disabled → test fails).

Correction on record: the build-L evidence line "Node 4 passed" was stale. After build L added the account commands
the stdio test's expected tool list no longer matched and the test hung on failure (the shim child was only killed
on the success path). Both are fixed here; the tool list Hermes sees is the original ten.

---

## Part K — What only the VM and the owner can close

1. `sudo bash deploy/van-trading-core/bootstrap.sh` on `van-trading-core`, then `qualify.sh` GREEN (arm64 packages,
   Supabase image pulls, systemd, ufw, commander over the VCN).
2. Hermes registration on `dial-hermes-control` (`register-commander-mcp.sh`) and a first `status` call.
3. Windows MT5 worker host: owner decision, `install.ps1`, certificates copied, `bridge.key` into the alias secrets.
4. Accounts: `vati accounts add` for a Deriv demo and/or an MT5 demo; session config; `vati-session@<alias>`.
5. Market data: `vati lake dukascopy …` for FX/gold history on the VM (the container could not reach Dukascopy).
6. Android build on a workstation with the SDK; device check of the Trading Command Center and the overlay panel.
7. Everything Rev 4 Part M already listed: real-data validation, Nautilus donor gate, curriculum, ZSE broker facts,
   independent security review, owner-signed LIMITED_LIVE.

---

## Part L — PR #49 closure authority addendum (owner-directed repository repair, 2026-09-20)

This addendum records the repository-level invariants the owner directed to be repaired during the PR #49 audit.
It does not mint live trading authority. Runtime authority still comes from the signed mandate and signed
strategy-promotion artifacts already required by this blueprint.

1. **Account-level allocation authority.** In a multi-instrument session, symbol-local evaluators may only produce
   CandidateOpportunity objects. Exactly one AccountDecisionCoordinator per account alias selects the order in
   which candidates reach the Risk Authority. It re-reads a candidate-specific RiskSnapshot before every
   admission. A missing Risk Authority or execution path is a refusal, never a successful selection.

2. **Risk-ceiling precedence.** Candidate conversion to TradeIntent requests no more than the capsule's admitted
   risk_limits.max_risk_per_trade and no more than the strategy budget in the signed mandate. Strategy budgets can
   narrow the existing capsule/mandate law automatically; raising a live ceiling requires a newly signed mandate
   and can never be applied by CapitalBudgetProposal itself.

3. **Evidence-bound strategy promotion.** For certificate-gated promotion states, the owner authority statement
   binds strategy_id, target state and the exact StrategyValidationCertificate.validation_hash. A token for one
   certificate cannot authorize another certificate. A strategy certificate must name immutable evidence refs and
   a data-manifest hash; production code provides no synthetic factory for a passing certificate.

4. **Certificate-backed feature admission.** A FeatureDefinition being registered does not make it production
   admissible. A certificate-required feature is unavailable to a capsule until FeatureRegistry re-evaluates a
   sealed FeatureValidationCertificate and records a PRODUCTION_ADMITTED certificate hash. Per-pass feature
   contracts also enforce venue class, timeframe and minimum history.

5. **Execution-policy boundary.** ExecutionPolicyEngine decides only how an already-approved trade is attempted.
   ExecutionRouter independently verifies the sealed policy decision, refuses DO_NOT_EXECUTE, and applies the
   selected template's bounded entry type and maximum slippage immediately before order submission.

6. **Cross-host account fence.** Multi-instrument production coordination uses a transactional PostgreSQL
   account_runtime_leases row. The current lease epoch travels to ExecutionRouter. Immediately before an
   OrderCommand may be submitted, the fence re-reads shared PostgreSQL authority and requires the same holder,
   the same epoch and a bounded remaining-validity margin. Store loss, takeover, stale epoch or insufficient
   validity all fail closed; a process-local cached lease is never sufficient authority to submit.

7. **MTF adoption boundary.** The timeframe-contract migration is provenance/schema adoption, not silent strategy
   mutation. The account runtime builds the required multi-timeframe state as shadow evidence from the existing
   BarLake and exposes completeness/hash truth. Those H4/H1/M15/M5 roles cannot alter a live strategy decision until
   a separately validated and owner-signed capsule revision explicitly adopts the MTF behavior.

8. **Candidate replay law.** Candidate IDs are deterministic across polling/restart. Re-admitting the same
   candidate ID and hash preserves its existing lifecycle state; a previously selected/rejected/expired candidate
   cannot become ACTIVE merely because the source bar was evaluated again.

9. **Restart lifecycle reconstruction law.** Restart never treats venue attribution alone as sufficient trading
   truth. An open venue position is reconstructed only when its trade_intent_id joins to the durable VATI
   ORDER_COMMAND that created it. Protection is rebuilt from the original command and may use a venue or durable
   current stop only when that stop is equal to or tighter than the original protection. Any unjoinable position,
   missing protection fact or widened stop remains unresolved and blocks new risk through reconciliation.

10. **Owner-ticket downstream-evidence law.** A signed owner ticket confirmation is consumed into runtime position
    truth before new risk is admitted. EXECUTION_RECEIPT durability and downstream lifecycle evidence are separate
    facts: after a crash, an existing receipt must not suppress a missing TCA_RECORD for an owner BUY or a missing
    TRADE_REVIEW for an owner SELL. Replay reconstructs memory/protection on every restart, repairs missing
    downstream evidence exactly once, and never duplicates evidence that is already durable.

The PR #48 anti-gap rule applies to all ten: a test or helper object is not a production join, and a repository
wiring gap may not be labelled an external runtime blocker.
