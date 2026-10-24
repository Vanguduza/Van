"""Fixed typed producer calls to the trusted Trading Core HTTPS authority.

No redirects, no raw method/path proxy, no caller supplied machine credential or CA.
The BROWSER_STREAM_PRODUCER-scoped token lives in a protected role-specific file.
"""
from __future__ import annotations
import ipaddress
import json
import os
import ssl
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class BrokerRefused(Exception):
    pass


@dataclass(frozen=True)
class BrokerConfig:
    origin: str
    ca_file: str
    token_file: str
    cert_file: str = ''
    key_file: str = ''
    expected_token_sha256: str = ''

    @classmethod
    def from_environment(cls, environment=None, *, service='CONTROL'):
        env = os.environ if environment is None else environment
        config = cls(
            env.get('VAN_BROWSER_BROKER_ORIGIN', ''),
            env.get('VAN_BROWSER_BROKER_CA', ''),
            env.get(f'VAN_BROWSER_{service}_BROKER_TOKEN_FILE', ''),
            env.get('VAN_BROWSER_BROKER_CLIENT_CERT', ''),
            env.get('VAN_BROWSER_BROKER_CLIENT_KEY', ''),
            env.get(f'VAN_BROWSER_{service}_BROKER_TOKEN_SHA256', ''),
        )
        config.validate()
        control = env.get('VAN_BROWSER_CONTROL_BROKER_TOKEN_FILE', '')
        stream = env.get('VAN_BROWSER_STREAM_BROKER_TOKEN_FILE', '')
        if not control or not stream or Path(control).resolve() == Path(stream).resolve():
            raise BrokerRefused('broker_role_credentials_must_be_distinct')
        control_hash = env.get('VAN_BROWSER_CONTROL_BROKER_TOKEN_SHA256', '')
        stream_hash = env.get('VAN_BROWSER_STREAM_BROKER_TOKEN_SHA256', '')
        if not re.fullmatch(r'[0-9a-f]{64}', control_hash) or not re.fullmatch(r'[0-9a-f]{64}', stream_hash) or control_hash == stream_hash:
            raise BrokerRefused('broker_role_fingerprints_must_be_distinct')
        return config

    def validate(self):
        parsed = urlsplit(self.origin)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.path not in {'', '/'}:
            raise BrokerRefused('broker_requires_https_origin')
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise BrokerRefused('broker_origin_components_refused')
        # Configured hostnames are supported for certificate verification. Raw public
        # IPs are refused; private VCN ingress is the intended machine authority route.
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address is not None and (not address.is_private or address.is_unspecified):
            raise BrokerRefused('broker_public_ip_refused')
        if not self.ca_file or not self.token_file or bool(self.cert_file) != bool(self.key_file):
            raise BrokerRefused('broker_trust_or_credential_unbound')

    def context(self):
        context = ssl.create_default_context(cafile=self.ca_file)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        if self.cert_file:
            context.load_cert_chain(self.cert_file, self.key_file)
        return context


