"""Owner account onboarding from the Van app (Rev 5 Part B, owner-directed).

The app types account details and credentials; the gateway verifies the device
signature (HMAC with the enrolled device secret, bound to the action and the exact
argument bytes), audits with secrets redacted, and forwards to the trading VM's
commander (`CommanderAccountControl`, signed HTTPS) or runs the same handlers
in-process when gateway and trading share a host (`LocalAccountControl`). Credentials
never persist on the gateway: OAuth tokens in flight live in an encrypted, short-lived
pending store and are deleted once linked."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import ssl
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException

ACTIONS = ("account_upsert", "account_credentials", "account_remove", "account_verify", "deriv_verify_email", "deriv_create_demo", "deriv_oauth_link", "ctrader_discover", "ctrader_link", "mt5_ea_issue_key", "oauth_start", "oauth_pending")
#: P1-SEC-004. Actions that only read state; a biometric prompt for these would train the
#: owner to approve without reading. Everything else changes an account or a credential and
#: needs a CryptoObject-bound A4 proof, not a prompt that returned a boolean.
READ_ONLY_ACTIONS = frozenset({"account_verify", "oauth_pending", "ctrader_discover"})

#: The rest, stated as the complement so a new action is guarded by default rather than by
#: somebody remembering to add it here.
def requires_owner_approval(action: str) -> bool:
    return action in ACTIONS and action not in READ_ONLY_ACTIONS


SECRET_ARG_KEYS = {"secrets", "client_password", "token", "access_token", "refresh_token", "client_secret", "verification_code", "code"}
MAX_AGE_S = 300
PENDING_TTL_S = 900
DERIV_OAUTH = "https://oauth.deriv.com/oauth2/authorize"


def canonical_args(args: dict) -> bytes:
    return json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_action(device_id: str, issued_at_unix: int, action: str, args: dict) -> str:
    return "|".join(["trading-account", device_id, str(issued_at_unix), action, hashlib.sha256(canonical_args(args)).hexdigest()])


def redact(args: dict) -> dict:
    return {k: ("[REDACTED]" if k in SECRET_ARG_KEYS else v) for k, v in args.items()}


def _trading_path() -> None:
    d = Path(__file__).resolve().parents[3] / "trading"
    if d.is_dir() and str(d) not in sys.path:
        sys.path.append(str(d))


# ------------------------------------------------------------------ control backends
class LocalAccountControl:
    """Same handlers the commander runs, in-process (single-host or development)."""
    def __init__(self, registry_path: str, secrets_dir: str, **overrides: Any) -> None:
        _trading_path()
        from commander.accounts import AccountControlSettings, build_account_handlers
        self.handlers = build_account_handlers(AccountControlSettings(registry_path=registry_path, secrets_dir=secrets_dir, **overrides))

    def run(self, cmd: str, args: dict) -> dict:
        if cmd not in self.handlers:
            raise HTTPException(404, f"unknown account command {cmd}")
        return self.handlers[cmd](args)


class CommanderAccountControl:
    """Signed HTTPS to the trading VM's commander."""
    def __init__(self, url: str, token_file: str, ca_file: str = "", timeout_s: float = 30.0) -> None:
        self.url, self.token_file, self.ca_file, self.timeout_s = url.rstrip("/"), token_file, ca_file, timeout_s

    def _token(self) -> str:
        p = Path(self.token_file)
        if not p.is_file():
            raise HTTPException(503, "commander token file not configured on the gateway")
        return p.read_text().strip()

    def run(self, cmd: str, args: dict) -> dict:
        _trading_path()
        from commander.auth import sign_headers
        body = json.dumps({"args": args, "requested_by": "van-gateway"}).encode()
        path = f"/v1/cmd/{cmd}"
        headers = {**sign_headers(self._token(), "POST", path, body), "Content-Type": "application/json"}
        ctx = ssl.create_default_context(cafile=self.ca_file) if self.ca_file else ssl.create_default_context()
        try:
            with urlopen(Request(self.url + path, data=body, method="POST", headers=headers), timeout=self.timeout_s, context=ctx) as r:  # noqa: S310
                return json.loads(r.read())["result"]
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", None)
            detail = ""
            try:
                detail = json.loads(exc.read()).get("detail", "")  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                detail = str(exc)[:200]
            raise HTTPException(int(code) if code and 400 <= int(code) < 600 else 502, f"commander: {detail}")


