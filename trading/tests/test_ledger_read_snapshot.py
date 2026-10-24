"""Owner read projections cannot reserve the financial writer or append effects."""
from concurrent.futures import ThreadPoolExecutor
import threading
import pytest
from vati.core.events import EventKind,make_event
from vati.core.ledger import Ledger,LedgerError

def event(n):return make_event(EventKind.SESSION,'read-snapshot-fixture',{'number':n},event_time_ms=n,received_time_ms=n,correlation_id='original-scope')

def test_read_snapshot_is_repeatable_while_an_independent_writer_can_commit(tmp_path):
    path=tmp_path/'facts.sqlite';reader=Ledger(path);reader.append(event(1));committed=threading.Event()
    def write():
        writer=Ledger(path)
        try:writer.append(event(2));committed.set();return writer.count()
        finally:writer.close()
    with ThreadPoolExecutor(max_workers=1) as executor:
        with reader.read_snapshot():
            assert reader.count()==1
            pending=executor.submit(write)
            assert committed.wait(2),'a read projection reserved the financial writer'
            assert pending.result(timeout=2)==2
            assert reader.count()==1 and reader.verify_incremental()[0]
        assert reader.count()==2 and reader.verify_incremental()[0]

def test_nested_read_preserves_the_snapshot_and_refuses_financial_writes(tmp_path):
    reader=Ledger(tmp_path/'facts.sqlite');reader.append(event(1))
    with reader.read_snapshot():
        with reader.read_snapshot():assert reader.count()==1
        with pytest.raises(LedgerError,match='read-only'):reader.append(event(2))
        assert reader.count()==1
    reader.append(event(3));assert reader.count()==2

def test_read_inside_existing_atomic_writer_never_ends_or_replaces_its_transaction(tmp_path):
    reader=Ledger(tmp_path/'facts.sqlite')
    with pytest.raises(RuntimeError,match='fixture-rollback'):
        with reader.atomic():
            reader.append(event(1))
            with reader.read_snapshot():assert reader.count()==1
            reader.append(event(2))
            raise RuntimeError('fixture-rollback')
    assert reader.count()==0
