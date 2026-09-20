# VAN Remote Browser Production Blueprint — Rev 1.5

**Status:** SUPERSEDING IMPLEMENTATION BLUEPRINT  
**Product:** VAN (`com.dial.van`)  
**Repository:** `Vanguduza/Van`  
**Repository baseline inspected:** `main` at `66e4e42a9e8994a0f3129fbda4c794b68b353120`  
**Repository version at baseline:** `0.5.0-dev`  
**Date:** 2026-09-19  
**Supersedes:** Rev 1 through Rev 1.4 in full. Prior revisions SHALL NOT be used for implementation.
**Expert-review basis:** `docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_EXPERT_REVIEW.md` on `claude/plan-review-r45a7u`.
**Rev 1.2 scope expansion:** hardened offline voice edge + durable multipath VAN⇄Hermes logical session with transport failover.
**Rev 1.3 alignment authority:** merged PR #48 (`66e4e42a9e8994a0f3129fbda4c794b68b353120`) and its closure/audit machinery.
**Rev 1.4 product expansion:** native Android multi-window/pop-up behavior, home-screen shortcuts, zero-manual-connectivity setup, and server-enforced single-S24 binding.
**Rev 1.5 consolidation:** resolves the Rev 1.4 expert-review C1–C3 and D1–D8 findings; removes stale normative contradictions; reorders the critical path.
**Primary objective:** Deliver a production-grade, extremely low-latency, visually clean, native-feeling browser inside VAN whose Chromium runtime executes on Oracle infrastructure, while remaining coherently integrated with the existing Hermes, VAN Gateway, Browser Harness, Stagehand, voice, mission, authority, evidence, degraded-mode, and Android systems.

---

# 0. EXECUTION CONTRACT

This document is not a conceptual architecture note. It is the implementation authority for a complete VAN Remote Browser vertical slice.

The implementation SHALL NOT be considered complete because files exist, classes compile, unit tests pass, an endpoint responds, or a demo screenshot looks correct.

A remote-browser capability is complete only when it passes all of these distinct states:

1. **DESIGNED** — contracts and authority boundaries are explicit.
2. **BUILT** — implementation exists.
3. **WIRED** — real production paths call it.
4. **REACHABLE** — the intended Android/UI surface can invoke it.
5. **LIVE** — it runs against the actual browser runtime, not a fixture or fake adapter.
6. **VERIFIED** — the requested effect is deterministically confirmed.
7. **OBSERVED** — telemetry/evidence proves the real execution path.
8. **RECOVERABLE** — reconnect, restart, crash, stale lease, and process-death paths work.
9. **CERTIFIED** — actual S24 device and Oracle runtime gates are green.

The repository has already demonstrated why this distinction is necessary: VAN has previously had components that were correctly described as **BUILT** while not yet being called by a real execution path. This blueprint treats that class of gap as a design failure, not as cleanup.

No implementation agent may collapse these states into a single `DONE` or `PASS`.

---

# 0A. REV 1.1 CORRECTION REGISTER

Rev 1.1 exists because the expert review found five blocking repository-contract mismatches and eleven significant implementation risks. All are now normative requirements.

## Blocking findings resolved in Rev 1.1

| Finding | Rev 1.1 disposition |
|---|---|
| B1 — S24 cannot reach private `van-trading-core` | Production streaming host is no longer `van-trading-core`. A dedicated public-facing browser-stream host is the recommended Phase 0 owner decision. `van-trading-core` remains private. |
| B2 — 2 OCPU ARM64 host cannot meet target encode budget safely | A1/Trading Core may be used only for bounded internal path proof. Production target must be a dedicated host sized from measured encode/capture results; hardware encode is preferred where available. |
| B3 — invalid profile aliases | Rev 1.1 uses the existing canonical aliases `public_research` and `authenticated_owner`. New aliases require an explicit owner-approved policy amendment. Existing `runtime.profile_root` remains authoritative. |
| B4 — five-minute non-renewable `PageLease` | Profile leases gain an explicit holder kind/id plus renewal/heartbeat semantics. Interactive sessions cannot continue accepting input after lease expiry. |
| B5 — realtime envelope did not match `events` store | Schema migration 27 extends events for durable IDs, device targeting and millisecond timestamps. Sequence remains globally monotonic, with device-filtered visibility and per-device cursors. |

## Significant findings resolved in Rev 1.1

| Finding | Rev 1.1 disposition |
|---|---|
| S1 — cross-channel DOWN/MOVE/UP ordering | Explicit gesture epochs, duplicated edge events, independent sequence spaces and server-side pointer state machine. No cross-stream arrival ordering is assumed. |
| S2 — `BrowserTask.mission_id` does not exist | Interactive sessions receive their own `MissionBinder.bind_browser_session(...)` reference path. Child tasks continue using the existing request-time binder. |
| S3 — grant-key lifecycle absent | Dedicated P-256 ECDSA gateway→stream-runtime signing key, `kid`, provisioning, verifier-only runtime, rotation overlap and revocation tests. |
| S4 — cellular data cost omitted | Android metered-network detection, data counter, owner-visible quality policy and default metered cap. |
| S5 — Android WebRTC/WebSocket dependencies unnamed | WebRTC Android artifact and OkHttp are explicit Phase 0 dependencies with pinned versions/digests. |
| S6 — Stagehand adoption is still pending | Phase 7 cannot begin until the existing Stagehand adoption decision is owner-approved and live-certified. **Rev 1.5.1 correction (§0F.2):** the decision is already owner-approved — `docs/decisions/VAN-ADOPT-STAGEHAND-001.yaml` records `owner_signature_status: SIGNED`, `APPROVED_AS_HERMES_SUBAGENT`, 2026-09-18. What remains for Phase 7 is live certification of the runtime, which is an external gate, not another owner signature. |
| S7 — old viewport input behavior ambiguous | Old/unacknowledged viewport revisions are rejected/withheld. No coordinate transform across Chromium reflow. |
| S8 — capture mechanism unspecified | Phase 1 must choose and certify display server + capture primitive. Capture latency is measured separately from encode. |
| S9 — canary pages conflicted with SSRF boundary | Canary origin is a distinct explicitly allowlisted test origin, never localhost/metadata/private-control addresses. |
| S10 — touch sampling wording | Historical MotionEvent samples are retained for velocity; outbound motion is coalesced per display frame. |
| S11 — matrix schema ambiguity | Remote Browser matrix uses `van-implementation-matrix/1` with an explicit Remote Browser extension block. |

No implementation agent may re-open any of these choices implicitly. Any material deviation requires a new documented decision or review finding.


# 0B. REV 1.2 CROSS-CUTTING ARCHITECTURE UPGRADE

Rev 1.2 adds two cross-cutting requirements that are now load-bearing for Remote Browser and for VAN as a whole:

1. **VAN⇄Hermes is a durable logical session, not a socket.**
2. **Voice input and voice output remain locally functional without public internet on the S24.**

These changes are inseparable. Remote browsing, voice research, spoken answers, missions, approvals and browser takeover all depend on reliable owner↔Hermes continuity. A single WebSocket, tunnel, reverse proxy or protocol must never become a single point of failure for the VAN experience.

Rev 1.2 therefore introduces:

- `VanHermesSessionManager`;
- `TransportSupervisor`;
- multiple interchangeable control/event transports;
- make-before-break failover when possible;
- content-level idempotency above transport;
- global durable event replay;
- transport-independent turn/command/response identity;
- route-diversity awareness;
- local encrypted outbox;
- response/speech segment cursors;
- offline ASR/VAD/TTS asset certification;
- Sherpa-ONNX-backed deterministic local voice fallback;
- speech continuity through network-path failover;
- voice-first production acceptance canaries.

### Rev 1.2 non-negotiable invariant

```text
No VAN feature may depend directly on one physical Hermes connection.

Features depend on the durable VAN–Hermes logical session.
Transports are replaceable carriers underneath it.
```

The Remote Browser media plane remains independent. Browser WebRTC may fail while the VAN⇄Hermes logical session remains healthy, and vice versa.

### Continuity is not falsely claimed

Multiple protocols over one failed route do not create route redundancy.

Rev 1.2 distinguishes:

```text
PROTOCOL_DIVERSITY
    different transport mechanisms

ROUTE_DIVERSITY
    independently reachable ingress paths

LOCAL_CONTINUITY
    capabilities that remain usable with no Hermes path
```

`MULTIPATH_HEALTHY` may be claimed only when at least two independently reachable approved paths are actually proven live. Otherwise VAN reports `SINGLE_PATH`, not a flattering multipath status.


# 0C. PR #48 MERGE ALIGNMENT — REV 1.3

Rev 1.3 is reconciled against merged PR #48:

```text
PR:          #48
merge SHA:   66e4e42a9e8994a0f3129fbda4c794b68b353120
main:        66e4e42a9e8994a0f3129fbda4c794b68b353120
version:     0.5.0-dev
schema:      26
PR size:     60 commits / 481 changed files
```

The PR's most important product lesson is now a binding implementation rule for Remote Browser:

> A component may exist, compile and pass its own tests while still being functionally absent because no real producer or consumer reaches it.

Remote Browser SHALL therefore integrate with the closure programme's existing machinery instead of creating a parallel proof system.

## 0C.1 Merged contracts Rev 1.3 reuses

PR #48 already provides real production foundations for several areas Rev 1.2 proposed to create.

| Concern | Merged PR #48 authority / implementation | Rev 1.3 action |
|---|---|---|
| Gateway retry/backoff | `android/.../gateway/GatewayRetry.kt` | Extend/reuse; no second retry implementation. |
| Offline command replay | `EncryptedCommandQueue`, `QueueReplayer`, `ReplayTrigger` | Extend metadata/policies; no second durable outbox. |
| Event stream | `EventStream.kt`, `PreferencesEventCursorStore.kt`, backend `EventBus` | Upgrade to push + replay; do not replace cursor/reducer. |
| Android degraded truth | `DegradedModeStore`, `SubsystemSignals`, `SubsystemHealth` | Extend with browser/session/voice dimensions. |
| Wake lifecycle | `WakeListenerService`, `WakeCoordinator`, `WakeRuntimeController`, `WakeModelLoader` | Bind a real admitted local model/runtime into these existing contracts. |
| Wake model truth | `WakeModelAsset.kt` | Preserve fail-closed model readiness/digest classification. |
| TTS call path | `TtsOutputManager.speak` is production-called but device-unverified | Harden backend and certify on S24; do not claim it is already proven. |
| Browser owner surfaces | `command/modules/BrowserModules.kt` | Add Interactive/Live Browser entry to the existing Browser & Automation module. |
| Browser worker boundary | `AdapterBackedWorker` / `SubagentWorker` wired | Attach live external Browser Harness/Stagehand runtime; do not invent a new browser-task authority. |
| Mission creation | accepted owner command → exactly one Mission | Browser/voice work attaches to that Mission; never creates a duplicate Mission. |
| Verification | `VERIFIED_SUCCESS` requires independent verifier/evidence | Remote Browser tasks obey same success contract. |
| Observability | correlation IDs, metrics, alerts, event lag | Add remote-browser/session metrics to existing instruments/catalogue. |
| CI truth | maturity gate, authority map, ledger reconcile, Kotlin reachability | Mandatory for every implementation pass. |
| Mutation proof | `tools/audit/mutation_suite.py` | Required for changed behavioral invariants. |

## 0C.2 Current merged external blocks that Rev 1.3 must not misrepresent

PR #48's component ledger currently records:

```text
WakeWordEngine                 EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE
WakePhraseVerifier             EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE
SpeakerSimilarityScorer        EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE
Wake pipeline/coordinator      INTEGRATED_AND_EVIDENCED
Wake acknowledgement playback  CALLED_UNTESTED maturity, terminal EXTERNALLY_BLOCKED / device gate
TtsOutputManager.speak         CALLED_UNTESTED maturity, terminal EXTERNALLY_BLOCKED / device gate
LocalSecondPassAsr             EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE

Browser Harness worker         EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE
Stagehand worker               EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE
SubagentWorker                 INTEGRATED_AND_EVIDENCED
browser adapter actuation      EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE
```

Rev 1.3 does not rewrite those current-state facts.

**Rev 1.5.1 correction (§0F.1).** The two rows above were quoted with `CALLED_UNTESTED` in
the column the other rows use for a terminal state, and those are two different fields. The
maturity class is still exactly `CALLED_UNTESTED` — both paths are called from production and
no test names either — but `P2-LEDGER-002` gave both the terminal state
`EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE`, blocked on a device that can play a sound or speak.
Nothing this document asks for changes. What changes is how §40.3 must be read: these are
terminal rows, not the non-terminal ones its mapping table assumes, and at this baseline the
component ledger holds no non-terminal rows at all.

Instead, it defines the work and owner decisions required to move those components to stronger maturity states.

## 0C.3 Schema consequence

Rev 1.2 incorrectly assumed the next schema migration would be 17.

PR #48 merged schema v26.

The Remote Browser semantic migration is therefore:

```text
MIGRATION_27
SCHEMA_VERSION = 27
```

unless repository state advances again before implementation, in which case the implementation agent MUST resolve the next unused version from the live repository rather than hard-code 27.

## 0C.4 Authority-map consequence

`docs/project-state/AUTHORITY_MAP.yaml` now enforces one owner per invariant.

Rev 1.3 SHALL NOT silently become an authority document merely because it exists.

Before implementation begins:

1. identify each genuinely new invariant subject introduced by Remote Browser;
2. assign it to exactly one permitted owning document;
3. if Rev 1.3 is to own a new subject, explicitly add it to `owning_documents`;
4. add implementation and tests only after they exist;
5. never duplicate an existing subject such as:
   - `android.gateway_resilience`;
   - `android.voice_runtime_is_shippable`;
   - `ops.degradation_is_scoped`;
   - `trust.browser_escalation`;
   - `verification.no_success_without_evidence`.

This prevents Rev 1.3 from creating the documentation contradiction class PR #48 was built to eliminate.


# 0D. REV 1.4 OWNER-S24 NATIVE-BROWSER AND ZERO-CONFIG CONTRACT

Rev 1.4 adds three non-negotiable product requirements.

## 0D.1 VAN Browser behaves like a normal Android browser window

The owner must be able to use VAN Browser as a normal application surface:

```text
full screen
split screen
Samsung pop-up/freeform view
Samsung DeX/freeform window
orientation/window-size changes
home-screen shortcuts to VAN Browser or a saved page
"Open with VAN" for safe http/https links where enabled
```

This is OS-native multi-window behavior, not VAN's floating assistant overlay.

Samsung documents `android:resizeableActivity="true"` as the key application contract that allows an activity to participate in split-screen and Samsung pop-up/freeform modes. Android's own multi-window guidance requires responsive behavior across changing window bounds.

Rev 1.4 therefore treats resizability, state continuity and live viewport renegotiation as production functionality.

## 0D.2 No manual connectivity configuration

The owner production build SHALL NOT ask for or expose editable fields for:

```text
Gateway URL
Hermes URL
WebSocket URL
browser stream host
TURN/STUN host
pairing token
device id
ingress token
fallback endpoint
certificate pin
transport priority
```

All non-secret connectivity configuration ships in a signed configuration manifest.

Secrets/credentials are provisioned automatically.

The owner may see read-only diagnostics, but no ordinary connectivity setup form exists.

## 0D.3 The production VAN instance works only on the owner's S24 Ultra

The package may physically install elsewhere if Android permits installation, but it MUST be cryptographically non-functional on any other handset.

The restriction is server enforced.

Do **not** implement this as only:

```kotlin
if (Build.MODEL == "SM-S928B") allow()
```

because another S24 Ultra would pass the same check.

The production binding is:

```text
this installed package
    +
this app signing identity
    +
this hardware-backed Android Keystore key
    +
this Gateway owner-device slot
```

The unique public-key fingerprint generated by the owner's phone becomes the sole active owner-device identity.

Copying the APK or copying bearer credentials to another phone does not produce the corresponding non-exportable private key.

## 0D.4 Normal system consent is not "manual connectivity configuration"

Android/Samsung can still require owner confirmation for platform-controlled operations such as:

```text
microphone permission
notification-listener access
draw-over-other-apps permission
biometric enrollment/use
launcher confirmation when pinning a home-screen shortcut
```

Those are Android security/launcher consent surfaces.

They are not VAN server configuration and SHALL NOT be replaced by insecure workarounds.


# 0E. REV 1.5 CONSOLIDATION / PRECEDENCE RULE

Rev 1.5 is intentionally a **consolidation revision**, not another append-only correction.

The Rev 1.4 expert review found that appended corrections had allowed stale normative text to survive in the original body. Rev 1.5 fixes the identified passages in place and establishes this permanent precedence rule:

> **If any historical sentence in this document conflicts with §§0A–0E or with a later section that explicitly says it supersedes an earlier contract, the later explicit contract governs. An implementation agent must not choose the older path.**

This rule is a safety net, not permission to leave known contradictions unresolved. The known stale passages identified by the Rev 1.4 expert review are edited in place in Rev 1.5.

## 0E.1 Rev 1.4 expert-review disposition

| Finding | Rev 1.5 resolution |
|---|---|
| C1 Stagehand host unresolved | **Resolved.** Chromium/media runtime is on a dedicated dual-homed Browser Stream Host. Stagehand and Browser Harness remain on private Trading Core. A narrow private `Browser Control Agent` on the stream host owns loopback CDP; Harness reaches it over mTLS on the private VCN. Raw CDP is never public or directly routable across hosts. |
| C2 nonexistent `ownerS24` flavor | **Resolved by removal.** Rev 1.5 does not introduce a product flavor. The single production owner build is the existing `release` build type. Immutable config lives under `src/release`. Cryptographic device binding, not a flavor name, makes the build owner-S24-only. |
| C3 RB↔component-ledger mapping undefined | **Resolved.** §40 now defines an explicit mapping and requires `component_refs` plus a ledger bridge check in the existing reconciliation gate. |
| D1 stale normative passages | **Resolved in place** plus this precedence clause. |
| D2 duplicate realtime/session socket | **Resolved.** the legacy standalone realtime endpoint/package are deleted from the plan. `/v1/session/ws` is the sole realtime semantic session socket; REST event replay remains the durable floor. |
| D3 critical path blocks browser on offline voice | **Resolved.** Minimum logical-session primitives gate the first browser slice. Offline voice and full multipath hardening run in parallel and gate final certification, not first-frame proof. |
| D4 prior Sherpa decline not clearly reversed | **Resolved.** The owner's later instruction requiring hardened offline voice explicitly supersedes the earlier decline. The decision artifact records the reversal; implementation does not ask the owner to re-decide it. |
| D5 no posture for S24 attestation failure | **Resolved.** Physical S24 attestation preflight happens before binding policy is frozen. Failure blocks certification; there is no silent downgrade to model-name or bearer-token binding. |
| D6 metered quality conflicts with normal SLO | **Resolved.** §26 now has separate unmetered and metered SLO profiles. |
| D7 lease cleanup grace ambiguous | **Resolved.** Grace is cleanup/reconnect only; actuation stops at expiry immediately. |
| D8 blueprint had no repository path | **Resolved.** Canonical intended repository path is `docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md`. |

## 0E.2 Owner instruction superseding prior offline-voice decline

The repository records an earlier owner decision not to build the Sherpa/local runtime at that time.

The owner has subsequently issued a later, explicit product requirement that offline voice input and local spoken answers be hardened because VAN must answer voice-originated questions by voice, including during connectivity degradation.

Under Project Truth's owner-authority rule, the later instruction supersedes the earlier product choice.

Implementation SHALL create:

```text
docs/decisions/VAN-ADOPT-OFFLINE-VOICE-RUNTIME-001.yaml
```

and record:

```text
decision_type: OWNER_SUPERSESSION
supersedes: <prior decision reference>
basis: owner instruction requiring hardened offline voice input and local talk-back
```

No implementation agent is self-authorizing this reversal; it is recording the owner's later instruction faithfully.

## 0E.3 Critical-path principle

Three tracks now exist:

```text
TRACK A — FIRST INTERACTIVE BROWSER VERTICAL SLICE
    minimum logical session identity/resume/fencing
    + browser runtime/media
    + S24 native viewport/input

TRACK B — CONNECTIVITY RESILIENCE HARDENING
    protocol fallback
    route diversity
    warm standby
    store-and-forward

TRACK C — OFFLINE VOICE HARDENING
    local wake
    local ASR fallback
    local TTS
    segment continuity
    barge-in
```

Track A does not wait for Tracks B or C to finish.

Final production certification requires all applicable Track A+B+C gates to be green.


# 0F. REV 1.5.1 REPOSITORY-LANDING CORRECTION REGISTER

Rev 1.5 landed in the repository at `docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md`
on 2026-09-19, against `main` at `66e4e42` — the merge commit it names as its own baseline.

§42.1 requires the implementation agent to read the live repository before changing code, and
§49 requires its checklist to be re-run against that repository rather than trusted from this
page. That was done first. Fifteen of this document's repository claims were checked against
the source; all fifteen hold, including the schema version, the exact shape of the `events`
table, the task-shaped `PageLease`, the absent `BrowserTask.mission_id`, the two profile
aliases and every Android class §2.7 says to reuse.

Four corrections follow from that pass. Each is edited in place per §0E's consolidation rule,
and recorded here so the edit is visible rather than silent.

| # | Correction | Where |
|---|---|---|
| 0F.1 | The §0C.2 ledger quote put `CALLED_UNTESTED` where the surrounding rows carry a terminal state. Both are real and they are different fields: the maturity class is still `CALLED_UNTESTED`, and `P2-LEDGER-002` gave both rows the terminal state `EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE` *inside* the merge this document cites. The first draft of this correction claimed no component is `CALLED_UNTESTED` any more; that was wrong, and a contract test caught it. | §0C.2 |
| 0F.2 | S6 treats the Stagehand adoption decision as pending. It is owner-approved (`SIGNED`, `APPROVED_AS_HERMES_SUBAGENT`, 2026-09-18). Phase 7's remaining gate is live certification of the runtime, which is external. | §0A/S6 |
| 0F.3 | The §49 Rev 1.5 checklist ended with "no migration-27 event text remains normative", contradicting §5.6, which makes migration 27 *the* event-store extension. Read with §0C.3 the line is about Rev 1.2's incorrect assumption of migration **17**. | §49 |
| 0F.4 | Two names §2.7 and §49 list as if they were files are symbols inside other files: `SubsystemHealth` is an object in `degraded/SubsystemSignals.kt`, and `WakeRuntimeController` is a class in `voice/WakeRuntime.kt`. Both exist. Recorded so that a later agent does not conclude they are missing and build a second one — the failure §42.2 forbids. | §2.7, §49 |

## 0F.6 Defects found while implementing this document

These are not corrections to the blueprint. They are defects in work done *against* it,
recorded here because §42.5 asks for the counterexample rather than the claim, and because
three of the four were green in every test that existed at the time.

