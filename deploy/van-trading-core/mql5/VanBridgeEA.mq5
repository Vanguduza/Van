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
   if(ArraySize(f) != 17 && ArraySize(f) != 18) return false;
   if(ArraySize(f) != ((f[1] == "ORDER_SEND_EXPIRING" || f[1] == "MARGIN_QUOTE" || f[1] == "SYMBOL_CONTRACT" || f[1] == "QUOTE_SNAPSHOT") ? 18 : 17)) return false;
   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(mode != ACCOUNT_TRADE_MODE_DEMO && mode != ACCOUNT_TRADE_MODE_REAL) return false;
   return f[13] == IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))
      && f[14] == Utf8Hex(AccountInfoString(ACCOUNT_SERVER))
      && f[15] == Utf8Hex(AccountInfoString(ACCOUNT_CURRENCY))
      && f[16] == (mode == ACCOUNT_TRADE_MODE_DEMO ? "true" : "false");
}

bool NativeEntryDeadline(const string &f[], long &deadlineMs)
{
   deadlineMs = 0;
   if(ArraySize(f) == 17 && f[1] == "ORDER_SEND") return true;
   if(ArraySize(f) != 18 || f[1] != "ORDER_SEND_EXPIRING") return false;
   deadlineMs = StringToInteger(f[17]);
   return deadlineMs > 0 && IntegerToString(deadlineMs) == f[17];
}

bool NativeEntryDeadlineCurrent(long deadlineMs)
{
   if(deadlineMs == 0) return true; // Existing explicitly unbounded legacy frame.
   long nowSeconds = (long)TimeGMT();
   // TimeGMT has second resolution. Refuse uncertainty inside that second;
   // rounding the original deadline up would silently extend its authority.
   return nowSeconds > 0 && nowSeconds * 1000 + 999 < deadlineMs;
}

// Native cash selection uses terminal time; it is not a UTC or settlement certificate.
string NativeBindingJson()
{
   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   return StringFormat("{\"login\":%I64d,\"server\":\"%s\",\"currency\":\"%s\",\"demo\":%s}",
      AccountInfoInteger(ACCOUNT_LOGIN), JsonEscape(AccountInfoString(ACCOUNT_SERVER)),
      JsonEscape(AccountInfoString(ACCOUNT_CURRENCY)), mode == ACCOUNT_TRADE_MODE_DEMO ? "true" : mode == ACCOUNT_TRADE_MODE_REAL ? "false" : "null");
}

string CashUnavailable(const string reason)
{
   return "{\"schema\":\"van.mt5.cash-telemetry/1\",\"complete\":false,\"reason\":\"" + reason + "\"}";
}

