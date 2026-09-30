"""Unit G12 — the egress proxy's decision rules, without a browser.

Owner answer 2026-09-30 after review I7 ("Egress proxy (Recommended)"). The real-Chromium
cases are in ``backend/tests/test_browser_egress_proxy.py``; this pins the pure decision
(``classify``), the authenticated policy channel (``PolicyStore``), the upstream address rule
and the refusals that keep test overrides out of a trust zone.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROXY = ROOT / "deploy/van-browser-core/browser/egress_proxy.py"
HARNESS = ROOT / "deploy/van-browser-core/browser/harness_service.py"
KEY = b"k" * 64


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ep = _load(PROXY, "van_egress_proxy_contract")

SCOPE = {"entries": [{"origin": "https://docs.example.com", "path_prefix": "/docs/"},
                     {"origin": "http://docs.example.com:8080", "path_prefix": None}]}


def _policy(mutating: bool, scope=SCOPE):
    return ep.Policy("a", 1, "h", "t", mutating, scope, time.monotonic() + 60)


def _req(method="GET", target="/docs/x", host="docs.example.com", extra=()):
    return ep.Request(method, target, "HTTP/1.1", [("Host", host), *extra])


@pytest.mark.parametrize("mutating,req,scheme,host,port,expected", [
    (False, _req(), "https", "docs.example.com", 443, None),
    (False, _req(target="/static/app.js"), "https", "docs.example.com", 443, None),  # reads: origin scope
    (False, _req(host="evil.example.net"), "https", "evil.example.net", 443, "EGRESS_ORIGIN_OUT_OF_SCOPE"),
    (False, _req(host="docs.example.com:8443"), "https", "docs.example.com", 8443, "EGRESS_ORIGIN_OUT_OF_SCOPE"),
    (False, _req(host="docs.example.com"), "https", "docs.example.com", 8443, "EGRESS_HOST_MISMATCH"),
    (False, _req(host="other.example.com"), "https", "docs.example.com", 443, "EGRESS_HOST_MISMATCH"),
    (False, _req(target="https://evil.example.net/x"), "https", "docs.example.com", 443, "EGRESS_HOST_MISMATCH"),
    (False, _req("POST", extra=[("Content-Length", "3")]), "https", "docs.example.com", 443, "EGRESS_WRITE_REFUSED"),
    (False, _req("DELETE"), "https", "docs.example.com", 443, "EGRESS_WRITE_REFUSED"),
    (False, _req("OPTIONS"), "https", "docs.example.com", 443, "EGRESS_WRITE_REFUSED"),
    (False, _req("GET", extra=[("Content-Length", "3")]), "https", "docs.example.com", 443, "EGRESS_WRITE_REFUSED"),
    (False, _req(extra=[("Upgrade", "websocket"), ("Connection", "Upgrade")]), "https", "docs.example.com", 443,
     "EGRESS_WEBSOCKET_REFUSED"),
    (False, _req(extra=[("Upgrade", "h2c")]), "https", "docs.example.com", 443, "EGRESS_UPGRADE_REFUSED"),
    (True, _req(extra=[("Upgrade", "h2c")]), "https", "docs.example.com", 443, "EGRESS_UPGRADE_REFUSED"),
    (False, _req(extra=[("Transfer-Encoding", "chunked")]), "https", "docs.example.com", 443, "EGRESS_REQUEST_INVALID"),
    (False, _req(extra=[("Content-Length", "0"), ("Content-Length", "0")]), "https", "docs.example.com", 443,
     "EGRESS_REQUEST_INVALID"),
    (True, _req("POST", extra=[("Content-Length", "3")]), "https", "docs.example.com", 443, None),
    (True, _req("POST", target="/api/pay", extra=[("Content-Length", "3")]), "https", "docs.example.com", 443,
     "EGRESS_WRITE_OUT_OF_SCOPE"),
    (True, _req(target="/api/ws-pay", extra=[("Upgrade", "websocket")]), "https", "docs.example.com", 443,
     "EGRESS_WRITE_OUT_OF_SCOPE"),
    (True, _req(target="/docs/ws", extra=[("Upgrade", "websocket")]), "https", "docs.example.com", 443, None),
    (False, _req(target="/api/ws-pay", host="docs.example.com:8080", extra=[("Upgrade", "websocket")]), "http",
     "docs.example.com", 8080, "EGRESS_WEBSOCKET_REFUSED"),
])
def test_classify(mutating, req, scheme, host, port, expected):
    assert ep.classify(_policy(mutating), req, scheme, host, port)[0] == expected


def test_no_policy_refuses_everything():
    assert ep.classify(None, _req(), "https", "docs.example.com", 443)[0] == "EGRESS_POLICY_UNKNOWN"


def test_connect_authorities_come_from_scope_origins_only():
    policy = _policy(False)
    assert policy.authorities == {("docs.example.com", 443): "https", ("docs.example.com", 8080): "http"}
    assert _policy(False, {"entries": []}).authorities == {}
    assert _policy(False, {"entries": [{"origin": "https://docs.example.com/path"}]}).authorities == {}


def _message(store_key=KEY, alias="a", generation=1, holder="h", mutating=False, scope=SCOPE):
    mac = ep.effect_mac(store_key, alias, generation, holder, "t", mutating, ep.scope_digest(scope))
    return {"alias": alias, "lease_generation": generation, "lease_holder_id": holder, "task_id": "t",
            "mutating": mutating, "task_scope": scope, "effect_mac": mac}


def test_policy_needs_the_effect_mac_and_a_current_generation():
    store = ep.PolicyStore(KEY)
    assert store.set(_message(generation=2)) is None and store.get("a").generation == 2
    flipped = dict(_message(generation=3), mutating=True)
    assert store.set(flipped) == "POLICY_MAC_INVALID"
    widened = dict(_message(generation=3), task_scope={"entries": [{"origin": "https://evil.example.net"}]})
    assert store.set(widened) == "POLICY_MAC_INVALID"
    assert store.set(_message(store_key=b"x" * 64, generation=3)) == "POLICY_MAC_INVALID"
    assert store.set(_message(generation=1)) == "POLICY_GENERATION_STALE"
    assert store.set(_message(generation=2, holder="other")) == "POLICY_GENERATION_STALE"
    assert store.get("a").mutating is False and store.get("a").generation == 2
    assert ep.PolicyStore(None).set(_message()) == "POLICY_KEY_UNCONFIGURED"
    assert store.set(dict(_message(), alias="../x")) == "POLICY_ALIAS_INVALID"


def test_policy_expires():
    store = ep.PolicyStore(KEY, ttl=0.05)
    assert store.set(_message()) is None
    time.sleep(0.1)
    assert store.get("a") is None


def test_the_mac_is_the_harness_effect_mac(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_HARNESS_STATE_ROOT", str(tmp_path))
    hs = _load(HARNESS, "van_harness_egress_contract")
    for mutating in (True, False):
        assert ep.effect_mac(KEY, "a", 3, "h", "t", mutating, ep.scope_digest(SCOPE)) == \
            hs.effect_mac(KEY, "a", 3, "h", "t", mutating, hs.scope_digest(SCOPE))
    assert ep.scope_digest(None) == hs.scope_digest(None)


@pytest.mark.parametrize("name", ["localhost", "127.0.0.1"])
def test_upstream_addresses_that_are_not_global_are_refused(tmp_path, name):
    proxy = ep.EgressProxy(ep.PolicyStore(KEY), ep.CertAuthority(tmp_path))
    with pytest.raises(ep.Refused) as err:
        asyncio.run(proxy._open_upstream(name, 9141, False))
    assert err.value.code == "EGRESS_UPSTREAM_ADDRESS_REFUSED"


def test_refusal_vocabulary_is_closed():
    assert ep.Refused("anything else").code == "EGRESS_REQUEST_INVALID"
    assert ep._refusal("EGRESS_WRITE_REFUSED").startswith(b"HTTP/1.1 403 Forbidden\r\nX-Van-Egress-Refused: EGRESS_WRITE_REFUSED\r\n")
    source = PROXY.read_text(encoding="utf-8")
    import re

    raised = set(re.findall(r'Refused\("([A-Z_]+)"\)', source)) | set(re.findall(r'code = "([A-Z_]+)"', source))
    assert raised and raised <= ep.REFUSALS


def _run(env: dict[str, str], tmp_path: Path) -> subprocess.CompletedProcess:
    base = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "VAN_EGRESS_STATE_DIR": str(tmp_path / "st"),
            "VAN_EGRESS_CONTROL_SOCKET": str(tmp_path / "c.sock")}
    return subprocess.run([sys.executable, str(PROXY)], env={**base, **env}, capture_output=True, text=True, timeout=30)


def test_a_trust_zone_proxy_refuses_test_overrides_and_a_missing_key(tmp_path):
    proc = _run({"VAN_TRUST_ZONE": "van-browser-core", "VAN_EGRESS_TEST_RESOLVE": json.dumps({"*:443": "127.0.0.1:1"})}, tmp_path)
    assert proc.returncode != 0 and "VAN_EGRESS_TEST_" in proc.stderr
    proc = _run({"VAN_TRUST_ZONE": "van-browser-core"}, tmp_path)
    assert proc.returncode != 0 and "VAN_EGRESS_FENCE_KEY_FILE" in proc.stderr


@pytest.mark.skipif(not Path("/usr/bin/openssl").is_file(), reason="needs openssl")
def test_private_keys_stay_in_the_state_directory_and_only_the_spki_leaves(tmp_path):
    ca = ep.CertAuthority(tmp_path / "state")
    ca.ensure()
    assert (tmp_path / "state").stat().st_mode & 0o777 == 0o700
    for name in ("ca.key", "leaf.key"):
        assert (tmp_path / "state" / name).stat().st_mode & 0o777 == 0o400
    assert len(ca.spki) == 44 and ca.spki.endswith("=")
    ctx = ca.context("docs.example.com")
    assert ctx is ca.context("docs.example.com")
    with pytest.raises(ep.Refused):
        ca.context("bad host")
