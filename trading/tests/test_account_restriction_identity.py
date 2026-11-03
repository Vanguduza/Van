"""Controlled in-memory observations; no provider or credential-file access."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from commander.account_restriction_identity import expected_identity_scope, observe_readonly_identity
from vati.accounts import Account
from vati.execution.mt5_identity import Mt5Identity
from vati.execution.mt5_pull import BridgeQueue, Mt5PullAdapter
from vati.execution.mt5_bridge import Mt5BridgeClient, Mt5BridgeAdapter
from test_mt5_funding_contract import account as native_mt5
from test_deriv_native_identity import Socket, native
from test_ctrader import FakeCtrader, make_adapter


class Registry:
    def credentials(self, alias):
        return {'DERIV_API_TOKEN': 'in-memory-fixture'}


def settings(connector=None):
    return SimpleNamespace(deriv_connector=connector, ctrader_transport_factory=None)


def test_paper_factory_current_and_closed():
    account = Account(alias='paper', broker='PAPER', mode='OBSERVE', currency='USD')
    owner = observe_readonly_identity(account, Registry(), settings(), clock_ms=lambda: 10000)
    assert owner.facts['source_kind'] == 'INTERNAL_PAPER_SIMULATION'
    assert owner.require_current()['identity_scope_ref'] == owner.facts['identity_scope_ref']
    assert owner.facts['execution_authority'] is False
    copied = owner.facts
    copied['source_received_at_ms'] = -1
    copied['execution_authority'] = True
    assert owner.require_current()['execution_authority'] is False
    assert owner.facts['source_received_at_ms'] == 10000
    owner.close()
    owner.close()
    with pytest.raises(HTTPException):
        owner.require_current()


def test_ea_native_queue_identity_without_trade_permission(monkeypatch):
    account = Account(alias='native', broker='MT5_EA', mode='OBSERVE', currency='USD',
                      login='12345678', server='Broker-Demo')
    queue = BridgeQueue()
    frame = native_mt5(trade_allowed=False, hedging=True)
    queue.set_state('native', frame, [], now_ms=10000, nonce='controlled-poll')
    adapter = Mt5PullAdapter(queue, account_alias='native', clock=lambda: 10000,
                             identity=Mt5Identity.from_account(account))
    monkeypatch.setattr('vati.app.service.build_adapter', lambda *args, **kwargs: adapter)
    owner = observe_readonly_identity(account, Registry(), settings(), clock_ms=lambda: 10000)
    assert owner.facts['source_kind'] == 'MT5_SIGNED_EA_POLL'
    assert adapter.sync_account().verified is False
    assert owner.require_current()['identity_scope_ref'] == owner.facts['identity_scope_ref']
    queue.set_state('native', {**frame, 'login': 87654321}, [], now_ms=10000, nonce='changed-poll')
    with pytest.raises(HTTPException) as failure:
        owner.require_current()
    assert failure.value.status_code == 409
    owner.close()


def test_ea_same_identity_new_nonce_rejects_old_observation(monkeypatch):
    account = Account(alias='native', broker='MT5_EA', mode='OBSERVE', currency='USD',
                      login='12345678', server='Broker-Demo')
    queue = BridgeQueue()
    frame = native_mt5(trade_allowed=False, hedging=True)
    queue.set_state('native', frame, [], now_ms=10000, nonce='first')
    adapter = Mt5PullAdapter(queue, account_alias='native', clock=lambda: 10000,
                             identity=Mt5Identity.from_account(account))
    monkeypatch.setattr('vati.app.service.build_adapter', lambda *args, **kwargs: adapter)
    owner = observe_readonly_identity(account, Registry(), settings(), clock_ms=lambda: 10000)
    try:
        queue.set_state('native', frame, [], now_ms=10000, nonce='second')
        with pytest.raises(HTTPException) as failure:
            owner.require_current()
        assert failure.value.detail['code'] == 'RESTRICTION_NATIVE_IDENTITY_CHANGED'
    finally:
        owner.close()


def test_ea_expiry_is_rechecked_after_actual_queue_read(monkeypatch):
    account = Account(alias='native', broker='MT5_EA', mode='OBSERVE', currency='USD',
                      login='12345678', server='Broker-Demo')
    queue = BridgeQueue()
    queue.set_state('native', native_mt5(trade_allowed=False, hedging=True), [], now_ms=10000, nonce='first')
    adapter = Mt5PullAdapter(queue, account_alias='native', clock=lambda: 10000,
                             identity=Mt5Identity.from_account(account))
    monkeypatch.setattr('vati.app.service.build_adapter', lambda *args, **kwargs: adapter)
    now = [10000]
    owner = observe_readonly_identity(account, Registry(), settings(), clock_ms=lambda: now[0])
    original_state = queue.state
    def delayed_state(alias):
        row = original_state(alias)
        now[0] = 40001
        return row
    monkeypatch.setattr(queue, 'state', delayed_state)
    try:
        with pytest.raises(HTTPException) as failure:
            owner.require_current()
        assert failure.value.detail['code'] == 'RESTRICTION_NATIVE_IDENTITY_STALE'
    finally:
        owner.close()


def test_deriv_native_authorize_read_only_profile_and_changed_identity():
    profile = native(scopes=['read'])
    sockets = []
    def connector(_url):
        result = Socket(profile)
        sockets.append(result)
        return result
    account = Account(alias='bound_demo', broker='DERIV', mode='OBSERVE', currency='USD',
                      login='VRTC900', server='1089')
    owner = observe_readonly_identity(account, Registry(), settings(connector), clock_ms=lambda: 10000)
    assert owner.facts['source_kind'] == 'DERIV_NATIVE_AUTHORIZE_READ'
    assert 'in-memory-fixture' not in str(owner.facts)
    before = len(sockets[0].requests)
    assert owner.require_current()['identity_scope_ref'] == owner.facts['identity_scope_ref']
    assert len(sockets[0].requests) == before
    owner._adapter.transport.authorized_profile['loginid'] = 'VRTC999'
    with pytest.raises(HTTPException):
        owner.require_current()
    profile['loginid'] = 'VRTC999'
    with pytest.raises(HTTPException):
        owner.refresh()
    assert all(set(request) <= {'req_id', 'authorize'} for sock in sockets for request in sock.requests)
    owner.close()


def test_windows_bridge_client_nonce_binding_without_network(monkeypatch):
    account = Account(alias='native', broker='MT5', mode='OBSERVE', currency='USD',
                      login='12345678', server='Broker-Demo')
    identity = Mt5Identity.from_account(account)
    requests = []
    def transport(request):
        requests.append(request)
        return {'nonce': request['nonce'], 'worker_time_ms': 10000,
                'identity_binding': identity.as_dict(),
                'account': native_mt5(verified=False, hedging=True)}
    client = Mt5BridgeClient(signing_key=b'fixture-only', transport=transport)
    adapter = Mt5BridgeAdapter(client, account_alias='native', identity=identity, clock=lambda: 10000)
    monkeypatch.setattr('vati.app.service.build_adapter', lambda *args, **kwargs: adapter)
    owner = observe_readonly_identity(account, Registry(), settings(), clock_ms=lambda: 10000)
    assert owner.require_current()['source_kind'] == 'MT5_SIGNED_MTLS_READ'
    assert len(requests) == 1
    adapter.sync_account()
    with pytest.raises(HTTPException):
        owner.require_current()
    owner.refresh()
    assert owner.require_current()['source_kind'] == 'MT5_SIGNED_MTLS_READ'
    owner.close()


def test_ctrader_actual_connection_scope_and_close(monkeypatch):
    fake = FakeCtrader()
    adapter = make_adapter(fake)
    monkeypatch.setattr('vati.app.service.build_adapter', lambda *args, **kwargs: adapter)
    account = Account(alias='ct_demo', broker='CTRADER', mode='OBSERVE', currency='USD', login='12345')
    owner = None
    try:
        owner = observe_readonly_identity(account, Registry(), settings(), clock_ms=lambda: 1_700_000_000_000)
        assert owner.facts['source_kind'] == 'CTRADER_AUTHENTICATED_NATIVE_ACCOUNT_READ'
        assert owner.require_current()['identity_scope_ref'] == owner.facts['identity_scope_ref']
        adapter.transport.host = 'live.ctraderapi.com'
        with pytest.raises(HTTPException):
            owner.require_current()
    finally:
        if owner is not None:
            owner.close()
        else:
            adapter.transport.close()
        fake.close()


def test_unknown_or_invalid_scope_holds():
    with pytest.raises(HTTPException):
        expected_identity_scope(Account(alias='bad', broker='ZSE_OWNER_TICKET', mode='OBSERVE', currency='USD'))
    with pytest.raises(HTTPException):
        expected_identity_scope(Account(alias='bad', broker='MT5_EA', mode='OBSERVE', currency='USD'))
