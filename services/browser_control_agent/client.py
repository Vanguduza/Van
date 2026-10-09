"""Trading Core caller for the narrow newline-framed private mTLS control API."""
from __future__ import annotations
import asyncio
import ipaddress
import ssl
import uuid
from dataclasses import dataclass
from services.browser_control_agent.wire import frame, encode_call, decode_response


class ControlTransportError(Exception):
    pass


@dataclass(frozen=True)
class ControlClientConfig:
    address: str
    port: int
    server_name: str
    ca_file: str
    cert_file: str
    key_file: str

    def context(self):
        try:
            address = ipaddress.ip_address(self.address)
        except ValueError as exc:
            raise ControlTransportError('control_destination_must_be_private_literal') from exc
        if not address.is_private or address.is_unspecified or not self.server_name or not 1 <= self.port <= 65535:
            raise ControlTransportError('control_destination_refused')
        context = ssl.create_default_context(cafile=self.ca_file)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.load_cert_chain(self.cert_file, self.key_file)
        return context


class BrowserControlClient:
    def __init__(self, config):
        self.config = config
        self.context = config.context()

    async def invoke(self, call):
        request_id = 'ctrl_' + uuid.uuid4().hex
        reader, writer = await asyncio.wait_for(asyncio.open_connection(
            self.config.address, self.config.port, ssl=self.context,
            server_hostname=self.config.server_name, limit=12 * 1024 * 1024 + 1,
        ), 10)
        try:
            writer.write(frame(encode_call(call, request_id=request_id)))
            await asyncio.wait_for(writer.drain(), 10)
            response = await asyncio.wait_for(reader.readline(), 30)
            if not response or not response.endswith(b'\n') or len(response) > 12 * 1024 * 1024:
                raise ControlTransportError('control_response_framing_invalid')
            returned_id, ok, payload = decode_response(response)
            if returned_id != request_id:
                raise ControlTransportError('control_response_id_mismatch')
            if not ok:
                raise ControlTransportError('control_operation_refused:' + str(payload))
            return payload
        finally:
            writer.close()
            await writer.wait_closed()
