# Expert review — VAN Remote Browser Production Blueprint Rev 1.4

**Status:** Review. Not an authority document; it does not amend Rev 1.4, `docs/SECURITY_POLICY.md`, `docs/PROJECT_TRUTH_PROTOCOL.md`, `PROJECT_CANONICAL_STATE.json`, `docs/project-state/AUTHORITY_MAP.yaml`, `evidence/van-system-audit/component_ledger.json`, or any other locked authority.
**Reviewed document:** `VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_4_OWNER_S24_NATIVE_BROWSER.md` (Rev 1.4, 49 sections, 8138 lines), supplied by the owner. Supersedes Rev 1–1.3.
**Repository state considered:** `main` @ `66e4e42` (PR #48 merge, `0.5.0-dev`, `SCHEMA_VERSION = 26`).
**Prior review:** `docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_EXPERT_REVIEW.md` (B1–B5, S1–S11).
**Reviewed at:** 2026-09-19.

## Verdict

Rev 1.4 closes all sixteen findings from the Rev 1 review, and it closes them properly — with dispositions
that match the repository rather than paraphrases of the finding. That deserves to be said precisely, because
it is rare:

- the baseline SHA `66e4e42a9e8994a0f3129fbda4c794b68b353120` is real and is current `origin/main`;
- `SCHEMA_VERSION` is in fact 26, so §0C.3's correction from 17 to 27 is right, and its instruction to resolve
  the next unused version dynamically if `main` advances is righter;
- the `events` table at `66e4e42` is still `(seq AUTOINCREMENT, event_type, payload_json, created_at_unix)`
  with no `event_id` and no device column, so B5's premise still holds and §5.6's migration is aimed correctly;
- `PageLease` still carries a mandatory `task_id`, `DEFAULT_LEASE_SECONDS` is still 300 and there is still no
  renewal method, so B4's premise still holds;
- `config/browser/profiles.yaml` still declares exactly `public_research` and `authenticated_owner` with
  `profile_root: /var/lib/van-trading/browser/profiles`, and Rev 1.4 now uses those verbatim;
- **every one of the twenty-three repository files Rev 1.4 names in §33.1 and §2.7 exists**, including
  `tools/ci/maturity_gate.py`, `tools/ci/authority_map.py`, `tools/ci/ledger_reconcile.py`,
  `tools/audit/kotlin_reachability.py` and `tools/audit/mutation_suite.py`;
- all five `AUTHORITY_MAP.yaml` subjects §0C.4 warns against duplicating exist;
- and **§0C.2's component-ledger states are exactly right** — `WakeWordEngine`, `WakePhraseVerifier`,
  `SpeakerSimilarityScorer`, `LocalSecondPassAsr`, `TtsOutputManager.speak`, `Browser Harness worker` and
  `Stagehand worker` are all `EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE` in
  `evidence/van-system-audit/component_ledger.json`, while `SubagentWorker` and the adapter-backed browser
  worker are `INTEGRATED_AND_EVIDENCED`.

Two of the resolutions are better than what the review asked for. S1's duplicated gesture edges with
`(session_id, gesture_id, edge_id)` dedupe (§8.3) gets fast-path latency *and* reliable healing, where the
review only asked for a pointer state machine. B5's choice to keep a globally monotonic `seq` with
device-filtered visibility and `event_id` dedupe (§5.6), rather than introducing per-device sequences, preserves
`PreferencesEventCursorStore` and the live `EventStream` contract — and the legacy backfill
(`legacy-event:<seq>`, `created_at_unix * 1000`, `target_device_id = NULL`) is the right migration detail.

The remaining problems are a different and lesser class. Rev 1.4 was assembled by **appending** correction
registers and new sections rather than editing the original body, so several unedited Rev 1 passages now issue
normative instructions that the corrections reverse. Three findings are blocking; none requires re-architecting,
and two are document edits.

---

## Blocking findings

### C1 — Where Stagehand runs, and how it reaches Chromium, is now unresolved

This is the load-bearing consequence of moving the stream runtime off `van-trading-core`, and Rev 1.4 states
both halves without reconciling them.

§2.5 (unedited from Rev 1) still says Trading Core is the deployment home for Stagehand, Playwright and the
Browser Harness, and that the first implementation *"SHALL therefore extend the existing Trading Core Browser
Fabric"*. But §13.1 and §25.2 place a *"bounded Browser Harness/Stagehand attachment endpoint"* on the new
dedicated public Browser Stream Host — because Stagehand must drive the **same visible Chromium** the owner is
looking at (§22, ADR-RB-005), and that Chromium is now on the stream host.

Chromium can only be on one host. §31.3 forbids exposing CDP publicly or through a public NSG. So exactly one
of these must be written down:

1. **Stagehand and the Harness move to the stream host** — then §2.5 is wrong, and Phase 7's entry conditions
   and §31.1's authority list both change (the stream host would then hold Stagehand's scope and step budgets).
