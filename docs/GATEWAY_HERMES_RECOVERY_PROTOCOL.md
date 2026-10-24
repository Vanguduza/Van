# Gateway recovery and Hermes owner-runtime protocol

This document describes the implemented gateway contract after the 2026-10-07 local
audit corrections. Local ASGI, temporary-database, signed-key, MockTransport and MCP
tests establish these gateway behaviors. They do not certify a deployed gateway, an
actual handset or the Hermes server. Historical live artifacts under `artifacts/runtime`
retain their own dates and source commits; they do not qualify later changes.

## Accepted command and uncertain handoff

The gateway authenticates the device, verifies the original signed command, resolves
the effective action class, seals owner context and creates a mission before dispatch.
An exact retry preserves that immutable request and snapshot. A changed request or
signature cannot reuse its authority or alter the original idempotency receipt.

The dispatch marker is durable before the Hermes POST. Only a definitive no-send
connection/pool failure or an explicitly supported rejection can retry the POST.
Read/write ambiguity, HTTP 408/409/5xx, a malformed acceptance receipt, or an abandoned
in-flight handoff yields `outcome_unknown`. The mission waits externally with a deadline;
an exact retry returns the same uncertainty and does not start another run.

A valid create response must contain a nonempty string `id`. The gateway durably records
that observed run ID before audit/verification work can fail. If its own acknowledgment
is interrupted, an exact authenticated retry recovers the receipt without another POST.
That receipt recovery does not renew intent, restart canceled work or grant new actions.

If a process stops after authority sealing but before the mission's AUTHORIZED transition,
an exact unexpired retry may finish that transition for a remote command only when no
dispatch marker exists. This is a proven no-send boundary; local executors and any marked
or uncertain handoff retain their existing reconciliation guards.

The available Hermes integration supports health, run creation and capability reads.
No evidenced run lookup, cancellation or idempotent-create schema is present in the
available server sources/contracts. The gateway therefore does not guess such routes.
Automatic reconciliation of a handoff whose create receipt was never observed remains
an integration requirement. Mission cancellation stops future gateway-authorized starts;
it does not prove an already-running remote operation stopped.

## Durable lifecycle callback

The runtime-scoped endpoint `POST /v1/runtime/missions/result` accepts:

```json
{"hermes_run_id":"run-id","status":"COMPLETED","summary":"worker lifecycle report"}
```

Allowed statuses are `COMPLETED`, `FAILED`, `WAITING_FOR_OWNER` and `WAITING_EXTERNAL`.
The worker cannot choose a mission or report `VERIFIED_SUCCESS`. Only a gateway-observed
run receipt creates the immutable run-to-mission binding.

Authenticated reports enter a durable inbox even when they arrive before the create
response. The endpoint returns 202 with `WAITING_FOR_BINDING` and a `receipt_id` while
unbound, or `QUEUED` when another consumer holds its processing lease. No mission moves
until the real receipt binds the run. Reports are replayed in arrival order after binding;
the existing mission-deadline job reconciles pending/expired-lease reports before expiry.
A gateway restart does not discard either inbox or binding.

An applied report returns 200 with `status: APPLIED`, mission state and verification
state. Duplicate outcomes reuse their receipt. A conflicting terminal report returns
409. Cancellation and terminal observations remain authoritative under concurrent
verification. Interrupted processing can resume from VERIFYING without fabricating
success or sending remote work again.

`COMPLETED` initiates independent mission verification. Empty/unobservable contracts
finish UNVERIFIABLE; a worker report and provider submission receipt do not prove success.
Generic action verification also remains an untrusted report. Only audited service
observers may produce independently observed action receipts.

## Safe reasoning tools

The fixed `van_owner_runtime` MCP allowlist exposes:

| Tool | Runtime-scoped operation |
|---|---|
| `assumption_record` | Record an assumption against an existing mission |
| `assumption_blocking` | Read unresolved HIGH/CRITICAL blockers |
| `premise_record` | Record a premise assessment and cited evidence for reasoning metrics |

