"""Expected provider account scope, independent of a registry/display alias.

This is a namespace for additional arbitration, never proof of a connected
account or an owner grant. Existing native identity checks remain authoritative.
"""
from dataclasses import dataclass
import hashlib
import json

from vati.accounts.registry import BrokerKind
from vati.execution.mt5_identity import Mt5Identity, login_id


def ctrader_host(account):
    from vati.execution.ctrader.transport import DEMO_HOST, LIVE_HOST
    return LIVE_HOST if (account.server or 'demo').lower() == 'live' or not account.demo else DEMO_HOST


@dataclass(frozen=True)
class ExpectedPhysicalScope:
    provider: str
    realm: str
    account_id: str

    def __post_init__(self):
        if (self.provider not in {'ctrader', 'mt5', 'deriv'}
                or any(not isinstance(v, str) or not v or v != v.strip()
                       for v in (self.realm, self.account_id))):
            raise ValueError('expected native account scope is incomplete')

    @property
    def lease_key(self):
        body = ['vati.expected-physical-account/1', self.provider, self.realm, self.account_id]
        encoded = json.dumps(body, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode()
        # A colon cannot collide with the registry's logical alias grammar.
        return 'native-account:v1:' + hashlib.sha256(encoded).hexdigest()

    @classmethod
    def from_account(cls, account):
        if type(account.demo) is not bool:
            raise ValueError('expected native environment must be a boolean')
        if account.broker == BrokerKind.CTRADER:
            return cls('ctrader', ctrader_host(account), login_id(account.login))
        if account.broker in {BrokerKind.MT5, BrokerKind.MT5_EA}:
            native = Mt5Identity.from_account(account)
            # EA and bridge transports can address the same underlying account.
            # Currency and display/demo labels do not split its server/login key.
            return cls('mt5', native.server, native.login)
        if account.broker == BrokerKind.DERIV:
            # Official WebSocket aliases and app/client IDs are not customer IDs.
            return cls('deriv', 'demo' if account.demo else 'live', account.login)
        raise ValueError('provider has no automated native account scope')
