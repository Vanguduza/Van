"""Actual runtime builders and shared SQL arbitration; no broker effect.

Injected paper transports retain fixture-only execution provenance. These cases
test the builders' lease scope, not native account connectivity or qualification.
"""
from dataclasses import replace
import os
from urllib.parse import urlsplit, urlunsplit

import pytest

from test_postgres_ledger_isolation import pg_dsn
from test_single_session_lease import config
from conftest import historical_mandate_dict
from vati.accounts import Account, AccountRegistry, CredentialRef
from vati.app.account_lease import LeaseOutcome
from vati.app.account_service import AccountCoordinatorService
from vati.app.service import SessionService
from vati.execution.paper import PaperAdapter
from vati.risk.serde import contract_to_dict


def build_fixture(path, contract, uri, kind, alias, login):
    path.mkdir()
    cfg = config(path, contract, ledger=uri)
    registry = AccountRegistry(cfg.registry_path)
    registry.remove(cfg.account_alias)
    registry.add(Account(alias=alias, broker='CTRADER', mode='DEMO_TRADER',
        currency='USD', login=login, server='demo',
        credential_ref=CredentialRef(env_var='SOURCE_FIXTURE_NOT_READ')))
    cfg.account_alias = alias
    cfg.mandate = historical_mandate_dict(venue='ctrader', mode='DEMO_TRADER',
        account_alias=alias, allowed_strategies=['FX-TREND-PULLBACK-01'])
    adapter = PaperAdapter(venue='ctrader', account_alias=alias)
    if kind == 'single':
        return SessionService(cfg, lambda now: [], clock=lambda: 1000, adapter=adapter).build()
    cfg.lake_root = str(path / 'lake')
    cfg.instruments = [{'symbol': 'GBPUSD', 'base': 'GBP', 'quote': 'USD',
        'contract': contract_to_dict(replace(contract, symbol='GBPUSD', base_currency='GBP'))}]
    return AccountCoordinatorService(cfg, clock=lambda: 1000, adapter=adapter).build()


@pytest.mark.parametrize('first_kind,second_kind', [
    ('single', 'single'), ('single', 'coordinator'),
    ('coordinator', 'single'), ('coordinator', 'coordinator')])
@pytest.mark.parametrize('peer_alias,peer_login,expected', [
    ('native_two', '123', LeaseOutcome.REFUSED_HELD_BY_OTHER),
    ('native_one', '456', LeaseOutcome.REFUSED_HELD_BY_OTHER),
    ('native_two', '456', LeaseOutcome.GRANTED)])
def test_actual_builders_preserve_alias_and_native_account_arbitration(
        tmp_path, eurusd, pg_dsn, first_kind, second_kind, peer_alias, peer_login, expected):
    from psycopg.conninfo import conninfo_to_dict
    database = conninfo_to_dict(pg_dsn)['dbname']
    uri = urlunsplit(urlsplit(os.environ['VATI_TEST_PG_DSN'])._replace(path='/' + database))
    services = []
    try:
        first = build_fixture(tmp_path / 'first', eurusd, uri, first_kind, 'native_one', '123')
        services.append(first)
        second = build_fixture(tmp_path / 'second', eurusd, uri, second_kind, peer_alias, peer_login)
        services.append(second)
        assert first.lease.acquire(now_ms=1000).outcome is LeaseOutcome.GRANTED
        original_epoch = first.lease.epoch
        assert second.lease.acquire(now_ms=1000).outcome is expected
        assert first.lease.fence(original_epoch, now_ms=1000)
        second.lease.release(now_ms=1000)
        assert first.lease.fence(original_epoch, now_ms=1000)
        with first.lease.submission_guard(original_epoch, now_ms=1000) as allowed:
            assert allowed is True
    finally:
        for service in reversed(services):
            try:
                service.lease.release(now_ms=1000)
            finally:
                service._lease_store.close()
                service._ledger.close()
