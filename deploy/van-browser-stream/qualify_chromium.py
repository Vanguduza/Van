#!/usr/bin/env python3
"""Read selected Chromium identity/argv and the dedicated nft policy; never mutate a host."""
import argparse
import json
from pathlib import Path
import pwd
import subprocess


def argv_status(argv, egress_port):
    required = {
        "--proxy-server": "--proxy-server=http://127.0.0.1:" + str(egress_port),
        "--proxy-bypass-list": "--proxy-bypass-list=<-loopback>",
        "--disable-quic": "--disable-quic",
        "--force-webrtc-ip-handling-policy": "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    }
    for name, expected in required.items():
        values = [item for item in argv if item == name or item.startswith(name + "=")]
        if values != [expected]:
            return {"status": "RED", "detail": "missing_or_conflicting_exact_egress_argument:" + name}
    return {"status": "GREEN", "detail": "exact_profile_proxy_and_quic_webrtc_arguments_observed"}


def process_status(pid, expected_uid, egress_port, proc=Path("/proc")):
    try:
        if pid <= 0:
            raise ValueError("missing_pid")
        status = (proc / str(pid) / "status").read_text()
        ids = next(line for line in status.splitlines() if line.startswith("Uid:")).split()[1:]
        if len(ids) != 4 or any(int(value) != expected_uid for value in ids):
            return {"status": "RED", "detail": "selected_chromium_process_uid_mismatch"}
        with (proc / str(pid) / "cmdline").open("rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024 or not raw.endswith(b"\0"):
            raise ValueError("unreadable_argv")
        argv = [value.decode("utf-8") for value in raw.split(b"\0")[:-1]]
    except (OSError, ValueError, StopIteration, UnicodeError):
        return {"status": "UNKNOWN", "detail": "selected_chromium_process_identity_or_argv_unavailable"}
    return argv_status(argv, egress_port)


def match(left, right):
    return {"match": {"op": "==", "left": left, "right": right}}


def expected_rules(declaration, identities):
    rules = []
    if {entry["instance"] for entry in declaration["instances"]} != {"public", "owner"}:
        raise ValueError("profile_instances_unbound")
    for entry in declaration["instances"]:
        users = entry["users"]
        instance = entry["instance"]
        if (users != ["van-browser-" + instance, "van-control-" + instance, "van-stream-" + instance]
                or entry["egress_user"] != "van-egress-" + instance):
            raise ValueError("profile_service_identities_unbound")
        uids = [0] + [identities[user] for user in users]
        common = [match({"payload": {"protocol": "ip", "field": "daddr"}}, "127.0.0.1"),
                  match({"payload": {"protocol": "tcp", "field": "dport"}}, entry["cdp_port"])]
        rules.append(common + [match({"meta": {"key": "skuid"}}, {"set": sorted(uids)}), {"accept": None}])
        rules.append(common + [{"reject": "tcp_reset"}])
    for entry in declaration["instances"]:
        uid = match({"meta": {"key": "skuid"}}, identities[entry["users"][0]])
        rules.append([uid, match({"payload": {"protocol": "ip", "field": "daddr"}}, "127.0.0.1"),
                      match({"payload": {"protocol": "tcp", "field": "dport"}}, entry["egress_port"]), {"accept": None}])
        rules.append([uid, match({"payload": {"protocol": "ip", "field": "saddr"}}, "127.0.0.1"),
                      match({"payload": {"protocol": "ip", "field": "daddr"}}, "127.0.0.1"),
                      match({"payload": {"protocol": "tcp", "field": "sport"}}, entry["cdp_port"]),
                      match({"ct": {"key": "state"}}, "established"),
                      match({"ct": {"key": "direction"}}, "reply"), {"accept": None}])
        rules.append([uid, {"reject": "port_unreachable"}])
    return rules


def canonical_expr(expression):
    if not isinstance(expression, dict) or len(expression) != 1:
        raise ValueError("unsupported_rule_expression")
    if "reject" in expression:
        value = expression["reject"]
        if value is None or value == {"type": "icmpx", "expr": "port-unreachable"}:
            return {"reject": "port_unreachable"}
        if value in ({"type": "tcp reset"}, {"type": "tcp reset", "expr": None}):
            return {"reject": "tcp_reset"}
        raise ValueError("unsupported_reject")
    if "accept" in expression:
        if expression["accept"] is not None:
            raise ValueError("unsupported_accept")
        return expression
    value = expression.get("match")
    if not isinstance(value, dict) or set(value) != {"op", "left", "right"} or value["op"] not in {"==", "in"}:
        raise ValueError("unsupported_match")
    left, right = value["left"], value["right"]
    if value["op"] == "in" and not (
            left == {"ct": {"key": "state"}}
            or left == {"meta": {"key": "skuid"}} and isinstance(right, dict) and set(right) == {"set"}):
        raise ValueError("unsupported_membership")
    if left == {"meta": {"key": "skuid"}}:
        if isinstance(right, dict) and set(right) == {"set"} and all(type(uid) is int for uid in right["set"]):
            right = {"set": sorted(right["set"])}
        elif type(right) is not int:
            raise ValueError("unsupported_uid")
    elif left == {"ct": {"key": "state"}}:
        if right == {"set": ["established"]}:
            right = "established"
        if right != "established":
            raise ValueError("unsupported_connection_state")
    elif left == {"ct": {"key": "direction"}}:
        if right != "reply":
            raise ValueError("unsupported_connection_direction")
    elif left not in ({"payload": {"protocol": "ip", "field": "saddr"}},
                       {"payload": {"protocol": "ip", "field": "daddr"}},
                       {"payload": {"protocol": "tcp", "field": "sport"}},
                       {"payload": {"protocol": "tcp", "field": "dport"}}):
        raise ValueError("unsupported_match_field")
    return match(left, right)


def firewall_status(observation, declaration, identities):
    try:
        if not isinstance(observation, dict) or set(observation) != {"nftables"}:
            raise ValueError("missing_nft_observation")
        selected = [entry for instance in declaration["instances"] for entry in instance["users"] + [instance["egress_user"]]]
        uids = [identities[user] for user in selected]
        if any(type(uid) is not int or uid <= 0 for uid in uids) or len(set(uids)) != len(uids):
            return {"status": "RED", "detail": "browser_service_uids_not_distinct"}
        tables, chains, rules = [], [], []
        for entry in observation["nftables"]:
            if not isinstance(entry, dict) or len(entry) != 1:
                raise ValueError("unsupported_nft_record")
            if "metainfo" in entry:
                continue
            if "table" in entry:
                tables.append(entry["table"])
            elif "chain" in entry:
                chains.append(entry["chain"])
            elif "rule" in entry:
                rule = entry["rule"]
                if (rule.get("family"), rule.get("table"), rule.get("chain")) != ("inet", "van_browser_cdp", "output"):
                    raise ValueError("unexpected_rule_scope")
                rules.append([canonical_expr(expr) for expr in rule["expr"]])
            else:
                raise ValueError("unsupported_nft_record")
        if len(tables) != 1 or (tables[0].get("family"), tables[0].get("name")) != ("inet", "van_browser_cdp"):
            raise ValueError("dedicated_nft_table_unavailable")
        if tables[0].get("flags", []) != []:
            return {"status": "RED", "detail": "dedicated_nft_table_flags_not_active_unrestricted"}
        if len(chains) != 1 or any(chains[0].get(key) != value for key, value in {
            "family": "inet", "table": "van_browser_cdp", "name": "output", "type": "filter", "hook": "output",
            "prio": -50, "policy": "accept"}.items()):
            return {"status": "RED", "detail": "dedicated_nft_output_chain_mismatch"}
        if json.dumps(rules, sort_keys=True) != json.dumps(expected_rules(declaration, identities), sort_keys=True):
            return {"status": "RED", "detail": "ordered_profile_uid_proxy_cdp_fence_mismatch"}
    except (KeyError, TypeError, ValueError):
        return {"status": "UNKNOWN", "detail": "nft_or_profile_observation_unsupported_or_unavailable"}
    return {"status": "GREEN", "detail": "complete_ordered_profile_uid_proxy_cdp_fences_observed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", choices=("flags", "kernel"), required=True)
    parser.add_argument("--pid", type=int, default=0)
    parser.add_argument("--instance", choices=("public", "owner"), required=True)
    parser.add_argument("--egress-port", type=int, required=True)
    parser.add_argument("--declaration", type=Path, default=Path("/etc/van-browser-stream/profiles-declaration.json"))
    args = parser.parse_args()
    try:
        if not 1024 <= args.egress_port <= 65535:
            raise ValueError("profile_egress_port_unbound")
        if args.check == "flags":
            result = process_status(args.pid, pwd.getpwnam("van-browser-" + args.instance).pw_uid, args.egress_port)
        else:
            with args.declaration.open("rb") as stream:
                raw = stream.read(256 * 1024 + 1)
            if len(raw) > 256 * 1024:
                raise ValueError("profile_declaration_unbounded")
            declaration = json.loads(raw)
            selected = next(entry for entry in declaration["instances"] if entry["instance"] == args.instance)
            if selected["egress_port"] != args.egress_port:
                raise ValueError("selected_profile_proxy_port_mismatch")
            identities = {user: pwd.getpwnam(user).pw_uid for entry in declaration["instances"]
                for user in entry["users"] + [entry["egress_user"]]}
            observed = subprocess.run(["nft", "-j", "-nn", "list", "table", "inet", "van_browser_cdp"],
                check=True, capture_output=True, text=True, timeout=3)
            if len(observed.stdout) > 256 * 1024:
                raise ValueError("nft_observation_unbounded")
            result = firewall_status(json.loads(observed.stdout), declaration, identities)
    except (OSError, KeyError, TypeError, ValueError, StopIteration, subprocess.SubprocessError):
        result = {"status": "UNKNOWN", "detail": "profile_process_or_kernel_observation_unavailable"}
    print(json.dumps(result))
    return 0 if result["status"] == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
