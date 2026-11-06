"""Native account margin facts; absence is never an available balance."""
from decimal import Decimal, localcontext
from vati.funding.mt5 import amount


def mt5_margin(account):
    def read(name):
        try:return amount(account[name])
        except (KeyError,TypeError,ValueError,ArithmeticError):return None
    used=read('margin_used');free=read('margin_free');level=read('margin_level')
    if used is not None and used<0:used=None
    # MT5 reports zero for a flat account's undefined equity/margin ratio.
    # Keep the actual zero committed margin; do not invent an infinite ratio.
    if used==0 and level==0:level=None
    return used,free,level


def mt5_risk_equity(account):
    """Exclude known broker credit even if cash-history coverage is unavailable."""
    equity=amount(str(account['equity']))
    try:credit=amount(account['credit'])
    except (KeyError,TypeError,ValueError,ArithmeticError):return equity
    if credit<0:return equity  # A native liability needs qualification, not extra risk capital.
    with localcontext() as context:
        context.prec=512
        return equity-credit


def account_margin_body(adapter, account, *, observed_at_ms):
    """Original account facts plus explicitly calculated risk bounds; no action."""
    from vati.execution.paper import PaperAdapter
    from vati.execution.zse_ticket import OwnerTicketAdapter
    from vati.execution.mt5_bridge import Mt5BridgeAdapter
    from vati.execution.mt5_pull import Mt5PullAdapter
    from vati.execution.ctrader.adapter import CtraderAdapter
    if isinstance(adapter,PaperAdapter):basis='PAPER_SIMULATION'
    elif isinstance(adapter,OwnerTicketAdapter):basis='OWNER_TICKET_NO_BROKER_MARGIN'
    elif isinstance(adapter,(Mt5BridgeAdapter,Mt5PullAdapter)):basis='MT5_NATIVE_ACCOUNT_INFORMATION'
    elif isinstance(adapter,CtraderAdapter):basis='CTRADER_NATIVE_PER_SYMBOL_MARGIN_CASH_EQUITY_BOUND'
    else:basis='UNKNOWN'
    used,free,level=(getattr(account,name,None) for name in ('used_margin','free_margin','margin_level_pct'))
    finite=all(v is None or type(v) is Decimal and v.is_finite() for v in (used,free,level))
    known=finite and type(account.equity) is Decimal and account.equity.is_finite() and used is not None and used>=0 and free is not None and (used==0 and level is None or used>0 and level is not None)
    if basis=='MT5_NATIVE_ACCOUNT_INFORMATION' and getattr(account,'native_observation',None) is not None:
        known=known and account.native_observation.risk_equity is not None
    risk_free=risk_level=None
    if known:
        from vati.risk.margin import cash_margin_bounds
        risk_free,risk_level=cash_margin_bounds(account.equity,used,free,level)
    state=('SIMULATED' if basis=='PAPER_SIMULATION' else 'NOT_APPLICABLE' if basis=='OWNER_TICKET_NO_BROKER_MARGIN'
        else 'OBSERVED' if known and basis!='UNKNOWN' else 'UNAVAILABLE')
    def text(v):return str(v) if v is not None and type(v) is Decimal and v.is_finite() else None
    return {'schema':'vati.account-margin/1','state':state,'basis':basis,'account_alias':account.account_alias,
        'observed_at_ms':observed_at_ms,'used_margin':text(used),'free_margin':text(free),
        'margin_level_pct':text(level),'risk_free_margin_bound':text(risk_free),'risk_margin_level_bound_pct':text(risk_level),
        'margin_level_applicable':used>0 if known else None,'execution_authority':False}


def reported_account_margin(snapshot, alias):
    from vati.core.canonical import canonical_hash
    from vati.core.events import EventKind
    unknown={'state':'UNMEASURED','execution_authority':False}
    if snapshot is None:return unknown
    try:
        p=snapshot.payload['margin']
        if (snapshot.kind is not EventKind.ACCOUNT_SNAPSHOT or snapshot.producer not in {'vati-service','vati-account-service'}
            or snapshot.hash!=canonical_hash(snapshot.body()) or p['schema']!='vati.account-margin/1'
            or p['account_alias']!=alias or snapshot.payload['account_alias']!=alias or p['execution_authority'] is not False
            or type(p['observed_at_ms']) is not int or not 0<=snapshot.event_time_ms<=p['observed_at_ms']<=snapshot.received_time_ms
            or p['state'] not in {'OBSERVED','SIMULATED','NOT_APPLICABLE','UNAVAILABLE'}):raise ValueError()
        if p['state']=='OBSERVED':
            if p['basis'] not in {'MT5_NATIVE_ACCOUNT_INFORMATION','CTRADER_NATIVE_PER_SYMBOL_MARGIN_CASH_EQUITY_BOUND'}:
                raise ValueError()
            def money(key):
                value=p[key]
                if value is None:return None
                if key.startswith('risk_'):
                    if type(value) is not str or not 1<=len(value)<=1024:raise ValueError()
                    result=Decimal(value)
                    if not result.is_finite():raise ValueError()
                    return result
                return amount(value)
            used,free,level=(money(key) for key in ('used_margin','free_margin','margin_level_pct'))
            risk_free,risk_level=(money(key) for key in ('risk_free_margin_bound','risk_margin_level_bound_pct'))
            if (used is None or used<0 or free is None or risk_free is None
                or type(p['margin_level_applicable']) is not bool or p['margin_level_applicable']!=(used>0)
                or used>0 and (level is None or risk_level is None)
                or used==0 and (level is not None or risk_level is not None)):raise ValueError()
            from vati.risk.margin import cash_margin_bounds
            expected_free,expected_level=cash_margin_bounds(amount(snapshot.payload['equity']),used,free,level)
            if (risk_free,risk_level)!=(expected_free,expected_level):raise ValueError()
        return {k:p[k] for k in ('state','basis','observed_at_ms' ,'used_margin','free_margin','margin_level_pct',
            'risk_free_margin_bound','risk_margin_level_bound_pct','margin_level_applicable','execution_authority')}|{
            'snapshot_ref':snapshot.hash,'received_at_ms':snapshot.received_time_ms}
    except (KeyError,TypeError,ValueError,ArithmeticError,AttributeError):
        return unknown|{'state':'UNAVAILABLE','reason':'ACCOUNT_MARGIN_PROOF_NOT_BOUND'}
