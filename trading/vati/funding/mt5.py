"""Original MT5 cash observations; native clock values are never called UTC.

Currency digits describe display precision, not an invented settlement quantum.
This contract preserves the native double's decimal text. It does not certify
settled money, fee allocation or cash-flow-adjusted percentage returns.
"""
from dataclasses import dataclass
from decimal import Decimal, localcontext
from vati.core.decimal_context import native_decimal_context
from vati.core.canonical import canonical_hash
from vati.funding.native import native_int

SCHEMA='van.mt5.cash-telemetry/1'
TIME_BASES={'MT5_SIGNED_EA_POLL':'MT5_TERMINAL_NATIVE_NOT_UTC_QUALIFIED',
    'MT5_SIGNED_MTLS_READ':'MT5_PYTHON_QUERY_UTC_HOST_NOT_BROKER_CLOCK'}
MAX_CASH_ROWS=4096


def amount(value):
    if not isinstance(value,str) or not 1<=len(value)<=128:raise ValueError('mt5_native_money_text_required')
    result=Decimal(value)
    if not result.is_finite() or abs(result.as_tuple().exponent)>128:raise ValueError('mt5_native_money_invalid')
    return result


def text(value):
    if not isinstance(value,str) or not value.strip() or value!=value.strip() or len(value)>256:raise ValueError('mt5_native_identity_invalid')
    return value


@dataclass(frozen=True)
class Mt5CashFact:
    native_id: int
    operation: str
    native_time_ms: int
    profit: Decimal
    commission: Decimal
    swap: Decimal
    fee: Decimal

    def body(self):
        return {'native_id':self.native_id,'operation':self.operation,'native_time_ms':self.native_time_ms,
            **{k:str(getattr(self,k)) for k in ('profit','commission','swap','fee')}}

    @classmethod
    def from_body(cls,body):
        if not isinstance(body,dict) or set(body)!=set(cls.__dataclass_fields__):raise ValueError('mt5_native_cash_format_invalid')
        native_int(body['native_id'],minimum=1,maximum=2**64-1);native_int(body['native_time_ms'],minimum=0)
        operation=text(body['operation'])
        if operation in {'DEAL_TYPE_BUY','DEAL_TYPE_SELL'}:raise ValueError('mt5_trade_is_not_a_cash_fact')
        return cls(body['native_id'],operation,body['native_time_ms'],*(amount(body[k]) for k in ('profit','commission','swap','fee')))


