"""The installer cannot confuse staged credentials with actual Gateway admission."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("owner_installer", Path(__file__).resolve().parents[2] / "tools/provisioning/provision_owner_device.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def receipt():
    return {"state": "SESSION_ADMITTED", "steps": {s: True for s in
            ["binding", "pairing", "tls_certificate", "session_admitted"]},
            "transport_receipt": {"audit_id": "test-observed-admission", "van_session_id": "test-session"}}


def test_installer_mints_after_device_ready_and_install_then_waits_for_server(monkeypatch, capsys):
    calls = []
    secret = "test-internal-credential-never-printed"
    monkeypatch.setenv("INSTALLER_TEST_TOKEN", secret)
    def run(argv, **kwargs):
        calls.append("check" if "get-state" in argv else "model" if "getprop" in argv else "install" if "install" in argv else "handoff")
        return "device" if "get-state" in argv else "SM_S928B" if "getprop" in argv else "accepted"
    def issue(*args, **kwargs):
        calls.append("mint")
        assert args[1] == secret
        return {"payload": {"bootstrap_token": "b" * 40, "provisioning_id": "attempt"}, "signature": "signature", "kid": "key"}
    def wait(*args, **kwargs):
        calls.append("receipt")
        assert args[2] == "b" * 40
        return receipt()
    monkeypatch.setattr(installer, "run", run)
    monkeypatch.setattr(installer, "request_payload", issue)
    monkeypatch.setattr(installer, "wait_for_admission", wait)
    assert installer.main(["--gateway", "https://van.example", "--internal-token-env", "INSTALLER_TEST_TOKEN",
                           "--serial", "synthetic-s24", "--allow-development-artifact", "--apk", "owner.apk"]) == 0
    assert calls == ["check", "model", "install", "mint", "handoff", "receipt"]
    printed = capsys.readouterr()
    assert secret not in printed.out + printed.err
    assert "b" * 40 not in printed.out + printed.err
    assert json.loads(printed.out)["owner_e2e_verified"] is False
    assert json.loads(printed.out)["owner_release_artifact_verified"] is False


def test_staging_never_passes_admission_and_timeout_is_failure(monkeypatch):
    clock = iter([0.0, 3.0])
    monkeypatch.setattr(installer.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(installer, "request_json", lambda *a, **kw: {"state": "NEEDS_BINDING"})
    with pytest.raises(installer.ProvisioningFailed, match="timed out: NEEDS_BINDING"):
        installer.wait_for_admission("https://van.example", "credential", "b" * 40, wait_seconds=1)


def test_incomplete_admission_receipt_is_failure(monkeypatch):
    incomplete = receipt()
    incomplete["steps"]["binding"] = False
    monkeypatch.setattr(installer, "request_json", lambda *a, **kw: incomplete)
    with pytest.raises(installer.ProvisioningFailed, match="incomplete"):
        installer.wait_for_admission("https://van.example", "credential", "b" * 40, wait_seconds=1)


def test_transient_readback_retries_same_attempt_without_minting(monkeypatch):
    calls = []
    def read(*args, **kwargs):
        calls.append((args[2], args[3]))
        if len(calls) == 1:
            raise installer.ProvisioningFailed("temporary transport failure", retryable=True)
        return receipt()
    monkeypatch.setattr(installer, "request_json", read)
    monkeypatch.setattr(installer.time, "sleep", lambda _: None)
    result = installer.wait_for_admission("https://van.example", "credential", "b" * 40, wait_seconds=5)
    assert result["state"] == "SESSION_ADMITTED"
    assert calls == [(installer.PROVISIONING_STATUS_ROUTE, {"bootstrap_token": "b" * 40})] * 2


def test_adb_failures_never_print_payload_or_full_argv(monkeypatch):
    secret = "sensitive-envelope"
    def timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 1, output=secret, stderr=secret)
    monkeypatch.setattr(installer.subprocess, "run", timeout)
    with pytest.raises(installer.ProvisioningFailed) as failure:
        installer.run(installer.start_argv(None, secret))
    assert secret not in str(failure.value)


def test_operator_credential_does_not_follow_http_redirect():
    destination_calls = []
    class Destination(BaseHTTPRequestHandler):
        def do_GET(self):
            destination_calls.append(self.headers.get("X-Van-Internal-Token"))
            self.send_response(200)
            self.end_headers()
        def log_message(self, *args):
            pass
    destination = ThreadingHTTPServer(("127.0.0.1", 0), Destination)
    class Redirect(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{destination.server_port}/leak")
            self.end_headers()
        def log_message(self, *args):
            pass
    redirect = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (destination, redirect)]
    for thread in threads:
        thread.start()
    try:
        with pytest.raises(installer.ProvisioningFailed, match="302"):
            installer.request_json(f"http://127.0.0.1:{redirect.server_port}", "credential", "/test", {})
        assert destination_calls == []
    finally:
        for server in (redirect, destination):
            server.shutdown()
            server.server_close()


@pytest.mark.parametrize("gateway", ["http://untrusted.example", "https://user:password@van.example", "https://van.example?token=bad"])
def test_installer_refuses_untrusted_operator_urls_before_network(gateway):
    with pytest.raises(installer.ProvisioningFailed, match="trusted HTTPS"):
        installer.request_json(gateway, "credential", "/test", {})


def test_release_provisioning_refuses_missing_packet_before_device_or_network(monkeypatch):
    monkeypatch.setattr(installer, "run", lambda *args, **kw: pytest.fail("must not touch phone"))
    monkeypatch.setattr(installer, "request_payload", lambda *args, **kw: pytest.fail("must not mint"))
    with pytest.raises(installer.ProvisioningFailed, match="bindings required"):
        installer.main(["--gateway", "https://owner.example:8443", "--serial", "synthetic-s24", "--apk", "owner.apk"])


def test_provisioning_refuses_implicit_device_even_for_development(monkeypatch):
    monkeypatch.setattr(installer, "run", lambda *args, **kw: pytest.fail("must not touch phone"))
    with pytest.raises(installer.ProvisioningFailed, match="serial required"):
        installer.main(["--gateway", "https://van.example", "--allow-development-artifact"])


def test_provisioning_checks_admitted_model_before_install_or_mint(monkeypatch):
    monkeypatch.setenv("INSTALLER_TEST_TOKEN", "synthetic-enrolment")
    monkeypatch.setattr(installer, "run", lambda argv, **kw: "device" if "get-state" in argv else "OTHER_MODEL")
    monkeypatch.setattr(installer, "request_payload", lambda *args, **kw: pytest.fail("must not mint"))
    with pytest.raises(installer.ProvisioningFailed, match="model does not match"):
        installer.main(["--gateway", "https://van.example", "--serial", "synthetic-s24", "--allow-development-artifact",
                        "--internal-token-env", "INSTALLER_TEST_TOKEN", "--apk", "owner.apk"])
