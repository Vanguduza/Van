"""LAC-230: exact original connection withdrawal and recovery (SOURCE fixtures)."""
import pytest

from test_google_owner_revoke_and_scrub import _settings, client

SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'


@pytest.mark.asyncio
async def test_lost_revoke_reply_retry_cannot_withdraw_reconnected_generation(client):
    ac, app = client
    await app.state.google.store_refresh_token('owner', 'SOURCE-original', [SCOPE])
    first = await ac.post('/v1/google/owner-revoke')
    assert first.status_code == 200
    assert first.json()['connected'] is False
    # Legitimate explicit host reconnect, including reuse of the same logical owner ID.
    await app.state.google.store_refresh_token('owner', 'SOURCE-replacement', [SCOPE])
    assert (await ac.get('/v1/google/status')).json()['connected'] is True
    # Transport retry of the lost first reply must not select this new connection.
    retry = await ac.post('/v1/google/owner-revoke')
    assert retry.status_code in (200, 409)
    assert (await ac.get('/v1/google/status')).json()['connected'] is True

@pytest.mark.asyncio
async def test_explicit_connect_is_new_generation_even_with_same_token_bytes(client):
    _, app = client
    google = app.state.google
    await google.store_refresh_token('owner', 'SOURCE-same-token', [SCOPE])
    first = await google.connection_detail()
    await google.store_refresh_token('owner', 'SOURCE-same-token', [SCOPE])
    second = await google.connection_detail()
    assert first['connection_generation'] != second['connection_generation']
    assert first['source_revision'] != second['source_revision']
    assert 'SOURCE-same-token' not in str(second)


@pytest.mark.asyncio
async def test_routine_token_refresh_preserves_logical_connection(client):
    _, app = client
    google = app.state.google
    class OAuth:
        async def access_token(self, refresh):
            assert refresh == 'SOURCE-refresh'
            return 'SOURCE-access'
    class Transport:
        requires_access_token = True
    google.oauth = OAuth()
    google.transport = Transport()
    await google.store_refresh_token('owner', 'SOURCE-refresh', [SCOPE])
    before = await google.connection_detail()
    assert await google._api_token('owner') == 'SOURCE-access'
    assert await google.connection_detail() == before


@pytest.mark.asyncio
async def test_withdrawal_readiness_failure_rolls_back_credential_and_generation(client):
    _, app = client
    google = app.state.google
    await google.store_refresh_token('owner', 'SOURCE-before', [SCOPE])
    before = await google.connection_detail()
    async with app.state.store.connection() as db:
        await db.execute("CREATE TRIGGER source_readiness_failure BEFORE UPDATE ON google_capability_connections BEGIN SELECT RAISE(ABORT,'SOURCE-interrupted'); END")
        await db.execute("INSERT INTO google_capability_connections(capability_id,owner_id,credential_plane,state,metadata_json,updated_at_unix) VALUES('SOURCE-workspace','owner_google_account','workspace_oauth','READY','{}',1)")
        await db.commit()
    with pytest.raises(Exception, match='SOURCE-interrupted'):
        await google.revoke()
    assert await google.connection_detail() == before
    assert await google._refresh_token('owner') == 'SOURCE-before'


@pytest.mark.asyncio
async def test_selected_withdrawal_original_receipt_survives_reconnect_and_restart(client):
    ac, app = client
    from van_gateway.google.service import GoogleService
    row = await app.state.store.fetchone('SELECT device_id FROM devices')
    device = row['device_id']
    google = app.state.google
    await google.store_refresh_token('owner', 'SOURCE-original', [SCOPE])
    selected = await google.withdrawal_detail(device_id=device)
    request = selected['withdrawal_request']
    receipt = await google.withdraw_selected(request, device_id=device)
    assert receipt['state'] == 'APPLIED' and receipt['changed'] is True
    assert receipt['provider_token_revoked'] is False
    await google.store_refresh_token('owner', 'SOURCE-replacement', [SCOPE])
    replacement = await google.connection_detail()
    # Reopen both owner and store. No in-memory result cache can satisfy recovery.
    from van_gateway.storage.db import Store
    restarted = GoogleService(Store(app.state.store.path), '', transport=google.transport)
    restarted._fernet = google._fernet
    assert await restarted.original_withdrawal(request['operation_id'], device_id=device) == receipt
    assert await restarted.withdraw_selected(request, device_id=device) == receipt
    assert await restarted.connection_detail() == replacement
    assert await restarted._refresh_token('owner') == 'SOURCE-replacement'
    saved = await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',
                                          (google._withdrawal_key(request['operation_id']),))
    assert 'APPLIED' not in saved['value'] and 'SOURCE-original' not in saved['value']