@dataclass(frozen=True)
class Mt5FundingFrame:
    account_alias: str
    login: int
    server: str
    currency: str
    demo: bool
    observed_at_ms: int
    source_kind: str
    source_nonce: str
    native_clock_ms: int
    query_native_to_ms: int
    balance: Decimal
    reported_equity: Decimal
    credit: Decimal
    currency_digits: int
    movements: tuple[Mt5CashFact,...]

    @property
    def from_ms(self):return self.observed_at_ms
    @property
    def to_ms(self):return self.observed_at_ms
    @property
    def scope_hash(self):
        return canonical_hash({'provider':'MT5','login':self.login,'server':self.server,'currency':self.currency,'demo':self.demo})
    @property
    def net_equity(self):
        with localcontext(native_decimal_context(precision=512)):
            return self.reported_equity-self.credit
    @property
    def source_ref(self):
        body=self.body();body.pop('account_alias')
        return canonical_hash(body)
    def body(self):
        return {'schema':'mt5-funding-observation/1','scope_hash':self.scope_hash,
            **{k:getattr(self,k) for k in ('account_alias','login','server','currency','demo','observed_at_ms','source_kind','source_nonce',
                'native_clock_ms','query_native_to_ms','currency_digits')},
            **{k:str(getattr(self,k)) for k in ('balance','reported_equity','credit')},
            'from_ms':self.from_ms,'to_ms':self.to_ms,'movements':[r.body() for r in self.movements],
            'native_time_basis':TIME_BASES[self.source_kind],
            'money_basis':'NATIVE_DOUBLE_TEXT_NOT_SETTLED_MINOR_UNITS'}
    def mark_body(self):
        return {'schema':'mt5-account-mark/1','scope_hash':self.scope_hash,'source_ref':self.source_ref,
            **{k:getattr(self,k) for k in ('account_alias','login','server','currency','demo','observed_at_ms','source_kind','source_nonce','native_clock_ms','query_native_to_ms','currency_digits')},
            'balance':str(self.balance),'reported_equity':str(self.reported_equity),'credit':str(self.credit),
            'net_equity':str(self.net_equity),'valuation_basis':'REPORTED_ACCOUNT_EQUITY_MINUS_NATIVE_ACCOUNT_CREDIT'}

    @classmethod
    def from_body(cls,body):
        if not isinstance(body,dict):raise ValueError('mt5_funding_frame_invalid')
        fields=set(cls.__dataclass_fields__)
        if set(body)!=fields|{'schema','scope_hash','from_ms','to_ms','native_time_basis','money_basis'}:raise ValueError('mt5_funding_frame_invalid')
        if (body['schema']!='mt5-funding-observation/1' or body['native_time_basis']!=TIME_BASES.get(body.get('source_kind'))
            or body['money_basis']!='NATIVE_DOUBLE_TEXT_NOT_SETTLED_MINOR_UNITS'):raise ValueError('mt5_funding_frame_invalid')
        for k in ('account_alias','server','currency','source_nonce'):text(body[k])
        if body['source_kind'] not in {'MT5_SIGNED_EA_POLL','MT5_SIGNED_MTLS_READ'} or type(body['demo']) is not bool:raise ValueError('mt5_funding_source_invalid')
        native_int(body['login'],minimum=1)
        for k in ('observed_at_ms','native_clock_ms','query_native_to_ms','from_ms','to_ms'):native_int(body[k],minimum=0)
        native_int(body['currency_digits'],minimum=0,maximum=16)
        if body['query_native_to_ms']<body['native_clock_ms'] or body['from_ms']!=body['to_ms'] or body['to_ms']!=body['observed_at_ms']:raise ValueError('mt5_funding_clock_invalid')
        rows=body['movements']
        if not isinstance(rows,list) or len(rows)>MAX_CASH_ROWS:raise ValueError('mt5_funding_rows_invalid')
        rows=tuple(Mt5CashFact.from_body(r) for r in rows)
        if len({r.native_id for r in rows})!=len(rows) or any(r.native_time_ms>body['query_native_to_ms'] for r in rows):raise ValueError('mt5_funding_cash_identity_invalid')
        values={k:body[k] for k in fields};values.update({k:amount(body[k]) for k in ('balance','reported_equity','credit')});values['movements']=tuple(sorted(rows,key=lambda r:r.native_id))
        if values['credit']<0:raise ValueError('mt5_credit_liability_requires_qualification')
        result=cls(**values)
        if result.scope_hash!=body['scope_hash']:raise ValueError('mt5_funding_scope_invalid')
        return result


def frame_from_poll(account_alias,account,*,received_ms,nonce,source_kind='MT5_SIGNED_EA_POLL'):
    """Only the authenticated adapter supplies this cache; owner JSON is not an ingress."""
    raw=account.get('funding') if isinstance(account,dict) else None
    if not isinstance(raw,dict) or raw.get('schema')!=SCHEMA or raw.get('complete') is not True:raise ValueError('mt5_native_cash_unavailable')
    required={'schema','complete','native_from_ms','native_to_ms','native_clock_ms','binding_before','balance_before','credit_before','movements'}
    if set(raw)!=required or raw['native_from_ms']!=0:raise ValueError('mt5_native_cash_query_invalid')
    native_int(raw['native_from_ms'],minimum=0,maximum=0)
    if not isinstance(raw['movements'],list) or len(raw['movements'])>MAX_CASH_ROWS:raise ValueError('mt5_funding_rows_invalid')
    binding={k:account.get(k) for k in ('login','server','currency','demo')}
    if canonical_hash(raw['binding_before'])!=canonical_hash(binding):raise ValueError('mt5_native_identity_changed_during_cash_read')
    if amount(raw['balance_before'])!=amount(account['balance']) or amount(raw['credit_before'])!=amount(account['credit']):raise ValueError('mt5_native_funds_changed_during_cash_read')
    result=Mt5FundingFrame(account_alias,binding['login'],binding['server'],binding['currency'],binding['demo'],received_ms,source_kind,nonce,
        raw['native_clock_ms'],raw['native_to_ms'],amount(account['balance']),amount(account['equity']),amount(account['credit']),account['currency_digits'],
        tuple(Mt5CashFact.from_body(r) for r in raw['movements']))
    return Mt5FundingFrame.from_body(result.body())
