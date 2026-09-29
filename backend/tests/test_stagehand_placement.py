"""Owner decisions 2026-09-29 §§1, 4, 5 — Stagehand production placement/model gate."""

from __future__ import annotations

import pytest

from van_gateway.automation.placement import (
    FORBIDDEN_STAGEHAND_ZONES,
    STAGEHAND_PLACEMENT_SATISFIED,
    stagehand_production_enabled,
    stagehand_production_state,
)
from van_gateway.config import Settings


def _pki(tmp_path):
    paths = {}
    for name in ("browser_core_ca_file", "browser_core_client_cert_file", "browser_core_client_key_file"):
        p = tmp_path / f"{name}.pem"
        p.write_text("placeholder-not-a-key\n", encoding="utf-8")
        paths[name] = str(p)
    return paths


def _ready_settings(tmp_path, **overrides) -> Settings:
    values = dict(
        browser_enabled=True,
        browser_stagehand_zone="van-browser-core",
        browser_stagehand_base_url="https://10.77.0.6:9443/stagehand",
        **_pki(tmp_path),
    )
    values.update(overrides)
    return Settings(**values)


def _healthy(**overrides) -> dict:
    body = {
        "ok": True,
        "trust_zone": "van-browser-core",
        "runtime_version": "4.1.0",
        "model_name": "anthropic/claude-sonnet-5",
        "model_key_present": True,
        "provider_key_in_browser_memory": False,
        "direct_agent_loop": False,
        "model_self_selection": False,
    }
    body.update(overrides)
    return body


def test_default_model_is_the_owner_decided_pair_not_empty():
    s = Settings()
    assert (s.browser_stagehand_model_provider, s.browser_stagehand_model_name) == (
        "anthropic",
        "claude-sonnet-5",
    )
    # The immutable snapshot id is not established from this repository.
    assert s.browser_stagehand_model_revision == ""
    assert stagehand_production_state(s)["model_revision_status"] == "UNVERIFIED_IMMUTABLE_SNAPSHOT"


def test_default_settings_are_production_disabled():
    enabled, reason = stagehand_production_enabled(Settings())
    assert enabled is False
    assert reason == "BROWSER_FABRIC_DISABLED"
    enabled, reason = stagehand_production_enabled(Settings(browser_enabled=True))
    assert (enabled, reason) == (False, "STAGEHAND_ZONE_UNDECLARED")


@pytest.mark.parametrize("zone", sorted(FORBIDDEN_STAGEHAND_ZONES))
def test_forbidden_zones_are_refused_by_name(tmp_path, zone):
    s = _ready_settings(tmp_path, browser_stagehand_zone=zone)
    enabled, reason = stagehand_production_enabled(s, worker_health=_healthy(trust_zone=zone))
    assert enabled is False
    assert reason == f"STAGEHAND_PLACEMENT_FORBIDDEN:{zone}"


def test_unknown_zone_is_refused(tmp_path):
    s = _ready_settings(tmp_path, browser_stagehand_zone="some-other-host")
    assert stagehand_production_enabled(s, worker_health=_healthy())[1].startswith(
        "STAGEHAND_ZONE_NOT_VAN_BROWSER_CORE"
    )


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:9140", "https://127.0.0.1:9140", "http://10.77.0.6:9140", ""],
)
def test_loopback_or_unauthenticated_endpoint_is_not_cross_zone(tmp_path, url):
    s = _ready_settings(tmp_path, browser_stagehand_base_url=url)
    assert stagehand_production_enabled(s, worker_health=_healthy()) == (
        False,
        "STAGEHAND_ENDPOINT_NOT_CROSS_ZONE_MTLS",
    )


@pytest.mark.parametrize(
    "url",
    [
        # review I minor 4: a literal set let these through.
        "https://127.0.0.2:9443",
        "https://localhost.:9443",
        "https://LOCALHOST:9443",
        "https://127.255.255.254:9443",
        "https://127.1:9443",
        "https://2130706433:9443",
        "https://0x7f.1:9443",
        "https://[::1]:9443",
        "https://[0:0:0:0:0:0:0:1]:9443",
        "https://[::ffff:127.0.0.1]:9443",
        "https://[::]:9443",
        "https://0.0.0.0:9443",
        "https://0:9443",
        "https://169.254.169.254:9443",
        "https://[fe80::1]:9443",
        "https://browser.localhost:9443",
        "https://browser.localhost.:9443",
        "https://localhost.localdomain:9443",
    ],
)
def test_every_loopback_link_local_or_unspecified_host_is_refused(tmp_path, url):
    s = _ready_settings(tmp_path, browser_stagehand_base_url=url)
    assert stagehand_production_enabled(s, worker_health=_healthy()) == (
        False,
        "STAGEHAND_ENDPOINT_NOT_CROSS_ZONE_MTLS",
    )


