"""A corrupt rotated credential is an unavailable service, never a gateway 500."""

import httpx
import pytest

from van_gateway.dial_dev.client import DialDevClient, DialDevUnavailable
from van_gateway.dial_dev.config import DialDevConfig


async def test_non_utf8_rotated_token_is_a_typed_failure_before_socket_open(tmp_path):
    credential = tmp_path / "dial.token"
    credential.write_bytes(b"\xff" * 64)
    requests = []
    client = DialDevClient(
        DialDevConfig(enabled=True, base_url="https://dial.invalid", token_file=str(credential)),
        transport=httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(200)),
    )
    with pytest.raises(DialDevUnavailable) as raised:
        await client.get("/v1/dev/projects")
    assert raised.value.reason == "credential_invalid"
    assert requests == []