string NativeCashJson()
{
   ResetLastError();
   string bindingBefore = NativeBindingJson();
   double balanceBefore = AccountInfoDouble(ACCOUNT_BALANCE);
   double creditBefore = AccountInfoDouble(ACCOUNT_CREDIT);
   if(GetLastError() != 0 || !MathIsValidNumber(balanceBefore) || !MathIsValidNumber(creditBefore))
      return CashUnavailable("NATIVE_ACCOUNT_FUNDS_UNAVAILABLE");
   datetime queryTo = TimeCurrent() + 1;
   if(!HistorySelect((datetime)0, queryTo)) return CashUnavailable("HISTORY_SELECT_UNAVAILABLE");
   int total = HistoryDealsTotal();
   if(total < 0 || total > 200000) return CashUnavailable("HISTORY_SELECTION_RESOURCE_BOUND");
   string rows = "["; int cashCount = 0;
   for(int i = 0; i < total; i++)
   {
      ResetLastError();
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0 || GetLastError() != 0) return CashUnavailable("NATIVE_DEAL_UNAVAILABLE");
      ResetLastError();
      long rawType = HistoryDealGetInteger(ticket, DEAL_TYPE);
      if(GetLastError() != 0) return CashUnavailable("NATIVE_DEAL_TYPE_UNAVAILABLE");
      if(rawType == DEAL_TYPE_BUY || rawType == DEAL_TYPE_SELL) continue;
      if(cashCount >= 4096) return CashUnavailable("CASH_FACT_RESOURCE_BOUND");
      ResetLastError();
      long at = HistoryDealGetInteger(ticket, DEAL_TIME_MSC);
      double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
      double commission = HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      double swap = HistoryDealGetDouble(ticket, DEAL_SWAP);
      double fee = HistoryDealGetDouble(ticket, DEAL_FEE);
      if(GetLastError() != 0 || at < 0 || !MathIsValidNumber(profit) || !MathIsValidNumber(commission)
         || !MathIsValidNumber(swap) || !MathIsValidNumber(fee)) return CashUnavailable("NATIVE_CASH_VALUES_UNAVAILABLE");
      if(cashCount > 0) rows += ",";
      rows += StringFormat("{\"native_id\":%I64u,\"operation\":\"%s\",\"native_time_ms\":%I64d,\"profit\":\"%s\",\"commission\":\"%s\",\"swap\":\"%s\",\"fee\":\"%s\"}",
         ticket, JsonEscape(EnumToString((ENUM_DEAL_TYPE)rawType)), at, DoubleToString(profit,-16), DoubleToString(commission,-16), DoubleToString(swap,-16), DoubleToString(fee,-16));
      cashCount++;
   }
   rows += "]";
   long nativeClock = (long)TimeCurrent() * 1000;
   ResetLastError();
   string bindingAfter = NativeBindingJson();
   double balanceAfter = AccountInfoDouble(ACCOUNT_BALANCE), creditAfter = AccountInfoDouble(ACCOUNT_CREDIT);
   if(GetLastError() != 0 || bindingAfter != bindingBefore || balanceAfter != balanceBefore
      || creditAfter != creditBefore || nativeClock > (long)queryTo*1000)
      return CashUnavailable("ACCOUNT_CHANGED_DURING_CASH_READ");
   return StringFormat("{\"schema\":\"van.mt5.cash-telemetry/1\",\"complete\":true,\"native_from_ms\":0,\"native_to_ms\":%I64d,\"native_clock_ms\":%I64d,\"binding_before\":%s,\"balance_before\":\"%s\",\"credit_before\":\"%s\",\"movements\":%s}",
      (long)queryTo*1000, nativeClock, bindingBefore, DoubleToString(balanceBefore,-16), DoubleToString(creditBefore,-16), rows);
}

//+------------------------------------------------------------------+
//| snapshot                                                           |
//+------------------------------------------------------------------+
string NativeMarginJson()
{
   ResetLastError();
   double used = AccountInfoDouble(ACCOUNT_MARGIN);
   int usedError = GetLastError();
   ResetLastError();
   double free = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   int freeError = GetLastError();
   ResetLastError();
   double level = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);
   int levelError = GetLastError();
   if(usedError != 0 || freeError != 0 || levelError != 0 || used < 0
      || !MathIsValidNumber(used) || !MathIsValidNumber(free) || !MathIsValidNumber(level))
      return "\"margin_used\":null,\"margin_free\":null,\"margin_level\":null";
   return StringFormat("\"margin_used\":\"%s\",\"margin_free\":\"%s\",\"margin_level\":\"%s\"",
      DoubleToString(used,-16), DoubleToString(free,-16), DoubleToString(level,-16));
}

