"""VAN autonomous web acquisition core.

This module absorbs the strongest crawl-orchestration patterns into VAN without
making a third-party crawler the authority layer. Browser Harness/JEV remain the
control plane; Scrapling/Katana/Steel/Playwright/Stagehand are execution adapters.

The frontier is durable, bounded, lease-fenced and restart-safe. It deliberately
stores only opaque session/network references; cookies, tokens and browser
profile material stay inside the existing Browser Session Broker / runtime.
"""

from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

from pydantic import BaseModel, Field

from van_gateway.automation.canonical import digest, new_id
from van_gateway.storage.db import Store


class AcquisitionRoute(str, Enum):
    DIRECT_HTTP = "DIRECT_HTTP"
    SCRAPLING_HTTP = "SCRAPLING_HTTP"
    KATANA_RECON = "KATANA_RECON"
    SCRAPLING_BROWSER = "SCRAPLING_BROWSER"
    HARNESS = "HARNESS"
    STAGEHAND = "STAGEHAND"


class AcquisitionState(str, Enum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    COMPLETED = "COMPLETED"
    DEAD_LETTER = "DEAD_LETTER"
    CANCELLED = "CANCELLED"


class AcquisitionFailure(str, Enum):
    NETWORK = "NETWORK"
    RATE_LIMIT = "RATE_LIMIT"
    SERVER = "SERVER"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    SESSION_INVALID = "SESSION_INVALID"
    DOM_DRIFT = "DOM_DRIFT"
    CHALLENGE = "CHALLENGE"
    EXTRACTION = "EXTRACTION"
    RUNTIME = "RUNTIME"
    POLICY = "POLICY"
    UNSAFE = "UNSAFE"
    UNKNOWN = "UNKNOWN"


PERMANENT_FAILURES = {AcquisitionFailure.POLICY, AcquisitionFailure.UNSAFE}


class AcquisitionSignals(BaseModel):
    """Observed signals used by the deterministic route selector.

    JEV may populate/accelerate these signals, but it does not become an
    authority source. A hint can choose among otherwise-admissible routes only.
    """

    structured_endpoint_available: bool = False
    unknown_site: bool = False
    reconnaissance_complete: bool = False
    javascript_required: bool = False
    browser_required: bool = False
    semantic_interaction_required: bool = False
    selector_drift: bool = False
    domain_skill_available: bool = False
    jev_hint: AcquisitionRoute | None = None


class WebWorkItem(BaseModel):
    item_id: str
    canonical_url: str
    url_digest: str
    domain: str
    profile_alias: str
    source: str = "DISCOVERY"
    parent_item_id: str | None = None
    depth: int = 0
    priority: int = 50
    preferred_route: AcquisitionRoute | None = None
    route: AcquisitionRoute | None = None
    state: AcquisitionState = AcquisitionState.QUEUED
    attempt_count: int = 0
    max_attempts: int = 5
    next_eligible_at_ms: int | None = None
    lease_owner: str | None = None
    lease_token: str | None = None
    lease_expires_at_ms: int | None = None
    checkpoint_ref: str | None = None
    last_failure_class: AcquisitionFailure | None = None
    last_error_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at_ms: int
    updated_at_ms: int
    completed_at_ms: int | None = None


class AcquisitionSession(BaseModel):
    session_id: str
    profile_alias: str
    domain_scope: str
    network_identity_ref: str | None = None
    state: str = "READY"
    use_count: int = 0
    failure_count: int = 0
    created_at_ms: int
    updated_at_ms: int
    retired_at_ms: int | None = None


class RouteDecision(BaseModel):
    route: AcquisitionRoute
    reason: str


def canonicalize_url(url: str) -> tuple[str, str]:
    """Normalize identity without changing query semantics.

    Fragments never reach the server and are dropped. Query ordering is
    preserved because some applications use ordered/repeated parameters.
    """

    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("web_acquisition_requires_http_url")

    scheme = parts.scheme.lower()
    host = parts.hostname.lower()
    port = parts.port
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"

    path = parts.path or "/"
    canonical = urlunsplit(SplitResult(scheme, host, path, parts.query, ""))
    return canonical, parts.hostname.lower()


class AcquisitionRouter:
    """Cheap deterministic routing first; semantic browsing is the last resort."""

    @staticmethod
    def decide(item: WebWorkItem, signals: AcquisitionSignals) -> RouteDecision:
        if item.preferred_route is not None:
            return RouteDecision(route=item.preferred_route, reason="owner_or_caller_preference")
        if signals.structured_endpoint_available:
            return RouteDecision(route=AcquisitionRoute.DIRECT_HTTP, reason="structured_endpoint")
        if signals.unknown_site and not signals.reconnaissance_complete:
            return RouteDecision(route=AcquisitionRoute.KATANA_RECON, reason="unknown_site_recon")
        if signals.domain_skill_available and not signals.selector_drift:
            return RouteDecision(route=AcquisitionRoute.HARNESS, reason="qualified_domain_skill")
        if signals.semantic_interaction_required:
            return RouteDecision(route=AcquisitionRoute.STAGEHAND, reason="semantic_ui_required")
        if signals.browser_required or signals.javascript_required or signals.selector_drift:
            return RouteDecision(route=AcquisitionRoute.SCRAPLING_BROWSER, reason="browser_required")
        if signals.jev_hint is not None:
            return RouteDecision(route=signals.jev_hint, reason="jev_advisory_hint")
        return RouteDecision(route=AcquisitionRoute.SCRAPLING_HTTP, reason="default_lightweight_path")


class AcquisitionSessionPool:
    """Durable virtual-session registry.

    This is intentionally metadata-only. Authentication material belongs to the
    Browser Session Broker/Steel profile and is referenced by alias.
    """

    def __init__(self, store: Store) -> None:
        self.store = store

    async def acquire(
        self,
        *,
        profile_alias: str,
        domain_scope: str,
        network_identity_ref: str | None = None,
        now_ms: int | None = None,
    ) -> AcquisitionSession:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        row = await self.store.fetchone(
            """
            SELECT * FROM web_acquisition_sessions
            WHERE profile_alias = ? AND domain_scope = ? AND state = 'READY'
            ORDER BY failure_count ASC, use_count ASC, updated_at_ms ASC
            LIMIT 1
            """,
            (profile_alias, domain_scope),
        )
        if row is None:
            sid = new_id("wacqsess")
            await self.store.execute(
                """
                INSERT INTO web_acquisition_sessions(
                  session_id, profile_alias, domain_scope, network_identity_ref,
                  state, use_count, failure_count, created_at_ms, updated_at_ms, retired_at_ms
                ) VALUES (?, ?, ?, ?, 'READY', 1, 0, ?, ?, NULL)
                """,
                (sid, profile_alias, domain_scope, network_identity_ref, now, now),
            )
            return AcquisitionSession(
                session_id=sid,
                profile_alias=profile_alias,
                domain_scope=domain_scope,
                network_identity_ref=network_identity_ref,
                use_count=1,
                created_at_ms=now,
                updated_at_ms=now,
            )

        await self.store.execute(
            "UPDATE web_acquisition_sessions SET use_count = use_count + 1, updated_at_ms = ? "
            "WHERE session_id = ?",
            (now, row["session_id"]),
        )
        return AcquisitionSession(
            session_id=str(row["session_id"]),
            profile_alias=str(row["profile_alias"]),
            domain_scope=str(row["domain_scope"]),
            network_identity_ref=row["network_identity_ref"],
            state=str(row["state"]),
            use_count=int(row["use_count"]) + 1,
            failure_count=int(row["failure_count"]),
            created_at_ms=int(row["created_at_ms"]),
            updated_at_ms=now,
            retired_at_ms=row["retired_at_ms"],
        )

    async def record_failure(
        self, session_id: str, *, retire: bool = False, now_ms: int | None = None
    ) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        if retire:
            await self.store.execute(
                "UPDATE web_acquisition_sessions SET failure_count = failure_count + 1, "
                "state = 'RETIRED', retired_at_ms = ?, updated_at_ms = ? WHERE session_id = ?",
                (now, now, session_id),
            )
        else:
            await self.store.execute(
                "UPDATE web_acquisition_sessions SET failure_count = failure_count + 1, "
                "updated_at_ms = ? WHERE session_id = ?",
                (now, session_id),
            )


class AcquisitionFrontier:
    """Durable Crawlee-style frontier implemented inside VAN's authority boundary."""

    DEFAULT_LEASE_SECONDS = 120

    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def _row_to_item(row: Any) -> WebWorkItem:
        return WebWorkItem(
            item_id=str(row["item_id"]),
            canonical_url=str(row["canonical_url"]),
            url_digest=str(row["url_digest"]),
            domain=str(row["domain"]),
            profile_alias=str(row["profile_alias"]),
            source=str(row["source"]),
            parent_item_id=row["parent_item_id"],
            depth=int(row["depth"]),
            priority=int(row["priority"]),
            preferred_route=(
                AcquisitionRoute(str(row["preferred_route"])) if row["preferred_route"] else None
            ),
            route=AcquisitionRoute(str(row["route"])) if row["route"] else None,
            state=AcquisitionState(str(row["state"])),
            attempt_count=int(row["attempt_count"]),
            max_attempts=int(row["max_attempts"]),
            next_eligible_at_ms=row["next_eligible_at_ms"],
            lease_owner=row["lease_owner"],
            lease_token=row["lease_token"],
            lease_expires_at_ms=row["lease_expires_at_ms"],
            checkpoint_ref=row["checkpoint_ref"],
            last_failure_class=(
                AcquisitionFailure(str(row["last_failure_class"]))
                if row["last_failure_class"]
                else None
            ),
            last_error_code=row["last_error_code"],
            metadata=json.loads(str(row["metadata_json"] or "{}")),
            created_at_ms=int(row["created_at_ms"]),
            updated_at_ms=int(row["updated_at_ms"]),
            completed_at_ms=row["completed_at_ms"],
        )

    async def configure_domain(
        self,
        domain: str,
        *,
        max_concurrency: int = 2,
        min_delay_ms: int = 0,
        cooldown_until_ms: int | None = None,
        now_ms: int | None = None,
    ) -> None:
        if max_concurrency < 1 or max_concurrency > 64:
            raise ValueError("web_domain_max_concurrency_out_of_range")
        if min_delay_ms < 0:
            raise ValueError("web_domain_min_delay_negative")
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            """
            INSERT INTO web_domain_controls(
              domain, max_concurrency, min_delay_ms, cooldown_until_ms,
              last_claimed_at_ms, error_score, updated_at_ms
            ) VALUES (?, ?, ?, ?, NULL, 0, ?)
            ON CONFLICT(domain) DO UPDATE SET
              max_concurrency=excluded.max_concurrency,
              min_delay_ms=excluded.min_delay_ms,
              cooldown_until_ms=excluded.cooldown_until_ms,
              updated_at_ms=excluded.updated_at_ms
            """,
            (domain.lower(), max_concurrency, min_delay_ms, cooldown_until_ms, now),
        )

    async def enqueue(
        self,
        url: str,
        *,
        profile_alias: str = "public_research",
        source: str = "DISCOVERY",
        parent_item_id: str | None = None,
        depth: int = 0,
        priority: int = 50,
        preferred_route: AcquisitionRoute | None = None,
        max_attempts: int = 5,
        metadata: dict[str, Any] | None = None,
        now_ms: int | None = None,
    ) -> WebWorkItem:
        if not 0 <= priority <= 100:
            raise ValueError("web_acquisition_priority_out_of_range")
        if depth < 0:
            raise ValueError("web_acquisition_depth_negative")
        if not 1 <= max_attempts <= 20:
            raise ValueError("web_acquisition_max_attempts_out_of_range")

        canonical_url, domain = canonicalize_url(url)
        url_digest = digest({"url": canonical_url})
        now = int(time.time() * 1000) if now_ms is None else now_ms
        item_id = new_id("wacq")
        payload = json.dumps(metadata or {}, sort_keys=True, separators=(",", ":"))

        await self.store.execute(
            """
            INSERT INTO web_acquisition_items(
              item_id, canonical_url, url_digest, domain, profile_alias, source,
              parent_item_id, depth, priority, preferred_route, route, state,
              attempt_count, max_attempts, next_eligible_at_ms, lease_owner,
              lease_token, lease_expires_at_ms, checkpoint_ref, last_failure_class,
              last_error_code, metadata_json, created_at_ms, updated_at_ms, completed_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'QUEUED',
                      0, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, NULL)
            ON CONFLICT(url_digest, profile_alias) DO UPDATE SET
              priority = MAX(web_acquisition_items.priority, excluded.priority),
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                item_id, canonical_url, url_digest, domain, profile_alias, source,
                parent_item_id, depth, priority,
                preferred_route.value if preferred_route else None,
                max_attempts, payload, now, now,
            ),
        )
        row = await self.store.fetchone(
            "SELECT * FROM web_acquisition_items WHERE url_digest = ? AND profile_alias = ?",
            (url_digest, profile_alias),
        )
        assert row is not None
        return self._row_to_item(row)

    async def _expire_leases(self, db: Any, now: int) -> None:
        await db.execute(
            """
            UPDATE web_acquisition_items
            SET state = 'QUEUED', lease_owner = NULL, lease_token = NULL,
                lease_expires_at_ms = NULL, updated_at_ms = ?
            WHERE state IN ('CLAIMED','RUNNING')
              AND lease_expires_at_ms IS NOT NULL
              AND lease_expires_at_ms <= ?
            """,
            (now, now),
        )

    async def claim(
        self,
        *,
        worker_id: str,
        lease_seconds: int | None = None,
        now_ms: int | None = None,
    ) -> WebWorkItem | None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        ttl = max(30, int(lease_seconds or self.DEFAULT_LEASE_SECONDS))
        token = f"wlease_{uuid.uuid4().hex}"
        expires = now + ttl * 1000

        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            await self._expire_leases(db, now)
            cur = await db.execute(
                """
                SELECT i.*, COALESCE(c.max_concurrency, 2) AS domain_max,
                       COALESCE(c.min_delay_ms, 0) AS domain_delay,
                       c.cooldown_until_ms AS domain_cooldown,
                       c.last_claimed_at_ms AS domain_last_claim
                FROM web_acquisition_items i
                LEFT JOIN web_domain_controls c ON c.domain = i.domain
                WHERE i.state IN ('QUEUED','RETRY_WAIT')
                  AND (i.next_eligible_at_ms IS NULL OR i.next_eligible_at_ms <= ?)
                  AND (c.cooldown_until_ms IS NULL OR c.cooldown_until_ms <= ?)
                ORDER BY i.priority DESC, i.created_at_ms ASC
                LIMIT 64
                """,
                (now, now),
            )
            candidates = await cur.fetchall()

            chosen = None
            for row in candidates:
                delay = int(row["domain_delay"] or 0)
                last_claim = row["domain_last_claim"]
                if last_claim is not None and now - int(last_claim) < delay:
                    continue
                active_cur = await db.execute(
                    """
                    SELECT COUNT(*) AS n FROM web_acquisition_items
                    WHERE domain = ? AND state IN ('CLAIMED','RUNNING')
                      AND lease_expires_at_ms > ?
                    """,
                    (row["domain"], now),
                )
                active = await active_cur.fetchone()
                if int(active["n"]) >= int(row["domain_max"]):
                    continue
                chosen = row
                break

            if chosen is None:
                await db.commit()
                return None

            cur = await db.execute(
                """
                UPDATE web_acquisition_items
                SET state = 'CLAIMED', attempt_count = attempt_count + 1,
                    lease_owner = ?, lease_token = ?, lease_expires_at_ms = ?,
                    next_eligible_at_ms = NULL, updated_at_ms = ?
                WHERE item_id = ? AND state IN ('QUEUED','RETRY_WAIT')
                """,
                (worker_id, token, expires, now, chosen["item_id"]),
            )
            if cur.rowcount != 1:
                await db.rollback()
                return None
            await db.execute(
                """
                INSERT INTO web_domain_controls(
                  domain, max_concurrency, min_delay_ms, cooldown_until_ms,
                  last_claimed_at_ms, error_score, updated_at_ms
                ) VALUES (?, 2, 0, NULL, ?, 0, ?)
                ON CONFLICT(domain) DO UPDATE SET
                  last_claimed_at_ms=excluded.last_claimed_at_ms,
                  updated_at_ms=excluded.updated_at_ms
                """,
                (chosen["domain"], now, now),
            )
            await db.commit()

        row = await self.store.fetchone(
            "SELECT * FROM web_acquisition_items WHERE item_id = ?", (chosen["item_id"],)
        )
        assert row is not None
        return self._row_to_item(row)

    async def start(
        self, item_id: str, *, worker_id: str, lease_token: str, now_ms: int | None = None
    ) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            cur = await db.execute(
                """
                UPDATE web_acquisition_items SET state='RUNNING', updated_at_ms=?
                WHERE item_id=? AND state='CLAIMED' AND lease_owner=? AND lease_token=?
                  AND lease_expires_at_ms > ?
                """,
                (now, item_id, worker_id, lease_token, now),
            )
            await db.commit()
            if cur.rowcount != 1:
                raise RuntimeError("web_acquisition_lease_not_active")

    async def checkpoint(
        self,
        item_id: str,
        *,
        checkpoint_ref: str,
        worker_id: str,
        lease_token: str,
        now_ms: int | None = None,
    ) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            cur = await db.execute(
                """
                UPDATE web_acquisition_items
                SET checkpoint_ref=?, updated_at_ms=?
                WHERE item_id=? AND state IN ('CLAIMED','RUNNING')
                  AND lease_owner=? AND lease_token=? AND lease_expires_at_ms > ?
                """,
                (checkpoint_ref, now, item_id, worker_id, lease_token, now),
            )
            await db.commit()
            if cur.rowcount != 1:
                raise RuntimeError("web_acquisition_checkpoint_without_active_lease")

    async def set_route(
        self,
        item_id: str,
        *,
        route: AcquisitionRoute,
        worker_id: str,
        lease_token: str,
        now_ms: int | None = None,
    ) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            cur = await db.execute(
                """
                UPDATE web_acquisition_items SET route=?, updated_at_ms=?
                WHERE item_id=? AND lease_owner=? AND lease_token=? AND lease_expires_at_ms > ?
                """,
                (route.value, now, item_id, worker_id, lease_token, now),
            )
            await db.commit()
            if cur.rowcount != 1:
                raise RuntimeError("web_acquisition_route_without_active_lease")

    async def complete(
        self,
        item_id: str,
        *,
        worker_id: str,
        lease_token: str,
        checkpoint_ref: str | None = None,
        now_ms: int | None = None,
    ) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            cur = await db.execute(
                """
                UPDATE web_acquisition_items
                SET state='COMPLETED', checkpoint_ref=COALESCE(?, checkpoint_ref),
                    lease_owner=NULL, lease_token=NULL, lease_expires_at_ms=NULL,
                    completed_at_ms=?, updated_at_ms=?
                WHERE item_id=? AND lease_owner=? AND lease_token=?
                  AND lease_expires_at_ms > ?
                """,
                (checkpoint_ref, now, now, item_id, worker_id, lease_token, now),
            )
            await db.commit()
            if cur.rowcount != 1:
                raise RuntimeError("web_acquisition_complete_without_active_lease")

    @staticmethod
    def _backoff_ms(attempt_count: int) -> int:
        return min(60 * 60 * 1000, 5_000 * (2 ** max(0, attempt_count - 1)))

    async def fail(
        self,
        item_id: str,
        *,
        worker_id: str,
        lease_token: str,
        failure: AcquisitionFailure,
        error_code: str,
        retry_after_ms: int | None = None,
        now_ms: int | None = None,
    ) -> AcquisitionState:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        row = await self.store.fetchone(
            "SELECT * FROM web_acquisition_items WHERE item_id = ?", (item_id,)
        )
        if row is None:
            raise KeyError("unknown_web_acquisition_item")
        if row["lease_owner"] != worker_id or row["lease_token"] != lease_token:
            raise RuntimeError("web_acquisition_failure_without_active_lease")
        if int(row["lease_expires_at_ms"] or 0) <= now:
            raise RuntimeError("web_acquisition_failure_after_lease_expiry")

        attempts = int(row["attempt_count"])
        max_attempts = int(row["max_attempts"])
        terminal = failure in PERMANENT_FAILURES or attempts >= max_attempts

        if terminal:
            await self.store.execute(
                """
                UPDATE web_acquisition_items
                SET state='DEAD_LETTER', last_failure_class=?, last_error_code=?,
                    lease_owner=NULL, lease_token=NULL, lease_expires_at_ms=NULL,
                    completed_at_ms=?, updated_at_ms=?
                WHERE item_id=?
                """,
                (failure.value, error_code, now, now, item_id),
            )
            dead_letter_id = new_id("wacqdl")
            await self.store.execute(
                """
                INSERT OR IGNORE INTO automation_dead_letter(
                  dead_letter_id, run_id, event_id, capability_id, failure_class,
                  last_error_code, attempt_count, evidence_refs_json, next_action,
                  detail_json, created_at_ms, updated_at_ms, resolved_at_ms, resolution
                ) VALUES (?, ?, NULL, 'van.web-acquisition', ?, ?, ?, '[]',
                          'REVIEW_OR_REQUEUE', ?, ?, ?, NULL, NULL)
                """,
                (
                    dead_letter_id, item_id, failure.value, error_code, attempts,
                    json.dumps({"url_digest": row["url_digest"], "domain": row["domain"]}),
                    now, now,
                ),
            )
            return AcquisitionState.DEAD_LETTER

        delay = (
            max(int(retry_after_ms or 0), self._backoff_ms(attempts))
            if failure is AcquisitionFailure.RATE_LIMIT
            else self._backoff_ms(attempts)
        )
        next_at = now + delay
        await self.store.execute(
            """
            UPDATE web_acquisition_items
            SET state='RETRY_WAIT', last_failure_class=?, last_error_code=?,
                next_eligible_at_ms=?, lease_owner=NULL, lease_token=NULL,
                lease_expires_at_ms=NULL, updated_at_ms=?
            WHERE item_id=?
            """,
            (failure.value, error_code, next_at, now, item_id),
        )
        if failure is AcquisitionFailure.RATE_LIMIT:
            await self.store.execute(
                """
                INSERT INTO web_domain_controls(
                  domain, max_concurrency, min_delay_ms, cooldown_until_ms,
                  last_claimed_at_ms, error_score, updated_at_ms
                ) VALUES (?, 1, 1000, ?, NULL, 1, ?)
                ON CONFLICT(domain) DO UPDATE SET
                  cooldown_until_ms=MAX(COALESCE(web_domain_controls.cooldown_until_ms, 0),
                                        excluded.cooldown_until_ms),
                  max_concurrency=MAX(1, web_domain_controls.max_concurrency - 1),
                  error_score=web_domain_controls.error_score + 1,
                  updated_at_ms=excluded.updated_at_ms
                """,
                (str(row["domain"]), next_at, now),
            )
        return AcquisitionState.RETRY_WAIT

    async def stats(self) -> dict[str, int]:
        rows = await self.store.fetchall(
            "SELECT state, COUNT(*) AS n FROM web_acquisition_items GROUP BY state"
        )
        return {str(row["state"]): int(row["n"]) for row in rows}


__all__ = [
    "AcquisitionFailure",
    "AcquisitionFrontier",
    "AcquisitionRoute",
    "AcquisitionRouter",
    "AcquisitionSession",
    "AcquisitionSessionPool",
    "AcquisitionSignals",
    "AcquisitionState",
    "RouteDecision",
    "WebWorkItem",
    "canonicalize_url",
]