| # | Defect | Counterexample that found it | Where it was fixed |
|---|---|---|---|
| 0F.6a | `OwnerDeviceBindingService.require_proof` was implemented, unit-tested against itself, and called by nothing. ADR-RB-025 read as satisfied while a stolen device token reached every owner route, and `/v1/device-binding/status` answered `bound: true` throughout. | A privileged request with **no proof header at all**. No unit test of a verifier can construct that case; only a test through the ingress can. | `van_gateway/app.py` — `requires_device_proof` and `enforce_device_proof` in the ingress middleware; `backend/tests/test_device_proof_enforcement.py`. |
| 0F.6b | The first version of that gate asked `for_device(caller)`, so the proof was mandatory only for a device that had already enrolled. A second paired phone skipped the gate entirely by never having proved anything. | A second paired device performing an owner mutation while the owner's phone is bound: the request succeeded. | The gate now reads `active()`: once any device is bound, every other device is refused outright. |
| 0F.6c | Two implementations of one canonical JSON form. Both sorted keys, both dropped whitespace, and both agreed on every ASCII document — but Python's `json.dumps` escapes non-ASCII and the Kotlin verifier emitted the character. A manifest or command payload with one accented character verified on the phone and nowhere else. | Shared vectors generated by the gateway, including `naïve — 東京` and an astral-plane character. Invisible in a source diff. | `security/VanCanonicalJson.kt` is now the single rule; `evidence/van-remote-browser/cross_language_vectors.json` plus the two tests that read it. |
| 0F.6d | The device's `SessionEnvelope` wrote `direction: "DEVICE_TO_GATEWAY"`, which reads better than the gateway's `UPSTREAM` and is rejected by the envelope validator. Every message would have failed at the door. | A contract test comparing the device's constants with the gateway's `Direction` enum, written because 0F.6c had just shown that field *names* matching is not the same as field *values* matching. | `session/SessionEnvelope.kt`; the check is `test_the_device_uses_the_gateways_spelling_of_direction`. |
| 0F.6e | The proof middleware read the request body and then hand-rolled a replay by reassigning `request._receive`, with a comment asserting that without it every proved route would parse an empty body. The comment was wrong. Starlette's `BaseHTTPMiddleware` already wraps the request in a `_CachedRequest` whose documented behaviour is exactly that, so the replay was a second mechanism for one job and the one I wrote was the one nothing exercised. | A mutation deleting the replay line: the suite stayed green. | The replay was removed rather than the mutation weakened; the assertion that a proved POST returns the field it sent is kept as the regression test for a Starlette that stops caching. |
| 0F.6f | A refusal test asserted `status_code in {401, 403}`, which passed with the ownership check deleted — the proof names its own device, so the request was refused anyway, as `device_not_bound`. Two different facts collapsed into one loose assertion. | A mutation removing `if binding.device_id != device_id`: it survived. | The test now pins `403 device_not_owner_device`. Both refusals are correct and only one of them is true. |
| 0F.6g | The Android speech queue had two guards covering one case: a duplicate `segmentId` and an index at or below what the owner had heard. Every test exercised both at once, so a mutation of the index check survived. It is not redundant — it is the only thing that catches a *renumbered* stream, where the Gateway re-segments an answer and produces a new id for text already spoken — but nothing had separated them. Eighth occurrence of overlapping guards in this programme. | A mutation deleting the index check: green. | An isolating test offering a new id at a spoken index, plus a cross-stream guard, because two answers in one queue were comparing their indexes as if they were one sequence. |
| 0F.6h | `SpeechStreamService.open` is idempotent on `response_id`, and the test for it asserted the stream id and segment count — both of which are derived from the response id and therefore identical with the guard removed. The property it actually protects is the cursor: a second `open` forgets what the device reported it heard, so the resume replays audio the owner already heard. | A mutation removing the idempotency check: green. | The test now reports a cursor, re-opens, and asserts the cursor survived. |
| 0F.6i | Two more of the same shape in one checkpoint. An abbreviation test used a sentence whose halves were short enough for the fragment packing to rejoin them, so it passed with the abbreviation handling deleted; and `_split_long` had an early return for a sentence with no clause boundary that the loop below already handled identically. | Mutations of both: green. | The test uses halves long enough to survive packing; the dead branch was removed rather than the mutation weakened. |
| 0F.6j | `MissionBinder.bind_browser_session` bound under the capability id `browser.interactive.session`, which no registry declared. §7 refuses an undeclared capability, and the route called the binder unguarded, so **every** mission-bound browser session — §23.1's own worked example — was a 500, after the session had leased the owner's authenticated profile. The binder's tests pass `capabilities=None`, which returns before the registry is consulted; the route's tests never pass a `mission_id`. Neither side was wrong; the path between them had never run. | Opening a session with a `mission_id` against the real app, which no test did. | The capability is declared `EXTERNAL_RUNTIME` against `browser_stream_host` rather than `STATIC`, so the refusal is earned rather than removed; the route unwinds the session; `tests/contracts/test_stream_host_readiness_is_earned.py` parses the binder's constant and requires the registry to hold it. |
| 0F.6k | Six new §28.1 instruments are `MetricSource.GATEWAY` and none of them can fire without a Stream Host, so `INSTRUMENT_SILENT` would have paged every deployment without one every fifteen minutes, forever. | The existing test that a device metric's silence is not a fault: it failed the moment the catalogue grew. | `silence_is_normal` on the declaration, fenced by a test that derives the exempt set from the property and another that requires the rule to still fire. |
| 0F.6l | Two of §28.1's four *device* metrics were added to the gateway in a third dict, `DEVICE_COUNTERS`, beside the two the device-telemetry contract test reads. The test whose whole job is to stop the gateway's list and the phone's enum drifting was reading two thirds of the list. | Running it after the catalogue grew, and asking why it still passed. | The contract folds the counters in, and a second test requires every name in the enum to be one `record_device_sample` actually ingests. |
| 0F.6m | Two mutation survivors in one checkpoint, both tests asserting something true either way. `BrowserStreamTelemetry`'s clock-step test asserted that the backwards frame emits nothing and that the age is measured from it — both hold with the guard removed. What the guard decides is whether the fps window stays anchored in the future, which suppresses every reading until real time catches up and then reports a rate the decoder never achieved. And the drop-count guard was tested with zero, which is equivalent with or without it; its real job is a *negative* count from a cumulative counter differenced across a decoder restart, which subtracts drops that happened. | Mutations of both: green. | Isolating assertions on what each guard actually decides, and the mutation labels corrected to name the real failure. |
| 0F.6n | Three test failures that looked like an intermittent lease bug in the Gateway: the unwind after a refused Mission binding sometimes left the owner's profile leased, reproducing about once in thirteen runs and never under investigation. It was the mutation harness, running in another shell, editing the source in place — the mutation current at the time was the one that replaces that very unwind with `pass`. | Noticing that the reproduction rate dropped to zero the moment the harness finished, and that the three failures matched two mutation labels exactly. | A warning at the top of `tools/audit/mutation.py`, and the assertion in the test now prints the profile row and every session so the next such failure states its cause instead of requiring one. |
| 0F.6o | §17.5 sends an external http/https VIEW intent "through §9.14". The document has no §9.14: section 9 stops at 9.5. So the one rule that decides what an app on the owner's phone can make VAN open was a reference to nothing. | Implementing it and looking for the section. | The rule is stated in full at the implementation — untrusted navigation input, not an owner command; the public profile, fixed rather than parameterised; a second scheme anywhere in the address refused — rather than left as a dangling cross-reference. |
| 0F.6p | `tools/audit/kotlin_reachability.py` stripped comments and then strings, with two regular expressions. A Kotlin *string* containing comment punctuation therefore closed a block comment a KDoc had opened much earlier, and everything between vanished before any reference was counted. The string that did it is `"*/*"`, the MIME wildcard every Android file chooser passes: adding one to `BrowserActivity` made the gate report the renderer it constructs as referenced by nothing. | The gate's own output, on a file that had just been edited. | One left-to-right scanner handling block comments (Kotlin's nest), line comments, raw strings and ordinary strings in one pass; `tests/contracts/test_kotlin_reachability_stripper.py`, including the mirror bug the obvious fix has. |
| 0F.6q | The cross-language input-protocol contract compared the *intersection* of kind names and asserted there were at least nine. A kind on one side only was never in the intersection, so it was never compared and never missed — §17.2's six navigation kinds went into Python first and the test stayed green with the phone unable to send any of them. | Adding the kinds and asking why nothing failed. | Set equality, the two non-kind names the regex also matches listed explicitly, and the navigation kinds named on their own because equality is satisfied by both sides having none of them. |
| 0F.6r | Three C32 mutation survivors, all tests that were true either way. The resize coalescer's overdue branch was unreachable — a pending change always post-dates the last send, so the cadence can never be what is holding it. The omnibox's whitespace check looked redundant because every example in its test fell out as a search through some other clause. And the tab reducer's "is this the active tab" check was tested with two tabs, where the neighbour a wrong implementation picks is the active one. | Mutation. | The dead branch removed rather than the mutation weakened; isolating cases for the other two — a query whose last word looks like a host, and four tabs instead of two. |

Two lessons generalise. The first is why the vectors file exists rather than a
source-to-source comparison: **two implementations that are each correctly tested against
themselves prove nothing about each other.** Three of the first four are that failure.

The second is why 0F.6e through 0F.6i and 0F.6m are here at all: **a suite that stays
green when a guard is deleted is describing the guard, not testing it.** All of them were
found by mutation, after the tests for them had been written and had passed, and none was
visible any other way. Several are the same shape — two guards covering one case, so
neither is falsifiable on its own — which this programme has now hit nine times. The fix is
never to weaken the mutation: it is an isolating test, or the discovery that one of the two
guards was dead and should go.

0F.6m adds a variant worth naming separately, because it is not overlapping guards. Both
of its tests asserted something that was true with the guard and true without it — not
because two mechanisms covered the case, but because the assertion was about the wrong
consequence. A test can exercise exactly the right line and still be describing it. The
mutation is what tells the difference, and when it survives the question to ask is not
"which other guard covered this" but "what does this guard actually decide".

0F.6p is the one to keep in mind when reading any of the others: **the audit tools are
code, and they fail the same way the code does.** A gate that reports deadness silently
over-reporting it is worse than no gate, because the action an over-report invites is
deleting something that is running. It was found by its own output looking wrong on a file
that had just been edited — which is only possible because the output names files rather
than printing a count.

0F.6n is not a defect in the product at all, and it is recorded because it cost more
than several that were: **a test failing while the mutation harness is running is not
evidence about the product.** The harness edits source in place, so a parallel suite reads
whichever mutation is current. The rule is now written where the harness is, and the
assertion that failed prints enough state to say so next time.

A third lesson, from 0F.6j and 0F.6l: **a constant passed between two modules is an
interface, and nothing was checking either of these.** A capability id named in Python and
declared in JSON, and a metric name declared in Python and mirrored in Kotlin. Both were
green on each side. Both were broken across. The fix in each case is a test that reads one
side's value and requires the other to hold it, rather than two lists a person keeps in
step.

## 0F.5 Owner decisions taken by delegation

The owner instructed that this document be implemented to completion and that the agent use
its own recommendations wherever an owner decision was required. Those decisions are recorded
as artefacts, not as assumptions inside code:

```text
docs/decisions/VAN-ADOPT-REMOTE-BROWSER-STREAMING-001.yaml
docs/decisions/VAN-ADOPT-OFFLINE-VOICE-RUNTIME-001.yaml
registries/remote_browser_dependencies.json
```

Each carries `decision_type` honestly. `OWNER_DELEGATED_RECOMMENDATION` is not a countersigned
owner decision, and every part that needs the owner to provision hardware, supply a model or
hold a device is listed as an action still outstanding rather than absorbed into a status.

**One dependency deviates from this document and the deviation is deliberate.** §32.2 proposes
`okhttp:5.5.0`; that artefact carries Kotlin 2.1 metadata and this project compiles with the
Kotlin 1.9.24 plugin, so admitting it would have broken the Android build the first time it
was read. `okhttp:4.12.0` is admitted instead, with its digest measured from the artefact.
§32.2's own rule — that the admitted version is locked only after Gradle and Android
compatibility verification — is what produced the different answer.

---

# 1. PRODUCT OUTCOME

The owner shall be able to open a dedicated VAN Browser surface on the Samsung S24 and interact with a real Chromium browser that runs on the Oracle-side VAN Browser Runtime.

The experience shall feel like a native mobile browser:

- native Android browser chrome;
- native address/search bar;
- native tab switcher;
- native Android keyboard;
- responsive taps, swipes, fling scrolling, long press and pinch;
- full-screen remote webpage viewport;
- high-quality text;
- adaptive 60 FPS remote rendering under normal interactive conditions;
- browser audio;
- downloads represented by native VAN UI;
- session persistence through managed browser profiles;
- seamless owner control and VAN/Hermes takeover;
- voice control;
- VAN analysis of the page currently visible to the owner;
- local spoken responses through VAN TTS;
- immediate owner takeover whenever the owner touches the viewport;
- reconnect without silently losing authoritative state.

The website is rendered on Oracle. The Android device is not a WebView mirror and is not independently loading the same web page.

The governing model is:

```text
NATIVE ANDROID EXPERIENCE
┌──────────────────────────────────────────┐
│ VAN Browser chrome                      │
│ address/search • tabs • menu • VAN      │
├──────────────────────────────────────────┤
│                                          │
│      REMOTE CHROMIUM VIEWPORT            │
│      rendered on Oracle                  │
│                                          │
├──────────────────────────────────────────┤
│ native controls / voice / status         │
└──────────────────────────────────────────┘
```

The runtime model is:

```text
                              CONTROL / AUTHORITY PLANE

                              DIAL Hermes / profile van
                                      │
                                      │ reasoning, missions,
                                      │ Stagehand intent,
                                      │ approvals, evidence
                                      ▼
                               VAN Gateway
                                      │
                         signed task/session authority
                                      │
                                      ▼
                          Browser Session Broker
                                      │
                                      ▼
                            Browser Runtime / CDP
                                      │
                    ┌─────────────────┴───────────────┐
                    │                                 │
              Stagehand/Playwright               Chromium
                    │                                 │
                    └──────────── CDP ────────────────┘


                        REAL-TIME INTERACTION DATA PLANE

 Samsung S24                                                  Oracle
┌──────────────────────┐                         ┌────────────────────────┐
│ native VAN Browser   │                         │ Browser Stream Gateway │
│                      │                         │                        │
│ WebRTC decoder       │◄════ H.264 / Opus ═════│ capture + encode       │
│ SurfaceView          │                         │                        │
│                      │════ DataChannels ═════► │ input router           │
│ touch / IME / stylus │                         │                        │
└──────────────────────┘                         └───────────┬────────────┘
                                                           │
                                                           ▼
                                                        Chromium
                                                           │
                                                           ▼
                                                        Internet
```

**Hermes is not in the pixel loop.**  
**The VAN Gateway is not in the pixel loop.**  
**Stagehand is not in the human touch-to-photon loop.**

Those systems retain authority and intelligence without becoming latency multipliers.

---

# 2. EXISTING VAN CONTRACTS THAT MUST BE PRESERVED


The current VAN repository already contains the correct foundations. The Remote Browser implementation must extend them, not fork them.

## 2.1 Canonical authority

`PROJECT_CANONICAL_STATE.json` establishes:

- owner instruction as Project Truth authority;
- silent feature thinning forbidden;
- release requiring provenance;
- canonical lineage requiring verification;
- CI not being Project Truth authority;
- release currently blocked until applicable external gates are proven.

Remote Browser work MUST preserve these rules.

## 2.2 Hermes boundary

Current repository truth states:

- Hermes profile `van` is the sole VAN agent runtime.
- Android does not become a second agent.
- Browser workers are subordinate workers.
- Stagehand and Browser Harness do not independently create VAN commands.
- browser output cannot elevate authority.
- external content is untrusted.
- owner success cannot be inferred from a tool claiming success.

Remote Browser SHALL NOT create a new autonomous intelligence loop in Android, WebRTC, Chromium, GStreamer, Stagehand, or Browser Stream Gateway.

## 2.3 Existing Browser Fabric

The current repository already provides:

```text
backend/van_gateway/browser/
    models.py
    policy.py
    service.py
    adapters.py
    subagent.py
    api.py
```

It already defines:

- `BrowserTask`
- `BrowserTaskStatus`
- `BrowserStrategy`
- `AutonomyTier`
- `PageLease`
- `BrowserEvidence`
- `BrowserObservation`
- `BrowserSessionBroker`
- `BrowserTaskService`
- `BrowserPolicyEngine`
- browser profile aliases
- digest-only evidence
- prompt-injection assessment
- secret containment
- Stagehand / Browser Harness separation
- action-class enforcement
- task scope and lease semantics

These remain authoritative.

Remote Browser SHALL NOT introduce another competing `BrowserTask`, `BrowserPolicy`, profile registry, evidence store, domain-policy engine, or autonomy ladder.

## 2.4 Existing Android architecture

The Android application already has:

```text
gateway/
voice/
visual/
overlay/
mission/
degraded/
security/
queue/
notification/
trading/
```

`VanGatewayClient` already exposes Browser Fabric status/task/escalation/evidence reads, and it already has a sequenced `/v1/events?after_seq=` recovery API.

Voice already supports:

- local/on-device recognition policy;
- caller-audio injection where available;
- transcript provenance;
- partial/final results;
- second-pass recognition;
- local TextToSpeech;
- barge-in;
- speech animation frames;
- VAN durable visual state integration.

Remote Browser SHALL use those existing voice contracts.

## 2.5 Existing deployment direction

The existing browser/automation preflight establishes private Trading Core as the current deployment home for:

- Stagehand;
- Playwright;
- Browser Harness;
- browser profiles and browser domain policy;
- Browser Fabric authority/bootstrap.

Rev 1.5 keeps those **control/automation responsibilities** on private Trading Core.

The interactive Chromium renderer/media encoder does **not** run there in production. It runs on the dedicated Browser Stream Host defined in §13/§25.

The two hosts cooperate over a private VCN through the narrow Browser Control Agent contract; raw CDP never crosses the public interface.

The dedicated stream host is a Phase-0 architectural requirement, not a later performance contingency.

---



## 2.6 PR #48 closure programme is now part of the implementation contract

Before and after each Remote Browser closure group run:

```text
python tools/ci/maturity_gate.py
python tools/ci/authority_map.py
python tools/ci/ledger_reconcile.py
python tools/audit/kotlin_reachability.py
```

For behavior-changing closure groups also run:

```text
python tools/audit/mutation_suite.py
```

New Remote Browser components MUST appear in the same maturity/component accounting used by PR #48.

No component may be described as `INTEGRATED_AND_EVIDENCED` unless it has:

```text
producer
consumer
production caller
tests
runtime evidence
```

Repository-complete but externally absent components remain:

```text
EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE
```

until their external runtime/device/artifact is actually demonstrated.

## 2.7 Existing Android resilience must be evolved in place

The merged Android application already owns:

```text
GatewayRetryPolicy
GatewayCircuitBreaker
EncryptedCommandQueue
QueueReplayer
ReplayTrigger
EventStream
PreferencesEventCursorStore
DegradedModeStore
SubsystemSignals / SubsystemHealth
```

Rev 1.3 forbids parallel replacements for these concerns.

The new logical Hermes session and Remote Browser use them as lower-level primitives or extend them where their current contract is insufficient.

# 3. SCOPE

## 3.1 Required production capability

Rev 1 SHALL support:

- public HTTPS browsing;
- search engines;
- normal links/navigation;
- redirects;
- cookies/session persistence through approved profile aliases;
- text/password/email/number form input;
- owner manual browsing;
- tabs;
- reload/back/forward;
- page zoom/pinch;
- scrolling/fling;
- long press;
- clipboard under explicit policy;
- website audio;
- file downloads;
- upload from phone by explicit owner action;
- owner-visible connection state;
- orientation changes;
- network handoff/reconnect;
- browser process recovery;
- native VAN voice interaction;
- “ask VAN about this page”;
- VAN/Hermes analysis against the actual active browser target;
- autonomous Stagehand/Browser Harness operation of the same visible session;
- immediate owner takeover;
- browser activity bound to Missions when invoked by a Mission;
- durable browser evidence;
- low-latency telemetry;
- explicit degraded states.

## 3.2 Not silently implied

The following are distinct capabilities and MUST NOT be pretended complete merely because ordinary browsing works:

- camera forwarding into a remote web page;
- microphone forwarding to arbitrary websites;
- USB devices;
- DRM/Widevine protected playback;
- FIDO hardware keys physically attached to the S24;
- local Android passkeys transparently acting as remote Chromium passkeys;
- arbitrary browser extensions;
- unrestricted internal-network browsing;
- payment automation;
- live broker trading through the browser.

If any of these are later required, each receives its own authority/security design and acceptance gate.

Browser audio output IS in Rev 1. Website microphone/camera forwarding is not a prerequisite for the web-search/research target and therefore is explicitly outside Rev 1 rather than accidentally omitted.

---

# 4. ARCHITECTURAL DECISIONS




## ADR-RB-001 — native Android shell

VAN Browser SHALL be a native Android surface.

The Android UI owns:

- browser chrome;
- address field;
- search mode;
- tabs;
- menus;
- downloads;
- connection indicators;
- VAN controls;
- permission prompts;
- takeover indicator;
- voice state;
- degraded-state UI.

The webpage viewport alone is remotely rendered.

Do not stream an Ubuntu desktop.
Do not stream a Chrome toolbar.
Do not wrap a generic VNC client as the product experience.

## ADR-RB-002 — WebRTC interactive transport

Interactive media and high-frequency owner input SHALL use WebRTC.

Preferred transport:

```text
S24 ⇄ direct UDP/ICE ⇄ Browser Stream Gateway
```

Fallback:

```text
S24 ⇄ TURN in same OCI region ⇄ Browser Stream Gateway
```

Last-resort fallback:

```text
TCP/TLS relay
```

The product SHALL expose transport mode in diagnostics because TURN/TCP fallback can materially alter perceived latency.

## ADR-RB-003 — H.264 first

Initial production video codec:

```text
H.264
4:2:0
60 FPS target
no B-frame dependency
short GOP
low-latency encoder settings
adaptive bitrate
hardware decode on Android where available
```

AV1/H.265 are future negotiated profiles after measured end-to-end latency proves they improve the VAN workload on the selected Oracle shape and S24 decoder.

Compression efficiency is secondary to total interaction latency.

## ADR-RB-004 — GStreamer media plane

The first production server implementation SHALL use a native media pipeline, not Python-frame copying.

Recommended implementation:

```text
Chromium surface
   ↓
X11 or Wayland capture
   ↓
GStreamer native pipeline
   ↓
x264 low-latency encoder
   ↓
RTP
   ↓
webrtcbin
   ↓
S24
```

Python may orchestrate signaling/session state around GStreamer, but Python SHALL NOT receive every raw video frame and re-encode it in Python-space.

## ADR-RB-005 — existing Browser Fabric owns browser authority

Remote interactive sessions extend `BrowserSessionBroker`.

They do not replace it.

An interactive session holds a profile lease. Agent child tasks act inside that session rather than independently competing for the same profile.

## ADR-RB-006 — separate profile lease from control lease

Two different exclusivity problems exist and MUST be represented separately.

### Profile lease
Existing `PageLease` / profile lease protects one browser profile from conflicting sessions.

### Control lease
New `BrowserControlLease` decides who may actively generate browser actions inside an already-open interactive session.

Control-holder values:

```text
OWNER
HERMES_DETERMINISTIC
HERMES_STAGEHAND
SYSTEM_RECOVERY
NONE
```

There may be many observers.
There is exactly one active control holder.

## ADR-RB-007 — owner touch wins

Intentional owner viewport input immediately preempts agent control.

Required transition:

```text
HERMES_STAGEHAND
      │
      │ first intentional owner DOWN/key event
      ▼
OWNER_PREEMPT_REQUESTED
      │
      ├── stop/pause semantic action selection
      ├── flush pending agent input
      ├── persist takeover event
      └── grant OWNER
```

Target: owner control hand-back visible within 100 ms after local touch processing, excluding a pathological network outage.

## ADR-RB-008 — event state is durable; pixels are not

High-frequency media, cursor motion and transient telemetry are not persisted in the VAN event ledger.

Durable state changes are.

Examples persisted:

- session created;
- profile attached;
- active URL changed;
- tab created/closed;
- control owner changed;
- agent takeover started/stopped;
- download created/completed;
- escalation raised;
- task verified/failed;
- stream degraded/recovered;
- session ended.

## ADR-RB-009 — no third source of truth

If data is already authoritative in an existing VAN service, Remote Browser references it.

Examples:

- authority → existing command/approval system;
- mission identity → Mission Core;
- browser policy → existing BrowserPolicyEngine/config;
- browser profile → BrowserSessionBroker;
- task execution → BrowserTaskService;
- evidence → existing BrowserEvidence;
- owner device identity → existing pairing/device token/HMAC;
- assistant state → existing event/visual-state mechanisms.

---


## ADR-RB-010 — VAN⇄Hermes is a logical session above transport

Android features SHALL bind to a `VanHermesSession`, never directly to a WebSocket, HTTP connection, tunnel URL or transport object.

The logical session survives:

- WebSocket disconnect;
- ingress endpoint switch;
- Wi-Fi→cellular handoff;
- HTTP/2 fallback;
- process-level transport recreation;
- short Gateway restart where replay state remains available.

Stable identity:

```text
van_session_id
session_epoch
device_id
owner_principal
```

Ephemeral identity:

```text
transport_connection_id
path_id
path_epoch
socket_id
ICE candidate pair
```

An ephemeral connection may die without changing the owner turn, command, browser context or response identity.

## ADR-RB-011 — application semantics are effectively-once, transport is at-least-once

Exactly-once delivery is not assumed at the network layer.

Commands may be retransmitted after ambiguous failure.

Safety is provided by:

```text
command_id
idempotency_key
payload_digest
server-side command record
action receipts
```

The same applies to downstream events:

```text
event_id
global seq
response_id
speech_segment_id
```

Duplicate transport delivery never becomes duplicate owner action or duplicate spoken output.

## ADR-RB-012 — make-before-break failover

When the active transport is degrading but still alive:

```text
detect degradation
   ↓
activate warm standby
   ↓
authenticate/resume same logical session
   ↓
reconcile event cursor + command states
   ↓
promote new path epoch
   ↓
retire old path
```

If the active transport dies abruptly, recovery becomes break-before-make, but the logical session still resumes.

## ADR-RB-013 — control, media and bulk data use separate continuity planes

VAN SHALL not force every byte through one connection.

```text
CONTROL / EVENT PLANE
    commands, responses, approvals, mission state, voice semantics

BROWSER MEDIA PLANE
    WebRTC video/audio + browser high-frequency input

BULK DATA PLANE
    uploads/downloads/artifacts; resumable transfer
```

Each plane can fail and recover independently.

## ADR-RB-014 — offline voice is a platform capability

Wake detection, acknowledgement, microphone capture, VAD, primary/fallback ASR, TTS, barge-in and critical status phrases SHALL work without public internet access on the S24.

Hermes is required for remote reasoning/web work, but public-internet voice services are not required to hear or speak.

## ADR-RB-015 — voice-originated questions default to spoken replies

Unless the owner explicitly requests silent/display-only behavior, an owner turn that starts through voice defaults to:

```text
display complete answer
+
speak a concise conversational answer
```

The speech representation is separate from the full display representation.

## ADR-RB-016 — local voice output never waits for a cloud audio file

Hermes returns semantic text/segments. The S24 synthesizes speech locally.

Cloud-generated speech may be an optional enhancement in a future approved capability, never the only production talk-back path.



## ADR-RB-017 — PR #48 retry/replay machinery is canonical on Android

`VanHermesSessionManager` SHALL compose:

```text
GatewayRetryPolicy
GatewayCircuitBreaker
ReplayTrigger
QueueReplayer
EventStream
PreferencesEventCursorStore
```

rather than duplicating their semantics.

A transport-specific retry policy may specialize a timeout/cadence but must delegate the fundamental retryability rules:

```text
transport failure → retry candidate
408/429/5xx      → retry candidate
401/403/404/409/410/422 → terminal answer
```

unless a new protocol gives a specifically documented reason otherwise.

## ADR-RB-018 — command-to-Mission link is already canonical

PR #48 establishes:

```text
accepted owner command
    ↓
exactly one Mission
```

Remote Browser does not create another Mission for the same owner request.

Interactive session/task activities attach to the command's existing Mission by reference.

A purely manual owner browsing session may have no Mission until the owner asks VAN to perform work.

## ADR-RB-019 — merged browser admin surfaces remain the parent UI

The existing Browser & Automation module already exposes:

```text
browser tasks
managed sessions/profiles
browser policy/capabilities
```

Remote Browser adds a first-class **Interactive Browser** entry to that module.

A dedicated full-screen Activity may still host the live viewport for performance/UX, but it is launched from and returns to the existing Browser module; it is not a parallel browser-management product.

## ADR-RB-020 — voice model adoption changes maturity, not history

PR #48 correctly records the concrete wake engine and local second-pass ASR as externally blocked.

Rev 1.3's hardened-offline-voice requirement is future work.

Implementation SHALL create an explicit owner-adoption decision for the concrete offline voice runtime/model bundle before changing:

```text
WakeWordEngine
WakePhraseVerifier
LocalSecondPassAsr
TTS backend
```

from externally blocked to implemented.

The current ledger is never edited retroactively to imply PR #48 shipped those artifacts.



## ADR-RB-021 — BrowserActivity is explicitly resizable

The live Browser activity SHALL declare:

```xml
android:resizeableActivity="true"
```

and SHALL NOT lock portrait/landscape orientation.

On Samsung this enables participation in native split-screen and pop-up/freeform modes when the OS exposes those modes.

Picture-in-picture is a separate Android feature and MUST NOT be enabled merely to imitate Samsung pop-up view.

## ADR-RB-022 — Browser media/session lifetime is independent of Activity recreation

A window resize, split-screen transition, pop-up conversion or orientation change must not rebuild the remote Chromium session or restart navigation.

The long-lived objects live outside Activity instance lifetime:

```text
BrowserSessionRepository
BrowserMediaSessionManager
VanPeerConnectionClient
control/session cursors
```

The Activity owns only:

```text
renderer attachment
window metrics
local chrome
IME surface
gesture input surface
```

If Android recreates `BrowserActivity`, the renderer detaches and reattaches to the same live session.

## ADR-RB-023 — Home-screen shortcuts contain no authority or credentials

A shortcut may contain only an opaque local `shortcut_id` plus non-sensitive presentation metadata.

It MUST NOT contain:

```text
Gateway token
device token
profile cookie
BrowserStreamGrant
TURN credential
Hermes token
raw authenticated session identifier
```

The shortcut resolves through VAN's locally protected shortcut registry, then normal device/session authentication occurs.

## ADR-RB-024 — Production connectivity is signed configuration, not owner-entered state

Release connectivity configuration is read-only at runtime.

`VanGatewayClient.baseUrl` mutable setter and `pairThisDevice(gatewayUrl, pairingToken)` remain development/migration tooling only.

The owner production build consumes an admitted signed connectivity manifest and an automatically provisioned hardware-bound identity.

## ADR-RB-025 — Device binding is proof-of-possession based

Every privileged Gateway/session request from the owner production build SHALL be bound to a non-exportable Android Keystore P-256 key.

A copied access token without proof-of-possession is insufficient.

The Gateway stores exactly one active production owner-device key fingerprint until an explicit administrative rebind occurs.

## ADR-RB-026 — Automatic provisioning is installer-driven, not UI-driven

The first production installation is provisioned by the deployment/install pipeline.

