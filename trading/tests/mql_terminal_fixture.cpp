// Test-only terminal interface for executing the actual extracted EA bodies.
// This is a deterministic C++ model, not a MetaTrader runtime or broker.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <iostream>
#include <map>
#include <limits>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>
using string = std::string;
using ushort = unsigned short;
using ENUM_ACCOUNT_INFO_DOUBLE = int;
int StringLen(const string& s) { return s.size(); }
ushort StringGetCharacter(const string& s,int i) { return (unsigned char)s.at(i); }
string StringSubstr(const string& s,int start,int count=-1) { return s.substr(start,count<0 ? string::npos : count); }
bool StringSetCharacter(string& s,int i,ushort c) { s.at(i)=(char)c; return true; }
int StringCompare(const string& a,const string& b) { return a.compare(b); }
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
long utc_clock=1700000000;
long TimeGMT() { return utc_clock; }
string IntegerToString(long value) { return std::to_string(value); }
long StringToInteger(const string& value) { try { return std::stol(value); } catch(...) { return 0; } }
string Utf8Hex(const string& value) {
 std::ostringstream out;
 for(unsigned char c:value) out<<std::hex<<std::setw(2)<<std::setfill('0')<<(int)c;
 return out.str();
}
using datetime = long;
long terminal_clock=1700000000;
long TimeCurrent() { return terminal_clock; }
int last_error=0;
void ResetLastError() { last_error=0; }
int GetLastError() { return last_error; }
string DoubleToString(double value,int digits) {
 std::ostringstream out;
 out << (digits < 0 ? std::scientific : std::fixed) << std::setprecision(std::abs(digits)) << value;
 return out.str();
}
enum ENUM_DEAL_TYPE { DEAL_TYPE_BUY=0, DEAL_TYPE_SELL=1, DEAL_TYPE_BALANCE=2,
 DEAL_TYPE_CREDIT=3, DEAL_TYPE_CHARGE=4, DEAL_TYPE_CORRECTION=5, DEAL_TYPE_BONUS=6 };
string EnumToString(ENUM_DEAL_TYPE value) {
 switch(value) { case DEAL_TYPE_BUY:return "DEAL_TYPE_BUY"; case DEAL_TYPE_SELL:return "DEAL_TYPE_SELL";
 case DEAL_TYPE_BALANCE:return "DEAL_TYPE_BALANCE"; case DEAL_TYPE_CREDIT:return "DEAL_TYPE_CREDIT";
 case DEAL_TYPE_CHARGE:return "DEAL_TYPE_CHARGE"; case DEAL_TYPE_CORRECTION:return "DEAL_TYPE_CORRECTION";
 case DEAL_TYPE_BONUS:return "DEAL_TYPE_BONUS"; default:return "DEAL_TYPE_UNKNOWN"; }
}
enum {
 ACCOUNT_TRADE_MODE, ACCOUNT_LOGIN, ACCOUNT_EQUITY, ACCOUNT_BALANCE, ACCOUNT_CURRENCY,
 ACCOUNT_SERVER, ACCOUNT_TRADE_ALLOWED, ACCOUNT_MARGIN_MODE, ACCOUNT_TRADE_EXPERT,
 TERMINAL_TRADE_ALLOWED, TERMINAL_CONNECTED, MQL_TRADE_ALLOWED,
 POSITION_SYMBOL, POSITION_TYPE, POSITION_VOLUME, POSITION_PRICE_OPEN, POSITION_SL,
 POSITION_TP, POSITION_COMMENT, POSITION_MAGIC, POSITION_PROFIT, POSITION_IDENTIFIER,
 DEAL_POSITION_ID, ORDER_SL, ORDER_SYMBOL, ORDER_TYPE, ORDER_VOLUME_CURRENT, ORDER_PRICE_OPEN,
 ORDER_TP, ORDER_COMMENT, ORDER_MAGIC, ACCOUNT_CREDIT, ACCOUNT_CURRENCY_DIGITS,
 DEAL_TYPE, DEAL_TIME_MSC, DEAL_PROFIT, DEAL_COMMISSION, DEAL_SWAP, DEAL_FEE,
 ACCOUNT_MARGIN, ACCOUNT_MARGIN_FREE, ACCOUNT_MARGIN_LEVEL, ACCOUNT_LEVERAGE
};
const long ACCOUNT_TRADE_MODE_DEMO=20, ACCOUNT_TRADE_MODE_REAL=21;
const long ACCOUNT_MARGIN_MODE_RETAIL_HEDGING=2, POSITION_TYPE_BUY=0, ORDER_TIME_GTC=0;
const int ORDER_TYPE_BUY=0, ORDER_TYPE_SELL=1;
struct MqlTick { double bid=1.1234,ask=1.1235; };
bool SymbolInfoTick(const string&,MqlTick&) { return true; }
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
double account_credit=200, account_balance=12344.12345678, account_equity=12345.12345678;
double required_margin=33.25;
bool floor_drop_during_margin=false, floor_drop_final=false, floor_rise_during_margin=false;
bool reported_level_available=true, reported_level_drop_final=false, reported_level_rise=false;
int post_margin_level_reads=0;
bool margin_calculation_available=true;
bool cash_drop_during_margin=false, cash_drop_final=false, cash_units_change=false;
bool expire_margin_read=false, disable_margin_read=false;
int margin_calls=0, post_margin_cash_reads=0, currency_digits=2, last_margin_side=-1;
double last_margin_price=0;
double account_margin=1000, account_margin_free=11345.12345678, account_margin_level=1234.512345678;
bool margin_available=true;
bool funds_available=true, history_available=true, native_deal_available=true;
bool cash_amount_available=true, change_funds_during_query=false, change_identity_during_query=false;
bool expire_cash_query=false;
bool expire_entry_read=false, drift_entry_identity=false, disable_entry_read=false;
long native_login=12345678;
struct CashDeal { ulong ticket=9007199254740993UL; long type=DEAL_TYPE_BALANCE, at=1699999999000L;
 double profit=12344.12345678, commission=0, swap=0, fee=-.00000013; };
