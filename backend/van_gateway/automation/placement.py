"""Stagehand production placement and model gate (owner decisions 2026-09-29 §§1, 4, 5).

One question, one answer: *may the Stagehand semantic lane run in production from here?*

    stagehand_production_enabled(settings, *, worker_health=None) -> tuple[bool, str]

It returns ``(True, STAGEHAND_PLACEMENT_SATISFIED)`` only when every placement and model
condition below holds, and otherwise ``(False, reason)`` where ``reason`` is a stable
machine-readable code. ``False`` means **STAGEHAND = PRODUCTION_DISABLED**.

What it decides, and what it does not:

* It decides *placement* (§1): Stagehand runs in production only in the dedicated
  ``van-browser-core`` trust zone, reached across zones through the authenticated mTLS
  edge. ``van-trading-core``, ``dial-control`` and ``van-private-core`` are refused by
  name; an undeclared or unknown zone is refused too. If ``van-browser-core`` is not the
  running zone, or it is unavailable (no fresh worker health, or health that does not
  prove the zone), the answer is PRODUCTION_DISABLED. There is no fallback zone:
  provisioning Stagehand temporarily on ``van-trading-core`` is forbidden (§1).
* It decides the *model* (§4): the owner-decided pair ``anthropic`` / ``claude-sonnet-5``.
  Any other configured pair is reported, not silently accepted, and keeps Stagehand
  production-disabled until another explicit owner decision.
* It checks the runtime *version identity* (§5): the worker must report the released
  4.1.0 artifact, read from the installed package metadata (not a constant), and must
  not serve ``/act`` (§8).
* It does **not** decide governance gates (signed owner ingress §2, the health production
  gate §6, the verifier/executor blockers §§7-8). Callers AND this result with those; a
  ``True`` here is necessary, never sufficient.
* It does **not** touch the deterministic Browser Harness path or the dial-jev lane (§1,
  §9). Those continue under their own policy whatever this returns.

The Programme B router (``backend/van_gateway/browser/**``) calls this; it is kept outside
that package so placement has exactly one owner.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import threading
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

#: The only zone that may ever run production Stagehand (§1).
VAN_BROWSER_CORE = "van-browser-core"
#: Zones named by the owner as forbidden production placements for Stagehand (§1).
FORBIDDEN_STAGEHAND_ZONES = frozenset({"van-trading-core", "dial-control", "van-private-core"})

#: §4 — canonical provider/model. Not a floating "latest", not a substitute.
CANONICAL_STAGEHAND_PROVIDER = "anthropic"
CANONICAL_STAGEHAND_MODEL = "claude-sonnet-5"
#: §5 — the adopted released artifact.
STAGEHAND_RELEASE_VERSION = "4.1.0"
STAGEHAND_RELEASE_COMMIT = "cd7b230778cf92269e4cb90e80d97f5113781c51"
STAGEHAND_RELEASE_INTEGRITY = (
    "sha512-PJikMBVoaCRh6TFD7GcmeISmsMq4IwUu1BD5FOsGUVDUxrVqZomWa6W6dF+a/zu4xRZu2Z2xX1nXVMDaCuZWsw=="
)

#: The worker's /health must say its version was read from the installed package.
RUNTIME_VERSION_SOURCE = "installed-package-metadata"

PRODUCTION_DISABLED = "PRODUCTION_DISABLED"
STAGEHAND_PLACEMENT_SATISFIED = "STAGEHAND_PLACEMENT_SATISFIED"

_NUMERIC_HOST = re.compile(r"^[0-9a-fx.]+$")

#: Review I2 carried minor (probe placement2.py): ``https://localtest.me:9443`` passed, because
#: only the literal host was classified and that name resolves to 127.0.0.1. A named endpoint
#: is now resolved and every address it resolves to must be a possible cross-zone peer.
#:
#: The zone contract (deploy/van-browser-core/zone.json BC-IF-1, BC-IF-2) puts the only
#: cross-zone listener on a *private overlay address* inside the private VCN. These are the
#: private ranges such an address can be in (RFC 1918, the RFC 6598 shared space overlay
#: meshes use, and IPv6 ULA). Any other private or reserved address class (documentation,
#: benchmarking, 0/8, 240/4, ...) cannot be that listener and is refused.
OVERLAY_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = tuple(
    ipaddress.ip_network(net)
    for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "fc00::/7")
)
#: getaddrinfo has no timeout of its own; a resolution slower than this fails closed.
DNS_RESOLVE_TIMEOUT_S = 2.0

#: ``resolver(host) -> addresses`` (textual IPs). Raising, returning nothing or timing out is
#: unresolvable, which fails closed. Injected by tests so they never need the network.
Resolver = Callable[[str], Iterable[str]]


def _getaddrinfo_resolver(host: str) -> list[str]:
    """Every address ``host`` resolves to, bounded by ``DNS_RESOLVE_TIMEOUT_S``."""
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["infos"] = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except Exception as exc:  # noqa: BLE001 — any failure is unresolvable
            box["error"] = exc

    # A daemon thread, not an executor: a hung lookup must not hold interpreter shutdown.
    worker = threading.Thread(target=run, name="stagehand-placement-dns", daemon=True)
    worker.start()
    worker.join(DNS_RESOLVE_TIMEOUT_S)
    if worker.is_alive():
        raise TimeoutError(f"resolving {host!r} took longer than {DNS_RESOLVE_TIMEOUT_S}s")
    if "error" in box:
        raise box["error"]
    return [str(info[4][0]) for info in box["infos"]]


DEFAULT_RESOLVER: Resolver = _getaddrinfo_resolver


def _ip_of(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """The address a literal host denotes, including the shorthand IPv4 forms.

    ``ipaddress`` only accepts the dotted quad, but the resolver behind httpx also
    accepts ``127.1``, ``2130706433`` and ``0x7f.1`` (inet_aton), all of which reach
    loopback. Anything numeric-looking is therefore read the way the socket layer reads it.
    """
    candidate = host.split("%", 1)[0]  # an IPv6 zone id does not change the address class
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        pass
    if _NUMERIC_HOST.match(candidate) and any(ch.isdigit() for ch in candidate):
        try:
            return ipaddress.IPv4Address(socket.inet_aton(candidate))
        except (OSError, ValueError):
            return None
    return None


def _is_local_host(hostname: str | None) -> bool:
    """True when ``hostname`` cannot be a cross-zone peer: this host or the link.

    Rejects every loopback address (all of 127.0.0.0/8 and ::1, including IPv4-mapped
    forms), link-local, unspecified, ``localhost`` and any ``*.localhost`` name, each with
    or without the trailing root dot. An empty host is local too: it names no peer.
    """
    host = (hostname or "").strip().lower().strip("[]").rstrip(".")
    if not host:
        return True
    if host == "localhost" or host.endswith(".localhost") or host == "localhost.localdomain":
        return True
    ip = _ip_of(host)
    if ip is None:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    for addr in (ip, mapped) if mapped is not None else (ip,):
        if addr.is_loopback or addr.is_link_local or addr.is_unspecified:
            return True
    return False


def _address_refused(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True when ``ip`` cannot be the van-browser-core cross-zone edge (see OVERLAY_NETWORKS)."""
    mapped = getattr(ip, "ipv4_mapped", None)
    addr = mapped if mapped is not None else ip
    if addr.is_loopback or addr.is_link_local or addr.is_unspecified or addr.is_multicast:
        return True
    if any(addr in net for net in OVERLAY_NETWORKS if net.version == addr.version):
        return False
    return addr.is_private or addr.is_reserved


