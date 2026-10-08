"""One-use owner file/clipboard plane, confined to a deployment-bound quarantine.

CDP methods here are fixed internal conversations, never caller supplied method names,
paths, selectors or scripts. Grants are consumed by the current trusted broker first.
"""
from __future__ import annotations
import asyncio
import hashlib
import os
import re
import stat
import uuid
import time
from pathlib import Path

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_CLIPBOARD_BYTES = 64 * 1024
GUID = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


class FileRefused(Exception):
    pass


def observed_mime(head):
    if head.startswith(b'%PDF-'):
        return 'application/pdf'
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if head.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if head.startswith((b'MZ', b'\x7fELF', b'PK\x03\x04')):
        return 'application/octet-stream'
    try:
        text = head.decode('utf-8')
    except UnicodeDecodeError:
        return 'application/octet-stream'
    if '\x00' not in text:
        return 'text/plain'
    return 'application/octet-stream'


class FilePlane:
    def __init__(self, session, root, *, clipboard_enabled=True):
        self.session = session
        configured = Path(root)
        if not configured.is_absolute() or configured.is_symlink():
            raise FileRefused('file_quarantine_path_refused')
        self.root = configured.resolve(strict=True)
        if not self.root.is_dir() or self.root.is_symlink():
            raise FileRefused('file_quarantine_not_directory')
        self.directory = self.root / session.producer_id
        self.directory.mkdir(mode=0o1770)
        self.directory.chmod(0o1770)
        self.downloads = {}
        self.choosers = {}
        self.frame_ids = set()
        self.clipboard_enabled = clipboard_enabled
        self.tasks = set()
        self.closed = False
        self.deleted = set()
        self.import_lock = asyncio.Lock()

    def path(self, resource_id):
        if not GUID.fullmatch(resource_id):
            raise FileRefused('file_resource_id_invalid')
        path = self.directory / resource_id
        if path.parent != self.directory or path.is_symlink():
            raise FileRefused('file_path_refused')
        return path

    async def start(self):
        session = self.session
        tree = await session.cdp.send(session.target_id, 'Page.getFrameTree', {})
        def frames(node):
            identifier = node.get('frame', {}).get('id')
            if identifier:
                self.frame_ids.add(identifier)
            for child in node.get('childFrames', [])[:64]:
                frames(child)
        frames(tree.get('frameTree', {}))
        # Fixed quarantine generated from actual producer identity. This privileged CDP
        # conversation is not in the narrow automation agent's public operation allowlist.
        await session.cdp._command('Browser.setDownloadBehavior', {
            'behavior': 'allowAndName', 'downloadPath': str(self.directory), 'eventsEnabled': True,
        })
        await session.cdp.send(session.target_id, 'Page.setInterceptFileChooserDialog', {'enabled': True})

    def schedule(self, coroutine):
        if self.closed or len(self.tasks) >= 16:
            coroutine.close()
            return
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self._finished)
        return task

    def _finished(self, task):
        self.tasks.discard(task)
        if not task.cancelled():
            try:
                task.result()
            except Exception:
                self.session.emit('file.refused', reason='file_producer_event_refused')

    def event(self, event):
        session = self.session
        method = event.get('method')
        params = event.get('params', {})
        own_session = session.cdp._sessions.get(session.target_id) == event.get('sessionId')
        if method == 'Page.frameNavigated' and own_session:
            identifier = params.get('frame', {}).get('id')
            if identifier:
                self.frame_ids.add(identifier)
        if method == 'Browser.downloadWillBegin':
            identifier = params.get('guid', '')
            if not GUID.fullmatch(identifier):
                return
            if params.get('frameId') not in self.frame_ids or sum('sealed_path' not in value for value in self.downloads.values()) >= 16 or len(self.downloads) >= 128:
                self.schedule(session.cdp._command('Browser.cancelDownload', {'guid': identifier}))
                return
            self.downloads[identifier] = {'name': params.get('suggestedFilename', '')[:256], 'url_digest': hashlib.sha256(params.get('url', '').encode()).hexdigest(), 'reported': False}
            self.downloads[identifier]['started_task'] = self.schedule(self.report_started(identifier))
        elif method == 'Browser.downloadProgress' and params.get('guid') in self.downloads:
            identifier = params['guid']
            received = params.get('receivedBytes', 0)
            if received > MAX_FILE_BYTES:
                self.schedule(self.cancel_download(identifier, 'download_size_limit'))
            elif params.get('state') == 'completed':
                if 'finished_task' not in self.downloads[identifier]:
                    self.downloads[identifier]['finished_task'] = self.schedule(self.finish_download(identifier))
            elif params.get('state') == 'canceled':
                self.schedule(self.session.broker.report_download(session.producer_id, event='failed', download_id=identifier, target_id=session.target_id, reason='browser_cancelled'))
        elif method == 'Page.fileChooserOpened' and own_session:
            node = params.get('backendNodeId')
            if type(node) is not int or node <= 0 or len(self.choosers) >= 8:
                return
            identifier = 'choose_' + uuid.uuid4().hex
            self.choosers[identifier] = {'backend_node_id': node, 'expires_at': asyncio.get_running_loop().time() + 120, 'generation': session.control_generation, 'viewport_revision': session.viewport['revision']}
            self.schedule(self.register_chooser(identifier))

    async def report_started(self, identifier):
        entry = self.downloads[identifier]
        await self.session.broker.report_download(self.session.producer_id, event='started', download_id=identifier, target_id=self.session.target_id, suggested_name=entry['name'], url_digest=entry['url_digest'])
        entry['reported'] = True
        self.session.emit('download.available', download_id=identifier, state='IN_PROGRESS')

    async def cancel_download(self, identifier, reason):
        await self.session.cdp._command('Browser.cancelDownload', {'guid': identifier})
        await self.session.broker.report_download(self.session.producer_id, event='failed', download_id=identifier, target_id=self.session.target_id, reason=reason)
        path = self.path(identifier)
        path.unlink(missing_ok=True)

    async def finish_download(self, identifier):
        # The completed Chromium file is named by GUID, never the suggested filename.
        path = self.path(identifier)
        sealed = self.path('sealed_' + identifier)
        total = sum(item.stat().st_size for item in self.root.glob('prod_*/sealed_*') if item.is_file() and not item.is_symlink())
        if total + path.stat().st_size > 256 * 1024 * 1024:
            await self.cancel_download(identifier, 'download_quarantine_limit')
            return
        size, sha, mime = await asyncio.to_thread(self.seal, path, sealed)
        entry = self.downloads[identifier]
        if entry.get('started_task') is not None:
            await entry['started_task']
        if not entry['reported']:
            await self.report_started(identifier)
        entry.update({'byte_size': size, 'content_sha256': sha, 'observed_mime': mime})
        entry['sealed_path'] = sealed
        await self.session.broker.report_download(self.session.producer_id, event='finished', download_id=identifier, target_id=self.session.target_id, byte_size=size, content_sha256=sha, observed_mime=mime)
        self.session.emit('download.available', download_id=identifier, state='COMPLETED')

    @staticmethod
    def seal(source, destination):
        source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        destination_fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        total = 0
        digest = hashlib.sha256()
        first = b''
        try:
            with os.fdopen(source_fd, 'rb') as input_file, os.fdopen(destination_fd, 'wb') as output_file:
                info = os.fstat(input_file.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                    raise FileRefused('file_size_or_kind_refused')
                while chunk := input_file.read(65536):
                    if not first:
                        first = chunk[:4096]
                    total += len(chunk)
                    if total > MAX_FILE_BYTES:
                        raise FileRefused('file_size_limit')
                    digest.update(chunk)
                    output_file.write(chunk)
                output_file.flush()
                os.fsync(output_file.fileno())
            destination.chmod(0o400)
            source.unlink()
            return total, digest.hexdigest(), observed_mime(first)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise

    @staticmethod
    def describe(path):
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                raise FileRefused('file_size_or_kind_refused')
            digest = hashlib.sha256()
            first = handle.read(4096)
            digest.update(first)
            total = len(first)
            while chunk := handle.read(65536):
                total += len(chunk)
                if total > MAX_FILE_BYTES:
                    raise FileRefused('file_size_limit')
                digest.update(chunk)
            if total != info.st_size:
                raise FileRefused('file_changed_during_hash')
            return total, digest.hexdigest(), observed_mime(first)

    async def register_chooser(self, identifier):
        node = await self.session.cdp.send(self.session.target_id, 'DOM.describeNode', {'backendNodeId': self.choosers[identifier]['backend_node_id'], 'depth': 0})
        attrs = node.get('node', {}).get('attributes', [])
        attributes = dict(zip(attrs[::2], attrs[1::2]))
        accept = attributes.get('accept', '')
        accept_types = [entry.strip()[:128] for entry in accept.split(',')[:16] if entry.strip()]
        await self.session.broker.register_chooser(self.session.producer_id, identifier, self.session.target_id)
        self.session.emit('file.chooser', chooser_id=identifier, target_id=self.session.target_id, expires_in_ms=120000, accept_types=accept_types, multiple=False)

    async def apply_deletions(self, requests):
        if not isinstance(requests, list) or len(requests) > 128:
            raise FileRefused('download_deletion_requests_invalid')
        for request in requests:
            producer = request.get('artifact_producer_session_id', '')
            identifier = request.get('download_id', '')
            if not re.fullmatch(r'prod_[0-9a-f]{32}', producer) or not GUID.fullmatch(identifier):
                raise FileRefused('download_deletion_binding_invalid')
            directory = self.root / producer
            if directory.is_symlink():
                raise FileRefused('download_deletion_path_invalid')
            path = directory / ('sealed_' + identifier)
            if path.is_symlink():
                raise FileRefused('download_deletion_path_invalid')
            self.deleted.add(identifier)
            path.unlink(missing_ok=True)
            await self.session.broker.report_download(self.session.producer_id, event='deleted', download_id=identifier, target_id=request['target_id'])

    async def consume(self, token, operation, resource_id, **fields):
        result = await self.session.broker.consume_transfer(self.session.producer_id, token, operation, resource_id, **fields)
        if result.get('producer_session_id', self.session.producer_id) != self.session.producer_id or (operation not in {'download', 'analyse'} and result.get('target_id') != self.session.target_id) or result.get('operation') != operation:
            raise FileRefused('file_grant_binding_mismatch')
        from services.browser_stream_host.runtime import check_authority
        authority = result.get('authority')
        check_authority(authority, expected_session=self.session.session_id)
        self.session.check_binding(authority)
        return result

    async def _approved_download(self, identifier, token, *, operation):
        entry = self.downloads.get(identifier)
        grant = await self.consume(token, operation, identifier)
        if entry and 'sealed_path' in entry:
            path = entry['sealed_path']
        else:
            # Reconnection does not destroy an already classified download. The current
            # broker grant names its original producer, never a caller supplied path.
            producer = grant.get('artifact_producer_session_id', '')
            if not re.fullmatch(r'prod_[0-9a-f]{32}', producer) or not GUID.fullmatch(identifier):
                raise FileRefused('download_artifact_binding_invalid')
            directory = self.root / producer
            if directory.is_symlink():
                raise FileRefused('download_artifact_path_refused')
            path = directory / ('sealed_' + identifier)
            if path.is_symlink() or time.time() - path.stat().st_mtime > 86400:
                raise FileRefused('download_artifact_expired')
        size, sha, mime = await asyncio.to_thread(self.describe, path)
        if (entry and (size != entry.get('byte_size') or sha != entry.get('content_sha256'))) or grant.get('content_sha256') != sha or grant.get('byte_size') != size:
            raise FileRefused('download_changed_since_approval')
        return path, size, mime, grant

    async def download(self, identifier, token):
        path, size, mime, _ = await self._approved_download(identifier, token, operation='download')
        return path, size, mime

    async def analyse(self, identifier, token):
        path, size, mime, grant = await self._approved_download(identifier, token, operation='analyse')
        def bounded_analysis():
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, 'rb') as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size != size:
                    raise FileRefused('analysis_file_changed')
                digest = hashlib.sha256()
                preview = b''
                total = 0
                while chunk := handle.read(65536):
                    total += len(chunk)
                    if total > MAX_FILE_BYTES:
                        raise FileRefused('analysis_size_limit')
                    digest.update(chunk)
                    if len(preview) < 65536:
                        preview += chunk[:65536-len(preview)]
                if total != grant['byte_size'] or digest.hexdigest() != grant['content_sha256']:
                    raise FileRefused('analysis_content_changed_since_approval')
                result = {'download_id': identifier, 'byte_size': total, 'content_sha256': digest.hexdigest(),
                    'observed_mime': observed_mime(preview[:4096]), 'analysis_kind': 'BOUNDED_STATIC_INSPECTION',
                    'content_authority': 'UNTRUSTED_FILE_EVIDENCE', 'executed_content': False,
                    'truncated': total > len(preview), 'text_preview': None}
                if mime == 'text/plain':
                    try:
                        text = preview.decode('utf-8')
                        if '\x00' not in text:
                            result.update(text_preview=text, preview_line_count=len(text.splitlines()))
                    except UnicodeDecodeError:
                        pass
                result['analysis_sha256'] = hashlib.sha256(__import__('json').dumps(result, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                return result
        result = await asyncio.to_thread(bounded_analysis)
        # A fresh producer authority read fences delivery after owner preemption,
        # session closure or device revocation during a slow filesystem read.
        authority = await self.session.broker.authority(self.session.producer_id)
        from services.browser_stream_host.runtime import check_authority
        check_authority(authority, expected_session=self.session.session_id)
        self.session.check_binding(authority)
        receipt = {key: value for key, value in result.items() if key != 'text_preview'}
        await self.session.broker.report_file_result(self.session.producer_id,
            transfer_id=grant['transfer_id'], operation='analyse', resource_id=identifier, receipt=receipt)
        return {**result, 'transfer_id': grant['transfer_id'], 'operation': 'analyse', 'resource_id': identifier, 'session_id': self.session.session_id, 'producer_session_id': self.session.producer_id, 'status': 'VERIFIED_SUCCESS'}

    async def import_file(self, identifier, token, content, *, expected_size, expected_sha):
        if self.import_lock.locked():
            raise FileRefused('import_in_progress')
        async with self.import_lock:
            if len(self.downloads) >= 128:
                raise FileRefused('import_artifact_count_limit')
            total = sum(item.stat().st_size for item in self.root.glob('prod_*/sealed_*') if item.is_file() and not item.is_symlink())
            if type(expected_size) is not int or total + expected_size > 256 * 1024 * 1024:
                raise FileRefused('import_quarantine_limit')
            return await self._import_file(identifier, token, content, expected_size=expected_size, expected_sha=expected_sha)

    async def _import_file(self, identifier, token, content, *, expected_size, expected_sha):
        if not re.fullmatch(r'import_[0-9a-f]{32}', identifier):
            raise FileRefused('import_resource_invalid')
        if type(expected_size) is not int or not 0 <= expected_size <= MAX_FILE_BYTES or not re.fullmatch(r'[0-9a-f]{64}', expected_sha):
            raise FileRefused('import_metadata_invalid')
        grant = await self.consume(token, 'file_import', identifier, byte_size=expected_size, content_sha256=expected_sha)
        source, sealed = self.path(identifier), self.path('sealed_' + identifier)
        descriptor = os.open(source, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        total, digest = 0, hashlib.sha256()
        try:
            with os.fdopen(descriptor, 'wb') as handle:
                async for chunk in content:
                    total += len(chunk)
                    if total > expected_size or total > MAX_FILE_BYTES:
                        raise FileRefused('import_size_mismatch')
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            if total != expected_size or digest.hexdigest() != expected_sha:
                raise FileRefused('import_content_mismatch')
            authority = await self.session.broker.authority(self.session.producer_id)
            from services.browser_stream_host.runtime import check_authority
            check_authority(authority, expected_session=self.session.session_id)
            self.session.check_binding(authority)
            size, sha, mime = await asyncio.to_thread(self.seal, source, sealed)
            # Re-open and independently describe the sealed artifact, not the input
            # stream's self-reported hash, before publishing its available record.
            observed = await asyncio.to_thread(self.describe, sealed)
            if observed != (size, sha, mime) or sha != expected_sha:
                raise FileRefused('import_sealed_readback_mismatch')
            await self.session.broker.report_download(self.session.producer_id, event='started',
                download_id=identifier, target_id=self.session.target_id,
                suggested_name=grant['suggested_name'], declared_mime=grant.get('mime_type'),
                url_digest=hashlib.sha256(('OWNER_FILE_IMPORT:' + sha).encode()).hexdigest())
            self.downloads[identifier] = {'sealed_path': sealed, 'byte_size': size, 'content_sha256': sha,
                'observed_mime': mime, 'name': grant['suggested_name'], 'reported': True}
            result = await self.session.broker.report_download(self.session.producer_id, event='finished',
                download_id=identifier, target_id=self.session.target_id,
                byte_size=size, content_sha256=sha, observed_mime=mime)
            return {'download_id': identifier, 'resource_id': identifier, 'operation': 'file_import', 'session_id': self.session.session_id, 'producer_session_id': self.session.producer_id, 'transfer_id': grant['transfer_id'], 'byte_size': size,
                'content_sha256': sha, 'observed_mime': mime, 'state': result.get('state'),
                'status': 'VERIFIED_SUCCESS', 'observation_source': 'NATIVE_SEALED_FILE_READBACK'}
        except BaseException:
            source.unlink(missing_ok=True)
            # Once broker publication starts, retain the confined artifact so an
            # owner can reconcile a lost final report without repeating the import.
            if identifier not in self.downloads:
                sealed.unlink(missing_ok=True)
            raise

    async def upload(self, identifier, token, content, *, expected_size, expected_sha):
        chooser = self.choosers.get(identifier)
        if not chooser or chooser['expires_at'] <= asyncio.get_running_loop().time() or chooser['generation'] != self.session.control_generation:
            raise FileRefused('upload_chooser_expired')
        if type(expected_size) is not int or not 0 <= expected_size <= MAX_FILE_BYTES or not re.fullmatch(r'[0-9a-f]{64}', expected_sha):
            raise FileRefused('upload_expected_content_invalid')
        grant = await self.consume(token, 'upload', identifier, byte_size=expected_size, content_sha256=expected_sha)
        name = grant.get('suggested_name') or 'upload.bin'
        # Preserve a safe basename for sites that inspect it, without accepting a path.
        name = re.sub(r'[^A-Za-z0-9._-]', '_', name)[:128].strip('.') or 'upload.bin'
        directory = self.directory / ('upload_' + uuid.uuid4().hex)
        directory.mkdir(mode=0o770)
        path = directory / name
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)
        digest = hashlib.sha256()
        total = 0
        try:
            with os.fdopen(descriptor, 'wb') as handle:
                async for chunk in content:
                    total += len(chunk)
                    if total > expected_size or total > MAX_FILE_BYTES:
                        raise FileRefused('upload_size_limit')
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            if total != expected_size or digest.hexdigest() != expected_sha:
                raise FileRefused('upload_content_mismatch')
            current = await self.session.broker.authority(self.session.producer_id)
            from services.browser_stream_host.runtime import check_authority
            check_authority(current, expected_session=self.session.session_id)
            self.session.check_binding(current)
            if current.get('control_holder') != 'OWNER' or current.get('control_issued_for') != self.session.owner_device_id:
                raise FileRefused('upload_owner_authority_lost')
            if (current.get('control_lease_id') != grant['authority'].get('control_lease_id')
                    or current.get('control_generation') != grant['authority'].get('control_generation')
                    or type(current.get('control_expires_at_ms')) is not int
                    or current['control_expires_at_ms'] <= int(time.time() * 1000)):
                raise FileRefused('upload_owner_lease_expired')
            from van_gateway.browser.input_protocol import InputAuthority
            frozen = grant['authority']
            await self.session.broker.authorize_input(self.session.producer_id, InputAuthority(
                self.session.session_id, frozen['control_lease_id'], frozen['control_generation'], frozen['viewport']['revision'],
            ))
            await self.session.cdp.send(self.session.target_id, 'DOM.setFileInputFiles', {'files': [str(path)], 'backendNodeId': chooser['backend_node_id']})
            self.choosers.pop(identifier, None)
            # Chromium consumes asynchronously. A finite cleanup task retains it briefly;
            # source acceptance must exercise actual chooser consumption on target sites.
            self.schedule(self.expire_upload(path, directory))
            return {'attached': True, 'chooser_id': identifier, 'target_id': self.session.target_id, 'producer_session_id': self.session.producer_id, 'byte_size': total, 'content_sha256': expected_sha}
        except BaseException:
            path.unlink(missing_ok=True)
            directory.rmdir()
            raise

    async def expire_upload(self, path, directory):
        await asyncio.sleep(15 * 60)
        path.unlink(missing_ok=True)
        directory.rmdir()

    async def clipboard(self, token, operation, *, text=None):
        if not self.clipboard_enabled:
            raise FileRefused('clipboard_disabled_by_host_policy')
        if operation == 'paste':
            if not isinstance(text, str) or len(text.encode()) > MAX_CLIPBOARD_BYTES:
                raise FileRefused('clipboard_size_limit')
            raw = text.encode()
            await self.consume(token, operation, self.session.target_id, byte_size=len(raw), content_sha256=hashlib.sha256(raw).hexdigest())
            await self.session.cdp.send(self.session.target_id, 'Input.insertText', {'text': text})
            return {'pasted': True, 'producer_session_id': self.session.producer_id, 'target_id': self.session.target_id, 'byte_size': len(raw), 'content_sha256': hashlib.sha256(raw).hexdigest()}
        if operation != 'copy':
            raise FileRefused('clipboard_operation_refused')
        grant = await self.consume(token, operation, self.session.target_id)
        # Constant expression, no script supplied by caller. Password and editable field
        # values are excluded. Selection extraction is bounded inside Chromium and again
        # before it leaves the runtime; no OS clipboard polling or silent sync exists.
        expression = "(() => {const e=document.activeElement;if(e&&((e.tagName==='INPUT')||(e.tagName==='TEXTAREA')||e.isContentEditable))return '';return String(window.getSelection()||'').slice(0,65536);})()"
        frame_tree = await self.session.cdp.send(self.session.target_id, 'Page.getFrameTree', {})
        frame_id = frame_tree.get('frameTree', {}).get('frame', {}).get('id')
        if not isinstance(frame_id, str) or not frame_id:
            raise FileRefused('clipboard_frame_unavailable')
        world = await self.session.cdp.send(self.session.target_id, 'Page.createIsolatedWorld', {'frameId': frame_id, 'worldName': 'VAN_OWNER_CLIPBOARD'})
        context_id = world.get('executionContextId')
        if type(context_id) is not int:
            raise FileRefused('clipboard_context_unavailable')
        # The isolated world prevents a page from replacing getSelection/prototypes to
        # turn this constant extraction into its own script. A native timeout is bounded.
        from van_gateway.browser.input_protocol import InputAuthority
        frozen = grant['authority']
        await self.session.broker.authorize_input(self.session.producer_id, InputAuthority(
            self.session.session_id, frozen['control_lease_id'], frozen['control_generation'], frozen['viewport']['revision'],
        ))
        result = await self.session.cdp.send(self.session.target_id, 'Runtime.evaluate', {'expression': expression, 'contextId': context_id, 'returnByValue': True, 'awaitPromise': False, 'timeout': 1000})
        text = result.get('result', {}).get('value')
        if not isinstance(text, str) or len(text.encode()) > MAX_CLIPBOARD_BYTES:
            raise FileRefused('clipboard_result_invalid')
        return {'text': text, 'producer_session_id': self.session.producer_id, 'target_id': self.session.target_id}

    async def close(self):
        self.closed = True
        for task in tuple(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        for identifier, entry in self.downloads.items():
            if 'sealed_path' not in entry:
                try:
                    await self.session.cdp._command('Browser.cancelDownload', {'guid': identifier})
                except Exception:
                    pass
        # Download quarantines remain under TTL cleanup rather than deleting bytes an
        # explicitly approved transfer might still be reading. Cleanup is confined here.
        for path in self.directory.iterdir():
            if path.is_file() and not path.is_symlink():
                if not path.name.startswith('sealed_'):
                    path.unlink(missing_ok=True)
            elif path.is_dir() and not path.is_symlink():
                for child in path.iterdir():
                    if child.is_file() and not child.is_symlink():
                        child.unlink(missing_ok=True)
                path.rmdir()
        if not any(self.directory.iterdir()):
            self.directory.rmdir()
