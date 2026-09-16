# Expert review — VAN Offline Voice, Wake & Personalized Speech Architecture Rev 2

**Status:** Review. Not an authority document; it does not amend Rev 2, `docs/SECURITY_POLICY.md`, or any locked authority.
**Reviewed document:** `VAN_OFFLINE_VOICE_WAKE_PERSONALIZED_SPEECH_ARCHITECTURE_REV2.md` (Rev 2.0, 47 sections).
**Repository state considered:** `main` @ `a6756df`, plus `2fc93e8` (VATI stack lock 5.1 — cTrader sender gate, credential commands fenced from agents) and `db0e988` (live VAN ingress certification).
**Reviewed at:** 2026-09-16.

## Verdict

Rev 2 is a strong signal-processing and certification design and a real improvement on Rev 1. Its
core corrections — one physical microphone owner, rolling pre-roll, selective rather than permanent
second-pass ASR, the hotword-API correction, speaker-similarity-is-not-authentication, word/span
evidence as first-class data, and partial certification invalidation — are all right, and the
"measure before you threshold" discipline in §33 matches how VAN already certifies everything else.

The gaps are almost entirely at the **seams with VAN as it actually exists**. Rev 2 reads as a
self-contained voice blueprint: it invents its own action classes, its own certification record, its
own visual vocabulary and its own definition of done, in a repository that already has canonical,
in some cases *locked*, versions of all four. Implemented literally, Rev 2 would either break
existing contract tests or quietly stand up a parallel governance system beside the one
`PROJECT_CANONICAL_STATE.json` treats as authority.

Six findings are blocking in the sense that the section as written cannot be implemented without
violating or forking an existing authority. The rest are design gaps of the ordinary kind.

---

## Blocking findings

### B1 — §20's A/B/C/D action classes collide with the locked A1–A5 policy and omit A5

Rev 2 §20 defines four voice action classes: A (safe local), B (privacy-bearing), C (consequential),
D (risk-reducing emergency).

VAN already has a canonical action-class taxonomy in `docs/SECURITY_POLICY.md:25-31` — A1 safe
read/deterministic local, A2 bounded external read, A3 bounded write, A4 destructive/send-as-owner,
A5 prohibited/always deny. `SECURITY_POLICY.md` is listed in
`PROJECT_CANONICAL_STATE.json → canonical_state.locked_authorities`. It is not a convention; it is
implemented: `android/app/src/main/java/com/dial/van/queue/CommandQueueModels.kt:5-14` defines
`CommandSensitivity{NORMAL, ELEVATED, DESTRUCTIVE, SECRET}` annotated to A1 / A2–A3 / A4 / A5, and
`android/app/src/main/java/com/dial/van/security/BiometricGate.kt` gates A4 specifically.

Three distinct problems follow:

1. **Letter collision with inverted meaning.** Rev 2 "class A" is the *safest* class. Canonical "A4"
   is the *most dangerous*. Any engineer or agent reading both documents in the same session will
   mis-bind them, and the failure direction is toward under-gating.
2. **No A5.** Rev 2 has no "prohibited, always deny" voice class at all. VAN does — `SECRET` exists
   precisely for content that must never leave the device or be executed from an ambient context.
   There is no voice denylist in Rev 2 for the obvious A5 utterances (read back an OTP, speak a
   token, dictate a credential), even though §38 tests for secret handling indirectly.
3. **`VoiceActionPolicy` cannot reach the queue.** `EncryptedCommandQueue` accepts a
   `CommandSensitivity`. A policy that emits A/B/C/D has nothing to hand it.

**Required correction.** Delete A/B/C/D. Express §20 as a mapping from resolved voice command →
existing A1–A5 / `CommandSensitivity`, state explicitly that §20 does not amend `SECURITY_POLICY.md`,
and add the A5 voice denylist as a named, tested set.

### B2 — §20 class D has no offline behavior and is not bound to the certified device-signed ingress

`db0e988` certified the live ingress model: an owner ingress bearer on the loopback gateway, device
HMAC credentials encrypted at rest that rehydrate across restart, expiry on signed commands
(`signed_stale_command_after_restart: "expired"`), and atomic revocation that survives a second
restart (`active_grants_after_revoke: 0`, `post_revoke_command_after_second_restart: "denied"`).
`QueuedCommand` carries `idempotencyKey` and `expiresAtEpochMs` to match.