These operations do not admit owner truth, resolve approvals or widen action authority.
Model-supplied evidence-reference strings cannot mark assumptions VERIFIED/FALSIFIED.
Supersession cannot replace a HIGH/CRITICAL blocker with a nonblocking obligation.
No generic assumption-resolution tool is exposed until a deterministic observer can
correlate the exact assumption with its observed postcondition. The service-internal
observer flag is never accepted as a caller-body authority field.

## Recoverable first pairing response

Android first validates the signed provisioning payload and durably stores its pending
device ID, HMAC secret, candidate access token and exact pairing body in encrypted local
storage. No universal credentials are embedded in the APK. It binds the chosen device ID
to its attested hardware identity before pairing.

New recovery-capable pairing adds `device_access_token` to the existing pair body. It
must contain at least 32 characters of client-generated cryptographic randomness. The
gateway requires a fresh signature from the active, chain-verified bound hardware key
over the exact `POST /v1/devices/pair` body, and consumes its proof nonce durably.
The enrollment transaction checks the exact binding ID again before committing.

Enrollment, ticket consumption, grant, access-token hash and immutable pairing-attempt
digest commit together. The gateway stores no recoverable access-token copy. An exact
retry may return ingress credentials and the same client-known token after a new valid
proof, even after the consumed ticket's original issuance window has elapsed. It neither
spends a new ticket nor mints a device/grant/token. A changed body/token, absent attempt,
revoked device, changed/revoked hardware binding or rotated access-token hash refuses.
Legacy server-generated tokens remain single-return and have no receipt-recovery path.

## Recoverable session opening and socket admission

`POST /v1/session/open` accepts an optional `open_request_id` of 16–128 URL-safe letters,
digits, `_` or `-`; a UUID is suitable. Android persists that ID and its exact body before
POST. The response echoes the ID so an older server that ignored it cannot masquerade
as a recovery-capable server.

The gateway derives a device-scoped stable session ID and atomically records the session,
first path and opening-parameter digest. Exact retries return that session and its current
authoritative epoch without another path grant. Changed parameters return 409
`session_open_request_conflict`; a closed session returns 409 `session_closed`. An opening
without a request ID retains legacy distinct-session behavior.

WebSocket admission verifies device token, session ownership, strict binding/attestation
policy and a fresh one-use hardware proof for `GET /v1/session/ws` with empty body. Only
a server-verified matching mTLS certificate can substitute for the request proof. Caller
certificate headers cannot mint that identity. Token/binding revocation is rechecked
before inbound control frames and downstream polling; competing loops share one shielded
close operation so receiver shutdown cannot cancel the refusal frame.

An accepted handshake writes `session.transport.admitted` with the observed device,
session, binding, actual certificate serial, certificate-match flag and proof-verification
flag. It contains no tokens or signatures. This is historical transport admission,
not current liveness, Hermes execution or verified task completion.

## Recoverable session operations

Session message admission checks both the message ID and the session-scoped idempotency
key under one SQLite write transaction. The operation kind, command identity and actual
payload digest must all match; message-ID reuse across sessions cannot read another
session's result. Unkeyed envelopes still deduplicate by their exact message ID.

A known message with no completed result is not acknowledged as successful. HTTP returns
503 `session_result_pending`; WebSocket returns an acknowledgement with `accepted: false`
and that refusal. A resume snapshot reports `RESULT_PENDING`; Android retains its exact
original in-flight envelope and durable outbox entry until the existing authority supplies
a result. A generic transport admission without a recorded result does not settle it.

The production recovery delegate uses the existing operation authorities. Command recovery
reuses the originally signed request and the command orchestrator's durable idempotency;
a definitive no-send/rejection can recover from `degraded`, while an uncertain Hermes
handoff remains `outcome_unknown` and is never dispatched again. An in-flight command
remains pending. This closes the outer session cache's former permanent `degraded` result
without widening the sealed authority or refreshing owner intent.

Decision answers must be actual JSON booleans on both REST and session carriers. Their
first APPROVED/REJECTED answer is atomic and immutable: exact response recovery preserves
the original timestamp, and an opposite answer or expired decision returns
`decision_already_resolved`. Attention recovery may finish marking the same decision
handled; it cannot reverse that decision.

