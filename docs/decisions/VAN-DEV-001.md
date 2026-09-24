# VAN-DEV-001 — DIAL development projection proxy (backend)

One unit per file, in VAN's Development Pack for the DIAL Development Control Centre.

**Design authority:** DIAL `VAN-DEVCC-R1` — *VAN Development Control Centre Design Rev 1*
(`dial-development-system/docs/dial/final-audit/06_DEVELOPMENT_SYSTEM/VAN_DEVELOPMENT_CONTROL_CENTRE_DESIGN_REV_1.md`),
§§3, 3.4, 7, 8. Finalised in DIAL under owner decision OD-C ("design and logic finalised in
DIAL, built in VAN"). This file is the VAN-side implementation record; it does not restate
the design and does not own it.

**DIAL dependency:** HOT-DU-008 (the Development Projection API v1 on `dial-control`). Until
that server exists, this unit is repository-complete and live-unverified.

**Status: IMPLEMENTED (repository), live verification PENDING.** Owner implementation
authority is recorded as pending below; an agent may not mark it signed.

### What VAN does and does not do

VAN **displays** DIAL development state and **forwards typed owner commands** to DIAL. It
never plans, schedules or executes DIAL work. Hermes profile `van` stays VAN's sole agent
runtime (`docs/SECURITY_POLICY.md`, "Hermes execution boundary"); the `dial_dev` package does
not import VAN's Hermes bridge, orchestrator, mission or command services, and a contract test
fails if it ever does.

### What was built

`backend/van_gateway/dial_dev/`:

| File | Role |
|---|---|
| `config.py` | Paths (`/v1/dial-dev` → `/v1/dev`), the closed action set, task views, envelope keys, identifier rule, `DialDevConfig` |
| `client.py` | Typed httpx client. Bearer read from the token file on every call (rotation needs no restart); no Android header is forwarded; redirects not followed; proxy env ignored; any DIAL answer containing the credential is refused (`upstream_echoed_credential`) |
| `api.py` | The `/v1/dial-dev/*` router: 19 reads, the SSE passthrough, `POST /actions` |
| `degraded.py` | DIAL `degraded[]` → VAN `DegradedCode` (VAN-DEV-010) |

Configuration (`backend/van_gateway/config.py`, env prefix `VAN_`):

| Variable | Default | Meaning |
|---|---|---|
| `VAN_DIAL_DEV_ENABLED` | `false` | Off → every `/v1/dial-dev/*` answers `404 {"error":"dial_dev_disabled"}` |
| `VAN_DIAL_DEV_BASE_URL` | empty | WireGuard address of `dial-control`, e.g. `http://10.77.0.1:<port>` |
| `VAN_DIAL_DEV_TOKEN_FILE` | empty | Gateway-side file holding the DIAL-scoped bearer (≥ 32 chars, no whitespace) |
| `VAN_DIAL_DEV_TIMEOUT_S` | `10` | Per-request timeout (SSE: connect only) |
| `VAN_DIAL_DEV_STALE_MS` | `30000` | Stale threshold sent to the device beside the envelope |
| `VAN_DIAL_DEV_WORKSPACES_STALE_MS` | `10000` | Same, for workspace routes |
| `VAN_DIAL_DEV_ATTENTION_ENABLED` | `true` | VAN-DEV-002 ingestion worker, when the proxy is enabled |

### The route contract (Android and the DIAL projection server are held to it)

Every route is on the VAN gateway. Reads need the ingress token + device token (the same
middleware every owner GET uses; no hardware proof, so a poll never costs a Keystore
signature). The one mutation needs a verified hardware device proof.

| VAN route | DIAL upstream | Notes |
|---|---|---|
| `GET /v1/dial-dev/projects` | `GET /v1/dev/projects` | |
| `GET /v1/dial-dev/projects/{p}/home` | `GET /v1/dev/projects/{p}/home` | |
| `GET /v1/dial-dev/projects/{p}/stage-plan` | `GET /v1/dev/projects/{p}/stage-plan` | |
| `GET /v1/dial-dev/projects/{p}/tasks?view=` | `GET /v1/dev/projects/{p}/tasks?view=` | `view` required: `now next in_progress needs_me blocked review failed completed all` |
| `GET /v1/dial-dev/projects/{p}/graph` | `GET /v1/dev/projects/{p}/graph` | |
| `GET /v1/dial-dev/tasks/{taskId}` | `GET /v1/dev/tasks/{taskId}` | |
| `GET /v1/dial-dev/agents` | `GET /v1/dev/agents` | |
| `GET /v1/dial-dev/workspaces` | `GET /v1/dev/workspaces` | stale header 10000 |
| `GET /v1/dial-dev/workspaces/{id}` | `GET /v1/dev/workspaces/{id}` | stale header 10000 |
| `GET /v1/dial-dev/workspaces/{id}/diff` | `GET /v1/dev/workspaces/{id}/diff` | stale header 10000 |
| `GET /v1/dial-dev/workspaces/{id}/terminal-tail?lines=` | `GET /v1/dev/workspaces/{id}/terminal-tail?lines=` | `lines` 1–200, default 200 |
| `GET /v1/dial-dev/{reviews,memory,research,design,ci,security}` | `GET /v1/dev/{same}` | |
| `GET /v1/dial-dev/evidence/{ref}` | `GET /v1/dev/evidence/{ref}` | |
| `GET /v1/dial-dev/infrastructure` | `GET /v1/dev/infrastructure` | VAN-DEV-010 |
| `GET /v1/dial-dev/events` | `GET /v1/dev/events` (SSE) | relayed line by line, `text/event-stream` |
| `POST /v1/dial-dev/actions` | `POST /v1/dev/actions` | device proof, closed set, idempotent |

Identifiers (`{p}`, `{taskId}`, `{id}`, `{ref}`) must match
`^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$` and contain no `..`; anything else is refused before
DIAL is asked.

**Responses.**

* Read 2xx: DIAL's body **byte for byte** — the §3.1 envelope
  `{projection_revision, observed_at, sources, freshness_ms, degraded[], data}` — plus headers
  `Cache-Control: no-store` and `X-Van-Dial-Dev-Stale-After-Ms`. A 2xx body missing any
  envelope key is not relayed: `503 upstream_malformed`.
* DIAL's own 4xx (404, 409 `STALE_VIEW`, 422 …) other than 401/403: passed through unchanged,
  status and body.
* DIAL unreachable / timeout / 5xx / 401 / 403 / redirect / malformed:
  `503 {"error":"dial_dev_unavailable","reason":R}` with `R` ∈ `unconfigured`,
  `credential_invalid`, `unreachable`, `timeout`, `upstream_error`, `upstream_auth_refused`,
  `upstream_redirect`, `upstream_malformed`, `upstream_echoed_credential`. No exception text,
  URL or address is ever included.
* Disabled: `404 {"error":"dial_dev_disabled"}`.
* Refused by the gateway: `422 {"error":"dial_dev_request_invalid","reason":<field>}`, or for
  an action outside the set `422 {"error":"dial_dev_action_not_allowed","reason":"action_not_allowed"}`.

**Action body** (device → gateway; closed, unknown fields refused):

```json
{
  "action": "PAUSE_TASK_SAFE",
  "target": { "project_id": "dial-development-system", "task_id": "HOT-DU-021", "decision_id": "…" },
  "params": {},
  "idempotency_key": "8–128 chars",
  "expected_projection_revision": "sha256:…"
}
```

`action` ∈ `STEER_TASK PAUSE_TASK_SAFE RESUME_TASK REQUEST_CHECKPOINT REQUEST_REVIEW
REVOKE_TASK DECIDE PAUSE_MISSION RESUME_MISSION REPRIORITISE`. `target.project_id` always;
`target.task_id` for the six task actions; `DECIDE` needs `target.decision_id` and
`params.decision` ∈ `APPROVE|REJECT`; `STEER_TASK` needs `params.guidance` (1–4000 chars).

Forwarded to DIAL: the five fields above plus `owner_device_proof_ref`, which the **gateway**
mints (`van-device-proof:sha256:<hex>` over device id, proof timestamp and proof signature). A
device-supplied `owner_device_proof_ref` is ignored.

Answers: DIAL's `202 {action_id, state:"ACCEPTED"}` relayed unchanged; `409 STALE_VIEW`
relayed unchanged; a replay of a completed key returns the stored answer with
`X-Van-Idempotent-Replay: true`; same key, different request → `409 {"error":"idempotency_conflict"}`;
concurrent duplicate → `409 {"error":"idempotency_in_flight"}`; unbound device or unverified
proof → `403 {"error":"device_proof_required"}` (bound device with no proof is refused earlier by
the middleware: `401 {"detail":"device_proof_required"}`).

Idempotency uses the existing `IdempotencyService`, keys namespaced `dial-dev:<key>`. A
2xx completes the key. A DIAL refusal or an unreachable DIAL marks it FAILED, so the
**identical** request may be retried under the same key (DIAL de-duplicates on the key if a
timed-out attempt did land). After `STALE_VIEW` the request changes (new expected revision),
so the device must mint a **new** key.

### Requirements and their proofs

| ID | Requirement | Proof |
|---|---|---|
| VAN-DEV-001-R1 | Reads require owner-device auth; internal control credentials are not an owner device | `backend/tests/test_dial_dev_proxy.py::TestReadsNeedOwnerDeviceAuth` |
| VAN-DEV-001-R2 | `POST /actions` requires a verified hardware device proof, including on an unbound device | `TestActionsNeedADeviceProof`, `test_an_unbound_device_cannot_act_on_dial_on_its_token_alone` |
| VAN-DEV-001-R3 | The DIAL credential reaches DIAL and never any response, header, error or SSE line | `TestTheCredentialNeverComesBack`, `test_the_bearer_reaches_dial_and_no_van_credential_does` |
| VAN-DEV-001-R4 | Envelope passed through unchanged; 409 STALE_VIEW passed through unchanged | `TestEnvelopePassThrough` |
| VAN-DEV-001-R5 | DIAL unreachable → 503 `dial_dev_unavailable`; degraded registry reflects it and recovers | `TestDialUnavailableIs503` |
| VAN-DEV-001-R6 | Closed action set; malformed actions never leave the gateway | `TestRequestsAreRefusedBeforeDialSeesThem` |
| VAN-DEV-001-R7 | A retried action is forwarded once | `TestIdempotentRetry` |
| VAN-DEV-001-R8 | Android holds no DIAL address, credential, config name or `/v1/dev/` path; every `/v1/dial-dev` path it builds is served | `tests/contracts/test_dial_dev_boundary.py` |
| VAN-DEV-001-R9 | Authority subjects cannot silently disappear | `tests/contracts/test_authority_map.py::test_dial_development_subjects_cannot_disappear` |

Authority map subjects: `dial_dev.projection_proxy`, `dial_dev.action_forwarder`
(`docs/project-state/AUTHORITY_MAP.yaml`).

### Decisions taken in implementation (for owner review)

1. **Authority-map owners are VAN documents.** §3.4 says the subjects are "owner DIAL". The
   authority-map gate only admits owners listed in `owning_documents`, all of which are VAN
   files; DIAL's design file is not in this repository. The two proxy subjects are owned by
   `docs/SECURITY_POLICY.md` (credential isolation, signed/idempotent mutations) and the
   attention subject by `docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md`. Declaring a new
   owning document is a deliberate owner act and was not taken.
2. **Actions refuse the unbound-device fallback.** Other owner mutations accept a token-only
   request from an unbound device while `VAN_REQUIRE_DEVICE_BINDING=false`. §1 of the design
   requires hardware device proof for every dev action, so this route does not.
3. **`REVOKE_TASK` / reject-decision carry no separate A4 owner-approval challenge on the
   gateway.** The design places the destructive confirmation in the device's `ApprovalSheet`
   (VAN-DEV-009) and the execution in DIAL. Whether VAN's A4 rule should additionally require
   an `OwnerApprovalProof` bound to the action is an owner question, recorded below.

### Not done here

Android (VAN-DEV-003…009, 011) is a separate unit. Live verification against DIAL HOT-DU-008
and the §8 E2E (with HOT-DU-048) need the DIAL server and are external gates.

### What the owner is asked to decide

1. Whether the owners chosen in decision 1 are acceptable, or whether a VAN-side copy of the
   VAN-DEVCC-R1 contract should be declared an owning document.
2. Whether `REVOKE_TASK` and `DECIDE`/`REJECT` should require a VAN A4 owner-approval proof in
   addition to the device proof (decision 3).

```yaml
unit_id: VAN-DEV-001
design_ref: DIAL VAN-DEVCC-R1 §§3, 3.4, 7, 8
implementation_status: REPOSITORY_COMPLETE_LIVE_UNVERIFIED
owner_signature_status: PENDING
owner_signature_evidence_ref: null
project_truth_authorization: PENDING_OWNER_RECORD
```
