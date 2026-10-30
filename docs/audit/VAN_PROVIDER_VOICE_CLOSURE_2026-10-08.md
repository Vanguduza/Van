# VAN current source closure — 8 October 2026

The confirmed repository defects and missing owner contracts described below are
implemented and locally validated. The current redesign inventory contains **42
feature groups, 105 source functions, 78 screens or hosted surfaces, 345 endpoint
declarations and 200 schemas**. Production deployment, provider qualification and
physical S24 acceptance remain outstanding.

Use the [frontend registry guide](OWNER_FRONTEND_REGISTRY_GUIDE.md) and
[searchable contract](OWNER_FRONTEND_CONTRACT.html) as the design inputs. The
[current validation receipt](VAN_PROVIDER_VOICE_VALIDATION_2026-10-08.json) supplies
the exact runner selections, counts, artifacts and current source bindings. The
earlier [pre-S24 report](VAN_PRE_S24_CLOSURE_2026-10-08.md) and its receipts are
historical for changed components.

The selected backend is **van-trading-core**, with Hermes profile `van` on
**dial-control**. The proposed phone ingress is a narrowly admitted VAN TLS route
on **oracle-admin**, preserving private core and Hermes services and their
separate authority. Later physical acceptance uses native Artemis through the
authorized DIAL/Commander route. No host deployment or handset connection was
executed by this workspace.

## Implemented owner functions

| Area | Current contract and required states |
| --- | --- |
| Decisions and missions | Typed choice/note/evidence/revision/expiry, immutable answer recovery, durable pause/resume/direction and native dispatch/checkpoint fences. Resume requires a fresh owner command after a closed command; a running OS process is not reported stopped without observation. |
| Memory and learning | Exact paginated retained-record inspection/export, dependency/revision-bound A4 erasure, observed owner decision patterns/counterexamples and structured external disagreements. Unsupported, stale or malformed evidence remains unmeasured; producer states expose NO_DATA, PARTIAL and DEGRADED. |
| Consent and automation | Exact finite A4 consent/revocation/readback, immutable typed workflow candidates, separate admission and execution, bounded predicates/branches/maps/merges/waits, native reminders and protected HTTP effects with current fences and independent target readback. |
| Browser effects and files | Signed A3 task preparation, native domain/profile review, immutable A4 click/fill plans, verified task completion, bounded inert file analysis/preview, explicit phone upload/download/clipboard and encrypted outcome recovery. Uncertain effects are observed through supported recovery contracts. |
| Owner artifact destinations | Oracle/VEKL catalog, exact immutable request review/recovery, native A4 admission, separate attested provider introspection/atomic claim, one protected byte write and independent persisted-byte verification. Default production catalog remains UNAVAILABLE until actual target qualification. |
| Generic voice assets | Pinned generic wake/ASR/TTS/speaker assets bundled in the APK, streamed integrity checks, atomic private installation off the UI thread, native engine preparation and bounded energy endpointing. Engine/model readiness is separate from acoustic accuracy. |
| Local owner speaker profile | Enroll/replace, microphone consent, actual clip progress, capture cancellation, readiness and exact erasure. Three real clips and consistent native embeddings precede encrypted commit/readback. Fresh remote owner binding is required for enrollment and scoring; offline privacy erasure uses genuine existing local keys and authenticated stored revision. |
| Android connection and controls | Actual clients and controls are wired to their existing routes, hosted dialogs and native activities. Release/installer provisioning supplies route and trust; no in-app host, port, token or CA entry is required. Android permissions and consequential native biometric approvals remain explicit. |

The final review also fixed three confirmed defects: the new external artifact
write now declares its irreversible authority semantics; both speaker profile
mutation boundaries recheck the original thirty-second consent and current
authenticated revision immediately before effect; and the reusable CI template
contains the same pinned asset-acquisition steps as the active workflow.
Uncertain external writes have no invented rollback or remote-delete contract.

Provider introspection/claim is authenticated by actual TLS client proof and the
current exact provider/owner/project pin, separate from owner sessions and
internal static service bearers. The Android app submits the canonical native
action `browser.file.provider.submit` with exactly `session_id`, `request_id` and
`request_sha256`. **Check external receipt** reports a later observed byte effect
separately; it cannot upgrade the original UNKNOWN/UNVERIFIABLE command or lift
its replacement fence. File contents remain untrusted data.

Speaker enrollment uses dedicated strong biometric, one-use signed consent bound
to the operation, model, hardware and approval keys, current owner binding and
prior profile revision. Raw microphone PCM stays in memory. No owner profile,
recording or embedding was fabricated. Capture cancellation waits for actual
native handle release before wake rearming; failure to release remains visible.
Speaker similarity supplies evidence and grants no command authority.

## Current local evidence

