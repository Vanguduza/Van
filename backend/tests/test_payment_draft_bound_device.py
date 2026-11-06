"""A bound key can store a draft; its proof is never a payment approval."""
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'trading/tests'))

from test_device_proof_enforcement import (_base_headers,_bind,_paired,_proof_headers,_settings,
    client as owner_client_fixture)
from test_payment_contracts import intent
from vati.core import Ledger


@pytest.mark.asyncio
async def test_bound_draft_write_requires_exact_request_proof_and_read_needs_no_new_approval(owner_client_fixture,tmp_path):
    ac,app=owner_client_fixture;enrolled=await _paired(app);key=await _bind(app,enrolled.device.device_id)
    path=tmp_path/'native-drafts.sqlite';app.state.trading.ledger_path=str(path)
    with closing(Ledger(path)):pass
    app.state.funding_drafts.clock=lambda:1500
    original=intent();original=replace(original,quote=replace(original.quote,beneficiary=replace(original.quote.beneficiary,owner_ref='owner')))
    target='/v1/trading/funding/drafts';raw=json.dumps({'intent':original.body()}).encode()
    headers={**_base_headers(enrolled),'Content-Type':'application/json'}
    unsigned=await ac.post(target,content=raw,headers=headers)
    assert unsigned.status_code==401 and unsigned.json()['detail']=='device_proof_required'
    with closing(Ledger(path)) as ledger:assert ledger.count()==0
    signed=await ac.post(target,content=raw,headers={**headers,
        **_proof_headers(key,method='POST',path=target,device_id=enrolled.device.device_id,body=raw)})
    assert signed.status_code==200,signed.text
    assert signed.json()['execution_authority'] is False and signed.json()['state']=='DRAFT_STORED_NOT_APPROVED'
    read=await ac.get(target+'/'+original.request_id+'/receipt',headers=_base_headers(enrolled))
    assert read.status_code==200 and read.json()==signed.json() and read.headers['cache-control']=='no-store'
    assert not await app.state.store.fetchall('SELECT * FROM mission_activities')
