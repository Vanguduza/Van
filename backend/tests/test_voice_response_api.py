"""Real HTTP speech production from authenticated command results, without redispatch."""
import pytest

from test_command_execution_result import _settings, client, _enrol, _signed, INTERNAL, INGRESS


async def completed(ac, app):
    device = await _enrol(ac, app)
    body = _signed(app, device, 'brief me about the current project', idempotency_key='voice-result')
    accepted = await ac.post('/v1/commands', json=body)
    assert accepted.status_code == 200, accepted.text
    mission = await app.state.missions.get(accepted.json()['mission_id'])
    binding = await app.state.store.fetchone('SELECT hermes_run_id FROM hermes_run_bindings WHERE mission_id=?', (mission.mission_id,))
    result = await ac.post('/v1/runtime/missions/result', headers={'X-Van-Internal-Token': INTERNAL},
        json={'hermes_run_id': binding['hermes_run_id'], 'status': 'COMPLETED',
              'summary': 'The trade was successful'})
    assert result.status_code == 200, result.text
    read = (await ac.get('/v1/commands/' + body['command_id'])).json()
    return body, read


def playback(command, result, nonce='playback-request-0001'):
    return {'command_id': command['command_id'], 'result_ref': result['result_ref'],
            'playback_request_id': nonce}


@pytest.mark.asyncio
async def test_real_result_produces_truthful_segments_idempotently_without_dispatch(client, monkeypatch):
    ac, app = client
    command, result = await completed(ac, app)
    assert result['owner_status'] == 'COULD_NOT_VERIFY'
    assert result['spoken_text'].startswith('Finished, but VAN could not confirm it worked')
    assert 'The trade was successful' in result['spoken_text']
    async def forbidden(*args, **kwargs):
        pytest.fail('a speech request dispatched new work')
    monkeypatch.setattr(app.state.orchestrator.hermes, 'create_run', forbidden)
    first = await ac.post('/v1/voice/responses', json=playback(command, result))
    assert first.status_code == 200, first.text
    data = first.json()
    assert 'could not confirm' in ' '.join(s['text'] for s in data['segments'])
    assert data['last_spoken_segment'] == -1
    sid = data['speech_stream_id']
    report = await ac.post(f'/v1/voice/streams/{sid}/cursors',
        json={'last_received_segment': data['total_segments'] - 1, 'last_spoken_segment': 0})
    assert report.status_code == 200, report.text
    again = (await ac.post('/v1/voice/responses', json=playback(command, result))).json()
    assert again['speech_stream_id'] == sid
    assert again['last_spoken_segment'] == 0
    other = (await ac.post('/v1/voice/responses', json=playback(command, result, 'playback-request-0002'))).json()
    assert other['speech_stream_id'] != sid
    assert other['last_spoken_segment'] == -1


@pytest.mark.asyncio
async def test_interrupt_is_terminal_and_cannot_be_revived_by_open_or_resume(client):
    ac, app = client
    command, result = await completed(ac, app)
    data = (await ac.post('/v1/voice/responses', json=playback(command, result))).json()
    sid = data['speech_stream_id']
    stopped = await ac.post(f'/v1/voice/streams/{sid}/interrupt')
    assert stopped.status_code == 200
    assert stopped.json()['interrupted'] is True
    for payload in [(await ac.get(f'/v1/voice/streams/{sid}')).json(),
                    (await ac.post('/v1/voice/responses', json=playback(command, result))).json()]:
        assert payload['segments'] == []
        assert payload['last_spoken_segment'] == -1
        assert payload['interrupted']


@pytest.mark.asyncio
async def test_foreign_device_cannot_open_read_acknowledge_or_interrupt(client):
    ac, app = client
    command, result = await completed(ac, app)
    opened = (await ac.post('/v1/voice/responses', json=playback(command, result))).json()
    sid = opened['speech_stream_id']
    await _enrol(ac, app, 'foreign-phone')
    attempts = [await ac.post('/v1/voice/responses', json=playback(command, result)),
                await ac.get(f'/v1/voice/streams/{sid}'),
                await ac.post(f'/v1/voice/streams/{sid}/cursors', json={'last_received_segment': 0, 'last_spoken_segment': 0}),
                await ac.post(f'/v1/voice/streams/{sid}/interrupt')]
    assert [r.status_code for r in attempts] == [404] * 4
    assert app.state.speech_streams.get(sid).last_spoken_segment == -1
    assert not app.state.speech_streams.get(sid).interrupted


@pytest.mark.asyncio
@pytest.mark.parametrize('received,spoken', [(True, 0), (0, False), (0.0, 0), (0, -2), (999, 0), (0, 1)])
async def test_cursor_rejects_coercion_out_of_range_and_unreceived_speech(client, received, spoken):
    ac, app = client
    command, result = await completed(ac, app)
    opened = (await ac.post('/v1/voice/responses', json=playback(command, result))).json()
    sid = opened['speech_stream_id']
    response = await ac.post(f'/v1/voice/streams/{sid}/cursors',
        json={'last_received_segment': received, 'last_spoken_segment': spoken})
    assert response.status_code == 422, response.text
    assert app.state.speech_streams.get(sid).last_spoken_segment == -1