The disjoint complete local suites recorded **7,232 passing executions and four
optional skips**. Two fresh actual AGP release-refusal checks passed separately,
yielding **7,234 fresh passing executions**. Two retained PostgreSQL/DDS cases
have independently verified unchanged input bytes, yielding **7,236 qualified
source cases**; these two are retained executions. Focused and overlapping tests
are excluded from those totals.

| Suite | Passing cases |
| --- | ---: |
| Complete backend | 3,231 |
| Complete contracts | 994 |
| Complete trading | 1,293 |
| Hermes/policy/scenarios | 89 |
| Native browser services | 160 |
| Android JVM | 1,262 |
| Android app unit | 203 |

The final contract run bound 2,060 repository inputs and two external inputs;
all bytes remained unchanged. It validates the current registry, endpoint
bindings and prepared acceptance plan. Two opt-in AGP cases and two optional
trading cases remain visible as skips in their default JUnit runs, with separate
fresh or retained qualification receipts.

The [backend component receipt](validation/backend-component-requalification-provider-speaker-2026-10-08-r8.json)
preserves the full-run wrapper's truthful global change witness. All 443 actual
backend/runtime/test inputs and 1,192 non-Android runtime dependencies retained
their exact bytes. The two complete backend modules that inspect Android source
were rerun against the final tree: 16 passes, counted as overlapping evidence.

The [final Android receipt](validation/android-owner-controls-final-receipt-2026-10-08-r4.json)
binds all 584 source/test/build inputs unchanged before, between and after the
successful app/JVM runs. Assembly and lint passed with zero Error/Fatal findings
(87 warnings and 19 hints). Independent APK inspection verified 45 pinned voice
files, the actual DEX manifest pin, seven ARM64 ELF libraries and 16 KiB native
ELF/ZIP alignment. The resulting APK is a developer debug build: 317,069,609 bytes,
SHA256 `1562d995bfe6d12f54c7c583e9e5569a79a4129f0e828bb30952df22a5393078`.

Generic native smoke checks establish engine construction and bounded decoding.
They also recorded **zero synthetic "Hey Van" hits** and transcription of the
short synthetic "hie van" as **"I THEN"**. Wake/transcription accuracy and speaker
discrimination therefore remain unqualified. The bundled runtime includes the
declared GPL components; corresponding-source inventory is INVENTORIED_NOT_COMPLETE.
The authorized private-owner acceptance scope does not establish public release
qualification.

The [production snapshot](validation/van-production-source-freeze-provider-speaker-2026-10-08-r8.json)
contains 1,413 exact files, SHA256
`c55031c4be0cc6da94b86d103066b4b683d71be3c6d779a56bc3520fffb7b61e`,
against base commit `12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af`.

## Remaining acceptance prerequisites

| Prerequisite | Current state |
| --- | --- |
| Authorized native DIAL/Commander/Artemis route | No callable production connector, current native schemas or admitted device is exposed here. Wireless debugging alone does not pair or admit the S24. |
| Core ingress, trust and private services | Deployment/profile/preflight/rollback/collection tooling is prepared. Actual governed VAN ingress capability, host deployment, TLS and firewall evidence, private Hermes and service canaries remain unverified. |
| Owner release and installer | Existing production signer, current trust/profile/attestation and signed provisioning bindings must be supplied through the authorized deployment environment. Release guards refuse absent bindings. No owner release was built. |
| Oracle/VEKL target | VAN consumer/admission/frontend source is implemented. The actual governed target API, current capability and live attested persisted-byte canary are absent; production buttons remain disabled. |
| S24 physical and acoustic work | Pair/admit the exact handset through the existing authorized native route, install the verified owner packet, execute device cases, qualify actual wake/transcription/speaker behavior and enroll the real owner privately. |
| Environment activation and visual design | Publish the saved reusable cloud-environment draft after review. The requested Rive/app visual redesign remains separately deferred. |

The [Artemis plan](VAN_ARTEMIS_ACCEPTANCE_PLAN_2026-10-08.json) contains **826
prepared cases and zero physical executions**. The three local speaker lifecycle
cases require exact private device metadata readback, without raw audio or
embedding export. Imported receipt consistency does not authenticate a producer
or qualify a physical effect. Use the
[native handoff](../../tools/certification/NATIVE_ARTEMIS_HANDOFF_PROMPT.md) and
[host collector](../../tools/certification/pre_phone_host_acceptance.py) for the
next authorized session.

All source changes remain in the workspace. An exact-base source packet and a
separate finite proof/APK sidecar are prepared under `/workspace/van-audit` with
independent restoration/hash checks. Source restoration preserves the changes;
it does not reproduce the recorded APK/tests or qualify a deployed service.
Nothing was committed, pushed, deployed or tested on the S24 by this workspace.