2. **They stay on Trading Core and reach CDP over a private VCN path** to the stream host — then the stream
   host is dual-homed, and §15.3 must say so explicitly rather than only listing public ingress.
3. **The stream host is dual-homed** with a public media/signalling NIC and a private VCN NIC carrying CDP,
   Gateway control and Harness attachment.

(3) is almost certainly correct: it satisfies §15.3's *"private control connections to Gateway/Hermes remain on
VCN/internal paths"*, keeps CDP off the public interface per §31.3, and lets §31.1's authority split hold. But
it is currently implied by three sections and stated by none, and an implementation agent has no way to choose.
Pick one, state it in §13.1, and make §2.5 say what remains true — that Trading Core is the home of the Browser
*Fabric authority* (profiles, domain policy, task service), not of the media runtime.

The stale deploy path compounds this: §33 still lists `deploy/van-trading-core/browser/streaming/**` as the
streaming service's home, which puts the new host's install scripts, systemd unit and GStreamer pipelines inside
the private host's deployment package. Move it to something like `deploy/van-browser-stream/**`.

### C2 — The `ownerS24` product flavor does not exist, and creating it is not in the plan

Rev 1.4's entire zero-config and device-binding contract is expressed as a **build flavor** distinction:

- §0D.2 forbids connectivity fields in "the owner production build";
- §31.8 splits behavior explicitly between "debug/developer build" and "ownerS24 production build";
- §33 names `android/app/src/ownerS24/res/raw/van_connectivity_manifest.json`;
- §36.12's tests run "on owner production flavor".

`android/app/build.gradle.kts` at `66e4e42` contains **no `productFlavors` and no `flavorDimensions`**. There is
one source set. Introducing a flavor dimension is not a line in a Gradle file — it multiplies every variant,
changes the `android-and-visual-evidence` CI job, changes which APK §39.1 publishes as the path to the physical
S24 gate, and interacts with `android/verification` (a separate pure-Kotlin JVM module that today compiles
against a single source set).

Neither Phase 0 nor Phase 0C lists it. §33's bare "Modify existing: build.gradle.kts" is the only trace. Add
flavor creation as an explicit Phase 0C work item with its CI and signing consequences named — §31.15 already
establishes that signing identity is load-bearing here, and a new flavor is exactly where an unstable signing
identity re-enters.

### C3 — §40.1's ledger mapping is undefined, and `ledger_reconcile.py` will enforce the gap

`evidence/van-system-audit/component_ledger.json` declares:

```json
"terminal_states_allowed": [
  "INTEGRATED_AND_EVIDENCED",
  "DELIBERATELY_REMOVED_CANON_CORRECTED",
  "EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE"
]
```

and its rule: *"A component is complete only when terminal_state is set AND, for INTEGRATED_AND_EVIDENCED,
producer/consumer/production_caller/tests/runtime_evidence are all non-null."*

§40 defines seven Remote Browser statuses — `NOT_STARTED`, `BUILT_UNWIRED`, `WIRED_UNPROVEN`, `LIVE_UNVERIFIED`,
`VERIFIED_UNCERTIFIED`, `CERTIFIED`, `BLOCKED` — **none of which is one of the three**. §40.1 then requires that
an RB row reaching `CERTIFIED` have "compatible terminal states" in the component ledger, without saying what
maps to what.

