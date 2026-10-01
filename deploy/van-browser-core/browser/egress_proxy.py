#!/usr/bin/env python3
"""van-browser-core egress proxy (owner answer 2026-09-30 after review I7, "Egress proxy (Recommended)").

Every request the Harness-owned Chromium makes leaves the host through this process. It runs
as its own unit and its own user (``van-browser-egress``); the zone firewall
(``deploy/van-browser-core/firewall/van-browser-core.nft``) drops every direct TCP connection
and every UDP datagram from the browser user except loopback and DNS to the configured
resolver, so the proxy cannot be bypassed from a page.

Why it exists (review I7): a WebSocket handshake reaches the server whatever CDP Fetch and
``Network.setBlockedURLs`` do, and writes issued after an action's guard window are not
covered by the in-browser guard. The proxy enforces the task's admitted effects for as long as
the task's policy is in force, not only while one action runs.

Design: TLS interception with a zone-local CA (the alternative, a CONNECT host allowlist, was
evaluated and cannot refuse ``wss://<in-scope host>/ws-pay``; see
``docs/project-state/VAN_BROWSER_CORE_MIGRATION_20260929.md`` §Egress proxy):

* one loopback listener per browser profile alias (``VAN_EGRESS_PORT_RANGE``). Chromium is
  launched with ``--proxy-server`` pointing at its alias's listener and
  ``--proxy-bypass-list=<-loopback>`` (loopback goes through the proxy too);
* the policy for an alias (task scope + mutating flag) arrives only over the control socket
  (a Unix socket, never reachable from a page) and only with the gateway's effect MAC
  (``van-harness-effect/1``, the Harness lease-fence key) over the lease fence, the task id,
  the flag and the scope digest. The proxy verifies the MAC itself; the Harness relays it;
* no policy, an expired policy or a stale lease generation: every request is refused;
* the Harness revokes a lease's policy (``revoke``, unit G13, MAC ``van-egress-revoke/1``) at
  the lease's start (older leases' policies), at its end and when its network guard froze the
  page; a finally revoked lease's policy is never installed again;
* ``CONNECT`` is allowed only to a host:port that is an origin of the task scope. Inside the
  tunnel TLS is terminated with a per-host certificate minted by the zone-local CA over one
  leaf key; Chromium trusts it only through ``--ignore-certificate-errors-spki-list`` naming
  that leaf key (no system or profile trust store is changed). Upstream TLS is verified
  normally against the system trust store;
* each decrypted (or plain-HTTP) request: its origin must be a scope origin; ``GET``/``HEAD``/``OPTIONS``
  without a body pass; any other method, any request body, any ``Upgrade: websocket`` is
  refused unless the task is admitted as mutating *and* the URL is inside the task scope
  (the shared URL scope rule below, ``WRITE``); any other ``Upgrade`` (including a list
  naming ``websocket`` among others) is refused. After an admitted handshake the client's
  later bytes are relayed only once the upstream answers ``101`` naming ``websocket``;
  otherwise that one response is all the connection carries (review I9 MAJOR-1);
* upstream addresses that are not globally routable (loopback, private, link-local...) are
  refused, so an in-scope name cannot be pointed at the zone's own loopback services. The one
  exception (unit G14, owner answer "In-zone canary origin"): the guard canary's own
  ``*.internal`` origin, at its pinned private overlay address and port, TLS-verified against
  its pinned certificate, only for the canary lease qualify.sh armed (see "guard canary"
  below). A task scope that names any ``*.internal`` host is refused at policy install;
* one request per connection; a refusal is ``403`` with ``X-Van-Egress-Refused: <code>``
  from a closed vocabulary. The decision log holds alias, method, origin and code: never a
  path, query, header or body.

Private keys (the CA key and the leaf key) are generated here, in the unit's state directory
(mode 0700, owner ``van-browser-egress``, files 0400), on first start. They are never
copied
off the host, never readable by the browser user and never in the repository. Only the leaf
key's SPKI hash (public) is handed to the Harness.

Standard library plus the ``openssl`` command line (already required by the zone's PKI
script); no new Python dependency.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import signal
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SERVICE_VERSION = "van-browser-egress-proxy/1"
TRUST_ZONE = os.getenv("VAN_TRUST_ZONE", "")
CONTROL_SOCKET = os.getenv("VAN_EGRESS_CONTROL_SOCKET", "/run/van-browser-egress/control.sock")
STATE_DIR = Path(os.getenv("VAN_EGRESS_STATE_DIR", "/var/lib/van-browser-egress"))
FENCE_KEY_FILE = os.getenv("VAN_EGRESS_FENCE_KEY_FILE", "")
DECISION_LOG = os.getenv("VAN_EGRESS_DECISION_LOG", "")
PORT_RANGE = os.getenv("VAN_EGRESS_PORT_RANGE", "9150-9199")
POLICY_TTL_SECONDS = float(os.getenv("VAN_EGRESS_POLICY_TTL_SECONDS", "600"))
#: The model-provider tunnel for the Stagehand worker (CONNECT only, fixed host:port list, no
#: interception). Empty: no service listener.
SERVICE_PORT = int(os.getenv("VAN_EGRESS_SERVICE_PORT", "9149"))
SERVICE_ALLOW = os.getenv("VAN_EGRESS_SERVICE_ALLOW", "")
OPENSSL = os.getenv("VAN_EGRESS_OPENSSL", "/usr/bin/openssl")
#: Unit G14 (owner answer 2026-09-30 after unit G13, "In-zone canary origin (Recommended)"):
#: the guard canary's origin on the zone's private overlay, the overlay address it is served
#: from and its certificate (pinned: the only trust anchor for that one upstream). Empty
#: origin and address: no canary exception exists.
CANARY_ORIGIN = os.getenv("VAN_BROWSER_CANARY_ORIGIN", "")
CANARY_ADDRESS = os.getenv("VAN_BROWSER_CANARY_ADDRESS", "")
CANARY_CERT = os.getenv("VAN_BROWSER_CANARY_CERT", "")
#: Development/test only; refused when a trust zone is configured (see ``_test_overrides``).
TEST_RESOLVE = os.getenv("VAN_EGRESS_TEST_RESOLVE", "")
TEST_UPSTREAM_CAFILE = os.getenv("VAN_EGRESS_TEST_UPSTREAM_CAFILE", "")

LOOPBACK = "127.0.0.1"
MAX_HEAD_BYTES = 65536
MAX_CONTROL_BYTES = 262144
MAX_BODY_BYTES = 16 * 1024 * 1024
IO_TIMEOUT_SECONDS = 30.0
#: Review I8 MINOR-7: OPTIONS (no body) is a read, as the in-browser guard treats it (a CORS
#: preflight must reach an in-scope origin for the read that follows it to work).
READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
PROFILE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
TOKEN_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
#: Review I8 MAJOR-3: no CR, LF or NUL anywhere in a request line or header line; a request
#: target of visible ASCII only; header values without control characters (HTAB allowed).
BAD_LINE_CHARS = re.compile(r"[\r\n\x00]")
TARGET_RE = re.compile(r"^[\x21-\x7e]+$")
HEADER_VALUE_BAD = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")
#: Review I8 MAJOR-3: the uid that may use the per-alias listeners (the browser user) and the
#: uid that may use the service tunnel (the Stagehand user). Loopback TCP is open to every
#: local user; the proxy asks the kernel who owns the client socket and refuses anyone else.
#: Required in a trust zone.
CLIENT_UID = os.getenv("VAN_EGRESS_CLIENT_UID", "")
SERVICE_CLIENT_UID = os.getenv("VAN_EGRESS_SERVICE_CLIENT_UID", "")
HOP_BY_HOP = frozenset({"connection", "proxy-connection", "keep-alive", "proxy-authorization",
                        "proxy-authenticate", "te", "trailer", "transfer-encoding", "upgrade"})
EFFECT_MAC_CONTEXT = "van-harness-effect/1"
MIN_KEY_BYTES = 32
STATE_SCHEMA = "van-egress-policy-state/1"

#: Closed vocabulary of refusals (``X-Van-Egress-Refused`` and the decision log).
REFUSALS = frozenset({
    "EGRESS_POLICY_UNKNOWN", "EGRESS_CONNECT_OUT_OF_SCOPE", "EGRESS_ORIGIN_OUT_OF_SCOPE",
    "EGRESS_HOST_MISMATCH", "EGRESS_WEBSOCKET_REFUSED", "EGRESS_UPGRADE_REFUSED",
    "EGRESS_WRITE_REFUSED", "EGRESS_WRITE_OUT_OF_SCOPE", "EGRESS_REQUEST_INVALID",
    "EGRESS_UPSTREAM_ADDRESS_REFUSED", "EGRESS_UPSTREAM_UNAVAILABLE", "EGRESS_SERVICE_OUT_OF_ALLOWLIST",
    "EGRESS_CLIENT_REFUSED",
})


# --- VAN shared URL scope rule: begin (review I6 M3) ---
# Byte-identical in backend/van_gateway/browser/task_scope.py and in the Harness helpers
# (deploy/van-browser-core/browser/harness_service.py VAN_HELPERS_PY): tests/contracts
# pins that, and both sides run backend/tests/fixtures/task_scope/url_vectors.v1.json.
# A URL is parsed the way the WHATWG URL parser parses an http(s) URL (the parser the
# browser uses), so the check sees the page the browser will load: tab/newline removed,
# C0/space trimmed, scheme and host lower-cased, host percent-decoded, a trailing host dot
# dropped, the default port dropped, userinfo ignored, backslash read as slash, %2E read as
# "." (as Chromium does), and dot segments (".", "..") removed. Anything the rule does
# not model exactly (IPv6, non-ASCII hosts, other than two slashes after the scheme) is
# not parsed: it is out of scope (fail closed). A path whose segment percent-decodes to a
# slash, a backslash, a NUL or a dot segment is ambiguous (a server may decode it before
# resolving): also out of scope.
import re as _vs_re
from urllib.parse import unquote as _vs_unquote

_VS_TRIM = "".join(chr(_c) for _c in range(0x21))
_VS_DOT = (".", "%2e")
_VS_DOTDOT = ("..", ".%2e", "%2e.", "%2e%2e")
_VS_PATH_ENCODE = frozenset(' "<>`{}')
_VS_SCHEME = _vs_re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*):")
_VS_HOST = _vs_re.compile(r"[a-z0-9\-]+(?:\.[a-z0-9\-]+)*")


def _vs_path(path):
    path = path.replace("\\", "/")
    if not path.startswith("/"):
        path = "/" + path
    encoded = []
    for ch in path:
        code = ord(ch)
        if code < 0x20 or code == 0x7F or ch in _VS_PATH_ENCODE:
            encoded.append("%%%02X" % code)
        elif code > 0x7E:
            encoded.extend("%%%02X" % b for b in ch.encode("utf-8"))
        else:
            encoded.append(ch)
    # Chromium (the browser the Harness drives) also decodes %2E to "." anywhere in a path
    # (checked against it in backend/tests/test_browser_review_i6_scope.py).
    segments = _vs_re.sub(r"%2[eE]", ".", "".join(encoded)).split("/")[1:]
    out = []
    for i, seg in enumerate(segments):
        last = i == len(segments) - 1
        low = seg.lower()
        if low in _VS_DOTDOT:
            if out:
                out.pop()
            if last:
                out.append("")
        elif low in _VS_DOT:
            if last:
                out.append("")
        else:
            out.append(seg)
    return "/" + "/".join(out)


def _vs_authority(scheme, rest):
    end = len(rest)
    for i, ch in enumerate(rest):
        if ch in "/\\?#":
            end = i
            break
    hostport, tail = rest[:end].rsplit("@", 1)[-1], rest[end:]
    if hostport.startswith("["):
        return None
    host, _sep, port = hostport.partition(":")
    try:
        host = _vs_unquote(host, errors="strict").lower()
    except UnicodeDecodeError:
        return None
    if host.endswith("."):
        host = host[:-1]
    if not host or not _VS_HOST.fullmatch(host):
        return None
    if port:
        if not _vs_re.fullmatch(r"[0-9]+", port) or int(port) > 65535:
            return None
        port = int(port)
        if port == {"http": 80, "https": 443}[scheme]:
            port = None
    else:
        port = None
    return (scheme, host, port, _vs_path(_vs_re.split(r"[?#]", tail, maxsplit=1)[0] or "/"))


def _vs_parse(raw, base=None):
    # (scheme, host, port|None, path) of an http(s) URL, resolved against ``base``; None
    # when it is not an http(s) URL this rule parses exactly.
    s = "" if raw is None else str(raw)
    try:
        s.encode("utf-8")
    except UnicodeEncodeError:
        return None
    s = s.strip(_VS_TRIM).replace("\t", "").replace("\n", "").replace("\r", "")
    m = _VS_SCHEME.match(s)
    if m:
        scheme = m.group(1).lower()
        rest = s[m.end():]
        if scheme not in ("http", "https") or len(rest) - len(rest.lstrip("/\\")) != 2:
            return None
        return _vs_authority(scheme, rest[2:])
    b = base if isinstance(base, tuple) else (_vs_parse(base) if base is not None else None)
    if b is None:
        return None
    lead = len(s) - len(s.lstrip("/\\"))
    if lead >= 2:
        return _vs_authority(b[0], s[2:]) if lead == 2 else None
    rel = _vs_re.split(r"[?#]", s, maxsplit=1)[0]
    if lead == 1:
        path = rel
    elif rel == "":
        path = b[3]
    else:
        path = b[3][: b[3].rfind("/") + 1] + rel
    return (b[0], b[1], b[2], _vs_path(path))


def _vs_origin(parts):
    return parts[0] + "://" + parts[1] + ("" if parts[2] is None else ":" + str(parts[2]))


def _vs_ambiguous(path):
    for seg in path.split("/"):
        if "%" not in seg:
            continue
        try:
            decoded = _vs_unquote(seg, errors="strict")
        except UnicodeDecodeError:
            return True
        if "/" in decoded or "\\" in decoded or "\x00" in decoded or decoded in (".", ".."):
            return True
    return False


def _vs_normal_prefix(prefix):
    # A recorded path prefix is used only when it is already in normal form.
    if not isinstance(prefix, str) or not prefix.startswith("/"):
        return False
    parts = _vs_parse("http://h" + prefix)
    return parts is not None and parts[3] == prefix and not _vs_ambiguous(prefix)


def _vs_scope_violation(entries, url, what="PAGE", base=None):
    # None when ``url`` (resolved against ``base``) is inside one of ``entries``
    # ({"origin", "path_prefix"} dicts); otherwise the typed reason.
    if not isinstance(entries, (list, tuple)) or not entries:
        return "TASK_SCOPE_MISSING"
    raw = "" if url is None else str(url)
    if not raw.strip(_VS_TRIM):
        return "TASK_SCOPE_" + what + "_URL_UNKNOWN"
    parts = _vs_parse(raw, base)
    if parts is None:
        m = _VS_SCHEME.match(raw.strip(_VS_TRIM).replace("\t", "").replace("\n", "").replace("\r", ""))
        if m and m.group(1).lower() not in ("http", "https"):
            return "TASK_SCOPE_" + what + "_URL_NOT_HTTP"
        return "TASK_SCOPE_" + what + "_URL_INVALID"
    if _vs_ambiguous(parts[3]):
        return "TASK_SCOPE_" + what + "_PATH_AMBIGUOUS"
    origin, path, same_origin = _vs_origin(parts), parts[3], False
    for entry in entries:
        entry_origin = entry.get("origin") if isinstance(entry, dict) else None
        declared = _vs_parse(entry_origin) if isinstance(entry_origin, str) else None
        if declared is None or declared[3] != "/" or _vs_origin(declared) != origin:
            continue
        same_origin = True
        prefix = entry.get("path_prefix")
        if not prefix:
            return None
        if not _vs_normal_prefix(prefix):
            continue
        if path.startswith(prefix) if prefix.endswith("/") else (path == prefix or path.startswith(prefix + "/")):
            return None
    return "TASK_SCOPE_" + what + ("_PATH_OUTSIDE" if same_origin else "_ORIGIN_OUTSIDE")
# --- VAN shared URL scope rule: end ---


def _tcp_hex(address: str, port: int) -> str:
    """The ``/proc/net/tcp`` spelling of an IPv4 endpoint (address bytes in host order)."""
    return socket.inet_aton(address)[::-1].hex().upper() + ":" + f"{port:04X}"


def socket_owner_uid(client: tuple[str, int], server: tuple[str, int], table: str = "/proc/net/tcp") -> int | None:
    """Review I8 MAJOR-3: the uid owning the client end of a loopback TCP connection, from the
    kernel's socket table (the TCP counterpart of SO_PEERCRED, which only Unix sockets have:
    Chromium's --proxy-server needs TCP). None when the connection is not found."""
    want_local, want_remote = _tcp_hex(*client), _tcp_hex(*server)
    try:
        with open(table, encoding="ascii") as handle:
            next(handle, None)
            for line in handle:
                fields = line.split()
                if len(fields) > 7 and fields[1] == want_local and fields[2] == want_remote:
                    return int(fields[7])
    except (OSError, ValueError):
        return None
    return None


