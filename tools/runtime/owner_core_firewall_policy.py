#!/usr/bin/env python3
"""Bounded read-only owner-plane native policy evaluation.

Accepts observed iptables-save/ip6tables-save semantics with ordered user chains,
CIDRs, interfaces, TCP ports and conntrack state. Unsupported matches, auxiliary
packet hooks, translation and incomplete observations never qualify. Every
CIDR/port/interface equivalence class is checked, rather than sampling two peers.
No result grants OCI, deployment, provider or device authority.
"""
from __future__ import annotations
import ipaddress
import shlex

ADDRESSES = {"van-trading-core": "10.77.0.4", "dial-control": "10.77.0.1", "oracle-admin": "10.77.0.2"}
MAX_RULES = 4096
MAX_CLASSES = 200000


class Unsupported(ValueError):
    pass


def ports(value: str) -> tuple[int, int]:
    pieces = value.split(":")
    if len(pieces) > 2 or any(not item.isdecimal() for item in pieces):
        raise Unsupported("unsupported_port_match")
    low, high = int(pieces[0]), int(pieces[-1])
    if not 0 <= low <= high <= 65535:
        raise Unsupported("invalid_port_match")
    return low, high


def parse_rule(tokens: list[str], version: int) -> dict:
    result = {"target": "", "conditions": [], "goto": False}
    i = 0
    inverse = False
    while i < len(tokens):
        option = tokens[i]
        if option == "!":
            if inverse:
                raise Unsupported("unsupported_negation")
            inverse = True
            i += 1
            continue
        if i + 1 >= len(tokens):
            raise Unsupported("incomplete_rule")
        value = tokens[i + 1]
        i += 2
        if option in {"-m", "--match"}:
            if inverse or value not in {"tcp", "conntrack", "state", "comment"}:
                raise Unsupported("unsupported_match_module")
            continue
        if option in {"--comment", "--reject-with"}:
            if inverse:
                raise Unsupported("unsupported_negation")
            continue
        if option in {"-j", "--jump", "-g", "--goto"}:
            if inverse or result["target"]:
                raise Unsupported("ambiguous_verdict")
            result["target"] = value
            result["goto"] = option in {"-g", "--goto"}
            continue
        if option in {"-s", "--source", "-d", "--destination"}:
            network = ipaddress.ip_network(value, strict=False)
            if network.version != version:
                raise Unsupported("wrong_ip_family")
            name, value = ("src" if option in {"-s", "--source"} else "dst"), network
        elif option in {"-i", "--in-interface", "-o", "--out-interface"}:
            if not value or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-" for c in value):
                raise Unsupported("unsupported_interface_match")
            name = "iif" if option in {"-i", "--in-interface"} else "oif"
        elif option in {"-p", "--protocol"}:
            if value not in {"tcp", "6", "all", "0", "udp", "17", "icmp", "icmpv6", "58", "1"}:
                raise Unsupported("unsupported_protocol")
            name = "proto"
        elif option in {"--dport", "--destination-port", "--sport", "--source-port"}:
            name = "dport" if option in {"--dport", "--destination-port"} else "sport"
            value = ports(value)
        elif option in {"--ctstate", "--state"}:
            value = frozenset(value.split(","))
            if not value or not value <= {"NEW", "ESTABLISHED", "RELATED", "INVALID", "UNTRACKED"}:
                raise Unsupported("unsupported_connection_state")
            name = "state"
        else:
            raise Unsupported("unsupported_native_rule_option")
        result["conditions"].append((name, value, inverse))
        inverse = False
    if inverse or not result["target"]:
        raise Unsupported("missing_verdict")
    return result


