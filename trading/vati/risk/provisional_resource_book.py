"""Durable projected entry holds in the existing financial ledger.

IN PROGRESS: these holds cannot publish or authorize an order. Complete fees,
active shared policy, legacy-obligation migration and native/economic release
are mandatory before the final reservation owner can admit execution. Expiry
does not release a hold. There is deliberately no automatic release operation.
"""
import hashlib,json,time

from vati.core import EventKind,make_event
from vati.core.canonical import canonical_hash,canonical_json
from vati.core.ledger import GENESIS,committed_source_snapshot,require_committed_source_read
from vati.core.units import Money
from vati.funding.native import native_int
from vati.risk.entry_margin import _body
from vati.risk.entry_resource_projection import project_entry_resources
from vati.risk.mandate_source import capture_mandate_source,validate_mandate_source
from vati.risk.serde import mandate_binding_hash

EVENT='PROVISIONAL_ENTRY_RESOURCE_HOLD'
PRODUCER='vati-financial-resource-owner'
SCHEMA='vati.provisional-entry-resource-hold/1'
V1_MISSING=('FEES','FILL_CONTINGENCIES','NATIVE_CONTRACT_VALUATION','PRICE_AND_ORDER_SEMANTICS',
    'PORTFOLIO_GROUP_RESOURCES','ACTIVE_SHARED_POLICY','QUALIFIED_RUNTIME_COHORT',
    'LEGACY_OBLIGATION_MIGRATION','NATIVE_ECONOMIC_RECONCILIATION')
# This schema's original obligations are immutable. A later admission schema
# must retain its own versioned history rather than edit old receipts.
MISSING=V1_MISSING


class ResourceHoldError(ValueError):pass


class ResourceHoldUnknown(OSError):
    def __init__(self,key):
        self.key=key
        super().__init__('RESOURCE_HOLD_STORAGE_OUTCOME_UNKNOWN_READ_ORIGINAL')


def _key(physical,scope,alias,idempotency):
    return canonical_hash([physical,scope,alias,idempotency])


