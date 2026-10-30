"""Runtime ingestion of original native facts, without any payment effect.

Cash-window coverage and return qualification are separate. The provider's total
historical equity is not silently treated as bonus-excluded equity. A failure to
read cash history does not disable protective position management.
"""
from decimal import Decimal
from vati.execution.base import VenueUnavailable
from vati.execution.ctrader.transport import CtraderApiError
from vati.funding.journal import FundingBook
from vati.funding.native import NativeAccountMark,native_int
from vati.core.units import UnitError
from vati.core.ledger import committed_source_snapshot
from vati.funding.movement_journal import FinancialMovementBook,MovementPublicationUnknown,STORAGE_ERRORS

WEEK_MS=604800000

def _financial_projection(ledger,scope_hash,*,materialize=False):
    book=FinancialMovementBook(ledger)
    try:
        if not materialize:return book.projection(scope_hash)
        result=book.materialize(scope_hash)
        # Repeated account snapshots retain a bounded receipt summary. The
        # current owner read model independently resolves original detail.
        rows=result.pop('movements')
        result['last_publication']=rows[-1]['publication'] if rows else None
        return result
    except MovementPublicationUnknown as error:
        return {'state':'UNKNOWN','reason':'FINANCIAL_PUBLICATION_UNKNOWN_RECONCILE_ORIGINAL_REQUEST',
            'original_request_id':error.request_id,'scope_hash':scope_hash,
            'current_original_source_verified':False,'settlement_qualification':'NOT_ISSUED',
            'risk_capital_qualified':False,'execution_authority':False}
    except (UnitError,*STORAGE_ERRORS):
        return {'state':'UNAVAILABLE','reason':'FINANCIAL_PROJECTION_UNAVAILABLE','scope_hash':scope_hash,
            'current_original_source_verified':False,'settlement_qualification':'NOT_ISSUED',
            'risk_capital_qualified':False,'execution_authority':False}

def _capture_deals(ledger,adapter,mark):
    from vati.funding.deal_journal import DealBook
    if not callable(getattr(adapter,'deal_history',None)):
        return {'state':'UNSUPPORTED','reason':'NATIVE_DEAL_HISTORY_NOT_PROVIDED'}
    book=DealBook(ledger);previous=book.observations(mark.scope_hash);windows=previous['coverage_windows']
    start=max(w['to_ms'] for w in windows) if windows else max(0,mark.observed_at_ms-WEEK_MS)
    if mark.registered_at_ms is not None:start=max(start,mark.registered_at_ms)
    if start>mark.observed_at_ms:return {'state':'UNAVAILABLE','reason':'OBSERVATION_CLOCK_MOVED_BACKWARD'}
    end=min(start+WEEK_MS,mark.observed_at_ms)
    try:statement=adapter.deal_history(from_ms=start,to_ms=end)
    except (CtraderApiError,VenueUnavailable,TimeoutError,ConnectionError,OSError):
        return {'state':'UNAVAILABLE','reason':'NATIVE_DEAL_HISTORY_UNAVAILABLE','retry_from_ms':start}
    if statement.scope_hash!=mark.scope_hash:
        return {'state':'UNAVAILABLE','reason':'NATIVE_ACCOUNT_BINDING_CHANGED','retry_from_ms':start}
    receipt=book.record_statement(statement)
    return {'state':'CONFLICT' if receipt['state']=='CONFLICT' or previous['state']=='CONFLICT' else 'OBSERVED',
        'statement':receipt,'coverage_from_ms':start,'coverage_to_ms':end,
        'catch_up_state':'PENDING' if end<mark.observed_at_ms else 'CURRENT_WINDOW_READ'}

def capture_funding(ledger,adapter,account,*,now_ms):
    native_int(now_ms,minimum=0)
    mark=getattr(account,'funding_mark',None)
    result={'state':'UNSUPPORTED','reason':'NATIVE_CASH_HISTORY_NOT_PROVIDED',
        'return_qualification':'NOT_ISSUED','execution_authority':False}
    if not isinstance(mark,NativeAccountMark):return result
    if (mark.account_alias!=account.account_alias or mark.currency!=account.currency or mark.balance!=account.balance
        or mark.net_equity!=account.equity or not account.verified):
        raise ValueError('funding_runtime_account_binding_invalid')
    native_int(mark.observed_at_ms,minimum=0)
    result.update(native_mark=mark.body(),scope_hash=mark.scope_hash,state='UNMEASURED',reason='NORMALIZED_HISTORICAL_VALUATION_NOT_QUALIFIED')
    book=FundingBook(ledger)
    # The native scope, not alias or a mutable frontend cache, owns the cursor.
    prior=book.observations(mark.scope_hash)
    windows=prior['coverage_windows']
    start=max(w['to_ms'] for w in windows) if windows else max(0,mark.observed_at_ms-WEEK_MS)
    if mark.registered_at_ms is not None:
        native_int(mark.registered_at_ms,minimum=0)
        start=max(start,mark.registered_at_ms)
    if start>mark.observed_at_ms:
        return result|{'state':'UNAVAILABLE','reason':'OBSERVATION_CLOCK_MOVED_BACKWARD'}
    end=min(start+WEEK_MS,mark.observed_at_ms)
    try:
        statement=adapter.cash_movements(from_ms=start,to_ms=end)
    except (CtraderApiError,VenueUnavailable,TimeoutError,ConnectionError,OSError):
        return result|{'state':'UNAVAILABLE','reason':'NATIVE_CASH_HISTORY_UNAVAILABLE','retry_from_ms':start}
    if statement.scope_hash!=mark.scope_hash:
        return result|{'state':'UNAVAILABLE','reason':'NATIVE_ACCOUNT_BINDING_CHANGED','retry_from_ms':start}
    # Journal failures propagate: an observation must never appear saved after a
    # failed commit. Repeating the original window recovers a lost commit ACK.
    receipt=book.record_statement(statement)
    deal_observation=_capture_deals(ledger,adapter,mark)
    financial_movements=_financial_projection(ledger,mark.scope_hash,materialize=True)
    return result|{'state':'CONFLICT' if receipt['state']=='CONFLICT' or prior['state']=='CONFLICT' else 'OBSERVED',
        'statement':receipt,'coverage_from_ms':start,'coverage_to_ms':end,
        'deal_observation':deal_observation,
        'financial_movements':financial_movements,
        'catch_up_state':'PENDING' if end<mark.observed_at_ms else 'CURRENT_WINDOW_READ'}

