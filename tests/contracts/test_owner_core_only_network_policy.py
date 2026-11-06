"""Synthetic core-only policy fixtures; no live deployment, OCI or handset claims."""
import copy
import hashlib
import json
import time

import pytest
from tools.runtime import owner_core_firewall_policy as policy
from tools.runtime import owner_core_network_observations as collector

DECLARATION = {
    "schema_version": 2, "topology": "CORE_ONLY_V2", "runtime_hosts": ["van-trading-core"],
    "ingress_capability": "VAN_OWNER_CORE_DIRECT_MTLS_V1", "public_ingress_interface": "enp0s6",
    "required_network_lanes": [
        {"source": "owner_phone", "target_host": "van-trading-core", "target_address": "10.0.1.233", "port": 8443, "protocol": "DIRECT_MTLS_HTTPS_WSS"},
        {"source": "127.0.0.1", "target_host": "van-trading-core", "target_address": "127.0.0.1", "port": 8787, "protocol": "SCOPED_TOKEN_LOCAL_HTTP"},
        {"source": "127.0.0.1", "target_host": "van-trading-core", "target_address": "127.0.0.1", "port": 8642, "protocol": "HERMES_PROFILE_LOCAL_HTTP"}]}
BASE = "*filter\n:INPUT DROP [0:0]\n:OUTPUT ACCEPT [0:0]\n:FORWARD DROP [0:0]\n"
NAT = "*nat\n:PREROUTING ACCEPT [0:0]\n:INPUT ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\n:POSTROUTING ACCEPT [0:0]\nCOMMIT\n"
STATE = "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT\n"
LOCAL = "-A INPUT -i lo -j ACCEPT\n"
PUBLIC = "-A INPUT -i enp0s6 -d 10.0.1.233/32 -p tcp --dport 8443 -j ACCEPT\n"
V4 = BASE + STATE + LOCAL + PUBLIC + "COMMIT\n" + NAT
V6 = BASE + STATE + LOCAL + "COMMIT\n" + NAT


def evaluate(body=V4, ipv6=V6, declaration=DECLARATION, host="van-trading-core", nft=None):
    return policy.evaluate(declaration, host, ipv4=body, ipv6=ipv6, nft={"nftables": []} if nft is None else nft)


def test_exact_direct_and_local_lanes_pass_local_scope_without_oci_or_deployment_authority():
    result = evaluate()
    assert result["outcome"] == "PASS_LOCAL_NATIVE_POLICY_ONLY"
    assert result["parts"]["OCI_NSG_and_security_lists"]["status"] == "UNKNOWN"
    assert not any(result[field] for field in ("deployment_authority_verified", "device_provisioning_permitted", "live_e2e_qualified"))
    assert len(policy.declared_lanes(DECLARATION)) == 3


@pytest.mark.parametrize("rule", [
    "-A INPUT -p tcp --dport 8443 -j ACCEPT\n",
    "-A INPUT -i wg-dial -d 10.0.1.233/32 -p tcp --dport 8443 -j ACCEPT\n",
    "-A INPUT -i enp0s6 -p tcp --dport 8443 -j ACCEPT\n",
    "-A INPUT -s 127.0.0.1/32 -p tcp --dport 8787 -j ACCEPT\n",
    "-A INPUT -i wg-dial -s 10.77.0.1/32 -p tcp --dport 8787 -j ACCEPT\n",
    "-A INPUT -p tcp --dport 8642 -j ACCEPT\n",
    "-A FORWARD -p tcp --dport 8443 -j ACCEPT\n",
    "-A FORWARD -p tcp --dport 8787 -j ACCEPT\n",
    "-A INPUT -p tcp --sport 1234 --dport 8642 -j ACCEPT\n",
    "-A INPUT -i enp0s6 -d 10.0.1.233/32 -p tcp --dport 8443 -j DROP\n",
])
def test_wrong_interface_public_runtime_forwarding_narrow_holes_and_earlier_denies_fail(rule):
    assert evaluate(V4.replace(STATE, rule + STATE))["outcome"] == "FAIL"


def test_missing_local_runtime_or_ingress_and_reply_are_failures():
    for body in (V4.replace(LOCAL, ""), V4.replace(PUBLIC, ""), V4.replace(":OUTPUT ACCEPT", ":OUTPUT DROP")):
        assert evaluate(body)["outcome"] == "FAIL"


def test_unadmitted_ipv6_external_new_admission_fails():
    assert evaluate(ipv6=V6.replace(STATE, "-A INPUT -p tcp --dport 8443 -j ACCEPT\n" + STATE))["outcome"] == "FAIL"


