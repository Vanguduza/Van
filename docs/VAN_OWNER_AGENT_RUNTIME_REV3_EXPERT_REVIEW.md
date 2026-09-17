# Expert review — VAN Deterministic Owner-Agent Runtime Architecture Rev 3

**Status:** Review. Not an authority document; it does not amend Rev 3, `docs/SECURITY_POLICY.md`, or any locked authority.
**Reviewed document:** `VAN_CANONICAL_OWNER_AGENT_RUNTIME_ARCHITECTURE_REV3.md` (Rev 3.0, 37 sections, 4740 lines), which consolidates and supersedes Voice Rev 2 as its §30.
**Repository state considered:** `main` @ `a6756df`, plus `2fc93e8` (VATI stack lock 5.1 — cTrader sender gate, credential commands fenced from agents) and `db0e988` (live VAN ingress certification).
**Reviewed at:** 2026-09-16.
**Supersedes:** the Rev 2-scoped review previously committed on this branch. Voice Rev 2 is embedded verbatim as Rev 3 §30, so every finding against it is carried forward here under its Rev 3 section number.

## Verdict

Rev 3 is a significant intellectual step up from Rev 2. The execution contract in §0 — that VAN
distinguishes `understood`, `planned`, `submitted`, `executed` and `verified-complete`, and may claim
an external mutation only when declared postconditions verify — is the single most valuable idea in
either document, and it is exactly the discipline VAN's existing ledger and attestation culture
already applies to itself. The authority hierarchy (§3.3), epistemic fact states (§3.1), the
contradiction engine (§12), idempotency and checkpointing (§19–§20), and the insistence that
GraphRAG is selective rather than canonical memory (§8) are all correct and worth building.

The problem is that Rev 3 is much more ambitious than Rev 2 in a specific direction that the document
never confronts: **it moves planning, policy, execution, research and learning onto the device**, and
it does so in a repository whose locked security policy says in as many words that Android does not
form an independent VAN agent loop. Rev 3 never states where its seven planes run. That single
omission is the source of the four most serious findings below, and it is not a detail that can be
settled during implementation — it determines the credential model, the network surface, the
authorization model and the battery budget all at once.

The second structural problem is that consolidating Rev 2 by paste rather than by merge has left the
document with **two mutually contradictory action-class taxonomies inside itself**, on top of the
canonical one it already conflicts with.

Seven findings are blocking. All Rev 2 findings survive verbatim and are restated in §30 terms.

---

## Blocking findings

### B1 — Rev 3 places an agent runtime on Android; `SECURITY_POLICY.md` says Android is not one

`docs/SECURITY_POLICY.md` — a locked authority per `PROJECT_CANONICAL_STATE.json →
canonical_state.locked_authorities` — states:

> Hermes profile `van` is the sole agent runtime. Android, the gateway, Gemini Live, Deep Research,
> Antigravity, Jules, Workspace Studio and other provider surfaces do not form independent VAN agent
> loops.

The existing implementation honors this. `VoiceInterfaces.kt` carries the comment "Does not embed an
agent loop — transcripts are enqueued for Hermes dispatch upstream," and the device path is
`EncryptedCommandQueue` → `QueueReplayer` → gateway.

Rev 3 §29 puts `AdaptiveCommandResolver`, `IntentClassifier`, `OwnerLanguageModel`, `ActionPlanner`,
`ActionPolicyEngine`, `ExecutionRuntime`, `ResearchRuntime`, `ExaAdapter` and `OwnerLearningEngine`
under `android/app/src/main/java/com/dial/van/`. §2's plane diagram has the device resolving intent,
compiling a typed action DAG, authorizing it, executing against Google, NotebookLM, Hermes, Trading
and Browser adapters, verifying postconditions and learning from outcomes. §16's worked example has
VAN autonomously researching, patching an artifact, running validation and creating a commit. §17
grants `AUTO_EXECUTE` to research and `EXECUTE_UNDER_POLICY` to "repository implementation work".

That is an independent agent loop, on Android, by any reading. Rev 3 does not acknowledge the
conflict, and §0 describes VAN as "an owner-specific execution agent **and** Hermes bot" without
resolving which surface hosts which plane.

This is not a naming quibble. The answer determines: where the Exa credential lives (B4), whether
`TradingActionAdapter` is a second order sender (B3), whether model inference happens on-device or
via Hermes, what the device battery and memory budget must cover (M3), and whether the owner's
context graph leaves the phone at all.