§40.1's *intent* is right and its prohibition is the best sentence in the section (an RB row cannot call a
component `CERTIFIED` while the ledger says `EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE`). But Phase 10 runs
`ledger_reconcile.py`, and without a declared mapping table there is nothing for it to check against. Write the
table into §40.1: which RB statuses require which ledger terminal state, and which RB statuses require the
ledger's five non-null evidence fields.

---

## Significant findings

### D1 — Five unedited sections now contradict the corrections that supersede them

Rev 1.4 says *"No implementation agent may re-open any of these choices implicitly"* (§0A) — but the original
body still states the superseded choices as normative text:

| Line | Stale text | Superseded by |
|---|---|---|
| 540 | *"If benchmarks later prove that video encoding requires a dedicated compute/GPU shape, runtime placement **may change**"* | §25.5: *"Rev 1's promotion gate is moved to Phase 0"* — this is precisely the late-contingency framing Rev 1.4 abolished |
| 2114 | §9.5's device binding: paired token + device HMAC + server allowlist | §0D.3, ADR-RB-025, §31.10: hardware-backed non-exportable P-256 key, proof-of-possession, `Build.MODEL` explicitly insufficient |
| 2431 | §11.1: *"60 Hz MotionEvent sampling"* | §8.7 (S10): retain historical samples for velocity, coalesce outbound per frame |
| 2494 | §12.2: input for an unacknowledged viewport is *"withheld **or transformed deterministically**"* | §8.1 (S7): *"Old/unacknowledged viewport revisions are **rejected**… does not allow coordinate transformation across Chromium reflow"*, and §12.5 |
| 3492 | §20.13: *"Rev 1.1 **migration-17** event semantics remain"* | §0C.3: migration is **27** |

§9.5 is the one that matters most: an agent implementing "S24 binding" from §9 would build the HMAC-and-allowlist
scheme that §31.10 says is insufficient, and §36.13's "copied tokens without device proof refused" test would
then fail against the code §9.5 told it to write.

A document of 8138 lines with four appended correction registers will keep accumulating these. The cheap fix is
one precedence clause near the top — *"where §§0A–0D conflict with §§1–49, §§0A–0D govern"* — plus in-place
edits of these five. The expensive fix is a clean Rev 2. Either is fine; leaving both texts as normative is not,
because it is the documentation-contradiction class `AUTHORITY_MAP.yaml` was built to eliminate.

### D2 — Two realtime sockets and two backend packages for one concern

§34 lists both `WSS /v1/realtime` (line 5914, the Rev 1 endpoint) and `WSS /v1/session/ws` (line 5929, the Rev
1.2 durable-session endpoint). §33's file plan lists both `backend/van_gateway/realtime/{models,service,api}.py`
and `backend/van_gateway/session/{models,service,router,api,websocket,http_stream,resume,health}.py`. §20
describes only the session layer.

That is two packages, two sockets and two sets of models for one concern, in a document whose ADR-RB-009 forbids
a third source of truth and whose §42.2 says to find the existing owner before creating a new one. Phase 5 then
asks for a WSS implementation that Phase 2A already built.

Either delete `/v1/realtime` and `backend/van_gateway/realtime/**`, or state that `/v1/realtime` is a Phase 5
stepping stone superseded by `/v1/session/ws` — and if the latter, Phase 5's exit gate should say the stepping
stone is removed, not left behind.

### D3 — The critical path tripled and the phase order did not

Rev 1 tracked 50 work items. Rev 1.4 tracks 114 (RB-001…RB-114), adding a multipath transport stack
(RB-059…071), an offline voice runtime (RB-072…086) and a device-attestation/provisioning programme
(RB-100…114). Phases 2A and 2B are inserted **before** Phase 3.

