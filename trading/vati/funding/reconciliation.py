"""Native balance-version reconciliation and explicitly scoped marked returns.

No historical bonus is guessed from current bonuses. Returns spanning external
flows require normalized historical flow valuations; otherwise they are unknown.
"""
from decimal import Decimal
from fractions import Fraction
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.core.ledger import LedgerError
from vati.funding.classification import classify
from vati.funding.deal_journal import DealBook
from vati.funding.journal import FundingBook
from vati.funding.native import NativeAccountMark
from vati.funding.unitization import unitize,_render
from vati.funding.valuation import ValuationSnapshot

POLICY_VERSION='native-balance-period/1.0.0'

def covers(windows,start,end):
    cursor=start
    for row in sorted(windows,key=lambda row:(row['from_ms'],row['to_ms'])):
        lo,hi=row['from_ms'],row['to_ms']
        if hi<cursor:continue
        if lo>cursor:return False
        cursor=hi+1
        if cursor>end:return True
    return False

def _marks(ledger,scope):
    rows=[]
    for event in ledger.iter(EventKind.ACCOUNT_SNAPSHOT):
        p=event.payload;body=p.get('native_account_mark')
        if not isinstance(body,dict):continue
        candidate=canonical_hash({k:body.get(k) for k in ('provider','environment','native_account_id','deposit_asset_id','currency')})
        if scope not in {candidate,body.get('scope_hash')}:continue
        try:
            valuation=ValuationSnapshot(event)
            mark=NativeAccountMark.from_body(valuation.body()['native_mark'])
            if mark.scope_hash!=scope:raise ValueError()
        except (KeyError,TypeError,ValueError,ArithmeticError) as exc:raise LedgerError('native_account_mark_source_invalid') from exc
        rows.append((event,mark))
    return rows

