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
import tempfile
from dataclasses import dataclass, field, replace
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import HTTPException
from commander.account_effects import (AccountEffectError, AccountEffectJournal, AccountOperationUnconfirmed,
    AccountOperationBlocked, JOURNALED_COMMANDS, invoke_account_effect, mark_account_effect, operation_intent, readback)

ALIAS_RE = re.compile(r"^[a-z0-9_]{3,32}$")
BROKER_SECRET_KEYS = {
    "DERIV": {"DERIV_API_TOKEN", "DERIV_APP_ID"},
    "CTRADER": {"CTRADER_CLIENT_ID", "CTRADER_CLIENT_SECRET", "CTRADER_ACCESS_TOKEN", "CTRADER_REFRESH_TOKEN"},
    "MT5_EA": {"BRIDGE_SIGNING_KEY"},
    "MT5": {"BRIDGE_SIGNING_KEY", "BRIDGE_CA_FILE", "BRIDGE_CLIENT_CERT", "BRIDGE_CLIENT_KEY"},
    "PAPER": set(), "ZSE_OWNER_TICKET": set(),
}
ACCOUNT_MUTATIONS = frozenset({"account_upsert", "account_credentials", "account_remove",
    "deriv_create_demo", "deriv_oauth_link", "ctrader_link", "mt5_ea_issue_key"})
