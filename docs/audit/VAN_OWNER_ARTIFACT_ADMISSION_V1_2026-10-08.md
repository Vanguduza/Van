# Owner artifact admission contract

VAN implements the owner draft, canonical A4 submission, native byte reader,
dedicated admission signer, provider transport authentication, atomic one-use
claim and independent effect observations. The actual Oracle archive and VEKL
owner candidate ingress remain **UNAVAILABLE** until their governed target
implementation, namespace, identity and current capability are bound. No target
job, production key, live receipt or truth promotion was created by this work.

## Owner interface

All owner routes require the current paired owner of the exact browser session.
They expose no signing key, admission bearer, native transfer bearer or editable
connection setting.

| Method | Path below `/v1/browser/interactive-sessions/{session_id}` | Outcome |
|---|---|---|
| GET | `/file-provider-contracts` | Current exact target/source qualification; empty bindings report unavailable |
| POST | `/file-provider-requests` | Immutable source/target draft, without write authority |
| GET | `/file-provider-requests` | Latest 100 owner records with idempotency keys for reply-loss recovery |
| GET | `/file-provider-requests/{request_id}` | Exact durable request and current canonical qualification |
| POST | `/file-provider-requests/{request_id}/cancel` | Fence undispatched work; dispatched work remains uncertain |
| GET | `/file-provider-requests/{request_id}/observation` | Explicit bounded read of an already claimed external effect |

The draft body contains exactly `download_id`, `provider`, `owner_namespace`,
`project_namespace`, `content_sha256`, `byte_size`, `deadline_ms` and
`idempotency_key`. Provider is `ORACLE_OWNER_ARCHIVE` or
`VEKL_OWNER_CANDIDATE_INGRESS`. SHA-256 is 64 lowercase hexadecimal characters;
bytes are bounded to 64 MiB and the draft deadline to 15 minutes. Namespace and
provider scope must match the qualified operator binding. The backend confirms
the actual completed, nonquarantined native file, current producer/frame,
profile lease, owner control and independently read bytes. Immutable source and
target fields are rehashed when the durable draft is read; corruption is refused.

Draft IDs are `bfile_` followed by 32 lowercase hexadecimal characters. The
returned `approval_command` is `submit browser file` followed by exact JSON:

```json
{"session_id":"<owned-session>","request_id":"<immutable-request>","request_sha256":"<immutable-digest>"}
```

Only the existing command ingress may execute this instruction. The canonical
action is `browser.file.provider.submit`, A4, with these three parameters and
freshness at most 30 seconds. The existing exact device-bound biometric challenge
is mandatory. Owner decision answers, page instructions, conversation content,
provider bearers and transport possession cannot authorize the action.

## Effect and recovery semantics

The gateway makes one source byte retrieval with a one-use native download
grant. It records the consumed transfer ID, source digest and byte count before
minting the target admission. It records dispatch intent under the writer lock
immediately before the single external adapter call. One bounded transfer runs
at a time per runtime; an overlapping operation is refused before silent queuing
can exhaust the owner's approval window.

| State | Meaning and replacement fence |
|---|---|
| DRAFT | No target dispatch; fresh exact A4 approval still required |
| REFUSED | Definite refusal before target dispatch, `effect_attempted=false` and a stable reason |
| CANCELLED | Draft or undispatched transfer fenced before target dispatch |
| RUNNING | Target dispatch admitted; completion is being observed |
| UNKNOWN | Dispatch may have happened; cancellation or failure does not authorize resend |
| UNVERIFIABLE | An observed effect lacks successful canonical action/mission verification |
| VERIFIED_SUCCESS | Canonical action and mission both succeeded with two separate verifier readbacks |

The initial write reply is insufficient. Initial receipt/content readback,
action readback and mission readback each read the persisted target bytes
separately. Every receipt binds the exact admission/claim, provider identity,
namespace, digest and size. Content stays
`UNTRUSTED_OWNER_FILE_EVIDENCE`, with `executed_content=false`,
`owner_truth_promoted=false` and `project_truth_promoted=false`.

The backend blocks a replacement for the exact target/content across all
sessions if any older draft, running or unknown write remains unsettled. This
check examines durable records under the creation writer lock; a bounded owner
history cannot hide an old uncertain write and authorize a replacement.

Explicit observation returns `session_id`, `request_id`, `request_sha256`,
`canonical_status` and `effect_observation`. Its status is
`OBSERVED_EXTERNAL_EFFECT` only when independent receipt and persisted bytes
match; otherwise `STILL_UNKNOWN`. It never rewrites a terminal action/mission or
releases a replacement fence. `automatic_replacement_authorized` is always false.
`governed_reconciliation_required` remains true for any unknown/unverifiable
command even if bytes are found. An unclaimed admission or an expired observation
window cannot mint a fresh scope or certify that the effect did not occur.

## Private provider callbacks

The exact POST callbacks are:

```text
/v1/browser/artifact-provider/admissions/{admission_id}/introspect
/v1/browser/artifact-provider/admissions/{admission_id}/claim
```

