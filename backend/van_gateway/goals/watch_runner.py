"""Scheduled read-only public-page watches for OMV-003.

This is deliberately not an agent loop. It performs the fixed sequence:
register public profile → navigate once → read visible text → seal digest evidence →
evaluate the owner-authored condition. It never calls Stagehand, chooses actions, clicks,
fills, logs in, expands scope or mints mutation authority.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import re
import time
from typing import Any
from urllib.parse import urlsplit

from van_gateway.browser.adapters import broker_lease_fence, harness_lease_fence
from van_gateway.browser.models import (
    AutonomyTier, BrowserStrategy, BrowserTaskStatus,
)
from van_gateway.browser.service import (
    BrowserSessionBroker, BrowserTaskService, BrowserTaskTransitionRefused,
)
from van_gateway.models import ActionClass

from .models import Watch, WatchConditionKind, WatchObservation, WatchSourceKind
from .service import GoalService

class _HandedToOwner(Exception):
    """Unit G15 — the watch's page lease came back with a network owner code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_PRICE = re.compile(r"(?:USD\s*|\$)\s*([0-9]{1,9}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)")


class WatchRunner:
    """Execute only due BROWSER watches through the qualified deterministic harness."""

    PROFILE_ALIAS = "public_research"

    def __init__(
        self,
        service: GoalService,
        *,
        tasks: BrowserTaskService,
        broker: BrowserSessionBroker,
        harness: Any,
    ) -> None:
        self.service = service
        self.tasks = tasks
        self.broker = broker
        self.harness = harness

    @staticmethod
    def _visible_text(info: dict[str, Any]) -> str:
        extraction = info.get("extraction")
        if not isinstance(extraction, dict):
            return ""
        return str(extraction.get("visible_text") or "")[:32768]

    @staticmethod
    def _observation(watch: Watch, info: dict[str, Any]) -> Any:
        text = WatchRunner._visible_text(info)
        kind = WatchConditionKind(str(watch.condition.get("kind", "")).upper())
        if kind is WatchConditionKind.TEXT_CONTAINS:
            return text
        if kind in {WatchConditionKind.NUMERIC_ABOVE, WatchConditionKind.NUMERIC_BELOW}:
            match = _PRICE.search(text)
            if match is None:
                raise ValueError("WATCH_PRICE_NOT_FOUND")
            try:
                value = Decimal(match.group(1).replace(",", ""))
            except InvalidOperation as exc:
                raise ValueError("WATCH_PRICE_INVALID") from exc
            if not value.is_finite():
                raise ValueError("WATCH_PRICE_INVALID")
            return float(value)
        # Change/boolean watches compare a compact stable projection rather than retaining
        # whole pages in SQLite. BOOLEAN_TRUE normally arrives through a provider adapter,
        # but if the owner deliberately bound it to a page, non-empty visible text is true.
        if kind is WatchConditionKind.BOOLEAN_TRUE:
            return bool(text.strip())
        normalized = "\n".join(line.rstrip() for line in text.splitlines()).strip()
        return {
            "content_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "title": str(info.get("title") or "")[:512],
        }

    async def run(self, *, now_ms: int | None = None, limit: int = 20) -> dict[str, Any]:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        due = await self.service.due_watches(
            now_ms=now, source_kind=WatchSourceKind.BROWSER, limit=limit
        )
        if not due:
            return {"due": 0, "checked": 0, "triggered": 0, "failed": 0}

        status = await self.harness.status()
        if not bool(getattr(status, "ready", False)):
            for watch in due:
                await self.service.record_observation(
                    watch.watch_id,
                    WatchObservation(
                        success=False,
                        error_code="WATCH_BROWSER_RUNTIME_NOT_READY",
                    ),
                    now_ms=now,
                )
            return {"due": len(due), "checked": 0, "triggered": 0, "failed": len(due)}

        checked = triggered = failed = 0
        await self.broker.register_profile(profile_alias=self.PROFILE_ALIAS, now_ms=now)

        for watch in due:
            task = None
            lease = None
            try:
                parsed = urlsplit(watch.target)
                domain = str(parsed.hostname or "")
                task = await self.tasks.create_task(
                    profile_alias=self.PROFILE_ALIAS,
                    strategy=BrowserStrategy.HARNESS,
                    autonomy_tier=AutonomyTier.L1_HARNESS_DETERMINISTIC,
                    action_class=ActionClass.A1,
                    target_domain=domain,
                    goal="Read one public page for an owner-authored watch; do not interact.",
                    mutating=False,
                    capability_id="owner.watch.public_page",
                    inputs={"watch_id": watch.watch_id},
                    now_ms=now,
                )
                lease = await self.broker.acquire_lease(
                    profile_alias=self.PROFILE_ALIAS, task_id=task.task_id, now_ms=now
                )
                # Review I4 MINOR-A: the navigation carries the lease generation and is
                # re-checked against the broker before it reaches the Harness.
                nav_error: Exception | None = None
                try:
                    with harness_lease_fence(broker_lease_fence(self.broker, lease)):
                        info = await self.harness.navigate(task, watch.target)
                except Exception as exc:  # noqa: BLE001 - re-raised after the lease is back
                    nav_error = exc
                # Unit G15 (review I8 MAJOR-2): the lease — the watch's only Harness call is
                # behind it — is given back before anything is recorded, because an end state
                # is final and the release is where the Harness reports what the page's guard
                # did after that call. A watch never acts, so the page's load-time background
                # writes were dropped and the watch continues (owner answer after review I7,
                # "Block silently, continue"); anything the release still reports (a write
                # after an automated action, a WebSocket it could only detect, a guard it could
                # not keep on) goes to the owner.
                released = await self.broker.release_lease(lease, now_ms=now)
                lease = None
                if released.owner_code is not None:
                    raise _HandedToOwner(released.owner_code)
                if nav_error is not None:
                    raise nav_error
                observation = self._observation(watch, info)
                evidence = await self.tasks.seal_evidence(
                    task=task,
                    kind="watch_observation",
                    url=str(info.get("url") or watch.target),
                    extraction={
                        "watch_id": watch.watch_id,
                        "observation_sha256": hashlib.sha256(
                            repr(observation).encode("utf-8")
                        ).hexdigest(),
                    },
                    now_ms=now,
                )
                result = await self.service.record_observation(
                    watch.watch_id,
                    WatchObservation(observation=observation),
                    now_ms=now,
                )
                # §7 / review I M-2: COMPLETED needs a VERIFIED verdict. This task is a
                # read-only A1 read whose postcondition is the sealed evidence itself, so
                # the task service reads the evidence row back rather than taking ours.
                verdict = await self.tasks.verify_read_only_evidence(
                    task=task, evidence_id=evidence.evidence_id, now_ms=now
                )
                if verdict != "VERIFIED":
                    raise RuntimeError(f"WATCH_EVIDENCE_{verdict}")
                await self.tasks.complete(
                    task_id=task.task_id,
                    status=BrowserTaskStatus.COMPLETED,
                    evidence_pointer=f"browser-evidence://{evidence.evidence_id}",
                    now_ms=now,
                )
                checked += 1
                triggered += 1 if result["triggered"] else 0
            except _HandedToOwner as handed:
                failed += 1
                await self.service.record_observation(
                    watch.watch_id,
                    WatchObservation(success=False, error_code=f"WATCH_OWNER_TAKEOVER:{handed.code}"[:200]),
                    now_ms=now,
                )
                try:
                    await self.tasks.set_working_status(
                        task_id=task.task_id, status=BrowserTaskStatus.WAITING_FOR_OWNER,
                        error_code=f"OWNER_TAKEOVER:{handed.code}"[:200], now_ms=now,
                    )
                except BrowserTaskTransitionRefused:
                    pass  # the task ended elsewhere meanwhile; it stays ended
            except Exception as exc:  # one broken watch cannot stop the scheduler job
                failed += 1
                code = str(exc) if str(exc).startswith("WATCH_") else type(exc).__name__
                await self.service.record_observation(
                    watch.watch_id,
                    WatchObservation(success=False, error_code=code[:200]),
                    now_ms=now,
                )
                if task is not None:
                    try:
                        await self.tasks.complete(
                            task_id=task.task_id,
                            status=BrowserTaskStatus.FAILED,
                            error_code=code[:200],
                            now_ms=now,
                        )
                    except BrowserTaskTransitionRefused:
                        # Review I3 MINOR-3: the task already ended elsewhere (e.g. CANCELLED
                        # mid-run). End states are sticky, so there is nothing to write; the
                        # failure is on the watch's record and the other watches still run.
                        pass
            finally:
                if lease is not None:
                    await self.broker.release_lease(lease, now_ms=now)

        return {
            "due": len(due), "checked": checked,
            "triggered": triggered, "failed": failed,
        }