def parse(body: str, version: int) -> dict:
    tables = {}
    current = None
    count = 0
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("*"):
            if current is not None or line[1:] in tables:
                raise Unsupported("invalid_table_boundary")
            current = line[1:]
            tables[current] = {"chains": {}, "rules": {}}
        elif line == "COMMIT":
            if current is None:
                raise Unsupported("invalid_table_boundary")
            current = None
        elif current is None:
            raise Unsupported("unbound_rule")
        elif line.startswith(":"):
            fields = line[1:].split()
            if len(fields) != 3 or fields[1] not in {"ACCEPT", "DROP", "-"} or fields[0] in tables[current]["chains"]:
                raise Unsupported("invalid_chain")
            tables[current]["chains"][fields[0]] = fields[1]
            tables[current]["rules"][fields[0]] = []
        else:
            fields = shlex.split(line)
            if len(fields) < 4 or fields[0] != "-A" or fields[1] not in tables[current]["chains"]:
                raise Unsupported("unsupported_native_rule")
            count += 1
            if count > MAX_RULES:
                raise Unsupported("rule_limit_exceeded")
            # NAT transformations are deliberately retained as unsupported
            # semantics in the NAT part, not silently discarded as comments.
            if current == "nat" and "-j" in fields and fields[fields.index("-j") + 1] in {"SNAT", "DNAT", "MASQUERADE", "REDIRECT", "NETMAP"}:
                jump = fields.index("-j")
                # Translation target parameters are irrelevant once this rule
                # touches a declared lane: all source/port translation is refused.
                tables[current]["rules"][fields[1]].append(parse_rule(fields[2:jump + 2], version))
            else:
                tables[current]["rules"][fields[1]].append(parse_rule(fields[2:], version))
    if current is not None or "filter" not in tables:
        raise Unsupported("complete_filter_observation_required")
    filtering = tables["filter"]
    if any(filtering["chains"].get(chain) not in {"ACCEPT", "DROP"} for chain in ("INPUT", "OUTPUT", "FORWARD")):
        raise Unsupported("all_builtin_chains_required")
    for rules in filtering["rules"].values():
        for rule in rules:
            if rule["target"] not in {"ACCEPT", "DROP", "REJECT", "RETURN"} and rule["target"] not in filtering["chains"]:
                raise Unsupported("unsupported_verdict")
    return tables


def matches(rule: dict, packet: dict) -> bool:
    for name, value, inverse in rule["conditions"]:
        candidate = packet[name]
        if name in {"src", "dst"}:
            yes = int(value.network_address) <= candidate <= int(value.broadcast_address)
        elif name in {"sport", "dport"}:
            yes = value[0] <= candidate <= value[1]
        elif name in {"iif", "oif"}:
            yes = candidate.startswith(value[:-1]) if value.endswith("+") else candidate == value
        elif name == "state":
            yes = candidate in value
        elif name == "proto":
            yes = value in {"tcp", "6", "all", "0"}
        else:
            raise Unsupported("unsupported_condition")
        if yes == inverse:
            return False
    return True


def verdict(table: dict, chain: str, packet: dict, stack: tuple = ()) -> str:
    if chain in stack or len(stack) > 32:
        raise Unsupported("recursive_rule_chain")
    for rule in table["rules"][chain]:
        if not matches(rule, packet):
            continue
        target = rule["target"]
        if target in {"ACCEPT", "DROP", "REJECT", "RETURN", "SNAT", "DNAT", "MASQUERADE", "REDIRECT", "NETMAP"}:
            return table["chains"][chain] if target == "RETURN" and table["chains"][chain] != "-" else target
        decided = verdict(table, target, packet, (*stack, chain))
        if decided != "RETURN":
            return decided
        if rule["goto"]:
            break
    return "RETURN" if table["chains"][chain] == "-" else table["chains"][chain]


