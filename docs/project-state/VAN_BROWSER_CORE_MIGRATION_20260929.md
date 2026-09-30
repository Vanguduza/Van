# van-browser-core — Stagehand production placement, model and migration (2026-09-29)

Authority: owner decisions 2026-09-29 §1 (Stagehand production host), §4 (model provider),
§5 (version); authorization record `auth-20260929-owner-stagehand-private-plane-gates`
(owner session instruction; no device or cryptographic signature claimed). Closes the
repository side of OQ-STAGEHAND-HOST, OQ-STAGEHAND-MODEL and OQ-STAGEHAND-VERSION-AT-ADOPTION.
Does **not** close signed ingress (§2, `SIGNED_INGRESS_PENDING`), the health production gate
(§6) or the verifier/executor blockers (§§7–8).

DEC-039: Stagehand upstream is a dependency pinned by exact version and integrity, and a
reference for reading its released `dist/` to answer compatibility questions. No upstream
code was copied into VAN.

## 1. Design

### 1.1 Zones

| Zone | Runs | Must not run |
|---|---|---|
| **van-browser-core** (new, dedicated host) | Stagehand 4.1.0 worker; Browser Harness 0.1.13 worker and the Harness-owned Chromium; the mTLS edge | anything with trading, owner-model, owner-private memory or Project Truth authority |
| van-trading-core | VATI, Commander, ledger, brokers | Stagehand in production (historical browser package is dev-only) |
| dial-control | Hermes, VAN Gateway, Browser Router | Stagehand in production |
| van-private-core | Owner Cognitive Model, owner-private Hindsight/OpenViking | Stagehand, Chromium, generic browser automation |

Stagehand attaches to the Harness-owned Chromium through a loopback CDP handoff file
(`/run/van-browser-core/<alias>/cdp-endpoint.json`), so the two must co-reside; that is why
the Harness and its Chromium move with Stagehand (§1 permits co-residence under the
existing lease/isolation rules). The deterministic Harness path's *policy* is unchanged —
Stagehand being PRODUCTION_DISABLED never disables it.

### 1.2 Repository topology

```text
deploy/van-browser-core/
  README.md                         package overview
  zone.json                         machine-readable zone manifest (excluded authorities, interfaces, release, model)
  bootstrap.sh                      dedicated-host install; refuses foreign-zone hosts and wildcard/loopback edge binds
  qualify.sh                        JSON self-qualification; UNKNOWN is never GREEN
  runtime.env.example               the zone's only env; VAN_TRUST_ZONE=van-browser-core; model pin
  browser/package.json, package-lock.json   moved (git mv) from deploy/van-trading-core/browser
  browser/harness_service.py        moved; zone-local default paths; reports trust_zone
  browser/stagehand_service.mjs     moved; zone refusal, model pin, trust_zone/model/credential-locus on /health
  systemd/van-browser-harness.service, van-stagehand.service, van-browser-core-edge.service
  edge/Caddyfile                    mTLS edge, fixed operations only
  pki/make-browser-core-pki.sh      zone-private CA; one caller identity (van-gateway)
backend/van_gateway/automation/placement.py   gateway-side placement/model gate
tests/contracts/test_van_browser_core_zone.py  zone contract
backend/tests/test_stagehand_placement.py      gate unit tests
```

### 1.3 The placement gate (the function the Programme B router calls)

```python
from van_gateway.automation.placement import stagehand_production_enabled
enabled, reason = stagehand_production_enabled(settings, *, worker_health=None)
# -> tuple[bool, str]; False means STAGEHAND = PRODUCTION_DISABLED
```

`stagehand_production_state(settings, *, worker_health=None)` returns the same answer as a
projection with the pin facts for health/readiness surfaces.

It returns `(True, "STAGEHAND_PLACEMENT_SATISFIED")` only if all hold, in this order:

1. `browser_enabled` (`BROWSER_FABRIC_DISABLED`);
2. `browser_stagehand_zone` is declared (`STAGEHAND_ZONE_UNDECLARED`), is not
   van-trading-core / dial-control / van-private-core (`STAGEHAND_PLACEMENT_FORBIDDEN:<zone>`)
   and is exactly `van-browser-core` (`STAGEHAND_ZONE_NOT_VAN_BROWSER_CORE:<zone>`);
3. `browser_stagehand_base_url` is `https` to a non-loopback host
   (`STAGEHAND_ENDPOINT_NOT_CROSS_ZONE_MTLS`) and the three mTLS client files exist
   (`STAGEHAND_MTLS_CLIENT_IDENTITY_MISSING:<field>`);
