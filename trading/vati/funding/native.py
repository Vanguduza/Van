"""Immutable native statement facts; a digest supplies integrity, not authority."""
from dataclasses import dataclass
from decimal import Decimal
from vati.core.canonical import canonical_hash

@dataclass(frozen=True)
class NativeAccountMark:
    provider: str
    environment: str
    account_alias: str
    native_account_id: int
    deposit_asset_id: int
    currency: str
    observed_at_ms: int
    balance: Decimal
    net_equity: Decimal
    balance_version: int | None
    manager_bonus: Decimal | None
    ib_bonus: Decimal | None
    nonwithdrawable_bonus: Decimal | None
    registered_at_ms: int | None = None

    @property
    def scope_hash(self):
        return canonical_hash({"provider":self.provider,"environment":self.environment,
            "native_account_id":self.native_account_id,"deposit_asset_id":self.deposit_asset_id,"currency":self.currency})

    def body(self):
        return {"schema":"native-account-mark/1","scope_hash":self.scope_hash,
            **{k:getattr(self,k) for k in ('provider','environment','account_alias','native_account_id','deposit_asset_id','currency','observed_at_ms','balance_version','registered_at_ms')},
            **{k:str(getattr(self,k)) if getattr(self,k) is not None else None for k in ('balance','net_equity','manager_bonus','ib_bonus','nonwithdrawable_bonus')},
            'valuation_basis':'BALANCE_PLUS_NATIVE_NET_UNREALIZED_EXCLUDING_SEPARATE_BONUSES'}

    @classmethod
    def from_body(cls,body):
        fields=set(cls.__dataclass_fields__)
        if (not isinstance(body,dict) or set(body)!=fields|{'schema','scope_hash','valuation_basis'}
            or body['schema']!='native-account-mark/1'
            or body['valuation_basis']!='BALANCE_PLUS_NATIVE_NET_UNREALIZED_EXCLUDING_SEPARATE_BONUSES'):
            raise ValueError('native_account_mark_format_invalid')
        values={k:body[k] for k in fields}
        for key in ('balance','net_equity','manager_bonus','ib_bonus','nonwithdrawable_bonus'):
            value=values[key]
            if value is None and key not in {'balance','net_equity'}:continue
            if not isinstance(value,str) or not 1<=len(value)<=128:raise ValueError('native_account_mark_money_invalid')
            value=Decimal(value)
            if (not value.is_finite() or len(value.as_tuple().digits)>4096 or abs(value.as_tuple().exponent)>4096):
                raise ValueError('native_account_mark_money_invalid')
            values[key]=value
        for key in ('native_account_id','deposit_asset_id'):native_int(values[key],minimum=1)
        native_int(values['observed_at_ms'],minimum=0)
        for key in ('balance_version','registered_at_ms'):
            if values[key] is not None:native_int(values[key],minimum=0)
        if values['provider']!='CTRADER' or values['environment'] not in {'DEMO','LIVE'}:raise ValueError('native_account_mark_scope_invalid')
        for key in ('currency','account_alias'):
            if not isinstance(values[key],str) or not values[key].strip():raise ValueError('native_account_mark_scope_invalid')
        mark=cls(**values)
        if mark.scope_hash!=body['scope_hash']:raise ValueError('native_account_mark_scope_invalid')
        return mark

@dataclass(frozen=True)
class NativeCashMovement:
    native_id: int
    operation: str
    delta: Decimal
    balance_after: Decimal
    equity_after: Decimal | None
    balance_version: int | None
    occurred_at_ms: int
    money_digits: int

    def body(self):
        return {"native_id": self.native_id, "operation": self.operation,
            "delta": str(self.delta), "balance_after": str(self.balance_after),
            "equity_after": str(self.equity_after) if self.equity_after is not None else None,
            "balance_version": self.balance_version, "occurred_at_ms": self.occurred_at_ms,
            "money_digits": self.money_digits}

@dataclass(frozen=True)
class NativeCashStatement:
    provider: str
    environment: str
    account_alias: str
    native_account_id: int
    deposit_asset_id: int
    currency: str
    from_ms: int
    to_ms: int
    observed_at_ms: int
    movements: tuple[NativeCashMovement, ...]

    def body(self):
        return {"schema": "native-cash-statement/1", "provider": self.provider,
            "environment": self.environment, "account_alias": self.account_alias, "native_account_id": self.native_account_id,
            "deposit_asset_id": self.deposit_asset_id, "currency": self.currency,
            "from_ms": self.from_ms, "to_ms": self.to_ms, "observed_at_ms": self.observed_at_ms,
            "movements": [row.body() for row in self.movements]}

    @classmethod
    def from_body(cls,body):
        if (not isinstance(body,dict) or body.get('schema')!='native-cash-statement/1'
            or set(body)!={'schema','provider','environment','account_alias','native_account_id','deposit_asset_id','currency','from_ms','to_ms','observed_at_ms','movements'}):
            raise ValueError('native_cash_statement_format_invalid')
        def amount(value):
            if not isinstance(value,str) or not 1<=len(value)<=128:raise ValueError('native_cash_amount_format_invalid')
            result=Decimal(value)
            if not result.is_finite():raise ValueError('native_cash_amount_format_invalid')
            return result
        if not isinstance(body['movements'],list):raise ValueError('native_cash_statement_format_invalid')
        rows=[]
        fields={'native_id','operation','delta','balance_after','equity_after','balance_version','occurred_at_ms','money_digits'}
        for row in body['movements']:
            if not isinstance(row,dict) or set(row)!=fields:raise ValueError('native_cash_statement_format_invalid')
            rows.append(NativeCashMovement(row['native_id'],row['operation'],amount(row['delta']),amount(row['balance_after']),
                amount(row['equity_after']) if row['equity_after'] is not None else None,row['balance_version'],row['occurred_at_ms'],row['money_digits']))
        return cls(body['provider'],body['environment'],body['account_alias'],body['native_account_id'],body['deposit_asset_id'],
            body['currency'],body['from_ms'],body['to_ms'],body['observed_at_ms'],tuple(rows))

    @property
    def scope_hash(self):
        # Alias and receipt time are presentation/availability, not account identity.
        return canonical_hash({"provider":self.provider,"environment":self.environment,
            "native_account_id":self.native_account_id,"deposit_asset_id":self.deposit_asset_id,"currency":self.currency})

    @property
    def digest(self):
        return canonical_hash(self.body())


def native_int(value, *, minimum=-(2**63), maximum=2**63-1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("native_integer_required")
    return value


def native_money(value, digits):
    value=native_int(value);digits=native_int(digits,minimum=0,maximum=18)
    # Tuple construction is exact even when a caller uses a low Decimal precision.
    return Decimal((int(value<0),tuple(int(x) for x in str(abs(value))),-digits))