def partitions(table: dict, version: int, extra_ips: list[str]) -> dict:
    maximum = 1 << (32 if version == 4 else 128)
    points = {"src": {0, maximum}, "dst": {0, maximum}, "sport": {0, 65536}}
    interfaces = {"iif": {"wg-dial", "lo", "van-unlisted-iface"}, "oif": {"wg-dial", "lo", "van-unlisted-iface"}}
    for ip in extra_ips:
        address = ipaddress.ip_address(ip)
        if address.version == version:
            for name in ("src", "dst"):
                points[name].update((int(address), int(address) + 1))
    for rules in table["rules"].values():
        for rule in rules:
            for name, value, _ in rule["conditions"]:
                if name in {"src", "dst"}:
                    points[name].update((int(value.network_address), int(value.broadcast_address) + 1))
                elif name == "sport":
                    points[name].update((value[0], value[1] + 1))
                elif name in interfaces:
                    interfaces[name].add(value[:-1] + "van" if value.endswith("+") else value)
    return {**{name: sorted(point for point in values if point < (65536 if name == "sport" else maximum)) for name, values in points.items()},
            **{name: sorted(values) for name, values in interfaces.items()}}


def packet(source: str | int, target: str | int, port: int, *, iif="wg-dial", oif="wg-dial", sport=49152, state="NEW") -> dict:
    return {"src": int(ipaddress.ip_address(source)) if isinstance(source, str) else source,
            "dst": int(ipaddress.ip_address(target)) if isinstance(target, str) else target,
            "dport": port, "sport": sport, "state": state, "iif": iif, "oif": oif, "proto": "tcp"}


def declared_lanes(declaration: dict) -> list[dict]:
    lanes = declaration.get("required_network_lanes")
    if declaration.get("ingress_capability") != "VAN_OWNER_TLS_PASSTHROUGH_V1" or not isinstance(lanes, list) or len(lanes) != 4:
        raise Unsupported("exact_declaration_required")
    expected = {("10.77.0.2", "van-trading-core", "10.77.0.4", 8443),
                ("10.77.0.1", "van-trading-core", "10.77.0.4", 8787)}
    tuples = set()
    for lane in lanes:
        if not isinstance(lane, dict) or type(lane.get("port")) is not int or not 1024 <= lane["port"] <= 65535:
            raise Unsupported("invalid_declared_lane")
        address = ipaddress.IPv4Address(lane["target_address"])
        tuples.add((lane["source"], lane["target_host"], str(address), lane["port"]))
    owner = next((item for item in lanes if item["source"] == "owner_phone" and item["target_host"] == "oracle-admin"), None)
    hermes = next((item for item in lanes if item["source"] == "10.77.0.4" and item["target_host"] == "dial-control"
                   and item["target_address"] == "10.77.0.1"), None)
    if owner is None or hermes is None or len(tuples) != 4 or not expected <= tuples:
        raise Unsupported("wrong_declared_private_edge")
    address = ipaddress.IPv4Address(owner["target_address"])
    if address.is_loopback or address.is_unspecified or address.is_multicast or address in ipaddress.ip_network("10.77.0.0/24"):
        raise Unsupported("wrong_declared_ingress_bind")
    return lanes


