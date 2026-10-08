"""Local fixtures test source/config binding and credential boundaries, not live hosts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import ssl

import pytest
from van_gateway.mtls.pki import init_ca

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("pre_phone_acceptance", ROOT / "tools/certification/pre_phone_host_acceptance.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.fixture
def bound(tmp_path, monkeypatch):
    state = tmp_path / "state"
    config = tmp_path / "config"
    config.mkdir()
    ca = state / "mtls"
    init_ca(ca)
    input_profile = {"schema_version": 2, "profile_id": "synthetic-local-test", "backend_host": "van-trading-core",
                     "hermes_host": "van-trading-core", "ingress_host": "van-trading-core",
                     "public_gateway_url": "https://owner-ingress.example.net:8443", "ingress_bind_address": "10.0.0.122", "ingress_interface": "eth0",
                     "ingress_capability_receipt": "synthetic-test:receipt", "hermes_api_url": "http://127.0.0.1:8642",
                     "gateway_ca_file": str(ca / "ca.crt"), "hermes_runtime_token_file": "/private/acceptance/runtime.token",
                     "connectivity_signing_key_file": "/private/acceptance/connectivity.key", "connectivity_signing_kid": "test-kid",
                     "mtls_directory": str(ca), "database_file": str(state / "owner.sqlite3"),
                     "commander_api_url": "https://10.77.0.4:9133", "commander_token_file": "/private/acceptance/commander.token",
                     "commander_ca_file": "/private/acceptance/commander.ca.crt"}
    import prepare_owner_core_deployment as compiler
    artifacts = compiler.render(input_profile)
    public = tmp_path / "android.properties"
    public.write_bytes(artifacts["android-owner-core.properties"])
    (config / "owner-core.env").write_bytes(artifacts["owner-core.env"])
    (config / "google-workspace.env").write_text("VAN_GOOGLE_TOKEN_FERNET_KEY=synthetic-google-key\n")
    gateway = {"VAN_INGRESS_TOKEN": "synthetic-ingress-token-" * 2, "VAN_HERMES_BEARER_TOKEN": "synthetic-hermes-token-" * 2,
               "VAN_DEVICE_SECRET_FERNET_KEY": "synthetic-device-key", "VAN_DEVICE_ENROLMENT_TOKEN": "synthetic-enrolment-" * 3,
               "VAN_INTERNAL_CONTROL_SCOPED_TOKENS": "runtime:" + "synthetic-runtime-" * 3,
               "VAN_OBSERVABILITY_TOKEN": "synthetic-observability-" * 3,
               "VAN_OWNER_DEVICE_SIGNING_CERT_SHA256": "b" * 64, "VAN_OWNER_DEVICE_ATTESTATION_ROOTS": "c" * 64}
    (config / "gateway.env").write_text("".join(f"{key}={value}\n" for key, value in gateway.items()))
    for path in config.iterdir():
        path.chmod(0o600)
    runtime = state / "runtime"
    runtime.mkdir()
    (runtime / "source.py").write_text("# synthetic local fixture\n")
    expected = "a" * 40
    (runtime / "DEPLOYED_SHA").write_text(expected + "\n")
    metadata = {"source_clean": True, "repository_sha": expected, "expected_repository_sha": expected,
                "runtime_sha256": {"source.py": hashlib.sha256((runtime / "source.py").read_bytes()).hexdigest()},
                "configuration_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in config.iterdir()}}
    (runtime / "DEPLOYED_SOURCE.json").write_text(json.dumps(metadata))
    monkeypatch.setattr(runner.platform, "node", lambda: "van-trading-core")
    monkeypatch.setattr(runner.platform, "machine", lambda: "aarch64")
    return config, state, public, expected


def test_unbound_inputs_refuse_all_network_and_inherited_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "inherited-secret-must-not-be-used")
    monkeypatch.setattr(runner, "observe", lambda *args: pytest.fail("unbound collector made a request"))
    result = runner.collect(tmp_path / "missing-config", tmp_path, tmp_path / "missing-profile", "a" * 40)
    assert result["outcome"] == "BLOCKED"
    assert result["device_provisioning_permitted"] is False
    assert "inherited-secret" not in json.dumps(result)


def test_profile_ca_effective_settings_and_narrow_tokens_bind_without_phone_key(bound):
    values, checks, tls = runner.bindings(*bound)
    assert all(checks.values())
    assert values["runtime"].startswith("synthetic-runtime-")
    assert tls.minimum_version == tls.maximum_version == ssl.TLSVersion.TLSv1_3
    assert tls.verify_mode == ssl.CERT_REQUIRED
    assert tls.check_hostname is True


@pytest.mark.parametrize("change", ["runtime", "configuration", "unexpected-env", "wrong-sha"])
def test_changed_deployed_bytes_or_environment_block_before_network(bound, change, monkeypatch):
    config, state, public, expected = bound
    if change == "runtime":
        (state / "runtime/source.py").write_text("tampered\n")
    elif change == "configuration":
        (config / "gateway.env").write_text((config / "gateway.env").read_text() + "VAN_DIAL_DEV_ENABLED=true\n")
    elif change == "unexpected-env":
        (config / "trading-commander.env").write_text("VAN_ENV=development\n")
        (config / "trading-commander.env").chmod(0o600)
    else:
        expected = "d" * 40
    monkeypatch.setattr(runner, "observe", lambda *args: pytest.fail("changed binding made a request"))
    result = runner.collect(config, state, public, expected)
    assert result["outcome"] == "FAIL"
    assert {check["name"]: check["outcome"] for check in result["checks"]}["exact_deployed_source_and_configuration"] == "FAIL"


def test_mismatching_phone_profile_refuses_before_network(bound, monkeypatch):
    config, state, public, expected = bound
    public.write_text(public.read_text().replace("owner-ingress.example.net", "other-ingress.example.net"))
    monkeypatch.setattr(runner, "observe", lambda *args: pytest.fail("mismatched endpoint made a request"))
    assert runner.collect(config, state, public, expected)["outcome"] == "BLOCKED"


@pytest.mark.parametrize("scopes", ["runtime,device_enrolment", "runtime,observability", "runtime,automation"])
def test_acceptance_will_not_select_broad_or_enrolment_credentials(scopes):
    with pytest.raises(ValueError):
        runner.scoped_token({"VAN_INTERNAL_CONTROL_SCOPED_TOKENS": scopes + ":" + "synthetic-wide-" * 3}, runner.ControlScope.RUNTIME)


def test_credential_collapse_across_entries_is_refused():
    token = "synthetic-collapsed-" * 3
    with pytest.raises(ValueError):
        runner.scoped_token({"VAN_INTERNAL_CONTROL_SCOPED_TOKENS": f"runtime:{token};device_enrolment:{token}"}, runner.ControlScope.RUNTIME)


def test_only_get_observations_and_current_recorded_canaries_can_pass(bound, monkeypatch):
    calls = []
    ready = {"state": "READY", "configured": True, "egress_enabled": True, "contains_secrets": False,
             "evidence_pointer": "synthetic-recorded-canary", "verified_at_ms": int(runner.time.time() * 1000),
             "runtime_version": "test-1", "expected_version": "test-1"}
    def fake_observe(url, tls, headers, timeout):
        calls.append((url, tls, headers))
        status = 200
        if url.startswith("https://"):
            assert not any(name in headers for name in ("Authorization", "X-Van-Ingress-Token", "X-Van-Internal-Token"))
            status, data = 403, {"detail": "client_certificate_required"}
        elif url.endswith("/v1/runtime/status"):
            data = {"hermes_is_sole_agent_runtime": True, "signed_command_authority_required": True}
        elif url.endswith("/v1/automation/health"):
            data = {"runtime": ready, "governance": {"production_activation_permitted": True}}
        elif url.endswith("/v1/browser/health"):
            data = {"harness": ready, "stagehand": ready, "governance": {"production_activation_permitted": True}}
        elif url.endswith("/v1/observability/health"):
            data = {"audit_chain": {"ok": True}, "scheduler": {"running": True},
                    "device_pki": {"configured": True, "present": True, "days_remaining": 365}}
        else:
            data = {"ok": True, "profile": "van", "service": "van-gateway", "hermes": {"ok": True, "profile": "van"}}
        return data | {"remote_secret": "not-in-receipt"}, {"http_status": status, "body_sha256": "e" * 64}
    monkeypatch.setattr(runner, "observe", fake_observe)
    result = runner.collect(*bound)
    assert result["outcome"] == "PASS_HOST_HEALTH_ONLY"
    assert len(calls) == 8
    assert all(url.startswith(("http://127.0.0.1:8787/", "http://127.0.0.1:8642/", "https://owner-ingress.example.net:8443/")) for url, _, _ in calls)
    assert result["handset_verified"] is result["fresh_provider_execution_verified"] is result["live_e2e_qualified"] is False
    assert result["ingress_authority_verified"] is result["device_provisioning_permitted"] is False
    encoded = json.dumps(result)
    assert "synthetic-runtime-" not in encoded and "not-in-receipt" not in encoded


def test_redirect_and_server_error_never_qualify_public_ingress(bound, monkeypatch):
    monkeypatch.setattr(runner, "observe", lambda *args: ({}, {"http_status": 302, "body_sha256": "e" * 64}))
    result = runner.collect(*bound)
    assert result["outcome"] == "FAIL"
    assert runner.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://other.example.net") is None