**Required correction.** Add a deployment-locus table to §2: for each of the seven planes, state
whether it runs on Android, in the gateway, or in Hermes profile `van`, and which cross-boundary
protocol carries it. If the intent is genuinely to run planning, policy and research on-device, that
is an amendment to a locked authority and belongs to the owner under
`owner_instruction_is_project_truth_authority`, recorded as such — not settled inside an architecture
blueprint. Until it is resolved, no Phase E–G work should start.

### B2 — Three action-class taxonomies, two of them inside this one document

- `docs/SECURITY_POLICY.md:25-31` (locked): **A1** safe read/deterministic local, **A2** bounded
  external read, **A3** bounded write, **A4** destructive/send-as-owner, **A5** prohibited.
  Implemented in `queue/CommandQueueModels.kt:5-14` as
  `CommandSensitivity{NORMAL, ELEVATED, DESTRUCTIVE, SECRET}` and gated by `security/BiometricGate.kt`.
- Rev 3 §17: **A** SAFE_LOCAL, **B** PRIVACY_BEARING, **C** NORMAL_EXTERNAL_WRITE,
  **D** CONSEQUENTIAL, **E** RISK_REDUCING_EMERGENCY.
- Rev 3 §30.20 (Voice Rev 2, pasted unchanged): **A** safe local, **B** privacy-bearing,
  **C** consequential, **D** risk-reducing emergency.

So within Rev 3, **class C means "ordinary external write, execute under policy" in §17 and
"consequential — require explicit confirmation and/or biometrics" in §30.20**, and class D means
"consequential" in one and "emergency fast path" in the other. Same letters, incompatible gates, same
document. §30.A's integration mapping table resolves `VoiceActionPolicy` into the global engine but
says nothing about the class letters, so the contradiction is unmediated.

Separately, both invented taxonomies still lack any equivalent of **A5 / prohibited**, and neither can
be handed to `EncryptedCommandQueue`, which takes a `CommandSensitivity`.

**Required correction.** Delete both invented ladders. Express §17 as a mapping from
`ActionDescriptor.riskClass` onto the canonical A1–A5 / `CommandSensitivity`, rewrite §30.20 as a
pointer to §17 rather than a parallel table, and add the A5 voice/command denylist as a named, tested
set (read back an OTP, speak a token, dictate a credential).

### B3 — `trading.halt` as a registered on-device action collides with the VATI sender gate

`2fc93e8` completed two boundaries: `stack_lock.json` carries `single_order_sender`
(`vati-execution-router`) and the T0 gate set including `ctrader_execution`
(`executes_live_orders: true`); and the commander omits the credential-bearing account commands from
`/v1/tools` and refuses them `403` with an audit line when `requested_by` is in `AGENT_REQUESTERS`
(`hermes`, `agent`, `model`, `claude`, `codex`, `sol`, `sonnet`).

Rev 3 §15 registers `trading.halt` and `hermes.command.dispatch` as action IDs; §29 and §36 give
`TradingActionAdapter` a slot in the device-side `ExecutionRuntime`. Combined with §17's delegated
autonomy — `EXECUTE_UNDER_POLICY` covering "approved service mutations" — this is a materially larger
trading surface than Rev 2's single spoken `TRADING_HALT`, and Rev 3 never says what `requested_by`
value any of it carries.

**Required correction.** Add "VAN is never a sender of record under the VATI single-sender gate" to
§35; specify the `requested_by` value for device- and Hermes-originated dispatch; and, following the
repo's induced-failure convention from `2fc93e8`, require a test proving a VAN-originated fenced
command is refused and audited, which fails if the boundary is disabled.

### B4 — The Exa research runtime has no credential locus, no egress gate and no dependency policy

§22 places `ExaAdapter` in the research plane; §29 puts it under `android/.../research/`. Rev 3 never
says where the Exa API credential lives.

VAN's established model, certified in `db0e988`: the Workspace refresh credential is encrypted in the
**gateway vault**, short-lived access tokens are exchanged inside the gateway, and neither is
forwarded to Hermes prompts. `SECURITY_POLICY.md` requires credentials to stay in approved secure
stores, never in prompts or logs, and keeps credential planes separated. An API key shipped in an
Android APK is none of those things.

Three further gaps:

- **No external gate row.** Research egress is a new outbound network surface. `EXTERNAL_GATES.md`
  has rows for every other provider plane; Exa has none, and there is no CONFIGURED/READY treatment
  for it.
