from __future__ import annotations

import re
import time
from enum import Enum

from pydantic import BaseModel, Field


class AppPolicy(str, Enum):
    NORMAL = "normal"
    PRIORITY = "priority"
    MUTE = "mute"


class NotificationClass(str, Enum):
    INFO = "INFO"
    FOLLOW_UP = "FOLLOW_UP"
    BLOCKER = "BLOCKER"
    URGENT = "URGENT"


OTP_RE = re.compile(
    r"(?i)\b(otp|one[-\s]?time|verification code|security code|auth(entication)? code)\b|"
    r"\b\d{4,8}\b"
)
SECRET_HINTS = ("password", "otp", "verification code", "security code", "bank", "2fa", "mfa", "one-time")


class PhoneNotification(BaseModel):
    key: str
    package: str
    title: str
    text: str
    importance: int = 3
    posted_at_unix: int
    policy: AppPolicy = AppPolicy.NORMAL


class FilteredNotification(BaseModel):
    key: str
    package: str
    title: str
    text: str
    classification: NotificationClass
    suppressed: bool = False
    redacted: bool = False
    reason: str | None = None
    payload: dict = Field(default_factory=dict)


#: How long a notification key is remembered as already-seen. Long enough that a
#: phone re-posting the same notification after a reconnect is still a duplicate;
#: short enough that the table does not become a permanent record of every
#: notification the owner's phone has ever produced.
DEDUPE_TTL_SECONDS = 7 * 86_400


class NotificationIntelligence:
    """Local-first filtering. Secrets never leave the device unredacted."""

    def __init__(self, quiet_hours: bool = False, suppressions=None) -> None:
        self.quiet_hours = quiet_hours
        self._seen: set[str] = set()
        # P3-OPS-005. Optional so the pure classifier stays constructible without a
        # database — several tests exercise the redaction rules and nothing else —
        # but create_app always supplies one, and without it dedupe dies at restart.
        self.suppressions = suppressions

    async def ingest_durable(self, note: PhoneNotification) -> FilteredNotification:
        """`ingest`, with the already-seen check answered from the database.

        P3-OPS-005: the in-memory set said "not seen" for every notification after
        a restart, so the owner was shown things they had already dismissed. The
        set is kept as a same-process fast path; the database is what makes the
        answer survive.
        """
        from van_gateway.ops.suppression import SuppressionChannel

        already = note.key in self._seen
        if not already and self.suppressions is not None:
            already = await self.suppressions.is_suppressed(
                SuppressionChannel.NOTIFICATION, note.key
            ) is not None
        filtered = self.ingest(note, already_seen=already)
        if not already and self.suppressions is not None:
            await self.suppressions.suppress(
                SuppressionChannel.NOTIFICATION, note.key,
                reason="already_delivered", ttl_seconds=DEDUPE_TTL_SECONDS,
            )
        return filtered

    def ingest(self, note: PhoneNotification, *, already_seen: bool = False) -> FilteredNotification:
        if already_seen or note.key in self._seen:
            return FilteredNotification(
                key=note.key,
                package=note.package,
                title=note.title,
                text="",
                classification=NotificationClass.INFO,
                suppressed=True,
                reason="duplicate",
            )
        self._seen.add(note.key)

        if note.policy == AppPolicy.MUTE:
            return FilteredNotification(
                key=note.key,
                package=note.package,
                title=note.title,
                text="",
                classification=NotificationClass.INFO,
                suppressed=True,
                reason="muted_app",
            )

        blob = f"{note.title}\n{note.text}".lower()
        secret = any(h in blob for h in SECRET_HINTS) or bool(OTP_RE.search(note.text))
        text = note.text
        redacted = False
        if secret:
            text = OTP_RE.sub("[REDACTED]", text)
            redacted = True
            # Banking/auth: suppress body from leaving device
            if any(h in blob for h in ("bank", "otp", "2fa", "mfa", "verification code")):
                return FilteredNotification(
                    key=note.key,
                    package=note.package,
                    title=note.title,
                    text="[SECRET_SUPPRESSED]",
                    classification=NotificationClass.URGENT if "bank" in blob else NotificationClass.FOLLOW_UP,
                    suppressed=True,
                    redacted=True,
                    reason="secret_suppressed",
                )

        classification = NotificationClass.INFO
        if note.policy == AppPolicy.PRIORITY or note.importance >= 4:
            classification = NotificationClass.FOLLOW_UP
        if note.importance >= 5 or "urgent" in blob or "asap" in blob:
            classification = NotificationClass.URGENT
        if "fail" in blob or "blocked" in blob or "overdue" in blob:
            classification = NotificationClass.BLOCKER

        if self.quiet_hours and classification not in (NotificationClass.URGENT, NotificationClass.BLOCKER):
            return FilteredNotification(
                key=note.key,
                package=note.package,
                title=note.title,
                text=text,
                classification=classification,
                suppressed=True,
                redacted=redacted,
                reason="quiet_hours",
            )

        return FilteredNotification(
            key=note.key,
            package=note.package,
            title=note.title,
            text=text,
            classification=classification,
            suppressed=False,
            redacted=redacted,
            payload={"posted_at_unix": note.posted_at_unix, "ingested_at_unix": int(time.time())},
        )

    @staticmethod
    def gateway_redact(text: str) -> str:
        """Second-pass redaction at gateway before any model exposure."""
        return OTP_RE.sub("[REDACTED]", text)
