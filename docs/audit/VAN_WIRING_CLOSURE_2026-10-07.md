# VAN wiring closure — 7 October 2026

This is the current source implementation review. It supersedes earlier statements in
this audit directory about absent CDP, WebRTC, file-transfer, clipboard, Gmail MIME and
compiled automation producers. Earlier validation files remain historical evidence.
Final integrated validation and the source manifest are recorded alongside this report.

The [final validation receipt](VAN_WIRING_CLOSURE_VALIDATION_2026-10-07.json) records
**6,574 passing local test executions, 10 skipped, zero failures**. Android assembly,
lint and seven 16 KiB compatible native libraries passed. The [frontend contract](OWNER_FRONTEND_CONTRACT.html)
and [registry guide](OWNER_FRONTEND_REGISTRY_GUIDE.md) cover **42 features, 77 functions,
70 screens/hosted surfaces, 307 endpoint declarations and 165 schemas**. The prepared acceptance plan has
726 cases and zero physical executions.

The [local acceptance supplement](validation/wiring-local-acceptance-supplement-2026-10-07.json)
separately closes seven originally skipped cases: actual Gradle release-target/signing
refusal, character reference integrity, Hermes installer state preservation with rsync,
DIAL resource resolution and ledger parity/tampering detection against real isolated
PostgreSQL. Together these provide **6,581 passing local test executions**. The three
remaining skipped OCI firewall checks require privileges unavailable here. Original
suite receipts and registry hash bindings remain unchanged.

The registry classifies 30 feature groups as source-wired, four as requiring external
contracts/assets, and eight as containing explicit incomplete source contracts. These
counts describe the whole groups; implemented subfunctions do not make an unsupported
branch complete.

The selected deployment is VAN on **van-trading-core**, Hermes profile `van` on
**dial-control**, a separate VAN phone TLS ingress, and isolated public/owner browser
instances. Android receives its route and trust through the release profile and signed,
single-use installer provisioning. It has no owner host, port, API-key or certificate
configuration screen. Normal Android permission and biometric prompts remain necessary.

## Implemented connections and controls

| Area | Implemented behavior |
| --- | --- |
| Phone connection | Release-target validation, pinned HTTPS/WSS, hardware-bound identity, signed provisioning, exact enrollment recovery, credential renewal, session admission/resume and offline outbox reconciliation. |
| Commands and missions | Immutable intent and authority, exact retries, durable callback recovery, independent success verification, current cancellation/message controls and owner-visible pending/unknown/error states. |
| Owner information | Independent Home data loading, real project/mission/reminder navigation, connected-source readiness and revocation, memory and learning views, and explicit unavailable/cached data. |
| Owner autonomy | Discovered domain and S0–S4 ceiling controls, exact sealed A4 biometric approval, atomic current-device checks and independent readback. Lost replies recover committed changes without reapplying an older superseded ceiling. |
| Owner declarations | Explicit vocabulary definitions and collaboration instructions, bound owner/session proof, bounded typed fields, atomic owner provenance, separate exact readback and reversible forgetting. They grant no action permission and do not certify inferred traits. |
| Gmail | Actual MIME preparation, fresh private From/To/Cc/Bcc/Subject/body review, content-digest-bound biometric approval, immutable approved send payload and independent sent-message readback. Original-draft retention is disclosed. |
| Calendar and research | Real resource operations, ETag concurrency, preserved timed-event duration, exact effect readback and typed provider outage/redirect/malformed-response failures. |
| Trading | Read-only integrity/readiness, current ticket list, hardware-proved exact ticket authority, biometric confirmation, finite amounts, atomic fill recording and independent ledger verification. Ticket confirmation records broker evidence; it does not submit an order. |
| Browser owner control | Actual WebRTC video and data channels, frame/viewport acknowledgement, measured input coordinates, keyboard mapping, takeover/pause/resume, session renewal, chooser-bound uploads, quarantined verified downloads, cleanup acknowledgements and explicit clipboard copy/paste. |
| Browser delegated reads | Core-issued bounded deterministic navigation/read/DOM/evidence plans, canonical task/caller/domain/control fences, fresh authorization at the effect boundary, actual navigation-commit checks and source-bound download observations. |
| Browser deployment | Separate users, ports, Chromium profiles, encrypted staging and credentials; persistent cross-profile CDP fencing; fixed same-origin HTTPS signalling/file/clipboard routes with verified upstream TLS. |
| Automation | Real provisioned n8n helper IDs and narrow credentials, sealed parent/helper graphs, fresh pre-run drift checks, supported typed callback operations, current per-step MAC grants, durable lost-reply handling, independent observation, staged dedupe delivery and current-authority standing schedule/event production. |
| Platform compatibility | Compatible Rive runtime with 16 KiB native-library alignment, explicit Fragment ActivityResult dependency, and release inspection of native ELF and APK alignment. |

