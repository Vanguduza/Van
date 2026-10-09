"""The public and owner stacks must have distinct mediated egress and exact live readbacks."""
import copy
import json
import os
from pathlib import Path
import shlex
import types

import pytest

from .test_browser_profile_deployment import profile, environment, profiles, installer
import qualify_chromium as qualify


def prepared(profile):
    artifacts = profiles.render(profile)
    declaration = json.loads(artifacts["declaration.json"])
    identities = {user: 2000 + index for index, user in enumerate(
        user for entry in declaration["instances"] for user in entry["users"] + [entry["egress_user"]])}
    return artifacts, declaration, identities


def observation(declaration, identities):
    # Native nft JSON observations use numeric identities and ordered expressions.
    # This synthetic fixture grants no kernel qualification; mutations below model
    # the unsafe policy changes that must fail readback.
    rules = copy.deepcopy(qualify.expected_rules(declaration, identities))
    for rule in rules:
        for expression in rule:
            if expression == {"reject": "tcp_reset"}:
                expression["reject"] = {"type": "tcp reset", "expr": None}
            elif expression == {"reject": "port_unreachable"}:
                expression["reject"] = {"type": "icmpx", "expr": "port-unreachable"}
    return {"nftables": [{"metainfo": {"json_schema_version": 1}},
        {"table": {"family": "inet", "name": "van_browser_cdp", "handle": 10}},
        {"chain": {"family": "inet", "table": "van_browser_cdp", "name": "output", "type": "filter",
            "hook": "output", "prio": -50, "policy": "accept"}},
        *[{"rule": {"family": "inet", "table": "van_browser_cdp", "chain": "output", "expr": rule}}
          for rule in rules]]}


def test_each_rendered_chromium_uses_own_proxy_with_no_extra_authority(profile):
    artifacts, declaration, _ = prepared(profile)
    seen = set()
    for entry in declaration["instances"]:
        name = entry["instance"]
        chromium, egress = environment(artifacts[name + "/chromium.env"]), environment(artifacts[name + "/egress.env"])
        assert int(chromium["VAN_BROWSER_EGRESS_PORT"]) == entry["egress_port"]
        assert egress == {"VAN_BROWSER_EGRESS_PORT": chromium["VAN_BROWSER_EGRESS_PORT"]}
        assert entry["egress_user"] not in entry["users"]
        assert entry["egress_port"] not in seen
        seen.add(entry["egress_port"])
        unit = artifacts["systemd/van-browser-chromium@.service"].decode()
        command = next(line.partition("=")[2] for line in unit.splitlines() if line.startswith("ExecStart="))
        argv = shlex.split(command.replace("${VAN_BROWSER_EGRESS_PORT}", chromium["VAN_BROWSER_EGRESS_PORT"]))
        assert qualify.argv_status(argv, entry["egress_port"])["status"] == "GREEN"
        assert "BindsTo=van-browser-egress-proxy@%i.service van-browser-cdp-isolation.service" in unit
    proxy = artifacts["systemd/van-browser-egress-proxy@.service"].decode()
    assert "User=van-egress-%i" in proxy and "--host 127.0.0.1 --port ${VAN_BROWSER_EGRESS_PORT}" in proxy
    assert "InaccessiblePaths=-/var/lib/van-browser-profiles -/var/lib/van-browser-transfers -/etc/van-browser-stream/profiles" in proxy


@pytest.mark.parametrize("conflict", ["same_proxy", "ingress", "other_cdp", "other_control", "own_stream", "boolean", "privileged"])
def test_profile_proxy_port_collision_or_unbounded_value_refuses_preparation(profile, conflict):
    public, owner = profile["profiles"]["public"], profile["profiles"]["owner"]
    public["egress_port"] = 8899
    owner["egress_port"] = {"same_proxy": 8899, "ingress": profile["ingress_port"], "other_cdp": public["cdp_port"],
        "other_control": public["control_port"], "own_stream": owner["stream_port"], "boolean": True, "privileged": 80}[conflict]
    with pytest.raises(ValueError, match="distinct_unprivileged_profile_ports_required"):
        profiles.render(profile)


def test_generated_uid_policy_scopes_cdp_and_proxy_before_a_catch_all_deny(profile, monkeypatch):
    _, declaration, identities = prepared(profile)
    monkeypatch.setattr(installer.pwd, "getpwnam", lambda user: types.SimpleNamespace(pw_uid=identities[user]))
    lines = installer.firewall(declaration).decode().splitlines()
    for entry in declaration["instances"]:
        uid = identities[entry["users"][0]]
        own = [line.strip() for line in lines if line.strip().startswith("meta skuid " + str(uid) + " ")]
        assert own == [
            f'meta skuid {uid} ip daddr 127.0.0.1 tcp dport {entry["egress_port"]} accept',
            f'meta skuid {uid} ip saddr 127.0.0.1 ip daddr 127.0.0.1 tcp sport {entry["cdp_port"]} ct state established ct direction reply accept',
            f'meta skuid {uid} reject']
        allow = next(line for line in lines if "tcp dport " + str(entry["cdp_port"]) in line and "accept" in line)
        assert str(identities[entry["egress_user"]]) not in allow
        other = next(item for item in declaration["instances"] if item != entry)
        assert str(identities[other["users"][0]]) not in allow
    assert "ct state established,related" not in "\n".join(lines)


