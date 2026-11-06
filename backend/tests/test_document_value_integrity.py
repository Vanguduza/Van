"""PDF fields and downloaded bytes must match the information supplied to the owner."""
import io
from pypdf import PdfReader,PdfWriter
from pypdf.generic import NameObject,NumberObject,TextStringObject
import pytest
from test_document_fabric import form_pdf,static_pdf
from test_local_typed_actions import client,_settings,_pair_for_test
from van_gateway.documents.pdf import inspect_pdf,fill_pdf,PdfDocumentError


def with_flags(value):
    reader=PdfReader(io.BytesIO(form_pdf()));writer=PdfWriter();writer.clone_document_from_reader(reader)
    field=writer.root_object['/AcroForm']['/Fields'][0].get_object()
    field[NameObject('/Ff')]=value
    stream=io.BytesIO();writer.write(stream);return stream.getvalue()


def test_required_pdf_field_is_reported_as_required_to_the_owner():
    inspection=inspect_pdf(with_flags(NumberObject(2)))
    assert inspection.fields[0].required is True


def test_malformed_pdf_field_flags_are_not_silently_treated_as_unrestricted():
    with pytest.raises(PdfDocumentError):inspect_pdf(with_flags(TextStringObject('false')))


def test_pdf_writer_acknowledgement_is_not_proof_that_requested_values_were_written(monkeypatch):
    monkeypatch.setattr(PdfWriter,'update_page_form_field_values',lambda *args,**kwargs:None)
    with pytest.raises(PdfDocumentError,match='PDF_FIELD_POSTCONDITION_FAILED'):
        fill_pdf(form_pdf(),{'owner_name':'Expected owner value'})


@pytest.mark.asyncio
async def test_paired_owner_can_download_a_pdf_with_a_unicode_filename(client):
    from urllib.parse import unquote
    ac,app,_=client;await _pair_for_test(ac,app,'dev-pdf','fixture-document-device-secret')
    source=static_pdf();response=await ac.post('/v1/documents/import',files={'file':('測試.pdf',source,'application/pdf')})
    assert response.status_code==200,response.text
    doc=response.json()
    try:response=await ac.get(f"/v1/documents/{doc['document_id']}/content/source")
    except Exception as exc:response=exc
    assert not isinstance(response,Exception),f'valid filename broke owner download: {type(response).__name__}'
    assert response.status_code==200 and response.content==source
    disposition=response.headers['content-disposition']
    assert "filename*=UTF-8''" in disposition
    assert unquote(disposition.split("filename*=UTF-8''",1)[1])=='測試-source.pdf'
    assert response.headers['cache-control']=='no-store' and response.headers['x-content-type-options']=='nosniff'


@pytest.mark.asyncio
async def test_document_binary_download_has_an_actual_binary_api_contract(client):
    _,app,_=client
    response_schema=app.openapi()['paths']['/v1/documents/{document_id}/content/{variant}']['get']['responses']['200']['content']
    assert 'application/pdf' in response_schema and 'application/json' not in response_schema


def checkbox_pdf():
    from pypdf.generic import ArrayObject,DictionaryObject,DecodedStreamObject,FloatObject
    reader=PdfReader(io.BytesIO(form_pdf()));writer=PdfWriter();writer.clone_document_from_reader(reader)
    field=writer.root_object['/AcroForm']['/Fields'][0].get_object()
    states=DictionaryObject()
    for state in ['/Off','/Accepted']:
        stream=DecodedStreamObject();stream.set_data(b'q Q')
        stream.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),
            NameObject('/BBox'):ArrayObject([FloatObject(0),FloatObject(0),FloatObject(20),FloatObject(20)])})
        states[NameObject(state)]=writer._add_object(stream)
    field.update({NameObject('/FT'):NameObject('/Btn'),NameObject('/Ff'):NumberObject(2),
        NameObject('/V'):NameObject('/Off'),NameObject('/AS'):NameObject('/Off'),
        NameObject('/AP'):DictionaryObject({NameObject('/N'):states})})
    output=io.BytesIO();writer.write(output);return output.getvalue()


@pytest.mark.parametrize('checked',[False,True])
def test_real_checkbox_values_and_custom_on_state_are_preserved(checked):
    source=checkbox_pdf();before=inspect_pdf(source).fields[0]
    assert before.required is True and before.on_value=='/Accepted'
    output,_=fill_pdf(source,{'owner_name':checked})
    field=inspect_pdf(output).fields[0]
    assert field.value is checked and field.required is True
    assert str(PdfReader(io.BytesIO(output)).get_fields()['owner_name']['/V'])==('/Accepted' if checked else '/Off')


