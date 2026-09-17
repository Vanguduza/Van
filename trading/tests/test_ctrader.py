"""cTrader Open API: schema codec against hand-verified bytes, and the adapter against a fake cTrader speaking the same protocol."""
from __future__ import annotations

import socket
import struct
import threading
import time
from decimal import Decimal

import pytest

from vati.execution.base import OrderCommand, StopMode
from vati.execution.ctrader import SCHEMA, CtraderAdapter, CtraderApiError, CtraderError, CtraderTransport, authorize_url, discover_accounts, exchange_code
from vati.execution.ctrader.feed import trendbars
from vati.execution.ctrader.protoschema import ProtoSchemaError
from vati.risk.contracts import Direction, LossModel

D = Decimal


def test_codec_matches_hand_verified_wire_bytes():
    # ProtoMessage{payloadType=2100, payload=ProtoOAApplicationAuthReq{clientId="id", clientSecret="s"}, clientMsgId="abc"}
    assert SCHEMA.wrap("ProtoOAApplicationAuthReq", {"clientId": "id", "clientSecret": "s"}, "abc").hex() == "08b410120a08b410120269641a01731a03616263"
    # field 19 relativeStopLoss=2000 → tag 0x98 0x01, varint 0xd0 0x0f; enums by name; payloadType default emitted
    assert SCHEMA.encode("ProtoOANewOrderReq", {"ctidTraderAccountId": 12, "symbolId": 1, "orderType": "MARKET", "tradeSide": "SELL", "volume": 100000, "relativeStopLoss": 2000}).hex() == "08ba10100c18012001280230a08d069801d00f"
    # negative int64, double, repeated, nested, unknown-field skip, enum reverse
    b = SCHEMA.encode("ProtoOATrader", {"ctidTraderAccountId": 5, "balance": -125, "depositAssetId": 1, "moneyDigits": 2, "traderLogin": 777})
    d = SCHEMA.decode("ProtoOATrader", b)
    assert d["balance"] == -125 and d["traderLogin"] == 777 and d["accountType"] == "HEDGED"
    pos = SCHEMA.encode("ProtoOAPosition", {"positionId": 9, "tradeData": {"symbolId": 1, "volume": 100000, "tradeSide": "BUY", "label": "vati:x"}, "positionStatus": "POSITION_STATUS_OPEN", "swap": 0, "price": 1.10005, "stopLoss": 1.099})
    dp = SCHEMA.decode("ProtoOAPosition", pos)
    assert dp["tradeData"]["tradeSide"] == "BUY" and abs(dp["price"] - 1.10005) < 1e-12 and dp["positionStatus"] == "POSITION_STATUS_OPEN"
    lst = SCHEMA.encode("ProtoOASymbolByIdReq", {"ctidTraderAccountId": 1, "symbolId": [1, 2, 300]})
    assert SCHEMA.decode("ProtoOASymbolByIdReq", lst)["symbolId"] == [1, 2, 300]
    assert SCHEMA.decode("ProtoOATrader", b + bytes.fromhex("f8ff0301"))["traderLogin"] == 777      # unknown field 8191 skipped
    with pytest.raises(ProtoSchemaError, match="required"):
        SCHEMA.encode("ProtoOANewOrderReq", {"ctidTraderAccountId": 1})
    with pytest.raises(ProtoSchemaError, match="unknown fields"):
        SCHEMA.encode("ProtoOATraderReq", {"ctidTraderAccountId": 1, "bogus": 2})
    assert SCHEMA.payload_type["ProtoOAExecutionEvent"] == 2126 and SCHEMA.message_for_payload[51] == "ProtoHeartbeatEvent" and SCHEMA.message_for_payload[2142] == "ProtoOAErrorRes"
    assert SCHEMA.enums["ProtoOATrendbarPeriod"]["H1"] == 9 and SCHEMA.enums["ProtoOAExecutionType"]["ORDER_FILLED"] == 3


