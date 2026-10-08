"""Production browser profiles must isolate both authority and host resources."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import types

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from van_gateway.mtls.pki import init_ca, DeviceCA

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "deploy/van-browser-stream"
sys.path.insert(0, str(PACKAGE))
import prepare_profiles as profiles
import install_profiles as installer


@pytest.fixture
def profile():
    data = {"schema_version": 1, "profile_id": "synthetic-isolated-browser", "encrypted_profile_device": "/dev/synthetic-encrypted-device",
            "chromium_executable": "/usr/bin/true", "chromium_sha256": "a" * 64,
            "nginx_executable": "/usr/bin/true", "nginx_sha256": "b" * 64,
            "signed_signal_base_url": "https://browser.example:9445/rtc", "ingress_bind": "10.0.1.241", "ingress_port": 9445,
            "ingress_tls_cert_file": "/synthetic/ingress/media.crt", "ingress_tls_key_file": "/synthetic/ingress/media.key",
            "broker_origin": "https://10.77.0.4:8443", "profiles": {}}
    names = ("grant_public_key_file", "control_ca_file", "control_server_cert_file", "control_server_key_file",
             "stream_tls_cert_file", "stream_tls_key_file", "broker_ca_file", "control_broker_token_file", "stream_broker_token_file",
             "control_broker_client_cert_file", "control_broker_client_key_file", "stream_broker_client_cert_file", "stream_broker_client_key_file")
    for index, (instance, alias) in enumerate(profiles.ALIASES.items()):
        values = {key: "/synthetic/" + instance + "/" + key for key in names}
        values.update({"profile_alias": alias, "cdp_port": 9222 + index, "control_bind": "10.0.1.240", "control_port": 9443 + index,
                       "stream_bind": "10.0.1.241", "stream_port": 8443 + index, "grant_kid": "synthetic-grant-key",
                       "public_signal_url": "https://browser.example:9445/rtc/" + instance,
                       "stream_tls_ca_file": "/synthetic/" + instance + "/stream-ca.crt", "stream_tls_server_name": instance + ".browser.example",
                       "control_broker_token_sha256": str(index * 2 + 1) * 64, "stream_broker_token_sha256": str(index * 2 + 2) * 64,
                       "core_client": {"address": "10.0.1.240", "port": 9443 + index, "server_name": "10.0.1.240",
                           "ca_file": "/synthetic/core/" + instance + "/ca.crt", "cert_file": "/synthetic/core/" + instance + "/client.crt",
                           "key_file": "/synthetic/core/" + instance + "/client.key", "caller_common_name": "van-trading-core"}})
        data["profiles"][instance] = values
    return data


def environment(raw):
    # This reads systemd's generated quoted configuration via shell-free data
    # parsing for test assertions; core fragment intentionally uses plain JSON.
    result = {}
    for line in raw.decode().splitlines():
        name, value = line.split("=", 1)
        result[name] = json.loads(value) if value.startswith('"') else value
    return result


def test_profiles_have_distinct_runtime_identity_storage_routes_and_authority(profile):
    artifacts = profiles.render(profile)
    declaration = json.loads(artifacts["declaration.json"])
    assert declaration["installed"] is declaration["live_qualified"] is False
    assert len({user for i in declaration["instances"] for user in i["users"]}) == 6
    assert len({i["transfer_group"] for i in declaration["instances"]}) == 2
    for instance, alias in profiles.ALIASES.items():
        stream = environment(artifacts[instance + "/stream.env"])
        control = environment(artifacts[instance + "/control.env"])
        chromium = environment(artifacts[instance + "/chromium.env"])
        assert stream["VAN_BROWSER_SIGNAL_PATH"] == "/rtc/" + instance
        assert stream["VAN_BROWSER_PROFILE_ALIAS"] == control["VAN_BROWSER_PROFILE_ALIAS"] == alias
        assert chromium["VAN_BROWSER_PROFILE_MOUNT"] == profiles.PROFILE_ROOT + "/" + instance
        assert stream["VAN_BROWSER_QUARANTINE_ROOT"] == profiles.TRANSFER_ROOT + "/" + instance
        assert stream["VAN_BROWSER_BROKER_CLIENT_KEY"] != control["VAN_BROWSER_BROKER_CLIENT_KEY"]
        assert stream["VAN_BROWSER_STREAM_BROKER_TOKEN_SHA256"] != control["VAN_BROWSER_CONTROL_BROKER_TOKEN_SHA256"]
    core = environment(artifacts["gateway-browser-profile-bindings.env"])
    clients = json.loads(core["VAN_BROWSER_CONTROL_PROFILE_CLIENTS"])
    proxy = json.loads(core["VAN_BROWSER_CONTROL_PROXY_BINDINGS"])
    assert set(clients) == set(profiles.ALIASES.values())
    assert set(proxy) == {client["proxy_principal_sha256"] for client in clients.values()}
    assert not set(proxy).intersection(client["stream_principal_sha256"] for client in clients.values())
    assert all(value == ["van-trading-core"] for value in proxy.values())


@pytest.mark.parametrize("defect", ["missing_profile", "alias", "shared_port", "public_control", "wildcard_stream", "shared_token_path",
                                   "shared_token_hash", "shared_tls_key", "shared_tls_certificate", "wrong_core_port", "relative_path",
                                   "path_injection", "broker_public_ip", "ice", "clipboard", "viewport"])
def test_invalid_or_conflated_profile_bindings_refuse_before_output(profile, defect):
    public, owner = profile["profiles"].values()
    if defect == "missing_profile":
        del profile["profiles"]["owner"]
    elif defect == "alias":
        owner["profile_alias"] = "public_research"
    elif defect == "shared_port":
        owner["cdp_port"] = public["cdp_port"]
    elif defect == "public_control":
        owner["control_bind"] = "8.8.8.8"
    elif defect == "wildcard_stream":
        owner["stream_bind"] = "0.0.0.0"
    elif defect == "shared_token_path":
        owner["stream_broker_token_file"] = public["control_broker_token_file"]
    elif defect == "shared_token_hash":
        owner["stream_broker_token_sha256"] = public["control_broker_token_sha256"]
    elif defect == "shared_tls_key":
        owner["stream_broker_client_key_file"] = public["control_broker_client_key_file"]
    elif defect == "shared_tls_certificate":
        owner["stream_broker_client_cert_file"] = public["control_broker_client_cert_file"]
    elif defect == "wrong_core_port":
        owner["core_client"]["port"] = public["control_port"]
    elif defect == "relative_path":
        owner["control_server_key_file"] = "relative/key"
    elif defect == "path_injection":
        profile["chromium_executable"] = "/usr/bin/chromium\nUser=root"
    elif defect == "broker_public_ip":
        profile["broker_origin"] = "https://8.8.8.8:8443"
    elif defect == "ice":
        owner["ice_servers"] = [{"urls": ["http://unsafe.example"]}]
    elif defect == "clipboard":
        owner["clipboard_enabled"] = "false"
    else:
        owner["width"] = True
    with pytest.raises(ValueError):
        profiles.render(profile)


def test_preparation_example_is_deliberately_unbound_and_writes_nothing(tmp_path):
    output = tmp_path / "must-not-exist"
    result = subprocess.run([sys.executable, str(PACKAGE / "prepare_profiles.py"), "--profile", str(PACKAGE / "profiles.example.json"),
                             "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 2 and json.loads(result.stdout)["status"] == "BLOCKED"
    assert not output.exists()


def test_installer_dry_run_is_side_effect_free_and_does_not_read_credentials(profile, tmp_path):
    selected = tmp_path / "profile.json"
    selected.write_text(json.dumps(profile))
    result = subprocess.run([sys.executable, str(PACKAGE / "install_profiles.py"), "--profile", str(selected), "--dry-run"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["mutation_started"] is receipt["services_started"] is receipt["live_qualified"] is False
    assert receipt["status"] == "PREPARED_NOT_INSTALLED"
    assert list(tmp_path.iterdir()) == [selected]


def test_cdp_firewall_allows_only_matching_profile_uids_without_flushing_foreign_tables(profile, monkeypatch):
    declaration = json.loads(profiles.render(profile)["declaration.json"])
    identities = {user: 1000 + n for n, user in enumerate(user for entry in declaration["instances"] for user in entry["users"])}
    monkeypatch.setattr(installer.pwd, "getpwnam", lambda user: types.SimpleNamespace(pw_uid=identities[user]))
    rules = installer.firewall(declaration).decode()
    for entry in declaration["instances"]:
        port = str(entry["cdp_port"])
        allow = next(line for line in rules.splitlines() if "tcp dport " + port in line and "accept" in line)
        assert all(str(identities[user]) in allow for user in entry["users"])
        assert all(str(uid) not in allow for user, uid in identities.items() if user not in entry["users"])
        assert "tcp dport " + port + " reject with tcp reset" in rules
    assert "flush table inet van_browser_cdp" in rules and "flush ruleset" not in rules


def test_systemd_instances_use_literal_confined_paths_and_matching_dependencies(profile):
    artifacts = profiles.render(profile)
    for kind in ("chromium", "control-agent", "stream"):
        unit = artifacts["systemd/van-browser-" + kind + "@.service"].decode()
        assert "User=van-" in unit and "%i" in unit
        assert "ProtectProc=invisible" in unit and "ProtectSystem=strict" in unit
        assert "EnvironmentFile=/etc/van-browser-stream/profiles/%i/" in unit
        assert all("${" not in line for line in unit.splitlines() if line.startswith(("ReadWritePaths=", "InaccessiblePaths=")))
    chromium = artifacts["systemd/van-browser-chromium@.service"].decode()
    assert "--remote-debugging-address=127.0.0.1" in chromium
    assert "van-browser-cdp-isolation.service" in chromium
    assert "RequiresMountsFor=/var/lib/van-browser-profiles" in chromium
    assert "van-browser-profiles.mount" not in chromium
    assert "ReadWritePaths=/var/lib/van-browser-profiles/%i /var/lib/van-browser-transfers/%i" in chromium
    assert "BindsTo=van-browser-chromium@%i.service" in artifacts["systemd/van-browser-control-agent@.service"].decode()


def test_core_fragment_uses_gateway_data_reader_without_shell_evaluation(profile, tmp_path):
    sys.path.insert(0, str(ROOT / "tools/runtime"))
    from preflight_owner_core import read_environment
    artifact = profiles.render(profile)["gateway-browser-profile-bindings.env"]
    path = tmp_path / "browser.env"
    path.write_bytes(artifact)
    values = read_environment(path)
    assert set(json.loads(values["VAN_BROWSER_CONTROL_PROFILE_CLIENTS"])) == set(profiles.ALIASES.values())


def test_fixed_media_ingress_preserves_signed_origin_and_verifies_both_native_tls_peers(profile):
    artifacts = profiles.render(profile)
    ingress = artifacts["media-ingress.conf"].decode()
    assert "listen 10.0.1.241:9445 ssl;" in ingress and "ssl_protocols TLSv1.3;" in ingress
    assert "location / { return 404; }" in ingress
    assert ingress.count("proxy_ssl_verify on;") == 10
    assert "proxy_ssl_name public.browser.example;" in ingress and "proxy_ssl_name owner.browser.example;" in ingress
    assert "location = /rtc/public" in ingress and "location = /rtc/owner" in ingress
    assert "/files/download/" in ingress and "/files/upload/" in ingress and "/clipboard/copy" in ingress
    assert "X-Van-Authenticated" not in ingress and "proxy_request_buffering off;" in ingress
    # Even unused compiled-in modules initialize their temporary paths during
    # nginx -t/start; none may fall back to a host's unencrypted /var/lib/nginx.
    for module, directory in (("client_body", "client"), ("proxy", "proxy"),
                              ("fastcgi", "fastcgi"), ("uwsgi", "uwsgi"), ("scgi", "scgi")):
        assert module + "_temp_path /var/lib/van-browser-transfers/.ingress/" + directory + ";" in ingress
    core = environment(artifacts["gateway-browser-profile-bindings.env"])
    urls = json.loads(core["VAN_BROWSER_STREAM_PROFILE_SIGNAL_URLS"])
    assert urls == {alias: core["VAN_BROWSER_STREAM_SIGNAL_URL"] + "/" + instance for instance, alias in profiles.ALIASES.items()}


@pytest.mark.parametrize("defect", ["cross_origin", "wrong_path", "ingress_port", "shared_ingress_key"])
def test_media_ingress_refuses_unbound_origin_or_shared_private_key(profile, defect):
    entry = profile["profiles"]["owner"]
    if defect == "cross_origin":
        entry["public_signal_url"] = "https://another.example:9445/rtc/owner"
    elif defect == "wrong_path":
        entry["public_signal_url"] = "https://browser.example:9445/browser/owner"
    elif defect == "ingress_port":
        profile["ingress_port"] = entry["stream_port"]
    else:
        entry["stream_broker_client_key_file"] = profile["ingress_tls_key_file"]
    with pytest.raises(ValueError):
        profiles.render(profile)


def credentials(profile, tmp_path):
    directory = tmp_path / "pki"
    init_ca(directory)
    ca = DeviceCA(directory)
    ca.issue_server("DNS:browser.example")
    profile["ingress_tls_cert_file"] = str(directory / "server.crt")
    profile["ingress_tls_key_file"] = str(directory / "server.key")
    for instance, entry in profile["profiles"].items():
        for role in ("control", "stream"):
            client_key = ec.generate_private_key(ec.SECP256R1())
            identity = "synthetic-" + instance + "-" + role
            csr = x509.CertificateSigningRequestBuilder().subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, identity)])).sign(client_key, hashes.SHA256())
            issued = ca.issue_client(csr.public_bytes(serialization.Encoding.PEM).decode(), identity)
            cert = tmp_path / (instance + "-" + role + ".crt")
            key = tmp_path / (instance + "-" + role + ".key")
            cert.write_text(issued.certificate_pem)
            key.write_bytes(client_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            key.chmod(0o600)
            token = tmp_path / (instance + "-" + role + ".token")
            value = ("synthetic-" + instance + "-" + role + "-credential-").encode() + b"a" * 32
            token.write_bytes(value + b"\n")
            token.chmod(0o600)
            entry[role + "_broker_token_file"] = str(token)
            entry[role + "_broker_token_sha256"] = hashlib.sha256(value).hexdigest()
            entry[role + "_broker_client_cert_file"] = str(cert)
            entry[role + "_broker_client_key_file"] = str(key)
            for kind in (("control_server_cert_file", "control_server_key_file") if role == "control" else ("stream_tls_cert_file", "stream_tls_key_file")):
                other = tmp_path / (instance + "-" + kind)
                other.write_bytes(cert.read_bytes() if kind.endswith("cert_file") else key.read_bytes())
                other.chmod(0o600)
                entry[kind] = str(other)
        for kind in ("grant_public_key_file", "control_ca_file", "broker_ca_file"):
            entry[kind] = str(directory / "ca.crt")
    return json.loads(profiles.render(profile)["declaration.json"])


def test_installer_checks_actual_private_token_bytes_and_distinct_broker_tls_identities(profile, tmp_path):
    declaration = credentials(profile, tmp_path)
    installer.check_credentials(declaration)
    selector = declaration["instances"][0]["copy_selectors"]["control-pki/producer.token"]
    Path(selector).write_text("changed-secret-never-print")
    with pytest.raises(ValueError, match="fingerprint_mismatch"):
        installer.check_credentials(declaration)


def test_installer_refuses_duplicate_broker_certificate_even_at_distinct_paths(profile, tmp_path):
    declaration = credentials(profile, tmp_path)
    first, second = declaration["instances"]
    copies, others = first["copy_selectors"], second["copy_selectors"]
    for suffix in ("crt", "key"):
        Path(others["control-pki/broker-client." + suffix]).write_bytes(Path(copies["control-pki/broker-client." + suffix]).read_bytes())
    with pytest.raises(ValueError, match="distinct_matching_role_broker_tls_identity"):
        installer.check_credentials(declaration)

