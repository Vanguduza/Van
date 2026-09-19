# VAN Voice / Speech Systems Audit (read-only)

Repo: /home/user/Van  branch: claude/van-system-audit-ysgtcd  HEAD: dff38a0
Scope: android/app/src/main/java/com/dial/van/voice/*, voice unit tests, build.gradle.kts, AndroidManifest,
VanApplication wiring, overlay/command-centre/controller integration, van_gateway command path, docs.
Method: every claim below is backed by a file:line citation. No repository files were modified.

Paths are absolute under /home/user/Van; "voice/" = android/app/src/main/java/com/dial/van/voice/.

---------------------------------------------------------------------------------------------------
## 0. Headline

The voice package is a well-designed set of *policies and shells* around Android platform services.
What is genuinely wired end-to-end today is: **tap "Voice" -> Android on-device SpeechRecognizer ->
transcript -> VanCommandController -> HMAC-v2 signed /v1/commands (origin_channel=VOICE,
speech_evidence_ref) -> gateway -> Hermes run**. Everything that makes it "Voice 2.0" — always-on
wake-word, "hie van" acknowledgement, second-pass ASR fusion, speaker similarity, barge-in, spoken
responses — is either an interface with no implementation, a class that is never constructed, or a
method that is never called.

Critically: **VAN never speaks.** `TtsOutputManager.speak()` (voice/VoiceInterfaces.kt:414) has zero
call sites in the app, and `WakeAcknowledgementManager.play()` (voice/WakeAcknowledgement.kt:110) has
zero call sites. The only "response" to a voice command is a text bubble in the chat state.

---------------------------------------------------------------------------------------------------
## 1. WAKE WORD

### 1.1 What engine performs local wake-word detection?
**None is shipped.** The wake stack is a pure scoring/decision pipeline with injectable scorers:

- `fun interface WakeWordEngine { fun score(pcm16: ByteArray): Float }` — voice/WakeRuntime.kt:31-34
- `fun interface WakePhraseVerifier { fun verify(pcm16): Float }` — voice/WakeRuntime.kt:36-39
- `fun interface SpeakerSimilarityScorer { fun similarity(pcm16): Float }` — voice/WakeRuntime.kt:41-44
- `EnergyVadGate` (RMS threshold 0.012, real code) — voice/WakeRuntime.kt:46-59
- `WakeDecisionEngine.decide()` two-stage thresholds — voice/WakeRuntime.kt:62-77
- `WakePipeline(kws, verifier, speaker?, vad, decisionEngine)` — voice/WakeRuntime.kt:79-101
- `WakeRuntimeController` feeds arbiter frames into the pipeline — voice/WakeRuntime.kt:107-140
- `WakeCoordinator` lifecycle state machine — voice/WakeCoordinator.kt:39-164

Grep for implementers of `WakeWordEngine`/`WakePhraseVerifier`/`SpeakerSimilarityScorer` in
android/app/src/main: **zero**. The only implementations are lambdas returning constants in
android/app/src/test/java/com/dial/van/voice/WakeRuntimeTest.kt:13,26-28,39-41,50-52,61-63.

Grep for constructors of `WakeCoordinator` / `WakePipeline` / `WakeRuntimeController` outside the
voice package: **zero**. `VanApplication.onCreate()` (android/app/src/main/java/com/dial/van/VanApplication.kt:59-80)
constructs `PersonalSpeechModel`, `WakeAcknowledgementManager`, `VoiceInputManager`, `TtsOutputManager`,
`VoiceSessionCoordinator` — and no wake pipeline. Nothing ever calls `WakeCoordinator.arm()`.

Dependencies: android/app/build.gradle.kts:128-161 lists Compose, lifecycle, security-crypto,
biometric, coroutines, serialization, Rive. **No Porcupine/Picovoice, Vosk, Whisper, sherpa-onnx,
onnxruntime, TFLite, ML Kit.** No `jniLibs`, no `.so/.onnx/.tflite/.ppn` anywhere under android/.
The comment "A concrete local KWS implementation is injected at construction" (WakeRuntime.kt:105)
and "independent of the concrete sherpa model bundle" (WakeCoordinator.kt:56) describe a component
that does not exist in the repo.

So: not Porcupine, not a custom model, not Android hotword, not a continuously-listening
SpeechRecognizer, and not a keyword match on a transcript. It is an **unimplemented scorer interface**.
There is also no keyword fallback: `VoiceInputManager` never looks for "hie van"/"hey van" in
transcripts (voice/VoiceInterfaces.kt:120-190 only packages hypotheses).

### 1.2 What is the wake phrase actually configured?
No wake *detection* phrase is configured anywhere (no constant, no model, no regex). The only
literal in code is the **acknowledgement** text:
`WakeAcknowledgementPolicy.TEXT = "hie van"` — voice/WakeAcknowledgement.kt:15.
`WakeWordEngine.score()` docs say "for the configured wake phrase" (WakeRuntime.kt:32) but nothing
configures one. "Hey Van" appears nowhere in code; "hie van" appears in code only as the ack string
and in docs/VAN_OWNER_AGENT_RUNTIME_REV3_EXPERT_REVIEW.md:225-251 and
docs/project-state/UNIFIED_INTELLIGENCE_IMPLEMENTATION_MATRIX.json:276. hermes/ has no wake phrase.

### 1.3 Is there a local pre-rendered acknowledgement, and does it play before network?
Pre-render code exists and is real: `WakeAcknowledgementManager` synthesizes "hie van" via
`TextToSpeech.synthesizeToFile` into `filesDir/voice/wake_ack_v1.wav` on first init
(voice/WakeAcknowledgement.kt:51-97), loads it into a `SoundPool` with `USAGE_ASSISTANT`
(:38-48, :100-108) and exposes `play()` (:110-115) and `isReady()` (:117). It is instantiated at
VanApplication.kt:66, so the asset *is* rendered at app start.

But `play()` is designed to be called by `WakeCoordinator.handleAccepted()`
(voice/WakeCoordinator.kt:88-108, via the `playAcknowledgement` lambda) — and no `WakeCoordinator`
is ever built. Grep for `wakeAcknowledgement.` or `.play()` outside voice/: zero hits.
**Result: the ack is rendered but never played. Nothing ever plays before network because nothing
plays at all.** The design intent (ack before `contextWarmup` and `beginRecognition`,
WakeCoordinator.kt:96-108) is correct but dormant.

---------------------------------------------------------------------------------------------------
## 2. CAPTURE + ASR

### 2.1 ASR engine
Android platform **on-device** `SpeechRecognizer` only:
- `SpeechRecognizer.isOnDeviceRecognitionAvailable()` gate — voice/VoiceInterfaces.kt:73-74
- `SpeechRecognizer.createOnDeviceSpeechRecognizer(appContext)` — :78-88
- Intent: `LANGUAGE_MODEL_FREE_FORM`, `EXTRA_PREFER_OFFLINE=true`, `EXTRA_MAX_RESULTS=5`,
  `EXTRA_BIASING_STRINGS` (API 33+), `EXTRA_AUDIO_SOURCE` fed from a pipe (API 33+),
  `EXTRA_REQUEST_WORD_CONFIDENCE/TIMING` (API 34+) — :268-302
- Class docstring: "It never uses the generic/cloud-capable recognizer." — :56-58
No cloud ASR, no Whisper, no sherpa. Backend tier policy `VoiceRecognitionPolicy.decide()`
(voice/VoiceRecognitionModels.kt:23-60): API>=33 with on-device -> ANDROID_ON_DEVICE_CALLER_AUDIO;
API 31-32 -> DIRECT_MIC (arbiter must yield the mic, :44); API<=30 or no on-device recognizer ->
`SHERPA_PRIMARY_REQUIRED`, and for that tier `recognizer = null` (VoiceInterfaces.kt:84-87) so
`startListening` emits `ERROR_SHERPA_PRIMARY_REQUIRED` (-10001) at :218-226. **On any device
without Google on-device recognition, voice input does not work at all.**

### 2.2 Microphone lifecycle / audio arbitration (`VoiceAudioArbiter`)
Real, careful code: single `AudioRecord` owner using `VOICE_RECOGNITION` source, 16 kHz mono PCM16
(voice/VoiceAudioArbiter.kt:51-79), AEC/NS effects enabled when available (:81-88), a 750 ms
pre-roll ring (0.5-1 s clamp, :37-40, :165-168), fan-out to registered sinks (:97-119), a bounded
non-blocking pipe to the recognizer (`VoiceAudioPipeSession`, :172-223, 24-frame queue with drop
oldest), `yieldToSystemCapture()` releases the mic (:122-124). `VoiceTurnAudioCapture` is a 30 s
per-turn evidence ring (voice/VoiceTurnAudioCapture.kt:11-45) used only to feed second-pass ASR.
No Android **AudioFocus** request anywhere (grep `AudioFocusRequest|requestAudioFocus`: none);
"arbiter" is VAN-internal ownership, not OS focus. Telephony/other-app capture interruption is
not observed by any receiver; `yieldToSystemCapture()` has no caller outside the DIRECT_MIC branch
at VoiceInterfaces.kt:241 and the dormant WakeCoordinator.

### 2.3 Endpointing / thresholds
Endpointing is delegated entirely to Android: `onEndOfSpeech` closes the pipe
(VoiceInterfaces.kt:105-111); no VAD-based end-of-utterance logic of VAN's own. No silence timeout
extras are set. Thresholds that exist in code:
- Wake: vadRms 0.012, kwsCandidate 0.58, kwsStrong 0.82, phraseAccept 0.72, phraseStrong 0.88,
  speakerSupport 0.70 — voice/WakeRuntime.kt:22-29 (dormant).
- Second-pass trigger: LOW_CONFIDENCE_THRESHOLD 0.68 — voice/VoiceSecondPass.kt:44.
- Fusion: ANDROID_WEAK 0.62, LOCAL_STRONG 0.82, CORROBORATED_LOCAL 0.72, MIN_ADVANTAGE 0.18 —
  voice/VoiceSecondPass.kt:133-136.
No confidence threshold gates *dispatch*: `VanApplication.onFinalResult` submits any non-blank
transcript regardless of `hypothesisConfidence` (VanApplication.kt:154-167).

### 2.4 VoiceSecondPass fusion
`VoiceSecondPassPolicy.decide()` (VoiceSecondPass.kt:28-45) decides to run a local pass when text
is blank, top confidence <0.68, API-34 alternative spans exist, or a known personal confusion is
flagged. `SpeechFusionEngine.fuse()` (:52-102) prefers the local result only when identical text is
not the case and (corroborated by Android hypotheses/reconstructed spans with conf>=0.72) or
(Android weak and local>=0.82) or (local advantage >=0.18 and local>=0.82). Clean, tested logic.
**But**: `interface LocalSecondPassAsr { isReady(); transcribe(pcm16, biasingStrings) }`
(:23-26) has **no implementation**, and `VoiceInputManager` is constructed with
`secondPassCoordinator = null` (default at VoiceInterfaces.kt:64; VanApplication.kt:70-74 passes
none). At :169-189 the second-pass branch is therefore skipped every time. Fusion is
IMPLEMENTED_BUT_ISOLATED.

### 2.5 PersonalSpeechModel — what does it learn/store?
It is a **confusion-edge graph + vocabulary bias list**, not acoustic adaptation
(voice/PersonalSpeechModel.kt:43-46 "deterministic data, not an agent loop"):
- Stores `SpeechConfusionEdge(observed, corrected, contexts, trust, count, lastConfirmedAtMs, pinned)`
  as JSON in `EncryptedSharedPreferences` (:32-41, :48-56, :164-208).
- `recordCorrection()` only accepts OWNER_CONFIRMED / PROJECT_TRUTH / DETERMINISTIC_STATE trust
  (:59-99, :228-235); CONVERSATION/UNTRUSTED/SECRET can never teach.
- `biasingStrings()` returns top-N `corrected` terms by a context+trust+recency+frequency score
  (:125-143, :210-222) — this is fed into `RecognizerIntent.EXTRA_BIASING_STRINGS`
  (VoiceInterfaces.kt:277-284, max 40 strings of <=64 chars).
- `correctionFor()` does exact normalized-string replacement of the *whole* transcript
  (:145-160), applied at VanApplication.kt:155 before dispatch.
**Nothing ever writes to it**: grep `recordCorrection|pinTerm` in main sources -> only the
definitions. There is no UI/flow that records an owner correction. So biasing is always empty and
`correctionFor` always returns null in the shipped app. Storage is real; learning loop is absent.

### 2.6 Barge-in
`BargeInHook` (VoiceInterfaces.kt:50-53) implemented by `TtsOutputManager.onBargeInRequested()`
(:419-430) which stops TTS. Invoked only from `VoiceSessionCoordinator.beginOwnerTurn()`
(:445-448) — i.e. barge-in is **manual** (pressing Voice while VAN speaks). Since VAN never speaks
(see §4), it can never trigger. No acoustic/VAD barge-in during TTS.

### 2.7 Background operation
`FloatingOverlayService` is a foreground service of type `specialUse`
(android/app/src/main/AndroidManifest.xml:50-57), **not** `microphone`. On Android 14+ a
microphone-using FGS without `foregroundServiceType="microphone"` cannot start mic capture from the
background. There is no `FOREGROUND_SERVICE_MICROPHONE` permission (manifest:4-12). Voice starts
only from an explicit tap: overlay `beginVoice()` (overlay/FloatingOverlayService.kt:743-747) or
Command Centre button (command/CommandCentreActivity.kt:416). No always-on background listening exists.

### 2.8 Interruption / network loss
- Recognizer errors -> `callback.onError(code)` -> `voiceUi.error` + visual warning
  (VoiceInterfaces.kt:113-118; VanApplication.kt:169-173). No retry.
- Network loss affects only dispatch: `VanCommandController.submit` catches and records
  "Command dispatch failed" (control/VanCommandController.kt:148-166, :310-324). Voice commands are
  **not** enqueued to `EncryptedCommandQueue` for replay; only notification/share ingress enqueue
  (grep `commandQueue.enqueue`: notification/VanNotificationListenerService.kt:55,
  share/ShareIntentReceiver.kt:39). ASR itself is offline (`EXTRA_PREFER_OFFLINE`).

---------------------------------------------------------------------------------------------------
## 3. TRANSCRIPT -> COMMAND

Exact path:
1. `VoiceInputManager.listener.onResults` builds `VoiceRecognitionResult(turnId, text, hypotheses,
   confidence, words, alternatives, backend, ...)` — VoiceInterfaces.kt:120-167; `speechEvidenceRef =
   "android://voice/$turnId"` is a derived string, VoiceRecognitionModels.kt:92.
2. `finishRecognition` -> `callback.onFinalResult(result)` — :262-266.
3. `VanApplication.onFinalResult` applies `correctionFor`, updates UI, and calls
   `commandController.submitText(text, VOICE, turnId, speechEvidenceRef)` — VanApplication.kt:154-167.
4. `VanCommandController.submitText` sets `idempotencyKey = "voice:$turnId"` (:106-110), wraps a
   `VanOwnerCommand(actionClass="A1")` and calls `gateway.dispatchCommand(... originChannel="VOICE",
   speechEvidenceRef ...)` — control/VanCommandController.kt:93-167, :326-331.
5. `VanGatewayClient.dispatchCommand` builds the v2 canonical string including `turnId`,
   `originChannel`, `speechEvidenceRef`, signs with device HMAC-SHA256, POSTs `/v1/commands` —
   gateway/VanGatewayClient.kt:340-425.
6. Gateway: `AuthService.canonical_command_v2` covers `speech_evidence_ref` in the HMAC
   (backend/van_gateway/auth/service.py:302, :329); orchestrator verifies (orchestrator.py:119-147),
   resolves typed intent (`self.resolver.resolve(req.text)`, :159), seals a `CommandAuthorityRecord`
   (:440-458), and passes `speech_evidence_ref`, `turn_id`, `origin_channel` to Hermes as run
   metadata (:497-524). Result: `status="accepted"`, message "Accepted and routed to Hermes profile
   van with canonical owner context and sealed authority" (:566-576).

**Signed transcript provenance (matrix claim)**: TRUE in the narrow sense — the transcript text,
turn_id, origin_channel=VOICE and speech_evidence_ref are all under the device HMAC and forwarded to
Hermes; test backend/tests/test_rev31_runtime_wiring.py:125-202 asserts `metadata["speech_evidence_ref"]`
round-trips. FALSE in the strong sense — `speech_evidence_ref` is an opaque string
`android://voice/<uuid>` that resolves to nothing: the turn PCM is discarded on close
(VoiceTurnAudioCapture.kt:36-40), no audio hash/duration/confidence is signed, and the gateway
never validates the ref format or fetches evidence. It is provenance *labelling*, not provenance.

**Voice vs typed at the gateway**: no difference. `OriginChannel.VOICE` (models.py:26) is only
(a) stored in the authority record and audit (orchestrator.py:445, :551), (b) forwarded in Hermes
metadata (:509), (c) allowed in automation capability `allowed_origin_channels` (automation/api.py:256).
No branch in orchestrator.py/resolver.py/authority.py keys on VOICE. The only client-side difference
is the deterministic idempotency key `voice:<turnId>` (VanCommandController.kt:106-107).

**Intent/context resolution**: `TypedCommandResolver.resolve()` (backend/van_gateway/command/resolver.py:115-192)
does regex exact-matching for a small action set (trading halt, NotebookLM note create, notebook
enterprise delete, research, owner-context read); everything else returns
`HERMES_INTERPRETATION_REQUIRED` / `GENERAL_OWNER_INTENT` (:188-192) and Hermes interprets. There is
no Android-side intent resolution and no conversational context carried with a voice turn (no prior
turn ids, no conversation id — grep `conversationId|multi.turn` in android: none).

---------------------------------------------------------------------------------------------------
## 4. TTS

Engine: Android platform `android.speech.tts.TextToSpeech` in `TtsOutputManager`
(voice/VoiceInterfaces.kt:362-438): `speak(text)` uses `QUEUE_FLUSH` (:414-417) and requires
`ready` set in `onInit` (:374-375); `onRangeStart` synthesizes pseudo-visemes `frame % 15` and
mouthOpen `(frame%10)/10` (:404-410) — synthetic, not from real phoneme timing.

**When does it speak?** Never. `grep -rn "\.speak(" android/app/src/main` -> only the definition at
VoiceInterfaces.kt:416. `VanApplication` constructs `ttsOutput` (:75) and implements
`TtsOutputCallback` (:180-196) to drive the avatar, but no code path calls `speak`.
`VanCommandController.recordResponse` produces *text* only ("Hermes accepted the command. Completion
has not been confirmed yet." / "The requested postcondition has been verified." /
"The command was rejected, failed, or could not be verified.", control/VanCommandController.kt:280-292)
into `VanConversationMessage` state (:294-307). Those strings are never handed to TTS.

**Does it speak "done" before verification?** It cannot speak anything, so no. If wired to these
messages, the mapping at :246-256 is honest: "accepted"/"submitted"/"executing"/"verifying" -> ACCEPTED
with "Completion has not been confirmed yet."; only "verified_success"/"succeeded"/"success"/"completed"
-> SUCCEEDED. The visual layer mirrors this (VanGatewayClient.kt:432-450: accepted -> dispatchAccepted,
verified_success -> SUCCESS). The backend test backend/tests/test_speech_sync.py:82-88 asserts
"TTS end does not imply task SUCCESS" — but note that test defines its own `SpeechCueClock` class
inline (:6-68); grep `viseme|speech_sync` in backend/van_gateway -> **no production module**. It
tests a fixture, not the gateway.

The wake **acknowledgement** is the only other spoken output design (§1.3) and it is never played.

---------------------------------------------------------------------------------------------------
## 5. MISSION BINDING

Confirmed: voice commands do NOT bind to missions.
- `orchestrator.py` imports no mission module (lines 1-24) and `grep -n mission orchestrator.py` -> 0.
- `CommandRequest` (models.py:110-134) has no `mission_id`; `VanOwnerCommand`
  (VanCommandController.kt:50-62) has no mission field; `dispatchCommand` sends none
  (VanGatewayClient.kt:340-419).
- `MissionOrigin.OWNER_VOICE` / `OriginChannel.VOICE` exist on the mission model
  (mission/models.py:111-117, :209) and `MissionService.create` accepts them (mission/service.py:70,
  :139), but missions are created only via `POST` in mission/api.py:328 by an explicit caller;
  `MissionBinder` binds browser tasks/automation runs to missions (mission/binding.py:1-19, :60),
  not commands. Backend tests use VOICE origin as fixture data only
  (test_mission_binding_api.py:106, test_mission_core.py:51).
The matrix note "Mission binding is the delta" (UNIFIED_INTELLIGENCE_IMPLEMENTATION_MATRIX.json:276)
is accurate on this point, but understates the other deltas (§9).

---------------------------------------------------------------------------------------------------
## 6. Other capabilities

| Capability | Status | Evidence |
|---|---|---|
| Push-to-talk | PARTIAL (tap-to-talk only) | overlay/FloatingOverlayService.kt:743-747, command/CommandCentreActivity.kt:416 call `beginOwnerTurn()`; no hold-to-talk, `endOwnerTurn` (VoiceInterfaces.kt:450) has no caller |
| Hands-free continuous conversation | ABSENT | `WakeCoordinator.commandTurnFinished(rearm=true)` (WakeCoordinator.kt:111-117) is the re-arm hook; never called; coordinator never built |
| Conversational continuity / multi-turn | ABSENT | no conversation id, no prior-turn refs; grep `conversationId|multi.turn|follow.up` in android main -> 0; gateway takes single `text` |
| Latency measurement / P95 | ABSENT | grep `p95|latency` android main -> only `FORMATTING_OPTIMIZE_LATENCY` extra (VoiceInterfaces.kt:285). `VoiceRecognitionResult.startedAtMs/finalizedAtMs` (VoiceRecognitionModels.kt:87-88) exist but are never read. Backend declares VOICE dimension unmeasurable: evolution/vaneval.py:78-81 |
| False-positive suppression | PARTIAL (design only) | two-stage KWS+phrase verifier+VAD with UNCERTAIN state (WakeRuntime.kt:62-77); no cooldown/debounce/refractory (grep -> 0); `onUncertain` only stores evidence (WakeCoordinator.kt:58); all dormant |

---------------------------------------------------------------------------------------------------
## 7. Tests

All three are JVM unit tests (JUnit4), run by CI `./gradlew :app:testDebugUnitTest`
(.github/workflows/van-ci.yml:93). No `androidTest/` directory exists (find -> none). No audio
fixtures (`find android -name "*.wav|*.pcm|*.ogg|*.mp3"` -> none); tests synthesize a 3200-byte
square wave (`loudPcm()`, WakeRuntimeTest.kt:74-84).

**WakeRuntimeTest.kt** (86 lines, 6 tests):
- silence rejected before KWS is invoked (:9-19)
- strong KWS+phrase accepts even with speaker 0.01 (:22-32)
- borderline KWS 0.70/phrase 0.78 + speaker 0.88 -> ACCEPT (:35-43)
- same borderline without speaker support -> UNCERTAIN (:46-54)
- phrase verifier 0.50 rejects despite KWS 0.95/speaker 0.99 (:57-65)
- energy VAD distinguishes square wave from zeros (:68-72)
All scorers are constant lambdas; tests exercise `WakeDecisionEngine` arithmetic only.

**VoiceSecondPassTest.kt** (76 lines, 6 tests): policy triggers on conf 0.41 (:10-15), not on 0.94
(:17-21), triggers on alternatives even at 0.85 (:23-32); fusion: corroborated "VEKL" 0.80 replaces
"vehicle" 0.66 (:34-45), weak local 0.71 cannot override 0.95 Android (:47-54), strong local 0.91
replaces weak 0.31 (:56-62). Pure functions with hand-built `VoiceRecognitionResult`.

**VoiceRecognitionPolicyTest.kt** (61 lines, 6 tests): API 30 -> SHERPA_PRIMARY_REQUIRED (:11-16),
API 31 -> DIRECT_MIC + yield (:19-24), API 33 -> CALLER_AUDIO without word evidence (:27-33), API 34
-> word evidence (:36-41), API 36 without on-device -> SHERPA_PRIMARY_REQUIRED (:44-47),
`PcmRingBuffer` ordering (:50-60).

Backend: backend/tests/test_speech_sync.py tests an inline `SpeechCueClock` (see §4);
test_rev31_runtime_wiring.py:125-202 proves `speech_evidence_ref`/`turn_id`/VOICE round-trip through
signature -> orchestrator -> Hermes metadata (with a fake Hermes).

Not tested anywhere: `VoiceInputManager`, `VoiceAudioArbiter`, `VoiceAudioPipeSession`,
`WakeCoordinator`, `WakeAcknowledgementManager`, `TtsOutputManager`, `PersonalSpeechModel`,
`VanApplication.onFinalResult`. Nothing runs on a device or with real audio.

---------------------------------------------------------------------------------------------------
## 8. Simulation: "Create a NotebookLM notebook for this project"

Preconditions: owner taps "Voice" (there is no wake path); device is API>=31 with Google on-device
recognition; RECORD_AUDIO granted; device enrolled with the gateway.

1. `VoiceSessionCoordinator.beginOwnerTurn()` -> `VoiceInputManager.startListening(turnId)`
   (VoiceInterfaces.kt:445-448, :207-251). Arbiter opens `AudioRecord`, pipe attaches, on-device
   recognizer starts. No ack sound, no spoken prompt. Avatar enters LISTENING
   (VanApplication.kt:175-178).
2. Partials update `voiceUi.partialTranscript` (:149-152). Android endpoints; `onResults` yields
   text e.g. "create a notebooklm notebook for this project", confidence say 0.8. Second pass is
   skipped (`secondPassCoordinator == null`). `correctionFor` returns null (empty model).
3. `submitText(source=VOICE, idempotencyKey="voice:<turnId>", actionClass="A1")`
   -> signed v2 POST with origin_channel=VOICE, speech_evidence_ref="android://voice/<turnId>".
4. Gateway resolver: the utterance does **not** match `NOTE_PATTERNS` (resolver.py:86-89 require
   "notebooklm note <title>" or "note in notebooklm <title>"), nor the enterprise delete patterns
   -> `HERMES_INTERPRETATION_REQUIRED`, `GENERAL_OWNER_INTENT` (:188-192). Effective class stays A1
   (client-signed) because canonical is None (:194-198). Note: `google.notebook.enterprise.create`
   exists in action/registry.py:37 but no resolver rule reaches it; Hermes must interpret.
5. Orchestrator seals authority, checks Hermes health, creates a Hermes run, returns
   `status="accepted"`, message "Accepted and routed to Hermes profile van with canonical owner
   context and sealed authority" (orchestrator.py:566-576).
6. Android: `recordResponse` maps "accepted" -> `VanCommandStatus.ACCEPTED`; because the wire
   `message` is non-blank, the VAN chat bubble reads the gateway sentence above
   (VanCommandController.kt:280-282), not the local "Completion has not been confirmed yet." line.
   Visual: `dispatchAccepted()` then settle to idle after 900 ms (VanGatewayClient.kt:436-439).
7. **What VAN says aloud: nothing.** No TTS call exists. Whether the notebook was actually created
   is never surfaced back to this voice turn: there is no polling of the Hermes run, no
   verified_success push into the controller, no mission created.

Would it claim success before external verification? **No spoken claim at all; the text claim is
"accepted/routed", which is honest and not a success claim.** The risk is the opposite: the owner
gets no completion feedback via voice ever. (If a future change wired `ttsOutput.speak(responseText)`,
the gateway's own message wording "Accepted and routed..." would be spoken before any verification —
acceptable, but the "sealed authority" phrasing could be heard as done. Flagging for the TTS design.)

---------------------------------------------------------------------------------------------------
## 9. Classification

| Area | Class | Why |
|---|---|---|
| Wake word | STUB | Interfaces + decision engine + coordinator exist (WakeRuntime.kt, WakeCoordinator.kt) with zero engine implementations, zero constructions, no dependency. Unit-tested with constants only. |
| Wake acknowledgement ("hie van") | IMPLEMENTED_BUT_ISOLATED | Pre-render + SoundPool real (WakeAcknowledgement.kt:33-155) and instantiated (VanApplication.kt:66); `play()` never called. |
| ASR (capture + on-device recognizer) | INTEGRATED | Tap -> arbiter -> on-device SpeechRecognizer -> transcript -> controller (VoiceInterfaces.kt:59-359, VanApplication.kt:154-167). Not E2E_VERIFIED: no device/instrumentation test, no recorded fixtures; fails hard on devices without Google on-device ASR. |
| Second-pass ASR fusion | IMPLEMENTED_BUT_ISOLATED | Policy/fusion real and unit-tested; `LocalSecondPassAsr` has no implementation; coordinator wired as null. |
| PersonalSpeechModel | PARTIAL | Encrypted store + scoring + bias export real and wired to recognizer bias (VanApplication.kt:73); no write path (`recordCorrection`/`pinTerm` never called) so it is always empty; it is a bias list/confusion map, not adaptation. |
| TTS | IMPLEMENTED_BUT_ISOLATED | `TtsOutputManager` real, constructed, callbacks drive avatar; `speak()` has no caller. VAN is mute. |
| Transcript -> signed command | INTEGRATED | Full path to gateway with HMAC-covered turn_id/origin_channel/speech_evidence_ref (VanGatewayClient.kt:365-385; auth/service.py:329). Provenance is a label; audio evidence not retained. |
| Barge-in | STUB | Manual hook only via `beginOwnerTurn`; no acoustic barge-in; unreachable because TTS never speaks. |
| Background / always-on | ABSENT | FGS type `specialUse`, no `microphone` FGS type, no wake arm call. |
| Mission binding | ABSENT | No mission id on commands; orchestrator has no mission import. |
| Speaker similarity | STUB | Interface only (WakeRuntime.kt:41-44). |
| Latency / P95 | ABSENT | Timestamps exist but unread; backend declares VOICE unmeasurable (vaneval.py:78-81). |

Matrix WS28 "EXISTS_UPGRADE ... all exist. Mission binding is the delta"
(UNIFIED_INTELLIGENCE_IMPLEMENTATION_MATRIX.json:273-280) overstates: wake pipeline and second-pass
"exist" as untethered policy code; the ack exists but is never played; no KWS engine, no local ASR
engine, no spoken output. The honest delta list is: KWS engine, phrase verifier, local ASR engine,
wake arming in a mic-typed FGS, ack playback, TTS invocation, correction capture UI, mission binding.

---------------------------------------------------------------------------------------------------
## 10. Stubs / interfaces without implementation / dead wiring (file:line)

Interfaces with no concrete class in app sources:
- voice/WakeRuntime.kt:31 `WakeWordEngine`
- voice/WakeRuntime.kt:36 `WakePhraseVerifier`
- voice/WakeRuntime.kt:41 `SpeakerSimilarityScorer`
- voice/VoiceSecondPass.kt:23 `LocalSecondPassAsr`

Classes never constructed in app sources:
- voice/WakeRuntime.kt:79 `WakePipeline` (test-only)
- voice/WakeRuntime.kt:107 `WakeRuntimeController`
- voice/WakeCoordinator.kt:39 `WakeCoordinator`
- voice/VoiceSecondPass.kt:140 `VoiceSecondPassCoordinator`

Public methods with no caller in app sources:
- voice/VoiceInterfaces.kt:414 `TtsOutputManager.speak()`  -> VAN never speaks
- voice/WakeAcknowledgement.kt:110 `WakeAcknowledgementManager.play()` -> ack never played
- voice/WakeAcknowledgement.kt:117/119 `isReady()/status()` -> readiness never checked
- voice/PersonalSpeechModel.kt:59 `recordCorrection()`, :101 `pinTerm()` -> model never learns
- voice/VoiceInterfaces.kt:450 `VoiceSessionCoordinator.endOwnerTurn()` -> no explicit stop
- voice/WakeCoordinator.kt:111 `commandTurnFinished()`, :120 `yieldToSystemCapture()`,
  :127 `resumeAfterSystemCapture()`, :139 `revokeAuthority()`
- voice/VoiceAudioArbiter.kt:122 `yieldToSystemCapture()` (only DIRECT_MIC branch at VoiceInterfaces.kt:241)

Constructor parameters always defaulted to no-op in the only construction site (VanApplication.kt:70-74):
- `secondPassCoordinator = null` (VoiceInterfaces.kt:64)
- `personalConfusionProvider = { false }` (VoiceInterfaces.kt:65)

Backend tiers that cannot work:
- voice/VoiceRecognitionModels.kt:45-59 `SHERPA_PRIMARY_REQUIRED` -> VoiceInterfaces.kt:84-87
  recognizer=null -> :221-223 emits `ERROR_SHERPA_PRIMARY_REQUIRED`; `SHERPA_PRIMARY` and
  `FUSED_ANDROID_SHERPA` backends (VoiceRecognitionModels.kt:6-7) have no engine.

Synthetic/placeholder data:
- voice/VoiceInterfaces.kt:404-410 visemes from `frame % 15`, mouthOpen from `frame % 10`
  (not phoneme-derived).
- voice/VoiceRecognitionModels.kt:92 `speechEvidenceRef = "android://voice/$turnId"` — a URI that
  nothing serves.

Comments describing components not present:
- voice/WakeRuntime.kt:105 "A concrete local KWS implementation is injected at construction."
- voice/WakeCoordinator.kt:56 "independent of the concrete sherpa model bundle"
- android/README.md:50 "voice/ VoiceInputManager, TtsOutputManager, barge-in, speech sync frames"

Backend:
- backend/tests/test_speech_sync.py:6-68 `SpeechCueClock` defined inside the test; no production
  counterpart in backend/van_gateway.
- backend/van_gateway/evolution/vaneval.py:78-81 VOICE explicitly "unmeasurable without owner data".

No literal `TODO`/`FIXME`/`stub`/`placeholder` markers exist in voice/ or the three integration
files (grep -> 0); the gaps are structural, not annotated.

---------------------------------------------------------------------------------------------------
## 11. Notable design observations (non-blocking)

- Expert review M1 (docs/VAN_OWNER_AGENT_RUNTIME_REV3_EXPERT_REVIEW.md:225-260) flags that a spoken
  "hie van" overlaps owner speech captured by pre-roll. Code partially addresses the TTS cold-start
  half (pre-rendered WAV via SoundPool) but the overlap/AEC certification concern is unaddressed and
  moot while nothing plays.
- `WakeCoordinator.arm()` refuses to arm unless `acknowledgementReady()` (WakeCoordinator.kt:71-74)
  — good fail-closed design, would need the ack asset to exist before wake can ever be enabled.
- `VoiceRecognitionPolicy` API-31/32 tier forces the arbiter to release the mic
  (VoiceInterfaces.kt:241), meaning wake and command recognition could never share capture on those
  devices even if wake were implemented.
- The `speech_evidence_ref` in the HMAC gives replay/idempotency binding (`voice:<turnId>`) but no
  audio integrity. To make "signed transcript provenance" real, the ref would need to carry a hash of
  the turn PCM (VoiceTurnAudioCapture already holds it during the turn) and the gateway would need to
  validate/retain it.
