"""Read-only owner projection of original MT5 observations; no invented PnL."""
from vati.funding.mt5_journal import Mt5FundingBook
from vati.core.ledger import LedgerError
from vati.funding.mt5 import amount


def reported_mt5(ledger,event,profile,observation,mark,unknown):
    mismatch=unknown|{'reason':'CURRENT_PROFILE_NATIVE_SCOPE_MISMATCH'}
    if (profile.get('broker')!='MT5' or profile.get('alias')!=mark.get('account_alias')
        or profile.get('login')!=str(mark.get('login')) or profile.get('server')!=mark.get('server')
        or profile.get('currency')!=mark.get('currency') or type(profile.get('demo')) is not bool
        or profile['demo'] is not mark.get('demo')):return mismatch
    try:
        book=Mt5FundingBook(ledger)
        queries=book._queries(mark['scope_hash'])
        query=next((q for q in queries if q.hash==observation.get('query_ref')),None)
        statement=observation.get('statement')
        if (query is None or not isinstance(statement,dict) or query.payload['mark']!=mark
            or query.payload['scope_hash']!=observation.get('scope_hash')
            or query.payload['cash_statement_ref']!=statement.get('statement_ref')):
            raise LedgerError('mt5_snapshot_original_query_unavailable')
        if (amount(event.payload['equity'])!=amount(mark['net_equity'])
            or amount(event.payload['balance'])!=amount(mark['balance'])):
            raise LedgerError('mt5_snapshot_valuation_binding_invalid')
        # Timestamps alone do not establish availability when events share a
        # millisecond. The linked query must precede this actual snapshot.
        seen=False;found=False;latest_statement=None
        for original in ledger.iter():
            if original.hash==event.hash:
                found=True;break
            if (not seen and original.kind is book.kind
                and original.payload.get('scope_hash')==mark['scope_hash']):latest_statement=original.hash
            if original.hash==query.hash:seen=True
        if not seen or not found or latest_statement is None or query.received_time_ms>event.received_time_ms:
            raise LedgerError('mt5_snapshot_query_not_available')
        facts=book.observations(mark['scope_hash'],as_of=latest_statement)
        rows=[row|{'classification':{'category':'UNQUALIFIED_NATIVE_MT5_CASH','state':'UNQUALIFIED'}}
              for row in facts['movements']]
        return unknown|{'state':'CONFLICT' if facts['state']=='CONFLICT' else 'OBSERVED',
            'reason':'MT5_NATIVE_CASH_OBSERVED_NOT_ECONOMICALLY_QUALIFIED','scope_hash':mark['scope_hash'],
            'native_mark':mark,'snapshot_ref':event.hash,'query_ref':query.hash,
            'statement_ref':query.payload['cash_statement_ref'],'movement_count':len(rows),
            'movements':rows[-100:],'movements_truncated':len(rows)>100,'conflicts':facts['conflicts'],
            'collector_state':observation.get('collector_state','UNKNOWN'),
            'native_time_basis':'MT5_TERMINAL_NATIVE_NOT_UTC_QUALIFIED' if mark['source_kind']=='MT5_SIGNED_EA_POLL' else 'MT5_PYTHON_QUERY_UTC_HOST_NOT_BROKER_CLOCK',
            'money_basis':'NATIVE_DOUBLE_TEXT_NOT_SETTLED_MINOR_UNITS',
            'coverage_state':'SUCCESSFUL_AVAILABLE_HISTORY_QUERY_NOT_LIFETIME_OR_SETTLEMENT_CERTIFICATION'}
    except (KeyError,TypeError,ValueError,ArithmeticError,LedgerError):
        return unknown|{'state':'UNAVAILABLE','reason':'MT5_ORIGINAL_FUNDING_QUERY_UNAVAILABLE'}
