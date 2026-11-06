"""Actual coordinator construction and shared PostgreSQL lease arbitration.

Paper venue/source fixtures exercise runtime ownership, not native execution.
"""
from dataclasses import replace
import os
from urllib.parse import urlsplit,urlunsplit

import pytest

from test_postgres_ledger_isolation import pg_dsn
from test_single_session_lease import config
from vati.app.account_service import AccountCoordinatorService
from vati.app.account_lease import LeaseOutcome
from vati.risk.serde import contract_to_dict


@pytest.fixture
def coordinators(tmp_path,eurusd,pg_dsn):
    from psycopg.conninfo import conninfo_to_dict
    database=conninfo_to_dict(pg_dsn)['dbname']
    uri=urlunsplit(urlsplit(os.environ['VATI_TEST_PG_DSN'])._replace(path='/'+database))
    cfg=config(tmp_path,eurusd,ledger=uri);cfg.lake_root=str(tmp_path/'lake')
    cfg.instruments=[{'symbol':'GBPUSD','base':'GBP','quote':'USD',
        'contract':contract_to_dict(replace(eurusd,symbol='GBPUSD',base_currency='GBP'))}]
    clock={'now':1000};owned=[]
    try:
        for _ in range(2):owned.append(AccountCoordinatorService(cfg,clock=lambda:clock['now']).build())
        yield owned,clock
    finally:
        for service in reversed(owned):
            try:service.lease.release(now_ms=clock['now'])
            finally:
                service._lease_store.close();service._ledger.close()


def test_same_process_coordinator_peer_cannot_displace_its_live_owner(coordinators):
    (first,second),clock=coordinators
    assert first.lease.acquire(now_ms=clock['now']).outcome is LeaseOutcome.GRANTED
    epoch=first.lease.epoch
    assert second.lease.acquire(now_ms=clock['now']).outcome is LeaseOutcome.REFUSED_HELD_BY_OTHER
    assert first.router.lease_fence(epoch) is True
    assert second.router.lease_fence(None) is False
    assert first.lease.instance_id!=second.lease.instance_id


def test_same_process_peer_shutdown_cannot_release_another_coordinators_authority(coordinators):
    (first,second),clock=coordinators
    assert first.lease.acquire(now_ms=clock['now']).permits_orders
    epoch=first.lease.epoch
    second.lease.acquire(now_ms=clock['now']);second.lease.release(now_ms=clock['now'])
    assert first.router.lease_fence(epoch) is True
    with first.router.lease_submission_guard(epoch) as allowed:assert allowed is True


def test_expired_owner_stays_fenced_after_real_peer_takeover_and_late_shutdown(coordinators):
    (first,second),clock=coordinators
    assert first.lease.acquire(now_ms=clock['now']).permits_orders
    original=first.lease.epoch;clock['now']=first.lease.held.expires_at_ms+1
    assert second.lease.acquire(now_ms=clock['now']).permits_orders
    assert second.lease.epoch>original
    first.lease.release(now_ms=clock['now'])
    assert first.router.lease_fence(original) is False
    assert second.router.lease_fence(second.lease.epoch) is True
    with second.router.lease_submission_guard(second.lease.epoch) as allowed:assert allowed is True
