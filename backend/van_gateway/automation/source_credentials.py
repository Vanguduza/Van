"""Operator-bound source credentials stay on the gateway, outside n8n graphs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlparse

from van_gateway.automation.credentials import CredentialAlias, CredentialClass, CredentialResolver
from van_gateway.automation.policy import PolicyError


class SourceCredentialError(PolicyError):
    pass


class SourceCredentialStore:
    MAX_BYTES = 65536

    def __init__(self, configuration_file: str = "") -> None:
        self.configuration_file = configuration_file

    @property
    def configured(self) -> bool:
        return bool(self.configuration_file)

    @classmethod
    def _protected_read(cls, filename: str) -> str:
        if not isinstance(filename, str) or not Path(filename).is_absolute():
            raise SourceCredentialError("SOURCE_CREDENTIAL_FILE_INVALID")
        descriptor = None
        try:
            descriptor = os.open(filename, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.getuid()}
                    or info.st_mode & 0o077 or info.st_size > cls.MAX_BYTES):
                raise SourceCredentialError("SOURCE_CREDENTIAL_FILE_NOT_PROTECTED")
            data = os.read(descriptor, cls.MAX_BYTES + 1)
            if len(data) > cls.MAX_BYTES:
                raise SourceCredentialError("SOURCE_CREDENTIAL_FILE_INVALID")
            return data.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise SourceCredentialError("SOURCE_CREDENTIAL_FILE_UNAVAILABLE") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _entries(self) -> dict:
        if not self.configured:
            return {}
        try:
            payload = json.loads(self._protected_read(self.configuration_file))
        except ValueError as exc:
            raise SourceCredentialError("SOURCE_CREDENTIAL_CONFIGURATION_INVALID") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(payload.get("aliases"), dict):
            raise SourceCredentialError("SOURCE_CREDENTIAL_CONFIGURATION_INVALID")
        entries = payload["aliases"]
        if len(entries) > 64:
            raise SourceCredentialError("SOURCE_CREDENTIAL_CONFIGURATION_INVALID")
        for name, entry in entries.items():
            try:
                if not isinstance(entry, dict) or entry.get("admitted") is not True:
                    raise ValueError("alias not admitted")
                credential_class = CredentialClass(entry["credential_class"])
                if credential_class not in {CredentialClass.C3_SENSITIVE_INTEGRATION, CredentialClass.C4_LOW_RISK_INTEGRATION}:
                    raise ValueError("class not permitted")
                CredentialResolver().register(CredentialAlias(name, credential_class, admitted=True))
                domains = entry["allowed_domains"]
                if (not isinstance(domains, list) or not domains or len(domains) > 32
                        or any(not isinstance(domain, str) or re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain) is None
                               or ".." in domain for domain in domains)):
                    raise ValueError("domain invalid")
                if entry["header_name"] not in {"Authorization", "X-API-Key"}:
                    raise ValueError("header not permitted")
                if entry.get("value_prefix", "") not in {"", "Bearer ", "Token "}:
                    raise ValueError("prefix not permitted")
                if not isinstance(entry["token_file"], str) or not Path(entry["token_file"]).is_absolute():
                    raise ValueError("token file invalid")
                methods = entry.get("allowed_methods", ["GET"])
                if (not isinstance(methods, list) or not methods or len(methods) != len(set(methods))
                        or any(method not in {"GET", "POST", "PUT", "PATCH", "DELETE"} for method in methods)):
                    raise ValueError("method invalid")
            except (KeyError, ValueError, TypeError, PolicyError) as exc:
                raise SourceCredentialError("SOURCE_CREDENTIAL_CONFIGURATION_INVALID") from exc
        return entries

    def has(self, alias: str, domain: str | None = None, method: str = "GET") -> bool:
        entry = self._entries().get(alias)
        return bool(entry and (domain is None or domain in entry["allowed_domains"]) and method in entry.get("allowed_methods", ["GET"]))

    def admitted_handles(self, aliases: list[str]) -> dict[str, str]:
        """Non-secret semantic handles, never n8n credential IDs or header values."""
        entries = self._entries()
        if any(alias not in entries for alias in aliases):
            raise SourceCredentialError("SOURCE_CREDENTIAL_ALIAS_UNAVAILABLE")
        return {alias: "gateway-protected-source" for alias in aliases}

    async def headers(self, alias: str, url: str, *, method: str = "GET") -> dict[str, str]:
        entry = self._entries().get(alias)
        if entry is None:
            raise SourceCredentialError("SOURCE_CREDENTIAL_ALIAS_UNAVAILABLE")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.hostname not in entry["allowed_domains"]:
            raise SourceCredentialError("SOURCE_CREDENTIAL_DOMAIN_DENIED")
        if method not in entry.get("allowed_methods", ["GET"]):
            raise SourceCredentialError("SOURCE_CREDENTIAL_METHOD_DENIED")
        token = self._protected_read(entry["token_file"]).strip()
        if not token or len(token) > 16384 or any(character in token for character in "\r\n\x00"):
            raise SourceCredentialError("SOURCE_CREDENTIAL_TOKEN_INVALID")
        return {entry["header_name"]: entry.get("value_prefix", "") + token}
