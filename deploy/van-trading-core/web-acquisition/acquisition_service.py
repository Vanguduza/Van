#!/usr/bin/env python3
"""Loopback-only read-only worker for VAN public web acquisition.

Scrapling handles public HTTP and public dynamic rendering. Katana is an optional
shallow reconnaissance helper. Authentication, secrets, account-visible browser
profiles and semantic actions remain in the existing Browser Harness/Stagehand
plane; this worker has no credential API and no access to browser profile data.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SERVICE_VERSION = "van-web-acquisition-worker/1.0.0"
SCRAPLING_EXPECTED = os.getenv("VAN_SCRAPLING_VERSION", "0.4.15")
KATANA_EXPECTED = os.getenv("VAN_KATANA_VERSION", "1.4.0")
BIND = os.getenv("VAN_WEB_ACQUISITION_BIND", "127.0.0.1")
PORT = int(os.getenv("VAN_WEB_ACQUISITION_PORT", "9143"))
CHROMIUM = os.getenv("VAN_CHROMIUM_EXECUTABLE", "")
KATANA_BIN = os.getenv("VAN_KATANA_BIN", "/usr/local/bin/katana")
MAX_BODY_BYTES = 64 * 1024
MAX_RESULT_TEXT = int(os.getenv("VAN_WEB_ACQUISITION_MAX_TEXT_BYTES", str(512 * 1024)))
MAX_KATANA_ENDPOINTS = int(os.getenv("VAN_KATANA_MAX_ENDPOINTS", "2000"))
MAX_KATANA_DEPTH = int(os.getenv("VAN_KATANA_MAX_DEPTH", "3"))
MAX_KATANA_SECONDS = int(os.getenv("VAN_KATANA_MAX_SECONDS", "30"))
DOMAIN_RE = re.compile(r"^[a-z0-9.-]{1,253}$")

if BIND not in {"127.0.0.1", "::1", "localhost"}:
    raise SystemExit("web acquisition worker refuses non-loopback bind")


class WorkerError(RuntimeError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def safe_domain(value: Any) -> str:
    domain = str(value or "").strip().lower().rstrip(".")
    if not DOMAIN_RE.fullmatch(domain) or ".." in domain:
        raise WorkerError("TARGET_DOMAIN_INVALID", 422)
    return domain


def safe_url(value: Any, domain: str) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise WorkerError("URL_SCHEME_FORBIDDEN", 422)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host != domain and not host.endswith("." + domain):
        raise WorkerError("URL_OUTSIDE_TARGET_DOMAIN", 403)
    if parsed.username or parsed.password:
        raise WorkerError("URL_USERINFO_FORBIDDEN", 422)
    return url


def scrub_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    host = parsed.hostname.lower()
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}{parsed.path or '/'}"


def _scrapling_version() -> str | None:
    try:
        return importlib.metadata.version("scrapling")
    except importlib.metadata.PackageNotFoundError:
        return None


def _katana_version() -> str | None:
    path = Path(KATANA_BIN)
    if not path.is_file() or not os.access(path, os.X_OK):
        return None
    try:
        done = subprocess.run(
            [str(path), "-version"], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (done.stdout + "\n" + done.stderr).strip()
    match = re.search(r"(?:v)?(\d+\.\d+\.\d+)", text)
    return match.group(1) if match else None


def health() -> dict[str, Any]:
    scrapling = _scrapling_version()
    katana = _katana_version()
    return {
        "ok": scrapling == SCRAPLING_EXPECTED,
        "service": SERVICE_VERSION,
        "scrapling": scrapling,
        "scrapling_expected": SCRAPLING_EXPECTED,
        "katana": katana,
        "katana_expected": KATANA_EXPECTED,
        "katana_ready": katana == KATANA_EXPECTED,
        "chromium_ready": bool(CHROMIUM and Path(CHROMIUM).is_file()),
        "bind": BIND,
        "auth_surface": False,
        "challenge_solver_enabled": False,
    }


def _page_payload(page: Any, requested_url: str) -> dict[str, Any]:
    body = bytes(getattr(page, "body", b"") or b"")
    try:
        content = str(page.markdown(main_content_only=True))
        representation = "MARKDOWN_MAIN_CONTENT"
    except Exception:
        content = body.decode("utf-8", errors="replace")
        representation = "BODY_TEXT_FALLBACK"
    encoded = content.encode("utf-8", errors="replace")
    truncated = encoded[:MAX_RESULT_TEXT].decode("utf-8", errors="replace")
    status = int(getattr(page, "status", 0) or 0)
    final_url = scrub_url(str(getattr(page, "url", requested_url) or requested_url))
    return {
        "ok": True,
        "status": status,
        "final_url": final_url,
        "representation": representation,
        "content": truncated,
        "content_truncated": len(encoded) > MAX_RESULT_TEXT,
        "content_digest": "sha256:" + hashlib.sha256(body).hexdigest(),
        "byte_size": len(body),
        "contains_secrets": False,
    }


def scrapling_http(body: dict[str, Any], domain: str) -> dict[str, Any]:
    url = safe_url(body.get("url"), domain)
    try:
        from scrapling.fetchers import Fetcher
        page = Fetcher.get(url)
    except Exception as exc:
        raise WorkerError("SCRAPLING_HTTP_FAILED", 502) from exc
    return _page_payload(page, url)


def scrapling_browser(body: dict[str, Any], domain: str) -> dict[str, Any]:
    """Public dynamic fallback only; no profile, cookie or credential input exists."""
    url = safe_url(body.get("url"), domain)
    if not CHROMIUM or not Path(CHROMIUM).is_file():
        raise WorkerError("CHROMIUM_EXECUTABLE_UNAVAILABLE", 503)
    timeout_ms = max(1_000, min(int(body.get("timeout_ms", 30_000)), 60_000))
    try:
        from scrapling.fetchers import DynamicFetcher
        page = DynamicFetcher.fetch(
            url,
            executable_path=CHROMIUM,
            timeout=timeout_ms,
            network_idle=bool(body.get("network_idle", True)),
        )
    except Exception as exc:
        raise WorkerError("SCRAPLING_BROWSER_FAILED", 502) from exc
    return _page_payload(page, url)


def _collect_urls(value: Any, out: set[str]) -> None:
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            clean = scrub_url(value)
            if clean:
                out.add(clean)
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"raw", "body", "headers", "request_raw", "response_raw"}:
                continue
            _collect_urls(child, out)
        return
    if isinstance(value, list):
        for child in value:
            _collect_urls(child, out)


def katana_recon(body: dict[str, Any], domain: str) -> dict[str, Any]:
    url = safe_url(body.get("url"), domain)
    version = _katana_version()
    if version != KATANA_EXPECTED:
        raise WorkerError("KATANA_RUNTIME_UNAVAILABLE", 503)
    depth = max(1, min(int(body.get("depth", 2)), MAX_KATANA_DEPTH))
    duration = max(1, min(int(body.get("duration_seconds", 15)), MAX_KATANA_SECONDS))
    cmd = [
        KATANA_BIN, "-u", url, "-d", str(depth), "-ct", f"{duration}s",
        "-jc", "-jsonl", "-omit-raw", "-omit-body", "-silent",
        "-mrs", str(2 * 1024 * 1024), "-timeout", "10", "-retry", "1",
    ]
    try:
        done = subprocess.run(
            cmd, capture_output=True, text=True, timeout=duration + 10, check=False,
            env={"PATH": os.environ.get("PATH", "")},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkerError("KATANA_RECON_FAILED", 502) from exc
    if done.returncode != 0:
        raise WorkerError("KATANA_RECON_FAILED", 502)
    urls: set[str] = set()
    parsed_lines = 0
    for line in done.stdout.splitlines():
        if parsed_lines >= 20_000 or len(urls) >= MAX_KATANA_ENDPOINTS:
            break
        line = line.strip()
        if not line:
            continue
        parsed_lines += 1
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        found: set[str] = set()
        _collect_urls(item, found)
        for candidate in found:
            try:
                safe_url(candidate, domain)
            except WorkerError:
                continue
            urls.add(candidate)
            if len(urls) >= MAX_KATANA_ENDPOINTS:
                break
    return {
        "ok": True,
        "endpoints": sorted(urls),
        "endpoint_count": len(urls),
        "depth": depth,
        "duration_seconds": duration,
        "katana_version": version,
        "contains_secrets": False,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = SERVICE_VERSION

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[van-web-acquisition] {self.address_string()} {fmt % args}", flush=True)

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/health":
            status = health()
            self.send_json(200 if status["ok"] else 503, status)
            return
        self.send_json(404, {"error": "NOT_FOUND"})

    def do_POST(self) -> None:
        try:
            raw_length = self.headers.get("content-length")
            if raw_length is None:
                raise WorkerError("CONTENT_LENGTH_REQUIRED", 411)
            length = int(raw_length)
            if length < 0 or length > MAX_BODY_BYTES:
                raise WorkerError("REQUEST_TOO_LARGE", 413)
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise WorkerError("REQUEST_BODY_NOT_OBJECT", 422)
            if payload.get("mode") != "READ_ONLY_ACQUISITION":
                raise WorkerError("ACQUISITION_MODE_REQUIRED", 403)
            domain = safe_domain(payload.get("target_domain"))
            if self.path == "/fetch/http":
                result = scrapling_http(payload, domain)
            elif self.path == "/fetch/browser":
                result = scrapling_browser(payload, domain)
            elif self.path == "/recon/katana":
                result = katana_recon(payload, domain)
            else:
                raise WorkerError("OPERATION_NOT_ALLOWED", 404)
            self.send_json(200, result)
        except WorkerError as exc:
            self.send_json(exc.status, {"error": exc.code})
        except (json.JSONDecodeError, ValueError):
            self.send_json(400, {"error": "REQUEST_INVALID"})


def main() -> None:
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    server.daemon_threads = True
    print(f"{SERVICE_VERSION} listening on {BIND}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
