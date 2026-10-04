"""Repository contract for the public web-acquisition worker."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "deploy/van-trading-core/web-acquisition/acquisition_service.py"
RUNTIME_ENV = ROOT / "deploy/van-trading-core/web-acquisition/runtime.env.example"
REQUIREMENTS = ROOT / "deploy/van-trading-core/web-acquisition/requirements.txt"
SYSTEMD_UNIT = ROOT / "deploy/van-trading-core/systemd/vati-web-acquisition.service"
BOOTSTRAP = ROOT / "deploy/van-trading-core/web-acquisition/bootstrap-web-acquisition-runtime.sh"


def _source() -> str:
    return SERVICE.read_text(encoding="utf-8")


def test_acquisition_worker_is_loopback_read_only_and_has_no_auth_surface():
    source = _source()
    env = RUNTIME_ENV.read_text(encoding="utf-8")
    assert 'BIND = os.getenv("VAN_WEB_ACQUISITION_BIND", "127.0.0.1")' in source
    assert "READ_ONLY_ACQUISITION" in source
    assert '"auth_surface": False' in source
    assert '"challenge_solver_enabled": False' in source
    assert "StealthyFetcher" not in source
    assert "solve_cloudflare" not in source
    assert "secretref://" not in source
    assert "profile_alias" not in source
    assert "VAN_WEB_ACQUISITION_BIND=127.0.0.1" in env


def test_runtime_dependencies_are_exactly_pinned():
    requirements = REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    assert requirements == [
        "scrapling[rag]==0.4.15",
        "crawlee[beautifulsoup]==1.10.2",
    ]


def test_katana_is_bounded_shallow_recon_not_authenticated_browser():
    source = _source()
    assert '"-jc"' in source
    assert '"-omit-raw"' in source
    assert '"-omit-body"' in source
    assert "MAX_KATANA_DEPTH" in source
    assert "MAX_KATANA_SECONDS" in source
    assert '"private-ips"' in source
    assert '"-fs", "rdn"' in source
    assert '"-rl", "5"' in source
    assert "assert_public_resolution" in source
    assert "browser_public_guard" in source
    assert '"-H"' not in source
    assert "Cookie:" not in source
    assert '"-headless"' not in source
    assert '"-xhr"' not in source


def test_url_boundary_rejects_cross_domain_and_userinfo(monkeypatch):
    monkeypatch.setenv("VAN_WEB_ACQUISITION_BIND", "127.0.0.1")
    spec = importlib.util.spec_from_file_location("van_acquisition_worker", SERVICE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.safe_url("https://shop.example.com/a", "example.com").endswith("/a")
    with pytest.raises(module.WorkerError, match="OUTSIDE_TARGET_DOMAIN"):
        module.safe_url("https://attacker.example.net/a", "example.com")
    with pytest.raises(module.WorkerError, match="USERINFO_FORBIDDEN"):
        module.safe_url("https://user:pass@example.com/a", "example.com")


def test_crawlee_is_bulk_public_orchestration_not_authority():
    source = _source()
    env = RUNTIME_ENV.read_text(encoding="utf-8")
    assert 'CRAWLEE_EXPECTED = os.getenv("VAN_CRAWLEE_VERSION", "1.10.2")' in source
    assert '"/crawl/crawlee"' in source
    assert "BeautifulSoupCrawler" in source
    assert "ConcurrencySettings" in source
    assert "use_session_pool=True" in source
    assert "retry_on_blocked=False" in source
    assert "ImpitHttpClient(follow_redirects=False)" in source
    assert "max_requests_per_crawl=max_pages" in source
    assert "max_crawl_depth=max_depth" in source
    assert "max_tasks_per_minute=max_tasks_per_minute" in source
    assert "VAN_CRAWLEE_MAX_PAGES=1000" in env
    assert "VAN_CRAWLEE_MAX_DEPTH=6" in env
    assert "VAN_CRAWLEE_MAX_CONCURRENCY=12" in env
    assert "VAN_CRAWLEE_MAX_TASKS_PER_MINUTE=240" in env
    assert "VAN_CRAWLEE_MAX_SECONDS=300" in env
    assert "VAN_CRAWLEE_MAX_JOBS=1" in env
    assert "VAN_CRAWLEE_MAX_DISCOVERED_URLS=2000" in env
    assert "CRAWLEE_JOB_SLOTS" in source
    assert "asyncio.wait_for" in source
    assert "request_handler_timeout=timedelta(seconds=30)" in source
    assert "navigation_timeout=timedelta(seconds=20)" in source


def test_acquisition_service_is_least_privilege_and_resource_bounded():
    unit = SYSTEMD_UNIT.read_text(encoding="utf-8")
    assert "User=van-acquisition" in unit
    assert "Group=van-acquisition" in unit
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "ProtectHome=true" in unit
    assert "MemoryMax=1024M" in unit
    assert "TasksMax=256" in unit
    assert "CPUWeight=10" in unit
    assert "IPAddressDeny=10.0.0.0/8" in unit
    assert "IPAddressDeny=169.254.0.0/16" in unit
    assert "IPAddressDeny=fc00::/7" in unit


def test_bootstrap_verifies_exact_worker_dependency_versions():
    script = BOOTSTRAP.read_text(encoding="utf-8")
    assert "python3.12 -m venv" in script
    assert '"scrapling":"0.4.15"' in script
    assert '"crawlee":"1.10.2"' in script
    assert "van-web-acquisition-worker/1.1.0" in script
    assert "crawlee_ready" in script
    assert "challenge_solver_enabled" in script
    assert "systemctl enable vati-web-acquisition.service" in script