The owner does not type URLs, tokens, IDs or certificates.

The provisioning path is single-use, short-lived, hardware-attested, and permanently disabled after enrollment succeeds.

## ADR-RB-027 — Connectivity can rotate without owner editing settings

Endpoints and pins rotate through a Gateway-signed connectivity update.

The app trusts only manifests signed by the pinned VAN connectivity-config authority key.

A broken endpoint is repaired by signed configuration or a new owner build, never by asking the owner to type a server address.

# 5. REQUIRED DATA MODEL EXTENSIONS





Add these models under the existing Browser Fabric. They extend, rather than fork, current Browser Fabric authority.

Recommended files:

```text
backend/van_gateway/browser/
    interactive_models.py
    interactive_service.py
    stream_grants.py
    control_lease.py
```

Do not overload `BrowserTask` with interactive-session lifecycle.

## 5.1 InteractiveBrowserSession

```python
class InteractiveBrowserSession(BaseModel):
    session_id: str
    owner_device_id: str

    # MUST be one of the currently canonical aliases unless an owner-approved
    # profile-policy amendment has admitted another alias.
    profile_alias: str  # initially: public_research | authenticated_owner
    profile_lease_id: str

    state: InteractiveSessionState
    active_target_id: str | None
    active_url_digest: str | None

    viewport_width: int
    viewport_height: int
    device_scale_factor: float
    viewport_revision: int

    requested_fps: int
    negotiated_codec: str | None
    negotiated_transport: str | None

    control_holder: BrowserControlHolder
    control_lease_id: str | None
    control_generation: int

    created_at_ms: int
    connected_at_ms: int | None
    last_client_seen_at_ms: int | None
    last_profile_lease_renewed_at_ms: int | None
    suspended_at_ms: int | None
    expires_at_ms: int

    mission_id: str | None
    originating_command_id: str | None
```

## 5.2 Interactive session state machine

```text
REQUESTED
   ↓
AUTHORIZED
   ↓
ALLOCATING
   ↓
SIGNALING
   ↓
CONNECTING
   ↓
INTERACTIVE
   ├──────────────► AGENT_CONTROLLED
   │                     │
   │                     └──► INTERACTIVE
   │
   ├──────────────► RECONNECTING
   │                     │
   │                     ├──► INTERACTIVE
   │                     └──► SUSPENDED
   │
   ├──────────────► SUSPENDED
   │                     │
   │                     └──► CONNECTING
   │
   └──────────────► TERMINATING
                         ↓
                    TERMINATED

Any non-terminal state may enter FAILED.
FAILED is not VERIFIED_SUCCESS.
```

No UI may infer a completed browser task from `INTERACTIVE` or `TERMINATED`.

## 5.3 Profile lease evolution

The repository's existing `PageLease` is task-shaped and defaults to five minutes. Rev 1.1 explicitly evolves it into a backward-compatible profile lease.

Add:

```python
class ProfileLeaseHolderKind(str, Enum):
    TASK = "TASK"
    INTERACTIVE_SESSION = "INTERACTIVE_SESSION"

class PageLease(BaseModel):
    lease_id: str
    profile_alias: str

    holder_kind: ProfileLeaseHolderKind
    holder_id: str

    # compatibility field for existing task consumers only
    task_id: str | None = None

    acquired_at_ms: int
    expires_at_ms: int
    generation: int
```

Existing task acquisition maps:

```text
holder_kind = TASK
holder_id = task_id
task_id = task_id
```

Interactive acquisition maps:

```text
holder_kind = INTERACTIVE_SESSION
holder_id = session_id
task_id = null
```

### Renewal contract

Interactive profile leases are renewable.

Normative timing:

```text
lease TTL:                 120 seconds
client/runtime heartbeat:   20 seconds
renew when remaining:       <80 seconds
expiry grace for CLEANUP/RECONNECT ONLY: 30 seconds
```

The Gateway remains the profile-lease authority.

If renewal fails and the lease expires:

**The 30-second grace is cleanup/reconnect-only. It never extends actuation authority.**

1. Browser Stream Runtime MUST stop accepting owner or agent input immediately at the expiry instant.
2. Session enters `BROWSER_PROFILE_LEASE_EXPIRED`.
3. Video may remain frozen/read-only only during bounded cleanup/reconnect grace.
4. No Stagehand/Browser Harness action may run.
5. A new valid lease must be acquired before actuation resumes.
6. If reacquisition fails, the session terminates.

A Hermes outage does not itself stop renewal if the Gateway remains healthy. A Gateway outage cannot mint or renew authority.

Required methods:

```text
acquire_lease(...)
renew_lease(lease_id, holder_id, generation, ttl_seconds)
release_lease(...)
assert_lease_active(...)
```

Renewal increments neither control generation nor browser task authority; it only extends profile exclusivity.

## 5.4 BrowserControlLease

Profile ownership and actuation authority are separate.

```python
class BrowserControlLease(BaseModel):
    control_lease_id: str
    session_id: str
    holder: BrowserControlHolder
    issued_for: str
    issued_at_ms: int
    expires_at_ms: int
    generation: int
    revoked_at_ms: int | None
```

Every actuation packet carries:

```text
session_id
control_lease_id
control_generation
```

A stale generation is rejected server-side.

## 5.5 BrowserStreamGrant

After normal paired-device authentication the Gateway mints a short-lived stream connection grant.

The grant uses a **dedicated P-256 ECDSA gateway→stream-runtime signing key**. This reuses VAN's existing asymmetric algorithm family while keeping the key plane independent from owner approval keys.

Recommended claims:

```json
{
  "version": 1,
  "grant_id": "bsg_...",
  "kid": "browser-stream-signing-2026-01",
  "session_id": "ibs_...",
  "device_id": "android-...",
  "profile_alias": "authenticated_owner",
  "aud": "van-browser-stream-runtime",
  "scope": [
    "webrtc.signal",
    "browser.view",
    "browser.owner_input"
  ],
  "issued_at_ms": 0,
  "expires_at_ms": 0,
  "nonce": "...",
  "max_width": 1080,
  "max_height": 2400,
  "max_fps": 60
}
```

### Signing-key lifecycle

Phase 0 SHALL define:

```text
private key owner: VAN Gateway runtime identity
private key storage: 0600 root/gateway-readable secret file or approved secret store
public verifier: Browser Stream Runtime only
format: PEM P-256 public key
token format: compact JWS ES256 or equivalent deterministic envelope
kid: mandatory
rotation overlap: current + immediately previous verifier
old key rejection: mandatory after overlap window
```

Provisioning to the dedicated stream host is an administrative deployment action; the private key never leaves the Gateway host.

Rotation tests are mandatory.

## 5.6 Database migration — schema version 27

Current schema version at the PR #48 merged baseline is 26.

Rev 1.3 uses the next semantic migration **27** at the inspected baseline. If main advances, use the next unused migration number.

Add:

```text
browser_interactive_sessions
browser_control_leases
browser_stream_grants
browser_session_targets
browser_session_events
browser_downloads
```

Do not duplicate:

```text
browser_profiles
browser_tasks
browser_evidence
```

### Event-store extension

Migration 27 also extends the existing `events` table rather than claiming a new incompatible realtime store.

Add nullable/backfilled columns:

```text
event_id TEXT
target_device_id TEXT
occurred_at_ms INTEGER
mission_id TEXT
command_id TEXT
correlation_id TEXT
```

Create:

```text
UNIQUE INDEX idx_events_event_id ON events(event_id) WHERE event_id IS NOT NULL
INDEX idx_events_device_seq ON events(target_device_id, seq)
INDEX idx_events_mission_seq ON events(mission_id, seq)
```

Existing `seq INTEGER PRIMARY KEY AUTOINCREMENT` remains the globally monotonic cursor.

Realtime semantics are therefore:

```text
global monotonically increasing seq
+
device-scoped visibility/filtering
+
per-device cursor
+
event_id deduplication
```

Per-device sequences are NOT introduced.

`EventBus.replay(device_id, after_seq)` MUST filter to:

```text
target_device_id IS NULL OR target_device_id = :device_id
```

and continue updating the existing `event_cursors` table.

Foreign-key/reference relationships tie interactive sessions to existing profiles, missions and browser tasks without moving those authorities.



### PR #48 compatibility requirements for the event migration

The existing `events` table and Android `EventStream` are live production contracts.

Migration 27 MUST be additive and backward compatible.

For pre-migration rows:

```text
event_id        = deterministic legacy id derived from seq, e.g. "legacy-event:<seq>"
occurred_at_ms  = created_at_unix * 1000
target_device_id = NULL   # broadcast under current semantics
```

Do not rewrite `seq`.

`EventBus.publish(...)` becomes an additive API:

```python
publish(
    event_type,
    payload,
    *,
    target_device_id=None,
    event_id=None,
    mission_id=None,
    command_id=None,
    correlation_id=None,
    occurred_at_ms=None,
)
```

Existing callers that pass only `(event_type, payload)` continue to work.

Android's existing `EventRecord` and `EventStream.applyPage(...)` evolve rather than being replaced.

The client retains:

```text
PreferencesEventCursorStore
global seq cursor
MAX_RETAINED
catch-up paging
failure backoff
runtime-envelope cadence
```

and gains optional:

```text
event_id
occurred_at_ms
correlation_id
targeting metadata
```

Deduplication prefers `event_id` when present and falls back to `seq` for legacy records.



## 5.7 Owner-device binding records

If migration 27 has not yet shipped, include these in the same Remote Browser migration. If it has shipped, use the next unused schema migration.

Add:

```text
owner_device_bindings
device_attestation_events
connectivity_config_versions
```

Recommended shape:

```sql
CREATE TABLE owner_device_bindings (
  binding_id TEXT PRIMARY KEY,
  owner_principal_id TEXT NOT NULL,
  device_id TEXT NOT NULL UNIQUE,
  device_key_fingerprint TEXT NOT NULL UNIQUE,
  public_key_pem TEXT NOT NULL,
  key_security_level TEXT NOT NULL,
  app_package_name TEXT NOT NULL,
  app_signing_cert_sha256 TEXT NOT NULL,
  attestation_root_fingerprint TEXT,
  verified_boot_state TEXT,
  os_version TEXT,
  os_patch_level TEXT,
  status TEXT NOT NULL,
  bound_at_ms INTEGER NOT NULL,
  last_proof_at_ms INTEGER,
  revoked_at_ms INTEGER,
  revoke_reason TEXT
);

CREATE UNIQUE INDEX uq_active_owner_device
ON owner_device_bindings(owner_principal_id)
WHERE status = 'ACTIVE';
```

The unique active owner-device constraint is a server-side guarantee.

## 5.8 Browser shortcut registry

Android stores shortcut records locally in encrypted/private storage.

Suggested model:

```text
BrowserShortcutRecord {
    shortcut_id
    canonical_url
    title
    favicon_digest_or_ref
    profile_alias
    created_at_ms
    last_opened_at_ms
    sensitivity
}
```

The launcher shortcut itself contains only:

```text
shortcut_id
display label
safe icon
explicit VAN activity intent
```

If the shortcut record is missing, revoked or device binding is invalid, the shortcut does not navigate.

# 6. SESSION CREATION PROTOCOL


## 6.1 Android request

New endpoint:

```text
POST /v1/browser/interactive-sessions
```

Normal existing Android auth is required:

```text
X-Van-Ingress-Token
X-Van-Device-Token
```

Initial allowed profile aliases are the ones that actually exist in `config/browser/profiles.yaml`:

```text
public_research
authenticated_owner
```

Example:

```json
{
  "profile_alias": "authenticated_owner",
  "viewport": {
    "width": 1080,
    "height": 2016,
    "device_scale_factor": 1.0
  },
  "media": {
    "preferred_video": ["H264"],
    "preferred_audio": ["OPUS"],
    "max_fps": 60
  },
  "mission_id": null,
  "idempotency_key": "..."
}
```

Any future alias such as `dial-development` or `trading-readonly` requires an explicit owner-approved amendment to `config/browser/profiles.yaml`. An implementation agent may not invent profile aliases.

## 6.2 Gateway work

The Gateway SHALL:

1. authenticate ingress;
2. authenticate the exact paired device;
3. verify the single approved owner device may launch Remote Browser;
4. resolve `profile_alias` through the current BrowserPolicyEngine;
5. acquire a renewable profile lease using `holder_kind=INTERACTIVE_SESSION`;
6. create `InteractiveBrowserSession`;
7. create initial OWNER control lease;
8. mint one-time `BrowserStreamGrant`;
9. register a durable session-created event;
10. if `mission_id` exists, call the new session-specific Mission binder;
11. return stream signaling information.

## 6.3 Response

```json
{
  "session_id": "ibs_...",
  "state": "AUTHORIZED",
  "stream_grant": "...",
  "signal_url": "https://<approved-stream-host>/rtc",
  "ice_servers": [
    {
      "urls": ["stun:..."]
    },
    {
      "urls": ["turn:..."],
      "username": "...",
      "credential": "..."
    }
  ],
  "expires_at_ms": 0
}
```

TURN credentials are ephemeral.

## 6.4 Signaling

Android talks directly to the approved Browser Stream Runtime for SDP/ICE signaling using the one-time grant.

The VAN Gateway does not proxy the steady-state media path.

The production `signal_url` MUST NOT point at private-only `van-trading-core`.

# 7. WEBRTC CHANNEL CONTRACT


One PeerConnection may carry video, audio and multiple data channels. Rev 1.1 does **not** assume ordering between separate SCTP streams.

## 7.1 Video

```text
direction: server → Android
codec: H.264 first
target: 60 FPS
```

## 7.2 Audio

```text
direction: server → Android
codec: Opus
sample rate: 48 kHz
```

## 7.3 FAST_INPUT

```text
channel label: van.fast-input.v1
ordered: false
maxRetransmits: 0
```

Use for:

- pointer/touch MOVE;
- scroll deltas;
- gesture velocity updates;
- transient hover/stylus movement;
- a **duplicate low-latency copy** of gesture DOWN/UP/CANCEL edge events.

FAST_INPUT has its own sequence space:

```text
fast_seq
```

Packets may be lost or reordered.

## 7.4 RELIABLE_INPUT

```text
channel label: van.reliable-input.v1
ordered: true
reliable: true
```

Use for canonical:

- gesture DOWN;
- gesture UP/CANCEL;
- key down/up;
- committed text;
- IME composition;
- URL navigation;
- back/forward/reload;
- tab actions;
- explicit clipboard actions;
- file chooser decisions;
- owner takeover requests.

RELIABLE_INPUT has a separate sequence space:

```text
reliable_seq
```

Gap detection applies only to the reliable sequence.

## 7.5 CONTROL

```text
channel label: van.browser-control.v1
ordered: true
reliable: true
```

Use for:

- target/tab state;
- viewport resize and `viewport.ack`;
- focus/input-context changes;
- active URL metadata;
- stream mode;
- agent/owner control transitions;
- download metadata;
- heartbeat;
- quality negotiation;
- profile-lease health.

## 7.6 TELEMETRY

Telemetry never blocks input.

Examples:

```text
server_capture_ms
server_encode_ms
browser_cpu
encoder_cpu
rtt
jitter
packet_loss
frames_encoded
frames_dropped
current_bitrate
```

# 8. INPUT WIRE FORMAT


Use a deterministic binary schema: protobuf or explicitly-versioned CBOR.

Do not send ad-hoc JSON for pointer motion.

## 8.1 Common actuation envelope

```text
InputAuthority {
  protocol_version
  session_id
  control_lease_id
  control_generation
  viewport_revision
}
```

Old/unacknowledged viewport revisions are **rejected**. Rev 1.1 does not allow coordinate transformation across Chromium reflow.

The Android client withholds actuation until `viewport.ack(revision)` for the currently displayed layout.

## 8.2 Gesture identity

Every pointer gesture receives:

```text
gesture_id
pointer_id
gesture_epoch
```

`gesture_epoch` is monotonically increasing per pointer ID.

Canonical logical invariant remains:

```text
DOWN -> MOVE* -> UP/CANCEL
```

but it is enforced by a server state machine, **not by cross-channel arrival order**.

## 8.3 Edge duplication

DOWN/UP/CANCEL are sent twice:

```text
FAST_INPUT      immediate best-effort edge copy
RELIABLE_INPUT  canonical ordered edge copy
```

Both copies carry the same:

```text
gesture_id
gesture_epoch
edge_id
```

The server de-duplicates by `(session_id, gesture_id, edge_id)`.

This provides immediate interaction under healthy networks while reliable delivery heals edge loss.

## 8.4 Server pointer state machine

For each `(session_id, pointer_id)`:

```text
CLOSED
  └─ valid DOWN/implicit fast-edge ─► OPEN(gesture_epoch)

OPEN
  ├─ MOVE with same epoch ─────────► OPEN
  ├─ UP/CANCEL same epoch ─────────► CLOSED
  └─ newer DOWN epoch ─────────────► CANCEL old + OPEN new
```

Rules:

- a MOVE for an unknown/closed gesture is buffered for at most one tiny bounded window (target ≤8 ms) awaiting its duplicated DOWN; otherwise it is dropped;
- a MOVE from an older epoch is dropped;
- UP/CANCEL for an unknown old epoch is idempotently ignored;
- canonical reliable DOWN/UP confirms/heals fast edges;
- after a gesture timeout, server synthesizes CANCEL;
- no permanently-pressed pointer is possible.

## 8.5 Sequence spaces

Do not use one sequence number across reliable and unreliable channels.

Use:

```text
fast_seq       — informational/stale-discard only
reliable_seq   — ordered gap detection/recovery
motion_seq     — per gesture/pointer for MOVE stale discard
```

Legitimately dropped FAST_INPUT packets do not trigger protocol-gap recovery.

## 8.6 Coordinates

Transmit normalized coordinates:

```text
x = 0..65535
y = 0..65535
```

Server maps them only against the acknowledged `viewport_revision`.

## 8.7 MotionEvent handling

The S24 may provide historical touch samples above the display frame rate.

Android SHALL:

- retain MotionEvent historical samples for velocity/fling estimation;
- coalesce outbound MOVE state to at most one packet per display frame under normal operation;
- preserve final velocity information;
- not discard history before velocity calculation.

## 8.8 CDP injection

Owner input is translated directly through the deterministic browser-control layer using primitives such as:

```text
Input.dispatchTouchEvent
Input.dispatchMouseEvent
Input.insertText
Input.imeSetComposition
Input.synthesizeScrollGesture
Input.synthesizePinchGesture
```

Stagehand never sits in this loop.

# 9. ANDROID IMPLEMENTATION




Create a dedicated package:

```text
android/app/src/main/java/com/dial/van/browser/
```

Recommended structure:

```text
browser/
    BrowserActivity.kt
    BrowserViewModel.kt
    BrowserSessionRepository.kt
    BrowserModels.kt
    BrowserRoute.kt

    ui/
        BrowserScreen.kt
        BrowserChrome.kt
        BrowserTabStrip.kt
        BrowserAddressBar.kt
        BrowserDownloadsPanel.kt
        BrowserConnectionBadge.kt
        BrowserVanPanel.kt

    rtc/
        VanPeerConnectionClient.kt
        VanWebRtcFactory.kt
        BrowserSignalClient.kt
        BrowserIcePolicy.kt
        BrowserVideoSink.kt
        BrowserAudioSink.kt

    input/
        RemoteBrowserViewport.kt
        BrowserInputRouter.kt
        GestureState.kt
        CoordinateMapper.kt
        StylusMapper.kt

    ime/
        RemoteInputConnection.kt
        BrowserImeBridge.kt
        RemoteInputContext.kt

    control/
        BrowserControlLeaseClient.kt
        HumanTakeoverController.kt

    telemetry/
        BrowserTelemetryCollector.kt
        BrowserQualityController.kt

    download/
        BrowserDownloadRepository.kt

    upload/
        BrowserUploadCoordinator.kt
```

## 9.1 Existing Browser module + live viewport navigation

PR #48 already ships the Browser & Automation owner surface under:

```text
android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt
```

It already exposes:

```text
tasks
sessions/profiles
policy/capabilities
evidence drill-down
```

Rev 1.3 adds:

```text
Interactive Browser / Live Browser
```

to that existing module.

`BrowserActivity` may be introduced as the dedicated full-screen renderer because the live WebRTC viewport has different lifecycle/performance requirements from a dashboard card, but:

- it is launched from the existing Browser module;
- it shares the same BrowserSessionRepository/state;
- it does not duplicate tasks/profiles/policy pages;
- it returns authoritative session state to the existing Browser surface.

Additional entry points may include:

- floating VAN expanded rail;
- voice command producing a browser-visible result;
- notification/deep link from a browser result.

Kotlin reachability must prove every new Activity/controller is reachable from a manifest/root entry point.

## 9.2 Native composition

Use Compose for chrome.

The remote viewport itself SHOULD be a dedicated Android `View` container holding the WebRTC renderer and an input-capture overlay.

Recommended hierarchy:

```text
Compose
└── AndroidView(RemoteBrowserViewport)
       ├── SurfaceViewRenderer
       └── InputCaptureView
```

This preserves high-fidelity `MotionEvent` information while keeping the surrounding application Compose-native.

## 9.3 Rendering

Preferred path:

```text
RTP
 ↓
native WebRTC
 ↓
Android hardware decoder where supported
 ↓
VideoFrame
 ↓
SurfaceViewRenderer / EGL
 ↓
SurfaceFlinger
 ↓
display
```

Do not decode the stream inside a WebView.

Do not render every video frame into a Compose bitmap.

Do not round-trip decoded frames through Kotlin byte arrays.

## 9.4 Client frame queue policy

The browser is interactive, not cinema playback.

When delayed frames accumulate, prefer freshness.

The implementation SHALL:

- keep receiver/jitter buffering minimal but stable;
- avoid an application-level deep frame queue;
- drop obsolete frames rather than display the page hundreds of milliseconds late;
- record dropped-frame metrics.

## 9.5 S24 production binding

The production owner build is cryptographically bound to the enrolled hardware-backed owner-device key described in §31.9–§31.14.

Canonical rule:

```text
device model / Build.MODEL
    = diagnostic only

hardware-backed key proof-of-possession
    + app signing identity
    + Gateway single-active-owner-device binding
    = authorization
```

Existing paired-device access tokens remain transitional/session credentials but are not sufficient by themselves for privileged owner capability.

A copied APK, copied token set or another S24 Ultra cannot obtain owner capability without the enrolled device private key.

# 10. NATIVE KEYBOARD / IME

A browser that streams a remote keyboard does not feel native.

The Android IME MUST remain local.

## 10.1 Focus protocol

Browser Runtime detects editable focus state and sends:

```json
{
  "type": "input_context.changed",
  "target_id": "...",
  "editable": true,
  "input_type": "email",
  "password": false,
  "multiline": false,
  "selection_start": 4,
  "selection_end": 4,
  "revision": 19
}
```

Android opens the appropriate IME.

## 10.2 Android input connection

`RemoteBrowserViewport` SHALL expose an `InputConnection` when remote input context is editable.

Support:

- commitText;
- setComposingText;
- finishComposingText;
- deleteSurroundingText;
- setSelection;
- editor actions;
- enter/tab/backspace;
- Unicode.

## 10.3 Password fields

When `password=true`:

- never persist typed text;
- never log it;
- disable screenshots in sensitive native overlays where appropriate;
- mark input packets sensitive;
- server input router never emits password content into task evidence;
- clipboard paste requires explicit owner action.

The current Browser Security Policy continues to prohibit browser secrets from entering Hermes prompts or evidence.

---

# 11. SCROLLING AND GESTURES


Scrolling is the most perceptually sensitive operation.

## 11.1 Required first-pass behavior

The first production pass SHALL provide correct remote scrolling before speculative prediction.

Required:

- MotionEvent historical samples retained for velocity/fling estimation, with outbound MOVE state coalesced to at most one packet per display frame under normal operation;
- MOVE coalescing per display frame;
- FAST_INPUT channel;
- server stale-MOVE discard;
- direct CDP touch/scroll injection;
- fling velocity sent once on release;
- no per-event Hermes/Stagehand hop.

## 11.2 Speculative local scroll

Client-side texture translation MAY be added after authoritative scrolling is stable.

If implemented, it must:

- be explicitly feature-gated;
- disable for nested scroll containers until reliable scroll-target metadata exists;
- reconcile without visible jump;
- immediately abandon prediction when remote frames disagree.

Do not ship fake smoothness that breaks sticky headers, nested scroll areas, maps, or canvases.

---

# 12. VIEWPORT, ORIENTATION AND SCALE



## 12.1 Canonical viewport

Android computes the content viewport after:

- status/navigation bars;
- display cutouts;
- VAN browser chrome;
- keyboard inset.

It sends:

```text
viewport_width
viewport_height
viewport_revision
orientation
device_scale_factor
```

## 12.2 Resize sequence

```text
Android layout changes
      ↓
150 ms debounce for orientation/inset storm
      ↓
viewport.resize
      ↓
Browser Runtime resizes Chromium target/window
      ↓
encoder/capture caps update
      ↓
viewport.ack(revision)
```

Android keeps the old frame scaled/letterboxed until the matching revision arrives.

Input for an unacknowledged new viewport is withheld. Rev 1.5 forbids coordinate transformation across an unacknowledged Chromium reflow.

---



## 12.3 Continuous window resize protocol

Samsung pop-up/freeform windows can be resized continuously.

Do not renegotiate Chromium on every raw pixel callback.

Use two stages:

```text
LOCAL RESIZE
  immediately scale/letterbox current decoded frame to new Android content rect
  continue drawing chrome at native size

REMOTE RESIZE
  coalesce window-size changes
  send viewport candidate at bounded cadence
```

Recommended active drag cadence:

```text
max remote resize messages: 10 Hz
stability debounce:          80–120 ms
final settle message:        <=250 ms after final bounds
```

## 12.4 Atomic viewport revision

Each candidate contains:

```text
viewport_revision
android_window_width_px
android_window_height_px
content_width_px
content_height_px
density
font_scale
display_rotation
window_mode
system_insets
browser_chrome_insets
```

`window_mode` is informational:

```text
FULLSCREEN
SPLIT
FREEFORM_POPUP
DESKTOP_FREEFORM
UNKNOWN_RESIZABLE
```

Never authorize behavior based solely on this label.

Sequence:

```text
Android sends revision N
    ↓
server resizes Chromium/capture
    ↓
server sends viewport.ack(N)
    ↓
first frame for N identified
    ↓
Android atomically swaps:
    render transform
    touch transform
    IME geometry
```

Until that point, touch continues to map against the last acknowledged viewport.

## 12.5 No click-offset window

The implementation must prove that resizing cannot produce:

```text
visible button at x1,y1
tap sent to stale Chromium coordinate x2,y2
```

Touch input for a newly-sized surface is either:

- temporarily mapped through the old acknowledged content rect;
- or withheld for the tiny transition window.

It is never guessed.

## 12.6 Window-state restoration

Persist:

```text
active session id/reference
active target id
tab selection
address-bar edit state
scroll/session context reference
last acknowledged viewport revision
```

Do not persist ephemeral WebRTC secrets.

Activity recreation restores presentation from repository/session truth.

# 13. SERVER BROWSER RUNTIME

Rev 1.5 locks one production topology.

## 13.1 Production topology — dual-homed Browser Stream Host

