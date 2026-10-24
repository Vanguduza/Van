"""The registry's expected physical MT5 account, independent of its display alias."""
from dataclasses import dataclass

from vati.execution.base import VenueUnavailable


def login_id(value):
    if not ((type(value) is int and value > 0)
            or (isinstance(value, str) and value.isascii() and value.isdigit() and int(value) > 0)):
        raise VenueUnavailable('MT5 physical account identity has no valid login')
    if int(value) > 2**63-1:
        raise VenueUnavailable('MT5 physical account identity login exceeds native range')
    return str(int(value))


@dataclass(frozen=True)
class Mt5Identity:
    login: str
    server: str
    currency: str
    demo: bool

    def __post_init__(self):
        object.__setattr__(self, 'login', login_id(self.login))
        if (any(not isinstance(v, str) or not v.strip() or v != v.strip()
                for v in (self.server, self.currency)) or type(self.demo) is not bool):
            raise VenueUnavailable('MT5 physical account identity is incomplete')

    @classmethod
    def from_account(cls, account):
        return cls(account.login, account.server, account.currency, account.demo)

    def as_dict(self):
        return {'login': self.login, 'server': self.server, 'currency': self.currency, 'demo': self.demo}

    def validate(self, observed):
        if (not isinstance(observed, dict) or login_id(observed.get('login')) != self.login
            or observed.get('server') != self.server or observed.get('currency') != self.currency
            or type(observed.get('demo')) is not bool or observed['demo'] is not self.demo):
            raise VenueUnavailable('MT5 physical account identity differs from the registered binding')
