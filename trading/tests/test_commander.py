"""Van trading commander: typed, signed, allowlisted; never a shell."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from commander.app import COMMANDS, CommanderSettings, create_app, redact
from commander.auth import HDR_NONCE, HDR_SIG, HDR_TS, NonceCache, sign_headers, verify_request
from vati.core import EventKind, Ledger, make_event

TOKEN = "t" * 40


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.active = {"vati-session@paper_lab.service": "active", "vati-vekl.service": "active"}

    def __call__(self, argv, timeout):
        self.calls.append(argv)
        if argv[:2] == ["systemctl", "list-units"]:
            return 0, "vati-session@paper_lab.service loaded active running x\n", ""
        if argv[:2] == ["systemctl", "is-active"]:
            return 0, self.active.get(argv[2], "inactive") + "\n", ""
        if argv[:2] == ["systemctl", "is-enabled"]:
            return 0, "enabled\n", ""
        if argv[:2] == ["systemctl", "restart"]:
            self.active[argv[2]] = "active"; return 0, "", ""
        if argv[0] == "journalctl":
            return 0, "starting session\nBRIDGE_SIGNING_KEY=abcdef123 loaded\nauthorize token=xyz done\nok\n", ""
        if argv[0] == "node":
            return 0, "v22.0.0\n", ""
        if "backtest" in argv:
            Path(argv[argv.index("--out") + 1]).write_text(json.dumps({"trades": 3, "ledger_ok": True, "decision_replay_identical": True}))
            return 0, "", ""
        return 127, "", "unexpected"


@pytest.fixture
def env(tmp_path):
    hb = tmp_path / "hb"; hb.mkdir()
    (hb / "paper_lab.json").write_text(json.dumps({"account_alias": "paper_lab", "status": "RUNNING", "updated_ms": int(time.time() * 1000), "cycles": 5}))
    led = Ledger(tmp_path / "l.sqlite"); led.append(make_event(EventKind.SESSION, "t", {"event": "STARTED"}, event_time_ms=1, received_time_ms=1)); led.close()
    data = tmp_path / "data"; (data / "bt").mkdir(parents=True)
    (data / "bt" / "cfg.json").write_text("{}"); (data / "bt" / "bars.csv").write_text("x")
    runner = FakeRunner()
    st = CommanderSettings(token=TOKEN, ledger=str(tmp_path / "l.sqlite"), heartbeat_dir=str(hb), log_dir=str(tmp_path / "log"), data_dir=str(data), vekl_url="http://127.0.0.1:1", runner=runner, accounts_registry=str(tmp_path / "accounts.json"))
    return TestClient(create_app(st)), runner, tmp_path


def post(client, name, args=None, token=TOKEN, headers=None):
    body = json.dumps({"args": args or {}, "requested_by": "test"}).encode()
    h = headers or sign_headers(token, "POST", f"/v1/cmd/{name}", body)
    return client.post(f"/v1/cmd/{name}", content=body, headers={**h, "content-type": "application/json"})


def test_signature_skew_nonce_and_replay(env):
    client, _, _ = env
    assert client.get("/health").json()["commands"] == list(COMMANDS)
    assert post(client, "status", token="wrong" * 8).status_code == 401
    body = json.dumps({"args": {}}).encode()
    old = sign_headers(TOKEN, "POST", "/v1/cmd/status", body, now=time.time() - 3600)
    assert post(client, "status", headers=old).status_code == 401
    h = sign_headers(TOKEN, "POST", "/v1/cmd/status", body)
    assert client.post("/v1/cmd/status", content=body, headers=h).status_code == 200
    r = client.post("/v1/cmd/status", content=body, headers=h)
    assert r.status_code == 401 and "replayed" in r.json()["detail"]
    # signature is bound to the path: a valid signature for status cannot drive restart_service
    h2 = sign_headers(TOKEN, "POST", "/v1/cmd/status", body)
    assert client.post("/v1/cmd/restart_service", content=body, headers=h2).status_code == 401
    ok, why = verify_request(TOKEN, {HDR_TS: "x", HDR_NONCE: "n", HDR_SIG: "s"}, "POST", "/p", b"", nonces=NonceCache())
    assert not ok and "missing" in why
    assert client.post("/v1/cmd/shell", content=body, headers=sign_headers(TOKEN, "POST", "/v1/cmd/shell", body)).status_code == 404


def test_status_services_restart_and_tail_are_allowlisted_and_redacted(env):
    client, runner, tmp = env
    st = post(client, "status").json()["result"]
    assert st["heartbeats"][0]["account_alias"] == "paper_lab" and st["ledger"]["events"] == 1 and st["vekl"]["ok"] is False
    assert {u["unit"] for u in st["units"]} >= {"vati-session@paper_lab.service", "vati-vekl.service", "vati-commander.service"}
    assert post(client, "services").json()["result"]["units"]
    assert post(client, "restart_service", {"unit": "vati-session@paper_lab.service"}).json()["result"]["restarted"] is True
    assert post(client, "restart_service", {"unit": "sshd.service"}).status_code == 403
    assert post(client, "restart_service", {"unit": "vati-vekl.service; rm -rf /"}).status_code == 403
    assert all(len(c) >= 2 and c[0] in ("systemctl", "journalctl", "node") for c in runner.calls)
    tail = post(client, "tail_log", {"unit": "vati-vekl.service", "lines": 3}).json()["result"]
    assert tail["lines"] == ["BRIDGE_SIGNING_KEY=[REDACTED] loaded", "authorize token=[REDACTED] done", "ok"]
    assert post(client, "tail_log", {"unit": "nginx.service"}).status_code == 403
    assert redact("api_key: abc") == "api_key: [REDACTED]" and redact("plain text") == "plain text"
    audit = (tmp / "log" / "commander-audit.jsonl").read_text().splitlines()
    assert any('"cmd": "restart_service"' in l and "refused" in l for l in audit) and any('"result": "ok"' in l for l in audit)


def test_backtest_paths_are_confined_and_halt_needs_owner_signature(env):
    client, runner, tmp = env
    r = post(client, "run_backtest", {"config": "bt/cfg.json", "bars": "bt/bars.csv"}).json()["result"]
    assert r["exit_code"] == 0 and r["summary"]["trades"] == 3 and "candidate" in r["authority"]
    assert post(client, "run_backtest", {"config": "../../etc/passwd", "bars": "bt/bars.csv"}).status_code == 403
    assert post(client, "run_backtest", {"config": "bt/missing.json", "bars": "bt/bars.csv"}).status_code == 404
    assert post(client, "halt", {"owner_signature_ref": ""}).status_code == 403
    h = post(client, "halt", {"owner_signature_ref": "owner:sig-1", "reason": "manual"}).json()["result"]
    led = Ledger(tmp / "l.sqlite")
    ev = list(led.iter(EventKind.KILL_SWITCH))[-1]
    assert h["halted"] and ev.hash == h["event_hash"] and ev.payload["trigger"] == "OWNER_HALT" and ev.producer == "van-commander" and led.verify_chain()[0]
    assert post(client, "vekl_resolve", {"instruction": "x"}).status_code == 502          # VEKL down → 502, never a silent success
    d = post(client, "doctor").json()["result"]
    assert d["ledger_reachable"] and d["node"] == "v22.0.0" and "disk_free_gb" in d
    a = post(client, "accounts").json()["result"]
    assert a["accounts"] == [] and "add one" in a["note"]
    assert client.get("/v1/tools", headers=sign_headers(TOKEN, "GET", "/v1/tools", b"")).json()["tools"][0]["name"] == "status"


def test_session_service_observes_commander_halt(tmp_path, eurusd):
    from conftest import mandate_dict
    from test_backtest_runner_cli import synthetic_bars
    from vati.accounts import Account, AccountRegistry
    from vati.app.service import ServiceConfig, SessionService, lake_bar_source
    from vati.market_data.feeds import BarLake
    from vati.risk.serde import contract_to_dict
    AccountRegistry(tmp_path / "a.json").add(Account(alias="paper_lab", broker="PAPER", mode="DEMO_TRADER", currency="USD"))
    lake = BarLake(tmp_path / "lake"); bars = synthetic_bars(); lake.write(bars, symbol="EURUSD", timeframe="H1", source="t", provenance="SYNTHETIC")
    cfg = ServiceConfig(account_alias="paper_lab", symbol="EURUSD", base="EUR", quote="USD", timeframe="H1", contract=contract_to_dict(eurusd), mandate=mandate_dict(venue="paper", mode="DEMO_TRADER", allowed_strategies=["FX-TREND-PULLBACK-01"]),
                        capsules=["FX-TREND-PULLBACK-01"], registry_path=str(tmp_path / "a.json"), ledger=str(tmp_path / "l.sqlite"), lake_root=str(tmp_path / "lake"), heartbeat_path=str(tmp_path / "hb.json"))
    clock = {"now": bars[100].end_ms}
    svc = SessionService(cfg, lake_bar_source(lake, "EURUSD", "H1"), clock=lambda: clock["now"]).build(); svc.start()
    clock["now"] = bars[101].end_ms + 1
    assert svc.step_once() not in (None, "NEW_TRADES_BLOCKED")
    st = CommanderSettings(token=TOKEN, ledger=str(tmp_path / "l.sqlite"), heartbeat_dir=str(tmp_path), log_dir=str(tmp_path / "log"), data_dir=str(tmp_path), runner=FakeRunner())
    client = TestClient(create_app(st))
    assert post(client, "halt", {"owner_signature_ref": "owner:sig"}).status_code == 200
    clock["now"] = bars[102].end_ms + 1
    assert svc.step_once() == "NEW_TRADES_BLOCKED" and not svc.runner.permit_new_orders
    hb = json.loads((tmp_path / "hb.json").read_text()); assert "OWNER_HALT" in hb["kill_switch"]