def client_allowed(writer: asyncio.StreamWriter, uid: str) -> bool:
    """True when no uid is configured (development) or the client socket belongs to it."""
    if not uid:
        return True
    try:
        peer, local = writer.get_extra_info("peername"), writer.get_extra_info("sockname")
        owner = socket_owner_uid((peer[0], int(peer[1])), (local[0], int(local[1])))
    except (TypeError, ValueError, IndexError, OSError):
        return False
    return owner is not None and str(owner) == uid.strip()


class Refused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in REFUSALS else "EGRESS_REQUEST_INVALID"


# ------------------------------------------------------------------------------ policy
def scope_digest(scope: Any) -> str:
    """Same bytes as ``scope_digest`` in harness_service.py and the gateway's adapters."""
    return hashlib.sha256(
        json.dumps(scope if isinstance(scope, dict) else None, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def effect_mac(key: bytes, alias: str, generation: int, holder_id: str, task_id: str,
               mutating: bool, digest: str) -> str:
    """Same bytes as ``effect_mac`` in harness_service.py (``van-harness-effect/1``)."""
    message = (f"{EFFECT_MAC_CONTEXT}\n{alias}\n{int(generation)}\n{holder_id}\n{task_id}\n"
               f"{'1' if mutating else '0'}\n{digest}").encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


REVOKE_MAC_CONTEXT = "van-egress-revoke/1"


def revoke_mac(key: bytes, alias: str, generation: int, holder_id: str, final: bool) -> str:
    """Same bytes as ``egress_revoke_mac`` in harness_service.py (unit G13)."""
    message = f"{REVOKE_MAC_CONTEXT}\n{alias}\n{int(generation)}\n{holder_id}\n{'1' if final else '0'}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


# ------------------------------------------------------------------------ guard canary
#
# Unit G14 (owner answer 2026-09-30 after unit G13, "In-zone canary origin (Recommended)"):
# "The canary serves its fixture from a dedicated canary hostname on the zone's private
# overlay, listed in the proxy config as the only allowed non-global upstream. It is checked
# by qualify.sh and never reachable by a task scope. The proxy's local-address rule stays
# strict for everything else."
#
# * Overlay names are reserved: a policy whose scope names a host under ``.internal`` is
#   refused (POLICY_SCOPE_RESERVED_HOST) unless it is the canary's own policy: alias
#   ``guard_canary``, task id ``van-guard-canary``, read-only, every entry the canary origin.
# * The exception itself (host, pinned address, port; TLS verified against the pinned canary
#   certificate only) is used only while that policy is in force *and* qualify.sh's canary
#   has armed it for the same lease (``op: canary``, MAC ``van-egress-canary/1`` under the
#   lease-fence key). No gateway code computes that MAC context.
# * Anything else naming the canary host is refused as a non-global upstream, before any
#   lookup; every other non-global address is refused exactly as before.
CANARY_ALIAS = "guard_canary"
CANARY_TASK_ID = "van-guard-canary"
CANARY_MAC_CONTEXT = "van-egress-canary/1"
CANARY_GRANT_TTL_SECONDS = 180.0
RESERVED_HOST_SUFFIX = ".internal"


def reserved_host(host: str) -> bool:
    """A zone-overlay name (``*.internal``): never part of a task scope."""
    host = str(host or "").lower().rstrip(".")
    return host == RESERVED_HOST_SUFFIX[1:] or host.endswith(RESERVED_HOST_SUFFIX)


class Canary:
    """The one allowed non-global upstream: exact host, exact (pinned) address, exact port."""

    def __init__(self, origin: str, host: str, port: int, address: str) -> None:
        self.origin, self.host, self.port, self.address = origin, host, port, address


def parse_canary(origin: str, address: str) -> Canary | None:
    """None when neither is configured; ValueError when the pair is not a valid canary.

    The origin is ``https://<name>.internal[:port]`` with no path; the address is a specific
    IPv4 address on a private network: not global, not loopback (the zone's own loopback
    services stay unreachable), not unspecified, link-local, multicast or reserved."""
    origin, address = str(origin or "").strip(), str(address or "").strip()
    if not origin and not address:
        return None
    parts = _vs_parse(origin)
    exact = set() if parts is None else {_vs_origin(parts), f"https://{parts[1]}:{parts[2] or 443}"}
    if parts is None or parts[0] != "https" or origin.rstrip("/") not in exact \
            or not reserved_host(parts[1]) or "." not in parts[1]:
        raise ValueError("VAN_BROWSER_CANARY_ORIGIN must be https://<name>.internal[:port] with no path")
    try:
        ip = ipaddress.ip_address(address)
    except ValueError as exc:
        raise ValueError("VAN_BROWSER_CANARY_ADDRESS must be an IPv4 address") from exc
    if ip.version != 4 or ip.is_global or ip.is_loopback or ip.is_unspecified or ip.is_link_local \
            or ip.is_multicast or ip.is_reserved:
        raise ValueError("VAN_BROWSER_CANARY_ADDRESS must be a private overlay IPv4 address (not global, loopback,"
                         " unspecified, link-local, multicast or reserved)")
    return Canary(_vs_origin(parts), parts[1], parts[2] or 443, str(ip))


def canary_mac(key: bytes, alias: str, generation: int, holder_id: str, task_id: str,
               origin: str, address: str) -> str:
    """Same bytes as ``canary_mac`` in harness_service.py and guard_canary.py."""
    message = (f"{CANARY_MAC_CONTEXT}\n{alias}\n{int(generation)}\n{holder_id}\n{task_id}\n"
               f"{origin}\n{address}").encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def load_key(path: str) -> bytes | None:
    if not path:
        return None
    key = Path(path).read_bytes().strip()
    if len(key) < MIN_KEY_BYTES:
        raise ValueError("key shorter than 32 bytes")
    return key


class Policy:
    def __init__(self, alias: str, generation: int, holder: str, task_id: str, mutating: bool,
                 scope: dict[str, Any], expires: float) -> None:
        self.alias, self.generation, self.holder, self.task_id = alias, generation, holder, task_id
        self.mutating, self.scope, self.expires = mutating, scope, expires
        self.entries = scope.get("entries") if isinstance(scope.get("entries"), list) else []
        #: scope origins, normalised by the shared rule ("https://host" / "http://host:8080")
        self.origins: set[str] = set()
        #: (host, port, scheme) a CONNECT may open
        self.authorities: dict[tuple[str, int], str] = {}
        for entry in self.entries:
            raw = entry.get("origin") if isinstance(entry, dict) else None
            parts = _vs_parse(raw) if isinstance(raw, str) else None
            if parts is None or parts[3] != "/":
                continue
            self.origins.add(_vs_origin(parts))
            port = parts[2] if parts[2] is not None else {"http": 80, "https": 443}[parts[0]]
            # An https entry wins when the same host:port is named with both schemes.
            if self.authorities.get((parts[1], port)) != "https":
                self.authorities[(parts[1], port)] = parts[0]


class PolicyStore:
    """Per-alias task policy. Set only with a valid effect MAC; newest lease generation wins."""

    def __init__(self, key: bytes | None, ttl: float = POLICY_TTL_SECONDS, canary: Canary | None = None,
                 state_file: Path | None = None) -> None:
        self.key = key
        self.ttl = ttl
        self.policies: dict[str, Policy] = {}
        self.newest: dict[str, tuple[int, str]] = {}
        #: Unit G13 — per alias, the leases whose policy was finally revoked (lease end, or
        #: the Harness guard froze the page): their policy is never installed again.
        self.ended: dict[str, set[tuple[int, str]]] = {}
        #: Review I8 MINOR-2: ``newest`` and ``ended`` survive a restart (a captured policy of
        #: an older or finally revoked lease is not re-admitted by restarting the proxy).
        #: Policies themselves do not: after a restart every alias starts with none.
        #: Unit G14 — the configured canary origin, and the lease qualify.sh armed it for:
        #: (generation, holder, task id, monotonic expiry).
        self.canary = canary
        self.canary_grant: tuple[int, str, str, float] | None = None
        self.state_file = state_file
        if state_file is not None:
            self._load()

    def _load(self) -> None:
        try:
            raw = self.state_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        data = json.loads(raw)  # unreadable state: the proxy refuses to start (fail closed)
        if not isinstance(data, dict) or data.get("schema") != STATE_SCHEMA:
            raise ValueError("policy state file has an unknown schema")
        for alias, (generation, holder) in data["newest"].items():
            self.newest[str(alias)] = (int(generation), str(holder))
        for alias, leases in data["ended"].items():
            self.ended[str(alias)] = {(int(g), str(h)) for g, h in leases}

    def _save(self) -> None:
        if self.state_file is None:
            return
        data = {"schema": STATE_SCHEMA,
                "newest": {a: [g, h] for a, (g, h) in sorted(self.newest.items())},
                "ended": {a: sorted([g, h] for g, h in leases) for a, leases in sorted(self.ended.items())}}
        tmp = self.state_file.with_name(self.state_file.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, separators=(",", ":")))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.state_file)

    def _reserved_scope(self, alias: str, task_id: str, mutating: bool, scope: dict[str, Any]) -> bool:
        """True when the scope names an overlay host and is not exactly the canary's own."""
        entries = scope.get("entries") if isinstance(scope.get("entries"), list) else []
        canary_own = (self.canary is not None and alias == CANARY_ALIAS and task_id == CANARY_TASK_ID
                      and not mutating)
        for entry in entries:
            raw = entry.get("origin") if isinstance(entry, dict) else None
            parts = _vs_parse(raw) if isinstance(raw, str) else None
            host = parts[1] if parts is not None else ""
            if parts is None and isinstance(raw, str) and RESERVED_HOST_SUFFIX in raw.lower():
                return True  # unparseable but names an overlay host: refuse, never guess
            if parts is not None and reserved_host(host):
                if not canary_own or parts[3] != "/" or _vs_origin(parts) != self.canary.origin:
                    return True
        return False

    def arm_canary(self, msg: dict[str, Any]) -> str | None:
        """Unit G14 — qualify.sh's guard canary arms the canary exception for one lease of the
        canary alias. None when armed; otherwise the refusal code. Arming installs no policy:
        the Harness still pushes the lease's own (effect-MACed) policy, and the exception is
        used only while that policy is the canary's own and matches this grant."""
        alias, task_id = msg.get("alias"), msg.get("task_id")
        generation, holder, mac = msg.get("lease_generation"), msg.get("lease_holder_id"), msg.get("canary_mac")
        if self.canary is None:
            return "CANARY_UNCONFIGURED"
        if self.key is None:
            return "POLICY_KEY_UNCONFIGURED"
        if alias != CANARY_ALIAS or task_id != CANARY_TASK_ID:
            return "CANARY_TASK_INVALID"
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1 \
                or not isinstance(holder, str) or not holder or not isinstance(mac, str):
            return "POLICY_FIELDS_INVALID"
        expected = canary_mac(self.key, alias, generation, holder, task_id, self.canary.origin, self.canary.address)
        if not hmac.compare_digest(mac, expected):
            return "CANARY_MAC_INVALID"
        newest = self.newest.get(alias)
        if newest is not None and generation < newest[0]:
            return "POLICY_GENERATION_STALE"
        if (generation, holder) in self.ended.get(alias, ()):
            return "POLICY_LEASE_ENDED"
        self.canary_grant = (generation, holder, task_id, time.monotonic() + CANARY_GRANT_TTL_SECONDS)
        return None

    def canary_armed(self, policy: Policy | None) -> bool:
        """The exception applies to this request's policy: the canary's own, read-only, for
        the lease qualify.sh armed, within the grant's lifetime."""
        grant = self.canary_grant
        return (self.canary is not None and policy is not None and grant is not None
                and policy.alias == CANARY_ALIAS and policy.task_id == CANARY_TASK_ID and not policy.mutating
                and (policy.generation, policy.holder, policy.task_id) == grant[:3]
                and time.monotonic() < grant[3])

    def set(self, msg: dict[str, Any]) -> str | None:
        """None when installed; otherwise the refusal code."""
        alias = msg.get("alias")
        generation, holder = msg.get("lease_generation"), msg.get("lease_holder_id")
        task_id, mac, scope = msg.get("task_id"), msg.get("effect_mac"), msg.get("task_scope")
        mutating = msg.get("mutating")
        if self.key is None:
            return "POLICY_KEY_UNCONFIGURED"
        if not isinstance(alias, str) or not PROFILE_RE.fullmatch(alias):
            return "POLICY_ALIAS_INVALID"
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1 \
                or not isinstance(holder, str) or not holder or not isinstance(task_id, str) \
                or not isinstance(mutating, bool) or not isinstance(mac, str) or not isinstance(scope, dict):
            return "POLICY_FIELDS_INVALID"
        expected = effect_mac(self.key, alias, generation, holder, task_id, mutating, scope_digest(scope))
        if not hmac.compare_digest(mac, expected):
            return "POLICY_MAC_INVALID"
        if self._reserved_scope(alias, task_id, mutating, scope):
            # Unit G14: a task scope never names the zone's overlay (the canary origin included).
            return "POLICY_SCOPE_RESERVED_HOST"
        newest = self.newest.get(alias)
        if newest is not None and (generation < newest[0] or (generation == newest[0] and holder != newest[1])):
            return "POLICY_GENERATION_STALE"
        if (generation, holder) in self.ended.get(alias, ()):
            return "POLICY_LEASE_ENDED"
        changed = self.newest.get(alias) != (generation, holder)
        self.newest[alias] = (generation, holder)
        if changed:
            self._save()  # before the policy is usable
        self.policies[alias] = Policy(alias, generation, holder, task_id, mutating, scope,
                                      time.monotonic() + self.ttl)
        return None

    def revoke(self, msg: dict[str, Any]) -> str | None:
        """Unit G13 — the Harness takes a lease's policy away. None when done; else the code.

        Removes the alias's policy if it belongs to an older lease, or to this lease. With
        ``final`` (the lease ended, or its guard froze the page) this lease's policy can never
        be installed again. A newer lease's policy is never touched. The message carries a MAC
        under the lease-fence key (context ``van-egress-revoke/1``), so no local caller without
        the key can revoke, and none can widen anything."""
        alias = msg.get("alias")
        generation, holder, final = msg.get("lease_generation"), msg.get("lease_holder_id"), msg.get("final")
        mac = msg.get("revoke_mac")
        if self.key is None:
            return None  # without the key no policy was ever installed: nothing to revoke
        if not isinstance(alias, str) or not PROFILE_RE.fullmatch(alias):
            return "POLICY_ALIAS_INVALID"
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1 \
                or not isinstance(holder, str) or not holder or not isinstance(final, bool) or not isinstance(mac, str):
            return "POLICY_FIELDS_INVALID"
        if not hmac.compare_digest(mac, revoke_mac(self.key, alias, generation, holder, final)):
            return "POLICY_MAC_INVALID"
        policy = self.policies.get(alias)
        if policy is not None and (policy.generation < generation
                                   or (policy.generation, policy.holder) == (generation, holder)):
            del self.policies[alias]
        grant = self.canary_grant
        if alias == CANARY_ALIAS and grant is not None and (
                grant[0] < generation or (final and grant[:2] == (generation, holder))):
            # Unit G14: the canary exception ends with its lease (a newer lease's start, or
            # this lease's end / freeze); the lease's own start leaves the grant it was armed with.
            self.canary_grant = None
        if final:
            ended = self.ended.setdefault(alias, set())
            ended.add((generation, holder))
            newest = self.newest.get(alias)
            # Only the newest ended lease matters (older generations are stale anyway).
            if newest is not None:
                self.ended[alias] = {e for e in ended if e[0] >= newest[0]}
            self._save()
        return None

    def get(self, alias: str) -> Policy | None:
        policy = self.policies.get(alias)
        if policy is None or time.monotonic() >= policy.expires:
            return None
        return policy


