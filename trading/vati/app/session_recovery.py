"""Reconstruct a session's original native entry state without replaying orders."""
from collections import Counter,defaultdict
from decimal import Decimal

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.execution.reconciliation import LedgerPosition
from vati.execution.recovery_scope import NativePositionHistory
from vati.execution.review import initial_risk_from_ledger
from vati.lifecycle.thesis import TradeThesis
from vati.risk.contracts import Direction


def number(value,*,positive=False):
    result=Decimal(str(value))
    if not result.is_finite() or (positive and result<=0):
        raise ValueError('original entry numerical evidence is invalid')
    return result


def original_context(history,iid):
    """Only context available before the first original native command counts."""
    command,_=history.commands[iid];contexts={};risks=[]
    for event in history.rows:
        if event.hash==history.command_refs[iid]:
            break
        if event.correlation_id!=iid or event.producer!='vati-cycle' or event.hash!=canonical_hash(event.body()):
            continue
        p=event.payload
        if event.kind is EventKind.RISK_DECISION and p.get('account_alias')==history.account_alias:
            decision=p.get('decision',{});intent=p.get('inputs',{}).get('intent',{})
            if (decision.get('decision_hash')==command['decision_hash']
                and decision['decision_hash']==canonical_hash({k:v for k,v in decision.items() if k!='decision_hash'})
                and intent.get('account_alias')==history.account_alias and intent.get('trade_intent_id')==iid):
                risks.append(decision)
        if (event.kind is not EventKind.SESSION or p.get('event')!='ENTRY_CONTEXT'
            or p.get('schema')!='vati.entry-context/1' or p.get('account_alias')!=history.account_alias
            or p.get('decision_hash')!=command['decision_hash']):
            continue
        try:
            context=dict(p['context'])
            if p['context_hash']!=canonical_hash(context):continue
            if any(context.get(k)!=command[k] for k in ('symbol','strategy_id','direction')):continue
            if any(type(context[k]) is not bool for k in ('opened_in_blackout','event_certified','execution_policy_applied')):continue
            if any(not isinstance(context[k],str) or not context[k] for k in ('regime','session','event_window')):continue
            if number(context['cost_pct'])<0 or not 0<number(context['original_approved_risk_pct'],positive=True)<=1:continue
            contexts[p['context_hash']]=context
        except (KeyError,TypeError,ValueError,ArithmeticError):
            continue
    if len(contexts)!=1 or not risks:
        return None
    result=next(iter(contexts.values()))
    if any(number(r['approved_risk_pct'])!=number(result['original_approved_risk_pct']) for r in risks):
        return None
    result['cost_pct']=number(result['cost_pct'])
    result['original_approved_risk_pct']=number(result['original_approved_risk_pct'])
    result['targets']=tuple(number(v,positive=True) for v in result['targets'])
    if result['targets']!=tuple(number(v,positive=True) for v in command.get('targets',())):
        return None
    return result


def recover_session(cycle,positions):
    try:
        return _recover_session(cycle,positions)
    except Exception:
        # Malformed/unreadable native financial evidence cannot become a
        # healthy empty snapshot. Keep already restored protection in place.
        return (),('native-session-recovery-incomplete',)


