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
