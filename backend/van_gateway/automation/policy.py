"""Rev 1.3 §§40-41, 105-107, 203-207 — automation policy loaded from repository config.

The policy files were landed by the trading-core bootstrap work
(``config/automation/*``, ``config/browser/*``). This module reads them rather
than restating them, so there is exactly one place where "which nodes, which
domains, which credential classes" is defined.

Everything fails closed: a missing policy file yields a policy that denies, not
one that permits.
"""

from __future__ import annotations

import ipaddress
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[3]
AUTOMATION_CONFIG = REPO_ROOT / "config" / "automation"
BROWSER_CONFIG = REPO_ROOT / "config" / "browser"

#: §203 / config/automation/credentials.yaml.example.
#: C0/C1 are the classes the Security Policy amendment forbids n8n from holding.
CREDENTIAL_CLASSES = ("C0_OWNER_ROOT", "C1_FINANCIAL_EXECUTION", "C2_CANONICAL_SERVICE",
                      "C3_SENSITIVE_INTEGRATION", "C4_LOW_RISK_INTEGRATION")
N8N_FORBIDDEN_CREDENTIAL_CLASSES = frozenset({"C0_OWNER_ROOT", "C1_FINANCIAL_EXECUTION", "C2_CANONICAL_SERVICE"})

#: §207 — SSRF. Blocked before DNS resolution and again after, by the caller.
_DEFAULT_BLOCKED_NETWORKS = (
    "0.0.0.0/8", "10.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
    "192.0.0.0/24", "192.168.0.0/16", "198.18.0.0/15", "224.0.0.0/4", "240.0.0.0/4",
    "::1/128", "fc00::/7", "fe80::/10",
)


class PolicyError(ValueError):
    """Raised when a workflow, domain or credential violates repository policy."""


