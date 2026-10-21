#!/usr/bin/env python3
"""Prepare isolated browser stacks from explicit settings; never start services."""
from __future__ import annotations
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

PACKAGE = Path(__file__).resolve().parent
ALIASES = {"public": "public_research", "owner": "authenticated_owner"}
ETC = "/etc/van-browser-stream/profiles"
PROFILE_ROOT = "/var/lib/van-browser-profiles"
TRANSFER_ROOT = "/var/lib/van-browser-transfers"


def text_value(data, name):
    value = data.get(name)
    if not isinstance(value, str) or not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("unbound_profile_setting:" + name)
    return value


def path_value(data, name):
    value = text_value(data, name)
    if not value.startswith("/") or ".." in Path(value).parts or any(c in value for c in "\\\"'%$*?[]"):
        raise ValueError("literal_absolute_path_required:" + name)
    return value


def sha_value(data, name):
    value = text_value(data, name)
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("invalid_identity_fingerprint:" + name)
    return value


def address_value(data, name, *, private=False):
    value = text_value(data, name)
    address = ipaddress.ip_address(value)
    if (address.version != 4 or address.is_unspecified or address.is_loopback or address.is_multicast
            or private and not address.is_private):
        raise ValueError("explicit_listener_address_required:" + name)
    return value


def env(values):
    return "".join(key + '="' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"\n'
                   for key, value in values.items()).encode()


