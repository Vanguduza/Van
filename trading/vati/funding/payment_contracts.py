"""Immutable funding drafts, not beneficiary verification or permission to pay.

The provider owner must independently resolve the original quote and beneficiary
proof before approval, reservation or send. No instrument fields, provider
client, ledger writer, owner grant or execution route are defined here. Before
retaining untrusted text, callers must enforce the existing payment boundary.
"""
from dataclasses import dataclass
import re

from vati.core.canonical import canonical_hash,canonical_json
from vati.core.units import Money

HEX=re.compile('[a-f0-9]{64}',re.ASCII)
IDENTITY=re.compile('[A-Za-z0-9][A-Za-z0-9_:.-]{0,127}',re.ASCII)
MAX_TIME=253402300799000


class PaymentContractError(ValueError):
    pass


def _ref(value):
    if type(value) is not str or HEX.fullmatch(value) is None:
        raise PaymentContractError('PAYMENT_REFERENCE_INVALID')
    return value


def _identity(value):
    if type(value) is not str or IDENTITY.fullmatch(value) is None:
        raise PaymentContractError('PAYMENT_IDENTITY_INVALID')
    return value


def _reference_text(value):
    if (type(value) is not str or not 1<=len(value)<=1024 or not value.strip()
            or len(value.encode('utf-8'))>1024 or any(ord(c)<32 or ord(c)==127 for c in value)):
        raise PaymentContractError('PAYMENT_REFERENCE_TEXT_INVALID')
    return value


def _integer(value,*,minimum=0,maximum=MAX_TIME):
    if type(value) is not int or not minimum<=value<=maximum:
        raise PaymentContractError('PAYMENT_INTEGER_INVALID')
    return value


def _money(value,*,positive=False):
    if type(value) is not Money or value.minor_units<(1 if positive else 0):
        raise PaymentContractError('PAYMENT_EXACT_NONNEGATIVE_MONEY_REQUIRED')
    return value


def _asset(value):return value.currency,value.asset_ref


def _wire(body,keys,constants,parse):
    try:
        if type(body) is not dict or len(body)!=len(keys) or set(body)!=set(keys):raise ValueError
        for key,value in constants.items():
            if type(body[key]) is not type(value) or body[key]!=value:raise ValueError
        result=parse(body)
        if canonical_json(result.body())!=canonical_json(body):raise ValueError
        return result
    except (KeyError,TypeError,ValueError,ArithmeticError):
        raise PaymentContractError('PAYMENT_WIRE_FORMAT_INVALID') from None


def _fee_set(body):
    if type(body) is not list or len(body)>32:raise PaymentContractError('PAYMENT_FEE_SET_INVALID')
    return tuple(PaymentFee.from_body(fee) for fee in body)


@dataclass(frozen=True)
class BeneficiaryRef:
    provider: str
    environment: str
    owner_ref: str
    account_scope_ref: str
    beneficiary_digest: str
    verification_record_ref: str

    def __post_init__(self):
        _identity(self.provider);_identity(self.owner_ref)
        if self.environment not in ('DEMO','LIVE') or type(self.environment) is not str:
            raise PaymentContractError('PAYMENT_ENVIRONMENT_INVALID')
        for value in (self.account_scope_ref,self.beneficiary_digest,self.verification_record_ref):_ref(value)

    def body(self):
        # References name original non-secret records. Digests are integrity
        # bindings, never proof that a beneficiary has actually been verified.
        return {'schema':'vati.beneficiary-ref/1','provider':self.provider,'environment':self.environment,
            'owner_ref':self.owner_ref,'account_scope_ref':self.account_scope_ref,
            'beneficiary_digest':self.beneficiary_digest,'verification_record_ref':self.verification_record_ref,
            'verification_state':'UNVERIFIED_REFERENCE','execution_authority':False}

    @classmethod
    def from_body(cls,body):
        fields=tuple(cls.__dataclass_fields__)
        constants={'schema':'vati.beneficiary-ref/1','verification_state':'UNVERIFIED_REFERENCE','execution_authority':False}
        return _wire(body,fields+tuple(constants),constants,lambda b:cls(**{k:b[k] for k in fields}))


@dataclass(frozen=True)
class PaymentFee:
    fee_id: str
    amount: Money
    included_in_debit: bool

    def __post_init__(self):
        _identity(self.fee_id);_money(self.amount)
        if type(self.included_in_debit) is not bool:raise PaymentContractError('PAYMENT_FEE_INCLUSION_INVALID')

    def body(self):
        return {'fee_id':self.fee_id,'amount':self.amount.body(),'included_in_debit':self.included_in_debit}

    @classmethod
    def from_body(cls,body):
        return _wire(body,('fee_id','amount','included_in_debit'),{},
            lambda b:cls(b['fee_id'],Money.from_body(b['amount']),b['included_in_debit']))