- **No dependency policy.** Contrast §30.29.5, which is rigorous about sherpa: version-pinned,
  licence-reviewed, SBOM-visible, SHA-256 verified, rollbackable, forbidden from adding hidden
  telemetry. Exa — a live third-party service in the hot path of §17's `AUTO_EXECUTE` tier — gets
  none of that treatment.
- **Autonomous egress.** §17 grants research `AUTO_EXECUTE`. VAN may therefore send owner-derived
  query text to a third party without owner confirmation. §27.8 bounds *what* is sent, which is good,
  but not *whether* — and for a device that also holds the owner's context graph, the boundary
  deserves an explicit statement.

**Required correction.** State the credential locus (recommended: gateway-mediated, matching
Workspace); add Exa rows to `EXTERNAL_GATES.md`; extend §30.29.5's dependency policy to cover external
service adapters; and state whether autonomous research egress requires owner opt-in.

### B5 — The API 36 obligation is overdue, and Rev 3's own contradiction engine points straight at it

§12's worked example is canonical `targetSdk = 36` versus observed `targetSdk = 34`, yielding
`IMPLEMENTATION_CONFORMANCE_GAP`. That example is literally true of this repository today
(`android/app/build.gradle.kts:11,16`).

§30.2.1 states, correctly, that as of 31 August 2026 Play requires new apps and updates to target API
36. That date has passed. The sharper truth Rev 3 still does not state is that **VAN cannot submit any
update to Play in its current state**, voice or otherwise. `PROJECT_CANONICAL_STATE.json` carries
`release_blocked: true` but cites 0.5.0-dev and `EXTERNAL_GATES.md`, and `EXTERNAL_GATES.md` has no
row for the target-API obligation.

**Required correction.** Re-state §31 Phase A as a current, standalone release blocker rather than a
prerequisite for context work, and add the row to `EXTERNAL_GATES.md`.

### B6 — §30.27's visual mapping bypasses a locked authority and the current aura system

`visual-authority/rive_contract.json` is in `locked_authorities`. It is bound in code by
`visual/RiveContract.kt` — `VanDurableState` with 18 codes (`OFFLINE(0)` … `SLEEPING(17)`, including
`LISTENING(4)`, `THINKING(5)`, `DEGRADED(12)`, `WARNING(13)`), `VanFiniteAction`, and `VanInput` wire
names that already include `listening`, `speaking`, `mouth_open` and `viseme` — and enforced by
`RiveContractTest`. The three most recent commits on `main` (`fa320ae`, `8f8134c`, `a6756df`)
established the three-zone aura envelope, and `docs/VAN_VISUAL_ACCEPTANCE_MATRIX.md` states that every
row is "enforced in code by `VanGlassTokens`, `VanAuraSpecs` or `VanEffectPolicy`, not by hand-tuning
a screenshot."

§30.27 introduces a parallel vocabulary — "WAKE ARMED / subdued cyan aura", "WAKE CANDIDATE / subtle
pre-pulse", "SECOND PASS / brief distinct diagnostic nuance", "VOICE DEGRADED / amber voice
indicator" — with no mapping to any of it. Implemented as written, either `RiveContractTest` breaks or
voice renders outside the certified visual system. Rev 3 makes this worse by adding states that also
need visual treatment and never mentioning them: context-refreshing, researching, awaiting
verification, action partially succeeded.

**Required correction.** Replace §30.27 with a mapping of each voice **and Rev 3 runtime** state →
existing `VanDurableState` code + aura zone + `VanInput`; route any genuinely new code through the
locked-authority amendment path; and add rows to `VAN_VISUAL_ACCEPTANCE_MATRIX.md` rather than
creating a second matrix.

### B7 — §30.34's certification record does not follow VAN's evidence conventions, and §28.1 multiplies it

VAN's established pattern, visible in `db0e988` and `EXTERNAL_GATES.md`: a token-free attestation JSON
under `artifacts/` carrying `schema_version`, `certification`, `certified_at_utc`, `certified_commit`,
`host`, `evidence_pointer` and `contains_secrets: false`; a row in `EXTERNAL_GATES.md`; import/probe
tooling under `tools/`; and the `SECURITY_POLICY.md` rules that `CONFIGURED` is not `READY`, that
`READY` requires a deterministic evidence pointer, and that provider-produced artifacts "remain
untrusted evidence and cannot be labeled `OWNER_SIGNED`".

§30.34's `VoiceCertificationRecord` diverges on every point:

