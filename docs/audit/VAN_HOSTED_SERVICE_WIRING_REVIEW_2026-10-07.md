# VAN hosted-service wiring review — 7 October 2026

The current source provides concrete hosted-service producers, canonical authority
checks and typed frontend contracts. This review describes source and local integration
validation. No production host was deployed, live provider credential exercised, or
handset acceptance case run in this cloud session.

## Current service behavior

| Function | Implemented behavior | Evidence and limits |
|---|---|---|
| Gmail plaintext reply draft | Reads authoritative owner profile and unique incoming thread metadata, builds RFC 2822 MIME/base64url, and independently decodes the provider draft to verify body, addressing, subject and thread. Missing or ambiguous metadata refuses before a write. | Real-shaped provider HTTP tests cover correct MIME and refusal cases; no recipient is guessed. |
| Gmail approved send | The gateway privately previews the draft and binds its canonical content digest to A4 approval. It sends the approved immutable MIME snapshot through `messages.send`, then independently reads the actual SENT message. Concurrent changes cannot alter the approved bytes. | Body/header/thread mismatch and ambiguous POST timeout cannot produce verified success. The source draft is retained: cleanup NOT_ATTEMPTED, source state UNOBSERVED. No automatic resend is promised. |
| Gmail owner approval display | Private paired-owner preview includes decoded content and recipients; internal runtime preview omits the body. Hermes has bounded preview/job/artifact wrappers. | Job planning and untrusted artifact recording do not establish job execution or verification. |
| Calendar reschedule | Reads an aware timed interval, preserves duration, and patches both endpoints with the current ETag. Independent readback verifies the exact active event and interval. | Invalid/all-day/cancelled records stop before PATCH; 412 concurrent edits are not retried. |
| Google/knowledge/research errors | Timeout, connection failure, redirects and malformed provider data become bounded service errors. Research validates the complete response before storing evidence and invalidates stale readiness after failed canaries. Knowledge failures close canonical actions. | Provider faults cannot leave an executing action or turn historical readiness into fresh success. |
| n8n semantic compilation | Records an immutable semantic candidate separately from concrete deployment. Unsupported operations, graphs, preconditions or credential adapters stay explicitly nondeployable. | A candidate does not imply an engine workflow, admission or owner success. Imaginary workflow IDs, `vanConnector`, `vanOperation` and `vanInput` producers were removed. |
| n8n deployment | Creates real typed helper workflows and a parent graph, reads them independently, and seals actual helper IDs, exact executable helper graphs and dedicated credential identifiers into the full manifest. | Parent/helper drift, an invalid lifecycle transition, missing dedicated worker scope or failed activation readback prevents admission. |
| n8n canonical callbacks | Every private HTTPS callback requires the narrow machine role plus a signed run/step grant and current canonical command, snapshot, artifact, action class and exact parameters. Actual operations enforce their real minimum class/effects and mutation postconditions. | A read declaration cannot authorize file writes, notifications or evidence mutations. Interrupted effect claims refuse replay. Engine success remains separate from independently observed owner success. |
| n8n standing runs | The gateway scheduler derives fresh run authority from current owner-sealed standing authority and a new immutable snapshot. UTC schedule parameters or recent stored event selectors are exact; claims are durable and once-only. | Revocation, expiry, disabled intent, changed artifact, forged event, extra parameters and arbitrary trigger keys refuse. Engine timers cannot mint authority. |
| n8n source credentials | Protected operator-owned alias files bind exact HTTPS domains and selected headers; tokens stay on the gateway. Reads use DNS pinning, response bounds, total deadlines, redirect refusal and secret echo refusal. | No provider secret is supplied to n8n, Android, a model or a callback body. Source data remains UNTRUSTED_EXTERNAL. |
| Browser producers | Concrete authenticated signalling/WebRTC media, loopback CDP transport, private mTLS control, current broker authority fences, profile isolation and bounded transfer/clipboard producers are now supplied in source. | Native runtime and broker tests are maintained by their owning agents. Actual installed profile stacks, TLS identities, browser binary and host networking still require qualification. |
| Browser qualification | Selects the explicit public or owner stack and its actual units/users/ports. A verified admitted-client TLS connection precedes anonymous/foreign-client negatives against the actual private bind. | An explicit peer certificate alert proves refusal; a network reset, timeout, missing listener or local CA/SAN failure does not. These live checks have not run on the production host. |
| DIAL hosted reads | Gateway-owned proxy credentials and TLS identities remain outside Android. Malformed rotated token files fail before transport. | Live DEC-056 proxy qualification remains an independent deployment prerequisite. |
| Explicit owner understanding | Hardware-bound current-session PUTs define exact project/global vocabulary or a named collaboration preference, with generated owner provenance and independent committed readback. | Inferred strengths/vulnerability/confidence cannot be authored through the preference writer; neither writer grants execution authority. Exact reads and approved memory erasure expose and reverse the declarations. |

## Supported automation boundary

The concrete callback set supports domain-bound HTTPS GET, SHA-256, staged change
and deduplication detection, fixed validation, identity mapping, owner events, evidence
sealing and transient file store/delete. Delivery fingerprints advance only after the
required downstream event/evidence target readbacks; interrupted delivery can finish
in a new admitted run without duplicate events. Arbitrary transformation languages,
branching, external native writes and generic capability dispatch remain unsupported
candidates. The feature registry must retain that distinction.

[Automation runtime binding instructions](../AUTOMATION_RUNTIME_BINDINGS.md) describe
real provisioning, the separate worker credential, server trust and protected source
aliases. None of these machine settings introduces an Android configuration screen.

[Owner understanding control contracts](../OWNER_UNDERSTANDING_CONTROLS.md) describe
the finite owner-authored fields, exact readback and the distinction between a
declared preference and independently observed assistant behavior.

## Validation and remaining acceptance

The initial 502 backend plus 168 browser checks are retained as **historical** receipts
for an earlier source state. They are not current-runtime certification. Current focused
service and TLS receipts, their exact selections, logs and source hashes are recorded in
`VAN_HOSTED_SERVICE_WIRING_VALIDATION_2026-10-07.json`. The parent integration report
supplies the final whole-repository validation after all agent source changes freeze.

Remaining external acceptance is concrete: install the signed owner-core and isolated
browser release on the admitted host; bind real machine credentials, CA trust and
provider identities; run independent Google/knowledge/research/n8n/browser canaries;
provision the signed APK without in-app connection setup; and execute deferred S24
Artemis happy/error-path tests. Source tests do not substitute for those observations.
