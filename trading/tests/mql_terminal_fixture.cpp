// Test-only terminal interface for executing the actual extracted EA bodies.
// This is a deterministic C++ model, not a MetaTrader runtime or broker.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <iostream>
#include <map>
#include <limits>
#include <string>
#include <vector>
using string = std::string;
int StringLen(const string& s) { return s.size(); }
template<class T> int ArraySize(const std::vector<T>& v) { return v.size(); }
template<class T> void ArrayResize(std::vector<T>& v, int n) { v.resize(n); }
void StringReplace(string& s, const string& from, const string& to) {
  size_t at=0; while ((at=s.find(from,at))!=string::npos) { s.replace(at,from.size(),to); at+=to.size(); }
}
const char* fmtarg(const string& s) { return s.c_str(); }
template<class T> T fmtarg(T value) { return value; }
template<class... T> string StringFormat(string fmt, T... args) {
  StringReplace(fmt,"%I64u","%lu"); StringReplace(fmt,"%I64d","%ld");
  int n=std::snprintf(nullptr,0,fmt.c_str(),fmtarg(args)...);
  std::vector<char> out(n+1); std::snprintf(out.data(),out.size(),fmt.c_str(),fmtarg(args)...);
  return out.data();
}
bool MathIsValidNumber(double n) { return std::isfinite(n); }
long TimeGMT() { return 1700000000; }
enum {
 ACCOUNT_TRADE_MODE, ACCOUNT_LOGIN, ACCOUNT_EQUITY, ACCOUNT_BALANCE, ACCOUNT_CURRENCY,
 ACCOUNT_SERVER, ACCOUNT_TRADE_ALLOWED, ACCOUNT_MARGIN_MODE, ACCOUNT_TRADE_EXPERT,
 TERMINAL_TRADE_ALLOWED, TERMINAL_CONNECTED, MQL_TRADE_ALLOWED,
 POSITION_SYMBOL, POSITION_TYPE, POSITION_VOLUME, POSITION_PRICE_OPEN, POSITION_SL,
 POSITION_TP, POSITION_COMMENT, POSITION_MAGIC, POSITION_PROFIT, POSITION_IDENTIFIER,
 DEAL_POSITION_ID, ORDER_SL, ORDER_SYMBOL, ORDER_TYPE, ORDER_VOLUME_CURRENT, ORDER_PRICE_OPEN,
 ORDER_TP, ORDER_COMMENT, ORDER_MAGIC
};
const long ACCOUNT_TRADE_MODE_DEMO=20, ACCOUNT_TRADE_MODE_REAL=21;
const long ACCOUNT_MARGIN_MODE_RETAIL_HEDGING=22, POSITION_TYPE_BUY=0, ORDER_TIME_GTC=0;
const uint TRADE_RETCODE_PLACED=10008, TRADE_RETCODE_DONE=10009, TRADE_RETCODE_DONE_PARTIAL=10010;
const uint TRADE_RETCODE_REJECT=10006, TRADE_RETCODE_INVALID=10013, TRADE_RETCODE_INVALID_VOLUME=10014;
const uint TRADE_RETCODE_INVALID_PRICE=10015, TRADE_RETCODE_INVALID_STOPS=10016;
const uint TRADE_RETCODE_TRADE_DISABLED=10017, TRADE_RETCODE_MARKET_CLOSED=10018, TRADE_RETCODE_NO_MONEY=10019;
const uint TRADE_RETCODE_PRICE_CHANGED=10020, TRADE_RETCODE_PRICE_OFF=10021, TRADE_RETCODE_INVALID_EXPIRATION=10022;
const uint TRADE_RETCODE_SERVER_DISABLES_AT=10026, TRADE_RETCODE_CLIENT_DISABLES_AT=10027;
const uint TRADE_RETCODE_INVALID_FILL=10030, TRADE_RETCODE_LIMIT_ORDERS=10033, TRADE_RETCODE_LIMIT_VOLUME=10034;
const uint TRADE_RETCODE_INVALID_ORDER=10035, TRADE_RETCODE_LIMIT_POSITIONS=10040;
const uint TRADE_RETCODE_LONG_ONLY=10042, TRADE_RETCODE_SHORT_ONLY=10043, TRADE_RETCODE_CLOSE_ONLY=10044;
const uint TRADE_RETCODE_FIFO_CLOSE=10045, TRADE_RETCODE_HEDGE_PROHIBITED=10046;
struct Position { ulong ticket=42, identifier=900; double volume=.00123456, price=1.123456789012345, sl=1.12, tp=1.2, profit=.00001234; long type=0; string symbol="EURUSD"; };
std::map<ulong,Position> positions={{42,Position()}};
ulong selected=0;
bool selection_ok=true, connected=true, modify_effect=true, pending_order_visible=true;
long margin_mode=ACCOUNT_MARGIN_MODE_RETAIL_HEDGING;
int pending_count=0;
int modify_calls=0, close_calls=0, entry_calls=0;
long AccountInfoInteger(int field) {
 if(field==ACCOUNT_TRADE_MODE) return ACCOUNT_TRADE_MODE_DEMO;
 if(field==ACCOUNT_LOGIN) return 12345678;
 if(field==ACCOUNT_MARGIN_MODE) return margin_mode;
 return 1;
}
double AccountInfoDouble(int field) { return field==ACCOUNT_EQUITY ? 12345.12345678 : 12344.12345678; }
string AccountInfoString(int field) { return field==ACCOUNT_CURRENCY ? "USD" : "broker-demo"; }
long TerminalInfoInteger(int field) { return field==TERMINAL_CONNECTED ? connected : 1; }
long MQLInfoInteger(int) { return 1; }
int PositionsTotal() { return positions.size(); }
ulong PositionGetTicket(int index) { auto it=positions.begin(); std::advance(it,index); selected=it->first; return it->first; }
bool PositionSelectByTicket(ulong ticket) { selected=ticket; return selection_ok && positions.count(ticket); }
long PositionGetInteger(int field) {
 auto& p=positions.at(selected);
 return field==POSITION_TYPE ? p.type : field==POSITION_IDENTIFIER ? p.identifier : 123;
}
double PositionGetDouble(int field) {
 auto& p=positions.at(selected);
 switch(field) { case POSITION_VOLUME:return p.volume; case POSITION_PRICE_OPEN:return p.price;
 case POSITION_SL:return p.sl; case POSITION_TP:return p.tp; default:return p.profit; }
}
string PositionGetString(int field) { return field==POSITION_SYMBOL ? positions.at(selected).symbol : "vati:fixture"; }
bool SymbolSelect(const string&,bool) { return true; }
bool HistoryDealSelect(ulong ticket) { return ticket==77; }
long HistoryDealGetInteger(ulong, int) { return 900; }
bool OrderSelect(ulong ticket) { return pending_order_visible && ticket==11; }
int OrdersTotal() { return pending_count; }
ulong OrderGetTicket(int) { return 11; }
double OrderGetDouble(int) { return 1.12; }
string OrderGetString(int) { return "EURUSD"; }
struct Trade {
 uint rc=TRADE_RETCODE_DONE; ulong order=11, deal=77; double volume=.00123456, price=1.123456789012345;
 bool action_ok=true;
 void SetExpertMagicNumber(long) {} void SetDeviationInPoints(int) {}
 bool BuyLimit(double,double,string,double,double,long,long,string) { return action_ok; }
 bool SellLimit(double,double,string,double,double,long,long,string) { return action_ok; }
 bool Buy(double,string,double,double,double,string) { entry_calls++; return action_ok; }
 bool Sell(double,string,double,double,double,string) { entry_calls++; return action_ok; }
 uint ResultRetcode() { return rc; } ulong ResultOrder() { return order; } ulong ResultDeal() { return deal; }
 double ResultVolume() { return volume; } double ResultPrice() { return price; }
 string ResultRetcodeDescription() { return "fixture native reply"; }
 bool PositionModify(ulong ticket,double sl,double) {
  modify_calls++; if(modify_effect && action_ok && rc==TRADE_RETCODE_DONE && positions.count(ticket)) positions[ticket].sl=sl;
  return action_ok;
 }
 bool PositionClose(ulong) { close_calls++; return action_ok; }
 bool PositionClosePartial(ulong,double) { close_calls++; return action_ok; }
} trade;
std::vector<string> pendingResults;