@pytest.mark.parametrize('value',[NumberObject(-1),NumberObject(2**32),TextStringObject('0')])
def test_invalid_flag_type_or_range_has_a_typed_refusal(value):
    with pytest.raises(PdfDocumentError,match='PDF_FIELD_FLAGS_INVALID'):inspect_pdf(with_flags(value))


def malformed_page_tree():
    writer=PdfWriter();writer.add_blank_page(width=100,height=100)
    writer.root_object['/Pages'].get_object()[NameObject('/Kids')]=NameObject('/NotAnArray')
    output=io.BytesIO();writer.write(output);return output.getvalue()


def test_syntactically_valid_pdf_with_a_bad_page_tree_is_a_typed_refusal():
    try:result=inspect_pdf(malformed_page_tree())
    except Exception as exc:result=exc
    assert isinstance(result,PdfDocumentError),f'untyped corrupt-input outcome: {type(result).__name__}'


@pytest.mark.asyncio
async def test_failed_writer_postcondition_never_publishes_filled_status_or_artifact(tmp_path,monkeypatch):
    from van_gateway.storage.db import Store
    from van_gateway.artifacts.service import ArtifactService
    from van_gateway.documents.service import DocumentService,DocumentServiceError
    store=Store(str(tmp_path/'docs.sqlite'));await store.migrate();service=DocumentService(store,ArtifactService(store))
    doc=await service.import_pdf(filename='form.pdf',data=form_pdf())
    monkeypatch.setattr(PdfWriter,'update_page_form_field_values',lambda *args,**kwargs:None)
    with pytest.raises(DocumentServiceError,match='PDF_FIELD_POSTCONDITION_FAILED'):
        await service.fill(doc.document_id,{'owner_name':'Expected result'})
    current=await service.get(doc.document_id)
    assert current.status.value=='IMPORTED' and current.output_artifact_id is None
    assert len(await store.fetchall('SELECT * FROM owner_artifacts'))==1
    assert not list(service.root.glob('*.filled-*'))


@pytest.mark.asyncio
async def test_corrupt_page_tree_has_a_refused_gateway_outcome_without_publication(client):
    ac,app,_=client;await _pair_for_test(ac,app,'dev-pdf','fixture-document-device-secret')
    response=await ac.post('/v1/documents/import',files={'file':('broken.pdf',malformed_page_tree(),'application/pdf')})
    assert response.status_code==422 and response.json()['detail']=='PDF_INVALID'
    assert not await app.state.store.fetchall('SELECT * FROM documents')
    assert not await app.state.store.fetchall("SELECT * FROM owner_artifacts WHERE canonical_source_type LIKE 'document.%'")


@pytest.mark.asyncio
async def test_gateway_refuses_a_false_writer_success_without_claiming_a_filled_document(client,monkeypatch):
    ac,app,hermes=client;await _pair_for_test(ac,app,'dev-pdf','fixture-document-device-secret')
    response=await ac.post('/v1/documents/import',files={'file':('owner.pdf',form_pdf(),'application/pdf')})
    assert response.status_code==200,response.text
    did=response.json()['document_id']
    monkeypatch.setattr(PdfWriter,'update_page_form_field_values',lambda *args,**kwargs:None)
    response=await ac.post(f'/v1/documents/{did}/fill',json={'values':{'owner_name':'Expected result'}})
    assert response.status_code==409 and response.json()['detail']=='PDF_FIELD_POSTCONDITION_FAILED'
    record=(await ac.get(f'/v1/documents/{did}')).json()
    assert record['status']=='IMPORTED' and record['output_artifact_id'] is None
    response=await ac.get(f'/v1/documents/{did}/content/output')
    assert response.status_code==409 and response.json()['detail']=='DOCUMENT_OUTPUT_UNAVAILABLE'
    assert hermes['create_run']==0


@pytest.mark.asyncio
async def test_download_variant_contract_has_only_the_supported_owner_variants(client):
    _,app,_=client;operation=app.openapi()['paths']['/v1/documents/{document_id}/content/{variant}']['get']
    parameter=next(p for p in operation['parameters'] if p['name']=='variant')
    assert set(parameter['schema'].get('enum',[]))=={'source','output'}


def test_pdf_postcondition_rejects_a_nonempty_but_wrong_value(monkeypatch):
    update=PdfWriter.update_page_form_field_values
    def wrong(self,page,fields,*args,**kwargs):return update(self,page,{'owner_name':'Wrong value'},*args,**kwargs)
    monkeypatch.setattr(PdfWriter,'update_page_form_field_values',wrong)
    with pytest.raises(PdfDocumentError,match='PDF_FIELD_POSTCONDITION_FAILED'):
        fill_pdf(form_pdf(),{'owner_name':'Expected value'})
