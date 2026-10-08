# Browser effects and owner files

Repository implementation is separate from host and handset qualification. No
deployed Oracle, VEKL, browser host, or S24 effect is claimed by this document.

## Exact implemented contracts

Owner routes use the existing device proof classifier on
`/v1/browser/interactive-sessions/{session_id}`:

The owner first submits the exact signed A3 command
`prepare browser task {"session_id":"…","target_domain":"…","goal":"…"}`.
The domain must match the currently authenticated native origin projection;
the goal is bounded to 1,000 characters. This binds a nonmutating task to the
command's existing Mission without starting a worker or delegating control.
The preparation Mission remains RUNNING under a finite deadline because the
broader freeform goal has no independent success contract.

- `POST /action-plans`: immutable idempotent draft with existing mission-bound
  `task_id`, current `target_id`, deadline (maximum 15 minutes), and 1–12 exact
  `click_element`/`fill_element` steps. Duplicate step IDs, scripts, unknown
  fields, cross-domain URL predicates and unsealed fill values are refused.
- `GET /action-plans`: owner-scoped plans plus the actual current mission/profile
  task candidates, exact observed preparation domain, 30-second command freshness,
  and explicit current canonical/registered profile mutation posture.
  `GET /action-plans/{plan_id}` reads durable status.
- `POST /action-plans/{plan_id}/cancel`: fences later dispatch. It does not undo
  an already admitted external operation.

The draft returns `approval_command` in the exact form
`execute browser plan {"session_id":"…","plan_id":"…","plan_sha256":"…"}`.
Only the existing signed A4 command and fresh bound biometric admission can
authorize `browser.plan.execute` with all three exact parameters. An advisory
decision answer never creates browser scope authority or resumes a stopped task.
Each prepared task permits one immutable plan. Both the canonical profile and
the current broker record must permit gateway-authorized mutation; a public
research profile cannot authorize these effects.

The private broker resolves `click_element`, `fill_element`, `observe_effect`
using only `{plan_id,plan_sha256,step_id}` references. It retrieves selectors,
values and predicates from the immutable plan. Raw `dispatch_input` remains
unavailable to task automation. Profile/control generation, current target,
device revocation, mission pause, sealed command expiry, viewport acknowledgement
and current real page domain are checked at each native effect boundary. Each
native boundary fences both the prepared parent Mission and the command's
current canonical Mission, under the same broker transaction. Standing automation
and advisory answers cannot substitute for the exact OWNER_COMMAND source.
Each
effect is durably claimed before dispatch. Credential fields, ambiguous selectors,
occluded click targets and off-screen geometry are refused. Two fixed bounded
DOM property getters are internal readback conversations; caller JavaScript is
never accepted. Semantic proposals can produce a draft, but cannot execute it.

Per-step native dispatch receipts do not prove completion. A distinct native
readback must match the sealed predicate. The canonical ActionRuntime verifier
calls `BrowserActionPlanService.verify` for another independent post-submission
readback, then the Mission verifier performs its own final readback after the
ActionExecution reaches VERIFIED_SUCCESS. That terminal execution admits only
observation, never another mutation. The grant reserves exactly four calls per
step: effect, initial native observation, action verifier and Mission verifier.
Missing/false outcomes cannot become verified success. A lost reply
leaves `UNKNOWN`; a claimed mutation is never automatically replayed.

After actual plan ActionReceipt and Mission verification, preparation completion
rechecks the exact owner authority, plan hash, source task/Mission bindings and
independent native predicates before completing the task. It closes the original
freeform Mission UNVERIFIABLE and records `approved_effects_verified=true` with
`freeform_goal_independently_verified=false`. Taking control and submitting a new
fresh signed preparation can bind a new task/Mission while retaining the old
session activity as historical evidence. If metadata reconciliation was
interrupted after the durable verified-plan marker, the new signed preparation
can finish that metadata update; it never repeats the browser effect.

File routes use the existing current owner lease, media acknowledgement and
one-use stream transfer authority:

- `POST /transfer-grants` adds `analyse`, with exact `target_id`/`download_id`.
  It permits a classified completed or quarantined hashed native artifact.
  Empty `POST host_url` at `/files/analyse/{download_id}` performs bounded
  static inspection, reopens with NOFOLLOW, verifies the approved hash/size and
  returns an inert UTF-8 preview (up to 64 KiB) or binary metadata. It never runs
  content, macros, archives or embedded instructions. Result authority is
  `UNTRUSTED_FILE_EVIDENCE`, not owner truth.
- `GET /downloads/{download_id}/operations` recovers metadata-only authenticated
  analysis receipts after reply loss. It does not return file contents.
- `POST /transfer-grants` adds `file_import` with exact `target_id`,
  `byte_size`, `content_sha256`, `suggested_name`, optional `mime_type`.
  The gateway generates `resource_id=import_<uuid>`. `POST host_url` at
  `/files/import/{resource_id}` consumes that exact one-use grant, streams at
  most 64 MiB, seals the confined file, independently rehashes it, then reports
  a real download record. The owner recovers reply loss through the download
  record for that resource ID. Import is not a browser file chooser operation.
- Existing `download` grants deliver safe bytes for inert open and send to the
  owner's phone; existing `upload` grants attach exact approved phone bytes to
  the current native chooser. Quarantined content cannot be opened or sent.

