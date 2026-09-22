package com.dial.van.voice

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Rev 1.5 §§21.5, 21.6, 21.7, 21.18, 21.20, 21.21, 21.22 — who speaks, who listens, and who
 * gives way.
 *
 * The three failures worth naming, all of which these cover:
 *
 *  * Android's offline TTS data is a downloadable component an OS update can remove. An
 *    engine that reports itself installed and then needs a network is worse than one that
 *    is absent, because VAN discovers it at the moment it tries to answer;
 *  * the phone hears its own speaker. Without an echo guard, every answer barges in on
 *    itself after the first loud syllable and VAN cannot finish a sentence;
 *  * a website's video and an incoming call are not the same claim on the owner's audio.
 */
class LocalTtsRouterTest {

    private fun engines(
        sherpa: Boolean = false,
        android: Boolean = false,
        androidOfflineData: Boolean = true,
        bank: Boolean = false,
    ) = mapOf(
        TtsEngineKind.SHERPA_ONNX to TtsEngineReadiness(TtsEngineKind.SHERPA_ONNX, sherpa),
        TtsEngineKind.ANDROID_OFFLINE to TtsEngineReadiness(
            TtsEngineKind.ANDROID_OFFLINE, android, offlineDataVerified = androidOfflineData,
        ),
        TtsEngineKind.CRITICAL_PHRASE_BANK to TtsEngineReadiness(
            TtsEngineKind.CRITICAL_PHRASE_BANK, bank,
        ),
    )

    @Test
    fun `a prepared sherpa voice is preferred over Android for assistant answers`() {
        val selection = LocalTtsRouter.select(
            SpeechKind.ASSISTANT_ANSWER, engines(sherpa = true, android = true),
        )
        assertEquals(TtsEngineKind.SHERPA_ONNX, (selection as TtsSelection.Engine).kind)
    }

    @Test
    fun `the sherpa voice can speak with no Android offline voice installed`() {
        val selection = LocalTtsRouter.select(SpeechKind.ASSISTANT_ANSWER, engines(sherpa = true))
        assertEquals(TtsEngineKind.SHERPA_ONNX, (selection as TtsSelection.Engine).kind)
    }

    @Test
    fun `android is used only when its offline data is verified`() {
        val ok = LocalTtsRouter.select(SpeechKind.ASSISTANT_ANSWER, engines(android = true))
        assertEquals(TtsEngineKind.ANDROID_OFFLINE, (ok as TtsSelection.Engine).kind)
    }

    @Test
    fun `an android engine whose offline data vanished is named rather than tried`() {
        // §21.18's exact case. The engine is installed, reports itself available, and needs
        // a network VAN may not have — so VAN says what happened instead of going quiet.
        val selection = LocalTtsRouter.select(
            SpeechKind.ASSISTANT_ANSWER, engines(android = true, androidOfflineData = false),
        )
        val silent = selection as TtsSelection.Silent
        assertEquals("android_tts_offline_data_missing", silent.reason)
        assertTrue(silent.ownerSentence.contains("data this phone no longer has"))
    }

    @Test
    fun `the wake acknowledgement comes from the phrase bank, not a synthesiser`() {
        // §21.5 — it must not wait for a synthesiser to initialise. One that is synthesised
        // arrives after the owner has started talking.
        val selection = LocalTtsRouter.select(
            SpeechKind.CRITICAL_PHRASE, engines(sherpa = true, bank = true), phraseKey = "wake_ack",
        )
        assertEquals(TtsEngineKind.CRITICAL_PHRASE_BANK, (selection as TtsSelection.Engine).kind)
    }

    @Test
    fun `a critical phrase with no bank falls through to the best real synthesiser`() {
        // Late is worse than immediate and much better than nothing. If VAN's local model
        // is prepared it wins; Android remains the fallback when it is not.
        val sherpa = LocalTtsRouter.select(
            SpeechKind.CRITICAL_PHRASE, engines(sherpa = true, android = true), phraseKey = "wake_ack",
        )
        assertEquals(TtsEngineKind.SHERPA_ONNX, (sherpa as TtsSelection.Engine).kind)

        val android = LocalTtsRouter.select(
            SpeechKind.CRITICAL_PHRASE, engines(android = true), phraseKey = "wake_ack",
        )
        assertEquals(TtsEngineKind.ANDROID_OFFLINE, (android as TtsSelection.Engine).kind)
    }

    @Test
    fun `no engine at all says so instead of failing silently`() {
        val silent = LocalTtsRouter.select(SpeechKind.ASSISTANT_ANSWER, engines()) as TtsSelection.Silent
        assertEquals("no_usable_tts_engine", silent.reason)
        assertTrue(silent.ownerSentence.contains("on the screen instead"))
    }

    @Test
    fun `the wake path can ask whether it will be able to acknowledge`() {
        // Worth knowing before the wake word: with no acknowledgement the owner does not
        // know VAN heard them, so they repeat themselves into a live microphone.
        assertTrue(LocalTtsRouter.wakeAcknowledgementAvailable(engines(bank = true)))
        assertFalse(LocalTtsRouter.wakeAcknowledgementAvailable(engines(sherpa = true)))
    }

    @Test
    fun `a missed budget names the stage rather than saying voice was slow`() {
        val misses = LocalTtsRouter.slowStages(wakeAckMs = 400, ttsFirstAudioMs = 900)
        assertEquals(setOf("wake acknowledgement", "first audio"), misses.keys)
        assertEquals(400L to 150L, misses["wake acknowledgement"])
    }

    @Test
    fun `a stage inside its budget is not reported`() {
        assertTrue(LocalTtsRouter.slowStages(wakeAckMs = 120, ttsFirstAudioMs = 300).isEmpty())
    }