# ------------------------------------------------------------------ pending OAuth store (encrypted at rest, short-lived)
class OAuthPending:
    def __init__(self, store, fernet_key: str) -> None:
        from cryptography.fernet import Fernet
        self.store = store
        self._f = Fernet(fernet_key.encode() if fernet_key else Fernet.generate_key())

    async def migrate(self) -> None:
        await self.store.execute("CREATE TABLE IF NOT EXISTS trading_oauth_pending (state TEXT PRIMARY KEY, broker TEXT NOT NULL, payload_enc TEXT NOT NULL, created_at_unix INTEGER NOT NULL)")

    async def create(self, broker: str, payload: dict) -> str:
        state = secrets.token_urlsafe(24)
        await self.store.execute("DELETE FROM trading_oauth_pending WHERE created_at_unix < ?", (int(time.time()) - PENDING_TTL_S,))
        await self.store.execute("INSERT INTO trading_oauth_pending(state, broker, payload_enc, created_at_unix) VALUES (?, ?, ?, ?)", (state, broker, self._f.encrypt(json.dumps(payload).encode()).decode(), int(time.time())))
        return state

    async def get(self, state: str) -> Optional[dict]:
        row = await self.store.fetchone("SELECT broker, payload_enc, created_at_unix FROM trading_oauth_pending WHERE state = ?", (state,))
        if row is None or int(row["created_at_unix"]) < int(time.time()) - PENDING_TTL_S:
            return None
        return {"broker": row["broker"], **json.loads(self._f.decrypt(row["payload_enc"].encode()))}

    async def latest(self, broker: str) -> Optional[str]:
        row = await self.store.fetchone("SELECT state FROM trading_oauth_pending WHERE broker = ? ORDER BY created_at_unix DESC LIMIT 1", (broker,))
        return row["state"] if row else None

    async def update(self, state: str, payload: dict) -> None:
        cur = await self.get(state)
        if cur is None:
            raise HTTPException(404, "unknown or expired OAuth state")
        cur.pop("broker", None)
        await self.store.execute("UPDATE trading_oauth_pending SET payload_enc = ? WHERE state = ?", (self._f.encrypt(json.dumps({**cur, **payload}).encode()).decode(), state))

    async def consume(self, state: str) -> None:
        await self.store.execute("DELETE FROM trading_oauth_pending WHERE state = ?", (state,))


