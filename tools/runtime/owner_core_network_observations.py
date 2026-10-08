#!/usr/bin/env python3
"""Read bounded local network observations for an admitted owner-core recipe.

This collector never changes interfaces, firewall rules or services and reads no
WireGuard private/preshared keys. Supported native policy is evaluated in memory;
OCI, governed ingress, provider routes and phone qualification remain separate.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import shutil
import selectors
import subprocess
import time

try:
    from . import owner_core_firewall_policy as policy_source
    from .owner_core_firewall_policy import declared_lanes, evaluate
except ImportError:
    import owner_core_firewall_policy as policy_source
    from owner_core_firewall_policy import declared_lanes, evaluate

HOST_ADDRESSES = {"van-trading-core": "10.77.0.4", "dial-control": "10.77.0.1", "oracle-admin": "10.77.0.2"}
MAX_BYTES = 2 * 1024 * 1024


def probe(program: str, args: list[str]) -> dict:
    executable = shutil.which(program)
    result = {"program": program, "args": args, "outcome": "BLOCKED"}
    if executable is None:
        result["reason"] = "binary_unavailable"
        return result
    try:
        # Bound the live read, not merely its size after capture_output has
        # allocated it. Stderr is discarded and never becomes diagnostic data.
        reply = subprocess.Popen([executable, *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        body = bytearray()
        deadline = time.monotonic() + 10
        with selectors.DefaultSelector() as ready:
            ready.register(reply.stdout, selectors.EVENT_READ)
            while ready.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(program, 10)
                for key, _ in ready.select(remaining):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        ready.unregister(key.fileobj)
                        continue
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        result["reason"] = "observation_limit_exceeded"
                        reply.kill()
                        reply.wait(timeout=1)
                        return result
        return_code = reply.wait(timeout=max(0.01, deadline - time.monotonic()))
        if return_code:
            result.update(reason="observation_refused", exit_code=return_code)
        else:
            result.update(outcome="OBSERVED", body=body.decode("utf-8"),
                          body_sha256=hashlib.sha256(body).hexdigest(),
                          binary_sha256=hashlib.sha256(Path(executable).read_bytes()).hexdigest())
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
        result["reason"] = type(error).__name__
    finally:
        if "reply" in locals():
            if reply.poll() is None:
                reply.kill()
                reply.wait(timeout=1)
            if reply.stdout is not None:
                reply.stdout.close()
    return result


def listeners(body: str) -> set[tuple[str, int]]:
    pairs = set()
    for line in body.splitlines():
        fields = line.split()
        if len(fields) < 5:
            raise ValueError("listener_observation_invalid")
        address, separator, port = fields[3].rpartition(":")
        if not separator or not port.isdecimal():
            raise ValueError("listener_observation_invalid")
        pairs.add((address.strip("[]"), int(port)))
    return pairs


def private_listener_checks(host: str, lanes: list[dict], pairs: set[tuple[str, int]]) -> dict:
    if host == "van-trading-core":
        allowed = {("127.0.0.1", 8787), ("10.77.0.4", 8787), ("10.77.0.4", 8443)}
        ports = {8787, 8443}
        required = allowed
    elif host == "dial-control":
        lane = next(item for item in lanes if item["target_host"] == host and item["source"] == "10.77.0.4")
        allowed = required = {("10.77.0.1", lane["port"])}
        ports = {lane["port"]}
    else:
        lane = next(item for item in lanes if item["target_host"] == host and item["source"] == "owner_phone")
        required = {(lane["target_address"], lane["port"])}
        # Preserve the separately governed existing overlay DDS listener if the
        # new VAN ingress uses the same numeric port on its dedicated VNIC.
        allowed = required | {("10.77.0.2", 8443)}
        ports = {lane["port"]}
    relevant = {pair for pair in pairs if pair[1] in ports}
    return {"required_exact_listeners_present": required <= pairs,
            "protected_listener_bindings_narrow": bool(relevant) and relevant <= allowed}


def collect(declaration: Path, expected_declaration_sha: str, host: str, *, run=probe) -> dict:
    report = {"kind": "READ_ONLY_LOCAL_NETWORK_OBSERVATIONS", "host_role": host, "checks": {}, "observations": [],
              "host_mutations": 0, "firewall_admission_verified": False, "OCI_policy_verified": False,
              "governed_ingress_verified": False, "owner_signed_apk_verified": False,
              "device_provisioning_permitted": False, "live_e2e_qualified": False,
              "collector_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "policy_source_sha256": hashlib.sha256(Path(policy_source.__file__).read_bytes()).hexdigest()}
    try:
        body = declaration.read_bytes()
        if hashlib.sha256(body).hexdigest() != expected_declaration_sha:
            raise ValueError("selected_declaration_mismatch")
        selected = json.loads(body)
        lanes = declared_lanes(selected)
        if host not in HOST_ADDRESSES:
            raise ValueError("exact_owner_core_declaration_required")
        report["declaration_sha256"] = expected_declaration_sha
        report["checks"]["selected_host_identity"] = platform.node() == host
        if not report["checks"]["selected_host_identity"]:
            report["outcome"] = "BLOCKED"
            return report
        observed = {}
        plans = [("overlay_addresses", "ip", ["-j", "address", "show", "dev", "wg-dial"]),
                 ("listeners", "ss", ["-H", "-ltn"]),
                 ("overlay_handshakes", "wg", ["show", "wg-dial", "latest-handshakes"]),
                 ("overlay_allowed_ips", "wg", ["show", "wg-dial", "allowed-ips"]),
                 ("nft_ruleset", "nft", ["-j", "list", "ruleset"]),
                 ("iptables_ruleset", "iptables-save", []),
                 ("ip6tables_ruleset", "ip6tables-save", [])]
        outgoing_peers = {"van-trading-core": ["10.77.0.1"], "dial-control": ["10.77.0.4", "10.77.0.2"],
                          "oracle-admin": ["10.77.0.4"]}[host]
        plans += [("route_to_" + peer, "ip", ["-j", "route", "get", peer]) for peer in outgoing_peers]
        for name, program, args in plans:
            observation = run(program, args)
            # Raw rules and peer identifiers remain in memory. No stderr, process
            # listings or WireGuard private-key output enter the receipt.
            observed[name] = observation
            report["observations"].append({"name": name, **{key: value for key, value in observation.items() if key != "body"}})
        addresses = json.loads(observed["overlay_addresses"].get("body", "[]"))
        report["checks"]["selected_private_overlay_address"] = any(
            item.get("local") == HOST_ADDRESSES[host] for entry in addresses for item in entry.get("addr_info", []))
        if observed["listeners"]["outcome"] == "OBSERVED":
            report["checks"].update(private_listener_checks(host, lanes, listeners(observed["listeners"]["body"])))
        else:
            report["checks"]["listener_observation_available"] = False
        timestamps = []
        if observed["overlay_handshakes"]["outcome"] == "OBSERVED":
            for line in observed["overlay_handshakes"]["body"].splitlines():
                fields = line.split()
                if len(fields) != 2 or not fields[1].isdecimal():
                    raise ValueError("invalid_handshake_observation")
                timestamps.append(int(fields[1]))
        report["checks"]["at_least_one_fresh_overlay_handshake"] = any(0 <= time.time() - value <= 180 for value in timestamps)
        for peer in outgoing_peers:
            route = observed["route_to_" + peer]
            entries = json.loads(route.get("body", "[]"))
            report["checks"]["private_route_to_" + peer] = route["outcome"] == "OBSERVED" and len(entries) == 1 and (
                entries[0].get("dev") == "wg-dial" and entries[0].get("prefsrc") == HOST_ADDRESSES[host])
        report["checks"]["live_firewall_ruleset_observed"] = any(
            observed[name]["outcome"] == "OBSERVED" and bool(observed[name].get("body", "").strip())
            for name in ("nft_ruleset", "iptables_ruleset"))
        native_nft = observed["nft_ruleset"]
        native = evaluate(selected, host,
                          ipv4=observed["iptables_ruleset"].get("body"),
                          ipv6=observed["ip6tables_ruleset"].get("body"),
                          nft=json.loads(native_nft["body"]) if native_nft["outcome"] == "OBSERVED" else None)
        report["native_policy"] = native
        report["checks"]["no_confirmed_native_policy_violation"] = native["outcome"] != "FAIL"
        report["outcome"] = ("PASS_LOCAL_NETWORK_POLICY_ONLY" if native["local_native_policy_verified"] else
                             "LOCAL_OBSERVATIONS_COMPLETE_POLICY_UNVERIFIED") if all(report["checks"].values()) else "BLOCKED"
        report["pending_policy_checks"] = ["exact_overlay_peer_identity_and_AllowedIPs", "OCI_VNIC_security_lists_and_NSGs",
                                           "governed_receipt_scope_and_expiry", "actual_provider_callback_route_bindings"]
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        report.update(outcome="BLOCKED", reason=type(error).__name__)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--declaration", type=Path, required=True)
    parser.add_argument("--expected-declaration-sha256", required=True)
    parser.add_argument("--host-role", choices=sorted(HOST_ADDRESSES), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = collect(args.declaration, args.expected_declaration_sha256, args.host_role)
    if args.out.exists():
        parser.error("new receipt path required; existing observations are retained")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    args.out.chmod(0o600)
    print(json.dumps(report, indent=2))
    return 0 if report["outcome"] == "PASS_LOCAL_NETWORK_POLICY_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
