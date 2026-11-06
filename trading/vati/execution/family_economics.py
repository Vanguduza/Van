"""SOURCE-only native-owner observations for the family restatement consumer.

This implements the consumer contract, not a live deal/correction issuer. Real
per-deal correction/bust/late-charge production remains NOT_QUALIFIED. No default
issuer, provider certificate, trading authority or public control is supplied.
"""
from decimal import Decimal
from fractions import Fraction

from vati.authority import OwnerAuthorityVerifier
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.execution.paper import PaperAdapter
from vati.execution.recovery_scope import NativePositionHistory
from vati.risk.control_archive import archive_verified_control

SCHEMA='family-native-economic-source-observation/1'
PRODUCER='vati-synthetic-native-economic-owner'
KEYS=frozenset({'schema','evidence_domain','environment','account_alias','venue','family_id',
    'root_intent_id','currency','sequence','previous_ref','effective_at_ms','available_at_ms',
    'source_owner_id','source_revision','source_hash','deals'})
DEAL_KEYS=frozenset({'native_deal_id','entry_ref','exit_ref','position_id','trade_intent_id',
    'symbol','quantity','execution_price','net_cash_delta','currency','source_revision'})


class EconomicObservationError(ValueError):
    pass


def subject(body):return SCHEMA+':'+canonical_hash(body)


def _amount(value):
    if type(value) is not str or len(value)>256:
        raise EconomicObservationError('native economic amount must be exact bounded text')
    d=Decimal(value)
    if not d.is_finite():raise EconomicObservationError('native economic amount is nonfinite')
    return d