Rev 2 §20 class D says an emergency command "may use a fast fail-safe path, but the target system
must still authenticate and enforce the command independently," and §41 invariant 26 says
understanding is not completing. That is directionally right and operationally empty. Missing:

- **No binding to the signed path.** Rev 2 never states that a voice-originated command is dispatched
  as a device-signed, nonce-bearing, expiry-bounded request. `HermesVoiceDispatcher` is described only
  as "signed".
- **No defined behavior when an emergency command cannot reach its target.** "Halt autonomous
  trading" spoken with no reachable gateway has exactly two candidate behaviors — refuse loudly, or
  enqueue for replay — and both are dangerous in different ways. A silently queued halt that fires
  twenty minutes later against a changed position is arguably worse than a refusal. Rev 2 picks
  neither, and §30 only notes that remote execution "requires authenticated reachable target".
- **No revocation interaction.** Device-grant revocation is currently VAN's kill switch. A
  wake-armed VAN that keeps executing local actions after the owner revoked the device is a hole.
  There is no `VOICE_GRANT_REVOKED` state in §21.
- **"Fast fail-safe path" vs A4.** Canonical A4 requires explicit owner approval. Rev 2 should say
  plainly which A-class an emergency halt is, and if it is deliberately gated *below* A4 for
  latency reasons, that is a security decision that belongs to the owner, recorded as such.

**Required correction.** Add a section binding `VoiceActionPolicy` → device-signed dispatch (nonce,
expiry, idempotency key derived from `turnId`, never from transcript text); add `VOICE_GRANT_REVOKED`
as a disarming state; and state the required behavior for an unreachable class-D command. The
recommendation is refuse-and-alarm — a persistent, owner-visible unacknowledged-emergency state —
never a silent queue.

### B3 — Voice is an unclassified requester against the VATI sender gate

`2fc93e8` completed two boundaries in the trading stack: `stack_lock.json` now carries the
`single_order_sender` and T0 gate sets including `ctrader_execution` (`executes_live_orders: true`),
and the commander fences the eleven credential-bearing account commands — omitted from `/v1/tools`
and refused `403` with an audit line when `requested_by` is in `AGENT_REQUESTERS`
(`hermes`, `agent`, `model`, `claude`, `codex`, `sol`, `sonnet`).

Rev 2 §19 lists `TRADING_HALT` as a local deterministic command and §20 class D covers halting
autonomous trading. It never says what `requested_by` a voice-originated command carries.

This matters in both directions. `SECURITY_POLICY.md` states Hermes profile `van` is the sole agent
runtime and that Android does not form an independent agent loop — so a voice command routed through
Hermes *is* an agent requester and will be correctly 403'd on fenced commands, which is right but
undocumented and will read as a bug when first hit. A voice command routed through the gateway
device path is the owner, which is also defensible. Rev 2 must choose, and must state that voice
never becomes a second order sender under the single-sender gate.

**Required correction.** Add "voice is never a sender of record" to §41; specify the `requested_by`
value for voice-originated dispatch; and, following the repo's induced-failure convention from
`2fc93e8`, require a test proving a voice-originated fenced command is refused and audited, which
fails if the boundary is disabled.

### B4 — The API 36 migration is overdue, not pending; VAN cannot ship Play updates today

Rev 2 §2.1 states, correctly, that as of 31 August 2026 Play requires new apps and updates to target
API 36. That date has passed. `android/app/build.gradle.kts:11,16` still reads `compileSdk = 34` /
`targetSdk = 34`.

Rev 2 frames this as a migration that is "mandatory before production voice certification". The
sharper and more actionable truth is that VAN cannot submit *any* update to Play in its current
state, voice or otherwise, and `PROJECT_CANONICAL_STATE.json` already carries `release_blocked: true`
without naming this as a reason (`release_block_reason` cites 0.5.0-dev and EXTERNAL_GATES). There is
no row in `docs/EXTERNAL_GATES.md` for the target-API obligation.

**Required correction.** Re-state §2 as a current release blocker rather than a voice prerequisite,
add the row to `EXTERNAL_GATES.md`, and decouple Phase 0 from the voice programme so the migration
is not gated behind voice work it does not depend on.

### B5 — §27's visual mapping bypasses a locked authority and the current aura system

