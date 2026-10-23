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
//|   id|op|symbol|type|volume|price|sl|tp|position|comment|magic|deviation|order_type|login|server_hex|currency_hex|demo |
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

// Seventeen significant digits round-trip native doubles. Never round a
// crypto-sized quantity to two decimals or an instrument price to five.
string JsonNumber(double value) { return MathIsValidNumber(value) ? StringFormat("%.17g", value) : "null"; }

// A timeout/connection loss is not proof that the venue refused an effect.
bool NativeRefusal(uint rc)
{
   return rc == TRADE_RETCODE_REJECT || rc == TRADE_RETCODE_INVALID
      || rc == TRADE_RETCODE_INVALID_VOLUME || rc == TRADE_RETCODE_INVALID_PRICE
      || rc == TRADE_RETCODE_INVALID_STOPS || rc == TRADE_RETCODE_TRADE_DISABLED
      || rc == TRADE_RETCODE_MARKET_CLOSED || rc == TRADE_RETCODE_NO_MONEY
      || rc == TRADE_RETCODE_PRICE_CHANGED || rc == TRADE_RETCODE_PRICE_OFF
      || rc == TRADE_RETCODE_INVALID_EXPIRATION || rc == TRADE_RETCODE_INVALID_FILL
      || rc == TRADE_RETCODE_INVALID_ORDER || rc == TRADE_RETCODE_LIMIT_ORDERS
      || rc == TRADE_RETCODE_LIMIT_VOLUME || rc == TRADE_RETCODE_LIMIT_POSITIONS
      || rc == TRADE_RETCODE_LONG_ONLY || rc == TRADE_RETCODE_SHORT_ONLY
      || rc == TRADE_RETCODE_CLOSE_ONLY || rc == TRADE_RETCODE_FIFO_CLOSE
      || rc == TRADE_RETCODE_HEDGE_PROHIBITED || rc == TRADE_RETCODE_CLIENT_DISABLES_AT
      || rc == TRADE_RETCODE_SERVER_DISABLES_AT;
}

// Order, deal, position identifier and position ticket are distinct native IDs.
// Resolve the deal's stable position identifier to exactly one current ticket;
// never fall back to an order ticket or a symbol-only guess.
ulong ResolvePositionTicket(ulong deal, const string symbol)
{
   if(deal == 0 || !HistoryDealSelect(deal)) return 0;
   long identifier = HistoryDealGetInteger(deal, DEAL_POSITION_ID);
   if(identifier <= 0) return 0;
   ulong found = 0;
   for(int i = 0; i < PositionsTotal(); i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket)) return 0;
      if(PositionGetInteger(POSITION_IDENTIFIER) != identifier || PositionGetString(POSITION_SYMBOL) != symbol) continue;
      if(found != 0) return 0;
      found = ticket;
   }
   return found;
}

string Utf8Hex(const string value)
{
   uchar data[]; StringToCharArray(value, data, 0, StringLen(value), CP_UTF8);
   return HexOf(data);
}

bool NativeIdentityMatches(const string &f[])
{
   if(ArraySize(f) != 17) return false;
   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(mode != ACCOUNT_TRADE_MODE_DEMO && mode != ACCOUNT_TRADE_MODE_REAL) return false;
   return f[13] == IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))
      && f[14] == Utf8Hex(AccountInfoString(ACCOUNT_SERVER))
      && f[15] == Utf8Hex(AccountInfoString(ACCOUNT_CURRENCY))
      && f[16] == (mode == ACCOUNT_TRADE_MODE_DEMO ? "true" : "false");
}