def _read_yaml(path: Path) -> dict[str, Any]:
    """Minimal YAML reader for the flat policy files this repo uses.

    The gateway has no YAML dependency and the policy files are deliberately a
    simple subset (scalars, nested maps, ``- `` block sequences, inline
    ``[a, b]``). Using a tiny reader keeps the dependency surface of a
    security-relevant path small.
    """
    if not path.is_file():
        return {}
    lines: list[tuple[int, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append((len(raw) - len(raw.lstrip()), stripped))
    block, _ = _parse_block(lines, 0, lines[0][0] if lines else 0)
    return block if isinstance(block, dict) else {}


def _parse_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    """Parse one indentation block, returning the value and the next line index."""
    if index >= len(lines):
        return {}, index

    if lines[index][1].startswith("- "):
        items: list[Any] = []
        while index < len(lines) and lines[index][0] == indent and lines[index][1].startswith("- "):
            items.append(_scalar(lines[index][1][2:]))
            index += 1
        return items, index

    mapping: dict[str, Any] = {}
    while index < len(lines):
        line_indent, line = lines[index]
        if line_indent < indent:
            break
        if line_indent > indent or ":" not in line:
            index += 1
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        index += 1
        if value not in ("", "|", ">", ">-", "|-"):
            mapping[key] = _scalar(value)
            continue
        # Empty value: the child block decides whether this key holds a map or a
        # list. Deciding here rather than assuming a map is what keeps block
        # sequences under a key (`prohibited_effects:\n  - X`) parsing correctly.
        if index < len(lines) and lines[index][0] > line_indent:
            child, index = _parse_block(lines, index, lines[index][0])
            mapping[key] = child
        else:
            mapping[key] = {}
    return mapping, index


def _scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [_scalar(v) for v in inner.split(",")] if inner else []
    if value in ("{}", "[]"):
        return {} if value == "{}" else []
    low = value.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~", "none"):
        return None
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


@dataclass(frozen=True)
class NodeAllowlist:
    """§41 — deny by default."""

    allowed: frozenset[str] = frozenset()
    denied: frozenset[str] = frozenset()
    community_allowed: bool = False
    generated_code_allowed: bool = False
    http_requires_domain_policy: bool = True

    def check(self, node_type: str) -> None:
        if node_type in self.denied:
            raise PolicyError(f"node_explicitly_denied:{node_type}")
        if node_type not in self.allowed:
            raise PolicyError(f"node_not_allowlisted:{node_type}")


@dataclass(frozen=True)
class DomainPolicy:
    """§§106, 205-207 — default-deny egress with SSRF guards."""

    default_deny: bool = True
    ssrf_enabled: bool = True
    blocked_networks: tuple[str, ...] = _DEFAULT_BLOCKED_NETWORKS
    admitted: frozenset[str] = frozenset()

    def check_domain(self, domain: str | None) -> None:
        if domain is None:
            return
        host = domain.strip().lower()
        if not host:
            raise PolicyError("external_domain_empty")
        if self.ssrf_enabled:
            self._reject_literal_ip(host)
        if host not in self.admitted:
            raise PolicyError(f"external_domain_not_admitted:{host}")

    def check_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("https",):
            raise PolicyError(f"external_scheme_not_permitted:{parsed.scheme or 'none'}")
        self.check_domain(parsed.hostname)

    def _reject_literal_ip(self, host: str) -> None:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return
        for network in self.blocked_networks:
            try:
                if address in ipaddress.ip_network(network, strict=False):
                    raise PolicyError(f"ssrf_blocked_address:{host}")
            except ValueError:
                continue
        # A bare literal IP is never an admitted domain name, so reject anyway.
        raise PolicyError(f"ssrf_literal_ip_denied:{host}")


@dataclass(frozen=True)
class AutomationPolicy:
    """§347 — the compiled view of ``config/automation/policy.yaml``."""

    policy_version: str = "van-automation-policy-unloaded"
    allowed_action_classes: frozenset[str] = frozenset()
    prohibited_effects: frozenset[str] = frozenset()
    cold_auto_admit: dict[str, bool] = field(default_factory=dict)
    max_steps: int = 0
    max_branches: int = 0
    max_external_domains: int = 0
    engine_success_is_owner_success: bool = False
    consequential_effects_require_verifier: bool = True
    community_nodes_allowed: bool = False
    generated_code_nodes_allowed: bool = False
    nodes: NodeAllowlist = field(default_factory=NodeAllowlist)
    domains: DomainPolicy = field(default_factory=DomainPolicy)

    def may_auto_admit(self, action_class: str) -> bool:
        """§36 — only A1/A2 may auto-admit, and only if policy says so."""
        return bool(self.cold_auto_admit.get(action_class, False))


def _load_node_allowlist() -> NodeAllowlist:
    path = AUTOMATION_CONFIG / "node_allowlist.json"
    if not path.is_file():
        return NodeAllowlist()
    data = json.loads(path.read_text(encoding="utf-8"))
    return NodeAllowlist(
        allowed=frozenset(data.get("allowed_official_nodes", [])),
        denied=frozenset(data.get("explicitly_denied_nodes", [])),
        community_allowed=bool(data.get("community_nodes_allowed", False)),
        generated_code_allowed=bool(data.get("generated_code_nodes_allowed", False)),
        http_requires_domain_policy=bool(data.get("http_request_requires_domain_policy", True)),
    )


def _load_domain_policy() -> DomainPolicy:
    data = _read_yaml(AUTOMATION_CONFIG / "domains.yaml")
    ssrf = data.get("ssrf") or {}
    blocked_raw = str(ssrf.get("blocked_ip_ranges", "default"))
    extra = tuple(part.strip() for part in blocked_raw.split(",") if part.strip() and part.strip() != "default")
    admitted = data.get("external_domains") or {}
    return DomainPolicy(
        default_deny=str(data.get("default_external_policy", "deny_until_admitted")).startswith("deny"),
        ssrf_enabled=bool(ssrf.get("enabled", True)),
        blocked_networks=_DEFAULT_BLOCKED_NETWORKS + extra,
        admitted=frozenset(admitted.keys()) if isinstance(admitted, dict) else frozenset(),
    )


@lru_cache(maxsize=1)
def load_automation_policy() -> AutomationPolicy:
    data = _read_yaml(AUTOMATION_CONFIG / "policy.yaml")
    if not data:
        # Fail closed: no policy file means nothing compiles.
        return AutomationPolicy(nodes=_load_node_allowlist(), domains=_load_domain_policy())
    limits = data.get("workflow_limits") or {}
    verification = data.get("verification") or {}
    community = data.get("community_nodes") or {}
    code = data.get("code_nodes") or {}
    cold = data.get("cold_auto_admit") or {}
    return AutomationPolicy(
        policy_version=str(data.get("policy_version", "van-automation-policy-1")),
        allowed_action_classes=frozenset(str(c) for c in (data.get("allowed_action_classes") or [])),
        prohibited_effects=frozenset(str(e) for e in (data.get("prohibited_effects") or [])),
        cold_auto_admit={str(k): bool(v) for k, v in cold.items()},
        max_steps=int(limits.get("max_steps", 0)),
        max_branches=int(limits.get("max_branches", 0)),
        max_external_domains=int(limits.get("max_external_domains", 0)),
        engine_success_is_owner_success=bool(verification.get("engine_success_is_owner_success", False)),
        consequential_effects_require_verifier=bool(
            verification.get("consequential_effects_require_postcondition_verifier", True)
        ),
        community_nodes_allowed=bool(community.get("allowed", False)),
        generated_code_nodes_allowed=bool(code.get("generated_allowed", False)),
        nodes=_load_node_allowlist(),
        domains=_load_domain_policy(),
    )


@dataclass(frozen=True)
class BrowserPolicy:
    """§§182-185, 378, 407 — browser profile and domain policy."""

    policy_version: str = "van-browser-domains-unloaded"
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    admitted_domains: frozenset[str] = frozenset()
    mutate_default_deny: bool = True
    download_default_deny: bool = True
    raw_cookie_export_forbidden: bool = True
    session_leases_required: bool = True
    #: Owner decision 2026-09-18 (VAN-ADOPT-STAGEHAND-001): autonomy is permitted
    #: as a Hermes-managed subagent, so the ceiling is L5. The bounds that keep it
    #: subordinate — assigned goal, domain scope, step budget — are enforced by
    #: browser/subagent.py, not by holding the tier down.
    max_autonomy_tier: str = "L5"

    def check_profile(self, alias: str) -> dict[str, Any]:
        profile = self.profiles.get(alias)
        if profile is None:
            raise PolicyError(f"browser_profile_not_admitted:{alias}")
        return profile

    def check_mutation(self, alias: str) -> None:
        profile = self.check_profile(alias)
        if str(profile.get("mutation", "forbidden")) == "forbidden":
            raise PolicyError(f"browser_profile_mutation_forbidden:{alias}")


@lru_cache(maxsize=1)
def load_browser_policy() -> BrowserPolicy:
    profiles_data = _read_yaml(BROWSER_CONFIG / "profiles.yaml")
    domains_data = _read_yaml(BROWSER_CONFIG / "domains.yaml")
    runtime = profiles_data.get("runtime") or {}
    defaults = domains_data.get("default_policy") or {}
    admitted = domains_data.get("admitted_domains") or {}
    tier = os.environ.get("VAN_BROWSER_SEMANTIC_MAX_TIER", "L5").strip().upper()
    if tier not in ("L0", "L1", "L2", "L3", "L4", "L5"):
        # An unrecognised value falls back to the deterministic tier rather than
        # the ceiling: a typo must never widen autonomy.
        tier = "L3"
    return BrowserPolicy(
        policy_version=str(domains_data.get("policy_version", "van-browser-domains-1")),
        profiles=profiles_data.get("profiles") or {},
        admitted_domains=frozenset(admitted.keys()) if isinstance(admitted, dict) else frozenset(),
        mutate_default_deny=str(defaults.get("mutate", "deny")).startswith("deny"),
        download_default_deny=str(defaults.get("download", "deny")).startswith("deny"),
        raw_cookie_export_forbidden=str(runtime.get("raw_cookie_export", "forbidden")) == "forbidden",
        session_leases_required=bool(runtime.get("session_leases_required", True)),
        max_autonomy_tier=tier,
    )


def reset_policy_cache() -> None:
    """Test hook: policies are cached because they are read on every compile."""
    load_automation_policy.cache_clear()
    load_browser_policy.cache_clear()


__all__ = [
    "AutomationPolicy",
    "BrowserPolicy",
    "CREDENTIAL_CLASSES",
    "DomainPolicy",
    "N8N_FORBIDDEN_CREDENTIAL_CLASSES",
    "NodeAllowlist",
    "PolicyError",
    "load_automation_policy",
    "load_browser_policy",
    "reset_policy_cache",
]
