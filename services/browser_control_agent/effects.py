"""Fixed, bounded native conversations for sealed effects and independent readback.

No caller script, CDP method, coordinate, or selector is accepted here. Selectors
and values come from the gateway's immutable owner-approved step projection.
"""
from __future__ import annotations
import json
import math


async def unique_node(cdp, target, selector):
    document = await cdp.send(target, "DOM.getDocument", {"depth": 1})
    result = await cdp.send(target, "DOM.querySelectorAll", {"nodeId": document["root"]["nodeId"], "selector": selector})
    nodes = result.get("nodeIds", [])
    if len(nodes) != 1 or type(nodes[0]) is not int:
        raise ValueError("browser_effect_selector_not_unique")
    return nodes[0]


async def safe_input(cdp, target, node):
    result = await cdp.send(target, "DOM.describeNode", {"nodeId": node, "depth": 0})
    description = result.get("node", {})
    attrs = description.get("attributes", [])
    attributes = dict(zip(attrs[::2], attrs[1::2]))
    sensitive = " ".join(str(attributes.get(key, "")) for key in ("type", "name", "id", "autocomplete")).lower()
    if (description.get("nodeName", "").upper() not in {"INPUT", "TEXTAREA"}
        or attributes.get("type", "text").lower() not in {"text", "search", "email", "url", "tel"}
        or "disabled" in attributes or "readonly" in attributes
        or any(word in sensitive for word in ("password", "secret", "token", "otp", "one-time", "credit", "cc-", "csrf", "cvv"))):
        raise ValueError("browser_effect_credential_or_unsupported_field_refused")


async def property_value(cdp, target, node, kind):
    # These two constant functions are bounded getters, not caller JavaScript. They
    # do not enumerate the DOM, access storage/cookies, or accept arbitrary code.
    resolved = await cdp.send(target, "DOM.resolveNode", {"nodeId": node})
    object_id = resolved.get("object", {}).get("objectId")
    if not object_id:
        raise ValueError("browser_effect_node_resolution_failed")
    function = ("function(){return String(this.value).slice(0,4097);}" if kind == "value"
                else "function(){return String(this.textContent).slice(0,4097);}")
    try:
        result = await cdp.send(target, "Runtime.callFunctionOn", {"objectId": object_id,
            "functionDeclaration": function, "returnByValue": True, "silent": True})
        value = result.get("result", {}).get("value")
        if result.get("exceptionDetails") or not isinstance(value, str) or len(value) > 4096:
            raise ValueError("browser_effect_readback_failed")
        return value
    finally:
        await cdp.send(target, "Runtime.releaseObject", {"objectId": object_id})


async def observe(cdp, target, predicate):
    kind = predicate["kind"]
    if kind == "url_equals":
        history = await cdp.send(target, "Page.getNavigationHistory", {})
        index, entries = history.get("currentIndex"), history.get("entries", [])
        actual = entries[index].get("url") if type(index) is int and 0 <= index < len(entries) else None
        return {"kind": kind, "postcondition_matched": actual == predicate["url"], "observed_url": actual}
    node = await unique_node(cdp, target, predicate["selector"])
    if kind == "input_value_equals":
        await safe_input(cdp, target, node)
        value = await property_value(cdp, target, node, "value")
        matched = value == predicate["value"]
    elif kind == "element_text_equals":
        value = await property_value(cdp, target, node, "text")
        matched = value == predicate["text"]
    elif kind == "element_attribute_equals":
        result = await cdp.send(target, "DOM.getAttributes", {"nodeId": node})
        attrs = result.get("attributes", [])
        value = dict(zip(attrs[::2], attrs[1::2])).get(predicate["attribute"])
        matched = value == predicate["value"]
    else:
        raise ValueError("browser_effect_unknown_predicate")
    return {"kind": kind, "postcondition_matched": matched,
        "observed_sha256": __import__("hashlib").sha256(str(value).encode()).hexdigest()}


async def execute(cdp, call, projection, fence):
    step = projection["planned_step"]
    if call.operation.value == "observe_effect":
        await fence()
        result = await observe(cdp, call.target_id, step["postcondition"])
        await fence()
        return {**result, "plan_id": projection["plan_id"], "step_id": step["step_id"],
            "observation_source": "NATIVE_CDP_INDEPENDENT_READBACK"}
    if call.operation.value != step["operation"]:
        raise ValueError("browser_effect_operation_mismatch")
    node = await unique_node(cdp, call.target_id, step["selector"])
    if step["operation"] == "fill_element":
        await safe_input(cdp, call.target_id, node)
        await fence()
        await cdp.send(call.target_id, "DOM.focus", {"nodeId": node})
        await fence()
        await cdp.send(call.target_id, "Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
        await fence()
        await cdp.send(call.target_id, "Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
        await fence()
        await cdp.send(call.target_id, "Input.insertText", {"text": step["text"]})
    else:
        # CDP computes the unique element's geometry; caller coordinates are never
        # accepted. Only a fully visible bounded content quad can be actuated.
        result = await cdp.send(call.target_id, "DOM.getContentQuads", {"nodeId": node})
        quads = result.get("quads", [])
        viewport = projection["authority"]["viewport"]
        if len(quads) != 1 or len(quads[0]) != 8 or any(type(v) not in {int, float} or not math.isfinite(v) for v in quads[0]):
            raise ValueError("browser_effect_geometry_unavailable")
        quad = quads[0]
        if any(not 0 <= quad[i] < viewport["width"] or not 0 <= quad[i+1] < viewport["height"] for i in range(0,8,2)):
            raise ValueError("browser_effect_outside_viewport")
        x, y = sum(quad[::2])/4, sum(quad[1::2])/4
        actual_node = await cdp.send(call.target_id, "DOM.getNodeForLocation", {"x": int(x), "y": int(y), "includeUserAgentShadowDOM": False})
        description = await cdp.send(call.target_id, "DOM.describeNode", {"nodeId": node, "depth": 0})
        if not actual_node.get("backendNodeId") or actual_node["backendNodeId"] != description.get("node", {}).get("backendNodeId"):
            raise ValueError("browser_effect_target_occluded")
        await fence()
        await cdp.send(call.target_id, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await fence()
        await cdp.send(call.target_id, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    await fence()
    return {"effect_dispatched": True, "plan_id": projection["plan_id"],
        "plan_sha256": projection["plan_sha256"], "step_id": step["step_id"],
        "execution_id": projection["execution_id"], "verification": "REQUIRES_INDEPENDENT_READBACK"}
