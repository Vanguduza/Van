"""Explicit simulated-terminal cash telemetry; never live provider evidence."""
from copy import deepcopy


def cash_telemetry(account,*,credit,native_clock_ms,movements,currency_digits):
    result=deepcopy(account);binding={k:result[k] for k in ('login','server','currency','demo')}
    result['credit']=str(credit);result['currency_digits']=currency_digits
    result['funding']={'schema':'van.mt5.cash-telemetry/1','complete':True,'native_from_ms':0,
        'native_to_ms':native_clock_ms+1000,'native_clock_ms':native_clock_ms,
        'binding_before':binding,'balance_before':str(result['balance']),'credit_before':str(credit),'movements':deepcopy(movements)}
    result['balance']=str(result['balance']);result['equity']=str(result['equity'])
    return result