@dataclass(frozen=True)
class PaymentQuote:
    quote_record_ref: str
    revision: int
    beneficiary: BeneficiaryRef
    amount: Money
    quoted_debit: Money
    fees: tuple[PaymentFee,...]
    reference: str
    issued_at_ms: int
    expires_at_ms: int
    conversion_record_ref: str|None=None

    def __post_init__(self):
        _ref(self.quote_record_ref);_integer(self.revision,minimum=1,maximum=2**63-1)
        if type(self.beneficiary) is not BeneficiaryRef:raise PaymentContractError('PAYMENT_BENEFICIARY_REFERENCE_REQUIRED')
        _money(self.amount,positive=True);_money(self.quoted_debit,positive=True);_reference_text(self.reference)
        _integer(self.issued_at_ms);_integer(self.expires_at_ms,minimum=self.issued_at_ms+1)
        if type(self.fees) is not tuple or len(self.fees)>32 or any(type(fee) is not PaymentFee for fee in self.fees):
            raise PaymentContractError('PAYMENT_FEE_SET_INVALID')
        if len({fee.fee_id for fee in self.fees})!=len(self.fees):raise PaymentContractError('PAYMENT_FEE_IDENTITY_DUPLICATE')
        if any(fee.included_in_debit and _asset(fee.amount)!=_asset(self.quoted_debit) for fee in self.fees):
            raise PaymentContractError('PAYMENT_INCLUDED_FEE_ASSET_MISMATCH')
        if self.conversion_record_ref is not None:_ref(self.conversion_record_ref)
        if _asset(self.amount)!=_asset(self.quoted_debit):
            if self.conversion_record_ref is None:raise PaymentContractError('PAYMENT_CONVERSION_REFERENCE_REQUIRED')
            # No inferred exchange rate, rounding or asset equivalence. The
            # original provider conversion still needs independent resolution.
        else:
            total=self.amount
            for fee in self.fees:
                if fee.included_in_debit:total=total+fee.amount
            if total.fraction!=self.quoted_debit.fraction:
                raise PaymentContractError('PAYMENT_DEBIT_FEE_TOTAL_DIFFERS')

    def body(self):
        return {'schema':'vati.payment-quote/1','quote_record_ref':self.quote_record_ref,'revision':self.revision,
            'beneficiary':self.beneficiary.body(),'amount':self.amount.body(),'quoted_debit':self.quoted_debit.body(),
            'fees':[fee.body() for fee in sorted(self.fees,key=lambda f:f.fee_id)],'reference':self.reference,
            'issued_at_ms':self.issued_at_ms,'expires_at_ms':self.expires_at_ms,
            'conversion_record_ref':self.conversion_record_ref,'state':'UNVERIFIED_PROVIDER_QUOTE',
            'provider_qualified':False,'execution_authority':False}

    @property
    def quote_hash(self):return canonical_hash(self.body())

    @classmethod
    def from_body(cls,body):
        fields=tuple(cls.__dataclass_fields__)
        constants={'schema':'vati.payment-quote/1','state':'UNVERIFIED_PROVIDER_QUOTE','provider_qualified':False,'execution_authority':False}
        def parse(b):
            values={k:b[k] for k in fields}
            values.update(beneficiary=BeneficiaryRef.from_body(b['beneficiary']),amount=Money.from_body(b['amount']),
                quoted_debit=Money.from_body(b['quoted_debit']),fees=_fee_set(b['fees']))
            return cls(**values)
        return _wire(body,fields+tuple(constants),constants,parse)

    def declared_debits(self):
        """Exact provider-claimed requirements; no collateral or reservation proof."""
        amounts={_asset(self.quoted_debit):self.quoted_debit}
        for fee in self.fees:
            if not fee.included_in_debit:
                key=_asset(fee.amount)
                amounts[key]=amounts[key]+fee.amount if key in amounts else fee.amount
        return tuple(amounts[key] for key in sorted(amounts))

    def validate_binding(self,*,expected_hash,owner_ref,account_scope_ref,beneficiary_digest,now_ms):
        """Reject stale/changed preview input. This never approves a payment."""
        _ref(expected_hash);_identity(owner_ref);_ref(account_scope_ref);_ref(beneficiary_digest);_integer(now_ms)
        if (self.quote_hash!=expected_hash or self.beneficiary.owner_ref!=owner_ref
                or self.beneficiary.account_scope_ref!=account_scope_ref
                or self.beneficiary.beneficiary_digest!=beneficiary_digest):
            raise PaymentContractError('PAYMENT_QUOTE_BINDING_DIFFERS')
        if now_ms<self.issued_at_ms:raise PaymentContractError('PAYMENT_QUOTE_NOT_YET_ISSUED')
        if now_ms>=self.expires_at_ms:raise PaymentContractError('PAYMENT_QUOTE_EXPIRED')


@dataclass(frozen=True)
class PaymentIntent:
    request_id: str
    operation: str
    quote: PaymentQuote

    def __post_init__(self):
        _identity(self.request_id)
        if self.operation not in ('DEPOSIT','WITHDRAW','TRANSFER') or type(self.operation) is not str:
            raise PaymentContractError('PAYMENT_OPERATION_INVALID')
        if type(self.quote) is not PaymentQuote:raise PaymentContractError('PAYMENT_QUOTE_REQUIRED')

    def body(self):
        return {'schema':'vati.payment-intent/1','request_id':self.request_id,'operation':self.operation,
            'quote_hash':self.quote.quote_hash,'quote':self.quote.body(),'state':'DRAFT_NOT_APPROVED',
            'provider_qualified':False,'execution_authority':False}

    @property
    def intent_hash(self):return canonical_hash(self.body())

    @classmethod
    def from_body(cls,body):
        constants={'schema':'vati.payment-intent/1','state':'DRAFT_NOT_APPROVED','provider_qualified':False,'execution_authority':False}
        def parse(b):
            _ref(b['quote_hash'])
            return cls(b['request_id'],b['operation'],PaymentQuote.from_body(b['quote']))
        return _wire(body,('request_id','operation','quote_hash','quote')+tuple(constants),constants,
            parse)

    def validate_binding(self,*,expected_intent_hash,owner_ref,account_scope_ref,beneficiary_digest,now_ms):
        _ref(expected_intent_hash)
        if self.intent_hash!=expected_intent_hash:raise PaymentContractError('PAYMENT_INTENT_BINDING_DIFFERS')
        self.quote.validate_binding(expected_hash=self.quote.quote_hash,owner_ref=owner_ref,
            account_scope_ref=account_scope_ref,beneficiary_digest=beneficiary_digest,now_ms=now_ms)