@pytest.mark.parametrize("fault", ["oracle", "control", "old_capability", "extra_host", "extra_lane", "cross_host", "wildcard", "overlay", "interface", "bool_port", "wrong_protocol"])
def test_declared_core_only_topology_cannot_widen(fault):
    declaration = copy.deepcopy(DECLARATION)
    if fault in {"oracle", "control"}:
        declaration["required_network_lanes"][0]["target_host"] = "oracle-admin" if fault == "oracle" else "dial-control"
    elif fault == "old_capability":
        declaration["ingress_capability"] = "VAN_OWNER_TLS_PASSTHROUGH_V1"
    elif fault == "extra_host":
        declaration["runtime_hosts"].append("dial-control")
    elif fault == "extra_lane":
        declaration["required_network_lanes"].append(copy.deepcopy(declaration["required_network_lanes"][0]))
    elif fault == "cross_host":
        declaration["required_network_lanes"][1]["source"] = "10.77.0.1"
    elif fault in {"wildcard", "overlay"}:
        declaration["required_network_lanes"][0]["target_address"] = "0.0.0.0" if fault == "wildcard" else "10.77.0.4"
    elif fault == "interface":
        declaration["public_ingress_interface"] = "lo"
    elif fault == "bool_port":
        declaration["required_network_lanes"][0]["port"] = True
    else:
        declaration["required_network_lanes"][2]["protocol"] = "SCOPED_TOKEN_LOCAL_HTTP"
    assert evaluate(declaration=declaration)["outcome"] == "FAIL"


@pytest.mark.parametrize("host", ["oracle-admin", "dial-control"])
def test_current_declaration_refuses_non_core_collection(host):
    assert evaluate(host=host)["outcome"] == "FAIL"


def test_incomplete_native_or_independent_nft_is_unknown():
    assert evaluate(ipv6=None)["outcome"] == "UNKNOWN"
    assert evaluate(body=V4.replace(NAT, ""))["outcome"] == "UNKNOWN"
    assert evaluate(nft={"nftables": [{"chain": {"hook": "input"}}]})["outcome"] == "UNKNOWN"


def test_local_nat_translation_is_failure_and_unrelated_nat_is_unknown():
    translated = V4.replace(NAT, NAT.replace("COMMIT", "-A POSTROUTING -o lo -s 127.0.0.1/32 -d 127.0.0.1/32 -p tcp --dport 8787 -j MASQUERADE\nCOMMIT"))
    assert evaluate(translated)["parts"]["IPv4_NAT"]["status"] == "FAIL"
    assert evaluate(translated.replace("127.0.0.1/32 -d 127.0.0.1/32", "172.18.0.0/16 -d 172.19.0.0/16"))["parts"]["IPv4_NAT"]["status"] == "UNKNOWN"


@pytest.mark.parametrize("address,port", [("0.0.0.0", 8443), ("::", 8443), ("10.77.0.4", 8787), ("10.77.0.4", 8642)])
def test_listener_observation_rejects_overlay_and_wildcard_runtime(address, port):
    lanes = policy.declared_lanes(DECLARATION)
    pairs = {(lane["target_address"], lane["port"]) for lane in lanes} | {(address, port)}
    assert not collector.private_listener_checks("van-trading-core", lanes, pairs)["protected_listener_bindings_narrow"]


def test_collector_observes_core_vnic_and_only_local_runtime_lanes(tmp_path, monkeypatch):
    monkeypatch.setattr(collector.platform, "node", lambda: "van-trading-core")
    path = tmp_path / "declaration.json"
    path.write_text(json.dumps(DECLARATION))
    calls = []
    def run(program, args):
        calls.append((program, args))
        if program == "ip":
            iface = args[-1]
            body = json.dumps([{"ifname": iface, "addr_info": [{"family": "inet", "local": "10.0.1.233" if iface == "enp0s6" else "10.77.0.4"}]}])
        elif program == "ss":
            body = "LISTEN 0 128 10.0.1.233:8443 *:*\nLISTEN 0 128 127.0.0.1:8787 *:*\nLISTEN 0 128 127.0.0.1:8642 *:*\n"
        elif program == "wg":
            body = "synthetic-public-peer " + (str(int(time.time()) - 2) if "latest-handshakes" in args else "10.77.0.1/32") + "\n"
        else:
            body = V4 if program == "iptables-save" else V6 if program == "ip6tables-save" else '{"nftables":[]}'
        return {"program": program, "args": args, "outcome": "OBSERVED", "body": body, "body_sha256": hashlib.sha256(body.encode()).hexdigest()}
    result = collector.collect(path, hashlib.sha256(path.read_bytes()).hexdigest(), "van-trading-core", run=run)
    assert result["outcome"] == "PASS_LOCAL_NETWORK_POLICY_ONLY"
    assert result["runtime_hosts"] == ["van-trading-core"] and result["checks"]["selected_core_ingress_interface_address"]
    assert not any("route" in args for _, args in calls)
    assert not result["OCI_policy_verified"] and not result["live_e2e_qualified"]
