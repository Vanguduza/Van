"""Browser actions stay inside the task's own truth. This implements the task-scope rule the
owner confirmed on 2026-09-30 ("Yes, confirmed": the confirmation block of
docs/decisions/OWNER-DECISION-20260930-BROWSER-TASK-SCOPE.md, authorization
``auth-20260930-owner-explicit-task-scope-confirmation``): each browser task's recorded scope
decides what automation may act on, and anything outside it goes to the owner. Section 3 of
that record (the integrator's reading, then pending) is what the owner confirmed.

The owner rejected a fixed allowlist ("I do not want to build a fixed allowlist, pages should
[be] relevant to the task truth"). A classifier cannot prove a click on an arbitrary page is
safe: the page controls every input the classifier reads. So the primary control is the
task, not the page: an automated action runs at the task's admitted class only when

(a) the page it runs on — its origin, and its path where the task declares one — is inside
    the scope recorded for *this* task (``TaskScope``), and a link/submit's destination is
    too;
(b) the target is the element VAN actually classified: the Harness bound it (``binding``:
    CDP backendNodeId + a digest of what was classified) and re-verifies that binding, the
    hit test and the page at the moment it acts (review I5 MAJOR-2);
(c) it does not cross the money/commitment boundary (``action_risk`` A4 and the payment
    boundary, applied by the lanes before this gate — payments first).

Anything else goes to lane 4 (owner takeover / policy refusal) with a typed reason
(``TASK_SCOPE:<code>``). ``action_risk`` stays as defence in depth.

Where the scope comes from
==========================

* **Hermes declares it when it creates the task** — ``POST /v1/browser/tasks`` field
  ``scope`` (MCP tool ``browser_task_create``): a list of URL prefixes such as
  ``["https://docs.example.com/guide/"]``. Each is an origin (scheme, host, port) and an
  optional path prefix. Every origin's host must be the task's ``target_domain`` or a
  subdomain of it (the Harness refuses anything else anyway). Recorded ``source:
  HERMES_DECLARED``.
* **When Hermes declares none**, creation records the scope the task already names: its
  ``target_domain`` as the single origin ``https://<target_domain>`` with no path limit
  (``source: TARGET_DOMAIN``). This is task truth Hermes supplied (the domain the task was
  admitted for), not an allowlist anyone maintains.
* **Owner approvals widen it for that task only**: every domain in a
  ``browser_scope_authorizations`` row the owner's decision produced for the task is added
  as ``https://<domain>`` with ``source`` ``OWNER_APPROVED:<authorization id>`` when the
  task is loaded (``BrowserApi._task_scope``); nothing rewrites the recorded scope.
* **An assignment can only narrow it**: ``/v1/browser/assignments`` keeps only the entries
  whose host is in the assignment's ``allowed_domains``.

Missing scope fails closed
==========================

A task whose truth carries no scope (a row created before this rule, ``scope_json`` NULL,
unparseable, or with no entries) is out of scope for every action: ``TASK_SCOPE_MISSING``,
lane 4. Nothing guesses a scope for it.

The Harness enforces (a) and (b) again, atomically, at the moment it acts (it receives the
scope and the binding with each ``/click``, ``/press`` and ``/fill``), so a page that moves
between the gateway's check and the action is refused there too.
"""

from __future__ import annotations

import json
from typing import Any, Iterable
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

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


#: Operations the gate covers. ``done``/``abstain`` act on nothing.
GATED_OPERATIONS = frozenset({"click", "fill", "select", "press_key", "scroll", "navigate"})
#: Operations whose target must be the bound, Harness-verified element.
BOUND_OPERATIONS = frozenset({"click", "fill", "select", "press_key"})

SOURCE_HERMES = "HERMES_DECLARED"
SOURCE_TARGET_DOMAIN = "TARGET_DOMAIN"


class TaskScopeError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ScopeEntry(BaseModel):
    """One origin, optionally limited to a path prefix."""

    origin: str
    path_prefix: str | None = None
    source: str = SOURCE_HERMES


class TaskScope(BaseModel):
    """The pages a browser task may act on — part of the task's own truth."""

    entries: list[ScopeEntry] = Field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def to_wire(self) -> dict[str, Any]:
        """What the Harness receives with an action (it re-checks the page against it)."""
        return {"entries": [{"origin": e.origin, "path_prefix": e.path_prefix} for e in self.entries]}

    def hosts(self) -> set[str]:
        return {urlsplit(e.origin).hostname or "" for e in self.entries}

    def narrowed_to_hosts(self, hosts: Iterable[str]) -> "TaskScope":
        allowed = {str(h).strip().lower().rstrip(".") for h in hosts}
        return TaskScope(entries=[e for e in self.entries if (urlsplit(e.origin).hostname or "") in allowed])

    def with_origin(self, host: str, source: str) -> "TaskScope":
        origin = f"https://{host.strip().lower().rstrip('.')}"
        if any(e.origin == origin and e.path_prefix is None for e in self.entries):
            return self
        return TaskScope(entries=[*self.entries, ScopeEntry(origin=origin, path_prefix=None, source=source)])


