"""Expected identity and dual-scope arbitration, without native venue effects."""
from dataclasses import replace

import pytest

from vati.accounts import Account, CredentialRef
from vati.accounts.physical_scope import ExpectedPhysicalScope, ctrader_host
from vati.app.account_lease import AccountRuntimeLease, InMemoryLeaseStore, LeaseOutcome
from vati.app.physical_account_lease import PhysicalAccountRuntimeLease, build_runtime_lease
from vati.execution.ctrader import DEMO_HOST, LIVE_HOST


def account(broker='CTRADER', **kw):
    return replace(Account(alias='native_one', broker=broker, mode='DEMO_TRADER', currency='USD',
                           server='demo', login='123', credential_ref=CredentialRef(env_var='FIXTURE_REF')), **kw)


@pytest.mark.parametrize('broker', ['CTRADER', 'MT5', 'MT5_EA', 'DERIV'])
def test_profile_and_credential_labels_do_not_split_one_account(broker):
    original = account(broker)
    profile = replace(original, alias='native_two', label='Other view', notes='fixture',
                      venue='other_route', mode='OBSERVE', currency='EUR',
                      credential_ref=CredentialRef(env_var='DIFFERENT_FIXTURE_REF'))
    assert ExpectedPhysicalScope.from_account(original) == ExpectedPhysicalScope.from_account(profile)


@pytest.mark.parametrize('server,demo,expected', [
    ('', True, DEMO_HOST), ('demo', True, DEMO_HOST), ('DeMo', True, DEMO_HOST),
    ('LIVE', True, LIVE_HOST), ('demo', False, LIVE_HOST), ('', False, LIVE_HOST)])
def test_ctrader_scope_uses_the_actual_factory_host(server, demo, expected):
    value = account(server=server, demo=demo)
    assert ctrader_host(value) == expected
    assert ExpectedPhysicalScope.from_account(value).realm == expected


@pytest.mark.parametrize('broker', ['CTRADER', 'MT5', 'MT5_EA'])
def test_native_numeric_login_normalization_keeps_one_scope(broker):
    assert ExpectedPhysicalScope.from_account(account(broker, login='000123')) == ExpectedPhysicalScope.from_account(account(broker))


@pytest.mark.parametrize('broker', ['CTRADER', 'MT5', 'MT5_EA'])
@pytest.mark.parametrize('login', [True, 0, -1, str(2**63), '1.0', ''])
def test_invalid_native_numeric_id_cannot_become_an_arbitration_scope(broker, login):
    with pytest.raises((ValueError, RuntimeError)):
        ExpectedPhysicalScope.from_account(account(broker, login=login))


def test_mt5_bridge_and_ea_share_exact_server_login_scope():
    bridge = account('MT5', server='Broker-Server')
    assert ExpectedPhysicalScope.from_account(bridge) == ExpectedPhysicalScope.from_account(replace(bridge, broker='MT5_EA'))
    assert ExpectedPhysicalScope.from_account(bridge) != ExpectedPhysicalScope.from_account(replace(bridge, server='broker-server'))


def test_deriv_client_app_and_endpoint_alias_do_not_split_customer_identity():
    first = account('DERIV', login='VRTC123', server='1089', bridge_url='wss://ws.derivws.com/websockets/v3')
    second = replace(first, server='9999', bridge_url='wss://ws.binaryws.com/websockets/v3')
    assert ExpectedPhysicalScope.from_account(first) == ExpectedPhysicalScope.from_account(second)
    assert ExpectedPhysicalScope.from_account(first) != ExpectedPhysicalScope.from_account(replace(first, demo=False))


@pytest.mark.parametrize('login', ['', ' ', None, True])
def test_deriv_missing_native_login_cannot_become_a_sending_scope(login):
    with pytest.raises(ValueError):
        ExpectedPhysicalScope.from_account(account('DERIV', login=login))


def test_scope_encoding_preserves_structural_boundaries_and_alias_namespace():
    first = ExpectedPhysicalScope('mt5', 'server|part', 'account')
    second = ExpectedPhysicalScope('mt5', 'server', 'part|account')
    assert first.lease_key != second.lease_key
    assert first.lease_key.startswith('native-account:v1:')
    assert ':' in first.lease_key and len(first.lease_key) < 128


@pytest.mark.parametrize('broker,mode', [('CTRADER', 'OBSERVE'), ('DERIV', 'ADVISOR'),
    ('MT5', 'SHADOW_TRADER'), ('PAPER', 'DEMO_TRADER'), ('ZSE_OWNER_TICKET', 'DEMO_TRADER')])
def test_non_sending_and_owner_ticket_paths_keep_original_lease_contract(broker, mode):
    value = build_runtime_lease(InMemoryLeaseStore(), account=account(broker, login=''),
                                mode=mode, instance_id='fixture')
    assert type(value) is AccountRuntimeLease
    assert value.account_alias == 'native_one'


def lease(store, alias='native_one', instance='first', scope=None, ttl=1000):
    return PhysicalAccountRuntimeLease(store, physical_scope=scope or ExpectedPhysicalScope.from_account(account()),
        account_alias=alias, instance_id=instance, ttl_ms=ttl)