- `vanCommitSha: String?` is **nullable** (line 3426 of Rev 3). VAN's convention makes
  `certified_commit` mandatory; a nullable commit permits an unanchored certification, which is
  exactly what §30.34.1's partial-invalidation logic exists to prevent.
- **No `evidence_pointer`**, so the §30.33 SLO numbers are self-asserted by the runtime being
  certified — the "CONFIGURED claimed as READY" failure the policy forbids.
- **No `host`, no `contains_secrets`.**
- **The signer is never named.** A device-local key makes this self-attestation, and per policy a
  device-produced artifact cannot be `OWNER_SIGNED`. Owner sign-off must stay external, as it does for
  the device acceptance checklist.
- `signature: ByteArray` in a `@Serializable data class` (line 3448) gives identity-based
  `equals`/`hashCode` — a real correctness bug for comparing, deduplicating or testing records,
  independent of policy.

§28.1 then multiplies this shape into five more records (`OwnerContextCertificationRecord`,
`CommandResolutionCertificationRecord`, `ActionExecutionCertificationRecord`,
`ResearchCertificationRecord`, `VanRuntimeCertificationRecord`) without fixing it, so the defect
propagates six-fold. And §34's definition of done never adds rows to `EXTERNAL_GATES.md`, which is the
only mechanism that actually moves `release_blocked`.

**Required correction.** Fix the shape once — mandatory commit and build fingerprint,
`evidence_pointer`, `host`, `contains_secrets`, named signer, base64 `String` signature or an explicit
serializer plus `equals`/`hashCode` — and define the other five as the same schema with a different
`certification` value. Extend `tools/certification/run_certification_harness.py` rather than standing
up a parallel harness, and add the rows to `EXTERNAL_GATES.md`.

---

## Major findings

### M1 — The "hie van" acknowledgement contradicts the pre-roll design it sits on top of

§1.1 requires that an accepted wake produce an immediate local `"hie van"`, after which "owner
continues naturally". §35 makes this three separate invariants (29, 30, 31), including that context
warming "cannot delay it".

But §30.7.2 and §30.7.3 exist precisely because the owner *does not pause* — the rolling pre-buffer
and the wake cut-point are there to capture a command word that follows the wake phrase immediately.
So in the normal case the pre-roll was designed for, the owner is speaking their command **while VAN
is speaking the acknowledgement**, on a device where §30.10 gates wake decisions during VAN TTS and
explicitly defers full-duplex barge-in and AEC certification.

§1.1 asserts that "buffered audio and turn gating prevent the acknowledgement from causing microphone
races or clipped post-wake speech." Buffering preserves the samples; it does not unmix them. The
recognizer still receives owner speech with VAN's TTS leaking into the same channel, which is the
exact condition §30.8 lists as a certification environment ("VAN TTS leakage") and §30.10 says must be
separately certified before barge-in is enabled.

Two further gaps in the same behavior:

- **TTS cold start.** `TtsOutputManager` only sets `ready` after `onInit`. A cold `TextToSpeech` init
  takes seconds. "Immediately" requires either a pre-warmed engine held across the armed lifetime or a
  pre-rendered PCM asset played through the audio path. Rev 3 mandates the behavior in six places and
  never mentions the warm-up requirement.
- **Two sources of truth for the literal.** `"hie van"` is hard-specified in §1.1, §30.B, §32.6, §34,
  §35.29 and §36 — *and* listed in §6 as a value in the deterministic fact store
  (`VAN wake acknowledgement = "hie van"`). If the fact store is authoritative, the five hard-coded
  copies are a conformance hazard; if the literal is authoritative, §6 is decoration. Pick one.

**Required correction.** Resolve the overlap explicitly. The cheapest resolution is a short non-verbal
earcon rather than speech — it acknowledges wake without occupying the channel the recognizer needs
and without requiring AEC. If the spoken form is the owner's firm preference, then Rev 3 must either
make the ack duckable on detected speech (which *is* the barge-in capability §30.10 defers, and should
be named as a dependency) or accept and certify the overlap under §30.8's TTS-leakage condition.
Either way, add a warm-TTS requirement and a single authoritative source for the string.

### M2 — The shipped recognizer may be cloud-backed; that is a live violation of the Core Rule

`voice/VoiceInterfaces.kt:54` uses `SpeechRecognizer.isRecognitionAvailable(context)` +
`createSpeechRecognizer(context)` — the system default recognizer, which may transcribe in the cloud.
Line 100 sets `EXTRA_MAX_RESULTS` to `1`. There is no `EXTRA_PREFER_OFFLINE`, no on-device
availability check, and no on-device recognizer anywhere in the tree.

