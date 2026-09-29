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

**Worker `/act` and version identity.** The van-browser-core worker serves `/act` only when
`VAN_STAGEHAND_ACT_ENDPOINT_DEV_ONLY=1` is set on a development-only placement. Otherwise
`/act` is `404 NOT_FOUND` and `/health` reports `act_endpoint_enabled: false`.
`/health.runtime_version` is read from the installed
`node_modules/@browserbasehq/stagehand/package.json` (`runtime_version_source:
installed-package-metadata`), not a constant. The placement gate requires that source, the
exact 4.1.0 version and `act_endpoint_enabled: false` (review I minor 5).
