//+------------------------------------------------------------------+
//| VanBridgeEA.mq5 — Van MT5 pull-bridge Expert Advisor (Rev 5 route 4)|
//|                                                                    |
//| Runs inside the MT5 terminal (MetaQuotes VPS, broker VPS or any   |
//| terminal) and PULLS signed commands from van-trading-core every   |
//| PollMs. It never decides size, never opens a position without a   |
//| stop loss, never widens a stop, and reports account + positions   |
//| on every poll so the Linux core always has venue truth.           |
//|                                                                    |
//| Wire: POST {BridgeUrl}/ea/v1/{Alias}/poll  (JSON body)             |
//|   X-Van-Ts, X-Van-Nonce, X-Van-Signature =                         |
//|   HMAC-SHA256(SigningKey, ts + "\n" + nonce + "\n" + alias + "\n" + SHA256hex(body)) |
//| Reply: one command per line                                        |
//|   id|op|symbol|type|volume|price|sl|tp|position|comment|magic|deviation |
//|                                                                    |
//| Terminal setting required: Tools ▸ Options ▸ Expert Advisors ▸    |
//| "Allow WebRequest for listed URL" → add BridgeUrl.                 |
//+------------------------------------------------------------------+
#property copyright "Van trading system"
#property version   "1.00"
#property strict
#include <Trade\Trade.mqh>

input string BridgeUrl   = "https://trading.example.com";   // van-trading-core pull endpoint (public TLS name)
input string Alias       = "mt5_ea";                        // account alias registered on van-trading-core
input string SigningKey  = "";                              // 32+ char key issued by the Van app for this alias
input int    PollMs      = 1000;                            // poll interval
input int    TimeoutMs   = 5000;                            // WebRequest timeout

CTrade   trade;
string   pendingResults[];   // JSON objects to report on the next poll
long     nonceCounter = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   if(StringLen(SigningKey) < 32) { Print("VanBridgeEA: SigningKey must be at least 32 characters"); return(INIT_PARAMETERS_INCORRECT); }
   if(StringFind(BridgeUrl, "https://") != 0) { Print("VanBridgeEA: BridgeUrl must be https"); return(INIT_PARAMETERS_INCORRECT); }
   trade.SetAsyncMode(false);
   EventSetMillisecondTimer(PollMs);
   Print("VanBridgeEA started for alias ", Alias, " → ", BridgeUrl);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) { EventKillTimer(); }

//+------------------------------------------------------------------+
//| crypto helpers                                                     |
//+------------------------------------------------------------------+
string HexOf(const uchar &data[])
{
   string s = "";
   for(int i = 0; i < ArraySize(data); i++) s += StringFormat("%02x", data[i]);
   return s;
}

bool Sha256(const uchar &data[], uchar &out[])
{
   uchar key[];
   return CryptEncode(CRYPT_HASH_SHA256, data, key, out) > 0;
}

// HMAC-SHA256 per RFC 2104 with a 64-byte block.
string HmacSha256Hex(const string keyStr, const uchar &msg[])
{
   uchar key[]; StringToCharArray(keyStr, key, 0, StringLen(keyStr), CP_UTF8);
   if(ArraySize(key) > 64) { uchar kh[]; Sha256(key, kh); ArrayResize(key, 32); ArrayCopy(key, kh, 0, 0, 32); }
   uchar ipad[64], opad[64];
   for(int i = 0; i < 64; i++) { uchar k = (i < ArraySize(key)) ? key[i] : 0; ipad[i] = (uchar)(k ^ 0x36); opad[i] = (uchar)(k ^ 0x5c); }
   uchar inner[]; ArrayResize(inner, 64 + ArraySize(msg)); ArrayCopy(inner, ipad, 0, 0, 64); ArrayCopy(inner, msg, 64, 0, ArraySize(msg));
   uchar innerHash[]; Sha256(inner, innerHash);
   uchar outer[]; ArrayResize(outer, 64 + ArraySize(innerHash)); ArrayCopy(outer, opad, 0, 0, 64); ArrayCopy(outer, innerHash, 64, 0, ArraySize(innerHash));
   uchar mac[]; Sha256(outer, mac);
   return HexOf(mac);
}

string JsonEscape(string s) { StringReplace(s, "\\", "\\\\"); StringReplace(s, "\"", "\\\""); StringReplace(s, "\n", " "); return s; }