# ------------------------------------------------------------------------ certificates
class CertAuthority:
    """The zone-local interception CA and the one leaf key every minted certificate uses."""

    def __init__(self, state_dir: Path, openssl: str = OPENSSL) -> None:
        self.dir = state_dir
        self.openssl = openssl
        self.ca_key, self.ca_crt = state_dir / "ca.key", state_dir / "ca.crt"
        self.leaf_key = state_dir / "leaf.key"
        self.certs = state_dir / "certs"
        self.contexts: dict[str, tuple[float, ssl.SSLContext]] = {}
        self.spki = ""

    def _run(self, *args: str) -> bytes:
        return subprocess.run([self.openssl, *args], check=True, capture_output=True, timeout=20).stdout

    def ensure(self) -> None:
        self.dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.dir, 0o700)
        self.certs.mkdir(mode=0o700, exist_ok=True)
        old = os.umask(0o277)
        try:
            if not self.ca_key.exists() or not self.ca_crt.exists():
                self._run("req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
                          "-keyout", str(self.ca_key), "-out", str(self.ca_crt), "-days", "3650",
                          "-subj", "/CN=van-browser-core egress interception CA",
                          "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
                          "-addext", "keyUsage=critical,keyCertSign")
            if not self.leaf_key.exists():
                self._run("genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256",
                          "-out", str(self.leaf_key))
        finally:
            os.umask(old)
        for path in (self.ca_key, self.leaf_key):
            os.chmod(path, 0o400)
        der = self._run("pkey", "-in", str(self.leaf_key), "-pubout", "-outform", "DER")
        self.spki = base64.b64encode(hashlib.sha256(der).digest()).decode()

    def _mint(self, host: str) -> Path:
        try:
            ipaddress.ip_address(host)
            san = f"IP:{host}"
        except ValueError:
            san = f"DNS:{host}"
        out = self.certs / f"{host}.crt"
        tmp = self.certs / f".{host}.crt.tmp"
        self._run("req", "-new", "-x509", "-key", str(self.leaf_key), "-CA", str(self.ca_crt),
                  "-CAkey", str(self.ca_key), "-subj", f"/CN={host}", "-days", "7",
                  "-addext", f"subjectAltName={san}", "-addext", "extendedKeyUsage=serverAuth",
                  "-addext", "basicConstraints=critical,CA:FALSE", "-out", str(tmp))
        os.replace(tmp, out)
        return out

    def context(self, host: str) -> ssl.SSLContext:
        if not _VS_HOST.fullmatch(host) or len(host) > 253:
            raise Refused("EGRESS_REQUEST_INVALID")
        cached = self.contexts.get(host)
        if cached and time.time() - cached[0] < 86400:
            return cached[1]
        cert = self._mint(host)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(str(cert), str(self.leaf_key))
        # HTTP/1.1 only: a WebSocket then arrives as an ``Upgrade`` request this proxy reads
        # (not an HTTP/2 extended CONNECT inside a stream it would have to demultiplex).
        ctx.set_alpn_protocols(["http/1.1"])
        self.contexts[host] = (time.time(), ctx)
        return ctx


