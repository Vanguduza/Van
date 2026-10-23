"""Document metadata, immutable artifacts and owner edits form one publication."""
import asyncio
import io
from pathlib import Path
from pypdf import PdfReader,PdfWriter
from pypdf.generic import ArrayObject,DictionaryObject,FloatObject,NameObject,TextStringObject
import pytest
from test_document_fabric import form_pdf
from van_gateway.artifacts.service import ArtifactService
from van_gateway.documents.service import DocumentService
from van_gateway.storage.db import Store


async def service(tmp_path):
    store=Store(str(tmp_path/'docs.sqlite'));await store.migrate()
    return DocumentService(store,ArtifactService(store))


def two_fields():
    reader=PdfReader(io.BytesIO(form_pdf()));writer=PdfWriter();writer.clone_document_from_reader(reader)
    acro=writer.root_object['/AcroForm'];first=acro['/Fields'][0].get_object()
    second=DictionaryObject(dict(first));second[NameObject('/T')]=TextStringObject('owner_email')
    second[NameObject('/Rect')]=ArrayObject([FloatObject(20),FloatObject(50),FloatObject(220),FloatObject(80)])
    ref=writer._add_object(second);acro['/Fields'].append(ref);writer.pages[0]['/Annots'].append(ref)
    output=io.BytesIO();writer.write(output);return output.getvalue()


@pytest.mark.asyncio
async def test_failed_import_does_not_leave_a_published_artifact_or_unowned_pdf(tmp_path):
    s=await service(tmp_path)
    await s.store.execute("CREATE TRIGGER fixture_no_document BEFORE INSERT ON documents BEGIN SELECT RAISE(ABORT,'document unavailable'); END")
    with pytest.raises(Exception,match='document unavailable'):
        await s.import_pdf(filename='owner.pdf',data=form_pdf())
    assert not await s.store.fetchall('SELECT * FROM documents')
    artifacts=await s.store.fetchall('SELECT * FROM owner_artifacts')
    assert (len(artifacts),len(list(s.root.glob('*.pdf'))))==(0,0)


@pytest.mark.asyncio
async def test_failed_fill_does_not_leave_an_output_artifact_or_orphaned_copy(tmp_path):
    s=await service(tmp_path);doc=await s.import_pdf(filename='owner.pdf',data=form_pdf())
    await s.store.execute("CREATE TRIGGER fixture_no_output BEFORE UPDATE ON documents BEGIN SELECT RAISE(ABORT,'output unavailable'); END")
    with pytest.raises(Exception,match='output unavailable'):
        await s.fill(doc.document_id,{'owner_name':'Owner'})
    current=await s.get(doc.document_id)
    assert current.status.value=='IMPORTED' and current.output_artifact_id is None
    artifacts=await s.store.fetchall('SELECT * FROM owner_artifacts')
    assert (len(artifacts),len(list(s.root.glob('*.pdf'))))==(1,1)


@pytest.mark.asyncio
async def test_replaying_identical_canonical_output_reuses_its_original_result_card(tmp_path):
    s=await service(tmp_path);doc=await s.import_pdf(filename='owner.pdf',data=form_pdf())
    first=await s.fill(doc.document_id,{'owner_name':'Owner'})
    second=await s.fill(doc.document_id,{'owner_name':'Owner'})
    assert first.output_sha256==second.output_sha256
    assert first.output_artifact_id==second.output_artifact_id
    assert len(await s.store.fetchall('SELECT * FROM owner_artifacts'))==2


@pytest.mark.asyncio
async def test_later_partial_fill_preserves_owner_values_already_written(tmp_path):
    s=await service(tmp_path);doc=await s.import_pdf(filename='owner.pdf',data=two_fields())
    await s.fill(doc.document_id,{'owner_name':'Owner'})
    await s.fill(doc.document_id,{'owner_email':'owner@example.com'})
    data,_=await s.bytes_for(doc.document_id,'output');fields=PdfReader(io.BytesIO(data)).get_fields()
    assert (str(fields['owner_name']['/V']),str(fields['owner_email']['/V']))==('Owner','owner@example.com')
    proposal=await s.propose_fill(doc.document_id,{})
    assert proposal.proposed_values['owner_name']=='Owner' and proposal.proposed_values['owner_email']=='owner@example.com'


