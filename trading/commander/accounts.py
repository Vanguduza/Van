"""Account onboarding commands for the commander (Rev 5 Part B, owner-directed: accounts are
configured from the Van app, not the CLI).

Every command here writes only two places on van-trading-core: the non-secret account
registry and the alias' 0600 secrets file. Secrets arrive over the commander's signed
channel, are written with `os.open(..., 0o600)`, and are never echoed back, logged or
audited by value. Broker network calls (Deriv account opening, cTrader discovery,
connectivity verification) run here on the VM because the VM is the host with venue
egress; they are injectable for tests."""

from __future__ import annotations

import json
import os
import re
import secrets as pysecrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import HTTPException

ALIAS_RE = re.compile(r"^[a-z0-9_]{3,32}$")
BROKER_SECRET_KEYS = {
    "DERIV": {"DERIV_API_TOKEN", "DERIV_APP_ID"},
    "CTRADER": {"CTRADER_CLIENT_ID", "CTRADER_CLIENT_SECRET", "CTRADER_ACCESS_TOKEN", "CTRADER_REFRESH_TOKEN"},
    "MT5_EA": {"BRIDGE_SIGNING_KEY"},
    "MT5": {"BRIDGE_SIGNING_KEY", "BRIDGE_CA_FILE", "BRIDGE_CLIENT_CERT", "BRIDGE_CLIENT_KEY"},
    "PAPER": set(), "ZSE_OWNER_TICKET": set(),
}
ACCOUNT_COMMANDS = ("account_upsert", "account_credentials", "account_remove", "account_verify", "deriv_verify_email", "deriv_create_demo", "deriv_oauth_link", "ctrader_discover", "ctrader_oauth_exchange", "ctrader_link", "mt5_ea_issue_key")
ACCOUNT_TOOL_SCHEMAS = {
    "account_upsert": {"description": "Create or replace a non-secret account record (alias, broker, mode, currency, identifiers). Credentials go through account_credentials.", "properties": {"alias": {"type": "string"}, "broker": {"type": "string"}, "mode": {"type": "string"}, "currency": {"type": "string"}, "label": {"type": "string"}, "server": {"type": "string"}, "login": {"type": "string"}, "bridge_url": {"type": "string"}, "demo": {"type": "boolean"}}, "required": ["alias", "broker"]},
    "account_credentials": {"description": "Store credential values for an alias in its 0600 secrets file (allowlisted keys per broker). Values are never echoed.", "properties": {"alias": {"type": "string"}, "secrets": {"type": "object"}}, "required": ["alias", "secrets"]},
    "account_remove": {"description": "Remove an account record and shred its secrets file.", "properties": {"alias": {"type": "string"}}, "required": ["alias"]},
    "account_verify": {"description": "Connect to the venue with the stored credentials and report equity/currency/connectivity. No order is placed.", "properties": {"alias": {"type": "string"}}, "required": ["alias"]},
    "deriv_verify_email": {"description": "Start Deriv account opening: send the verification email.", "properties": {"email": {"type": "string"}, "app_id": {"type": "string"}}, "required": ["email"]},
    "deriv_create_demo": {"description": "Create a Deriv virtual (demo) account from the emailed code and register it under an alias.", "properties": {"alias": {"type": "string"}, "email": {"type": "string"}, "verification_code": {"type": "string"}, "client_password": {"type": "string"}, "residence": {"type": "string"}, "app_id": {"type": "string"}}, "required": ["alias", "verification_code", "client_password", "residence"]},
    "deriv_oauth_link": {"description": "Register a Deriv account from the OAuth redirect tokens (loginid → token).", "properties": {"alias": {"type": "string"}, "loginid": {"type": "string"}, "token": {"type": "string"}, "currency": {"type": "string"}, "app_id": {"type": "string"}, "label": {"type": "string"}}, "required": ["alias", "loginid", "token"]},
    "ctrader_discover": {"description": "List cTrader accounts reachable with an access token (demo and live).", "properties": {"client_id": {"type": "string"}, "client_secret": {"type": "string"}, "access_token": {"type": "string"}}, "required": ["client_id", "client_secret", "access_token"]},
    "ctrader_oauth_exchange": {"description": "Exchange a cTrader OAuth code for tokens.", "properties": {"client_id": {"type": "string"}, "client_secret": {"type": "string"}, "code": {"type": "string"}, "redirect_uri": {"type": "string"}}, "required": ["client_id", "client_secret", "code", "redirect_uri"]},
    "ctrader_link": {"description": "Register a cTrader account (ctid) with its application credentials and tokens.", "properties": {"alias": {"type": "string"}, "client_id": {"type": "string"}, "client_secret": {"type": "string"}, "access_token": {"type": "string"}, "refresh_token": {"type": "string"}, "ctid_trader_account_id": {"type": "integer"}, "is_live": {"type": "boolean"}, "label": {"type": "string"}, "currency": {"type": "string"}}, "required": ["alias", "client_id", "client_secret", "access_token", "ctid_trader_account_id"]},
    "mt5_ea_issue_key": {"description": "Register an MT5 account served by VanBridgeEA and issue its signing key (returned once, for the EA inputs).", "properties": {"alias": {"type": "string"}, "login": {"type": "string"}, "server": {"type": "string"}, "label": {"type": "string"}, "currency": {"type": "string"}, "demo": {"type": "boolean"}}, "required": ["alias", "login", "server"]},
}


