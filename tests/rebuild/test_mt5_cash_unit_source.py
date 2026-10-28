"""Execute exact EA integer-string source with an explicit C++ API shim.

This is a source arithmetic oracle, not execution by MetaTrader or a broker.
Official MetaEditor compilation and actual terminal qualification remain separate.
The independent oracle uses Python Fraction, never the string implementation.
"""
from fractions import Fraction
from pathlib import Path
import json,math,random,shutil,subprocess
import pytest

EA=Path(__file__).resolve().parents[2]/'deploy/van-trading-core/mql5/VanBridgeEA.mq5'


@pytest.fixture(scope='module')
def source_executable(tmp_path_factory):
    compiler=shutil.which('g++')
    assert compiler is not None,'This source arithmetic qualification requires the declared g++ test tool'
    text=EA.read_text()
    units=text.split('// BEGIN_NATIVE_CASH_UNITS\n',1)[1].split('// END_NATIVE_CASH_UNITS',1)[0]
    amount=text[text.index('bool NativeCashAmount('):text.index('bool NativeEntryCashScope(')]
    bound=text[text.index('bool NativeEntryCashBound('):text.index('struct EntryCashMarginCheck')]
    shim=r'''
#include <string>
#include <iostream>
#include <sstream>
#include <iomanip>
#include <cmath>
#include <cstdio>
#include <cstdlib>
using string=std::string;using ushort=unsigned short;
int StringLen(const string &s){return (int)s.size();}
ushort StringGetCharacter(const string &s,int i){return (unsigned char)s.at(i);}
string StringSubstr(const string &s,int start,int count=-1){return s.substr(start,count<0?string::npos:count);}
bool StringSetCharacter(string &s,int i,ushort c){s.at(i)=(char)c;return true;}
int StringCompare(const string &a,const string &b){return a.compare(b);}
enum ENUM_ACCOUNT_INFO_DOUBLE{ACCOUNT_EQUITY,ACCOUNT_CREDIT,ACCOUNT_MARGIN,ACCOUNT_MARGIN_FREE};
double values[4];bool missing[4];int nativeError=0;int currencyScale=2;
void ResetLastError(){nativeError=0;}
int GetLastError(){return nativeError;}
double AccountInfoDouble(ENUM_ACCOUNT_INFO_DOUBLE f){if(missing[f])nativeError=501;return values[f];}
bool MathIsValidNumber(double n){return std::isfinite(n);}
string JsonNumber(double value){char out[64];std::snprintf(out,sizeof(out),"%.17g",value);return out;}
bool NativeEntryCashScope(string &scope,int &digits){scope="explicit-source-fixture";digits=currencyScale;return true;}
'''
    main=r'''
int main(){string row;
 while(std::getline(std::cin,row)){
  std::istringstream in(row);string op,result;in>>op;
  if(op=="U"){int scale,up;string text;in>>scale>>up>>std::quoted(text);
   std::cout<<(NativeMoneyUnitsFromText(text,scale,up!=0,result)?result:"REFUSED")<<"\n";
  }else if(op=="S"){string a,b;in>>a>>b;
   std::cout<<(NativeUnitsSubtract(a,b,result)?result:"REFUSED")<<"\n";
  }else if(op=="B"){in>>currencyScale;
   for(int i=0;i<4;i++){string raw;in>>raw;char *end=nullptr;values[i]=std::strtod(raw.c_str(),&end);missing[i]=!end || *end!=0;}
   std::cout<<(NativeEntryCashBound("explicit-source-fixture",currencyScale,result)?result:"REFUSED")<<"\n";
  }else return 2;
 }
}
'''
    folder=tmp_path_factory.mktemp('actual-ea-cash-string-source-shim')
    cpp=folder/'original_ea_units.cpp';binary=folder/'original_ea_units'
    cpp.write_text(shim+units+amount+bound+main)
    built=subprocess.run([compiler,'-std=c++17','-O2','-Wall','-Wextra','-Werror',str(cpp),'-o',str(binary)],capture_output=True,text=True,timeout=30)
    assert built.returncode==0,built.stderr
    def execute(rows):
        result=subprocess.run([str(binary)],input='\n'.join(rows)+'\n',capture_output=True,text=True,timeout=15)
        assert result.returncode==0,result.stderr
        lines=result.stdout.splitlines();assert len(lines)==len(rows)
        return lines
    return execute


def units(value,scale,up):
    number=Fraction(value)*10**scale
    return -((-number.numerator)//number.denominator) if up else number.numerator//number.denominator


def test_actual_ea_text_source_matches_independent_fraction_floor_and_ceil(source_executable):
    rng=random.Random(118)
    values=['0','-0','0.1','0.10000000000000001','33.25000000000001','0.000000000000000001',
        '4.9406564584124654e-324','1.7976931348623157e+308','9007199254740993','99999999999999999']
    values+=[str(rng.randrange(1,10**17))+'e'+str(rng.randrange(-340,309)) for _ in range(1024)]
    rows=[];expected=[]
    for value in values:
        for up in [False,True]:
            scale=rng.randrange(17);rows.append(f'U {scale} {int(up)} '+json.dumps(value));expected.append(str(units(value,scale,up)))
    assert source_executable(rows)==expected


@pytest.mark.parametrize('value',['','None','null','nan','inf','-1','-0.0001','+1','1.','1e','1e+','1e401','1.2.3','1 2','1e1e1'])
def test_unavailable_or_malformed_money_is_never_zero(source_executable,value):
    assert source_executable(['U 2 1 '+json.dumps(value)])==['REFUSED']


def test_actual_ea_source_subtraction_retains_borrow_and_large_units_without_float(source_executable):
    rng=random.Random(51);pairs=[(10**100,1),(9007199254740993,9007199254740992),(1,2),(0,0)]
    pairs += [(rng.randrange(10**120),rng.randrange(10**120)) for _ in range(512)]
    assert source_executable([f'S {a} {b}' for a,b in pairs])==[str(a-b) if a>=b else 'REFUSED' for a,b in pairs]


def test_actual_ea_cash_bound_uses_original_units_and_credit_exclusion(source_executable):
    vectors=[(2,['100','95','0','100']),(2,['100','0','90','100']),
        (2,['1000','250.5','33.25','900']),(2,['0.1','0','0','0.1']),
        (16,['9007199254740992','0','1','9007199254740992']),
        (2,['100','-1','0','100']),(2,['missing','0','0','100']),
        (2,['100','0','nan','100']),(2,['100','0','0','inf']),
        (2,['10','0','10','10']),(2,['1','2','0','1'])]
    rows=[];expected=[]
    for scale,raw in vectors:
        rows.append('B '+str(scale)+' '+' '.join(raw))
        try:
            native=[float(x) for x in raw]
            if not all(math.isfinite(x) and x>=0 for x in native):raise ValueError
            # Match original MQL %.17g text at the native numeric boundary.
            a,b,c,d=[format(x,'.17g') for x in native]
            capacity=min(units(a,scale,False)-units(b,scale,True)-units(c,scale,True),units(d,scale,False))
            expected.append(str(max(0,capacity)))
        except ValueError:expected.append('REFUSED')
    assert source_executable(rows)==expected
