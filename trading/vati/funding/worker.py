"""One bounded read worker per runtime; no trading or withdrawal interface.

Requests coalesce while the provider is slow. Only native journal windows advance
the cursor; an interrupted request is recovered from original history next time.
"""
from copy import deepcopy
import threading
from vati.core.ledger_pg import PostgresLedger,open_ledger
from vati.funding.native import NativeAccountMark
from vati.funding.runtime import capture_funding

class FundingIngestWorker:
    def __init__(self,ledger_path,reader_factory,*,ledger_name=None):
        self._path=ledger_path;self._factory=reader_factory;self._ledger_name=ledger_name
        self._condition=threading.Condition();self._pending=None;self._result=None;self._reader=None
        self._stopping=False;self._active=False
        self._thread=threading.Thread(target=self._run,name='vati-native-cash-reader',daemon=True)
        self._thread.start()

    def submit(self,account,now_ms):
        with self._condition:
            if self._stopping:raise RuntimeError('funding_collector_stopped')
            self._pending=(account,now_ms);self._condition.notify()
            result=deepcopy(self._result)
        if result is not None and result.get('scope_hash')==account.funding_mark.scope_hash:
            return result|{'collector_state':'QUEUED'}
        return {'state':'PENDING','reason':'NATIVE_HISTORY_READ_QUEUED','scope_hash':account.funding_mark.scope_hash,
            'native_mark':account.funding_mark.body(),'return_qualification':'NOT_ISSUED','execution_authority':False,
            'collector_state':'QUEUED'}

    def _run(self):
        ledger=None
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda:self._stopping or self._pending is not None)
                    if self._stopping:return
                    account,now=self._pending;self._pending=None;self._active=True
                try:
                    if ledger is None:
                        # A PostgreSQL connection can use native keyword conninfo,
                        # not only a URL. Preserve the actual originating engine
                        # and scope instead of guessing SQLite from its text.
                        ledger=PostgresLedger(self._path,ledger_name=self._ledger_name) if self._ledger_name is not None else open_ledger(self._path)
                    if self._reader is None:self._reader=self._factory()
                    result=capture_funding(ledger,self._reader,account,now_ms=now)
                except Exception:
                    # Original journal commits remain recoverable. Neither native
                    # error text nor credential-shaped provider notes are exposed.
                    result={'state':'UNAVAILABLE','reason':'NATIVE_FUNDING_COLLECTOR_UNAVAILABLE',
                        'scope_hash':account.funding_mark.scope_hash,'native_mark':account.funding_mark.body(),
                        'return_qualification':'NOT_ISSUED','execution_authority':False}
                with self._condition:
                    self._result=result;self._active=False;self._condition.notify_all()
        finally:
            try:
                if self._reader is not None:self._reader.close()
            finally:
                if ledger is not None:ledger.close()

    def close(self):
        with self._condition:
            self._stopping=True;self._pending=None;self._condition.notify_all()
        # A daemon blocked in provider I/O owns its separate read socket; the
        # trading runtime never waits for its network timeout during shutdown.
        self._thread.join(timeout=0.05)

    def wait_idle(self,timeout=5):
        with self._condition:
            return self._condition.wait_for(lambda:not self._active and self._pending is None,timeout=timeout)

def snapshot_funding(service,ledger,adapter,account,*,now_ms):
    from vati.funding.mt5_runtime import capture_cached_mt5
    cached=capture_cached_mt5(ledger,account,now_ms=now_ms)
    if cached is not None:return cached
    mark=getattr(account,'funding_mark',None)
    if not isinstance(mark,NativeAccountMark):
        return {'state':'UNSUPPORTED','reason':'NATIVE_CASH_HISTORY_NOT_PROVIDED','return_qualification':'NOT_ISSUED','execution_authority':False}
    if ledger.path==':memory:':
        return {'state':'UNAVAILABLE','reason':'DURABLE_FUNDING_JOURNAL_REQUIRED','return_qualification':'NOT_ISSUED','execution_authority':False}
    worker=getattr(service,'_funding_worker',None)
    if worker is None:
        worker=FundingIngestWorker(ledger.path,adapter.funding_reader,ledger_name=getattr(ledger,'name',None))
        service._funding_worker=worker
    return worker.submit(account,now_ms)

def stop_funding(service):
    worker=getattr(service,'_funding_worker',None)
    if worker is not None:worker.close();service._funding_worker=None
