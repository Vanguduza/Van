"""Exact, currently provisioned mTLS principals for artifact admission callbacks.

The protocol shim's ``van.mtls`` extension contains the certificate actually
verified in the TLS handshake. HTTP headers, owner-device state and machine
bearers cannot establish this principal. A pin grants only its configured
provider/owner/project target; signed one-use admission remains a separate gate.
No certificates, signing keys or default provider authority are generated here.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID
from fastapi import HTTPException, Request

from van_gateway.mtls.transport import EXTENSION

PURPOSE = "OWNER_ARTIFACT_WRITE_ADMISSION"
PROVIDERS = frozenset({"ORACLE_OWNER_ARCHIVE", "VEKL_OWNER_CANDIDATE_INGRESS"})
STATE_PRINCIPAL = "van_artifact_provider_principal"
_NAMESPACE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ROUTE = re.compile(
    r"/v1/browser/artifact-provider/admissions/[A-Za-z0-9][A-Za-z0-9_-]{0,63}/(?:introspect|claim)"
)
_CONFIG_KEYS = frozenset({"schema_version", "providers", "source_clients", "signer"})
_PROVIDER_KEYS = frozenset({"provider", "origin", "ca_file", "client_cert_file", "client_key_file",
    "provider_identity", "capability_receipt_sha256", "owner_namespace", "project_namespace", "provider_principal_sha256"})


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_config_field")
        result[key] = value
    return result


def load_artifact_transport_bindings(path: str | Path | None) -> tuple[ProviderTransportBinding, ...]:
    """Reload only public transport bindings; never open a configured private key.

    The operator-owned artifact config has schema_version/providers/source_clients/signer fields.
    Full provider execution configuration is validated by its own loader. This
    read intentionally does not cache pins, so removing one blocks the next call.
    """
    if not path:
        return ()
    try:
        with Path(path).open("rb") as file:
            encoded = file.read(65537)
        if len(encoded) > 65536:
            raise ValueError("config_too_large")
        value = json.loads(encoded, object_pairs_hook=_unique_object)
        if (not isinstance(value, dict) or not set(value) <= _CONFIG_KEYS
            or type(value.get("schema_version")) is not int or value["schema_version"] != 1):
            raise ValueError("invalid_config_fields")
        providers = value.get("providers")
        if not isinstance(providers, list) or len(providers) > 16:
            raise ValueError("invalid_providers")
        bindings = []
        for row in providers:
            if (not isinstance(row, dict) or set(row) != _PROVIDER_KEYS
                or any(not isinstance(v, str) or not v or len(v) > 4096 for v in row.values())):
                raise ValueError("invalid_provider_fields")
            binding = ProviderTransportBinding(certificate_sha256=row["provider_principal_sha256"],
                provider_identity=row["provider_identity"], provider=row["provider"],
                owner_namespace=row["owner_namespace"], project_namespace=row["project_namespace"])
            binding.validate()
            bindings.append(binding)
        return tuple(bindings)
    except (OSError, TypeError, ValueError, RecursionError):
        raise ValueError("artifact_provider_transport_configuration_invalid") from None


def is_artifact_provider_route(scope: dict) -> bool:
    """Only these two POST routes use the separate provider authentication lane."""
    return (scope.get("type") == "http" and scope.get("method") == "POST"
            and isinstance(scope.get("path"), str) and _ROUTE.fullmatch(scope["path"]) is not None)


def is_https_artifact_provider_route(scope: dict) -> bool:
    """The public TLS gate must never admit a forwarded HTTP provider request."""
    return scope.get("scheme") == "https" and is_artifact_provider_route(scope)


@dataclass(frozen=True)
class ProviderTransportBinding:
    certificate_sha256: str
    provider_identity: str
    provider: str
    owner_namespace: str
    project_namespace: str
    purpose: str = PURPOSE

    def validate(self) -> None:
        if (not isinstance(self.certificate_sha256, str) or not _SHA256.fullmatch(self.certificate_sha256)
            or not isinstance(self.provider_identity, str) or not 1 <= len(self.provider_identity) <= 256
            or self.provider_identity != self.provider_identity.strip()
            or any(ord(c) < 33 or ord(c) > 126 for c in self.provider_identity)
            or self.provider not in PROVIDERS or self.purpose != PURPOSE
            or not isinstance(self.owner_namespace, str) or not _NAMESPACE.fullmatch(self.owner_namespace)
            or not isinstance(self.project_namespace, str) or not _NAMESPACE.fullmatch(self.project_namespace)):
            raise ValueError("artifact_provider_transport_binding_invalid")


@dataclass(frozen=True)
class ProviderPrincipal:
    certificate_sha256: str
    provider_identity: str
    provider: str
    owner_namespace: str
    project_namespace: str
    purpose: str = PURPOSE


def require_provider_target(principal: ProviderPrincipal, *, provider: str, provider_identity: str,
                            owner_namespace: str, project_namespace: str) -> None:
    """A valid certificate never widens its configured provider or namespace."""
    if (not isinstance(principal, ProviderPrincipal) or principal.purpose != PURPOSE
        or (principal.provider, principal.provider_identity, principal.owner_namespace, principal.project_namespace)
        != (provider, provider_identity, owner_namespace, project_namespace)):
        raise HTTPException(403, "artifact_provider_target_mismatch")


class ProviderTransportAuthenticator:
    def __init__(self, bindings_provider: Callable[[], Iterable[ProviderTransportBinding] | None] | None = None):
        self.bindings_provider = bindings_provider

    def authenticate_scope(self, scope: dict) -> ProviderPrincipal:
        if not is_https_artifact_provider_route(scope) or scope.get("query_string", b""):
            raise HTTPException(403, "artifact_provider_transport_required")
        try:
            bindings = tuple(self.bindings_provider() or ()) if self.bindings_provider else ()
            if not bindings:
                raise HTTPException(503, "artifact_provider_transport_unconfigured")
            by_pin = {}
            for binding in bindings:
                if not isinstance(binding, ProviderTransportBinding):
                    raise ValueError("invalid_binding")
                binding.validate()
                prior = by_pin.get(binding.certificate_sha256)
                if prior is not None and prior != binding:
                    # One principal cannot silently select a target from request data.
                    raise ValueError("ambiguous_provider_principal")
                by_pin[binding.certificate_sha256] = binding
        except HTTPException:
            raise
        except (TypeError, ValueError):
            raise HTTPException(503, "artifact_provider_transport_configuration_invalid") from None

        extensions = scope.get("extensions")
        tls = extensions.get(EXTENSION) if isinstance(extensions, dict) else None
        certificate = tls.get("client_cert_der") if isinstance(tls, dict) else None
        if not isinstance(certificate, bytes) or not certificate or len(certificate) > 16384:
            raise HTTPException(403, "artifact_provider_certificate_required")
        pin = hashlib.sha256(certificate).hexdigest()
        binding = by_pin.get(pin)
        if binding is None:
            raise HTTPException(403, "artifact_provider_certificate_not_bound")
        try:
            leaf = x509.load_der_x509_certificate(certificate)
            now = datetime.now(timezone.utc)
            if not leaf.not_valid_before_utc <= now < leaf.not_valid_after_utc:
                raise ValueError("certificate_not_current")
            if leaf.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
                raise ValueError("not_client_leaf")
            if ExtendedKeyUsageOID.CLIENT_AUTH not in leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value:
                raise ValueError("client_auth_required")
        except (ValueError, x509.ExtensionNotFound, x509.DuplicateExtension):
            raise HTTPException(403, "artifact_provider_certificate_invalid") from None
        return ProviderPrincipal(**binding.__dict__)

    async def authenticate(self, request: Request) -> ProviderPrincipal:
        # Re-evaluate current configuration on every handler call; a state value
        # left by middleware does not keep a removed certificate admitted.
        return self.authenticate_scope(request.scope)


class ProviderTransportMiddleware:
    """Optional pure-ASGI exact-route gate; unrelated owner routes stay untouched."""
    def __init__(self, app, authenticator: ProviderTransportAuthenticator):
        self.app, self.authenticator = app, authenticator

    async def __call__(self, scope, receive, send):
        if not is_artifact_provider_route(scope):
            return await self.app(scope, receive, send)
        try:
            principal = self.authenticator.authenticate_scope(scope)
        except HTTPException as exc:
            body = json.dumps({"detail": exc.detail}).encode()
            await send({"type": "http.response.start", "status": exc.status_code,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        scope.setdefault("state", {})[STATE_PRINCIPAL] = principal
        await self.app(scope, receive, send)