# ------------------------------------------------------------------ fake cTrader
class FakeCtrader:
    """Speaks the framed protocol with the same codec; deterministic answers; unsolicited execution events."""
    def __init__(self):
        self.a, self.b = socket.socketpair()
        self.requests: list[tuple[str, dict]] = []
        self.positions: dict[int, dict] = {}
        self.next_pos = 100
        self.reject_next_order = False
        threading.Thread(target=self.serve, daemon=True).start()

    def connector(self, host, port):
        self.host = host; return self.a

    def send(self, name, body, cid=None):
        payload = SCHEMA.wrap(name, body, cid)
        self.b.sendall(struct.pack(">I", len(payload)) + payload)

    def _recv(self, n):
        buf = b""
        while len(buf) < n:
            c = self.b.recv(n - len(buf))
            if not c: raise ConnectionError
            buf += c
        return buf

    def serve(self):
        try:
            while True:
                (ln,) = struct.unpack(">I", self._recv(4))
                name, body, cid = SCHEMA.unwrap(self._recv(ln))
                self.requests.append((name, body))
                self.handle(name, body, cid)
        except (ConnectionError, OSError):
            return

    def handle(self, name, body, cid):
        acct = 12345
        if name == "ProtoHeartbeatEvent":
            return self.send("ProtoHeartbeatEvent", {})
        if name == "ProtoOAApplicationAuthReq":
            return self.send("ProtoOAApplicationAuthRes", {}, cid) if body["clientSecret"] == "app-secret" else self.send("ProtoOAErrorRes", {"errorCode": "CH_CLIENT_AUTH_FAILURE", "description": "bad app secret"}, cid)
        if name == "ProtoOAAccountAuthReq":
            return self.send("ProtoOAAccountAuthRes", {"ctidTraderAccountId": acct}, cid) if body["accessToken"] == "tok" else self.send("ProtoOAErrorRes", {"errorCode": "INVALID_REQUEST", "description": "bad token"}, cid)
        if name == "ProtoOAGetAccountListByAccessTokenReq":
            return self.send("ProtoOAGetAccountListByAccessTokenRes", {"accessToken": body["accessToken"], "ctidTraderAccount": [{"ctidTraderAccountId": acct, "isLive": False, "traderLogin": 5551234, "brokerTitleShort": "FP Markets"}]}, cid)
        if name == "ProtoOASymbolsListReq":
            return self.send("ProtoOASymbolsListRes", {"ctidTraderAccountId": acct, "symbol": [{"symbolId": 1, "symbolName": "EURUSD", "enabled": True}, {"symbolId": 41, "symbolName": "XAUUSD", "enabled": True}]}, cid)
        if name == "ProtoOASymbolByIdReq":
            syms = [{"symbolId": 1, "digits": 5, "pipPosition": 4, "lotSize": 10_000_000, "minVolume": 100_000, "stepVolume": 100_000, "maxVolume": 10**10}, {"symbolId": 41, "digits": 2, "pipPosition": 1, "lotSize": 10_000, "minVolume": 100, "stepVolume": 100, "maxVolume": 10**8}]
            return self.send("ProtoOASymbolByIdRes", {"ctidTraderAccountId": acct, "symbol": [s for s in syms if s["symbolId"] in body["symbolId"]]}, cid)
        if name == "ProtoOATraderReq":
            return self.send("ProtoOATraderRes", {"ctidTraderAccountId": acct, "trader": {"ctidTraderAccountId": acct, "balance": 1005309, "depositAssetId": 1, "moneyDigits": 2, "traderLogin": 5551234}}, cid)
        if name == "ProtoOAReconcileReq":
            return self.send("ProtoOAReconcileRes", {"ctidTraderAccountId": acct, "position": list(self.positions.values())}, cid)
        if name == "ProtoOANewOrderReq":
            if self.reject_next_order:
                self.reject_next_order = False
                self.send("ProtoOAExecutionEvent", {"ctidTraderAccountId": acct, "executionType": "ORDER_REJECTED", "order": {"orderId": 1, "tradeData": {"symbolId": body["symbolId"], "volume": body["volume"], "tradeSide": body["tradeSide"]}, "orderType": body["orderType"], "orderStatus": "ORDER_STATUS_REJECTED", "clientOrderId": body["clientOrderId"]}, "errorCode": "NOT_ENOUGH_MONEY"}, cid)
                return
            pid = self.next_pos; self.next_pos += 1
            fill = 1.10008 if body["tradeSide"] == "BUY" else 1.10000
            sl = fill - body["relativeStopLoss"] / 100000 if body["tradeSide"] == "BUY" else fill + body["relativeStopLoss"] / 100000
            self.positions[pid] = {"positionId": pid, "tradeData": {"symbolId": body["symbolId"], "volume": body["volume"], "tradeSide": body["tradeSide"], "label": body.get("label", "")}, "positionStatus": "POSITION_STATUS_OPEN", "swap": 0, "price": fill, "stopLoss": round(sl, 5)}
            order = {"orderId": 500 + pid, "tradeData": self.positions[pid]["tradeData"], "orderType": body["orderType"], "orderStatus": "ORDER_STATUS_FILLED", "clientOrderId": body["clientOrderId"], "positionId": pid}
            self.send("ProtoOAExecutionEvent", {"ctidTraderAccountId": acct, "executionType": "ORDER_ACCEPTED", "order": order}, cid)   # the real API echoes clientMsgId on the first execution event
            self.send("ProtoOAExecutionEvent", {"ctidTraderAccountId": acct, "executionType": "ORDER_FILLED", "position": self.positions[pid], "order": order,
                                                 "deal": {"dealId": 9000 + pid, "orderId": 500 + pid, "positionId": pid, "volume": body["volume"], "filledVolume": body["volume"], "symbolId": body["symbolId"], "createTimestamp": 1, "executionTimestamp": 1_700_000_000_000, "executionPrice": fill, "tradeSide": body["tradeSide"], "dealStatus": "FILLED", "commission": -350, "moneyDigits": 2}})
            return
        if name == "ProtoOAAmendPositionSLTPReq":
            self.positions[body["positionId"]]["stopLoss"] = body["stopLoss"]
            return self.send("ProtoOAExecutionEvent", {"ctidTraderAccountId": acct, "executionType": "ORDER_ACCEPTED", "position": self.positions[body["positionId"]]}, cid)
        if name == "ProtoOAClosePositionReq":
            p = self.positions.pop(body["positionId"])
            self.send("ProtoOAExecutionEvent", {"ctidTraderAccountId": acct, "executionType": "ORDER_FILLED", "position": {**p, "positionStatus": "POSITION_STATUS_CLOSED"}, "order": {"orderId": 2, "tradeData": p["tradeData"], "orderType": "MARKET", "orderStatus": "ORDER_STATUS_FILLED", "closingOrder": True},
                                                 "deal": {"dealId": 1, "orderId": 2, "positionId": body["positionId"], "volume": body["volume"], "filledVolume": body["volume"], "symbolId": p["tradeData"]["symbolId"], "createTimestamp": 1, "executionTimestamp": 2, "executionPrice": 1.1050, "tradeSide": "SELL", "dealStatus": "FILLED", "closePositionDetail": {"entryPrice": p["price"], "grossProfit": 4920, "swap": 0, "commission": -350, "balance": 1010229, "moneyDigits": 2}}}, cid)
            return
        if name == "ProtoOAGetTrendbarsReq":
            bars = [{"volume": 10 + i, "period": body["period"], "low": 110000 + i * 10, "deltaOpen": 5, "deltaClose": 12, "deltaHigh": 20, "utcTimestampInMinutes": 28_333_333 + i * 60} for i in range(3)]
            return self.send("ProtoOAGetTrendbarsRes", {"ctidTraderAccountId": acct, "period": body["period"], "timestamp": body["toTimestamp"], "trendbar": bars, "symbolId": body["symbolId"]}, cid)
        if name == "ProtoOASubscribeSpotsReq":
            self.send("ProtoOASubscribeSpotsRes", {"ctidTraderAccountId": acct}, cid)
            return self.send("ProtoOASpotEvent", {"ctidTraderAccountId": acct, "symbolId": body["symbolId"][0], "bid": 110100, "ask": 110108})
        self.send("ProtoOAErrorRes", {"errorCode": "UNSUPPORTED", "description": name}, cid)


