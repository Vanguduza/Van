"""The existing scoped Gmail-to-document adapter preserves unknown outcomes."""
import pytest
from test_google_capabilities_have_routes import client,_settings,_call
from test_document_fabric import form_pdf
from van_gateway.documents.service import DocumentServiceError


@pytest.mark.asyncio
async def test_gmail_import_does_not_relabel_uncertain_publication_as_bad_input(client,monkeypatch):
    ac,app=client
    async def attachment(message_id,attachment_id):
        assert (message_id,attachment_id)==('message-fixture','attachment-fixture')
        return form_pdf()
    async def unknown(**kwargs):
        raise DocumentServiceError('DOCUMENT_PUBLICATION_UNKNOWN',document_id='doc-original',publication_id='document_publication:original')
    monkeypatch.setattr(app.state.google,'gmail_attachment_get',attachment)
    monkeypatch.setattr(app.state.documents,'import_pdf',unknown)
    r=await _call(ac,'/v1/google/gmail/attachment/import-pdf','POST',message_id='message-fixture',attachment_id='attachment-fixture')
    assert r.status_code==503,r.text
    assert r.json()['detail']=={'code':'DOCUMENT_PUBLICATION_UNKNOWN','document_id':'doc-original','publication_id':'document_publication:original'}
