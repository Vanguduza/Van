"""Confined actual file bytes, hash receipts and delayed-transfer authority regressions."""
import asyncio
import copy
import hashlib
import os
import time
from types import SimpleNamespace

import pytest
from services.browser_stream_host.files import FilePlane, FileRefused
from services.browser_stream_host.tests.test_native_stream import authority


class Broker:
    def __init__(self, current):
        self.current = current
        self.reports = []
        self.consumed = set()
    async def authority(self, producer):
        return copy.deepcopy(self.current)
    async def authorize_input(self, producer, supplied):
        assert supplied.control_lease_id == self.current['control_lease_id']
        if self.current['control_expires_at_ms'] <= int(time.time()*1000):
            raise FileRefused('current_lease_expired')
        return copy.deepcopy(self.current)
    async def consume_transfer(self, producer, token, operation, resource, **fields):
        if token in self.consumed:
            raise FileRefused('token_reused')
        self.consumed.add(token)
        return {'operation': operation, 'producer_session_id': producer, 'target_id': 'page',
                'authority': copy.deepcopy(self.current), 'suggested_name': 'owner.txt', **fields}
    async def report_download(self, producer, **fields):
        self.reports.append(fields)
        return {}


class Browser:
    def __init__(self):
        self.effects = []
    async def send(self, target, method, params):
        self.effects.append((method, params))
        if method == 'Page.getFrameTree':
            return {'frameTree': {'frame': {'id': 'frame'}}}
        if method == 'Page.createIsolatedWorld':
            return {'executionContextId': 7}
        if method == 'Runtime.evaluate':
            return {'result': {'value': 'owner selection'}}
        return {}
    async def _command(self, method, params):
        self.effects.append((method, params))
        return {}


def session():
    current = authority()
    browser, broker = Browser(), Broker(current)
    result = SimpleNamespace(producer_id='prod_'+'a'*32, session_id='ibs_test', target_id='page', owner_device_id='phone',
                             control_generation=1, viewport=current['viewport'], broker=broker, cdp=browser,
                             emit=lambda *args, **kwargs: None)
    def binding(value):
        if value['control_generation'] != 1 or value['viewport']['revision'] != 1:
            raise FileRefused('current_binding_changed')
    result.check_binding = binding
    return result


@pytest.mark.asyncio
async def test_upload_attaches_real_confined_bytes_only_after_current_owner_fence(tmp_path):
    peer = session()
    plane = FilePlane(peer, tmp_path)
    plane.choosers['choose_real'] = {'backend_node_id': 17, 'expires_at': asyncio.get_running_loop().time()+60, 'generation':1}
    body = b'owner approved file'
    async def chunks():
        yield body
    receipt = await plane.upload('choose_real', 'oneuse', chunks(), expected_size=len(body), expected_sha=hashlib.sha256(body).hexdigest())
    assert receipt['attached'] is True and receipt['target_id'] == 'page'
    calls = [params for method, params in peer.cdp.effects if method == 'DOM.setFileInputFiles']
    assert len(calls) == 1
    assert calls[0]['backendNodeId'] == 17
    path = calls[0]['files'][0]
    assert str(tmp_path) in path and open(path,'rb').read() == body
    with pytest.raises(FileRefused):
        await plane.upload('choose_real', 'oneuse', chunks(), expected_size=len(body), expected_sha=hashlib.sha256(body).hexdigest())
    await plane.close()


@pytest.mark.asyncio
async def test_delayed_upload_control_expiry_never_attaches_and_cleans_bytes(tmp_path):
    peer = session()
    plane = FilePlane(peer, tmp_path)
    plane.choosers['choose_real'] = {'backend_node_id': 17, 'expires_at': asyncio.get_running_loop().time()+60, 'generation':1}
    body = b'owner approved file'
    async def chunks():
        yield body
        peer.broker.current['control_expires_at_ms'] = int(time.time()*1000)-1
    with pytest.raises(FileRefused, match='lease_expired'):
        await plane.upload('choose_real', 'oneuse', chunks(), expected_size=len(body), expected_sha=hashlib.sha256(body).hexdigest())
    assert not any(method == 'DOM.setFileInputFiles' for method, _ in peer.cdp.effects)
    assert list(plane.directory.iterdir()) == []
    await plane.close()


@pytest.mark.asyncio
async def test_upload_hash_mismatch_never_attaches(tmp_path):
    peer = session()
    plane = FilePlane(peer, tmp_path)
    plane.choosers['choose_real'] = {'backend_node_id':17,'expires_at':asyncio.get_running_loop().time()+60,'generation':1}
    async def chunks():
        yield b'wrong'
    with pytest.raises(FileRefused, match='content_mismatch'):
        await plane.upload('choose_real', 'grant', chunks(), expected_size=5, expected_sha='0'*64)
    assert not peer.cdp.effects
    await plane.close()


def test_sealed_download_uses_observed_bytes_and_cannot_follow_symlink(tmp_path):
    source = tmp_path / 'guid'
    destination = tmp_path / 'sealed_guid'
    body = b'%PDF-1.7 owner document'
    source.write_bytes(body)
    size, sha, mime = FilePlane.seal(source, destination)
    assert size == len(body) and sha == hashlib.sha256(body).hexdigest() and mime == 'application/pdf'
    assert destination.read_bytes() == body and os.stat(destination).st_mode & 0o777 == 0o400
    assert not source.exists()
    link = tmp_path / 'symlink'
    link.symlink_to(destination)
    with pytest.raises(OSError):
        FilePlane.describe(link)


@pytest.mark.asyncio
async def test_clipboard_copy_is_explicit_isolated_and_bounded(tmp_path):
    peer = session()
    plane = FilePlane(peer, tmp_path)
    result = await plane.clipboard('copy-grant', 'copy')
    assert result['text'] == 'owner selection'
    evaluate = next(params for method, params in peer.cdp.effects if method == 'Runtime.evaluate')
    assert evaluate['contextId'] == 7 and evaluate['timeout'] == 1000
    assert 'expression' in evaluate and 'getSelection' in evaluate['expression']
    with pytest.raises(FileRefused, match='token_reused'):
        await plane.clipboard('copy-grant', 'copy')
    await plane.close()


@pytest.mark.asyncio
async def test_host_clipboard_disable_and_oversize_paste_never_reads_or_actuates(tmp_path):
    peer = session()
    plane = FilePlane(peer, tmp_path, clipboard_enabled=False)
    with pytest.raises(FileRefused, match='disabled'):
        await plane.clipboard('grant', 'copy')
    assert not peer.cdp.effects and not peer.broker.consumed
    plane.clipboard_enabled = True
    with pytest.raises(FileRefused, match='size_limit'):
        await plane.clipboard('grant', 'paste', text='x'*65537)
    assert not peer.cdp.effects and not peer.broker.consumed
    await plane.close()
