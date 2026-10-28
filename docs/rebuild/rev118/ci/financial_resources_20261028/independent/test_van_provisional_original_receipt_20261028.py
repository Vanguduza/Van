"""Independent historical receipt readback; genuine test owner/source owners."""
from conftest import eurusd,_register_owner_authority_key,_reap_ctrader_fixture_sockets
from test_provisional_resource_book import prepared


def test_later_requirement_list_cannot_rewrite_an_original_durable_hold(tmp_path,eurusd,monkeypatch):
    import vati.risk.provisional_resource_book as module
    sdk,clock,ledger,command,margin,current,authority,book,router=prepared(tmp_path,eurusd)
    try:
        original=book.reserve_entry(command,margin,current,authority);count=ledger.count()
        assert 'FEES' in original['missing_requirements']
        monkeypatch.setattr(module,'MISSING',[])
        replay=book.reserve_entry(command,margin,current,None)
        assert replay==original,'historical readback silently removed original unresolved obligations'
        assert ledger.count()==count and not sdk.sent
    finally:ledger.close()