`visual-authority/rive_contract.json` is in `locked_authorities`. It is bound in code by
`android/app/src/main/java/com/dial/van/visual/RiveContract.kt` — `VanDurableState` with 18 codes
(`OFFLINE(0)` … `SLEEPING(17)`, including `LISTENING(4)`, `THINKING(5)`, `DEGRADED(12)`,
`WARNING(13)`), `VanFiniteAction`, and `VanInput` wire names that already include `listening`,
`speaking`, `mouth_open` and `viseme` — and enforced by `RiveContractTest`. The three most recent
commits on `main` (`fa320ae`, `8f8134c`, `a6756df`) established the three-zone aura envelope, and
`docs/VAN_VISUAL_ACCEPTANCE_MATRIX.md` states that every row is "enforced in code by
`VanGlassTokens`, `VanAuraSpecs` or `VanEffectPolicy`, not by hand-tuning a screenshot."

Rev 2 §27 introduces a parallel vocabulary — "WAKE ARMED / subdued cyan aura", "WAKE CANDIDATE /
subtle pre-pulse", "SECOND PASS / brief distinct diagnostic nuance", "VOICE DEGRADED / amber voice
indicator" — with no mapping to any of it. Implemented as written, either `RiveContractTest` breaks
or voice renders outside the certified visual system. `VOICE DEGRADED` in particular needs to
reconcile against the existing `DEGRADED(12)` and `WARNING(13)` states rather than introduce a third.

**Required correction.** Replace §27's table with a mapping of each voice state → existing
`VanDurableState` code + aura zone + `VanInput`, note which (if any) new codes the contract would
need and route those through the locked-authority amendment path, and add voice rows to
`VAN_VISUAL_ACCEPTANCE_MATRIX.md` instead of creating a second matrix.

### B6 — §34's certification record does not follow VAN's evidence conventions, so it cannot discharge a gate

VAN's established pattern, visible in `db0e988` and `docs/EXTERNAL_GATES.md`: a token-free attestation
JSON under `artifacts/` carrying `schema_version`, `certification`, `certified_at_utc`,
`certified_commit`, `host`, `evidence_pointer` and `contains_secrets: false`; a row in
`EXTERNAL_GATES.md`; import/probe tooling under `tools/`; and the rules in `SECURITY_POLICY.md` that
`CONFIGURED` is not `READY`, that `READY` requires a deterministic evidence pointer, and that
provider-produced artifacts "remain untrusted evidence and cannot be labeled `OWNER_SIGNED`".

Rev 2 §34's `VoiceCertificationRecord` diverges on every one of those points:

- `vanCommitSha: String?` is **nullable**. VAN's convention makes `certified_commit` mandatory; a
  nullable commit permits an unanchored certification, which is precisely the drift §34.1 exists to
  prevent.
- **No `evidence_pointer`.** Without one, the §33 SLO numbers are self-asserted by the runtime being
  certified — the exact "CONFIGURED claimed as READY" failure the policy forbids.
- **No `host`, no `contains_secrets`.**
- **The signer is never named.** If the key is device-local, this is self-attestation, and per policy
  a device-produced artifact cannot be `OWNER_SIGNED`. Owner sign-off must remain external, as it does
  for the device acceptance checklist.
- `signature: ByteArray` inside a `@Serializable data class` gives identity-based `equals`/`hashCode`
  — a genuine correctness bug for comparing, deduplicating or testing records, independent of policy.
- **§40's definition of done never adds rows to `EXTERNAL_GATES.md`**, which is the only mechanism
  that actually moves `release_blocked`.

**Required correction.** Make commit and build fingerprint mandatory; add `evidence_pointer`, `host`,
`contains_secrets`; name the signer and state that owner sign-off stays external; serialize the
signature as base64 `String` or supply an explicit serializer plus `equals`/`hashCode`; extend
`tools/certification/run_certification_harness.py` rather than standing up a parallel harness; and add
the voice rows to `EXTERNAL_GATES.md`.

---

## Major findings

### M1 — The shipped recognizer may be cloud-backed; that is a live violation of the Core Rule

`android/app/src/main/java/com/dial/van/voice/VoiceInterfaces.kt:54` uses
`SpeechRecognizer.isRecognitionAvailable(context)` + `createSpeechRecognizer(context)` — the system
default recognizer, which may transcribe in the cloud. Line 100 sets `EXTRA_MAX_RESULTS` to `1`.
There is no `EXTRA_PREFER_OFFLINE`, no on-device availability check, and no on-device recognizer
anywhere in the tree.