def _endpoint_refusal(hostname: str | None, resolver: Resolver) -> str | None:
    """``None`` when the endpoint host may be the cross-zone edge, else a refusal reason.

    A literal address is classified as written; a name is resolved and refused if it does
    not resolve, or if *any* address it resolves to is refused (a name with one loopback
    answer among several can still land on loopback).
    """
    if _is_local_host(hostname):
        return "STAGEHAND_ENDPOINT_NOT_CROSS_ZONE_MTLS"
    host = (hostname or "").strip().lower().strip("[]").rstrip(".")
    literal = _ip_of(host)
    if literal is not None:
        return "STAGEHAND_ENDPOINT_NOT_CROSS_ZONE_MTLS" if _address_refused(literal) else None
    try:
        answers = [str(a) for a in resolver(host)]
    except Exception:  # noqa: BLE001 — resolution failure, timeout included, fails closed
        return "STAGEHAND_ENDPOINT_UNRESOLVABLE"
    if not answers:
        return "STAGEHAND_ENDPOINT_UNRESOLVABLE"
    for answer in answers:
        try:
            ip = ipaddress.ip_address(answer.split("%", 1)[0])
        except ValueError:
            return "STAGEHAND_ENDPOINT_UNRESOLVABLE"
        if _address_refused(ip):
            return "STAGEHAND_ENDPOINT_NOT_CROSS_ZONE_MTLS"
    return None


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _file_present(path: str) -> bool:
    return bool(path) and Path(path).is_file()