@pytest.mark.parametrize(
    "url", ["https://10.77.0.6:9443/stagehand", "https://browser-core.van.internal:9443", "https://[fd00::6]:9443"]
)
def test_cross_zone_hosts_still_pass_the_endpoint_check(tmp_path, url):
    s = _ready_settings(tmp_path, browser_stagehand_base_url=url)
    assert stagehand_production_enabled(s, worker_health=_healthy()) == (True, STAGEHAND_PLACEMENT_SATISFIED)


def test_missing_mtls_client_identity_disables(tmp_path):
    s = _ready_settings(tmp_path, browser_core_client_key_file=str(tmp_path / "absent.key"))
    enabled, reason = stagehand_production_enabled(s, worker_health=_healthy())
    assert enabled is False
    assert reason == "STAGEHAND_MTLS_CLIENT_IDENTITY_MISSING:browser_core_client_key_file"


@pytest.mark.parametrize(
    ("provider", "model"),
    [("anthropic", "claude-sonnet-4-5"), ("anthropic", "claude-sonnet-4-6"), ("openai", "gpt-5.5")],
)
def test_no_silent_downgrade_or_substitution(tmp_path, provider, model):
    s = _ready_settings(
        tmp_path, browser_stagehand_model_provider=provider, browser_stagehand_model_name=model
    )
    enabled, reason = stagehand_production_enabled(s, worker_health=_healthy(model_name=f"{provider}/{model}"))
    assert enabled is False
    assert reason == f"STAGEHAND_MODEL_NOT_OWNER_DECIDED:{provider}/{model}"


def test_unavailable_zone_is_production_disabled(tmp_path):
    s = _ready_settings(tmp_path)
    assert stagehand_production_enabled(s) == (False, "VAN_BROWSER_CORE_UNAVAILABLE:health_unverified")
    assert stagehand_production_enabled(s, worker_health=_healthy(ok=False))[0] is False


def test_running_zone_must_be_proved_by_the_worker(tmp_path):
    s = _ready_settings(tmp_path)
    enabled, reason = stagehand_production_enabled(
        s, worker_health=_healthy(trust_zone="van-trading-core")
    )
    assert (enabled, reason) == (False, "STAGEHAND_RUNNING_ZONE_MISMATCH:van-trading-core")
    enabled, reason = stagehand_production_enabled(s, worker_health=_healthy(trust_zone=None))
    assert (enabled, reason) == (False, "STAGEHAND_RUNNING_ZONE_MISMATCH:unreported")


def test_runtime_version_and_model_must_match(tmp_path):
    s = _ready_settings(tmp_path)
    assert stagehand_production_enabled(s, worker_health=_healthy(runtime_version="4.2.0-alpha"))[1] == (
        "STAGEHAND_RUNTIME_VERSION_MISMATCH"
    )
    assert stagehand_production_enabled(
        s, worker_health=_healthy(model_name="anthropic/claude-sonnet-4-6")
    )[1] == "STAGEHAND_RUNTIME_MODEL_MISMATCH"


def test_provider_key_in_browser_memory_disables(tmp_path):
    """Stagehand 4.1.0's default model path hands the key to its in-Chromium worker."""
    s = _ready_settings(tmp_path)
    for value in (True, None):
        enabled, reason = stagehand_production_enabled(
            s, worker_health=_healthy(provider_key_in_browser_memory=value)
        )
        assert (enabled, reason) == (False, "STAGEHAND_PROVIDER_KEY_ENTERS_BROWSER_MEMORY")


def test_all_placement_conditions_met(tmp_path):
    s = _ready_settings(tmp_path)
    assert stagehand_production_enabled(s, worker_health=_healthy()) == (
        True,
        STAGEHAND_PLACEMENT_SATISFIED,
    )
    state = stagehand_production_state(s, worker_health=_healthy())
    assert state["state"] == "PLACEMENT_SATISFIED"
    assert state["stagehand_release_commit"] == "cd7b230778cf92269e4cb90e80d97f5113781c51"


def test_settings_carry_no_credential_value_for_the_model():
    """§4 — the model name is configured; no provider key is a Settings field."""
    fields = set(Settings.model_fields)
    stagehand_fields = {f for f in fields if "stagehand" in f}
    assert not {f for f in stagehand_fields if "key" in f or "token" in f or "secret" in f}