```text
PUBLIC / OWNER MEDIA SIDE
S24
  │
  │ HTTPS/WSS signaling
  │ WebRTC UDP/media
  ▼
┌──────────────────────────────────────────────┐
│ DEDICATED BROWSER STREAM HOST                │
│                                              │
│ public interface:                            │
│   signaling / ICE / WebRTC / TURN as needed │
│                                              │
│ private VCN interface:                       │
│   Browser Control Agent mTLS RPC             │
│   Gateway/session control                    │
│   observability/control health               │
│                                              │
│ local only:                                  │
│   Chromium                                   │
│   CDP                                        │
│   Wayland/PipeWire capture                   │
│   encoder                                    │
└───────────────┬──────────────────────────────┘
                │ private VCN only
                │ narrow mTLS control API
                ▼
┌──────────────────────────────────────────────┐
│ PRIVATE TRADING CORE                         │
│                                              │
│ Stagehand                                    │
│ Playwright / Browser Harness                 │
│ Browser Fabric task orchestration            │
│ profiles / domain-policy authority           │
└──────────────────────────────────────────────┘
```

This is not optional topology text.

### Why dual-homed

The Stream Host must simultaneously:

- accept owner media/signaling from the internet;
- expose **no public CDP**;
- allow the existing private Browser Fabric to control the same visible Chromium;
- avoid moving Stagehand/Harness authority onto the public media host.

Therefore it has:

```text
public media/signaling path
+
private VCN control path
```

## 13.2 Browser Control Agent

Raw CDP remains bound to loopback on the Stream Host.

A small privileged-by-capability, unprivileged-by-OS service runs locally:

```text
van-browser-control-agent
```

It is the **only** cross-host bridge to Chromium.

It exposes a narrow private API such as:

```text
attach(session_id, target_id, control_lease)
navigate(...)
dispatch_input(...)
query_dom(...)
query_accessibility(...)
observe_navigation(...)
observe_download(...)
capture_evidence(...)
```

It does **not** expose:

```text
arbitrary shell
raw public CDP websocket
filesystem root
Docker socket
unbounded JavaScript execution primitive
```

Stagehand/Browser Harness on Trading Core uses this agent over mTLS on the VCN.

The agent validates:

```text
session_id
control lease
control generation
task scope
step budget
caller service identity
```

before any actuation.

## 13.3 Service-to-service authentication

Private Browser Control RPC requires:

```text
mTLS
+
scoped service credential
+
session/task capability
```

Credentials are independent from:

```text
owner device key
device HMAC
BrowserStreamGrant
Gateway root/admin token
```

Rotation follows the existing control-credential discipline.

## 13.4 Canonical profile configuration

Existing `config/browser/profiles.yaml` remains authoritative.

Initial aliases:

```text
public_research
authenticated_owner
```

The profile authority stays with Browser Fabric on Trading Core.

For the Stream Host, the session broker supplies only the resolved profile/session capability needed to mount/use the correct profile storage path.

No implementation agent invents a new profile registry.

## 13.5 Profile storage placement

Because Chromium executes on the Stream Host, persistent browser-profile bytes must be accessible there without duplicating profile authority.

Choose one deployment implementation during Phase 0:

```text
A. encrypted profile volume attached/mounted only to Stream Host,
   with Trading Core storing metadata/leases only; PREFERRED

or

B. private encrypted network volume with exclusive lease enforcement
```

Do not keep active Chromium profile files only on Trading Core while Chromium runs elsewhere.

The selected storage implementation must preserve:

```text
single active profile lease
0700-equivalent access
encryption at rest
no public export
backup/restore policy
```

## 13.6 Runtime users

Create dedicated unprivileged identities:

```text
vanbrowser
van-browser-control
```

Do not run Chromium as root.
Do not run the media service as Hermes.
Do not expose a Docker socket.

## 13.7 Display server and capture contract

Phase 1 selects one concrete stack.

Preferred:

```text
headless Wayland compositor
    ↓
PipeWire capture
    ↓
DMA-BUF / low-copy path where supported
    ↓
GStreamer
```

Capture latency and encode latency are measured separately.

## 13.8 Chromium process

Chromium launches with:

- CDP loopback-only;
- explicit resolved profile directory;
- sandbox enabled;
- no arbitrary extension loading;
- deterministic viewport;
- crash supervision;
- pinned Chromium build matching certified Playwright/CDP contract.

## 13.9 Session isolation

Each session receives:

```text
session runtime dir
display/socket
signaling state
resolved profile capability
bounded resource cgroup
```

No session receives root credentials, Gateway signing keys or owner-device private material.

# 14. MEDIA PIPELINE


## 14.1 Production target

The product target remains:

```text
viewport width: up to 1080
target FPS: 60
codec: H.264
stationary text: high quality
```

The chosen dedicated production host must be benchmarked against this target.

## 14.2 A1 path-proof target

The current private `van-trading-core` A1 shape is not the production placement.

If used for internal proof only:

```text
720p
30–45 FPS
software H.264
explicitly labelled PATH_PROOF_NOT_PRODUCT_TARGET
```

Failure or success on this proof does not certify production.

## 14.3 Encoder preference

For the production stream host prefer a shape with a supported hardware H.264 encoder if available and operationally justified.

If software x264 is used, use a measured low-latency profile such as:

```text
tune=zerolatency
bframes=0
minimal lookahead
short keyframe interval
RTP-friendly packetization
no deep frame queue
```

Exact options are certified by measured end-to-end latency and text quality.

## 14.4 Text quality

Web browsing is text-heavy.

Quality control favors:

- sharp stationary text;
- 60 FPS responsiveness during scrolling;
- rapid recovery to high quality after movement stops.

## 14.5 Audio

Chromium audio routes to a dedicated virtual sink and then Opus/WebRTC.

When VAN speaks:

- browser audio may duck;
- owner policy may choose duck/pause;
- local VAN TTS retains clear priority.

# 15. NETWORK AND ICE DESIGN


## 15.1 Production reachability requirement

The Browser Stream Host MUST have an owner-approved public reachability design.

Preferred ICE order:

1. direct public UDP candidate to dedicated Browser Stream Host;
2. regional TURN/UDP;
3. TURN/TCP/TLS only as a last resort.

The private `van-trading-core` VM is not a candidate.

## 15.2 TURN placement

TURN must be reachable from the S24 and near the Browser Stream Host.

A TURN service on a private-only VCN is invalid.

## 15.3 OCI security rules

Expose only the dedicated stream host's required ingress:

```text
HTTPS/WSS signaling
STUN/TURN
bounded UDP media range
```

CDP is never public.

Private control connections to Gateway/Hermes remain on VCN/internal paths.

## 15.4 Browser egress isolation

Remote Chromium needs public internet but not arbitrary access to VAN's internal control network.

Always block at minimum:

```text
127.0.0.0/8
169.254.0.0/16
OCI instance metadata
link-local ranges
unapproved RFC1918/private targets
localhost aliases
file:// and privileged chrome:// where not explicitly required
```

DNS rebinding protections are mandatory.

## 15.5 Deterministic canary origin

Deterministic browser canaries MUST NOT be served on localhost.

Provide a distinct canary origin such as:

```text
https://browser-canary.<controlled-domain>/
```

or an explicitly allowlisted VCN test origin reachable only by the Browser Runtime.

The canary origin receives its own narrow policy entry.

The SSRF boundary is not weakened to make tests pass.

# 16. OWNER MANUAL BROWSING POLICY

The current security model uses domain/capability controls for browser workers.

General owner web browsing requires a deliberate policy distinction.

Add an owner-approved policy proposal for:

```text
OWNER_INTERACTIVE_BROWSER
```

Its meaning:

- the authenticated owner may manually navigate ordinary public HTTP/HTTPS pages;
- this does not grant autonomous Stagehand authority;
- internal/private/metadata addresses remain blocked;
- page content remains UNTRUSTED_EXTERNAL;
- owner manual typing does not create standing automation authority;
- payments remain A4 per occurrence;
- trading authority remains behind VATI;
- automatic mutation by agents still obeys current browser domain/action policy.

Do not silently relax `config/browser/domains.yaml`.

If Project Truth requires amendment, create the decision artifact and leave it `PENDING_OWNER` until the owner signs it.

---

# 17. BROWSER TABS AND NATIVE CHROME


The UI must not pretend to manage tabs locally while Chromium owns different target state.

## 17.1 Tab source of truth

Chromium target state is authoritative.

Browser Runtime listens to CDP target events.

Android receives:

```text
tab.created
tab.updated
tab.activated
tab.closed
```

Each tab model:

```text
target_id
title
url
url_digest
favicon_ref
loading
can_go_back
can_go_forward
security_state
```

## 17.2 Address bar

When owner enters text:

- classify local text as URL vs search query;
- send a navigation command through RELIABLE_INPUT;
- Browser Runtime resolves the configured search engine if it is a query;
- navigation happens on Oracle.

Search suggestions that require network access may be performed by the Oracle runtime or omitted initially; do not leak typed owner input to a suggestion provider without policy.

## 17.3 Loading state

Native loading indicator is driven from CDP lifecycle/network events, not guessed from video frames.

---



## 17.4 Normal browser menu

At minimum expose native owner actions:

```text
New tab
Close tab
Reload / stop
Back
Forward
Share page
Copy page link
Find in page
Add to Home screen
Downloads
Open Browser & Automation
```

Where a capability is not yet live, omit it rather than showing inert controls.

## 17.5 Share/open interoperability

Sharing a page exports only the current safe canonical URL/title through Android share intents.

No cookies/profile state/stream tokens leave VAN.

Receiving an external http/https VIEW intent is treated as **untrusted navigation input, not an owner command**:

- it opens the address in a session the owner can see;
- it opens in the *public* profile, never the authenticated one — a link from a messaging app opening in the browser that holds the owner's logged-in cookies is the whole of the attack;
- it creates no Mission and carries no authority;
- only `http` and `https` are accepted, and a second scheme anywhere in the address is refused: that redirect belongs to the sending app, and an https wrapper does not make VAN carry it.

(Rev 1.5 as issued cross-referenced a "§9.14"; the document contains no such section — section 9 ends at 9.5 — so the rule is stated here in full rather than by reference. Recorded as §0F.6o.)

## 17.6 System back behavior

Android back follows this order:

```text
close transient browser panel/dialog
else close address-bar edit state
else Chromium canGoBack → browser back
else Activity/task back
```

Do not make the system Back gesture unexpectedly close the whole browser while page history exists.

# 18. DOWNLOADS

Downloads occur on Oracle first.

## 18.1 Download state

```text
CREATED
IN_PROGRESS
COMPLETED
FAILED
QUARANTINED
DELETED
```

Metadata:

```text
download_id
session_id
target_id
filename
mime_type
size_bytes
sha256
source_url_digest
local_server_ref
created_at
completed_at
```

## 18.2 Security

Downloaded executable/script/archive content is not automatically executed.

Recommended pipeline:

```text
download
 ↓
quarantine directory
 ↓
hash
 ↓
MIME validation
 ↓
optional malware scan
 ↓
owner-visible completed state
```

## 18.3 Owner actions

Native actions:

```text
Open in VAN
Analyse
Save on Oracle
Send to phone
Add to VEKL
Delete
```

Each action has its own authority/policy.

A 500 MB download should not automatically consume phone bandwidth.

---

# 19. PHONE-TO-REMOTE FILE UPLOAD

When a web page opens a file chooser:

1. Browser Runtime emits `file_chooser.requested`.
2. VAN opens Android `ACTION_OPEN_DOCUMENT`.
3. Owner selects file.
4. VAN transfers bytes through an authenticated upload endpoint/channel.
5. Gateway/runtime stores an ephemeral object.
6. Runtime resolves it to a local path.
7. Playwright/CDP attaches it to the chooser.
8. Ephemeral copy expires/deletes after bounded TTL unless owner explicitly retains it.

The file content must not be logged or injected into Hermes unless the owner separately asks VAN to analyse it.

---

# 20. REAL-TIME VAN/HERMES EVENT CHANNEL




Rev 1.2 replaces the idea of “the realtime socket” with a **durable VAN⇄Hermes logical session**.

The Android-facing network authority still terminates at VAN Gateway. Android does not bypass the Gateway and connect directly to internal Hermes execution APIs.

```text
Android VAN
   │
   ▼
VanHermesSessionManager
   │
   ├─ Primary realtime carrier
   ├─ Protocol fallback carrier
   ├─ Alternate-ingress carrier
   └─ Store-and-forward floor
   │
   ▼
VAN Gateway
   │
   ▼
Hermes profile van
```

## 20.1 Android architecture — extend the merged PR #48 stream/replay stack

Do not create another event reducer or cursor store.

Keep and extend:

```text
android/app/src/main/java/com/dial/van/events/EventStream.kt
android/app/src/main/java/com/dial/van/events/PreferencesEventCursorStore.kt
android/app/src/main/java/com/dial/van/gateway/GatewayRetry.kt
android/app/src/main/java/com/dial/van/gateway/QueueReplayer.kt
android/app/src/main/java/com/dial/van/gateway/ReplayTrigger.kt
android/app/src/main/java/com/dial/van/queue/EncryptedCommandQueue.kt
```

Add:

```text
android/app/src/main/java/com/dial/van/session/
    VanHermesSessionManager.kt
    VanHermesSessionState.kt
    SessionEnvelope.kt
    SessionResumeRequest.kt
    SessionResumeResult.kt

    transport/
        HermesTransport.kt
        TransportSupervisor.kt
        TransportHealth.kt
        TransportPathDescriptor.kt
        WebSocketTransport.kt
        Http2StreamTransport.kt
```

`VanHermesSessionManager` SHALL feed durable downstream pages/events into the existing `EventStream.applyPage(...)`.

The REST replay floor continues to call the existing `/v1/events?after_seq=` path and store the resulting cursor through `PreferencesEventCursorStore`.

Store-and-forward SHALL extend `EncryptedCommandQueue` / `QueueReplayer`; no `DurableOutboxAdapter` or second queue is created.

Path retry/backoff uses `GatewayRetryPolicy` and `GatewayCircuitBreaker` as canonical primitives.

## 20.2 Gateway architecture

Create:

```text
backend/van_gateway/session/
    models.py
    service.py
    router.py
    api.py
    websocket.py
    http_stream.py
    resume.py
```

The Session Router calls the existing:

```text
CommandAuthorityService / command endpoint
DecisionService
Mission services
EventBus
Browser services
Hermes bridge
```

It does not create a second command authority.

## 20.3 Logical session identity

A `VanHermesSession` contains:

```text
van_session_id
session_epoch
device_id
principal_type
created_at_ms
last_resumed_at_ms
last_client_event_seq
last_server_ack_seq
state
```

A transport connection contains:

```text
transport_connection_id
path_id
path_epoch
protocol
route_id
endpoint_id
connected_at_ms
last_rx_ms
last_tx_ms
rtt_ms
health_state
```

`path_epoch` increments every time the active uplink authority moves to another path.

A late frame from an older path epoch cannot become a new command.

## 20.4 Session message envelope

All semantic session messages use a transport-independent envelope:

```json
{
  "protocol_version": 1,
  "message_id": "msg_...",
  "van_session_id": "vhs_...",
  "session_epoch": 7,
  "path_epoch": 19,
  "device_id": "android-...",
  "direction": "UPSTREAM",
  "kind": "command.submit",
  "created_at_ms": 0,
  "expires_at_ms": 0,

  "turn_id": "turn_...",
  "command_id": "cmd_...",
  "response_id": null,
  "event_id": null,

  "idempotency_key": "...",
  "correlation_id": "...",
  "payload_digest": "...",
  "payload": {}
}
```

High-frequency WebRTC browser input does **not** use this envelope.

## 20.5 Initial transport set

Rev 1.2 defines a minimum three-level continuity ladder.

### Path class A — primary full-duplex realtime

```text
protocol: WSS over TLS
endpoint: /v1/session/ws
direction: full duplex
use: commands, events, response streaming, approvals, speech semantics
```

This is the normal low-latency path.

### Path class B — HTTP/2 fallback

Upstream:

```text
POST /v1/session/messages
```

Downstream:

```text
GET /v1/session/events-stream
HTTP/2 streaming / SSE-style event frames
```

This path must carry the same `SessionEnvelope` semantics.

It is intentionally different enough from WebSocket handling to survive middleboxes or ingress components that break WebSockets while ordinary HTTPS still works.

### Path class C — compatibility/replay floor

Use existing durable APIs:

```text
POST /v1/commands
GET  /v1/events?device_id=...&after_seq=...
GET  command/mission state as required
```

This path is slower but must allow VAN to recover command and event truth.

### Future optional path — QUIC/WebTransport

May be admitted later after Android/runtime dependency review.

Rev 1.2 does not require it for first production closure.

## 20.6 Route diversity

A `TransportPathDescriptor` contains:

```text
path_id
protocol
endpoint
route_id
priority
supports_full_duplex
supports_streaming_downlink
metered_allowed
standby_mode
```

Two paths with different protocols but the same `route_id` provide protocol diversity only.

To certify true route redundancy, two active candidates must have distinct independently tested `route_id` values.

Examples of possible route diversity, subject to owner deployment decisions:

```text
direct approved Oracle ingress
alternate authenticated ingress/relay
different public endpoint terminating into the same Gateway authority
```

No path may bypass device authentication or VAN Gateway authority.

## 20.7 Transport Supervisor

`TransportSupervisor` owns path health and failover.

States:

```text
STARTING
PRIMARY_CONNECTING
MULTIPATH_HEALTHY
SINGLE_PATH
FAILOVER_PREPARING
FAILOVER_COMMITTING
RECOVERING
STORE_AND_FORWARD
OFFLINE_LOCAL
```

Per-path health:

```text
HEALTHY
SUSPECT
DEGRADED
FAILED
COOLDOWN
```

## 20.8 Dynamic health probing

When VAN is actively:

- listening;
- waiting for Hermes;
- speaking a streamed response;
- using agent browser control;
- awaiting approval/result;

use an active-session heartbeat target approximately:

```text
2 s heartbeat
2 missed heartbeats -> SUSPECT
transport error -> immediate SUSPECT/FAILED
```

When idle/background:

```text
10–30 s heartbeat depending Android power policy
```

Do not wake the radio every two seconds permanently in background.

Health score includes:

```text
connectivity
RTT
RTT variance
application heartbeat age
write success
read freshness
recent disconnects
HTTP/WebSocket status
route reachability
```

## 20.9 Warm standby policy

During an active owner interaction, VAN SHOULD maintain one authenticated warm fallback when battery/network policy permits.

Warm standby carries:

```text
heartbeats
session cursor reconciliation
no duplicate command uplink
```

Only one path epoch is authoritative for new upstream owner messages.

Downstream duplicates are safe because `event_id`/`response segment id` are deduplicated.

When idle, fallback may be cold to preserve battery.

## 20.10 Failover transaction

A path switch is a transaction.

```text
1. mark primary SUSPECT
2. open/resume fallback with same van_session_id
3. send:
       session_epoch
       last durable event seq
       unresolved command ids
       active turn id
       active response id
       last received speech segment
4. Gateway returns authoritative resume snapshot
5. reconcile:
       commands
       decisions
       response cursor
       mission state
6. Gateway grants new path_epoch
7. client atomically promotes fallback
8. old path becomes non-authoritative
9. delayed old-path upstream envelopes are rejected
```

The client must never “just open another socket and continue.”

## 20.11 Session resume contract

Request:

```json
{
  "van_session_id": "vhs_...",
  "session_epoch": 7,
  "device_id": "android-...",
  "last_event_seq": 18430,
  "pending_command_ids": ["cmd_827"],
  "active_turn_id": "turn_196",
  "active_response_id": "rsp_58",
  "last_received_response_segment": 4,
  "last_spoken_speech_segment": 2
}
```

Response:

```json
{
  "accepted": true,
  "session_epoch": 7,
  "new_path_epoch": 20,
  "authoritative_event_cursor": 18434,
  "command_states": {
    "cmd_827": "RUNNING"
  },
  "response_state": {
    "response_id": "rsp_58",
    "next_segment": 5,
    "complete": false
  },
  "replay_from_seq": 18431
}
```

## 20.12 Command ambiguity and effectively-once execution

If VAN transmitted a command and lost the path before ACK:

```text
client state = SENT_ACK_UNKNOWN
```

On another path VAN resubmits the **same**:

```text
command_id
idempotency_key
payload_digest
```

Gateway behavior:

```text
new key                  -> validate + execute/submit once
known key, same digest   -> return existing authoritative command state
known key, different digest -> reject conflict
```

A reconnect must never mint a fresh command ID merely to “retry.”

## 20.13 Event replay

Rev 1.5 migration-27 event semantics remain:

```text
global seq
event_id
target_device_id
device-filtered replay
per-device cursor
```

Realtime push and REST replay are two carriers for the same durable event authority.

## 20.14 Local durable outbox — extend PR #48's queue/replayer

Extend `EncryptedCommandQueue` and its existing `QueueReplayer`/`ReplayTrigger` metadata with:

```text
message_id
command_id
idempotency_key
turn_id
created_at
expires_at
freshness_policy
action_class
requires_live_owner_context
last_attempt_path
attempt_count
```

Commands must be classified before storage.

Examples:

```text
SAFE_TO_RETRY
STORE_UNTIL_TTL
REQUIRE_RECONFIRM_ON_RECONNECT
NEVER_STORE
```

A4/destructive actions do not silently execute hours later because connectivity returned.

## 20.15 Store-and-forward state

When every Hermes transport is unavailable:

```text
VanHermesSessionManager = STORE_AND_FORWARD
```

Locally available features remain operational.

Remote work is queued only when policy allows.

UI/voice must distinguish:

```text
"queued"
```

from:

```text
"submitted"
"running"
"completed"
```

## 20.16 Control-plane continuity targets

During an active owner turn:

```text
detected hard transport failure → fallback connect/resume p95 < 2.0 s
warm-standby promotion target                  < 750 ms
duplicate owner command execution             = 0
lost durable events after successful resume   = 0
repeated spoken response segments             = 0
```

These targets are measured independently from browser WebRTC latency.

## 20.17 Browser independence

The remote browser media PeerConnection is not tunneled through the Hermes session.

Examples:

```text
Hermes WSS fails
    browser manual viewport may continue
    Session Manager moves to HTTP fallback
    browser intelligence pauses/resumes

Browser WebRTC fails
    Hermes voice/control remains healthy
    VAN can explain the browser transport failure
    browser reconnect occurs separately
```

This failure isolation is mandatory.



## 20.18 PR #48 event-stream integration rule

Realtime push is an acceleration path, not a second event truth.

All live WSS/HTTP2 event frames are normalized into the same logical `EventPage`/`EventRecord` model consumed by the existing Activity surface.

The current poll loop remains:

```text
replay/catch-up floor
offline recovery
post-process-death recovery
fallback when push transport is unavailable
```

Do not delete it merely because WebSocket works.

## 20.19 PR #48 retry/circuit integration rule

`TransportSupervisor` may maintain per-path health, but retryability and breaker semantics must reuse the existing tested rules in `GatewayRetry.kt`.

Mutation tests must prove that changing:

```text
409 from terminal → retryable
401 from terminal → retryable
transport failure from retryable → terminal
```

breaks the Remote Browser/session tests as well as the existing gateway tests.

That proves the old and new paths share the same invariant instead of coincidentally duplicating it.



## 20.20 Single realtime semantic endpoint

Rev 1.5 has exactly one full-duplex realtime semantic endpoint:

```text
WSS /v1/session/ws
```

There is no second realtime semantic socket.

There is no second standalone realtime backend package.

Durable recovery remains:

```text
GET /v1/events?device_id=...&after_seq=...
```

and HTTP/2 streaming fallback remains:

```text
GET /v1/session/events-stream
```

All three feed the same event/session semantics and existing Android `EventStream`.

# 21. VOICE SYMBIOSIS



Voice is a primary owner interface and a resilience subsystem.

The production invariant is:

> VAN must not require public internet access on the S24 to hear the owner or to speak a Hermes response.

The phone still needs a working VAN⇄Hermes path for remote reasoning/web work. If every Hermes path is down, local voice functions remain available and VAN must describe that state truthfully.

## 21.1 Existing PR #48 voice foundation

PR #48 materially advances the voice baseline.

Merged production/repository truth:

```text
VoiceAudioArbiter                   integrated
VoiceInputManager                   integrated
Android on-device SpeechRecognizer integrated
WakeCoordinator                     integrated
WakeRuntimeController               integrated
WakeListenerService                 integrated microphone FGS
WakeModelAsset policy               integrated
WakeModelLoader                     integrated
Wake acknowledgement call path      wired, device-unverified
TtsOutputManager.speak              wired, device-unverified
PersonalSpeechModel correction UI   integrated
Speaker verification gate           integrated

WakeWordEngine concrete runtime      absent/external block
WakePhraseVerifier concrete runtime  absent/external block
LocalSecondPassAsr concrete runtime  absent/external block
```

Therefore Rev 1.3 does not create another wake service, wake coordinator, model loader, acknowledgement manager, audio arbiter or TTS caller.

It fills the concrete local-runtime gaps behind the existing interfaces and then proves them on the physical S24.

Speaker similarity remains provenance/context and MUST NOT become authorization merely because the offline model can estimate a speaker.

## 21.2 Voice edge architecture

```text
                         S24 — LOCAL VOICE EDGE

microphone
   ↓
VoiceAudioArbiter
   ↓
wake / push-to-talk
   ↓
local acknowledgement: "hie van"
   ↓
VAD
   ↓
ASR router
   ├─ Android on-device ASR
   └─ Sherpa-ONNX local ASR fallback/second pass
   ↓
TranscriptFusion
   ↓
signed transcript provenance
   ↓
VanHermesSessionManager
   ↓
Hermes / browser / tools / internet

                         S24 — LOCAL OUTPUT EDGE

Hermes semantic response
   ↓
response/speech segment queue
   ↓
LocalTtsRouter
   ├─ bundled Sherpa-ONNX TTS
   ├─ verified Android offline TTS fallback
   └─ pre-rendered critical phrase bank
   ↓
AudioFocus + playback
   ↓
speech sync / mouth / viseme / VAN state
```

No cloud ASR/TTS is required for the normal path.

## 21.3 Deterministic offline voice dependency

Rev 1.2 admits Sherpa-ONNX as the preferred local voice runtime candidate because its Android stack supports:

```text
ASR
VAD
keyword spotting
offline TTS
```

and can operate entirely on-device.

Dependency admission MUST pin:

```text
sherpa-onnx version
Android native binaries / ABI
SHA-256
source revision
licence
ASR model IDs + hashes
VAD model ID + hash
TTS model ID + hash
vocabulary/lexicon revision
```

Do not use “latest” in production.

## 21.4 Voice asset pack

Extend PR #48's existing wake-model asset policy with a signed/versioned voice bundle manifest.

Recommended new manifest:

```text
android/app/src/main/assets/voice/voice_asset_manifest.json
```

This manifest complements `WakeModelAsset.kt`; it does not replace its readiness/digest policy.

Logical contents:

```json
{
  "schema": "van-voice-assets/1",
  "bundle_version": "...",
  "wake": {},
  "vad": {},
  "asr": {},
  "tts": {},
  "critical_phrases": {},
  "vocabulary_revision": "...",
  "files": [
    {
      "path": "...",
      "sha256": "...",
      "size": 0
    }
  ]
}
```

