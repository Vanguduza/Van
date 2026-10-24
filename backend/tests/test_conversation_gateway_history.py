"""Paired owner restoration, history paging and non-executing follow-up lifecycle."""
import pytest
from test_local_typed_actions import client,_settings,_pair_for_test

pytestmark=pytest.mark.asyncio


async def test_gateway_history_is_recent_pageable_and_rejects_foreign_cursors(client):
    ac,app,hermes=client;await _pair_for_test(ac,app,'dev-history','fixture-history-device-secret')
    main=(await ac.get('/v1/conversations/main')).json()
    side=await ac.post('/v1/conversations',json={'title':'Owner conversation'});assert side.status_code==200,side.text
    tid=side.json()['thread_id'];ids=[]
    for n in range(5):
        response=await ac.post(f'/v1/conversations/{tid}/messages',json={'role':'OWNER','body':f'Message {n}'})
        assert response.status_code==200,response.text
        ids.append(response.json()['message_id'])
    restored=await ac.get(f'/v1/conversations/{tid}')
    assert restored.status_code==200 and restored.json()['message_count']==5
    page=await ac.get(f'/v1/conversations/{tid}/messages',params={'limit':2})
    assert page.status_code==200,page.text
    assert [m['message_id'] for m in page.json()['messages']]==ids[-2:]
    assert page.json()['has_more'] is True and page.json()['total_count']==5
    older=await ac.get(f'/v1/conversations/{tid}/messages',params={'limit':3,'before_message_id':page.json()['next_before_message_id']})
    assert older.status_code==200 and [m['message_id'] for m in older.json()['messages']]==ids[:3]
    assert older.json()['has_more'] is False
    wrong=await ac.get(f"/v1/conversations/{main['thread_id']}/messages",params={'before_message_id':ids[-1]})
    assert wrong.status_code==409 and wrong.json()['detail']=='MESSAGE_CURSOR_INVALID'
    assert (await ac.get('/v1/conversations/missing/messages')).status_code==404
    assert hermes['create_run']==0


async def test_followup_promotion_is_a_fresh_prompt_without_work_dispatch(client):
    ac,app,hermes=client;await _pair_for_test(ac,app,'dev-history','fixture-history-device-secret')
    tid=(await ac.post('/v1/conversations',json={'title':'Queue'})).json()['thread_id']
    queued=await ac.post(f'/v1/conversations/{tid}/followups',json={'prompt':'Review actual current state'})
    assert queued.status_code==200,queued.text
    fid=queued.json()['followup_id']
    response=await ac.post(f'/v1/conversations/{tid}/followups/{fid}/decision',json={'action':'promote'})
    assert response.status_code==200,response.text
    assert response.json()['status']=='PROMOTED' and response.json()['fresh_owner_prompt']=='Review actual current state'
    assert response.json()['command_id'] is None and hermes['create_run']==0
    duplicate=await ac.post(f'/v1/conversations/{tid}/followups/{fid}/decision',json={'action':'dismiss'})
    assert duplicate.status_code==409 and duplicate.json()['detail']=='FOLLOWUP_ALREADY_DECIDED'