@pytest.mark.asyncio
async def test_old_selection_refuses_new_generation_and_retains_original_refusal(client):
    _, app = client
    device = (await app.state.store.fetchone('SELECT device_id FROM devices'))['device_id']
    google = app.state.google
    await google.store_refresh_token('owner', 'SOURCE-same', [SCOPE])
    request = (await google.withdrawal_detail(device_id=device))['withdrawal_request']
    await google.store_refresh_token('owner', 'SOURCE-same', [SCOPE])
    replacement = await google.connection_detail()
    result = await google.withdraw_selected(request, device_id=device)
    assert result['state'] == 'REFUSED'
    assert result['reason_code'] == 'workspace_withdrawal_stale_connection'
    assert await google.withdraw_selected(request, device_id=device) == result
    assert await google.connection_detail() == replacement


@pytest.mark.asyncio
async def test_readonly_proposal_creates_no_durable_mutation(client):
    _, app = client
    device = (await app.state.store.fetchone('SELECT device_id FROM devices'))['device_id']
    await app.state.google.store_refresh_token('owner', 'SOURCE-token', [SCOPE])
    before = [tuple(r) for r in await app.state.store.fetchall('SELECT * FROM runtime_meta ORDER BY key')]
    a = await app.state.google.withdrawal_detail(device_id=device)
    b = await app.state.google.withdrawal_detail(device_id=device)
    assert a['withdrawal_request']['operation_id'] != b['withdrawal_request']['operation_id']
    assert [tuple(r) for r in await app.state.store.fetchall('SELECT * FROM runtime_meta ORDER BY key')] == before


@pytest.mark.asyncio
async def test_expired_pending_refuses_but_completed_original_recovers_after_deadline(client, monkeypatch):
    _, app = client
    import van_gateway.google.service as module
    device = (await app.state.store.fetchone('SELECT device_id FROM devices'))['device_id']
    google = app.state.google
    await google.store_refresh_token('owner', 'SOURCE-token', [SCOPE])
    first = (await google.withdrawal_detail(device_id=device))['withdrawal_request']
    pending = (await google.withdrawal_detail(device_id=device))['withdrawal_request']
    result = await google.withdraw_selected(first, device_id=device)
    now = module.time.time()
    monkeypatch.setattr(module.time, 'time', lambda: now+601)
    assert await google.withdraw_selected(first, device_id=device) == result
    refusal = await google.withdraw_selected(pending, device_id=device)
    assert refusal['reason_code'] == 'workspace_withdrawal_request_expired'
    assert refusal['changed'] is False


@pytest.mark.asyncio
async def test_tampered_original_receipt_retains_forensic_state_and_replacement(client):
    _, app = client
    from van_gateway.google.service import GoogleAuthError
    device = (await app.state.store.fetchone('SELECT device_id FROM devices'))['device_id']
    google = app.state.google
    await google.store_refresh_token('owner', 'SOURCE-old', [SCOPE])
    request = (await google.withdrawal_detail(device_id=device))['withdrawal_request']
    await google.withdraw_selected(request, device_id=device)
    await google.store_refresh_token('owner', 'SOURCE-new', [SCOPE])
    await app.state.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',
                                  ('SOURCE-corrupt', google._withdrawal_key(request['operation_id'])))
    with pytest.raises(GoogleAuthError, match='integrity'):
        await google.withdraw_selected(request, device_id=device)
    assert await google._refresh_token('owner') == 'SOURCE-new'
    assert (await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',
            (google._withdrawal_key(request['operation_id']),)))['value'] == 'SOURCE-corrupt'

