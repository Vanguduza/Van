# VAN frontend registry guide

The 2026-10-08 inventory contains **42 owner capabilities, 105 source functions,
78 screens/hosted surfaces, 345 endpoint declarations and 200 schema components**.
Use the [searchable contract](OWNER_FRONTEND_CONTRACT.html) to review it and the
JSON files below as the design input. Current implementation and remaining external
contracts are separate from visual redesign and live qualification. Current
source-bound Android and backend checks passed; the exact current local evidence
is recorded in [the provider/voice validation](VAN_PROVIDER_VOICE_VALIDATION_2026-10-08.json).
Earlier build and test receipts remain historical for changed inputs.

| Artifact | Design use |
| --- | --- |
| [Owner features](../../registries/owner_features.json) | Owner goals, information, current functions, authority, required states, screen links and explicit missing contracts. |
| [Owner screens](../../registries/owner_screens.json) | Actual navigation, nested routes, inline sections, hosted modals, native activities and their feature/endpoint mappings. |
| [Endpoints](../../registries/owner_endpoints.json) | Actual HTTP/WebSocket declarations, authentication, proof requirements, conditional registration and source locations. |
| [Schemas](../../registries/owner_endpoint_schemas.json) | The OpenAPI component definitions referenced by request and response contracts. |

`current_implementation.functions` describes located source interactions.
`information`, `actions` and acceptance states also retain the required product
scope; read the row's gaps before treating that whole scope as implemented.
`SOURCE_WIRING_INCOMPLETE` identifies a missing or unsupported functional contract.
`SOURCE_WIRED_REQUIRES_ACCEPTANCE` identifies supported wiring whose stated external,
visual or physical acceptance remains pending. Neither status proves deployment
or handset behavior. Baseline fields and archived registries describe earlier
source, and are not current qualification.

Respect the actual host of each surface. Trading `tickets` is a nested route in
`trading`; broker-fill confirmation is a hosted modal, and autonomy controls are
an inline section in `settings/permissions`. Headless installer intake is not an
owner configuration screen. Android obtains its backend/Hermes route and trust
through the signed release and installer; the redesign needs no host, port, token
or certificate entry form.

Owner screens may call only their admitted owner endpoints. Internal browser
producers and automation callbacks use their host-side per-purpose authority.
Artifact provider admission introspection/claim has a separate attested provider
lane: actual HTTPS-verified client certificate, current exact provider/owner/project
pin and signed admission. Neither owner credentials nor internal static bearers
authorize that lane. `service_endpoint_ids` records dependencies for independent observation,
not Android access. A route declaration, provider registration, draft, accepted
request or successful transport is insufficient evidence of an owner effect.

Preserve independent source failures, cached age and UNKNOWN health. Show exact
normalized parameters, current target/context and expiry before consequential
approval. Discard and biometric refusal must remain explicit. An uncertain effect
holds input or settlement until exact independent readback; automatic retries
must preserve the original identity and only use a supported recovery contract.

Browser record review/removal, actual phone save/upload and explicit clipboard
copy/paste are separate functions. Byte effects require the exact current target, source transfer, opaque producer
session identity, explicitly observed generation and byte hash. Readback must
match the independently expected case correlation, not merely contain nonempty IDs. Delegated bounded navigation and
observation use their own read authority. Bounded click/fill requires a current
native target, admitted mutation profile and fresh biometric A4 approval of an
immutable exact effect plan. Uncertain effects are observed rather than repeated.
A broker-fill confirmation
records evidence and never submits an order. Owner vocabulary/collaboration
declarations record explicit preferences and never grant action authority.

The owner can inspect/export individual retained records, review their exact
dependent erasure scope and request fresh A4 approval. Changed content or a new
dependent link requires a new plan and approval. Learning producers report actual
bounded observations, candidate counterexamples, structured disagreements and
`NO_DATA`/`PARTIAL`/`DEGRADED` without guessing reasons or granting action authority.
Typed owner decisions have exact choice/note/revision/expiry recovery; mission
pause/resume/direction exposes an ordered dispatch fence and worker checkpoint,
without claiming an already running process stopped. Exact consent and automation
candidate/admission/run contracts retain separate native and service authority.

