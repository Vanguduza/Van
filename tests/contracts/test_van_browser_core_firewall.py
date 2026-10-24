"""Unit G12 — the van-browser-core zone firewall and its qualification.

Owner answer 2026-09-30 after review I7, "Firewall UDP in zone (Recommended)": "Add a host
firewall rule in the van-browser-core deploy that drops all UDP from the browser user except
DNS to the resolver. Applied at provisioning and checked by qualify.sh." Plus, for the egress
proxy: direct TCP from the browser user is dropped except to the local proxy (loopback).

Two layers:

* parse-level (always): the ruleset's rules, their order, what bootstrap.sh and the units do
  with it, and that qualify.sh requires the checks;
* live, in a throw-away network namespace (``unshare -n``; needs root, ``unshare`` and
  ``nft``, skipped otherwise): the real ruleset loaded into the kernel's nftables, sockets
  opened as an unprivileged uid standing in for the browser user, and ``qualify.sh`` itself
  run against it and against a running egress proxy. This is the kernel's enforcement of the
  ruleset, not a van-browser-core host: provisioning on the real host stays unverified.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ZONE_DIR = ROOT / "deploy" / "van-browser-core"
RULESET = ZONE_DIR / "firewall" / "van-browser-core.nft"
VARS_INCLUDE = '/etc/van-browser-core/firewall-vars.nft'
ORDER = ["van-local-reset", "van-dns-resolver", "van-udp-drop", "van-loopback-tcp", "van-loopback-tcp6",
         "van-tcp-bypass-reject", "van-other-drop"]
FIREWALL_CHECKS = ["firewall_loaded", "browser_udp_blocked", "browser_tcp_bypass_blocked"]
EGRESS_CHECKS = ["egress_proxy_active", "egress_refuses_without_policy", "egress_policy_mac_enforced",
                 "egress_refuses_websocket_and_write", "egress_refuses_smuggling", "egress_refuses_other_users"]


def _chain(name: str) -> list[str]:
    text = RULESET.read_text(encoding="utf-8")
    chain = re.search(rf"chain {name} \{{(.*?)\n\t\}}", text, re.S).group(1)
    return [line.strip() for line in chain.splitlines() if line.strip() and not line.strip().startswith("#")]


# ------------------------------------------------------------------------------ parse level
def test_ruleset_rules_and_order():
    """Review I8 MAJOR-4: only the browser/Stagehand users' packets are filtered (a jump); the
    output chain accepts everything else, including packets that have no owning socket."""
    text = RULESET.read_text(encoding="utf-8")
    assert f'include "{VARS_INCLUDE}"' in text
    assert _chain("output") == [
        "type filter hook output priority filter; policy accept;",
        'meta skuid { $VAN_BROWSER_UID, $VAN_STAGEHAND_UID } jump browser_out comment "van-browser-users"',
    ]
    rules = _chain("browser_out")
    comments = [re.search(r'comment "([a-z0-9-]+)"$', r).group(1) for r in rules]
    assert comments == ORDER
    by = dict(zip(comments, rules))
    # Resets towards this host only (what makes a rejected connect fail at once).
    assert by["van-local-reset"] == 'oifname "lo" tcp flags rst accept comment "van-local-reset"'
    # DNS: the one resolver, UDP port 53, nothing else (review I8 MINOR-5: no TCP/53).
    assert by["van-dns-resolver"] == 'ip daddr $VAN_DNS_RESOLVER udp dport 53 accept comment "van-dns-resolver"'
    assert "tcp dport 53" not in "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    # Every other UDP datagram: no port, address or interface exception.
    assert by["van-udp-drop"] == 'meta l4proto udp counter drop comment "van-udp-drop"'
    # TCP: loopback addresses only, then reset; then drop anything else.
    assert by["van-loopback-tcp"] == 'oifname "lo" ip daddr 127.0.0.0/8 meta l4proto tcp accept comment "van-loopback-tcp"'
    assert by["van-loopback-tcp6"] == 'oifname "lo" ip6 daddr ::1 meta l4proto tcp accept comment "van-loopback-tcp6"'
    assert by["van-tcp-bypass-reject"] == 'meta l4proto tcp counter reject with tcp reset comment "van-tcp-bypass-reject"'
    assert by["van-other-drop"] == 'counter drop comment "van-other-drop"'
    accepts = [r for r in rules if " accept " in f" {r} "]
    assert len(accepts) == 4, accepts  # local resets, UDP DNS, loopback TCP x2: nothing else
    rule_text = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    assert "skuid !=" not in rule_text


def test_bootstrap_applies_the_ruleset_at_provisioning_before_starting_workers():
    text = (ZONE_DIR / "bootstrap.sh").read_text(encoding="utf-8")
    check = text.index('run "nft -c -f $ETC/firewall.nft"')
    load = text.index('run "nft -f $ETC/firewall.nft"')
    assert check < load < text.index('run "systemctl restart')
    assert "define VAN_BROWSER_UID = %s" in text and "define VAN_DNS_RESOLVER = %s" in text
    assert "define VAN_STAGEHAND_UID = %s" in text and 'STAGEHAND_UID="$(id -u van-stagehand' in text
    assert 'BROWSER_UID="$(id -u van-browser' in text
    assert "VAN_BROWSER_DNS_RESOLVER must be the IPv4 address" in text
    assert "nft (nftables) is not installed; the zone firewall is not optional" in text
    assert text.index("van-browser-core-firewall.service van-browser-egress.service van-browser-harness.service") \
        < text.index("VAN_BROWSER_CORE_WORKERS_GREEN")
    assert 'assert h["egress_proxy"] is True' in text


def test_bootstrap_refuses_without_a_resolver(tmp_path):
    # Exercise the real resolver guard without depending on this dial-control
    # host's foreign-zone markers. No bootstrap mutations are executed.
    source = (ZONE_DIR / "bootstrap.sh").read_text()
    start = source.index('DNS_RESOLVER="${VAN_BROWSER_DNS_RESOLVER:-}"')
    end = source.index("node - <<", start)
    guard = tmp_path / "resolver-guard.sh"
    guard.write_text("set -euo pipefail\nCONFIG=/nonexistent/van-resolver-test\n"
                     'refuse() { echo "refused: $*" >&2; exit 2; }\n' + source[start:end])
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    proc = subprocess.run(["bash", str(guard)], env=env, capture_output=True,
                          text=True, timeout=60)
    assert proc.returncode == 2 and "VAN_BROWSER_DNS_RESOLVER" in proc.stderr
    proc = subprocess.run(["bash", str(guard)],
                          env={**env, "VAN_BROWSER_DNS_RESOLVER": "0.0.0.0"}, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2


def test_units_bind_the_workers_to_the_firewall_and_the_proxy():
    systemd = ZONE_DIR / "systemd"
    harness = (systemd / "van-browser-harness.service").read_text(encoding="utf-8")
    stagehand = (systemd / "van-stagehand.service").read_text(encoding="utf-8")
    egress = (systemd / "van-browser-egress.service").read_text(encoding="utf-8")
    firewall = (systemd / "van-browser-core-firewall.service").read_text(encoding="utf-8")
    assert "BindsTo=van-browser-core-firewall.service van-browser-egress.service" in harness
    assert "BindsTo=van-browser-core-firewall.service" in stagehand
    assert "Requires=van-browser-core-firewall.service" in egress
    # The proxy is not the browser user (the firewall would otherwise keep it in too).
    assert "User=van-browser-egress" in egress and "User=van-browser\n" not in egress
    assert "User=van-browser\n" in harness
    assert "ExecStart=/usr/sbin/nft -f /etc/van-browser-core/firewall.nft" in firewall
    assert "ExecStartPre=/usr/sbin/nft -c -f /etc/van-browser-core/firewall.nft" in firewall
    assert "Before=network-pre.target van-browser-harness.service van-stagehand.service van-browser-egress.service" in firewall


def test_qualify_requires_the_firewall_and_proxy_checks():
    text = (ZONE_DIR / "qualify.sh").read_text(encoding="utf-8")
    for check in FIREWALL_CHECKS + EGRESS_CHECKS + ["harness_uses_egress_proxy"]:
        lines = re.findall(rf"add {check} [^\n]*", text)
        assert {line.split()[2] for line in lines} == {"GREEN", "RED"}, check
        # Required: no trailing required=0 argument, so a RED fails qualification.
        assert not any(re.search(r'" 0$', line) for line in lines), check


# ------------------------------------------------------------------------------ live (netns)
def _live_available() -> bool:
    if os.geteuid() != 0 or not shutil.which("unshare") or not shutil.which("nft") or not shutil.which("setpriv"):
        return False
    return subprocess.run(["unshare", "-n", "true"], capture_output=True).returncode == 0


live = pytest.mark.skipif(not _live_available(), reason="needs root, unshare -n, nft and setpriv")

NETNS_DRIVER = textwrap.dedent(r'''
    import errno, fcntl, json, os, socket, struct, subprocess, sys, threading, time
    mode, ruleset = sys.argv[1], sys.argv[2]

    def ifup(name):
        s = socket.socket()
        flags = struct.unpack("16sH", fcntl.ioctl(s, 0x8913, struct.pack("16sH", name.encode(), 0)))[1]
        fcntl.ioctl(s, 0x8914, struct.pack("16sH", name.encode(), flags | 1))

    def addr(name, ip, mask):
        s = socket.socket()
        for req, value in ((0x8916, ip), (0x891C, mask)):  # SIOCSIFADDR, SIOCSIFNETMASK
            sa = struct.pack("HH4s8x", socket.AF_INET, 0, socket.inet_aton(value))
            fcntl.ioctl(s, req, struct.pack("16s", name.encode()) + sa)

    def route(dst, mask, dev):
        # SIOCADDRT: a unicast (not local) route, so 192.0.2.1 is "remote": a packet to it
        # leaves through lo and nothing answers (no firewall: a connect times out).
        import ctypes
        class SockaddrIn(ctypes.Structure):
            _fields_ = [("family", ctypes.c_ushort), ("port", ctypes.c_ushort), ("addr", ctypes.c_uint32),
                        ("zero", ctypes.c_ubyte * 8)]
        class RtEntry(ctypes.Structure):
            _fields_ = [("pad1", ctypes.c_ulong), ("dst", SockaddrIn), ("gateway", SockaddrIn), ("genmask", SockaddrIn),
                        ("flags", ctypes.c_ushort), ("pad2", ctypes.c_short), ("pad3", ctypes.c_ulong),
                        ("pad4", ctypes.c_void_p), ("metric", ctypes.c_short), ("dev", ctypes.c_char_p),
                        ("mtu", ctypes.c_ulong), ("window", ctypes.c_ulong), ("irtt", ctypes.c_ushort)]
        rt = RtEntry()
        ip4 = lambda value: struct.unpack("=I", socket.inet_aton(value))[0]
        rt.dst = SockaddrIn(socket.AF_INET, 0, ip4(dst))
        rt.genmask = SockaddrIn(socket.AF_INET, 0, ip4(mask))
        rt.flags = 0x1  # RTF_UP
        name = ctypes.create_string_buffer(dev.encode())
        rt.dev = ctypes.cast(name, ctypes.c_char_p)
        fcntl.ioctl(socket.socket(), 0x890B, bytes(memoryview(rt)))

    ifup("lo")
    addr("lo:1", "192.0.2.10", "255.255.255.255")  # this host's own non-loopback address
    if os.environ.get("VAN_TEST_REMOTE_IS_LOCAL"):
        # 192.0.2.1 becomes a local address with nothing listening: the kernel itself answers a
        # connect with RST (ECONNREFUSED) whether or not the ruleset is loaded.
        addr("lo:2", "192.0.2.1", "255.255.255.255")
    else:
        route("192.0.2.0", "255.255.255.0", "lo")    # and a "remote" network
    listener = socket.socket(); listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("0.0.0.0", 18080)); listener.listen(16)
    threading.Thread(target=lambda: [listener.accept()[0].close() for _ in iter(int, 1)], daemon=True).start()

    PROBE = """
    import errno, socket, sys
    def udp(h, p):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.sendto(b"x", (h, p)); return "SENT"
        except OSError as e:
            return "BLOCKED" if e.errno == errno.EPERM else "ERR%d" % e.errno
    def tcp(h, p):
        s = socket.socket(); s.settimeout(2)
        try:
            s.connect((h, p)); return "CONNECTED"
        except ConnectionRefusedError:
            return "REJECTED"
        except socket.timeout:
            return "TIMEOUT"
        except OSError as e:
            return "ERR%d" % e.errno
    def ping(h):
        import struct
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_ICMP); s.settimeout(1.5)
            s.sendto(struct.pack("!BBHHH", 8, 0, 0, 1, 1) + b"van", (h, 0)); s.recvfrom(1024); return "REPLY"
        except socket.timeout:
            return "NO_REPLY"
        except OSError as e:
            return "BLOCKED" if e.errno == errno.EPERM else "ERR%d" % e.errno
    def unreach():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(1.5)
        try:
            s.connect(("127.0.0.1", 9)); s.send(b"x"); s.recv(10); return "DATA"
        except ConnectionRefusedError:
            return "ICMP_UNREACH_RECEIVED"
        except socket.timeout:
            return "NO_ICMP"
        except OSError as e:
            return "ERR%d" % e.errno
    print({"udp_stun_loopback": udp("127.0.0.1", 3478), "udp_quic_remote": udp("192.0.2.1", 443),
           "icmp_ping_loopback": ping("127.0.0.1"), "icmp_ping_host_address": ping("192.0.2.10"),
           "udp_closed_port_icmp": unreach(), "tcp_resolver_53": tcp("127.0.0.53", 53),
           "udp_dns_offhost": udp("192.0.2.10", 53), "tcp_dns_offhost": tcp("192.0.2.10", 53),
           "udp_dns_resolver": udp("127.0.0.53", 53), "udp_resolver_other_port": udp("127.0.0.53", 54),
           "udp_dns_other_server": udp("192.0.2.1", 53),
           "tcp_loopback": tcp("127.0.0.1", 18080), "tcp_host_address": tcp("192.0.2.10", 18080),
           "tcp_remote": tcp("192.0.2.1", 443)})
    """

    with open("/proc/sys/net/ipv4/ping_group_range", "w") as f:
        f.write("0 2147483647")
    for addr53 in ("127.0.0.53", "192.0.2.10"):
        l53 = socket.socket(); l53.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        l53.bind((addr53, 53)); l53.listen(4)
        threading.Thread(target=lambda l=l53: [l.accept()[0].close() for _ in iter(int, 1)], daemon=True).start()

    def probe(uid=None):
        cmd = ["/usr/bin/python3", "-c", PROBE]
        if uid is not None:
            cmd = ["setpriv", f"--reuid={uid}", f"--regid={uid}", "--clear-groups"] + cmd
        return eval(subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout)

    out = {"before": probe(65534), "before_root": probe()}
    if mode in ("load", "qualify"):
        subprocess.run(["nft", "-f", ruleset], check=True)
        out["browser"], out["root"] = probe(65534), probe()
        out["stagehand"], out["other_user"] = probe(65533), probe(65532)
    if mode in ("qualify", "qualify_unloaded"):
        env = dict(os.environ, VAN_QUALIFY_BROWSER_USER="nobody", VAN_QUALIFY_STAGEHAND_USER="65533",
                   PATH="/usr/sbin:/usr/bin:/sbin:/bin")
        q = subprocess.run(["bash", sys.argv[3]], env=env, capture_output=True, text=True, timeout=120)
        out["qualify"] = json.loads(q.stdout.strip().splitlines()[-1])
    print("NETNS " + json.dumps(out))
''')


def _netns(tmp_path: Path, mode: str, env: dict | None = None, resolver: str = "127.0.0.53") -> dict:
    (tmp_path / "vars.nft").write_text(f"define VAN_BROWSER_UID = 65534\ndefine VAN_STAGEHAND_UID = 65533\ndefine VAN_DNS_RESOLVER = {resolver}\n",
                                       encoding="utf-8")
    ruleset = tmp_path / "firewall.nft"
    ruleset.write_text(RULESET.read_text(encoding="utf-8").replace(VARS_INCLUDE, str(tmp_path / "vars.nft")),
                       encoding="utf-8")
    driver = tmp_path / "driver.py"
    driver.write_text(NETNS_DRIVER, encoding="utf-8")
    proc = subprocess.run(["unshare", "-n", sys.executable, str(driver), mode, str(ruleset),
                           str(ZONE_DIR / "qualify.sh")], capture_output=True, text=True, timeout=300,
                          env={**os.environ, **(env or {})})
    line = [l for l in proc.stdout.splitlines() if l.startswith("NETNS ")]
    assert line, proc.stdout + proc.stderr
    return json.loads(line[-1][6:])


@live
def test_live_ruleset_drops_browser_udp_and_direct_tcp(tmp_path):
    out = _netns(tmp_path, "load")
    # Before the ruleset: the stand-in browser uid can send UDP anywhere (the instrument works).
    assert out["before"]["udp_stun_loopback"] == "SENT" and out["before"]["udp_quic_remote"] == "SENT"
    assert out["before"]["tcp_host_address"] == "CONNECTED"
    browser = out["browser"]
    assert browser["udp_stun_loopback"] == "BLOCKED"      # WebRTC STUN
    assert browser["udp_quic_remote"] == "BLOCKED"        # QUIC / WebTransport
    assert browser["udp_resolver_other_port"] == "BLOCKED"
    assert browser["udp_dns_other_server"] == "BLOCKED"
    assert browser["udp_dns_resolver"] == "SENT"          # DNS to the configured resolver only
    assert browser["tcp_loopback"] == "CONNECTED"         # the proxy listeners, CDP, the Harness API
    assert browser["tcp_host_address"] == "REJECTED"      # this host's own non-loopback address
    assert browser["tcp_remote"] == "REJECTED"            # any direct connection: the proxy cannot be bypassed
    # Review I8 MINOR-5: no TCP/53 rule. A loopback resolver (as here, 127.0.0.53) stays
    # reachable over TCP like every loopback port; an off-host one does not (next test).
    assert browser["tcp_resolver_53"] == "CONNECTED"
    assert browser["icmp_ping_loopback"] == "BLOCKED"
    # Review I8 MINOR-4: the Stagehand user is confined the same way.
    assert {k: out["stagehand"][k] for k in browser} == browser
    # Other users are untouched (the egress proxy's user goes out) ...
    for user in ("root", "other_user"):
        assert out[user]["udp_stun_loopback"] == "SENT" and out[user]["tcp_host_address"] == "CONNECTED", user
        assert out[user]["tcp_resolver_53"] == "CONNECTED", user
    # ... and so are packets without an owning socket (review I8 MAJOR-4): the kernel's echo
    # replies and its ICMP port-unreachable reach root exactly as before the ruleset.
    for key in ("icmp_ping_loopback", "icmp_ping_host_address", "udp_closed_port_icmp"):
        assert out["before_root"][key] == out["root"][key], key
    assert out["root"]["icmp_ping_loopback"] == "REPLY" and out["root"]["icmp_ping_host_address"] == "REPLY"
    assert out["root"]["udp_closed_port_icmp"] == "ICMP_UNREACH_RECEIVED"


@live
def test_live_dns_to_an_off_host_resolver_is_udp_only(tmp_path):
    """Review I8 MINOR-5: the owner's exception is UDP DNS; TCP/53 to the resolver is reset."""
    out = _netns(tmp_path, "load", resolver="192.0.2.10")
    assert out["before"]["tcp_dns_offhost"] == "CONNECTED"      # the instrument works
    assert out["browser"]["udp_dns_offhost"] == "SENT"
    assert out["browser"]["tcp_dns_offhost"] == "REJECTED"
    assert out["root"]["tcp_dns_offhost"] == "CONNECTED"


