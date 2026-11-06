#!/usr/bin/env python3
"""Read UFW's ordered literal status; reject unsafe Commander admission.

This is a bounded UFW summary check, not native/OCI firewall qualification.
Unknown application profiles, matches or actions fail closed. No host changes.
"""
from __future__ import annotations
import argparse
import ipaddress
import json
import re
import sys


def admin_sources(value: str) -> set[int]:
    sources = set()
    for item in value.split(","):
        network = ipaddress.ip_network(item, strict=True)
        if network.version != 4 or network.prefixlen != 32 or network.network_address not in ipaddress.ip_network("10.0.0.0/16"):
            raise ValueError("exact_vcn_admin_sources_required")
        sources.add(int(network.network_address))
    if not sources:
        raise ValueError("exact_vcn_admin_sources_required")
    return sources


def boundaries(networks: list, version: int) -> list[int]:
    maximum = 1 << (32 if version == 4 else 128)
    points = {0, maximum}
    for network in networks:
        if network.version == version:
            points.update((int(network.network_address), int(network.broadcast_address) + 1))
    return sorted(point for point in points if point < maximum)


def evaluate(body: str, cidrs: str) -> dict:
    result = {"status": "RED", "ufw_commander_scope_verified": False,
              "native_firewall_admission_verified": False, "host_mutations": 0}
    try:
        approved = admin_sources(cidrs)
        if not re.search(r"^Status: active$", body, re.M):
            raise ValueError("ufw_active_observation_required")
        if not re.search(r"^Default: (deny|reject) \(incoming\),", body, re.M):
            raise ValueError("observed_default_incoming_deny_required")
        rules = []
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith(("Status:", "Logging:", "Default:", "New profiles:", "To", "--")):
                continue
            line = re.sub(r"^\[\s*\d+\]\s*", "", line).split(" #", 1)[0]
            columns = re.split(r"\s{2,}", line)
            if len(columns) != 3:
                raise ValueError("unsupported_ufw_summary")
            target, action, source = columns
            if action.endswith(" OUT"):
                continue
            if action not in {"ALLOW IN", "DENY IN", "REJECT IN", "LIMIT IN"}:
                raise ValueError("unsupported_ufw_action")
            ipv6 = "(v6)" in target or "(v6)" in source
            target = target.replace("(v6)", "").strip()
            source = source.replace("(v6)", "").strip()
            # An interface constraint is preserved in the ordered model. UFW's
            # status has no implicit loopback rules; it cannot certify those.
            target_parts = target.split(" on ")
            source_parts = source.split(" on ")
            if len(target_parts) > 2 or len(source_parts) > 2:
                raise ValueError("unsupported_ufw_interface")
            interface = target_parts[1] if len(target_parts) == 2 else None
            if len(source_parts) == 2:
                if interface and interface != source_parts[1]:
                    raise ValueError("unsupported_ufw_interface")
                interface = source_parts[1]
            if interface is not None and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}", interface):
                raise ValueError("unsupported_ufw_interface")
            target = target_parts[0]
            match = re.fullmatch(r"(\d+)(?::(\d+))?(?:/(tcp|udp))?", target)
            if target == "Anywhere":
                relevant = True
            elif match:
                low, high = int(match[1]), int(match[2] or match[1])
                if not 1 <= low <= high <= 65535:
                    raise ValueError("unsupported_ufw_port")
                relevant = low <= 9133 <= high and match[3] != "udp"
            else:
                raise ValueError("unsupported_ufw_target")
            if not relevant:
                continue
            network = ipaddress.ip_network(("::/0" if ipv6 else "0.0.0.0/0") if source == "Anywhere" else source, strict=False)
            if network.version != (6 if ipv6 else 4):
                raise ValueError("ambiguous_ufw_family")
            rules.append((network, interface, action))
        networks = [rule[0] for rule in rules] + [ipaddress.ip_network(f"{ipaddress.IPv4Address(value)}/32") for value in approved]
        interfaces = {rule[1] for rule in rules if rule[1]} | {"van-unlisted-iface"}
        for version in (4, 6):
            for address in boundaries(networks, version):
                for interface in interfaces:
                    first = next((action for network, iface, action in rules
                                  if network.version == version and int(network.network_address) <= address <= int(network.broadcast_address)
                                  and (iface is None or iface == interface)), "DENY IN")
                    accepted = first in {"ALLOW IN", "LIMIT IN"}
                    if accepted and (version != 4 or address not in approved):
                        raise ValueError("unapproved_commander_source_admitted")
        for address in approved:
            if not any(next((action for network, iface, action in rules
                             if network.version == 4 and int(network.network_address) <= address <= int(network.broadcast_address)
                             and (iface is None or iface == interface)), "DENY IN")
                       in {"ALLOW IN", "LIMIT IN"} for interface in interfaces):
                raise ValueError("approved_commander_source_blocked")
        result.update(status="GREEN", ufw_commander_scope_verified=True, detail="ordered UFW summary admits only selected VCN /32 Commander sources")
    except (ValueError, TypeError):
        result["detail"] = "inactive, unsupported or unsafe ordered Commander UFW summary"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-cidrs", required=True)
    args = parser.parse_args()
    body = sys.stdin.read(2 * 1024 * 1024 + 1)
    result = evaluate(body, args.admin_cidrs) if len(body.encode()) <= 2 * 1024 * 1024 else {"status": "RED", "detail": "observation_limit_exceeded"}
    print(json.dumps(result))
    return 0 if result["status"] == "GREEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