@dataclass
class AccountControlSettings:
    registry_path: str
    secrets_dir: str
    deriv_connector: Optional[Callable[[str], Any]] = None                          # url → socket-like (tests); None = real websockets
    ctrader_transport_factory: Optional[Callable[[bool], Any]] = None               # is_live → CtraderTransport
    ctrader_http: Optional[Callable[[str, dict], dict]] = None
    verify_timeout_s: float = 20.0


def _secrets_path(st: AccountControlSettings, alias: str) -> Path:
    return Path(st.secrets_dir) / f"{alias}.env"


def _write_secrets(path: Path, values: dict[str, str], *, merge: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    existing: dict[str, str] = {}
    if merge and path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1); existing[k.strip()] = v.strip()
    existing.update({k: str(v) for k, v in values.items()})
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for k, v in existing.items():
            f.write(f"{k}={v}\n")
    os.chmod(path, 0o600)


def _shred(path: Path) -> None:
    if path.is_file():
        size = path.stat().st_size
        with open(path, "r+b") as f:
            f.write(os.urandom(size)); f.flush(); os.fsync(f.fileno())
        path.unlink()


def _alias(a: dict) -> str:
    alias = str(a.get("alias", "")).strip().lower()
    if not ALIAS_RE.match(alias):
        raise HTTPException(422, "alias must match [a-z0-9_]{3,32}")
    return alias