    @Test
    fun `the wake acknowledgement phrase is the one the owner contract names`() {
        assertEquals("Hie Van", LocalTtsRouter.CRITICAL_PHRASES["wake_ack"])
    }
}

class BargeInPolicyTest {

    @Test
    fun `playback stops before anything is sent anywhere`() {
        // §21.21 — Hermes does not need to acknowledge before the audio stops. A version
        // that notified first would make barge-in as slow as the network.
        val sequence = BargeInPolicy.sequence()
        assertEquals(BargeInStep.STOP_PLAYBACK, sequence.first())
        assertEquals(BargeInStep.SEND_SEMANTIC_INTERRUPTION_WHEN_TRANSPORT_ALLOWS, sequence.last())
    }

    @Test
    fun `VAN does not interrupt itself on its own voice`() {
        // The phone hears its own speaker. Without this, every answer cuts itself off.
        assertFalse(
            BargeInPolicy.isOwnerSpeech(
                rms = 0.9f, thresholdRms = 0.3f,
                withinPlaybackEchoWindow = true, vadSaysSpeech = true,
            ),
        )
    }

    @Test
    fun `the owner speaking does interrupt`() {
        assertTrue(
            BargeInPolicy.isOwnerSpeech(
                rms = 0.9f, thresholdRms = 0.3f,
                withinPlaybackEchoWindow = false, vadSaysSpeech = true,
            ),
        )
    }

    @Test
    fun `room noise below the threshold does not interrupt`() {
        assertFalse(
            BargeInPolicy.isOwnerSpeech(
                rms = 0.1f, thresholdRms = 0.3f,
                withinPlaybackEchoWindow = false, vadSaysSpeech = true,
            ),
        )
    }

    @Test
    fun `a confirmation being read back is not interruptible`() {
        // Cutting off a read-back before an irreversible action leaves the owner with half
        // a sentence and a pending action.
        val confirmation = SpeechSegment(
            responseId = "r", speechStreamId = "s", segmentId = "s_0",
            segmentIndex = 0, text = "Send 400 to...", interruptible = false,
        )
        assertFalse(BargeInPolicy.mayInterrupt(confirmation))
    }

    @Test
    fun `an ordinary answer is interruptible and so is nothing at all`() {
        val ordinary = SpeechSegment("r", "s", "s_0", 0, "The answer is...")
        assertTrue(BargeInPolicy.mayInterrupt(ordinary))
        assertTrue(BargeInPolicy.mayInterrupt(null))
    }
}

class AudioFocusPolicyTest {

    @Test
    fun `an incoming call takes the audio and VAN waits`() {
        // Ducking a call to read out a search result is a bug the owner experiences in
        // public.
        assertEquals(
            DuckingAction.YIELD,
            AudioFocusPolicy.decide(
                vanIsSpeaking = true, browserAudioPlaying = true,
                callInProgress = true, otherMediaHasFocus = true,
            ),
        )
    }

    @Test
    fun `a page playing video is paused rather than ducked`() {
        // §21.22 — ducked speech under a voiceover is still unintelligible.
        assertEquals(
            DuckingAction.PAUSE_OTHER_AUDIO,
            AudioFocusPolicy.decide(
                vanIsSpeaking = true, browserAudioPlaying = true,
                callInProgress = false, otherMediaHasFocus = false,
            ),
        )
    }

    @Test
    fun `other media is ducked`() {
        assertEquals(
            DuckingAction.DUCK_OTHER_AUDIO,
            AudioFocusPolicy.decide(
                vanIsSpeaking = true, browserAudioPlaying = false,
                callInProgress = false, otherMediaHasFocus = true,
            ),
        )
    }

    @Test
    fun `VAN not speaking takes nothing`() {
        assertEquals(
            DuckingAction.NONE,
            AudioFocusPolicy.decide(
                vanIsSpeaking = false, browserAudioPlaying = true,
                callInProgress = false, otherMediaHasFocus = true,
            ),
        )
    }

    @Test
    fun `only what VAN paused is resumed`() {
        // Resuming audio the owner paused is VAN pressing play on something they stopped.
        assertTrue(AudioFocusPolicy.shouldRestore(DuckingAction.PAUSE_OTHER_AUDIO))
        assertFalse(AudioFocusPolicy.shouldRestore(DuckingAction.YIELD))
        assertFalse(AudioFocusPolicy.shouldRestore(DuckingAction.NONE))
    }
}

class PreRollPolicyTest {

    @Test
    fun `the buffer is long enough to keep the start of a sentence`() {
        // Without it the owner says "Hey Van, delete the—" and VAN hears "delete the".
        val bytes = PreRollPolicy.bufferBytes()
        assertEquals(16_000 * 2 * 800 / 1000, bytes)
    }

    @Test
    fun `the buffer is bounded at both ends`() {
        assertEquals(PreRollPolicy.bufferBytes(PreRollPolicy.MIN_MS), PreRollPolicy.bufferBytes(1))
        assertEquals(PreRollPolicy.bufferBytes(PreRollPolicy.MAX_MS), PreRollPolicy.bufferBytes(99_999))
    }

    @Test
    fun `captured audio is not written to storage by default`() {
        // The pre-roll is a rolling recording of whatever is happening near the phone.
        assertFalse(PreRollPolicy.mayPersist(diagnosticEvidenceModeEnabled = false))
        assertTrue(PreRollPolicy.mayPersist(diagnosticEvidenceModeEnabled = true))
    }

    @Test
    fun `one component owns the microphone and everything else subscribes`() {
        // A second microphone session fights audio focus, and the symptom is the first
        // syllables disappearing, intermittently.
        assertEquals("VoiceAudioArbiter", CaptureOwnership.OWNER)
        assertEquals(CaptureConsumer.entries.size, CaptureOwnership.subscribersOnly().size)
    }
}
