"""Bounded original ledger primitives; PostgreSQL uses a disposable database."""
from contextlib import closing
import hashlib

import pytest

from test_postgres_ledger_isolation import pg_dsn
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.core.ledger import GENESIS, Ledger, LedgerError


def event(number):
    return make_event(EventKind.SESSION, 'page-fixture', {'observation': number},
        event_time_ms=number, received_time_ms=number, correlation_id='page-fixture')


@pytest.fixture(params=['sqlite', 'postgres'])
def stores(request, tmp_path):
    if request.param == 'sqlite':
        path=tmp_path/'ledger.sqlite'
        with closing(Ledger(path)) as reader, closing(Ledger(path)) as writer:
            yield reader,writer,None
    else:
        from vati.core.ledger_pg import PostgresLedger
        dsn=request.getfixturevalue('pg_dsn')
        with closing(PostgresLedger(dsn,ledger_name='pages')) as reader, \
             closing(PostgresLedger(dsn,ledger_name='pages')) as writer, \
             closing(PostgresLedger(dsn,ledger_name='foreign')) as other:
            yield reader,writer,other


def test_pages_match_original_hash_chain_and_fixed_watermark(stores):
    reader,writer,_=stores
    for n in range(1,5):writer.append(event(n))
    full=reader.read_page(0,256);assert len(full)==4
    previous=GENESIS
    for seq,item,prev,chain in full:
        assert item.hash==canonical_hash(item.body()) and prev==previous
        assert chain==hashlib.sha256((previous+item.hash).encode()).hexdigest()
        assert reader.event_at(seq)==(seq,item,prev,chain)
        previous=chain
    watermark=full[-1][0]
    first=reader.read_page(0,2,through_seq=watermark)
    writer.append(event(5))
    second=reader.read_page(first[-1][0],2,through_seq=watermark)
    assert first+second==full and reader.read_page(second[-1][0],2,through_seq=watermark)==[]
    assert reader.read_page(watermark,1)[0][1].hash==event(5).hash
    assert reader.read_page(watermark,1,through_seq=watermark)==[]
    assert reader.event_at(watermark+10000) is None
    assert reader.count()==5 and reader.verify_chain()==(True,5)


@pytest.mark.parametrize('after,limit,through',[
    (True,1,None),(-1,1,None),(1.0,1,None),(0,True,None),(0,0,None),(0,257,None),
    (0,1,True),(0,1,-1),(0,1,1.0)])
def test_invalid_page_boundaries_rejected_without_writes(stores,after,limit,through):
    reader,writer,_=stores;writer.append(event(1));head=reader.head()
    with pytest.raises((ValueError,TypeError)):reader.read_page(after,limit,through_seq=through)
    assert reader.count()==1 and reader.head()==head


@pytest.mark.parametrize('seq',[True,False,0,-1,1.0,'1',None])
def test_invalid_exact_ordinal_rejected(stores,seq):
    reader,_,_=stores
    with pytest.raises((ValueError,TypeError)):reader.event_at(seq)
    assert reader.count()==0


def test_read_page_respects_committed_snapshot_and_does_not_write(stores):
    reader,writer,_=stores;writer.append(event(1));original_head=reader.head()
    with reader.read_snapshot():
        before=reader.read_page(0,256);assert len(before)==1
        writer.append(event(2))
        assert reader.read_page(0,256)==before
        assert reader.event_at(before[0][0])==before[0]
        with pytest.raises(LedgerError):reader.append(event(3))
    assert original_head!=reader.head()
    assert [row[1].hash for row in reader.read_page(0,256)]==[event(1).hash,event(2).hash]
    assert reader.count()==2


def test_postgres_logical_gaps_and_foreign_ordinals_are_isolated(pg_dsn):
    from vati.core.ledger_pg import PostgresLedger
    with closing(PostgresLedger(pg_dsn,ledger_name='page-a')) as a, \
         closing(PostgresLedger(pg_dsn,ledger_name='page-b')) as b:
        a.append(event(1));b.append(event(2));a.append(event(3))
        own=a.read_page(0,256);foreign=b.read_page(0,256)
        assert len(own)==2 and len(foreign)==1
        assert own[0][0]<foreign[0][0]<own[1][0]
        assert a.event_at(foreign[0][0]) is None and b.event_at(own[0][0]) is None
        assert a.read_page(own[0][0],1)==[own[1]]
        assert a.read_page(own[0][0],256,through_seq=foreign[0][0])==[]
        assert own[1][2]==own[0][3] and a.verify_chain()==(True,2)


def test_sqlite_page_limit_is_applied_in_sql(tmp_path):
    with closing(Ledger(tmp_path/'limit.sqlite')) as ledger:
        for n in range(1,5):ledger.append(event(n))
        statements=[];ledger._conn.set_trace_callback(statements.append)
        try:rows=ledger.read_page(0,2)
        finally:ledger._conn.set_trace_callback(None)
        assert len(rows)==2
        selects=[statement for statement in statements if statement.lstrip().upper().startswith('SELECT')]
        assert len(selects)==1 and 'LIMIT' in selects[0].upper()