4. provider/model are exactly `anthropic`/`claude-sonnet-5`
   (`STAGEHAND_MODEL_UNCONFIGURED`, `STAGEHAND_MODEL_NOT_OWNER_DECIDED:<p>/<m>`);
5. `worker_health` (the worker's `GET /health` through the edge, fetched by the caller) is
   present and `ok` (`VAN_BROWSER_CORE_UNAVAILABLE:health_unverified|worker_not_ok`), proves
   `trust_zone == van-browser-core` (`STAGEHAND_RUNNING_ZONE_MISMATCH:<zone>`), runtime
   `4.1.0` (`STAGEHAND_RUNTIME_VERSION_MISMATCH`), model `anthropic/claude-sonnet-5`
   (`STAGEHAND_RUNTIME_MODEL_MISMATCH`), a present credential
   (`STAGEHAND_MODEL_CREDENTIAL_UNAVAILABLE`), that the provider key stays out of browser
   memory (`STAGEHAND_PROVIDER_KEY_ENTERS_BROWSER_MEMORY`) and no unbounded authority
   (`STAGEHAND_WORKER_AUTHORITY_UNBOUNDED`).

It is placement/model only. The router must AND it with the governance gates (§2 signed
ingress, §6 production gate, §§7–8 verifier/executor). It lives outside
`backend/van_gateway/browser/**` so placement has one owner.

Today, with every setting at its default, it returns `(False, "BROWSER_FABRIC_DISABLED")`;
with a real van-browser-core worker it would still return
`STAGEHAND_PROVIDER_KEY_ENTERS_BROWSER_MEMORY` (§3 below).

### 1.4 Excluded authorities

van-browser-core has no direct authority over, and its unit/env/config files may not name
any credential, socket, DB path or env name of: VATI Risk Authority
(`trading/vati/risk/authority.py`), Execution Router (`trading/vati/execution/router.py`),
broker credentials (`DERIV_API_TOKEN`, `CTRADER_*`, `BRIDGE_*`), trading secrets (every key
of `deploy/van-trading-core/env/van-trading-core.env.example`, the Supabase store's secret
keys, the Temporal bridge token), the Owner Model DB (`VAN_DATABASE_PATH` and the gateway's
authority secrets), owner-private Hindsight/OpenViking, or Project Truth mutation
(`GITHUB_TOKEN`/`GH_TOKEN`, `van-github-recovery`, `docs/project-state`). The contract test
derives these from the repository files and gateway `Settings`, and additionally requires
that the workers read **only** env names declared in the zone's own `runtime.env.example`.

### 1.5 Cross-zone interfaces (the complete list)

| ID | Direction | Transport / authentication | Surface |
|---|---|---|---|
| BC-IF-1 | van-gateway → van-browser-core | TLS 1.3 mutual TLS at the edge, zone-private CA issuing one caller identity | `GET /stagehand/health`, `POST /stagehand/{observe,extract}`, `GET /harness/health`, `POST /harness/{navigate,page_info,click,fill,press,scroll,screenshot,wait,upload,tabs}`; everything else 404, including `/stagehand/act` (§8) and `/stagehand/agent` |
| BC-IF-2 | van-browser-core → Browser Stream Host control agent | private VCN mTLS; `deploy/van-browser-stream/pki` now issues `browser-harness.browser-core.van.internal` / `stagehand.browser-core.van.internal` | Browser Control Agent wire protocol; no raw CDP |
| BC-IF-3 | van-browser-core → model provider | HTTPS egress to `api.anthropic.com` only (allowlist is a provisioning gate) | file-backed `secretref://browser/stagehand-model` |
| BC-IF-4 | van-browser-core → public web | Chromium egress | task domains bounded per task by gateway policy |

No inbound path exists from van-trading-core, van-private-core or Hermes shells/MCP; Hermes
reaches the browser only through van-gateway.

## 2. Historical placement: kept, development-only

`deploy/van-trading-core/browser/{bootstrap-browser-runtime.sh,runtime.env.example}` and
`deploy/van-trading-core/systemd/vati-{stagehand,browser-harness}.service` are kept as
**development-only** packaging, not deleted:

- the historical bootstrap exits 48 unless `VAN_BROWSER_HISTORICAL_DEV_ONLY=1`, and 49 if
  `VAN_ENV=production`; it installs from the moved sources;
- `deploy/van-trading-core/bootstrap.sh` no longer installs any browser runtime unless that
  flag is set (and no longer demands `VAN_VEKL_WORKER_HOST` for a production bootstrap);
- both vati-* units refuse to start (`ExecStartPre`) unless the env file says
  `VAN_BROWSER_HISTORICAL_DEV_ONLY=1` and `VAN_TRUST_ZONE=van-trading-core`;
- the Stagehand worker itself refuses any zone but van-browser-core without the flag, and
  with it reports `production_state: DEV_ONLY_NOT_PRODUCTION`;
- `deploy/van-trading-core/qualify.sh` now reports `stagehand_not_on_trading_core` RED if
  `vati-stagehand.service` is enabled or active on the trading core;
- the gateway gate refuses `van-trading-core` by name regardless of any of the above.

## 3. Model (§4) and version (§5)

- Gateway `Settings` default `browser_stagehand_model_provider/_name` to
  `anthropic`/`claude-sonnet-5` (previously empty). The van-browser-core worker pins
  `VAN_STAGEHAND_MODEL_PROVIDER=anthropic`, `VAN_STAGEHAND_MODEL_NAME=claude-sonnet-5` and
  answers 409 `MODEL_NOT_OWNER_DECIDED` to any request naming another model. The
  `StagehandAdapter` constructor default (unit G's file) is unchanged.
- **Compatibility, reproduced offline** against the locked tarball (`npm pack
  @browserbasehq/stagehand@4.1.0`, integrity matches the lock): the exported
  `StagehandClientCreateConfigSchema` **accepts** `anthropic/claude-sonnet-5` (the model id
  is in 4.1.0's closed `AnthropicModelId` enum) and rejects a bare `claude-sonnet-5` (the
  worker always sends the provider-prefixed form). The in-browser runtime lists
  `claude-sonnet-5` as a known model with its own capability branch and calls
  `https://api.anthropic.com`. No live model call was made; runtime operation with Sonnet 5
  remains a live-canary gate.
- **Consequence for pinning:** 4.1.0's model-id enum is closed. Any identifier not in it —
  including any dated snapshot id Anthropic might publish — is rejected by the schema. So
  pinning an immutable snapshot, if one exists, would need a different Stagehand version or a
  client-side LLM callback, which is a new owner decision. Whether Anthropic exposes an
  immutable snapshot id for Claude Sonnet 5 is **UNVERIFIED** from this sandbox;
  `browser_stagehand_model_revision` stays empty and `stagehand_production_state` reports
  `UNVERIFIED_IMMUTABLE_SNAPSHOT`.
- **Credential finding (blocks production):** with a `{ modelName, apiKey }` model config,
  the 4.1.0 SDK forwards the config — key included — in `stagehandInit` to the Stagehand
  runtime extension's service worker inside Chromium, which calls the provider from there.
  That places the provider key in browser memory, which §4 forbids. The worker reports
  `provider_key_in_browser_memory: true` and the gate keeps Stagehand PRODUCTION_DISABLED.
  4.1.0 also offers a client-side LLM (`model: { generate }`, "never crosses the wire"),
  under which the key can stay in the Node worker; adopting it is follow-up work.
- Version identity everywhere this package touches: `@browserbasehq/stagehand` 4.1.0 =
  upstream release commit `cd7b230778cf92269e4cb90e80d97f5113781c51`, npm integrity
  `sha512-PJikMBVoaCRh6TFD7GcmeISmsMq4IwUu1BD5FOsGUVDUxrVqZomWa6W6dF+a/zu4xRZu2Z2xX1nXVMDaCuZWsw==`.
  `ad2bf12e…` is later unreleased upstream work and is not 4.1.0.
- The pre-existing worker `stagehand_service.mjs` did not parse (`node --check` →
  `SyntaxError: Invalid or unexpected token` on the escaped template literal in its listen
  callback at base 379d6ab), so it could never have started. Fixed in the moved file.

## 4. Migration plan

1. **Repository (this change).** New package, gate, contract; historical package dev-only.
2. **Provision van-browser-core** (external): dedicated VM on the private overlay, Node
   22.18+, Python 3.12, Caddy; no other zone installed on it.
3. `make-browser-core-pki.sh --with-foreign-test-cert`; move the van-gateway client pair and
   `ca.crt` to the gateway host; move `ca.key` offline.
4. Place the provider credential at `/var/lib/van-browser-core/secrets/stagehand-model`
   (0600, van-browser). It never enters the repository.
5. `bootstrap.sh`, then `qualify.sh` until exit 0.
6. Re-issue the Browser Stream Host client certificates with the `.browser-core` identities
   and update the control agent's caller table.
7. On the existing van-trading-core: `systemctl disable --now vati-stagehand.service
   vati-browser-harness.service` and remove the units; `qualify.sh` must show
   `stagehand_not_on_trading_core` GREEN. Profiles under `/var/lib/van-trading/browser` are
   not copied automatically — re-establish them on van-browser-core (profile moves are an
   owner decision).
8. Gateway: set `VAN_BROWSER_STAGEHAND_ZONE=van-browser-core`,
   `VAN_BROWSER_STAGEHAND_BASE_URL`/`VAN_BROWSER_HARNESS_BASE_URL` to the edge, and the
   three `VAN_BROWSER_CORE_*_FILE` paths. The router (unit G) wires the mTLS transport and
   passes the worker health into `stagehand_production_enabled`.
9. Stagehand stays PRODUCTION_DISABLED until the §4 credential locus is fixed, the live
   canary passes with 4.1.0 reporting the expected artifact, and the governance gates are
   green.

## 5. No-temporary-trading-core rule

If van-browser-core is not provisioned, not qualified, or unreachable, **STAGEHAND =
PRODUCTION_DISABLED**. Stagehand is not provisioned on van-trading-core, dial-control or
van-private-core as a stop-gap. This is enforced four ways: the gateway gate refuses those
zones by name and refuses any zone whose health it cannot verify; the worker refuses to
start outside van-browser-core; the historical units and bootstrap refuse without an
explicit dev-only flag; and `tests/contracts/test_van_browser_core_zone.py` fails if any
package installs a production Stagehand unit outside `deploy/van-browser-core`.

## 6. External provisioning gates that remain

| Gate | State |
|---|---|
| van-browser-core host exists on the private overlay (dedicated, no other zone) | PENDING (external) |
| egress allowlist: `api.anthropic.com` + task domains only | PENDING (external) |
| Caddy installed; `caddy validate` of `edge/Caddyfile` (not available in the repo sandbox) | PENDING (host) |
| edge PKI issued; client pair on gateway; CA key offline | PENDING (host) |
| provider credential file placed on the host | PENDING (owner/operator) |
| `qualify.sh` exit 0 on the host | PENDING (host) |
| live canary: runtime reports 4.1.0 @ cd7b2307, Sonnet 5 operates through Stagehand | PENDING (live) |
| immutable Sonnet 5 snapshot id | UNVERIFIED; Stagehand 4.1.0 accepts only its closed id list |
| provider key kept out of browser memory (client-side LLM callback) | OPEN (repository follow-up) |
| Browser Stream Host certificates re-issued with `.browser-core` identities | PENDING (host) |
| decommission `vati-stagehand`/`vati-browser-harness` on the live trading core | PENDING (operator) |
| signed owner ingress (§2) | SIGNED_INGRESS_PENDING — unchanged, not waived |
| egress proxy + zone firewall qualified on the host (`qualify.sh` §6 checks GREEN; `VAN-BROWSER-CORE-EGRESS-001.yaml` → QUALIFIED with the pinned report) — §8 | PENDING (host); gates browser_harness, stagehand, jev_browser_effect |

## 7. Enforcement points and known limitations (independent review I, 2026-09-29)

**The gate is in the adapter.** `StagehandAdapter` evaluates the Stagehand production gate
before every worker call (observe, extract, act). The default gate is the router's own
composition (`interaction_router.load_stagehand_production_gate`): placement with the
worker's live `/health` AND `evaluate_production_gates()`. A missing, failing or non-`True`
gate refuses the call (`STAGEHAND_PRODUCTION_DISABLED:<reason>`). The adapter reports
`configured = false` and status `POLICY_DISABLED` while the gate is closed. So the
L2–L5 assignment path, the NotebookLM consumer and any future consumer are held to the
same gate as the B5 router (review I B-1). The deterministic Harness path does not use the
adapter and is unaffected.

**Owner takeover preempts the assignment path.** `BrowserSubagentRunner` checks the
router's `OwnerControlProbe` before every propose and every execute. Owner control, an
unreadable control state or a missing probe end the run `OWNER_TAKEOVER`, and the task is
left `WAITING_FOR_OWNER` (review I M-4). Resuming automation after the owner hands control
back is a new assignment; there is no automatic resume.

**COMPLETED needs a verdict.** `BrowserTaskService.complete(COMPLETED)` requires the task's
latest `postcondition_verification` evidence row to be `VERIFIED`. Only the verifier path
writes that kind; `seal_evidence` refuses it. The internal `/complete` route answers
409 `BROWSER_TASK_NOT_VERIFIED` otherwise (review I M-2).

**Limitation — the personal NotebookLM consumer is UNAVAILABLE.** `NotebookConsumerProvider`
asks questions and creates notes with `stagehand.act`, which §8 removed from the production
path. Its only read-back is `stagehand.extract`, i.e. Stagehand checking its own work,
which §7 forbids. It therefore reports `UNCONFIGURED` with
`details.unavailable_reason = NOTEBOOK_CONSUMER_REQUIRES_STAGEHAND_ACTUATION_AND_SELF_VERIFICATION`
and refuses every operation before opening a browser task (review I M-7). Restoring it
means rebuilding both operations as typed Browser Harness actions with an independent
postcondition verifier. Re-enabling `act()` is not an acceptable fix. NotebookLM
Enterprise (API) is unaffected.

**Worker `/act` and version identity.** The van-browser-core worker serves `/act` only on
an explicitly development-only placement (`VAN_BROWSER_HISTORICAL_DEV_ONLY=1`). Otherwise
`/act` is `404 NOT_FOUND`, like any unknown path, and `/health` reports
`act_endpoint_enabled: false`.
`/health.runtime_version` is read from the installed
`node_modules/@browserbasehq/stagehand/package.json` (`runtime_version_source:
installed-package-metadata`), not a constant. The placement gate requires that source, the
exact 4.1.0 version and `act_endpoint_enabled: false`, and `qualify.sh` checks the same
fields (review I minor 5).

## 8. Egress proxy and zone firewall (unit G12, 2026-09-30)

Authority: owner answers 2026-09-30 after independent review I7 (Claude Code session
`session_01ELKqm4GCPmPvF3ggKkgB1J`; no signature claimed), quoted verbatim in
`docs/decisions/VAN-BROWSER-CORE-EGRESS-001.yaml`: **"Egress proxy (Recommended)"** —
"Route the van-browser-core browser through a local egress proxy that refuses WebSocket
upgrades and non-GET requests unless the task is admitted as mutating. That is repository
and zone work, and it also covers UDP. Stagehand stays production-disabled until it exists."
— and **"Firewall UDP in zone (Recommended)"** — "Add a host firewall rule in the
van-browser-core deploy that drops all UDP from the browser user except DNS to the resolver.
Applied at provisioning and checked by qualify.sh."

### 8.1 What review I7 found, reproduced at 6ff52eb7 before the fix

Instrument: the fixture server's request log and a UDP socket on its port (outside the
browser), real Chromium 1194 with the worker's guard flags.

| Probe | Result at 6ff52eb7 |
|---|---|
| `new WebSocket('wss://docs.example.com/api/ws-pay?amount=500')` | `GET /api/ws-pay` reached the server |
| same, with `Network.setBlockedURLs(["ws://*","wss://*"])` | `GET /api/ws-pay` reached the server |
| WebRTC `RTCPeerConnection` with a STUN server | 5 UDP datagrams |
| `new WebTransport('https://…:<port>/wt-pay')` | 4 UDP datagrams |

With the proxy flags (below) and no firewall, WebTransport sent 0 datagrams (Chromium does
not open QUIC around a configured proxy) but WebRTC STUN still sent 5: only the firewall
stops it.

### 8.2 Design choice: TLS interception, not a CONNECT allowlist

| | CONNECT host allowlist | TLS interception (chosen) |
|---|---|---|
| `wss://<in-scope host>/ws-pay` handshake | **passes** (the proxy sees only `CONNECT host:443`) | refused: the proxy reads `Upgrade: websocket` inside TLS |
| non-GET inside TLS | not visible; left to the CDP guard (which covers only the action window) | refused unless mutating + inside the task scope, for as long as the policy is in force |
| out-of-scope host | refused at CONNECT | refused at CONNECT |
| key material | none | zone-local CA key + one leaf key (below) |
| Chromium trust change | none | `--ignore-certificate-errors-spki-list=<leaf key SPKI>` on this Chromium only |

The owner's case is the in-scope handshake (`/ws-pay?amount=500` on the task's own host), which
only interception refuses, so interception is used. The pin names the **leaf key**, not the
CA: the flag ignores errors for any chain containing a pinned key, and a site could append
the (public) CA certificate to its own chain, but it cannot prove possession of the leaf key.

