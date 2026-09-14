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


class NotificationIntelligence:
    """Local-first filtering. Secrets never leave the device unredacted."""

    def __init__(self, quiet_hours: bool = False) -> None:
        self.quiet_hours = quiet_hours
        self._seen: set[str] = set()

    def ingest(self, note: PhoneNotification) -> FilteredNotification:
        if note.key in self._seen:
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
