#!/usr/bin/env python3
"""Live certification for VAN's read-only public web-acquisition runtime.

CONFIGURED is never READY. This script requires a live loopback worker and a
real owner-supplied public canary URL, then persists readiness evidence only
after health/boundary checks and a successful acquisition.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from van_gateway.automation.external_runtime import (  # noqa: E402
    ExternalRuntimeRegistry,
    ReadinessEvidence,
)
from van_gateway.browser.acquisition import (  # noqa: E402
    AcquisitionEvidenceLedger,
    AcquisitionFrontier,
    AcquisitionRoute,
)
from van_gateway.browser.acquisition_adapters import (  # noqa: E402
    AcquisitionRuntimeError,
    HttpAcquisitionRuntimeAdapter,
)
from van_gateway.config import get_settings  # noqa: E402
from van_gateway.storage.db import Store  # noqa: E402

SERVICE_VERSION = "van-web-acquisition-worker/1.1.0"
EVIDENCE_DIR = ROOT / "artifacts" / "runtime"


async def run(target_url: str, crawl_url: str | None = None) -> int:
    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        print("FAIL: --url must be an http(s) public canary URL")
        return 2
    if crawl_url is not None:
        crawl_parsed = urlparse(crawl_url)
        if crawl_parsed.scheme not in {"http", "https"} or not crawl_parsed.hostname:
            print("FAIL: --crawl-url must be an http(s) public canary URL")
            return 2

    settings = get_settings()
    if not settings.browser_enabled:
        print("BLOCKED: VAN_BROWSER_ENABLED is false; no evidence recorded.")
        return 2

    store = Store(settings.database_path)
    await store.migrate()
    registry = ExternalRuntimeRegistry(store)
    adapter = HttpAcquisitionRuntimeAdapter(
        registry,
        base_url=settings.browser_acquisition_base_url,
        enabled=settings.browser_enabled,
        expected_version=settings.browser_acquisition_expected_version or SERVICE_VERSION,
    )

    try:
        health = await adapter.probe_health()
    except AcquisitionRuntimeError as exc:
        print(f"FAIL acquisition health: {exc}")
        return 1

    observed_service = str(health.get("service") or "")
    if observed_service != SERVICE_VERSION:
        print(f"FAIL service version mismatch: {observed_service!r} != {SERVICE_VERSION!r}")
        return 1
    if str(health.get("scrapling") or "") != "0.4.15":
        print("FAIL Scrapling runtime is not pinned to 0.4.15")
        return 1
    if str(health.get("crawlee") or "") != "1.10.2":
        print("FAIL Crawlee runtime is not pinned to 1.10.2")
        return 1

    frontier = AcquisitionFrontier(store)
    item = await frontier.enqueue(
        target_url,
        profile_alias="public_research",
        source="LIVE_CERTIFICATION",
        priority=100,
        max_attempts=1,
    )
    try:
        result = await adapter.fetch_http(item)
    except AcquisitionRuntimeError as exc:
        print(f"FAIL acquisition canary: {exc}")
        return 1

    digest = str(result.get("content_digest") or "")
    if not digest.startswith("sha256:") or int(result.get("byte_size") or 0) <= 0:
        print("FAIL acquisition canary returned no content-addressed payload")
        return 1
    if result.get("contains_secrets") is not False:
        print("FAIL acquisition canary violated the secret boundary")
        return 1

    ledger = AcquisitionEvidenceLedger(store)
    evidence = await ledger.record(
        item_id=item.item_id,
        kind="WEB_ACQUISITION_RUNTIME_CERTIFICATION",
        content_digest=digest,
        source_url=target_url,
        byte_size=int(result["byte_size"]),
        detail={
            "service": observed_service,
            "scrapling": health.get("scrapling"),
            "crawlee": health.get("crawlee"),
            "katana": health.get("katana"),
            "auth_surface": health.get("auth_surface"),
            "challenge_solver_enabled": health.get("challenge_solver_enabled"),
        },
    )
    chain = await ledger.verify_chain()
    if chain.get("ok") is not True:
        print(f"FAIL acquisition evidence chain: {chain}")
        return 1

    crawl_receipt = None
    if crawl_url is not None:
        crawl_item = await frontier.enqueue(
            crawl_url,
            profile_alias="public_research",
            source="LIVE_CRAWLEE_CERTIFICATION",
            priority=100,
            max_attempts=1,
        )
        try:
            crawl = await adapter.crawl(
                crawl_item,
                max_pages=10,
                max_depth=2,
                max_concurrency=2,
                max_tasks_per_minute=30,
                timeout_seconds=90,
                respect_robots_txt=True,
            )
        except AcquisitionRuntimeError as exc:
            print(f"FAIL Crawlee canary: {exc}")
            return 1
        if crawl.get("contains_secrets") is not False:
            print("FAIL Crawlee canary violated the secret boundary")
            return 1
        if str(crawl.get("crawlee_version") or "") != "1.10.2":
            print("FAIL Crawlee canary version mismatch")
            return 1
        if int(crawl.get("visited_count") or 0) < 1:
            print("FAIL Crawlee canary visited no pages")
            return 1
        if int(crawl.get("max_pages") or 0) != 10:
            print("FAIL Crawlee canary page bound mismatch")
            return 1
        if int(crawl.get("max_depth") or -1) != 2:
            print("FAIL Crawlee canary depth bound mismatch")
            return 1
        if int(crawl.get("max_concurrency") or 0) != 2:
            print("FAIL Crawlee canary concurrency bound mismatch")
            return 1
        if int(crawl.get("max_tasks_per_minute") or 0) != 30:
            print("FAIL Crawlee canary rate bound mismatch")
            return 1
        crawl_digest = str(crawl.get("content_digest") or "")
        if not crawl_digest.startswith("sha256:"):
            print("FAIL Crawlee canary returned no content digest")
            return 1
        crawl_evidence = await ledger.record(
            item_id=crawl_item.item_id,
            kind="WEB_ACQUISITION_CRAWLEE_CERTIFICATION",
            content_digest=crawl_digest,
            source_url=crawl_url,
            route=AcquisitionRoute.CRAWLEE_CRAWL,
            byte_size=int(crawl.get("byte_size") or 0),
            detail={
                "crawlee_version": crawl.get("crawlee_version"),
                "visited_count": crawl.get("visited_count"),
                "discovered_count": crawl.get("discovered_count"),
                "max_pages": crawl.get("max_pages"),
                "max_depth": crawl.get("max_depth"),
                "max_concurrency": crawl.get("max_concurrency"),
                "max_tasks_per_minute": crawl.get("max_tasks_per_minute"),
                "timeout_seconds": crawl.get("timeout_seconds"),
            },
        )
        chain = await ledger.verify_chain()
        if chain.get("ok") is not True:
            print(f"FAIL Crawlee evidence chain: {chain}")
            return 1
        crawl_pointer = f"web-acquisition-evidence://{crawl_evidence.evidence_id}"
        await registry.record_evidence(
            ReadinessEvidence(
                capability="web_acquisition_crawlee",
                evidence_pointer=crawl_pointer,
                runtime_version=str(crawl.get("crawlee_version") or ""),
                contains_secrets=False,
            )
        )
        crawl_receipt = {
            "url_digest": crawl_item.url_digest,
            "visited_count": int(crawl.get("visited_count") or 0),
            "discovered_count": int(crawl.get("discovered_count") or 0),
            "evidence_pointer": crawl_pointer,
            "content_digest": crawl_digest,
            "live_qualified": True,
        }

    pointer = f"web-acquisition-evidence://{evidence.evidence_id}"
    await registry.record_evidence(
        ReadinessEvidence(
            capability="web_acquisition",
            evidence_pointer=pointer,
            runtime_version=observed_service,
            contains_secrets=False,
        )
    )

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema_version": 1,
        "certification": "VAN_WEB_ACQUISITION_RUNTIME",
        "certified_at_unix": int(time.time()),
        "runtime_version": observed_service,
        "scrapling_version": health.get("scrapling"),
        "crawlee_version": health.get("crawlee"),
        "crawlee_ready": bool(health.get("crawlee_ready")),
        "crawlee_canary": crawl_receipt,
        "katana_version": health.get("katana"),
        "katana_ready": bool(health.get("katana_ready")),
        "auth_surface": False,
        "challenge_solver_enabled": False,
        "canary_url_digest": item.url_digest,
        "content_digest": digest,
        "evidence_pointer": pointer,
        "contains_secrets": False,
    }
    path = EVIDENCE_DIR / "van_web_acquisition_live_attestation.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("WEB_ACQUISITION_RUNTIME_GREEN")
    print(path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument(
        "--crawl-url",
        default=None,
        help="Optional public multi-page site used for a bounded Crawlee canary.",
    )
    args = parser.parse_args()
    return asyncio.run(run(args.url, args.crawl_url))


if __name__ == "__main__":
    raise SystemExit(main())