§30.2 describes the baseline only as "centered on `VoiceInterfaces.kt`" at API 34, and §31 Phase I
schedules the fix late. But §30.3 lists "silent switch to cloud STT" among the things the owner must
never experience, and the Core Rule on page 1 forbids it outright. The condition is present in `main`
today, and Rev 3's own §12 machinery would classify it as a conformance gap if pointed at it.

**Required correction.** Record it as a current known defect with a remediation ahead of the context
and research phases — either move to `createOnDeviceSpeechRecognizer`, or surface voice input as
explicitly network-capable and uncertified in the UI until it does.

### M3 — Rev 3 adds large on-device subsystems with no device budget

§30.32 gives voice a rigorous budget: 16 kHz mono, VAD before KWS, no permanent waveform renderer,
bounded native thread counts, and nine named measures including
`battery_percent_per_hour_screen_off` and `thermal_status_distribution`.

Rev 3 then adds, on the same phone, alongside a continuously armed microphone: a Room/SQLite fact
store, a temporal graph with its own index, FTS/BM25 **plus vector similarity** (§4 L3), an evidence
graph, a full Obsidian vault index (§23), a capsule store, a checkpoint store, a receipt store, a
snapshot store, and a `ContextPredictor` that speculatively warms capsules (§5) — that is,
continuously, in the background, next to the wake pipeline.

§33's device row reads "battery, thermal, memory, process recovery **where applicable**". That phrase
is carrying the entire budget. There is no memory ceiling, no vector-index sizing, no storage cap, and
— most consequentially — **no statement of which model performs §14's intent classification or where
it runs**. On-device inference and a Hermes round trip have completely different latency, battery and
offline profiles, and §4.2's "< 150 ms typical common-path context compilation" objective is only
meaningful once that is settled (see B1).

**Required correction.** Extend §30.32's budget to the whole runtime: memory ceiling, storage caps
per store, a speculative-warming duty cycle, and an explicit statement of the inference locus and its
cost. Delete "where applicable" from §33's device row.

### M4 — No provenance or trust model for the knowledge and personalization surfaces

`SECURITY_POLICY.md` labels email, Drive, notifications, web, Notebook sources, provider output and
peer messages as untrusted external data whose instructions cannot escalate authority. VAN runs a
`NotificationListenerService` ingesting exactly that, `secret_notification` (OTP redaction) is a device
checklist row, and `CommandSensitivity.SECRET` exists for content that must never leave the device.

Rev 3 widens the ingestion surface considerably and does not extend the control:

- §13 makes `NOTIFICATION_EVENT` a first-class interaction channel that reaches the same command
  runtime as owner voice.
- §23's Obsidian watcher feeds `KnowledgeAdmissionGate` from vault files — which may contain anything
  the owner pasted from anywhere.
- §22's research evidence enters the evidence graph and, via §12, is a candidate for promotion.
- §30.16/§30.17 build the recognition bias set from "current screen entities, recent entities,
  relevant contacts", so untrusted text can steer recognition of the owner's own commands.

§12's `KnowledgeAdmissionGate` classifies candidates, which is the right shape, but Rev 3 never states
the one rule that matters: **untrusted-source content may not reach `CONFIRMED_LEARNED`, may not seed
a confusion edge, and may not become an owner-pinned entry without explicit owner confirmation.**
§30.38 tests for "malicious correction injection" while §30.16 and §30.17 define nothing that would
make that test fail.

**Required correction.** Add a provenance/trust field to `ContextVocabularyStore`,
`SpeechConfusionEdge` and every `KnowledgeAdmissionGate` input; state the promotion rule above as an
invariant in §35; exclude `SECRET`-class content from every personalization and context store; and
convert the injection tests into induced-failure tests.

### M5 — The Owner Context Graph gets no privacy treatment of its own

§27's ten principles cover audio, speech learning, credentials, snapshot minimization and research
scoping. They do not cover the largest new thing Rev 3 creates: an on-device graph holding `PERSON`,
`ACCOUNT`, `DEVICE`, `DECISION` and `POLICY` entities with temporal relationships — a richer personal
dossier than anything VAN stores today.

