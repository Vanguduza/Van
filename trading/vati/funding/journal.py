"""Original native cash observations in the existing append-only financial journal.

Observation is not settlement approval, spendable capital or a qualified return.
Conflicting provider history is retained and quarantined, never silently restated.
"""
from decimal import Decimal,localcontext
import time
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind,make_event
from vati.core.ledger import LedgerError,history_through
from vati.funding.native import NativeCashStatement,native_int,native_money

PRODUCER='vati-native-funding'
SCHEMA='native-funding-observation/1'

class FundingBook:
    def __init__(self,ledger,*,clock=None):
        self.ledger=ledger;self.clock=clock or (lambda:int(time.time()*1000))

    @staticmethod
    def _key(statement):
        return canonical_hash({'scope_hash':statement.scope_hash,'from_ms':statement.from_ms,'to_ms':statement.to_ms,
            'movements':sorted((row.body() for row in statement.movements),key=lambda row:row['native_id'])})

    @staticmethod
    def _validate(statement):
        if not isinstance(statement,NativeCashStatement) or statement.provider!='CTRADER' or statement.environment not in {'DEMO','LIVE'}:
            raise ValueError('funding_native_scope_invalid')
        native_int(statement.native_account_id,minimum=1);native_int(statement.deposit_asset_id,minimum=1)
        if not isinstance(statement.currency,str) or not statement.currency.strip():raise ValueError('funding_native_currency_invalid')
        for value in (statement.from_ms,statement.to_ms,statement.observed_at_ms):native_int(value,minimum=0)
        if not statement.from_ms<=statement.to_ms<=statement.observed_at_ms:raise ValueError('funding_native_window_invalid')
        seen=set()
        for row in statement.movements:
            native_int(row.native_id,minimum=1);native_int(row.money_digits,minimum=0,maximum=18)
            native_int(row.occurred_at_ms,minimum=statement.from_ms,maximum=statement.to_ms)
            if row.native_id in seen:raise ValueError('funding_native_identity_duplicated')
            if not isinstance(row.operation,str) or not row.operation:raise ValueError('funding_native_operation_invalid')
            for value in (row.delta,row.balance_after):
                if not isinstance(value,Decimal) or not value.is_finite():raise ValueError('funding_native_money_invalid')
            for value in (row.delta,row.balance_after,row.equity_after):
                if value is None:continue
                if not isinstance(value,Decimal) or not value.is_finite():raise ValueError('funding_native_money_invalid')
                if not native_money(-(2**63),row.money_digits)<=value<=native_money(2**63-1,row.money_digits):raise ValueError('funding_native_money_invalid')
                with localcontext() as context:
                    context.prec=80
                    if value.quantize(native_money(1,row.money_digits))!=value:raise ValueError('funding_native_precision_invalid')
            if row.balance_version is not None:native_int(row.balance_version,minimum=0)
            seen.add(row.native_id)

    def _events(self,scope_hash,as_of=None):
        correlation='funding:'+scope_hash
        rows=history_through(self.ledger,correlation,as_of) if as_of else list(self.ledger.iter(EventKind.FUNDING_STATEMENT,correlation_id=correlation))
        output=[]
        for event in rows:
            if (event.kind is not EventKind.FUNDING_STATEMENT or event.producer!=PRODUCER
                or event.hash!=canonical_hash(event.body()) or event.payload.get('schema')!=SCHEMA
                or event.payload.get('scope_hash')!=scope_hash):raise LedgerError('funding_observation_journal_invalid')
            try:
                statement=NativeCashStatement.from_body(event.payload['statement']);self._validate(statement)
                if statement.scope_hash!=scope_hash or self._key(statement)!=event.payload['content_key'] or event.payload['state'] not in {'OBSERVED','CONFLICT'}:
                    raise ValueError('funding_observation_scope_invalid')
            except (KeyError,TypeError,ValueError,ArithmeticError) as exc:
                raise LedgerError('funding_observation_journal_invalid') from exc
            output.append(event)
        return output

    def record_statement(self,statement):
        self._validate(statement);received=native_int(self.clock(),minimum=statement.observed_at_ms)
        key=self._key(statement);scope=statement.scope_hash
        with self.ledger.atomic():
            if not self.ledger.verify_incremental()[0]:raise LedgerError('funding_observation_chain_invalid')
            previous=self._events(scope)
            for event in previous:
                if event.payload['content_key']==key:return self._receipt(event)
            originals={};conflicts={}
            for event in previous:
                if event.payload['state']!='OBSERVED':continue
                for row in event.payload['statement']['movements']:
                    old=originals.setdefault(row['native_id'],(row,event.hash))
                    if old[0]!=row:raise LedgerError('funding_original_history_conflict')
            for row in statement.movements:
                old=originals.get(row.native_id)
                if old and old[0]!=row.body():conflicts[str(row.native_id)]=old[1]
            event=make_event(EventKind.FUNDING_STATEMENT,PRODUCER,{'schema':SCHEMA,'scope_hash':scope,
                'content_key':key,'state':'CONFLICT' if conflicts else 'OBSERVED','statement':statement.body(),
                'conflicting_original_refs':conflicts,'execution_authority':False},event_time_ms=statement.to_ms,
                received_time_ms=received,correlation_id='funding:'+scope)
            self.ledger.append(event)
        return self._receipt(event)

    def collect_statement(self,adapter,*,from_ms,to_ms):
        # Native I/O precedes the journal writer lock. It cannot block order writes
        # while waiting for a provider, nor submit a financial movement.
        return self.record_statement(adapter.cash_movements(from_ms=from_ms,to_ms=to_ms))

    @staticmethod
    def _receipt(event):
        return {'statement_ref':event.hash,'scope_hash':event.payload['scope_hash'],'state':event.payload['state'],
            'observed_at_ms':event.payload['statement']['observed_at_ms'],'received_at_ms':event.received_time_ms,
            'row_count':len(event.payload['statement']['movements']),'execution_authority':False}

    def observations(self,scope_hash,*,as_of=None):
        with self.ledger.atomic():
            if not self.ledger.verify_incremental()[0]:raise LedgerError('funding_observation_chain_invalid')
            events=self._events(scope_hash,as_of);originals={};conflicts=[];windows=[]
            for event in events:
                if event.payload['state']=='CONFLICT':
                    conflicts.append({'statement_ref':event.hash,'original_refs':event.payload['conflicting_original_refs']})
                    continue
                body=event.payload['statement'];windows.append({'from_ms':body['from_ms'],'to_ms':body['to_ms'],'statement_ref':event.hash})
                for row in body['movements']:
                    old=originals.setdefault(row['native_id'],{'movement':row,'original_statement_ref':event.hash})
                    if old['movement']!=row:raise LedgerError('funding_original_history_conflict')
            return {'scope_hash':scope_hash,'state':'CONFLICT' if conflicts else 'OBSERVED' if events else 'NO_DATA',
                'movements':list(originals.values()),'coverage_windows':windows,'conflicts':conflicts,
                'return_qualification':'NOT_ISSUED','execution_authority':False}