string SnapshotJson()
{
   string funding = NativeCashJson();
   long accountMode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   string accountDemo = accountMode == ACCOUNT_TRADE_MODE_DEMO ? "true" : accountMode == ACCOUNT_TRADE_MODE_REAL ? "false" : "null";
   string acct = StringFormat("{\"login\":%I64d,\"server\":\"%s\",\"demo\":%s,\"equity\":\"%s\",\"balance\":\"%s\",\"credit\":\"%s\",\"currency_digits\":%I64d,\"currency\":\"%s\",\"trade_allowed\":%s,\"hedging\":%s,\"server_time_ms\":%I64d,\"funding\":%s,%s,\"entry_constraints\":{\"schema\":\"van.mt5.ea-entry-constraints/1\",\"explicit_deadline\":true,\"required_op\":\"ORDER_SEND_EXPIRING\",\"framed_fields\":18},\"expected_margin_constraints\":{\"schema\":\"van.mt5.ea-margin-constraints/1\",\"required_op\":\"MARGIN_QUOTE\",\"framed_fields\":18,\"explicit_deadline\":true},\"symbol_contract_constraints\":{\"schema\":\"van.mt5.ea-symbol-constraints/1\",\"required_op\":\"SYMBOL_CONTRACT\",\"framed_fields\":18,\"explicit_deadline\":true},\"quote_snapshot_constraints\":{\"schema\":\"van.mt5.ea-quote-constraints/1\",\"required_op\":\"QUOTE_SNAPSHOT\",\"framed_fields\":18,\"explicit_deadline\":true}}",
      AccountInfoInteger(ACCOUNT_LOGIN), JsonEscape(AccountInfoString(ACCOUNT_SERVER)), accountDemo,
      DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),-16), DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),-16),
      DoubleToString(AccountInfoDouble(ACCOUNT_CREDIT),-16), AccountInfoInteger(ACCOUNT_CURRENCY_DIGITS), JsonEscape(AccountInfoString(ACCOUNT_CURRENCY)),
      (AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) && AccountInfoInteger(ACCOUNT_TRADE_EXPERT) && TerminalInfoInteger(TERMINAL_CONNECTED) && TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED)) ? "true" : "false",
      AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING ? "true" : "false", (long)TimeGMT() * 1000, funding, NativeMarginJson());
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
   string orders = "[";
   for(int i = 0; i < OrdersTotal(); i++)
   {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0 || !OrderSelect(ticket)) { orders = "null"; break; }
      if(i > 0) orders += ",";
      orders += StringFormat("{\"ticket\":%I64u,\"symbol\":\"%s\",\"type\":%I64d,\"volume\":%s,\"price\":%s,\"sl\":%s,\"tp\":%s,\"comment\":\"%s\",\"magic\":%I64d}",
         ticket, JsonEscape(OrderGetString(ORDER_SYMBOL)), OrderGetInteger(ORDER_TYPE),
         JsonNumber(OrderGetDouble(ORDER_VOLUME_CURRENT)), JsonNumber(OrderGetDouble(ORDER_PRICE_OPEN)),
         JsonNumber(OrderGetDouble(ORDER_SL)), JsonNumber(OrderGetDouble(ORDER_TP)),
         JsonEscape(OrderGetString(ORDER_COMMENT)), OrderGetInteger(ORDER_MAGIC));
   }
   if(orders != "null") orders += "]";
   string res = "[";
   for(int i = 0; i < ArraySize(pendingResults); i++) { if(i > 0) res += ","; res += pendingResults[i]; }
   res += "]";
   return "{\"account\":" + acct + ",\"positions\":" + pos + ",\"orders\":" + orders + ",\"results\":" + res + "}";
}

void PushResult(const string json) { int n = ArraySize(pendingResults); ArrayResize(pendingResults, n + 1); pendingResults[n] = json; }

// Read-only native calculation. The core rechecks exact decimal increments;
// neither this result nor its native double format grants a reservation.
string MarginReadAccountJson()
{
   ResetLastError();
   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   string demo = mode == ACCOUNT_TRADE_MODE_DEMO ? "true" : mode == ACCOUNT_TRADE_MODE_REAL ? "false" : "null";
   long marginMode = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   string value = StringFormat("{\"login\":%I64d,\"server\":\"%s\",\"demo\":%s,\"currency\":\"%s\",\"currency_digits\":%I64d,\"leverage\":%I64d,\"margin_mode\":%I64d,\"hedging\":%s,\"balance\":\"%s\",\"equity\":\"%s\",\"credit\":\"%s\"}",
      AccountInfoInteger(ACCOUNT_LOGIN),JsonEscape(AccountInfoString(ACCOUNT_SERVER)),demo,
      JsonEscape(AccountInfoString(ACCOUNT_CURRENCY)),AccountInfoInteger(ACCOUNT_CURRENCY_DIGITS),
      AccountInfoInteger(ACCOUNT_LEVERAGE),marginMode,marginMode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING ? "true" : "false",
      DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),-16),DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),-16),DoubleToString(AccountInfoDouble(ACCOUNT_CREDIT),-16));
   return GetLastError()==0 ? value : "";
}