Rev 2 §2 describes the baseline only as "centered on `VoiceInterfaces.kt`" at API 34, and schedules
the on-device recognizer for Phase 4. But Rev 2's own §3 lists "silent switch to cloud STT" among the
things the owner must never experience, and the Core Rule on page 1 forbids exactly this. The
condition is present in `main` today.

**Required correction.** Record this in Rev 2 as a current known defect rather than a Phase 4
improvement, and add a Phase 0.5 that either moves to `createOnDeviceSpeechRecognizer` or, until it
does, surfaces voice input as explicitly network-capable and uncertified in the UI. Under VAN's own
evidence rules, shipping a possibly-cloud recognizer while the blueprint claims offline-first is the
kind of claim/evidence mismatch the whole certification apparatus exists to prevent.

### M2 — minSdk 26 against an API 31/33/34-only architecture, with no defined behavior below 31

`android/app/build.gradle.kts:15` sets `minSdk = 26`, and Rev 2 §2 explicitly says to "preserve the
project's deliberately selected minSdk". But the primary path requires API 31
(`createOnDeviceSpeechRecognizer`), 33 (`EXTRA_AUDIO_SOURCE`, `checkRecognitionSupport`,
`triggerModelDownload`) and 34 (`RecognitionPart`, `AlternativeSpan`, word confidence and timing).

On API 26–30 there is no dedicated on-device recognizer at all, so §41 invariant 4 — "Android's
dedicated on-device recognizer is the normal primary STT path" — is unsatisfiable and sherpa must be
the permanent primary. Yet §4.2's readiness states, §21's state machine and §30's capability matrix
have no API-tier branch, and §14.4's `ANDROID_STT_DEGRADED_SHERPA_PRIMARY` is framed as a
*degradation from health*, not as the normal steady state of a supported device tier. An API 28 phone
would sit permanently in a state named "degraded" while behaving exactly as designed.

**Required correction.** Add an explicit capability-tier table (26–30 / 31–32 / 33 / 34–35 / 36
target) stating per tier what the primary path is and what `VOICE_CERTIFIED` can mean; introduce
`SHERPA_PRIMARY_BY_API_FLOOR` as distinct from the degraded state; or raise `minSdk` with a recorded
rationale. Silently leaving a third of the supported range undefined is the worst of the three.

### M3 — The foreground-service change is unanalyzed against the existing overlay FGS and boot receiver

Rev 2 §29.2 says to add `FOREGROUND_SERVICE_MICROPHONE`; §6.2 cites the `VoiceInteractionService`
exemption from the FGS while-in-use restriction; §6.3 describes reboot re-arm.

The repository state it has to land in: `AndroidManifest.xml:5,41-45` — `FloatingOverlayService` runs
as `foregroundServiceType="specialUse"` with subtype `van_owner_assistant_overlay`; and
`AndroidManifest.xml:12,60` — `OverlayRecoveryReceiver` starts on `BOOT_COMPLETED` and
`MY_PACKAGE_REPLACED`. Three gaps:

