"""Rev 1.3 §§15-18, 83-84, 162-164, 209 — CanonicalExternalEvent ingestion.

The rule this module exists to enforce is §18: an external event may become
evidence or state, but **never an owner command**. Nothing here can produce an
owner-authorized action; the strongest outcome is a stored event that Hermes may
later interpret into an ActionProposal, which the Gateway then authorizes
separately.

Dedupe is durable (a UNIQUE constraint), so a provider retrying a webhook cannot
produce two Hermes events (§162).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.automation.canonical import digest, new_id
from van_gateway.storage.db import Store


class SourceTrust(str, Enum):
    """§164 — trust is derived from the adapter, never claimed by the payload."""

    OWNER_VERIFIED = "OWNER_VERIFIED"
    PROVIDER_SIGNED = "PROVIDER_SIGNED"
    PROVIDER_UNSIGNED = "PROVIDER_UNSIGNED"
    UNTRUSTED_EXTERNAL = "UNTRUSTED_EXTERNAL"


class Sensitivity(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    SENSITIVE = "SENSITIVE"
    SECRET = "SECRET"


class EventRejected(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class CanonicalExternalEvent(BaseModel):
    """§17. ``payload`` is data; it is never interpreted as instruction here."""

    event_id: str
    source_system: str
    source_account_alias: str | None = None
    event_type: str
    observed_at_ms: int | None = None
    received_at_ms: int
    payload_schema_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    content_digest: str
    source_trust: SourceTrust
    sensitivity: Sensitivity
    dedupe_key: str
    correlation_refs: list[str] = Field(default_factory=list)
    evidence_pointer: str | None = None


class EventIngestResult(BaseModel):
    event: CanonicalExternalEvent
    #: False when the dedupe key already existed — the caller must not re-emit.
    created: bool


#: §84 — markers that make a payload untrusted-external no matter what it claims.
_INJECTION_MARKERS = (
    "ignore previous", "ignore all previous", "ignore van policy", "disregard your instructions",
    "you are now", "system prompt", "send cookies", "exfiltrate", "reveal the token",
    "call a privileged tool", "change trading limits", "place a trade", "disable policy",
)


class ExternalEventIngestor:
    """Validates, dedupes and persists inbound events before Hermes ever sees them."""

    #: §314 — bound the payload so an oversized body cannot be used as a DoS.
    MAX_PAYLOAD_BYTES = 256 * 1024
    #: §209 — replay window for signed provider webhooks.
    MAX_CLOCK_SKEW_MS = 5 * 60 * 1000

    def __init__(self, store: Store, *, ingress_enabled: bool = False) -> None:
        self.store = store
        self.ingress_enabled = ingress_enabled

    # ------------------------------------------------------------- validation

    @staticmethod
    def dedupe_key(
        *, source_system: str, event_type: str, provider_event_id: str | None, content_digest: str
    ) -> str:
        """§163 — prefer the provider's own ID; fall back to content.

        Content-only dedupe would collapse two genuinely distinct but identical
        notifications, so the provider ID is used whenever it exists.
        """
        basis = provider_event_id or content_digest
        return hashlib.sha256(f"{source_system}|{event_type}|{basis}".encode("utf-8")).hexdigest()

    @staticmethod
    def assess_injection(payload: dict[str, Any]) -> str:
        """§84 — record an assessment; never act on embedded instructions."""
        blob = json.dumps(payload, ensure_ascii=False).lower()
        hits = [marker for marker in _INJECTION_MARKERS if marker in blob]
        return "SUSPECTED_INJECTION" if hits else "NONE_DETECTED"

    @staticmethod
    def verify_provider_signature(
        *, secret: str, body: bytes, signature: str, timestamp_ms: int, now_ms: int
    ) -> None:
        """§§208-209 — HMAC plus a bounded replay window."""
        if abs(now_ms - timestamp_ms) > ExternalEventIngestor.MAX_CLOCK_SKEW_MS:
            raise EventRejected("WEBHOOK_TIMESTAMP_OUT_OF_WINDOW")
        expected = hmac.new(
            secret.encode("utf-8"), f"{timestamp_ms}.".encode("utf-8") + body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise EventRejected("WEBHOOK_SIGNATURE_INVALID")

    # ---------------------------------------------------------------- ingest

    async def ingest(
        self,
        *,
        source_system: str,
        event_type: str,
        payload: dict[str, Any],
        payload_schema_id: str,
        source_trust: SourceTrust,
        sensitivity: Sensitivity = Sensitivity.INTERNAL,
        provider_event_id: str | None = None,
        source_account_alias: str | None = None,
        observed_at_ms: int | None = None,
        correlation_refs: list[str] | None = None,
        now_ms: int | None = None,
    ) -> EventIngestResult:
        if not self.ingress_enabled:
            # Fail closed: ingress ships disabled pending the owner amendment.
            raise EventRejected("AUTOMATION_INGRESS_DISABLED")

        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(raw) > self.MAX_PAYLOAD_BYTES:
            raise EventRejected("EVENT_PAYLOAD_TOO_LARGE")
        if source_trust is SourceTrust.OWNER_VERIFIED:
            # §18 — no adapter may mint owner authority by labelling an event.
            raise EventRejected("EXTERNAL_EVENT_CANNOT_CLAIM_OWNER_TRUST")

        now = int(time.time() * 1000) if now_ms is None else now_ms
        content_digest = digest(payload)
        key = self.dedupe_key(
            source_system=source_system,
            event_type=event_type,
            provider_event_id=provider_event_id,
            content_digest=content_digest,
        )

        existing = await self.store.fetchone(
            "SELECT * FROM automation_external_events WHERE dedupe_key = ?", (key,)
        )
        if existing is not None:
            # §162 — return the existing ID, do not emit a second Hermes event.
            return EventIngestResult(event=self._row_to_event(existing), created=False)

        event = CanonicalExternalEvent(
            event_id=new_id("event"),
            source_system=source_system,
            source_account_alias=source_account_alias,
            event_type=event_type,
            observed_at_ms=observed_at_ms,
            received_at_ms=now,
            payload_schema_id=payload_schema_id,
            payload=payload,
            content_digest=content_digest,
            source_trust=source_trust,
            sensitivity=sensitivity,
            dedupe_key=key,
            correlation_refs=sorted(correlation_refs or []),
        )
        try:
            await self.store.execute(
                """
                INSERT INTO automation_external_events(
                  event_id, source_system, source_account_alias, event_type, observed_at_ms,
                  received_at_ms, payload_schema_id, payload_digest, source_trust, sensitivity,
                  dedupe_key, evidence_pointer, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id, event.source_system, event.source_account_alias,
                    event.event_type, event.observed_at_ms, event.received_at_ms,
                    event.payload_schema_id, event.content_digest, event.source_trust.value,
                    event.sensitivity.value, event.dedupe_key, event.evidence_pointer,
                    Store.dumps(event.payload),
                ),
            )
        except Exception:  # pragma: no cover - UNIQUE race
            row = await self.store.fetchone(
                "SELECT * FROM automation_external_events WHERE dedupe_key = ?", (key,)
            )
            if row is None:
                raise
            return EventIngestResult(event=self._row_to_event(row), created=False)
        return EventIngestResult(event=event, created=True)

    async def get(self, event_id: str) -> CanonicalExternalEvent | None:
        row = await self.store.fetchone(
            "SELECT * FROM automation_external_events WHERE event_id = ?", (event_id,)
        )
        return self._row_to_event(row) if row is not None else None

    @staticmethod
    def _row_to_event(row: Any) -> CanonicalExternalEvent:
        return CanonicalExternalEvent(
            event_id=str(row["event_id"]),
            source_system=str(row["source_system"]),
            source_account_alias=str(row["source_account_alias"]) if row["source_account_alias"] else None,
            event_type=str(row["event_type"]),
            observed_at_ms=int(row["observed_at_ms"]) if row["observed_at_ms"] is not None else None,
            received_at_ms=int(row["received_at_ms"]),
            payload_schema_id=str(row["payload_schema_id"]),
            payload=json.loads(row["payload_json"] or "{}"),
            content_digest=str(row["payload_digest"]),
            source_trust=SourceTrust(str(row["source_trust"])),
            sensitivity=Sensitivity(str(row["sensitivity"])),
            dedupe_key=str(row["dedupe_key"]),
            evidence_pointer=str(row["evidence_pointer"]) if row["evidence_pointer"] else None,
        )


__all__ = [
    "CanonicalExternalEvent",
    "EventIngestResult",
    "EventRejected",
    "ExternalEventIngestor",
    "Sensitivity",
    "SourceTrust",
]
