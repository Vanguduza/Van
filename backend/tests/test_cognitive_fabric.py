import time

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from van_gateway.cognitive.api import build_cognitive_router
from van_gateway.cognitive.service import CognitiveService, CognitiveCandidate
from van_gateway.context.models import OwnerFactCandidate, EpistemicState, SourceTrust
from van_gateway.context.service import OwnerContextService, ContextAdmissionError
from van_gateway.storage.db import Store


def body(now, *, kind='OWNER_PATTERN', revision=0, candidate_id='test'):
    return dict(candidate_id=candidate_id, expected_context_revision=revision,
        provider_product='personal-muse-free', candidate_type=kind, observed_at_ms=now - 1,
        expires_at_ms=now + 100000, source_refs=['observation:test'], evidence_hashes=['e' * 64],
        confidence_permille=600, affected_scopes=['global'], summary='Prefers concise evidence',
        data_class='INTERNAL_SAFE_FOR_APPROVED_PROVIDER', response_hash='a' * 64,
        observed_instances=['conversation:one'])


async def service(tmp_path):
    store = Store(str(tmp_path / 'db.sqlite'))
    await store.migrate()
    return CognitiveService(store, OwnerContextService(store))


@pytest.mark.asyncio
async def test_owner_patterns_use_real_inferred_context_and_retry_does_not_duplicate(tmp_path):
    svc = await service(tmp_path)
    now = int(time.time() * 1000)
    candidate = CognitiveCandidate(**body(now))
    first = await svc.ingest(candidate, now_ms=now)
    assert await svc.ingest(candidate, now_ms=now + 1) == first
    row = await svc.store.fetchone('SELECT * FROM owner_facts WHERE fact_id = ?', ('cognitive:test',))
    assert row['authority'] == 'INFERRED'
    assert row['source_trust'] == 'MODEL_DERIVED'
    assert await svc.context.kernel_revision() == 1


@pytest.mark.asyncio
async def test_owner_correction_supersedes_pattern_and_cannot_be_overturned(tmp_path):
    svc = await service(tmp_path)
    now = int(time.time() * 1000)
    await svc.ingest(CognitiveCandidate(**body(now)), now_ms=now)
    correction = OwnerFactCandidate(fact_id='owner-correction', subject='OWNER', predicate='pattern', value='Prefers complete implementation',
        authority=EpistemicState.CANONICAL_OWNER, source_trust=SourceTrust.OWNER_EXPLICIT, source_ref='owner:command',
        valid_from_ms=now, observed_at_ms=now, supersedes_fact_id='cognitive:test')
    await svc.context.admit_fact(correction)
    assert (await svc.candidates(now_ms=now))[0]['state'] == 'SUPERSEDED'
    prior = await svc.store.fetchone('SELECT valid_until_ms FROM owner_facts WHERE fact_id = ?', ('cognitive:test',))
    assert prior['valid_until_ms'] == now
    model_override = correction.model_copy(update={'fact_id': 'override', 'authority': EpistemicState.INFERRED,
        'source_trust': SourceTrust.MODEL_DERIVED, 'supersedes_fact_id': 'owner-correction', 'valid_from_ms': now + 1})
    with pytest.raises(ContextAdmissionError, match='lower-authority'):
        await svc.context.admit_fact(model_override)


@pytest.mark.asyncio
async def test_revision_mismatch_no_candidate_written(tmp_path):
    svc = await service(tmp_path)
    now = int(time.time() * 1000)
    with pytest.raises(ContextAdmissionError, match='STALE_CONTEXT'):
        await svc.ingest(CognitiveCandidate(**body(now, revision=4)), now_ms=now)
    assert await svc.candidates(now_ms=now) == []


@pytest.mark.parametrize('extra', [{'authority': 'CANONICAL_OWNER'}, {'provider_product': 'muse-spark-api'}, {'sensitive_inference': True}, {'data_class': 'SECRET'}])
def test_no_self_promotion_paid_route_or_sensitive_candidate(extra):
    data = body(100)
    data.update(extra)
    with pytest.raises(ValidationError):
        CognitiveCandidate(**data)