def test_physical_takeover_invalidates_old_alias_and_late_release_cannot_displace_peer():
    store = InMemoryLeaseStore(); first = lease(store); peer = lease(store, 'native_two', 'peer')
    assert first.acquire(now_ms=0).permits_orders
    original = first.epoch
    assert peer.acquire(now_ms=1001).permits_orders
    assert first.fence(original, now_ms=1002, min_validity_ms=0) is False
    first.release(now_ms=1002)
    assert peer.fence(peer.epoch, now_ms=1002, min_validity_ms=0)
    assert peer.held.account_alias == 'native_two'


def test_failed_alias_acquisition_releases_only_its_own_additional_scope():
    store = InMemoryLeaseStore()
    original = lease(store); other_scope = ExpectedPhysicalScope('ctrader', DEMO_HOST, '456')
    peer = lease(store, instance='peer', scope=other_scope)
    assert original.acquire(now_ms=0).permits_orders
    assert peer.acquire(now_ms=1).outcome is LeaseOutcome.REFUSED_HELD_BY_OTHER
    assert original.fence(original.epoch, now_ms=2, min_validity_ms=0)
    independent = lease(store, 'native_two', 'third', other_scope)
    assert independent.acquire(now_ms=2).permits_orders


def test_failed_physical_renewal_drops_alias_instead_of_retaining_partial_permission():
    store = InMemoryLeaseStore(); original = lease(store); peer = lease(store, 'native_two', 'peer')
    assert original.acquire(now_ms=0).permits_orders
    old_epoch = original.epoch
    assert peer.acquire(now_ms=1001).permits_orders
    assert original.renew(now_ms=1002).outcome is LeaseOutcome.REFUSED_HELD_BY_OTHER
    assert original.held is None and not original.fence(old_epoch, now_ms=1002, min_validity_ms=0)
    assert peer.fence(peer.epoch, now_ms=1002, min_validity_ms=0)


def test_reacquisition_keeps_original_alias_epoch_monotonic():
    store = InMemoryLeaseStore(); original = lease(store)
    assert original.acquire(now_ms=0).permits_orders
    old_epoch = original.epoch
    original.release(now_ms=1)
    assert original.renew(now_ms=2).permits_orders
    assert original.epoch > old_epoch
    assert not original.fence(old_epoch, now_ms=3, min_validity_ms=0)
    assert original.fence(original.epoch, now_ms=3, min_validity_ms=0)


def test_unreachable_store_is_explicitly_not_a_successful_arbitration():
    store = InMemoryLeaseStore(); original = lease(store)
    assert original.acquire(now_ms=0).permits_orders
    store.reachable = False
    assert original.renew(now_ms=1).outcome is LeaseOutcome.STORE_UNREACHABLE
    assert original.held is None and not original.fence(None, now_ms=1)


def test_original_guarded_exception_and_nested_fences_keep_their_owner():
    store = InMemoryLeaseStore(); original = lease(store)
    assert original.acquire(now_ms=0).permits_orders
    epoch = original.epoch; failure = RuntimeError('original fixture body')
    with pytest.raises(RuntimeError) as error:
        with original.submission_guard(epoch, now_ms=1) as allowed:
            assert allowed
            assert original.fence(epoch, now_ms=1, min_validity_ms=0)
            with original.submission_guard(epoch, now_ms=1) as nested:
                assert nested
            raise failure
    assert error.value is failure
    assert original.fence(epoch, now_ms=2, min_validity_ms=0)


def test_intervening_physical_owner_cannot_renew_the_old_alias_epoch():
    store = InMemoryLeaseStore(); original = lease(store); peer = lease(store, 'native_two', 'peer')
    assert original.acquire(now_ms=0).permits_orders
    old_epoch = original.epoch
    assert peer.acquire(now_ms=1001).permits_orders
    peer.release(now_ms=1002)
    assert original.renew(now_ms=1003).outcome is LeaseOutcome.REFUSED_HELD_BY_OTHER
    assert original.held is None
    assert original.renew(now_ms=1004).permits_orders
    assert original.epoch > old_epoch
    assert not original.fence(old_epoch, now_ms=1004, min_validity_ms=0)


def test_live_alias_alone_cannot_pass_the_final_physical_guard():
    store = InMemoryLeaseStore(); original = lease(store); peer = lease(store, 'native_two', 'peer')
    assert original.acquire(now_ms=0).permits_orders
    epoch = original.epoch
    row = store.read('native_one')
    assert store.write_if(row, replace(row, expires_at_ms=10000))
    assert peer.acquire(now_ms=1001).permits_orders
    with original.submission_guard(epoch, now_ms=1002) as allowed:
        assert allowed is False
    assert original.held is None
    assert peer.fence(peer.epoch, now_ms=1002, min_validity_ms=0)


def test_failed_alias_renewal_releases_its_native_scope_without_releasing_peer():
    store = InMemoryLeaseStore(); original = lease(store)
    other_scope = ExpectedPhysicalScope('ctrader', DEMO_HOST, '456')
    peer = lease(store, instance='peer', scope=other_scope)
    assert original.acquire(now_ms=0).permits_orders
    native_row = store.read(original.physical_scope.lease_key)
    assert store.write_if(native_row, replace(native_row, expires_at_ms=10000))
    assert peer.acquire(now_ms=1001).permits_orders
    assert original.renew(now_ms=1002).outcome is LeaseOutcome.REFUSED_HELD_BY_OTHER
    assert original.held is None
    assert peer.fence(peer.epoch, now_ms=1002, min_validity_ms=0)
    independent = lease(store, alias='native_three', instance='third')
    assert independent.acquire(now_ms=1003).permits_orders