# ------------------------------------------------------------------ orchestration
@dataclass
class AccountOnboarding:
    control: Any
    pending: OAuthPending
    public_base_url: str
    deriv_app_id: str = "1089"

    def _cb(self, broker: str) -> str:
        return f"{self.public_base_url.rstrip('/')}/v1/trading/oauth/{broker}/callback"

    async def oauth_start(self, args: dict) -> dict:
        broker = str(args.get("broker", "")).lower()
        if broker == "deriv":
            state = await self.pending.create("deriv", {"app_id": str(args.get("app_id") or self.deriv_app_id)})
            return {"state": state, "url": f"{DERIV_OAUTH}?{urlencode({'app_id': args.get('app_id') or self.deriv_app_id, 'l': 'EN', 'brand': 'deriv', 'state': state})}", "callback": self._cb("deriv"),
                    "note": "register this callback as the redirect URL of the Deriv app (api.deriv.com → register application)"}
        if broker == "ctrader":
            cid, csec = str(args.get("client_id", "")).strip(), str(args.get("client_secret", "")).strip()
            if not cid or not csec:
                raise HTTPException(422, "cTrader application client_id and client_secret are required (openapi.ctrader.com → Applications)")
            state = await self.pending.create("ctrader", {"client_id": cid, "client_secret": csec})
            _trading_path()
            from vati.execution.ctrader import authorize_url
            return {"state": state, "url": authorize_url(cid, self._cb("ctrader"), state=state), "callback": self._cb("ctrader"), "note": "the application's redirect URI must equal the callback"}
        raise HTTPException(422, "broker must be deriv or ctrader")

    async def oauth_callback(self, broker: str, query: dict) -> dict:
        if broker == "ctrader":
            state, code = str(query.get("state", "")), str(query.get("code", ""))
            p = await self.pending.get(state)
            if p is None or not code:
                raise HTTPException(400, "missing code or unknown state")
            tok = self.control.run("ctrader_oauth_exchange", {"client_id": p["client_id"], "client_secret": p["client_secret"], "code": code, "redirect_uri": self._cb("ctrader")})
            await self.pending.update(state, {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token"), "ready": True})
            return {"broker": "ctrader", "state": state, "ready": True}
        if broker == "deriv":
            state = str(query.get("state", "")) or await self.pending.latest("deriv") or ""
            p = await self.pending.get(state)
            if p is None:
                raise HTTPException(400, "unknown or expired state")
            accounts = []
            i = 1
            while f"acct{i}" in query and f"token{i}" in query:
                accounts.append({"loginid": str(query[f"acct{i}"]), "token": str(query[f"token{i}"]), "currency": str(query.get(f"cur{i}", ""))})
                i += 1
            if not accounts:
                raise HTTPException(400, "no accounts in Deriv redirect")
            await self.pending.update(state, {"accounts": accounts, "ready": True})
            return {"broker": "deriv", "state": state, "ready": True, "accounts": len(accounts)}
        raise HTTPException(404, "unknown broker")

    async def oauth_pending(self, args: dict) -> dict:
        p = await self.pending.get(str(args.get("state", "")))
        if p is None:
            return {"ready": False, "expired": True}
        if not p.get("ready"):
            return {"ready": False}
        if p["broker"] == "deriv":
            return {"ready": True, "broker": "deriv", "accounts": [{"loginid": a["loginid"], "currency": a["currency"], "demo": a["loginid"].upper().startswith("VR")} for a in p.get("accounts", [])]}
        accts = self.control.run("ctrader_discover", {"client_id": p["client_id"], "client_secret": p["client_secret"], "access_token": p["access_token"]})
        return {"ready": True, "broker": "ctrader", "accounts": accts.get("accounts", []), "errors": accts.get("errors", [])}

    async def run(self, action: str, args: dict) -> dict:
        if action == "oauth_start":
            return await self.oauth_start(args)
        if action == "oauth_pending":
            return await self.oauth_pending(args)
        if action == "deriv_oauth_link" and args.get("state"):
            p = await self.pending.get(str(args["state"]))
            if p is None:
                raise HTTPException(404, "unknown or expired OAuth state")
            acct = next((a for a in p.get("accounts", []) if a["loginid"].upper() == str(args.get("loginid", "")).upper()), None)
            if acct is None:
                raise HTTPException(422, "loginid not in the OAuth result")
            out = self.control.run("deriv_oauth_link", {"alias": args.get("alias"), "loginid": acct["loginid"], "token": acct["token"], "currency": acct["currency"], "app_id": p.get("app_id"), "label": args.get("label", "")})
            await self.pending.consume(str(args["state"]))
            return out
        if action == "ctrader_link" and args.get("state"):
            p = await self.pending.get(str(args["state"]))
            if p is None or not p.get("ready"):
                raise HTTPException(404, "unknown, expired or incomplete OAuth state")
            out = self.control.run("ctrader_link", {"alias": args.get("alias"), "client_id": p["client_id"], "client_secret": p["client_secret"], "access_token": p["access_token"], "refresh_token": p.get("refresh_token"),
                                                     "ctid_trader_account_id": args.get("ctid_trader_account_id"), "is_live": args.get("is_live", False), "label": args.get("label", ""), "currency": args.get("currency", "USD")})
            await self.pending.consume(str(args["state"]))
            return out
        if action not in ACTIONS:
            raise HTTPException(404, f"unknown account action {action}")
        return self.control.run(action, args)
