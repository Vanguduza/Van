"""Reviewer-owned real signed HTTP expiry at the last staged enrollment receipt."""
import time
from types import SimpleNamespace
import aiosqlite
import pytest
from test_pairing_recovery import _settings, client, proofs, _pending, _post, _counts
from van_gateway.auth import service
from van_gateway.auth.service import AuthError

@pytest.mark.asyncio
async def test_signed_pairing_expiry_after_original_attempt_write_rolls_back_every_enrollment_record(client,proofs,monkeypatch):
    ac,app=client
    payload,key=await _pending(app)
    ticket=await app.state.store.fetchone('SELECT expires_at_unix FROM pairing_tickets')
    clock=[int(time.time())]
    monkeypatch.setattr(service,'time',SimpleNamespace(time=lambda:clock[0]))
    execute=aiosqlite.Connection.execute
    hits=[]
    async def elapsed(db,sql,*args,**kwargs):
        result=await execute(db,sql,*args,**kwargs)
        if sql.startswith('INSERT INTO pairing_attempts('):
            hits.append(True)
            clock[0]=int(ticket['expires_at_unix'])
        return result
    monkeypatch.setattr(aiosqlite.Connection,'execute',elapsed)
    response=await _post(ac,payload,key,proofs)
    assert hits==[True]
    assert response.status_code==400 and response.json()=={'detail':'Pairing ticket invalid or expired'}
    assert await _counts(app)==(0,0,0)
    assert (await app.state.store.fetchone('SELECT used_at_unix FROM pairing_tickets'))['used_at_unix'] is None
    with pytest.raises(AuthError,match='not loaded'):
        app.state.auth.sign(payload['device_id'],'must remain unavailable')