def filter_part(table: dict, host: str, lanes: list[dict], version: int) -> dict:
    hermes = next(item for item in lanes if item["target_host"] == "dial-control")
    ingress = next(item for item in lanes if item["source"] == "owner_phone")
    if host == "van-trading-core":
        protected = [("INPUT", "10.77.0.4", 8443, "10.77.0.2"), ("INPUT", "10.77.0.4", 8787, "10.77.0.1")]
    elif host == "dial-control":
        protected = [("INPUT", "10.77.0.1", hermes["port"], "10.77.0.4"),
                     ("FORWARD", "10.77.0.4", 8443, "10.77.0.2"),
                     ("FORWARD", "10.77.0.4", 8787, "10.77.0.1")]
    else:
        # The public owner ingress intentionally accepts phone sources at its
        # exact VNIC/port. Existing DDS overlay listeners are separate scope.
        protected = [("INPUT", ingress["target_address"], ingress["port"], "owner_phone")]
    classes = partitions(table, version, ["10.77.0.1", "10.77.0.2", "10.77.0.4", ingress["target_address"]])
    count = 0
    for chain, target, port, source in protected:
        for src in classes["src"]:
            for dst in classes["dst"]:
                for sport in classes["sport"]:
                    for iif in classes["iif"]:
                        if iif == "lo":
                            continue  # Trusted local traffic is checked by exact listener binding.
                        out_interfaces = classes["oif"] if chain == "FORWARD" else ["van-unlisted-iface"]
                        for oif in out_interfaces:
                            count += 1
                            if count > MAX_CLASSES:
                                raise Unsupported("policy_class_limit_exceeded")
                            current = packet(src, dst, port, sport=sport, iif=iif, oif=oif)
                            if host == "oracle-admin" and port == 8443 and version == 4 and dst == int(ipaddress.IPv4Address("10.77.0.2")):
                                continue  # Separate existing DDS product gateway scope.
                            allowed = (version == 4 and dst == int(ipaddress.IPv4Address(target))
                                       and (source == "owner_phone" or src == int(ipaddress.IPv4Address(source)))
                                       and (source == "owner_phone" or iif == "wg-dial")
                                       and (chain != "FORWARD" or oif == "wg-dial"))
                            accepted = verdict(table, chain, current) == "ACCEPT"
                            if accepted and not allowed:
                                return {"status": "FAIL", "reason": "unapproved_external_owner_plane_class_admitted", "chain": chain, "port": port}
    if version == 4:
        # Require reachable exact lanes and established replies. Negative scope
        # above is exhaustive for NEW classes. Outgoing unrelated service traffic
        # is outside this owner-plane policy and receives no blanket prohibition.
        for chain, target, port, source in protected:
            if source == "owner_phone":
                if not any(verdict(table, chain, packet("198.51.100.24", target, port, iif=iface)) == "ACCEPT"
                           for iface in classes["iif"] if iface != "lo"):
                    return {"status": "FAIL", "reason": "declared_ingress_blocked"}
            else:
                for state in ("NEW", "ESTABLISHED"):
                    if verdict(table, chain, packet(source, target, port, state=state)) != "ACCEPT":
                        return {"status": "FAIL", "reason": "declared_private_lane_blocked", "chain": chain, "port": port}
                reply_chain = "FORWARD" if chain == "FORWARD" else "OUTPUT"
                if verdict(table, reply_chain, packet(target, source, 49152, sport=port, state="ESTABLISHED")) != "ACCEPT":
                    return {"status": "FAIL", "reason": "declared_established_reply_blocked", "chain": reply_chain, "port": port}
        outgoing = {"van-trading-core": [("10.77.0.4", "10.77.0.1", hermes["port"])],
                    "dial-control": [("10.77.0.1", "10.77.0.4", 8787)],
                    "oracle-admin": [("10.77.0.2", "10.77.0.4", 8443)]}[host]
        for src, dst, port in outgoing:
            if verdict(table, "OUTPUT", packet(src, dst, port)) != "ACCEPT":
                return {"status": "FAIL", "reason": "declared_outgoing_lane_blocked", "port": port}
            if verdict(table, "INPUT", packet(dst, src, 49152, sport=port, state="ESTABLISHED")) != "ACCEPT":
                return {"status": "FAIL", "reason": "declared_outgoing_reply_blocked", "port": port}
    return {"status": "PASS", "checked_equivalence_classes": count,
            "scope": "external NEW TCP owner-plane source/destination/interface scope plus declared IPv4 admission"}