def _qualify_env(tmp_path: Path) -> dict:
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "zone").write_text("van-browser-core\n", encoding="utf-8")
    key = tmp_path / "fence.key"
    key.write_bytes(b"q" * 64)
    key.chmod(0o400)  # as bootstrap.sh installs it
    ctl = tmp_path / "egress.sock"
    (etc / "runtime.env").write_text(f"VAN_EGRESS_CONTROL_SOCKET={ctl}\nVAN_EGRESS_FENCE_KEY_FILE={key}\n"
                                     f"VAN_HARNESS_FENCE_KEY_FILE={key}\n", encoding="utf-8")
    return {"VAN_BROWSER_CORE_ETC": str(etc), "ctl": str(ctl), "key": str(key)}


def _statuses(report: dict) -> dict:
    return {c["check"]: c["status"] for c in report["checks"]}


@live
def test_live_qualify_reports_the_firewall_and_the_proxy_green(tmp_path):
    env = _qualify_env(tmp_path)
    proxy = subprocess.Popen(
        ["unshare", "-n", "--", sys.executable, str(ZONE_DIR / "browser" / "egress_proxy.py")],
        env={"PATH": "/usr/bin:/bin", "VAN_TRUST_ZONE": "van-browser-core", "VAN_EGRESS_CONTROL_SOCKET": env["ctl"],
             "VAN_EGRESS_FENCE_KEY_FILE": env["key"], "VAN_EGRESS_STATE_DIR": str(tmp_path / "egress-state"),
             "VAN_EGRESS_PORT_RANGE": "20000-20010", "VAN_EGRESS_CLIENT_UID": "65534"},
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 20
        while not Path(env["ctl"]).exists():
            assert proxy.poll() is None and time.monotonic() < deadline, proxy.stderr.read()
            time.sleep(0.05)
        # The proxy is in its own namespace: qualify reaches its control socket (a file) and its
        # listeners only through that socket's answers, so run qualify in the proxy's namespace.
        out = _netns_in(proxy.pid, tmp_path, env)
    finally:
        proxy.terminate()
        proxy.wait(5)
    print("QUALIFY_LIVE " + json.dumps(out))
    status = _statuses(out["qualify"])
    for check in FIREWALL_CHECKS + EGRESS_CHECKS:
        assert status[check] == "GREEN", (check, out["qualify"])
    assert status["harness_uses_egress_proxy"] == "RED"  # no Harness here: honest RED, not GREEN
    # No Stagehand here either; the probe itself ran (as uid 65533: key and socket denied).
    iso = next(c["detail"] for c in out["qualify"]["checks"] if c["check"] == "stagehand_isolated")
    assert status["stagehand_isolated"] == "RED" and "notrunning separate DENIED,DENIED,DENIED" in iso, iso
    assert "reset by van-tcp-bypass-reject" in next(c["detail"] for c in out["qualify"]["checks"]
                                                    if c["check"] == "browser_tcp_bypass_blocked")


def _netns_in(pid: int, tmp_path: Path, env: dict) -> dict:
    (tmp_path / "vars.nft").write_text("define VAN_BROWSER_UID = 65534\ndefine VAN_STAGEHAND_UID = 65533\ndefine VAN_DNS_RESOLVER = 127.0.0.53\n",
                                       encoding="utf-8")
    ruleset = tmp_path / "firewall.nft"
    ruleset.write_text(RULESET.read_text(encoding="utf-8").replace(VARS_INCLUDE, str(tmp_path / "vars.nft")),
                       encoding="utf-8")
    driver = tmp_path / "driver.py"
    driver.write_text(NETNS_DRIVER, encoding="utf-8")
    proc = subprocess.run(["nsenter", "-t", str(pid), "-n", sys.executable, str(driver), "qualify", str(ruleset),
                           str(ZONE_DIR / "qualify.sh")], capture_output=True, text=True, timeout=300,
                          env={**os.environ, "VAN_BROWSER_CORE_ETC": env["VAN_BROWSER_CORE_ETC"]})
    line = [l for l in proc.stdout.splitlines() if l.startswith("NETNS ")]
    assert line, proc.stdout + proc.stderr
    return json.loads(line[-1][6:])


@live
def test_live_qualify_fails_without_the_ruleset(tmp_path):
    """The check's failure mode, induced: no ruleset loaded -> RED, and UDP from the browser
    user is measured as sent."""
    out = _netns(tmp_path, "qualify_unloaded", _qualify_env(tmp_path))
    print("QUALIFY_UNLOADED " + json.dumps(out))
    status = _statuses(out["qualify"])
    assert status["firewall_loaded"] == "RED"
    assert status["browser_udp_blocked"] == "RED"
    assert status["browser_tcp_bypass_blocked"] == "RED"
    assert status["egress_proxy_active"] == "RED"  # no proxy running here either
    assert out["qualify"]["fails"] > 0


@live
def test_live_qualify_does_not_take_a_kernel_reset_for_the_ruleset(tmp_path):
    """Review I8 MINOR-5: a refused connect is not proof; without the ruleset the kernel can
    reset the probe too (here: the probe's target is a closed local address). The check needs
    the ruleset's own reject counter to move."""
    out = _netns(tmp_path, "qualify_unloaded", {**_qualify_env(tmp_path), "VAN_TEST_REMOTE_IS_LOCAL": "1"})
    detail = next(c for c in out["qualify"]["checks"] if c["check"] == "browser_tcp_bypass_blocked")
    assert "REJECTED" in detail["detail"]           # the kernel did reset it ...
    assert detail["status"] == "RED"                # ... and that is not the ruleset
