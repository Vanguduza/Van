#!/usr/bin/env python3
"""Loopback-only read-only worker for VAN public web acquisition.

Scrapling handles public HTTP and public dynamic rendering. Katana is an optional
shallow reconnaissance helper. Authentication, secrets, account-visible browser
profiles and semantic actions remain in the existing Browser Harness/Stagehand
plane; this worker has no credential API and no access to browser profile data.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import importlib.metadata
import json
import os
import re
import socket
import subprocess
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlparse

SERVICE_VERSION = "van-web-acquisition-worker/1.1.0"
SCRAPLING_EXPECTED = os.getenv("VAN_SCRAPLING_VERSION", "0.4.15")
CRAWLEE_EXPECTED = os.getenv("VAN_CRAWLEE_VERSION", "1.10.2")
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
MAX_CRAWLEE_PAGES = int(os.getenv("VAN_CRAWLEE_MAX_PAGES", "1000"))
MAX_CRAWLEE_DEPTH = int(os.getenv("VAN_CRAWLEE_MAX_DEPTH", "6"))
MAX_CRAWLEE_CONCURRENCY = int(os.getenv("VAN_CRAWLEE_MAX_CONCURRENCY", "12"))
MAX_CRAWLEE_TASKS_PER_MINUTE = int(os.getenv("VAN_CRAWLEE_MAX_TASKS_PER_MINUTE", "240"))
MAX_CRAWLEE_SECONDS = int(os.getenv("VAN_CRAWLEE_MAX_SECONDS", "300"))
MAX_CRAWLEE_JOBS = int(os.getenv("VAN_CRAWLEE_MAX_JOBS", "1"))
MAX_CRAWLEE_DISCOVERED_URLS = int(os.getenv("VAN_CRAWLEE_MAX_DISCOVERED_URLS", "2000"))
MAX_CRAWLEE_HOSTS = int(os.getenv("VAN_CRAWLEE_MAX_HOSTS", "32"))
MAX_CRAWLEE_PAGE_SUMMARIES = int(os.getenv("VAN_CRAWLEE_MAX_PAGE_SUMMARIES", "250"))
MAX_CRAWLEE_DISCOVERY_BYTES = int(os.getenv("VAN_CRAWLEE_MAX_DISCOVERY_BYTES", str(1024 * 1024)))
CRAWLEE_JOB_SLOTS = threading.BoundedSemaphore(max(1, MAX_CRAWLEE_JOBS))
DOMAIN_RE = re.compile(r"^[a-z0-9.-]{1,253}$")
SENSITIVE_QUERY_KEYS = {
    "access_token", "api_key", "apikey", "authorization", "auth",
    "credential", "password", "passwd", "session", "sessionid",
    "signature", "sig", "token", "x-amz-credential", "x-amz-signature",
}
NON_HTML_CRAWL_EXTENSIONS = {
    ".7z", ".avi", ".bmp", ".csv", ".doc", ".docx", ".epub", ".gif",
    ".gz", ".ico", ".jpeg", ".jpg", ".json", ".m4a", ".mkv", ".mov",
    ".mp3", ".mp4", ".pdf", ".png", ".rar", ".rss", ".svg", ".tar",
    ".tgz", ".wav", ".webm", ".webp", ".xls", ".xlsx", ".xml", ".zip",
}

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


def assert_public_resolution(url: str) -> None:
    """Refuse loopback/private/link-local/reserved destinations before egress."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise WorkerError("NON_PUBLIC_DESTINATION_FORBIDDEN", 403)
    try:
        literal = ipaddress.ip_address(host)
        addresses = {literal}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(info[4][0].split("%", 1)[0])
                for info in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
            }
        except (OSError, ValueError) as exc:
            raise WorkerError("PUBLIC_DNS_RESOLUTION_FAILED", 502) from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise WorkerError("NON_PUBLIC_DESTINATION_FORBIDDEN", 403)


