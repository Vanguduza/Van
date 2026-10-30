"""One scoped source capture on an independent reader; no activation or orders."""
from vati.core.canonical import canonical_hash
from vati.core.file_lock import exclusive_state_lock
from vati.execution.ctrader.contracts import NativeSymbolContract
from vati.execution.ctrader.read_identity import NativeReadIdentity
from vati.execution.ctrader.feed import MAX_TIMESTAMP, PERIOD, native_integer
from vati.market_data.native_archive import NativeArchiveError, REQUEST_ID


class NativeMarketCollector:
    def __init__(self, archive, reader_factory):
        self.archive, self.reader_factory = archive, reader_factory

    def collect(self, request_id, expected_contract, *, timeframe, from_ms, to_ms):
        if (not isinstance(request_id,str) or not REQUEST_ID.fullmatch(request_id)
                or not isinstance(expected_contract,(NativeSymbolContract,NativeReadIdentity))):
            raise NativeArchiveError('native market collection identity or contract invalid')
        scope=expected_contract.native_scope
        if not isinstance(timeframe,str) or timeframe not in PERIOD:
            raise NativeArchiveError('native market collection timeframe invalid')
        native_integer(from_ms,maximum=MAX_TIMESTAMP)
        native_integer(to_ms,minimum=from_ms,maximum=MAX_TIMESTAMP)
        part=self.archive._partition(scope,timeframe,create=True)
        # This lock serializes only the same original collection. Native I/O
        # holds neither the archive head writer nor the financial journal lock.
        with exclusive_state_lock(part/('request-'+canonical_hash(request_id))):
            original=self.archive.lookup(scope,timeframe,request_id)
            if original is not None:
                snapshot=self.archive.snapshot(scope,timeframe,revision=original['revision'])
                captured=snapshot['observation']
                if (original['contract_revision']!=expected_contract.revision
                        or captured['from_ms']!=from_ms or captured['to_ms']!=to_ms):
                    raise NativeArchiveError('native market collection identity conflicts with original window/contract')
                if original['index_state']!='CONSISTENT':
                    return self.archive.reconcile(scope,timeframe,request_id)
                return original
            reader=self.reader_factory()
            try:
                contract,observation=reader.read_window(expected_contract,timeframe=timeframe,from_ms=from_ms,to_ms=to_ms)
            finally:
                reader.close()
            if (contract.native_scope!=scope or contract.revision!=expected_contract.revision
                    or observation.from_ms!=from_ms or observation.to_ms!=to_ms
                    or observation.timeframe!=timeframe):
                raise NativeArchiveError('native market collection result differs from original request')
            return self.archive.record(request_id,contract,observation)