@pytest.mark.asyncio
async def test_old_and_new_output_artifacts_do_not_share_a_mutable_byte_reference(tmp_path):
    s=await service(tmp_path);doc=await s.import_pdf(filename='owner.pdf',data=form_pdf())
    first=await s.fill(doc.document_id,{'owner_name':'First'})
    old=await s.artifacts.get(first.output_artifact_id)
    second=await s.fill(doc.document_id,{'owner_name':'Second'})
    new=await s.artifacts.get(second.output_artifact_id)
    assert old.canonical_source_digest!=new.canonical_source_digest
    assert old.content_ref!=new.content_ref,'one immutable artifact reference was retargeted by a later fill'


@pytest.mark.asyncio
async def test_concurrent_partial_fills_preserve_both_independent_owner_edits(tmp_path):
    s=await service(tmp_path);doc=await s.import_pdf(filename='owner.pdf',data=two_fields())
    outcomes=await asyncio.gather(s.fill(doc.document_id,{'owner_name':'Owner'}),
        s.fill(doc.document_id,{'owner_email':'owner@example.com'}),return_exceptions=True)
    assert all(not isinstance(outcome,Exception) for outcome in outcomes),[type(outcome).__name__ for outcome in outcomes]
    data,_=await s.bytes_for(doc.document_id,'output');fields=PdfReader(io.BytesIO(data)).get_fields()
    assert (str(fields['owner_name']['/V']),str(fields['owner_email']['/V']))==('Owner','owner@example.com')


@pytest.mark.asyncio
async def test_concurrent_canonical_artifact_publishers_share_one_identity(tmp_path):
    from van_gateway.artifacts.models import ArtifactKind
    s=await service(tmp_path)
    async def publish():
        return await s.artifacts.ensure_projection(kind=ArtifactKind.REPORT,title='Canonical result',
            canonical_source_type='mission.outcome',canonical_source_id='mission-real-source',canonical_source_digest='a'*64)
    results=await asyncio.gather(*(publish() for _ in range(4)),return_exceptions=True)
    assert all(not isinstance(result,Exception) for result in results),[type(result).__name__ for result in results]
    assert len({result.artifact_id for result in results})==1
    assert len(await s.store.fetchall('SELECT * FROM owner_artifacts'))==1


@pytest.mark.asyncio
async def test_projection_lookup_cannot_adopt_a_different_owners_private_artifact(tmp_path):
    from van_gateway.artifacts.models import ArtifactKind
    s=await service(tmp_path)
    async def publish(owner):
        return await s.artifacts.ensure_projection(kind=ArtifactKind.REPORT,title='Private result',owner_id=owner,
            canonical_source_type='source.bound',canonical_source_id='same-source',canonical_source_digest='b'*64)
    first=await publish('owner-alpha');second=await publish('owner-beta')
    assert first.owner_id=='owner-alpha' and second.owner_id=='owner-beta'
    assert first.artifact_id!=second.artifact_id


@pytest.mark.asyncio
async def test_exact_old_version_readback_never_returns_the_latest_copy(tmp_path):
    s=await service(tmp_path);doc=await s.import_pdf(filename='owner.pdf',data=form_pdf())
    first=await s.fill(doc.document_id,{'owner_name':'First'})
    second=await s.fill(doc.document_id,{'owner_name':'Second'})
    old,_=await s.bytes_for(doc.document_id,'output',sha256=first.output_sha256)
    latest,_=await s.bytes_for(doc.document_id,'output')
    assert str(PdfReader(io.BytesIO(old)).get_fields()['owner_name']['/V'])=='First'
    assert str(PdfReader(io.BytesIO(latest)).get_fields()['owner_name']['/V'])=='Second'
    assert s._sha(old)==first.output_sha256 and s._sha(latest)==second.output_sha256
    assert doc.source_sha256==(await s.get(doc.document_id)).source_sha256


