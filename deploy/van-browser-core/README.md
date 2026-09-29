# van-browser-core — deployment package

Owner decision 2026-09-29 §1 (OQ-STAGEHAND-HOST). The dedicated VAN browser/automation
trust zone. Stagehand and the Harness-owned Chromium run here in production, and nowhere
else. Design, migration plan and gates: `docs/project-state/VAN_BROWSER_CORE_MIGRATION_20260929.md`.

Nothing in this directory has been run on a real host. There is no van-browser-core host
yet; provisioning it is an external gate. Until it exists and qualifies,
**STAGEHAND = PRODUCTION_DISABLED** — the gateway's
`van_gateway.automation.placement.stagehand_production_enabled()` says so, and there is no
fallback placement. Do not provision Stagehand on `van-trading-core` "for now".

```text
 dial-control / VAN Gateway                      van-browser-core (dedicated host)
   Browser Router (Programme B)                    ┌─────────────────────────────────────┐
   placement gate ──────── mTLS, one caller ─────► │ edge :9443 (private overlay only)   │
                                                   │   /stagehand/{health,observe,extract}│
                                                   │   /harness/{fixed operations}        │
                                                   │ loopback only                        │
                                                   │   van-stagehand      127.0.0.1:9140  │
                                                   │   van-browser-harness 127.0.0.1:9141 │
                                                   │   Harness-owned Chromium (CDP local) │
                                                   └───────────────┬─────────────────────┘
                                                                   │ HTTPS egress (allowlist)
                                                                   ▼
                                                     api.anthropic.com, task domains
```

| Component | Unit | Interface | Notes |
|---|---|---|---|
| Browser Harness 0.1.13 + Harness-owned Chromium | `van-browser-harness.service` | 127.0.0.1:9141 | the single executor for browser actuation |
| Stagehand 4.1.0 semantic worker | `van-stagehand.service` | 127.0.0.1:9140 | observe/extract proposals; `/agent` refused; `/act` 404 unless development-only, and never exposed across zones |
| mTLS edge (Caddy) | `van-browser-core-edge.service` | `VAN_BROWSER_CORE_EDGE_BIND`:9443 | the only cross-zone listener; zone-private CA; one caller (van-gateway) |

Stagehand 4.1.0 is the released artifact: upstream release commit
`cd7b230778cf92269e4cb90e80d97f5113781c51`, npm integrity
`sha512-PJikMBVoaCRh6TFD7GcmeISmsMq4IwUu1BD5FOsGUVDUxrVqZomWa6W6dF+a/zu4xRZu2Z2xX1nXVMDaCuZWsw==`.
`bootstrap.sh` refuses any other version or integrity. (`ad2bf12e…` is later unreleased
upstream work and is not 4.1.0.)

`/health.runtime_version` is read from the installed `@browserbasehq/stagehand`
`package.json` (`runtime_version_source: installed-package-metadata`), never a constant, so a
different installed artifact fails the gateway placement gate and `qualify.sh`.

Model: `anthropic/claude-sonnet-5` (§4), pinned in `runtime.env.example`; the worker refuses
a request naming another model. The credential is the file-backed
`secretref://browser/stagehand-model` under `VAN_BROWSER_SECRET_ROOT`, never a repository file.

## What this zone does not hold

No direct authority over, and no credential, path, socket or env name for: VATI Risk
Authority, Execution Router, broker credentials, trading secrets, the Owner Model database,
owner-private Hindsight, owner-private OpenViking, or Project Truth mutation.
`tests/contracts/test_van_browser_core_zone.py` fails the build if any unit/env/config file
here references one, derived from the real names in the repository.

## Install

```bash
sudo VAN_BROWSER_CORE_EDGE_BIND=<private overlay IP> bash deploy/van-browser-core/bootstrap.sh --dry-run
sudo VAN_BROWSER_CORE_EDGE_BIND=<private overlay IP> bash deploy/van-browser-core/pki/make-browser-core-pki.sh --with-foreign-test-cert
sudo VAN_BROWSER_CORE_EDGE_BIND=<private overlay IP> bash deploy/van-browser-core/bootstrap.sh
sudo bash deploy/van-browser-core/qualify.sh      # JSON; exit 0 only when every required check is GREEN
```

Then move `client-van-gateway…{crt,key}` and `ca.crt` to the gateway host and set
`VAN_BROWSER_CORE_CA_FILE`, `VAN_BROWSER_CORE_CLIENT_CERT_FILE`,
`VAN_BROWSER_CORE_CLIENT_KEY_FILE`, `VAN_BROWSER_STAGEHAND_ZONE=van-browser-core` and
`VAN_BROWSER_STAGEHAND_BASE_URL=https://<edge>:9443/stagehand`.

## The historical placement

`deploy/van-trading-core/browser/**` and `vati-{stagehand,browser-harness}.service` are the
historical packaging. They are kept for **development only**: the bootstrap refuses without
`VAN_BROWSER_HISTORICAL_DEV_ONLY=1` (and with `VAN_ENV=production`), the units refuse to
start without it, the Stagehand worker refuses any zone other than `van-browser-core`
without it, and the gateway placement gate refuses `van-trading-core` by name regardless.
