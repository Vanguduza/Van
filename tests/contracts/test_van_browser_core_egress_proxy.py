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


# ------------------------------------------------------- unit G14: the in-zone canary origin
#
# Owner answer 2026-09-30 after unit G13 ("In-zone canary origin (Recommended)"): the canary
# origin is the proxy's only allowed non-global upstream, never reachable by a task scope; the
# local-address rule stays strict for everything else. Live cases (Chromium, the real proxy
# process, a non-loopback fixture): backend/tests/test_browser_canary_origin.py.
CANARY_ORIGIN = "https://canary.van-browser-core.internal"
CANARY = ep.parse_canary(CANARY_ORIGIN, "10.40.0.9")
CANARY_SCOPE = {"entries": [{"origin": CANARY_ORIGIN, "path_prefix": "/docs/"}]}


@pytest.mark.parametrize("origin,address", [
    (CANARY_ORIGIN, "127.0.0.1"),                 # loopback stays unreachable
    (CANARY_ORIGIN, "127.0.0.53"),
    (CANARY_ORIGIN, "0.0.0.0"),
    (CANARY_ORIGIN, "169.254.10.1"),              # link-local
    (CANARY_ORIGIN, "8.8.8.8"),                   # global: not an overlay address
    (CANARY_ORIGIN, "224.0.0.1"),
    (CANARY_ORIGIN, "::1"),
    (CANARY_ORIGIN, "fd00::1"),                   # IPv4 only
    (CANARY_ORIGIN, ""),
    ("", "10.40.0.9"),
    ("http://canary.van-browser-core.internal", "10.40.0.9"),     # TLS only
    ("https://canary.example.com", "10.40.0.9"),                  # an overlay name only
    ("https://internal", "10.40.0.9"),
    ("https://canary.van-browser-core.internal/docs/", "10.40.0.9"),  # an origin, no path
    ("https://canary.van-browser-core.internal/?x=1", "10.40.0.9"),
    ("https://u@canary.van-browser-core.internal", "10.40.0.9"),
])
def test_a_canary_config_is_an_overlay_name_and_a_private_overlay_address(origin, address):
    with pytest.raises(ValueError):
        ep.parse_canary(origin, address)


def test_the_canary_config_parses_to_exact_host_address_and_port():
    assert ep.parse_canary("", "") is None
    assert (CANARY.origin, CANARY.host, CANARY.port, CANARY.address) == (CANARY_ORIGIN, "canary.van-browser-core.internal", 443, "10.40.0.9")
    c = ep.parse_canary("https://canary.van-browser-core.internal:8443/", "100.64.1.2")  # CGNAT overlay
    assert (c.origin, c.port) == ("https://canary.van-browser-core.internal:8443", 8443)
    assert ep.parse_canary("https://canary.van-browser-core.internal:443", "10.0.0.1").origin == CANARY_ORIGIN


def _canary_msg(store_key=KEY, alias="guard_canary", task="van-guard-canary", generation=5, holder="q", mutating=False,
                scope=CANARY_SCOPE):
    mac = ep.effect_mac(store_key, alias, generation, holder, task, mutating, ep.scope_digest(scope))
    return {"alias": alias, "lease_generation": generation, "lease_holder_id": holder, "task_id": task,
            "mutating": mutating, "task_scope": scope, "effect_mac": mac}


def _arm(store, store_key=KEY, alias="guard_canary", task="van-guard-canary", generation=5, holder="q",
         origin=CANARY_ORIGIN, address="10.40.0.9"):
    return store.arm_canary({"alias": alias, "lease_generation": generation, "lease_holder_id": holder, "task_id": task,
                             "canary_mac": ep.canary_mac(store_key, alias, generation, holder, task, origin, address)})


def test_no_task_policy_can_name_an_overlay_host():
    store = ep.PolicyStore(KEY, canary=CANARY)
    for msg in (_canary_msg(alias="a", task="t"), _canary_msg(task="task-1"), _canary_msg(alias="public_research"),
                _canary_msg(mutating=True),
                _canary_msg(scope={"entries": [{"origin": "https://other.van-browser-core.internal"}]}),
                _canary_msg(scope={"entries": [{"origin": CANARY_ORIGIN + "/docs/"}]}),
                _canary_msg(scope={"entries": [{"origin": "https://[canary.van-browser-core.internal]"}]}),
                _canary_msg(alias="a", task="t", scope={"entries": [{"origin": "https://x.internal"}]})):
        assert store.set(msg) == "POLICY_SCOPE_RESERVED_HOST", msg
    assert ep.PolicyStore(KEY).set(_canary_msg()) == "POLICY_SCOPE_RESERVED_HOST"  # no canary configured
    assert store.set(_canary_msg()) is None                                       # the canary's own
    assert store.set(_message(generation=9)) is None                              # ordinary scopes unaffected


