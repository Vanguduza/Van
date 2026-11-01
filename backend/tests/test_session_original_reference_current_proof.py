"""LAC234 SOURCE: historical lookup retains the current endpoint's proof anti-replay."""
import json

import pytest
from test_device_proof_enforcement import client, _settings, _paired, _bind, _proof_headers, _base_headers
from test_session_original_command_reference import signed, reference


@pytest.mark.asyncio
async def test_original_lookup_requires_fresh_distinct_current_read_proof(client):
    ac, app = client
    enrolled = await _paired(app)
    device_id = enrolled.device.device_id
    private_key = await _bind(app, device_id)  # Existing SOURCE attestation fixture, no native enrollment.

    def proved(path, value):
        raw = json.dumps(value).encode()
        return raw, {**_base_headers(enrolled), "Content-Type": "application/json",
                     **_proof_headers(private_key, method="POST", path=path, device_id=device_id, body=raw)}

    raw, headers = proved("/v1/session/open", {})
    opened_response = await ac.post("/v1/session/open", content=raw, headers=headers)
    assert opened_response.status_code == 200, opened_response.text
    opened = opened_response.json()
    original = signed(app, device_id)
    value = dict(van_session_id=opened["van_session_id"], session_epoch=opened["session_epoch"],
                 pending_command_ids=[original["command_id"]],
                 original_command_references=[reference(opened, original)])
    raw, headers = proved("/v1/session/resume", value)
    missing = await ac.post("/v1/session/resume", content=raw,
                            headers={**_base_headers(enrolled), "Content-Type": "application/json"})
    assert missing.status_code == 401, missing.text
    response = await ac.post("/v1/session/resume", content=raw, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["command_states"][original["command_id"]] == "ORIGINAL_UNRESOLVED"
    replay = await ac.post("/v1/session/resume", content=raw, headers=headers)
    assert replay.status_code == 401, replay.text
    nonces = await app.state.store.fetchall("SELECT * FROM command_nonces")
    # Open and resume each consume their own current-request proof, never the
    # historical command's nonce. Replaying the read does not add a third claim.
    assert len(nonces) == 2
    assert all(row["command_id"] != original["command_id"] for row in nonces)
    assert await app.state.store.fetchall("SELECT * FROM idempotency") == []