//+------------------------------------------------------------------+
//| snapshot                                                           |
//+------------------------------------------------------------------+
string SnapshotJson()
{
   string acct = StringFormat("{\"login\":%d,\"equity\":%.2f,\"balance\":%.2f,\"currency\":\"%s\",\"trade_allowed\":%s,\"hedging\":%s,\"server_time_ms\":%I64d}",
      (int)AccountInfoInteger(ACCOUNT_LOGIN), AccountInfoDouble(ACCOUNT_EQUITY), AccountInfoDouble(ACCOUNT_BALANCE), AccountInfoString(ACCOUNT_CURRENCY),
      (AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) && TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED)) ? "true" : "false",
      AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING ? "true" : "false", (long)TimeGMT() * 1000);
   string pos = "[";
   for(int i = 0; i < PositionsTotal(); i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket)) continue;
      if(i > 0 && StringLen(pos) > 1) pos += ",";
      pos += StringFormat("{\"ticket\":%I64u,\"symbol\":\"%s\",\"type\":\"%s\",\"volume\":%.2f,\"price_open\":%.5f,\"sl\":%.5f,\"tp\":%.5f,\"comment\":\"%s\",\"magic\":%I64d,\"profit\":%.2f}",
         ticket, PositionGetString(POSITION_SYMBOL), PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "BUY" : "SELL", PositionGetDouble(POSITION_VOLUME), PositionGetDouble(POSITION_PRICE_OPEN),
         PositionGetDouble(POSITION_SL), PositionGetDouble(POSITION_TP), JsonEscape(PositionGetString(POSITION_COMMENT)), PositionGetInteger(POSITION_MAGIC), PositionGetDouble(POSITION_PROFIT));
   }
   pos += "]";
   string res = "[";
   for(int i = 0; i < ArraySize(pendingResults); i++) { if(i > 0) res += ","; res += pendingResults[i]; }
   res += "]";
   return "{\"account\":" + acct + ",\"positions\":" + pos + ",\"results\":" + res + "}";
}

void PushResult(const string json) { int n = ArraySize(pendingResults); ArrayResize(pendingResults, n + 1); pendingResults[n] = json; }

//+------------------------------------------------------------------+
//| execution (SL required, tighten-only, no size decisions)          |
//+------------------------------------------------------------------+
void ExecOrderSend(const string id, const string symbol, const string side, double volume, double price, double sl, double tp, const string comment, long magic, int deviation, const string orderType)
{
   if(sl <= 0) { PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"reason\":\"no sl\"}", id)); return; }
   if(!SymbolSelect(symbol, true)) { PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"reason\":\"unknown symbol\"}", id)); return; }
   trade.SetExpertMagicNumber(magic);
   trade.SetDeviationInPoints(deviation);
   bool ok;
   if(orderType == "LIMIT") ok = (side == "BUY") ? trade.BuyLimit(volume, price, symbol, sl, tp, ORDER_TIME_GTC, 0, comment) : trade.SellLimit(volume, price, symbol, sl, tp, ORDER_TIME_GTC, 0, comment);
   else ok = (side == "BUY") ? trade.Buy(volume, symbol, 0.0, sl, tp, comment) : trade.Sell(volume, symbol, 0.0, sl, tp, comment);
   uint rc = trade.ResultRetcode();
   if(ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL))
   {
      ulong ticket = trade.ResultOrder();
      bool slConfirmed = false;
      if(PositionSelectByTicket(ticket)) slConfirmed = PositionGetDouble(POSITION_SL) > 0;
      PushResult(StringFormat("{\"id\":%s,\"status\":\"%s\",\"order\":%I64u,\"position\":%I64u,\"volume\":%.2f,\"price\":%.5f,\"arrival\":%.5f,\"sl_confirmed\":%s,\"server_time_ms\":%I64d,\"retcode\":%u}",
         id, rc == TRADE_RETCODE_DONE ? "FILLED" : "PARTIAL", ticket, ticket, trade.ResultVolume(), trade.ResultPrice(), trade.ResultPrice(), slConfirmed ? "true" : "false", (long)TimeGMT() * 1000, rc));
      // an entry that came back without its stop is flattened immediately: never hold an unprotected position
      if(!slConfirmed && orderType != "LIMIT") { trade.PositionClose(ticket); PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"reason\":\"stop not confirmed; position flattened\"}", id)); }
   }
   else if(ok && rc == TRADE_RETCODE_PLACED)
      PushResult(StringFormat("{\"id\":%s,\"status\":\"ACCEPTED\",\"order\":%I64u,\"sl_confirmed\":true,\"retcode\":%u}", id, trade.ResultOrder(), rc));
   else
      PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"reason\":\"%s\",\"retcode\":%u}", id, JsonEscape(trade.ResultRetcodeDescription()), rc));
}