At startup:

1. verify manifest signature/digest;
2. verify required model files;
3. perform lightweight engine self-test;
4. mark capabilities individually:
   - `LOCAL_WAKE_READY`
   - `LOCAL_ASR_READY`
   - `LOCAL_TTS_READY`
   - `VOICE_CRITICAL_PHRASES_READY`.

Missing local voice assets are a release-blocking condition for the owner S24 build.

## 21.5 Wake acknowledgement

For the established owner contract:

```text
wake phrase detected
   ↓
immediately play local "hie van"
```

The acknowledgement MUST be pre-rendered or otherwise guaranteed locally available.

It must not:

- contact Hermes;
- wait for ASR;
- wait for TTS engine initialization;
- depend on public internet.

Target:

```text
wake detection → audio start p95 < 150 ms
```

## 21.6 Audio capture ownership

Only one component owns `AudioRecord`.

`VoiceAudioArbiter` remains that owner.

Consumers subscribe to the same capture stream:

```text
wake detector
VAD
turn evidence buffer
ASR
barge-in detector
RMS/visual sync
```

Do not create competing microphone sessions that fight Android audio focus or lose pre-roll.

## 21.7 Pre-roll

Maintain a bounded circular PCM pre-roll so the beginning of an utterance is not lost when wake/VAD opens a turn.

Target:

```text
500–1000 ms local PCM pre-roll
```

Sensitive audio is memory-bounded and not persistently stored unless explicit diagnostic evidence mode is enabled.

## 21.8 ASR routing

Preferred hierarchy:

```text
A. Android on-device recognizer when available and certified
B. Sherpa-ONNX local ASR
C. two-pass/fusion when confidence or vocabulary rules require it
```

Cloud recognition is optional and must never be needed for core operation.

## 21.9 ASR confidence and second pass

A final transcript receives:

```text
turn_id
backend
text
alternatives
confidence
word timing where available
known-vocabulary matches
started_at_ms
finalized_at_ms
audio evidence digest/ref where permitted
```

Second-pass local recognition triggers on bounded rules such as:

```text
confidence below threshold
known VAN vocabulary confusion
proper noun/acronym ambiguity
high disagreement between hypotheses
owner correction history
```

Do not run an expensive second pass on every easy turn.

## 21.10 VAN vocabulary bias

Dynamic bias is compiled from bounded context:

```text
active project
active browser page/domain
current mission
recent owner turn
registered project names
known VAN technical vocabulary
approved personal speech vocabulary
```

Examples likely to require bias:

```text
VEKL
DDE
Hermes
VATI
Stagehand
Playwright
Supabase
Zimswitch
n8n
Antigravity
```

Biasing cannot rewrite the transcript merely because a term is expected. Raw alternatives/confidence remain evidence.

## 21.11 Offline command classification

After local ASR, before Hermes availability is known, classify the command:

```text
LOCAL_EXECUTABLE
REMOTE_REQUIRED
REMOTE_OPTIONAL
OWNER_APPROVAL_REQUIRED
```

Examples:

```text
"repeat your last answer"
    LOCAL_EXECUTABLE

"open VAN Browser"
    LOCAL_EXECUTABLE

"search the web for..."
    REMOTE_REQUIRED

"summarize the cached result"
    potentially LOCAL_EXECUTABLE

"send/delete/pay/execute..."
    authority-specific; never silently deferred
```

The classifier does not become an autonomous agent. It is a deterministic routing layer.

## 21.12 Voice turn identity

Every voice turn has:

```text
turn_id
wake_session_id
transcript_revision
command_id if submitted
origin_channel = VOICE
```

A transport failover keeps the same `turn_id` and `command_id`.

## 21.13 Response model

Hermes returns separate presentation and speech semantics:

```json
{
  "response_id": "rsp_58",
  "turn_id": "turn_196",
  "presentation": {
    "text": "full answer...",
    "cards": []
  },
  "speech": {
    "mode": "SPEAK",
    "interruptible": true,
    "segments": []
  }
}
```

The full screen answer and the spoken answer do not have to be identical.

Long research output SHOULD be summarized conversationally for speech.

## 21.14 Speech segment protocol

Hermes/Gateway streams semantically safe speech units.

```json
{
  "response_id": "rsp_58",
  "speech_stream_id": "sp_58",
  "segment_id": "sp_58_0004",
  "segment_index": 4,
  "text": "The second important factor is...",
  "final": false,
  "interruptible": true,
  "content_digest": "..."
}
```

Segment boundaries SHOULD be:

```text
clause
sentence
short paragraph
```

Never arbitrary model-token chunks.

## 21.15 Local speech queue

Android maintains:

```text
RECEIVED
SYNTHESIZING
READY
SPEAKING
SPOKEN
INTERRUPTED
FAILED
```

Persist minimal cursors:

```text
response_id
speech_stream_id
last_received_segment
last_spoken_segment
```

Do not persist synthesized raw audio indefinitely.

## 21.16 No duplicate speech after failover

If path A dies after segment 4 arrives:

```text
last_received_segment = 4
last_spoken_segment = 2
```

On session resume VAN reports both.

Gateway resumes from the required semantic cursor.

Duplicate `segment_id` is discarded.

A transport reconnect must never cause:

```text
"Here is your answer..."
```

to start again from segment 0 unless the owner explicitly asks for replay.

## 21.17 Speech buffering for seamless failover

When response streaming is active, maintain a small local ready queue where possible:

```text
target: 1–2 future speech segments
```

This queue allows TTS to continue while a control path switches.

Do not create a large queue that makes barge-in or refocused answers stale.

## 21.18 Local TTS router

Create:

```text
voice/tts/
    LocalTtsEngine.kt
    SherpaOnnxTtsEngine.kt
    AndroidOfflineTtsEngine.kt
    CriticalPhraseEngine.kt
    LocalTtsRouter.kt
```

Selection:

```text
arbitrary assistant answer
    preferred: bundled Sherpa-ONNX TTS
    fallback: Android TTS only if verified offline voice data is installed

critical system phrase
    preferred: pre-rendered phrase bank
```

Android TTS may remain available, but a system TTS voice whose offline data disappeared after an OS change cannot be the only production talk-back path.

## 21.19 TTS model selection gate

Choose the actual Sherpa-ONNX TTS model by S24 benchmark, not by reputation.

Candidate families may include compact VITS/Piper, Kitten, Kokoro or another supported offline model.

Required measurements:

```text
model size
cold init ms
warm first-audio latency
real-time factor
peak memory
battery/thermal effect
voice quality
pronunciation quality on VAN vocabulary
long-answer stability
```

The chosen model and voice are locked in `voice_asset_manifest.json`.

## 21.20 Speech latency SLOs

Target on the owner S24:

```text
wake acknowledgement start                 <150 ms p95
VAD end-of-speech finalization contribution <250 ms target
ASR final after end-of-speech              <700 ms p95
local TTS first audio after ready segment  <500 ms p95
barge-in → playback stop                   <100 ms p95
next listen state after barge-in           <150 ms p95
```

Model-dependent values must be measured; failure is reported, not hidden.

## 21.21 Barge-in

Barge-in is entirely local for immediate stop:

```text
owner speech detected
   ↓
local speech playback STOP
   ↓
speech segment state = INTERRUPTED
   ↓
VAN state = LISTENING
   ↓
new local ASR turn begins
   ↓
semantic interruption event sent when transport available
```

Hermes does not need to acknowledge before audio stops.

## 21.22 Browser audio arbitration

When VAN speaks over Browser audio:

```text
AudioManager focus
   ↓
browser audio duck or pause per policy
   ↓
VAN TTS
   ↓
browser audio restore
```

Website audio must not make VAN unintelligible.

Incoming calls/media focus changes are respected.

## 21.23 Voice state machine

```text
IDLE
 ↓
WAKE_DETECTED
 ↓
ACK_PLAYING
 ↓
LISTENING
 ↓
FINALIZING_ASR
 ↓
ROUTING
 ├─ LOCAL_EXECUTING
 ├─ REMOTE_SUBMITTING
 └─ QUEUED_OFFLINE
 ↓
WAITING_FOR_RESPONSE
 ↓
RESPONSE_STREAMING
 ↓
SPEAKING
 ├─ BARGED_IN → LISTENING
 └─ COMPLETE → IDLE
```

Network transport state is orthogonal. `SPEAKING` may continue through `FAILOVER_PREPARING`.

## 21.24 Connectivity capability matrix

### Public internet unavailable on S24, VAN⇄Hermes path healthy

```text
wake                         YES
local ASR                    YES
Hermes reasoning             YES
Oracle web search            YES
Remote Browser               YES if its media route works
local TTS                    YES
```

This is the target architecture.

### Hermes paths unavailable, phone locally healthy

```text
wake                         YES
local ASR                    YES
local deterministic commands YES
cached answer replay         YES
local TTS                    YES
offline queue                YES
fresh web/Hermes reasoning   NO
```

### Complete local-only state

VAN must not fabricate remote answers.

For a remote-required question it may say locally:

```text
"I can't reach Hermes right now."
```

and queue the request only when freshness/authority policy allows.

## 21.25 Delayed-answer speech policy

A question queued while Hermes is unavailable must not unexpectedly speak aloud hours later.

On later completion:

```text
if owner is in same active voice/session context:
    speech may resume normally

otherwise:
    post owner notification / Needs You item
    speak only after owner re-engages or policy explicitly permits
```

## 21.26 Voice success contract

Input states are distinct:

```text
WAKE_DETECTED
ACK_PLAYED
ASR_LISTENING
ASR_FINAL
COMMAND_QUEUED
COMMAND_SUBMITTED
COMMAND_ACCEPTED
```

Output states are distinct:

```text
RESPONSE_RECEIVED
SPEECH_SEGMENT_RECEIVED
TTS_SYNTHESIZED
TTS_STARTED
TTS_COMPLETED
OWNER_INTERRUPTED
TTS_FAILED
```

`RESPONSE_RECEIVED` is not proof that the owner heard the response.

## 21.27 Offline voice production canary

A mandatory device acceptance canary:

```text
disable ordinary public internet access for VAN on S24
retain approved VAN⇄Hermes path

Owner:
"Hey Van"

Expected:
local "hie van"

Owner asks a fresh web question

Expected path:
local ASR
 → durable VAN⇄Hermes session
 → Oracle web/browser work
 → semantic response
 → local TTS
 → spoken answer
```

The canary fails if:

- ASR contacts a public cloud service;
- TTS requires public internet;
- wake acknowledgement waits on Hermes;
- response is visible but cannot be spoken;
- path failover duplicates the command or speech;
- Hermes success is claimed before the actual remote result is verified.



## 21.28 Concrete PR #48 voice-gap closure

The implementation target is not a parallel `SherpaVoiceService`.

Create a concrete runtime adapter, for example:

```text
voice/offline/SherpaOnnxVoiceRuntime.kt
```

that implements/adapts the existing interfaces:

```text
WakeWordEngine
WakePhraseVerifier
LocalSecondPassAsr
```

and provides a local TTS backend behind the existing `TtsOutputManager` public call path.

`WakeModelLoader.pipelineOrNull()` becomes the binding point after:

```text
model present
digest valid
native runtime ready
runtime self-test green
```

The existing `WakeListenerService` continues to own the microphone foreground-service lifecycle.

The existing `VoiceAudioArbiter` continues to own AudioRecord and its current ~750 ms pre-roll behavior.

The existing `WakeAcknowledgementManager` remains responsible for `"hie van"`; the new voice runtime must not add a second acknowledgement path.

## 21.29 Owner-decision / ledger transition for offline voice

PR #48 records an earlier owner decision that declined building Sherpa and therefore correctly marks several components externally blocked.

Rev 1.3's requirement for hardened offline voice is a new product requirement, but implementation governance still requires an explicit adoption artifact such as:

```text
docs/decisions/VAN-ADOPT-OFFLINE-VOICE-RUNTIME-001.yaml
```

Until that decision is approved and the physical-device gates pass:

```text
WakeWordEngine
WakePhraseVerifier
LocalSecondPassAsr
```

must remain externally blocked in the component ledger.

After implementation, do not simply edit their terminal states.

Supply:

```text
producer
consumer
production caller
tests
physical S24 runtime evidence
falsified_by
```

and let the maturity gate validate the stronger claim.

## 21.30 Existing TTS truth is preserved

PR #48 makes `TtsOutputManager.speak()` production-reachable, but device playback is still externally unverified.

Rev 1.3 therefore separates:

```text
CALLED
DEVICE_AUDIO_STARTED
DEVICE_AUDIO_COMPLETED
OWNER_INTERRUPTED
FAILED
```

Physical S24 evidence is mandatory before `LOCAL_TTS_READY` or production-certified talk-back is claimed.

# 22. HERMES / STAGEHAND TAKEOVER

## 22.1 Control transition

When Hermes needs to operate the visible browser:

```text
OWNER
 ↓
TAKEOVER_REQUESTED
 ↓
policy + authority check
 ↓
control generation increments
 ↓
HERMES_STAGEHAND
```

Android receives a visible state:

```text
VAN is controlling this tab
[Take over]
```

## 22.2 Stagehand scope

Agent receives:

```text
session_id
target_id
goal
allowed_domains
action_class
step_budget
deadline
control_lease_id
control_generation
```

It does not receive:

- device HMAC;
- owner signing key;
- VAN internal token;
- raw browser cookies;
- unbounded scope.

## 22.3 Human preemption

The first owner DOWN event performs:

```text
local input lock
 ↓
human_preempt message
 ↓
server invalidates current control generation
 ↓
Stagehand actions with old generation fail
 ↓
new OWNER control lease
 ↓
queued agent action discarded
```

This is mandatory.

A UI-only “Take over” button without server control-generation invalidation is not sufficient.

---

# 23. MISSION INTEGRATION

PR #48 makes command→Mission creation canonical.

For any owner voice/text command:

```text
accepted command
    ↓
exactly one Mission
```

Remote Browser must attach to that Mission; it must not create a second mission.

## 23.1 Command-originated browser work

When the owner asks:

> “Van, search this page and explain it.”

the existing command/orchestrator path creates the Mission.

The interactive browser session is context.

The BrowserTask/agent activity binds by reference to the already-existing Mission.

Required relationship:

```text
Mission
  ├─ owner command
  ├─ interactive browser session ref
  ├─ browser task/activity
  ├─ verification/evidence
  └─ final owner-visible result
```

## 23.2 Pure manual browsing

A manually opened browser session may exist without a Mission.

Opening a web page manually is not itself a unit of agent work.

If the owner later asks VAN to perform a task using that session, that owner command creates the Mission, and the current browser session is attached as context/activity reference.

## 23.3 MissionBinder extension

If the existing binder lacks an interactive-session reference method, add:

```text
MissionBinder.bind_browser_session_reference(...)
```

The method must not call `MissionService.create`.

Existing BrowserTask and automation binding paths remain authoritative.

## 23.4 Verification

Browser worker completion does not transition the Mission to `VERIFIED_SUCCESS`.

PR #48's success contract applies unchanged:

```text
executor says complete
    ≠
verified success
```

A registered verifier/independent observation must establish the requested postcondition.

Manual browsing has no artificial success receipt.

# 24. VISUAL VAN INTEGRATION

Browser state SHALL drive the existing VAN embodiment through semantic states.

Examples:

```text
browser connection establishing -> CONNECTING
owner manual browsing           -> ATTENTIVE or IDLE
voice listening                 -> LISTENING
Hermes deciding search path     -> THINKING
browser navigating autonomously -> SEARCHING / WORKING
Stagehand active                -> DELEGATING / WORKING
result being spoken             -> SPEAKING
owner required                  -> WAITING_FOR_OWNER
connection degraded             -> DEGRADED
task verified                   -> SUCCESS
```

Do not animate SUCCESS merely because navigation finished.

Trade aura semantics remain governed by the trading state authority. Browser activity must not overwrite a higher-priority urgent/trading visual state incorrectly.

A visual-state arbitration policy is required.

---

# 25. RESOURCE PLACEMENT


## 25.1 Production placement — owner decision required

The recommended production architecture is a **dedicated public-facing Browser Stream Host**.

This simultaneously resolves:

- S24 reachability;
- public ICE/TURN placement;
- encode/capture compute isolation;
- protection of VATI/private Trading Core;
- avoidance of media-induced authority-service starvation.

`van-trading-core` remains private and unchanged.

The owner must explicitly approve the new host/shape as a Phase 0 infrastructure decision before production deployment.

## 25.2 Host responsibilities

Dedicated Browser Stream Host:

```text
Chromium
headless Wayland compositor
PipeWire/capture
GStreamer
H.264 encoder
WebRTC signaling/media
coturn or nearby TURN
Browser Harness/Stagehand attachment endpoint
```

Private Gateway/Hermes remain authority/control peers over private channels.

## 25.3 Resource sizing gate

The exact compute shape is selected from measured Phase 1 evidence.

Preferred characteristics:

- sufficient single-session Chromium render capacity;
- supported H.264 hardware encode where possible;
- network bandwidth adequate for 1080p60;
- enough memory for Chromium/profile/session runtime;
- resource headroom for one production session without sustained >80% system CPU.

## 25.4 A1 role

The 2 OCPU / 12 GB private ARM64 `van-trading-core` may be used only for:

- internal protocol proof;
- low-resolution capture/encode benchmark;
- Stagehand/Browser Harness integration development.

It is not the Rev 1.1 production stream placement.

## 25.5 Dedicated-host promotion is no longer a late contingency

Rev 1's promotion gate is moved to Phase 0.

If the owner declines a dedicated public stream host, the implementation must return to architecture review rather than expose Trading Core publicly or quietly lower the product target.

# 26. LATENCY BUDGET


The system is engineered against motion-to-photon, not just ping.

Design target under a healthy network:

```text
Android input capture           0–4 ms
uplink                           RTT/2
server input routing            <5 ms p95
Chromium render                 0–16.7 ms
capture                         <5 ms p95
encode                          <12 ms p95 target
downlink                         RTT/2
jitter buffer                   as low as stable
decode                          <8 ms p95 target
display/vsync                   0–16.7 ms
```

## 26.1 Unmetered / high-quality production SLO

Applies when:

```text
network is unmetered
or
owner explicitly enables high-quality mobile mode
```

Target:

```text
network RTT                        <80 ms preferred
interaction touch-to-visible       <100 ms p50 target
interaction touch-to-visible       <130 ms p95 target
server input dispatch               <5 ms p95
server capture                      <5 ms p95
server encode                      <12 ms p95
Android decoded/rendered FPS       >=55 p95 during active browsing
packet loss                        <2% typical
reconnect after transient loss     <3 s target
owner takeover acknowledgement     <100 ms target
```

## 26.2 Metered / data-constrained production SLO

Applies to default metered mobile-data policy.

Target quality is intentionally different:

```text
resolution class                   720p-class target
active rendered FPS                >=30 p95
preferred operating FPS            30–45
target media bitrate               approximately 1.5–3 Mbps
interaction touch-to-visible       <150 ms p95 when network RTT permits
owner takeover acknowledgement     <150 ms target
```

A metered session is **not** failed merely because it does not reach the unmetered `>=55 FPS` target.

It fails if it misses the metered profile or if the UI/telemetry falsely reports high-quality/unmetered certification.

## 26.3 Network-limited classification

If mobile RTT itself exceeds the interaction budget:

```text
session_status = NETWORK_LIMITED
```

Do not lower the normal product SLO silently.

Record:

```text
transport
route
metered flag
RTT
jitter
loss
quality profile
```

with every certification result.

## 26.4 Component budget

Healthy high-quality target:

```text
Android input capture           0–4 ms
uplink                           RTT/2
server input routing            <5 ms p95
Chromium render                 0–16.7 ms
capture                         <5 ms p95
encode                          <12 ms p95 target
downlink                         RTT/2
jitter buffer                   minimum stable
decode                          <8 ms p95 target
display/vsync                   0–16.7 ms
```

These remain design/measurement targets rather than guarantees independent of network physics.

# 27. QUALITY ADAPTATION


Create `BrowserQualityController`.

Inputs:

```text
RTT
jitter
packet loss
NACK rate
available outgoing bitrate
encode duration
capture duration
CPU pressure
decoder/rendered frame rate
metered-network state
Android Data Saver state
owner mobile-data quality preference
session bytes received/sent
```

## 27.1 Unmetered ladder

Example:

```text
ULTRA
1080-class viewport, 60 FPS, high bitrate

NORMAL
1080-class viewport, 60 FPS, moderate bitrate

CONSTRAINED
900p/720p class, 45–60 FPS

SURVIVAL
720p, 30 FPS, low bitrate
```

## 27.2 Metered-network default

On a metered network, default to a bounded profile unless the owner explicitly enables high-quality mobile data.

Initial target:

```text
720p-class
30–45 FPS
approximately 1.5–3 Mbps target envelope
```

This remains adaptive.

Android displays:

```text
current network type
metered/unmetered status
session data used
estimated current Mbps
quality mode
```

A one-session owner override may enable higher quality.

The app must not silently consume 4–12 Mbps for hours on metered mobile data.

## 27.3 Data accounting

Track per-session:

```text
media bytes received
media bytes sent
control bytes
session duration
average media bitrate
```

Use network statistics for product telemetry, not billing-grade accounting.

## 27.4 Hysteresis

Quality-state transitions require hysteresis to avoid oscillation.

A subtle degraded connection indicator is allowed; persistent noisy UI is not.

# 28. OBSERVABILITY

Each session receives one correlation identifier.

All subsystems use:

```text
session_id
device_id
mission_id where present
command_id where present
browser_task_id where present
target_id
control_generation
```

## 28.1 Required metrics

Server:

```text
browser_session_active
browser_session_connect_ms
browser_capture_ms
browser_encode_ms
browser_frame_fps
browser_frame_drop_rate
browser_cpu_pct
encoder_cpu_pct
browser_memory_mb
webrtc_rtt_ms
webrtc_jitter_ms
webrtc_packet_loss
webrtc_bitrate_bps
turn_relay_ratio
input_dispatch_ms
control_lease_preempt_ms
```

Android:

```text
browser_decode_fps
browser_render_fps
browser_frame_drop_count
browser_reconnect_count
browser_input_queue_depth
browser_last_frame_age_ms
browser_audio_underruns
```

## 28.2 No secret logging

Never log:

- typed password content;
- cookies;
- Authorization headers;
- access tokens;
- sessionStorage/localStorage secrets;
- OTP values;
- raw device secret;
- BrowserStreamGrant;
- TURN credential.

Use IDs and digests.

---

# 29. FAILURE AND RECOVERY


Failure recovery is layered. Do not collapse transport, session, browser and voice failures into `offline`.

## 29.1 Control transport failure

If primary WSS fails:

```text
TransportSupervisor
   ↓
promote warm HTTP/2/alternate path if available
   ↓
resume same van_session_id
   ↓
reconcile event cursor + unresolved command state
```

No new owner turn is created.

## 29.2 Protocol-specific failure

If WebSocket is blocked but HTTPS works:

```text
WSS FAILED
HTTP2_FALLBACK HEALTHY
```

VAN remains operational through the logical session.

UI may show a subtle degraded diagnostic, not a disruptive offline state.

## 29.3 Route failure

If all protocols on route A fail and route B is independently reachable:

```text
route A FAILED
route B resume
```

Only after route B is proven should VAN claim multipath recovery.

## 29.4 All Hermes paths fail

Enter:

```text
STORE_AND_FORWARD
```

Voice edge/local functions continue.

Remote-required commands follow TTL/reconfirmation policy.

If no safe queue behavior exists, fail immediately and tell the owner locally.

## 29.5 Transport recovers

Recovery sequence:

```text
authenticate
resume logical session
replay durable events
reconcile pending command IDs
reconcile active response/speech cursors
transition STORE_AND_FORWARD → SINGLE_PATH/MULTIPATH_HEALTHY
```

Queued A3/A4 work is not automatically executed unless its original authority/freshness contract explicitly permits it.

## 29.6 Failover during speech

Local TTS continues from already-received segments.

If fallback resumes before the ready queue empties, audible speech can remain uninterrupted.

If the queue empties:

- VAN may pause naturally;
- show CONNECTING/DEGRADED;
- after a bounded interval, optionally use a local critical phrase;
- resume from the next unseen segment.

Never repeat already-spoken segments.

## 29.7 Failover during ASR command submit

If the path dies after send but before ACK:

```text
same command_id
same idempotency_key
same payload_digest
```

is reconciled on fallback.

Never create a duplicate command.

## 29.8 Browser WebRTC failure

Browser media reconnect is independent from Hermes session transport.

Manual browser control pauses until its own stream/control lease is safe.

Voice/Hermes may remain fully functional and can explain the failure.

## 29.9 Mobile network switch

Wi-Fi→cellular may break both control and media candidate pairs.

Expected:

```text
control TransportSupervisor resumes path
browser performs ICE restart
logical owner turn survives both
```

## 29.10 Phone process death

On restart:

1. restore encrypted session metadata;
2. load event/speech cursors;
3. ask Gateway whether the logical session is resumable;
4. resume/replay;
5. separately reconnect Browser WebRTC if session still valid;
6. never trust cached completion state over Gateway truth.

## 29.11 Chromium crash

Existing Rev 1.1 behavior remains:

- mark recovering;
- stop input;
- restart supervised Chromium;
- restore safe target if possible;
- fail truthfully if state cannot be restored.

## 29.12 Gateway restart

Existing WebRTC media may remain alive if the Browser Runtime session lease allows it.

VAN control transport reconnects and resumes from durable state.

No new authority is granted until Gateway authority returns.

## 29.13 Hermes execution outage

Gateway/session transport may be healthy while Hermes is unavailable.

Report:

```text
CONNECTED_TO_GATEWAY
HERMES_EXECUTION_UNAVAILABLE
```

Manual browser usage may continue subject to leases.

Remote reasoning fails closed.

## 29.14 VM/stream host offline

Browser media is unavailable.

Hermes control/voice may still function if hosted on separate healthy infrastructure.

This is another reason not to conflate the planes.

# 30. DEGRADED-MODE INTEGRATION



Extend the existing degraded vocabulary with explicit plane/path reasons.

## VAN⇄Hermes logical session

```text
HERMES_PRIMARY_TRANSPORT_DEGRADED
HERMES_PRIMARY_TRANSPORT_FAILED
HERMES_PROTOCOL_FALLBACK_ACTIVE
HERMES_ALTERNATE_ROUTE_ACTIVE
HERMES_SINGLE_PATH_ONLY
HERMES_ALL_PATHS_UNAVAILABLE
HERMES_STORE_AND_FORWARD
HERMES_SESSION_RESUME_FAILED
HERMES_EVENT_REPLAY_FAILED
HERMES_COMMAND_RECONCILIATION_FAILED
```

## Local voice

```text
VOICE_WAKE_UNAVAILABLE
VOICE_LOCAL_ASR_UNAVAILABLE
VOICE_LOCAL_TTS_UNAVAILABLE
VOICE_ASSET_INTEGRITY_FAILED
VOICE_SECOND_PASS_UNAVAILABLE
VOICE_SPEECH_STREAM_STALLED
VOICE_TTS_SEGMENT_FAILED
```

## Browser