§27.3 says sensitive owner facts use encrypted local storage "where applicable". Rev 2 was stricter
about far less: §30.25 named eight encrypted stores and §30.29's `VoiceProfileRepository` exposed
`resetPersonalization()` and `eraseRetainedVoiceSamples()`. The graph has no stated encryption
requirement, no erase control, no export control, no retention policy and no size bound.

**Required correction.** Require Keystore-backed encryption for the fact store, graph and evidence
graph; add owner-facing erase and export controls mirroring `VoiceProfileRepository`; and set
retention and size policy. `allowBackup="false"` is already correct at `AndroidManifest.xml:16` and
should be stated as a requirement rather than left incidental.

### M6 — minSdk 26 against an API 31/33/34-only voice architecture

`android/app/build.gradle.kts:15` sets `minSdk = 26`, and §30.2 explicitly says to preserve it. The
primary voice path requires API 31 (`createOnDeviceSpeechRecognizer`), 33 (`EXTRA_AUDIO_SOURCE`,
`checkRecognitionSupport`, `triggerModelDownload`) and 34 (`RecognitionPart`, `AlternativeSpan`, word
confidence and timing).

On API 26–30 there is no dedicated on-device recognizer at all, so §30.1.2's invariant "the Android
recognizer is primary when its local capability is healthy" is unsatisfiable and sherpa must be
permanent primary. Yet §30.4.2's readiness states, §30.21's state machine and §30.30's capability
matrix have no API-tier branch, and §30.14.4's `ANDROID_STT_DEGRADED_SHERPA_PRIMARY` is framed as a
*degradation from health* rather than the normal steady state of a supported tier. An API 28 device
would sit permanently in a state named "degraded" while behaving exactly as designed.

**Required correction.** Add a capability-tier table (26–30 / 31–32 / 33 / 34–35 / 36 target) stating
per tier what the primary path is and what `VOICE_CERTIFIED` can mean; add
`SHERPA_PRIMARY_BY_API_FLOOR` as distinct from the degraded state; or raise `minSdk` with a recorded
rationale.

### M7 — The foreground-service change is unanalyzed against the existing overlay FGS and boot receiver

§30.29.2 says to add `FOREGROUND_SERVICE_MICROPHONE`; §30.6.2 cites the `VoiceInteractionService`
exemption from the FGS while-in-use restriction; §30.6.3 describes reboot re-arm.

The repository state it lands in: `AndroidManifest.xml:5,41-45` — `FloatingOverlayService` runs as
`foregroundServiceType="specialUse"` with subtype `van_owner_assistant_overlay`; and
`AndroidManifest.xml:12,60` — `OverlayRecoveryReceiver` starts on `BOOT_COMPLETED` and
`MY_PACKAGE_REPLACED`.

1. **Which service owns the mic type is never stated.** Adding `microphone` to the existing overlay
   FGS would put microphone capture under a Play-reviewed `specialUse` declaration *and* couple
   microphone lifetime to overlay presentation — which §30.6.2 explicitly forbids.
2. **Boot-start of a microphone FGS is restricted.** Rev 3 asserts the assistant exemption applies but
   requires no evidence that it does on target Samsung firmware before the existing boot receiver
   attempts a start.
3. **Play's `specialUse` and assistant declaration review is an external gate** absent from
   `EXTERNAL_GATES.md`.

**Required correction.** State that the wake runtime runs in its own `microphone`-type FGS separate
from the overlay's `specialUse` FGS; add a certification item for mic-FGS start under the assistant
role after boot, evidenced on target firmware or explicitly deferred to first foreground; and add the
Play declaration row to `EXTERNAL_GATES.md`.

---

## Moderate findings