Key handling: the CA key and the leaf key are generated by the proxy on first start in
`/var/lib/van-browser-egress` (directory 0700, files 0400, owner `van-browser-egress`); they
are never copied off the host, never readable by the browser user (`van-browser`) and never in
the repository. Only the leaf key's SPKI hash (public) leaves the proxy, over its control
socket to the Harness. Rotation: stop the proxy, delete the two keys, start it (the Harness
unit is `PartOf` the proxy and restarts with it). Upstream TLS is verified against the system
trust store; the proxy offers HTTP/1.1 only to Chromium, so a WebSocket arrives as an Upgrade
request it can read.

### 8.3 Enforcement

- **Proxy** (`deploy/van-browser-core/browser/egress_proxy.py`, `van-browser-egress.service`,
  standard library + the `openssl` CLI — no new Python dependency). One loopback listener per
  profile alias. Per request: no/expired policy → `EGRESS_POLICY_UNKNOWN`; CONNECT only to a
  task-scope origin; origin outside the scope (GET included) → refused; GET/HEAD without a body
  pass; other methods, bodies and `Upgrade: websocket` only for a task admitted as mutating and
  inside its scope (the shared URL scope rule, byte-identical third copy, pinned by
  `tests/contracts/test_task_scope_shared_url_rule.py`); other upgrades refused; non-global
  upstream addresses refused. One request per connection. Decision log: alias, method,
  origin, code — no path, query, header or body.