string MarginReadAccountScopeJson()
{
   return StringFormat("%I64d|%s|%s|%I64d|%I64d|%I64d|%I64d",
      AccountInfoInteger(ACCOUNT_LOGIN),AccountInfoString(ACCOUNT_SERVER),AccountInfoString(ACCOUNT_CURRENCY),
      AccountInfoInteger(ACCOUNT_TRADE_MODE),AccountInfoInteger(ACCOUNT_CURRENCY_DIGITS),
      AccountInfoInteger(ACCOUNT_LEVERAGE),AccountInfoInteger(ACCOUNT_MARGIN_MODE));
}

string MarginReadContractJson(const string symbol)
{
   double minimum=0,step=0,maximum=0,tick=0;
   if(!SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN,minimum) || !SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP,step)
      || !SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX,maximum) || !SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE,tick)
      || !MathIsValidNumber(minimum) || !MathIsValidNumber(step) || !MathIsValidNumber(maximum) || !MathIsValidNumber(tick)
      || minimum<=0 || step<=0 || maximum<minimum || tick<=0) return "";
   // Retain the original binary64 round-trip text. The receiver reconstructs
   // the same native double before the shared decimal increment checks.
   return StringFormat("{\"symbol\":\"%s\",\"volume_min\":\"%s\",\"volume_step\":\"%s\",\"volume_max\":\"%s\",\"trade_tick_size\":\"%s\",\"native_numeric_format\":\"MQL_BINARY64_ROUNDTRIP\"}",
      JsonEscape(symbol),DoubleToString(minimum,-16),DoubleToString(step,-16),DoubleToString(maximum,-16),DoubleToString(tick,-16));
}

string NativeSymbolContractJson(const string symbol)
{
   ENUM_SYMBOL_INFO_DOUBLE doubles[]={SYMBOL_VOLUME_MIN,SYMBOL_VOLUME_STEP,SYMBOL_VOLUME_MAX,SYMBOL_POINT,
      SYMBOL_TRADE_CONTRACT_SIZE,SYMBOL_TRADE_TICK_SIZE,SYMBOL_TRADE_TICK_VALUE,
      SYMBOL_TRADE_TICK_VALUE_PROFIT,SYMBOL_TRADE_TICK_VALUE_LOSS};
   string names[]={"volume_min","volume_step","volume_max","point","trade_contract_size",
      "trade_tick_size","trade_tick_value","trade_tick_value_profit","trade_tick_value_loss"};
   string value=StringFormat("{\"symbol\":\"%s\"",JsonEscape(symbol));
   double minimum=0,maximum=0;
   for(int i=0;i<ArraySize(doubles);i++)
   {
      double number=0;
      if(!SymbolInfoDouble(symbol,doubles[i],number) || !MathIsValidNumber(number)
         || (i<6 ? number<=0 : number<0)) return "";
      if(i==0) minimum=number;
      if(i==2) maximum=number;
      value+=StringFormat(",\"%s\":\"%s\"",names[i],DoubleToString(number,-16));
   }
   if(maximum<minimum) return "";
   ENUM_SYMBOL_INFO_INTEGER integers[]={SYMBOL_DIGITS,SYMBOL_TRADE_STOPS_LEVEL,SYMBOL_TRADE_FREEZE_LEVEL,
      SYMBOL_TRADE_MODE,SYMBOL_TRADE_CALC_MODE,SYMBOL_SPREAD};
   string integerNames[]={"digits","trade_stops_level","trade_freeze_level","trade_mode","trade_calc_mode","spread"};
   for(int i=0;i<ArraySize(integers);i++)
   {
      long number=0;
      if(!SymbolInfoInteger(symbol,integers[i],number) || number<0 || number>2147483647) return "";
      value+=StringFormat(",\"%s\":%I64d",integerNames[i],number);
   }
   ENUM_SYMBOL_INFO_STRING strings[]={SYMBOL_CURRENCY_BASE,SYMBOL_CURRENCY_PROFIT,SYMBOL_CURRENCY_MARGIN};
   string stringNames[]={"currency_base","currency_profit","currency_margin"};
   for(int i=0;i<ArraySize(strings);i++)
   {
      string text="";
      if(!SymbolInfoString(symbol,strings[i],text) || StringLen(text)>64) return "";
      value+=StringFormat(",\"%s\":\"%s\"",stringNames[i],JsonEscape(text));
   }
   return value+"}";
}