# ------------------------------------------------------------------------------ HTTP
class Request:
    def __init__(self, method: str, target: str, version: str, headers: list[tuple[str, str]]) -> None:
        self.method, self.target, self.version, self.headers = method, target, version, headers

    def header(self, name: str) -> list[str]:
        return [v for k, v in self.headers if k.lower() == name]


async def read_head(reader: asyncio.StreamReader) -> Request:
    try:
        raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), IO_TIMEOUT_SECONDS)
    except (asyncio.LimitOverrunError, asyncio.IncompleteReadError, asyncio.TimeoutError) as exc:
        raise Refused("EGRESS_REQUEST_INVALID") from exc
    try:
        text = raw.decode("latin-1")
    except UnicodeDecodeError as exc:  # pragma: no cover - latin-1 decodes everything
        raise Refused("EGRESS_REQUEST_INVALID") from exc
    lines = text[:-4].split("\r\n")
    # Review I8 MAJOR-3: a bare CR or LF (or a NUL) left in a line after the CRLF split is a
    # second line the upstream server may honour (a smuggled request); refused, never repaired.
    if any(BAD_LINE_CHARS.search(line) for line in lines):
        raise Refused("EGRESS_REQUEST_INVALID")
    parts = lines[0].split(" ")
    if len(parts) != 3 or not TOKEN_RE.fullmatch(parts[0]) or parts[2] not in ("HTTP/1.1", "HTTP/1.0") \
            or not TARGET_RE.fullmatch(parts[1]):
        raise Refused("EGRESS_REQUEST_INVALID")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line or line[0] in " \t" or ":" not in line:
            raise Refused("EGRESS_REQUEST_INVALID")  # obs-fold and junk are refused, not repaired
        name, value = line.split(":", 1)
        if not TOKEN_RE.fullmatch(name) or HEADER_VALUE_BAD.search(value):
            raise Refused("EGRESS_REQUEST_INVALID")
        headers.append((name, value.strip()))
    return Request(parts[0].upper(), parts[1], parts[2], headers)