```text
BROWSER_RUNTIME_UNREACHABLE
BROWSER_STREAM_SIGNAL_FAILED
BROWSER_UDP_BLOCKED
BROWSER_TURN_RELAYED
BROWSER_HIGH_RTT
BROWSER_HIGH_PACKET_LOSS
BROWSER_METERED_NETWORK
BROWSER_DATA_SAVER_ACTIVE
BROWSER_ENCODER_OVERLOADED
BROWSER_CHROMIUM_CRASHED
BROWSER_PROFILE_LOCKED
BROWSER_POLICY_DENIED
BROWSER_HERMES_UNAVAILABLE
BROWSER_AGENT_UNAVAILABLE
```

## Capability-state mapping

The UI shall derive capability truth, not just show one global red/green connection icon.

Example:

```text
Voice local:       READY
Hermes primary:    FAILED
Hermes fallback:   READY
Browser media:     READY
Agent browser:     READY
```

This means the owner can continue normally despite one failed path.

Degraded state is diagnostic truth, not a generic error aesthetic.



## 30.1 Extend PR #48 Android subsystem truth

Do not create a second browser/session health registry in Android.

Extend:

```text
SubsystemSignals
SubsystemHealth
DegradedModeStore
DegradedPanel
```

with facts such as:

```text
wakeModelReady
localSecondPassAsrReady
localTtsReady
hermesPrimaryPathHealthy
hermesFallbackPathHealthy
hermesPathCount
browserMediaConnected
browserRuntimeReachable
browserProfileLeaseValid
```

The evaluation remains pure Kotlin where possible so `android/verification` can execute it.

Physical facts are read by Android-specific adapters and projected into those pure models.

## 30.2 PR #48 owner-language rule

Owner-visible degraded language must continue to say:

```text
what broke
what still works
what VAN will not do
what the owner can do to restore it
```

A failed primary WebSocket with healthy fallback is not:

```text
VAN offline
```

It is a scoped transport degradation.

A missing local TTS engine with working text response is not:

```text
Hermes failed
```

It is a local voice-output failure.

# 31. SECURITY HARDENING



## 31.1 Stream runtime authority

Browser Stream Runtime possesses only what it needs:

- Gateway public key for grant verification;
- runtime-local browser control;
- session-scoped profile access;
- TURN configuration;
- no owner signing key;
- no device HMAC secret;
- no VAN internal root token;
- no VATI broker credentials.

## 31.2 Browser sandbox

Keep Chromium sandbox active.

Use seccomp/AppArmor/systemd restrictions where compatible.

Browser process does not run as the Gateway or Hermes user.

## 31.3 CDP protection

CDP is a privileged control surface.

Requirements:

- bind only to loopback/private namespace;
- randomize/contain debug endpoint;
- never publish through Cloudflare;
- never expose through public NSG;
- do not place CDP websocket URL in Android;
- do not log CDP bearer material.

## 31.4 Prompt injection

Manual owner browsing does not make page instructions trusted.

When VAN analyses the page:

```text
source_trust = UNTRUSTED_EXTERNAL
```

Existing injection assessment remains active.

Web content cannot:

- alter Project Truth;
- grant itself a capability;
- instruct Hermes to reveal secrets;
- raise action class;
- expand browser scope.

## 31.5 Payments

Existing policy remains:

- browser task cannot automate payment;
- payment requires fresh A4 owner biometric approval;
- payment instruments are not persisted.

## 31.6 Trading

Remote Browser may show trading-related websites.

It does not become a second execution route around VATI.

No browser page or Stagehand task may bypass the Risk Authority/single-sender gate.

---



## 31.7 Signed connectivity manifest

Create a build-time resource such as:

```text
android/app/src/release/res/raw/van_connectivity_manifest.json
```

Example logical schema:

```json
{
  "schema": "van-connectivity/2",
  "deployment_id": "owner-s24-production",
  "config_version": 1,
  "package_name": "com.dial.van",
  "control_paths": [
    {
      "path_id": "oracle-direct-primary",
      "route_id": "oracle-public-a",
      "protocols": ["wss", "https"],
      "base_url": "https://<configured-host>",
      "priority": 10
    },
    {
      "path_id": "oracle-direct-fallback",
      "route_id": "oracle-public-b",
      "protocols": ["https"],
      "base_url": "https://<configured-fallback-host>",
      "priority": 20
    }
  ],
  "browser": {
    "stream_host_allowlist": ["<approved-browser-stream-host>"],
    "turn_credential_issuer": "/v1/browser/turn-credentials"
  },
  "tls": {
    "spki_pins": ["current-pin", "next-pin"]
  },
  "device_policy": {
    "max_active_owner_devices": 1,
    "hardware_key_required": true
  }
}
```

This contains configuration, not bearer secrets.

The manifest is signed by the VAN connectivity-config authority.

At startup:

```text
verify signature
verify schema
verify package/environment
load paths
reject unsigned runtime override
```

## 31.8 No editable production endpoint

The current merged client has:

```text
var baseUrl
pairThisDevice(gatewayUrl, pairingToken)
```

Rev 1.4 changes production behavior:

```text
debug/developer build:
    mutable/manual pairing may remain behind explicit debug surface

production release build:
    base URL comes only from signed connectivity manifest
    no setter exposed to ordinary UI
    pairThisDevice(...) not reachable from production owner flow
```

Contract tests must fail if a production Compose screen exposes an editable Gateway/Hermes URL or pairing token.

## 31.9 Hardware-backed owner device identity

First provisioning creates a P-256 key:

```text
alias = van_owner_device_identity_v1
purposes = SIGN
digest = SHA-256
hardware backed = required
StrongBox = preferred where available and proven suitable
TEE = allowed fallback
private key export = impossible
```

Generate it with a Gateway-provided attestation challenge.

The server verifies:

```text
attestation challenge matches
certificate chain valid
attestation root accepted
revocation status acceptable
security level >= TrustedEnvironment
verified boot state acceptable
deviceLocked = true where attested
AttestationApplicationId package = com.dial.van
app signing certificate digest = expected owner build certificate
key public fingerprint not previously revoked
owner active-device slot available
```

StrongBox is preferred only if the actual S24 path is reliable; Android's own guidance notes StrongBox is more constrained and slower than ordinary hardware-backed Keystore. Do not make StrongBox a needless availability hazard.

## 31.10 Exact-phone binding

The exact device instance is identified operationally by the enrolled non-exportable public-key fingerprint.

Server state:

```text
owner principal
    ↓
ACTIVE owner_device_binding
    ↓
device_key_fingerprint = SHA256(SPKI(public key))
```

After binding:

```text
another S24 Ultra generates a different key → refused
emulator/software key → refused
copied APK → cannot prove possession of enrolled private key
copied bearer tokens → insufficient without device proof
```

Do not depend on IMEI/serial APIs. Android restricts privileged device-ID attestation, and this app does not need privileged device-owner powers merely to achieve one-phone binding.

## 31.11 Proof-of-possession request envelope

In addition to existing ingress/device tokens during transition, privileged requests carry a device proof.

Canonical input:

```text
device_id
device_key_id
unix_ms
nonce
HTTP method
canonical path
SHA256(body)
session_id if applicable
```

Sign:

```text
ECDSA P-256 / SHA-256
```

Headers or equivalent:

```text
X-Van-Device-Key-Id
X-Van-Device-Timestamp
X-Van-Device-Nonce
X-Van-Device-Proof
```

Gateway rejects:

```text
unknown key
revoked key
bad signature
expired timestamp
reused nonce
wrong device id
key not ACTIVE owner binding
```

Remote Browser stream grants include the bound device-key fingerprint so a bearer stream grant copied to another phone is unusable without matching device proof at signaling/session establishment.

## 31.12 Automated first-install provisioning

Create an installer workflow, for example:

```text
tools/android/provision_owner_s24.py
```

No owner form-filling.

Flow:

```text
1. verify connected ADB target is the intended installation target
2. verify APK signing certificate digest
3. Gateway admin endpoint creates:
       provisioning_id
       single-use bootstrap token
       expiry <= 5 minutes
       expected package/signing certificate
4. adb install -r owner build
5. installer launches dedicated provisioning entry point with the single-use token
6. app reads signed connectivity manifest
7. app requests attestation challenge from preconfigured Gateway
8. app generates hardware-backed key using challenge
9. app submits attestation chain + public key
10. Gateway validates attestation/application identity
11. Gateway atomically binds sole owner-device slot
12. Gateway returns device/session bootstrap material
13. app stores resulting tokens only in encrypted/private storage
14. bootstrap token is invalidated immediately
15. provisioning entry point becomes permanently unusable on this install
16. installer verifies `/v1/device-binding/status`
17. normal VAN launches
```

The bootstrap token is never committed to Git and need not be baked into the APK.

## 31.13 Provisioning entry-point hardening

If an exported provisioning Activity is needed so ADB shell can launch it:

- no broad implicit intent filters;
- no navigation or command execution;
- accepts only the expected provisioning payload;
- bootstrap token TTL <=5 min;
- server accepts one use;
- server refuses after owner-device slot is ACTIVE;
- Activity exits immediately when already provisioned;
- token never logged;
- task excluded from Recents;
- no screenshots if sensitive payload is visible;
- all authority comes from server validation, not from Activity export state.

## 31.14 Reinstall and recovery

Normal app update keeps app data/Keystore key and therefore keeps the device binding.

Uninstall/data-clear can delete app-private credentials and Keystore keys.

Recovery is deliberately **not** an in-app manual pairing screen.

Recovery requires an explicit administrative `REBOUND` workflow through the same physical/ADB deployment path:

```text
old binding → REVOKED
new hardware key → attested
owner-device slot → rebound
audit record → mandatory
```

The server never auto-binds a new key merely because the phone reports the same model.

## 31.15 Stable app signing identity is mandatory

PR #48 already identified unstable debug signing as an installation/upgrade problem.

Single-device production binding makes stable signing even more load-bearing.

Production/device-certification builds must use a stable owner-controlled signing identity.

The Gateway attestation policy pins the accepted signing-certificate SHA-256.

A differently signed build is refused even on the same physical S24.

## 31.16 Connectivity rotation

The app periodically checks an authenticated endpoint for a newer signed connectivity manifest.

Acceptance requires:

```text
signature valid
version > current
not-before satisfied
environment/deployment id matches
at least one trusted path remains
pin rotation contains overlap/current+next as required
```

If invalid:

```text
keep last known-good signed manifest
raise scoped degraded state
```

Never ask the owner to repair this by typing an IP address.

## 31.17 No WireGuard dependency

The production owner-S24 design does not require WireGuard/Tailscale.

The control/event paths use the signed direct Gateway/Hermes ingress configuration.

Browser media uses its independent WebRTC/ICE/TURN path.

If a future overlay network is introduced, it is an optional route implementation beneath `TransportSupervisor`, not a VAN product prerequisite.



## 31.18 No product flavor required

Rev 1.5 deliberately does **not** create `ownerS24` or any new flavor dimension.

Current repository build model remains:

```text
debug
release
```

Production owner behavior is tied to `release`.

Configuration source:

```text
android/app/src/release/res/raw/van_connectivity_manifest.json
```

Debug may retain developer-only manual overrides.

Release:

```text
no editable base URL
no manual pairing token
signed connectivity manifest required
stable owner signing certificate required
hardware-bound device proof required
```

This avoids multiplying the CI/build matrix merely to express an identity property that is already enforced cryptographically.

## 31.19 Physical S24 attestation preflight

Before freezing the production attestation policy, run a real-device preflight against the owner's actual S24.

Capture:

```text
key attestation certificate chain
attestation version
keymaster / KeyMint security level
hardware-backed / StrongBox result
verified boot state
deviceLocked where available
OS version
security patch level
AttestationApplicationId package name
app signing certificate digest
```

Write:

```text
artifacts/release/device-binding/s24-attestation-preflight.json
```

The preflight occurs **before** the one-active-device policy is locked.

## 31.20 Attestation fallback posture

No silent security downgrade is allowed.

Preferred acceptance:

```text
valid attestation chain
+
TrustedEnvironment or StrongBox-backed key
+
acceptable verified boot
+
expected package/signing certificate
```

If the real owner S24 cannot satisfy a required attestation property:

```text
DEVICE_BINDING_POLICY_BLOCKED
```

The implementation does NOT fall back automatically to:

```text
Build.MODEL
IMEI/serial
bearer tokens only
self-reported "hardware backed"
```

An alternative device-binding policy would require an explicit owner security exception/decision artifact and its own threat-model tests.

The browser vertical-slice engineering may continue in debug/development mode, but production owner-device certification remains blocked until the policy is resolved.

## 31.21 Current owner requirement supersedes prior local-voice decline

The new offline-voice decision artifact is not optional discovery.

It records a superseding owner instruction.

Implementation should not present this as a technology-selection request to the owner again.

Technology/model selection within that requirement remains evidence-gated.

# 32. DEPENDENCY GOVERNANCE




Create:

```text
registries/remote_browser_dependencies.json
```

No floating versions.

## 32.1 Android WebRTC

Official WebRTC Android development remains source-build oriented upstream. For a reproducible first pass, Rev 1.1 adopts the Maven Central precompiled `webrtc-sdk/android` distribution **only after digest/licence/source-revision verification**.

Current research candidate at blueprint revision time:

```text
io.github.webrtc-sdk:android:150.7871.01
```

The registry MUST record:

- Maven coordinate;
- artifact SHA-256;
- upstream Chromium/WebRTC source revision represented by the build;
- BSD/IP licence notices;
- supported ABIs;
- H.264 MediaCodec capability on the S24;
- result of a minimal decode/DataChannel canary.

If repository review rejects this donor, build from a pinned official WebRTC source revision on Linux. Do not fall back to `org.webrtc:google-webrtc:1.0.+`.

## 32.2 Android WebSocket

Adopt pinned OkHttp for realtime signaling/push.

Current research candidate:

```text
com.squareup.okhttp3:okhttp:5.5.0
```

The exact admitted version/digest is locked in the dependency registry after Gradle/Android compatibility verification.

Existing `HttpURLConnection` may remain for ordinary Gateway requests; Rev 1.1 does not require a wholesale network-stack rewrite.

## 32.3 Server/runtime dependencies

Record exact:

```text
Chromium build
Playwright
Stagehand
Browser Harness
GStreamer
capture plugins
x264/OpenH264 or hardware encoder stack
coturn
display/compositor
```

For every dependency record:

```text
version
source
digest
licence
architecture
adoption decision
runtime identity
```

## 32.4 Stagehand gate

Existing Stagehand adoption remains owner-gated.

Phase 7 cannot begin until:

```text
docs/decisions/VAN-ADOPT-STAGEHAND-001.yaml
```

is owner-approved and the live Stagehand runtime is certified.

Stagehand may not be treated as production-ready merely because code/adapters exist.



## 32.5 Offline voice runtime

Add Sherpa-ONNX to the dependency registry before implementation.

Official Sherpa-ONNX Android documentation supports local:

```text
speech recognition
VAD
keyword spotting
offline TTS
```

Pin exact native release and voice models.

The owner S24 release must contain or install from a VAN-controlled signed asset pack all voice assets required for offline operation.

## 32.6 HTTP/2/SSE fallback

If OkHttp remains the admitted Android network stack for the new session layer, also admit the SSE/event-stream component required by the selected implementation.

Do not hand-roll an unbounded line parser on the UI thread.

## 32.7 Transport endpoint registry

Create a deploy-time transport-path registry containing:

```text
path_id
protocol
endpoint
route_id
priority
certificate/pin policy
enabled
```

Endpoint changes must not require editing feature code.



## 32.8 PR #48 external-runtime maturity gates

At merged baseline the following are **not** live production workers merely because gateway adapters exist:

```text
Browser Harness worker
Stagehand worker
concrete WakeWordEngine
concrete LocalSecondPassAsr
```

Dependency admission and runtime installation must update the component ledger only after real producer→consumer→observable-effect evidence exists.

## 32.9 Existing owner decisions are not silently overwritten

Where PR #48 records a previous owner decision declining a runtime, Rev 1.3 implementation must create a new explicit owner decision rather than editing history.

This applies especially to the concrete offline voice runtime/model adoption.

# 33. REPOSITORY FILE PLAN





## Backend/Gateway

```text
backend/van_gateway/browser/interactive_models.py
backend/van_gateway/browser/interactive_service.py
backend/van_gateway/browser/control_lease.py
backend/van_gateway/browser/stream_grants.py
backend/van_gateway/browser/interactive_api.py

```

Modify existing:

```text
backend/van_gateway/app.py
backend/van_gateway/storage/db.py
backend/van_gateway/browser/api.py
backend/van_gateway/browser/service.py
backend/van_gateway/browser/policy.py
```

## Android

```text
android/app/src/main/java/com/dial/van/browser/**
android/app/src/main/java/com/dial/van/session/**
```

Modify existing:

```text
VanApplication.kt
VanGatewayClient.kt
CommandCentreActivity.kt
FloatingOverlayService.kt
VoiceInterfaces.kt or adjacent voice coordinator
AndroidManifest.xml
build.gradle.kts
```

## Deployment

```text
deploy/van-browser-stream/**
deploy/van-browser-stream/systemd/van-browser-streamd.service
```

## Config

```text
config/browser/streaming.yaml
config/browser/quality.yaml
```

Existing profile/domain files remain the policy authorities.

## Docs/evidence

```text
docs/decisions/VAN-ADOPT-REMOTE-BROWSER-STREAMING-001.yaml
docs/project-state/REMOTE_BROWSER_PREFLIGHT.md
docs/project-state/REMOTE_BROWSER_IMPLEMENTATION_MATRIX.json
docs/EXTERNAL_GATES.md
docs/PRODUCTION_ACCEPTANCE_LEDGER.md

artifacts/release/remote-browser/
```

---



## Rev 1.2 additions

### Gateway durable session

```text
backend/van_gateway/session/
    models.py
    service.py
    router.py
    api.py
    websocket.py
    http_stream.py
    resume.py
    health.py
```

### Android session layer

```text
android/app/src/main/java/com/dial/van/session/**
```

### Hardened local voice edge

```text
android/app/src/main/java/com/dial/van/voice/offline/
android/app/src/main/java/com/dial/van/voice/tts/
android/app/src/main/assets/voice/voice_asset_manifest.json
```

### Config

```text
config/transport/hermes_paths.yaml
config/voice/offline_voice.yaml
```

`hermes_paths.yaml` is deployment configuration, not owner authority; every path still terminates through approved Gateway authentication.



## 33.1 PR #48 files to MODIFY rather than duplicate

Android:

```text
android/app/src/main/java/com/dial/van/events/EventStream.kt
android/app/src/main/java/com/dial/van/events/PreferencesEventCursorStore.kt
android/app/src/main/java/com/dial/van/gateway/GatewayRetry.kt
android/app/src/main/java/com/dial/van/gateway/QueueReplayer.kt
android/app/src/main/java/com/dial/van/gateway/ReplayTrigger.kt
android/app/src/main/java/com/dial/van/queue/EncryptedCommandQueue.kt
android/app/src/main/java/com/dial/van/degraded/SubsystemSignals.kt
android/app/src/main/java/com/dial/van/voice/WakeListenerService.kt
android/app/src/main/java/com/dial/van/voice/WakeModelAsset.kt
android/app/src/main/java/com/dial/van/voice/WakeModelLoader.kt
android/app/src/main/java/com/dial/van/voice/VoiceInterfaces.kt
android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt
```

Backend:

```text
backend/van_gateway/events/bus.py
backend/van_gateway/storage/db.py
backend/van_gateway/browser/api.py
backend/van_gateway/browser/worker.py
backend/van_gateway/degraded/registry.py
backend/van_gateway/observability/instruments.py
backend/van_gateway/observability/metrics.py
```

Governance/evidence:

```text
docs/project-state/AUTHORITY_MAP.yaml
evidence/van-system-audit/component_ledger.json
evidence/van-system-audit/findings.json   # only for real audit findings, not as a planning checklist
docs/PRODUCTION_ACCEPTANCE_LEDGER.md
```

New files are introduced only for responsibilities with no current owner, such as the logical session/transport supervisor and the actual interactive media client.



## Rev 1.4 native-window / shortcut / provisioning additions

Android:

```text
android/app/src/main/java/com/dial/van/browser/BrowserMediaSessionManager.kt
android/app/src/main/java/com/dial/van/browser/BrowserWindowMode.kt
android/app/src/main/java/com/dial/van/browser/shortcut/BrowserShortcutManager.kt
android/app/src/main/java/com/dial/van/browser/shortcut/BrowserShortcutStore.kt
android/app/src/main/java/com/dial/van/browser/shortcut/BrowserShortcutActivity.kt
android/app/src/main/java/com/dial/van/browser/BrowserOpenActivity.kt

android/app/src/main/java/com/dial/van/security/OwnerDeviceIdentity.kt
android/app/src/main/java/com/dial/van/security/OwnerDeviceProvisioning.kt
android/app/src/main/java/com/dial/van/security/DeviceProofSigner.kt
android/app/src/main/java/com/dial/van/connectivity/ConnectivityManifest.kt
android/app/src/main/java/com/dial/van/connectivity/ConnectivityManifestVerifier.kt
android/app/src/main/java/com/dial/van/connectivity/ConnectivityRegistry.kt

android/app/src/release/res/raw/van_connectivity_manifest.json
android/app/src/main/res/xml/network_security_config.xml
```

Backend:

```text
backend/van_gateway/auth/device_binding.py
backend/van_gateway/auth/device_proof.py
backend/van_gateway/auth/provisioning.py
backend/van_gateway/connectivity/config.py
```

Deployment tooling:

```text
tools/android/provision_owner_s24.py
tools/android/verify_owner_device_binding.py
```



## 33.2 Canonical blueprint repository path

Rev 1.5 SHALL be stored in the repository at:

```text
docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md
```

If it owns any new invariant in `AUTHORITY_MAP.yaml`, that exact path must first be added to `owning_documents`.

Do not point the authority map at the downloadable `/mnt/data` filename.

## 33.3 Stream-host deployment package

Production streaming deployment lives under:

```text
deploy/van-browser-stream/
    README.md
    install.sh
    qualify.sh
    systemd/
    compositor/
    gstreamer/
    control-agent/
    coturn/
```

`deploy/van-trading-core/browser/` remains the Browser Fabric / Stagehand / Harness deployment package.

This directory split mirrors the locked host split in §13.

# 34. API SURFACE




Recommended Gateway endpoints:

```text
POST   /v1/browser/interactive-sessions
GET    /v1/browser/interactive-sessions/{session_id}
POST   /v1/browser/interactive-sessions/{session_id}/stream-grant
POST   /v1/browser/interactive-sessions/{session_id}/take-control
POST   /v1/browser/interactive-sessions/{session_id}/delegate-control
POST   /v1/browser/interactive-sessions/{session_id}/suspend
DELETE /v1/browser/interactive-sessions/{session_id}

GET    /v1/browser/interactive-sessions/{session_id}/tabs
GET    /v1/browser/interactive-sessions/{session_id}/downloads

```

The Browser Runtime signaling endpoint is a separate service, authenticated by `BrowserStreamGrant`.

---



## Rev 1.2 durable session APIs

```text
POST /v1/session/open
POST /v1/session/resume
GET  /v1/session/status
WSS  /v1/session/ws

POST /v1/session/messages
GET  /v1/session/events-stream
```

Existing:

```text
POST /v1/commands
GET  /v1/events
```

remain the compatibility/replay floor.

All command-like session messages are routed into the existing command authority path; the session API is transport, not a new authorization API.



## Rev 1.4 device/bootstrap/config APIs

Administrative/bootstrap plane:

```text
POST /v1/devices/bootstrap/create        # privileged deployment/admin only
POST /v1/devices/bootstrap/challenge     # single-use bootstrap token
POST /v1/devices/bootstrap/attest        # attestation + public key
GET  /v1/device-binding/status           # device-authenticated status
POST /v1/devices/rebind                  # privileged administrative recovery only
```

Connectivity:

```text
GET /v1/connectivity/manifest
```

This returns a newer signed manifest when available.

No public API allows an Android client to set arbitrary Gateway/Hermes URLs.

## Shortcut policy

Home-screen shortcut creation is local Android functionality and does not require a Gateway endpoint.

Opening a shortcut still uses normal interactive-session and device-authenticated Gateway APIs.



## 34.1 Realtime endpoint consolidation

The only full-duplex semantic session endpoint is:

```text
WSS /v1/session/ws
```

Do not implement any second realtime semantic endpoint.

REST event replay and HTTP/2 event streaming remain fallback carriers, not separate authorities.

# 35. FIRST-PASS IMPLEMENTATION ORDER

The implementation programme is now organized into one critical path plus parallel hardening tracks.

## Phase -1 — PR #48 closure-gate baseline

Before Phase 0 and after each closure group:

```text
python tools/ci/maturity_gate.py
python tools/ci/authority_map.py
python tools/ci/ledger_reconcile.py
python tools/audit/kotlin_reachability.py
```

Run mutation tests for changed load-bearing invariants.

No work proceeds from a pre-existing red baseline.

## Phase 0 — repository / authority / topology preflight

- resolve exact current `main`;
- read Project Truth / Security Policy / Authority Map;
- read current schema;
- revalidate canonical browser aliases;
- lock §13 dual-homed topology;
- create `deploy/van-browser-stream/`;
- select profile-storage implementation;
- define Browser Control Agent private mTLS contract;
- resolve next schema migration number;
- create implementation matrix + component refs;
- define owner-decision records;
- record exact dependency candidates.

**Exit gate:** no duplicated authority or unresolved host topology.

## Phase 0A — physical owner-S24 attestation preflight

Before freezing production device-binding policy:

- install/run preflight helper on actual S24;
- generate attested P-256 test key;
- inspect chain/security level/verified boot/app identity;
- record evidence;
- classify production binding policy as `SUPPORTED` or `BLOCKED`.

This does **not** block the debug remote-browser vertical slice if production binding is temporarily blocked.

## Phase 1 — Stream Host media/control proof

On the dedicated Browser Stream Host prove:

- Chromium;
- loopback CDP;
- Browser Control Agent;
- private mTLS call from Trading Core;
- compositor;
- capture;
- H.264;
- WebRTC;
- real public web page;
- media metrics.

**Exit gate:** Trading Core can privately control the same Chromium that streams to a reference client, with no public CDP.

## Phase 2 — minimum Gateway interactive-session authority

Implement only what the first device vertical slice requires:

- next schema migration;
- renewable profile lease;
- InteractiveBrowserSession;
- BrowserControlLease;
- stream grant;
- Gateway session APIs;
- minimal durable session identity.

## Phase 2A — minimum logical-session primitives for first frame

First-frame gate requires:

```text
RB-059 VanHermesSession identity
RB-066 resume handshake
RB-067 path_epoch fencing
```

It does **not** require full multipath route diversity, warm standby, store-and-forward or offline TTS.

**Exit gate:** one stable logical session can reconnect without creating a new command/session identity.

## Phase 3 — FIRST REAL S24 REMOTE-BROWSER VERTICAL SLICE

Implement:

```text
Browser entry from existing BrowserModules
BrowserActivity
native WebRTC client
SurfaceView renderer
address/search
real Oracle Chromium
tap
scroll
IME
viewport revision
basic reconnect
```

Use the real S24 and real dedicated stream host.

**Exit gate:**

