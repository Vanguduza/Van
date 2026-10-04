"""Repository contract for the public web-acquisition worker."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "deploy/van-trading-core/web-acquisition/acquisition_service.py"
RUNTIME_ENV = ROOT / "deploy/van-trading-core/web-acquisition/runtime.env.example"
REQUIREMENTS = ROOT / "deploy/van-trading-core/web-acquisition/requirements.txt"


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


def test_runtime_dependency_is_exactly_pinned():
    requirements = REQUIREMENTS.read_text(encoding="utf-8").strip()
    assert requirements == "scrapling[rag]==0.4.15"


def test_katana_is_bounded_shallow_recon_not_authenticated_browser():
    source = _source()
    assert '"-jc"' in source
    assert '"-omit-raw"' in source
    assert '"-omit-body"' in source
    assert "MAX_KATANA_DEPTH" in source
    assert "MAX_KATANA_SECONDS" in source
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