string NativeQuoteContractScope(const string symbol)
{
   ResetLastError();
   string value=StringFormat("%s|%s|%s|%s|%s|%s|%I64d|%I64d",symbol,
      SymbolInfoString(symbol,SYMBOL_CURRENCY_BASE),SymbolInfoString(symbol,SYMBOL_CURRENCY_PROFIT),
      SymbolInfoString(symbol,SYMBOL_CURRENCY_MARGIN),DoubleToString(SymbolInfoDouble(symbol,SYMBOL_TRADE_CONTRACT_SIZE),-16),
      DoubleToString(SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE),-16),
      SymbolInfoInteger(symbol,SYMBOL_DIGITS),SymbolInfoInteger(symbol,SYMBOL_TRADE_CALC_MODE));
   return GetLastError()==0 ? value : "";
}

void ExecQuoteSnapshot(const string id,const string &f[])
{
   long expiry=ArraySize(f)==18 ? StringToInteger(f[17]) : 0;
   if(!NativeIdentityMatches(f) || expiry<=0 || IntegerToString(expiry)!=f[17] || !NativeEntryDeadlineCurrent(expiry))
   { PushResult(StringFormat("{\"id\":%s,\"error\":\"native quote identity or deadline unavailable\"}",id)); return; }
   long start=(long)TimeGMT()*1000;
   string scope=MarginReadAccountScopeJson(),instrument=NativeQuoteContractScope(f[2]);
   string before=MarginReadAccountJson(),contractBefore=NativeSymbolContractJson(f[2]);
   MqlTick tick; ZeroMemory(tick);
   string tickJson="null";
   if(SymbolInfoTick(f[2],tick))
   {
      if(!MathIsValidNumber(tick.bid) || !MathIsValidNumber(tick.ask) || !MathIsValidNumber(tick.last)
         || !MathIsValidNumber(tick.volume_real) || tick.bid<0 || tick.ask<0 || tick.last<0
         || tick.volume_real<0 || tick.time_msc<0)
      { PushResult(StringFormat("{\"id\":%s,\"error\":\"native quote number unavailable\"}",id)); return; }
      tickJson=StringFormat("{\"bid\":\"%s\",\"ask\":\"%s\",\"last\":\"%s\",\"volume_real\":\"%s\",\"volume\":\"%I64u\",\"time\":\"%I64d\",\"time_msc\":\"%I64d\",\"flags\":\"%u\"}",
         DoubleToString(tick.bid,-16),DoubleToString(tick.ask,-16),DoubleToString(tick.last,-16),
         DoubleToString(tick.volume_real,-16),tick.volume,(long)tick.time,tick.time_msc,tick.flags);
   }
   string contractAfter=NativeSymbolContractJson(f[2]),after=MarginReadAccountJson();
   long selected=0,delayed=0;
   string selectedJson=SymbolInfoInteger(f[2],SYMBOL_SELECT,selected) ? (selected!=0 ? "true" : "false") : "null";
   string delayedJson=SymbolInfoInteger(f[2],SYMBOL_SUBSCRIPTION_DELAY,delayed) ? (delayed!=0 ? "true" : "false") : "null";
   long received=(long)TimeGMT()*1000+999;
   if(before=="" || after=="" || contractBefore=="" || contractAfter=="" || instrument==""
      || instrument!=NativeQuoteContractScope(f[2]) || scope!=MarginReadAccountScopeJson()
      || received<start || start<=0 || !TerminalInfoInteger(TERMINAL_CONNECTED)
      || !NativeIdentityMatches(f) || !NativeEntryDeadlineCurrent(expiry))
   { PushResult(StringFormat("{\"id\":%s,\"error\":\"native quote scope changed, unavailable or expired\"}",id)); return; }
   string request=StringFormat("{\"symbol\":\"%s\"}",JsonEscape(f[2]));
   string observation=StringFormat("{\"schema\":\"van.mt5.quote-snapshot/1\",\"request\":%s,\"account_before\":%s,\"account_after\":%s,\"contract_before\":%s,\"contract_after\":%s,\"tick\":%s,\"symbol_selected\":%s,\"subscription_delayed\":%s,\"requested_at_ms\":%I64d,\"received_at_ms\":%I64d,\"deadline_ms\":%I64d,\"native_clock_basis\":\"UTC_SECOND_INTERVAL\",\"native_numeric_format\":\"MQL_BINARY64_ROUNDTRIP\",\"tick_time_basis\":\"BROKER_UTC_LATEST_FULL_TICK_SNAPSHOT_NOT_INDIVIDUAL_SIDE_TIMES\",\"volume_basis\":\"NATIVE_LAST_TRADE_VOLUME_NOT_LOTS_OR_GENUINE_DEPTH\",\"account_snapshot_atomic\":false,\"risk_terms_qualified\":false,\"execution_authority\":false}",
      request,before,after,contractBefore,contractAfter,tickJson,selectedJson,delayedJson,start,received,expiry);
   PushResult(StringFormat("{\"id\":%s,\"observation\":%s}",id,observation));
}

