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
import asyncio
import hashlib
import json
import os
import re
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


def account_approval_text(device_id: str, issued_at_unix: int, action: str, args: dict, resource_version: str | None) -> str:
    text = canonical_action(device_id, issued_at_unix, action, args)
    return text if resource_version is None else text + "|native-resource:" + resource_version


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
        from commander.accounts import require_resource_version
        require_resource_version(cmd, args)
        return self.handlers[cmd](args)

    def resource_version(self, alias: str) -> dict:
        return self.handlers["account_revision"]({"alias": alias})

    def review(self, action: str, args: dict) -> dict:
        return self.run('account_review',{'action':action,'args':args})

    def operation(self, operation_id: str, device_id: str) -> dict:
        return self.run("account_operation", {"operation_id": operation_id, "device_id": device_id})


class CommanderAccountControl:
    """Signed HTTPS to the trading VM's commander."""
    def __init__(self, url: str, token_file: str, ca_file: str = "", timeout_s: float = 30.0) -> None:
        self.url, self.token_file, self.ca_file, self.timeout_s = url.rstrip("/"), token_file, ca_file, timeout_s

    def _token(self) -> str:
        p = Path(self.token_file)
        if not p.is_file():
            raise HTTPException(503, "commander token file not configured on the gateway")
        return p.read_text().strip()

    def resource_version(self, alias: str) -> dict:
        return self.run("account_revision", {"alias": alias})

    def review(self, action: str, args: dict) -> dict:
        return self.run('account_review',{'action':action,'args':args})

    def operation(self, operation_id: str, device_id: str) -> dict:
        return self.run("account_operation", {"operation_id": operation_id, "device_id": device_id})

    def run(self, cmd: str, args: dict) -> dict:
        _trading_path()
        from commander.auth import sign_headers
        body = json.dumps({"args": args, "requested_by": "van-gateway"}).encode()
        path = f"/v1/cmd/{cmd}"
        headers = {**sign_headers(self._token(), "POST", path, body), "Content-Type": "application/json"}
        ctx = ssl.create_default_context(cafile=self.ca_file) if self.ca_file else ssl.create_default_context()
        try:
            with urlopen(Request(self.url + path, data=body, method="POST", headers=headers), timeout=self.timeout_s, context=ctx) as r:  # noqa: S310
                response = json.loads(r.read())
                if response.get("command") != cmd or not isinstance(response.get("result"), dict):
                    raise ValueError("native command response binding is invalid")
                return response["result"]
        except Exception as exc:  # noqa: BLE001
            from commander.account_effects import AccountOperationUnconfirmed, AccountOperationBlocked
            code = getattr(exc, "code", None)
            detail = ""
            try:
                detail = json.loads(exc.read()).get("detail", "")  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                detail = "native command response unavailable"
            if isinstance(detail, dict) and detail.get("code") == "account_operation_unconfirmed":
                raise AccountOperationUnconfirmed(detail.get("operation_id")) from None
            if (cmd == "account_operation" or args.get("_native_operation")) and (not code or int(code) >= 500):
                # A timeout/502 is not evidence that a signed native command
                # failed before effect. The caller already knows this ID.
                raise AccountOperationUnconfirmed(args.get("_native_operation", {}).get("operation_id") or args.get("operation_id")) from None
            if isinstance(detail, str) and "original native operation" in detail:
                raise AccountOperationBlocked() from None
            raise HTTPException(int(code) if code and 400 <= int(code) < 600 else 502, f"commander: {detail}")


