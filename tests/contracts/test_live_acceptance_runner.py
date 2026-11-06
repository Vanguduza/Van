"""Unit validation of the live runner's refusal/evidence rules; no live receipts here."""

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("live_acceptance", ROOT / "tools/certification/run_live_acceptance.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def ready(**changes):
    return {"state": "READY", "configured": True, "egress_enabled": True,
            "contains_secrets": False, "evidence_pointer": "gateway://synthetic-canary",
            "verified_at_ms": 1_000_000, "runtime_version": "1.2.3", "expected_version": "1.2.3", **changes}


@pytest.mark.parametrize("changes", [
    {"state": "CONFIGURED"}, {"configured": False}, {"egress_enabled": False},
    {"contains_secrets": True}, {"evidence_pointer": ""}, {"verified_at_ms": None},
    {"verified_at_ms": 1}, {"verified_at_ms": 2_000_000}, {"runtime_version": "1.2.4"},
])
def test_reported_ready_needs_current_canary_and_matching_runtime(changes):
    assert runner.runtime_ready(ready(), 1_100_000, 200)
    assert not runner.runtime_ready(ready(**changes), 1_100_000, 200)


@pytest.mark.parametrize("target", ["http://gateway.invalid", "https://token@gateway.invalid", "https://gateway.invalid?token=secret", "https://gateway.invalid#secret"])
def test_secret_bearing_or_cleartext_targets_are_refused(target):
    with pytest.raises(ValueError):
        runner.base_url(target)


def test_documented_hermes_loopback_does_not_enable_public_cleartext_credentials():
    assert runner.base_url("http://127.0.0.1:8642", allow_loopback_http=True) == "http://127.0.0.1:8642"
    with pytest.raises(ValueError):
        runner.base_url("http://hermes.invalid:8642", allow_loopback_http=True)
    with pytest.raises(ValueError):
        runner.base_url("http://127.0.0.1:8642")


def test_a_gateway_override_never_inherits_another_hosts_ca(monkeypatch):
    monkeypatch.setenv("VAN_LIVE_GATEWAY_BASE_URL", "https://other.invalid")
    url, ca = runner.gateway_default()
    assert url == "https://other.invalid"
    assert ca == ""
    monkeypatch.delenv("VAN_LIVE_GATEWAY_CA_FILE", raising=False)
    with pytest.raises(ValueError, match="CA_FILE"):
        runner.gateway_context(ca)


def test_missing_credentials_block_before_any_network_call(monkeypatch):
    for name in ("VAN_LIVE_GATEWAY_BASE_URL", "VAN_LIVE_CLIENT_CERT_FILE", "VAN_LIVE_CLIENT_KEY_FILE",
                 "VAN_INGRESS_TOKEN", "VAN_LIVE_RUNTIME_TOKEN", "VAN_OBSERVABILITY_TOKEN",
                 "VAN_HERMES_BASE_URL", "VAN_HERMES_BEARER_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(runner, "get_json", lambda *args: pytest.fail("missing credentials must not make requests"))
    receipt = runner.collect()
    assert receipt["outcome"] == "BLOCKED"
    assert len(receipt["checks"]) == 6
    assert all(check["outcome"] == "BLOCKED" for check in receipt["checks"])
    assert receipt["owner_command_executed"] is False
    assert receipt["handset_verified"] is False
    assert receipt["deployed_source_verified"] is False


def test_mocked_unit_inputs_cannot_leak_secret_response_fields_into_receipts(monkeypatch):
    for name in ("VAN_LIVE_CLIENT_CERT_FILE", "VAN_LIVE_CLIENT_KEY_FILE", "VAN_INGRESS_TOKEN",
                 "VAN_LIVE_RUNTIME_TOKEN", "VAN_OBSERVABILITY_TOKEN", "VAN_HERMES_BEARER_TOKEN"):
        monkeypatch.setenv(name, "synthetic-credential-value")
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "https://hermes.invalid")
    monkeypatch.setattr(runner, "gateway_context", lambda *args: object())
    monkeypatch.setattr(runner, "get_json", lambda *args: ({"ok": True, "secret": "response-secret-material"}, {"http_status": 200, "body_sha256": "synthetic-hash"}))
    receipt = runner.collect()
    encoded = json.dumps(receipt)
    assert "synthetic-credential-value" not in encoded
    assert "response-secret-material" not in encoded
    assert receipt["outcome"] == "FAIL"
    assert receipt["handset_verified"] is False


@pytest.mark.parametrize("name", ["gateway", "automation", "browser", "operator"])
def test_malformed_sections_fail_the_predicate(name):
    assert not runner.evaluate(name, {"hermes": [], "governance": [], "device_pki": [], "audit_chain": [], "scheduler": []}, now_ms=0, max_age_seconds=1)


def test_redirects_do_not_forward_scoped_credentials():
    assert runner.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://other.invalid") is None