Mission cancellation is idempotent once VAN actually observes CANCELLED. State and its
`mission.cancelled` timeline event commit together. This still establishes only VAN's
mission cancellation and refusal of future starts, not termination of remote work.
Session mission notes use a server-derived stable operation identity; retrying an
interrupted acknowledgement records one `mission.message` event and returns its original
event ID. A note never reports that Hermes adopted it or executed new work.

Each resume grants a distinct authoritative path epoch in a single transaction with its
new path descriptor. A failed path write rolls the grant back. Admission rechecks the
current epoch under its own transaction, so a resume that won while a message waited for
admission cannot admit work from the retired path.

## Exact values in biometric approval

An `approval_required` command result supplies the resolver's `resolved_parameters`
alongside its action ID. The original biometric challenge's intent digest binds those
exact normalized parameters as well as its existing device, action, text and project
identity. Before consuming the proof, the gateway compares the current resolution with
that digest. Changed parameters and an old text-only challenge cannot authorize the
parameter-bound gateway path. The canonical v2 challenge structure and Android signature
algorithm remain unchanged; its digest is opaque to the device.

`send gmail draft id <draft-id>` resolves to `google.gmail.send` A4. A direct owner
command first reads the actual provider draft and binds `draft_id` plus its semantic
`draft_content_sha256` in the challenge. The digest covers thread, sender, all To/Cc/Bcc
recipients, reply headers, subject and decoded plain body. `approval_preview` supplies
safe sender/recipient/subject/body-digest fields; private plaintext is available only on
the paired-owner draft preview endpoint. Preview content remains untrusted external data.
An unavailable or unqualified preview cannot issue approval; a changed draft invalidates
the old proof without consuming it or treating the edit as owner-signature forgery.

Execution rechecks the approved digest and sends an immutable reconstructed MIME payload
using Gmail `messages.send`. It does not consume/delete the mutable source draft:
`source_draft_cleanup=NOT_ATTEMPTED`, `source_draft_state=UNOBSERVED`. Mission strategy
`gmail-sent-readback` locates the message through canonical action correlation and then
independently fetches its raw MIME. The sealed owner authority, exact semantic digest,
thread and SENT label must match; a worker's completion or old action receipt is
insufficient. No atomic conditional draft-send capability is claimed.

`confirm trading ticket ` followed by JSON exactly containing string `ticket_id`,
`fill_price`, `filled_qty` and `contract_note_ref` resolves to `trading.ticket.confirm`
A4. Bounded finite positive plain decimal values are normalized before approval. The
owner must also supply `client_context.owner_ticket_authority_ref`, an independently
signed trading credential with act `ticket-confirm` and subject equal to that ticket.
No body flag, biometric approval alone or arbitrary reference substitutes for it.
The local executor and separate mission strategy read the ledger afresh, require exact
confirmation values and a valid hash chain, and cite the confirmation event. This proves
the owner-recorded broker confirmation, not broker order placement or execution.

## Optional independent remote Git and CI observations

The gateway can configure `repository-sha` and `ci-run` against the fixed HTTPS GitHub API.
`VAN_GITHUB_VERIFICATION_REPOSITORIES` is a comma-separated allowlist of `owner/repository`
identities. `VAN_GITHUB_VERIFICATION_TOKEN_FILE` optionally binds a private read-only API
credential in a regular absolute-path file with no group/other permissions; it is read
per request so rotation applies without restart. No repositories or credentials are
configured by default. DIAL worker-local Git state and cached CI/receipt projections are
not substituted for fresh remote observation.

`RepositoryHeadPostconditions` requires `repository`, `branch`, full lowercase 40-character
`commit_sha`, and `repository_head_matches=true`. `CiRunPostconditions` also requires digit
string `run_id` and `workflow_id`, positive integer `run_attempt`, integer
`ci_requested_after_unix_ms`, and true `ci_run_matches`, `ci_completed`, `ci_success`.
Unknown fields or implicit/coerced identity types refuse. Git reads the exact remote
branch head; CI reads the exact workflow run attempt, checks repository/head/branch,
workflow/run/attempt, completed-success status and bounded timestamps, and reads the
remote branch again. Requests are GET-only, fixed-origin, TLS-verified, redirect-free,
proxy-free, time-bounded and size-bounded. Unconfigured sources and provider faults remain
UNVERIFIABLE; mismatching immutable identities remain failed verification.