@pytest.mark.asyncio
@pytest.mark.parametrize('replace', [False, True])
async def test_withdrawal_or_reconnect_wins_oauth_exchange_no_fresh_provider_call(client, replace):
    import asyncio
    from van_gateway.google.service import GoogleAuthError
    _, app = client
    google = app.state.google
    started = asyncio.Event()
    finish = asyncio.Event()
    class OAuth:
        async def access_token(self, refresh):
            started.set()
            await finish.wait()
            return 'SOURCE-stale-access'
    class Transport:
        requires_access_token = True
        calls = 0
        async def gmail_search(self, token, query):
            self.calls += 1
            return []
    transport = Transport()
    google.transport = transport
    google.oauth = OAuth()
    await google.store_refresh_token('owner', 'SOURCE-original', [SCOPE])
    task = asyncio.create_task(google.gmail_search('SOURCE-query'))
    try:
        await asyncio.wait_for(started.wait(), 2)
        if replace:
            await google.store_refresh_token('owner', 'SOURCE-original', [SCOPE])
        else:
            await google.revoke()
        finish.set()
        with pytest.raises(GoogleAuthError, match='withdrawn_or_replaced'):
            await asyncio.wait_for(task, 2)
        assert transport.calls == 0
    finally:
        finish.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_submitted_call_remains_observable_but_next_admission_is_blocked(client):
    import asyncio
    from van_gateway.google.service import GoogleAuthError
    _, app = client
    google = app.state.google
    submitted = asyncio.Event()
    finish = asyncio.Event()
    class Transport:
        requires_access_token = False
        calls = 0
        async def gmail_search(self, token, query):
            self.calls += 1
            submitted.set()
            await finish.wait()
            return [{'id': 'SOURCE-original-effect'}]
    transport = Transport()
    google.transport = transport
    await google.store_refresh_token('owner', 'SOURCE-original', [SCOPE])
    task = asyncio.create_task(google.gmail_search('SOURCE-query'))
    try:
        await asyncio.wait_for(submitted.wait(), 2)
        await google.revoke()
        with pytest.raises(GoogleAuthError, match='not_connected'):
            await google.gmail_search('SOURCE-next-query')
        finish.set()
        assert await asyncio.wait_for(task, 2) == [{'id': 'SOURCE-original-effect'}]
        assert transport.calls == 1
    finally:
        finish.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

@pytest.mark.asyncio
async def test_workspace_canary_binds_original_probe_and_live_generation_without_status_argument(client):
    _, app = client
    from van_gateway.google.mesh import GoogleCapabilityState, GoogleIdentityBroker
    from van_gateway.google.transport import FakeGoogleTransport
    google = app.state.google
    google.transport = FakeGoogleTransport()
    broker = GoogleIdentityBroker(app.state.store, app.state.google_broker.registry, workspace_source=google)
    await broker.register_principal(subject='SOURCE-owner')
    await google.store_refresh_token('owner', 'SOURCE-first', [SCOPE])
    probe = await broker.begin_workspace_probe('workspace_api')
    assert isinstance(await google.gmail_search('SOURCE-canary'), list)
    await broker.record_capability_evidence('workspace_api', state=GoogleCapabilityState.READY,
        evidence_pointer='SOURCE://actual-fixture-canary', metadata={'workspace_probe': probe})
    assert (await broker.capability_status('workspace_api')).state == GoogleCapabilityState.READY
    await broker.record_capability_evidence('gemini', state=GoogleCapabilityState.READY,
        evidence_pointer='SOURCE://independent-runtime')
    before_other = dict(await broker._evidence('gemini'))
    await google.store_refresh_token('owner', 'SOURCE-first', [SCOPE])
    with pytest.raises(ValueError, match='generation_unverified'):
        await broker.record_capability_evidence('workspace_api', state=GoogleCapabilityState.READY,
            evidence_pointer='SOURCE://late-original-probe', metadata={'workspace_probe': probe})
    assert (await broker.capability_status('workspace_api')).state == GoogleCapabilityState.CONFIGURED
    assert dict(await broker._evidence('gemini')) == before_other
    # Even a stale legacy READY row cannot bypass the actual read consumer.
    await app.state.store.execute("UPDATE google_capability_connections SET state='READY', metadata_json='{}' WHERE capability_id='workspace_api'")
    assert (await broker.capability_status('workspace_api')).state == GoogleCapabilityState.CONFIGURED
    await google.revoke()
    await app.state.store.execute("UPDATE google_capability_connections SET state='READY' WHERE capability_id='workspace_api'")
    assert (await broker.capability_status('workspace_api')).state == GoogleCapabilityState.AUTH_REQUIRED
    assert (await broker.capability_status('gemini')).state == GoogleCapabilityState.READY