```text
S24
 → authenticated session
 → real WebRTC
 → real Oracle Chromium
 → real internet page
 → owner tap/scroll/IME
 → visible resulting frame
 → measured evidence
```

This is the earliest meaningful product milestone.

## Phase 3A — native window behavior

After first-frame proof:

- split-screen;
- Samsung pop-up;
- responsive chrome;
- Activity-independent media session;
- continuous viewport resize;
- orientation/recreation;
- no session restart.

## Phase 4 — ordinary browser completeness

- tabs;
- loading state;
- browser audio;
- downloads;
- file upload;
- share/find/back behavior;
- quality UI;
- metered policy.

## Phase 4A — shortcuts/interoperability

- generic Browser shortcut;
- saved-page shortcut;
- shortcut revoke/update;
- safe Open-with-VAN http/https entry if adopted.

## PARALLEL TRACK B — connectivity resilience hardening

May begin once Phase 2A primitives exist.

Implement:

```text
WSS primary
HTTP/2 fallback
REST replay floor
TransportSupervisor
health scoring
warm standby
ACK-unknown command reconciliation
route diversity
store-and-forward
```

This track is **not** a prerequisite for Phase 3 first frame.

It IS a prerequisite for final production certification.

## PARALLEL TRACK C — offline voice hardening

May begin after Phase 0 owner-supersession artifact and can run concurrently with Phases 1–4.

Implement:

- admitted local voice runtime;
- local wake engine;
- phrase verification;
- local ASR fallback;
- local TTS backend;
- speech segments;
- cursor/dedupe;
- local barge-in;
- browser audio ducking.

This track is **not** a prerequisite for Phase 3 first frame.

It IS required for final voice/browser symbiotic certification.

## Phase 5 — realtime semantic-session completion

Converge Track B with the existing EventStream:

- `/v1/session/ws`;
- HTTP/2 event stream;
- REST replay;
- device-filtered event semantics;
- cursor resume;
- no second standalone realtime semantic endpoint.

## Phase 6 — voice/browser symbiosis

After Track C has a usable local voice edge:

- BrowserContextRef;
- voice-originated browser task;
- local speech result;
- barge-in;
- visual-state integration;
- transport failover during spoken result.

## Phase 7 — Stagehand/Harness same-session takeover

Entry prerequisites:

- owner-adopted Stagehand decision/live qualification;
- Browser Control Agent private path green.

Implement:

- Stagehand/Browser Harness on Trading Core;
- private control RPC to Stream Host;
- same-target actuation;
- control-generation fencing;
- owner preemption;
- Mission/evidence binding.

## Phase 8 — production owner-S24 zero-config provisioning

This is after attestation preflight and may be implemented earlier, but certification occurs here:

- signed release connectivity manifest;
- stable release signing;
- hardware-bound owner key;
- one-active-owner-device constraint;
- automatic ADB/bootstrap provisioning;
- no manual connectivity UI;
- second-phone refusal.

## Phase 9 — security / chaos / performance certification

Run:

- SSRF/DNS rebinding;
- gesture reordering;
- profile-lease expiry;
- transport failure;
- route failure;
- browser crash;
- stream-host crash;
- Gateway/Hermes outage;
- split/pop-up resize storm;
- metered/unmetered SLOs;
- voice failover;
- device-binding attacks;
- 30-minute soak.

## Phase 10 — exact-SHA closure

Only after all applicable tracks:

```text
maturity gate GREEN
authority map GREEN
ledger reconciliation GREEN
Kotlin reachability GREEN
mutation suite GREEN
CI GREEN on exact SHA
S24 device gates GREEN
external runtime gates GREEN
```

Update the component ledger through the §40 mapping; do not let the RB matrix overrule repository maturity truth.

# 36. TEST STRATEGY






## 36.1 Backend unit tests

At minimum:

```text
test_interactive_session_state_machine.py
test_interactive_profile_lease_renewal.py
test_interactive_profile_lease_expiry_mid_session.py
test_browser_control_lease.py
test_stream_grant_es256.py
test_stream_grant_rotation.py
test_stream_grant_replay.py
test_interactive_profile_policy.py
test_interactive_session_expiry.py
test_remote_browser_security.py
test_browser_session_mission_binding.py
test_realtime_delivery.py
test_realtime_device_filtering.py
test_realtime_resume.py
```

## 36.2 Input protocol contract tests

Must include:

- reliable DOWN delayed behind several fast MOVEs;
- fast DOWN received before reliable DOWN;
- fast UP received before reliable UP;
- MOVE arrives before any DOWN;
- MOVE arrives after UP;
- lost FAST_INPUT MOVE does not trigger reliable gap recovery;
- duplicate DOWN/UP is idempotent;
- newer gesture epoch cancels stale open gesture;
- server timeout synthesizes CANCEL;
- stale control generation rejects all actuation;
- old viewport revision rejects/withholds input.

## 36.3 Android unit tests

At minimum:

```text
CoordinateMapperTest
BrowserGestureStateTest
BrowserControlLeaseClientTest
HumanTakeoverControllerTest
RemoteInputContextTest
BrowserQualityControllerTest
MeteredNetworkPolicyTest
RealtimeCursorStoreTest
BrowserSessionRepositoryTest
BrowserTabReducerTest
BrowserDegradedStateTest
```

## 36.4 Instrumentation/device tests

Use the actual S24 for release certification:

- cold launch;
- connect;
- navigate;
- tap;
- form input;
- password field;
- fling scroll;
- pinch;
- rotate;
- tab open/close;
- audio;
- metered-network transition;
- download;
- upload;
- app background/foreground;
- process kill/restart;
- network switch;
- 10-second network loss;
- owner takeover from agent;
- voice query;
- TTS;
- barge-in.

## 36.5 Deterministic canaries

Use the explicitly allowlisted canary origin, never localhost.

Provide:

```text
/input
/scroll
/ime
/audio
/download
/tabs
/crash-recovery
```

External public websites are supplemental live canaries, not deterministic repository tests.



## 36.6 VAN⇄Hermes transport tests

Required:

```text
primary WSS healthy
WSS blocked, HTTP/2 fallback healthy
primary dies after command send before ACK
primary dies during response streaming
primary dies during approval wait
primary dies during speech segment streaming
fallback already warm
fallback cold
late packet from old path_epoch
duplicate event on two transports
event cursor gap/replay
same idempotency key + same digest
same idempotency key + different digest
all transports down → STORE_AND_FORWARD
recovery from STORE_AND_FORWARD
route A down + route B alive
protocol diversity without route diversity reports SINGLE_PATH
```

## 36.7 Offline voice tests

Required on S24:

```text
wake acknowledgement with network disabled
local VAD
Android local ASR
Sherpa local ASR
ASR fallback when Android recognizer unavailable
known VAN vocabulary
local TTS arbitrary answer
critical phrase playback
TTS with public internet blocked
barge-in latency
browser audio ducking
response segment dedupe
failover while speaking
failover while command submit is ACK-unknown
process death with response cursor
queued remote question expiry
delayed answer does not unexpectedly speak hours later
```

## 36.8 End-to-end voice/browser continuity canary

One mandatory scenario:

```text
1. Owner opens VAN Browser.
2. Owner says a fresh research question.
3. Local ASR produces transcript.
4. Hermes begins browser/web work.
5. Kill the primary Hermes control transport.
6. Fallback path resumes same logical session.
7. Browser work continues/reconciles.
8. Hermes produces response segments.
9. VAN speaks locally.
10. Owner barges in.
11. TTS stops locally.
12. New turn uses same durable session.
```

Acceptance:

```text
duplicate commands = 0
lost durable events = 0
repeated speech segments = 0
false success = 0
owner barge-in response p95 within target
```



## 36.9 PR #48 closure-gate tests

Add/extend contract tests proving:

```text
Remote Browser components cannot be marked integrated with no production caller.
New Kotlin Remote Browser classes are found by kotlin_reachability if orphaned.
Authority map rejects duplicate ownership of remote-browser/session invariants.
Ledger reconciliation catches a component still marked externally blocked after a real producer/consumer appears.
```

Mutation suite additions must include at least:

```text
remove Interactive Browser navigation entry
remove TransportSupervisor consumer
break queue replay trigger on connectivity recovery
make 409 retryable
make event cursor non-persistent
let worker self-report VERIFIED_SUCCESS
bypass wake-model readiness check
mark local TTS ready without device evidence
```

Every mutation must be caught by a named test/gate.



## 36.10 Multi-window / pop-up tests

Pure/unit/contract:

```text
window width → correct chrome mode
viewport revision never rewinds
resize coalescing bounded
stale viewport input rejected
Activity recreation does not create new browser session id
renderer detach/reattach preserves same media session
back uses Chromium history before Activity finish
```

Physical S24 instrumentation:

```text
full-screen portrait
enter split-screen
drag split divider repeatedly
rotate while split where OS permits
return full-screen
enter Samsung pop-up view
resize pop-up repeatedly
move pop-up
background/foreground pop-up
close/reopen presentation while bounded browser lease remains
```

Acceptance:

```text
unexpected page reloads = 0
duplicate browser sessions = 0
click-offset failures = 0
transport re-enrollments = 0
```

## 36.11 Home-screen shortcut tests

Required:

```text
generic browser shortcut pins
page shortcut pins
launcher confirmation cancellation is handled
shortcut contains no credential/token
page shortcut opens intended URL
malicious javascript: shortcut refused
file:/content:/intent: shortcut refused
revoked shortcut disabled
app update preserves shortcut target
lost device binding makes shortcut fail closed
```

## 36.12 Zero-config connectivity tests

On the production `release` build:

```text
no editable server URL in UI
no editable pairing token in UI
release refuses unsigned connectivity manifest
release refuses malformed manifest
release refuses unknown config signature
last-known-good survives bad update
all configured URLs require HTTPS/WSS as applicable
manual baseUrl mutation is unreachable from owner production UI
```

## 36.13 Single-S24 binding tests

Required backend/device tests:

```text
owner S24 first provisioning succeeds
same S24 normal app update succeeds
second Android phone with copied APK refused
second S24 Ultra model with copied APK refused
emulator/software attestation refused
wrong app signing cert refused
unlocked/unacceptable verified-boot state refused per policy
copied ingress/access tokens without device proof refused
replayed device-proof nonce refused
expired device-proof timestamp refused
revoked device key refused
uninstall/data-clear requires explicit administrative rebind
rebind revokes old key before new key activates
```

## 36.14 No-manual-configuration end-to-end canary

Start from:

```text
fresh owner-S24 install
no VAN prefs
no manually entered URL
no manually entered token
```

Automated installer provisions.

Expected owner experience:

```text
tap VAN
permissions/onboarding as required by Android
Browser available
Hermes session available
voice path available according to installed voice assets
no server/pairing configuration page
```



## 36.15 Phase-order regression test

Contract/document test must assert that the Phase 3 first-frame exit gate does not depend on:

```text
local TTS model selected
local ASR fallback certified
route-diversity certification
warm standby
```

Those are final-product requirements, not prerequisites for the first visual slice.

## 36.16 Attestation preflight test

Physical S24 preflight must record rather than assume:

```text
hardware key security level
StrongBox availability
attestation chain acceptance
verified boot state
device locked state where exposed
package/signing identity
```

If production binding policy is unsupported, test result is:

```text
BLOCKED_DEVICE_BINDING_POLICY
```

not an automatic downgrade.

# 37. PERFORMANCE CERTIFICATION


Create:

```text
tools/certification/certify_remote_browser.py
```

The tool SHALL emit:

```text
artifacts/release/remote-browser/
    runtime-identity.json
    network-path.json
    stream-quality.json
    input-latency.json
    recovery-canaries.json
    security-canaries.json
    device-canaries.json
    certification-summary.json
```

## 37.1 Component latency

Instrument:

```text
input captured on Android
input packet sent
input packet received
CDP dispatch complete
frame captured
frame encoded
RTP sent
RTP received
frame decoded
frame submitted to renderer
```

Use monotonic clocks.

Cross-device absolute times require clock calibration; do not subtract unsynchronized wall clocks.

## 37.2 Test-mode frame correlation

For deterministic latency canaries, add a debug-only test page and instrumentation path that correlates an `input_seq` with a visible frame change.

A practical debug method is:

- canary page changes a known small color block when receiving the input;
- debug `VideoSink` inspects the received frame before rendering;
- it detects the known color state;
- it correlates this with `input_seq`.

This gives a repeatable client-observed input-to-decoded-frame metric without OCR.

Do not ship the test overlay in release mode.

---



## 37.3 Rev 1.2 continuity evidence

Add:

```text
artifacts/release/remote-browser/
    hermes-session-paths.json
    hermes-failover-latency.json
    command-idempotency-canary.json
    event-replay-canary.json
    voice-offline-capabilities.json
    voice-asr-latency.json
    voice-tts-latency.json
    voice-barge-in-latency.json
    voice-failover-continuity.json
```

No “offline voice ready” claim is allowed without actual S24 evidence.

# 38. RED-TEAM MATRIX




The release suite SHALL cover at least:

1. replay BrowserStreamGrant;
2. use grant from second device;
3. expired grant;
4. grant signed by retired/rotated key;
5. unknown `kid`;
6. tampered session ID;
7. stale control generation;
8. agent input after owner takeover;
9. owner input during pending agent mutation;
10. malformed binary input;
11. oversized packet;
12. input flood;
13. fast MOVE before reliable DOWN;
14. fast MOVE after reliable UP;
15. lost unreliable MOVE;
16. duplicate gesture edge;
17. tab flood;
18. download flood;
19. navigation to localhost;
20. navigation to `169.254.169.254`;
21. unapproved private VCN target;
22. `file://` access;
23. privileged `chrome://`;
24. DNS rebinding;
25. page prompt injection;
26. page asks agent to reveal cookies;
27. page asks agent to raise action class;
28. password appears in logs;
29. cookies appear in evidence;
30. OTP appears in evidence;
31. Browser Runtime attempts internal-control endpoint;
32. Stagehand exceeds step budget;
33. Stagehand continues after control lease revocation;
34. payment attempt;
35. trading execution attempt outside VATI;
36. Chromium renderer crash;
37. Browser Stream Runtime restart;
38. Gateway restart;
39. Hermes unavailable;
40. mobile network loss;
41. packet reordering;
42. high jitter;
43. TURN fallback;
44. app process death;
45. device reboot;
46. stale session resume;
47. profile lease expires while pixels still flow;
48. profile lease renewal races a session close;
49. metered-network entry during active high-quality stream;
50. canary origin cannot reach blocked metadata/internal targets.

Every finding is:

```text
PASS
FAIL
BLOCKED_EXTERNAL
NOT_APPLICABLE_WITH_REASON
```

Never `assumed`.



### Rev 1.2 additional continuity attacks

Also test:

```text
old path sends command after new path_epoch committed
two transports race same command
fallback receives replay before live event
malicious/invalid session resume cursor
session resume from different device
replayed session-open proof
tampered response segment index
duplicate speech segment with different digest
speech segment arrives after owner barge-in
stale queued A4 command after reconnect
all route descriptors point to same physical endpoint
voice asset manifest tampered
ASR model missing
TTS model missing
Android system TTS loses offline voice data
browser audio refuses duck/focus
```



### Rev 1.4 owner-device / shortcut / windowing attacks

Also test:

```text
copy APK to another S24 Ultra
copy encrypted preferences to another handset
steal ingress token but not Keystore private key
reuse bootstrap token
use bootstrap after expiry
race two devices for owner-device slot
present valid hardware key from wrong package/signing cert
replace signed connectivity manifest with unsigned JSON
downgrade config_version
remove all trusted endpoint pins
force manual/baseUrl override in release
shortcut embeds javascript: URL
shortcut embeds file:// URL
shortcut attempts privileged internal URL
shortcut points to revoked profile
shortcut launch after device binding revoked
resize storm floods Gateway with viewport messages
stale viewport ack applied after newer ack
window recreation starts second PeerConnection
Samsung pop-up close leaves unbounded browser session
```

# 39. CI CHANGES



Extend `.github/workflows/van-ci.yml`.

Repository CI SHALL validate what CI can honestly prove:

- model/state tests;
- migration tests;
- grant cryptography;
- control arbitration;
- Android build/lint/unit tests;
- deterministic protocol tests;
- no secret logging tests;
- dependency-manifest validation;
- config schema.

CI SHALL NOT claim the real Oracle/WebRTC/S24 gate is green.

Live external certification remains separate and writes evidence.

A proposed CI job:

```text
remote-browser-contracts
    backend remote-browser tests
    realtime tests
    Android browser unit tests
    protocol schema compatibility
    dependency lock validation
```

A fail-closed test SHALL assert that production readiness is NOT `READY` without live runtime evidence.

---



## 39.1 PR #48 CI integration

Do not create a separate Remote Browser workflow that bypasses VAN's closure machinery.

Extend `.github/workflows/van-ci.yml`.

Remote Browser contract tests run **after**:

```text
Maturity gate
Authority map
```

and alongside:

```text
backend tests
contract tests
Kotlin reachability
ledger reconciliation
Android verification
Android build/lint
```

The existing debug APK artifact/signing-identity publication remains the path to the physical S24 gate.

CI still MUST NOT claim:

```text
Oracle streaming runtime READY
local wake model READY
local TTS audio VERIFIED
S24 browser latency CERTIFIED
```

without live external/device evidence.



## 39.2 Android variant policy

Rev 1.5 preserves the repository's existing build-type model:

```text
debug
release
```

No new product flavor/dimension is introduced.

CI implications:

- existing debug build/lint remains;
- add a release configuration-validation task that verifies the signed connectivity resource exists for release;
- production signing/device certification remains external to ordinary PR CI where secrets/keystore are unavailable;
- physical S24 acceptance uses the stable release-signed owner build.

`android/verification` continues to compile shared pure-Kotlin sources without a flavor explosion.

# 40. IMPLEMENTATION MATRIX

Create:

```text
docs/project-state/REMOTE_BROWSER_IMPLEMENTATION_MATRIX.json
```

It is a programme ledger, not the repository-wide maturity authority.

## 40.1 Required row shape

```json
{
  "schema": "van-implementation-matrix/1",
  "extension": "remote-browser/1.5",
  "id": "RB-001",
  "name": "...",
  "status": "NOT_STARTED",

  "built": false,
  "wired": false,
  "reachable": false,
  "live": false,
  "verified": false,
  "observed": false,
  "recoverable": false,
  "certified": false,

  "component_refs": [126],
  "ledger_expectation": "NON_TERMINAL",

  "producer": null,
  "consumer": null,
  "authority": "...",
  "evidence_refs": [],
  "tests": [],
  "external_gates": []
}
```

`component_refs` are component-ledger `n` identifiers.

A row may reference multiple components when the work item is an integration join.

## 40.2 RB status vocabulary

```text
NOT_STARTED
BUILT_UNWIRED
WIRED_UNPROVEN
LIVE_UNVERIFIED
VERIFIED_UNCERTIFIED
CERTIFIED
BLOCKED
DELIBERATELY_REMOVED
```

## 40.3 Explicit RB → component-ledger mapping

The component ledger has exactly these terminal states:

```text
INTEGRATED_AND_EVIDENCED
DELIBERATELY_REMOVED_CANON_CORRECTED
EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE
```

Mapping:

| RB status | Required component-ledger state |
|---|---|
| `NOT_STARTED` | component may be absent or present with `terminal_state = null`; MUST NOT be `INTEGRATED_AND_EVIDENCED` solely because this work is planned |
| `BUILT_UNWIRED` | referenced component row exists with `terminal_state = null`; maturity may be `STUB`, `PARTIAL`, `IMPLEMENTED_BUT_ISOLATED`, etc. |
| `WIRED_UNPROVEN` | referenced component row exists with `terminal_state = null`; producer/consumer may exist but runtime evidence/certification is incomplete |
| `LIVE_UNVERIFIED` | `terminal_state = null`; live actuation exists but the claimed product postcondition is not yet independently verified |
| `VERIFIED_UNCERTIFIED` | normally `terminal_state = null` until repository-wide maturity requirements are satisfied; external/device certification may still be missing |
| `CERTIFIED` | every referenced production component that the row claims complete MUST be `INTEGRATED_AND_EVIDENCED`, with non-null producer, consumer, production caller, tests and runtime evidence |
| `BLOCKED` | if repository implementation is complete and only an external/device/runtime dependency blocks use, referenced component MUST be `EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE`; otherwise keep `terminal_state = null` and describe the internal block |
| `DELIBERATELY_REMOVED` | referenced component MUST be `DELIBERATELY_REMOVED_CANON_CORRECTED`, with absence/canon evidence |

A programme row can never force a stronger component-ledger terminal state.

## 40.4 Ledger expectation field

Allowed values:

```text
NONE
NON_TERMINAL
INTEGRATED_AND_EVIDENCED
EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE
DELIBERATELY_REMOVED_CANON_CORRECTED
```

The row's `status` deterministically constrains `ledger_expectation`.

Example:

```text
CERTIFIED
    → INTEGRATED_AND_EVIDENCED

BLOCKED(repository complete; external runtime absent)
    → EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE
```

## 40.5 Reconciliation enforcement

Extend the existing:

```text
tools/ci/ledger_reconcile.py
```

or its directly-invoked library code to optionally read:

```text
docs/project-state/REMOTE_BROWSER_IMPLEMENTATION_MATRIX.json
```

and enforce:

1. every `component_ref` exists;
2. status→ledger mapping is valid;
3. `CERTIFIED` never references a non-terminal/external-block component;
4. external-block rows do not masquerade as certified;
5. deliberately-removed rows map only to the removal terminal state;
6. every `INTEGRATED_AND_EVIDENCED` reference has the five required evidence fields.

Add contract tests for every invalid combination.

Do not create a separate Remote Browser maturity authority.

## 40.6 Programme completion booleans remain useful

The nine booleans:

```text
built
wired
reachable
live
verified
observed
recoverable
certified
```

remain a finer-grained engineering ladder.

They do not replace the component-ledger terminal state.

## 40.7 Cross-cutting dimensions

Affected rows also carry:

```text
transport_independent: true|false
offline_voice_proven: true|false|null
```

These expose dependencies without changing maturity semantics.

# 41. MINIMUM WORK ITEMS





At minimum track separately:

```text
RB-001 canonical preflight
RB-002 owner streaming-host decision
RB-003 dependency admission
RB-004 schema migration 27
RB-005 renewable profile lease
RB-006 InteractiveBrowserSession
RB-007 BrowserControlLease
RB-008 P-256 BrowserStreamGrant + rotation
RB-009 Gateway session API
RB-010 dual-homed stream-host provisioning
RB-011 display/compositor
RB-012 capture pipeline
RB-013 H.264 encode
RB-014 Opus audio
RB-015 ICE/STUN
RB-016 TURN
RB-017 CDP input router
RB-018 cross-channel gesture state machine
RB-019 native Android WebRTC client
RB-020 remote viewport renderer
RB-021 coordinate mapping
RB-022 touch
RB-023 scrolling/fling
RB-024 IME
RB-025 orientation/viewport ack
RB-026 native address/search
RB-027 native tabs
RB-028 download broker
RB-029 phone upload
RB-030 metered-network policy/data counter
RB-031 reconnect
RB-032 app process recovery
RB-033 Chromium crash recovery
RB-034 realtime event migration/filtering
RB-035 realtime WebSocket client
RB-036 voice BrowserContextRef
RB-037 local TTS result integration
RB-038 barge-in
RB-039 visual-state arbitration
RB-040 Stagehand adoption/live gate
RB-041 Stagehand same-session attach
RB-042 control takeover
RB-043 owner preemption
RB-044 BrowserTask Mission binding regression proof
RB-045 InteractiveBrowserSession Mission binding
RB-046 evidence
RB-047 metrics
RB-048 quality adaptation
RB-049 SSRF/DNS-rebinding isolation
RB-050 profile secret isolation
RB-051 device-only authorization
RB-052 security red-team
RB-053 latency canary
RB-054 S24 device canaries
RB-055 production stream-host canaries
RB-056 soak test
RB-057 external gate update
RB-058 production acceptance closure
```

No item may disappear because an implementation agent chooses to defer it silently.



## Rev 1.2 cross-cutting work items

Track separately:

```text
RB-059 VanHermesSession model
RB-060 TransportPathDescriptor registry
RB-061 WSS primary transport
RB-062 HTTP/2 streaming fallback
RB-063 REST replay floor
RB-064 TransportSupervisor health scoring
RB-065 warm standby
RB-066 session resume handshake
RB-067 path_epoch fencing
RB-068 command ACK-unknown reconciliation
RB-069 encrypted durable outbox extension
RB-070 route-diversity certification
RB-071 session failover telemetry

RB-072 offline voice asset manifest
RB-073 Sherpa-ONNX Android runtime
RB-074 local VAD
RB-075 local ASR fallback
RB-076 transcript fusion/context bias
RB-077 LocalTtsRouter
RB-078 bundled local TTS model
RB-079 critical phrase bank
RB-080 semantic speech segmentation
RB-081 spoken-segment cursor/dedupe
RB-082 audio focus/browser ducking
RB-083 local barge-in
RB-084 delayed-answer speech policy
RB-085 offline voice S24 canary
RB-086 voice-through-failover canary
```



## Rev 1.4 work items

```text
RB-087 BrowserActivity explicit multi-window contract
RB-088 BrowserMediaSessionManager Activity-independent lifetime
RB-089 responsive compact/medium/expanded browser chrome
RB-090 continuous resize coalescer
RB-091 viewport revision atomic swap
RB-092 S24 split-screen certification
RB-093 S24 Samsung pop-up certification
RB-094 normal browser back/share/find behavior
RB-095 BrowserShortcutStore
RB-096 pinned generic browser shortcut
RB-097 pinned saved-page shortcut
RB-098 shortcut revocation/update
RB-099 safe Open-with-VAN http/https entry

RB-100 signed connectivity manifest
RB-101 connectivity manifest verifier
RB-102 immutable production connectivity registry
RB-103 hardware-backed owner-device identity
RB-104 Android key attestation verifier
RB-105 one-active-owner-device Gateway constraint
RB-106 request proof-of-possession
RB-107 single-use bootstrap provisioning
RB-108 automated ADB owner-S24 provisioning tool
RB-109 production manual-config removal
RB-110 signed connectivity rotation
RB-111 stable app-signing/device-binding gate
RB-112 second-device refusal canary
RB-113 owner-S24 reinstall/rebind recovery
RB-114 zero-manual-configuration acceptance canary
```



## Rev 1.5 consolidation work items

```text
RB-115 Browser Control Agent private VCN RPC
RB-116 Trading Core → Stream Host mTLS control path
RB-117 raw CDP loopback/public-exposure proof
RB-118 stream-host profile storage implementation
RB-119 RB→component-ledger reconciliation bridge
RB-120 S24 attestation preflight
RB-121 release-build immutable connectivity validation
RB-122 stale-contract/document contradiction guard
```

`ownerS24` product-flavor work item is intentionally absent; Rev 1.5 uses the existing `release` build type.

# 42. FIRST IMPLEMENTATION PASS RULES FOR OPUS / CHATGPT / CODEX






The implementation agent SHALL obey these rules.

## 42.1 Repository-first

Before changing code:

