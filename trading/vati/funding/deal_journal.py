"""Original complete native deal observations share the financial journal fence."""
from decimal import Decimal,localcontext
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.funding.deals import NativeDealStatement,NativeDeal,NativeCloseBalance
from vati.funding.journal import FundingBook
from vati.funding.native import native_int,native_money

class DealBook(FundingBook):
    kind=EventKind.FUNDING_DEAL_STATEMENT
    producer='vati-native-funding-deals'
    schema='native-funding-deal-observation/1'
    statement_type=NativeDealStatement
    row_field='deals'
    row_label='deal'
    correlation_prefix='funding-deals:'

    @staticmethod
    def _key(statement):
        return canonical_hash({'scope_hash':statement.scope_hash,'from_ms':statement.from_ms,'to_ms':statement.to_ms,
            'deals':sorted((row.body() for row in statement.deals),key=lambda row:row['native_id'])})

    @staticmethod
    def _validate(statement):
        if not isinstance(statement,NativeDealStatement) or statement.provider!='CTRADER' or statement.environment not in {'DEMO','LIVE'}:
            raise ValueError('funding_native_deal_scope_invalid')
        for value in (statement.native_account_id,statement.deposit_asset_id):native_int(value,minimum=1)
        if not isinstance(statement.currency,str) or not statement.currency.strip():raise ValueError('funding_native_currency_invalid')
        for value in (statement.from_ms,statement.to_ms,statement.observed_at_ms):native_int(value,minimum=0)
        if not statement.from_ms<=statement.to_ms<=statement.observed_at_ms or statement.to_ms-statement.from_ms>604800000:raise ValueError('funding_native_deal_window_invalid')
        native_int(statement.request_count,minimum=1,maximum=128)
        if len(statement.deals)>64000:raise ValueError('funding_native_deal_resource_bound')
        def money(value,digits):
            native_int(digits,minimum=0,maximum=18)
            if not isinstance(value,Decimal) or not value.is_finite():raise ValueError('funding_native_deal_money_invalid')
            if not native_money(-(2**63),digits)<=value<=native_money(2**63-1,digits):raise ValueError('funding_native_deal_money_invalid')
            with localcontext() as ctx:
                ctx.prec=80
                if value.quantize(native_money(1,digits))!=value:raise ValueError('funding_native_deal_precision_invalid')
        def price(value):
            if not isinstance(value,Decimal) or not value.is_finite() or value<=0 or len(str(value))>128:raise ValueError('funding_native_deal_price_invalid')
        seen=set()
        for row in statement.deals:
            if not isinstance(row,NativeDeal):raise ValueError('funding_native_deal_format_invalid')
            for value in (row.native_id,row.order_id,row.position_id,row.symbol_id):native_int(value,minimum=1)
            if row.native_id in seen:raise ValueError('funding_native_deal_identity_duplicated')
            seen.add(row.native_id);native_int(row.occurred_at_ms,minimum=statement.from_ms,maximum=statement.to_ms)
            native_int(row.requested_volume_cents,minimum=0);native_int(row.filled_volume_cents,minimum=0,maximum=row.requested_volume_cents)
            if not isinstance(row.status,str) or not row.status:raise ValueError('funding_native_deal_status_invalid')
            if row.money_digits is not None:native_int(row.money_digits,minimum=0,maximum=18)
            if row.commission is not None:money(row.commission,row.money_digits)
            if row.execution_price is not None:price(row.execution_price)
            if row.filled_volume_cents and (row.execution_price is None or row.status not in {'FILLED','PARTIALLY_FILLED'}):raise ValueError('funding_native_deal_fill_invalid')
            if row.close is not None:
                detail=row.close
                if not isinstance(detail,NativeCloseBalance) or not row.filled_volume_cents:raise ValueError('funding_native_deal_close_invalid')
                price(detail.entry_price)
                for value in (detail.gross_profit,detail.swap,detail.commission,detail.balance_after):money(value,detail.money_digits)
                if detail.pnl_conversion_fee is not None:money(detail.pnl_conversion_fee,detail.money_digits)
                if detail.balance_version is not None:native_int(detail.balance_version,minimum=0)
                if detail.closed_volume_cents is not None:native_int(detail.closed_volume_cents,minimum=0,maximum=row.filled_volume_cents)

    def collect_statement(self,adapter,*,from_ms,to_ms):
        return self.record_statement(adapter.deal_history(from_ms=from_ms,to_ms=to_ms))