@pytest.mark.asyncio
async def test_workspace_ready_without_original_probe_or_credential_owner_refuses(client):
    _, app = client
    from van_gateway.google.mesh import GoogleCapabilityState, GoogleIdentityBroker
    broker = GoogleIdentityBroker(app.state.store, app.state.google_broker.registry, workspace_source=app.state.google)
    await broker.register_principal(subject='SOURCE-owner')
    await app.state.google.store_refresh_token('owner', 'SOURCE-token', [SCOPE])
    with pytest.raises(ValueError, match='generation_unverified'):
        await broker.record_capability_evidence('workspace_api', state=GoogleCapabilityState.READY,
                                              evidence_pointer='SOURCE://no-probe')
    probe = await broker.begin_workspace_probe('workspace_api')
    probe['credential_owner_id'] = 'SOURCE-other-owner'
    with pytest.raises(ValueError, match='generation_unverified'):
        await broker.record_capability_evidence('workspace_api', state=GoogleCapabilityState.READY,
            evidence_pointer='SOURCE://wrong-owner', metadata={'workspace_probe': probe})

@pytest.mark.asyncio
async def test_registry_bound_alias_invalidation_preserves_independent_owners_and_planes(client):
    from dataclasses import replace
    from van_gateway.google.mesh import GoogleIdentityBroker
    _, app = client
    google = app.state.google
    registry = app.state.google_broker.registry
    registry.delegated_identities['SOURCE-inheriting'] = {
        'workspace_access': True, 'credential_inheritance': True,
        'allowed_capabilities': ['SOURCE-alias-capability']}
    registry._descriptors['SOURCE-alias-capability'] = replace(
        registry.get('workspace_api'), capability_id='SOURCE-alias-capability', identity_alias='SOURCE-inheriting')
    GoogleIdentityBroker(app.state.store, registry, workspace_source=google)
    async with app.state.store.connection() as db:
        for capability, owner, plane in [('SOURCE-canonical','owner_google_account','workspace_oauth'),
            ('SOURCE-alias','SOURCE-inheriting','workspace_oauth'),
            ('SOURCE-unrelated','SOURCE-independent-owner','workspace_oauth'),
            ('SOURCE-other-plane','owner_google_account','cloud_service')]:
            await db.execute('INSERT INTO google_capability_connections(capability_id,owner_id,state,credential_plane,metadata_json,updated_at_unix) VALUES(?,?,\'READY\',?,\'{}\',1)',
                             (capability,owner,plane))
        await db.commit()
    await google.store_refresh_token('owner', 'SOURCE-new', [SCOPE])
    rows = {r['capability_id']: dict(r) for r in await app.state.store.fetchall('SELECT * FROM google_capability_connections')}
    assert rows['SOURCE-canonical']['state'] == rows['SOURCE-alias']['state'] == 'CONFIGURED'
    assert rows['SOURCE-unrelated']['state'] == rows['SOURCE-other-plane']['state'] == 'READY'
    await google.revoke()
    rows = {r['capability_id']: dict(r) for r in await app.state.store.fetchall('SELECT * FROM google_capability_connections')}
    assert rows['SOURCE-canonical']['state'] == rows['SOURCE-alias']['state'] == 'AUTH_REQUIRED'
    assert rows['SOURCE-unrelated']['state'] == rows['SOURCE-other-plane']['state'] == 'READY'


@pytest.mark.asyncio
async def test_receipt_insert_failure_rolls_back_withdrawal_and_readiness(client):
    _, app = client
    google = app.state.google
    device = (await app.state.store.fetchone('SELECT device_id FROM devices'))['device_id']
    await google.store_refresh_token('owner', 'SOURCE-credential', [SCOPE])
    before = await google.connection_detail()
    request = (await google.withdrawal_detail(device_id=device))['withdrawal_request']
    async with app.state.store.connection() as db:
        await db.execute("CREATE TRIGGER source_journal_failure BEFORE INSERT ON runtime_meta WHEN NEW.key LIKE 'google_owner_withdrawal:%' BEGIN SELECT RAISE(ABORT,'SOURCE-journal-interrupted'); END")
        await db.commit()
    with pytest.raises(Exception, match='SOURCE-journal-interrupted'):
        await google.withdraw_selected(request, device_id=device)
    assert await google.connection_detail() == before
    assert await google._refresh_token('owner') == 'SOURCE-credential'
    assert await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',
        (google._withdrawal_key(request['operation_id']),)) is None