```text
git fetch
resolve actual current main
read PROJECT_CANONICAL_STATE.json
read PROJECT_TRUTH_PROTOCOL.md
read SECURITY_POLICY.md
read current Browser Fabric
read current implementation matrix
read current CI
read config/browser/profiles.yaml
read deploy/van-trading-core/README.md
read current schema version
verify Remote Browser dependency registry
```

The agent MUST explicitly verify the pinned Android WebRTC and OkHttp dependencies before writing Android transport code.

## 42.2 No parallel architecture

Before creating a new class/service/table, search for an existing owner.

Extend existing authority when one exists.

## 42.3 Vertical slices

Do not build many isolated abstractions before a real device path works.

The first real vertical proof is:

```text
S24
 → authenticated session
 → real approved public stream host
 → real WebRTC
 → real Oracle Chromium
 → real page
 → real touch
 → visible response
```

## 42.4 No fake adapters in acceptance

Mocks do not prove Oracle connectivity, WebRTC, Chromium rendering, media encode/decode, input, Stagehand takeover, reconnect or TTS.

## 42.5 No semantic completion inflation

Forbidden examples:

```text
"WebRTC integrated" because dependency exists.
"Browser complete" because a screenshot exists.
"Stagehand integrated" because an API responds.
"Low latency" because ping is low.
"Recovered" because systemd restarted.
```

## 42.6 Do not thin requirements

If the selected production host misses the 1080p60/latency target:

- record failure;
- tune;
- resize/change the dedicated host if justified;
- or seek an explicit owner-accepted product exception.

Do not expose `van-trading-core` publicly or lower the gate silently.

## 42.7 Test real consumers

For each producer ask:

```text
Who calls this?
From which production path?
What makes it reachable?
What proves the effect?
What happens on failure?
```

## 42.8 Update evidence with code

A pass that changes implementation without updating matrix/tests/evidence/docs is incomplete.

## 42.9 Review findings are closure gates

The implementation PR must include a checklist mapping B1–B5 and S1–S11 to:

```text
implementation refs
test refs
evidence refs
```

No finding may be closed by prose alone.



## 42.10 No feature-owned sockets

Android browser, voice, missions, approvals and notifications may not each create their own Hermes reconnect logic.

All semantic VAN⇄Hermes communication uses `VanHermesSessionManager`.

## 42.11 No cloud-only voice dependency

A change that makes:

```text
wake
ASR
TTS
barge-in
```

depend on internet is a regression even if cloud quality is higher.

## 42.12 Failover must be tested by killing the active path

Do not claim fallback because two endpoint classes exist in configuration.

Acceptance requires actively terminating/blocking the current transport during real work.

## 42.13 “Connected” is multidimensional

Implementation must report at least:

```text
local_voice_state
hermes_logical_session_state
active_control_path
standby_path_state
browser_media_state
Hermes_execution_state
```

One boolean `isConnected` is forbidden as the product truth model.



## 42.14 PR #48 anti-isolation rule

Before claiming any work item wired, perform a repository search/reachability proof for:

```text
constructor
producer
consumer
entry point
```

A class reached only from a test remains unintegrated.

## 42.15 Counterexample closure

For every Remote Browser closure ask:

> What counterexample would make all these tests green while the owner's requested real-world outcome is still false?

Add a test or external gate for that counterexample.

Examples:

```text
video frames arrive but touch does nothing
WebSocket fallback exists but every path uses the same dead route
TTS method is called but no sound reaches the S24 speaker
wake model file exists but no runtime consumes it
Stagehand adapter returns OK but no live browser changed
browser worker says completed but requested source was not found
```

If the counterexample still passes, the item is not closed.



## 42.16 Do not confuse pop-up view with VAN overlay

Samsung pop-up/freeform BrowserActivity and the floating VAN assistant overlay are different windows with different lifecycle/security behavior.

Do not implement the browser itself as a `SYSTEM_ALERT_WINDOW` overlay.

## 42.17 No manual-connectivity regression

An implementation that "solves" a failed connection by adding a text field for the owner to paste a URL/token is a product regression.

Connectivity repair belongs to:

```text
signed config rotation
transport failover
deployment/admin re-provisioning
```

## 42.18 Client-side model checks are defense-in-depth only

`Build.MODEL == "SM-S928B"` may be recorded as diagnostic/secondary gating.

It is never accepted as proof that this is the enrolled owner handset.

Server-enforced hardware-key proof is the binding authority.



## 42.19 Precedence / contradiction handling

If an implementation agent finds two normative passages that appear to conflict:

1. apply §0E precedence;
2. do not choose whichever is easier;
3. record the contradiction as a document defect;
4. implement the later explicit contract only.

## 42.20 Stream-host control path

Stagehand/Harness does not move onto the public media host unless a future owner-approved architecture revision says so.

Current Rev 1.5 contract:

```text
Stagehand + Browser Harness = private Trading Core
Chromium + media            = dual-homed Stream Host
cross-host control          = private mTLS Browser Control Agent
raw CDP                     = loopback only
```

## 42.21 First-frame priority

Do not block the first live S24 remote-browser vertical slice on unrelated final-certification work.

Minimum prerequisites are only those needed to make the slice safe and truthful.

Voice and multipath hardening continue concurrently and remain mandatory before final certification.

# 43. DEFINITION OF PRODUCTION COMPLETE





Remote Browser Rev 1.5 is production complete only when all of the following are true.

## Authority

- one authoritative Browser Fabric;
- no duplicate policy engine;
- no duplicate profile registry;
- no duplicate task system;
- owner device authentication enforced;
- one-time stream grants proven;
- owner touch preemption proven.

## Runtime

- actual Oracle Chromium runs;
- actual public web pages load through Oracle internet;
- actual H.264 stream reaches S24;
- audio reaches S24;
- real touch/scroll/IME reach Chromium;
- tabs sync;
- downloads work;
- reconnect works.

## Native experience

- no Linux desktop chrome visible;
- native Android browser chrome;
- native IME;
- orientation works;
- high-quality text;
- scrolling is comfortable;
- connection degradation is truthful.

## VAN symbiosis

- voice command can operate active session;
- Hermes analyses current page by server-side browser context;
- Stagehand acts on same visible browser;
- owner can take back control immediately;
- result arrives through realtime event path;
- VAN can speak concise result locally;
- barge-in works;
- visual state reflects real work.

## Governance

- Mission binding works without manual backfill;
- evidence is produced;
- Browser secrets never enter prompts/evidence;
- prompt injection remains untrusted;
- payments remain gated;
- VATI remains trading authority.

## Reliability

- app process death recovery;
- Chromium crash recovery;
- stream service restart recovery;
- network handoff recovery;
- stale lease protection;
- replay protection;
- soak test.

## Performance

- measured component latency;
- measured actual device FPS;
- measured encode load;
- measured network path;
- target SLOs green or an explicit owner-accepted exception exists.

## Certification

- CI green;
- live Oracle canaries green;
- S24 device canaries green;
- external gates updated;
- Production Acceptance Ledger updated;
- implementation matrix contains no hidden `BUILT_UNWIRED` item.

---



## VAN⇄Hermes continuity

- primary control/event path works;
- at least one protocol fallback works;
- path failover keeps the same logical session;
- ACK-unknown command reconciliation is proven;
- no duplicate consequential execution occurs;
- durable event replay is complete;
- stale path epochs are fenced;
- route-diversity status is truthful;
- STORE_AND_FORWARD state is proven.

## Offline voice

- wake acknowledgement is local;
- local ASR remains functional with public internet blocked;
- bundled/fallback local ASR is proven;
- arbitrary local TTS remains functional with public internet blocked;
- critical phrase bank is local;
- speech segment dedupe is proven;
- failover while speaking does not restart the answer;
- barge-in is local and within latency target;
- voice-originated fresh web question → Hermes/Oracle → local spoken answer canary passes.



## PR #48 repository-governance closure

Production complete additionally requires:

```text
maturity_gate.py GREEN
authority_map.py GREEN
ledger_reconcile.py GREEN
kotlin_reachability.py GREEN
relevant mutation suite GREEN
exact implementation SHA CI GREEN
```

Component ledger contains no Remote Browser component whose maturity claim is stronger than its evidence.

Any physical-device or external-runtime residual is named explicitly rather than hidden inside `CERTIFIED`.



## Native Android browser behavior

Production complete additionally means:

- Browser opens normally full-screen;
- S24 split-screen works;
- Samsung pop-up/freeform works;
- window resize does not restart the remote browser;
- browser chrome adapts cleanly to narrow window sizes;
- touch remains accurately mapped throughout viewport changes;
- home-screen browser shortcut works;
- saved-page shortcut works;
- launcher confirmation/cancellation is handled correctly;
- shortcut carries no credential.

## Owner-S24 zero-config binding

Production complete additionally means:

- all connectivity settings are preconfigured/signed;
- no production connectivity form exists;
- no manual pairing-token entry exists;
- first-install provisioning is automated;
- hardware-backed device key is enrolled;
- Gateway enforces one active owner-device key;
- copied APK on another phone is nonfunctional;
- copied tokens without device private key are nonfunctional;
- stable app signing identity is used;
- normal APK upgrade preserves binding;
- rebind is explicit, audited and administrative;
- direct VAN/Hermes control paths require no WireGuard.



## Stream/control topology

Production complete additionally requires:

- Stream Host public media interface proven;
- Stream Host private VCN interface proven;
- raw CDP proven loopback-only;
- Stagehand/Harness remains on private Trading Core;
- Browser Control Agent mTLS path proven;
- owner takeover/control-generation enforcement proven across the cross-host control path.

## Programme/ledger coherence

- every Remote Browser matrix row has valid `component_refs`;
- status→ledger mapping passes reconciliation;
- no `CERTIFIED` row points at an external-block/non-terminal component;
- no external runtime is laundered into a repository-complete claim.

# 44. RECOMMENDED FIRST RELEASE USER EXPERIENCE



When the owner taps **Browser**:

```text
1. VAN Browser opens instantly.
2. Native chrome renders locally.
3. A subtle "Connecting to VAN Browser…" state appears in the viewport.
4. Authenticated stream session is created.
5. Last approved browser profile opens.
6. Remote page appears.
7. Address/search input is immediately native.
```

When the owner searches manually:

```text
native text entry
 → Oracle Chromium navigation
 → Oracle internet
 → WebRTC frames
 → S24
```

When the owner says:

> “Van, compare this with what we already know.”

```text
local ASR
 → Hermes command
 → current BrowserContextRef
 → server-side DOM/source analysis
 → response pushed to S24
 → visual answer
 → local TTS
```

When the owner says:

> “Take over and find the original source.”

```text
Hermes requests control
 → control generation increments
 → Stagehand operates same visible tab
 → VAN visibly shows autonomous control
```

When the owner touches the page:

```text
owner touch
 → agent generation revoked
 → owner control restored
 → interaction continues
```

There is no conceptual break between “my browser” and “VAN's browser.” It is the same browser session with explicit, safe control arbitration.

---



## During a control-path failure

The owner should normally experience:

```text
VAN is speaking / researching
      ↓
primary WSS degrades
      ↓
fallback resumes same logical session
      ↓
speech/browser state continues
```

If failover completes before the local speech queue empties, there should be no audible restart and ideally no audible interruption.

A subtle diagnostic may say:

```text
Connection path changed
```

but the interaction itself remains continuous.

## When every Hermes path fails

VAN remains locally alive.

The owner can still say:

```text
"Hey Van"
```

and receive:

```text
"hie van"
```

Local commands and cached speech continue.

For fresh web reasoning VAN states that Hermes is unavailable and queues only policy-safe work.



## Normal Android windowing

The owner can use standard Samsung multitasking controls.

Example:

```text
VAN Browser full-screen
   ↓
Recents / app icon
   ↓
Open in split screen
   ↓
VAN Browser remains on same page/session
   ↓
owner opens another app beside it
```

Or:

```text
VAN Browser
   ↓
Open in pop-up view
   ↓
small movable/resizable browser window
   ↓
page remains live
   ↓
native address/keyboard/touch remain accurate
```

No special VAN "fake popup browser" is required.

## Add current page to Home screen

```text
⋮
Add to Home screen
   ↓
Android launcher confirmation
   ↓
page icon appears on owner home screen
```

Later:

```text
tap shortcut
   ↓
VAN validates bound S24 identity
   ↓
VAN Browser opens
   ↓
authenticated Oracle browser session opens/reuses
   ↓
saved page navigates
```

## First install

The owner should **not** see:

```text
Gateway URL:
Hermes host:
Pairing token:
TURN server:
Device ID:
```

The deployment flow has already provisioned those relationships.

Normal first-run UI is limited to owner-facing Android permissions/capability education and product onboarding.

## Wrong phone

If the owner APK is copied to another handset:

```text
app may install
    ↓
hardware identity does not match active owner binding
    ↓
Gateway/session access refused
    ↓
no browser/Hermes control capability
```

The UI states that this VAN build is not provisioned for that device.

It does not offer a pairing form.

# 45. ARCHITECTURAL NORTH STAR


The final system should be understood as three cooperating layers:

```text
1. VAN ANDROID
   owns presence, touch, voice, local UI and embodiment.

2. HERMES + VAN GATEWAY
   own meaning, authority, policy, missions, evidence and intelligence.

3. ORACLE BROWSER RUNTIME
   owns web execution, Chromium state, remote rendering and bounded browser actuation.
```

They are symbiotic because each layer does the work it is strongest at.

Android is not forced to become a cloud agent.
Hermes is not forced to become a video relay.
Stagehand is not forced into the owner's touch loop.
Chromium is not allowed to become an authority source.
The remote renderer is not allowed to invent VAN state.

That separation is what makes the system simultaneously:

- fast;
- native-feeling;
- secure;
- deterministic;
- recoverable;
- auditable;
- useful for both owner browsing and autonomous VAN research.

---



Rev 1.2 adds a fourth architectural principle:

```text
4. DURABLE SESSION / LOCAL VOICE EDGE
   owns continuity across transports and preserves owner interaction when
   individual network paths or public voice services are unavailable.
```

The relationship is:

```text
local voice remains alive
      +
durable VAN⇄Hermes semantic session
      +
independent Browser WebRTC media
      +
Oracle internet/web execution
```

This is the foundation for VAN feeling continuously present rather than behaving like a thin cloud client.

# 46. RESEARCH BASIS / IMPLEMENTATION REFERENCES



The design should be revalidated at implementation time against current upstream documentation, but the primary technical references behind this blueprint include:

1. **Android MediaCodec / low-latency decoding**  
   https://developer.android.com/reference/android/media/MediaCodec

2. **Chrome DevTools Protocol — Input domain**  
   https://chromedevtools.github.io/devtools-protocol/1-3/Input/

3. **WebRTC standard / RTCDataChannel and receiver behavior**  
   https://www.w3.org/TR/webrtc/

4. **Selkies design — Linux remote streaming, software/hardware encoding, WebRTC**  
   https://github.com/selkies-project/selkies/blob/main/docs/design.md

5. **Oracle Cloud Compute Shapes / Ampere A1**  
   https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm

6. **Current VAN repository authorities**  
   `PROJECT_CANONICAL_STATE.json`  
   `docs/PROJECT_TRUTH_PROTOCOL.md`  
   `docs/SECURITY_POLICY.md`  
   `docs/project-state/AUTOMATION_BROWSER_FABRIC_PREFLIGHT.md`  
   `backend/van_gateway/browser/*`  
   `android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt`  
   `android/app/src/main/java/com/dial/van/voice/VoiceInterfaces.kt`  
   `.github/workflows/van-ci.yml`

---



7. **Sherpa-ONNX Android — local ASR/TTS/VAD/KWS**  
   https://k2-fsa.github.io/sherpa/onnx/android/index.html  
   https://k2-fsa.github.io/sherpa/onnx/android/build-sherpa-onnx.html

8. **Sherpa-ONNX offline TTS model/runtime documentation**  
   https://k2-fsa.github.io/sherpa/onnx/c-api/html/tts.html



9. **Android Developers — Multi-window mode**  
   https://developer.android.com/develop/adaptive-apps/guides/support-multi-window-mode

10. **Android Developers — App resizability / Android 16 adaptive behavior**  
    https://developer.android.com/develop/adaptive-apps/guides/app-orientation-aspect-ratio-resizability

11. **Samsung Developer — Multi-window / pop-up view with resizable activities**  
    https://developer.samsung.com/codelab/galaxy-z/multi-window-copy-paste.html  
    https://developer.samsung.com/sdp/blog/en/2024/01/09/best-practices-of-app-development-for-various-screen-sizespowered-by-good-lock

12. **Android Developers — Pinned home-screen shortcuts**  
    https://developer.android.com/develop/ui/compose/system/shortcuts/creating-shortcuts

13. **Android Developers — Hardware-backed key attestation**  
    https://developer.android.com/privacy-and-security/security-key-attestation

14. **Android Open Source Project — Key/ID attestation, AttestationApplicationId**  
    https://source.android.com/docs/security/features/keystore/attestation

# 47. FINAL IMPLEMENTATION DIRECTIVE




The next implementation pass SHALL NOT begin by drawing the Browser screen.

It begins by locking the authority and wire contracts, proving the actual Oracle media path, and creating the first real end-to-end vertical slice on the S24.

The earliest meaningful milestone is not:

```text
BrowserActivity created
```

It is:

```text
authenticated Samsung S24
    ↓
native VAN Browser surface
    ↓
direct WebRTC session
    ↓
real Oracle Chromium
    ↓
Oracle internet
    ↓
real page rendered
    ↓
owner touch/scroll/IME
    ↓
real Chromium state change
    ↓
new frame visible on S24
    ↓
measured latency evidence
```

The second meaningful milestone is:

```text
owner voice
    ↓
Hermes
    ↓
same active browser
    ↓
Stagehand/Browser Harness
    ↓
verified web result
    ↓
same VAN UI
    ↓
local spoken response
    ↓
owner touches viewport
    ↓
immediate human control
```

Only after both paths are proven, hardened, recoverable and evidenced should Remote Browser be described as integrated.

This is the completion bar for VAN Remote Browser Rev 1.5.

---



Rev 1.2 adds a third mandatory proof:

```text
primary Hermes transport active
    ↓
voice question submitted
    ↓
kill/block primary transport
    ↓
fallback resumes SAME van_session_id / turn_id / command_id
    ↓
Hermes/Oracle completes fresh web work
    ↓
semantic response resumes
    ↓
S24 local TTS speaks answer
    ↓
no duplicate execution
    ↓
no repeated speech segment
    ↓
owner barge-in works locally
```

Remote Browser cannot be certified as symbiotically integrated while VAN's semantic/voice control depends on a single network socket or public cloud speech engine.



Rev 1.4 adds this mandatory owner-experience proof:

```text
fresh owner-S24 installation
    ↓
automated provisioning
    ↓
NO URL/token/pairing configuration
    ↓
open VAN Browser
    ↓
full-screen browsing works
    ↓
switch to split-screen
    ↓
same page/session continues
    ↓
switch to Samsung pop-up view
    ↓
resize repeatedly
    ↓
touch/IME stay aligned
    ↓
Add current page to Home screen
    ↓
launcher confirmation
    ↓
tap saved shortcut
    ↓
same bound S24 opens authenticated remote browser page
```

And the negative proof:

```text
copy same APK to another handset
    ↓
install
    ↓
attempt Gateway/Hermes/browser access
    ↓
REFUSED because hardware-backed owner-device key does not match
```

If either proof fails, Rev 1.4 is not production complete.



Rev 1.5 explicitly prioritizes **early vertical truth**:

```text
first:
    real S24
    real Stream Host
    real Chromium
    real page
    real touch

then in parallel:
    multipath resilience
    offline voice hardening
    zero-config production binding
    Stagehand takeover
```

Do not confuse "parallel hardening can finish later" with "optional." All required tracks still gate the final production certificate.

# 48. CURRENT DEPENDENCY RESEARCH NOTES



These are implementation-time observations, not timeless authority. The dependency registry remains the machine-readable authority once admitted.

- Upstream WebRTC Android documentation currently describes source checkout/build on Linux rather than a current official Maven release workflow.
- `webrtc-sdk/android` publishes precompiled WebRTC Android artifacts on Maven Central and currently documents `io.github.webrtc-sdk:android:150.7871.01` as a candidate.
- OkHttp currently documents `com.squareup.okhttp3:okhttp:5.5.0` as its current release candidate for admission.
- These coordinates MUST still pass VAN's own licence, digest, reproducibility, ABI and S24 H.264/DataChannel canaries before lock.

Rev 1.1 deliberately removes the implementation-agent freedom to choose an arbitrary WebRTC or WebSocket library during coding.



## Rev 1.2 voice note

Current Sherpa-ONNX official documentation describes Android support for local speech recognition and build targets for:

```text
SherpaOnnxTts
SherpaOnnxTtsEngine
SherpaOnnxVad
SherpaOnnxVadAsr
```

and states that Android speech recognition can operate without internet access.

Rev 1.2 uses this as the basis for dependency admission, not as proof that any specific model already meets the S24 latency/quality bar. Model selection remains evidence-gated.


## PR #48 merged-state note

The current repository truth at Rev 1.3 authoring is:

```text
main = 66e4e42a9e8994a0f3129fbda4c794b68b353120
schema = 26
version = 0.5.0-dev
```

The current repository already has robust shells and wiring for wake lifecycle, gateway retry, queue replay, event polling/cursor persistence and Browser administration surfaces.

The missing production work targeted by this blueprint is therefore primarily:

```text
live interactive remote-browser media/runtime
multipath logical VAN⇄Hermes session
concrete admitted offline wake/second-pass/TTS runtime
external Browser Harness / Stagehand runtime qualification
physical S24 evidence
```

Rev 1.3 is intentionally written around those remaining gaps rather than rebuilding what PR #48 already closed.



## Rev 1.4 platform note

Current Android/Samsung platform guidance supports the intended UX:

- Android supports split-screen/freeform participation for resizable activities.
- Samsung explicitly documents `android:resizeableActivity="true"` as enabling split-screen and pop-up/freeform view.
- Android pinned shortcuts support separate home-screen icons but launcher confirmation remains a platform-controlled user-consent step.
- Android Key Attestation can prove that a key is hardware backed, and its attestation application ID can bind the key to the package name and app signing-certificate digest.
- Device serial/IMEI attestation requires privileged device-owner/certificate-installer authority; Rev 1.4 deliberately does not depend on that. The unique enrolled hardware key is the exact owner-device identity.



## Rev 1.5 consolidation note

The Rev 1.4 expert review verified all original B1–B5/S1–S11 closures against repository state, then identified C1–C3 and D1–D8 document/integration issues.

Rev 1.5 resolves those without changing the fundamental product architecture.

The most material choices are now explicit:

```text
Stagehand/Harness host      = private Trading Core
Chromium/media host         = dedicated dual-homed Stream Host
cross-host browser control  = narrow private mTLS Browser Control Agent
raw CDP exposure            = loopback only

Android build variants      = existing debug/release only
owner production config     = src/release signed manifest
S24-only enforcement        = hardware-key/device-binding policy

realtime semantic socket    = /v1/session/ws only
durable replay              = /v1/events
HTTP fallback stream        = /v1/session/events-stream
```

# 49. PR #48 ALIGNMENT CHECKLIST

An implementation agent SHALL re-run this checklist against the live repository before coding.

```text
[ ] main still descends from PR #48 merge 66e4e42
[ ] current schema version re-read; next migration chosen dynamically
[ ] GatewayRetryPolicy reused, not duplicated
[ ] GatewayCircuitBreaker reused, not duplicated
[ ] EncryptedCommandQueue reused
[ ] QueueReplayer reused
[ ] ReplayTrigger reused
[ ] EventStream reused
[ ] PreferencesEventCursorStore reused
[ ] DegradedModeStore / SubsystemSignals extended
[ ] WakeListenerService reused
[ ] WakeCoordinator / WakeRuntimeController reused
[ ] WakeModelAsset / WakeModelLoader extended
[ ] Wake acknowledgement path reused
[ ] TtsOutputManager public speech path reused/refactored, not forked
[ ] BrowserModules is the owner-facing parent entry
[ ] existing BrowserTask/BrowserSessionBroker/BrowserPolicy remain authoritative
[ ] command→Mission exactly-once invariant preserved
[ ] independent verification required for success
[ ] correlation/evidence propagated into existing observability
[ ] AUTHORITY_MAP has one owner for every new invariant
[ ] component ledger updated with honest maturity
[ ] maturity gate green
[ ] authority map green
[ ] ledger reconciliation green
[ ] Kotlin reachability green
[ ] mutation suite covers new load-bearing invariants
[ ] exact SHA CI green
[ ] physical S24 gates recorded separately from CI
[ ] external Browser/Stagehand/runtime gates recorded separately from repository completion
```

If any box cannot be checked, Rev 1.3 implementation is not aligned with PR #48 and must stop at the appropriate `BLOCKED`/external-gate state rather than working around the merged architecture.


## Rev 1.4 owner-browser / S24 additions

```text
[ ] BrowserActivity explicitly resizable
[ ] no fixed BrowserActivity orientation
[ ] split-screen tested on owner S24
[ ] Samsung pop-up/freeform tested on owner S24
[ ] PeerConnection survives Activity recreation/window resize
[ ] viewport revisions prevent click-offset errors
[ ] browser UI remains usable in narrow pop-up
[ ] Add-to-Home-screen works
[ ] shortcut launcher cancellation handled
[ ] shortcut carries no credentials
[ ] safe http/https external open path, if enabled, rejects privileged schemes

[ ] production connectivity manifest signed
[ ] owner build exposes no editable Gateway/Hermes URL
[ ] owner build exposes no manual pairing token
[ ] stable app signing cert pinned in enrollment policy
[ ] hardware-backed P-256 device key generated
[ ] attestation challenge verified server-side
[ ] AttestationApplicationId package/signing cert verified
[ ] one-active-owner-device constraint enforced in database
[ ] every privileged request proves device-key possession
[ ] bootstrap token single-use and short-lived
[ ] automated ADB provisioning proven
[ ] copied APK on second phone refused
[ ] copied tokens without owner private key refused
[ ] normal app update preserves binding
[ ] uninstall/data-clear requires explicit audited rebind
[ ] no WireGuard dependency introduced
```


## Rev 1.5 consolidation checklist

```text
[ ] canonical blueprint stored at docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md
[ ] no stale ownerS24 flavor references remain
[ ] no legacy standalone realtime endpoint remains in implementation plan
[ ] no legacy standalone realtime backend package remains in implementation plan
[ ] Stagehand/Harness remains on private Trading Core
[ ] Stream Host is explicitly dual-homed
[ ] Browser Control Agent private mTLS RPC specified/implemented
[ ] raw CDP loopback-only test green
[ ] deploy/van-browser-stream package exists
[ ] profile storage location on Stream Host resolved
[ ] Phase 3 first-frame does not depend on offline voice certification
[ ] owner offline-voice supersession decision recorded
[ ] physical S24 attestation preflight recorded before policy lock
[ ] metered and unmetered SLOs evaluated separately
[ ] profile lease grace is cleanup-only
[ ] RB matrix component_refs valid
[ ] RB status → component-ledger mapping enforced by ledger reconciliation
[ ] no stale token+HMAC-only S24 binding text is implemented
[ ] no old viewport coordinate-transform rule is implemented
[ ] no migration-17 event text remains normative   # Rev 1.5.1 (§0F.3): was written "migration-27", which contradicts §5.6
```
