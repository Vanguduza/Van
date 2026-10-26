"""Exact scoped values, never proof of native facts or permission to spend.

Currency labels alone cannot identify an asset across providers. Quantities
name their instrument/contract owner. Conversion between identities requires
an actual separately validated conversion; these values never guess one.
"""
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
import re

MAX_DIGITS = 4096
MAX_SCALE = 4096
MAX_MINOR = 10**MAX_DIGITS - 1
INTEGER = re.compile(r'-?(?:0|[1-9][0-9]*)', re.ASCII)


class UnitError(ValueError):
    pass


def _identity(value, maximum=512):
    if (not isinstance(value, str) or not 1 <= len(value) <= maximum
            or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise UnitError('EXACT_UNIT_IDENTITY_REQUIRED')
    return value


def _scale(value):
    if type(value) is not int or not 0 <= value <= MAX_SCALE:
        raise UnitError('EXACT_UNIT_SCALE_INVALID')
    return value


def _minor(value):
    if type(value) is not int or abs(value) > MAX_MINOR:
        raise UnitError('EXACT_UNIT_INTEGER_OR_CAPACITY_INVALID')
    return value


def _parse_minor(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= MAX_DIGITS + 1
            or INTEGER.fullmatch(value) is None or value == '-0'):
        raise UnitError('EXACT_UNIT_CANONICAL_INTEGER_REQUIRED')
    return _minor(int(value))


def _from_decimal(value, scale):
    _scale(scale)
    if (not isinstance(value, Decimal) or not value.is_finite()
            or len(value.as_tuple().digits) > MAX_DIGITS
            or abs(value.as_tuple().exponent) > MAX_SCALE):
        raise UnitError('EXACT_UNIT_FINITE_DECIMAL_REQUIRED')
    exact = Fraction(value) * 10**scale
    if exact.denominator != 1:
        raise UnitError('EXACT_UNIT_NOT_REPRESENTABLE_AT_DECLARED_SCALE')
    return _minor(exact.numerator)


def _decimal(minor, scale):
    # Tuple construction preserves every digit even under hostile Decimal
    # rounding, precision, exponent limits or inexact traps in another caller.
    return Decimal((int(minor < 0), tuple(int(c) for c in str(abs(minor))), -scale))


def _rescale(minor, old, new):
    _scale(new)
    if new >= old:
        return _minor(minor * 10**(new-old))
    result, remainder = divmod(minor, 10**(old-new))
    if remainder:
        raise UnitError('EXACT_UNIT_RESCALE_WOULD_ROUND')
    return _minor(result)


@dataclass(frozen=True)
class Money:
    minor_units: int
    scale: int
    currency: str
    asset_ref: str

    def __post_init__(self):
        _minor(self.minor_units); _scale(self.scale)
        _identity(self.currency, 64); _identity(self.asset_ref)

    @classmethod
    def from_decimal(cls, value, *, scale, currency, asset_ref):
        return cls(_from_decimal(value, scale), scale, currency, asset_ref)

    @classmethod
    def from_body(cls, body):
        if not isinstance(body, dict) or set(body) != {'schema','minor_units','scale','currency','asset_ref'}:
            raise UnitError('EXACT_MONEY_FORMAT_INVALID')
        if body['schema'] != 'vati.money/1':
            raise UnitError('EXACT_MONEY_SCHEMA_INVALID')
        return cls(_parse_minor(body['minor_units']), body['scale'], body['currency'], body['asset_ref'])

    @property
    def decimal(self):
        return _decimal(self.minor_units, self.scale)

    @property
    def fraction(self):
        return Fraction(self.minor_units, 10**self.scale)

    def body(self):
        return {'schema':'vati.money/1','minor_units':str(self.minor_units),
            'scale':self.scale,'currency':self.currency,'asset_ref':self.asset_ref}

    def rescale(self, scale):
        return Money(_rescale(self.minor_units, self.scale, scale), scale, self.currency, self.asset_ref)

    def __add__(self, other):
        if type(other) is not Money:
            raise TypeError('money requires another Money value')
        if (other.currency, other.asset_ref) != (self.currency, self.asset_ref):
            raise UnitError('EXACT_MONEY_ASSET_MISMATCH_CONVERSION_REQUIRED')
        scale = max(self.scale, other.scale)
        a, b = self.rescale(scale), other.rescale(scale)
        return Money(a.minor_units + b.minor_units, scale, self.currency, self.asset_ref)

    def __neg__(self):
        return Money(-self.minor_units, self.scale, self.currency, self.asset_ref)

    def __sub__(self, other):
        if type(other) is not Money:
            raise TypeError('money requires another Money value')
        return self + (-other)


@dataclass(frozen=True)
class Quantity:
    units: int
    scale: int
    instrument_ref: str

    def __post_init__(self):
        _minor(self.units); _scale(self.scale); _identity(self.instrument_ref)

    @classmethod
    def from_decimal(cls, value, *, scale, instrument_ref):
        return cls(_from_decimal(value, scale), scale, instrument_ref)

    @classmethod
    def from_body(cls, body):
        if not isinstance(body, dict) or set(body) != {'schema','units','scale','instrument_ref'}:
            raise UnitError('EXACT_QUANTITY_FORMAT_INVALID')
        if body['schema'] != 'vati.quantity/1':
            raise UnitError('EXACT_QUANTITY_SCHEMA_INVALID')
        return cls(_parse_minor(body['units']), body['scale'], body['instrument_ref'])

    @property
    def decimal(self):
        return _decimal(self.units, self.scale)

    @property
    def fraction(self):
        return Fraction(self.units, 10**self.scale)

    def body(self):
        return {'schema':'vati.quantity/1','units':str(self.units),
            'scale':self.scale,'instrument_ref':self.instrument_ref}

    def rescale(self, scale):
        return Quantity(_rescale(self.units, self.scale, scale), scale, self.instrument_ref)

    def __add__(self, other):
        if type(other) is not Quantity:
            raise TypeError('quantity requires another Quantity value')
        if self.instrument_ref != other.instrument_ref:
            raise UnitError('EXACT_QUANTITY_INSTRUMENT_MISMATCH')
        scale = max(self.scale, other.scale)
        return Quantity(self.rescale(scale).units + other.rescale(scale).units, scale, self.instrument_ref)

    def __neg__(self):
        return Quantity(-self.units, self.scale, self.instrument_ref)

    def __sub__(self, other):
        if type(other) is not Quantity:
            raise TypeError('quantity requires another Quantity value')
        return self + (-other)


@dataclass(frozen=True)
class Posting:
    account_ref: str
    amount: Money

    def __post_init__(self):
        _identity(self.account_ref)
        if type(self.amount) is not Money:
            raise UnitError('POSTING_EXACT_MONEY_REQUIRED')

    def body(self):
        return {'account_ref':self.account_ref,'amount':self.amount.body()}

    @classmethod
    def from_body(cls, body):
        if not isinstance(body, dict) or set(body) != {'account_ref','amount'}:
            raise UnitError('POSTING_FORMAT_INVALID')
        return cls(body['account_ref'], Money.from_body(body['amount']))


def balanced_postings(postings):
    """Validate every asset separately; balance supplies no settlement authority."""
    if not isinstance(postings, (list, tuple)) or not 2 <= len(postings) <= 128:
        raise UnitError('POSTING_COUNT_INVALID')
    totals = {}; accounts = {}
    for posting in postings:
        if type(posting) is not Posting:
            raise UnitError('POSTING_VALUE_REQUIRED')
        key = (posting.amount.asset_ref, posting.amount.currency)
        totals[key] = totals.get(key, Fraction(0)) + posting.amount.fraction
        accounts.setdefault(key, set()).add(posting.account_ref)
    if any(total != 0 or len(accounts[key]) < 2 for key,total in totals.items()):
        raise UnitError('POSTINGS_UNBALANCED_OR_COUNTERACCOUNT_MISSING')
    return tuple(postings)