@pytest.mark.asyncio
async def test_selected_request_changed_body_wrong_caller_or_retired_caller_cannot_withdraw(client):
    from van_gateway.google.service import GoogleAuthError
    _, app = client
    google = app.state.google
    device = (await app.state.store.fetchone('SELECT device_id FROM devices'))['device_id']
    await google.store_refresh_token('owner', 'SOURCE-original', [SCOPE])
    request = (await google.withdrawal_detail(device_id=device))['withdrawal_request']
    for field in ('owner_id','connection_generation','expected_revision','operation_id'):
        changed = {**request, field: 'SOURCE-changed'}
        with pytest.raises(GoogleAuthError):
            await google.withdraw_selected(changed, device_id=device)
    with pytest.raises(GoogleAuthError, match='wrong_caller'):
        await google.withdraw_selected(request, device_id='SOURCE-other-device')
    await app.state.store.execute('UPDATE devices SET revoked_at_unix=1 WHERE device_id=?',(device,))
    with pytest.raises(GoogleAuthError, match='caller_not_current'):
        await google.withdraw_selected(request, device_id=device)
    assert await google._refresh_token('owner') == 'SOURCE-original'

@pytest.mark.asyncio
async def test_legacy_first_operation_recovers_but_reconnection_requires_explicit_intent(client):
    from van_gateway.google.service import GoogleAuthError
    _, app = client
    google = app.state.google
    device = (await app.state.store.fetchone('SELECT device_id FROM devices'))['device_id']
    await google.store_refresh_token('owner', 'SOURCE-original', [SCOPE])
    first = await google.withdraw_legacy(device_id=device)
    assert first['state'] == 'APPLIED' and first['changed'] is True
    assert await google.withdraw_legacy(device_id=device) == first
    await google.store_refresh_token('owner', 'SOURCE-original', [SCOPE])
    with pytest.raises(GoogleAuthError, match='explicit_operation_required'):
        await google.withdraw_legacy(device_id=device)
    assert await google._refresh_token('owner') == 'SOURCE-original'
    request = (await google.withdrawal_detail(device_id=device))['withdrawal_request']
    second = await google.withdraw_selected(request, device_id=device)
    assert second['state'] == 'APPLIED' and second['operation_id'] != first['operation_id']
    assert await google.original_withdrawal(first['operation_id'], device_id=device) == first

@pytest.mark.asyncio
async def test_http_original_readback_and_current_status_are_independent_after_reconnect(client):
    ac, app = client
    await app.state.google.store_refresh_token('owner', 'SOURCE-first', [SCOPE])
    status = await ac.get('/v1/google/status')
    assert status.headers['Cache-Control'] == 'no-store'
    request = status.json()['withdrawal_request']
    first = await ac.post('/v1/google/owner-revoke', json=request)
    assert first.status_code == 200, first.text
    receipt = first.json()['withdrawal_receipt']
    await app.state.google.store_refresh_token('owner', 'SOURCE-next', [SCOPE])
    original = await ac.get('/v1/google/owner-revocations/'+request['operation_id'])
    assert original.status_code == 200 and original.json() == receipt
    retried = await ac.post('/v1/google/owner-revoke', json=request)
    assert retried.status_code == 200 and retried.json()['withdrawal_receipt'] == receipt
    assert retried.json()['connected'] is True
    assert (await ac.get('/v1/google/status')).json()['connected'] is True


@pytest.mark.asyncio
async def test_current_lawful_other_device_can_manage_connection_but_not_original_callers_operation(client):
    ac, app = client
    await app.state.google.store_refresh_token('owner', 'SOURCE-first', [SCOPE])
    request = (await ac.get('/v1/google/status')).json()['withdrawal_request']
    ticket = await app.state.auth.create_pairing_ticket('SOURCE-replacement-phone')
    paired = await app.state.auth.pair_device(ticket.token, 'SOURCE-replacement-phone', 'SOURCE-secret', 'PEM', 'phone')
    headers = {'X-Van-Device-Token': paired.access_token}
    wrong = await ac.post('/v1/google/owner-revoke', json=request, headers=headers)
    assert wrong.status_code == 403
    # A distinct currently lawful owner selection may manage the existing connection.
    current = (await ac.get('/v1/google/status', headers=headers)).json()
    applied = await ac.post('/v1/google/owner-revoke', json=current['withdrawal_request'], headers=headers)
    assert applied.status_code == 200 and applied.json()['withdrawal_receipt']['state'] == 'APPLIED'
    wrong_read = await ac.get('/v1/google/owner-revocations/'+current['withdrawal_request']['operation_id'])
    assert wrong_read.status_code == 403