@pytest.mark.asyncio
async def test_stale_owner_review_cannot_overwrite_a_later_edit(tmp_path):
    from van_gateway.documents.service import DocumentServiceError
    s=await service(tmp_path);doc=await s.import_pdf(filename='owner.pdf',data=two_fields())
    review=await s.propose_fill(doc.document_id,{'owner_name':'Reviewed'})
    await s.fill(doc.document_id,{'owner_email':'later@example.com'})
    with pytest.raises(DocumentServiceError,match='DOCUMENT_PROPOSAL_STALE'):
        await s.fill(doc.document_id,{'owner_name':'Reviewed'},expected_proposal_sha256=review.proposal_sha256)
    current,_=await s.bytes_for(doc.document_id,'output')
    assert str(PdfReader(io.BytesIO(current)).get_fields()['owner_email']['/V'])=='later@example.com'
    fresh=await s.propose_fill(doc.document_id,{'owner_name':'Reviewed'})
    assert fresh.baseline_sha256!=review.baseline_sha256
    await s.fill(doc.document_id,{'owner_name':'Reviewed'},expected_proposal_sha256=fresh.proposal_sha256)


@pytest.mark.asyncio
async def test_legacy_short_hash_version_remains_readable_with_exact_digest(tmp_path):
    s=await service(tmp_path);doc=await s.import_pdf(filename='owner.pdf',data=form_pdf())
    first=await s.fill(doc.document_id,{'owner_name':'First'});await s.fill(doc.document_id,{'owner_name':'Second'})
    full=s._path(doc.document_id,'filled-'+first.output_sha256)
    legacy=s._path(doc.document_id,'filled-'+first.output_sha256[:16]);full.rename(legacy)
    await s.store.execute('UPDATE owner_artifacts SET content_ref=? WHERE artifact_id=?',
        ('document:'+doc.document_id+':output',first.output_artifact_id))
    data,_=await s.bytes_for(doc.document_id,'output',sha256=first.output_sha256)
    assert s._sha(data)==first.output_sha256 and str(PdfReader(io.BytesIO(data)).get_fields()['owner_name']['/V'])=='First'


@pytest.mark.asyncio
async def test_missing_or_expired_old_version_is_not_replaced_by_current_bytes(tmp_path):
    from van_gateway.documents.service import DocumentServiceError
    s=await service(tmp_path);doc=await s.import_pdf(filename='owner.pdf',data=form_pdf())
    first=await s.fill(doc.document_id,{'owner_name':'First'});await s.fill(doc.document_id,{'owner_name':'Second'})
    await s.store.execute('UPDATE owner_artifacts SET expires_at_ms=1 WHERE artifact_id=?',(first.output_artifact_id,))
    with pytest.raises(DocumentServiceError,match='DOCUMENT_VERSION_EXPIRED'):
        await s.bytes_for(doc.document_id,'output',sha256=first.output_sha256)
    await s.store.execute('UPDATE owner_artifacts SET expires_at_ms=NULL WHERE artifact_id=?',(first.output_artifact_id,))
    s._path(doc.document_id,'filled-'+first.output_sha256).unlink()
    with pytest.raises(DocumentServiceError,match='DOCUMENT_BYTES_MISSING'):
        await s.bytes_for(doc.document_id,'output',sha256=first.output_sha256)
    data,_=await s.bytes_for(doc.document_id,'output')
    assert str(PdfReader(io.BytesIO(data)).get_fields()['owner_name']['/V'])=='Second'


@pytest.mark.asyncio
async def test_expired_current_copy_cannot_be_used_to_revive_retained_values(tmp_path):
    from van_gateway.documents.service import DocumentServiceError
    s=await service(tmp_path);doc=await s.import_pdf(filename='owner.pdf',data=two_fields())
    filled=await s.fill(doc.document_id,{'owner_name':'Expired value'})
    await s.store.execute('UPDATE owner_artifacts SET expires_at_ms=1 WHERE artifact_id=?',(filled.output_artifact_id,))
    with pytest.raises(DocumentServiceError,match='DOCUMENT_VERSION_EXPIRED'):
        await s.propose_fill(doc.document_id,{'owner_email':'new@example.com'})
    with pytest.raises(DocumentServiceError,match='DOCUMENT_VERSION_EXPIRED'):
        await s.fill(doc.document_id,{'owner_email':'new@example.com'})
    assert len(await s.store.fetchall('SELECT * FROM owner_artifacts'))==2