**Mo1 — A null verifier has no defined status ceiling.** §15's `ActionDescriptor.verifierId` is
nullable and §21's status ladder ends at `VERIFIED_SUCCESS`. Rev 3 never says what terminal status an
action with no verifier may reach. It must not be able to reach `VERIFIED_SUCCESS` — that would
reintroduce exactly the false-completion failure §0 exists to prevent. §24 gets this right for
NotebookLM specifically ("distinguish unsupported consumer actions from supported authenticated
actions rather than fabricating completion") without generalizing it. Add an `UNVERIFIABLE` terminal
status and the rule that a null verifier caps status at `SUBMITTED`, with owner-visible wording to
match.

**Mo2 — §20's existence check can't distinguish "already done" from "done by someone else".** The
worked example reads target state after a timeout and concludes `VERIFIED_SUCCESS` if the note exists.
But it may exist because the owner created it manually, or from an earlier unrelated command. Require
correlation by idempotency key, creation timestamp or created-by, not bare existence.

**Mo3 — Voice dispatch and queue idempotency are unspecified.** `QueuedCommand` already carries
`idempotencyKey` and `expiresAtEpochMs`, matching the replay protection certified in `db0e988`
(`signed_stale_command_after_restart: "expired"`). §20 defines execution identity abstractly but never
binds it to the existing queue fields, and never says what a voice turn contributes. Specify the key
as `turnId`-derived — never transcript-derived, since identical text is a legitimate repeat — plus a
same-command debounce window.

**Mo4 — No `VOICE_GRANT_REVOKED` / device-revocation state.** `db0e988` certified that revocation
atomically clears grants and survives restart; it is currently VAN's kill switch. Neither §21's status
set nor §30.21's state machine has a state for it, so a wake-armed VAN would keep executing local
actions after the owner revoked the device.

**Mo5 — §30.20 class D still has no offline behavior.** "Halt autonomous trading" spoken with no
reachable gateway has exactly two candidate behaviors — refuse loudly, or enqueue for replay — and
both are dangerous in different ways. A silently queued halt firing twenty minutes later against a
changed position is arguably worse than a refusal. Rev 3 picks neither. Recommendation: refuse and
alarm, with a persistent owner-visible unacknowledged-emergency state, never a silent queue.

**Mo6 — Learned outcomes could widen autonomy tiers.** §26's `OutcomeLearning` learns "which
approaches succeed or fail in which contexts"; §17 defines `AUTO_EXECUTE` / `EXECUTE_UNDER_POLICY` /
`REQUIRE_EXPLICIT_CONFIRMATION` tiers. §35.25 correctly says learned behavior cannot grant itself
authorization, but nothing forbids learning from widening what flows through an *existing* tier.
State that the mapping action → authority class is owner/policy data and is never learned.

**Mo7 — §30.14's second pass has no turn budget.** Eleven triggers including `AndroidNoMatch`, which
fires constantly on noisy input. §30.33 measures the overhead but no rule bounds it. Add a per-turn
deadline and an invocation-rate ceiling, and make the policy's decision something the SLO evaluator
can reject rather than merely report.

**Mo8 — §30.7.3's wake cut-point is unbounded.** `utterance_start = wake_detection_time -
calibrated_pre_roll + optional_wake_phrase_trim_offset` is never clamped to ring-buffer capacity, and
behavior is undefined when detection latency exceeds the pre-roll window — the exact clipping case the
pre-buffer exists to prevent, and now also the case M1's acknowledgement makes more likely.

**Mo9 — §30.11.2's audio pipe has no backpressure or timeout design.** Undefined: recognizer does not
drain (pipe fills, writer blocks — and if that writer sits on the arbiter's frame-routing path, wake
detection starves); recognizer never returns (no watchdog); recognizer dies mid-utterance. §30.31
lists "broken pipe/descriptor closure" under recovery but assigns no owning component. Require a
bounded non-blocking writer with an explicit timeout, and make "the capture thread never blocks on a
recognizer" an invariant.

**Mo10 — No microphone-loss model.** §30.7.1 claims the arbiter is "the only normal owner of the
physical microphone while wake is armed." Android will not honor that — telephony, the system
assistant, Bixby and emergency calling take the mic. §30.31 covers route changes but not concurrent
capture loss or mic-mute (hardware privacy toggle, per-app disable). Add
`AudioManager.AudioRecordingCallback` observation, a `WAKE_SUSPENDED_MIC_UNAVAILABLE` state, and the
rule that VAN yields to telephony and emergency capture rather than contending.

**Mo11 — §33 and §30.33 don't name who ratifies an envelope.** `PROJECT_CANONICAL_STATE.json` sets
`agent_self_authorization_forbidden: true` and `owner_instruction_is_project_truth_authority: true`.
State that the owner ratifies an SLO profile and that an agent may not sign or ratify one.

**Mo12 — §30.4.1 step 19 cannot run unattended.** "Run airplane-mode certification" is a step in the
first-start installer state machine. An installer cannot toggle airplane mode. Mark it owner-gated or
move it out of the automated sequence.

---

## Minor and editorial

- **§30 reads as a foreign document.** It is pasted with its own voice intact — "Rev 1 recorded…",
  "Rev 2 makes the following repository migration mandatory…", "Rev 2 changes sherpa…". §30.A's
  mapping table is the only conflict-resolution mechanism, and it covers six terms. State plainly that
  §0–§29 govern globally and §30 governs the voice subsystem, and normalize §30's self-references.
- **Duplicate SLO and telemetry definitions.** §4.2 and §33 both define latency objectives; §28 and
  §30.35 both define telemetry, with overlapping-but-differently-named metrics
  (`command_resolution_ms` vs `resolver_latency_ms`). Consolidate or state which is canonical.
- §30.12.2's `WordEvidence` has `startMs` but no `endMs`, though §30.12 collects "RecognitionPart
  timing" and both forced alignment (§30.9.4) and wake trim (§30.7.3) need durations.
- Nullability is inconsistent for the same concept: `AsrHypothesis.locale: String` (§30.12.2) vs
  `SpeechConfusionEdge.locale: String?` (§30.16.4).
- §30.34 has `audioProfileRevision: Int` but §30.8 persists the winning audio profile "against
  device/firmware" — no field links the two.
- §3.2's `OwnerFact.confidence: Double` and §7.2's `TemporalEdge.confidence: Double` are unbounded
  doubles with no stated scale or calibration source; §30.18 is careful to keep resolution weights in a
  signed versioned profile, and these deserve the same treatment.
- §30.46's external reference list is good practice. Add VAN's own locked authorities
  (`SECURITY_POLICY.md`, `EXTERNAL_GATES.md`, `PROJECT_TRUTH_PROTOCOL.md`,
  `visual-authority/rive_contract.json`) with a note that they outrank this blueprint.

---

## Recommended Rev 3.1 change list, in order

1. **Settle the deployment locus.** Add the plane → surface table; if planning, policy, research or
   inference is to run on Android, raise it to the owner as a `SECURITY_POLICY.md` amendment. Nothing
   in Phases E–G should start before this. (B1)
2. Collapse the three action-class taxonomies onto A1–A5 / `CommandSensitivity`, add A5. (B2)
3. Classify VAN as a requester against the VATI sender gate and commander fence, with an
   induced-failure test. (B3)
4. Give Exa a credential locus, `EXTERNAL_GATES.md` rows, a dependency policy and an egress-consent
   rule. (B4)
5. Split the API 36 migration out as a standalone overdue release blocker. (B5)
6. Re-map §30.27 onto `VanDurableState` and the three-zone aura; extend it to Rev 3's new runtime
   states. (B6)
7. Fix the certification record shape once and derive §28.1's five records from it; extend the
   existing harness. (B7)
8. Resolve the acknowledgement/pre-roll overlap — earcon, duckable ack, or certified overlap — plus
   warm TTS and one source of truth for the string. (M1)
9. Record the possibly-cloud recognizer as a current defect with an early remediation. (M2)
10. Write the whole-runtime device budget and name the inference locus. (M3)
11. Add provenance/trust across the knowledge, context and personalization surfaces. (M4, M5)
12. Add the capability-tier table and resolve the FGS ownership question. (M6, M7)
13. Close the truthfulness gaps in the action ladder: `UNVERIFIABLE`, correlated existence checks,
    idempotency binding, revocation state, offline emergency behavior. (Mo1–Mo5)

Items 1–4, 11 and 13 are the security-relevant ones. Items 5, 6, 7 and 12 are where Rev 3 would
otherwise fork VAN's governance rather than extend it. Item 1 gates most of the rest.

---

## What Rev 3 gets right, and should keep

Worth stating plainly so a revision does not erode it. From the new material: the §0 execution
contract and its five distinct states, which is the most valuable idea in the document; the authority
hierarchy in §3.3 and the epistemic fact states in §3.1; §12's contradiction engine and its refusal to
flatten disagreement; the insistence in §8 that GraphRAG is selective and that exact lookup precedes
semantic retrieval; §19–§20's checkpointing and idempotency; §21's rule that `200`/`accepted` is not
evidence of completion; §22.3's rule that research cannot silently rewrite Project Truth; and the
clean separation in §26 between speech, language, entity, workflow and outcome learning.

Carried in from Rev 2: the single-microphone-owner correction; the bounded, measured pre-roll;
selective second-pass ASR with a standing requirement to prove it earns its battery; the honest
correction of the Rev 1 hotword claim; speaker similarity that can never authenticate and never lock
the owner out; word/token/span evidence over whole-sentence substitution; context-conditioned
confusion edges with decay and owner-pinned precedence; partial certification invalidation; and
baselining before setting thresholds.

Those are the parts that already match how VAN certifies everything else, and they are why the rest of
the document is worth fixing rather than replacing.
