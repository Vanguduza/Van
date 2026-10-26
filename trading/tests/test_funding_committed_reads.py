"""Actual writer rollback cannot manufacture committed native funding readiness."""
from contextlib import closing
import os
import uuid

import pytest

from test_native_balance_reconciliation import mark, snapshot, observe
from test_funding_risk_fence import native
from test_funding_owner_reports import profile
from vati.core import Ledger, EventKind, make_event
from vati.core.ledger import LedgerError
from vati.funding.reconciliation import period_report
from vati.funding.risk_fence import funding_risk_fence
from vati.funding.runtime import reported_funding


class RollbackFixture(Exception):
    pass


@pytest.fixture(params=['sqlite','postgres'])
def source(tmp_path,request):
    if request.param=='postgres':
        if os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1' or not os.environ.get('VATI_TEST_PG_DSN'):
            pytest.skip('requires actual isolated PostgreSQL committed-read fixture')
        from vati.core.ledger_pg import PostgresLedger
        ledger=PostgresLedger(os.environ['VATI_TEST_PG_DSN'],ledger_name='committed-read-'+uuid.uuid4().hex)
    else:ledger=Ledger(tmp_path/'committed-read.sqlite')
    with closing(ledger):
        snapshot(ledger,mark(1000));scope=observe(ledger)
        yield ledger,scope


def closing_snapshot(ledger):
    point=mark(3000,equity='110')
    event=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{
        'account_alias':point.account_alias,'equity':str(point.net_equity),'balance':str(point.balance),
        'currency':point.currency,'verified':True,'native_account_mark':point.body(),
        'funding_observation':{'state':'OBSERVED','reason':'FIXTURE_ORIGINAL_NATIVE_OBSERVATION',
            'scope_hash':point.scope_hash,'native_mark':point.body()}},event_time_ms=3000,
        received_time_ms=3010,correlation_id=point.account_alias)
    ledger.append(event);return event


def test_period_cannot_consume_a_closing_source_from_its_callers_writer(source):
    ledger,scope=source;before=ledger.head(),ledger.count()
    with pytest.raises(RollbackFixture):
        with ledger.atomic():
            closing=closing_snapshot(ledger)
            with pytest.raises(LedgerError,match='committed_source'):
                period_report(ledger,scope)
            raise RollbackFixture()
    assert (ledger.head(),ledger.count())==before
    assert not any(e.hash==closing.hash for e in ledger.iter(EventKind.ACCOUNT_SNAPSHOT))
    assert period_report(ledger,scope)['state']=='UNMEASURED'
    assert ledger.verify_chain()[0] and ledger.verify_incremental()[0]


def test_native_funding_prerequisite_holds_before_the_original_closing_fact_commits(source):
    ledger,scope=source;adapter,account=native(mark(3500,equity='110'))
    before=ledger.head(),ledger.count();requests=list(adapter.transport.requests)
    with pytest.raises(RollbackFixture):
        with ledger.atomic():
            closing_snapshot(ledger)
            readiness=funding_risk_fence(ledger,adapter,account,now_ms=7000)
            assert readiness.available is False
            assert readiness.reason.startswith('FUNDING_RISK_EVIDENCE_UNAVAILABLE:')
            raise RollbackFixture()
    assert (ledger.head(),ledger.count())==before and adapter.transport.requests==requests
    assert not funding_risk_fence(ledger,adapter,account,now_ms=7000).available


def test_owner_read_cannot_publish_uncommitted_funding_lineage(source):
    ledger,scope=source;before=ledger.head(),ledger.count()
    with pytest.raises(RollbackFixture):
        with ledger.atomic():
            closing=closing_snapshot(ledger)
            with pytest.raises(LedgerError,match='committed_source'):
                reported_funding(ledger,closing,profile())
            raise RollbackFixture()
    assert (ledger.head(),ledger.count())==before


def test_legitimate_committed_read_snapshot_preserves_native_readiness_and_owner_contract(source):
    ledger,scope=source;closing=closing_snapshot(ledger);adapter,account=native(mark(3500,equity='110'))
    before=ledger.head(),ledger.count();requests=list(adapter.transport.requests)
    with ledger.read_snapshot():
        period=period_report(ledger,scope)
        assert period['state']=='MEASURED' and period['closing_ref']==closing.hash
        assert funding_risk_fence(ledger,adapter,account,now_ms=7000).available is True
        assert reported_funding(ledger,closing,profile())['period']['closing_ref']==closing.hash
    assert (ledger.head(),ledger.count())==before and adapter.transport.requests==requests


def test_incremental_verification_does_not_misreport_corruption_after_owned_writer_rollback(source):
    ledger,scope=source;assert ledger.verify_incremental()[0]
    before=ledger.head(),ledger.count()
    with pytest.raises(RollbackFixture):
        with ledger.atomic():
            closing_snapshot(ledger)
            assert ledger.verify_incremental()[0]
            raise RollbackFixture()
    assert (ledger.head(),ledger.count())==before and ledger.verify_chain()[0]
    assert ledger.verify_incremental()[0]


@pytest.mark.parametrize('consumer',['risk','owner'])
def test_mt5_query_and_owner_snapshot_cannot_escape_the_callers_writer(source,tmp_path,consumer):
    from test_mt5_funding_contract import frame
    from test_mt5_funding_runtime import publish, profile as mt5_profile
    from vati.execution.base import AccountState
    from vati.execution.mt5_identity import Mt5Identity
    from vati.execution.mt5_pull import Mt5PullAdapter, BridgeQueue
    from vati.funding.mt5_runtime import capture_cached_mt5
    ledger,scope=source;native_frame=frame();queue=BridgeQueue(tmp_path/'mt5-source-read.sqlite')
    adapter=Mt5PullAdapter(queue,account_alias='native',clock=lambda:10000,
        identity=Mt5Identity('12345678','Broker-Demo','USD',True))
    account=AccountState('native',native_frame.net_equity,native_frame.balance,'USD',True,funding_mark=native_frame)
    before=ledger.head(),ledger.count()
    try:
        with pytest.raises(RollbackFixture):
            with ledger.atomic():
                observation=capture_cached_mt5(ledger,account,now_ms=10000)
                event=publish(ledger,account,observation)
                if consumer=='risk':
                    readiness=funding_risk_fence(ledger,adapter,account,now_ms=11000)
                    assert readiness.available is False
                    assert readiness.reason.startswith('FUNDING_RISK_EVIDENCE_UNAVAILABLE:')
                else:
                    with pytest.raises(LedgerError,match='committed_source'):
                        reported_funding(ledger,event,mt5_profile())
                raise RollbackFixture()
        assert (ledger.head(),ledger.count())==before
        assert queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0]==0
        assert ledger.verify_chain()[0] and ledger.verify_incremental()[0]
    finally:queue._conn.close()