- **Policy channel.** `network_guard_env` (Harness) verifies the gateway's effect MAC
  (`van-harness-effect/1`), then hands the policy and the MAC to the proxy over its Unix
  control socket; the proxy re-verifies the MAC with its own copy of the fence key and keeps
  the newest lease generation. A page cannot reach the socket or forge the MAC. A refused
  policy refuses the action (`EGRESS_POLICY_REFUSED`).
- **Chromium** (`ChromeSession.ensure()`): the only change is one argv line,
  `*egress_proxy_flags(self.alias),` after `*NETWORK_GUARD_CHROMIUM_FLAGS,` (for unit G11's
  merged `--disable-features` work): `--proxy-server`, `--proxy-bypass-list=<-loopback>`, the
  SPKI pin, `--disable-quic`. A trust-zone worker refuses to start Chromium without a proxy.
- **Firewall** (`deploy/van-browser-core/firewall/van-browser-core.nft`,
  `van-browser-core-firewall.service`): for sockets of the browser user only — UDP dropped
  except DNS to `VAN_BROWSER_DNS_RESOLVER`; TCP only to 127.0.0.0/8 and ::1; any other TCP
  reset; anything else dropped. Applied by `bootstrap.sh` at provisioning (refused without an
  IPv4 resolver or `nft`); the Harness and Stagehand units are bound to it.