ACCOUNT_COMMANDS = ("account_upsert", "account_credentials", "account_remove", "account_verify", "account_revision", "account_operation", "deriv_verify_email", "deriv_create_demo", "deriv_oauth_link", "ctrader_discover", "ctrader_oauth_exchange", "ctrader_link", "mt5_ea_issue_key")
ACCOUNT_TOOL_SCHEMAS = {
    "account_operation": {"description": "Read the original native account-operation outcome for its gateway-authenticated owner device. No effect or credential export.", "properties": {"operation_id": {"type": "string"}, "device_id": {"type": "string"}}, "required": ["operation_id", "device_id"]},
    "account_revision": {"description": "Read the native non-secret account configuration version for exact owner-intent binding.", "properties": {"alias": {"type": "string"}}, "required": ["alias"]},
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
    operation_ledger: str = ""  # Actual constructors bind the existing native VATI ledger.


def _secrets_path(st: AccountControlSettings, alias: str) -> Path:
    return Path(st.secrets_dir) / f"{alias}.env"


def _write_secrets(path: Path, values: dict[str, str], *, merge: bool = True) -> None:
    from vati.core.file_lock import exclusive_state_lock
    from vati.accounts.registry import load_secret_file

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(not isinstance(k, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", k)
           or not isinstance(v, str) or "\n" in v or "\r" in v for k, v in values.items()):
        raise ValueError("credential file requires valid keys and single-line text values")
    with exclusive_state_lock(path):
        if path.is_symlink():
            raise ValueError("credential destination must not be a symbolic link")
        # Validate old ownership/permissions even when replacing, before reading or changing it.
        old = load_secret_file(str(path)) if path.exists() else {}
        existing = old if merge else {}
        existing.update(values)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                for key, value in existing.items():
                    stream.write(f"{key}={value}\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def _shred(path: Path) -> None:
    from vati.core.file_lock import exclusive_state_lock
    with exclusive_state_lock(path):
        if path.is_symlink():
            raise ValueError("credential destination must not be a symbolic link")
        if path.is_file():
            size = path.stat().st_size
            with open(path, "r+b") as stream:
                stream.write(os.urandom(size))
                stream.flush()
                os.fsync(stream.fileno())
            path.unlink()


def _alias(a: dict) -> str:
    alias = str(a.get("alias", "")).strip().lower()
    if not ALIAS_RE.match(alias):
        raise HTTPException(422, "alias must match [a-z0-9_]{3,32}")
    return alias


def require_resource_version(command: str, args: dict) -> None:
    """Required on actual gateway/Commander ingress; direct handlers are native code."""
    if command not in ACCOUNT_MUTATIONS:
        return
    _alias(args)
    expected = args.get("_expected_resource_version")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise HTTPException(409, "native account resource version is required before mutation")
    if command in JOURNALED_COMMANDS:
        try:
            operation_intent(command, args)
        except AccountEffectError as exc:
            raise HTTPException(409, str(exc)) from None


def _boolean(args: dict, name: str, default: bool) -> bool:
    value = args.get(name, default)
    if type(value) is not bool:
        raise HTTPException(422, f"{name} must be a JSON boolean")
    return value


def build_account_handlers(st: AccountControlSettings) -> dict[str, Callable[[dict], dict]]:
    from vati.accounts import Account, AccountRegistry, AccountRegistryError, CredentialRef

    def reg() -> AccountRegistry:
        return AccountRegistry(st.registry_path)

    def upsert_record(alias: str, broker: str, *, mode: str = "DEMO_TRADER", currency: str = "USD", label: str = "", server: str = "", login: str = "", bridge_url: str = "", demo: bool = True, mandate_ref: str = "") -> dict:
        r = reg()
        sec = _secrets_path(st, alias)
        if broker in ("DERIV", "CTRADER", "MT5_EA", "MT5"):
            if not sec.is_file():
                mark_account_effect()
                _write_secrets(sec, {})
            cref = CredentialRef(secrets_file=str(sec))
        else:
            cref = CredentialRef()
        try:
            candidate = Account(alias=alias, broker=broker, mode=mode, currency=currency, label=label or alias, server=server, login=login, bridge_url=bridge_url, credential_ref=cref, demo=demo, mandate_ref=mandate_ref)
            candidate.validate()
            mark_account_effect()
            acc = r.replace(candidate) if alias in r.accounts else r.add(candidate)
        except AccountRegistryError as exc:
            raise HTTPException(422, str(exc))
        return acc.public()

    def clean_secrets(broker: str, values: dict[str, Any]) -> dict[str, str]:
        allowed = BROKER_SECRET_KEYS.get(broker, set())
        bad = [k for k in values if k not in allowed]
        if bad:
            raise HTTPException(422, f"keys not allowed for {broker}: {sorted(bad)}")
        clean = {k: str(v).strip() for k, v in values.items() if str(v).strip()}
        if any("\n" in v or "\r" in v for v in clean.values()):
            raise HTTPException(422, "secret values must be single-line")
        return clean

    def store_secrets(alias: str, broker: str, values: dict[str, Any]) -> list[str]:
        clean = clean_secrets(broker, values)
        mark_account_effect()
        reg().touch(alias)
        _write_secrets(_secrets_path(st, alias), clean)
        return sorted(clean)

    def verify_deriv_material(*, app_id: str, token: str, login: str, currency: str,
                              demo: bool | None, require_trade: bool, endpoint: str = "") -> dict:
        from vati.execution.deriv_identity import DerivIdentity, DerivIdentityError
        from vati.execution.transports.deriv_ws import DerivWebSocketTransport
        transport = DerivWebSocketTransport(app_id=app_id, token_provider=lambda: token,
            endpoint=endpoint or "wss://ws.derivws.com/websockets/v3",
            timeout_s=st.verify_timeout_s, connector=st.deriv_connector)
        try:
            response = transport({"authorize": "<token-from-vault-never-in-prompt>"})
            profile = response.get("authorize", {})
            virtual = profile.get("is_virtual")
            if type(virtual) is not int or virtual not in (0, 1):
                raise DerivIdentityError("Deriv native demo/live identity is unavailable")
            identity = DerivIdentity(login or profile.get("loginid", ""), currency,
                                     bool(virtual) if demo is None else demo, require_trade)
            identity.validate(profile)
            return profile
        except Exception:
            # An authorization read has no money effect. Do not include a raw
            # broker exception or echo_req: either can contain credential data.
            raise HTTPException(409, "Deriv credential or native account identity could not be verified; previous connection retained") from None
        finally:
            transport.close()

    def require_new_alias(alias: str) -> None:
        if alias in reg().accounts:
            raise HTTPException(409, "account alias already exists; use the approved account update flow")

    # ------------------------------------------------------------ generic
    def cmd_account_revision(a: dict) -> dict:
        from vati.accounts.resource_version import resource_snapshot
        return resource_snapshot(reg(), _alias(a))

    def open_operation_ledger():
        from vati.core.ledger_pg import open_ledger
        if not st.operation_ledger:
            raise HTTPException(503, "native VATI operation ledger is not configured; no effect dispatched")
        return open_ledger(st.operation_ledger)

    def cmd_account_operation(a: dict) -> dict:
        led = open_operation_ledger()
        try:
            state = AccountEffectJournal(led).status(a.get("operation_id"), a.get("device_id"))
            if state is None:
                # Absence does not prove a lost request can never arrive.
                raise AccountOperationUnconfirmed(a.get("operation_id"))
            return readback(state)
        except AccountEffectError:
            raise HTTPException(409, "native operation cannot be read for this owner device") from None
        finally:
            led.close()

    def cmd_account_upsert(a: dict) -> dict:
        alias = _alias(a)
        broker = str(a.get("broker", "")).upper()
        if broker not in BROKER_SECRET_KEYS:
            raise HTTPException(422, f"broker must be one of {sorted(BROKER_SECRET_KEYS)}")
        pub = upsert_record(alias, broker, mode=str(a.get("mode", "DEMO_TRADER")), currency=str(a.get("currency", "USD")).upper(), label=str(a.get("label", "")), server=str(a.get("server", "")), login=str(a.get("login", "")),
                            bridge_url=str(a.get("bridge_url", "")), demo=_boolean(a, "demo", True), mandate_ref=str(a.get("mandate_ref", "")))
        return {"account": pub, "secrets_file": str(_secrets_path(st, alias)) if broker in ("DERIV", "CTRADER", "MT5_EA", "MT5") else None}

    def cmd_account_credentials(a: dict) -> dict:
        alias = _alias(a)
        registry = reg()
        try:
            acc = registry.get(alias)
        except AccountRegistryError as exc:
            raise HTTPException(404, str(exc))
        values = a.get("secrets")
        if not isinstance(values, dict) or not values:
            raise HTTPException(422, "secrets must be a non-empty object")
        if acc.broker == "DERIV":
            from vati.accounts.access import SENDING_MODES
            clean = clean_secrets(acc.broker, values)
            expected_path = _secrets_path(st, alias).resolve()
            if not acc.credential_ref.secrets_file or Path(acc.credential_ref.secrets_file).resolve() != expected_path:
                raise HTTPException(409, "credential rotation must use the registered credential reference")
            candidate = {**registry.credentials(alias), **clean}
            app_id = acc.server or "1089"
            if candidate.get("DERIV_APP_ID", app_id) != app_id:
                raise HTTPException(409, "credential app ID differs from the registered connection")
            profile = verify_deriv_material(app_id=app_id, token=candidate.get("DERIV_API_TOKEN", ""),
                login=acc.login, currency=acc.currency, demo=acc.demo,
                require_trade=acc.mode in SENDING_MODES, endpoint=acc.bridge_url)
            # Pin an initially unbound account only after native readback. This
            # happens under the account-operation lock, before an entry can run.
            # A failed subsequent file swap leaves an identity whose old token
            # must still pass native verification; it cannot switch principals.
            if not acc.login:
                mark_account_effect()
                registry.replace(replace(acc, login=profile["loginid"]))
        keys = store_secrets(alias, acc.broker, values)
        return {"alias": alias, "stored_keys": keys}

    def cmd_account_remove(a: dict) -> dict:
        alias = _alias(a)
        r = reg()
        if alias not in r.accounts:
            raise HTTPException(404, f"unknown alias {alias}")
        mark_account_effect()
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
            adapter = build_adapter(acc, r, deriv_connector=st.deriv_connector)
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
        require_new_alias(alias)
        app_id = str(a.get("app_id") or "1089")
        t = deriv_transport(app_id)
        r = t({"new_account_virtual": 1, "verification_code": str(a["verification_code"]).strip(), "client_password": str(a["client_password"]), "residence": str(a["residence"]).lower(), "type": "trading"})
        if r.get("error"):
            raise HTTPException(502, f"Deriv: {r['error']}")
        nav = r.get("new_account_virtual", {})
        token = nav.get("oauth_token")
        if not token:
            raise HTTPException(502, "Deriv did not return an account token")
        verify_deriv_material(app_id=app_id, token=token, login=str(nav.get("client_id", "")),
            currency=str(nav.get("currency", "USD")), demo=True, require_trade=True)
        pub = upsert_record(alias, "DERIV", currency=str(nav.get("currency", "USD")), label=str(a.get("label") or f"Deriv demo {nav.get('client_id', '')}"), server=app_id, login=str(nav.get("client_id", "")), demo=True)
        store_secrets(alias, "DERIV", {"DERIV_API_TOKEN": token, "DERIV_APP_ID": app_id})
        return {"account": pub, "client_id": nav.get("client_id"), "currency": nav.get("currency"), "note": "virtual account created; token stored on van-trading-core"}

    def cmd_deriv_oauth_link(a: dict) -> dict:
        alias = _alias(a)
        require_new_alias(alias)
        loginid = str(a.get("loginid", "")).strip().upper()
        token = str(a.get("token", "")).strip()
        if not loginid or not token:
            raise HTTPException(422, "loginid and token required")
        currency = str(a.get("currency") or "USD").upper()
        app_id = str(a.get("app_id") or "1089")
        profile = verify_deriv_material(app_id=app_id, token=token, login=loginid,
            currency=currency, demo=None, require_trade=False)
        demo = bool(profile["is_virtual"])
        mode = "DEMO_TRADER" if demo and "trade" in profile["scopes"] else "OBSERVE"
        pub = upsert_record(alias, "DERIV", currency=currency, label=str(a.get("label") or f"Deriv {loginid}"), server=app_id, login=loginid, demo=demo, mode=mode)
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
        is_live = _boolean(a, "is_live", False)
        pub = upsert_record(alias, "CTRADER", currency=str(a.get("currency") or "USD").upper(), label=str(a.get("label") or f"cTrader {ctid}"), server="live" if is_live else "demo", login=str(ctid), demo=not is_live, mode="DEMO_TRADER" if not is_live else "OBSERVE")
        store_secrets(alias, "CTRADER", {"CTRADER_CLIENT_ID": a["client_id"], "CTRADER_CLIENT_SECRET": a["client_secret"], "CTRADER_ACCESS_TOKEN": a["access_token"], **({"CTRADER_REFRESH_TOKEN": a["refresh_token"]} if a.get("refresh_token") else {})})
        return {"account": pub}

    # ------------------------------------------------------------ mt5 ea
    def cmd_mt5_ea_issue_key(a: dict) -> dict:
        alias = _alias(a)
        key = pysecrets.token_hex(32)
        pub = upsert_record(alias, "MT5_EA", currency=str(a.get("currency") or "USD").upper(), label=str(a.get("label") or f"MT5 {a.get('login')}"), server=str(a.get("server", "")), login=str(a.get("login", "")), demo=_boolean(a, "demo", True))
        store_secrets(alias, "MT5_EA", {"BRIDGE_SIGNING_KEY": key})
        return {"account": pub, "signing_key": key, "ea_inputs": {"Alias": alias, "SigningKey": key, "BridgeUrl": os.environ.get("VAN_PUBLIC_HOST", "") and f"https://{os.environ['VAN_PUBLIC_HOST']}"}, "note": "shown once; paste into VanBridgeEA inputs"}

    handlers = {"account_upsert": cmd_account_upsert, "account_credentials": cmd_account_credentials, "account_remove": cmd_account_remove, "account_verify": cmd_account_verify, "account_revision": cmd_account_revision, "account_operation": cmd_account_operation,
            "deriv_verify_email": cmd_deriv_verify_email, "deriv_create_demo": cmd_deriv_create_demo, "deriv_oauth_link": cmd_deriv_oauth_link, "ctrader_discover": cmd_ctrader_discover,
            "ctrader_oauth_exchange": cmd_ctrader_oauth_exchange, "ctrader_link": cmd_ctrader_link, "mt5_ea_issue_key": cmd_mt5_ea_issue_key}

    def serialize_account_mutation(command, handler):
        @wraps(handler)
        def invoke(args):
            from vati.core.file_lock import exclusive_state_lock
            alias = _alias(args)
            path = Path(st.registry_path).resolve()
            with exclusive_state_lock(path.with_name(path.name + ".operation." + alias)):
                def check_version():
                    if "_expected_resource_version" in args:
                        expected = args["_expected_resource_version"]
                        actual = cmd_account_revision({"alias": alias})["resource_version"]
                        if not isinstance(expected, str) or expected != actual:
                            raise HTTPException(409, "account changed since owner approval; review the current account and approve again")
                if command not in JOURNALED_COMMANDS or "_native_operation" not in args:
                    # Internal native handler seams; real Local/HTTP ingress
                    # separately requires the verified operation context.
                    if st.operation_ledger:
                        led = open_operation_ledger()
                        try:
                            AccountEffectJournal(led).require_clear_targets(("account:"+alias,))
                        except AccountEffectError:
                            raise AccountOperationBlocked() from None
                        finally:
                            led.close()
                    check_version()
                    return handler(args)
                intent = operation_intent(command, args)
                led = open_operation_ledger()
                try:
                    journal = AccountEffectJournal(led)
                    # Known-result reads retain the ORIGINAL version. Never
                    # rebase a completed request onto today's registry record.
                    existing = journal.status(intent.operation_id, intent.device_id)
                    if existing is None:
                        check_version()
                    return invoke_account_effect(journal, intent, lambda: handler(args))
                except AccountEffectError:
                    raise AccountOperationUnconfirmed(intent.operation_id) from None
                finally:
                    led.close()
        return invoke

    # Serialize before the registry lookup as well as the file swap. Otherwise
    # a rotation can read an alias, wait for unlink, then recreate orphan secrets.
    for command in ACCOUNT_MUTATIONS:
        handlers[command] = serialize_account_mutation(command, handlers[command])
    return handlers


SECRET_ARG_KEYS = {"secrets", "client_password", "token", "access_token", "refresh_token", "client_secret", "verification_code", "code"}


def redact_args(args: dict) -> dict:
    return {k: ("[REDACTED]" if k in SECRET_ARG_KEYS else v) for k, v in args.items()}
