"""Current account/portfolio facts, never a second permission or an order.

The execution router invokes its bound RiskAuthority on these facts. A provider
cannot return a boolean approval or replace the original intent/command.
"""
from dataclasses import dataclass
from decimal import Decimal

from vati.risk.contracts import RiskSnapshot
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.risk.authority import _canonical_hash
from vati.risk.serde import snapshot_from_dict


@dataclass(frozen=True)
class CurrentRiskFacts:
    snapshot: RiskSnapshot
    observed_at_ms: int


def reported_current_risk(event, original):
    """Minimal read-only proof, bound to this trade's original approval."""
    unknown={'state':'UNMEASURED','execution_authority':False}
    if event is None:return unknown
    try:
        p=event.payload;before=original.payload['decision'];intent=original.payload['inputs']['intent']
        fresh=p['decision'];body={k:v for k,v in fresh.items() if k!='decision_hash'}
        qty=Decimal(p['original_command_quantity']);limit=Decimal(fresh['approved_size'])
        if (event.kind is not EventKind.RISK_REVALIDATION or event.producer!='vati-execution-router' or event.hash!=canonical_hash(event.body())
            or p['schema']!='vati.current-account-risk/1' or p['execution_authority'] is not False
            or p['original_decision_hash']!=before['decision_hash'] or p['account_alias']!=intent['account_alias']
            or event.correlation_id!=intent['trade_intent_id'] or fresh['trade_intent_id']!=intent['trade_intent_id']
            or not before.get('intent_hash') or fresh['intent_hash']!=before['intent_hash']
            or not before.get('mandate_hash') or fresh['mandate_hash']!=before['mandate_hash']
            or fresh['risk_snapshot_hash']!=_canonical_hash(snapshot_from_dict(p['snapshot']))
            or fresh['decision_hash']!=canonical_hash(body) or not qty.is_finite() or not limit.is_finite()
            or not 0<qty<=Decimal(before['approved_size']) or type(p['observed_at_ms']) is not int
            or not original.event_time_ms<=p['observed_at_ms']<=event.event_time_ms<=event.received_time_ms
            or p['snapshot']['now_unix']!=p['observed_at_ms']//1000
            or p['snapshot']['account_alias']!=intent['account_alias']):
            raise ValueError()
        fits=fresh['decision'] in {'APPROVED','REDUCED'} and qty<=limit
        if p['state']!=('SUFFICIENT' if fits else 'REFUSED'):raise ValueError()
        return {'state':p['state'],'reason_code':p['reason_code'],'reason_detail':p['reason_detail'],
            'proof_ref':event.hash,'original_decision_hash':p['original_decision_hash'],
            'original_command_hash':p['original_command_hash'],'decision_hash':fresh['decision_hash'],
            'observed_at_ms':p['observed_at_ms'],'received_at_ms':event.received_time_ms,
            'current_size_limit':fresh['approved_size'],'original_command_quantity':p['original_command_quantity'],
            'execution_authority':False}
    except (KeyError,TypeError,ValueError,ArithmeticError,AttributeError):
        return unknown|{'state':'UNAVAILABLE','reason_code':'CURRENT_RISK_PROOF_NOT_BOUND'}