void ExecSymbolContract(const string id,const string &f[])
{
   long expiry=ArraySize(f)==18 ? StringToInteger(f[17]) : 0;
   if(!NativeIdentityMatches(f) || expiry<=0 || IntegerToString(expiry)!=f[17] || !NativeEntryDeadlineCurrent(expiry))
   { PushResult(StringFormat("{\"id\":%s,\"error\":\"native symbol identity or deadline unavailable\"}",id)); return; }
   long start=(long)TimeGMT()*1000;
   string scope=MarginReadAccountScopeJson(),before=MarginReadAccountJson();
   string contract=NativeSymbolContractJson(f[2]),after=MarginReadAccountJson();
   long received=(long)TimeGMT()*1000+999;
   if(before=="" || after=="" || contract=="" || start<=0 || received<start
      || scope!=MarginReadAccountScopeJson() || !TerminalInfoInteger(TERMINAL_CONNECTED)
      || !NativeIdentityMatches(f) || !NativeEntryDeadlineCurrent(expiry))
   { PushResult(StringFormat("{\"id\":%s,\"error\":\"native symbol source changed, unavailable or expired\"}",id)); return; }
   string request=StringFormat("{\"symbol\":\"%s\"}",JsonEscape(f[2]));
   string observation=StringFormat("{\"schema\":\"van.mt5.symbol-contract/1\",\"request\":%s,\"account_before\":%s,\"account_after\":%s,\"contract\":%s,\"requested_at_ms\":%I64d,\"received_at_ms\":%I64d,\"deadline_ms\":%I64d,\"native_clock_basis\":\"UTC_SECOND_INTERVAL\",\"native_numeric_format\":\"MQL_BINARY64_ROUNDTRIP\",\"tick_value_basis\":\"NATIVE_SYMBOL_ACCOUNT_CURRENCY_VALUES_NO_SEPARATE_FX_TIMESTAMP\",\"account_snapshot_atomic\":false,\"risk_terms_qualified\":false,\"execution_authority\":false}",
      request,before,after,contract,start,received,expiry);
   PushResult(StringFormat("{\"id\":%s,\"observation\":%s}",id,observation));
}

