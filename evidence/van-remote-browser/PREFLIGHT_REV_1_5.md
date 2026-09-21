# Remote Browser Rev 1.5 — Phase −1 / Phase 0 preflight

**Blueprint:** `docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md` (8588 lines, landed unaltered)
**Repository state at preflight:** `main` = `66e4e42` (the PR #48 merge the blueprint cites)
**Date:** 2026-09-19

This is the §42.1 repository-first read and the §49 checklist, executed against the live
repository rather than trusted from the document. The blueprint is an implementation
authority that makes factual claims about this repository; those claims are checked here
before any of them is built on.

---

## 1. Phase −1 baseline — the four gates on `66e4e42`

```
maturity gate        PASSED
authority map        PASSED
ledger reconciler    PASSED   (no component understates its own integration)
kotlin reachability  PASSED
```

§35 forbids proceeding from a red baseline. The baseline is green.

## 2. Blueprint claims about this repository, checked

| claim | where | result |
|---|---|---|
| `main` descends from PR #48 merge `66e4e42` | §49 | **TRUE** — `main` *is* `66e4e42` |
| schema version is 26, next semantic migration is 27 | §0C.3, §5.6 | **TRUE** — `SCHEMA_VERSION = 26`; 27 unused |
| `events` is `seq INTEGER PRIMARY KEY AUTOINCREMENT` with no event id, device target or ms timestamp | §5.6 | **TRUE** — four columns: `seq`, `event_type`, `payload_json`, `created_at_unix` |
| `event_cursors` exists and is per-device | §5.6 | **TRUE** — `(device_id PRIMARY KEY, last_seq, updated_at_unix)` |
| `/v1/events?after_seq=` exists | §2.4 | **TRUE** — `get_events(device_id, after_seq)` → `events.replay(...)` |
| `PageLease` is task-shaped, non-renewable, no holder kind, no generation | §5.3 | **TRUE** — `lease_id, profile_alias, task_id, acquired_at_ms, expires_at_ms` |
| `BrowserTask` has no `mission_id` | §0A/S2 | **TRUE** — it carries `command_id`, `execution_id`, `capability_id` |
| `MissionBinder` has no browser-*session* binder | §0A/S2 | **TRUE** — `bind_browser_task` and `bind_automation_run` only |
| profile aliases are exactly `public_research` and `authenticated_owner` | §0A/B3, §6.1 | **TRUE** — `config/browser/profiles.yaml` |
| `runtime.profile_root` is authoritative | §0A/B3 | **TRUE** — and it points at `/var/lib/van-trading/...`, i.e. Trading Core, which is why RB-118 (stream-host profile storage) is a real open item |
| `BrowserSessionBroker`, `BrowserPolicyEngine`, `BrowserTaskService` exist and own browser authority | §2.3 | **TRUE** |
| Android has `GatewayRetry`, `EncryptedCommandQueue`, `QueueReplayer`, `ReplayTrigger`, `EventStream`, `PreferencesEventCursorStore`, `DegradedModeStore`, `SubsystemSignals`, `WakeListenerService`, `WakeCoordinator`, `WakeModelLoader`, `WakeModelAsset`, `BrowserModules` | §2.7, §49 | **TRUE** — all present |
| Android WebRTC and OkHttp are not yet dependencies | §0A/S5 | **TRUE** — neither appears in `android/app/build.gradle.kts`; RB-003 is genuinely open |
| the repository has no `deploy/van-browser-stream/` | §35 Phase 0 | **TRUE** — `deploy/` holds `systemd` and `van-trading-core` only |

Nothing in the blueprint's architectural premises was found to be false.

## 3. Discrepancies found, and how they are resolved

### 3.1 §0C.2 quotes a component ledger one commit out of date

The blueprint records:

```
Wake acknowledgement playback   CALLED_UNTESTED / device gate
TtsOutputManager.speak          CALLED_UNTESTED / device gate
```

Both were moved to `EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE` by `P2-LEDGER-002` (`85cc5e6`),
which is *inside* the merge the blueprint takes as its baseline. `CALLED_UNTESTED` no longer
exists anywhere in the ledger: all 142 components are at a terminal state.

This does not change what the blueprint asks for — those two paths are still unproven on a
device, which is what the quote was for — but §40.3's mapping table assumes non-terminal rows
are normal. They are not, in the current ledger. **New Remote Browser components may carry
`terminal_state = null`; no existing component may be moved back to it.**

### 3.2 §49's last line contradicts §5.6

```
[ ] no migration-27 event text remains normative
```

§5.6 and §5.7 make migration 27 the event-store extension. Read against §0C.3, this line is
about Rev 1.2's incorrect assumption of migration **17**, not 27. Under the §0E precedence
rule the later explicit contract governs, so: **the event-store extension is the next unused
migration, which at this baseline is 27**, resolved from the live repository at
implementation time rather than hard-coded.

### 3.3 Two names in §2.7/§49 are symbols, not files

`SubsystemHealth` is an `object` inside `degraded/SubsystemSignals.kt`; `WakeRuntimeController`
is a class inside `voice/WakeRuntime.kt`. Both exist; neither has a file of its own. Recorded
so a later agent does not conclude they are missing and build a second one — the exact
failure §42.2 forbids.

## 4. What Phase 0 cannot resolve in this repository

These are owner decisions or external artefacts, not work items an agent may choose:

- **RB-002 — the streaming host.** §0A/B1 rules out exposing private `van-trading-core`;
  §13/§25 require a dedicated dual-homed Browser Stream Host. Nothing can be provisioned
  from here.
- **RB-003 — dependency admission.** Android WebRTC and OkHttp need pinned
  versions/digests admitted through the existing dependency governance.
- **RB-040 — Stagehand adoption.** §35 Phase 7 cannot begin until the existing adoption
  decision is owner-approved and live-certified.
- **Offline-voice supersession.** §0E.2 requires
  `docs/decisions/VAN-ADOPT-OFFLINE-VOICE-RUNTIME-001.yaml` recording the owner's later
  instruction as `OWNER_SUPERSESSION`. That is a record of an owner instruction, so it is
  written only from the owner's own words, not inferred.
- **RB-120 — S24 attestation preflight.** Requires the physical device.

## 5. Standing constraint carried forward from PR #48

A Remote Browser component is `INTEGRATED_AND_EVIDENCED` only with a producer, a consumer, a
production caller, tests and runtime evidence. Until the stream host exists, everything that
depends on it is `EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE` with the absent artefact named —
never "complete" because the code compiles. That is the defect class the whole audit was
about, and the blueprint's §0 execution contract says the same thing in its own words.