def period_report(ledger,scope_hash,*,baseline_ref=None,closing_ref=None):
    result={'policy_version':POLICY_VERSION,'scope_hash':scope_hash,'state':'UNMEASURED','reason':'NATIVE_MARKS_UNAVAILABLE',
        'balance_state':'UNRECONCILED','return_qualification':'NOT_ISSUED','trade_alpha_claimed':False,
        'balance_reconciliation_basis':'NATIVE_BALANCE_VERSIONS_AND_POST_OPERATION_BALANCES',
        'trade_cost_settlement_qualification':'NOT_ISSUED',
        'execution_authority':False,'performance':None,'external_flows':[],'evidence_refs':[],
        'valuation_snapshots':None,
        'cash_neutral_net_account_pnl':None,'separate_business_income_or_expense':None,
        'net_account_pnl_excluding_capital_and_separate_business':None}
    with ledger.read_snapshot():
        if not ledger.verify_incremental()[0]:raise LedgerError('native_period_journal_invalid')
        marks=_marks(ledger,scope_hash)
        if not marks:return result
        if any(marks[i][1].observed_at_ms<marks[i-1][1].observed_at_ms for i in range(1,len(marks))):
            return result|{'reason':'NATIVE_OBSERVATION_CLOCK_MOVED_BACKWARD'}
        cash=FundingBook(ledger).observations(scope_hash);deals=DealBook(ledger).observations(scope_hash)
        result['knowledge_through_received_ms']=max([source.received_time_ms for source,_ in marks]
            +[body['knowledge_through_received_ms'] for body in (cash,deals) if body['knowledge_through_received_ms'] is not None])
        result['knowledge_basis']='LATEST_OBSERVED_HISTORY_NOT_AS_KNOWN_AT_TRADE_TIME'
        if cash['state']=='CONFLICT' or deals['state']=='CONFLICT':return result|{'reason':'NATIVE_HISTORY_CONFLICT'}
        baseline=next((row for row in marks if row[0].hash==baseline_ref),None) if baseline_ref else marks[0]
        if baseline is None:return result|{'reason':'BASELINE_SOURCE_REF_NOT_FOUND'}
        first,b=baseline
        covered=[row for row in marks if row[1].observed_at_ms>=b.observed_at_ms
            and covers(cash['coverage_windows'],b.observed_at_ms,row[1].observed_at_ms)
            and covers(deals['coverage_windows'],b.observed_at_ms,row[1].observed_at_ms)]
        closing=next((row for row in covered if row[0].hash==closing_ref),None) if closing_ref else (covered[-1] if covered else None)
        if closing is None:return result|{'reason':'NATIVE_PERIOD_COVERAGE_INCOMPLETE','baseline_ref':first.hash}
        last,c=closing
        first_valuation,last_valuation=ValuationSnapshot(first),ValuationSnapshot(last)
        result.update(baseline_ref=first.hash,closing_ref=last.hash,from_ms=b.observed_at_ms,to_ms=c.observed_at_ms,
            latest_mark_ms=marks[-1][1].observed_at_ms,
            valuation_snapshots={'baseline':first_valuation.body(),'closing':last_valuation.body()},
            baseline_balance=str(b.balance),closing_balance=str(c.balance))
        result['coverage_state']='CURRENT_MARK_COVERED' if last.hash==marks[-1][0].hash else 'OLDER_COVERED_MARK'
        if first.hash==last.hash:return result|{'reason':'NO_COVERED_LATER_MARK'}
        if b.balance_version is None or c.balance_version is None:return result|{'reason':'NATIVE_BALANCE_VERSION_UNAVAILABLE'}
        if c.balance_version<b.balance_version:return result|{'reason':'NATIVE_BALANCE_VERSION_MOVED_BACKWARD'}
        if c.balance_version-b.balance_version>64000:return result|{'reason':'NATIVE_BALANCE_PERIOD_RESOURCE_BOUND'}
        changes={};external=[];business=Fraction(0);refs=[first.hash,last.hash]
        def add(version,after,ref,kind,delta=None):
            if version in changes:return False
            changes[version]=(Fraction(Decimal(after)),ref,kind,Fraction(Decimal(delta)) if delta is not None else None)
            return True
        for observed in cash['movements']:
            row=observed['movement'];version=row['balance_version'];classification=classify(row['operation'],Decimal(row['delta']))
            inside=b.observed_at_ms<row['occurred_at_ms']<=c.observed_at_ms
            if version is None:
                if inside and classification['category']!='RESTRICTED_CREDIT':return result|{'reason':'NATIVE_CASH_ORDER_UNAVAILABLE'}
                continue
            if not b.balance_version<version<=c.balance_version:continue
            if classification['state']!='CLASSIFIED':return result|{'reason':'NATIVE_CASH_CLASSIFICATION_UNRESOLVED'}
            category=classification['category'];ref=observed['original_statement_ref']
            if not add(version,row['balance_after'],ref,category,row['delta']):return result|{'reason':'NATIVE_BALANCE_VERSION_COLLISION'}
            if category=='OTHER_BUSINESS_INCOME_OR_EXPENSE':business+=Fraction(Decimal(row['delta']))
            if category in {'EXTERNAL_CAPITAL','BROKER_SUPPORT_CAPITAL'} and Decimal(row['delta'])!=0:
                external.append({'native_id':row['native_id'],'operation':row['operation'],'delta':row['delta'],
                    'balance_version':version,'statement_ref':ref,'historical_total_equity':row['equity_after']})
        for observed in deals['deals']:
            row=observed['deal'];detail=row['close']
            if detail is None:continue
            version=detail['balance_version'];inside=b.observed_at_ms<row['occurred_at_ms']<=c.observed_at_ms
            if version is None:
                if inside:return result|{'reason':'NATIVE_CLOSE_ORDER_UNAVAILABLE'}
                continue
            if not b.balance_version<version<=c.balance_version:continue
            if not add(version,detail['balance_after'],observed['original_statement_ref'],'NATIVE_CLOSE'):
                return result|{'reason':'NATIVE_BALANCE_VERSION_COLLISION'}
        balance=Fraction(b.balance);balances={b.balance_version:balance}
        for version in range(b.balance_version+1,c.balance_version+1):
            if version not in changes:return result|{'reason':'NATIVE_BALANCE_VERSION_GAP','missing_version':version}
            after,ref,kind,delta=changes[version]
            if delta is not None:
                expected=balance if kind=='RESTRICTED_CREDIT' else balance+delta
                if after!=expected:return result|{'reason':'NATIVE_CASH_BALANCE_MISMATCH','balance_version':version}
            balance=after;balances[version]=balance;refs.append(ref)
        if balance!=Fraction(c.balance):return result|{'reason':'NATIVE_CLOSING_BALANCE_MISMATCH'}
        start_index=next(i for i,row in enumerate(marks) if row[0].hash==first.hash)
        end_index=next(i for i,row in enumerate(marks) if row[0].hash==last.hash)
        if end_index<=start_index:return result|{'reason':'NATIVE_MARK_ORDER_INVALID'}
        samples=marks[start_index:end_index+1];previous=b.balance_version
        for source,mark in samples:
            if mark.balance_version is None:return result|{'reason':'NATIVE_INTERMEDIATE_MARK_VERSION_UNAVAILABLE'}
            if mark.balance_version<previous or mark.balance_version not in balances:return result|{'reason':'NATIVE_INTERMEDIATE_MARK_ORDER_INVALID'}
            if Fraction(mark.balance)!=balances[mark.balance_version]:return result|{'reason':'NATIVE_INTERMEDIATE_MARK_BALANCE_MISMATCH'}
            previous=mark.balance_version;refs.append(source.hash)
        result.update(balance_state='RECONCILED',external_flows=sorted(external,key=lambda row:row['balance_version']),evidence_refs=list(dict.fromkeys(refs)))
        external_total=sum((Fraction(Decimal(row['delta'])) for row in external),Fraction(0))
        neutral_pnl=Fraction(c.net_equity)-Fraction(b.net_equity)-external_total
        result.update(cash_neutral_net_account_pnl=_render(neutral_pnl),separate_business_income_or_expense=_render(business),
            net_account_pnl_excluding_capital_and_separate_business=_render(neutral_pnl-business),
            cash_neutral_pnl_basis='NATIVE_NET_MARKS_MINUS_RECONCILED_EXTERNAL_CAPITAL_NOT_SETTLED_TRADE_ALPHA')
        if external:return result|{'reason':'NORMALIZED_HISTORICAL_FLOW_EQUITY_UNAVAILABLE'}
        performance=unitize(first_valuation.equity_point(),last_valuation.equity_point())
        if performance['status']=='MEASURED':
            peak=Fraction(b.net_equity);worst=Fraction(0)
            for source,mark in samples:
                net=Fraction(mark.net_equity);peak=max(peak,net);worst=max(worst,(peak-net)/peak)
            performance['worst_observed_drawdown']=_render(worst)
            performance['input_refs']=[source.hash for source,_ in samples]
            performance['evidence_refs']=result['evidence_refs']
        return result|{'state':performance['status'],'reason':performance.get('reason'),
            'performance':performance,'return_basis':'MARKED_ACCOUNT_RETURN_WITH_NATIVE_BALANCE_RECONCILIATION',
            'drawdown_basis':'SAMPLED_MARKS_ONLY_NOT_INTRAPERIOD_EXTREMA'}
