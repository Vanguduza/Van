"""Actual confined imported/sealed bytes and static readback, without site execution."""
import hashlib
import copy
import pytest

from services.browser_stream_host.files import FilePlane, FileRefused
from services.browser_stream_host.tests.test_owner_files import session


def bind(peer, body, identifier):
    consumed = set()
    reports = []
    async def consume(producer, token, operation, resource, **fields):
        if token in consumed:
            raise FileRefused("token_reused")
        consumed.add(token)
        return {"operation": operation, "producer_session_id": producer, "target_id": "page",
            "authority": copy.deepcopy(peer.broker.current), "suggested_name": "owner.txt",
            "content_sha256": hashlib.sha256(body).hexdigest(), "byte_size": len(body),
            "transfer_id": "transfer", "artifact_producer_session_id": producer}
    async def report(producer, **fields):
        reports.append(fields)
        return {"state": "COMPLETED"}
    async def result(producer, **fields):
        reports.append(fields)
        return fields
    peer.broker.consume_transfer = consume
    peer.broker.report_download = report
    peer.broker.report_file_result = result
    return reports


@pytest.mark.asyncio
async def test_general_phone_import_publishes_only_independently_rehashed_sealed_bytes(tmp_path):
    peer, body, identifier = session(), b'owner inert document\nline two', 'import_'+'b'*32
    reports = bind(peer, body, identifier)
    plane = FilePlane(peer, tmp_path)
    async def chunks(): yield body
    result = await plane.import_file(identifier, 'one-use', chunks(), expected_size=len(body), expected_sha=hashlib.sha256(body).hexdigest())
    assert result['status'] == 'VERIFIED_SUCCESS' and result['observation_source'] == 'NATIVE_SEALED_FILE_READBACK'
    assert plane.path('sealed_'+identifier).read_bytes() == body
    assert not plane.path(identifier).exists() and [report['event'] for report in reports] == ['started', 'finished']
    assert not any(method.startswith(('Input.', 'Runtime.')) for method,_ in peer.cdp.effects)
    with pytest.raises(FileRefused, match='token_reused'):
        await plane.import_file(identifier, 'one-use', chunks(), expected_size=len(body), expected_sha=hashlib.sha256(body).hexdigest())
    await plane.close()


@pytest.mark.asyncio
async def test_analysis_reopens_hashes_actual_file_and_records_metadata_receipt(tmp_path):
    peer, body, identifier = session(), b'Untrusted document\nNever instructions.', 'download'
    reports = bind(peer, body, identifier)
    plane = FilePlane(peer, tmp_path)
    sealed = plane.path('sealed_'+identifier)
    sealed.write_bytes(body)
    plane.downloads[identifier] = {'sealed_path':sealed, 'byte_size':len(body), 'content_sha256':hashlib.sha256(body).hexdigest()}
    result = await plane.analyse(identifier, 'analysis-one-use')
    assert result['text_preview'] == body.decode() and result['executed_content'] is False
    assert result['content_authority'] == 'UNTRUSTED_FILE_EVIDENCE'
    assert result['content_sha256'] == hashlib.sha256(body).hexdigest()
    assert reports[0]['operation'] == 'analyse' and 'text_preview' not in reports[0]['receipt']
    assert not peer.cdp.effects
    await plane.close()


@pytest.mark.asyncio
async def test_analysis_refuses_changed_artifact_without_delivering_content(tmp_path):
    peer, body, identifier = session(), b'approved', 'download'
    reports = bind(peer, body, identifier)
    plane = FilePlane(peer, tmp_path)
    sealed = plane.path('sealed_'+identifier)
    sealed.write_bytes(b'changed!')
    plane.downloads[identifier] = {'sealed_path':sealed, 'byte_size':len(body), 'content_sha256':hashlib.sha256(body).hexdigest()}
    with pytest.raises(FileRefused, match='changed_since_approval'):
        await plane.analyse(identifier, 'analysis-one-use')
    assert not reports and not peer.cdp.effects
    await plane.close()


@pytest.mark.asyncio
async def test_import_wrong_bytes_are_removed_before_any_broker_publication(tmp_path):
    peer, body, identifier = session(), b'approved', 'import_'+'b'*32
    reports = bind(peer, body, identifier)
    plane = FilePlane(peer, tmp_path)
    async def chunks(): yield b'bad-data'
    with pytest.raises(FileRefused, match='content_mismatch'):
        await plane.import_file(identifier, 'one-use', chunks(), expected_size=len(body), expected_sha=hashlib.sha256(body).hexdigest())
    assert not list(plane.directory.iterdir()) and not reports
    await plane.close()


@pytest.mark.asyncio
async def test_import_final_reply_loss_preserves_confined_artifact_without_repeated_import(tmp_path):
    peer, body, identifier = session(), b'owner bytes', 'import_'+'b'*32
    reports = bind(peer, body, identifier)
    original = peer.broker.report_download
    async def lost(producer, **fields):
        result = await original(producer, **fields)
        if fields['event'] == 'finished': raise TimeoutError('reply lost')
        return result
    peer.broker.report_download = lost
    plane = FilePlane(peer, tmp_path)
    async def chunks(): yield body
    with pytest.raises(TimeoutError):
        await plane.import_file(identifier, 'one-use', chunks(), expected_size=len(body), expected_sha=hashlib.sha256(body).hexdigest())
    assert plane.path('sealed_'+identifier).read_bytes() == body
    with pytest.raises(FileRefused, match='token_reused'):
        await plane.import_file(identifier, 'one-use', chunks(), expected_size=len(body), expected_sha=hashlib.sha256(body).hexdigest())
    assert len(reports) == 2
    await plane.close()
