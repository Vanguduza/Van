"""Operator supplied profile routes confined to the APK's signed browser prefix."""
from __future__ import annotations

import json
from urllib.parse import urlsplit


def parse_profile_signal_urls(raw: str, *, manifest_base_url: str) -> dict[str, str]:
    try:
        routes = json.loads(raw or "{}")
        if not isinstance(routes, dict):
            raise ValueError
        if not routes:
            return {}
        base = urlsplit(manifest_base_url)
        if base.scheme != "https" or not base.hostname or base.username or base.password or base.query or base.fragment:
            raise ValueError
        prefix = base.path.rstrip("/")
        result = {}
        for alias, url in routes.items():
            if not isinstance(alias, str) or not alias or not isinstance(url, str) or len(url) > 2048:
                raise ValueError
            parsed = urlsplit(url)
            if (parsed.scheme != "https" or parsed.hostname != base.hostname
                    or (parsed.port or 443) != (base.port or 443)
                    or parsed.username or parsed.password or parsed.query or parsed.fragment
                    or any(segment in {".", ".."} for segment in parsed.path.split("/"))
                    or "%" in parsed.path or "\\" in parsed.path
                    or not (parsed.path == prefix or parsed.path.startswith(prefix + "/"))):
                raise ValueError
            result[alias] = url.rstrip("/")
        return result
    except (ValueError, TypeError) as exc:
        raise ValueError("browser_stream_profile_signal_urls_invalid") from exc


def signal_url_for_profile(profile_alias: str, *, profile_urls: dict[str, str], fallback_url: str) -> str:
    # An explicit map is complete operator policy; missing entries cannot silently
    # send the owner to a different authenticated browser profile.
    return profile_urls.get(profile_alias, "") if profile_urls else fallback_url
