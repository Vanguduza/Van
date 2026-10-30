"""Native spot values and causal freshness; never a tradability certificate."""
from dataclasses import dataclass
import json
from decimal import Decimal, localcontext

from vati.core.canonical import canonical_hash,canonical_json
from vati.execution.ctrader.feed import native_integer


@dataclass(frozen=True)
class SpotObservation:
    scope_json: str
    contract_revision: str
    state: str
    bid: Decimal | None
    ask: Decimal | None
    bid_time_ms: int | None
    ask_time_ms: int | None
    processed_at_ms: int | None
    evaluated_at_ms: int | None
    age_ms: int | None
    ignored_older_updates: int
    subscription_acknowledged: bool
    control_state: str = 'NOT_REQUESTED'

    @property
    def scope(self):
        return json.loads(self.scope_json)

    @property
    def prices(self):
        if self.state in {'OBSERVED_UNQUALIFIED','OBSERVED_UNQUALIFIED_LATE_UPDATE_IGNORED'}:
            return self.bid,self.ask
        return None

    def body(self):
        with localcontext() as context:
            context.prec=80
            spread=str(self.ask-self.bid) if self.prices is not None else None
        data={'schema':'vati.ctrader-spot/1','scope':dict(self.scope),'contract_revision':self.contract_revision,
              'state':self.state,'bid':str(self.bid) if self.bid is not None else None,
              'ask':str(self.ask) if self.ask is not None else None,'spread':spread,
              'bid_native_time_ms':self.bid_time_ms,'ask_native_time_ms':self.ask_time_ms,
              'processed_at_ms':self.processed_at_ms,'evaluated_at_ms':self.evaluated_at_ms,
              'age_ms':self.age_ms,'ignored_older_updates':self.ignored_older_updates,
              'subscription_state':'ACKNOWLEDGED_QUEUED_NOT_DELIVERY' if self.subscription_acknowledged else 'NOT_ACKNOWLEDGED',
              'control_state':self.control_state,
              'price_basis':'NATIVE_RELATIVE_PRICE_1E5','availability_basis':'NATIVE_SIDE_TIMES_AND_HOST_PROCESSING_NOT_NETWORK_RECEIPT',
              'binding_basis':'CURRENT_PRODUCT_METADATA_AT_PROCESSING_NOT_PROVEN_EFFECTIVE_AT_TICK',
              'sequence_state':'NOT_PROVIDED_BY_NATIVE_SPOT','market_session_state':'UNKNOWN_FIRST_SNAPSHOT_MAY_BE_MARKET_CLOSED',
              'provider_qualified':False,'authority_effect':'NONE'}
        return data|{'observation_sha256':canonical_hash(data)}


class SpotBook:
    def __init__(self):
        self.rows={}

    def forget(self,product):
        self.rows.pop(product,None)

    def _entry(self,contract,connection):
        scope=contract.native_scope;product=scope['native_symbol_id']
        identity=(canonical_hash(scope),contract.revision,connection)
        row=self.rows.get(product)
        if row is None or row['identity']!=identity:
            row={'identity':identity,'bid':None,'ask':None,'bid_time':None,'ask_time':None,
                 'bid_floor':None,'ask_floor':None,'processed':None,'error':None,'ignored':0}
            self.rows[product]=row
        return row

    def observe(self,contract,connection,event,processed_at_ms):
        row=self._entry(contract,connection)
        now=None
        try:
            now=native_integer(processed_at_ms,maximum=253402300799000)
            if not isinstance(event,dict):raise ValueError('INVALID_NATIVE_EVENT')
            if 'payloadType' in event and event['payloadType']!='PROTO_OA_SPOT_EVENT':raise ValueError('INVALID_NATIVE_EVENT')
            scope=contract.native_scope
            if (native_integer(event['ctidTraderAccountId'],minimum=1)!=scope['native_account_id']
                    or native_integer(event['symbolId'],minimum=1)!=scope['native_symbol_id']):
                raise ValueError('NATIVE_SCOPE_MISMATCH')
            values={side:native_integer(event[side],minimum=1,maximum=2**64-1)
                    for side in ('bid','ask') if side in event}
            # Live trendbars/session-close can share this envelope without a
            # price update. They cannot renew either side's native quote time.
            if not values:
                row['processed']=now
                return
            if 'timestamp' not in event:raise ValueError('NATIVE_TIME_UNAVAILABLE')
            at=native_integer(event['timestamp'],maximum=now)
            # One timestamp can legitimately carry multiple side changes in a
            # millisecond. Older sides never overwrite newer recorded values.
            for side,value in values.items():
                floor=row[side+'_floor']
                if floor is not None and at<floor:
                    row['ignored']=min(row['ignored']+1,2**63-1)
                    continue
                with localcontext() as context:
                    context.prec=80
                    row[side]=Decimal(value)/Decimal(100000)
                row[side+'_time']=at;row[side+'_floor']=at
            row['processed']=now;row['error']=None
        except (KeyError,TypeError,ValueError,ArithmeticError) as exc:
            # A malformed update cannot leave an apparently usable previous
            # pair. Keep only time floors for stale/replayed update rejection.
            row['bid']=row['ask']=row['bid_time']=row['ask_time']=None
            row['processed']=now
            message=str(exc)
            row['error']=message if message in {'NATIVE_SCOPE_MISMATCH','NATIVE_TIME_UNAVAILABLE',
                'NATIVE_PRICE_UNAVAILABLE','INVALID_NATIVE_EVENT'} else 'INVALID_NATIVE_EVENT'

    def snapshot(self,contract,connection,*,now_ms,max_age_ms,subscribed=False):
        native_integer(max_age_ms,minimum=1)
        row=self._entry(contract,connection);age=None
        try:
            now=native_integer(now_ms,maximum=253402300799000)
            state=row['error'] or 'WAITING_NATIVE_QUOTE'
            if not subscribed:state='SUBSCRIPTION_NOT_ACKNOWLEDGED'
            elif not row['error']:
                if row['bid'] is None:state='WAITING_NATIVE_BID'
                elif row['ask'] is None:state='WAITING_NATIVE_ASK'
                elif row['bid_time']>now or row['ask_time']>now:state='HOST_CLOCK_BEHIND_NATIVE_QUOTE'
                else:
                    age=now-min(row['bid_time'],row['ask_time'])
                    if age>max_age_ms:state='STALE_NATIVE_QUOTE'
                    elif row['ask']<row['bid']:state='CROSSED_NATIVE_QUOTE'
                    else:state='OBSERVED_UNQUALIFIED_LATE_UPDATE_IGNORED' if row['ignored'] else 'OBSERVED_UNQUALIFIED'
        except (TypeError,ValueError):
            now=None;state='HOST_CLOCK_UNAVAILABLE'
        return SpotObservation(canonical_json(contract.native_scope),contract.revision,state,row['bid'],row['ask'],
            row['bid_time'],row['ask_time'],row['processed'],now,age,row['ignored'],subscribed)