def stagehand_production_enabled(
    settings: Any, *, worker_health: Mapping[str, Any] | None = None,
    resolver: Resolver | None = None,
) -> tuple[bool, str]:
    """Return ``(enabled, reason)`` for production Stagehand placement and model.

    ``settings`` is a ``van_gateway.config.Settings`` (duck-typed so certification tools
    can pass a namespace). ``worker_health`` is the JSON body the van-browser-core
    Stagehand worker returned from ``GET /health`` through the mTLS edge, fetched by the
    caller. ``None`` means the zone's availability was not established, which is
    PRODUCTION_DISABLED — this function never assumes a zone is up. ``resolver`` resolves
    a named endpoint (default: ``DEFAULT_RESOLVER``, getaddrinfo bounded by
    ``DNS_RESOLVE_TIMEOUT_S``); a literal address never touches it.
    """

    if not getattr(settings, "browser_enabled", False):
        return False, "BROWSER_FABRIC_DISABLED"

    zone = _norm(getattr(settings, "browser_stagehand_zone", ""))
    if not zone:
        return False, "STAGEHAND_ZONE_UNDECLARED"
    if zone in FORBIDDEN_STAGEHAND_ZONES:
        return False, f"STAGEHAND_PLACEMENT_FORBIDDEN:{zone}"
    if zone != VAN_BROWSER_CORE:
        return False, f"STAGEHAND_ZONE_NOT_VAN_BROWSER_CORE:{zone}"

    # Cross-zone access is only the authenticated mTLS edge. A loopback or plain-HTTP
    # endpoint means the worker is co-resident with the caller, i.e. not on
    # van-browser-core, or reached without authentication.
    base_url = str(getattr(settings, "browser_stagehand_base_url", "") or "")
    parts = urlsplit(base_url)
    if parts.scheme != "https":
        return False, "STAGEHAND_ENDPOINT_NOT_CROSS_ZONE_MTLS"
    refusal = _endpoint_refusal(parts.hostname, resolver or DEFAULT_RESOLVER)
    if refusal is not None:
        return False, refusal
    for field in ("browser_core_ca_file", "browser_core_client_cert_file", "browser_core_client_key_file"):
        if not _file_present(str(getattr(settings, field, "") or "")):
            return False, f"STAGEHAND_MTLS_CLIENT_IDENTITY_MISSING:{field}"

    provider = _norm(getattr(settings, "browser_stagehand_model_provider", ""))
    model = str(getattr(settings, "browser_stagehand_model_name", "") or "").strip()
    if not provider or not model:
        return False, "STAGEHAND_MODEL_UNCONFIGURED"
    if (provider, model) != (CANONICAL_STAGEHAND_PROVIDER, CANONICAL_STAGEHAND_MODEL):
        # §4: no silent downgrade and no substitution without another owner decision.
        return False, f"STAGEHAND_MODEL_NOT_OWNER_DECIDED:{provider}/{model}"

    if worker_health is None:
        return False, "VAN_BROWSER_CORE_UNAVAILABLE:health_unverified"
    if worker_health.get("ok") is not True:
        return False, "VAN_BROWSER_CORE_UNAVAILABLE:worker_not_ok"
    if _norm(worker_health.get("trust_zone")) != VAN_BROWSER_CORE:
        return False, f"STAGEHAND_RUNNING_ZONE_MISMATCH:{_norm(worker_health.get('trust_zone')) or 'unreported'}"
    # §5 / review I minor 5: the version must be the installed package's own metadata. A
    # worker that reports a constant can never mismatch, so its version proves nothing.
    if worker_health.get("runtime_version_source") != RUNTIME_VERSION_SOURCE:
        return False, "STAGEHAND_RUNTIME_VERSION_UNPROVEN"
    if str(worker_health.get("runtime_version", "")) != STAGEHAND_RELEASE_VERSION:
        return False, "STAGEHAND_RUNTIME_VERSION_MISMATCH"
    if str(worker_health.get("model_name", "")) != f"{CANONICAL_STAGEHAND_PROVIDER}/{CANONICAL_STAGEHAND_MODEL}":
        return False, "STAGEHAND_RUNTIME_MODEL_MISMATCH"
    if worker_health.get("model_key_present") is not True:
        return False, "STAGEHAND_MODEL_CREDENTIAL_UNAVAILABLE"
    # §4: the provider credential must never enter browser memory. Stagehand 4.1.0 sends
    # a `{modelName, apiKey}` model config to its in-Chromium extension service worker,
    # which then calls the provider from inside the browser. Only a worker that proves
    # the key stays out of the browser (a client-side LLM callback) may pass.
    if worker_health.get("provider_key_in_browser_memory") is not False:
        return False, "STAGEHAND_PROVIDER_KEY_ENTERS_BROWSER_MEMORY"
    if worker_health.get("direct_agent_loop") is not False or worker_health.get("model_self_selection") is not False:
        return False, "STAGEHAND_WORKER_AUTHORITY_UNBOUNDED"
    # §8 / review I minor 5: a worker that serves /act holds an actuation authority.
    if worker_health.get("act_endpoint_enabled") is not False:
        return False, "STAGEHAND_WORKER_ACTUATION_EXPOSED"

    return True, STAGEHAND_PLACEMENT_SATISFIED


def stagehand_production_state(
    settings: Any, *, worker_health: Mapping[str, Any] | None = None,
    resolver: Resolver | None = None,
) -> dict[str, Any]:
    """Projection for health/readiness surfaces: state, reason and the pin facts."""

    enabled, reason = stagehand_production_enabled(settings, worker_health=worker_health, resolver=resolver)
    revision = str(getattr(settings, "browser_stagehand_model_revision", "") or "").strip()
    return {
        "state": "PLACEMENT_SATISFIED" if enabled else PRODUCTION_DISABLED,
        "reason": reason,
        "required_zone": VAN_BROWSER_CORE,
        "forbidden_zones": sorted(FORBIDDEN_STAGEHAND_ZONES),
        "model": f"{CANONICAL_STAGEHAND_PROVIDER}/{CANONICAL_STAGEHAND_MODEL}",
        "model_revision": revision or None,
        "model_revision_status": "PINNED" if revision else "UNVERIFIED_IMMUTABLE_SNAPSHOT",
        "stagehand_version": STAGEHAND_RELEASE_VERSION,
        "stagehand_release_commit": STAGEHAND_RELEASE_COMMIT,
        "stagehand_integrity": STAGEHAND_RELEASE_INTEGRITY,
    }
