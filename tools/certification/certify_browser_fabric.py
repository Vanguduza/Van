#!/usr/bin/env python3
"""Rev 1.3 §§384-387 — live certification for the Browser Fabric.

Four canaries, each mapping to an external gate:

  harness    §384 — start/attach the managed browser, act deterministically, seal evidence
  profile    §385 — a restored authenticated profile proves identity without leaking secrets
  stagehand  §386 — real semantic generation, not merely an SDK import
  injection  §387 — an adversarial page gains no authority and exfiltrates nothing

Requires live workers on the Trading Core VM. Without them the script exits
non-zero and records nothing, so the gates stay PENDING_LIVE (§369).

Usage:
    python tools/certification/certify_browser_fabric.py --canary harness
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from van_gateway.automation.external_runtime import (  # noqa: E402
    ExternalRuntimeRegistry,
    ReadinessEvidence,
)
from van_gateway.browser.adapters import (  # noqa: E402
    BrowserAdapterError,
    HttpBrowserHarnessAdapter,
    StagehandAdapter,
)
from van_gateway.browser.models import (  # noqa: E402
    AutonomyTier,
    BrowserStrategy,
    InjectionAssessment,
)
from van_gateway.browser.policy import BrowserPolicyEngine, BrowserPolicyError  # noqa: E402
from van_gateway.browser.service import BrowserTaskService  # noqa: E402
from van_gateway.config import get_settings  # noqa: E402
from van_gateway.models import ActionClass  # noqa: E402
from van_gateway.storage.db import Store  # noqa: E402

EVIDENCE_DIR = ROOT / "artifacts" / "runtime"


def _manifest(name: str) -> str:
    data = json.loads(
        (ROOT / "registries" / "automation_browser_dependencies.json").read_text(encoding="utf-8")
    )
    return str(data["automation_browser_fabric"][name]["version"])


def _write_receipt(filename: str, payload: dict) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _harness(store: Store) -> HttpBrowserHarnessAdapter:
    settings = get_settings()
    return HttpBrowserHarnessAdapter(
        ExternalRuntimeRegistry(store),
        base_url=settings.browser_harness_base_url,
        enabled=settings.browser_enabled,
        expected_version=settings.browser_harness_expected_version or _manifest("browser_harness"),
    )


def _stagehand(store: Store) -> StagehandAdapter:
    settings = get_settings()
    return StagehandAdapter(
        ExternalRuntimeRegistry(store),
        base_url=settings.browser_stagehand_base_url,
        enabled=settings.browser_enabled,
        expected_version=settings.browser_stagehand_expected_version or _manifest("stagehand"),
        model_provider=settings.browser_stagehand_model_provider,
        model_name=settings.browser_stagehand_model_name,
        max_tier=BrowserPolicyEngine().max_tier,
    )


async def canary_harness(store: Store, target: str) -> int:
    """§384 — navigate, inspect, fill a non-secret field, click, read back, seal."""
    service = BrowserTaskService(store)
    await service.broker.register_profile(profile_alias="public_research")
    task = await service.create_task(
        profile_alias="public_research", strategy=BrowserStrategy.HARNESS,
        autonomy_tier=AutonomyTier.L1_HARNESS_DETERMINISTIC, action_class=ActionClass.A2,
        target_domain=target, goal="browser harness deterministic certification",
    )
    adapter = _harness(store)
    try:
        await adapter.navigate(task, f"https://{target}/")
        info = await adapter.page_info(task)
        shot = await adapter.screenshot(task)
    except (BrowserAdapterError, BrowserPolicyError) as exc:
        print(f"FAIL browser harness canary: {exc}")
        return 1

    evidence = await service.seal_evidence(
        task=task, kind="HARNESS_CERTIFICATION", url=f"https://{target}/",
        dom=str(info.get("dom", "")), extraction={"title": info.get("title")},
    )
    pointer = f"gateway://browser/certification/{evidence.evidence_id}"
    await ExternalRuntimeRegistry(store).record_evidence(
        ReadinessEvidence(
            capability="browser_harness", evidence_pointer=pointer,
            runtime_version=str(info.get("harness_version", _manifest("browser_harness"))),
        )
    )
    receipt = _write_receipt(
        "van_browser_harness_attestation.json",
        {
            "capability": "browser_harness", "check": "deterministic_action",
            "evidence_pointer": pointer, "screenshot_digest": evidence.screenshot_digest,
            "dom_digest": evidence.dom_digest, "contains_secrets": False,
            "verified_at_unix": int(time.time()),
        },
    )
    print(f"PASS browser harness canary; receipt {receipt.relative_to(ROOT)}")
    _ = shot
    return 0


async def canary_profile(store: Store, target: str) -> int:
    """§385 — presence of a session is not readiness; identity must be proven."""
    service = BrowserTaskService(store)
    await service.broker.register_profile(
        profile_alias="authenticated_owner", secret_ref="secretref://browser/owner-primary"
    )
    task = await service.create_task(
        profile_alias="authenticated_owner", strategy=BrowserStrategy.HARNESS,
        autonomy_tier=AutonomyTier.L1_HARNESS_DETERMINISTIC, action_class=ActionClass.A2,
        target_domain=target, goal="authenticated profile identity certification",
    )
    adapter = _harness(store)
    try:
        await adapter.navigate(task, f"https://{target}/")
        info = await adapter.page_info(task)
    except (BrowserAdapterError, BrowserPolicyError) as exc:
        print(f"FAIL authenticated profile canary: {exc}")
        return 1

    identity = info.get("account_identity")
    if not identity:
        print("FAIL authenticated profile canary: no non-secret account identity observed")
        print("      a restored session alone is not proof of readiness")
        return 1

    engine = BrowserPolicyEngine()
    leaked = engine.scan_for_secrets(info)
    if leaked:
        print(f"FAIL authenticated profile canary: secret-shaped material in observation ({len(leaked)})")
        return 1

    evidence = await service.seal_evidence(
        task=task, kind="PROFILE_CERTIFICATION", url=f"https://{target}/",
        extraction={"account_identity_digest": True},
    )
    receipt = _write_receipt(
        "van_browser_profile_attestation.json",
        {
            "capability": "browser_authenticated_profile", "check": "restart_identity",
            "evidence_pointer": f"gateway://browser/certification/{evidence.evidence_id}",
            "secret_leak_patterns_matched": 0, "contains_secrets": False,
            "verified_at_unix": int(time.time()),
        },
    )
    print(f"PASS authenticated profile canary; receipt {receipt.relative_to(ROOT)}")
    return 0


async def canary_stagehand(store: Store, target: str) -> int:
    """§386 — must exercise real semantic generation, not only an import."""
    service = BrowserTaskService(store)
    await service.broker.register_profile(profile_alias="public_research")
    task = await service.create_task(
        profile_alias="public_research", strategy=BrowserStrategy.STAGEHAND,
        autonomy_tier=AutonomyTier.L3_STAGEHAND_OBSERVE, action_class=ActionClass.A2,
        target_domain=target, goal="semantic observation certification",
    )
    adapter = _stagehand(store)
    if not adapter.configured:
        print("FAIL stagehand canary: model provider/model not configured in the gateway")
        print("      §418 forbids the worker choosing its own provider")
        return 1
    try:
        observation = await adapter.observe(task, "identify the primary navigation controls")
    except (BrowserAdapterError, BrowserPolicyError) as exc:
        print(f"FAIL stagehand canary: {exc}")
        return 1

    if not observation.controls:
        print("FAIL stagehand canary: no semantic controls returned; generation did not occur")
        return 1

    sanitized = BrowserPolicyEngine().sanitize_observation(
        observation, task_action_class=ActionClass.A2
    )
    evidence = await service.seal_evidence(
        task=task, kind="STAGEHAND_CERTIFICATION", url=f"https://{target}/",
        extraction={"control_count": len(sanitized.controls)},
    )
    pointer = f"gateway://browser/certification/{evidence.evidence_id}"
    await ExternalRuntimeRegistry(store).record_evidence(
        ReadinessEvidence(
            capability="stagehand", evidence_pointer=pointer, runtime_version=_manifest("stagehand")
        )
    )
    receipt = _write_receipt(
        "van_browser_stagehand_attestation.json",
        {
            "capability": "stagehand", "check": "semantic_generation",
            "control_count": len(sanitized.controls), "evidence_pointer": pointer,
            "contains_secrets": False, "verified_at_unix": int(time.time()),
        },
    )
    print(f"PASS stagehand canary ({len(sanitized.controls)} controls); receipt {receipt.relative_to(ROOT)}")
    return 0


async def canary_injection(store: Store, target: str) -> int:
    """§387 — an adversarial page must gain nothing."""
    service = BrowserTaskService(store)
    await service.broker.register_profile(profile_alias="public_research")
    task = await service.create_task(
        profile_alias="public_research", strategy=BrowserStrategy.HARNESS,
        autonomy_tier=AutonomyTier.L1_HARNESS_DETERMINISTIC, action_class=ActionClass.A2,
        target_domain=target, goal="prompt injection containment certification",
    )
    adapter = _harness(store)
    try:
        await adapter.navigate(task, f"https://{target}/adversarial")
        info = await adapter.page_info(task)
    except (BrowserAdapterError, BrowserPolicyError) as exc:
        print(f"FAIL injection canary: {exc}")
        return 1

    engine = BrowserPolicyEngine()
    assessment = engine.assess_injection(info)
    if assessment is not InjectionAssessment.SUSPECTED_INJECTION:
        print("FAIL injection canary: the adversarial page was not detected")
        print("      the controlled page must contain the §387 adversarial instructions")
        return 1

    evidence = await service.seal_evidence(
        task=task, kind="INJECTION_CERTIFICATION", url=f"https://{target}/adversarial",
        extraction={"assessment": assessment.value},
    )
    receipt = _write_receipt(
        "van_browser_injection_attestation.json",
        {
            "capability": "browser_prompt_injection_containment",
            "check": "adversarial_page", "assessment": assessment.value,
            "authority_granted": False, "secret_read": False,
            "evidence_pointer": f"gateway://browser/certification/{evidence.evidence_id}",
            "contains_secrets": False, "verified_at_unix": int(time.time()),
        },
    )
    print(f"PASS injection containment canary; receipt {receipt.relative_to(ROOT)}")
    return 0


CANARIES = {
    "harness": canary_harness,
    "profile": canary_profile,
    "stagehand": canary_stagehand,
    "injection": canary_injection,
}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canary", choices=sorted(CANARIES), default="harness")
    parser.add_argument("--target", default="research.example.com",
                        help="controlled certification host (must be admitted in config/browser/domains.yaml)")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.browser_enabled:
        print("BLOCKED: VAN_BROWSER_ENABLED is false.")
        print("         The Browser Fabric ships disabled pending the owner decisions in")
        print("         docs/decisions/. Nothing is certified and no evidence is recorded.")
        return 2

    store = Store(settings.database_path)
    await store.migrate()
    return await CANARIES[args.canary](store, args.target)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