1. **Which service owns the mic type is never stated.** Adding `microphone` to the existing overlay
   FGS would put microphone capture under a Play-reviewed `specialUse` declaration *and* couple
   microphone lifetime to overlay presentation — which §6.2 explicitly forbids ("the overlay must
   never be the reason the microphone remains alive").
2. **Boot-start of a microphone FGS is restricted.** Rev 2 asserts the assistant exemption applies but
   requires no evidence that it does on the target Samsung firmware before the existing boot receiver
   attempts a start. This is exactly the class of thing §36.1 should gate and does not.
3. **Play's `specialUse` and assistant declaration review is an external gate** and is absent from
   `EXTERNAL_GATES.md`.

**Required correction.** State that the wake runtime runs in its own `microphone`-type FGS,
separate from the overlay's `specialUse` FGS; add a certification item for mic-FGS start under the
assistant role after boot, evidenced on target firmware or explicitly deferred to first foreground;
and add the Play declaration row to `EXTERNAL_GATES.md`.

### M4 — PersonalSpeechModel has no provenance or trust model, and is reachable by prompt injection

§16.2 activates context from "recently referenced entities", "foreground screen", "authorized contact
interaction"; §17 builds the bias set from "current screen entities, recent entities, relevant
contacts"; §38 lists "malicious correction injection" as a *test case* while §16 and §17 define no
control that would make it fail.

`SECURITY_POLICY.md` labels email, Drive, notifications, web, provider output and peer messages as
untrusted external data whose instructions cannot escalate authority — and VAN runs a
`NotificationListenerService` ingesting precisely that content, with `secret_notification` (OTP
redaction) already a device-checklist row and `CommandSensitivity.SECRET` already defined for content
that must never leave the device.

So: if notification-, share- or email-derived strings can enter `EXTRA_BIASING_STRINGS` or seed
confusion edges, untrusted external text steers recognition of the owner's own commands. A hostile
notification can bias a contact name, or seed an edge that makes a command-bearing word resolve
somewhere else. Worse, secret-class content could be persisted into `personal_speech_model.enc` and
`speech_confusions.enc`, which are explicitly *not* transient.

**Required correction.** Add a provenance/trust field to `ContextVocabularyStore` and
`SpeechConfusionEdge`; forbid untrusted-source terms from seeding confusion edges or owner-pinned
entries without explicit owner confirmation to promote; exclude `SECRET`-class content from every
personalization store; and convert §38's injection test into an induced-failure test.

### M5 — No microphone-loss model; §7.1's ownership claim is stronger than Android allows

§7.1 states the arbiter is "the only normal owner of the physical microphone while wake is armed."
Android will not honor that: telephony, the system assistant, Bixby, emergency calling and other
higher-priority capture will take the microphone away. §31 lists audio-route changes and Bluetooth
transitions but not concurrent-capture loss or mic-mute (hardware privacy toggle, per-app mic
disable).

**Required correction.** Add `AudioManager.AudioRecordingCallback` / mic-mute observation, a
`WAKE_SUSPENDED_MIC_UNAVAILABLE` state in §21, and the explicit rule that VAN yields to telephony and
emergency capture rather than contending for the device — plus the owner-visible truthful state while
suspended, consistent with the rest of Rev 2's honesty posture.

---

## Moderate findings

**Mo1 — Second pass has no turn budget.** §14.2 lists eleven triggers including `AndroidNoMatch`,
which will fire constantly on noisy input. §33 measures second-pass overhead but no rule bounds it.
Add a per-turn deadline (second pass may not run if it would breach the final-transcript SLO) and an
invocation-rate ceiling, and make `SecondPassPolicy`'s decision an input the SLO evaluator can reject,
not merely a metric it reports.

**Mo2 — §7.3's wake cut-point is unbounded.** `utterance_start = wake_detection_time -
calibrated_pre_roll + optional_wake_phrase_trim_offset` is never clamped to the ring buffer's
capacity, and the document does not define behavior when detection latency exceeds the pre-roll
window — which is the exact clipping case the pre-buffer exists to prevent. Specify the clamp, the
over-latency behavior, and the metric that detects it.

**Mo3 — The `EXTRA_AUDIO_SOURCE` pipe has no backpressure or timeout design.** §11.2 says only that
"the writer closes the descriptor when the utterance is complete." Undefined: what happens when the
recognizer does not drain (pipe fills, writer blocks — and if that writer is on the arbiter's frame
routing path, wake detection starves), when it never returns a result (no watchdog), or when it dies
mid-utterance. §31 lists "broken pipe/descriptor closure" under recovery but assigns it no owning
component. Require a bounded, non-blocking writer with an explicit timeout, and state as an invariant
that the capture thread never blocks on a recognizer.

**Mo4 — Barge-in behavior regresses without saying so.** `BargeInHook` and `VoiceSessionCoordinator`
exist today in `VoiceInterfaces.kt`, and `barge_in` is a row in `docs/DEVICE_ACCEPTANCE_CHECKLIST.md`.
§10 suppresses wake during TTS and defers full-duplex barge-in to a separately certified capability.
That is the right call acoustically, but it changes what the existing checklist row means. Say so
explicitly, so the device checklist cannot pass on a weaker behavior than it passed on before.

**Mo5 — Voice dispatch idempotency is unspecified.** `QueuedCommand` carries an `idempotencyKey`.
A repeated utterance, a TV repeat, or VAN re-hearing itself must not produce two dispatches. Specify
the key as `turnId`-derived (never transcript-derived — identical text is a legitimate repeat) plus a
same-command debounce window.

**Mo6 — §33.2 does not name who ratifies an SLO envelope.** `PROJECT_CANONICAL_STATE.json` sets
`agent_self_authorization_forbidden: true` and `owner_instruction_is_project_truth_authority: true`.
State that the owner ratifies a `VoiceSloProfile` and that an agent may not sign or ratify one.

**Mo7 — No storage budget for the personalization stores.** §25 lists eight `.enc` stores; §16.6's
decay governs weights, not bytes. Correction history and recognizer-specific evidence grow without
bound on a device. Add caps, compaction and a retention policy. (`allowBackup="false"` is already set
at `AndroidManifest.xml:16`, which is correct and worth stating as a requirement rather than leaving
incidental.)

**Mo8 — §4.1 step 19 cannot run unattended.** "Run airplane-mode certification" is listed as a step
in the first-start installer state machine. An installer cannot toggle airplane mode; this needs owner
participation. Mark it owner-gated or move it out of the automated sequence.

---

## Minor and editorial

- §11's code sample gates on `Build.VERSION.SDK_INT >= 31` while the surrounding text assumes 33/34
  features on the same path; the sample should show the tier gating from M2.
- §12.2's `WordEvidence` has `startMs` but no `endMs`, though §12 collects "RecognitionPart timing"
  and both forced alignment (§9.4) and wake trim (§7.3) need durations.
- Nullability is inconsistent for the same concept: `AsrHypothesis.locale: String` (§12.2) vs
  `SpeechConfusionEdge.locale: String?` (§16.4).
- §34's record has `audioProfileRevision: Int` but §8 says the winning audio profile is persisted
  "against device/firmware" — there is no field linking the two.
- Rev 2 declares it supersedes `...REV1.md`, but no voice blueprint of any revision exists in `docs/`.
  Either land both or drop the line; as it stands the lineage is unverifiable, which
  `docs/PROJECT_TRUTH_PROTOCOL.md` cares about.
- §46's external reference list is good practice. Add VAN's own locked authorities to it
  (`SECURITY_POLICY.md`, `EXTERNAL_GATES.md`, `PROJECT_TRUTH_PROTOCOL.md`,
  `visual-authority/rive_contract.json`) with a note that they outrank this blueprint.

---

## Recommended Rev 3 change list, in order

1. Rewrite §20 against A1–A5 / `CommandSensitivity`, including the A5 voice denylist. (B1)
2. Bind §20 and the Hermes dispatcher to the certified device-signed ingress: nonce, expiry,
   `turnId` idempotency, `VOICE_GRANT_REVOKED`, and a defined unreachable-emergency behavior. (B2, Mo5)
3. Classify voice as a requester against the VATI sender gate and commander fence, with an
   induced-failure test. (B3)
4. Split §2 out as a standalone overdue-release-blocker with an `EXTERNAL_GATES.md` row, not a voice
   prerequisite. (B4)
5. Re-map §27 onto `VanDurableState` + the three-zone aura, and add rows to the visual acceptance
   matrix. (B5)
6. Rebuild §34 on the `db0e988` attestation shape, extend the existing certification harness, and add
   the `EXTERNAL_GATES.md` rows to §40's definition of done. (B6)
7. Record the possibly-cloud recognizer as a current defect with a Phase 0.5 remediation. (M1)
8. Add the API capability-tier table and the API-floor sherpa-primary state. (M2)
9. Resolve the FGS ownership question and add the boot-start and Play-declaration gates. (M3)
10. Add provenance/trust to the personalization stores and exclude untrusted and secret-class
    sources. (M4)
11. Add the microphone-loss model and suspended state. (M5)
12. Close the bounded-resource gaps: second-pass turn budget, pre-roll clamp, pipe backpressure,
    store size caps. (Mo1, Mo2, Mo3, Mo7)

Items 1–3 and 10 are the security-relevant ones. Items 5, 6 and 9 are where Rev 2 would otherwise
fork VAN's governance rather than extend it.

---

## What Rev 2 gets right, and should keep

Worth stating plainly so a Rev 3 edit does not erode it: the single-microphone-owner correction and
the rejection of the KWS/`SpeechRecognizer` handoff race; the bounded pre-roll with a measured rather
than guessed window; selective second-pass ASR with a standing requirement to prove it earns its
battery; the honest correction of the Rev 1 hotword-API claim; speaker similarity as a wake-confidence
feature that can never authenticate and can never lock the owner out; word/token/span evidence
treated as first-class instead of whole-sentence substitution; context-conditioned confusion edges
with decay and owner-pinned precedence; partial certification invalidation; and the discipline of
baselining before setting thresholds. Those are the parts of Rev 2 that already match how VAN
certifies everything else, and they are the reason the rest of the document is worth fixing rather
than replacing.