@pytest.mark.asyncio
async def test_attention_calibration_is_candidate_and_never_changes_thresholds(tmp_path):
    svc = await service(tmp_path)
    now = int(time.time() * 1000)
    data = body(now, kind='ATTENTION_CALIBRATION')
    data['attention_dimensions'] = {'importance': .5, 'interruption_cost': .9}
    await svc.ingest(CognitiveCandidate(**data), now_ms=now)
    assert await svc.context.kernel_revision() == 0
    assert (await svc.candidates(now_ms=now))[0]['authority'] == 'ADVISORY_CANDIDATE'
    data['candidate_id'] = 'invalid'
    data['attention_dimensions'] = {'risk_override': 1}
    with pytest.raises(ContextAdmissionError, match='ATTENTION_DIMENSIONS'):
        await svc.ingest(CognitiveCandidate(**data), now_ms=now)


@pytest.mark.asyncio
async def test_runtime_http_route_requires_server_credential_and_exposes_no_raw_owner_pattern(tmp_path):
    svc = await service(tmp_path)
    now = int(time.time() * 1000)
    await svc.ingest(CognitiveCandidate(**body(now)), now_ms=now)
    class Trading:
        def status(self):
            return {'ledger_available': True, 'ledger_stale': False, 'credentials': 'SHOULD_NOT_ESCAPE'}
    def authorize(token):
        if token != 'server-key':
            raise HTTPException(status_code=403, detail='internal_control_unauthorized')
    app = FastAPI()
    app.include_router(build_cognitive_router(store=svc.store, context=svc.context, trading=Trading(), require_internal=authorize))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.get('/v1/runtime/cognitive/projection')).status_code == 403
        response = await client.get('/v1/runtime/cognitive/projection', headers={'X-Van-Internal-Token': 'server-key'})
        assert response.status_code == 200
        assert response.json()['context_revision'] == 1
        assert 'Prefers concise evidence' not in response.text
        assert 'SHOULD_NOT_ESCAPE' not in response.text
        data = body(now, kind='MISSION_CANDIDATE', candidate_id='mission', revision=1)
        result = await client.post('/v1/runtime/cognitive/candidates', json=data, headers={'X-Van-Internal-Token': 'server-key'})
        assert result.status_code == 200
        assert result.json()['authority'] == 'ADVISORY_CANDIDATE'
        assert await svc.store.fetchone('SELECT * FROM missions', ()) is None