@pytest.mark.asyncio
@pytest.mark.parametrize('applied',[False,True])
async def test_native_commit_refusal_or_lost_ack_has_an_observed_publication_outcome(tmp_path,monkeypatch,applied):
    from contextlib import asynccontextmanager
    s=await service(tmp_path);doc=await s.import_pdf(filename='owner.pdf',data=form_pdf());connection=s.store.connection;failed=False
    class Connection:
        def __init__(self,db):self.db=db
        def __getattr__(self,name):return getattr(self.db,name)
        async def commit(self):
            nonlocal failed
            if not failed:
                failed=True
                if applied:await self.db.commit()
                raise RuntimeError('native commit acknowledgement unavailable')
            await self.db.commit()
    @asynccontextmanager
    async def wrapped():
        async with connection() as db:yield Connection(db)
    monkeypatch.setattr(s.store,'connection',wrapped)
    if applied:
        result=await s.fill(doc.document_id,{'owner_name':'Committed'})
        assert result.status.value=='FILLED'
        data,_=await s.bytes_for(doc.document_id,'output',sha256=result.output_sha256)
        assert str(PdfReader(io.BytesIO(data)).get_fields()['owner_name']['/V'])=='Committed'
    else:
        with pytest.raises(RuntimeError,match='native commit acknowledgement unavailable'):
            await s.fill(doc.document_id,{'owner_name':'Not committed'})
        current=await s.get(doc.document_id)
        assert current.status.value=='IMPORTED' and current.output_sha256 is None
    assert failed
    expected=2 if applied else 1
    assert len(await s.store.fetchall('SELECT * FROM owner_artifacts'))==expected
    assert len(list(s.root.glob('*.pdf')))==expected


@pytest.mark.asyncio
async def test_lost_ack_returns_original_version_even_after_another_writer_commits(tmp_path,monkeypatch):
    from contextlib import asynccontextmanager
    s=await service(tmp_path);doc=await s.import_pdf(filename='owner.pdf',data=form_pdf());connection=s.store.connection;failed=False;second=None
    class Connection:
        def __init__(self,db):self.db=db
        def __getattr__(self,name):return getattr(self.db,name)
        async def commit(self):
            nonlocal failed,second
            await self.db.commit()
            if not failed:
                failed=True
                second=await s.fill(doc.document_id,{'owner_name':'Second writer'})
                raise RuntimeError('first writer lost commit acknowledgement')
    @asynccontextmanager
    async def wrapped():
        async with connection() as db:yield Connection(db)
    monkeypatch.setattr(s.store,'connection',wrapped)
    first=await s.fill(doc.document_id,{'owner_name':'First writer'})
    assert first.output_sha256!=second.output_sha256
    assert (await s.get(doc.document_id)).output_sha256==second.output_sha256
    data,_=await s.bytes_for(doc.document_id,'output',sha256=first.output_sha256)
    assert str(PdfReader(io.BytesIO(data)).get_fields()['owner_name']['/V'])=='First writer'