class SourceFamilyEconomicObservations:
    """Configured synthetic native OWNER trust, available only to exact Paper."""
    def __init__(self,ledger,adapter,*,issuer,clock):
        if type(adapter) is not PaperAdapter or not isinstance(issuer,OwnerAuthorityVerifier):
            raise EconomicObservationError('SOURCE economics requires explicit Paper owner/issuer configuration')
        self.ledger,self.adapter,self.issuer,self.clock=ledger,adapter,issuer,clock

    def _rows(self,family_id):
        return [e for e in self.ledger.iter(EventKind.SESSION,correlation_id=family_id)
            if e.producer==PRODUCER and e.payload.get('schema')==SCHEMA]

    def _validate(self,body,*,original_cash=None):
        if (type(body) is not dict or set(body)!=KEYS or body['schema']!=SCHEMA
                or body['evidence_domain']!='SOURCE' or body['environment']!='PAPER'
                or body['account_alias']!=self.adapter.account_alias or body['venue']!=self.adapter.venue
                or body['venue']!='paper' or body['currency']!=self.adapter.currency
                or type(body['sequence']) is not int or body['sequence']<0
                or type(body['effective_at_ms']) is not int or type(body['available_at_ms']) is not int
                or not 0<=body['effective_at_ms']<=body['available_at_ms']
                or not all(type(body[k]) is str and body[k] for k in
                    ('family_id','root_intent_id','source_owner_id','source_revision','source_hash'))
                or type(body['deals']) is not list or not 1<=len(body['deals'])<=10000):
            raise EconomicObservationError('SOURCE native economic scope/schema/provenance differs')
        history=NativePositionHistory(self.ledger,account_alias=self.adapter.account_alias,venue=self.adapter.venue)
        source={e.hash:e for e in history.events(EventKind.EXECUTION_RECEIPT)}
        families=[e for e in history.rows if e.kind is EventKind.POSITION_FAMILY
            and e.producer=='vati-position-family' and e.correlation_id==body['family_id']
            and e.hash==canonical_hash(e.body())]
        if not families or families[-1].payload['members'][0]['trade_intent_id']!=body['root_intent_id']:
            raise EconomicObservationError('native economic observation has no original family')
        intents={m['trade_intent_id'] for m in families[-1].payload['members'] if m['role'] in {'ROOT','SCALE_IN'}}
        from vati.lifecycle.family import FamilyRegistry
        from vati.lifecycle.family_membership import original_native_snapshot
        from vati.risk.contracts import Direction
        roots=[e for e in source.values() if e.correlation_id==body['root_intent_id']
            and not e.payload.get('exit_action') and e.payload.get('status') in {'FILLED','PARTIAL'}]
        if len(roots)!=1:
            raise EconomicObservationError('original native economic root is ambiguous')
        restored=FamilyRegistry().restore(history,family_id=body['family_id'],trade_intent_id=body['root_intent_id'],
            symbol=families[-1].payload['symbol'],direction=Direction(families[-1].payload['direction']),
            position_id=roots[0].payload['broker_position_id'])
        snapshot=original_native_snapshot(history,restored,self.adapter)
        if not snapshot.known or any(leg.remaining!=0 for leg in snapshot.legs):
            raise EconomicObservationError('original family native close remains unresolved')
        seen=set();exit_refs=set();captured=[];total=Fraction(0)
        for deal in body['deals']:
            if type(deal) is not dict or set(deal)!=DEAL_KEYS:
                raise EconomicObservationError('native deal schema differs')
            opening=source.get(deal['entry_ref']);closed=source.get(deal['exit_ref'])
            if (not deal['native_deal_id'] or deal['native_deal_id'] in seen or deal['exit_ref'] in exit_refs
                    or not deal['source_revision'] or deal['currency']!=body['currency']
                    or opening is None or closed is None or opening.payload.get('exit_action')
                    or closed.payload.get('exit_action')!='CLOSE'
                    or closed.correlation_id not in intents or opening.correlation_id!=closed.correlation_id
                    or deal['trade_intent_id']!=closed.correlation_id
                    or deal['position_id']!=closed.payload.get('broker_position_id')
                    or opening.payload.get('broker_position_id')!=deal['position_id']
                    or history.commands[closed.correlation_id][0]['symbol']!=deal['symbol']
                    or _amount(deal['quantity'])!=_amount(str(closed.payload['filled_qty']))
                    or _amount(deal['execution_price'])!=_amount(str(closed.payload['average_fill']))
                    or min(closed.received_time_ms,closed.event_time_ms)>body['effective_at_ms']
                    or closed.received_time_ms>body['available_at_ms']):
                raise EconomicObservationError('native deal identity/currency/quantity/original source differs')
            seen.add(deal['native_deal_id']);exit_refs.add(deal['exit_ref'])
            cash=([row for row in self.adapter.closed if row.get('close_id')==deal['native_deal_id']]
                  if original_cash is None else [row for row in original_cash if row.get('close_id')==deal['native_deal_id']])
            if (len(cash)!=1 or cash[0].get('position_id')!=deal['position_id']
                    or cash[0].get('intent')!=deal['trade_intent_id']
                    or _amount(str(cash[0].get('qty')))!=_amount(deal['quantity'])
                    or _amount(str(cash[0].get('exit')))!=_amount(deal['execution_price'])):
                raise EconomicObservationError('native deal does not join its captured OWNER execution')
            captured.append(cash[0]);total+=Fraction(_amount(deal['net_cash_delta']))
        expected={e.hash for e in source.values() if e.correlation_id in intents
            and e.payload.get('exit_action')=='CLOSE' and Decimal(str(e.payload.get('filled_qty','0')))>0}
        if exit_refs!=expected:
            raise EconomicObservationError('native economic observation omits/conflicts original family executions')
        return total,captured

    def record(self,body,signature):
        from vati.core.canonical import canonical_json
        import json
        body=json.loads(canonical_json(body))
        with self.ledger.atomic():
            rows=self._rows(body.get('family_id'))
            duplicate=next((e for e in rows if e.payload['observation']==body),None)
            if duplicate is not None:return duplicate
            total,cash=self._validate(body)
            now=self.clock()
            if body['available_at_ms']!=now:
                raise EconomicObservationError('native economic knowledge time differs from actual reader clock')
            previous=rows[-1] if rows else None
            if (body['sequence']!=(previous.payload['observation']['sequence']+1 if previous else 0)
                    or body['previous_ref']!=(previous.hash if previous else None)):
                raise EconomicObservationError('native economic sequence/predecessor CAS differs')
            verified=self.issuer.verify(signature,act='native-family-economics-source',subject=subject(body),
                now_unix=now//1000,single_use=False)
            if verified.key_id!=body['source_owner_id']:
                raise EconomicObservationError('native economic issuer differs from configured owner')
            proof=archive_verified_control(signature,verified)
            event=make_event(EventKind.SESSION,PRODUCER,dict(schema=SCHEMA,observation=body,
                observation_hash=canonical_hash(body),verified_source_owner=proof,original_owner_cash=cash,
                native_provider_qualified=False,certificate_issued=False,execution_authority=False),
                event_time_ms=body['effective_at_ms'],received_time_ms=now,correlation_id=body['family_id'])
            self.ledger.append(event)
        return event

    def latest(self,family_id):
        rows=self._rows(family_id);previous=None
        for event in rows:
            p=event.payload;body=p['observation'];proof=p['verified_source_owner']
            if (event.hash!=canonical_hash(event.body()) or p['observation_hash']!=canonical_hash(body)
                    or body['previous_ref']!=(previous.hash if previous else None)
                    or body['sequence']!=(previous.payload['observation']['sequence']+1 if previous else 0)
                    or event.event_time_ms!=body['effective_at_ms'] or event.received_time_ms!=body['available_at_ms']):
                raise EconomicObservationError('original native economic source chain differs')
            verifier=OwnerAuthorityVerifier({body['source_owner_id']:proof['public_key_pem']})
            verified=verifier.verify(proof['token'],act='native-family-economics-source',subject=subject(body),
                now_unix=body['available_at_ms']//1000,single_use=False)
            from dataclasses import asdict
            if (proof['public_key_sha256']!=verified._verified_key_binding.public_key_sha256
                    or proof['verified_authority']!=asdict(verified)):
                raise EconomicObservationError('original native economic owner proof differs')
            self._validate(body,original_cash=p['original_owner_cash'])
            previous=event
        return previous
