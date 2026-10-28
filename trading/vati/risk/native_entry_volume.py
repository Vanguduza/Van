"""Original native deal volume for an original dispatched entry.

Gross entry execution is not net holdings, settled money or a refreshed entry
allowance. Fees, closes and later account marks cannot undo an observed entry.
The complete parent/child budget and reservation owner remain separate.
"""
from dataclasses import dataclass
from fractions import Fraction
import json,re

from vati.core import EventKind
from vati.core.canonical import canonical_hash,canonical_json
from vati.core.ledger import committed_source_snapshot
from vati.execution.ctrader.contracts import NativeSymbolContract
from vati.funding.deal_journal import DealBook
from vati.funding.native import native_int
from vati.risk.account_context import NativeAccountRiskContext
from vati.risk.physical_orders import physical_order_exposure

NATIVE_ID=re.compile('[1-9][0-9]{0,18}',re.ASCII)


class NativeEntryVolumeError(ValueError):pass


def _native_order_id(value):
    if type(value)is not str or NATIVE_ID.fullmatch(value)is None:
        raise NativeEntryVolumeError('ORIGINAL_NATIVE_ORDER_ID_UNAVAILABLE')
    return native_int(int(value),minimum=1)


@dataclass(frozen=True,init=False)
class OriginalNativeEntryVolume:
    _body_json:bytes

    def body(self):return json.loads(self._body_json)


