"""Owner decision 2026-09-30 — browser actions stay inside the task's own truth.

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
from urllib.parse import urljoin, urlsplit

from pydantic import BaseModel, Field

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


def _origin_of(parts) -> str:
    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").lower().rstrip(".")
    port = parts.port
    default = {"http": 80, "https": 443}.get(scheme)
    return f"{scheme}://{host}" + (f":{port}" if port and port != default else "")


def parse_scope_entry(raw: str, target_domain: str) -> ScopeEntry:
    """``https://host[:port][/path/prefix]`` -> ScopeEntry. No query, fragment or userinfo."""
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
    domain = str(target_domain or "").strip().lower().rstrip(".")
    host = parts.hostname.lower().rstrip(".")
    if not domain or not _host_within(host, domain):
        raise TaskScopeError("TASK_SCOPE_OUTSIDE_TARGET_DOMAIN")
    path = parts.path or ""
    return ScopeEntry(origin=_origin_of(parts), path_prefix=path if path not in ("", "/") else None)


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


def _path_within(path: str, prefix: str | None) -> bool:
    if not prefix:
        return True
    path = path or "/"
    if prefix.endswith("/"):
        return path.startswith(prefix)
    return path == prefix or path.startswith(prefix + "/")


def url_scope_violation(scope: TaskScope | None, url: str | None, *, what: str = "PAGE") -> str | None:
    """None when ``url`` is inside ``scope``; otherwise the typed reason."""
    if scope is None or not scope.entries:
        return "TASK_SCOPE_MISSING"
    if not url:
        return f"TASK_SCOPE_{what}_URL_UNKNOWN"
    try:
        parts = urlsplit(str(url))
        parts.port  # noqa: B018
    except ValueError:
        return f"TASK_SCOPE_{what}_URL_INVALID"
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return f"TASK_SCOPE_{what}_URL_NOT_HTTP"
    origin = _origin_of(parts)
    for entry in scope.entries:
        if entry.origin == origin and _path_within(parts.path, entry.path_prefix):
            return None
    if any(entry.origin == origin for entry in scope.entries):
        return f"TASK_SCOPE_{what}_PATH_OUTSIDE"
    return f"TASK_SCOPE_{what}_ORIGIN_OUTSIDE"


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
            resolved = urljoin(str(page), destination)
            violation = url_scope_violation(scope, resolved, what="DESTINATION")
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
