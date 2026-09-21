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
    DegradedCode.ANTIGRAVITY_CAPACITY_LIMITED: DegradedCapability(
        code=DegradedCode.ANTIGRAVITY_CAPACITY_LIMITED,
        broken="Antigravity live generation is capacity-limited by Google provider quota",
        still_works="Hermes van runtime, Jules/Codex/Claude development fallbacks, Workspace APIs when connected, Gemini runtime when credentialed",
        will_not_do="Antigravity live model generation until provider quota recovers",
        restore_action="Wait for Antigravity capacity / retry canary; route development via Jules or Hermes Claude/Codex delegates",
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
    DegradedCode.TRADING_LEDGER_UNAVAILABLE: DegradedCapability(
        code=DegradedCode.TRADING_LEDGER_UNAVAILABLE,
        broken="VATI trading ledger unreadable or chain verification failed",
        still_works="Everything outside trading; Hermes trading analysis without live status",
        will_not_do="Report trading status, list owner tickets, record owner halts or ticket confirmations",
        restore_action="Restore the ledger file (VAN_VATI_LEDGER_PATH) or run `python -m vati replay-verify`",
    ),
    # Rev 1.3 §§99-100, 421 — automation/browser failures degrade only their own
    # surface. VAN reasoning, VATI and the native paths keep working.
    DegradedCode.AUTOMATION_FABRIC_UNAVAILABLE: DegradedCapability(
        code=DegradedCode.AUTOMATION_FABRIC_UNAVAILABLE,
        broken="Self-hosted n8n automation fabric unreachable or not admitted",
        still_works="VAN reasoning, VATI trading, browser fabric, native integrations",
        will_not_do="n8n-backed automations, background integration routines, event workflows",
        restore_action="Start the pinned n8n stack on the Trading Core VM and re-run tools/certification/certify_automation_runtime.py",
    ),
    DegradedCode.AUTOMATION_WORKFLOW_DEGRADED: DegradedCapability(
        code=DegradedCode.AUTOMATION_WORKFLOW_DEGRADED,
        broken="One or more admitted workflows failed health checks and left HOT",
        still_works="Other admitted workflows, native and browser execution paths",
        will_not_do="Route owner requests through the degraded workflow",
        restore_action="Inspect the workflow run history, repair as a new artifact version and re-admit",
    ),
    DegradedCode.AUTOMATION_CREDENTIAL_EXPIRED: DegradedCapability(
        code=DegradedCode.AUTOMATION_CREDENTIAL_EXPIRED,
        broken="An integration credential held by the automation fabric is expired or rejected",
        still_works="Workflows not bound to that credential alias",
        will_not_do="Execute workflows requiring the expired connector",
        restore_action="Re-authorize the connector and re-provision the credential alias",
    ),
    DegradedCode.AUTOMATION_COMPILER_UNAVAILABLE: DegradedCapability(
        code=DegradedCode.AUTOMATION_COMPILER_UNAVAILABLE,
        broken="Workflow compiler or its policy/node catalog cannot load",
        still_works="Existing HOT workflows already deployed to n8n",
        will_not_do="Compile, repair or admit new workflow capabilities",
        restore_action="Restore config/automation/* policy files and verify the node catalog version",
    ),
    DegradedCode.AUTOMATION_SECURITY_AUDIT_FAILED: DegradedCapability(
        code=DegradedCode.AUTOMATION_SECURITY_AUDIT_FAILED,
        broken="The n8n security audit reported material findings",
        still_works="Read-only inspection of automation state",
        will_not_do="Admit new workflows or activate automations until findings are cleared",
        restore_action="Review AutomationSecurityEvidence, remediate the findings and re-run the audit",
    ),
    DegradedCode.AUTOMATION_INGRESS_DISABLED: DegradedCapability(
        code=DegradedCode.AUTOMATION_INGRESS_DISABLED,
        broken="External webhook ingress is disabled pending owner security amendment",
        still_works="Scheduled and owner-triggered automations, all native paths",
        will_not_do="Accept inbound external events from providers",
        restore_action="Record owner approval of VAN-AMEND-SECURITY-POLICY-001 and set VAN_AUTOMATION_INGRESS_ENABLED=1",
    ),
    DegradedCode.BROWSER_HARNESS_UNAVAILABLE: DegradedCapability(
        code=DegradedCode.BROWSER_HARNESS_UNAVAILABLE,
        broken="Deterministic browser actuator (Browser Harness) unreachable or unpinned",
        still_works="API, n8n and native capability paths; semantic browser if configured",
        will_not_do="Deterministic browser workflows and browser evidence capture",
        restore_action="Start the pinned browser-harness runtime and re-run tools/certification/certify_browser_fabric.py",
    ),
    DegradedCode.COMPUTER_USE_NO_SURFACE_WORKER: DegradedCapability(
        code=DegradedCode.COMPUTER_USE_NO_SURFACE_WORKER,
        broken="Computer Interaction Fabric has no worker for any surface",
        still_works="Browser fabric, n8n automation, Google and native capability paths, VATI T0",
        will_not_do="Desktop, terminal and mobile operations; nothing is queued for later",
        restore_action=(
            "Build and register a surface worker, then add its Surface to "
            "computer_use.fabric.SURFACE_WORKERS"
        ),
    ),
    DegradedCode.BROWSER_SEMANTIC_UNAVAILABLE: DegradedCapability(
        code=DegradedCode.BROWSER_SEMANTIC_UNAVAILABLE,
        broken="Semantic browser (Stagehand) unreachable or model provider unconfigured",
        still_works="Deterministic Browser Harness workflows, API/n8n/native paths",
        will_not_do="Semantic observation, typed extraction and workflow discovery",
        restore_action="Configure the gateway-held model provider and start the pinned Stagehand worker",
    ),
    DegradedCode.BROWSER_PROFILE_AUTH_REQUIRED: DegradedCapability(
        code=DegradedCode.BROWSER_PROFILE_AUTH_REQUIRED,
        broken="A managed browser profile lost its authenticated session",
        still_works="Public research profile and every other admitted profile",
        will_not_do="Authenticated operations against that one service",
        restore_action="Re-authenticate the profile through the owner browser access path; secrets stay in the session broker",
    ),

    # GAP-F-007 — nine codes existed in DegradedCode with no CATALOG entry, so
    # `snapshot()` raised KeyError and /health answered 500 in exactly the fault it
    # was meant to report. Every code is catalogued and a test pins exhaustiveness.
    DegradedCode.GOOGLE_PRINCIPAL_UNVERIFIED: DegradedCapability(
        code=DegradedCode.GOOGLE_PRINCIPAL_UNVERIFIED,
        broken="Canonical owner Google principal not registered or unverified",
        still_works="Non-Google capabilities and deterministic engines",
        will_not_do="Any Google capability routing",
        restore_action="Run tools/google/configure_google_identity.py and import the Hermes attestation",
    ),
    DegradedCode.GOOGLE_CAPABILITY_UNAVAILABLE: DegradedCapability(
        code=DegradedCode.GOOGLE_CAPABILITY_UNAVAILABLE,
        broken="A requested Google capability has no usable provider state",
        still_works="Other READY Google capabilities and non-Google tools",
        will_not_do="The specific Google capability until its live canary passes",
        restore_action="Run tools/google/certify_google_mesh.py and record READY evidence",
    ),
    DegradedCode.GOOGLE_OAUTH_CLIENT_UNCONFIGURED: DegradedCapability(
        code=DegradedCode.GOOGLE_OAUTH_CLIENT_UNCONFIGURED,
        broken="Workspace OAuth client id/secret missing from the gateway environment",
        still_works="Everything that does not need Workspace APIs",
        will_not_do="Gmail/Calendar/Drive/Contacts/Tasks",
        restore_action="Set VAN_GOOGLE_OAUTH_CLIENT_ID/SECRET and re-run the Workspace authorization tool",
    ),
    DegradedCode.GOOGLE_ACCOUNT_ENTITLEMENT_UNVERIFIED: DegradedCapability(
        code=DegradedCode.GOOGLE_ACCOUNT_ENTITLEMENT_UNVERIFIED,
        broken="Owner Google account plan/entitlement not verified",
        still_works="Workspace API reads where OAuth is READY",
        will_not_do="Entitlement-gated Gemini/consumer capabilities",
        restore_action="Import a Hermes attestation carrying the account entitlement",
    ),
    DegradedCode.OWNER_CONTEXT_UNAVAILABLE: DegradedCapability(
        code=DegradedCode.OWNER_CONTEXT_UNAVAILABLE,
        broken="Canonical owner-context kernel could not be read or sealed",
        still_works="Attention queue, reminders, missions already open",
        will_not_do="Dispatch new commands (context cannot be sealed)",
        restore_action="Check gateway storage (SQLite) health and restart the gateway",
    ),
    DegradedCode.OWNER_CONTEXT_CONFLICTED: DegradedCapability(
        code=DegradedCode.OWNER_CONTEXT_CONFLICTED,
        broken="Owner facts required by a command are in conflict",
        still_works="Commands whose requirements are not conflicted",
        will_not_do="Act on the conflicted requirement until the owner resolves it",
        restore_action="Resolve the conflict from the Memory surface (/v1/context/conflicts)",
    ),
    DegradedCode.RESEARCH_UNAVAILABLE: DegradedCapability(
        code=DegradedCode.RESEARCH_UNAVAILABLE,
        broken="External research provider (Exa) not configured or unreachable",
        still_works="Local knowledge, Google reads, deterministic engines",
        will_not_do="Web research missions",
        restore_action="Configure VAN_EXA_API_KEY and enable egress, then run the research canary",
    ),
    DegradedCode.RESEARCH_EGRESS_DENIED: DegradedCapability(
        code=DegradedCode.RESEARCH_EGRESS_DENIED,
        broken="Research egress refused by policy (sensitive class or egress disabled)",
        still_works="Non-sensitive research where egress is enabled",
        will_not_do="Sensitive-class egress without owner approval",
        restore_action="Owner approves sensitive egress for the specific query or enables egress",
    ),
    DegradedCode.DEVICE_OR_GRANT_REVOKED: DegradedCapability(
        code=DegradedCode.DEVICE_OR_GRANT_REVOKED,
        broken="The owner device or a capability grant was revoked",
        still_works="Nothing for the revoked device; other paired devices unaffected",
        will_not_do="Accept commands or actions from the revoked device/grant",
        restore_action="Re-pair the device through a new pairing ticket",
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
        # Unknown codes render as a generic entry rather than crashing /health (GAP-F-007).
        return [
            CATALOG.get(
                c,
                DegradedCapability(
                    code=c, broken=f"{c.value} active (uncatalogued)", still_works="Unknown",
                    will_not_do="Unknown", restore_action="Add this code to degraded/registry.py CATALOG",
                ),
            )
            for c in sorted(self._active, key=lambda x: x.value)
        ]

    def codes(self) -> list[str]:
        return [c.value for c in sorted(self._active, key=lambda x: x.value)]
