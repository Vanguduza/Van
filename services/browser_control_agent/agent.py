"""Rev 1.5 §13.2 — the narrow API, and the loopback CDP behind it.

`BrowserControlAgent` holds the testable authority/handler contract; production dispatch
resolves its durable authority through Trading Core and `LoopbackCdp` talks to Chromium.
Source tests can execute the real transport; deployed-host qualification is independent.

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

    Recording doubles test handlers; `cdp.py` supplies the real multiplexed transport.
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
    if result.get('errorText') or result.get('isDownload'):
        raise ValueError('control_agent_navigation_failed')
    observation = None
    if task.allowed_domains:
        wait = getattr(cdp, 'wait_navigation', None)
        if wait is None:
            # Recording transports may implement the same bounded read conversation.
            # Production LoopbackCdp additionally requires the actual loader commit.
            from van_gateway.browser.agent_grant import domain_allowed
            import asyncio
            deadline = asyncio.get_running_loop().time() + 10
            while asyncio.get_running_loop().time() < deadline:
                history = await cdp.send(call.target_id, 'Page.getNavigationHistory', {})
                entries = history.get('entries', [])
                index = history.get('currentIndex', -1)
                if type(index) is int and 0 <= index < len(entries):
                    actual = entries[index].get('url', '')
                    if actual == url:
                        if not domain_allowed(actual, task.allowed_domains):
                            raise ValueError('control_agent_navigation_redirect_outside_task_domain')
                        observation = {'url': actual, 'history': entries, 'current': index}
                        break
                    if not domain_allowed(actual, task.allowed_domains) and actual != 'about:blank':
                        raise ValueError('control_agent_navigation_redirect_outside_task_domain')
                await asyncio.sleep(0.05)
            if observation is None:
                raise ValueError('control_agent_navigation_commit_timeout')
        else:
            observation = await wait(call.target_id, result, url, task.allowed_domains)
    if observation is not None and task.allowed_domains:
        entries, current = _scoped_history(observation['history'], observation['current'], task.allowed_domains)
        observation = {**observation, 'history': entries, 'current': current}
    return {"frame_id": result.get("frameId"), "steps_remaining": task.steps_remaining, "navigation": observation}


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
    entries, current = _scoped_history(history.get('entries', []), history.get('currentIndex'), task.allowed_domains)
    return {"history": entries, "current": current}


def _scoped_history(entries, current, allowed_domains):
    if not allowed_domains:
        return entries, current
    from van_gateway.browser.agent_grant import domain_allowed
    selected = [(index, entry) for index, entry in enumerate(entries) if domain_allowed(entry.get('url', ''), allowed_domains)]
    mapped_current = next((index for index, (original, _) in enumerate(selected) if original == current), None)
    return [entry for _, entry in selected], mapped_current


async def _observe_download(cdp: CdpTransport, call: Call, task: TaskGrant) -> dict[str, Any]:
    # Downloads are reported, never fetched through this agent. A file the agent could
    # return is a file the private VCN carries out of the browser profile.
    observer = getattr(cdp, 'observed_downloads', None)
    observed = observer(call.target_id) if observer else []
    # An empty event cache is not proof that no download exists. Canonical owner
    # downloads are reported by the authenticated native producer to DownloadBroker.
    return {"downloads": observed, "observation_available": bool(observed), "complete_snapshot": False, "transfer": "not_through_this_agent"}


async def _capture_evidence(cdp: CdpTransport, call: Call, task: TaskGrant) -> dict[str, Any]:
    shot = await cdp.send(call.target_id, "Page.captureScreenshot", {"format": "png"})
    return {"screenshot_base64": shot.get("data", ""), "task_id": task.task_id}


async def _planned_effect_requires_durable_broker(cdp, call, task):
    # The in-memory harness cannot seal canonical owner authority. Production's
    # broker-backed dispatcher alone resolves immutable effects.
    raise ValueError("control_planned_effect_requires_durable_broker")


_HANDLERS = {
    Operation.CLICK_ELEMENT: _planned_effect_requires_durable_broker,
    Operation.FILL_ELEMENT: _planned_effect_requires_durable_broker,
    Operation.OBSERVE_EFFECT: _planned_effect_requires_durable_broker,
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
