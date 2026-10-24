# VanBridgeEA — Windows-free MT5 through a pull-bridge Expert Advisor

The EA runs inside any MT5 terminal that can stay online — a MetaQuotes VPS (migrated from a terminal), a broker
VPS, or a desktop — and pulls signed commands from `van-trading-core`. The trading VM never holds the MT5 login or
password; the terminal does. The EA never decides size, never opens without a stop loss, never widens a stop, and
flattens an entry whose stop the server did not confirm.

## Setup

1. Register the account in the Van app (Accounts → Add → *MT5 via Expert Advisor*). The app issues the alias and a
   32-character signing key; the key is stored on van-trading-core behind the alias' credential reference.
2. In MT5: Tools ▸ Options ▸ Expert Advisors ▸ enable **Allow WebRequest for listed URL** and add the bridge URL
   (`https://<public-host>`), and enable **Allow algorithmic trading**.
3. Compile `VanBridgeEA.mq5` in MetaEditor (Windows, macOS or MT5-under-Wine; the MT5 mobile apps cannot compile or
   run EAs), attach it to any chart, fill `BridgeUrl`, `Alias`, `SigningKey`.
4. Optional: Tools ▸ Virtual Hosting to migrate the terminal, with the EA, to a MetaQuotes VPS so the desktop can go
   offline. A broker VPS works the same way.
5. On the VM the pull endpoint must carry a **publicly trusted** certificate: MT5's `WebRequest` validates TLS
   against the system store and will not accept the private bridge CA. `bootstrap.sh --public-host <dns-name>`
   installs Caddy with automatic Let's Encrypt in front of `vati-mt5-pull` (port 443 → 127.0.0.1:9443).

## Honest constraints

- Deploying the EA needs a terminal once (MetaEditor to compile, a chart to attach). Route 1 (cTrader) needs nothing
  of the kind.
- Latency is the poll interval (1 s) plus broker execution; fine for the SWING/POSITION/SESSION horizons VATI trades,
  not for scalping, which the Risk Authority already gates on cost.
- Signature-only trust on this seam (no client certificate): keep the signing key in the EA inputs on the VPS and
  rotate it from the app if the VPS is ever shared.

## Physical account binding

Production factory connections require the registered numeric login, exact server, account currency and demo/live identity. The EA reports these on every signed poll. The registered poll provider rechecks identity, key and entry permission under the same locks as account writers before claiming queued commands. An undelivered command with a changed identity or disabled entry profile is refused with zero effect; a previously taken command retains its uncertainty.

Bound commands have 17 pipe-separated fields: the original 12 fields, explicit order type, numeric login, UTF-8 hex server name, UTF-8 hex currency and a boolean demo label. The EA checks the current native account against these fields before every operation. The order type comes from its explicit field. Server names containing Unicode or pipe characters remain unambiguous. Historical original-result reads do not supply a fresh account or position snapshot.

Update core and EA together; an older EA without native identity fields cannot satisfy production admission. Native MetaEditor compilation and terminal acceptance are still required for this source change. Native monetary finality, precision, full deadline/epoch enforcement and the other original execution requirements remain separate obligations.