Browser producer and automation worker requests use explicit machine routes and narrow
machine credentials. Their authentication is not represented as phone-owner identity.
The remaining owner routes retain device proof and TLS/device admission requirements.
Actual loopback HTTP cannot impersonate HTTPS through forwarded headers. Socket task
cleanup survives peer disconnect after revocation, while the control effect remains
refused. All nginx temporary selectors use encrypted ingress staging.

## Contract limits that the redesign must preserve

These limits are separately recorded in the feature/screen registries. They must not be
collapsed into a generic “waiting for phone testing” label.

- Delegating browser custody does not approve arbitrary input effects. The current native
  core plan supports bounded navigation and observation. Autonomous browser mutation
  lacks a typed owner-approved immutable action-plan contract and remains refused.
- Browser `ANALYSE`, `SAVE_ON_ORACLE` and VEKL file-ingestion permissions are not executable
  byte producers. Completed safe download transfer to the phone and observed host-file
  deletion are implemented; other actions must remain unavailable.
- Unsupported automation primitives, arbitrary expressions, branching graphs and
  unevaluated preconditions are nondeployable candidates. Only the implemented closed
  operation set can be provisioned and executed. Operation class/effects are checked
  independently of caller labels; n8n success alone never establishes owner success.
- General standing-permission creation lacks an executable authority contract. The
  permission inventory is metadata; writing it would not authorize an effect. Supported
  exact standing-automation contracts, owner ceiling editing and vocabulary/collaboration
  declarations have their own explicit contracts and controls.
- Decision-pattern/contradiction inference without an actual producer remains inactive.
  Observed records and explicit owner corrections remain distinct from inferred facts.
- Remote mission pause/resume/adoption, richer decision choices and individual derived
  memory-export controls remain governed by the missing contracts listed per feature.
- The visual frontend and Rive character redesign is deferred by the owner. This work
  supplies audited functionality and contracts for that redesign.

An explicit stored owner autonomy ceiling now limits learned suggestion/preparation;
successful history cannot raise a deliberately lowered ceiling. False-success and
negative-evidence suspension still apply.

## Validation and acceptance boundary

The final local Android build, unit tests, JVM tests, lint and seven packaged native
libraries have passed their recorded checks. Local browser checks exercise real TLS,
WebSocket CDP transport and aiortc peer/data channels with controlled fixtures. The cloud
image could not start Chromium's default sandbox; no sandbox bypass was used and these
fixtures are not a deployed Chromium or phone acceptance receipt.
The generated ingress passed an actual signed-package nginx parser with local fixture
paths and bind selectors. Systemd parsing passed with local executable selectors. Kernel
permissions prevented nft validation; actual firewall and profile confinement remain
host acceptance requirements.

The owner has deferred S24 testing until wiring is complete. No physical test, provider
canary, production deployment, signed owner release or handset provisioning is claimed
here. The debug APK is a local build artifact, not an owner release. Prepared deployment
configuration is distinct from installed and measured service readiness.

Use the current registries for actual functions, routes, schemas, authority, error states,
source citations and remaining contract limits. Use the native Artemis handoff for later
phone acceptance. Artemis runs directly through DIAL/Commander on dial-control; Hermes
remains VAN's application backend runtime.

The exact uncommitted implementation and evidence are packaged in
`/workspace/van-audit/van-wiring-source-handoff-2026-10-07.tar.gz`, with a SHA-256 sidecar
and restoration verification receipt. The handoff contains a binary tracked patch,
untracked source/tests/registries/docs and a hash manifest. It was reconstructed against
the exact base commit and checked against every frozen production file. Build artifacts,
credential bindings and local toolchains are outside the source bundle. No commit or
push was performed.
