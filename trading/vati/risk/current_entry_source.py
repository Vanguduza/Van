"""Original entry, margin and current-risk evidence for the financial owner.

This reader does not reserve capital or turn a historical risk decision into
current authority. The reservation writer must recheck freshness, source head,
current policy, owner controls and its aggregate obligations under its lock.
"""
from dataclasses import dataclass
from decimal import Decimal
import json

from vati.core import EventKind
from vati.core.canonical import canonical_hash,canonical_json
from vati.core.ledger import committed_source_snapshot,require_committed_source_read
from vati.execution.risk_refresh import reported_current_risk
from vati.funding.native import native_int
from vati.risk.account_context import validate_snapshot_context,inspect_context
from vati.risk.entry_margin import _body,_ref,EVENT
from vati.risk.native_history import _original_mt5_query
from vati.risk.native_margin_book import NativeMarginBook
from vati.risk.serde import snapshot_from_dict


class CurrentEntrySourceError(ValueError):
    pass


@dataclass(frozen=True,init=False)
class CurrentEntrySource:
    _body_json:bytes

    def body(self):return json.loads(self._body_json)


def current_entry_source(ledger,command,entry_margin_ref,current_risk_ref,*,available_at_ms):
    """Join actual committed sources, without native I/O or financial writes."""
    require_committed_source_read(ledger)
    try:
        native_int(available_at_ms,minimum=0)
        command_body=_body(command);_ref(entry_margin_ref);_ref(current_risk_ref)
        with committed_source_snapshot(ledger):
            if ledger.count()>100000:raise ValueError('source capacity')
            bindings=[e for e in ledger.iter(EventKind.SESSION) if e.hash==entry_margin_ref]
            if len(bindings)!=1:raise ValueError('original binding unavailable')
            bound=bindings[0]
            if bound.payload['event']!=EVENT:raise ValueError('original binding type')
            read=NativeMarginBook(ledger).lookup_entry(command.command_hash,bound.payload['source_ref'])
            if (read is None or read['receipt']['record_ref']!=entry_margin_ref
                    or canonical_json(read['command'])!=canonical_json(command_body)):
                raise ValueError('original binding differs from command')
            originals=[e for e in ledger.iter(EventKind.RISK_DECISION)
                if e.hash==read['receipt']['original_input_ref']]
            currents=[e for e in ledger.iter(EventKind.RISK_REVALIDATION) if e.hash==current_risk_ref]
            if len(originals)!=1 or len(currents)!=1:raise ValueError('original risk records unavailable')
            original,current=originals[0],currents[0];p=current.payload
            expected={'schema','account_alias','original_decision_hash','original_command_hash',
                'observed_at_ms','original_command_quantity','state','reason_code','reason_detail',
                'snapshot','decision','execution_authority'}
            if (type(p) is not dict or set(p)!=expected or current.schema_version!=1
                    or type(current.schema_version) is not int or current.hash!=canonical_hash(current.body())):
                raise ValueError('current risk record shape')
            report=reported_current_risk(current,original)
            if (report['state'] not in ('SUFFICIENT','REFUSED')
                    or report['original_command_hash']!=command.command_hash
                    or Decimal(report['original_command_quantity'])!=command.quantity):
                raise ValueError('current risk is not bound to this exact command')
            native_int(current.decision_time_ms,minimum=original.received_time_ms)
            native_int(p['observed_at_ms'],minimum=current.decision_time_ms)
            native_int(current.event_time_ms,minimum=max(p['observed_at_ms'],read['receipt']['available_at_ms']))
            native_int(current.received_time_ms,minimum=current.event_time_ms,maximum=available_at_ms)
            facts=snapshot_from_dict(p['snapshot']);validate_snapshot_context(facts)
            context=facts.native_account_context
            margin_context=read['observation']['native_account_context']
            if (context is None or context.account_alias!=command.account_alias
                    or context.provider!=margin_context['provider']
                    or context.physical_account_key!=margin_context['physical_account_key']
                    or context.monetary_scope_hash!=margin_context['monetary_scope_hash']):
                raise ValueError('current native monetary scope differs from original margin')
            if inspect_context(context)['observed_at_ms']>p['observed_at_ms']:
                raise ValueError('current native context was not yet available')
            if context.provider=='MT5':
                query=_original_mt5_query(ledger,context,queries={})
                if max(query.event_time_ms,query.received_time_ms)>p['observed_at_ms']:
                    raise ValueError('current native query not originally available')
            quote=read['observation'];until=quote['valid_until_ms']
            if command.expires_at_ms is not None:until=min(until,command.expires_at_ms)
            body={'schema':'vati.current-entry-risk-source/1','command_hash':command.command_hash,
                'original_risk_ref':original.hash,'entry_margin_ref':entry_margin_ref,
                'current_risk_ref':current_risk_ref,'source_head':ledger.head(),
                'physical_account_key':context.physical_account_key,
                'monetary_scope_hash':context.monetary_scope_hash,
                'risk_state':report['state'],'risk_reason_code':report['reason_code'],
                'risk_observed_at_ms':p['observed_at_ms'],'available_at_ms':current.received_time_ms,
                'quote_valid_until_ms':until,
                'quote_time_state':'EXPIRED' if available_at_ms>=until else 'WITHIN_ORIGINAL_WINDOW',
                'snapshot':p['snapshot'],'decision':p['decision'],
                'estimate_money':read['estimate_money'],'price_binding':read['price_binding'],
                'execution_authority':False,'reservation_qualified':False}
            body['source_ref']=canonical_hash(body)
            result=object.__new__(CurrentEntrySource)
            object.__setattr__(result,'_body_json',canonical_json(body).encode())
            return result
    except Exception as error:
        raise CurrentEntrySourceError('ENTRY_CURRENT_RISK_SOURCE_UNAVAILABLE:'+type(error).__name__) from None