def make_adapter(fake, token="tok", secret="app-secret"):
    t = CtraderTransport(host="demo.ctraderapi.com", connector=fake.connector, timeout_s=3, heartbeat_s=0.05)
    return CtraderAdapter(t, client_id="app-id", client_secret_provider=lambda: secret, access_token_provider=lambda: token, ctid_trader_account_id=12345, account_alias="ct_demo", fill_timeout_s=3, clock=lambda: 1_700_000_000_000)


def test_adapter_authenticates_reads_and_trades_with_stop_in_the_same_request():
    fake = FakeCtrader(); ad = make_adapter(fake)
    acct = ad.sync_account()
    assert acct.equity == D("10053.09") and acct.balance == D("10053.09") and acct.verified and fake.host == "demo.ctraderapi.com"
    assert [n for n, _ in fake.requests[:2]] == ["ProtoOAApplicationAuthReq", "ProtoOAAccountAuthReq"]
    assert ad.symbols["EURUSD"].symbol_id == 1 and ad.symbols["EURUSD"].lots_to_volume(D("0.10")) == 1_000_000 and ad.symbols["XAUUSD"].lots_to_volume(D("0.5")) == 5000
    assert ad.heartbeat(now_ms=1).connected and ad.positions() == []
    cmd = OrderCommand("intent-42", "d" * 64, "k", "ct_demo", "ctrader", "EURUSD", Direction.LONG, "MARKET", D("0.10"), D("1.10008"), D("1.09808"), StopMode.VENUE, LossModel.STOP_DISTANCE, targets=(D("1.10608"),), strategy_id="FX-TREND-PULLBACK-01").sealed()
    rec = ad.submit(cmd, now_ms=5)
    assert rec.status == "FILLED" and rec.filled_qty == D("0.10") and rec.average_fill == D("1.10008") and rec.protective_stop_confirmed and rec.protective_stop_price == D("1.09808") and rec.broker_position_id == "100"
    assert rec.fees == D("3.5")
    req = next(b for n, b in fake.requests if n == "ProtoOANewOrderReq")
    assert req["relativeStopLoss"] == 200 and req["relativeTakeProfit"] == 600 and req["label"] == "vati:intent-42" and req["clientOrderId"] == "intent-42" and req["volume"] == 1_000_000 and "stopLoss" not in req
    pos = ad.positions()
    assert len(pos) == 1 and pos[0].trade_intent_id == "intent-42" and pos[0].quantity == D("0.10") and pos[0].stop_price == D("1.09808") and pos[0].direction is Direction.LONG
    # stops only tighten
    assert ad.modify_stop("100", D("1.09900"), now_ms=6).status == "ACCEPTED"
    assert ad.modify_stop("100", D("1.09000"), now_ms=7).reject_reason == "refusing to widen protective stop"
    assert ad.modify_stop("999", D("1.1"), now_ms=7).status == "REJECTED"
    closed = ad.close("100", None, now_ms=8, reason="TARGET")
    assert closed.status == "FILLED" and closed.average_fill == D("1.1050") and ad.positions() == []
    # rejections come back as receipts, never exceptions
    assert ad.submit(OrderCommand(**{**cmd.__dict__, "protective_stop": None, "command_hash": ""}).sealed(), now_ms=9).reject_reason.startswith("cTrader orders require")
    fake.reject_next_order = True
    r2 = ad.submit(cmd, now_ms=10)
    assert r2.status == "REJECTED" and r2.reject_reason == "NOT_ENOUGH_MONEY"
    tiny = OrderCommand(**{**cmd.__dict__, "quantity": D("0.001"), "command_hash": ""}).sealed()
    assert "below venue minimum" in ad.submit(tiny, now_ms=11).reject_reason
    assert ad.submit(OrderCommand(**{**cmd.__dict__, "symbol": "GBPJPY", "command_hash": ""}).sealed(), now_ms=12).reject_reason.startswith("symbol GBPJPY not available")
    # spots + trendbars
    ad.subscribe_spots("EURUSD"); time.sleep(0.05)
    assert ad.spot("EURUSD") == (D("1.101"), D("1.10108"))
    bars = trendbars(ad, "EURUSD", "H1", from_ms=0, to_ms=10)
    assert len(bars) == 3 and bars[0].low == D("1.1") and bars[0].open == D("1.10005") and bars[0].close == D("1.10012") and bars[0].high == D("1.1002") and bars[1].start_ms - bars[0].start_ms == 3_600_000
    time.sleep(0.12); ad.heartbeat(now_ms=2)
    assert any(n == "ProtoHeartbeatEvent" for n, _ in fake.requests)


