"""Paired owner transport for immutable document versions and refused reviews."""
import io
from pypdf import PdfReader
import pytest
from test_document_fabric import form_pdf
from test_local_typed_actions import client,_settings,_pair_for_test

pytestmark=pytest.mark.asyncio


async def test_gateway_returns_exact_versions_and_rejects_a_stale_review(client):
    ac,app,hermes=client;await _pair_for_test(ac,app,'dev-doc','fixture-document-device-secret')
    r=await ac.post('/v1/documents/import',files={'file':('owner.pdf',form_pdf(),'application/pdf')},data={'project_id':'project-original'})
    assert r.status_code==200,r.text
    doc=r.json();did=doc['document_id']
    r=await ac.post(f'/v1/documents/{did}/proposal',json={'values':{'owner_name':'First'}})
    assert r.status_code==200,r.text
    review=r.json();assert review['baseline_sha256']==doc['source_sha256']
    r=await ac.post(f'/v1/documents/{did}/fill',json={'values':{'owner_name':'First'},'expected_proposal_sha256':review['proposal_sha256']})
    assert r.status_code==200,r.text
    first=r.json()
    r=await ac.post(f'/v1/documents/{did}/fill',json={'values':{'owner_name':'Second'}})
    assert r.status_code==200,r.text
    second=r.json()
    r=await ac.post(f'/v1/documents/{did}/fill',json={'values':{'owner_name':'First'},'expected_proposal_sha256':review['proposal_sha256']})
    assert r.status_code==409 and r.json()['detail']=='DOCUMENT_PROPOSAL_STALE'
    for version,value in [(first,'First'),(second,'Second')]:
        r=await ac.get(f'/v1/documents/{did}/content/output',params={'sha256':version['output_sha256']})
        assert r.status_code==200,r.text
        assert str(PdfReader(io.BytesIO(r.content)).get_fields()['owner_name']['/V'])==value
        artifact=(await ac.get('/v1/artifacts/'+version['output_artifact_id'])).json()
        assert artifact['content_ref'].endswith(version['output_sha256']) and artifact['project_id']=='project-original'
    fields=await ac.get(f'/v1/documents/{did}/fields')
    assert fields.status_code==200 and fields.json()['fields'][0]['value']=='Second'
    assert (await ac.get(f'/v1/documents/{did}/content/output',params={'sha256':'../invalid'})).status_code==422
    assert hermes['create_run']==0


@pytest.mark.parametrize('operation',['proposal','fill'])
async def test_gateway_does_not_silently_ignore_a_foreign_requested_context(client,operation):
    ac,app,_=client;await _pair_for_test(ac,app,'dev-doc','fixture-document-device-secret')
    r=await ac.post('/v1/documents/import',files={'file':('owner.pdf',form_pdf(),'application/pdf')},data={'project_id':'original-project'})
    assert r.status_code==200,r.text
    did=r.json()['document_id']
    r=await ac.post(f'/v1/documents/{did}/{operation}',json={'values':{'owner_name':'Different context'},'project_id':'different-project'})
    assert r.status_code==409 and r.json()['detail']=='DOCUMENT_CONTEXT_MISMATCH'
    assert (await ac.get(f'/v1/documents/{did}')).json()['output_artifact_id'] is None


async def test_fields_route_repairs_the_view_of_legacy_cached_values_from_verified_bytes(client):
    import json
    ac,app,_=client;await _pair_for_test(ac,app,'dev-doc','fixture-document-device-secret')
    r=await ac.post('/v1/documents/import',files={'file':('owner.pdf',form_pdf(),'application/pdf')});assert r.status_code==200,r.text
    did=r.json()['document_id']
    r=await ac.post(f'/v1/documents/{did}/fill',json={'values':{'owner_name':'Actual output value'}});assert r.status_code==200,r.text
    await app.state.store.execute('UPDATE documents SET fields_json=? WHERE document_id=?',
        (json.dumps([{'name':'owner_name','kind':'TEXT','value':'Legacy cached value','required':False}]),did))
    r=await ac.get(f'/v1/documents/{did}/fields')
    assert r.status_code==200 and r.json()['fields'][0]['value']=='Actual output value'


async def test_gateway_preserves_unknown_commit_ack_and_exact_native_identity(client,monkeypatch):
    from contextlib import asynccontextmanager
    ac,app,_=client;await _pair_for_test(ac,app,'dev-doc','fixture-document-device-secret')
    r=await ac.post('/v1/documents/import',files={'file':('owner.pdf',form_pdf(),'application/pdf')});assert r.status_code==200,r.text
    did=r.json()['document_id'];store=app.state.store;connection=store.connection;fetchone=store.fetchone;lost=False
    class Connection:
        def __init__(self,db):self.db=db;self.document_write=False
        def __getattr__(self,name):return getattr(self.db,name)
        async def execute(self,sql,params=()):
            if 'INSERT INTO runtime_meta' in sql and params and str(params[0]).startswith('document_publication:'):
                self.document_write=True
            return await self.db.execute(sql,params)
        async def commit(self):
            nonlocal lost
            await self.db.commit()
            if self.document_write and not lost:
                lost=True;raise RuntimeError('lost actual document commit reply')
    @asynccontextmanager
    async def wrapped():
        async with connection() as db:yield Connection(db)
    async def unavailable(sql,*args):
        if lost and 'SELECT value FROM runtime_meta' in sql:raise RuntimeError('native result readback unavailable')
        return await fetchone(sql,*args)
    monkeypatch.setattr(store,'connection',wrapped);monkeypatch.setattr(store,'fetchone',unavailable)
    r=await ac.post(f'/v1/documents/{did}/fill',json={'values':{'owner_name':'Actual committed result'}})
    assert r.status_code==503,r.text
    detail=r.json()['detail']
    assert detail['code']=='DOCUMENT_PUBLICATION_UNKNOWN' and detail['document_id']==did
    assert detail['publication_id'].startswith('document_publication:')
    monkeypatch.setattr(store,'fetchone',fetchone)
    r=await ac.get(f'/v1/documents/{did}/content/output')
    assert r.status_code==200,r.text
    assert str(PdfReader(io.BytesIO(r.content)).get_fields()['owner_name']['/V'])=='Actual committed result'
    assert await store.fetchone('SELECT key FROM runtime_meta WHERE key=?',(detail['publication_id'],)) is not None