Read literally, the S24 cannot render its first remote page until a Sherpa-ONNX offline voice runtime is
selected, benchmarked, bundled and certified (Phase 2B's exit gate is a spoken answer with public internet
blocked). Nothing in the browser vertical slice consumes local ASR or TTS. This contradicts §42.3 (*"Do not
build many isolated abstractions before a real device path works"*) and §47's own statement of the earliest
meaningful milestone, which is a rendered page and a touch — not a spoken answer.

Recommend: gate Phase 3 only on the session primitives it actually consumes — session identity, resume and
path-epoch fencing (RB-059, RB-066, RB-067) — and run Phase 2B's offline voice work in parallel with or after
Phase 3. That keeps §0B's invariant intact (features bind to the logical session, not a socket) without making
a TTS model selection the blocker for the first frame on the S24.

### D4 — Offline voice reverses a recorded owner decision; say so in those words

ADR-RB-020 and §21.29 correctly note that PR #48 records an earlier owner decision declining to build Sherpa,
correctly refuse to edit that history, and correctly require a new adoption artifact
(`docs/decisions/VAN-ADOPT-OFFLINE-VOICE-RUNTIME-001.yaml`). Good.

But §21.29 frames it as *"a new product requirement"*. It is a **reversal of a recorded owner decision**, which
under `PROJECT_CANONICAL_STATE.json → policy.agent_self_authorization_forbidden` and
`policy.owner_instruction_is_project_truth_authority` is a materially different thing to put in front of the
owner. One sentence, stated plainly, so the owner is signing what they are actually signing.

### D5 — No stated posture for the owner's S24 failing attestation

§31.9 requires `security level >= TrustedEnvironment`, an accepted attestation root, acceptable verified-boot
state and `deviceLocked = true where attested`. §31.14 then removes in-app recovery **by design** — recovery is
an administrative ADB rebind only.

If the owner's actual handset fails any of those checks at provisioning time, Phase 0C's exit gate hard-blocks
the entire programme on a device property nobody has measured. §31.9's caution about StrongBox being "more
constrained and slower" shows the right instinct but does not cover the failure case.

Add a Phase 0C pre-check that dumps the real S24's attestation chain, security level and verified-boot state
**before** the binding design is locked, and state the fallback posture if a required property is absent.

### D6 — The metered default is designed to miss the SLO table, and nothing says so

§27.2 sets the metered default at 720p-class, 30–45 FPS, ~1.5–3 Mbps. §26.1 sets a production SLO of
*"Android decoded/rendered FPS >= 55 p95 during active browsing"*, and §43 requires *"target SLOs green or an
explicit owner-accepted exception"*.

On cellular the product is deliberately below the SLO. As written, every metered certification run reads as a
failure, which is exactly the kind of pressure that produces a quietly lowered gate — the thing §42.6 forbids.
State that §26.1 applies to unmetered sessions and give metered sessions their own target set.

### D7 — Minor: the lease grace window is ambiguous

§5.3 gives TTL 120 s, heartbeat 20 s, renew at <80 s remaining, and *"expiry grace for cleanup: 30 seconds"* —
then says that on expiry the runtime *"MUST stop accepting owner or agent input immediately"*. Whether the 30 s
grace extends actuation (it must not) or only cleanup and reconnect (it should) decides what
`test_interactive_profile_lease_expiry_mid_session.py` asserts. One word.

### D8 — Minor: the blueprint has no repository path

§33 lists the decision artifact, preflight, matrix, external gates and acceptance ledger, but never says where
Rev 1.4 itself lives in the repository. §0C.4 requires adding it to `AUTHORITY_MAP.yaml → owning_documents` if
it is to own any invariant subject, and `authority_map.py` *"refuses an entry whose owner, implementation or
test does not exist"*. Name the path in §33.

---

## What Rev 1.4 gets right

**It closed the findings with repository facts, not prose.** B3 uses the two aliases that exist and keeps
`/var/lib/van-trading/browser/profiles`, explicitly forbidding the `/var/lib/van-browser/...` relocation Rev 1
invented. B4's `holder_kind`/`holder_id` with `task_id` retained as a compatibility field is the
backward-compatible shape, and the six-step expiry behavior (input stops, no Stagehand action, reacquire before
actuation resumes, terminate if reacquisition fails) is the correct fail-closed ordering.

**§8's input protocol is now complete and testable.** Three sequence spaces (§8.5), duplicated edges with
`edge_id` dedupe (§8.3), a per-pointer server state machine with a bounded ≤8 ms buffer for an early MOVE
(§8.4), and §36.2's eleven named ordering tests — including "fast MOVE before reliable DOWN" and "lost
FAST_INPUT MOVE does not trigger reliable gap recovery". That is a protocol someone can implement and falsify.

**§0C's integration with PR #48's machinery instead of around it.** Reusing `GatewayRetryPolicy`,
`GatewayCircuitBreaker`, `EncryptedCommandQueue`, `QueueReplayer`, `EventStream` and
`PreferencesEventCursorStore` rather than building a second outbox and a second reducer, with §33.1 listing
files to *modify* rather than duplicate, is what ADR-RB-009 actually means in practice.

**§40.1's prohibition.** *"The implementation matrix cannot override `EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE` by
calling the same component `CERTIFIED`."* That single sentence prevents a planning document from laundering a
maturity claim, which is the exact failure PR #48 was built to eliminate. (It needs the mapping table of C3 to
be enforceable, but the rule is right.)

