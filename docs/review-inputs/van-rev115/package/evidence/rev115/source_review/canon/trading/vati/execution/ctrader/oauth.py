"""cTrader Open API OAuth2 (openapi.ctrader.com) and account discovery.

The owner registers an application once (client id + secret); each trading account is
linked by the standard authorization-code flow. Tokens are stored behind the account's
credential reference on van-trading-core and refreshed through ProtoOARefreshTokenReq.
HTTP is injectable so the exchange is testable without the network."""

from __future__ import annotations

import json
from typing import Any, Callable, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

AUTH_URL = "https://openapi.ctrader.com/apps/auth"
TOKEN_URL = "https://openapi.ctrader.com/apps/token"


def authorize_url(client_id: str, redirect_uri: str, *, scope: str = "trading", state: str = "") -> str:
    q = {"client_id": client_id, "redirect_uri": redirect_uri, "scope": scope}
    if state:
        q["state"] = state
    return f"{AUTH_URL}?{urlencode(q)}"


def _http_post_form(url: str, params: dict[str, str], timeout_s: float = 15.0) -> dict[str, Any]:
    req = Request(url, data=urlencode(params).encode(), method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(req, timeout=timeout_s) as r:  # noqa: S310 — fixed https host
        return json.loads(r.read())


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str, *, http: Optional[Callable[[str, dict[str, str]], dict[str, Any]]] = None) -> dict[str, Any]:
    """→ {access_token, refresh_token, expires_in, token_type}. Raises ValueError on an error payload."""
    r = (http or _http_post_form)(TOKEN_URL, {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "client_id": client_id, "client_secret": client_secret})
    return _tokens(r)


def refresh_token_http(client_id: str, client_secret: str, refresh_token: str, *, http: Optional[Callable[[str, dict[str, str]], dict[str, Any]]] = None) -> dict[str, Any]:
    r = (http or _http_post_form)(TOKEN_URL, {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id, "client_secret": client_secret})
    return _tokens(r)


def _tokens(r: dict[str, Any]) -> dict[str, Any]:
    if r.get("errorCode") or r.get("error"):
        raise ValueError(f"cTrader token endpoint error: {r.get('errorCode') or r.get('error')}: {r.get('description') or r.get('error_description') or ''}")
    if not r.get("accessToken") and not r.get("access_token"):
        raise ValueError("cTrader token endpoint returned no access token")
    return {"access_token": r.get("accessToken") or r.get("access_token"), "refresh_token": r.get("refreshToken") or r.get("refresh_token"), "expires_in": int(r.get("expiresIn") or r.get("expires_in") or 0), "token_type": r.get("tokenType") or r.get("token_type") or "bearer"}


def discover_accounts(transport, *, client_id: str, client_secret: str, access_token: str) -> list[dict[str, Any]]:
    """Application auth then ProtoOAGetAccountListByAccessTokenReq → [{ctid_trader_account_id, is_live, trader_login}]."""
    transport.call("ProtoOAApplicationAuthReq", {"clientId": client_id, "clientSecret": client_secret})
    _, body = transport.call("ProtoOAGetAccountListByAccessTokenReq", {"accessToken": access_token})
    return [{"ctid_trader_account_id": a["ctidTraderAccountId"], "is_live": bool(a.get("isLive")), "trader_login": a.get("traderLogin"), "broker": a.get("brokerTitleShort")} for a in body.get("ctidTraderAccount", [])]
