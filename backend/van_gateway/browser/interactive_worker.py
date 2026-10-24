"""Core-issued deterministic work on the owner's explicitly delegated stream target."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time

from van_gateway.browser.agent_grant import domain_allowed
from van_gateway.browser.models import BrowserObservation, InjectionAssessment
from van_gateway.browser.subagent import ProposedAction
from van_gateway.browser.worker import DETERMINISTIC_TIERS, SemanticWorkerUnavailable
from services.browser_control_agent.agent import Call
from services.browser_control_agent.authority import Operation


def build_profile_control_clients(raw, *, caller_common_name, client_factory=None):
    """Build operator-bound clients; a configured map never falls back across profiles."""
    from services.browser_control_agent.client import BrowserControlClient, ControlClientConfig
    values = json.loads(raw)
    if not isinstance(values, dict):
        raise ValueError("interactive_profile_clients_must_be_map")
    factory = client_factory or BrowserControlClient
    required = {"address", "port", "server_name", "ca_file", "cert_file", "key_file",
                "caller_common_name", "proxy_principal_sha256", "stream_principal_sha256"}
    result, fingerprints = {}, set()
    for alias, binding in values.items():
        if alias not in {"public_research", "authenticated_owner"} or not isinstance(binding, dict) or set(binding) != required:
            raise ValueError("interactive_profile_binding_invalid")
        if binding["caller_common_name"] != caller_common_name:
            raise ValueError("interactive_profile_caller_identity_mismatch")
        for name in ("proxy_principal_sha256", "stream_principal_sha256"):
            value = binding[name]
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) or value in fingerprints:
                raise ValueError("interactive_profile_credentials_must_be_distinct")
            fingerprints.add(value)
        if type(binding["port"]) is not int or not 1 <= binding["port"] <= 65535:
            raise ValueError("interactive_profile_port_invalid")
        if any(not isinstance(binding[name], str) or not binding[name] for name in
               ("address", "server_name", "ca_file", "cert_file", "key_file")):
            raise ValueError("interactive_profile_tls_binding_missing")
        config = ControlClientConfig(**{name: binding[name] for name in
            ("address", "port", "server_name", "ca_file", "cert_file", "key_file")})
        result[alias] = (factory(config), caller_common_name, binding["proxy_principal_sha256"])
    return result


class InteractiveAssignmentFactory:
    def __init__(self, *, producers, store, client=None, caller_common_name=None,
                 proxy_principal_sha256=None, profile_clients=None):
        self.producers = producers
        self.store = store
        self.client = client
        self.caller = caller_common_name
        self.proxy = proxy_principal_sha256
        self.profile_clients = profile_clients or {}

    async def __call__(self, task, assignment, plan, session_id):
        if assignment.goal != task.goal or (task.command_id and assignment.command_id != task.command_id):
            raise ValueError("interactive_assignment_task_intent_mismatch")
        ranks = {"A1": 1, "A2": 2, "A3": 3, "A4": 4, "A5": 5}
        if ranks[assignment.action_class_ceiling.value] > ranks[task.action_class.value]:
            raise ValueError("interactive_assignment_widens_task_authority")
        if assignment.autonomy_tier not in DETERMINISTIC_TIERS:
            raise SemanticWorkerUnavailable("interactive control requires a deterministic admitted plan")
        if plan is None or not plan.steps or len(plan.steps) >= assignment.max_steps:
            raise ValueError("interactive_plan_requires_bounded_steps_and_finish_slot")
        for domain in assignment.allowed_domains:
            if not domain_allowed("https://" + domain + "/", (task.target_domain,)):
                raise ValueError("interactive_assignment_widens_task_domain")
        for step in plan.steps:
            if step.kind not in {"navigate", "read", "observe", "query_dom", "screenshot"}:
                raise ValueError("interactive_plan_operation_unsupported")
            if step.domain not in assignment.allowed_domains:
                raise ValueError("interactive_plan_domain_outside_assignment")
            if step.kind == "navigate" and (not step.url or not domain_allowed(step.url, (step.domain,))):
                raise ValueError("interactive_plan_navigation_outside_domain")
            if step.kind == "query_dom" and (not step.locator or len(step.locator) > 1024):
                raise ValueError("interactive_plan_selector_invalid")
        row = await self.store.fetchone("SELECT active_target_id, profile_alias FROM browser_interactive_sessions WHERE session_id=?", (session_id,))
        if row is None or not row["active_target_id"]:
            raise ValueError("interactive_target_unavailable")
        client, caller, proxy = self.client, self.caller, self.proxy
        if self.profile_clients:
            profile = row["profile_alias"]
            if profile != task.profile_alias or profile not in self.profile_clients:
                raise ValueError("interactive_profile_control_unavailable")
            client, caller, proxy = self.profile_clients[profile]
        if client is None or not caller or not proxy:
            raise ValueError("interactive_control_client_unbound")
        operations = 2 * len(plan.steps)
        if operations > 50:
            raise ValueError("interactive_control_budget_exceeds_limit")
        now = int(time.time() * 1000)
        deadline = assignment.deadline_ms or now + 120_000
        scope = "browser.actuate" if any(s.kind == "navigate" for s in plan.steps) else (
            "browser.evidence" if any(s.kind == "screenshot" for s in plan.steps) else "browser.observe")
        grant = await self.producers.issue_control_grant(task_id=task.task_id, session_id=session_id,
            target_id=row["active_target_id"], caller_common_name=caller,
            proxy_principal_sha256=proxy, scope=scope, step_budget=operations, deadline_ms=deadline)
        return InteractivePlanWorker(task=task, plan=plan, grant=grant, client=client)


class InteractivePlanWorker:
    def __init__(self, *, task, plan, grant, client):
        self.task, self.plan, self.grant, self.client = task, plan, grant, client

    async def propose(self, assignment, history):
        index = len(history)
        if index >= len(self.plan.steps):
            return ProposedAction(kind="finish", domain=assignment.allowed_domains[0],
                action_class=assignment.action_class_ceiling, done=True,
                rationale="Every admitted deterministic step produced a browser observation.")
        step = self.plan.steps[index]
        return ProposedAction(kind=step.kind, domain=step.domain, url=step.url,
            instruction=step.instruction, action_class=assignment.action_class_ceiling,
            payload={"planned_step_index": index})

    async def call(self, operation, params=None):
        grant = self.grant
        return await self.client.invoke(Call(operation=operation, session_id=grant["session_id"],
            target_id=grant["target_id"], lease_id=grant["control_lease_id"],
            lease_generation=grant["control_generation"], task_id=self.task.task_id, params=params or {}))

    async def navigation(self):
        result = await self.call(Operation.OBSERVE_NAVIGATION)
        entries, current = result.get("history"), result.get("current")
        if not isinstance(entries, list) or isinstance(current, bool) or not isinstance(current, int) or not 0 <= current < len(entries):
            raise ValueError("interactive_navigation_observation_invalid")
        url = entries[current].get("url")
        if not isinstance(url, str):
            raise ValueError("interactive_navigation_url_missing")
        return url

    async def execute(self, assignment, action):
        index = action.payload.get("planned_step_index")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.plan.steps):
            raise ValueError("interactive_plan_step_binding_invalid")
        step = self.plan.steps[index]
        if (action.kind, action.domain, action.url) != (step.kind, step.domain, step.url):
            raise ValueError("interactive_plan_proposal_changed")
        before = None
        # The admitted navigation may leave the initial blank or previous page.
        # Its destination is independently fenced by the native control server.
        if step.kind != "navigate":
            before = await self.navigation()
            if not domain_allowed(before, (step.domain,)):
                raise ValueError("interactive_target_outside_task_domain")
        extraction = {}
        if step.kind == "navigate":
            await self.call(Operation.NAVIGATE, {"url": step.url})
            after = await self.navigation()
            if not domain_allowed(after, (step.domain,)):
                raise ValueError("interactive_navigation_effect_outside_task_domain")
            extraction["url"] = after
        elif step.kind in {"read", "observe"}:
            observed = await self.call(Operation.QUERY_ACCESSIBILITY)
            nodes = observed.get("nodes")
            if not isinstance(nodes, list):
                raise ValueError("interactive_accessibility_observation_invalid")
            text = json.dumps(nodes, ensure_ascii=False, separators=(",", ":"))
            if len(text.encode()) > 65_536:
                raise ValueError("interactive_observation_too_large")
            extraction = {"url": before, "accessibility": text}
        elif step.kind == "query_dom":
            observed = await self.call(Operation.QUERY_DOM, {"selector": step.locator})
            if not isinstance(observed.get("found"), bool):
                raise ValueError("interactive_dom_observation_invalid")
            html = observed.get("outer_html", "")
            if not isinstance(html, str) or len(html.encode()) > 65_536:
                raise ValueError("interactive_dom_observation_too_large")
            extraction = {"url": before, "found": observed["found"], "outer_html": html}
        else:
            observed = await self.call(Operation.CAPTURE_EVIDENCE)
            try:
                content = base64.b64decode(observed["screenshot_base64"], validate=True)
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError("interactive_screenshot_observation_invalid") from exc
            if len(content) > 8 * 1024 * 1024 or not content.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("interactive_screenshot_observation_invalid")
            extraction = {"url": before, "screenshot_sha256": hashlib.sha256(content).hexdigest(), "screenshot_bytes": len(content)}
        return BrowserObservation(task_id=self.task.task_id, controls=[], extraction=extraction,
            injection_assessment=InjectionAssessment.NONE_DETECTED)