@pytest.mark.asyncio
async def test_changed_result_rejects_stale_open_and_discards_existing_stream(client):
    ac, app = client
    command, result = await completed(ac, app)
    opened = (await ac.post('/v1/voice/responses', json=playback(command, result))).json()
    sid = opened['speech_stream_id']
    await app.state.store.execute('UPDATE missions SET final_outcome=? WHERE mission_id=?',
        ('Corrected result', result['mission_id']))
    assert (await ac.post('/v1/voice/responses', json=playback(command, result))).status_code == 409
    assert (await ac.get(f'/v1/voice/streams/{sid}')).status_code == 409
    assert app.state.speech_streams.get(sid) is None


@pytest.mark.asyncio
async def test_arbitrary_speech_text_and_anonymous_requests_are_not_accepted(client):
    ac, app = client
    command, result = await completed(ac, app)
    body = {**playback(command, result), 'text': 'Everything was verified'}
    assert (await ac.post('/v1/voice/responses', json=body)).status_code == 422
    token = ac.headers.pop('X-Van-Device-Token')
    assert (await ac.post('/v1/voice/responses', json=playback(command, result))).status_code == 401
    ac.headers['X-Van-Device-Token'] = token
    ac.headers.pop('X-Van-Ingress-Token')
    assert (await ac.post('/v1/voice/responses', json=playback(command, result))).status_code == 401


@pytest.mark.asyncio
async def test_pending_work_is_not_speech_completion(client):
    ac, app = client
    device = await _enrol(ac, app)
    command = _signed(app, device, 'brief me about the project', idempotency_key='pending-voice')
    assert (await ac.post('/v1/commands', json=command)).status_code == 200
    result = (await ac.get('/v1/commands/' + command['command_id'])).json()
    assert result['owner_status'] == 'WORKING'
    response = await ac.post('/v1/voice/responses', json=playback(command, result))
    assert response.status_code == 409
    assert response.json()['detail'] == 'speech_result_not_ready'


@pytest.mark.asyncio
async def test_logical_session_resume_serves_the_bound_unheard_tail(client):
    ac, app = client
    command, result = await completed(ac, app)
    opened = (await ac.post('/v1/voice/responses', json=playback(command, result))).json()
    sid = opened['speech_stream_id']
    ack = await ac.post(f'/v1/voice/streams/{sid}/cursors',
        json={'last_received_segment': opened['total_segments'] - 1, 'last_spoken_segment': -1})
    assert ack.status_code == 200
    session = (await ac.post('/v1/session/open', json={})).json()
    response = await ac.post('/v1/session/resume', json={
        'van_session_id': session['van_session_id'], 'session_epoch': session['session_epoch'],
        'pending_command_ids': [command['command_id']]})
    assert response.status_code == 200, response.text
    state = response.json()['response_state']
    assert state['speech_stream_id'] == sid
    assert state['resume_from_segment'] == 0
    assert state['segments'][0]['segment_index'] == 0
    await ac.post(f'/v1/voice/streams/{sid}/interrupt')
    response = await ac.post('/v1/session/resume', json={
        'van_session_id': session['van_session_id'], 'session_epoch': session['session_epoch']})
    assert response.json()['response_state'] is None


@pytest.mark.asyncio
async def test_bound_result_words_are_immutable_and_unknown_source_is_removed(client):
    ac, app = client
    command, result = await completed(ac, app)
    opened = (await ac.post('/v1/voice/responses', json=playback(command, result))).json()
    sid = opened['speech_stream_id']
    with pytest.raises(ValueError, match='speech_bound_result_immutable'):
        app.state.speech_streams.append(sid, 'Actually it was verified')
    await app.state.store.execute('UPDATE missions SET owner_principal_id=? WHERE mission_id=?',
        ('device:another-owner', result['mission_id']))
    # A command whose durable ownership changed cannot remain readable through its old cache.
    response = await ac.get(f'/v1/voice/streams/{sid}')
    assert response.status_code in (404, 409)
    assert app.state.speech_streams.get(sid) is None


@pytest.mark.asyncio
async def test_cache_capacity_refuses_new_audio_but_preserves_existing_delivery(client):
    ac, app = client
    command, result = await completed(ac, app)
    first = (await ac.post('/v1/voice/responses', json=playback(command, result))).json()
    for index in range(63):
        app.state.speech_streams.open(response_id=f'capacity-{index}', turn_id='turn',
            device_id=command['device_id'], text='The answer is ready.')
    refused = await ac.post('/v1/voice/responses', json=playback(command, result, 'playback-request-capacity'))
    assert refused.status_code == 429
    retry = await ac.post('/v1/voice/responses', json=playback(command, result))
    assert retry.status_code == 200
    assert retry.json()['speech_stream_id'] == first['speech_stream_id']
