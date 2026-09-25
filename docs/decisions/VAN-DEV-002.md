# VAN-DEV-002 — DIAL approvals and blockers in Attention (backend)

**Design authority:** DIAL `VAN-DEVCC-R1` §2.2 ("Why Approvals and Blockers live in
Attention") and §8 ("Attention: dedupe per §2.2; closes only on projection APPLIED").
**Depends on:** VAN-DEV-001 (the proxy client), DIAL HOT-DU-008 (the projection and its
event stream).

**Status: IMPLEMENTED (repository), live verification PENDING.**

### Why here

VAN already has one triage surface with severity, dedupe and snooze
(`backend/van_gateway/attention/engine.py`). A second approvals list would split the owner's
"needs me" view. DIAL owner decisions and blockers therefore become Attention items.

### What was built

`backend/van_gateway/dial_dev/attention.py` — `DialDevAttentionIngest`, started by the app
lifespan when `VAN_DIAL_DEV_ENABLED` and `VAN_DIAL_DEV_ATTENTION_ENABLED` are both true, and
stopped on shutdown. `AttentionEngine.auto_resolve` was added so a source that is itself
authoritative for a condition can close it with evidence recorded on the row.

Behaviour:

1. Consumes DIAL's SSE `GET /v1/dev/events` (`{projection_revision, changed[]}` frames).
2. On every connect — so a reconnect **rehydrates** from the projection rather than from
   memory — and on any frame whose `changed[]` names `tasks`, `decisions`, `security` or
   `leases` (or that cannot be decoded), it reads `GET /v1/dev/projects` and, per project,
   `GET /v1/dev/projects/{p}/tasks?view=needs_me`.
3. Each owner item is upserted:

   ```text
   source      = "dial-dev"
   project_id  = <DIAL project id>
   dedupe_key  = "dial-dev:<kind>:<decision_id or task_id>:<projection_revision_of_origin>"
   severity    = lease_bypass, or finding_domain in {security, money, health} → URGENT
                 blocker with critical_path                                     → BLOCKER
                 otherwise (WAITING_OWNER approvals, off-path blockers)        → FOLLOW_UP
   payload     = { task_id, kind, deep_link: "van://work/dev/tasks/<id>", decision_id?,
                   dial_identity, projection_revision_of_origin, last_seen_projection_revision }
   ```

   The origin revision is DIAL's `origin_projection_revision` when stated; otherwise the
   revision at which VAN first saw the still-open condition (kept stable across re-reads);
   otherwise the current envelope's `projection_revision`.
4. **Closing.** An item becomes `AUTO_RESOLVED` only when a projection shows its
   `resolution_state == "APPLIED"` — in `needs_me`, or, for an item DIAL stopped listing, in
   `GET /v1/dev/tasks/{taskId}`'s `owner_items[]`. A tap (acknowledge/snooze) never closes it.
   Absence without APPLIED evidence — including `ACCEPTED`, `REJECTED`, `SUPERSEDED` or the
   task being unknown to DIAL — leaves it open. A closed item is never reopened by a late
   re-read of the same origin.
5. Stream failure: reconnect with exponential backoff (1 s → 60 s), and
   `DIAL_DEV_EVENT_STREAM_DOWN` in the degraded registry while disconnected. A sync that finds
   DIAL unreachable sets `DIAL_DEV_UNAVAILABLE` and changes nothing.
6. It never acts on DIAL: GETs only (tested), no import of VAN's Hermes, orchestrator, mission
   or command services (contract-tested).

### Projection shapes this unit reads (the DIAL projection server is held to them)

```text
GET /v1/dev/projects                          data.projects[].project_id
GET /v1/dev/projects/{p}/tasks?view=needs_me  data.tasks[] = { task_id, title?, state?, critical_path?, owner_items[] }
GET /v1/dev/tasks/{taskId}                    data.task_id, data.owner_items[]

owner_item = { kind: "approval" | "blocker" | "finding" | "lease_bypass",
               decision_id?, title?, finding_domain?, critical_path?,
               origin_projection_revision?,
               resolution_state?: "OPEN" | "ACCEPTED" | "APPLIED" | "REJECTED" | "SUPERSEDED" }
```

An unknown `kind`, a non-object item, or an identifier outside
`^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$` is skipped and counted, never guessed.

### Requirements and their proofs

| ID | Requirement | Proof (`backend/tests/test_dial_dev_attention.py`) |
|---|---|---|
| VAN-DEV-002-R1 | Severity mapping per §2.2 | `test_severity_follows_section_2_2` |
| VAN-DEV-002-R2 | Item shape: source, project, dedupe key, payload, deep link | `test_an_owner_item_becomes_one_attention_item_with_the_contract_shape` |
| VAN-DEV-002-R3 | Dedupe: same condition across revisions is one item; DIAL origin honoured | `test_rereading_the_same_condition_at_a_later_revision_is_the_same_item`, `test_dials_own_origin_revision_is_the_key_when_it_states_one`, `test_a_blocker_without_a_decision_is_keyed_by_task` |
| VAN-DEV-002-R4 | Never closes on tap | `test_a_tap_does_not_close_the_item` |
| VAN-DEV-002-R5 | Never closes on absence without APPLIED | `test_disappearing_from_needs_me_without_applied_evidence_leaves_it_open`, `test_a_task_dial_no_longer_knows_leaves_the_item_open` |
| VAN-DEV-002-R6 | Closes on APPLIED, from either projection | `test_the_item_closes_when_the_task_projection_shows_applied`, `test_the_item_closes_when_needs_me_itself_reports_applied` |
| VAN-DEV-002-R7 | Rehydrate on connect, resync only on relevant changes | `test_the_worker_rehydrates_on_connect_and_resyncs_on_task_changes`, `test_a_workspace_only_change_does_not_resync` |
| VAN-DEV-002-R8 | Reconnect with backoff; degraded while down, cleared when up | `test_a_dropped_stream_is_degraded_and_reconnects_with_backoff`, `test_a_connected_stream_clears_the_degraded_entry` |
| VAN-DEV-002-R9 | Started and stopped with the app, only when enabled | `test_the_app_starts_and_stops_the_worker_only_when_enabled`, `test_dial_dev_proxy.py::test_disabled_is_404_feature_disabled` |

Authority map subject: `dial_dev.attention_ingest`.

### Open points for owner review

1. **SUPERSEDED never closes an item.** The design says an item closes only on APPLIED. A
   decision DIAL supersedes therefore stays open until the owner handles it; the newer
   decision appears as its own item. If superseded items should close, that is a design change.
2. **A task DIAL forgets leaves its item open forever** (no APPLIED evidence can arrive).
   The Attention engine's 7-day STALE marking still applies to it.

```yaml
unit_id: VAN-DEV-002
design_ref: DIAL VAN-DEVCC-R1 §§2.2, 8
implementation_status: REPOSITORY_COMPLETE_LIVE_UNVERIFIED
owner_signature_status: PENDING
owner_signature_evidence_ref: null
project_truth_authorization: PENDING_OWNER_RECORD
```