Their strict body is `{"signed_admission":"<volatile-admission-token>"}`.
Admission IDs are `bfa_` followed by 32 lowercase hexadecimal characters.
Authentication requires the actual verified HTTPS handshake extension and a
currently configured dedicated provider certificate fingerprint. Owner-device
credentials, internal machine bearers and forwarded headers are insufficient.
The principal pins exactly provider identity, provider kind, owner namespace,
project namespace and `OWNER_ARTIFACT_WRITE_ADMISSION` purpose.

The token is dedicated ES256 with type `VAN-OWNER-ARTIFACT`, issuer
`van-trading-core`, exact audience and durable claims. It binds source/target,
request hash, canonical execution/command/device and context snapshot. Write
expiry is at most 30 seconds and cannot exceed the original approval/deadline.
The same immutable claims carry `observation_expires_at_ms`, at most five
minutes after issue. Only an already consumed claim can use that later window.

Claim verifies signature, exact durable claims, namespace/principal, current
capability, current config snapshot and canonical owner authority. A single
`BEGIN IMMEDIATE` rechecks device revocation, permission scope, pending mission
dispatch controls and native source custody, then consumes the nonce. If the
source parent was active at draft creation, later pause/cancellation/terminal
state blocks a new claim. A fresh draft created after an already terminal parent
pins that exact terminal state and uses its own new owner command authority.
Already claimed work is not undone by a later revocation; subsequent observations
still require a current device, config and scoped provider identity.

## Operator bindings and missing target

`VAN_BROWSER_ARTIFACT_PROVIDERS_FILE` names one bounded operator-owned JSON file:

```json
{
  "schema_version": 1,
  "providers": [],
  "source_clients": {},
  "signer": null
}
```

This safe empty configuration grants no authority. Configured provider rows
contain exactly `provider`, `origin`, `ca_file`, `client_cert_file`,
`client_key_file`, `provider_identity`, `capability_receipt_sha256`,
`owner_namespace`, `project_namespace` and `provider_principal_sha256`.
`source_clients` maps an existing profile alias to exact `origin`, `ca_file` and
optional paired `client_cert_file`/`client_key_file`. Origins are operator-bound
HTTPS origins; they are not inferred from a control-plane or signalling URL.
`signer` has exactly `kid`, `private_key_file`, `issuer`. Its preprovisioned
P-256 private key must be a regular mode 0600 file and must differ from stream and
connectivity keys. This loader generates no key.

Unknown/duplicate fields, malformed scope, duplicate transport principals or
invalid TLS/key files fail startup. The parsed file's exact SHA-256 is frozen;
changed/missing config disables pending submissions and claims. Provider pins
reload for every callback, and current config is checked again inside the nonce
writer transaction. Operator rotation requires unbinding or changing that config
and restarting with the newly approved snapshot.

The external target must implement current capabilities and inert storage at:

```text
GET /v1/owner-artifacts/capabilities
PUT /v1/owner-artifacts/{owner_namespace}/{project_namespace}/{content_sha256}
GET /v1/owner-artifacts/{owner_namespace}/{project_namespace}/{content_sha256}
GET /v1/owner-artifacts/{owner_namespace}/{project_namespace}/{content_sha256}/content
```

The operator-approved capability digest must match its exact current JSON. The
capability declares `VAN_OWNER_ARTIFACT_ADMISSION_V1`, provider/identity, exact
namespace admission, `current_admission_introspection=true`,
`atomic_one_use_admission_claim=true`, dedicated issuer/signer fingerprint,
`provider_transport_principal_sha256` and
`claimed_readback_expiry_field="observation_expires_at_ms"`.
VEKL additionally needs a real governed `oracle_instruction_job_id` and must
return an actual canonical candidate ID. Target writes must atomically bind
persisted inert bytes to the successful one-use claim; independent receipt and
octet-stream reads must enforce the claimed observation scope. Metadata and
content responses are streamed with size bounds; arbitrary extra target fields
are not projected into owner receipts.

These are proposed target APIs, not existing DDS routes. Exact DDS master
`27f917c9f35cba7180918bc89319e5303e3248d6` review found no compatible provider.
Its existing VEKL ingress accepts leased immutable public-research units, rejects
private owner-project evidence, and requires the authoritative VEKL worker store.
WhatsApp ingress accepts actual authenticated attachments in approved cache
roots; it is not an arbitrary file API. Oracle-admin is not a general archive
workload role. DDS `AGENTS.md` and `CLAUDE.md` require an existing owner-originated
Oracle instruction job and append-only authorization before persistent target
work. The twelve exact-SHA review inputs and hashes are retained in
`/workspace/van-audit/commander-online-source-27f917c/artifact-review-inputs.json`.
No DDS checkout, project truth, job or remote service was mutated.

Repository tests use controlled transports and test-only identities. They prove
the actual composed owner command pipeline, atomic admission/refusal races,
byte readbacks and recovery semantics; they do not qualify an external target,
deployed TLS route or physical handset.
