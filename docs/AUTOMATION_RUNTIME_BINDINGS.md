# Canonical automation runtime bindings

The gateway compiles a semantic candidate first. A candidate is not deployable or
admitted until its concrete n8n resources have been created and independently read
back. The owner app proposes immutable plans and reviews capability, binding,
request and run projections. Secret machine bindings remain operator-managed.

## Provisioning and admission

The operator binds an existing private n8n management API and API credential, its
qualified version, the canonical grant signer, and `VAN_AUTOMATION_WORKER_ENDPOINT`.
The worker endpoint must be the actual private HTTPS gateway listener at
`/v1/automation/worker/step`, with a concrete private IP and a trusted server
certificate. Install its CA into the n8n process trust store when a private CA is
used; TLS verification remains enabled.

The exact worker POST has a separate machine admission path through the gateway's
HTTPS gate. It still requires the dedicated worker scope, signed step MAC and current
canonical authority. It grants no owner identity and requires no owner-device
certificate or private key in n8n. Other owner routes retain their device-certificate
requirements.

Configure one distinct `automation_worker` scoped credential through the protected
gateway environment. It must hold that scope alone and must differ from owner,
Hermes, enrolment, observability and general automation credentials. The provisioner
creates an actual n8n `httpHeaderAuth` credential for that token. The credential does
not issue owner authority: every callback also requires a signed exact run/step
grant and current canonical command, snapshot, capability and action authority.

1. `POST /v1/automation/compile` validates and records the immutable IR candidate.
   Raw caller credential IDs cannot replace admitted server bindings.
2. `POST /v1/automation/workflows/{artifact_id}/provision` creates real helper
   workflows and the parent graph through the n8n API. A separate GET checks their
   executable fields. Real IDs, helper graphs and credential identifiers are sealed
   into the deployment manifest. Semantic identity remains independent of those IDs.
3. The guarded quarantine/validation/admission lifecycle remains mandatory.
   Admission reads every helper, activates the parent, and reads its exact active
   graph before atomically publishing the capability and its typed action definition.
   An invalid lifecycle transition has no management side effect.
4. Each dispatch reads the exact parent and helper graphs again, then supplies a
   primary admission grant and one bounded child grant per declared step. A provider
   timeout during an effect POST is not retried.

The paired-owner path follows the same lifecycle through exact signed commands:
`automation admit {artifact_id}` and `automation execute {capability_id} artifact
{artifact_id} with {inputs_json}`. Candidate proposal is signed
`POST /v1/owner/automation/plans`; its durable request can be reconciled read-only
at `/v1/owner/automation/requests/{idempotency_key}`. Dynamic resolution derives
the canonical action class, artifact pin and typed parameters before biometric
approval. Neither candidate metadata nor engine status confers authority.

Provisioning does not certify a working external n8n installation. A live callback
canary and independent target readback remain required. Mutable provider credentials
are checked by actual worker admission; changing a credential to an unusable value
fails the run rather than widening its owner authority.

## Supported runtime operations

The closed producer map supports domain-bound HTTPS GET, deterministic SHA-256,
change detection, fixed validation/deduplication, identity mapping, targeted owner
events, local evidence sealing, and transient file store/delete. External source
data remains `UNTRUSTED_EXTERNAL`; storing or hashing it does not attest its truth.
External reads require at least A2/NETWORK_READ. Notifications and file/evidence
mutations require their actual A3 effects and observable mutation postconditions.

The runtime also supports the closed typed predicate, mapping, selection and merge
language documented in [AUTOMATION_TYPED_OPERATIONS.md](AUTOMATION_TYPED_OPERATIONS.md).
The gateway evaluates labelled branches and bounded preconditions; n8n schedules
callbacks without deciding authority or inventing skipped inputs. Every skipped
receipt retains the exact settled parent digests and selection, and independent
observation recomputes that proof. Native `reminder.create` writes through the
actual service and reads the exact row. Defined external POST/PUT/PATCH/DELETE
operations require fresh A4 owner approval, protected method-specific credentials,
one request and a sealed observable independent GET predicate. Arbitrary actions,
code, undeclared expressions and user-defined nested subworkflows remain unsupported.
It never emits imaginary resource IDs, a `vanConnector` credential or unknown
`vanOperation` parameters. Engine success alone is never owner success.

Gateway standing runs use current owner-sealed standing authority and a fresh
immutable context snapshot. The scheduler checks UTC cron or an exact recent stored
event matching the admitted source selectors. It supplies exact parameters, claims
each trigger durably once, and refuses revoked, expired, disabled or changed
authority. Engine timers and externally callable n8n webhooks cannot mint authority.
An interrupted claimed run is not automatically replayed.

Change detection stages its fingerprint in a durable callback receipt. It advances
the delivered baseline only after every downstream event/evidence receipt and actual
target readback succeeds. Stable generation transition IDs allow a later newly admitted
run to finish an interrupted delivery without duplicating an already published event.
The earlier uncertain callback stays `IN_PROGRESS` and cannot be replayed. Migration 38
discards the old observation-only cache while preserving authority and effect receipts.

## Protected source credentials

Authenticated sources use `VAN_AUTOMATION_SOURCE_CREDENTIALS_FILE`.
This operator-owned JSON file and each referenced token file must be absolute,
regular files owned by root or the gateway user, with no group/world permissions.
Source tokens stay on the gateway and never appear in n8n graphs or callback bodies.

```json
{
  "schema_version": 1,
  "aliases": {
    "connector://reports/primary": {
      "credential_class": "C3_SENSITIVE_INTEGRATION",
      "admitted": true,
      "allowed_domains": ["reports.example.com"],
      "header_name": "Authorization",
      "value_prefix": "Bearer ",
      "token_file": "/etc/van/secrets/reports-primary.token"
    }
  }
}
```

Aliases default to GET-only. Defined consequential methods also require an explicit
protected `allowed_methods` list, such as `["GET","POST"]`; a plan cannot widen it.
Only the admitted exact HTTPS domain receives the selected header. DNS/public-address
checks, redirects refusal, total deadlines, response bounds and secret echo refusal
apply to the actual fetch and its independent readback. The example identifies the
configuration shape; it supplies no working host, provider or credential.