// EXTRACTED_EA_FUNCTIONS

int main(int argc, char** argv) {
 string c=argv[1];
 if(c=="snapshot" || c=="snapshot-missing" || c=="snapshot-escaped") {
  if(c=="snapshot-missing") selection_ok=false;
  if(c=="snapshot-escaped") positions[42].symbol="ABC\"Q\\R";
  std::cout<<SnapshotJson(); return 0;
 }
 if(c=="partial-close") { trade.rc=TRADE_RETCODE_DONE_PARTIAL; ExecClose("1",42,.001); }
 else if(c=="unknown-close") { trade.rc=10012; trade.action_ok=false; ExecClose("1",42,.001); }
 else if(c=="rejected-close") { trade.rc=TRADE_RETCODE_REJECT; trade.action_ok=false; ExecClose("1",42,.001); }
 else if(c=="zero-sell-stop") { positions[42].type=1; ExecModifySl("1",42,0,0); }
 else if(c=="modify-rejected") { trade.rc=TRADE_RETCODE_REJECT; ExecModifySl("1",42,1.121,0); }
 else if(c=="modify-unobserved") { modify_effect=false; ExecModifySl("1",42,1.121,0); }
 else if(c=="modify-good") { ExecModifySl("1",42,1.121,0); }
 else {
  if(c=="entry-weak-stop") positions[42].sl=1.1;
  if(c=="entry-no-stop") positions[42].sl=0;
  if(c=="entry-unknown-position") trade.deal=0;
  if(c=="entry-wrong-symbol") positions[42].symbol="USDJPY";
  if(c=="entry-partial") trade.rc=TRADE_RETCODE_DONE_PARTIAL;
  if(c=="entry-unknown") { trade.rc=10012; trade.action_ok=false; }
  if(c=="entry-pending") { trade.rc=TRADE_RETCODE_PLACED; pending_order_visible=false; }
  if(c=="entry-disconnected") connected=false;
  if(c=="entry-netting-position" || c=="entry-netting-pending" || c=="entry-netting-empty") margin_mode=0;
  if(c=="entry-netting-pending" || c=="entry-netting-empty") positions.clear();
  if(c=="entry-netting-pending") pending_count=1;
  double volume=c=="entry-negative-volume" ? -.001 : .00123456;
  double sl=c=="entry-nan-stop" ? std::numeric_limits<double>::quiet_NaN() : 1.12;
  ExecOrderSend("1","EURUSD",c=="entry-invalid-side" ? "INVALID" : "BUY",volume,1.123456789012345,sl,1.2,"vati:fixture",123,20,c=="entry-pending" ? "LIMIT" : "MARKET");
 }
 std::cout<<"{\"results\":[";
 for(size_t i=0;i<pendingResults.size();i++) { if(i) std::cout<<","; std::cout<<pendingResults[i]; }
 std::cout<<"],\"modify_calls\":"<<modify_calls<<",\"close_calls\":"<<close_calls<<",\"entry_calls\":"<<entry_calls<<"}";
}