Direct host requests retain the existing `X-Van-Producer-Session` header and
one-use bearer grant; upload/import additionally require the exact content length
and `X-Van-Content-SHA256`. No frontend URL, credential or host configuration is
introduced. Native TLS/route binding remains a deployment prerequisite.

## Oracle archive / VEKL candidate provider boundary

`backend/van_gateway/browser/artifact_provider.py` implements the strict VAN
consumer for proposed `VAN_OWNER_ARTIFACT_ADMISSION_V1`. It remains unbound;
SAVE_ON_ORACLE and ADD_TO_VEKL must stay unavailable until the actual target
implements and qualifies this contract. A local archive or staging record is
not evidence that either function happened on Oracle or in VEKL.

The provider needs an explicitly admitted owner/project namespace and exact
provider identity (`ORACLE_OWNER_ARCHIVE` or `VEKL_OWNER_CANDIDATE_INGRESS`),
private authenticated route, private CA, separate mTLS client identity and an
operator-verified capability receipt digest. GET
`/v1/owner-artifacts/capabilities` must return the exact contract, provider,
identity, admitted namespace and `current_admission_introspection=true`.
The VEKL target additionally requires an actual `oracle_instruction_job_id`.

`browser/artifact_admission.py` now implements immutable owner draft creation,
native persisted-byte retrieval, dedicated ES256 admission minting and provider
introspection/atomic one-use claims. The composed canonical action is
`browser.file.provider.submit` at A4 with exactly `session_id`, `request_id` and
`request_sha256`; the sealed draft binds the namespace, source ID/hash/size,
provider identity/pin, profile generation and idempotency key. The Android owner
reviews this exact request and submits its returned `approval_command` through
the existing fresh biometric approval flow. A caller boolean, owner decision,
bearer role credential or uploaded file instruction cannot supply admission.

The claim callback authenticates the actual verified mTLS leaf through
`auth/provider_transport.py`, pins its exact provider and owner/project scope,
then rechecks configuration/device/mission/consent under the same writer lock
that consumes the claim. Write admission lasts at most 30 seconds. The same
immutable token carries a separate five-minute observation expiry; only an
already consumed claim may use that later window for readonly receipt/content
inspection. Neither inspection nor re-signing the unchanged claims renews the
write window or permits another claim.

The actual target service and its governed namespace/Oracle job/private identity
remain external prerequisites. The default operator config is empty; a config
file or an online Commander does not prove a currently qualified provider.
Detailed routes and operator binding schema are in
`VAN_OWNER_ARTIFACT_ADMISSION_V1_2026-10-08.md`.

`PUT /v1/owner-artifacts/{owner}/{project}/{sha256}` takes bounded inert bytes,
signed admission, admission ID and idempotency key. There is exactly one write
attempt; transport uncertainty never retries automatically. Independent GET of
the same path must rehash target bytes and return exact provider identity,
namespace, hash, size, admission ID, receipt ID, `executed_content=false`,
`project_truth_promoted=false` and `owner_truth_promoted=false`. Oracle status is
`ARCHIVED`. VEKL status is `CANDIDATE_RECORDED` with a **real canonical**
`canonical_candidate_id` and `UNTRUSTED_OWNER_FILE_EVIDENCE` authority. This is
evidence admission, never automatic Project Truth promotion.
The separate `GET .../{sha256}/content` must deliver bounded inert octet-stream
bytes using the same claimed, unexpired observation scope. VAN independently computes the persisted
byte count and SHA-256; a matching metadata receipt without matching bytes is
refused. This endpoint is part of the proposed missing target contract, not an
existing Oracle/VEKL route.

Before target dispatch, source or authority refusal is `REFUSED` with no effect
attempt; cancellation can safely stop a draft or undispatched transfer. A
durable dispatch intent makes a subsequent failure or cancellation `UNKNOWN`.
The backend fences replacement writes to that exact target/content across all
sessions, independently of the bounded owner history. An explicit owner GET
of the observation route can report actual persisted bytes after a lost reply,
while preserving the old canonical `UNKNOWN`/`UNVERIFIABLE` status and replacement
fence. An unclaimed or expired scope yields `STILL_UNKNOWN`, never proof that no
write occurred. Governed reconciliation remains necessary in those cases.

The existing sources cannot stand in for that target:

- DDS `AGENTS.md`, “Project Truth authority”, requires an existing owner-originated
  Oracle instruction job and append-only authorization; this environment has no
  callable Oracle job/broker.
- DDS `agent-system/mcp/dial-research-server.mjs` exposes analysis submissions
  for exactly one leased immutable Development Unit (`worker_id`,`lease_id`,
  claims/sources), not arbitrary owner files.
- DDS `agent-system/orchestration/vekl-research-contracts.mjs` restricts research
  artifacts to `PUBLIC_RESEARCH_ONLY` and graph/truth provenance. Reclassifying
  private owner files as public research would violate that source contract.
- DDS `agent-system/orchestration/whatsapp-owner-input.mjs` only admits actual
  authenticated WhatsApp attachments inside approved Hermes cache roots. It is
  not an owner-artifact HTTP API and cannot accept a fabricated WhatsApp message.
- VAN `knowledge/vekl.py` reads `/v1/missions/{mission_id}/vekl`; it has no file
  write or candidate admission API.

No DDS source or Project Truth was mutated for this provider preparation.