def render(data):
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("profile_schema_version_required")
    profile_id = text_value(data, "profile_id")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", profile_id):
        raise ValueError("profile_id_invalid")
    device = path_value(data, "encrypted_profile_device")
    chromium = path_value(data, "chromium_executable")
    chromium_sha = sha_value(data, "chromium_sha256")
    nginx = path_value(data, "nginx_executable")
    nginx_sha = sha_value(data, "nginx_sha256")
    ingress_bind = address_value(data, "ingress_bind")
    ingress_port = data.get("ingress_port")
    if type(ingress_port) is not int or not 1024 <= ingress_port <= 65535:
        raise ValueError("explicit_unprivileged_media_ingress_port_required")
    signal_base = text_value(data, "signed_signal_base_url")
    signal = urlsplit(signal_base)
    if (signal.scheme != "https" or not signal.hostname or signal.username or signal.password or signal.query or signal.fragment
            or signal.path != "/rtc" or signal.port != ingress_port or signal.netloc.endswith(":")):
        raise ValueError("same_origin_signed_rtc_base_required")
    try:
        phone_address = ipaddress.ip_address(signal.hostname)
    except ValueError:
        if ("." not in signal.hostname or signal.hostname.endswith((".local", ".localhost", ".internal", ".invalid", ".test"))
                or not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", signal.hostname)):
            raise ValueError("public_phone_signal_origin_required")
    else:
        if not phone_address.is_global:
            raise ValueError("public_phone_signal_origin_required")
    ingress_cert = path_value(data, "ingress_tls_cert_file")
    ingress_key = path_value(data, "ingress_tls_key_file")
    origin = text_value(data, "broker_origin")
    broker = urlsplit(origin)
    if (broker.scheme != "https" or not broker.hostname or broker.username or broker.password
            or broker.query or broker.fragment or broker.path not in {"", "/"} or broker.netloc.endswith(":")):
        raise ValueError("private_https_broker_origin_required")
    try:
        broker_ip = ipaddress.ip_address(broker.hostname)
    except ValueError:
        if re.fullmatch(r"[0-9.]+", broker.hostname):
            raise ValueError("private_https_broker_origin_required")
    else:
        if not broker_ip.is_private or broker_ip.is_unspecified or broker_ip.is_loopback or broker_ip.is_multicast:
            raise ValueError("private_https_broker_origin_required")
    profiles = data.get("profiles")
    if not isinstance(profiles, dict) or set(profiles) != set(ALIASES):
        raise ValueError("exact_public_and_owner_profiles_required")
    artifacts, plan, ports, fingerprints, secret_paths, broker_cert_paths = {}, [], {ingress_port}, set(), {ingress_key}, set()
    proxy_bindings, core_clients, caller_names = {}, {}, set()
    signal_urls, upstreams, locations = {}, [], []
    for index, (instance, alias) in enumerate(ALIASES.items()):
        entry = profiles[instance]
        if not isinstance(entry, dict) or entry.get("profile_alias") != alias:
            raise ValueError("fixed_profile_alias_required")
        for name in ("cdp_port", "control_port", "stream_port", "egress_port"):
            port = entry.get(name, 8899 + index if name == "egress_port" else None)
            if type(port) is not int or not 1024 <= port <= 65535 or port in ports:
                raise ValueError("distinct_unprivileged_profile_ports_required")
            ports.add(port)
        egress_port = entry.get("egress_port", 8899 + index)
        control_bind = address_value(entry, "control_bind", private=True)
        stream_bind = address_value(entry, "stream_bind")
        public_signal = text_value(entry, "public_signal_url")
        if public_signal != signal_base + "/" + instance:
            raise ValueError("profile_signal_route_must_match_signed_origin_and_prefix")
        signal_urls[alias] = public_signal
        stream_ca = path_value(entry, "stream_tls_ca_file")
        stream_name = text_value(entry, "stream_tls_server_name")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,253}", stream_name):
            raise ValueError("literal_native_stream_tls_server_name_required")
        paths = {name: path_value(entry, name) for name in (
            "grant_public_key_file", "control_ca_file", "control_server_cert_file", "control_server_key_file",
            "stream_tls_cert_file", "stream_tls_key_file", "broker_ca_file", "control_broker_token_file",
            "stream_broker_token_file", "control_broker_client_cert_file", "control_broker_client_key_file",
            "stream_broker_client_cert_file", "stream_broker_client_key_file")}
        for name in ("control_server_key_file", "stream_tls_key_file", "control_broker_token_file", "stream_broker_token_file",
                     "control_broker_client_key_file", "stream_broker_client_key_file"):
            if paths[name] in secret_paths:
                raise ValueError("distinct_profile_and_role_secret_selectors_required")
            secret_paths.add(paths[name])
        for name in ("control_broker_client_cert_file", "stream_broker_client_cert_file"):
            if paths[name] in broker_cert_paths:
                raise ValueError("distinct_role_broker_certificate_selectors_required")
            broker_cert_paths.add(paths[name])
        role_hashes = {role: sha_value(entry, role + "_broker_token_sha256") for role in ("control", "stream")}
        for value in role_hashes.values():
            if value in fingerprints:
                raise ValueError("four_distinct_profile_role_fingerprints_required")
            fingerprints.add(value)
        core = entry.get("core_client")
        keys = {"address", "port", "server_name", "ca_file", "cert_file", "key_file", "caller_common_name"}
        if not isinstance(core, dict) or set(core) != keys or core["address"] != control_bind or core["port"] != entry["control_port"]:
            raise ValueError("matching_core_client_endpoint_required")
        for name in ("ca_file", "cert_file", "key_file"):
            path_value(core, name)
        for name in ("server_name", "caller_common_name"):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", text_value(core, name)):
                raise ValueError("literal_core_client_identity_required")
        caller_names.add(core["caller_common_name"])
        if len(caller_names) != 1:
            raise ValueError("canonical_core_client_common_name_required")
        core_clients[alias] = {**core, "proxy_principal_sha256": role_hashes["control"], "stream_principal_sha256": role_hashes["stream"]}
        proxy_bindings[role_hashes["control"]] = [core["caller_common_name"]]
        location = ETC + "/" + instance
        common = {"VAN_BROWSER_PROFILE_ALIAS": alias, "VAN_BROWSER_CDP_PORT": entry["cdp_port"],
                  "VAN_BROWSER_CDP_WEBSOCKET": "ws://127.0.0.1:" + str(entry["cdp_port"]),
                  "VAN_BROWSER_BROKER_ORIGIN": origin.rstrip("/"), "VAN_BROWSER_BROKER_CA": location + "/broker-ca.crt",
                  "VAN_BROWSER_CONTROL_BROKER_TOKEN_FILE": location + "/control-pki/producer.token",
                  "VAN_BROWSER_STREAM_BROKER_TOKEN_FILE": location + "/stream-pki/producer.token",
                  "VAN_BROWSER_CONTROL_BROKER_TOKEN_SHA256": role_hashes["control"],
                  "VAN_BROWSER_STREAM_BROKER_TOKEN_SHA256": role_hashes["stream"]}
        control = {**common, "VAN_BROWSER_CONTROL_BIND": control_bind, "VAN_BROWSER_CONTROL_PORT": entry["control_port"],
                   "VAN_BROWSER_PKI_DIR": location + "/control-pki",
                   "VAN_BROWSER_BROKER_CLIENT_CERT": location + "/control-pki/broker-client.crt",
                   "VAN_BROWSER_BROKER_CLIENT_KEY": location + "/control-pki/broker-client.key"}
        ice = entry.get("ice_servers", [])
        if not isinstance(ice, list) or len(ice) > 8:
            raise ValueError("bounded_ice_configuration_required")
        for item in ice:
            if not isinstance(item, dict) or set(item) - {"urls", "username", "credential"}:
                raise ValueError("bounded_ice_configuration_required")
            urls = [item.get("urls")] if isinstance(item.get("urls"), str) else item.get("urls")
            if (not isinstance(urls, list) or not 1 <= len(urls) <= 4
                    or any(not isinstance(url, str) or len(url) > 4096 or not url.startswith(("stun:", "stuns:", "turn:", "turns:")) for url in urls)
                    or any(not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value)
                           for key, value in item.items() if key != "urls")):
                raise ValueError("bounded_ice_configuration_required")
        clipboard = entry.get("clipboard_enabled", True)
        if type(clipboard) is not bool:
            raise ValueError("explicit_clipboard_boolean_required")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", text_value(entry, "grant_kid")):
            raise ValueError("bounded_grant_verification_key_id_required")
        stream = {**common, "VAN_BROWSER_STREAM_BIND": stream_bind, "VAN_BROWSER_STREAM_PORT": entry["stream_port"],
                  "VAN_BROWSER_SIGNAL_PATH": "/rtc/" + instance, "VAN_BROWSER_QUARANTINE_ROOT": TRANSFER_ROOT + "/" + instance,
                  "VAN_BROWSER_GRANT_KID": text_value(entry, "grant_kid"), "VAN_BROWSER_GRANT_PUBLIC_KEY": location + "/grant-verify.pem",
                  "VAN_BROWSER_STREAM_TLS_CERT": location + "/stream-pki/stream.crt",
                  "VAN_BROWSER_STREAM_TLS_KEY": location + "/stream-pki/stream.key",
                  "VAN_BROWSER_BROKER_CLIENT_CERT": location + "/stream-pki/broker-client.crt",
                  "VAN_BROWSER_BROKER_CLIENT_KEY": location + "/stream-pki/broker-client.key",
                  "VAN_BROWSER_CLIPBOARD_ENABLED": "1" if clipboard else "0",
                  "VAN_BROWSER_ICE_SERVERS_JSON": json.dumps(ice, separators=(",", ":"))}
        width, height = entry.get("width", 1080), entry.get("height", 2016)
        if type(width) is not int or type(height) is not int or not 1 <= width <= 8192 or not 1 <= height <= 8192:
            raise ValueError("bounded_chromium_viewport_required")
        artifacts[instance + "/chromium.env"] = env({"VAN_BROWSER_CDP_PORT": entry["cdp_port"],
            "VAN_BROWSER_PROFILE_MOUNT": PROFILE_ROOT + "/" + instance, "VAN_BROWSER_PROFILE_ALIAS": alias,
            "VAN_BROWSER_EGRESS_PORT": egress_port, "VAN_BROWSER_WIDTH": width, "VAN_BROWSER_HEIGHT": height})
        artifacts[instance + "/egress.env"] = env({"VAN_BROWSER_EGRESS_PORT": egress_port})
        artifacts[instance + "/control.env"] = env(control)
        artifacts[instance + "/stream.env"] = env(stream)
        copies = {"grant-verify.pem": "grant_public_key_file", "broker-ca.crt": "broker_ca_file",
                  "control-pki/ca.crt": "control_ca_file", "control-pki/agent.crt": "control_server_cert_file",
                  "control-pki/agent.key": "control_server_key_file", "control-pki/producer.token": "control_broker_token_file",
                  "control-pki/broker-client.crt": "control_broker_client_cert_file", "control-pki/broker-client.key": "control_broker_client_key_file",
                  "stream-pki/stream.crt": "stream_tls_cert_file", "stream-pki/stream.key": "stream_tls_key_file",
                  "stream-pki/producer.token": "stream_broker_token_file", "stream-pki/broker-client.crt": "stream_broker_client_cert_file",
                  "stream-pki/broker-client.key": "stream_broker_client_key_file"}
        plan.append({"instance": instance, "profile_alias": alias, "users": ["van-browser-" + instance, "van-control-" + instance, "van-stream-" + instance],
                     "egress_user": "van-egress-" + instance, "egress_port": egress_port,
                     "transfer_group": "van-transfer-" + instance, "copy_selectors": {name: paths[source] for name, source in copies.items()},
                     "expected_token_sha256": role_hashes, "cdp_port": entry["cdp_port"]})
        upstreams.append("upstream " + instance + "_native { server " + stream_bind + ":" + str(entry["stream_port"]) + "; }")
        proxy = "\n".join(["proxy_pass https://" + instance + "_native;", "proxy_http_version 1.1;", "proxy_ssl_protocols TLSv1.3;",
            "proxy_ssl_verify on;", "proxy_ssl_server_name on;", "proxy_ssl_name " + stream_name + ";",
            "proxy_ssl_trusted_certificate /etc/van-browser-stream/ingress/" + instance + "-stream-ca.crt;",
            "proxy_request_buffering off;", "proxy_buffering off;", "proxy_read_timeout 90s;", "proxy_connect_timeout 5s;"])
        for selector, method in [("= /rtc/" + instance, "POST"),
            ('~ "^/rtc/' + instance + '/files/download/[A-Za-z0-9_-]+$"', "GET"),
            ('~ "^/rtc/' + instance + '/files/upload/[A-Za-z0-9_-]+$"', "POST"),
            ("= /rtc/" + instance + "/clipboard/copy", "POST"), ("= /rtc/" + instance + "/clipboard/paste", "POST")]:
            locations.append("location " + selector + " {\nlimit_except " + method + " { deny all; }\n" + proxy + "\n}")
    # JSON begins with a non-quote character; EnvironmentFile preserves interior
    # JSON quotes. This also matches the gateway's data-only environment reader.
    artifacts["gateway-browser-profile-bindings.env"] = ("VAN_BROWSER_CONTROL_PROFILE_CLIENTS=" + json.dumps(core_clients, separators=(",", ":")) +
        "\nVAN_BROWSER_CONTROL_PROXY_BINDINGS=" + json.dumps(proxy_bindings, separators=(",", ":")) +
        "\nVAN_BROWSER_STREAM_SIGNAL_URL=" + signal_base + "\nVAN_BROWSER_STREAM_PROFILE_SIGNAL_URLS=" + json.dumps(signal_urls, separators=(",", ":")) + "\n").encode()
    for name in ("chromium", "control-agent", "stream", "transfer-stage", "egress-proxy"):
        template = (PACKAGE / "systemd" / ("van-browser-" + name + "@.service")).read_text()
        artifacts["systemd/van-browser-" + name + "@.service"] = template.replace("@CHROMIUM_EXECUTABLE@", '"' + chromium + '"').encode()
    artifacts["systemd/van-browser-cdp-isolation.service"] = (PACKAGE / "systemd/van-browser-cdp-isolation.service").read_bytes()
    for unit in ("van-browser-media-ingress.service", "van-browser-ingress-stage.service"):
        artifacts["systemd/" + unit] = (PACKAGE / "systemd" / unit).read_text().replace("@NGINX_EXECUTABLE@", '"' + nginx + '"').encode()
    artifacts["media-ingress.conf"] = ("worker_processes 1;\npid /run/van-browser-ingress/nginx.pid;\nerror_log /dev/null crit;\nevents { worker_connections 128; }\nhttp {\naccess_log off;\nclient_body_temp_path /var/lib/van-browser-transfers/.ingress/client;\nproxy_temp_path /var/lib/van-browser-transfers/.ingress/proxy;\nfastcgi_temp_path /var/lib/van-browser-transfers/.ingress/fastcgi;\nuwsgi_temp_path /var/lib/van-browser-transfers/.ingress/uwsgi;\nscgi_temp_path /var/lib/van-browser-transfers/.ingress/scgi;\n" +
        "\n".join(upstreams) + "\nserver {\nlisten " + ingress_bind + ":" + str(ingress_port) + " ssl;\nssl_protocols TLSv1.3;\nssl_certificate /etc/van-browser-stream/ingress/media.crt;\nssl_certificate_key /etc/van-browser-stream/ingress/media.key;\nclient_max_body_size 64m;\n" +
        "\n".join(locations) + "\nlocation / { return 404; }\n}\n}\n").encode()
    declaration = {"schema_version": 1, "profile_id": profile_id, "status": "PREPARED_NOT_INSTALLED",
                   "encrypted_profile_device": device, "chromium_executable": chromium, "chromium_sha256": chromium_sha,
                   "nginx_executable": nginx, "nginx_sha256": nginx_sha,
                   "ingress_copy_selectors": {"media.crt": ingress_cert, "media.key": ingress_key,
                       **{i + "-stream-ca.crt": profiles[i]["stream_tls_ca_file"] for i in ALIASES}},
                   "instances": plan, "artifact_sha256": {name: hashlib.sha256(value).hexdigest() for name, value in artifacts.items()},
                   "installed": False, "live_qualified": False, "pending_checks": ["encrypted_volume_identity", "four_distinct_scoped_producer_credentials",
                       "per_profile_core_mtls_and_proxy_bindings", "uid_scoped_cdp_firewall", "uid_fenced_per_profile_exact_ip_egress", "public_pinned_tls_signal_routes",
                       "pinned_nginx_tls_proxy_capability_and_ingress_recipe", "profile_state_migration_or_new_profile_admission", "host_qualification_and_core_canaries"]}
    artifacts["declaration.json"] = (json.dumps(declaration, indent=2) + "\n").encode()
    return artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        artifacts = render(json.loads(args.profile.read_text()))
        if args.output:
            args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
            for name, value in artifacts.items():
                target = args.output / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                fd, temporary = tempfile.mkstemp(dir=target.parent)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        os.fchmod(stream.fileno(), 0o600)
                        stream.write(value)
                    os.replace(temporary, target)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "BLOCKED", "reason": "invalid_or_unbound_browser_profiles", "installed": False, "live_qualified": False}))
        return 2
    print(json.dumps({"status": "PREPARED_NOT_INSTALLED", "artifacts": sorted(artifacts), "installed": False, "live_qualified": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