def _recover_session(cycle,positions):
    """Return expected ledger positions and unresolved original identities.

    Current venue positions supply current quantities/stops. Original command,
    risk, setup, thesis and cost evidence supply historical facts. A cold paper
    adapter is an empty process, not proof that durable exposure disappeared.
    """
    cfg=cycle.cfg;issues=set();expected={}
    try:
        history=NativePositionHistory(cycle.ledger,account_alias=cfg.account_alias,venue=cfg.venue)
    except Exception:
        return (),('native-position-history-unavailable',)
    receipts=defaultdict(list)
    for event in history.events(EventKind.EXECUTION_RECEIPT):
        p=event.payload;command=history.commands[event.correlation_id][0]
        if p.get('decision_hash')==command['decision_hash'] and not p.get('exit_action'):
            receipts[event.correlation_id].append(p)
    closed=set()
    for event in history.events(EventKind.TRADE_REVIEW):
        p=event.payload
        try:
            if (p.get('broker_ok') is True and p.get('record_revision',0)==0
                and p.get('outcome') not in {'UNKNOWN','BROKER_FAILURE'}
                and not str(p.get('pnl_basis','')).startswith('UNKNOWN')):
                number(p['pnl']);closed.add(event.correlation_id)
        except (KeyError,ValueError,ArithmeticError):pass
    tca={}
    for event in history.events(EventKind.TCA_RECORD):
        try:tca[event.correlation_id]=number(event.payload['cost_ratio'])
        except (KeyError,ValueError,ArithmeticError):pass
    theses=defaultdict(dict)
    for event in history.events(EventKind.TRADE_THESIS):
        try:
            thesis=TradeThesis.from_payload(event.payload);command=history.commands[event.correlation_id][0]
            if thesis.seal_ok() and thesis.strategy_id==command['strategy_id'] and thesis.direction==command['direction']:
                theses[event.correlation_id][thesis.seal]=thesis
        except (KeyError,TypeError,ValueError,ArithmeticError):pass
    health=defaultdict(list)
    for event in history.events(EventKind.TRADE_HEALTH):health[event.correlation_id].append(event.payload)
    counts=Counter(p.trade_intent_id for p in positions)
    restored=set()
    for position in positions:
        iid=position.trade_intent_id;joined=history.position_command(position)
        if joined is None or counts[iid]!=1 or position.symbol!=cfg.symbol:
            issues.add(iid or position.position_id);continue
        command,opened=joined
        software=command['stop_mode']=='SOFTWARE'
        try:
            initial=None if command.get('protective_stop') is None else number(command['protective_stop'],positive=True)
            current=initial if software else position.stop_price
            expected[iid]=LedgerPosition(iid,position.symbol,position.quantity,initial,software)
            if initial is not None:
                if current is None:raise ValueError('current native protection is missing')
                cycle.protection.restore(position.position_id,symbol=position.symbol,direction=position.direction,
                    entry=position.entry_price,initial_stop=initial,current_stop=number(current,positive=True),
                    target=number(command['targets'][0]) if command.get('targets') else None,
                    opened_ms=opened,software_stop=software)
            context=original_context(history,iid)
            thesis=next(iter(theses[iid].values())) if len(theses[iid])==1 else None
            risk=initial_risk_from_ledger(cycle.ledger,iid,available_cutoff_ms=opened)
            complete=(context is not None and thesis is not None and thesis.entry==position.entry_price
                      and risk is not None and iid in tca and iid not in closed)
            row={'symbol':position.symbol,'entry':position.entry_price,'stop':current,'direction':position.direction,
                'strategy_id':command.get('strategy_id',''),'decision_price':number(command['entry_price']),
                'quantity':position.quantity,'broker_position_id':position.position_id,'opened_ms':opened,
                'targets':tuple(number(v) for v in command.get('targets',())),
                'open':True,'pending':False,'protective_stop_confirmed':current is not None,
                'best_price':position.entry_price,'worst_price':position.entry_price,
                'recovered':True,'recovery_context_complete':complete,'cost_ratio':tca.get(iid),
                'cost_pct':None,'original_approved_risk_pct':None}
            if context is not None:row.update(context)
            if thesis is not None and complete:
                cycle.thesis.adopt(thesis)
                sign=Decimal(1) if position.direction is Direction.LONG else Decimal(-1)
                for fact in health[iid]:
                    try:
                        mfe=max(Decimal(0),number(fact['mfe_r']));mae=max(Decimal(0),number(fact['mae_r']))
                        best=position.entry_price+sign*mfe*thesis.risk_distance
                        worst=position.entry_price-sign*mae*thesis.risk_distance
                        row['best_price']=(max if sign>0 else min)(row['best_price'],best)
                        row['worst_price']=(min if sign>0 else max)(row['worst_price'],worst)
                    except (KeyError,ValueError,ArithmeticError):continue
            cycle._entries[iid]=row;restored.add(iid)
            if not complete:issues.add(iid)
        except (KeyError,TypeError,ValueError,ArithmeticError):issues.add(iid)
    for iid,(command,_) in history.commands.items():
        if iid in restored or iid in closed:continue
        facts=receipts[iid]
        filled=[p for p in facts if p.get('status') in {'FILLED','PARTIAL','OWNER_EXECUTED','BROKER_CONFIRMED'}
                and number(p.get('filled_qty','0'))>0]
        if filled:
            p=filled[0]
            expected[iid]=LedgerPosition(iid,command['symbol'],number(p['filled_qty'],positive=True),
                None if command.get('protective_stop') is None else number(command['protective_stop']),
                command['stop_mode']=='SOFTWARE')
        else:
            no_effect={'REJECTED','CANCELLED','EXPIRED'}
            clean=bool(facts) and all(p.get('status') in no_effect and number(p.get('filled_qty','0'))==0 for p in facts)
            observation=facts[-1].get('native_entry_observation',{}) if facts else {}
            resolved=(bool(facts) and facts[-1].get('status') in no_effect
                and number(facts[-1].get('filled_qty','0'))==0
                and all(number(p.get('filled_qty','0'))==0 for p in facts)
                and observation=={'schema':'vati.native-entry-observation/1',
                    'command_hash':command['command_hash'],'source':'ORIGINAL_NATIVE_RESULT'})
            if not clean and not resolved:issues.add(iid)
    return tuple(expected.values()),tuple(sorted(issues))