@pytest.mark.asyncio
async def test_unknown_commit_readback_preserves_bytes_and_reports_uncertainty(tmp_path,monkeypatch):
    from contextlib import asynccontextmanager
    from van_gateway.documents.service import DocumentServiceError
    s=await service(tmp_path);doc=await s.import_pdf(filename='owner.pdf',data=form_pdf());connection=s.store.connection;fetchone=s.store.fetchone;failed=False
    class Connection:
        def __init__(self,db):self.db=db
        def __getattr__(self,name):return getattr(self.db,name)
        async def commit(self):
            nonlocal failed
            await self.db.commit()
            if not failed:
                failed=True;raise RuntimeError('lost commit acknowledgement')
    @asynccontextmanager
    async def wrapped():
        async with connection() as db:yield Connection(db)
    async def unavailable(sql,*args):
        if 'SELECT value FROM runtime_meta' in sql:raise RuntimeError('native readback unavailable')
        return await fetchone(sql,*args)
    monkeypatch.setattr(s.store,'connection',wrapped);monkeypatch.setattr(s.store,'fetchone',unavailable)
    with pytest.raises(DocumentServiceError,match='DOCUMENT_PUBLICATION_UNKNOWN') as caught:
        await s.fill(doc.document_id,{'owner_name':'Committed without acknowledgement'})
    assert caught.value.document_id==doc.document_id and caught.value.publication_id.startswith('document_publication:')
    current=await s.get(doc.document_id)
    assert current.status.value=='FILLED' and len(list(s.root.glob('*.pdf')))==2
    assert len(await s.store.fetchall('SELECT * FROM owner_artifacts'))==2


@pytest.mark.asyncio
async def test_rollback_of_identical_replay_does_not_delete_an_existing_version(tmp_path):
    s=await service(tmp_path);doc=await s.import_pdf(filename='owner.pdf',data=form_pdf())
    first=await s.fill(doc.document_id,{'owner_name':'Preserve this'})
    await s.store.execute("CREATE TRIGGER fixture_no_replay BEFORE UPDATE ON documents BEGIN SELECT RAISE(ABORT,'replay refused'); END")
    with pytest.raises(Exception,match='replay refused'):
        await s.fill(doc.document_id,{'owner_name':'Preserve this'})
    stored=await s.store.fetchone('SELECT output_path FROM documents WHERE document_id=?',(doc.document_id,))
    assert Path(stored['output_path']).is_file(),'failed replay destroyed the original published bytes'
    data,_=await s.bytes_for(doc.document_id,'output',sha256=first.output_sha256)
    assert str(PdfReader(io.BytesIO(data)).get_fields()['owner_name']['/V'])=='Preserve this'
    assert len(await s.store.fetchall('SELECT * FROM owner_artifacts'))==2