void ExecMarginQuote(const string id,const string &f[])
{
   long expiry = ArraySize(f)==18 ? StringToInteger(f[17]) : 0;
   if(!NativeIdentityMatches(f) || expiry<=0 || IntegerToString(expiry)!=f[17] || !NativeEntryDeadlineCurrent(expiry))
   { PushResult(StringFormat("{\"id\":%s,\"error\":\"native margin identity or deadline unavailable\"}",id)); return; }
   double volume=StringToDouble(f[4]),price=StringToDouble(f[5]);
   if((f[3]!="BUY" && f[3]!="SELL") || !MathIsValidNumber(volume) || !MathIsValidNumber(price) || volume<=0 || price<=0)
   { PushResult(StringFormat("{\"id\":%s,\"error\":\"native margin request unavailable\"}",id)); return; }
   string beforeScope=MarginReadAccountScopeJson(),before=MarginReadAccountJson(),contract=MarginReadContractJson(f[2]);
   long start=(long)TimeGMT()*1000;
   double margin=0;
   ENUM_ORDER_TYPE side = f[3]=="BUY" ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(before=="" || contract=="" || start<=0 || !TerminalInfoInteger(TERMINAL_CONNECTED)
      || !OrderCalcMargin(side,f[2],volume,price,margin) || !MathIsValidNumber(margin) || margin<0)
   { PushResult(StringFormat("{\"id\":%s,\"error\":\"native isolated margin unavailable\"}",id)); return; }
   string after=MarginReadAccountJson(),latest=MarginReadContractJson(f[2]);
   long received=(long)TimeGMT()*1000+999;
   if(after=="" || beforeScope!=MarginReadAccountScopeJson() || contract!=latest || received<start
      || !TerminalInfoInteger(TERMINAL_CONNECTED) || !NativeIdentityMatches(f) || !NativeEntryDeadlineCurrent(expiry))
   { PushResult(StringFormat("{\"id\":%s,\"error\":\"native margin source changed or expired\"}",id)); return; }
   string request=StringFormat("{\"symbol\":\"%s\",\"type\":\"%s\",\"volume\":\"%s\",\"price\":\"%s\"}",JsonEscape(f[2]),f[3],JsonEscape(f[4]),JsonEscape(f[5]));
   string observation=StringFormat("{\"schema\":\"van.mt5.expected-margin/1\",\"state\":\"OBSERVED\",\"request\":%s,\"account_before\":%s,\"account_after\":%s,\"contract\":%s,\"raw_margin\":\"%s\",\"currency_digits\":%I64d,\"requested_at_ms\":%I64d,\"received_at_ms\":%I64d,\"deadline_ms\":%I64d,\"native_clock_basis\":\"UTC_SECOND_INTERVAL\",\"valuation_basis\":\"ISOLATED_ORDER_AT_REQUEST_PRICE_EXCLUDES_EXISTING_POSITIONS_AND_PENDING_ORDERS\",\"account_snapshot_atomic\":false,\"reservation_qualified\":false,\"execution_authority\":false}",
      request,before,after,contract,DoubleToString(margin,-16),AccountInfoInteger(ACCOUNT_CURRENCY_DIGITS),start,received,expiry);
   PushResult(StringFormat("{\"id\":%s,\"observation\":%s}",id,observation));
}

//+------------------------------------------------------------------+
//| execution (SL required, tighten-only, no size decisions)          |
//+------------------------------------------------------------------+
void ExecOrderSend(const string id, const string symbol, const string side, double volume, double price, double sl, double tp, const string comment, long magic, int deviation, const string orderType, const string &binding[])
{
   long deadlineMs = 0;
   if(!NativeIdentityMatches(binding) || !NativeEntryDeadline(binding, deadlineMs) || !NativeEntryDeadlineCurrent(deadlineMs))
   { PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"volume\":\"0\",\"reason\":\"native entry binding or deadline invalid or expired\"}", id)); return; }
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
   if(!NativeIdentityMatches(binding) || !NativeEntryDeadlineCurrent(deadlineMs) || !TerminalInfoInteger(TERMINAL_CONNECTED) || !TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_EXPERT) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
   { PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"volume\":\"0\",\"reason\":\"native entry authority expired or changed before dispatch\"}", id)); return; }
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
      if((op == "ORDER_SEND" || op == "ORDER_SEND_EXPIRING") && f[12] != "MARKET" && f[12] != "LIMIT")
      {
         PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"volume\":\"0\",\"reason\":\"unsupported explicit order type\"}", id));
         continue;
      }
      if(op == "QUOTE_SNAPSHOT") ExecQuoteSnapshot(id,f);
      else if(op == "SYMBOL_CONTRACT") ExecSymbolContract(id,f);
      else if(op == "MARGIN_QUOTE") ExecMarginQuote(id,f);
      else if(op == "ORDER_SEND" || op == "ORDER_SEND_EXPIRING") ExecOrderSend(id, f[2], f[3], StringToDouble(f[4]), StringToDouble(f[5]), StringToDouble(f[6]), StringToDouble(f[7]), f[9], StringToInteger(f[10]), (int)StringToInteger(f[11]), f[12], f);
      else if(op == "MODIFY_SL")  ExecModifySl(id, (ulong)StringToInteger(f[8]), StringToDouble(f[6]), StringToDouble(f[7]));
      else if(op == "CLOSE")      ExecClose(id, (ulong)StringToInteger(f[8]), StringToDouble(f[4]));
      else PushResult(StringFormat("{\"id\":%s,\"status\":\"REJECTED\",\"reason\":\"op not in contract\"}", id));
   }
   if(ArraySize(pendingResults) > 0) OnTimer();   // report executions without waiting a full interval
}
//+------------------------------------------------------------------+
