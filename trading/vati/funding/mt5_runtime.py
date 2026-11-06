"""Local authenticated-cache ingestion. No command or provider I/O is performed."""
from decimal import Decimal
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.funding.mt5 import Mt5FundingFrame
from vati.funding.mt5_journal import Mt5FundingBook
from vati.risk.history_scope import risk_history_for_account


def capture_cached_mt5(ledger,account,*,now_ms):
    frame=getattr(account,'funding_mark',None)
    if not isinstance(frame,Mt5FundingFrame):return None
    ref,receipt=Mt5FundingBook(ledger,clock=lambda:now_ms).capture(frame)
    return {'state':receipt['state'],'reason':'MT5_NATIVE_CASH_OBSERVED_NOT_ECONOMICALLY_QUALIFIED',
        'scope_hash':frame.scope_hash,'native_mark':frame.mark_body(),'statement':receipt,'query_ref':ref,
        'return_qualification':'NOT_ISSUED','execution_authority':False}


def mt5_risk_fence(ledger,adapter,account,*,now_ms):
    from vati.execution.mt5_pull import Mt5PullAdapter
    from vati.execution.mt5_bridge import Mt5BridgeAdapter
    from vati.funding.risk_fence import FundingRiskFence
    def hold(reason):return FundingRiskFence(False,'FUNDING_RISK_UNAVAILABLE:'+reason)
    frame=getattr(account,'funding_mark',None);identity=getattr(adapter,'identity',None)
    if not isinstance(adapter,(Mt5PullAdapter,Mt5BridgeAdapter)) or not isinstance(frame,Mt5FundingFrame):
        return hold('MT5_NATIVE_CASH_HISTORY_UNAVAILABLE')
    if identity is None:return hold('MT5_NATIVE_PHYSICAL_BINDING_UNAVAILABLE')
    identity.validate({'login':frame.login,'server':frame.server,'currency':frame.currency,'demo':frame.demo})
    Mt5FundingFrame.from_body(frame.body())
    if (account.verified is not True or account.account_alias!=adapter.account_alias or frame.account_alias!=account.account_alias
        or account.currency!=frame.currency or account.balance!=frame.balance or account.equity!=frame.net_equity):
        return hold('MT5_NATIVE_ACCOUNT_BINDING_INVALID')
    if frame.observed_at_ms>now_ms:return hold('CURRENT_NATIVE_MARK_AFTER_DECISION_TIME')
    with ledger.read_snapshot():
        if not ledger.verify_incremental()[0]:return hold('MT5_NATIVE_JOURNAL_INVALID')
        book=Mt5FundingBook(ledger);events=book._events(frame.scope_hash);queries=book._queries(frame.scope_hash)
        if not events or not queries:return hold('MT5_ORIGINAL_CASH_QUERY_UNAVAILABLE')
        if any(e.payload['state']=='CONFLICT' for e in events):return hold('MT5_NATIVE_CASH_HISTORY_CONFLICT')
        current=next((e for e in queries if e.payload['source_ref']==frame.source_ref),None)
        if current is None:return hold('MT5_CURRENT_QUERY_NOT_RECORDED')
        if max(e.received_time_ms for e in [*events,*queries])>now_ms:return hold('NATIVE_FUNDING_AFTER_DECISION_TIME')
        first=queries[0];baseline=next(e for e in events if e.hash==first.payload['cash_statement_ref'])
        original=Mt5FundingFrame.from_body(baseline.payload['statement'])
        if any(e.payload['mark']['source_kind']!=frame.source_kind for e in queries):
            return hold('MT5_NATIVE_QUERY_CLOCK_BASIS_CHANGED')
        if frame.native_clock_ms<max(e.payload['mark']['native_clock_ms'] for e in queries):return hold('MT5_NATIVE_CLOCK_MOVED_BACKWARD')
        if any(Decimal(e.payload['mark']['credit'])!=original.credit for e in queries):return hold('MT5_CREDIT_CHANGE_REQUIRES_RISK_NORMALIZATION')
        # No ordering is inferred from ticket numbers or unqualified native clocks.
        before={r.native_id:r.body() for r in original.movements};after={r.native_id:r.body() for r in frame.movements}
        if any(r['native_id'] not in before for e in events for r in e.payload['statement']['movements']):
            return hold('FLOW_ADJUSTED_RISK_NOT_QUALIFIED')
        if any(k not in after for k in before):return hold('MT5_NATIVE_CASH_HISTORY_SHRANK')
        if set(after)-set(before):return hold('FLOW_ADJUSTED_RISK_NOT_QUALIFIED')
        if before!=after:return hold('MT5_NATIVE_CASH_HISTORY_CONFLICT')
        known={'DEAL_TYPE_BALANCE','DEAL_TYPE_CREDIT','DEAL_TYPE_CHARGE','DEAL_TYPE_COMMISSION','DEAL_TYPE_COMMISSION_DAILY',
            'DEAL_TYPE_COMMISSION_MONTHLY','DEAL_TYPE_COMMISSION_AGENT_DAILY','DEAL_TYPE_COMMISSION_AGENT_MONTHLY','DEAL_TYPE_INTEREST',
            'DEAL_TYPE_DIVIDEND','DEAL_TYPE_DIVIDEND_FRANKED','DEAL_TYPE_TAX'}
        if any(r.operation not in known for r in original.movements):return hold('MT5_RISK_CAPITAL_BASIS_UNQUALIFIED')
        history=risk_history_for_account(ledger.iter(),frame.account_alias)
        if history.issue:return hold('ORIGINAL_RISK_HISTORY_UNRESOLVED')
        for event in history.events:
            if max(event.event_time_ms,event.received_time_ms)>now_ms:return hold('ORIGINAL_RISK_AFTER_DECISION_TIME')
            if event.kind not in {EventKind.RISK_DECISION,EventKind.TRADE_REVIEW}:continue
            if event.kind is EventKind.RISK_DECISION and event.payload.get('decision',{}).get('decision')=='REJECTED':continue
            if event.received_time_ms<first.received_time_ms:return hold('ORIGINAL_RISK_PREDATES_NATIVE_FUNDING_BASELINE')
        for event in ledger.iter(EventKind.ORDER_COMMAND):
            if event.payload.get('account_alias')==frame.account_alias and event.received_time_ms<first.received_time_ms:
                return hold('ORIGINAL_ORDER_PREDATES_NATIVE_FUNDING_BASELINE')
        return FundingRiskFence(True,'MT5_NATIVE_NO_NEW_CASH_FACTS:'+first.hash+':'+current.hash)