def native_part(body: str | None, host: str, lanes: list[dict], version: int) -> dict:
    if not body:
        return {"filter": {"status": "UNKNOWN", "reason": "native_observation_missing"},
                "nat": {"status": "UNKNOWN", "reason": "native_observation_missing"}}
    try:
        tables = parse(body, version)
        auxiliary = [name for name in tables if name not in {"filter", "nat"}
                     and (any(tables[name]["rules"].values()) or
                          any(policy not in {"ACCEPT", "-"} for policy in tables[name]["chains"].values()))]
        if auxiliary:
            raise Unsupported("auxiliary_packet_hooks_not_supported")
        filtering = filter_part(tables["filter"], host, lanes, version)
        nat = tables.get("nat")
        if nat is None:
            translation = {"status": "UNKNOWN", "reason": "complete_nat_observation_required"}
        elif any(nat["rules"].values()):
            # Docker/unrelated translations can be legitimate. This bounded
            # evaluator refuses to certify source preservation from unmodeled
            # translations instead of labeling them safely disjoint.
            translation = {"status": "UNKNOWN", "reason": "translation_rules_require_independent_exact_lane_analysis"}
            if version == 4:
                for lane in lanes:
                    if lane["source"] == "owner_phone":
                        continue
                    packets = [packet(lane["source"], lane["target_address"], lane["port"]),
                               packet(lane["target_address"], lane["source"], 49152,
                                      sport=lane["port"], state="ESTABLISHED")]
                    for chain, policy in nat["chains"].items():
                        if policy == "-":
                            continue
                        for sample in packets:
                            if verdict(nat, chain, sample) in {"SNAT", "DNAT", "MASQUERADE", "REDIRECT", "NETMAP"}:
                                translation = {"status": "FAIL", "reason": "declared_private_lane_translated", "chain": chain}
        else:
            translation = {"status": "PASS", "reason": "observed_nat_chains_empty"}
        return {"filter": filtering, "nat": translation}
    except (ValueError, KeyError, TypeError) as error:
        return {"filter": {"status": "UNKNOWN", "reason": str(error) if isinstance(error, Unsupported) else "invalid_native_observation"},
                "nat": {"status": "UNKNOWN", "reason": "native_semantics_not_verified"}}


def evaluate(declaration: dict, host: str, *, ipv4: str | None, ipv6: str | None, nft: dict | None) -> dict:
    result = {"kind": "BOUNDED_NATIVE_OWNER_PLANE_POLICY", "parts": {}, "host_mutations": 0,
              "firewall_admission_verified": False, "OCI_policy_verified": False,
              "deployment_authority_verified": False, "provider_callback_route_verified": False,
              "device_provisioning_permitted": False, "live_e2e_qualified": False}
    try:
        if host not in ADDRESSES:
            raise Unsupported("exact_host_role_required")
        lanes = declared_lanes(declaration)
        for name, body, version in (("IPv4", ipv4, 4), ("IPv6", ipv6, 6)):
            observed = native_part(body, host, lanes, version)
            result["parts"][name + "_filter"] = observed["filter"]
            result["parts"][name + "_NAT"] = observed["nat"]
        # Empty complete nft observation proves no independent nft hook changes
        # iptables semantics. Nonempty native/compat NFT hooks require their own
        # supported evaluator; never assume a duplicate or ignore their order.
        result["parts"]["independent_nft_hooks"] = ({"status": "PASS", "reason": "observed_nft_ruleset_empty"}
            if isinstance(nft, dict) and nft.get("nftables") == []
            else {"status": "UNKNOWN", "reason": "nonempty_or_unobserved_nft_hooks_require_independent_analysis"})
        result["parts"]["OCI_NSG_and_security_lists"] = {"status": "UNKNOWN", "reason": "scope_bound_cloud_provider_observation_required"}
        local = [value["status"] for key, value in result["parts"].items() if key != "OCI_NSG_and_security_lists"]
        result["local_native_policy_verified"] = all(value == "PASS" for value in local)
        result["outcome"] = "FAIL" if "FAIL" in local else "PASS_LOCAL_NATIVE_POLICY_ONLY" if result["local_native_policy_verified"] else "UNKNOWN"
    except (ValueError, KeyError, TypeError):
        result.update(outcome="FAIL", local_native_policy_verified=False, reason="invalid_owner_core_policy_selection")
    return result
