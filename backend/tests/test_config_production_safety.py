"""GAP-F-018 / GAP-F-021 — a production `Settings` must refuse migration-era and
loopback-only defaults, at construction, not at the first request that needed them.
"""

from __future__ import annotations

import pytest

from van_gateway.config import Settings


def _base_env(monkeypatch, **overrides):
    """A settings environment with nothing left to its default that the validator
    would otherwise trip on, so each test can flip exactly the one thing it checks."""
    env = {
        "VAN_ENV": "production",
        "VAN_REQUIRE_DEVICE_BINDING": "true",
        "VAN_HERMES_BASE_URL": "https://hermes.internal.example",
        "VAN_PUBLIC_BASE_URL": "https://van.example.com",
    }
    env.update(overrides)
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_development_is_unconstrained_by_default(monkeypatch):
    """The validator must be a no-op for every existing caller that never set VAN_ENV."""
    monkeypatch.delenv("VAN_ENV", raising=False)
    settings = Settings()
    assert settings.van_env == "development"
    assert settings.require_device_binding is False
    # No exception: the loopback defaults and require_device_binding=False are both
    # fine outside production.
    settings.assert_production_safe()


def test_production_refuses_require_device_binding_false(monkeypatch):
    _base_env(monkeypatch, VAN_REQUIRE_DEVICE_BINDING="false")
    with pytest.raises(ValueError, match="VAN_REQUIRE_DEVICE_BINDING must be true"):
        Settings()


def test_production_refuses_a_loopback_hermes_base_url(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.delenv("VAN_HERMES_BASE_URL", raising=False)  # falls back to the default
    with pytest.raises(ValueError, match="VAN_HERMES_BASE_URL"):
        Settings()


def test_production_refuses_a_loopback_public_base_url(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.delenv("VAN_PUBLIC_BASE_URL", raising=False)  # falls back to the default
    with pytest.raises(ValueError, match="VAN_PUBLIC_BASE_URL"):
        Settings()


def test_production_accepts_explicit_non_loopback_urls(monkeypatch):
    _base_env(monkeypatch)
    settings = Settings()
    assert settings.van_env == "production"
    assert settings.hermes_base_url == "https://hermes.internal.example"
    assert settings.van_public_base_url == "https://van.example.com"


def test_the_loopback_override_is_explicit_and_narrow(monkeypatch):
    """The escape hatch exists for a genuinely colocated deployment, and only covers
    the loopback refusal — it must never also excuse require_device_binding=False."""
    _base_env(
        monkeypatch,
        VAN_ALLOW_LOOPBACK_IN_PRODUCTION="1",
    )
    monkeypatch.delenv("VAN_HERMES_BASE_URL", raising=False)
    monkeypatch.delenv("VAN_PUBLIC_BASE_URL", raising=False)
    settings = Settings()
    assert settings.van_allow_loopback_in_production is True
    assert settings.hermes_base_url == "http://127.0.0.1:8642"

    monkeypatch.setenv("VAN_REQUIRE_DEVICE_BINDING", "false")
    with pytest.raises(ValueError, match="VAN_REQUIRE_DEVICE_BINDING must be true"):
        Settings()


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8642",
        "http://localhost:8642",
        "http://0.0.0.0:8642",
        "http://[::1]:8642",  # IPv6 loopback needs brackets in a URL authority
    ],
)
def test_every_loopback_spelling_is_caught(monkeypatch, url):
    _base_env(monkeypatch, VAN_HERMES_BASE_URL=url)
    with pytest.raises(ValueError, match="VAN_HERMES_BASE_URL"):
        Settings()


def test_a_non_loopback_host_that_merely_contains_localhost_is_not_flagged(monkeypatch):
    """The hostname is matched exactly, not by substring, so a real domain like
    `notlocalhost.example.com` is never mistaken for the loopback interface."""
    _base_env(monkeypatch, VAN_HERMES_BASE_URL="https://notlocalhost.example.com")
    Settings()  # must not raise