def test_arming_needs_the_canary_mac_the_canary_task_and_a_current_lease():
    store = ep.PolicyStore(KEY, canary=CANARY)
    assert ep.PolicyStore(KEY).arm_canary({}) == "CANARY_UNCONFIGURED"
    assert ep.PolicyStore(None, canary=CANARY).arm_canary({}) == "POLICY_KEY_UNCONFIGURED"
    assert _arm(store, alias="public_research") == "CANARY_TASK_INVALID"
    assert _arm(store, task="task-1") == "CANARY_TASK_INVALID"
    assert _arm(store, store_key=b"x" * 64) == "CANARY_MAC_INVALID"
    assert _arm(store, address="10.40.0.10") == "CANARY_MAC_INVALID"
    assert _arm(store, origin="https://other.van-browser-core.internal") == "CANARY_MAC_INVALID"
    # The effect MAC is not a canary MAC (context separation).
    assert store.arm_canary({"alias": "guard_canary", "lease_generation": 5, "lease_holder_id": "q",
                             "task_id": "van-guard-canary", "canary_mac": _canary_msg()["effect_mac"]}) == "CANARY_MAC_INVALID"
    assert store.set(_canary_msg(generation=6)) is None
    assert _arm(store, generation=5) == "POLICY_GENERATION_STALE"
    assert _arm(store, generation=6) is None


def test_the_exception_holds_only_for_the_armed_lease_policy_until_it_ends():
    store = ep.PolicyStore(KEY, canary=CANARY)
    assert store.set(_canary_msg()) is None
    assert store.canary_armed(store.get("guard_canary")) is False     # policy alone: not armed
    assert _arm(store) is None
    assert store.canary_armed(store.get("guard_canary")) is True
    assert store.canary_armed(None) is False
    other = ep.Policy("guard_canary", 5, "q", "task-1", False, CANARY_SCOPE, time.monotonic() + 60)
    assert store.canary_armed(other) is False                            # another task id
    mut = ep.Policy("guard_canary", 5, "q", "van-guard-canary", True, CANARY_SCOPE, time.monotonic() + 60)
    assert store.canary_armed(mut) is False                              # mutating
    newer = ep.Policy("guard_canary", 6, "q", "van-guard-canary", False, CANARY_SCOPE, time.monotonic() + 60)
    assert store.canary_armed(newer) is False                            # another lease
    # This lease's own start (non-final revoke) keeps the grant; its end removes it for good.
    rev = lambda final: store.revoke({"alias": "guard_canary", "lease_generation": 5, "lease_holder_id": "q", "final": final,
                                      "revoke_mac": ep.revoke_mac(KEY, "guard_canary", 5, "q", final)})
    assert rev(False) is None and store.canary_grant is not None
    assert store.set(_canary_msg()) is None and store.canary_armed(store.get("guard_canary")) is True
    assert rev(True) is None and store.canary_grant is None and store.get("guard_canary") is None
    assert _arm(store) == "POLICY_LEASE_ENDED"
    # A newer lease's start ends an older grant.
    assert store.set(_canary_msg(generation=7)) is None and _arm(store, generation=7) is None
    assert store.revoke({"alias": "guard_canary", "lease_generation": 8, "lease_holder_id": "q", "final": False,
                         "revoke_mac": ep.revoke_mac(KEY, "guard_canary", 8, "q", False)}) is None
    assert store.canary_grant is None


def test_the_grant_expires(monkeypatch):
    store = ep.PolicyStore(KEY, canary=CANARY)
    monkeypatch.setattr(ep, "CANARY_GRANT_TTL_SECONDS", 0.05)
    assert store.set(_canary_msg()) is None and _arm(store) is None
    time.sleep(0.1)
    assert store.canary_armed(store.get("guard_canary")) is False


@pytest.fixture
def canary_cert(tmp_path):
    if not Path("/usr/bin/openssl").is_file():
        pytest.skip("needs openssl")
    subprocess.run(["/usr/bin/openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
                    "-keyout", str(tmp_path / "canary.key"), "-out", str(tmp_path / "canary.crt"), "-days", "2",
                    "-subj", "/CN=canary", "-addext", "subjectAltName=DNS:canary.van-browser-core.internal"],
                   check=True, capture_output=True)
    return str(tmp_path / "canary.crt")


