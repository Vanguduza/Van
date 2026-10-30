"""Actual framed inactive history -> original archive -> immutable Parquet."""
from test_native_read_identity import identity, HistoryPeer, make_adapter, NOW
from vati.market_data.native_archive import NativeMarketArchive
from vati.market_data.native_collector import NativeMarketCollector
from vati.market_data.native_windows import NativeBarWindowReader
from vati.research.bar_partitions import NativeBarPartitionService
from vati_forecast_worker.source_partitions import verify_native_bar_partition


def test_inactive_native_source_identity_survives_parquet_and_independent_original_readback(tmp_path):
    expected=identity(wire=True);peer=HistoryPeer();parent=make_adapter(peer);parent.clock=lambda:NOW
    book=NativeMarketArchive(tmp_path/'native',clock=lambda:NOW+1000)
    try:
        receipt=NativeMarketCollector(book,parent.market_reader).collect('inactive-parquet',expected,
            timeframe='M1',from_ms=120000,to_ms=300000)
        reader=NativeBarWindowReader(book)
        window=reader.capture(expected.native_scope,'M1',through_revision=1,boundary_ref=receipt['record_ref'],
            as_of_ms=NOW+1000,from_ms=120000,to_ms=300000)
        service=NativeBarPartitionService(reader,tmp_path/'derived')
        result=service.publish(window,expected_scope=expected.native_scope)
        original=service.read(result['publication_ref'],expected_scope=expected.native_scope)
        assert verify_native_bar_partition(original.parquet,original.window())['row_count']==3
        capture=original.window()['source_records'][0]['contract']
        assert capture['schema']=='vati.ctrader-read-identity-capture/1'
        assert capture['source_kind']=='ARCHIVED' and capture['qualified_for_execution'] is False
        assert capture['lifecycle_effective_at_ms'] is None
        assert result['qualified_for_research'] is False and result['research_use_state']=='UNKNOWN_REFUSED'
    finally:peer.close()