@pytest.mark.asyncio
async def test_http_stale_original_refuses_and_legacy_retry_cannot_target_replacement(client):
    ac, app = client
    await app.state.google.store_refresh_token('owner', 'SOURCE-first', [SCOPE])
    request = (await ac.get('/v1/google/status')).json()['withdrawal_request']
    await app.state.google.store_refresh_token('owner', 'SOURCE-second', [SCOPE])
    stale = await ac.post('/v1/google/owner-revoke', json=request)
    assert stale.status_code == 409
    assert stale.json()['withdrawal_receipt']['state'] == 'REFUSED'
    assert stale.json()['connected'] is True
    assert (await ac.post('/v1/google/owner-revoke')).status_code == 200
    await app.state.google.store_refresh_token('owner', 'SOURCE-third', [SCOPE])
    ambiguous = await ac.post('/v1/google/owner-revoke')
    assert ambiguous.status_code == 409
    assert ambiguous.json()['detail'] == 'workspace_explicit_operation_required'
    assert await app.state.google._refresh_token('owner') == 'SOURCE-third'


@pytest.mark.asyncio
async def test_existing_internal_revoke_uses_internal_authority_without_device_identity_fabrication(client):
    ac, app = client
    from test_google_owner_revoke_and_scrub import INTERNAL
    await app.state.google.store_refresh_token('owner', 'SOURCE-first', [SCOPE])
    result = await ac.post('/v1/google/revoke', headers={'X-Van-Internal-Token':INTERNAL, 'X-Van-Device-Token':'SOURCE-not-a-device'})
    assert result.status_code == 200 and result.json()['connected'] is False
    assert await app.state.store.fetchone("SELECT key FROM runtime_meta WHERE key LIKE 'google_owner_withdrawal:%'") is None


@pytest.mark.asyncio
async def test_configured_strict_binding_profile_refuses_unbound_legacy_owner(client, monkeypatch):
    ac, app = client
    from van_gateway.config import get_settings
    from van_gateway.app import create_app
    from httpx import ASGITransport, AsyncClient
    await app.state.google.store_refresh_token('owner', 'SOURCE-first', [SCOPE])
    monkeypatch.setenv('VAN_REQUIRE_DEVICE_BINDING', 'true')
    get_settings.cache_clear()
    strict = create_app()
    async with strict.router.lifespan_context(strict):
        async with AsyncClient(transport=ASGITransport(app=strict), base_url='http://test', headers=dict(ac.headers)) as strict_client:
            result = await strict_client.post('/v1/google/owner-revoke')
            assert result.status_code in (403,503), result.text
            assert result.json()['detail'] in ('device_not_bound','owner_device_binding_unconfigured')
    assert await app.state.google._refresh_token('owner') == 'SOURCE-first'

@pytest.mark.asyncio
async def test_actual_http_withdrawal_wins_delayed_oauth_and_blocks_provider_boundary(client):
    import asyncio
    from test_google_owner_revoke_and_scrub import INTERNAL
    ac, app = client
    google = app.state.google
    started = asyncio.Event(); finish = asyncio.Event()
    class OAuth:
        async def access_token(self, refresh):
            started.set(); await finish.wait(); return 'SOURCE-delayed-token'
    class Transport:
        requires_access_token = True
        calls = 0
        async def gmail_search(self, token, query):
            self.calls += 1
            return []
    google.oauth = OAuth(); transport = Transport(); google.transport = transport
    await google.store_refresh_token('owner', 'SOURCE-token', [SCOPE])
    reviewed = (await ac.get('/v1/google/status')).json()
    effect = asyncio.create_task(ac.get('/v1/google/gmail/search', params={'q':'SOURCE-query'}, headers={'X-Van-Internal-Token':INTERNAL}))
    try:
        await asyncio.wait_for(started.wait(),2)
        withdrawn = await ac.post('/v1/google/owner-revoke', json=reviewed['withdrawal_request'])
        assert withdrawn.status_code == 200
        finish.set()
        result = await asyncio.wait_for(effect,2)
        assert result.status_code == 503 and transport.calls == 0
        original = await ac.get('/v1/google/owner-revocations/'+reviewed['withdrawal_request']['operation_id'])
        assert original.json() == withdrawn.json()['withdrawal_receipt']
    finally:
        finish.set()
        if not effect.done(): effect.cancel()
        await asyncio.gather(effect,return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['token','retired_binding'])