Native file preview and bounded analysis are implemented. The owner provider
panel reviews the exact file, destination, immutable request/digest and deadline;
an uncertain draft reply is recovered by its original identity. The native A4
action `browser.file.provider.submit` seals exactly `session_id`, `request_id`
and `request_sha256`. The external write is irreversible; no remote rollback
or deletion control is offered. Its separate attested provider atomically claims the signed
admission before one protected write, then supplies independently observed persisted
bytes. Untrusted contents are not executed or promoted to owner/project truth.

The proposed Oracle/VEKL provider has an **unbound, unqualified production target**;
default catalog state is `UNAVAILABLE` and its buttons remain disabled. Source for
the consumer, native admission and frontend cannot prove the target API exists.
After an uncertain effect, **Check external receipt** uses the existing claimed
read-only observation window. `OBSERVED_EXTERNAL_EFFECT` reports bytes separately;
it cannot upgrade the original `UNKNOWN`/`UNVERIFIABLE` command or release its
replacement fence. A missing receipt is `STILL_UNKNOWN`, and never proves absence.

Generic acoustic assets are pinned in the APK and installed atomically in private
storage off the UI thread; no model URL or file selection is required on the phone.
Actual engine preparation and bounded `EnergyVadGate` endpointing are separate
from model files and acoustic accuracy. An unused neural VAD is not marked ready.
Native constructor/decode checks do not qualify wake recognition, transcription
accuracy or speaker discrimination; physical acceptance remains unverified.
The recorded generic native smoke produced zero hits for synthetic "Hey Van" and
decoded the short synthetic "hie van" as "I THEN". These observations flag acoustic
qualification work; they do not supply an owner voice profile or claim accuracy.

The **Local owner speaker profile** section in `settings/voice` offers enrollment,
replacement, readiness, capture cancellation and exact erasure. A dedicated strong
biometric signature binds the local purpose, operation, model, hardware/approval
keys, current owner binding, prior profile revision and thirty-second one-use
consent. Three actual microphone clips must pass bounded signal and native embedding
consistency checks before encrypted commit and readback. Raw PCM stays in memory;
no owner recording or embedding has been fabricated. Enrollment and similarity
use require the fresh current remote owner binding. Offline privacy removal uses
genuine local device/hardware/approval keys and the authenticated stored revision,
then independently reads absence and revokes the scorer. Speaker similarity remains
evidence and grants no command or consequential-action authority.

The [acceptance plan](VAN_ARTEMIS_ACCEPTANCE_PLAN_2026-10-08.json) contains **826
prepared case contracts** against the current source snapshot. Zero physical cases
have been executed; prepared and locally checked contracts are not handset outcomes. The owner-selected
test route is native Artemis through DIAL/Commander on dial-control, outside
Hermes orchestration; use the [native handoff](../../tools/certification/NATIVE_ARTEMIS_HANDOFF_PROMPT.md).
The existing DDS/Hermes adapter is separately labeled legacy compatibility and
cannot qualify native operation. Actual native schemas, device admission,
deployment, signed owner release, provisioning and provider/phone evidence must
be observed in the later test session.
The three local speaker function cases require private device metadata readback,
bound to the installed S24/APK, source, current model and exact operation; they do
not invent a gateway profile API or export raw audio/embeddings. Imported receipt
consistency does not establish producer authenticity or physical speaker identity.
Private enrollment/erasure effects require those dedicated function cases. Broader
backend readbacks establish connection/owner-binding context and cannot certify
a local profile operation.

Regenerate actual schemas and reviewed contracts with
`python tools/audit/refresh_owner_registry.py`, then render the HTML with
`python tools/audit/render_owner_contract.py`. Current module entries and exact
Android gateway declarations/calls are regenerated from source; unresolved
citations stop the refresh. The immutable pre-closure registry remains archived.
After final local validation, the parent can supply absolute paths for `--final-source-manifest` and
`--android-receipt`; receipts without stable source binding and passing nonempty
checks are rejected. Prepare the final acceptance plan using the same manifest
through `artemis_acceptance.py prepare --source-manifest ...`.