# ------------------------------------------------------------------ pending OAuth store (encrypted at rest, short-lived)
class OAuthPending:
    def __init__(self, store, fernet_key: str) -> None:
        from cryptography.fernet import Fernet
        self.store = store
        self._f = Fernet(fernet_key.encode() if fernet_key else Fernet.generate_key())
        from van_gateway.trading.oauth_effects import OAuthEffects
        self.effects = OAuthEffects(store,self._f,self._decode_row)

    async def migrate(self) -> None:
        await self.store.execute("CREATE TABLE IF NOT EXISTS trading_oauth_pending (state TEXT PRIMARY KEY, broker TEXT NOT NULL, payload_enc TEXT NOT NULL, created_at_unix INTEGER NOT NULL)")
        await self.effects.migrate()

    async def create(self, broker: str, payload: dict) -> str:
        state = secrets.token_urlsafe(24)
        await self.store.execute("DELETE FROM trading_oauth_pending WHERE created_at_unix < ?", (int(time.time()) - PENDING_TTL_S,))
        created = int(time.time())
        material = {**payload,"_state":state,"_broker":broker,"_created_at_unix":created}
        await self.store.execute("INSERT INTO trading_oauth_pending(state, broker, payload_enc, created_at_unix) VALUES (?, ?, ?, ?)", (state, broker, self._f.encrypt(json.dumps(material).encode()).decode(), created))
        return state

    async def get(self, state: str) -> Optional[dict]:
        row = await self.store.fetchone("SELECT state, broker, payload_enc, created_at_unix FROM trading_oauth_pending WHERE state = ?", (state,))
        return self._decode_row(row)

    def _decode_row(self,row):
        if row is None:
            return None
        from cryptography.fernet import InvalidToken
        try:
            payload = json.loads(self._f.decrypt(row["payload_enc"].encode()))
            if (not isinstance(payload, dict) or payload.get("_state") != row["state"]
                or payload.get("_broker") != row["broker"] or type(payload.get("_created_at_unix")) is not int
                or payload["_created_at_unix"] != int(row["created_at_unix"])):
                raise ValueError("invalid or unbound pending payload")
        except (InvalidToken, ValueError, TypeError):
            raise HTTPException(409, "OAuth state cannot be read; restart linking without adopting old credentials") from None
        if payload["_created_at_unix"] < int(time.time()) - PENDING_TTL_S:
            return None
        return {**payload, "broker": row["broker"]}

    async def latest(self, broker: str) -> Optional[str]:
        row = await self.store.fetchone("SELECT state FROM trading_oauth_pending WHERE broker = ? ORDER BY created_at_unix DESC LIMIT 1", (broker,))
        return row["state"] if row else None

    async def update(self, state: str, payload: dict) -> None:
        if {"broker","_owner_device_id","_state","_broker","_created_at_unix"} & payload.keys():
            raise ValueError("OAuth update cannot rebind an authorization")
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

    async def approval_context(self,action,args,*,owner_device_id=None):
        if action!='account_upsert':
            return await self.resource_version(action,args,owner_device_id=owner_device_id),None
        alias=args.get('alias')
        if not isinstance(alias,str) or not re.fullmatch(r'[a-z0-9_]{3,32}',alias.strip().lower()):
            raise HTTPException(422,'account alias must match [a-z0-9_]{3,32}')
        _trading_path()
        from vati.core.canonical import canonical_hash
        from van_gateway.trading.account_contracts import AccountResolvedReview
        try:
            review=await asyncio.to_thread(self.control.review,action,args)
            AccountResolvedReview.model_validate(review)
            expected_changes=sorted(key for key,value in review['after'].items()
                if review['before'] is None or review['before'].get(key)!=value)
            if (review.get('schema')!='vati.account-review/1' or review.get('action')!=action
                or review.get('alias')!=str(args.get('alias','')).strip().lower()
                or review.get('request_digest')!=canonical_hash(args)
                or review.get('review_digest')!=canonical_hash({k:v for k,v in review.items() if k!='review_digest'})
                or not isinstance(review.get('after'),dict)
                or review['after'].get('alias')!=alias.strip().lower()
                or review.get('changed_fields')!=expected_changes
                or not re.fullmatch(r'[0-9a-f]{64}',review.get('resource_version',''))):
                raise ValueError('unbound native review')
            return review['resource_version'],review
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(409,'Native account settings cannot be resolved for owner review; no change dispatched') from None

    async def resource_version(self, action: str, args: dict, *, owner_device_id: str | None = None) -> str | None:
        _trading_path()
        from commander.accounts import ACCOUNT_MUTATIONS
        if action not in ACCOUNT_MUTATIONS:
            return None
        if action in {"deriv_oauth_link", "ctrader_link"} and args.get("state"):
            broker = "deriv" if action == "deriv_oauth_link" else "ctrader"
            pending = await self.pending.get(str(args["state"]))
            if pending is None:
                if await self.pending.effects.owns_link(str(args["state"]), broker, owner_device_id):
                    return None  # Only the original known/unknown result can be read.
                raise HTTPException(404, "unknown or expired OAuth state")
            self._owner(pending, owner_device_id)
            if pending.get("broker") != broker:
                raise HTTPException(400, "OAuth state belongs to a different broker")
            if await self.pending.effects.owns_link(str(args['state']),broker,owner_device_id):
                return None  # Original finality reader; never a new alias mutation.
        alias = args.get("alias")
        if not isinstance(alias, str) or not re.fullmatch(r"[a-z0-9_]{3,32}", alias.strip().lower()):
            raise HTTPException(422, "account alias must match [a-z0-9_]{3,32}")
        alias = alias.strip().lower()
        try:
            snapshot = await asyncio.to_thread(self.control.resource_version, alias)
            original_uncertainty=(action in {'deriv_oauth_link','ctrader_link'} and args.get('state')
                and await self.pending.effects.unresolved_link_target(alias))
            if action in {'deriv_create_demo','deriv_oauth_link','ctrader_link'} and snapshot.get('state')=='REGISTERED' and not original_uncertainty:
                raise HTTPException(409,'Account alias already exists; use a new alias or the verified update workflow')
            version = snapshot.get("resource_version")
            if snapshot.get("alias") != alias or not isinstance(version, str) or not re.fullmatch(r"[0-9a-f]{64}", version):
                raise ValueError("invalid native resource version")
            return version
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(409, "native account version is unavailable; no account change was sent") from None

    @staticmethod
    def _owner(pending: dict, owner_device_id: str | None) -> None:
        if not isinstance(owner_device_id, str) or not owner_device_id or pending.get("_owner_device_id") != owner_device_id:
            raise HTTPException(403, "OAuth state belongs to another device or has no verified owner; restart linking")

    async def oauth_start(self, args: dict, *, owner_device_id: str | None = None) -> dict:
        if not isinstance(owner_device_id, str) or not owner_device_id:
            raise HTTPException(403, "authenticated owner device is required to start OAuth")
        broker = str(args.get("broker", "")).lower()
        if broker == "deriv":
            state = await self.pending.create("deriv", {"app_id": str(args.get("app_id") or self.deriv_app_id), "_owner_device_id": owner_device_id})
            return {"state": state, "url": f"{DERIV_OAUTH}?{urlencode({'app_id': args.get('app_id') or self.deriv_app_id, 'l': 'EN', 'brand': 'deriv', 'state': state})}", "callback": self._cb("deriv"),
                    "note": "register this callback as the redirect URL of the Deriv app (api.deriv.com → register application)"}
        if broker == "ctrader":
            cid, csec = str(args.get("client_id", "")).strip(), str(args.get("client_secret", "")).strip()
            if not cid or not csec:
                raise HTTPException(422, "cTrader application client_id and client_secret are required (openapi.ctrader.com → Applications)")
            state = await self.pending.create("ctrader", {"client_id": cid, "client_secret": csec, "_owner_device_id": owner_device_id})
            _trading_path()
            from vati.execution.ctrader import authorize_url
            return {"state": state, "url": authorize_url(cid, self._cb("ctrader"), state=state), "callback": self._cb("ctrader"), "note": "the application's redirect URI must equal the callback"}
        raise HTTPException(422, "broker must be deriv or ctrader")

    async def _recover_effect(self,state,operation,claim,exc):
        from van_gateway.trading.oauth_effects import OAuthEffectUnconfirmed
        try:
            await asyncio.shield(self.pending.effects.uncertain(state,operation,claim.digest,type(exc).__name__))
            if isinstance(exc,asyncio.CancelledError):
                raise exc
            receipt = await self.pending.effects.applied(state,operation,claim.digest)
            if receipt is not None:
                return receipt
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        raise OAuthEffectUnconfirmed() from None

    async def oauth_callback(self, broker: str, query: dict) -> dict:
        state = str(query.get("state", ""))
        if broker == "ctrader":
            code = str(query.get("code", ""))
            if not code:
                raise HTTPException(400,"missing OAuth code")
            payload = {"code":code}
        elif broker == "deriv":
            accounts = []
            i = 1
            while f"acct{i}" in query and f"token{i}" in query:
                account = {"loginid":str(query[f"acct{i}"]),"token":str(query[f"token{i}"]),"currency":str(query.get(f"cur{i}",""))}
                if any(not value.strip() for value in account.values()):
                    raise HTTPException(400,"Deriv authorization requires explicit nonempty account, token and currency")
                accounts.append(account)
                i += 1
            if not accounts:
                raise HTTPException(400,"no accounts in Deriv redirect")
            payload = {"accounts":accounts}
        else:
            raise HTTPException(404,"unknown broker")
        claim = await self.pending.effects.begin(state,"CALLBACK",broker,payload)
        if not claim.fresh:
            return claim.receipt
        try:
            if broker == "ctrader":
                p = claim.material
                tokens = await asyncio.to_thread(self.control.run,"ctrader_oauth_exchange",{
                    "client_id":p["client_id"],"client_secret":p["client_secret"],"code":code,"redirect_uri":self._cb("ctrader")})
                if (not isinstance(tokens,dict) or not isinstance(tokens.get("access_token"),str) or not tokens["access_token"].strip()
                    or tokens.get("refresh_token") is not None and not isinstance(tokens["refresh_token"],str)):
                    raise ValueError("provider token response is incomplete")
                patch = {"access_token":tokens["access_token"],"refresh_token":tokens.get("refresh_token"),"ready":True}
                receipt = {"broker":broker,"state":state,"ready":True}
            else:
                patch = {**payload,"ready":True}
                receipt = {"broker":broker,"state":state,"ready":True,"accounts":len(accounts)}
            await self.pending.effects.complete(state,"CALLBACK",claim.digest,receipt,patch=patch)
            return receipt
        except BaseException as exc:
            return await self._recover_effect(state,"CALLBACK",claim,exc)

    async def oauth_pending(self, args: dict, *, owner_device_id: str | None = None) -> dict:
        state = str(args.get("state", ""))
        effect = await self.pending.effects.unconfirmed(state,owner_device_id)
        if effect is not None:
            return effect
        p = await self.pending.get(state)
        if p is None:
            return {"ready": False, "expired": True}
        self._owner(p, owner_device_id)
        if not p.get("ready"):
            return {"ready": False}
        if p["broker"] == "deriv":
            return {"ready": True, "broker": "deriv", "accounts": [{"loginid": a["loginid"], "currency": a["currency"], "demo": a["loginid"].upper().startswith("VR")} for a in p.get("accounts", [])]}
        accts = await asyncio.to_thread(self.control.run,"ctrader_discover", {"client_id": p["client_id"], "client_secret": p["client_secret"], "access_token": p["access_token"]})
        return {"ready": True, "broker": "ctrader", "accounts": accts.get("accounts", []), "errors": accts.get("errors", [])}

    async def run(self, action: str, args: dict, *, owner_device_id: str | None = None, native_resource_version: str | None = None, native_operation: dict | None = None, native_review: dict | None = None) -> dict:
        if action == "oauth_start":
            return await self.oauth_start(args, owner_device_id=owner_device_id)
        if action == "oauth_pending":
            return await self.oauth_pending(args, owner_device_id=owner_device_id)
        if action in {"deriv_oauth_link","ctrader_link"} and args.get("state"):
            broker = "deriv" if action=="deriv_oauth_link" else "ctrader"
            state = str(args["state"])
            def validate(p):
                if broker == "deriv":
                    if not any(a["loginid"].upper()==str(args.get("loginid","")).upper() for a in p.get("accounts",[])):
                        raise HTTPException(422,"loginid not in the OAuth result")
                elif (type(args.get("ctid_trader_account_id")) is not int or args["ctid_trader_account_id"]<=0
                      or type(args.get("is_live",False)) is not bool):
                    raise HTTPException(422,"cTrader account identity and environment must be typed")
            claim = await self.pending.effects.begin(state,"LINK",broker,args,owner_device_id=owner_device_id,validate=validate)
            if not claim.fresh:
                return claim.receipt
            try:
                p = claim.material
                if broker == "deriv":
                    account = next(a for a in p["accounts"] if a["loginid"].upper()==str(args.get("loginid","")).upper())
                    values = {"alias":args.get("alias"),"loginid":account["loginid"],"token":account["token"],"currency":account["currency"],"app_id":p.get("app_id"),"label":args.get("label","")}
                else:
                    values = {"alias":args.get("alias"),"client_id":p["client_id"],"client_secret":p["client_secret"],"access_token":p["access_token"],"refresh_token":p.get("refresh_token"),
                              "ctid_trader_account_id":args["ctid_trader_account_id"],"is_live":args.get("is_live",False),"label":args.get("label",""),"currency":args.get("currency","USD")}
                if native_resource_version is None:
                    raise HTTPException(409, "native account version is required before a new link")
                values["_expected_resource_version"] = native_resource_version
                result = await asyncio.to_thread(self.control.run,action,values)
                account_result = result.get("account") if isinstance(result,dict) else None
                expected_login = values["loginid"] if broker=="deriv" else str(values["ctid_trader_account_id"])
                if (not isinstance(account_result,dict)
                    or account_result.get("alias") != str(values["alias"]).strip().lower()
                    or account_result.get("broker") != broker.upper()
                    or str(account_result.get("login")) != str(expected_login)
                    or account_result.get("currency") != str(values["currency"]).upper()
                    or account_result.get("mode") not in {"DEMO_TRADER","OBSERVE"}):
                    raise ValueError("native account receipt does not match the requested link")
                await self.pending.effects.complete(state,"LINK",claim.digest,result,consume=True)
                return result
            except BaseException as exc:
                return await self._recover_effect(state,"LINK",claim,exc)
        if action not in ACTIONS:
            raise HTTPException(404, f"unknown account action {action}")
        _trading_path()
        from commander.accounts import ACCOUNT_MUTATIONS
        values = dict(args)
        if action in ACCOUNT_MUTATIONS:
            if native_resource_version is None:
                raise HTTPException(409, "native account version is required before mutation")
            values["_expected_resource_version"] = native_resource_version
        from commander.account_effects import JOURNALED_COMMANDS, AccountOperationUnconfirmed
        from vati.core.canonical import canonical_hash
        if action in JOURNALED_COMMANDS:
            if not native_operation or native_operation.get("device_id") != owner_device_id:
                raise HTTPException(403, "verified native operation context is required")
            values["_native_operation"] = {**native_operation, "request_digest": canonical_hash(args)}
            if action=='account_upsert':
                if not native_review or native_review.get('resource_version')!=native_resource_version or native_review.get('request_digest')!=canonical_hash(args):
                    raise HTTPException(409,'Resolved native account review is required')
                values['_expected_review_digest']=native_review['review_digest']
                values['_native_operation']['authority_ref']+='::review:'+native_review['review_digest']
        try:
            return await asyncio.to_thread(self.control.run,action,values)
        except HTTPException as exc:
            if action in JOURNALED_COMMANDS and exc.status_code >= 500:
                raise AccountOperationUnconfirmed(native_operation["operation_id"]) from None
            raise
        except Exception:
            if action in JOURNALED_COMMANDS:
                raise AccountOperationUnconfirmed(native_operation["operation_id"]) from None
            raise
