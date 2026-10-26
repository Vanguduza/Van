"""Bounded original native depth changes, never a complete or tradable book.

The pinned protocol has no sequence, native timestamp or snapshot boundary.
Keep its unsigned prices verbatim: the depth message does not define a scale.
Spot-price documentation cannot silently supply a depth-price qualification.
"""
from dataclasses import dataclass
from decimal import Decimal
import json

from vati.core.canonical import canonical_hash, canonical_json
from vati.execution.ctrader.contracts import NativeSymbolContract
from vati.execution.ctrader.feed import native_integer

MAX_TIME=253402300799000
UINT64=2**64-1


@dataclass(frozen=True)
class DepthObservation:
    body_json: str

    def body(self):
        return json.loads(self.body_json)

    @property
    def state(self):
        return self.body()['state']


class DepthBook:
    def __init__(self, *, max_quotes=4096):
        self.max_quotes=native_integer(max_quotes,minimum=1,maximum=16384)
        self.rows={}

    def forget(self,product):
        self.rows.pop(product,None)

    def _entry(self,contract,connection):
        if not isinstance(contract,NativeSymbolContract):
            raise ValueError('NATIVE_DEPTH_CONTRACT_REQUIRED')
        native_integer(connection,minimum=1)
        scope=contract.native_scope;product=scope['native_symbol_id']
        identity=(canonical_hash(scope),contract.revision,connection)
        row=self.rows.get(product)
        if row is None or row['identity']!=identity:
            if row is None and len(self.rows)>=64:raise ValueError('NATIVE_DEPTH_PRODUCT_CAPACITY')
            row={'identity':identity,'quotes':{},'processed':None,'changed':None,
                 'error':None,'observed':False,'events':0}
            self.rows[product]=row
        return row

    def observe(self,contract,connection,event,processed_at_ms):
        row=self._entry(contract,connection)
        if row['error'] is not None:return  # Only a fresh native context recovers lost continuity.
        reason='INVALID_NATIVE_DEPTH_EVENT'
        try:
            now=native_integer(processed_at_ms,minimum=contract.received_at_ms,maximum=MAX_TIME)
            if row['processed'] is not None and now<row['processed']:
                reason='NATIVE_DEPTH_PROCESSING_CLOCK_REGRESSED';raise ValueError()
            if not isinstance(event,dict):raise ValueError()
            if event.get('payloadType','PROTO_OA_DEPTH_EVENT')!='PROTO_OA_DEPTH_EVENT':raise ValueError()
            scope=contract.native_scope
            if (native_integer(event['ctidTraderAccountId'],minimum=1)!=scope['native_account_id']
                    or native_integer(event['symbolId'],minimum=1,maximum=UINT64)!=scope['native_symbol_id']):
                reason='NATIVE_DEPTH_SCOPE_MISMATCH';raise ValueError()
            additions=event.get('newQuotes',[]);deletions=event.get('deletedQuotes',[])
            if not isinstance(additions,list) or not isinstance(deletions,list):raise ValueError()
            if len(additions)+len(deletions)>self.max_quotes:
                reason='NATIVE_DEPTH_EVENT_CAPACITY';raise ValueError()
            new={};deleted=set()
            for quote in additions:
                if not isinstance(quote,dict) or set(quote) not in ({'id','size','bid'},{'id','size','ask'}):raise ValueError()
                identity=native_integer(quote['id'],maximum=UINT64)
                size=native_integer(quote['size'],maximum=UINT64)
                side='bid' if 'bid' in quote else 'ask'
                price=native_integer(quote[side],minimum=1,maximum=UINT64)
                if identity in new:
                    reason='NATIVE_DEPTH_DUPLICATE_QUOTE_ID';raise ValueError()
                new[identity]=(side,price,size)
            for identity in deletions:
                identity=native_integer(identity,maximum=UINT64)
                if identity in deleted or identity in new:
                    reason='NATIVE_DEPTH_AMBIGUOUS_CHANGE_ORDER';raise ValueError()
                if identity not in row['quotes']:
                    reason='NATIVE_DEPTH_UNSEEN_DELETION';raise ValueError()
                deleted.add(identity)
            next_quotes={k:v for k,v in row['quotes'].items() if k not in deleted}
            next_quotes.update(new)
            if len(next_quotes)>self.max_quotes:
                reason='NATIVE_DEPTH_BOOK_CAPACITY';raise ValueError()
            row['quotes']=next_quotes;row['processed']=now;row['events']=min(row['events']+1,2**63-1)
            if new or deleted:row['changed']=now;row['observed']=True
        except (KeyError,TypeError,ValueError,ArithmeticError):
            row['quotes']={};row['error']=reason;row['observed']=False

    def snapshot(self,contract,connection,*,now_ms,max_age_ms,subscribed=False,limit=100,
                 control_state='NOT_REQUESTED',backlog=False):
        native_integer(max_age_ms,minimum=1)
        native_integer(limit,minimum=1,maximum=self.max_quotes)
        if type(subscribed) is not bool:raise ValueError('NATIVE_DEPTH_SUBSCRIPTION_STATE_INVALID')
        if type(backlog) is not bool:raise ValueError('NATIVE_DEPTH_BACKLOG_STATE_INVALID')
        row=self._entry(contract,connection);age=None;evaluated=None
        state='RECOVERY_REQUIRED' if row['error'] else 'WAITING_NATIVE_DEPTH'
        try:
            evaluated=native_integer(now_ms,minimum=contract.received_at_ms,maximum=MAX_TIME)
            if row['processed'] is not None and evaluated<row['processed']:raise ValueError()
            if row['changed'] is not None:age=evaluated-row['changed']
            if not subscribed:state='SUBSCRIPTION_NOT_ACKNOWLEDGED'
            elif row['error']:state='RECOVERY_REQUIRED'
            elif row['observed']:
                state='STALE_NATIVE_DEPTH_PROCESSING_AGE' if age>max_age_ms else 'OBSERVED_PARTIAL_NATIVE_DEPTH'
        except (TypeError,ValueError):state='NATIVE_DEPTH_EVALUATION_CLOCK_INVALID'
        if backlog and subscribed and row['error'] is None:state='NATIVE_DEPTH_BACKLOG_UNPROCESSED'
        def quote(identity,value):
            side,price,size=value
            return {'native_quote_id':str(identity),'side':side.upper(),'native_price':str(price),
                    'native_size_cents':str(size),'native_size':str(Decimal((0,tuple(map(int,str(size))),-2)))}
        # Never present cached levels as usable after a stop, error or expiry.
        visible=state=='OBSERVED_PARTIAL_NATIVE_DEPTH'
        bids=sorted(((k,v) for k,v in row['quotes'].items() if v[0]=='bid'),key=lambda x:(-x[1][1],x[0]))
        asks=sorted(((k,v) for k,v in row['quotes'].items() if v[0]=='ask'),key=lambda x:(x[1][1],x[0]))
        body={'schema':'vati.ctrader-depth/1','scope':contract.native_scope,'contract_revision':contract.revision,
              'state':state,'recovery_reason':row['error'],'control_state':control_state,
              'subscription_state':'ACKNOWLEDGED_QUEUED_NOT_DELIVERY' if subscribed else 'NOT_ACKNOWLEDGED',
              'bids':[quote(k,v) for k,v in bids[:limit]] if visible else [],
              'asks':[quote(k,v) for k,v in asks[:limit]] if visible else [],
              'observed_quote_count':len(row['quotes']),'observed_bid_count':len(bids),'observed_ask_count':len(asks),
              'display_limit_per_side':limit,'display_truncated':len(bids)>limit or len(asks)>limit,
              'observed_changes':row['observed'],'native_change_events_processed':row['events'],
              'processed_at_ms':row['processed'],'last_change_processed_at_ms':row['changed'],
              'evaluated_at_ms':evaluated,'processing_age_ms':age,
              'side_state':'TWO_SIDED' if bids and asks else 'BID_ONLY' if bids else 'ASK_ONLY' if asks else 'NO_OBSERVED_QUOTES',
              'crossed_observed_levels':bool(bids and asks and bids[0][1][1]>asks[0][1][1]),
              'native_timestamp_ms':None,'native_sequence':None,'complete_book':False,'empty_book_proven':False,
              'sequence_state':'NOT_PROVIDED_BY_NATIVE_DEPTH','snapshot_boundary':'NOT_PROVIDED_BY_NATIVE_DEPTH',
              'availability_basis':'LOCAL_PROCESSING_CLOCK_NOT_NATIVE_TIME_OR_NETWORK_RECEIPT',
              'price_basis':'NATIVE_UINT64_DEPTH_PRICE_SCALE_NOT_QUALIFIED','price_scale':None,
              'normalized_prices_available':False,'size_basis':'NATIVE_QUOTE_CENTS_NOT_LOTS_OR_NOTIONAL',
              'provider_qualified':False,'tradability_qualified':False,'authority_effect':'NONE'}
        body['observation_sha256']=canonical_hash(body)
        return DepthObservation(canonical_json(body))
