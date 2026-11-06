"""Authentication and cached contracts belong to one native connection."""
from decimal import Decimal

import pytest

from test_ctrader_feed_contract import registry_fixture
from vati.execution.base import VenueUnavailable


def fixture():
    adapter, responses = registry_fixture()
    transport = adapter.transport
    transport.connected = True
    transport.connection_id = 1
    transport.connect = lambda: None
    calls = []
    responses.update({
        'ProtoOAApplicationAuthReq': ['ProtoOAApplicationAuthRes', {}],
        'ProtoOAAccountAuthReq': ['ProtoOAAccountAuthRes', {'ctidTraderAccountId': 123}],
    })
    def call(name, body):
        calls.append(name)
        return responses[name]
    transport.call = call
    return adapter, transport, responses, calls


def test_replacement_connection_reauthenticates_and_refreshes_contracts_before_use():
    adapter, transport, responses, calls = fixture()
    adapter._ensure_auth()
    old_revision = adapter.symbol('EURUSD').contract_revision
    adapter._last_spot[12] = (Decimal('1.1'), Decimal('1.2'))
    calls.clear()
    transport.connection_id = 2
    responses['ProtoOASymbolByIdReq'][1]['symbol'][0]['minVolume'] = 2000
    adapter._ensure_auth()
    assert calls[:2] == ['ProtoOAApplicationAuthReq', 'ProtoOAAccountAuthReq']
    assert adapter.symbol('EURUSD').min_volume == 2000
    assert adapter.symbol('EURUSD').contract_revision != old_revision
    assert adapter._last_spot == {}, 'original connection quote cache survived reconnect'


@pytest.mark.parametrize('invalid', ['application_type', 'account_type', 'other_account', 'bool_account'])
def test_wrong_native_authentication_response_never_authenticates_or_admits_cached_contracts(invalid):
    adapter, transport, responses, calls = fixture()
    adapter._load_symbols()
    if invalid == 'application_type':
        responses['ProtoOAApplicationAuthReq'][0] = 'ProtoHeartbeatEvent'
    elif invalid == 'account_type':
        responses['ProtoOAAccountAuthReq'][0] = 'ProtoOATraderRes'
    else:
        responses['ProtoOAAccountAuthReq'][1]['ctidTraderAccountId'] = True if invalid == 'bool_account' else 999
    with pytest.raises(VenueUnavailable):
        adapter._ensure_auth()
    assert not adapter._authed
    with pytest.raises(VenueUnavailable):
        adapter.symbol('EURUSD')


def test_connection_change_between_authentication_responses_refuses_the_mixed_handshake():
    adapter, transport, responses, calls = fixture()
    original = transport.call
    def changed(name, body):
        result = original(name, body)
        if name == 'ProtoOAAccountAuthReq':
            transport.connection_id = 2
        return result
    transport.call = changed
    with pytest.raises(VenueUnavailable):
        adapter._ensure_auth()
    assert not adapter._authed
    assert 'ProtoOASymbolsListReq' not in calls


def test_contract_refresh_across_connection_change_keeps_old_bytes_unavailable():
    adapter, transport, responses, calls = fixture()
    adapter._ensure_auth()
    previous = dict(adapter.symbols)
    original = transport.call
    def changed(name, body):
        result = original(name, body)
        if name == 'ProtoOASymbolByIdReq':
            transport.connection_id += 1
        return result
    transport.call = changed
    with pytest.raises(VenueUnavailable):
        adapter._load_symbols()
    assert adapter.symbols == previous
    with pytest.raises(VenueUnavailable):
        adapter.symbol('EURUSD')


def test_failed_reauthentication_fences_the_previous_contract_and_quote_cache():
    adapter, transport, responses, calls = fixture()
    adapter._ensure_auth()
    previous = dict(adapter.symbols)
    adapter._last_spot[12] = (Decimal('1.1'), Decimal('1.2'))
    transport.connection_id = 2
    responses['ProtoOAAccountAuthReq'][0] = 'ProtoHeartbeatEvent'
    with pytest.raises(VenueUnavailable):
        adapter._ensure_auth()
    assert adapter.symbols == previous and adapter._last_spot == {}
    assert not adapter._authed
    with pytest.raises(VenueUnavailable):
        adapter.symbol('EURUSD')


def test_direct_contract_lookup_refuses_a_replacement_before_reauthentication():
    adapter, transport, responses, calls = fixture()
    adapter._ensure_auth()
    transport.connection_id = 2
    with pytest.raises(VenueUnavailable):
        adapter.symbol('EURUSD')


def test_actual_protocol_reconnect_reauthenticates_the_new_peer_and_refreshes_native_contracts():
    from test_ctrader import FakeCtrader, make_adapter
    first, second = FakeCtrader(), FakeCtrader()
    adapter = make_adapter(first)
    adapter._ensure_auth()
    first_id = adapter.transport.connection_id
    adapter._last_spot[1] = (Decimal('1'), Decimal('2'))
    adapter.transport.close()
    adapter.transport._connector = second.connector
    adapter.transport.connect()  # A connected socket alone grants no cached auth.
    adapter._ensure_auth()
    assert adapter.transport.connection_id > first_id
    assert [name for name, _ in second.requests[:4]] == [
        'ProtoOAApplicationAuthReq', 'ProtoOAAccountAuthReq',
        'ProtoOASymbolsListReq', 'ProtoOASymbolByIdReq',
    ]
    assert adapter.symbol('EURUSD').symbol_id == 1 and adapter._last_spot == {}
    adapter.transport.close()