void ExecModifySl(const string id, ulong ticket, double sl, double tp)
{
   if(!PositionSelectByTicket(ticket)) { PushResult(StringFormat("{\"id\":%s,\"ok\":false,\"reason\":\"position not found\"}", id)); return; }
   double oldSl = PositionGetDouble(POSITION_SL);
   bool isBuy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
   if(oldSl > 0 && ((isBuy && sl < oldSl) || (!isBuy && sl > oldSl))) { PushResult(StringFormat("{\"id\":%s,\"ok\":false,\"reason\":\"refusing to widen protective stop\"}", id)); return; }
   if(tp <= 0) tp = PositionGetDouble(POSITION_TP);
   bool ok = trade.PositionModify(ticket, sl, tp);
   PushResult(StringFormat("{\"id\":%s,\"ok\":%s,\"reason\":\"%s\",\"retcode\":%u}", id, ok ? "true" : "false", ok ? "" : JsonEscape(trade.ResultRetcodeDescription()), trade.ResultRetcode()));
}

void ExecClose(const string id, ulong ticket, double volume)
{
   if(!PositionSelectByTicket(ticket)) { PushResult(StringFormat("{\"id\":%s,\"status\":\"UNKNOWN\",\"reason\":\"position not found\"}", id)); return; }
   bool ok = (volume > 0 && volume < PositionGetDouble(POSITION_VOLUME)) ? trade.PositionClosePartial(ticket, volume) : trade.PositionClose(ticket);
   uint rc = trade.ResultRetcode();
   if(ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL))
      PushResult(StringFormat("{\"id\":%s,\"status\":\"FILLED\",\"volume\":%.2f,\"price\":%.5f}", id, trade.ResultVolume(), trade.ResultPrice()));
   else
      PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"reason\":\"%s\",\"retcode\":%u}", id, JsonEscape(trade.ResultRetcodeDescription()), rc));
}

//+------------------------------------------------------------------+
//| poll loop                                                          |
//+------------------------------------------------------------------+
void OnTimer()
{
   string body = SnapshotJson();
   uchar bodyBytes[]; StringToCharArray(body, bodyBytes, 0, StringLen(body), CP_UTF8);
   uchar bodyHash[]; Sha256(bodyBytes, bodyHash);
   string ts = IntegerToString((long)TimeGMT());
   nonceCounter++;
   string nonce = StringFormat("%I64d-%I64d", (long)TimeGMT(), nonceCounter);
   string canonical = ts + "\n" + nonce + "\n" + Alias + "\n" + HexOf(bodyHash);
   uchar canonBytes[]; StringToCharArray(canonical, canonBytes, 0, StringLen(canonical), CP_UTF8);
   string sig = HmacSha256Hex(SigningKey, canonBytes);
   string headers = "Content-Type: application/json\r\nX-Van-Ts: " + ts + "\r\nX-Van-Nonce: " + nonce + "\r\nX-Van-Signature: " + sig + "\r\n";
   uchar result[]; string resultHeaders;
   int code = WebRequest("POST", BridgeUrl + "/ea/v1/" + Alias + "/poll", headers, TimeoutMs, bodyBytes, result, resultHeaders);
   if(code != 200) { if(code == -1) Print("VanBridgeEA: WebRequest failed (add ", BridgeUrl, " to allowed URLs), error ", GetLastError()); else Print("VanBridgeEA: bridge HTTP ", code); return; }
   ArrayResize(pendingResults, 0);   // results delivered; the server acknowledged them with a 200
   string text = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
   string lines[]; int n = StringSplit(text, '\n', lines);
   for(int i = 0; i < n; i++)
   {
      if(StringLen(lines[i]) == 0) continue;
      string f[]; int k = StringSplit(lines[i], '|', f);
      if(k < 12) { Print("VanBridgeEA: malformed command line"); continue; }
      string id = f[0], op = f[1];
      if(op == "ORDER_SEND")      ExecOrderSend(id, f[2], f[3], StringToDouble(f[4]), StringToDouble(f[5]), StringToDouble(f[6]), StringToDouble(f[7]), f[9], StringToInteger(f[10]), (int)StringToInteger(f[11]), StringFind(f[9], "LIMIT") >= 0 ? "LIMIT" : "MARKET");
      else if(op == "MODIFY_SL")  ExecModifySl(id, (ulong)StringToInteger(f[8]), StringToDouble(f[6]), StringToDouble(f[7]));
      else if(op == "CLOSE")      ExecClose(id, (ulong)StringToInteger(f[8]), StringToDouble(f[4]));
      else PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"reason\":\"op not in contract\"}", id));
   }
   if(ArraySize(pendingResults) > 0) OnTimer();   // report executions without waiting a full interval
}
//+------------------------------------------------------------------+