//+------------------------------------------------------------------+
//| snapshot                                                           |
//+------------------------------------------------------------------+
string SnapshotJson()
{
   long accountMode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   string accountDemo = accountMode == ACCOUNT_TRADE_MODE_DEMO ? "true" : accountMode == ACCOUNT_TRADE_MODE_REAL ? "false" : "null";
   string acct = StringFormat("{\"login\":%I64d,\"server\":\"%s\",\"demo\":%s,\"equity\":%s,\"balance\":%s,\"currency\":\"%s\",\"trade_allowed\":%s,\"hedging\":%s,\"server_time_ms\":%I64d}",
      AccountInfoInteger(ACCOUNT_LOGIN), JsonEscape(AccountInfoString(ACCOUNT_SERVER)), accountDemo,
      JsonNumber(AccountInfoDouble(ACCOUNT_EQUITY)), JsonNumber(AccountInfoDouble(ACCOUNT_BALANCE)), JsonEscape(AccountInfoString(ACCOUNT_CURRENCY)),
      (AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) && AccountInfoInteger(ACCOUNT_TRADE_EXPERT) && TerminalInfoInteger(TERMINAL_CONNECTED) && TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED)) ? "true" : "false",
      AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING ? "true" : "false", (long)TimeGMT() * 1000);
   string pos = "[";
   for(int i = 0; i < PositionsTotal(); i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket)) { pos = "null"; break; }
      if(i > 0 && StringLen(pos) > 1) pos += ",";
      pos += StringFormat("{\"ticket\":%I64u,\"symbol\":\"%s\",\"type\":\"%s\",\"volume\":%s,\"price_open\":%s,\"sl\":%s,\"tp\":%s,\"comment\":\"%s\",\"magic\":%I64d,\"profit\":%s}",
         ticket, JsonEscape(PositionGetString(POSITION_SYMBOL)), PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "BUY" : "SELL", JsonNumber(PositionGetDouble(POSITION_VOLUME)), JsonNumber(PositionGetDouble(POSITION_PRICE_OPEN)),
         JsonNumber(PositionGetDouble(POSITION_SL)), JsonNumber(PositionGetDouble(POSITION_TP)), JsonEscape(PositionGetString(POSITION_COMMENT)), PositionGetInteger(POSITION_MAGIC), JsonNumber(PositionGetDouble(POSITION_PROFIT)));
   }
   if(pos != "null") pos += "]";
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
   if(!MathIsValidNumber(sl) || sl <= 0 || !MathIsValidNumber(volume) || volume <= 0 || !MathIsValidNumber(price) || !MathIsValidNumber(tp) || tp < 0 || (side != "BUY" && side != "SELL") || (orderType != "MARKET" && orderType != "LIMIT") || (orderType == "LIMIT" && price <= 0))
   { PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"volume\":\"0\",\"reason\":\"invalid native entry parameters or protective stop\"}", id)); return; }
   if(!TerminalInfoInteger(TERMINAL_CONNECTED) || !TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_EXPERT) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
   { PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"volume\":\"0\",\"reason\":\"current native entry permission unavailable\"}", id)); return; }
   if(!SymbolSelect(symbol, true)) { PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"reason\":\"unknown symbol\"}", id)); return; }
   // This route has no aggregate netting ownership/allocation contract. A new
   // entry must not close somebody else's lot or reset its protective stop.
   if(AccountInfoInteger(ACCOUNT_MARGIN_MODE) != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
   {
      bool clear = true;
      for(int i = 0; i < PositionsTotal(); i++)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0 || !PositionSelectByTicket(ticket) || PositionGetString(POSITION_SYMBOL) == symbol) { clear = false; break; }
      }
      for(int i = 0; clear && i < OrdersTotal(); i++)
      {
         ulong ticket = OrderGetTicket(i);
         if(ticket == 0 || !OrderSelect(ticket) || OrderGetString(ORDER_SYMBOL) == symbol) { clear = false; break; }
      }
      if(!clear) { PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"volume\":\"0\",\"reason\":\"netting symbol has existing or unknown exposure; allocation reconciliation required\"}", id)); return; }
   }
   trade.SetExpertMagicNumber(magic);
   trade.SetDeviationInPoints(deviation);
   bool ok;
   if(orderType == "LIMIT") ok = (side == "BUY") ? trade.BuyLimit(volume, price, symbol, sl, tp, ORDER_TIME_GTC, 0, comment) : trade.SellLimit(volume, price, symbol, sl, tp, ORDER_TIME_GTC, 0, comment);
   else ok = (side == "BUY") ? trade.Buy(volume, symbol, 0.0, sl, tp, comment) : trade.Sell(volume, symbol, 0.0, sl, tp, comment);
   uint rc = trade.ResultRetcode();
   if(ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL))
   {
      // Capture the entry result before any protective action overwrites CTrade.
      ulong order = trade.ResultOrder();
      ulong deal = trade.ResultDeal();
      double filled = trade.ResultVolume(), fillPrice = trade.ResultPrice();
      ulong ticket = ResolvePositionTicket(deal, symbol);
      bool slConfirmed = false;
      if(ticket != 0 && PositionSelectByTicket(ticket))
      {
         double actualSl = PositionGetDouble(POSITION_SL);
         slConfirmed = actualSl > 0 && ((side == "BUY" && actualSl >= sl) || (side == "SELL" && actualSl <= sl));
      }
      string recovery = "null";
      // Preserve the original fill, and record the separate emergency close.
      // An unavailable ticket must never target an unrelated order/position.
      if(!slConfirmed && ticket != 0)
      {
         bool closed = trade.PositionClose(ticket);
         uint closeRc = trade.ResultRetcode();
         string closeStatus = closed && closeRc == TRADE_RETCODE_DONE ? "FILLED" : closed && closeRc == TRADE_RETCODE_DONE_PARTIAL ? "PARTIAL" : NativeRefusal(closeRc) ? "REJECTED" : "UNKNOWN";
         recovery = StringFormat("{\"status\":\"%s\",\"position\":%I64u,\"volume\":%s,\"retcode\":%u}", closeStatus, ticket, JsonNumber(trade.ResultVolume()), closeRc);
      }
      PushResult(StringFormat("{\"id\":%s,\"status\":\"%s\",\"order\":%I64u,\"deal\":%I64u,\"position\":%s,\"volume\":%s,\"price\":%s,\"sl_confirmed\":%s,\"protection_recovery\":%s,\"server_time_ms\":%I64d,\"retcode\":%u}",
         id, rc == TRADE_RETCODE_DONE ? "FILLED" : "PARTIAL", order, deal, ticket != 0 ? StringFormat("%I64u", ticket) : "null", JsonNumber(filled), JsonNumber(fillPrice), slConfirmed ? "true" : "false", recovery, (long)TimeGMT() * 1000, rc));
   }
   else if(ok && rc == TRADE_RETCODE_PLACED)
   {
      ulong order = trade.ResultOrder();
      bool confirmed = OrderSelect(order) && OrderGetString(ORDER_SYMBOL) == symbol && OrderGetDouble(ORDER_SL) > 0 && ((side == "BUY" && OrderGetDouble(ORDER_SL) >= sl) || (side == "SELL" && OrderGetDouble(ORDER_SL) <= sl));
      PushResult(StringFormat("{\"id\":%s,\"status\":\"ACCEPTED\",\"order\":%I64u,\"sl_confirmed\":%s,\"retcode\":%u}", id, order, confirmed ? "true" : "false", rc));
   }
   else
      PushResult(StringFormat("{\"id\":%s,\"status\":\"%s\",\"reason\":\"%s\",\"retcode\":%u}", id, NativeRefusal(rc) ? "REJECTED" : "UNKNOWN", JsonEscape(trade.ResultRetcodeDescription()), rc));
}

