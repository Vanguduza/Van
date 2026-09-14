from __future__ import annotations

import time
from typing import Any

from van_gateway.attention.engine import AttentionEngine
from van_gateway.models import (
    AttentionSeverity,
    AttentionState,
    Briefing,
    BriefingCategory,
    BriefingSection,
)
from van_gateway.storage.db import Store


class BriefingService:
    """Deterministic-first owner briefing. Never invents missing data."""

    def __init__(self, store: Store, attention: AttentionEngine) -> None:
        self.store = store
        self.attention = attention

    async def build(
        self,
        *,
        calendar_items: list[dict[str, Any]] | None = None,
        mail_items: list[dict[str, Any]] | None = None,
        notification_items: list[dict[str, Any]] | None = None,
        project_health: list[dict[str, Any]] | None = None,
        hermes_health: dict[str, Any] | None = None,
        degraded: list[str] | None = None,
        quiet_hours: bool = False,
    ) -> Briefing:
        now = int(time.time())
        attention_items = await self.attention.list_open(now=now, quiet_hours=quiet_hours)

        needs_now = [
            {"id": i.id, "title": i.title, "severity": i.severity.value, "source": i.source}
            for i in attention_items
            if i.severity in (AttentionSeverity.URGENT, AttentionSeverity.BLOCKER) and i.state != AttentionState.WAITING_ON_OTHERS
        ]
        waiting = [
            {"id": i.id, "title": i.title, "source": i.source}
            for i in attention_items
            if i.state == AttentionState.WAITING_ON_OTHERS
        ]
        lower = [
            {"id": i.id, "title": i.title, "severity": i.severity.value}
            for i in attention_items
            if i.severity == AttentionSeverity.INFO
        ]

        today: list[dict[str, Any]] = []
        if calendar_items is not None:
            today.extend({"kind": "calendar", **c} for c in calendar_items)
        reminder_rows = await self.store.fetchall(
            "SELECT id, text, due_at_unix, status FROM reminders WHERE status = 'OPEN' AND due_at_unix BETWEEN ? AND ?",
            (now - 3600, now + 24 * 3600),
        )
        today.extend(
            {"kind": "reminder", "id": r["id"], "text": r["text"], "due_at_unix": int(r["due_at_unix"])}
            for r in reminder_rows
        )

        messages: list[dict[str, Any]] = []
        if mail_items is not None:
            messages.extend({"kind": "mail", **m} for m in mail_items)
        if notification_items is not None:
            messages.extend({"kind": "notification", **n} for n in notification_items)

        projects_at_risk: list[dict[str, Any]] = []
        if project_health is not None:
            projects_at_risk = [p for p in project_health if p.get("risk")]

        recent = await self.store.fetchall(
            "SELECT id, result, created_at_unix FROM audit WHERE result IN ('ok', 'success', 'completed', 'accepted') ORDER BY created_at_unix DESC LIMIT 20"
        )
        recent_completions = [
            {"id": r["id"], "result": r["result"], "created_at_unix": int(r["created_at_unix"])}
            for r in recent
        ]

        handled_rows = await self.store.fetchall(
            "SELECT id, title, source FROM attention WHERE state IN ('HANDLED', 'AUTO_RESOLVED') ORDER BY updated_at_unix DESC LIMIT 20"
        )
        handled = [{"id": r["id"], "title": r["title"], "source": r["source"]} for r in handled_rows]

        if hermes_health is not None and hermes_health.get("ok") is False:
            needs_now.append({"id": "hermes-health", "title": "Hermes unhealthy", "severity": "BLOCKER", "source": "hermes"})

        sections = [
            BriefingSection(category=BriefingCategory.NEEDS_YOU_NOW, items=needs_now),
            BriefingSection(category=BriefingCategory.TODAY, items=today),
            BriefingSection(category=BriefingCategory.WAITING_ON_OTHERS, items=waiting),
            BriefingSection(category=BriefingCategory.PROJECTS_AT_RISK, items=projects_at_risk),
            BriefingSection(category=BriefingCategory.MESSAGES_REQUIRING_REPLY, items=messages),
            BriefingSection(category=BriefingCategory.RECENT_COMPLETIONS, items=recent_completions),
            BriefingSection(category=BriefingCategory.HANDLED_AUTOMATICALLY, items=handled),
            BriefingSection(category=BriefingCategory.LOWER_PRIORITY, items=lower),
        ]
        return Briefing(
            generated_at_unix=now,
            sections=sections,
            invented_data=False,
            degraded=list(degraded or []),
        )