class BrokerClient:
    def __init__(self, config: BrokerConfig):
        config.validate()
        self.config = config
        self._session = None
        self._token = ''

    async def start(self):
        import aiohttp
        token_path = Path(self.config.token_file)
        if token_path.stat().st_mode & 0o077:
            raise BrokerRefused('broker_token_file_permissions')
        token = token_path.read_text().strip()
        if not token or len(token) > 8192 or '\r' in token or '\n' in token:
            raise BrokerRefused('broker_token_invalid')
        self._token = token
        if self.config.expected_token_sha256 and hashlib.sha256(token.encode()).hexdigest() != self.config.expected_token_sha256:
            raise BrokerRefused('broker_credential_fingerprint_mismatch')
        self._session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=self.config.context(), limit=32),
            timeout=aiohttp.ClientTimeout(total=10), trust_env=False,
        )

    async def _post(self, path, body):
        if self._session is None:
            raise BrokerRefused('broker_client_not_started')
        async with self._session.post(
            self.config.origin.rstrip('/') + path,
            headers={'X-Van-Internal-Token': self._token}, json=body, allow_redirects=False,
        ) as response:
            raw = await response.content.read(262145)
            if len(raw) > 262144:
                raise BrokerRefused('broker_response_too_large')
            if response.status != 200:
                # Do not expose response bodies containing profile data or credentials.
                raise BrokerRefused(f'broker_authority_refused_{response.status}')
            try:
                result = json.loads(raw)
            except ValueError as exc:
                raise BrokerRefused('broker_response_invalid') from exc
            if not isinstance(result, dict):
                raise BrokerRefused('broker_response_invalid')
            return result

    @staticmethod
    def _producer_id(value):
        if not isinstance(value, str) or not value or len(value) > 128 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in value):
            raise BrokerRefused('broker_producer_id_invalid')
        return value

    async def redeem(self, stream_grant, producer_session_id):
        self._producer_id(producer_session_id)
        return await self._post('/v1/browser/stream-producer/redeem', {
            'stream_grant': stream_grant, 'producer_session_id': producer_session_id,
        })

    async def authority(self, producer_id):
        producer_id = self._producer_id(producer_id)
        result = await self._post(f'/v1/browser/stream-producer/{producer_id}/authority', {})
        return result.get('authority', result)

    async def authorize_input(self, producer_id, authority):
        producer_id = self._producer_id(producer_id)
        result = await self._post(f'/v1/browser/stream-producer/{producer_id}/authorize-input', {
            'session_id': authority.session_id,
            'control_lease_id': authority.control_lease_id,
            'control_generation': authority.control_generation,
            'viewport_revision': authority.viewport_revision,
        })
        return result.get('authority', result)

    async def observe(self, producer_id, event, **fields):
        producer_id = self._producer_id(producer_id)
        allowed = {'viewport_revision', 'target_id', 'url', 'title', 'codec', 'transport', 'reason', 'frame_sequence', 'media_epoch', 'width', 'height'}
        if set(fields) - allowed:
            raise BrokerRefused('broker_observation_field_refused')
        return await self._post(f'/v1/browser/stream-producer/{producer_id}/observe', {'event': event, **fields})

    async def authorize_call(self, caller_common_name, call):
        return await self._post('/v1/browser/control-producer/authorize-call', {
            'caller_common_name': caller_common_name,
            'operation': call.operation.value,
            'session_id': call.session_id, 'target_id': call.target_id,
            'lease_id': call.lease_id, 'lease_generation': call.lease_generation,
            'task_id': call.task_id, 'params': call.params,
        })

    async def validate_call(self, caller_common_name, call):
        return await self._post('/v1/browser/control-producer/validate-call', {
            'caller_common_name': caller_common_name,
            'operation': call.operation.value,
            'session_id': call.session_id, 'target_id': call.target_id,
            'lease_id': call.lease_id, 'lease_generation': call.lease_generation,
            'task_id': call.task_id, 'params': call.params,
        })

    async def validate_result(self, caller_common_name, call):
        return await self._post('/v1/browser/control-producer/validate-result', {
            'caller_common_name': caller_common_name,
            'operation': call.operation.value,
            'session_id': call.session_id, 'target_id': call.target_id,
            'lease_id': call.lease_id, 'lease_generation': call.lease_generation,
            'task_id': call.task_id, 'params': call.params,
        })

    async def report_download(self, producer_id, **fields):
        producer_id = self._producer_id(producer_id)
        allowed = {'event', 'download_id', 'target_id', 'suggested_name', 'declared_mime', 'url_digest', 'byte_size', 'content_sha256', 'observed_mime', 'reason'}
        if set(fields) - allowed:
            raise BrokerRefused('broker_download_field_refused')
        return await self._post(f'/v1/browser/stream-producer/{producer_id}/downloads', fields)

    async def register_chooser(self, producer_id, chooser_id, target_id):
        producer_id = self._producer_id(producer_id)
        return await self._post(f'/v1/browser/stream-producer/{producer_id}/chooser', {'chooser_id': chooser_id, 'target_id': target_id})

    async def consume_transfer(self, producer_id, transfer_grant, operation, resource_id, **fields):
        producer_id = self._producer_id(producer_id)
        if set(fields) - {'content_sha256', 'byte_size'} or operation not in {'download', 'upload', 'copy', 'paste', 'analyse', 'file_import'}:
            raise BrokerRefused('broker_transfer_field_refused')
        return await self._post(f'/v1/browser/stream-producer/{producer_id}/consume-transfer-grant', {
            'transfer_grant': transfer_grant, 'operation': operation, 'resource_id': resource_id, **fields,
        })

    async def report_file_result(self, producer_id, **fields):
        producer_id = self._producer_id(producer_id)
        return await self._post(f'/v1/browser/stream-producer/{producer_id}/file-results', fields)

    async def close(self):
        if self._session is not None:
            await self._session.close()
        self._session = None
        self._token = ''