@pytest.mark.asyncio
async def test_actual_gateway_isolates_cognitive_credential_from_runtime_authority(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from van_gateway.app import create_app
    from van_gateway.config import get_settings
    token = 'candidate-machine-only-token-0123456789'
    legacy = 'legacy-runtime-token-0123456789'
    monkeypatch.setenv('VAN_DATABASE_PATH', str(tmp_path / 'gateway.sqlite'))
    monkeypatch.setenv('VAN_HERMES_BASE_URL', 'http://hermes.test')
    monkeypatch.setenv('VAN_GOOGLE_TOKEN_FERNET_KEY', Fernet.generate_key().decode())
    monkeypatch.setenv('VAN_DEVICE_SECRET_FERNET_KEY', Fernet.generate_key().decode())
    monkeypatch.setenv('VAN_INGRESS_TOKEN', 'ingress-test-0123456789')
    monkeypatch.setenv('VAN_INTERNAL_CONTROL_TOKEN', legacy)
    monkeypatch.setenv('VAN_INTERNAL_CONTROL_SCOPED_TOKENS', 'cognitive:' + token)
    monkeypatch.setenv('VAN_EXA_EGRESS_ENABLED', 'false')
    get_settings.cache_clear()
    try:
        app = create_app()
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
                result = await client.get('/v1/runtime/cognitive/projection', headers={'X-Van-Internal-Token': token})
                assert result.status_code == 200
                assert result.json()['project_id'] == 'van'
                assert result.json()['data_class'] == 'INTERNAL_SANITIZED'
                assert result.json()['source_revision'] == result.json()['context_revision']
                denied = await client.get('/v1/runtime/cognitive/projection', headers={'X-Van-Internal-Token': legacy})
                assert denied.status_code == 403
                denied = await client.post('/v1/runtime/resolve', json={'text': 'trade'}, headers={'X-Van-Internal-Token': token})
                assert denied.status_code == 403
                now = int(time.time() * 1000)
                candidate = body(now, kind='GUARDIAN_OBSERVATION', revision=result.json()['context_revision'])
                created = await client.post('/v1/runtime/cognitive/candidates', json=candidate, headers={'X-Van-Internal-Token': token})
                assert created.status_code == 200
                assert created.json()['data_class'] == 'INTERNAL_SANITIZED'
                assert created.json()['provider_approval_required'] is True
    finally:
        get_settings.cache_clear()

@pytest.mark.asyncio
async def test_semantic_machine_slices_use_distinct_authoritative_sources_and_canonical_envelopes(tmp_path):
    svc = await service(tmp_path)
    class Trading:
        def cognitive_slice(self, operation):
            return {'operation': operation, 'state': 'DEGRADED', 'reason': 'TRADING_LEDGER_UNAVAILABLE', 'records': []}
    for operation, payload_key in [('missions', 'missions'), ('attention', 'attention'), ('owner-context', 'public_facts'), ('capability-utilization', 'capabilities')]:
        result = await svc.slice(operation, Trading())
        assert result['operation'] == operation
        assert payload_key in result['payload']
        assert result['domain'] == 'owner'
        assert result['data_class'] == 'INTERNAL_SANITIZED'
        assert result['projection_revision']
        assert 'guardian' not in result['payload']
    for operation in ('trading-market', 'strategy-health', 'performance', 'tca', 'learning-episodes'):
        result = await svc.slice(operation, Trading())
        assert result['domain'] == 'trading'
        assert result['state'] == 'DEGRADED'
        assert result['payload']['reason'] == 'TRADING_LEDGER_UNAVAILABLE'
    with pytest.raises(ContextAdmissionError, match='UNKNOWN_COGNITIVE'):
        await svc.slice('broker-orders', Trading())


@pytest.mark.asyncio
async def test_real_trading_slices_are_bounded_hash_bound_and_exclude_money_and_credentials(tmp_path):
    from vati.core.ledger import Ledger
    from vati.core.events import EventKind, make_event
    from van_gateway.trading.service import TradingService
    path = tmp_path / 'vati.sqlite'
    ledger = Ledger(path)
    ledger.append(make_event(EventKind.TCA_RECORD, 'test-authority', {'slippage': '.01', 'cost_ratio': '1.2',
        'fees': '999', 'filled_qty': '500', 'broker_credentials': 'FORBIDDEN_SECRET'}, event_time_ms=10, received_time_ms=10))
    ledger.append(make_event(EventKind.COGNITIVE_PERFORMANCE, 'test-authority', {'model_id': 'test-model',
        'mean_delta_r': '.02', 'assessments': 50, 'approved_size': '500'}, event_time_ms=11, received_time_ms=11))
    ledger.close()
    trading = TradingService(str(path))
    tca = trading.cognitive_slice('tca')
    assert tca['state'] == 'AVAILABLE'
    assert tca['records'][0]['slippage'] == '.01'
    assert tca['records'][0]['source_event_hash']
    assert 'fees' not in tca['records'][0]
    assert 'FORBIDDEN_SECRET' not in str(tca)
    performance = trading.cognitive_slice('performance')
    assert performance['records'][0]['model_id'] == 'test-model'
    assert 'approved_size' not in str(performance)
    assert trading.cognitive_slice('strategy-health')['state'] == 'AVAILABLE_EMPTY'


@pytest.mark.asyncio
async def test_machine_transport_is_trusted_route_metadata_not_payload(tmp_path):
    svc = await service(tmp_path)
    now = int(time.time() * 1000)
    data = body(now, kind='GUARDIAN_OBSERVATION')
    result = await svc.ingest(CognitiveCandidate(**data), now_ms=now, trusted_ingress='DOT_COGNITIVE_MACHINE')
    assert result['transport'] == 'DOT_COGNITIVE_MACHINE'
    data['transport'] = 'CANONICAL_OWNER'
    with pytest.raises(ValidationError):
        CognitiveCandidate(**data)