def reported_funding(ledger,event,account_record):
    with committed_source_snapshot(ledger):return _reported_funding(ledger,event,account_record)

def _reported_funding(ledger,event,account_record):
    """Read only facts linked by the original account snapshot and native scope."""
    unknown={'state':'UNMEASURED','reason':'NO_NATIVE_FUNDING_OBSERVATION','return_qualification':'NOT_ISSUED',
        'execution_authority':False,'movements':[],'movement_count':0,
        'financial_movements':{'state':'UNSUPPORTED','reason':'NATIVE_EXACT_CASH_POSTING_NOT_PROVIDED',
            'current_original_source_verified':False,'settlement_qualification':'NOT_ISSUED',
            'risk_capital_qualified':False,'execution_authority':False}}
    if event is None:return unknown
    p=event.payload;observation=p.get('funding_observation')
    if not isinstance(observation,dict):return unknown
    mark=p['native_account_mark'] if 'native_account_mark' in p else observation.get('native_mark')
    if not isinstance(mark,dict):return unknown|{'state':observation.get('state','UNMEASURED'),'reason':observation.get('reason','NO_NATIVE_FUNDING_OBSERVATION')}
    if mark.get('schema')=='mt5-account-mark/1':
        from vati.funding.mt5_report import reported_mt5
        return reported_mt5(ledger,event,account_record,observation,mark,unknown)
    from vati.core.canonical import canonical_hash
    scope={k:mark.get(k) for k in ('provider','environment','native_account_id','deposit_asset_id','currency')}
    expected_environment='DEMO' if account_record.get('demo') is True else 'LIVE' if account_record.get('demo') is False else None
    if (mark.get('scope_hash')!=canonical_hash(scope) or observation.get('scope_hash')!=mark.get('scope_hash')
        or mark.get('account_alias')!=account_record['alias'] or mark.get('currency')!=account_record.get('currency')
        or scope['provider']!=account_record.get('broker') or scope['environment']!=expected_environment):
        return unknown|{'reason':'CURRENT_PROFILE_NATIVE_SCOPE_MISMATCH'}
    # No current login is inferred from old alias-only snapshots. cTrader login
    # in the registry is its native ctidTraderAccountId, not its display login.
    login=account_record.get('login')
    if not isinstance(login,str) or login!=str(scope['native_account_id']):
        return unknown|{'reason':'CURRENT_PROFILE_NATIVE_SCOPE_MISMATCH'}
    facts=FundingBook(ledger).observations(mark['scope_hash'])
    from vati.funding.deal_journal import DealBook
    from vati.funding.reconciliation import period_report
    deal_facts=DealBook(ledger).observations(mark['scope_hash'])
    from vati.funding.classification import classify
    rows=[row|{'classification':classify(row['movement']['operation'],Decimal(row['movement']['delta']))} for row in facts['movements']]
    return unknown|{'state':'CONFLICT' if facts['state']=='CONFLICT' else observation['state'],'reason':observation['reason'],
        'scope_hash':mark['scope_hash'],'native_mark':mark,'snapshot_ref':event.hash,
        'statement_ref':observation.get('statement',{}).get('statement_ref'),
        'coverage_windows':facts['coverage_windows'],'conflicts':facts['conflicts'],
        'movement_count':len(rows),'movements':rows[-100:],'movements_truncated':len(rows)>100,
        'collector_state':observation.get('collector_state','UNKNOWN'),
        'native_deals':{'state':deal_facts['state'],'deal_count':len(deal_facts['deals']),
            'deals':deal_facts['deals'][-100:],'deals_truncated':len(deal_facts['deals'])>100,
            'coverage_windows':deal_facts['coverage_windows'],'conflicts':deal_facts['conflicts']},
        'period':period_report(ledger,mark['scope_hash']),
        'financial_movements':_financial_projection(ledger,mark['scope_hash']),
        'catch_up_state':observation.get('catch_up_state','UNKNOWN')}