void ExecModifySl(const string id, ulong ticket, double sl, double tp)
{
   if(!MathIsValidNumber(sl) || sl <= 0) { PushResult(StringFormat("{\"id\":%s,\"ok\":false,\"reason\":\"positive finite stop required\"}", id)); return; }
   if(!PositionSelectByTicket(ticket)) { PushResult(StringFormat("{\"id\":%s,\"ok\":false,\"reason\":\"position not found\"}", id)); return; }
   double oldSl = PositionGetDouble(POSITION_SL);
   bool isBuy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
   if(oldSl > 0 && ((isBuy && sl < oldSl) || (!isBuy && sl > oldSl))) { PushResult(StringFormat("{\"id\":%s,\"ok\":false,\"reason\":\"refusing to widen protective stop\"}", id)); return; }
   if(tp <= 0) tp = PositionGetDouble(POSITION_TP);
   bool ok = trade.PositionModify(ticket, sl, tp);
   uint rc = trade.ResultRetcode();
   bool confirmed = false;
   if(ok && rc == TRADE_RETCODE_DONE && PositionSelectByTicket(ticket))
   {
      double actualSl = PositionGetDouble(POSITION_SL);
      confirmed = actualSl > 0 && (isBuy ? actualSl >= sl : actualSl <= sl);
   }
   PushResult(StringFormat("{\"id\":%s,\"ok\":%s,\"reason\":\"%s\",\"retcode\":%u}", id, confirmed ? "true" : NativeRefusal(rc) ? "false" : "null", confirmed ? "" : JsonEscape(trade.ResultRetcodeDescription()), rc));
}

void ExecClose(const string id, ulong ticket, double volume)
{
   if(!PositionSelectByTicket(ticket)) { PushResult(StringFormat("{\"id\":%s,\"status\":\"UNKNOWN\",\"reason\":\"position not found\"}", id)); return; }
   bool ok = (volume > 0 && volume < PositionGetDouble(POSITION_VOLUME)) ? trade.PositionClosePartial(ticket, volume) : trade.PositionClose(ticket);
   uint rc = trade.ResultRetcode();
   if(ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL))
      PushResult(StringFormat("{\"id\":%s,\"status\":\"%s\",\"volume\":%s,\"price\":%s,\"retcode\":%u}", id, rc == TRADE_RETCODE_DONE ? "FILLED" : "PARTIAL", JsonNumber(trade.ResultVolume()), JsonNumber(trade.ResultPrice()), rc));
   else
      PushResult(StringFormat("{\"id\":%s,\"status\":\"%s\",\"reason\":\"%s\",\"retcode\":%u}", id, NativeRefusal(rc) ? "REJECTED" : "UNKNOWN", JsonEscape(trade.ResultRetcodeDescription()), rc));
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
      if(!NativeIdentityMatches(f))
      {
         PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"ok\":false,\"volume\":\"0\",\"reason\":\"native physical identity binding differs\"}", id));
         continue;
      }
      if(op == "ORDER_SEND" && f[12] != "MARKET" && f[12] != "LIMIT")
      {
         PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"volume\":\"0\",\"reason\":\"unsupported explicit order type\"}", id));
         continue;
      }
      if(op == "ORDER_SEND")      ExecOrderSend(id, f[2], f[3], StringToDouble(f[4]), StringToDouble(f[5]), StringToDouble(f[6]), StringToDouble(f[7]), f[9], StringToInteger(f[10]), (int)StringToInteger(f[11]), f[12]);
      else if(op == "MODIFY_SL")  ExecModifySl(id, (ulong)StringToInteger(f[8]), StringToDouble(f[6]), StringToDouble(f[7]));
      else if(op == "CLOSE")      ExecClose(id, (ulong)StringToInteger(f[8]), StringToDouble(f[4]));
      else PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"reason\":\"op not in contract\"}", id));
   }
   if(ArraySize(pendingResults) > 0) OnTimer();   // report executions without waiting a full interval
}
//+------------------------------------------------------------------+
