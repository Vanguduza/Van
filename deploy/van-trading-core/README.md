# van-trading-core — deployment package

Target: the dedicated OCI VM (`VM.Standard.A1.Flex`, 2 OCPU / 12 GB, Ubuntu 24.04 **ARM64**, private IP
`10.0.1.233`, subnet `10.0.1.0/24`, SSH + control port `9133` admitted only from `10.0.0.0/16`).

```text
dial-hermes-control (10.0.0.184)                 van-trading-core (10.0.1.233)                    Windows MT5 worker
  Hermes profile van                              vati-commander  :9133  (HTTPS, HMAC, typed)       mt5_bridge_worker :9443
   └─ mcp_servers.van_trading_commander  ───────► vati-vekl       :9134  (loopback, trading VEKL)    (mTLS server + HMAC)
      (stdio shim → signed HTTPS)                 vati-session@<alias>   (DecisionCycle per account)         ▲
                                                  vati-supabase          (PostgreSQL authority store)        │ mTLS client cert
                                                  Deriv WebSocket ────► ws.derivws.com                       │
                                                  MT5 bridge client ─────────────────────────────────────────┘
```

| Component | Unit | Port | Notes |
|---|---|---|---|
| Commander (Hermes subordinate) | `vati-commander.service` | 9133/tcp, TLS | `trading/commander`; typed commands only; owner-signed halt |
| Trading VEKL | `vati-vekl.service` | 127.0.0.1:9134 | `trading/vekl`; DIAL resolver vendored with provenance |
| Trading sessions | `vati-session@<alias>.service` | — | `python -m vati serve --config config/sessions/<alias>.json` |
| Supabase (PostgreSQL 17, studio, auth, rest, realtime, storage) | `vati-supabase.service` | loopback only | donor compose pinned in `supabase/DONOR_PROVENANCE.json`; secrets generated, never the demo keys |
| Ledger schema | `supabase/init/01_vati_ledger.sql.tpl` | — | append-only `vati.events`; role `vati` cannot UPDATE/DELETE events |
| Bridge PKI | `pki/make-bridge-pki.sh` | — | private CA; commander TLS cert; MT5 worker server cert; vati-core client cert |
| MT5 (no Windows) | `vati-mt5-pull.service` + `mql5/VanBridgeEA.mq5` | 127.0.0.1:9443 behind Caddy :443 (`--public-host`) | pull bridge: the EA on a MetaQuotes/broker VPS polls signed commands |
| cTrader | in-process adapter | outbound 5035/tcp | Linux-native Open API, no terminal |
| MT5 (Windows worker, optional) | `windows/mt5_worker` | 9443/tcp on a Windows host | only if a Windows host exists; not required |
| NautilusTrader | `--with-nautilus` | — | `nautilus_trader==1.231.0` (aarch64 wheel, Python 3.12) installed only at the Phase 3 donor gate |

## Run

```bash
sudo bash deploy/van-trading-core/bootstrap.sh --dry-run        # inspect the plan
sudo bash deploy/van-trading-core/bootstrap.sh                  # idempotent install
sudo bash deploy/van-trading-core/qualify.sh                    # JSON report; exit 0 only when every required check is GREEN
```

Then on `dial-hermes-control`:

```bash
scp van-trading-core:/opt/van-trading/secrets/commander.token ~/.van/commander.token && chmod 600 ~/.van/commander.token
scp van-trading-core:/opt/van-trading/secrets/pki/ca.crt ~/.van/van-trading-bridge-ca.crt
bash deploy/van-trading-core/hermes/register-commander-mcp.sh --dry-run && bash deploy/van-trading-core/hermes/register-commander-mcp.sh
```

## Plugging in an account

From the Van app (Accounts → + Add account). The CLI below remains for recovery only.

### Recovery CLI

```bash
# secrets never enter the registry: one 0600 file per alias
sudo -u vati install -m 0600 /dev/null /opt/van-trading/secrets/deriv_demo.env
echo 'DERIV_API_TOKEN=<token>' | sudo -u vati tee /opt/van-trading/secrets/deriv_demo.env >/dev/null
sudo -u vati /opt/van-trading/venv/bin/python -m vati accounts add --registry /opt/van-trading/config/accounts.json \
    --alias deriv_demo --broker DERIV --server <deriv-app-id> --secrets-file /opt/van-trading/secrets/deriv_demo.env
sudo -u vati /opt/van-trading/venv/bin/python -m vati accounts verify --registry /opt/van-trading/config/accounts.json --alias deriv_demo
# MT5: --broker MT5 --bridge-url https://<worker>:9443 --secrets-file <alias>.env containing BRIDGE_SIGNING_KEY, BRIDGE_CA_FILE, BRIDGE_CLIENT_CERT, BRIDGE_CLIENT_KEY
```

A session file (`config/sessions/<alias>.json`) names the account alias, symbol, timeframe, contract, mandate
and capsules; `systemctl enable --now vati-session@<alias>` starts it. A live mandate on a demo account, or
the reverse, refuses to start (safety identity mismatch).

## What is verified in the repository (no VM needed)

- `bash bootstrap.sh --dry-run` prints the full plan; every script passes `bash -n`.
- `supabase/generate-env.sh` replaces every demo secret and mints anon/service JWTs (tested).
- `pki/make-bridge-pki.sh` issues a CA and three leaf certificates with the right SANs (tested).
- `hermes/register-commander-mcp.sh` splices one block into a commented YAML, is idempotent and backs up (tested).
- `windows/mt5_worker/mt5_bridge_worker.py` is exercised on Linux with a fake terminal, and end to end over
  mTLS + HMAC from the Linux transport (`trading/tests/test_mt5_worker.py`).
- The PostgreSQL ledger is tested on a real PostgreSQL 16 (`trading/tests/test_infra_live.py`).

## What only the VM can verify

Package installation on arm64, Supabase image pulls, systemd activation, ufw, and the commander over the
private VCN. `qualify.sh` is the acceptance instrument for those; its JSON belongs in the implementation ledger.