- **Qualification** (`qualify.sh` §6, all required): `firewall_loaded`,
  `browser_udp_blocked`, `browser_tcp_bypass_blocked`, `egress_proxy_active`,
  `egress_refuses_without_policy`, `egress_policy_mac_enforced`,
  `egress_refuses_websocket_and_write`, `harness_uses_egress_proxy`.
- **Production gate.** `docs/decisions/VAN-BROWSER-CORE-EGRESS-001.yaml` gate
  `egress_qualification` (kind `qualify_report`) is required by the `browser_harness`,
  `stagehand` and `jev_browser_effect` capabilities. It is PENDING. GREEN needs status
  `QUALIFIED` *and* the host's `qualify.sh` report under `evidence/van-browser-core/qualify/`,
  sha256-pinned in the record, for zone van-browser-core, with every required check present,
  required and GREEN; a RED check is BLOCKED; the word alone is UNKNOWN.

### 8.4 Verified where

| Claim | Evidence | Where |
|---|---|---|
| ws:// and wss:// handshakes to `/ws-pay` refused, absent from the server log | `backend/tests/test_browser_egress_proxy.py` | real Chromium + proxy process, sandbox |
| out-of-scope `wss://` host and out-of-scope GET refused at CONNECT | same | sandbox |
| in-scope GET passes; no policy refuses all; loopback refused; delayed writes refused for read-only tasks; SPKI pin required | same | sandbox |
| MAC-less / flipped / stale policy refused | same + `tests/contracts/test_van_browser_core_egress_proxy.py` | sandbox |
| browser-uid UDP (STUN, QUIC, other DNS) fails with EPERM; DNS to the resolver passes; direct TCP reset; loopback TCP connects; other users untouched | `tests/contracts/test_van_browser_core_firewall.py` (live) | real nftables in a throw-away network namespace, sandbox |
| `qualify.sh` reports the firewall and proxy checks GREEN with the ruleset and a running proxy, RED without | same | network namespace, sandbox |
| firewall loaded and enforced on the van-browser-core host; `qualify.sh` exit 0 there | — | **UNVERIFIED** (no host) |