def _authority(value: str) -> tuple[str, int]:
    host, sep, port = value.rpartition(":")
    if not sep or not host or not port.isdigit() or int(port) > 65535 or host.startswith("["):
        raise Refused("EGRESS_REQUEST_INVALID")
    host = host.lower().rstrip(".")
    if not _VS_HOST.fullmatch(host):
        raise Refused("EGRESS_REQUEST_INVALID")
    return host, int(port)


def _refusal(code: str) -> bytes:
    body = code.encode()
    return (f"HTTP/1.1 403 Forbidden\r\nX-Van-Egress-Refused: {code}\r\ncontent-type: text/plain\r\n"
            f"content-length: {len(body)}\r\ncache-control: no-store\r\nconnection: close\r\n\r\n").encode() + body


def classify(policy: Policy | None, req: Request, scheme: str, host: str, port: int) -> tuple[str | None, str]:
    """(refusal code or None, url). The whole decision for one request, pure."""
    if policy is None:
        return "EGRESS_POLICY_UNKNOWN", ""
    default = {"http": 80, "https": 443}[scheme]
    authority = host if port == default else f"{host}:{port}"
    target = req.target
    if target.startswith(("http://", "https://")):
        parts = _vs_parse(target)
        if parts is None or parts[0] != scheme or parts[1] != host or (parts[2] or default) != port:
            return "EGRESS_HOST_MISMATCH", ""
        target = target[len(scheme) + 3:]
        target = target[target.find("/"):] if "/" in target else "/"
    if not target.startswith("/"):
        return "EGRESS_REQUEST_INVALID", ""
    hosts = req.header("host")
    if len(hosts) != 1:
        return "EGRESS_REQUEST_INVALID", ""
    parsed_host = _vs_parse(f"{scheme}://{hosts[0]}/")
    if parsed_host is None or parsed_host[1] != host or (parsed_host[2] or default) != port:
        return "EGRESS_HOST_MISMATCH", ""
    url = f"{scheme}://{authority}{target}"
    parts = _vs_parse(url)
    if parts is None or _vs_origin(parts) not in policy.origins:
        return "EGRESS_ORIGIN_OUT_OF_SCOPE", url
    # Review I8 MAJOR-3: what is forwarded is the target this decision parsed (the normalised
    # path the scope rule saw, plus the query), never the bytes the client sent.
    query = target.split("#", 1)[0].partition("?")
    url = f"{scheme}://{authority}{parts[3]}" + (f"?{query[2]}" if query[1] else "")
    lengths = req.header("content-length")
    if req.header("transfer-encoding") or len(lengths) > 1 or (lengths and not lengths[0].isdigit()):
        return "EGRESS_REQUEST_INVALID", url
    has_body = bool(lengths) and int(lengths[0]) > 0
    upgrades = [u.strip().lower() for u in req.header("upgrade")]
    # Review I9 MAJOR-1: the one protocol the proxy admits is ``websocket``, alone. A list
    # (``websocket, h2c``) let the upstream pick a protocol this proxy never reads.
    if upgrades and upgrades != ["websocket"]:
        return "EGRESS_UPGRADE_REFUSED", url
    websocket = bool(upgrades)
    if websocket or has_body or req.method not in READ_METHODS:
        if not policy.mutating:
            return ("EGRESS_WEBSOCKET_REFUSED" if websocket else "EGRESS_WRITE_REFUSED"), url
        if _vs_scope_violation(policy.entries, url, "WRITE") is not None:
            return "EGRESS_WRITE_OUT_OF_SCOPE", url
    return None, url