async def test_actor_currentness_is_rechecked_under_writer_before_withdrawal(client,change):
    ac, app = client
    from van_gateway.google.service import GoogleAuthError
    google = app.state.google
    device = (await app.state.store.fetchone('SELECT device_id FROM devices'))['device_id']
    await google.store_refresh_token('owner', 'SOURCE-token', [SCOPE])
    request = (await google.withdrawal_detail(device_id=device))['withdrawal_request']
    if change == 'token':
        await app.state.store.execute("UPDATE devices SET access_token_hash='SOURCE-new-token-hash' WHERE device_id=?",(device,))
    else:
        await app.state.store.execute("INSERT INTO owner_device_bindings(binding_id,owner_principal_id,device_id,device_key_fingerprint,public_key_pem,key_security_level,app_package_name,app_signing_cert_sha256,status,bound_at_ms) VALUES('SOURCE-binding','SOURCE-owner',?,'SOURCE-key','SOURCE-pem','SOURCE-fixture','SOURCE-app','SOURCE-cert','REVOKED',1)",(device,))
    if change == 'token':
        # A currently lawful replaced credential cannot execute the pending old
        # authorization context; its original operation receives durable refusal.
        result = await google.withdraw_selected(request,device_id=device)
        assert result['state'] == 'REFUSED' and result['changed'] is False
        assert result['reason_code'] == 'workspace_withdrawal_request_not_current'
    else:
        with pytest.raises(GoogleAuthError, match='caller_not_current'):
            await google.withdraw_selected(request,device_id=device)
    assert await google._refresh_token('owner') == 'SOURCE-token'

@pytest.mark.asyncio
@pytest.mark.parametrize('terminal_state', ['APPLIED','REFUSED'])
async def test_completed_history_current_same_principal_credential_replacement_preserves_original(client, terminal_state):
    """SOURCE trusted replacement diagnostic, not a production token-rotation route."""
    import hashlib
    ac, app = client
    google = app.state.google
    await google.store_refresh_token('owner', 'SOURCE-original', [SCOPE])
    request = (await ac.get('/v1/google/status')).json()['withdrawal_request']
    if terminal_state == 'REFUSED':
        await google.store_refresh_token('owner', 'SOURCE-replacement', [SCOPE])
    completed = await ac.post('/v1/google/owner-revoke', json=request)
    receipt = completed.json()['withdrawal_receipt']
    assert receipt['state'] == terminal_state
    key = google._withdrawal_key(request['operation_id'])
    original = (await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,)))['value']
    # Existing ordinary grant renewal does not rotate credentials and still permits history.
    device = request['caller_device_id']
    await app.state.auth.renew_grant(device)
    assert (await ac.get('/v1/google/owner-revocations/'+request['operation_id'])).status_code == 200
    before = dict(await app.state.store.fetchone('SELECT * FROM devices WHERE device_id=?',(device,)))
    current = 'SOURCE-trusted-current-token-replacement-0123456789'
    await app.state.store.execute('UPDATE devices SET access_token_hash=? WHERE device_id=?',
                                 (hashlib.sha256(current.encode()).hexdigest(),device))
    ac.headers['X-Van-Device-Token'] = current
    assert (await app.state.auth.require_access_token(current)).device_id == device
    assert (await ac.get('/v1/google/status')).status_code == 200
    connection_before_history = dict(await app.state.store.fetchone("SELECT * FROM google_connections WHERE owner_id='owner'"))
    history = await ac.get('/v1/google/owner-revocations/'+request['operation_id'])
    assert history.status_code == 200, history.text
    assert history.json() == receipt
    replay = await ac.post('/v1/google/owner-revoke',json=request)
    assert replay.status_code == (200 if terminal_state == 'APPLIED' else 409), replay.text
    assert replay.json()['withdrawal_receipt'] == receipt
    assert dict(await app.state.store.fetchone("SELECT * FROM google_connections WHERE owner_id='owner'")) == connection_before_history
    after = dict(await app.state.store.fetchone('SELECT * FROM devices WHERE device_id=?',(device,)))
    assert {k:v for k,v in before.items() if k!='access_token_hash'} == {k:v for k,v in after.items() if k!='access_token_hash'}
    assert (await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,)))['value'] == original