class ProvisionalResourceBook:
    def __init__(self,ledger,*,clock=None,max_records=4096,max_bytes=16*1024**2):
        if type(max_records)is not int or not 1<=max_records<=100000:raise ResourceHoldError('RESOURCE_RECORD_CAPACITY_INVALID')
        if type(max_bytes)is not int or not 1<=max_bytes<=256*1024**2:raise ResourceHoldError('RESOURCE_BYTE_CAPACITY_INVALID')
        self.ledger=ledger;self.clock=clock or (lambda:int(time.time()*1000))
        self.max_records,self.max_bytes=max_records,max_bytes

    def _now(self):return native_int(self.clock(),minimum=0)

    @staticmethod
    def _receipt(event):
        p=event.payload
        return {'record_ref':event.hash,'key':event.correlation_id,'command_hash':p['command']['command_hash'],
            'state':'PROVISIONAL_RESOURCE_HOLD','available_at_ms':event.received_time_ms,
            'burdens':p['projection']['burdens'],'quote_valid_until_ms':p['projection']['quote_valid_until_ms'],
            'missing_requirements':list(p['missing_requirements']),'execution_authority':False,
            'reservation_qualified':False,'eligible_for_native_dispatch':False}

    @staticmethod
    def _check_capacity(projection,prior):
        selected=[p for p in prior if p['physical_account_key']==projection['physical_account_key']]
        if any(p['monetary_scope_hash']!=projection['monetary_scope_hash'] for p in selected):
            raise ResourceHoldError('RESOURCE_CURRENCY_SCOPE_MIGRATION_UNRESOLVED')
        policies=[projection,*selected]
        names=dict.fromkeys(name for p in policies for name in p['burdens'])
        for name in names:
            required_body=next(p['burdens'][name] for p in policies if name in p['burdens'])
            required=Money.from_body(required_body)
            capacities=[Money.from_body(p['capacities'][name] if name in p['capacities']
                else p['unobserved_currency_leg_capacity']) for p in policies]
            holds=[Money.from_body(p['burdens'][name]) for p in policies if name in p['burdens']]
            if any((v.currency,v.asset_ref)!=(required.currency,required.asset_ref) for v in [*capacities,*holds]):
                raise ResourceHoldError('RESOURCE_MONETARY_IDENTITY_INVALID')
            capacity=min(v.fraction for v in capacities)
            held=sum((v.fraction for v in holds),0)
            if held>capacity:raise ResourceHoldError('RESOURCE_CAPACITY_EXCEEDED:'+name)
        slots=dict.fromkeys(name for p in policies for name in p['slot_burdens'])
        for name in slots:
            capacities=[p['slot_capacities'][name] if name in p['slot_capacities']
                else p['unobserved_instrument_slot_capacity'] for p in policies]
            holds=[p['slot_burdens'].get(name,0) for p in policies]
            if any(type(v)is not int or v<0 for v in [*capacities,*holds]):
                raise ResourceHoldError('RESOURCE_SLOT_IDENTITY_INVALID')
            if sum(holds)>min(capacities):raise ResourceHoldError('RESOURCE_SLOT_CAPACITY_EXCEEDED:'+name)

    def _history(self):
        if self.ledger.count()>100000 or not self.ledger.verify_chain()[0]:
            raise ResourceHoldError('RESOURCE_SOURCE_HISTORY_UNAVAILABLE')
        found={};size=0;last=-1;previous=GENESIS
        for event in self.ledger.iter():
            p=event.payload
            if event.kind is EventKind.SESSION and isinstance(p,dict) and p.get('event')==EVENT:
                size+=len(canonical_json(event.body()).encode())
                if len(found)>=self.max_records or size>self.max_bytes:raise ResourceHoldError('RESOURCE_HISTORY_CAPACITY')
                if (set(p)!={'event','schema','command','projection','mandate_source','missing_requirements'} or p['schema']!=SCHEMA
                        or event.producer!=PRODUCER or type(event.schema_version)is not int or event.schema_version!=1
                        or event.decision_time_ms is not None or event.hash!=canonical_hash(event.body())):
                    raise ResourceHoldError('RESOURCE_RECORD_INVALID')
                if type(p['missing_requirements'])is not list or p['missing_requirements']!=list(V1_MISSING):
                    raise ResourceHoldError('RESOURCE_ORIGINAL_REQUIREMENTS_INVALID')
                from vati.risk.entry_margin import _decode
                command=_decode(p['command']);projection=p['projection']
                native_int(event.received_time_ms,minimum=max(0,last),maximum=projection['quote_valid_until_ms']-1)
                if type(event.event_time_ms)is not int or event.event_time_ms!=event.received_time_ms:
                    raise ResourceHoldError('RESOURCE_ORIGINAL_STORAGE_CLOCK_INVALID')
                validate_mandate_source(p['mandate_source'],decision_time_ms=event.received_time_ms,
                    expected_hash=projection['policy_hash'])
                verified=project_entry_resources(self.ledger,command,projection['entry_margin_ref'],
                    projection['current_risk_ref'],p['mandate_source'],at_ms=event.received_time_ms).body()
                verified['source_head']=previous
                if verified!=projection:raise ResourceHoldError('RESOURCE_ORIGINAL_PROJECTION_INVALID')
                key=_key(projection['physical_account_key'],projection['monetary_scope_hash'],
                    command.account_alias,command.idempotency_key)
                if key!=event.correlation_id or key in found:raise ResourceHoldError('RESOURCE_ORIGINAL_IDENTITY_INVALID')
                self._check_capacity(projection,[e.payload['projection'] for e in found.values()])
                found[key]=event;last=event.received_time_ms
            previous=hashlib.sha256((previous+event.hash).encode()).hexdigest()
        return found,size,last

    def lookup(self,physical,scope,alias,idempotency):
        with committed_source_snapshot(self.ledger):
            event=self._history()[0].get(_key(physical,scope,alias,idempotency))
            return None if event is None else self._receipt(event)

    def reserve_entry(self,command,entry_margin_ref,current_risk_ref,authority):
        require_committed_source_read(self.ledger)
        if getattr(self.ledger,'_read_snapshot_depth',0):raise ResourceHoldError('RESOURCE_HOLD_REQUIRES_OWN_WRITER')
        command_body=_body(command);now=self._now()
        from vati.risk.current_entry_source import current_entry_source
        with committed_source_snapshot(self.ledger):
            source=current_entry_source(self.ledger,command,entry_margin_ref,current_risk_ref,available_at_ms=now).body()
            key=_key(source['physical_account_key'],source['monetary_scope_hash'],command.account_alias,command.idempotency_key)
            rows,size,last=self._history();known=rows.get(key)
            if known is not None:
                if known.payload['command']!=command_body:raise ResourceHoldError('RESOURCE_ORIGINAL_REQUEST_CONFLICT')
                return self._receipt(known)
            from vati.risk.authority import RiskAuthority
            if type(authority)is not RiskAuthority:raise ResourceHoldError('RESOURCE_CURRENT_AUTHORITY_REQUIRED')
            m=authority.mandate
            if (not m.authority_matches_policy() or not m.sends_orders()
                    or mandate_binding_hash(m)!=source['decision']['mandate_hash']):
                raise ResourceHoldError('RESOURCE_CURRENT_AUTHORITY_REQUIRED')
            original=next(e for e in self.ledger.iter(EventKind.RISK_DECISION) if e.hash==source['original_risk_ref'])
            proof=capture_mandate_source(m,original.payload['inputs']['mandate'],now_ms=now)
            if proof.get('state')!='ORIGINAL_BOUND':raise ResourceHoldError('RESOURCE_OWNER_AUTHORITY_UNAVAILABLE')
            projection=project_entry_resources(self.ledger,command,entry_margin_ref,current_risk_ref,proof,at_ms=now).body()
            if projection['quote_time_state']!='WITHIN_ORIGINAL_WINDOW':raise ResourceHoldError('RESOURCE_QUOTE_EXPIRED')
            self._check_capacity(projection,[e.payload['projection'] for e in rows.values()])
            head=self.ledger.head()
            if head!=projection['source_head']:raise ResourceHoldError('RESOURCE_SOURCE_CHANGED')
        started=False;changed=False
        try:
            with m.owner_authority_submission_guard() as current:
                if not current:raise ResourceHoldError('RESOURCE_OWNER_AUTHORITY_UNAVAILABLE')
                with self.ledger.atomic():
                    if self.ledger.head()!=head:changed=True
                    else:
                        at=self._now()
                        if at<max(last,now) or at>=projection['quote_valid_until_ms'] or m.is_expired(at//1000):
                            raise ResourceHoldError('RESOURCE_EXPIRED_OR_CLOCK_REGRESSED')
                        # Waiting for the writer cannot extend a standing token.
                        # Reuse the existing real verifier under its key guard;
                        # retain that original proof for historical readback.
                        proof=capture_mandate_source(m,original.payload['inputs']['mandate'],now_ms=at)
                        if proof.get('state')!='ORIGINAL_BOUND':
                            raise ResourceHoldError('RESOURCE_OWNER_AUTHORITY_UNAVAILABLE')
                        checked=self._now()
                        if (checked<at or checked>=projection['quote_valid_until_ms']
                                or m.is_expired(checked//1000) or not m.authority_matches_policy()
                                or any(checked//1000>=p['verified_authority']['expires_at_unix'] for p in proof['authorities'])):
                            raise ResourceHoldError('RESOURCE_EXPIRED_OR_CLOCK_REGRESSED')
                        at=checked
                        if len(rows)>=self.max_records or self.ledger.count()>=100000:raise ResourceHoldError('RESOURCE_HISTORY_CAPACITY')
                        event=make_event(EventKind.SESSION,PRODUCER,{'event':EVENT,'schema':SCHEMA,
                            'command':command_body,'projection':projection,'mandate_source':proof,
                            'missing_requirements':list(V1_MISSING)},
                            event_time_ms=at,received_time_ms=at,correlation_id=key)
                        if size+len(canonical_json(event.body()).encode())>self.max_bytes:raise ResourceHoldError('RESOURCE_BYTE_CAPACITY')
                        started=True;self.ledger.append(event)
            known=self.lookup(source['physical_account_key'],source['monetary_scope_hash'],command.account_alias,command.idempotency_key)
            if changed:
                if known is not None and known['command_hash']==command.command_hash:return known
                raise ResourceHoldError('RESOURCE_SOURCE_CHANGED_RETRY_ORIGINAL')
            if known is None or known['record_ref']!=event.hash:raise ResourceHoldUnknown(key)
            return known
        except ResourceHoldUnknown:raise
        except Exception:
            if started:raise ResourceHoldUnknown(key) from None
            raise