@pytest.mark.asyncio
@pytest.mark.parametrize('operation',['import','fill'])
async def test_actual_task_cancellation_before_commit_rolls_back_metadata_and_new_bytes(tmp_path,monkeypatch,operation):
    s=await service(tmp_path);doc=await s.import_pdf(filename='source.pdf',data=form_pdf()) if operation=='fill' else None
    entered=asyncio.Event();blocked=asyncio.Event()
    method='create' if operation=='import' else 'ensure_projection';original=getattr(s.artifacts,method)
    async def pause(**kwargs):
        result=await original(**kwargs)
        entered.set();await blocked.wait()
        return result
    monkeypatch.setattr(s.artifacts,method,pause)
    coro=s.import_pdf(filename='owner.pdf',data=form_pdf()) if operation=='import' else s.fill(doc.document_id,{'owner_name':'Cancelled pending commit'})
    task=asyncio.create_task(coro)
    await asyncio.wait_for(entered.wait(),5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    expected=0 if operation=='import' else 1
    assert len(await s.store.fetchall('SELECT * FROM owner_artifacts'))==expected
    assert len(list(s.root.glob('*.pdf')))==expected
    assert not list(s.root.glob('.document-*'))
    if doc is not None:assert (await s.get(doc.document_id)).status.value=='IMPORTED'


@pytest.mark.asyncio
async def test_canonical_artifact_publication_excludes_a_real_read_write_interleaving(tmp_path,monkeypatch):
    import sqlite3
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from van_gateway.artifacts.models import ArtifactKind
    s=await service(tmp_path);connection=s.store.connection;attempted=committed=False
    @asynccontextmanager
    async def interleaved():
        async with connection() as db:
            async def execute(sql,params=()):
                cursor=await db.execute(sql,params)
                if 'FROM owner_artifacts' not in sql or 'canonical_source_type = ?' not in sql:return cursor
                async def fetchone():
                    nonlocal attempted,committed
                    row=await cursor.fetchone()
                    if not attempted:
                        attempted=True
                        with sqlite3.connect(s.store.path,timeout=0) as competitor:
                            try:
                                competitor.execute("INSERT INTO owner_artifacts(artifact_id,owner_id,kind,title,canonical_source_type,canonical_source_id,canonical_source_digest,created_at_ms) VALUES('native-competing-card','owner','REPORT','Same canonical result','source.canonical','result-one',?,2000)",('d'*64,))
                                competitor.commit();committed=True
                            except sqlite3.OperationalError as exc:assert 'locked' in str(exc)
                    return row
                return SimpleNamespace(fetchone=fetchone)
            class Connection:
                def __getattr__(self,name):return getattr(db,name)
                async def execute(self,sql,params=()):return await execute(sql,params)
            yield Connection()
    monkeypatch.setattr(s.store,'connection',interleaved)
    try:
        result=await s.artifacts.ensure_projection(kind=ArtifactKind.REPORT,title='Same canonical result',
            canonical_source_type='source.canonical',canonical_source_id='result-one',canonical_source_digest='d'*64)
    except Exception as exc:result=exc
    assert attempted and not isinstance(result,Exception),f'canonical publication failed: {type(result).__name__}'
    if not committed:
        other=await s.artifacts.ensure_projection(kind=ArtifactKind.REPORT,title='Same canonical result',
            canonical_source_type='source.canonical',canonical_source_id='result-one',canonical_source_digest='d'*64)
        assert other.artifact_id==result.artifact_id
    rows=await s.store.fetchall('SELECT artifact_id FROM owner_artifacts')
    assert len(rows)==1 and rows[0]['artifact_id']==result.artifact_id


@pytest.mark.asyncio
async def test_explicit_empty_required_value_is_still_reported_missing(tmp_path):
    from test_document_value_integrity import with_flags
    from pypdf.generic import NumberObject
    s=await service(tmp_path);doc=await s.import_pdf(filename='required.pdf',data=with_flags(NumberObject(2)))
    review=await s.propose_fill(doc.document_id,{'owner_name':''})
    assert 'owner_name' in review.missing_fields
    assert review.model_dump().get('missing_required_fields')==['owner_name']


@pytest.mark.asyncio
async def test_restricted_artifact_projection_is_not_adopted_as_private_content(tmp_path):
    from van_gateway.artifacts.models import ArtifactKind,ArtifactSensitivity
    from van_gateway.artifacts.service import ArtifactServiceError
    s=await service(tmp_path)
    await s.artifacts.create(kind=ArtifactKind.PDF,title='Opaque secret reference',
        canonical_source_type='source.protected',canonical_source_id='protected',canonical_source_digest='e'*64,
        sensitivity=ArtifactSensitivity.SECRET_REF_ONLY)
    with pytest.raises(ArtifactServiceError,match='artifact_projection_sensitivity_conflict'):
        await s.artifacts.ensure_projection(kind=ArtifactKind.PDF,title='Publicly usable file',
            canonical_source_type='source.protected',canonical_source_id='protected',canonical_source_digest='e'*64,
            content_ref='document:protected:output')


@pytest.mark.asyncio
async def test_document_version_cannot_bypass_secret_reference_only_policy(tmp_path):
    from van_gateway.documents.service import DocumentServiceError
    s=await service(tmp_path);doc=await s.import_pdf(filename='owner.pdf',data=form_pdf())
    filled=await s.fill(doc.document_id,{'owner_name':'Protected field'})
    await s.store.execute("UPDATE owner_artifacts SET sensitivity='SECRET_REF_ONLY',content_ref=NULL WHERE artifact_id=?",(filled.output_artifact_id,))
    with pytest.raises(DocumentServiceError,match='DOCUMENT_VERSION_RESTRICTED'):
        await s.bytes_for(doc.document_id,'output',sha256=filled.output_sha256)
    with pytest.raises(DocumentServiceError,match='DOCUMENT_VERSION_RESTRICTED'):
        await s.fill(doc.document_id,{'owner_name':'Cannot revive protected content'})
