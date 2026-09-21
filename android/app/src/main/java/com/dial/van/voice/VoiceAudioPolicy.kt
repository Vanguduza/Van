package com.dial.van.voice

/**
 * Rev 1.5 §§21.6, 21.7, 21.21, 21.22 — the microphone, the pre-roll, barge-in, and who
 * ducks for whom.
 *
 * Four decisions that are all about audio and are all made locally, which is the point:
 * §21.21 says barge-in stops playback without Hermes acknowledging anything. A design where
 * the semantic interruption event had to round-trip before the audio stopped would mean the
 * owner talks over VAN for as long as the network takes.
 */

/** §21.6 — the consumers that subscribe to the one capture stream. */
enum class CaptureConsumer {
    WAKE_DETECTOR,
    VAD,
    TURN_EVIDENCE_BUFFER,
    ASR,
    BARGE_IN_DETECTOR,
    RMS_VISUAL_SYNC,
}

object CaptureOwnership {
    /**
     * §21.6 — one component owns `AudioRecord`, and it is `VoiceAudioArbiter`.
     *
     * Stated as a constant because the failure of getting it wrong is not a crash: a second
     * microphone session fights Android's audio focus, and the symptom is the *first* few
     * hundred milliseconds of the owner's sentence disappearing, intermittently.
     */
    const val OWNER = "VoiceAudioArbiter"

    /** Every consumer subscribes; none of them opens the microphone. */
    fun subscribersOnly(): Set<CaptureConsumer> = CaptureConsumer.entries.toSet()
}

/**
 * §21.7 — the circular PCM buffer that keeps the start of an utterance.
 *
 * Without it, the wake detector fires, the turn opens, and the first syllable after the
 * wake word is already gone — the owner says "Hey Van, delete the—" and VAN hears "delete
 * the". Bounded and in memory, never written to disk outside an explicit diagnostic mode,
 * because it is a continuous recording of the room.
 */
object PreRollPolicy {
    const val MIN_MS = 500
    const val TARGET_MS = 800
    const val MAX_MS = 1_000

    /** 16 kHz mono 16-bit, which is what the recogniser wants. */
    const val SAMPLE_RATE_HZ = 16_000
    const val BYTES_PER_SAMPLE = 2

    fun bufferBytes(milliseconds: Int = TARGET_MS): Int {
        val clamped = milliseconds.coerceIn(MIN_MS, MAX_MS)
        return SAMPLE_RATE_HZ * BYTES_PER_SAMPLE * clamped / 1000
    }

    /**
     * Whether captured audio may be written to storage.
     *
     * False unless diagnostics are explicitly on. The pre-roll is a rolling recording of
     * whatever is happening near the phone, and "it was useful for debugging" is how that
     * ends up in a log directory.
     */
    fun mayPersist(diagnosticEvidenceModeEnabled: Boolean): Boolean = diagnosticEvidenceModeEnabled
}

/** §21.21 — what a detected owner voice does to playback, in order. */
enum class BargeInStep {
    STOP_PLAYBACK,
    MARK_SEGMENTS_INTERRUPTED,
    ENTER_LISTENING,
    BEGIN_LOCAL_ASR_TURN,
    SEND_SEMANTIC_INTERRUPTION_WHEN_TRANSPORT_ALLOWS,
}

object BargeInPolicy {

    /**
     * A segment declared non-interruptible is not interrupted by speech.
     *
     * The case this is for: a confirmation VAN is reading back before an irreversible
     * action. Cutting that off halfway leaves the owner with half a sentence and a pending
     * action, which is worse than making them wait two seconds.
     */
    fun mayInterrupt(segment: SpeechSegment?): Boolean = segment?.interruptible ?: true

    /**
     * The sequence, with the local steps first.
     *
     * The ordering is the guarantee: playback stops before anything is sent anywhere.
     * Hermes does not need to acknowledge before the audio stops, and a version that
     * notified first would make barge-in as slow as the network.
     */
    fun sequence(): List<BargeInStep> = listOf(
        BargeInStep.STOP_PLAYBACK,
        BargeInStep.MARK_SEGMENTS_INTERRUPTED,
        BargeInStep.ENTER_LISTENING,
        BargeInStep.BEGIN_LOCAL_ASR_TURN,
        BargeInStep.SEND_SEMANTIC_INTERRUPTION_WHEN_TRANSPORT_ALLOWS,
    )

    /**
     * Whether this audio is the owner talking rather than VAN's own voice coming back in.
     *
     * The phone hears itself. Without the echo guard every answer barges in on itself after
     * the first loud syllable, and VAN becomes unable to finish a sentence.
     */
    fun isOwnerSpeech(
        rms: Float,
        thresholdRms: Float,
        withinPlaybackEchoWindow: Boolean,
        vadSaysSpeech: Boolean,
    ): Boolean = vadSaysSpeech && rms >= thresholdRms && !withinPlaybackEchoWindow
}

/** §21.22 — what happens to the browser's audio when VAN speaks over it. */
enum class DuckingAction {
    DUCK_OTHER_AUDIO,
    PAUSE_OTHER_AUDIO,
    /** VAN stays quiet: something with more right to the audio is using it. */
    YIELD,
    NONE,
}

object AudioFocusPolicy {

    /**
     * Decide what to do with whatever else is making noise.
     *
     * The one that must not be got wrong is the call: an incoming call takes the audio and
     * VAN waits, because a website's video and a phone call are not the same claim on the
     * owner's attention. A design that ducked a call to read out a search result would be
     * a bug the owner experiences in public.
     */
    fun decide(
        vanIsSpeaking: Boolean,
        browserAudioPlaying: Boolean,
        callInProgress: Boolean,
        otherMediaHasFocus: Boolean,
    ): DuckingAction = when {
        callInProgress -> DuckingAction.YIELD
        !vanIsSpeaking -> DuckingAction.NONE
        // A page playing video is paused rather than ducked: ducked speech under a
        // voiceover is still unintelligible, which §21.22 names directly.
        browserAudioPlaying -> DuckingAction.PAUSE_OTHER_AUDIO
        otherMediaHasFocus -> DuckingAction.DUCK_OTHER_AUDIO
        else -> DuckingAction.NONE
    }

    /**
     * Whether what was paused should be resumed once VAN stops.
     *
     * Only what VAN itself paused. Resuming audio the owner paused is VAN pressing play on
     * something they deliberately stopped.
     */
    fun shouldRestore(action: DuckingAction): Boolean =
        action == DuckingAction.PAUSE_OTHER_AUDIO || action == DuckingAction.DUCK_OTHER_AUDIO
}
