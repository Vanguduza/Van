"""Cloud token exchanges validate provider responses before caching credentials."""

import json

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from van_gateway.knowledge.notebook import CloudAccessTokenProvider, NotebookProviderError


@pytest.fixture
def service_account_file(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    account = tmp_path / "account.json"
    account.write_text(json.dumps({"client_email": "synthetic@example.invalid", "private_key": pem}))
    return account


@pytest.mark.parametrize("response", [
    httpx.Response(200, text="invalid JSON"),
    httpx.Response(200, json=[]),
    httpx.Response(200, json={"access_token": 42}),
    httpx.Response(200, json={"access_token": "synthetic", "expires_in": "unknown"}),
    httpx.Response(200, json={"access_token": "synthetic", "expires_in": -1}),
])
async def test_malformed_token_response_is_not_cached(service_account_file, response):
    provider = CloudAccessTokenProvider(
        service_account_file=str(service_account_file),
        transport=httpx.MockTransport(lambda request: response),
    )
    with pytest.raises(NotebookProviderError, match="notebook_enterprise_token_exchange_malformed"):
        await provider.token()
    assert provider._cached_token == "" and provider._expires_at == 0


async def test_token_redirect_is_not_an_exchange(service_account_file):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://other.invalid"})

    provider = CloudAccessTokenProvider(service_account_file=str(service_account_file), transport=httpx.MockTransport(handler))
    with pytest.raises(NotebookProviderError, match="notebook_enterprise_token_exchange_failed:302"):
        await provider.token()
    assert len(requests) == 1
    assert provider._cached_token == ""


async def test_valid_token_response_is_cached_until_expiry(service_account_file):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url == "https://oauth2.googleapis.com/token"
        return httpx.Response(200, json={"access_token": "short-lived-synthetic", "expires_in": 3600})

    provider = CloudAccessTokenProvider(service_account_file=str(service_account_file), transport=httpx.MockTransport(handler))
    assert await provider.token() == "short-lived-synthetic"
    assert await provider.token() == "short-lived-synthetic"
    assert len(requests) == 1