**§42.15's counterexample closure.** *"What counterexample would make all these tests green while the owner's
requested real-world outcome is still false?"* — with examples including "video frames arrive but touch does
nothing", "WebSocket fallback exists but every path uses the same dead route" and "TTS method is called but no
sound reaches the S24 speaker". This is the best paragraph in the document and should survive verbatim into
every future revision.

**§0B's PROTOCOL_DIVERSITY / ROUTE_DIVERSITY / LOCAL_CONTINUITY distinction**, with `MULTIPATH_HEALTHY`
claimable only when two independently reachable paths are proven live and `SINGLE_PATH` reported otherwise.
§36.6's "protocol diversity without route diversity reports SINGLE_PATH" test makes it real rather than
aspirational.

**§31.10 and §42.18.** Binding to the enrolled non-exportable key fingerprint, explicitly refusing
`Build.MODEL == "SM-S928B"` as proof, and explicitly declining to depend on IMEI/serial attestation that would
require privileged device-owner authority. §36.13's "second S24 Ultra model with copied APK refused" is the test
that proves the distinction.

**§32.1's handling of the WebRTC supply chain.** Naming `io.github.webrtc-sdk:android:150.7871.01` as a
*candidate* pending digest, licence, source-revision and S24 H.264/DataChannel verification, with an explicit
fallback to a pinned official source build and an explicit prohibition on `org.webrtc:google-webrtc:1.0.+`.

**§42.9.** *"Review findings are closure gates… No finding may be closed by prose alone"*, with a required
B1–B5/S1–S11 checklist mapping each to implementation, test and evidence refs. This review's own findings should
be held to the same rule.

---

## Recommended disposition

1. Resolve **C1** as one architecture sentence in §13.1 (dual-homed stream host is the likely answer), fix §2.5
   to scope Trading Core to the Browser Fabric authority, and move the §33 deploy path off
   `deploy/van-trading-core/`.
2. Add **C2** (the `ownerS24` flavor, with its CI and signing consequences) as an explicit Phase 0C work item.
3. Write **C3**'s RB-status → ledger-terminal-state mapping table into §40.1 before Phase 10 depends on it.
4. Close **D1** with a precedence clause plus in-place edits of the five stale passages — §9.5 first.
5. Resolve **D2** by deleting one of the two realtime stacks.
6. Put **D3** (phase resequencing) and **D4** (the offline-voice decision reversal) to the owner as decisions,
   not as implementation details.
7. **D5**–**D8** are closable inside the document.

Rev 1.4's core programme, RB-001…RB-058, is ready to implement once C1–C3 and D1 are closed. The Rev 1 review's
sixteen findings are genuinely closed, and the parts of this document that were right in Rev 1 — §0's nine
states, ADR-RB-006, §5.4's control generation, §22.3's preemption, §31.4's untrusted page content, §39's refusal
to let CI claim a device gate — survived the expansion intact.
