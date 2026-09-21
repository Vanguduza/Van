"""Rev 1.5 §13.2 — the narrow API, and the loopback CDP behind it.

The split in this file is the design. `BrowserControlAgent` is the contract Trading Core
calls and it decides nothing about the browser; `CdpTransport` is the part that talks to
Chromium and decides nothing about authority. That way the half that cannot run in this
repository is also the half with no rules in it.

What the agent refuses to be, from §13.2, and why each one is on the list:

    arbitrary shell                  the host runs the owner's browser profile
    raw public CDP websocket         CDP is remote code execution, by design
    filesystem root                  `Page.navigate` will fetch file:/// happily
    Docker socket                    root on the host, one API call away
    unbounded JavaScript execution   `Runtime.evaluate` in a logged-in page

`query_dom` is the one that looks like it might be the last of those and is not: it takes a
selector and returns structured text, and the extraction runs through `DOM.querySelector`
plus `DOM.getOuterHTML` rather than through `Runtime.evaluate`. A version that took an
expression would be the forbidden primitive with a friendlier name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from services.browser_control_agent.authority import (
    ControlAuthority,
    Operation,
    TaskGrant,
)


class CdpTransport(Protocol):
    """Whatever actually speaks to Chromium on 127.0.0.1.

    A Protocol rather than a class because the real one needs a running browser and this
    repository has none. The tests drive a recording double; the production implementation
    lives in `cdp.py` and is `EXTERNAL_RUNTIME` in the ledger until a host runs it.
    """

    async def send(self, target_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class Call:
    """One RPC as it arrives over mTLS. The caller's name is not in here on purpose.

    `caller_common_name` is read from the peer certificate by the transport layer and
    passed separately, because a field a caller can fill in is not an identity.
    """

    operation: Operation
    session_id: str
    target_id: str
    lease_id: str
    lease_generation: int
    task_id: str
    params: dict[str, Any]


class BrowserControlAgent:

    def __init__(self, *, authority: ControlAuthority, cdp: CdpTransport) -> None:
        self._authority = authority
        self._cdp = cdp

    async def invoke(self, *, caller_common_name: str, call: Call) -> dict[str, Any]:
        """Authorize, then act. Never the other way round.

        The ordering is the whole guarantee: there is no path from a request to the browser
        that does not go through `authorize`, and `authorize` raises rather than returning
        a flag that a caller could forget to read.
        """
        task = self._authority.authorize(
            caller_common_name=caller_common_name,
            operation=call.operation,
            session_id=call.session_id,
            lease_id=call.lease_id,
            lease_generation=call.lease_generation,
            task_id=call.task_id,
        )
        handler = _HANDLERS[call.operation]
        return await handler(self._cdp, call, task)


# --------------------------------------------------------------------------- handlers
#
# Each one is a fixed CDP conversation. None of them takes a method name or a script from
# the caller, which is the property that makes this agent narrow rather than a proxy.


async def _attach(cdp: CdpTransport, call: Call, task: TaskGrant) -> dict[str, Any]:
    result = await cdp.send(call.target_id, "Target.attachToTarget", {"flatten": True})
    return {"attached": True, "session": result.get("sessionId"), "task_id": task.task_id}


async def _navigate(cdp: CdpTransport, call: Call, task: TaskGrant) -> dict[str, Any]:
    url = str(call.params.get("url", ""))
    # The scheme allowlist is here rather than in the policy layer because this is the
    # last place before the browser: `file://` reads the host's disk into a page the owner
    # is watching, and `chrome://` reaches the browser's own settings.
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("control_agent_navigate_scheme_refused")
    result = await cdp.send(call.target_id, "Page.navigate", {"url": url})
    return {"frame_id": result.get("frameId"), "steps_remaining": task.steps_remaining}


async def _dispatch_input(cdp: CdpTransport, call: Call, task: TaskGrant) -> dict[str, Any]:
    await cdp.send(call.target_id, "Input.dispatchMouseEvent", dict(call.params))
    return {"dispatched": True, "steps_remaining": task.steps_remaining}


async def _query_dom(cdp: CdpTransport, call: Call, task: TaskGrant) -> dict[str, Any]:
    document = await cdp.send(call.target_id, "DOM.getDocument", {"depth": 1})
    node = await cdp.send(
        call.target_id,
        "DOM.querySelector",
        {"nodeId": document.get("root", {}).get("nodeId"), "selector": str(call.params.get("selector", ""))},
    )
    if not node.get("nodeId"):
        return {"found": False}
    html = await cdp.send(call.target_id, "DOM.getOuterHTML", {"nodeId": node["nodeId"]})
    return {"found": True, "outer_html": html.get("outerHTML", "")}


async def _query_accessibility(cdp: CdpTransport, call: Call, task: TaskGrant) -> dict[str, Any]:
    tree = await cdp.send(call.target_id, "Accessibility.getFullAXTree", {})
    return {"nodes": tree.get("nodes", [])}


async def _observe_navigation(cdp: CdpTransport, call: Call, task: TaskGrant) -> dict[str, Any]:
    history = await cdp.send(call.target_id, "Page.getNavigationHistory", {})
    return {"history": history.get("entries", []), "current": history.get("currentIndex")}


async def _observe_download(cdp: CdpTransport, call: Call, task: TaskGrant) -> dict[str, Any]:
    # Downloads are reported, never fetched through this agent. A file the agent could
    # return is a file the private VCN carries out of the browser profile.
    return {"downloads": call.params.get("known", []), "transfer": "not_through_this_agent"}


async def _capture_evidence(cdp: CdpTransport, call: Call, task: TaskGrant) -> dict[str, Any]:
    shot = await cdp.send(call.target_id, "Page.captureScreenshot", {"format": "png"})
    return {"screenshot_base64": shot.get("data", ""), "task_id": task.task_id}


_HANDLERS = {
    Operation.ATTACH: _attach,
    Operation.NAVIGATE: _navigate,
    Operation.DISPATCH_INPUT: _dispatch_input,
    Operation.QUERY_DOM: _query_dom,
    Operation.QUERY_ACCESSIBILITY: _query_accessibility,
    Operation.OBSERVE_NAVIGATION: _observe_navigation,
    Operation.OBSERVE_DOWNLOAD: _observe_download,
    Operation.CAPTURE_EVIDENCE: _capture_evidence,
}

#: Every CDP method this agent will ever send. The allowlist is the claim "narrow" made
#: checkable: a handler that grew a `Runtime.evaluate` would fail the test that compares
#: this set against what the handlers actually send.
PERMITTED_CDP_METHODS = frozenset(
    {
        "Target.attachToTarget",
        "Page.navigate",
        "Page.getNavigationHistory",
        "Page.captureScreenshot",
        "Input.dispatchMouseEvent",
        "DOM.getDocument",
        "DOM.querySelector",
        "DOM.getOuterHTML",
        "Accessibility.getFullAXTree",
    }
)

#: What must never be reachable, named so the test says why it failed rather than that a
#: set changed. Each of these is an escape from the narrow contract into a general one.
FORBIDDEN_CDP_METHODS = frozenset(
    {
        "Runtime.evaluate",
        "Runtime.callFunctionOn",
        "Runtime.compileScript",
        "Page.addScriptToEvaluateOnNewDocument",
        "Browser.setDownloadBehavior",
        "IO.read",
        "Fetch.continueRequest",
        "Network.setCookies",
        "Storage.getCookies",
    }
)