def _host_within(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def parse_scope_entry(raw: str, target_domain: str) -> ScopeEntry:
    """``https://host[:port][/path/prefix]`` -> ScopeEntry. No query, fragment or userinfo;
    the path must already be in the normal form the browser would load (review I6 M3: no
    dot segments, backslashes or encoded separators), since the prefix is compared with
    the normalised path of every page and destination."""
    text = str(raw or "").strip()
    try:
        parts = urlsplit(text)
        parts.port  # noqa: B018 - raises on a malformed port
    except ValueError as exc:
        raise TaskScopeError("TASK_SCOPE_ENTRY_INVALID") from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise TaskScopeError("TASK_SCOPE_ENTRY_SCHEME_OR_HOST_INVALID")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise TaskScopeError("TASK_SCOPE_ENTRY_INVALID")
    whatwg = _vs_parse(text)
    if whatwg is None:
        raise TaskScopeError("TASK_SCOPE_ENTRY_INVALID")
    domain = str(target_domain or "").strip().lower().rstrip(".")
    if not domain or not _host_within(whatwg[1], domain):
        raise TaskScopeError("TASK_SCOPE_OUTSIDE_TARGET_DOMAIN")
    path = parts.path or "/"
    if whatwg[3] != path or _vs_ambiguous(path):
        raise TaskScopeError("TASK_SCOPE_ENTRY_PATH_NOT_NORMAL")
    return ScopeEntry(origin=_vs_origin(whatwg), path_prefix=path if path != "/" else None)


def scope_for_new_task(target_domain: str, declared: list[str] | None) -> TaskScope:
    """The scope recorded when a task is created (see the module docstring)."""
    if declared:
        entries = [parse_scope_entry(item, target_domain) for item in declared]
        return TaskScope(entries=entries)
    domain = str(target_domain or "").strip().lower().rstrip(".")
    if not domain:
        raise TaskScopeError("TASK_SCOPE_OUTSIDE_TARGET_DOMAIN")
    return TaskScope(entries=[ScopeEntry(origin=f"https://{domain}", path_prefix=None, source=SOURCE_TARGET_DOMAIN)])


def load_scope(raw: Any) -> TaskScope | None:
    """``browser_tasks.scope_json`` -> TaskScope, or None (missing/unreadable = no scope)."""
    if raw is None or raw == "":
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        scope = TaskScope.model_validate(data)
    except (ValueError, TypeError):
        return None
    return scope if scope.entries else None


def url_scope_violation(scope: TaskScope | None, url: str | None, *, what: str = "PAGE", base: str | None = None) -> str | None:
    """None when ``url`` (resolved against ``base``) is inside ``scope``; otherwise the typed
    reason. The rule is the shared ``_vs_scope_violation`` the Harness runs too."""
    if scope is None or not scope.entries:
        return "TASK_SCOPE_MISSING"
    return _vs_scope_violation(scope.to_wire()["entries"], url, what, base)


def element_destination(element: dict[str, Any] | None) -> str | None:
    """Where activating the element navigates: a link's href, or the submission URL of a
    submit control (formaction over the form's action). None when it does neither."""
    if not isinstance(element, dict):
        return None
    form = element.get("form") if isinstance(element.get("form"), dict) else None
    if form and element.get("submits") is True:
        return str(form.get("formaction") or form.get("action") or "") or "(form-without-action)"
    attributes = element.get("attributes") if isinstance(element.get("attributes"), dict) else {}
    href = attributes.get("href") or element.get("href")
    return str(href) if href else None


def task_scope_gate(
    scope: TaskScope | None,
    *,
    operation: str,
    element: dict[str, Any] | None = None,
    page_url: str | None = None,
    navigate_url: str | None = None,
    activates: bool = True,
) -> str | None:
    """Rules (a) and (b), gateway side. None = the action may run at the admitted class.

    ``element`` is the Harness-reported target (the focused element for ``press_key``),
    carrying ``binding`` and ``page_url`` from ``/describe``. ``scroll`` has no target; its
    page is checked by the Harness, which receives the scope with the call. ``activates``
    (press_key): the key activates the focused element (Enter/Space), so its destination
    counts — including Enter in a field, which submits the field's form.
    """
    if operation not in GATED_OPERATIONS:
        return None
    if scope is None or not scope.entries:
        return "TASK_SCOPE_MISSING"
    if operation == "navigate":
        return url_scope_violation(scope, navigate_url, what="NAVIGATE")
    if operation == "scroll":
        return None
    if not isinstance(element, dict):
        return "TASK_SCOPE_TARGET_UNRESOLVED"
    binding = element.get("binding")
    if not isinstance(binding, dict) or not isinstance(binding.get("backend_node_id"), int) or not binding.get("digest"):
        return "TASK_SCOPE_TARGET_NOT_BOUND"
    page = page_url or element.get("page_url")
    violation = url_scope_violation(scope, page, what="PAGE")
    if violation is not None:
        return violation
    if operation == "click" or (operation == "press_key" and activates):
        destination = element_destination(element)
        form = element.get("form") if isinstance(element.get("form"), dict) else None
        if destination is None and operation == "press_key" and form:
            # Enter in a field submits its form (implicit submission).
            destination = str(form.get("action") or "") or "(form-without-action)"
        if destination is not None:
            if destination == "(form-without-action)":
                destination = page
            # Resolved against the page the way the browser resolves it (review I6 M3).
            violation = url_scope_violation(scope, destination, what="DESTINATION", base=page)
            if violation is not None:
                return violation
    return None


__all__ = [
    "BOUND_OPERATIONS",
    "GATED_OPERATIONS",
    "ScopeEntry",
    "TaskScope",
    "TaskScopeError",
    "element_destination",
    "load_scope",
    "parse_scope_entry",
    "scope_for_new_task",
    "task_scope_gate",
    "url_scope_violation",
]