### 8.5 Remaining limits

- Live enforcement on a provisioned host is unverified (above).
- DNS to the configured resolver stays open to the browser user (the owner's exception):
  lookups can carry data; nothing inspects them. Behind the proxy Chromium needs no DNS.
- Loopback TCP stays open to the browser user (CDP, the Harness API and the proxy listeners
  share the uid). Chromium routes loopback through the proxy, which refuses it; a renderer
  escape is not stopped by the firewall.
- GET/HEAD to any path of an in-scope origin passes: a state-changing GET on an in-scope site
  is not refused (the owner's wording is "POST/PUT/DELETE and similar"). Out-of-scope origins
  are refused for every method, which closes I7's out-of-scope GET/prefetch case.
- A task's policy stays in force until the next action on that profile replaces it or
  `VAN_EGRESS_POLICY_TTL_SECONDS` (600) passes; background writes of a finished mutating
  task's pages can be admitted in that window, inside that task's scope only.
- HTTP/1.1 only towards Chromium; chunked request bodies refused; one request per connection.
- The proxy holds decrypted page traffic in memory (cookies, bodies); it logs none of it.
- Stagehand's model-provider traffic via the service tunnel (`HTTPS_PROXY`,
  `NODE_USE_ENV_PROXY`) is unverified; Stagehand stays PRODUCTION_DISABLED.
- The resolver must be IPv4.

### 8.6 Guard canary origin (unit G14, 2026-09-30)

Owner answer after unit G13, "In-zone canary origin (Recommended)": *"The canary serves its
fixture from a dedicated canary hostname on the zone's private overlay, listed in the proxy
config as the only allowed non-global upstream. It is checked by qualify.sh and never reachable
by a task scope. The proxy's local-address rule stays strict for everything else."*

**Reproduced before the fix (17fec5d8).** `guard_canary.py` behind the proxy exited 1: every
case navigated to the proxy's 403 page, `/describe` found no `#b` and `/click` answered
`TARGET_BINDING_REQUIRED`. A direct probe of the proxy with a MACed read-only policy answered
`EGRESS_UPSTREAM_ADDRESS_REFUSED` for a fixture on 127.0.0.1 and on 192.0.2.2 alike, and the
decision log said `ALLOW` for both (the address refusal happened after the log line; it is now
logged as `UPSTREAM`).

**Design.**

| Piece | What it does |
|---|---|
| Origin | `VAN_BROWSER_CANARY_ORIGIN` (`https://<name>.internal[:port]`) at `VAN_BROWSER_CANARY_ADDRESS` (private IPv4; loopback, unspecified, link-local, multicast, reserved and global refused; bootstrap.sh defaults it to the edge's overlay address). Certificate self-signed for the name by bootstrap.sh. |
| Proxy exception | Exact host, pinned address (no DNS lookup), exact port, TLS only, verified against the pinned canary certificate only. Used only while alias `guard_canary` holds the read-only policy of task `van-guard-canary` for the lease qualify.sh armed (`op: canary`, MAC `van-egress-canary/1` under the lease-fence key, 180 s, ended by that lease's end or a newer lease). Anything else naming the canary host is `EGRESS_UPSTREAM_ADDRESS_REFUSED`. |
| Never task-reachable | `*.internal` is reserved: the gateway (`task_scope.py`: declared scopes, target domains, owner-approved widening; recorded scopes fail closed), the Harness (409 `TASK_SCOPE_RESERVED_HOST` before the fence, unless the canary's own MAC-checked call) and the proxy (`POLICY_SCOPE_RESERVED_HOST`). |
| Canary | Serves the fixture over TLS on the canary address; immediate and delayed guard cases through the proxy; a `proxy` case (GET through the canary lease's listener reaches the fixture, a WebSocket upgrade is refused `EGRESS_WEBSOCKET_REFUSED` and never reaches it); a `task_refused` case. |

**Verified where** (repository sandbox; the overlay address is the sandbox interface's
TEST-NET address 192.0.2.2; Chromium 1194; browser-harness 0.1.13):

| Claim | Evidence |
|---|---|
| canary passes end to end through the proxy and the real Harness worker (browser-harness binary) | live run: `guard_canary.py` exit 0, and the real `qualify.sh` (only the installed canary path and interpreter swapped) reports `network_guard_canary` GREEN |
| a normal task cannot reach the canary origin | `backend/tests/test_browser_canary_origin.py`: API create 422, Harness 409, proxy `POLICY_SCOPE_RESERVED_HOST`, another alias's Chromium gets `EGRESS_CONNECT_OUT_OF_SCOPE`, an unarmed canary lease gets `EGRESS_UPSTREAM_ADDRESS_REFUSED` |
| 127.0.0.1, localhost, the overlay address under any other name, other private and link-local addresses stay refused while the canary is armed | same file (live) + `tests/contracts/test_van_browser_core_egress_proxy.py` |
| Chromium's own resolution is not involved | Chromium launched with `--host-resolver-rules=MAP <canary name> 127.0.0.1`; the page still comes from 192.0.2.2 and the loopback service sees nothing |
| each guard fails when broken | 10 induced mutations (proxy reserved-host check, grant check, exact port, local-address rule, certificate pin, WebSocket rule; Harness reserved-scope refusal, canary MAC; gateway reserved_host, owner-widening catch): each failed its tests; live: breaking the guard, the proxy's WebSocket rule or the exception turns the canary RED |
| on a provisioned host (overlay address, Chromium 1243) | **UNVERIFIED** |

**Limits.** Every holder of the lease-fence key (the gateway's copy, the Harness, the proxy,
root) can compute the canary MAC; the separation from task traffic is the reserved names, the
fixed alias/task id and the MAC context, not a separate key. Under the proxy Chromium never
resolves the canary name, so `--host-resolver-rules` plays no part in production.

### 8.7 Review I8 remediation in the egress scope (unit G14, 2026-09-30)

Each finding was reproduced on this branch before the fix, with review I8's own probes.

| Finding | Reproduced | Fix | After |
|---|---|---|---|
| MAJOR-3 request smuggling | `proxy_attacks.py`: `X-A: 1\n\nPOST /api/pay` put a POST upstream under a read-only policy (CONNECT and plain HTTP); a smuggled DELETE outside the path scope under a mutating one | CR/LF/NUL in request and header lines, non-visible-ASCII targets and control characters in header values refused; the parsed, normalised target is forwarded; listeners serve only the configured browser uid, the service tunnel only the Stagehand uid (owner read from `/proc/net/tcp` for the exact 4-tuple: SO_PEERCRED exists only for Unix sockets, and `--proxy-server` needs TCP) | every smuggling variant `EGRESS_REQUEST_INVALID`, nothing upstream; root refused `EGRESS_CLIENT_REFUSED` |
| MAJOR-4 firewall | `fw_netns.py`: after the ruleset root's pings got no reply and its ICMP port-unreachable never arrived | output chain accepts; only `meta skuid { browser, stagehand } jump browser_out` | root ping REPLY and unreachable received; browser/Stagehand uids confined as before |
| MINOR-1 egress gate | gate-lab report with fails=2, `network_guard_canary` RED: GREEN | fails must be 0 and every required check GREEN; `network_guard_canary`, `egress_refuses_smuggling`, `egress_refuses_other_users`, `stagehand_isolated` required | the lab report is BLOCKED |
| MINOR-2 restart | after a proxy restart a finally revoked lease's policy was accepted and its POST went through | newest/ended leases persisted (0600, fsync+rename) | `POLICY_LEASE_ENDED` / `POLICY_GENERATION_STALE` after restart |
| MINOR-4 Stagehand keys | Stagehand ran as `van-browser` (unit file) | own user `van-stagehand`; control socket group `van-egress-ctl`; own secret root; CDP endpoint files 0640 in 0750 dirs | `stagehand_isolated` check (RED in the sandbox: no Stagehand; its probe verified denied) |
| MINOR-5 qualify.sh | argv from the Harness's own report; any ECONNREFUSED passed; TCP/53 open | argv read from `/proc/<pid>/cmdline`; reject counter must increase; TCP/53 rule removed | live: the argv check flagged the sandbox's foreign non-proxied Chromium processes and passed the Harness's own; a kernel RST without the ruleset is RED |
| MINOR-7 OPTIONS | refused under read-only | OPTIONS without a body is a read | reaches in-scope origins; out-of-scope and with a body refused |

Induced failures: 12 mutations of these fixes; 11 are caught by a test. The survivor: removing
only the CR/LF/NUL line check, because the header-value, header-name and target checks also
refuse those bytes; removing it together with the header-value check lets the smuggled request
through and is caught (live). One mutation (`stagehand_isolated` accepting anything) first
survived too: the check's probe crashed on a numeric uid and was RED for the wrong reason.
Correction: c2d6390e's message claims that qualify.sh fix, but the commit holds only the test;
the fix was lost when the induction script restored qualify.sh with `git checkout` before it
was committed (the full suite run at 8921882c showed it: the netns qualify test failed). The fix
is in the commit after 8921882c, and the probe's stderr now reaches the check's detail. Remaining: IPv6 neighbour discovery and kernel tunnels
are accepted by construction but untested (the sandbox has no IPv6); a loopback resolver
(e.g. 127.0.0.53) stays reachable over TCP like every loopback port; everything here is
sandbox evidence, not host qualification.