def test_bad_credentials_and_disconnect_fail_closed():
    fake = FakeCtrader()
    with pytest.raises(CtraderApiError, match="CH_CLIENT_AUTH_FAILURE"):
        make_adapter(fake, secret="wrong").sync_account()
    fake2 = FakeCtrader()
    with pytest.raises(CtraderApiError, match="bad token"):
        make_adapter(fake2, token="nope").sync_account()
    fake3 = FakeCtrader(); ad = make_adapter(fake3); ad.sync_account()
    fake3.b.close()
    with pytest.raises(CtraderError):
        ad.transport.call("ProtoOATraderReq", {"ctidTraderAccountId": 12345})
    assert not ad.heartbeat(now_ms=1).connected
    dead = CtraderTransport(host="127.0.0.1", port=1, timeout_s=1)
    with pytest.raises(CtraderError, match="connect failed"):
        dead.call("ProtoHeartbeatEvent", {})


def test_oauth_helpers_and_account_discovery():
    assert authorize_url("cid", "https://gw/cb", state="s1") == "https://openapi.ctrader.com/apps/auth?client_id=cid&redirect_uri=https%3A%2F%2Fgw%2Fcb&scope=trading&state=s1"
    calls = []
    def http(url, params):
        calls.append((url, params))
        return {"accessToken": "at", "refreshToken": "rt", "expiresIn": 2628000, "tokenType": "bearer"} if params.get("code") == "good" else {"errorCode": "INVALID_GRANT", "description": "expired"}
    tok = exchange_code("cid", "sec", "good", "https://gw/cb", http=http)
    assert tok == {"access_token": "at", "refresh_token": "rt", "expires_in": 2628000, "token_type": "bearer"} and calls[0][1]["grant_type"] == "authorization_code"
    with pytest.raises(ValueError, match="INVALID_GRANT"):
        exchange_code("cid", "sec", "bad", "https://gw/cb", http=http)
    fake = FakeCtrader()
    t = CtraderTransport(connector=fake.connector, timeout_s=3)
    accts = discover_accounts(t, client_id="app-id", client_secret="app-secret", access_token="tok")
    assert accts == [{"ctid_trader_account_id": 12345, "is_live": False, "trader_login": 5551234, "broker": "FP Markets"}]


def test_registry_and_service_know_ctrader(tmp_path):
    from vati.accounts import Account, AccountRegistry, CredentialRef
    reg = AccountRegistry(tmp_path / "a.json")
    sec = tmp_path / "ct.env"; sec.write_text("CTRADER_CLIENT_ID=app-id\nCTRADER_CLIENT_SECRET=s\nCTRADER_ACCESS_TOKEN=tok\nCTRADER_REFRESH_TOKEN=rt\n"); sec.chmod(0o600)
    a = reg.add(Account(alias="ct_demo", broker="CTRADER", mode="DEMO_TRADER", currency="USD", server="demo", login="12345", credential_ref=CredentialRef(secrets_file=str(sec))))
    assert a.router_venue == "ctrader" and a.safety_identity == "DEMO"
    from vati.app.service import build_adapter
    ad = build_adapter(a, reg)
    assert isinstance(ad, CtraderAdapter) and ad.ctid_trader_account_id == 12345 and ad.transport.host == "demo.ctraderapi.com" and ad.client_id == "app-id"