def _canary_proxy(tmp_path, cert, resolve=None):
    return ep.EgressProxy(ep.PolicyStore(KEY, canary=CANARY), ep.CertAuthority(tmp_path / "ca"), canary_cert=cert,
                          resolve=resolve)


def test_the_canary_host_is_refused_without_a_lookup_unless_armed_tls_and_the_exact_port(tmp_path, canary_cert, monkeypatch):
    # A test override pointing everything at loopback cannot move the canary host either.
    proxy = _canary_proxy(tmp_path, canary_cert, {"*:443": "127.0.0.1:1", "canary.van-browser-core.internal:443": "127.0.0.1:1"})

    async def boom(*a, **k):
        raise AssertionError("no connection for a refused canary request")

    monkeypatch.setattr(asyncio, "open_connection", boom)
    monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "getaddrinfo", boom)
    for host, port, tls, armed in (("canary.van-browser-core.internal", 443, True, False),
                                   ("canary.van-browser-core.internal", 8443, True, True),
                                   ("canary.van-browser-core.internal", 443, False, True)):
        with pytest.raises(ep.Refused) as err:
            asyncio.run(proxy._open_upstream(host, port, tls, armed))
        assert err.value.code == "EGRESS_UPSTREAM_ADDRESS_REFUSED", (host, port, tls, armed)
    seen = []

    async def record(host, port, **kwargs):
        seen.append((host, port, kwargs.get("server_hostname"), kwargs.get("ssl") is proxy.canary_ctx))
        raise OSError("recorded")

    monkeypatch.setattr(asyncio, "open_connection", record)
    with pytest.raises(ep.Refused):
        asyncio.run(proxy._open_upstream("canary.van-browser-core.internal", 443, True, True))
    # Exactly the pinned address and port, the canary name for SNI/verification, the pinned context.
    assert seen == [("10.40.0.9", 443, "canary.van-browser-core.internal", True)]
    assert proxy.canary_ctx.verify_mode == __import__("ssl").CERT_REQUIRED and proxy.canary_ctx.check_hostname


@pytest.mark.parametrize("name", ["localhost", "127.0.0.1", "10.40.0.9", "192.0.2.2", "169.254.169.254"])
def test_every_other_non_global_upstream_stays_refused_with_a_canary_configured(tmp_path, canary_cert, name):
    """The canary address itself, reached under any name but the canary's, is refused too,
    armed or not."""
    proxy = _canary_proxy(tmp_path, canary_cert)
    for tls, armed in ((False, False), (True, False), (True, True)):
        with pytest.raises(ep.Refused) as err:
            asyncio.run(proxy._open_upstream(name, 443, tls, armed))
        assert err.value.code == "EGRESS_UPSTREAM_ADDRESS_REFUSED"


def test_a_canary_config_without_its_pinned_certificate_refuses_to_start(tmp_path):
    with pytest.raises(ValueError):
        ep.EgressProxy(ep.PolicyStore(KEY, canary=CANARY), ep.CertAuthority(tmp_path), canary_cert="")
    proc = _run({"VAN_BROWSER_CANARY_ORIGIN": CANARY_ORIGIN, "VAN_BROWSER_CANARY_ADDRESS": "127.0.0.1"}, tmp_path)
    assert proc.returncode != 0 and "VAN_BROWSER_CANARY_ADDRESS" in proc.stderr


def test_the_canary_mac_is_the_same_in_the_harness_proxy_and_canary(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_HARNESS_STATE_ROOT", str(tmp_path))
    hs = _load(HARNESS, "van_harness_canary_contract")
    args = (KEY, "guard_canary", 5, "q", "van-guard-canary", CANARY_ORIGIN, "10.40.0.9")
    assert ep.canary_mac(*args) == hs.canary_mac(*args)
    assert ep.canary_mac(*args) != ep.effect_mac(KEY, "guard_canary", 5, "q", "van-guard-canary", False,
                                                 ep.scope_digest(CANARY_SCOPE))
    assert (hs.CANARY_ALIAS, hs.CANARY_TASK_ID, hs.CANARY_MAC_CONTEXT) == (ep.CANARY_ALIAS, ep.CANARY_TASK_ID, ep.CANARY_MAC_CONTEXT)
    canary = (ROOT / "deploy/van-browser-core/browser/guard_canary.py").read_text(encoding="utf-8")
    assert "service.canary_mac(" in canary and '"op": "canary"' in canary
    # No gateway code computes the canary MAC context.
    assert not [p for p in (ROOT / "backend/van_gateway").rglob("*.py") if "van-egress-canary" in p.read_text(encoding="utf-8")]