std::vector<CashDeal> native_deals={CashDeal()};
long AccountInfoInteger(int field) {
 if(field==ACCOUNT_TRADE_MODE) return ACCOUNT_TRADE_MODE_DEMO;
 if(field==ACCOUNT_LOGIN) return native_login;
 if(field==ACCOUNT_CURRENCY_DIGITS) return currency_digits;
 if(field==ACCOUNT_LEVERAGE) return 30;
 if(field==ACCOUNT_MARGIN_MODE) return margin_mode;
 return 1;
}
double AccountInfoDouble(int field) {
 if(field==ACCOUNT_MARGIN || field==ACCOUNT_MARGIN_FREE || field==ACCOUNT_MARGIN_LEVEL) {
  if(!margin_available) last_error=1;
  if(field==ACCOUNT_MARGIN_LEVEL && !reported_level_available) last_error=1;
  if(field==ACCOUNT_MARGIN_LEVEL && margin_calls && reported_level_drop_final && ++post_margin_level_reads>=2) account_margin_level=210;
  return field==ACCOUNT_MARGIN ? account_margin : field==ACCOUNT_MARGIN_FREE ? account_margin_free : account_margin_level;
 }
 if(!funds_available) last_error=1;
 if(field==ACCOUNT_EQUITY && margin_calls && cash_drop_final && ++post_margin_cash_reads>=2) account_equity=20;
 if(field==ACCOUNT_EQUITY && margin_calls && floor_drop_final && ++post_margin_cash_reads>=2) account_equity=500;
 return field==ACCOUNT_EQUITY ? account_equity : field==ACCOUNT_CREDIT ? account_credit : account_balance;
}
bool OrderCalcMargin(int side,const string&,double,double price,double &result) {
 last_margin_side=side;last_margin_price=price;
 margin_calls++;result=required_margin;
 if(cash_drop_during_margin) account_equity=20;
 if(floor_drop_during_margin) account_equity=500;
 if(floor_rise_during_margin) account_equity=2000;
 if(reported_level_rise) account_margin_level=1000;
 if(cash_units_change) currency_digits=3;
 if(expire_margin_read) utc_clock++;
 if(disable_margin_read) connected=false;
 return margin_calculation_available;
}
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
bool SymbolSelect(const string&,bool) {
 if(expire_entry_read) utc_clock++;
 if(drift_entry_identity) native_login++;
 if(disable_entry_read) connected=false;
 return true;
}
bool HistoryDealSelect(ulong ticket) { return ticket==77; }
bool HistorySelect(datetime from,datetime to) {
 if(from!=0 || to!=terminal_clock+1) { last_error=1; return false; }
 if(change_funds_during_query) account_balance+=1;
 if(change_identity_during_query) native_login+=1;
 if(expire_cash_query) terminal_clock+=2;
 return history_available;
}
int HistoryDealsTotal() { return native_deals.size(); }
ulong HistoryDealGetTicket(int index) {
 if(!native_deal_available) { last_error=1; return 0; }
 return native_deals.at(index).ticket;
}
long HistoryDealGetInteger(ulong ticket,int field) {
 if(field==DEAL_POSITION_ID) return 900;
 for(auto& row:native_deals) if(row.ticket==ticket) return field==DEAL_TYPE ? row.type : row.at;
 last_error=1; return 0;
}
double HistoryDealGetDouble(ulong ticket,int field) {
 if(!cash_amount_available) { last_error=1; return 0; }
 for(auto& row:native_deals) if(row.ticket==ticket) {
  return field==DEAL_PROFIT ? row.profit : field==DEAL_COMMISSION ? row.commission : field==DEAL_SWAP ? row.swap : row.fee;
 }
 last_error=1; return 0;
}
bool OrderSelect(ulong ticket) { return pending_order_visible && ticket==11; }
int OrdersTotal() { return pending_count; }
ulong OrderGetTicket(int) { return 11; }
double OrderGetDouble(int field) { return field==ORDER_VOLUME_CURRENT ? .00123456 : field==ORDER_PRICE_OPEN ? 1.123456789012345 : 1.12; }
long OrderGetInteger(int field) { return field==ORDER_TYPE ? 2 : 123; }
string OrderGetString(int) { return "EURUSD"; }
struct Trade {
 uint rc=TRADE_RETCODE_DONE; ulong order=11, deal=77; double volume=.00123456, price=1.123456789012345;
 bool action_ok=true;
 void SetExpertMagicNumber(long) {} void SetDeviationInPoints(int) {}
 bool BuyLimit(double,double,string,double,double,long,long,string) { entry_calls++;return action_ok; }
 bool SellLimit(double,double,string,double,double,long,long,string) { entry_calls++;return action_ok; }
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
 if(c.rfind("snapshot",0)==0) {
  if(c=="snapshot-margin-unavailable") margin_available=false;
  if(c=="snapshot-margin-flat") { account_margin=0; account_margin_free=12345.12345678; account_margin_level=0; }
  if(c=="snapshot-margin-nonfinite") account_margin_free=std::numeric_limits<double>::quiet_NaN();
  if(c=="snapshot-missing") selection_ok=false;
  if(c=="snapshot-escaped") positions[42].symbol="ABC\"Q\\R";
  if(c=="snapshot-pending" || c=="snapshot-order-unavailable") pending_count=1;
  if(c=="snapshot-order-unavailable") pending_order_visible=false;
  if(c=="snapshot-cash-history-unavailable") history_available=false;
  if(c=="snapshot-cash-deal-unavailable") native_deal_available=false;
  if(c=="snapshot-cash-values-unavailable") cash_amount_available=false;
  if(c=="snapshot-cash-funds-unavailable") funds_available=false;
  if(c=="snapshot-cash-funds-changed") change_funds_during_query=true;
  if(c=="snapshot-cash-identity-changed") change_identity_during_query=true;
  if(c=="snapshot-cash-query-expired") expire_cash_query=true;
  if(c=="snapshot-cash-nonfinite") native_deals[0].fee=std::numeric_limits<double>::quiet_NaN();
  if(c=="snapshot-cash-tiny-fee") native_deals[0].fee=-1.2345678901234567e-30;
  if(c=="snapshot-cash-empty") native_deals.clear();
  if(c=="snapshot-cash-trade") native_deals[0].type=DEAL_TYPE_BUY;
  if(c=="snapshot-cash-bound") native_deals.resize(4097);
  if(c=="snapshot-cash-history-bound") native_deals.resize(200001);
  std::cout<<SnapshotJson(); return 0;
 }
 if(c=="partial-close") { trade.rc=TRADE_RETCODE_DONE_PARTIAL; ExecClose("1",42,.001); }
 else if(c=="unknown-close") { trade.rc=10012; trade.action_ok=false; ExecClose("1",42,.001); }
 else if(c=="rejected-close") { trade.rc=TRADE_RETCODE_REJECT; trade.action_ok=false; ExecClose("1",42,.001); }
 else if(c=="zero-sell-stop") { positions[42].type=1; ExecModifySl("1",42,0,0); }
 else if(c=="modify-rejected") { trade.rc=TRADE_RETCODE_REJECT; ExecModifySl("1",42,1.121,0); }
 else if(c=="modify-unobserved") { modify_effect=false; ExecModifySl("1",42,1.121,0); }
 else if(c=="modify-good") { ExecModifySl("1",42,1.121,0); }
 else if(c=="cash-protective-close") { account_equity=1;account_margin_free=0;ExecClose("1",42,.001); }
 else if(c=="cash-protective-modify") { account_equity=1;account_margin_free=0;ExecModifySl("1",42,1.121,0); }
 else {
  if(c.rfind("entry-cash",0)==0) { account_equity=1000;account_credit=0;account_margin=0;account_margin_free=1000; }
  if(c=="entry-cash-credit" || c=="entry-cash-limit-insufficient") { account_equity=100;account_credit=95;account_margin_free=100; }
  if(c=="entry-cash-used") { account_equity=100;account_margin=90;account_margin_free=100; }
  if(c=="entry-cash-missing") funds_available=false;
  if(c=="entry-cash-nonfinite") required_margin=std::numeric_limits<double>::quiet_NaN();
  if(c=="entry-cash-zero") required_margin=0;
  if(c=="entry-cash-fraction-boundary") { account_equity=33.25;account_margin_free=33.25;required_margin=33.25000001; }
  if(c=="entry-cash-after") cash_drop_during_margin=true;
  if(c=="entry-cash-final") cash_drop_final=true;
  if(c=="entry-cash-units") cash_units_change=true;
  if(c=="entry-cash-deadline") expire_margin_read=true;
  if(c=="entry-cash-permission") disable_margin_read=true;
  if(c=="entry-cash-sell") positions[42].type=1;
  if(c=="entry-cash-limit-good") trade.rc=TRADE_RETCODE_PLACED;
  if(c=="entry-market-accepted") trade.rc=TRADE_RETCODE_PLACED;
  if(c.rfind("entry-floor",0)==0) {
   account_equity=1000;account_credit=0;account_margin=100;account_margin_free=900;required_margin=400;
   if(c=="entry-floor-low") required_margin=450;
   if(c=="entry-floor-credit") { account_equity=1100;account_credit=100;account_margin_free=1000; }
   if(c=="entry-floor-good") required_margin=399.5;
   if(c=="entry-floor-fraction-held") required_margin=399.99;
   if(c=="entry-floor-after") { required_margin=200;floor_drop_during_margin=true; }
   if(c=="entry-floor-final") { required_margin=200;floor_drop_final=true; }
   if(c=="entry-floor-improved") floor_rise_during_margin=true;
   if(c=="entry-floor-reported" || c=="entry-floor-reported-improved") { required_margin=10;account_margin_level=210; }
   if(c=="entry-floor-reported-improved") reported_level_rise=true;
   if(c=="entry-floor-reported-equal") { required_margin=10;account_margin_level=220; }
   if(c=="entry-floor-reported-good") { required_margin=10;account_margin_level=250; }
   if(c=="entry-floor-reported-fraction") { required_margin=10;account_margin_level=220.005; }
   if(c=="entry-floor-reported-final") { required_margin=10;account_margin_level=1000;reported_level_drop_final=true; }
   if(c=="entry-floor-level-missing") reported_level_available=false;
   if(c=="entry-floor-level-invalid") account_margin_level=std::numeric_limits<double>::quiet_NaN();
   if(c=="entry-floor-level-negative") account_margin_level=-1;
   if(c=="entry-floor-subminor") { account_margin=.001;account_margin_level=1e8;account_margin_free=999.999;required_margin=1; }
   if(c=="entry-floor-limit") trade.rc=TRADE_RETCODE_PLACED;
  }
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
  double sl=c=="entry-nan-stop" ? std::numeric_limits<double>::quiet_NaN() : c=="entry-cash-sell" ? 1.13 : 1.12;
  std::vector<string> binding(17,""); binding[1]="ORDER_SEND";
  binding[13]=IntegerToString(native_login); binding[14]=Utf8Hex(AccountInfoString(ACCOUNT_SERVER));
  binding[15]=Utf8Hex(AccountInfoString(ACCOUNT_CURRENCY)); binding[16]="true";
  if(c.rfind("entry-deadline",0)==0 || c=="entry-cash-deadline") {
   binding[1]="ORDER_SEND_EXPIRING"; binding.push_back(IntegerToString(utc_clock*1000+1000));
   if(c=="entry-deadline-expired") binding[17]=IntegerToString(utc_clock*1000);
   if(c=="entry-deadline-subsecond") binding[17]=IntegerToString(utc_clock*1000+500);
   if(c=="entry-deadline-malformed") binding[17]+="garbage";
   if(c=="entry-deadline-overflow") binding[17]="9223372036854775808";
   if(c=="entry-deadline-delayed") expire_entry_read=true;
  }
  if(c=="entry-identity-delayed") drift_entry_identity=true;
  if(c=="entry-permission-delayed") disable_entry_read=true;
  ExecOrderSend("1","EURUSD",c=="entry-invalid-side" ? "INVALID" : c=="entry-cash-sell" ? "SELL" : "BUY",volume,1.123456789012345,sl,1.2,"vati:fixture",123,20,c=="entry-pending" || c=="entry-cash-limit-good" || c=="entry-cash-limit-insufficient" || c=="entry-floor-limit" ? "LIMIT" : "MARKET",binding);
 }
 std::cout<<"{\"results\":[";
 for(size_t i=0;i<pendingResults.size();i++) { if(i) std::cout<<","; std::cout<<pendingResults[i]; }
 std::cout<<"],\"modify_calls\":"<<modify_calls<<",\"close_calls\":"<<close_calls<<",\"entry_calls\":"<<entry_calls<<",\"margin_calls\":"<<margin_calls<<",\"last_margin_side\":"<<last_margin_side<<",\"post_margin_cash_reads\":"<<post_margin_cash_reads<<"}";
}
