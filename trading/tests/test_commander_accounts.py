"""Account onboarding through the commander: registry + 0600 secrets on the VM, broker flows with injected venues, nothing echoed."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from commander.accounts import AccountControlSettings, redact_args
from commander.app import COMMANDS, CommanderSettings, create_app
from commander.auth import sign_headers
from test_commander import FakeRunner, TOKEN, post
from test_ctrader import FakeCtrader
from vati.accounts import AccountRegistry
from vati.execution.ctrader import CtraderTransport


class FakeDeriv:
    """Socket-like Deriv endpoint: the real DerivWebSocketTransport speaks to it, so token injection is exercised."""
    def __init__(self):
        self.msgs, self.out = [], []
    def connector(self, url):
        return self
    def send(self, raw):
        m = json.loads(raw); rid = m["req_id"]; self.msgs.append({k: v for k, v in m.items() if k != "req_id"})
        if "verify_email" in m:
            self.out.append({"req_id": rid, "verify_email": 1})
        elif "new_account_virtual" in m:
            self.out.append({"req_id": rid, "error": {"message": "InvalidToken: code expired", "code": "InvalidToken"}} if m["verification_code"] != "ABC123" else {"req_id": rid, "new_account_virtual": {"client_id": "VRTC900", "oauth_token": "a1-virtualtoken", "currency": "USD", "balance": 10000}})
        elif "authorize" in m:
            self.out.append({"req_id": rid, "authorize": {"loginid": "VRTC900", "balance": "10000.00", "currency": "USD"}} if m["authorize"] in ("a1-virtualtoken", "a1-linked") else {"req_id": rid, "error": {"message": "InvalidToken", "code": "InvalidToken"}})
        elif "ping" in m:
            self.out.append({"req_id": rid, "ping": "pong"})
        else:
            self.out.append({"req_id": rid})
    def recv(self):
        return json.dumps(self.out.pop(0))
    def close(self):
        pass


@pytest.fixture
def env(tmp_path):
    deriv = FakeDeriv()
    fakes = []
    def ct_factory(is_live):
        f = FakeCtrader(); fakes.append(f)
        return CtraderTransport(host="live.ctraderapi.com" if is_live else "demo.ctraderapi.com", connector=f.connector, timeout_s=3)
    ctl = AccountControlSettings(registry_path=str(tmp_path / "accounts.json"), secrets_dir=str(tmp_path / "secrets"), deriv_connector=deriv.connector, ctrader_transport_factory=ct_factory,
                                 ctrader_http=lambda url, params: {"accessToken": "ct-at", "refreshToken": "ct-rt", "expiresIn": 100} if params.get("code") == "good" else {"errorCode": "INVALID_GRANT"})
    st = CommanderSettings(tokens={"van-gateway": TOKEN}, ledger=str(tmp_path / "l.sqlite"), heartbeat_dir=str(tmp_path / "hb"), log_dir=str(tmp_path / "log"), data_dir=str(tmp_path), runner=FakeRunner(), accounts_registry=str(tmp_path / "accounts.json"), secrets_dir=str(tmp_path / "secrets"), account_control=ctl)
    return TestClient(create_app(st)), tmp_path, deriv, fakes


def test_upsert_credentials_verify_remove_never_echo_secrets(env):
    client, tmp, deriv, fakes = env
    assert "account_upsert" in COMMANDS and "mt5_ea_issue_key" in COMMANDS
    r = post(client, "account_upsert", {"alias": "Deriv Demo", "broker": "DERIV"}); assert r.status_code == 422           # alias rule
    r = post(client, "account_upsert", {"alias": "deriv_demo", "broker": "DERIV", "server": "1089", "label": "Deriv demo"})
    assert r.status_code == 200 and r.json()["result"]["account"]["safety_identity"] == "DEMO" and r.json()["result"]["account"]["credential_ref"] == {"kind": "file"}
    sec = tmp / "secrets" / "deriv_demo.env"
    assert sec.is_file() and oct(sec.stat().st_mode & 0o777) == "0o600"
    r = post(client, "account_credentials", {"alias": "deriv_demo", "secrets": {"DERIV_API_TOKEN": "a1-linked", "EVIL": "x"}}); assert r.status_code == 422
    r = post(client, "account_credentials", {"alias": "deriv_demo", "secrets": {"DERIV_API_TOKEN": "a1-linked", "DERIV_APP_ID": "1089"}})
    assert r.json()["result"] == {"alias": "deriv_demo", "stored_keys": ["DERIV_API_TOKEN", "DERIV_APP_ID"]} and "a1-linked" not in r.text
    assert "DERIV_API_TOKEN=a1-linked" in sec.read_text() and "a1-linked" not in (tmp / "accounts.json").read_text()
    v = post(client, "account_verify", {"alias": "deriv_demo"}).json()["result"]
    assert v["ok"] is True and v["equity"] == "10000.00" and v["currency"] == "USD" and "token" not in json.dumps(v).lower()
    audit = (tmp / "log" / "commander-audit.jsonl").read_text()
    assert "a1-linked" not in audit and "[REDACTED]" in audit
    assert post(client, "account_remove", {"alias": "deriv_demo"}).json()["result"]["removed"] and not sec.exists()
    assert post(client, "account_verify", {"alias": "deriv_demo"}).status_code == 404
    assert redact_args({"alias": "x", "secrets": {"K": "v"}, "code": "c"}) == {"alias": "x", "secrets": "[REDACTED]", "code": "[REDACTED]"}


def test_deriv_demo_creation_and_oauth_link(env):
    client, tmp, deriv, fakes = env
    assert post(client, "deriv_verify_email", {"email": "not-an-email"}).status_code == 422
    r = post(client, "deriv_verify_email", {"email": "owner@example.com", "app_id": "1089"}).json()["result"]
    assert r["sent"] and deriv.msgs[-1] == {"verify_email": "owner@example.com", "type": "account_opening"}
    bad = post(client, "deriv_create_demo", {"alias": "deriv_demo", "verification_code": "WRONG", "client_password": "Pa55word!", "residence": "zw"})
    assert bad.status_code == 502 and "code expired" in bad.json()["detail"]
    r = post(client, "deriv_create_demo", {"alias": "deriv_demo", "verification_code": "ABC123", "client_password": "Pa55word!", "residence": "ZW"})
    assert r.status_code == 200 and r.json()["result"]["client_id"] == "VRTC900" and "Pa55word" not in r.text and "a1-virtualtoken" not in r.text
    assert deriv.msgs[-1]["residence"] == "zw" and deriv.msgs[-1]["type"] == "trading"
    reg = AccountRegistry(tmp / "accounts.json"); a = reg.get("deriv_demo")
    assert a.broker == "DERIV" and a.login == "VRTC900" and a.demo and reg.credentials("deriv_demo")["DERIV_API_TOKEN"] == "a1-virtualtoken"
    assert post(client, "account_verify", {"alias": "deriv_demo"}).json()["result"]["ok"] is True
    r = post(client, "deriv_oauth_link", {"alias": "deriv_real", "loginid": "CR12345", "token": "a1-linked", "currency": "USD"}).json()["result"]
    assert r["account"]["safety_identity"] == "READ ONLY" and r["account"]["demo"] is False and r["account"]["mode"] == "OBSERVE"   # a real account starts read-only until an owner mandate says otherwise
    assert (tmp / "log" / "commander-audit.jsonl").read_text().count("a1-linked") == 0


def test_ctrader_discover_exchange_and_link(env):
    client, tmp, deriv, fakes = env
    r = post(client, "ctrader_discover", {"client_id": "app-id", "client_secret": "app-secret", "access_token": "tok"}).json()["result"]
    assert r["accounts"] == [{"ctid_trader_account_id": 12345, "is_live": False, "trader_login": 5551234, "broker": "FP Markets", "environment": "demo"}]
    assert post(client, "ctrader_discover", {"client_id": "app-id", "client_secret": "wrong", "access_token": "tok"}).status_code == 502
    assert post(client, "ctrader_oauth_exchange", {"client_id": "a", "client_secret": "s", "code": "bad", "redirect_uri": "https://gw/cb"}).status_code == 502
    tok = post(client, "ctrader_oauth_exchange", {"client_id": "a", "client_secret": "s", "code": "good", "redirect_uri": "https://gw/cb"}).json()["result"]
    assert tok["access_token"] == "ct-at"
    r = post(client, "ctrader_link", {"alias": "ct_demo", "client_id": "app-id", "client_secret": "app-secret", "access_token": "tok", "refresh_token": "rt", "ctid_trader_account_id": 12345, "is_live": False, "label": "FP Markets demo"}).json()["result"]
    assert r["account"]["broker"] == "CTRADER" and r["account"]["login"] == "12345" and r["account"]["safety_identity"] == "DEMO"
    v = post(client, "account_verify", {"alias": "ct_demo"}).json()["result"]
    assert v["ok"] is True and v["balance"] == "10053.09"
    sec = (tmp / "secrets" / "ct_demo.env").read_text()
    assert "CTRADER_CLIENT_SECRET=app-secret" in sec and "CTRADER_REFRESH_TOKEN=rt" in sec


def test_mt5_ea_key_issue_and_verify(env, monkeypatch):
    client, tmp, deriv, fakes = env
    monkeypatch.setenv("VAN_PUBLIC_HOST", "trading.example.com")
    monkeypatch.setenv("VAN_MT5_PULL_QUEUE", str(tmp / "pull.sqlite"))
    r = post(client, "mt5_ea_issue_key", {"alias": "mt5_ea", "login": "12345678", "server": "Broker-Demo", "label": "MT5 demo"}).json()["result"]
    key = r["signing_key"]
    assert len(key) == 64 and r["ea_inputs"] == {"Alias": "mt5_ea", "SigningKey": key, "BridgeUrl": "https://trading.example.com"} and r["account"]["broker"] == "MT5_EA"
    assert f"BRIDGE_SIGNING_KEY={key}" in (tmp / "secrets" / "mt5_ea.env").read_text()
    v = post(client, "account_verify", {"alias": "mt5_ea"}).json()["result"]
    assert v["ok"] is False and "has not polled" in v["detail"]
    # the EA polls once → verify turns green
    from vati.execution.mt5_pull import BridgeQueue
    BridgeQueue(tmp / "pull.sqlite").set_state("mt5_ea", {"login": 12345678, "equity": 1, "balance": 1}, [], now_ms=int(__import__("time").time() * 1000), nonce="n")
    assert post(client, "account_verify", {"alias": "mt5_ea"}).json()["result"]["ok"] is True
    # the audit never carries the key
    assert key not in (tmp / "log" / "commander-audit.jsonl").read_text()
