"""Local native-policy/collector fixtures; no host, packet, OCI or phone proof."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from tools.runtime import check_ufw_commander_scope as ufw
from tools.runtime import owner_core_firewall_policy as policy
from tools.runtime import owner_core_network_observations as collector

ROOT = Path(__file__).resolve().parents[2]
DECLARATION = {"ingress_capability": "VAN_OWNER_TLS_PASSTHROUGH_V1", "required_network_lanes": [
    {"source": "owner_phone", "target_host": "oracle-admin", "target_address": "10.0.0.122", "port": 18443},
    {"source": "10.77.0.2", "target_host": "van-trading-core", "target_address": "10.77.0.4", "port": 8443},
    {"source": "10.77.0.1", "target_host": "van-trading-core", "target_address": "10.77.0.4", "port": 8787},
    {"source": "10.77.0.4", "target_host": "dial-control", "target_address": "10.77.0.1", "port": 8642}]}

EMPTY_NAT = "*nat\n:PREROUTING ACCEPT [0:0]\n:INPUT ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\n:POSTROUTING ACCEPT [0:0]\nCOMMIT\n"
BASE = "*filter\n:INPUT DROP [0:0]\n:OUTPUT ACCEPT [0:0]\n:FORWARD DROP [0:0]\n"
ESTABLISHED = "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT\n-A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT\n"
CORE = "-A INPUT -i lo -j ACCEPT\n-A INPUT -i wg-dial -s 10.77.0.2/32 -d 10.77.0.4/32 -p tcp --dport 8443 -j ACCEPT\n-A INPUT -i wg-dial -s 10.77.0.1/32 -d 10.77.0.4/32 -p tcp --dport 8787 -j ACCEPT\n"
CONTROL = "-A INPUT -i wg-dial -s 10.77.0.4/32 -d 10.77.0.1/32 -p tcp --dport 8642 -j ACCEPT\n-A FORWARD -i wg-dial -o wg-dial -s 10.77.0.2/32 -d 10.77.0.4/32 -p tcp --dport 8443 -j ACCEPT\n-A FORWARD -i wg-dial -o wg-dial -s 10.77.0.1/32 -d 10.77.0.4/32 -p tcp --dport 8787 -j ACCEPT\n"
ORACLE = "-A INPUT -i eth0 -d 10.0.0.122/32 -p tcp --dport 18443 -j ACCEPT\n"
V6 = BASE + ESTABLISHED + "COMMIT\n" + EMPTY_NAT


def rules(role="van-trading-core", prefix=""):
    return BASE + prefix + ESTABLISHED + {"van-trading-core": CORE, "dial-control": CONTROL, "oracle-admin": ORACLE}[role] + "COMMIT\n" + EMPTY_NAT


def evaluate(body=None, role="van-trading-core", ipv6=V6, nft=None):
    return policy.evaluate(DECLARATION, role, ipv4=body or rules(role), ipv6=ipv6,
                           nft={"nftables": []} if nft is None else nft)


@pytest.mark.parametrize("role", ["van-trading-core", "dial-control", "oracle-admin"])
def test_exact_observed_native_lanes_pass_local_scope_only(role):
    result = evaluate(role=role)
    assert result["outcome"] == "PASS_LOCAL_NATIVE_POLICY_ONLY"
    assert result["local_native_policy_verified"]
    assert all(part["status"] == "PASS" for name, part in result["parts"].items() if name != "OCI_NSG_and_security_lists")
    assert result["parts"]["OCI_NSG_and_security_lists"]["status"] == "UNKNOWN"
    assert result["firewall_admission_verified"] is result["provider_callback_route_verified"] is result["live_e2e_qualified"] is False


@pytest.mark.parametrize("prefix", [
    "-A INPUT -p tcp --dport 8443 -j ACCEPT\n",
    "-A INPUT -s 203.0.113.77/32 -p tcp --dport 8443 -j ACCEPT\n",
    "-A INPUT -s 10.77.0.3/32 -p tcp --dport 8443 -j ACCEPT\n",
    "-A INPUT -i eth0 -s 10.77.0.2/32 -d 10.77.0.4/32 -p tcp --dport 8443 -j ACCEPT\n",
    "-A INPUT -p tcp --sport 1234 --dport 8443 -j ACCEPT\n",
    "-A INPUT -i wg-dial -s 10.77.0.2/32 -d 10.77.0.4/32 -p tcp --dport 8443 -j DROP\n",
])
def test_world_wrong_source_wrong_interface_narrow_hole_and_earlier_deny_refused(prefix):
    assert evaluate(rules(prefix=prefix))["outcome"] == "FAIL"


def test_ordered_user_chain_return_and_default_policy_are_evaluated():
    body = rules().replace(":FORWARD DROP [0:0]\n", ":FORWARD DROP [0:0]\n:VAN_SCOPE - [0:0]\n")
    body = body.replace(CORE, "-A INPUT -j VAN_SCOPE\n-A INPUT -j DROP\n" + CORE.replace("-A INPUT", "-A VAN_SCOPE") + "-A VAN_SCOPE -j RETURN\n")
    assert evaluate(body)["outcome"] == "PASS_LOCAL_NATIVE_POLICY_ONLY"
    # RETURN in a built-in chain resumes that chain's policy. With ACCEPT it
    # opens traffic, even though a later DROP and narrow rule look reassuring.
    unsafe = rules().replace(":INPUT DROP", ":INPUT ACCEPT").replace(ESTABLISHED, "-A INPUT -j RETURN\n" + ESTABLISHED)
    assert evaluate(unsafe)["outcome"] == "FAIL"


def test_earlier_broad_allow_beats_later_narrow_deny():
    body = rules(prefix="-A INPUT -p tcp --dport 8443 -j ACCEPT\n-A INPUT -s 203.0.113.77/32 -p tcp --dport 8443 -j DROP\n")
    assert evaluate(body)["parts"]["IPv4_filter"]["status"] == "FAIL"


def test_reverse_output_or_hub_forwarding_refusal_is_not_success():
    assert evaluate(rules().replace(":OUTPUT ACCEPT", ":OUTPUT DROP"))["outcome"] == "FAIL"
    assert evaluate(rules("dial-control").replace(CONTROL, CONTROL.split("-A FORWARD")[0]), role="dial-control")["outcome"] == "FAIL"


def test_ipv6_world_open_cannot_hide_behind_ipv4_scope():
    unsafe = V6.replace(":INPUT DROP", ":INPUT ACCEPT")
    assert evaluate(ipv6=unsafe)["parts"]["IPv6_filter"]["status"] == "FAIL"


@pytest.mark.parametrize("fault", ["missing_v6", "missing_nat", "nft_hooks", "unsupported_match", "auxiliary_hook", "recursive_chain"])
def test_incomplete_or_unmodeled_native_semantics_are_unknown(fault):
    body, v6, nft = rules(), V6, {"nftables": []}
    if fault == "missing_v6":
        v6 = None
    elif fault == "missing_nat":
        body = body.replace(EMPTY_NAT, "")
    elif fault == "nft_hooks":
        nft = {"nftables": [{"chain": {"family": "inet", "table": "other", "name": "base", "hook": "input"}}]}
    elif fault == "unsupported_match":
        body = rules(prefix="-A INPUT -m owner --uid-owner 1000 -j ACCEPT\n")
    elif fault == "auxiliary_hook":
        body += "*mangle\n:PREROUTING DROP [0:0]\nCOMMIT\n"
    else:
        body = body.replace(":FORWARD DROP [0:0]\n", ":FORWARD DROP [0:0]\n:RECURSE - [0:0]\n").replace(ESTABLISHED, "-A INPUT -j RECURSE\n-A RECURSE -j RECURSE\n" + ESTABLISHED)
    assert evaluate(body, ipv6=v6, nft=nft)["outcome"] == "UNKNOWN"


def test_translation_of_declared_lane_is_failure_unrelated_translation_unknown():
    translated = rules().replace("COMMIT\n", "COMMIT\n", 1).replace(EMPTY_NAT, EMPTY_NAT.replace("COMMIT", "-A POSTROUTING -s 10.77.0.2/32 -d 10.77.0.4/32 -p tcp --dport 8443 -j MASQUERADE\nCOMMIT"))
    assert evaluate(translated)["parts"]["IPv4_NAT"]["status"] == "FAIL"
    unrelated = translated.replace("10.77.0.2/32 -d 10.77.0.4/32", "172.18.0.0/16 -d 172.19.0.0/16")
    assert evaluate(unrelated)["parts"]["IPv4_NAT"]["status"] == "UNKNOWN"


def ufw_status(rows):
    return "Status: active\nLogging: on (low)\nDefault: deny (incoming), allow (outgoing), deny (routed)\nNew profiles: skip\nTo                         Action      From\n--                         ------      ----\n" + rows


@pytest.mark.parametrize("row", [
    "9133/tcp                   ALLOW IN    Anywhere\n",
    "9133                       ALLOW IN    10.0.0.0/16\n",
    "9133/tcp                   ALLOW IN    10.77.0.1\n",
    "9130:9140/tcp              ALLOW IN    Anywhere\n",
    "Anywhere on eth0           ALLOW IN    Anywhere\n",
    "9133/tcp (v6)              ALLOW IN    Anywhere (v6)\n",
    "9133/tcp                   DENY IN     10.0.0.123\n",
])
def test_legacy_commander_false_green_cases_refused(row):
    assert ufw.evaluate(ufw_status(row + "9133/tcp                   ALLOW IN    10.0.0.123\n"), "10.0.0.123/32")["status"] == "RED"


def test_ufw_exact_sources_and_order_pass_without_native_authority():
    body = ufw_status("[ 1] 9133/tcp               ALLOW IN    10.0.0.123\n[ 2] 9133/tcp               DENY IN     Anywhere\n")
    result = ufw.evaluate(body, "10.0.0.123/32")
    assert result["status"] == "GREEN" and not result["native_firewall_admission_verified"]
    assert ufw.evaluate(body.replace("deny (incoming)", "allow (incoming)"), "10.0.0.123/32")["status"] == "RED"
    assert ufw.evaluate(body, "10.0.0.0123/32")["status"] == "RED"


@pytest.mark.parametrize("unsafe", [False, True])
def test_actual_qualifier_branch_executes_strict_readonly_cli(tmp_path, unsafe):
    # Execute the exact changed branch, avoiding unrelated privileged host checks.
    script = (ROOT / "deploy/van-trading-core/qualify.sh").read_text()
    branch = script.split("# A port substring cannot establish source scope", 1)[1].split('if VAN_ADMIN_CIDRS=', 1)[0]
    branch = "# A port substring cannot establish source scope" + branch
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "python3").symlink_to(sys.executable)
    status = ufw_status("9133/tcp                   ALLOW IN    " + ("Anywhere" if unsafe else "10.0.0.123") + "\n")
    (bindir / "ufw").write_text("#!/bin/sh\n[ \"$*\" = 'status verbose' ] || exit 9\ncat <<'STATUS'\n" + status + "STATUS\n")
    (bindir / "ufw").chmod(0o700)
    run = subprocess.run(["bash", "-c", 'set -uo pipefail\nadd() { printf "%s:%s\\n" "$1" "$2"; }\n' + branch],
                         env={**os.environ, "APP": str(ROOT), "PATH": str(bindir) + ":" + os.environ["PATH"]}, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == ("firewall:RED" if unsafe else "firewall:GREEN")


@pytest.fixture
def declaration(tmp_path, monkeypatch):
    path = tmp_path / "declaration.json"
    path.write_text(json.dumps(DECLARATION))
    monkeypatch.setattr(collector.platform, "node", lambda: "van-trading-core")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_run(unsafe=False):
    calls = []
    def run(program, args):
        calls.append((program, args))
        if program == "ip":
            body = json.dumps([{"dev": "wg-dial", "prefsrc": "10.77.0.4"}]) if "route" in args else json.dumps([{"addr_info": [{"local": "10.77.0.4"}]}])
        elif program == "ss":
            body = "LISTEN 0 128 127.0.0.1:8787 *:*\nLISTEN 0 128 10.77.0.4:8787 *:*\nLISTEN 0 128 10.77.0.4:8443 *:*\n"
        elif program == "wg":
            body = "synthetic-public-peer " + (str(int(time.time()) - 5) if "latest-handshakes" in args else "10.77.0.0/24") + "\n"
        elif program == "iptables-save":
            body = rules(prefix="-A INPUT -p tcp --dport 8443 -j ACCEPT\n" if unsafe else "")
        elif program == "ip6tables-save":
            body = V6
        else:
            body = '{"nftables":[]}\n'
        return {"program": program, "args": args, "outcome": "OBSERVED", "body": body, "body_sha256": hashlib.sha256(body.encode()).hexdigest()}
    return run, calls


def test_collector_binds_inputs_reads_safe_native_facts_and_never_qualifies_phone(declaration):
    run, calls = fixture_run()
    result = collector.collect(*declaration, "van-trading-core", run=run)
    assert result["outcome"] == "PASS_LOCAL_NETWORK_POLICY_ONLY"
    assert result["native_policy"]["local_native_policy_verified"]
    assert result["firewall_admission_verified"] is result["OCI_policy_verified"] is result["device_provisioning_permitted"] is False
    assert ("wg", ["show", "wg-dial", "latest-handshakes"]) in calls
    assert ("wg", ["show", "wg-dial", "allowed-ips"]) in calls
    assert not any("dump" in args for _, args in calls)
    assert "synthetic-public-peer" not in json.dumps(result)


def test_collector_refuses_confirmed_policy_failure(declaration):
    run, _ = fixture_run(unsafe=True)
    assert collector.collect(*declaration, "van-trading-core", run=run)["outcome"] == "BLOCKED"


def test_wrong_declaration_or_host_refuses_before_probe(declaration, monkeypatch):
    no_probe = lambda *_: pytest.fail("wrong selection executed native probe")
    assert collector.collect(declaration[0], "f" * 64, "van-trading-core", run=no_probe)["outcome"] == "BLOCKED"
    monkeypatch.setattr(collector.platform, "node", lambda: "cloud-host")
    assert collector.collect(*declaration, "van-trading-core", run=no_probe)["outcome"] == "BLOCKED"


def test_hash_matching_declaration_cannot_add_an_extra_core_source(declaration):
    path, _ = declaration
    body = json.loads(path.read_text())
    body["required_network_lanes"][1]["source"] = "10.77.0.3"
    path.write_text(json.dumps(body))
    no_probe = lambda *_: pytest.fail("wrong private edge executed a probe")
    assert collector.collect(path, hashlib.sha256(path.read_bytes()).hexdigest(), "van-trading-core", run=no_probe)["outcome"] == "BLOCKED"


@pytest.mark.parametrize("wildcard", ["0.0.0.0", "::", "*"])
def test_private_listener_checks_refuse_ipv4_ipv6_or_unspecified_bindings(wildcard):
    pairs = {("127.0.0.1", 8787), ("10.77.0.4", 8787), ("10.77.0.4", 8443), (wildcard, 8443)}
    assert not collector.private_listener_checks("van-trading-core", DECLARATION["required_network_lanes"], pairs)["protected_listener_bindings_narrow"]


def test_ingress_same_numeric_port_preserves_separate_DDS_overlay_listener():
    lane = {"source": "owner_phone", "target_host": "oracle-admin", "target_address": "10.0.0.122", "port": 8443}
    assert all(collector.private_listener_checks("oracle-admin", [lane], {("10.0.0.122", 8443), ("10.77.0.2", 8443)}).values())


@pytest.mark.parametrize("case", ["success", "too_large", "nonzero"])
def test_actual_probe_bounds_stdout_and_discards_stderr_without_host_commands(tmp_path, monkeypatch, case):
    program = tmp_path / "fixture-probe"
    program.write_text("#!" + sys.executable + "\nimport sys\nsys.stderr.write('synthetic-stderr-must-not-be-published')\n"
                       + ("sys.stdout.write('x' * 4096)\n" if case == "too_large" else
                          "sys.exit(7)\n" if case == "nonzero" else "sys.stdout.write('fixture-only')\n"))
    program.chmod(0o700)
    monkeypatch.setattr(collector.shutil, "which", lambda _: str(program))
    monkeypatch.setattr(collector, "MAX_BYTES", 128)
    result = collector.probe("fixture-probe", [])
    assert "synthetic-stderr" not in json.dumps(result)
    if case == "success":
        assert result["outcome"] == "OBSERVED" and result["body"] == "fixture-only"
        assert result["body_sha256"] == hashlib.sha256(b"fixture-only").hexdigest()
    else:
        assert result["outcome"] == "BLOCKED" and "body" not in result
        assert result["reason"] == ("observation_limit_exceeded" if case == "too_large" else "observation_refused")
