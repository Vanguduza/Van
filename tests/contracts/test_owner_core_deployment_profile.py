"""Exercise selected core routing, trust output and refusal without touching an estate host."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from van_gateway.mtls.pki import init_ca

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/runtime/prepare_owner_core_deployment.py"
spec = importlib.util.spec_from_file_location("core_deployment", TOOL)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
preflight_spec = importlib.util.spec_from_file_location("core_preflight", ROOT / "tools/runtime/preflight_owner_core.py")
preflight = importlib.util.module_from_spec(preflight_spec)
preflight_spec.loader.exec_module(preflight)
target_spec = importlib.util.spec_from_file_location("core_android_target_probe", ROOT / "tests/contracts/test_android_production_target.py")
target = importlib.util.module_from_spec(target_spec)
target_spec.loader.exec_module(target)
probe = target.probe
product_spec = importlib.util.spec_from_file_location("core_product_tls_fixture", ROOT / "backend/tests/test_dial_dev_product_mtls.py")
product = importlib.util.module_from_spec(product_spec)
product_spec.loader.exec_module(product)
product_tls_gateway = product.tls_gateway


@pytest.fixture
def profile(tmp_path):
    directory = tmp_path / "public-pki"
    init_ca(directory)
    return {
        "schema_version": 2, "profile_id": "synthetic-test-core",
        "backend_host": "van-trading-core", "hermes_host": "van-trading-core", "ingress_host": "van-trading-core",
        "public_gateway_url": "https://owner-ingress.example:8443/", "ingress_bind_address": "10.0.0.122", "ingress_interface": "eth0",
        "ingress_capability_receipt": "synthetic-test:typed-recipe:123",
        "hermes_api_url": "http://127.0.0.1:8642", "gateway_ca_file": str(directory / "ca.crt"),
        "hermes_runtime_token_file": "/private/hermes/van-runtime.token",
        "connectivity_signing_key_file": "/private/owner-runtime/connectivity.key",
        "connectivity_signing_kid": "test-connectivity-1", "mtls_directory": "/private/owner-runtime/mtls",
        "database_file": "/private/owner-runtime/owner.sqlite3", "commander_api_url": "https://10.0.1.233:9133",
        "commander_token_file": "/private/owner-runtime/commander.gateway.token", "commander_ca_file": "/private/owner-runtime/commander.ca.crt",
    }


def test_compilation_places_phone_gateway_and_runtime_only_on_core(profile):
    result = module.render(profile)
    assert not any(name.endswith(".cfg") for name in result)
    env = result["owner-core.env"].decode()
    assert 'VAN_MTLS_BIND="10.0.0.122"' in env and 'VAN_MTLS_INTERFACE="eth0"' in env
    assert 'VAN_LOOPBACK_HOST="127.0.0.1"' in env
    assert 'VAN_HERMES_BASE_URL="http://127.0.0.1:8642"' in env
    assert 'VAN_ALLOW_LOOPBACK_IN_PRODUCTION="false"' in env
    assert "VAN_DIAL_DEV_ENABLED" not in env
    declaration = json.loads(result["declaration.json"])
    assert declaration["status"] == "PREPARED_NOT_DEPLOYED"
    assert declaration["live_qualified"] is declaration["deployed"] is declaration["ingress_authority_verified"] is False
    assert declaration["runtime_hosts"] == ["van-trading-core"]
    assert declaration["topology"] == "CORE_ONLY_V2"
    assert len(declaration["required_network_lanes"]) == 3
    assert {lane["target_host"] for lane in declaration["required_network_lanes"]} == {"van-trading-core"}
    assert all(lane["source"] == lane["target_address"] == "127.0.0.1"
               for lane in declaration["required_network_lanes"] if lane["source"] != "owner_phone")
    ca = x509.load_pem_x509_certificate(Path(profile["gateway_ca_file"]).read_bytes())
    props = result["android-owner-core.properties"].decode()
    assert "VAN_GATEWAY_CA_SHA256=" + ca.fingerprint(hashes.SHA256()).hex() in props
    assert "VAN_GATEWAY_INGRESS_HOST=van-trading-core" in props
    assert "oracle-admin" not in "".join(content.decode() for content in result.values())
    assert "PRIVATE KEY" not in "".join(content.decode() for content in result.values())


def test_emitted_profile_passes_actual_android_release_target_validator(profile, tmp_path, probe):
    output = tmp_path / "compiled.properties"
    output.write_bytes(module.render(profile)["android-owner-core.properties"])
    result = probe(output)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "ACCEPTED"


def test_optional_operator_binding_selectors_are_literal_paths_only(profile, tmp_path, monkeypatch):
    provider = tmp_path / "operator-provider-bindings.json"
    machine_ca = tmp_path / "machine-client-ca.crt"
    provider.write_text("synthetic-private-provider-selector-body-must-not-be-copied")
    provider.chmod(0o600)
    machine_ca.write_text("synthetic-public-machine-ca-body-must-not-be-copied")
    machine_ca.chmod(0o644)
    profile.update(browser_artifact_providers_file=str(provider), mtls_machine_client_ca_file=str(machine_ca))
    # Only the existing phone CA is read by compilation. Optional operator files
    # are metadata selectors, never copied into generated APK/profile artifacts.
    original = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda path: pytest.fail("optional binding contents read")
                        if path in {provider, machine_ca} else original(path))
    result = module.render(profile)
    env_path = tmp_path / "owner-core.env"
    env_path.write_bytes(result["owner-core.env"])
    values = preflight.read_environment(env_path)
    assert values["VAN_BROWSER_ARTIFACT_PROVIDERS_FILE"] == str(provider)
    assert values["VAN_MTLS_MACHINE_CLIENT_CA_FILE"] == str(machine_ca)
    assert all(preflight.optional_operator_file_checks(values).values())
    assert "must-not-be-copied" not in "".join(value.decode() for value in result.values())
    declaration = json.loads(result["declaration.json"])
    assert declaration["artifact_sha256"]["owner-core.env"] == hashlib.sha256(result["owner-core.env"]).hexdigest()
    assert preflight.optional_operator_file_checks({}) == {}
    provider.chmod(0o644)
    assert not all(preflight.optional_operator_file_checks(values).values())


@pytest.mark.parametrize("name", ["browser_artifact_providers_file", "mtls_machine_client_ca_file"])
@pytest.mark.parametrize("path", ["relative/config.json", "$(cat /private/key)", "/private/config\nVAN_ENV=development", "/private/$TOKEN", "/private/%n/config"])
def test_optional_operator_binding_refuses_nonliteral_file_paths(profile, name, path):
    profile[name] = path
    with pytest.raises(ValueError):
        module.render(profile)


def test_optional_preflight_binding_refuses_missing_or_symlinked_file(tmp_path):
    regular = tmp_path / "binding.json"
    regular.write_text("synthetic")
    regular.chmod(0o600)
    link = tmp_path / "link.json"
    link.symlink_to(regular)
    for path in (str(tmp_path / "absent.json"), str(link), "relative.json", "/private/$TOKEN"):
        assert not all(preflight.optional_operator_file_checks({"VAN_BROWSER_ARTIFACT_PROVIDERS_FILE": path}).values())


@pytest.mark.parametrize("addition", ["preamble", "trailer", "second_certificate"])
def test_ca_refuses_extraneous_pem_content(profile, addition):
    path = Path(profile["gateway_ca_file"])
    original = path.read_bytes()
    path.write_bytes(b"arbitrary preamble\n" + original if addition == "preamble" else
                     original + b"arbitrary trailer\n" if addition == "trailer" else original + original)
    with pytest.raises(ValueError, match="public_ca_certificate_only"):
        module.render(profile)


def test_ca_refuses_explicit_non_signing_key_usage(profile):
    from cryptography.hazmat.primitives import serialization
    path = Path(profile["gateway_ca_file"])
    old = x509.load_pem_x509_certificate(path.read_bytes())
    key = serialization.load_pem_private_key(path.with_name("ca.key").read_bytes(), password=None)
    certificate = (x509.CertificateBuilder().subject_name(old.subject).issuer_name(old.issuer)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(old.not_valid_before_utc).not_valid_after(old.not_valid_after_utc)
                   .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                   .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
                   .sign(key, hashes.SHA256()))
    path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    with pytest.raises(ValueError, match="gateway_ca_certificate_signing_required"):
        module.render(profile)


def test_real_unit_order_and_effective_settings_preserve_profile_over_stale_trading(profile, tmp_path, monkeypatch):
    renderer_spec = importlib.util.spec_from_file_location("core_unit_renderer", ROOT / "tools/runtime/render_systemd_unit.py")
    renderer = importlib.util.module_from_spec(renderer_spec)
    renderer_spec.loader.exec_module(renderer)
    config = tmp_path / "config"
    config.mkdir()
    (config / "google-workspace.env").write_text("")
    (config / "gateway.env").write_text("VAN_ENV=development\n")
    (config / "trading-commander.env").write_text(
        "VAN_ENV=development\nVAN_REQUIRE_DEVICE_BINDING=false\nVAN_MTLS_ENABLED=false\n"
        "VAN_MTLS_BIND=0.0.0.0\nVAN_MTLS_PORT=9999\nVAN_HERMES_BASE_URL=http://127.0.0.1:8642\n"
        "VAN_PUBLIC_BASE_URL=http://127.0.0.1:8787\nVAN_DATABASE_PATH=/stale/runtime/owner.sqlite3\n"
        "VAN_DEVICE_ENROLMENT_TOKEN=synthetic-runtime\nVAN_INTERNAL_CONTROL_SCOPED_TOKENS=runtime:synthetic-runtime\n")
    (config / "owner-core.env").write_bytes(module.render(profile)["owner-core.env"])
    unit = renderer.render("gateway", home=tmp_path, state_root=tmp_path / "state", config_root=config)
    ordered_paths = [Path(line.split("=", 1)[1].removeprefix("-"))
                     for line in unit.splitlines() if line.startswith("EnvironmentFile=")]
    actual = {}
    for path in ordered_paths:
        if path.is_file():
            actual.update(preflight.read_environment(path))
    expected = preflight.effective_environment(config / "google-workspace.env", config / "gateway.env",
                                              config / "trading-commander.env", config / "owner-core.env")
    assert actual == expected and ordered_paths[-1].name == "owner-core.env"
    with monkeypatch.context() as patch:
        for name in tuple(os.environ):
            if name.startswith("VAN_"):
                patch.delenv(name)
        for key, value in actual.items():
            patch.setenv(key, value)
        from van_gateway.config import Settings
        settings = Settings(_env_file=None)
    assert settings.van_env == "production" and settings.require_device_binding and settings.mtls_enabled
    assert settings.mtls_bind == "10.0.0.122" and settings.mtls_port == 8443
    assert settings.hermes_base_url == profile["hermes_api_url"]
    assert settings.database_path == profile["database_file"]
    assert settings.van_public_base_url == profile["public_gateway_url"].rstrip("/")
    assert preflight.configuration_checks(actual)["core_only_profile"]
    assert not preflight.configuration_checks(actual)["enrolment_credential_separated_from_runtime"]


def test_effective_unit_files_cannot_borrow_missing_secrets_from_shell(profile, tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_HERMES_BEARER_TOKEN", "synthetic-shell-secret-must-not-qualify")
    (tmp_path / "google.env").write_text("")
    (tmp_path / "gateway.env").write_text("")
    (tmp_path / "core.env").write_bytes(module.render(profile)["owner-core.env"])
    actual = preflight.effective_environment(tmp_path / "google.env", tmp_path / "gateway.env", profile=tmp_path / "core.env")
    assert "VAN_HERMES_BEARER_TOKEN" not in actual
    assert not preflight.configuration_checks(actual)["separate_service_credentials_present"]


@pytest.mark.parametrize("bound", [False, True])
def test_profile_preserves_explicit_product_mtls_binding_and_unbound_disabled_default(profile, tmp_path, monkeypatch, product_tls_gateway, bound):
    from van_gateway.config import Settings
    from van_gateway.dial_dev.config import DialDevConfig
    product_config, *_ = product_tls_gateway
    (tmp_path / "google.env").write_text("")
    fields = {} if not bound else {
        "VAN_DIAL_DEV_ENABLED": "true", "VAN_DIAL_DEV_BASE_URL": "https://10.77.0.2:8443",
        "VAN_DIAL_DEV_TOKEN_FILE": product_config.token_file,
        "VAN_DIAL_DEV_TLS_CA_FILE": product_config.tls_ca_file,
        "VAN_DIAL_DEV_TLS_CLIENT_CERT_FILE": product_config.tls_client_cert_file,
        "VAN_DIAL_DEV_TLS_CLIENT_KEY_FILE": product_config.tls_client_key_file,
    }
    (tmp_path / "gateway.env").write_text("".join(f'{key}="{value}"\n' for key, value in fields.items()))
    (tmp_path / "core.env").write_bytes(module.render(profile)["owner-core.env"])
    actual = preflight.effective_environment(tmp_path / "google.env", tmp_path / "gateway.env", profile=tmp_path / "core.env")
    with monkeypatch.context() as patch:
        for key in tuple(os.environ):
            if key.startswith("VAN_"):
                patch.delenv(key)
        for key, value in actual.items():
            patch.setenv(key, value)
        settings = Settings(_env_file=None)
    config = DialDevConfig.from_settings(settings)
    assert settings.dial_dev_enabled is bound and config.configured is bound
    if bound:
        assert config.production and config.product_gateway_route and config.tls_configured
        assert config.tls_client_key_file == product_config.tls_client_key_file


@pytest.mark.parametrize("token", ["synthetic-runtime", "synthetic-enrolment", "synthetic-hermes", "synthetic-ingress"])
def test_gateway_commander_credential_cannot_reuse_another_purpose_token(token):
    effective = {"VAN_INTERNAL_CONTROL_SCOPED_TOKENS": "runtime,google:synthetic-runtime; browser:other-runtime",
                 "VAN_DEVICE_ENROLMENT_TOKEN": "synthetic-enrolment", "VAN_HERMES_BEARER_TOKEN": "synthetic-hermes",
                 "VAN_INGRESS_TOKEN": "synthetic-ingress"}
    assert not preflight.commander_credential_separate(effective, token)
    assert preflight.commander_credential_separate(effective, "synthetic-gateway-commander-only")


@pytest.mark.parametrize("fault", [None, "shared", "wrong_hash", "broad", "stream_proxy", "wrong_cn"])
def test_browser_deployment_admits_only_separate_narrow_native_control_identity(fault):
    control_token, stream_token = "synthetic-control-only-" + "c" * 32, "synthetic-stream-only-" + "s" * 32
    control = hashlib.sha256(control_token.encode()).hexdigest()
    stream = hashlib.sha256(stream_token.encode()).hexdigest()
    values = {
        "VAN_BROWSER_CONTROL_CLIENT_ADDRESS": "10.77.0.1",
        "VAN_BROWSER_CONTROL_BROKER_TOKEN_SHA256": control,
        "VAN_BROWSER_STREAM_BROKER_TOKEN_SHA256": stream,
        "VAN_BROWSER_CONTROL_PROXY_PRINCIPAL_SHA256": control,
        "VAN_BROWSER_CONTROL_PROXY_BINDINGS": json.dumps({control: ["van-trading-core"]}),
        "VAN_INTERNAL_CONTROL_SCOPED_TOKENS": f"browser_stream_producer:{control_token};browser_stream_producer:{stream_token}",
    }
    if fault == "shared":
        values["VAN_BROWSER_STREAM_BROKER_TOKEN_SHA256"] = control
    elif fault == "wrong_hash":
        values["VAN_BROWSER_CONTROL_BROKER_TOKEN_SHA256"] = "a" * 64
    elif fault == "broad":
        values["VAN_INTERNAL_CONTROL_SCOPED_TOKENS"] += f";device_enrolment:{stream_token}"
    elif fault == "stream_proxy":
        values["VAN_BROWSER_CONTROL_PROXY_BINDINGS"] = json.dumps({control: ["van-trading-core"], stream: ["van-trading-core"]})
    elif fault == "wrong_cn":
        values["VAN_BROWSER_CONTROL_PROXY_BINDINGS"] = json.dumps({control: ["foreign-client"]})
    checks = preflight.browser_credential_checks(values)
    assert all(checks.values()) is (fault is None)


@pytest.mark.parametrize("name,value", [
    ("backend_host", "dial-control"), ("hermes_host", "dial-control"), ("ingress_host", "oracle-admin"), ("ingress_host", "dial-control"),
    ("public_gateway_url", "https://62.83.35.103:8443"), ("public_gateway_url", "https://10.77.0.4:8443"),
    ("public_gateway_url", "http://owner.example:8443"), ("public_gateway_url", "https://owner.example:443"),
    ("public_gateway_url", "https://token@owner.example:8443"), ("public_gateway_url", "https://owner.example:8443?"),
    ("public_gateway_url", "https://@owner.example:8443"), ("public_gateway_url", "HTTPS://owner.example:8443"),
    ("public_gateway_url", "https://owner.example:8443/path"), ("public_gateway_url", "https://999.999.999.999:8443"),
    ("ingress_bind_address", "0.0.0.0"), ("ingress_bind_address", "10.77.0.2"),
    ("ingress_capability_receipt", None), ("ingress_capability_receipt", "receipt\nOTHER=value"),
    ("hermes_api_url", "http://10.77.0.1:8642"), ("ingress_interface", "lo"), ("ingress_interface", "eth0;bad"), ("hermes_api_url", "https://10.77.0.2:8443"),
    ("hermes_api_url", "http://@10.77.0.1:8642"), ("hermes_api_url", "HTTP://10.77.0.1:8642"),
    ("hermes_api_url", "http://10.77.0.1:8642/p/other"), ("schema_version", True),
    ("connectivity_signing_key_file", "$(cat /secret)"),
    ("database_file", "/private/owner-runtime/runtime/backend/data/owner.sqlite3"),
    ("database_file", "/outside-state/owner.sqlite3"),
    ("commander_api_url", "http://10.0.1.233:9133"),
    ("commander_api_url", "https://10.77.0.1:9133"),
    ("commander_api_url", "https://@10.0.1.233:9133"), ("commander_api_url", "HTTPS://10.0.1.233:9133"),
])
def test_wrong_roles_unbound_capability_and_unsafe_routes_refused(profile, name, value):
    profile[name] = value
    with pytest.raises(ValueError):
        module.render(profile)


def test_unbound_example_cannot_emit_android_or_ingress_configuration(tmp_path):
    result = subprocess.run([sys.executable, str(TOOL), "--profile",
                             str(ROOT / "deploy/van-owner-core/profile.example.json"), "--output", str(tmp_path / "out")],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "BLOCKED"
    assert not (tmp_path / "out").exists()


def test_failed_profile_does_not_print_credential_or_replace_prior_output(tmp_path, profile):
    profile["public_gateway_url"] = "https://synthetic-secret-never-print@owner.example:8443"
    source = tmp_path / "input.json"
    source.write_text(json.dumps(profile))
    out = tmp_path / "out"
    out.mkdir()
    (out / "android-owner-core.properties").write_text("old-reviewed-config")
    result = subprocess.run([sys.executable, str(TOOL), "--profile", str(source), "--output", str(out)],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert "synthetic-secret-never-print" not in result.stdout + result.stderr
    assert (out / "android-owner-core.properties").read_text() == "old-reviewed-config"


def test_production_inherited_from_settings_environment_also_requires_immutable_source(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "gateway.env").write_text("")
    (config / "google-workspace.env").write_text("")
    env = {**os.environ, "HOME": str(tmp_path), "VAN_CONFIG_ROOT": str(config),
           "VAN_STATE_ROOT": str(tmp_path / "state"), "VAN_ENV": "production"}
    env.pop("VAN_EXPECTED_REPOSITORY_SHA", None)
    env.pop("VAN_INSTALL_STAGE_ONLY", None)
    result = subprocess.run(["bash", str(ROOT / "tools/runtime/install_van_gateway_service.sh")],
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert "immutable_expected_repository_sha_required" in result.stderr
    assert not (tmp_path / "state").exists()


def test_private_ca_material_is_not_accepted_as_public_trust_input(profile):
    profile["gateway_ca_file"] = str(Path(profile["gateway_ca_file"]).with_name("ca.key"))
    with pytest.raises(ValueError, match="public_ca_certificate_only"):
        module.render(profile)


def test_host_preflight_preserves_trading_headroom_and_rejects_shared_enrolment(profile):
    rendered = module.render(profile)["owner-core.env"].decode()
    values = {key: value.strip('"') for key, value in (line.split("=", 1) for line in rendered.splitlines())}
    secrets = {"VAN_DEVICE_SECRET_FERNET_KEY": "synthetic", "VAN_GOOGLE_TOKEN_FERNET_KEY": "synthetic",
               "VAN_HERMES_BEARER_TOKEN": "synthetic-hermes", "VAN_INTERNAL_CONTROL_SCOPED_TOKENS": "runtime,google:synthetic-runtime",
               "VAN_DEVICE_ENROLMENT_TOKEN": "synthetic-separate-enrolment", "VAN_INGRESS_TOKEN": "synthetic-ingress-" + "a" * 32,
               "VAN_OWNER_DEVICE_SIGNING_CERT_SHA256": "b" * 64, "VAN_OWNER_DEVICE_ATTESTATION_ROOTS": "c" * 64}
    assert all(preflight.configuration_checks({**secrets, **values}).values())
    secrets["VAN_DEVICE_ENROLMENT_TOKEN"] = "synthetic-runtime"
    assert not preflight.configuration_checks({**secrets, **values})["enrolment_credential_separated_from_runtime"]
    secrets["VAN_INTERNAL_CONTROL_TOKEN"] = "synthetic-legacy"
    assert not preflight.configuration_checks({**secrets, **values})["legacy_all_scope_control_disabled"]
    assert not preflight.memory_headroom_ok("MemAvailable: 5242879 kB\n")
    assert preflight.memory_headroom_ok("MemAvailable: 5242880 kB\n")
    assert not preflight.memory_headroom_ok("MemFree: 16777216 kB\n")


def test_hermes_core_registration_uses_scoped_file_without_gateway_secret_environment(tmp_path):
    import yaml
    home = tmp_path / "hermes"
    target = home / "profiles/van/mcp/owner_runtime_stdio.mjs"
    target.parent.mkdir(parents=True)
    target.write_text((ROOT / "hermes/mcp/owner_runtime_stdio.mjs").read_text())
    config = home / "config.yaml"
    config.write_text("mcp_servers:\n  existing:\n    command: preserve-this-sibling\n")
    token = tmp_path / "runtime.token"
    token.write_text("synthetic-never-copy-token-value")
    token.chmod(0o600)
    result = subprocess.run(["bash", str(ROOT / "tools/hermes/register_owner_runtime_mcp.sh")],
                            env={**os.environ, "HERMES_HOME": str(home), "VAN_OWNER_RUNTIME_HOST": "van-trading-core",
                                 "VAN_OWNER_RUNTIME_URL": "http://127.0.0.1:8787", "VAN_OWNER_RUNTIME_TOKEN_FILE": str(token),
                                 "VAN_GATEWAY_ENV_FILE": str(tmp_path / "unavailable.env")},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    servers = yaml.safe_load(config.read_text())["mcp_servers"]
    assert servers["existing"]["command"] == "preserve-this-sibling"
    assert servers["van_owner_runtime"]["env"] == {"VAN_OWNER_RUNTIME_URL": "http://127.0.0.1:8787",
                                                     "VAN_OWNER_RUNTIME_TOKEN_FILE": str(token)}
    assert token.read_text() not in config.read_text() + result.stdout + result.stderr


def test_explicit_unavailable_scoped_token_never_falls_back_to_ambient_legacy(tmp_path):
    result = subprocess.run(["node", str(ROOT / "hermes/mcp/owner_runtime_stdio.mjs")],
                            env={**os.environ, "VAN_OWNER_RUNTIME_TOKEN_FILE": str(tmp_path / "missing.token"),
                                 "VAN_INTERNAL_CONTROL_TOKEN": "synthetic-all-scope-never-use"},
                            input="", capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert "synthetic-all-scope-never-use" not in result.stdout + result.stderr


def test_hermes_scoped_transport_refuses_real_cross_host_redirect(tmp_path):
    import http.server
    import threading
    received = []
    class Destination(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(("destination", self.headers.get("x-van-internal-token")))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        def log_message(self, *args):
            pass
    destination = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Destination)
    class Source(Destination):
        def do_GET(self):
            received.append(("source", self.headers.get("x-van-internal-token")))
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{destination.server_port}/credential-leak")
            self.end_headers()
    source = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Source)
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (source, destination)]
    for thread in threads:
        thread.start()
    token = tmp_path / "scoped.token"
    token.write_text("synthetic-scoped-token")
    token.chmod(0o600)
    try:
        result = subprocess.run(["node", str(ROOT / "hermes/mcp/owner_runtime_stdio.mjs")],
                                env={**os.environ, "VAN_OWNER_RUNTIME_URL": f"http://127.0.0.1:{source.server_port}",
                                     "VAN_OWNER_RUNTIME_TOKEN_FILE": str(token), "VAN_INTERNAL_CONTROL_TOKEN": "synthetic-ambient-all-scope"},
                                input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "runtime_status", "arguments": {}}}) + "\n",
                                capture_output=True, text=True, timeout=10)
    finally:
        for server in (source, destination):
            server.shutdown()
        for thread in threads:
            thread.join()
    assert result.returncode == 0
    assert json.loads(result.stdout)["result"]["isError"] is True
    assert received == [("source", "synthetic-scoped-token")]
    assert "synthetic-scoped-token" not in result.stdout + result.stderr
    assert "synthetic-ambient-all-scope" not in result.stdout + result.stderr


def test_qualification_treats_environment_as_data_and_refuses_credential_redirect(tmp_path):
    import http.server
    import threading
    arrivals = []
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            arrivals.append((self.path, self.headers.get("X-Van-Ingress-Token")))
            self.send_response(302)
            self.send_header("Location", "/credential-leak-destination")
            self.end_headers()
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = tmp_path / "config"
    config.mkdir()
    marker = tmp_path / "must-not-be-created"
    (config / "gateway.env").write_text(
        "VAN_ENV=production\nVAN_REQUIRE_DEVICE_BINDING=true\n"
        "VAN_INGRESS_TOKEN=synthetic-not-a-production-token-1234\n"
        f"VAN_UNUSED=$(touch {marker})\n")
    try:
        result = subprocess.run(["bash", str(ROOT / "tools/runtime/qualify_gateway_host.sh")],
                                env={**os.environ, "VAN_CONFIG_ROOT": str(config), "VAN_STATE_ROOT": str(tmp_path / "state"),
                                     "VAN_GATEWAY_HEALTH_URL": f"http://127.0.0.1:{server.server_port}/health"},
                                capture_output=True, text=True, timeout=30)
    finally:
        server.shutdown()
        thread.join()
    assert result.returncode == 1 and "RED" in result.stdout
    assert not marker.exists()
    assert [path for path, token in arrivals] == ["/health"]
    assert "synthetic-not-a-production-token-1234" not in result.stdout + result.stderr
