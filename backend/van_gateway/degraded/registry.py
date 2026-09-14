from __future__ import annotations

from van_gateway.models import DegradedCapability, DegradedCode


CATALOG: dict[DegradedCode, DegradedCapability] = {
    DegradedCode.HERMES_OFFLINE: DegradedCapability(
        code=DegradedCode.HERMES_OFFLINE,
        broken="Hermes profile `van` unreachable",
        still_works="Local reminders, attention queue, offline command enqueue",
        will_not_do="Agent reasoning, project mutations, Bot Chat delivery",
        restore_action="Restore Hermes network/process and verify /health",
    ),
    DegradedCode.GEMINI_UNAVAILABLE: DegradedCapability(
        code=DegradedCode.GEMINI_UNAVAILABLE,
        broken="Gemini runtime credential missing or provider down",
        still_works="Other Hermes delegates when configured",
        will_not_do="Gemini-preferred Google-centric reasoning",
        restore_action="Configure separate Gemini API credential in Hermes van profile",
    ),
    DegradedCode.GOOGLE_TOKEN_EXPIRED: DegradedCapability(
        code=DegradedCode.GOOGLE_TOKEN_EXPIRED,
        broken="Google OAuth refresh failed",
        still_works="Non-Google tools and deterministic engines",
        will_not_do="Gmail/Calendar/Drive/Contacts/Tasks",
        restore_action="Re-consent Google OAuth from Connections settings",
    ),
    DegradedCode.GOOGLE_PARTIAL: DegradedCapability(
        code=DegradedCode.GOOGLE_PARTIAL,
        broken="Some Google scopes unavailable",
        still_works="Granted Google scopes only",
        will_not_do="Operations requiring missing scopes",
        restore_action="Reconnect Google with required narrow scopes",
    ),
    DegradedCode.NOTIFICATION_PERMISSION_REVOKED: DegradedCapability(
        code=DegradedCode.NOTIFICATION_PERMISSION_REVOKED,
        broken="Notification listener permission revoked",
        still_works="Manual share-to-Van and owner commands",
        will_not_do="Phone notification triage",
        restore_action="Re-enable notification access for Van",
    ),
    DegradedCode.STALE_PROJECT_TRUTH: DegradedCapability(
        code=DegradedCode.STALE_PROJECT_TRUTH,
        broken="Project Truth SHA mismatch or missing",
        still_works="Read-only status questions if repo readable",
        will_not_do="Project mutations",
        restore_action="Refresh Project Truth and re-verify SHA",
    ),
    DegradedCode.REPO_UNAVAILABLE: DegradedCapability(
        code=DegradedCode.REPO_UNAVAILABLE,
        broken="Registered project repository unreachable",
        still_works="Other projects and non-repo tools",
        will_not_do="Repo-scoped mutation/status for that project",
        restore_action="Mount/register repository path or restore network access",
    ),
    DegradedCode.GROUP_ROOM_UNSUPPORTED: DegradedCapability(
        code=DegradedCode.GROUP_ROOM_UNSUPPORTED,
        broken="Hermes gateway lacks native group room capability",
        still_works="Direct native bot messaging",
        will_not_do="Multi-member council rooms",
        restore_action="Upgrade Hermes gateway or use direct message_agent fallback",
    ),
    DegradedCode.WORKER_UNAVAILABLE: DegradedCapability(
        code=DegradedCode.WORKER_UNAVAILABLE,
        broken="Registered worker/peer offline",
        still_works="Local Hermes delegates that are healthy",
        will_not_do="Tasks assigned to that worker",
        restore_action="Bring worker online and re-negotiate capabilities",
    ),
    DegradedCode.EVENT_CURSOR_RESET: DegradedCapability(
        code=DegradedCode.EVENT_CURSOR_RESET,
        broken="Event cursor was reset; replay required",
        still_works="Live events after reset point",
        will_not_do="Guarantee unbroken historical continuity across reset",
        restore_action="Run paginated replay from seq 0 and acknowledge reset",
    ),
    DegradedCode.AUDIT_PROBLEM: DegradedCapability(
        code=DegradedCode.AUDIT_PROBLEM,
        broken="Audit sink write failure",
        still_works="Non-mutating reads if policy allows",
        will_not_do="High-impact mutations without audit",
        restore_action="Repair audit storage and verify write probe",
    ),
    DegradedCode.STORAGE_PROBLEM: DegradedCapability(
        code=DegradedCode.STORAGE_PROBLEM,
        broken="Gateway storage unavailable",
        still_works="Nothing stateful",
        will_not_do="All persistent operations",
        restore_action="Repair database path/permissions and migrate",
    ),
    DegradedCode.PHONE_OFFLINE: DegradedCapability(
        code=DegradedCode.PHONE_OFFLINE,
        broken="Owner device offline from gateway",
        still_works="Encrypted offline command queue on device",
        will_not_do="Live Hermes turns until reconnect",
        restore_action="Restore connectivity; replay non-expired queue",
    ),
    DegradedCode.BACKEND_UNAVAILABLE: DegradedCapability(
        code=DegradedCode.BACKEND_UNAVAILABLE,
        broken="Van gateway unreachable from device",
        still_works="Local UI shell and queued intents",
        will_not_do="Authenticated gateway mutations",
        restore_action="Restore gateway process/network",
    ),
}


class DegradedRegistry:
    def __init__(self) -> None:
        self._active: set[DegradedCode] = set()

    def set(self, code: DegradedCode, active: bool) -> None:
        if active:
            self._active.add(code)
        else:
            self._active.discard(code)

    def snapshot(self) -> list[DegradedCapability]:
        return [CATALOG[c] for c in sorted(self._active, key=lambda x: x.value)]

    def codes(self) -> list[str]:
        return [c.value for c in sorted(self._active, key=lambda x: x.value)]