def build_account_handlers(st: AccountControlSettings) -> dict[str, Callable[[dict], dict]]:
    from vati.accounts import Account, AccountRegistry, AccountRegistryError, CredentialRef

    def reg() -> AccountRegistry:
        return AccountRegistry(st.registry_path)

    def upsert_record(alias: str, broker: str, *, mode: str = "DEMO_TRADER", currency: str = "USD", label: str = "", server: str = "", login: str = "", bridge_url: str = "", demo: bool = True, mandate_ref: str = "") -> dict:
        r = reg()
        if alias in r.accounts:
            r.remove(alias)
        sec = _secrets_path(st, alias)
        if broker in ("DERIV", "CTRADER", "MT5_EA", "MT5"):
            if not sec.is_file():
                _write_secrets(sec, {})
            cref = CredentialRef(secrets_file=str(sec))
        else:
            cref = CredentialRef()
        try:
            acc = r.add(Account(alias=alias, broker=broker, mode=mode, currency=currency, label=label or alias, server=server, login=login, bridge_url=bridge_url, credential_ref=cref, demo=demo, mandate_ref=mandate_ref))
        except AccountRegistryError as exc:
            raise HTTPException(422, str(exc))
        return acc.public()

    def store_secrets(alias: str, broker: str, values: dict[str, Any]) -> list[str]:
        allowed = BROKER_SECRET_KEYS.get(broker, set())
        bad = [k for k in values if k not in allowed]
        if bad:
            raise HTTPException(422, f"keys not allowed for {broker}: {sorted(bad)}")
        clean = {k: str(v).strip() for k, v in values.items() if str(v).strip()}
        if any("\n" in v for v in clean.values()):
            raise HTTPException(422, "secret values must be single-line")
        _write_secrets(_secrets_path(st, alias), clean)
        return sorted(clean)

    # ------------------------------------------------------------ generic
    def cmd_account_upsert(a: dict) -> dict:
        alias = _alias(a)
        broker = str(a.get("broker", "")).upper()
        if broker not in BROKER_SECRET_KEYS:
            raise HTTPException(422, f"broker must be one of {sorted(BROKER_SECRET_KEYS)}")
        pub = upsert_record(alias, broker, mode=str(a.get("mode", "DEMO_TRADER")), currency=str(a.get("currency", "USD")).upper(), label=str(a.get("label", "")), server=str(a.get("server", "")), login=str(a.get("login", "")),
                            bridge_url=str(a.get("bridge_url", "")), demo=bool(a.get("demo", True)), mandate_ref=str(a.get("mandate_ref", "")))
        return {"account": pub, "secrets_file": str(_secrets_path(st, alias)) if broker in ("DERIV", "CTRADER", "MT5_EA", "MT5") else None}

    def cmd_account_credentials(a: dict) -> dict:
        alias = _alias(a)
        try:
            acc = reg().get(alias)
        except AccountRegistryError as exc:
            raise HTTPException(404, str(exc))
        values = a.get("secrets")
        if not isinstance(values, dict) or not values:
            raise HTTPException(422, "secrets must be a non-empty object")
        keys = store_secrets(alias, acc.broker, values)
        return {"alias": alias, "stored_keys": keys}

    def cmd_account_remove(a: dict) -> dict:
        alias = _alias(a)
        r = reg()
        if alias not in r.accounts:
            raise HTTPException(404, f"unknown alias {alias}")
        r.remove(alias); _shred(_secrets_path(st, alias))
        return {"alias": alias, "removed": True}

    def cmd_account_verify(a: dict) -> dict:
        alias = _alias(a)
        r = reg()
        try:
            acc = r.get(alias)
        except AccountRegistryError as exc:
            raise HTTPException(404, str(exc))
        if acc.broker == "MT5_EA":
            from vati.execution.mt5_pull import BridgeQueue, Mt5PullAdapter
            q = BridgeQueue(os.environ.get("VAN_MT5_PULL_QUEUE", ":memory:"))
            hb = Mt5PullAdapter(q, account_alias=alias).heartbeat(now_ms=int(time.time() * 1000))
            return {"alias": alias, "ok": hb.connected, "detail": "EA is polling" if hb.connected else "EA has not polled in the last 30 s; check BridgeUrl/Alias/SigningKey in the terminal", "safety_identity": acc.safety_identity}
        try:
            from vati.app.service import build_adapter
            adapter = build_adapter(acc, r)
            if st.deriv_connector and acc.broker == "DERIV":
                from vati.execution.transports.deriv_ws import DerivWebSocketTransport
                adapter.transport = DerivWebSocketTransport(app_id=acc.server or "1089", token_provider=lambda: r.credentials(alias).get("DERIV_API_TOKEN", ""), connector=st.deriv_connector)
            if st.ctrader_transport_factory and acc.broker == "CTRADER":
                adapter.transport = st.ctrader_transport_factory(not acc.demo)
            state = adapter.sync_account()
            hb = adapter.heartbeat(now_ms=int(time.time() * 1000))
            return {"alias": alias, "ok": bool(state.verified and hb.connected), "equity": str(state.equity), "balance": str(state.balance), "currency": state.currency, "verified": state.verified, "connected": hb.connected, "safety_identity": acc.safety_identity}
        except Exception as exc:  # noqa: BLE001 — verification must report, not crash
            return {"alias": alias, "ok": False, "detail": str(exc)[:300], "safety_identity": acc.safety_identity}

    # ------------------------------------------------------------ deriv
    def deriv_transport(app_id: str):
        from vati.execution.transports.deriv_ws import DerivWebSocketTransport
        return DerivWebSocketTransport(app_id=app_id, token_provider=lambda: "", connector=st.deriv_connector)

    def cmd_deriv_verify_email(a: dict) -> dict:
        email = str(a.get("email", "")).strip()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            raise HTTPException(422, "valid email required")
        t = deriv_transport(str(a.get("app_id") or "1089"))
        r = t({"verify_email": email, "type": "account_opening"})
        if r.get("error"):
            raise HTTPException(502, f"Deriv: {r['error']}")
        return {"sent": bool(r.get("verify_email")), "email": email}

    def cmd_deriv_create_demo(a: dict) -> dict:
        alias = _alias(a)
        app_id = str(a.get("app_id") or "1089")
        t = deriv_transport(app_id)
        r = t({"new_account_virtual": 1, "verification_code": str(a["verification_code"]).strip(), "client_password": str(a["client_password"]), "residence": str(a["residence"]).lower(), "type": "trading"})
        if r.get("error"):
            raise HTTPException(502, f"Deriv: {r['error']}")
        nav = r.get("new_account_virtual", {})
        token = nav.get("oauth_token")
        if not token:
            raise HTTPException(502, "Deriv did not return an account token")
        pub = upsert_record(alias, "DERIV", currency=str(nav.get("currency", "USD")), label=str(a.get("label") or f"Deriv demo {nav.get('client_id', '')}"), server=app_id, login=str(nav.get("client_id", "")), demo=True)
        store_secrets(alias, "DERIV", {"DERIV_API_TOKEN": token, "DERIV_APP_ID": app_id})
        return {"account": pub, "client_id": nav.get("client_id"), "currency": nav.get("currency"), "note": "virtual account created; token stored on van-trading-core"}

    def cmd_deriv_oauth_link(a: dict) -> dict:
        alias = _alias(a)
        loginid = str(a.get("loginid", "")).strip().upper()
        token = str(a.get("token", "")).strip()
        if not loginid or not token:
            raise HTTPException(422, "loginid and token required")
        demo = loginid.startswith("VR")
        pub = upsert_record(alias, "DERIV", currency=str(a.get("currency") or "USD").upper(), label=str(a.get("label") or f"Deriv {loginid}"), server=str(a.get("app_id") or "1089"), login=loginid, demo=demo, mode="DEMO_TRADER" if demo else "OBSERVE")
        store_secrets(alias, "DERIV", {"DERIV_API_TOKEN": token, "DERIV_APP_ID": str(a.get("app_id") or "1089")})
        return {"account": pub}

    # ------------------------------------------------------------ ctrader
    def ctrader_transport(is_live: bool):
        if st.ctrader_transport_factory:
            return st.ctrader_transport_factory(is_live)
        from vati.execution.ctrader import DEMO_HOST, LIVE_HOST, CtraderTransport
        return CtraderTransport(host=LIVE_HOST if is_live else DEMO_HOST)

    def cmd_ctrader_discover(a: dict) -> dict:
        from vati.execution.ctrader import CtraderApiError, CtraderError, discover_accounts
        found = []
        errors = []
        for is_live in (False, True):
            t = ctrader_transport(is_live)
            try:
                for acc in discover_accounts(t, client_id=str(a["client_id"]), client_secret=str(a["client_secret"]), access_token=str(a["access_token"])):
                    found.append({**acc, "environment": "live" if is_live else "demo"})
            except (CtraderApiError, CtraderError) as exc:
                errors.append(f"{'live' if is_live else 'demo'}: {exc}")
            finally:
                try:
                    t.close()
                except Exception:  # noqa: BLE001
                    pass
        seen = {}
        for f in found:
            seen.setdefault(f["ctid_trader_account_id"], f)
        if not seen and errors:
            raise HTTPException(502, "; ".join(errors)[:300])
        return {"accounts": list(seen.values()), "errors": errors}

    def cmd_ctrader_oauth_exchange(a: dict) -> dict:
        from vati.execution.ctrader import exchange_code
        try:
            tok = exchange_code(str(a["client_id"]), str(a["client_secret"]), str(a["code"]), str(a["redirect_uri"]), http=st.ctrader_http)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"cTrader token exchange failed: {str(exc)[:200]}")
        return tok

    def cmd_ctrader_link(a: dict) -> dict:
        alias = _alias(a)
        ctid = int(a["ctid_trader_account_id"])
        is_live = bool(a.get("is_live", False))
        pub = upsert_record(alias, "CTRADER", currency=str(a.get("currency") or "USD").upper(), label=str(a.get("label") or f"cTrader {ctid}"), server="live" if is_live else "demo", login=str(ctid), demo=not is_live, mode="DEMO_TRADER" if not is_live else "OBSERVE")
        store_secrets(alias, "CTRADER", {"CTRADER_CLIENT_ID": a["client_id"], "CTRADER_CLIENT_SECRET": a["client_secret"], "CTRADER_ACCESS_TOKEN": a["access_token"], **({"CTRADER_REFRESH_TOKEN": a["refresh_token"]} if a.get("refresh_token") else {})})
        return {"account": pub}

    # ------------------------------------------------------------ mt5 ea
    def cmd_mt5_ea_issue_key(a: dict) -> dict:
        alias = _alias(a)
        key = pysecrets.token_hex(32)
        pub = upsert_record(alias, "MT5_EA", currency=str(a.get("currency") or "USD").upper(), label=str(a.get("label") or f"MT5 {a.get('login')}"), server=str(a.get("server", "")), login=str(a.get("login", "")), demo=bool(a.get("demo", True)))
        store_secrets(alias, "MT5_EA", {"BRIDGE_SIGNING_KEY": key})
        return {"account": pub, "signing_key": key, "ea_inputs": {"Alias": alias, "SigningKey": key, "BridgeUrl": os.environ.get("VAN_PUBLIC_HOST", "") and f"https://{os.environ['VAN_PUBLIC_HOST']}"}, "note": "shown once; paste into VanBridgeEA inputs"}

    return {"account_upsert": cmd_account_upsert, "account_credentials": cmd_account_credentials, "account_remove": cmd_account_remove, "account_verify": cmd_account_verify,
            "deriv_verify_email": cmd_deriv_verify_email, "deriv_create_demo": cmd_deriv_create_demo, "deriv_oauth_link": cmd_deriv_oauth_link, "ctrader_discover": cmd_ctrader_discover,
            "ctrader_oauth_exchange": cmd_ctrader_oauth_exchange, "ctrader_link": cmd_ctrader_link, "mt5_ea_issue_key": cmd_mt5_ea_issue_key}


SECRET_ARG_KEYS = {"secrets", "client_password", "token", "access_token", "refresh_token", "client_secret", "verification_code", "code"}


def redact_args(args: dict) -> dict:
    return {k: ("[REDACTED]" if k in SECRET_ARG_KEYS else v) for k, v in args.items()}