@pytest.mark.asyncio
async def test_pending_original_context_replacement_is_durable_refusal_without_new_effect(client):
    import hashlib
    ac, app = client
    google = app.state.google
    await google.store_refresh_token('owner','SOURCE-still-current',[SCOPE])
    request = (await ac.get('/v1/google/status')).json()['withdrawal_request']
    original_token = google._open(request['request_token'])
    current = 'SOURCE-trusted-current-pending-token-0123456789'
    await app.state.store.execute('UPDATE devices SET access_token_hash=? WHERE device_id=?',
        (hashlib.sha256(current.encode()).hexdigest(),request['caller_device_id']))
    ac.headers['X-Van-Device-Token'] = current
    assert (await ac.get('/v1/google/status')).status_code == 200
    result = await ac.post('/v1/google/owner-revoke',json=request)
    assert result.status_code == 409
    receipt = result.json()['withdrawal_receipt']
    assert receipt['state'] == 'REFUSED' and receipt['changed'] is False
    assert receipt['reason_code'] == 'workspace_withdrawal_request_not_current'
    assert await google._refresh_token('owner') == 'SOURCE-still-current'
    record = google._open((await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',
        (google._withdrawal_key(request['operation_id']),)))['value'])
    assert record['request'] == request and record['caller_context'] == original_token['caller_context']
    assert (await ac.get('/v1/google/owner-revocations/'+request['operation_id'])).json() == receipt
    assert (await ac.post('/v1/google/owner-revoke',json=request)).json()['withdrawal_receipt'] == receipt

@pytest.mark.asyncio
async def test_completed_history_wrong_owner_device_profile_or_revocation_remains_denied(client):
    from van_gateway.google.service import GoogleAuthError, GoogleService
    from cryptography.fernet import Fernet
    ac, app = client
    google = app.state.google
    await google.store_refresh_token('owner','SOURCE-original',[SCOPE])
    request = (await ac.get('/v1/google/status')).json()['withdrawal_request']
    await ac.post('/v1/google/owner-revoke',json=request)
    device = request['caller_device_id']
    with pytest.raises(GoogleAuthError,match='wrong_caller'):
        await google.original_withdrawal(request['operation_id'],device_id=device,owner_id='SOURCE-other-owner')
    with pytest.raises(GoogleAuthError,match='wrong_caller'):
        await google.withdraw_selected(request,device_id=device,owner_id='SOURCE-other-owner')
    ticket = await app.state.auth.create_pairing_ticket('SOURCE-other-device')
    other = await app.state.auth.pair_device(ticket.token,'SOURCE-other-device','SOURCE-secret','PEM','phone')
    assert (await ac.get('/v1/google/owner-revocations/'+request['operation_id'],
        headers={'X-Van-Device-Token':other.access_token})).status_code == 403
    # An independently protected gateway profile cannot authenticate the original
    # sealed history, even when supplied its database-shaped original bytes.
    different_profile = GoogleService(app.state.store,Fernet.generate_key().decode())
    with pytest.raises(GoogleAuthError,match='integrity'):
        await different_profile.original_withdrawal(request['operation_id'],device_id=device)
    await app.state.store.execute('UPDATE devices SET revoked_at_unix=1 WHERE device_id=?',(device,))
    assert (await ac.get('/v1/google/owner-revocations/'+request['operation_id'])).status_code in (401,403)


@pytest.mark.asyncio
async def test_completed_legacy_history_current_same_device_credential_replacement_is_original(client):
    import hashlib
    ac, app = client
    await app.state.google.store_refresh_token('owner','SOURCE-original',[SCOPE])
    first = await ac.post('/v1/google/owner-revoke')
    receipt = first.json()['withdrawal_receipt']
    current = 'SOURCE-trusted-legacy-current-token-0123456789'
    await app.state.store.execute('UPDATE devices SET access_token_hash=? WHERE device_id=?',
        (hashlib.sha256(current.encode()).hexdigest(),receipt['caller_device_id']))
    ac.headers['X-Van-Device-Token'] = current
    again = await ac.post('/v1/google/owner-revoke')
    assert again.status_code == 200 and again.json()['withdrawal_receipt'] == receipt