def read_original_entry_volume(book,command_hash,source_ref,*,available_at_ms,max_events=100000,max_bytes=32*1024**2):
    """Join the existing command, original receipts and deduplicated deal owner."""
    try:
        native_int(available_at_ms,minimum=0)
        native_int(max_events,minimum=1,maximum=1000000);native_int(max_bytes,minimum=1,maximum=256*1024**2)
        with committed_source_snapshot(book.ledger):
            if book.ledger.count()>max_events:raise NativeEntryVolumeError('NATIVE_ENTRY_HISTORY_CAPACITY')
            original=book.lookup_entry(command_hash,source_ref)
            if original is None:raise NativeEntryVolumeError('ORIGINAL_ENTRY_MARGIN_UNAVAILABLE')
            q=original['observation'];binding=original['receipt']
            native_int(binding['available_at_ms'],minimum=0,maximum=available_at_ms)
            if q['schema']!='vati.ctrader-expected-margin/1':
                raise NativeEntryVolumeError('PROVIDER_ENTRY_DEAL_VOLUME_UNAVAILABLE')
            context=NativeAccountRiskContext(**q['native_account_context'])
            exposure=physical_order_exposure(book.ledger,context,available_at_ms=available_at_ms)
            if exposure.unresolved_refs:raise NativeEntryVolumeError('NATIVE_ENTRY_ORIGINAL_OWNERSHIP_UNRESOLVED')
            selected=[o for o in exposure.orders if o.command['command_hash']==command_hash]
            if len(selected)!=1:raise NativeEntryVolumeError('ORIGINAL_DISPATCHED_ENTRY_UNAVAILABLE_OR_AMBIGUOUS')
            order=selected[0]
            dispatched=order.command
            if (any(dispatched.get(k)!=v for k,v in original['command'].items())
                    or dispatched.get('native_entry_margin_ref')!=binding['record_ref']
                    or order.original_input_ref!=binding['original_input_ref']):
                raise NativeEntryVolumeError('ORIGINAL_ENTRY_COMMAND_BINDING_DIFFERS')
            events={};size=0
            for event in book.ledger.iter():
                size+=len(canonical_json(event.body()).encode())
                if size>max_bytes:raise NativeEntryVolumeError('NATIVE_ENTRY_HISTORY_BYTE_CAPACITY')
                if max(event.event_time_ms,event.received_time_ms)<=available_at_ms:events[event.hash]=event
            owners={};receipt_refs=[]
            for candidate in exposure.orders:
                for ref in candidate.receipt_refs:
                    event=events[ref];p=event.payload
                    if p.get('exit_action') is not None:continue
                    raw=p.get('broker_order_id')
                    if raw in ('',None):continue
                    # A provider-owned identifier must not be interpreted from
                    # a comment, alias, position ID or another parent's symbol.
                    native=_native_order_id(raw)
                    owners.setdefault(native,set()).add(candidate.command_ref)
                    if candidate.command_ref==order.command_ref:receipt_refs.append(ref)
            native_ids={n for n,refs in owners.items() if order.command_ref in refs}
            if not native_ids:raise NativeEntryVolumeError('ORIGINAL_NATIVE_ORDER_ID_UNAVAILABLE')
            if any(owners[n]!={order.command_ref} for n in native_ids):
                raise NativeEntryVolumeError('NATIVE_ORDER_CLAIMED_BY_MULTIPLE_COMMANDS')
            scope={k:q[k] for k in ('native_account_id','deposit_asset_id','currency')}
            native_contract=NativeSymbolContract.from_body(q['native_contract'])
            scope.update(provider='CTRADER',environment=native_contract.native_scope['environment'])
            scope_hash=canonical_hash(scope)
            deal_owner=DealBook(book.ledger)
            publications=list(book.ledger.iter(deal_owner.kind,correlation_id=deal_owner.correlation_prefix+scope_hash))
            known=[e for e in publications if e.hash in events]
            anchor=known[-1].hash if known else None
            if anchor is not None:
                for event in publications:
                    if event.hash not in events:
                        raise NativeEntryVolumeError('NATIVE_DEAL_AVAILABILITY_PREFIX_CLOCK_CONFLICT')
                    if event.hash==anchor:break
                # The existing owner takes an original publication hash, not
                # a timestamp. Never replace that durable availability anchor.
                observations=deal_owner.observations(scope_hash,as_of=anchor)
            else:observations={'state':'NO_DATA','deals':[]}
            if observations['state']=='CONFLICT':raise NativeEntryVolumeError('NATIVE_ENTRY_DEAL_HISTORY_CONFLICT')
            facts=[];total=0
            for captured in observations['deals']:
                row=captured['deal']
                if row['order_id'] not in native_ids:continue
                if row['symbol_id']!=q['native_symbol_id']:
                    raise NativeEntryVolumeError('NATIVE_ENTRY_ORDER_SYMBOL_CONFLICT')
                count=native_int(row['filled_volume_cents'],minimum=0)
                total+=count
                facts.append({'native_deal_id':row['native_id'],'native_order_id':row['order_id'],
                    'filled_volume_cents':count,'original_statement_ref':captured['original_statement_ref'],
                    'original_row_digest':canonical_hash(row),'available_at_ms':captured['received_at_ms'],
                    'raw_commission':row['commission'],'raw_money_digits':row['money_digits'],
                    'raw_close_detail':row['close']})
            facts.sort(key=lambda row:row['native_deal_id'])
            bound=q['native_volume'];lot_size=q['native_contract']['metadata']['detail']['lotSize']
            lots=Fraction(total,lot_size)
            if total>bound:state='NATIVE_GROSS_VOLUME_EXCEEDS_ORIGINAL_COMMAND'
            elif total and order.state=='NO_EFFECT':state='NATIVE_DEALS_CONTRADICT_NO_EFFECT_RECEIPT'
            elif facts:state='ORIGINAL_GROSS_ENTRY_VOLUME_OBSERVED'
            else:state='NO_MATCHING_OBSERVED_DEALS_NOT_ZERO_OUTSTANDING'
            body={'schema':'vati.original-native-entry-volume/1','state':state,
                'command_hash':command_hash,'command_ref':order.command_ref,'entry_record_ref':binding['record_ref'],
                'original_input_ref':binding['original_input_ref'],'native_margin_source_ref':source_ref,
                'physical_account_key':context.physical_account_key,'monetary_scope_hash':context.monetary_scope_hash,
                'native_scope':scope,'native_symbol_id':q['native_symbol_id'],
                'native_contract_revision':q['native_contract_revision'],'original_command_volume_cents':bound,
                'observed_gross_filled_volume_cents':total,'observed_lot_equivalent':{
                    'numerator':str(lots.numerator),'denominator':str(lots.denominator)},
                'original_receipt_refs':sorted(set(receipt_refs)),'native_order_ids':sorted(native_ids),
                'deal_facts':facts,'knowledge_through_ms':available_at_ms,
                'deal_statement_knowledge_anchor':anchor,
                'native_deal_observation_state':observations['state'],
                'quantity_basis':'GROSS_NATIVE_EXECUTION_CENTS_NOT_FEE_NET_HOLDINGS',
                'remaining_entry_allowance':None,'fee_or_exit_budget_credit':False,
                'parent_lifetime_budget_complete':False,'reservation_qualified':False,
                'execution_authority':False,'settlement_qualified':False}
            value=object.__new__(OriginalNativeEntryVolume)
            object.__setattr__(value,'_body_json',canonical_json(body).encode());return value
    except NativeEntryVolumeError:raise
    except (KeyError,TypeError,ValueError,ArithmeticError) as error:
        raise NativeEntryVolumeError('ORIGINAL_NATIVE_ENTRY_VOLUME_UNAVAILABLE:'+type(error).__name__) from None
