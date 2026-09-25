"""VAN-DEV-002 — DIAL owner decisions and blockers, raised in VAN's one Attention queue.

DIAL-side approvals and blockers are not a second list on the phone (VAN-DEVCC-R1 §2.2):
they are Attention items with source `dial-dev`, so the owner's "needs me" view stays one
view. This worker keeps that queue in step with DIAL's projection:

* it consumes DIAL's SSE `/v1/dev/events` and, when tasks or decisions change (and once on
  every connect, which is what makes a reconnect rehydrate rather than drift), reads each
  admitted project's `tasks?view=needs_me`;
* each owner item becomes an Attention upsert keyed
  `dial-dev:<kind>:<task_id|decision_id>:<projection_revision_of_origin>`, so a re-read of
  the same condition is the same item and a genuinely new one is a new item;
* an item closes **only** when a later projection shows it `APPLIED` — never on tap, never
  because it merely stopped being listed. Absence without evidence leaves it open.

It never acts on DIAL. The only DIAL calls it makes are GETs.

Projection shapes this worker reads (DIAL's projection server is held to them):

    GET /v1/dev/projects                         data.projects[].project_id
    GET /v1/dev/projects/{p}/tasks?view=needs_me data.tasks[]: {task_id, title?, state?,
                                                 critical_path?, owner_items[]}
    GET /v1/dev/tasks/{taskId}                   data.task_id, data.owner_items[]

    owner_item = {kind: approval|blocker|finding|lease_bypass, decision_id?, title?,
                  finding_domain?: security|money|health|..., critical_path?,
                  origin_projection_revision?, resolution_state?:
                  OPEN|ACCEPTED|APPLIED|REJECTED|SUPERSEDED}
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

import httpx

from van_gateway.attention.engine import AttentionEngine
from van_gateway.degraded.registry import DegradedRegistry
from van_gateway.dial_dev import degraded as dial_degraded
from van_gateway.dial_dev.client import DialDevClient, DialDevDisabled, DialDevUnavailable
from van_gateway.dial_dev.config import ENVELOPE_KEYS, UPSTREAM_PREFIX, valid_identifier
from van_gateway.models import AttentionSeverity, AttentionState, DegradedCode

log = logging.getLogger("van_gateway.dial_dev.attention")

SOURCE = "dial-dev"
DEEP_LINK = "van://work/dev/tasks/{task_id}"

KINDS: frozenset[str] = frozenset({"approval", "blocker", "finding", "lease_bypass"})
#: §2.2 — findings in these domains interrupt the owner.
URGENT_DOMAINS: frozenset[str] = frozenset({"security", "money", "health"})
#: The one resolution state that closes an item.
APPLIED = "APPLIED"
#: What in an event's `changed[]` can move an owner item.
SYNC_TRIGGERS: frozenset[str] = frozenset({"tasks", "decisions", "security", "leases"})


def severity_for(item: dict[str, Any], task: dict[str, Any]) -> AttentionSeverity:
    """§2.2, in precedence order.

    security/money/health finding or lease-bypass alert → URGENT;
    blocker on the critical path → BLOCKER;
    everything else (WAITING_OWNER approvals, off-path blockers) → FOLLOW_UP.
    """
    kind = item.get("kind")
    domain = str(item.get("finding_domain") or "").lower()
    if kind == "lease_bypass" or domain in URGENT_DOMAINS:
        return AttentionSeverity.URGENT
    critical = bool(item.get("critical_path", task.get("critical_path", False)))
    if kind == "blocker" and critical:
        return AttentionSeverity.BLOCKER
    return AttentionSeverity.FOLLOW_UP


def _revision(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > 200 or any(ch.isspace() for ch in value):
        return None
    return value


def _identity(item: dict[str, Any], task_id: str) -> tuple[str, str] | None:
    kind = item.get("kind")
    if kind not in KINDS:
        return None
    decision_id = item.get("decision_id")
    if decision_id is not None:
        if not isinstance(decision_id, str) or not valid_identifier(decision_id):
            return None
        return kind, decision_id
    return kind, task_id


def dedupe_key(kind: str, ident: str, origin_revision: str) -> str:
    return f"{SOURCE}:{kind}:{ident}:{origin_revision}"


async def parse_sse(lines: AsyncIterator[str]) -> AsyncIterator[dict[str, Any] | None]:
    """Yield one decoded `data:` payload per SSE event; None for an undecodable one."""
    data: list[str] = []
    async for line in lines:
        if line == "":
            if data:
                raw = "\n".join(data)
                data = []
                try:
                    decoded = json.loads(raw)
                except ValueError:
                    yield None
                    continue
                yield decoded if isinstance(decoded, dict) else None
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if field == "data":
            data.append(value[1:] if value.startswith(" ") else value)


class DialDevAttentionIngest:
    def __init__(
        self,
        client: DialDevClient,
        attention: AttentionEngine,
        *,
        degraded: DegradedRegistry | None = None,
        events: Any | None = None,
        backoff_initial_s: float = 1.0,
        backoff_max_s: float = 60.0,
    ) -> None:
        self.client = client
        self.attention = attention
        self.degraded = degraded
        self.events = events
        self.backoff_initial_s = backoff_initial_s
        self.backoff_max_s = backoff_max_s
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        #: Observable for tests and /health-style inspection.
        self.connects = 0
        self.syncs = 0

    # ---------------------------------------------------------------- lifecycle

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping = asyncio.Event()
            self._task = asyncio.create_task(self.run(), name="dial-dev-attention-ingest")

    async def stop(self, grace_s: float = 2.0) -> None:
        """Stop at a boundary when possible: a sync in flight finishes its writes.

        Only a worker still blocked on the open stream after the grace period is cancelled,
        and a read is the one thing safe to abandon half way.
        """
        self._stopping.set()
        task, self._task = self._task, None
        if task is not None:
            if not task.done():
                await asyncio.wait({task}, timeout=grace_s)
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutting down
                pass

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def _stream_down(self, down: bool) -> None:
        if self.degraded is not None:
            self.degraded.set(DegradedCode.DIAL_DEV_EVENT_STREAM_DOWN, down)

    async def _pause(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stopping.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def run(self) -> None:
        """Consume DIAL's event stream until stopped, reconnecting with backoff."""
        backoff = self.backoff_initial_s
        while not self._stopping.is_set():
            try:
                stream = await self.client.open_stream(f"{UPSTREAM_PREFIX}/events")
            except DialDevDisabled:
                return
            except DialDevUnavailable as exc:
                log.warning("dial_dev event stream unavailable: %s", exc.reason)
                self._stream_down(True)
                await self._pause(backoff)
                backoff = min(backoff * 2, self.backoff_max_s)
                continue
            try:
                if stream.response.status_code != 200:
                    raise DialDevUnavailable("upstream_error")
                self.connects += 1
                self._stream_down(False)
                backoff = self.backoff_initial_s
                # Rehydrate on every (re)connect: whatever changed while disconnected is
                # read from the projection, not replayed from memory.
                await self.sync_safely()
                async for event in parse_sse(stream.lines()):
                    if self._stopping.is_set():
                        break
                    if self._should_sync(event):
                        await self.sync_safely()
            except asyncio.CancelledError:
                raise
            except (DialDevUnavailable, httpx.HTTPError) as exc:
                log.warning("dial_dev event stream dropped: %s", type(exc).__name__)
            finally:
                await stream.close()
            if self._stopping.is_set():
                break
            self._stream_down(True)
            await self._pause(backoff)
            backoff = min(backoff * 2, self.backoff_max_s)

    @staticmethod
    def _should_sync(event: dict[str, Any] | None) -> bool:
        if event is None:
            return True  # undecodable: re-reading is the safe answer
        changed = event.get("changed")
        if not isinstance(changed, list):
            return True
        return any(str(item) in SYNC_TRIGGERS for item in changed)

    # --------------------------------------------------------------------- sync

    async def sync_safely(self) -> dict[str, int] | None:
        try:
            return await self.sync()
        except DialDevDisabled:
            return None
        except DialDevUnavailable as exc:
            dial_degraded.mark_unavailable(self.degraded, True)
            log.warning("dial_dev attention sync skipped: %s", exc.reason)
            return None

    async def _envelope(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        upstream = await self.client.get(path, params=params)
        if upstream.status_code == 404:
            return None
        if not 200 <= upstream.status_code < 300:
            raise DialDevUnavailable(
                "upstream_auth_refused" if upstream.status_code in (401, 403) else "upstream_error"
            )
        try:
            envelope = json.loads(upstream.body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise DialDevUnavailable("upstream_malformed") from exc
        if not isinstance(envelope, dict) or any(k not in envelope for k in ENVELOPE_KEYS):
            raise DialDevUnavailable("upstream_malformed")
        if not isinstance(envelope.get("data"), dict):
            raise DialDevUnavailable("upstream_malformed")
        dial_degraded.apply_envelope(self.degraded, envelope)
        return envelope

    async def sync(self) -> dict[str, int]:
        counts = {"projects": 0, "upserted": 0, "closed": 0, "skipped": 0, "left_open": 0}
        projects = await self._envelope(f"{UPSTREAM_PREFIX}/projects")
        rows = (projects or {}).get("data", {}).get("projects") or []
        for project in rows:
            project_id = project.get("project_id") if isinstance(project, dict) else None
            if not isinstance(project_id, str) or not valid_identifier(project_id):
                counts["skipped"] += 1
                continue
            counts["projects"] += 1
            await self._sync_project(project_id, counts)
        self.syncs += 1
        return counts

    async def _open_rows(self, project_id: str) -> list[dict[str, Any]]:
        rows = await self.attention.store.fetchall(
            "SELECT dedupe_key, payload_json FROM attention "
            "WHERE source = ? AND project_id = ? AND state NOT IN (?, ?)",
            (SOURCE, project_id, AttentionState.HANDLED.value, AttentionState.AUTO_RESOLVED.value),
        )
        out = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except ValueError:
                payload = {}
            out.append({"dedupe_key": row["dedupe_key"], "payload": payload})
        return out

    async def _sync_project(self, project_id: str, counts: dict[str, int]) -> None:
        envelope = await self._envelope(
            f"{UPSTREAM_PREFIX}/projects/{project_id}/tasks", params={"view": "needs_me"}
        )
        if envelope is None:
            return
        revision = _revision(envelope.get("projection_revision"))
        if revision is None:
            raise DialDevUnavailable("upstream_malformed")
        open_rows = await self._open_rows(project_id)
        open_by_identity: dict[tuple[str, str], list[str]] = {}
        for row in open_rows:
            payload = row["payload"]
            ident = (payload.get("kind"), payload.get("dial_identity"))
            if ident[0] and ident[1]:
                open_by_identity.setdefault(ident, []).append(row["dedupe_key"])

        still_open: set[tuple[str, str]] = set()
        tasks = envelope["data"].get("tasks") or []
        for task in tasks:
            if not isinstance(task, dict):
                counts["skipped"] += 1
                continue
            task_id = task.get("task_id")
            if not isinstance(task_id, str) or not valid_identifier(task_id):
                counts["skipped"] += 1
                continue
            for item in task.get("owner_items") or []:
                if not isinstance(item, dict):
                    counts["skipped"] += 1
                    continue
                identity = _identity(item, task_id)
                if identity is None:
                    counts["skipped"] += 1
                    continue
                if item.get("resolution_state") == APPLIED:
                    counts["closed"] += await self._close(
                        identity, item, open_by_identity, revision
                    )
                    continue
                still_open.add(identity)
                await self._upsert(project_id, task, task_id, identity, item, revision, open_by_identity)
                counts["upserted"] += 1

        # Open items DIAL no longer lists. Absence is not evidence: each is closed only if
        # the task's own projection shows it APPLIED, and left open otherwise.
        absent = [ident for ident in open_by_identity if ident not in still_open]
        task_ids = {}
        for ident in absent:
            keys = open_by_identity[ident]
            for row in open_rows:
                if row["dedupe_key"] in keys:
                    task_ids.setdefault(row["payload"].get("task_id"), []).append(ident)
                    break
        for task_id, idents in task_ids.items():
            if not isinstance(task_id, str) or not valid_identifier(task_id):
                counts["left_open"] += len(idents)
                continue
            detail = await self._envelope(f"{UPSTREAM_PREFIX}/tasks/{task_id}")
            applied: set[tuple[str, str]] = set()
            if detail is not None:
                for item in detail["data"].get("owner_items") or []:
                    if not isinstance(item, dict):
                        continue
                    identity = _identity(item, task_id)
                    if identity is not None and item.get("resolution_state") == APPLIED:
                        applied.add(identity)
            detail_revision = _revision((detail or {}).get("projection_revision")) or revision
            for ident in idents:
                if ident in applied:
                    counts["closed"] += await self._close(
                        ident, {}, open_by_identity, detail_revision
                    )
                else:
                    counts["left_open"] += 1

    async def _close(
        self,
        identity: tuple[str, str],
        item: dict[str, Any],
        open_by_identity: dict[tuple[str, str], list[str]],
        revision: str,
    ) -> int:
        origin = _revision(item.get("origin_projection_revision"))
        keys = open_by_identity.get(identity, [])
        if origin is not None:
            keys = [k for k in keys if k == dedupe_key(identity[0], identity[1], origin)]
        closed = 0
        for key in keys:
            if await self.attention.auto_resolve(key, {
                "closed_by": "dial_projection",
                "closed_reason": "APPLIED",
                "closed_at_projection_revision": revision,
            }):
                closed += 1
                if self.events is not None:
                    await self.events.publish("attention.resolved", {"dedupe_key": key, "source": SOURCE})
        return closed

    async def _upsert(
        self,
        project_id: str,
        task: dict[str, Any],
        task_id: str,
        identity: tuple[str, str],
        item: dict[str, Any],
        revision: str,
        open_by_identity: dict[tuple[str, str], list[str]],
    ) -> None:
        kind, ident = identity
        origin = _revision(item.get("origin_projection_revision"))
        if origin is not None:
            key = dedupe_key(kind, ident, origin)
        elif open_by_identity.get(identity):
            # Same condition still open: keep the revision it originated at.
            key = open_by_identity[identity][0]
        else:
            key = dedupe_key(kind, ident, revision)
        origin_revision = key[len(f"{SOURCE}:{kind}:{ident}:"):]
        title = str(item.get("title") or task.get("title") or f"DIAL {kind.replace('_', ' ')}: {task_id}")
        payload = {
            "task_id": task_id,
            "kind": kind,
            "deep_link": DEEP_LINK.format(task_id=task_id),
            "dial_identity": ident,
            "projection_revision_of_origin": origin_revision,
            "last_seen_projection_revision": revision,
        }
        if item.get("decision_id") is not None:
            payload["decision_id"] = ident
        record = await self.attention.upsert(
            title=title[:200],
            severity=severity_for(item, task),
            source=SOURCE,
            dedupe_key=key,
            project_id=project_id,
            payload=payload,
        )
        if self.events is not None:
            await self.events.publish("attention.upserted", record.model_dump(mode="json"))
