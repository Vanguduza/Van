"""Immutable native cash sets plus small source-bound current MT5 query receipts."""
from decimal import Decimal
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind,make_event
from vati.core.ledger import LedgerError
from vati.funding.journal import FundingBook
from vati.funding.mt5 import Mt5FundingFrame
from vati.funding.native import native_int


class Mt5FundingBook(FundingBook):
    kind=EventKind.FUNDING_MT5_STATEMENT
    producer='vati-native-mt5-funding'
    schema='native-mt5-funding-observation/1'
    statement_type=Mt5FundingFrame
    correlation_prefix='funding-mt5:'

    @staticmethod
    def _key(frame):
        # No new full financial statement for every poll of unchanged cash.
        # Current query/mark evidence is independently retained below.
        return canonical_hash({'scope_hash':frame.scope_hash,'cash':sorted((r.body() for r in frame.movements),key=lambda r:r['native_id'])})

    @staticmethod
    def _validate(frame):
        if not isinstance(frame,Mt5FundingFrame):raise ValueError('mt5_native_frame_required')
        Mt5FundingFrame.from_body(frame.body())

    def capture(self,frame):
        self._validate(frame);received=native_int(self.clock(),minimum=frame.observed_at_ms)
        with self.ledger.atomic():
            receipt=self.record_statement(frame)
            for e in self._queries(frame.scope_hash):
                if e.payload['source_ref']==frame.source_ref:return e.hash,receipt
            event=make_event(EventKind.FUNDING_MT5_QUERY,self.producer,{'schema':'native-mt5-query/1',
                'scope_hash':frame.scope_hash,'source_ref':frame.source_ref,'mark':frame.mark_body(),
                'cash_key':self._key(frame),'cash_statement_ref':receipt['statement_ref'],'execution_authority':False},
                event_time_ms=frame.observed_at_ms,received_time_ms=received,correlation_id='mt5-query:'+frame.scope_hash)
            self.ledger.append(event)
        return event.hash,receipt

    def _queries(self,scope):
        rows=list(self.ledger.iter(EventKind.FUNDING_MT5_QUERY,correlation_id='mt5-query:'+scope))
        statements={e.hash:e for e in self._events(scope)}
        for event in rows:
            p=event.payload
            if (event.producer!=self.producer or event.hash!=canonical_hash(event.body())
                or p.get('schema')!='native-mt5-query/1' or p.get('scope_hash')!=scope
                or set(p)!={'schema','scope_hash','source_ref','mark','cash_key','cash_statement_ref','execution_authority'}
                or p['execution_authority'] is not False
                or p.get('cash_statement_ref') not in statements):raise LedgerError('mt5_native_query_journal_invalid')
            statement=statements[p['cash_statement_ref']]
            frame=Mt5FundingFrame.from_body(statement.payload['statement'])
            # Reconstitute the source frame from original immutable cash rows
            # and the small current mark; source_ref must reproduce exactly.
            mark=p.get('mark')
            try:
                from dataclasses import replace
                current=replace(frame,**{k:mark[k] for k in ('account_alias','login','server','currency','demo','observed_at_ms','source_kind','source_nonce','native_clock_ms','query_native_to_ms','currency_digits')},
                    balance=Decimal(mark['balance']),reported_equity=Decimal(mark['reported_equity']),credit=Decimal(mark['credit']))
                self._validate(current)
                if current.mark_body()!=mark or current.source_ref!=p['source_ref'] or self._key(current)!=p['cash_key'] or current.scope_hash!=scope:raise ValueError()
                if (event.event_time_ms!=current.observed_at_ms or event.received_time_ms<event.event_time_ms
                    or statement.received_time_ms>event.received_time_ms):raise ValueError()
            except (KeyError,TypeError,ValueError,ArithmeticError) as exc:raise LedgerError('mt5_native_query_source_invalid') from exc
        return rows