class EgressProxy:
    def __init__(self, store: PolicyStore, ca: CertAuthority, *, port_range: str = PORT_RANGE,
                 resolve: dict[str, str] | None = None, upstream_cafile: str | None = None,
                 service_allow: str = SERVICE_ALLOW, service_port: int = SERVICE_PORT,
                 decision_log: str = DECISION_LOG, canary_cert: str = CANARY_CERT,
                 client_uid: str = CLIENT_UID, service_client_uid: str = SERVICE_CLIENT_UID) -> None:
        self.store, self.ca = store, ca
        self.client_uid, self.service_client_uid = client_uid.strip(), service_client_uid.strip()
        for value in (self.client_uid, self.service_client_uid):
            if value and not value.isdigit():
                raise ValueError("VAN_EGRESS_CLIENT_UID / VAN_EGRESS_SERVICE_CLIENT_UID must be numeric uids")
        #: Unit G14 — the canary upstream is verified against its pinned certificate only
        #: (never the system trust store, never the test CA file), for the canary host name.
        self.canary_ctx: ssl.SSLContext | None = None
        if store.canary is not None:
            if not canary_cert or not Path(canary_cert).is_file():
                raise ValueError("VAN_BROWSER_CANARY_CERT must name the canary's certificate")
            self.canary_ctx = ssl.create_default_context(cafile=canary_cert)
            self.canary_ctx.set_alpn_protocols(["http/1.1"])
        low, _, high = port_range.partition("-")
        self.ports = range(int(low), int(high or low) + 1)
        self.listeners: dict[str, tuple[int, asyncio.base_events.Server]] = {}
        self.resolve_override = resolve or {}
        self.upstream_ctx = ssl.create_default_context(cafile=upstream_cafile or None)
        self.upstream_ctx.set_alpn_protocols(["http/1.1"])
        self.service_allow = {_authority(a.strip()) for a in service_allow.split(",") if a.strip()}
        self.service_port = service_port
        self.decision_log = decision_log
        self.lock = asyncio.Lock()

    # -- decisions
    def log(self, alias: str, method: str, origin: str, code: str | None) -> None:
        if not self.decision_log:
            return
        record = {"ts": round(time.time(), 3), "alias": alias, "method": method[:16],
                  "origin": origin[:300], "decision": "REFUSE" if code else "ALLOW", "code": code}
        try:
            with open(self.decision_log, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, separators=(",", ":")) + "\n")
        except OSError:
            pass

    # -- upstream
    async def _open_upstream(self, host: str, port: int, tls: bool, canary_ok: bool = False):
        canary = self.store.canary
        if canary is not None and host == canary.host:
            # Unit G14 — the only allowed non-global upstream: this exact host, only over TLS on
            # this exact port, only to the pinned address (no lookup: DNS cannot move it), and
            # only for the armed canary lease's own policy. Otherwise it is what it is: an
            # overlay name, refused like any other non-global upstream.
            if not canary_ok or not tls or port != canary.port or self.canary_ctx is None:
                raise Refused("EGRESS_UPSTREAM_ADDRESS_REFUSED")
            try:
                return await asyncio.wait_for(asyncio.open_connection(
                    canary.address, canary.port, ssl=self.canary_ctx, server_hostname=canary.host),
                    IO_TIMEOUT_SECONDS)
            except (OSError, ssl.SSLError, asyncio.TimeoutError) as exc:
                raise Refused("EGRESS_UPSTREAM_UNAVAILABLE") from exc
        override = self.resolve_override.get(f"{host}:{port}") or self.resolve_override.get(f"*:{port}")
        if override:
            addr_host, _, addr_port = override.rpartition(":")
            addresses = [(addr_host, int(addr_port))]
        else:
            loop = asyncio.get_running_loop()
            try:
                infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            except OSError as exc:
                raise Refused("EGRESS_UPSTREAM_UNAVAILABLE") from exc
            addresses = []
            for info in infos:
                ip = ipaddress.ip_address(info[4][0])
                if not ip.is_global:
                    # A scope name must not reach the zone's own loopback or a private network.
                    raise Refused("EGRESS_UPSTREAM_ADDRESS_REFUSED")
                addresses.append((info[4][0], port))
        last: Exception | None = None
        for addr, addr_port in addresses:
            try:
                return await asyncio.wait_for(asyncio.open_connection(
                    addr, addr_port, ssl=self.upstream_ctx if tls else None,
                    server_hostname=host if tls else None), IO_TIMEOUT_SECONDS)
            except (OSError, ssl.SSLError, asyncio.TimeoutError) as exc:
                last = exc
        raise Refused("EGRESS_UPSTREAM_UNAVAILABLE") from last

    @staticmethod
    async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
        try:
            while True:
                chunk = await asyncio.wait_for(src.read(65536), IO_TIMEOUT_SECONDS)
                if not chunk:
                    break
                dst.write(chunk)
                await dst.drain()
        except (OSError, asyncio.TimeoutError, ssl.SSLError):
            pass
        finally:
            try:
                if dst.can_write_eof():
                    dst.write_eof()
            except (OSError, RuntimeError):
                pass

    @staticmethod
    async def _upstream_head(up_reader: asyncio.StreamReader) -> tuple[bytes, bool]:
        """The upstream's answer head to an ``Upgrade`` request and whether it switched to
        ``websocket``. A switch to anything else is refused: the proxy reads no other protocol."""
        try:
            head = await asyncio.wait_for(up_reader.readuntil(b"\r\n\r\n"), IO_TIMEOUT_SECONDS)
        except (asyncio.LimitOverrunError, asyncio.IncompleteReadError) as exc:
            raise Refused("EGRESS_UPSTREAM_UNAVAILABLE") from exc
        lines = head[:-4].decode("latin-1").split("\r\n")
        status = lines[0].split(" ")
        if len(status) < 2 or status[1] != "101":
            return head, False
        upgrades = [value.strip().lower() for name, _, value in (line.partition(":") for line in lines[1:])
                    if name.strip().lower() == "upgrade"]
        if status[0] != "HTTP/1.1" or upgrades != ["websocket"]:
            raise Refused("EGRESS_UPGRADE_REFUSED")
        return head, True

    async def _forward(self, req: Request, reader, writer, scheme: str, host: str, port: int, url: str,
                       alias: str = "", canary_ok: bool = False) -> None:
        try:
            up_reader, up_writer = await self._open_upstream(host, port, scheme == "https", canary_ok)
        except Refused as exc:
            # Unit G14: the upstream refusal is a decision too (the request line above was
            # logged ALLOW before the address was known).
            self.log(alias, "UPSTREAM", f"{scheme}://{host}:{port}", exc.code)
            raise
        try:
            target = url[len(scheme) + 3:]
            target = target[target.find("/"):] if "/" in target else "/"
            websocket = bool(req.header("upgrade"))
            lines = [f"{req.method} {target} HTTP/1.1"]
            for name, value in req.headers:
                if name.lower() in HOP_BY_HOP:
                    continue
                lines.append(f"{name}: {value}")
            if websocket:
                lines += ["Connection: Upgrade", f"Upgrade: {req.header('upgrade')[0]}"]
            else:
                lines.append("Connection: close")
            up_writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
            length = int((req.header("content-length") or ["0"])[0])
            if length > MAX_BODY_BYTES:
                raise Refused("EGRESS_REQUEST_INVALID")
            if length:
                up_writer.write(await asyncio.wait_for(reader.readexactly(length), IO_TIMEOUT_SECONDS))
            await up_writer.drain()
            if websocket:
                # Review I9 MAJOR-1: the client's later bytes are frames only once the upstream
                # has switched to WebSocket. An upstream that ignores the upgrade answers with an
                # ordinary response on a live connection, and a request the client pipelined
                # behind the handshake would reach it unjudged. Until a ``101`` naming
                # ``websocket`` arrives nothing more of the client's is relayed; without one,
                # that one response is all this connection carries.
                head, switched = await self._upstream_head(up_reader)
                writer.write(head)
                await writer.drain()
                if switched:
                    await asyncio.gather(self._pipe(reader, up_writer), self._pipe(up_reader, writer))
                else:
                    await self._pipe(up_reader, writer)
            else:
                # The response only; nothing more the client sends reaches upstream on this
                # connection (one request per connection).
                await self._pipe(up_reader, writer)
        finally:
            up_writer.close()

    # -- one client connection
    async def _request(self, alias: str, reader, writer, scheme: str, host: str, port: int) -> None:
        req = await read_head(reader)
        policy = self.store.get(alias)
        code, url = classify(policy, req, scheme, host, port)
        origin = f"{scheme}://{host}:{port}"
        self.log(alias, req.method + (" UPGRADE" if req.header("upgrade") else ""), origin, code)
        if code:
            raise Refused(code)
        await self._forward(req, reader, writer, scheme, host, port, url, alias, self.store.canary_armed(policy))

    async def handle(self, alias: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            try:
                if not client_allowed(writer, self.client_uid):
                    # Review I8 MAJOR-3: only the browser user's sockets use a task's policy.
                    self.log(alias, "CLIENT", "", "EGRESS_CLIENT_REFUSED")
                    raise Refused("EGRESS_CLIENT_REFUSED")
                req = await read_head(reader)
                if req.method == "CONNECT":
                    host, port = _authority(req.target)
                    policy = self.store.get(alias)
                    code = None
                    if policy is None:
                        code = "EGRESS_POLICY_UNKNOWN"
                    elif (host, port) not in policy.authorities:
                        code = "EGRESS_CONNECT_OUT_OF_SCOPE"
                    self.log(alias, "CONNECT", f"{host}:{port}", code)
                    if code:
                        raise Refused(code)
                    scheme = policy.authorities[(host, port)]
                    ctx = None
                    if scheme == "https":
                        ctx = await asyncio.get_running_loop().run_in_executor(None, self.ca.context, host)
                        # Nothing the client sends after the 200 may land in the plain-text
                        # reader: its TLS ClientHello belongs to the TLS layer started below.
                        writer.transport.pause_reading()
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await writer.drain()
                    if ctx is not None:
                        await asyncio.wait_for(writer.start_tls(ctx), IO_TIMEOUT_SECONDS)
                    await self._request(alias, reader, writer, scheme, host, port)
                else:
                    # A plain-HTTP proxy request (absolute-form).
                    parts = _vs_parse(req.target) if req.target.startswith("http://") else None
                    if parts is None:
                        self.log(alias, req.method, "", "EGRESS_REQUEST_INVALID")
                        raise Refused("EGRESS_REQUEST_INVALID")
                    host, port = parts[1], parts[2] or 80
                    policy = self.store.get(alias)
                    code, url = classify(policy, req, "http", host, port)
                    self.log(alias, req.method + (" UPGRADE" if req.header("upgrade") else ""),
                             f"http://{host}:{port}", code)
                    if code:
                        raise Refused(code)
                    await self._forward(req, reader, writer, "http", host, port, url, alias)
            except Refused as exc:
                try:
                    writer.write(_refusal(exc.code))
                    await writer.drain()
                except (OSError, RuntimeError, ssl.SSLError):
                    pass
        except (OSError, ssl.SSLError, asyncio.TimeoutError, asyncio.IncompleteReadError, ValueError):
            pass
        finally:
            try:
                writer.close()
            except (OSError, RuntimeError):
                pass

    async def handle_service(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """The Stagehand model-provider tunnel: CONNECT to a fixed host:port list, no MITM."""
        try:
            try:
                if not client_allowed(writer, self.service_client_uid):
                    self.log("_service", "CLIENT", "", "EGRESS_CLIENT_REFUSED")
                    raise Refused("EGRESS_CLIENT_REFUSED")
                req = await read_head(reader)
                if req.method != "CONNECT":
                    raise Refused("EGRESS_SERVICE_OUT_OF_ALLOWLIST")
                host, port = _authority(req.target)
                if (host, port) not in self.service_allow:
                    self.log("_service", "CONNECT", f"{host}:{port}", "EGRESS_SERVICE_OUT_OF_ALLOWLIST")
                    raise Refused("EGRESS_SERVICE_OUT_OF_ALLOWLIST")
                up_reader, up_writer = await self._open_upstream(host, port, False)
                self.log("_service", "CONNECT", f"{host}:{port}", None)
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
                try:
                    await asyncio.gather(self._pipe(reader, up_writer), self._pipe(up_reader, writer))
                finally:
                    up_writer.close()
            except Refused as exc:
                writer.write(_refusal(exc.code))
                await writer.drain()
        except (OSError, ssl.SSLError, asyncio.TimeoutError, ValueError):
            pass
        finally:
            try:
                writer.close()
            except (OSError, RuntimeError):
                pass

    # -- listeners and control
    async def listener(self, alias: str) -> int:
        async with self.lock:
            if alias in self.listeners:
                return self.listeners[alias][0]
            used = {port for port, _ in self.listeners.values()}
            for port in self.ports:
                if port in used or port == self.service_port:
                    continue
                try:
                    server = await asyncio.start_server(
                        lambda r, w, a=alias: self.handle(a, r, w), LOOPBACK, port, limit=MAX_HEAD_BYTES)
                except OSError:
                    continue
                self.listeners[alias] = (port, server)
                return port
        raise RuntimeError("EGRESS_PORTS_EXHAUSTED")

    async def control(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        reply: dict[str, Any]
        try:
            line = await asyncio.wait_for(reader.readline(), 10)
            msg = json.loads(line) if line else None
            if not isinstance(msg, dict):
                raise ValueError("not an object")
            op = msg.get("op")
            if op == "health":
                reply = {"ok": True, "service": SERVICE_VERSION, "trust_zone": TRUST_ZONE or None,
                         "policy_key": self.store.key is not None, "listeners": len(self.listeners),
                         "test_overrides": bool(self.resolve_override) or bool(TEST_UPSTREAM_CAFILE),
                         "interception": "zone-local-ca", "leaf_spki_sha256": self.ca.spki,
                         # Unit G14: the one allowed non-global upstream, or None.
                         "canary": None if self.store.canary is None else {
                             "origin": self.store.canary.origin, "address": self.store.canary.address,
                             "port": self.store.canary.port, "certificate_pinned": self.canary_ctx is not None}}
            elif op == "listener":
                alias = msg.get("alias")
                if not isinstance(alias, str) or not PROFILE_RE.fullmatch(alias):
                    raise ValueError("alias")
                reply = {"ok": True, "port": await self.listener(alias), "spki": self.ca.spki}
            elif op == "policy":
                error = self.store.set(msg)
                if error is None and isinstance(msg.get("alias"), str):
                    await self.listener(msg["alias"])
                reply = {"ok": error is None, "error": error}
            elif op == "canary":
                # Unit G14: qualify.sh's guard canary arms the canary exception for one lease.
                error = self.store.arm_canary(msg)
                reply = {"ok": error is None, "error": error}
            elif op == "revoke":
                # Unit G13: lease start (older leases' policy), lease end and guard freeze.
                error = self.store.revoke(msg)
                reply = {"ok": error is None, "error": error}
            else:
                reply = {"ok": False, "error": "OP_UNKNOWN"}
        except (ValueError, asyncio.TimeoutError, asyncio.LimitOverrunError, RuntimeError) as exc:
            reply = {"ok": False, "error": "CONTROL_INVALID" if not isinstance(exc, RuntimeError) else str(exc)}
        try:
            writer.write((json.dumps(reply, separators=(",", ":")) + "\n").encode())
            await writer.drain()
        except OSError:
            pass
        finally:
            writer.close()

    async def serve(self, control_socket: str) -> None:
        path = Path(control_socket)
        path.unlink(missing_ok=True)
        control = await asyncio.start_unix_server(self.control, str(path), limit=MAX_CONTROL_BYTES)
        # Group-writable: the Harness (browser user's group) connects; nothing else does.
        os.chmod(path, 0o660)
        servers = [control]
        if self.service_allow:
            servers.append(await asyncio.start_server(self.handle_service, LOOPBACK, self.service_port,
                                                      limit=MAX_HEAD_BYTES))
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await stop.wait()
        for server in servers + [s for _, s in self.listeners.values()]:
            server.close()


def _test_overrides() -> tuple[dict[str, str], str | None]:
    if not TEST_RESOLVE and not TEST_UPSTREAM_CAFILE:
        return {}, None
    if TRUST_ZONE:
        raise SystemExit("egress proxy refuses VAN_EGRESS_TEST_* overrides in a trust zone")
    return (json.loads(TEST_RESOLVE) if TEST_RESOLVE else {}), (TEST_UPSTREAM_CAFILE or None)


def main() -> None:
    resolve, cafile = _test_overrides()
    try:
        key = load_key(FENCE_KEY_FILE)
    except (OSError, ValueError) as exc:
        raise SystemExit("egress proxy: VAN_EGRESS_FENCE_KEY_FILE unreadable or shorter than 32 bytes") from exc
    if key is None and TRUST_ZONE:
        # Without the key no policy can be verified; every request would be refused anyway.
        raise SystemExit("egress proxy refuses to start in a trust zone without VAN_EGRESS_FENCE_KEY_FILE")
    if TRUST_ZONE and (not CLIENT_UID.strip() or (SERVICE_ALLOW.strip() and not SERVICE_CLIENT_UID.strip())):
        # Review I8 MAJOR-3: loopback TCP is open to every local user.
        raise SystemExit("egress proxy refuses to start in a trust zone without VAN_EGRESS_CLIENT_UID"
                         " (and VAN_EGRESS_SERVICE_CLIENT_UID when the service tunnel is configured)")
    try:
        canary = parse_canary(CANARY_ORIGIN, CANARY_ADDRESS)
    except ValueError as exc:
        raise SystemExit(f"egress proxy: {exc}") from exc
    ca = CertAuthority(STATE_DIR)
    ca.ensure()
    try:
        store = PolicyStore(key, canary=canary, state_file=STATE_DIR / "policy-state.json")
        proxy = EgressProxy(store, ca, resolve=resolve, upstream_cafile=cafile)
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"egress proxy: {exc}") from exc
    asyncio.run(proxy.serve(CONTROL_SOCKET))


if __name__ == "__main__":
    sys.exit(main())
