"""Bound native account facts, independent of cash-history coverage.

This is a source observation, not a cash statement, settled valuation or order
permission. Unknown credit cannot become a measured cash-backed risk equity.
"""
from dataclasses import dataclass
from decimal import Decimal, localcontext
from vati.core.canonical import canonical_hash
from vati.execution.mt5_identity import Mt5Identity
from vati.execution.base import VenueUnavailable
from vati.funding.mt5 import amount, text
from vati.funding.native import native_int

SOURCES = {'MT5_SIGNED_MTLS_READ', 'MT5_SIGNED_EA_POLL'}


@dataclass(frozen=True)
class Mt5AccountObservation:
    account_alias: str
    identity: Mt5Identity
    reported_equity: Decimal
    balance: Decimal
    credit: Decimal | None
    source_kind: str
    source_nonce: str
    source_received_at_ms: int
    observed_at_ms: int

    def __post_init__(self):
        text(self.account_alias); text(self.source_nonce)
        if type(self.identity) is not Mt5Identity or self.source_kind not in SOURCES:
            raise ValueError('native_account_source_invalid')
        text(self.identity.server); text(self.identity.currency)
        native_int(self.source_received_at_ms, minimum=0); native_int(self.observed_at_ms, minimum=0)
        if self.source_received_at_ms > self.observed_at_ms:
            raise ValueError('native_account_source_after_read')
        for value in (self.reported_equity, self.balance, self.credit):
            if value is not None:
                if type(value) is not Decimal: raise ValueError('native_account_money_invalid')
                amount(str(value))
        if self.reported_equity is None or self.balance is None:
            raise ValueError('native_account_valuation_unavailable')

    @property
    def valuation_state(self):
        return ('CREDIT_UNAVAILABLE' if self.credit is None else
                'CREDIT_LIABILITY_UNQUALIFIED' if self.credit < 0 else 'CREDIT_EXCLUDED')

    @property
    def risk_equity(self):
        if self.valuation_state != 'CREDIT_EXCLUDED': return None
        with localcontext() as context:
            context.prec = 512
            return self.reported_equity - self.credit

    @property
    def scope_hash(self):
        return canonical_hash({'provider': 'MT5', **self.identity.as_dict(), 'login': int(self.identity.login)})

    def body(self):
        value = {'schema': 'vati.mt5-account-observation/1', 'account_alias': self.account_alias,
            'provider': 'MT5', **self.identity.as_dict(), 'login': int(self.identity.login),
            'scope_hash': self.scope_hash, 'source_kind': self.source_kind, 'source_nonce': self.source_nonce,
            'source_received_at_ms': self.source_received_at_ms, 'observed_at_ms': self.observed_at_ms,
            'reported_equity': str(self.reported_equity), 'balance': str(self.balance),
            'credit': str(self.credit) if self.credit is not None else None,
            'risk_equity': str(self.risk_equity) if self.risk_equity is not None else None,
            'valuation_state': self.valuation_state, 'money_basis': 'NATIVE_DOUBLE_TEXT_NOT_SETTLED_MINOR_UNITS',
            'execution_authority': False}
        return value | {'source_ref': canonical_hash(value)}

    @classmethod
    def from_native(cls, alias, identity, account, *, source_kind, source_nonce, source_received_at_ms, observed_at_ms):
        identity.validate(account)
        try: credit = amount(account['credit'])
        except (KeyError, TypeError, ValueError, ArithmeticError): credit = None
        return cls(alias, identity, amount(str(account['equity'])), amount(str(account['balance'])), credit,
                   source_kind, source_nonce, source_received_at_ms, observed_at_ms)

    @classmethod
    def from_body(cls, body):
        if not isinstance(body, dict): raise ValueError('native_account_observation_invalid')
        if body.get('execution_authority') is not False or body.get('source_ref') != canonical_hash({k:v for k,v in body.items() if k!='source_ref'}):
            raise ValueError('native_account_observation_seal_invalid')
        value = cls(body['account_alias'], Mt5Identity(body['login'], body['server'], body['currency'], body['demo']),
            amount(body['reported_equity']), amount(body['balance']), amount(body['credit']) if body['credit'] is not None else None,
            body['source_kind'], body['source_nonce'], body['source_received_at_ms'], body['observed_at_ms'])
        if body != value.body(): raise ValueError('native_account_observation_changed')
        return value


def account_observation_body(account):
    value = getattr(account, 'native_observation', None)
    return value.body() if type(value) is Mt5AccountObservation else None


def observe_mt5_account(alias, identity, account, **metadata):
    if identity is None: return None
    try:
        return Mt5AccountObservation.from_native(alias, identity, account, **metadata)
    except (KeyError, TypeError, ValueError, ArithmeticError):
        # Missing legacy observation metadata withholds this proof, while the
        # adapter's independent physical-identity checks and protection survive.
        return None


def reported_account_observation(event, profile):
    """Join original producer/seal/valuation and the current physical profile."""
    from vati.core.events import EventKind
    unknown = {'state': 'UNMEASURED', 'execution_authority': False}
    if event is None: return unknown
    try:
        if event.payload.get('native_account_observation') is None: return unknown
        value = Mt5AccountObservation.from_body(event.payload['native_account_observation'])
        try:
            expected = Mt5Identity(profile.get('login'), profile.get('server'), profile.get('currency'), profile.get('demo'))
        except VenueUnavailable:
            return unknown | {'state': 'UNAVAILABLE', 'reason': 'CURRENT_PROFILE_NATIVE_SCOPE_MISMATCH'}
        if profile.get('broker') != 'MT5' or profile.get('alias') != value.account_alias or expected != value.identity:
            return unknown | {'state': 'UNAVAILABLE', 'reason': 'CURRENT_PROFILE_NATIVE_SCOPE_MISMATCH'}
        if (event.kind is not EventKind.ACCOUNT_SNAPSHOT or event.producer not in {'vati-service', 'vati-account-service'}
            or event.hash != canonical_hash(event.body()) or event.payload['account_alias'] != value.account_alias
            or event.payload['currency'] != value.identity.currency or event.payload['verified'] is not True
            or type(event.event_time_ms) is not int or type(event.received_time_ms) is not int
            or not 0 <= event.event_time_ms <= event.received_time_ms
            or not 0 <= value.observed_at_ms <= event.received_time_ms
            or amount(event.payload['balance']) != value.balance
            or amount(event.payload['equity']) != (value.risk_equity if value.risk_equity is not None else value.reported_equity)):
            raise ValueError('native_account_snapshot_join_invalid')
        return value.body() | {'state': 'OBSERVED', 'snapshot_ref': event.hash, 'received_at_ms': event.received_time_ms}
    except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError, VenueUnavailable):
        return unknown | {'state': 'UNAVAILABLE', 'reason': 'NATIVE_ACCOUNT_OBSERVATION_NOT_BOUND'}
