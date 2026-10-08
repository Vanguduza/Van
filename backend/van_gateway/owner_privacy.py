"""Credential and reference screening shared by owner projections; no runtime imports."""
from __future__ import annotations
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_SECRET = re.compile(
    r"(?i)(?:\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"password|passwd|authorization|(?:set-)?cookie|session[_-]?id)\b[\"']?\s*[:=]"
    r"|\bbearer\s+\S+|\bsk-[A-Za-z0-9_-]{16,}|-----BEGIN .*PRIVATE KEY-----|secretref://"
    r"|\b(?:otp|one[- ]time password|verification code)\b.{0,32}\b\d{4,8}\b"
    r"|\b\d{4,8}\b\s*(?:is your|otp|verification code))"
)
_HOST_PATH = re.compile(r"/(?:opt|etc|home|root|workspace|var|tmp)/[^\s\"'<>]*")
_REFERENCE_SCHEMES = frozenset({
    "http", "https", "gateway", "evidence", "vekl", "obsidian", "notebook", "notebook-operation",
    "knowledge", "research", "research-evidence", "browser-evidence", "provider-readback", "automation-run",
    "standing-intent", "ledger", "owner-fact", "reminder", "mission", "google-readiness", "google-job",
    "google-artifact", "memory-erasure", "canary", "synthetic", "test",
})


def _text(value: Any, bound: int = 512) -> str:
    text = str(value or "")
    if _SECRET.search(text):
        return "[redacted]"
    return _HOST_PATH.sub("[host path]", text)[:bound]


def _reference(value: Any) -> str | None:
    """Keep citations usable, without userinfo, query secrets or filesystem paths."""
    if not value:
        return None
    text = str(value)
    if _SECRET.search(text) or text.startswith("/"):
        return None
    try:
        url = urlsplit(text)
        if (url.scheme and url.scheme not in _REFERENCE_SCHEMES) or url.username or url.password:
            return None
        if url.scheme:
            fragment = "" if url.scheme in {"http", "https"} else url.fragment
            return _text(urlunsplit((url.scheme, url.netloc, url.path, "", fragment)), 1024)
    except ValueError:
        return None
    return _text(text, 1024)