@pytest.mark.parametrize("defect", ["missing_deny", "wrong_proxy", "cross_uid", "earlier_allow", "wrong_hook", "duplicate_uid", "unsupported_state", "missing_direction", "original_direction", "numeric_alias"])
def test_kernel_readback_refuses_missing_widened_or_unsupported_profile_fence(profile, defect):
    _, declaration, identities = prepared(profile)
    observed = observation(declaration, identities)
    records = observed["nftables"]
    if defect == "missing_deny":
        records.pop()
    elif defect == "wrong_proxy":
        records[7]["rule"]["expr"][2]["match"]["right"] = declaration["instances"][1]["egress_port"]
    elif defect == "cross_uid":
        records[7]["rule"]["expr"][0]["match"]["right"] = identities["van-browser-owner"]
    elif defect == "earlier_allow":
        records.insert(3, {"rule": {"family": "inet", "table": "van_browser_cdp", "chain": "output", "expr": [{"accept": None}]}})
    elif defect == "wrong_hook":
        records[2]["chain"]["hook"] = "input"
    elif defect == "duplicate_uid":
        identities["van-egress-owner"] = identities["van-browser-public"]
    elif defect == "unsupported_state":
        records[8]["rule"]["expr"][-3]["match"]["right"] = {"set": ["established", "related"]}
    elif defect == "missing_direction":
        records[8]["rule"]["expr"].pop(-2)
    elif defect == "original_direction":
        records[8]["rule"]["expr"][-2]["match"]["right"] = "original"
    else:
        records[7]["rule"]["expr"][2]["match"]["right"] = float(declaration["instances"][0]["egress_port"])
    assert qualify.firewall_status(observed, declaration, identities)["status"] in {"RED", "UNKNOWN"}


def test_complete_known_kernel_observation_accepts_only_exact_distinct_profile_fences(profile):
    _, declaration, identities = prepared(profile)
    assert qualify.firewall_status(observation(declaration, identities), declaration, identities)["status"] == "GREEN"


@pytest.mark.parametrize("flags", [["dormant"], ["unsupported"], "dormant", None])
def test_disabled_or_unsupported_native_table_flags_cannot_qualify_green(profile, flags):
    _, declaration, identities = prepared(profile)
    observed = observation(declaration, identities)
    observed["nftables"][1]["table"]["flags"] = flags
    assert qualify.firewall_status(observed, declaration, identities)["status"] == "RED"


def test_explicit_empty_native_table_flags_preserve_active_policy_qualification(profile):
    _, declaration, identities = prepared(profile)
    observed = observation(declaration, identities)
    observed["nftables"][1]["table"]["flags"] = []
    assert qualify.firewall_status(observed, declaration, identities)["status"] == "GREEN"


def test_standard_native_uid_set_and_established_membership_are_narrowly_equivalent(profile):
    _, declaration, identities = prepared(profile)
    observed = observation(declaration, identities)
    # Explicit native expression shapes, independent of expected_rules output.
    observed["nftables"][3]["rule"]["expr"][2] = {"match": {"op": "in",
        "left": {"meta": {"key": "skuid"}}, "right": {"set": [2002, 0, 2001, 2000]}}}
    observed["nftables"][8]["rule"]["expr"][-3] = {"match": {"op": "in",
        "left": {"ct": {"key": "state"}}, "right": {"set": ["established"]}}}
    observed["nftables"][11]["rule"]["expr"][-3] = {"match": {"op": "in",
        "left": {"ct": {"key": "state"}}, "right": "established"}}
    observed["nftables"][8]["rule"]["expr"][-2] = {"match": {"op": "==",
        "left": {"ct": {"key": "direction"}}, "right": "reply"}}
    assert qualify.firewall_status(observed, declaration, identities)["status"] == "GREEN"
    observed["nftables"][8]["rule"]["expr"][-3]["match"]["right"] = {"set": ["established", "related"]}
    assert qualify.firewall_status(observed, declaration, identities)["status"] == "UNKNOWN"


@pytest.mark.parametrize("expression", [
    {"match": {"op": "in", "left": {"meta": {"key": "skuid"}}, "right": {"set": [0, True, 2000]}}},
    {"match": {"op": "in", "left": {"meta": {"key": "skuid"}}, "right": 2000}},
    {"match": {"op": "in", "left": {"payload": {"protocol": "tcp", "field": "dport"}}, "right": {"set": [8899, 8900]}}},
])
def test_membership_normalization_never_accepts_numeric_alias_or_unbounded_port_set(expression):
    with pytest.raises(ValueError):
        qualify.canonical_expr(expression)


@pytest.mark.parametrize("defect", ["substring", "conflicting_duplicate", "missing_webrtc", "quic_value"])
def test_argv_readback_refuses_substring_or_override_that_changes_effective_egress(defect):
    argv = ["chromium", "--proxy-server=http://127.0.0.1:8899", "--proxy-bypass-list=<-loopback>",
            "--disable-quic", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"]
    if defect == "substring":
        argv[1] = "--other=" + argv[1]
    elif defect == "conflicting_duplicate":
        argv.append("--proxy-server=direct://")
    elif defect == "missing_webrtc":
        argv.pop()
    else:
        argv[3] = "--disable-quic=false"
    assert qualify.argv_status(argv, 8899)["status"] == "RED"


def test_process_readback_checks_actual_uid_and_rejects_missing_pid():
    actual = qualify.process_status(os.getpid(), os.getuid() + 1, 8899)
    assert actual == {"status": "RED", "detail": "selected_chromium_process_uid_mismatch"}
    assert qualify.process_status(0, os.getuid(), 8899)["status"] == "UNKNOWN"