def assert_scoped_final(url: str, domain: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host != domain and not host.endswith("." + domain):
        raise WorkerError("CROSS_DOMAIN_REDIRECT_REQUIRES_RECON", 409)
    assert_public_resolution(url)


def browser_public_guard(domain: str):
    """Return a Playwright page setup that blocks private egress and scope-changing navigation."""
    def setup(page):
        def route_handler(route):
            request = route.request
            try:
                target = request.url
                parsed = urlparse(target)
                if parsed.scheme not in {"http", "https"}:
                    route.abort()
                    return
                assert_public_resolution(target)
                host = (parsed.hostname or "").lower().rstrip(".")
                if request.is_navigation_request() and (
                    host != domain and not host.endswith("." + domain)
                ):
                    route.abort()
                    return
                route.continue_()
            except Exception:
                route.abort()
        page.route("**/*", route_handler)
    return setup


def safe_url(value: Any, domain: str) -> str:
    url = str(value or "").strip()
    if not url or len(url) > 4096:
        raise WorkerError("URL_LENGTH_INVALID", 422)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise WorkerError("URL_SCHEME_FORBIDDEN", 422)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host != domain and not host.endswith("." + domain):
        raise WorkerError("URL_OUTSIDE_TARGET_DOMAIN", 403)
    if parsed.username or parsed.password:
        raise WorkerError("URL_USERINFO_FORBIDDEN", 422)
    for key, _value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.strip().lower() in SENSITIVE_QUERY_KEYS:
            raise WorkerError("SENSITIVE_QUERY_FORBIDDEN", 422)
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


def _crawlee_version() -> str | None:
    try:
        return importlib.metadata.version("crawlee")
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
    crawlee = _crawlee_version()
    katana = _katana_version()
    return {
        "ok": scrapling == SCRAPLING_EXPECTED and crawlee == CRAWLEE_EXPECTED,
        "service": SERVICE_VERSION,
        "scrapling": scrapling,
        "scrapling_expected": SCRAPLING_EXPECTED,
        "crawlee": crawlee,
        "crawlee_expected": CRAWLEE_EXPECTED,
        "crawlee_ready": crawlee == CRAWLEE_EXPECTED,
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
    assert_public_resolution(url)
    try:
        from scrapling.fetchers import Fetcher
        page = Fetcher.get(
            url, follow_redirects="safe", max_redirects=10, timeout=30, retries=1
        )
    except Exception as exc:
        raise WorkerError("SCRAPLING_HTTP_FAILED", 502) from exc
    final_url = str(getattr(page, "url", url) or url)
    assert_scoped_final(final_url, domain)
    return _page_payload(page, url)


def scrapling_browser(body: dict[str, Any], domain: str) -> dict[str, Any]:
    """Public dynamic fallback only; no profile, cookie or credential input exists."""
    url = safe_url(body.get("url"), domain)
    assert_public_resolution(url)
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
            page_setup=browser_public_guard(domain),
        )
    except Exception as exc:
        raise WorkerError("SCRAPLING_BROWSER_FAILED", 502) from exc
    final_url = str(getattr(page, "url", url) or url)
    assert_scoped_final(final_url, domain)
    return _page_payload(page, url)


async def _crawlee_crawl_async(body: dict[str, Any], domain: str) -> dict[str, Any]:
    """Bounded public multi-page crawl.

    Crawlee supplies adaptive concurrency, request queue/deduplication, retry and
    public-session rotation. VAN remains authoritative: this returns sanitized
    page/discovery summaries for the gateway to persist into the VAN frontier.
    """
    seed = safe_url(body.get("url"), domain)
    assert_public_resolution(seed)
    max_pages = max(1, min(int(body.get("max_pages", 100)), MAX_CRAWLEE_PAGES))
    max_depth = max(0, min(int(body.get("max_depth", 3)), MAX_CRAWLEE_DEPTH))
    max_concurrency = max(
        1, min(int(body.get("max_concurrency", 6)), MAX_CRAWLEE_CONCURRENCY)
    )
    max_tasks_per_minute = max(
        1,
        min(
            int(body.get("max_tasks_per_minute", 120)),
            MAX_CRAWLEE_TASKS_PER_MINUTE,
        ),
    )
    crawl_timeout = max(
        30,
        min(
            int(body.get("timeout_seconds", 300)),
            MAX_CRAWLEE_SECONDS,
            1800,
        ),
    )

    try:
        from crawlee import ConcurrencySettings
        from crawlee.crawlers import BeautifulSoupCrawler, BeautifulSoupCrawlingContext
        from crawlee.http_clients import ImpitHttpClient
        from crawlee.storages import RequestQueue
    except Exception as exc:
        raise WorkerError("CRAWLEE_RUNTIME_UNAVAILABLE", 503) from exc

    pages: list[dict[str, Any]] = []
    discovered: set[str] = set()
    rejected = 0
    redirects_admitted = 0
    redirects_rejected = 0
    discovered_only_count = 0
    failed_urls: list[str] = []
    resolved_hosts: set[str] = set()

    def assert_crawl_public(candidate: str) -> None:
        host = (urlparse(candidate).hostname or "").lower().rstrip(".")
        if host not in resolved_hosts:
            if len(resolved_hosts) >= max(1, MAX_CRAWLEE_HOSTS):
                raise WorkerError("CRAWLEE_HOST_BUDGET_EXCEEDED", 422)
            assert_public_resolution(candidate)
            resolved_hosts.add(host)

    # Never share Crawlee's implicit default queue between VAN jobs. The VAN
    # item id is sanitized into a run-scoped alias; the queue is dropped after
    # this bounded crawl. Cross-job durability belongs to the VAN frontier.
    raw_item_id = str(body.get("item_id") or "anonymous").lower()
    queue_alias = "van-" + re.sub(r"[^a-z0-9]+", "-", raw_item_id).strip("-")[:80]
    request_queue = await RequestQueue.open(alias=queue_alias)
    await request_queue.purge()
    assert_crawl_public(seed)

    crawler = BeautifulSoupCrawler(
        request_manager=request_queue,
        http_client=ImpitHttpClient(follow_redirects=False),
        max_requests_per_crawl=max_pages,
        max_crawl_depth=max_depth,
        max_request_retries=2,
        use_session_pool=True,
        retry_on_blocked=False,
        concurrency_settings=ConcurrencySettings(
            min_concurrency=1,
            desired_concurrency=1,
            max_concurrency=max_concurrency,
            max_tasks_per_minute=max_tasks_per_minute,
        ),
        navigation_timeout=timedelta(seconds=20),
        request_handler_timeout=timedelta(seconds=30),
        respect_robots_txt_file=bool(body.get("respect_robots_txt", True)),
    )

    @crawler.router.default_handler
    async def request_handler(context: BeautifulSoupCrawlingContext) -> None:
        nonlocal rejected, redirects_admitted, redirects_rejected, discovered_only_count
        if len(pages) >= max_pages:
            crawler.stop("VAN max_pages reached")
            return
        requested_url = safe_url(str(context.request.url), domain)
        assert_crawl_public(requested_url)

        # Redirects are handled explicitly because Impit is configured with
        # follow_redirects=False. This prevents a scope-changing redirect from
        # being contacted before VAN validates it.
        status_code = int(context.http_response.status_code)
        if 300 <= status_code < 400:
            location = None
            for header_name in context.http_response.headers:
                if str(header_name).lower() == "location":
                    location = str(context.http_response.headers[header_name])
                    break
            if location:
                redirected = urljoin(requested_url, location)
                try:
                    safe_url(redirected, domain)
                    assert_crawl_public(redirected)
                except WorkerError:
                    redirects_rejected += 1
                    return
                redirects_admitted += 1
                discovered.add(redirected)
                await context.add_requests(
                    [redirected],
                    strategy="same-domain",
                    limit=1,
                )
            return

        loaded_url = str(getattr(context.request, "loaded_url", None) or requested_url)
        assert_scoped_final(loaded_url, domain)
        assert_crawl_public(loaded_url)

        html = str(context.soup)
        raw = html.encode("utf-8", errors="replace")
        pages.append(
            {
                "url": scrub_url(loaded_url),
                "title": (
                    str(context.soup.title.string)[:512]
                    if context.soup.title and context.soup.title.string
                    else None
                ),
                "content_digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "byte_size": len(raw),
            }
        )

        candidates: list[str] = []
        for link in context.soup.find_all("a", href=True)[:5000]:
            href = str(link.get("href") or "").strip()
            if not href:
                continue
            candidate = urljoin(loaded_url, href)
            try:
                safe_url(candidate, domain)
                assert_crawl_public(candidate)
            except WorkerError:
                rejected += 1
                continue
            if len(discovered) < MAX_CRAWLEE_DISCOVERED_URLS:
                discovered.add(candidate)
                suffix = Path(urlparse(candidate).path).suffix.lower()
                if suffix in NON_HTML_CRAWL_EXTENSIONS:
                    discovered_only_count += 1
                    continue
                candidates.append(candidate)

        remaining = max_pages - len(pages)
        if remaining <= 0:
            crawler.stop("VAN max_pages reached")
            return
        if candidates:
            await context.add_requests(
                candidates,
                strategy="same-domain",
                limit=remaining,
            )

    @crawler.failed_request_handler
    async def failed_request_handler(context: Any, error: Exception) -> None:
        if len(failed_urls) < 100:
            failed_urls.append(scrub_url(str(context.request.url)))

    try:
        try:
            final_statistics = await asyncio.wait_for(
                crawler.run([seed], purge_request_queue=False),
                timeout=crawl_timeout,
            )
        except TimeoutError as exc:
            raise WorkerError("CRAWLEE_TIMEOUT", 504) from exc
        except WorkerError:
            raise
        except Exception as exc:
            raise WorkerError("CRAWLEE_CRAWL_FAILED", 502) from exc
    finally:
        try:
            await request_queue.drop()
        except Exception:
            # Cleanup failure must not change crawl truth; the next job uses a
            # distinct alias and the service storage directory is bounded.
            pass

    if not pages or int(final_statistics.requests_finished) < 1:
        raise WorkerError("CRAWLEE_NO_PAGES", 502)

    bounded_discovered: list[str] = []
    discovery_bytes = 0
    for candidate in sorted(discovered):
        encoded_len = len(candidate.encode("utf-8", errors="replace"))
        if discovery_bytes + encoded_len > max(1024, MAX_CRAWLEE_DISCOVERY_BYTES):
            break
        bounded_discovered.append(candidate)
        discovery_bytes += encoded_len

    summary = {
        "seed": scrub_url(seed),
        "pages": pages[: max(1, MAX_CRAWLEE_PAGE_SUMMARIES)],
        "page_summaries_truncated": len(pages) > max(1, MAX_CRAWLEE_PAGE_SUMMARIES),
        "discovered_urls": bounded_discovered,
        "discovered_urls_truncated": len(bounded_discovered) < len(discovered),
        "discovery_url_bytes": discovery_bytes,
        "visited_count": len(pages),
        "discovered_count": len(discovered),
        "rejected_count": rejected,
        "redirects_admitted": redirects_admitted,
        "redirects_rejected": redirects_rejected,
        "discovered_only_count": discovered_only_count,
        "requests_total": int(final_statistics.requests_total),
        "requests_finished": int(final_statistics.requests_finished),
        "requests_failed": int(final_statistics.requests_failed),
        "retry_histogram": list(final_statistics.retry_histogram),
        "partial": int(final_statistics.requests_failed) > 0,
        "failed_urls": failed_urls,
        "resolved_host_count": len(resolved_hosts),
        "max_hosts": max(1, MAX_CRAWLEE_HOSTS),
        "max_pages": max_pages,
        "max_depth": max_depth,
        "max_concurrency": max_concurrency,
        "max_tasks_per_minute": max_tasks_per_minute,
        "timeout_seconds": crawl_timeout,
        "crawlee_version": _crawlee_version(),
    }
    encoded = json.dumps(summary, sort_keys=True, separators=(",", ":")).encode("utf-8")
    summary["content_digest"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    summary["byte_size"] = sum(int(page["byte_size"]) for page in pages)
    summary["contains_secrets"] = False
    summary["ok"] = True
    return summary


def crawlee_crawl(body: dict[str, Any], domain: str) -> dict[str, Any]:
    if not CRAWLEE_JOB_SLOTS.acquire(blocking=False):
        raise WorkerError("CRAWLEE_BUSY", 429)
    try:
        return asyncio.run(_crawlee_crawl_async(body, domain))
    finally:
        CRAWLEE_JOB_SLOTS.release()


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
    assert_public_resolution(url)
    version = _katana_version()
    if version != KATANA_EXPECTED:
        raise WorkerError("KATANA_RUNTIME_UNAVAILABLE", 503)
    depth = max(1, min(int(body.get("depth", 2)), MAX_KATANA_DEPTH))
    duration = max(1, min(int(body.get("duration_seconds", 15)), MAX_KATANA_SECONDS))
    cmd = [
        KATANA_BIN, "-u", url, "-d", str(depth), "-ct", f"{duration}s",
        "-jc", "-jsonl", "-omit-raw", "-omit-body", "-silent",
        "-e", "private-ips", "-fs", "rdn", "-c", "2", "-p", "1",
        "-rl", "5", "-mdp", "500", "-duc",
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
            elif self.path == "/crawl/crawlee":
                result = crawlee_crawl(payload, domain)
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
