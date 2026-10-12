# Muse dual-surface owner interaction — implementation contract (2026-10-12)

**Status:** implementation candidate, not qualified or merged. Owner requirement: the mobile implementation is inside the existing **VAN Android app** (`com.dial.van`, Jetpack Compose); the private **DIAL Work Tracker Site** must independently expose **the same live capabilities**. The Site is not a WebView substitute for native Android and Android is not an embedded Site.

## Authority and placement

Muse has **one** authoritative browser session, project-task registry, watchdog, event history and approval ledger on the existing VAN/DIAL estate. Hermes governance applies where required by the source task; direct owner Muse tasks retain their existing direct owner route. The Android and Site interfaces are views/authorized command clients, never competing work or Project Truth authorities.

```
Muse authenticated browser + current-job watchdog (existing VAN host)
                     │ browser DOM/accessibility change observer
                     ▼
      Project-scoped Muse interaction broker + durable command/approval ledger
                 ╱          ╲
       VAN gateway           existing Site owner BFF / outbound DIAL relay
        ╱                          ╲
 VAN Android Compose            DIAL Work Tracker Site
 (native notifications)         (Web Push + inbox)
```

Both clients use the same `event_id`, `task_id`, `thread_id`, `approval_id`, `session_id`, `project_id`, source revision and immutable receipts. The broker is the sole authority for whether a browser control is still pending. Cache copies and notifications are **not** authority. A read can be stale; a successful HTTP command receipt is not proof the browser acted.

## Interaction event family (proposed `muse.interaction.v1`)

Each event carries `event_id`, `source_sequence`, `source_observed_at`, `session_id`, `project_id`/explicit independent scope, `thread_id`, `task_id`, `event_type`, `source_revision`, and `evidence_digest`. Events include:

- `conversation.message`: role, bounded redacted text, message ID, attachment references with grant checks
- `task.state_changed`: queued/running/waiting/terminal, meaningful progress, watchdog dimensions and capture qualification separately
- `approval.requested`: stable approval ID, **exact** provider action and scope, action fingerprint, browser-control generation, current revision, allowed choices, expiry, optional safe visual preview
- `approval.resolved`: provider-observed outcome and one-use command receipt; do not assume from HTTP 202
- `watchdog.alert`: unhealthy/stale/waiting, dedupe key, notification relevance, source timestamp
- `session.gap`: discontinuity that forces resync and disables owner actuation until reconciled

The observer should read the existing provider DOM/accessibility tree and inspect a screenshot only for unsupported controls. It must not OCR/click by guessed coordinate, restore a second browser profile, or scrape credentials. Unknown/unsafe provider prompts fall back to the original provider interface; never generate a pretend Allow button.

## Owner actions and admission

A verified owner chooses from **provider-offered** options. Initially expose `ALLOW_ONCE` and `DENY`; `ALWAYS_ALLOW` is **not** a default or an implicit permission. Explicit high-risk actions use VAN's existing A4 biometric challenge on Android; the Site requires equivalently strong owner step-up, not just a logged-in Site session.

A decision envelope binds: owner principal + verified device/session, exact approval ID, task/project/scope, `session_id`, action fingerprint, control generation, `expected_revision`, `idempotency_key`, expiry and choice. The gateway verifies device proof and appropriate A4 evidence; the broker atomically compares this fence against the *currently rendered provider prompt*, dispatches exactly once, and requires a subsequent provider-state observation before reporting completion. Refuse stale generation, changed prompt, expired approval, mismatched project/branch, reused idempotency key with different body, unqualified session or unreliable capture. Never silently retry a click on uncertain outcome.

Conversation messages, project creation, task submission, scope previews, continuations and exact-job cancellation use the same project authority and journal; no blind arbitrary browser shell commands. A new Site-created project is a tracker record until admitted to the canonical project registry; it is not automatically a GitHub repository or a Muse-native project.

## Native Android (VAN)

- `Work → Muse` opens a **Jetpack Compose** workspace with conversations, current tasks, approval cards, project picker and captured results. Do not package a second Muse APK or add a WebView wrapper.
- Read via the already paired VAN gateway and its pinned mTLS/device-token path. Mutations use existing `postProved`, requiring a valid device proof; A4 retains biometric binding. Nothing sends the Site service credential to Android.
- Use a foreground SSE/stream with durable cursor/reconnect and a bounded fallback fetch, not rapid polling while the app is backgrounded. Show source age and wait/no-data states. Native push/notification taps deep link `van://work/muse` then re-fetch the *current* approval before offering actions.
- This branch establishes the screen/protocol baseline but `/v1/muse/overview` and `/v1/muse/actions` are **not yet implemented in the VAN gateway**; the native UI intentionally fails closed and cannot claim live permissions. This is not a production-ready handoff.

## DIAL Work Tracker Site

- Add **Muse → Chat / Tasks / Approvals / Projects / Inbox**, displaying the same `muse.interaction.v1` source events and receipt states as Android. Keep its already verified 175-job history/task controls and current outbound relay.
- Add structured live approval and conversation ingestion to the **existing** signed owner-command relay; **not** direct access to VAN CDP/VNC and not a new listening port. Use notification deep links back to the exact current task/approval. Do not copy VAN device credentials into Site.
- Current Site release has live task operations only. **Live provider conversation and Allow/Deny have not been implemented or verified**, and no Site source was modified in this isolated VAN branch.

## Network and qualification invariants

**No VPN/route/firewall/DNS/CDP/session/profile/service changes** are authorized by this feature branch. Existing WireGuard and VNC/noVNC remain untouched fallback surfaces. Native source/registry/permission fences are preserved. Test before/after hashes and service PIDs independently on VAN and DIAL VMs for any eventual deployment.

Acceptance must demonstrate: identical live messages and source cursor in both UIs; a real Muse permission observed on both within the lag budget; one owner-click `ALLOW_ONCE` on Android followed by provider state/ledger acknowledgment and card removal on Site, then converse Site `DENY`; changed-control/expired-approval negative tests; duplicate retry without double-click; task/project isolation; native permission notification while phone backgrounded; Site Web Push; long mobile-session reliability; network and browser invariants unchanged; exact accepted evidence. **DESIGNED != IMPLEMENTED != TESTED != DEPLOYED != QUALIFIED.**

## Handoff

1. Implement and qualify broker event producer and signed one-use browser-control action on VAN's existing authenticated session, with fake-provider tests first and bounded native canary after.
2. Wire the existing VAN gateway owner routes as trusted mediation; no new grant authority and no direct Site credential on Android. Add Android SSE/notification/deep-link and full task/project UX.
3. Deploy Site consumer/approval UI using its separate authenticated owner BFF, while preserving existing task DB and relay receipts.
4. Run cross-surface live E2E and regression checks; only then mark the feature accepted and consider Android release/production Site publication. Preserve a VNC fallback.

**Owner source:** 2026-10-12 conversation directing native implementation in VAN Android **and** the Site. This contract is a proposed implementation record on an isolated feature branch, not a new canonical decision ID.
