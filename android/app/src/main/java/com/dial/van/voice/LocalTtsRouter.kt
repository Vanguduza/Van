package com.dial.van.voice

/**
 * Rev 1.5 §§21.5, 21.18, 21.20 — which engine speaks, and what happens when none can.
 *
 * §21.18's rule, and the reason for it: "a system TTS voice whose offline data disappeared
 * after an OS change cannot be the only production talk-back path." That is not
 * hypothetical — Android's offline voice data is a downloadable component that an OS update
 * can remove, and a VAN that discovered this at the moment it tried to answer would simply
 * go quiet.
 *
 * So there are three engines with a strict order, and the critical phrase bank is separate
 * from all of them. §21.5 requires the wake acknowledgement to be pre-rendered: it must not
 * wait for ASR, for a synthesiser to initialise, or for Hermes. An acknowledgement that has
 * to be synthesised is an acknowledgement that arrives after the owner has started talking.
 */
enum class TtsEngineKind {
    /**
     * VAN-owned offline synthesis through sherpa-onnx OfflineTts.
     *
     * The engine is considered usable only after the checksum-pinned LOCAL_TTS bundle is
     * present and [SherpaLocalTtsRuntime.prepare] has created/self-tested the runtime.
     * Playback is VAN-owned PCM through AudioTrack, so barge-in can stop the actual audio
     * and avatar RMS comes from the samples being played.
     */
    SHERPA_ONNX,

    /** Android's own, usable only when verified offline voice data is installed. */
    ANDROID_OFFLINE,

    /** Pre-rendered audio for a fixed set of phrases. Never synthesised, never late. */
    CRITICAL_PHRASE_BANK,
}

/** What an engine can currently do, as opposed to what it is for. */
data class TtsEngineReadiness(
    val kind: TtsEngineKind,
    val installed: Boolean,
    /**
     * Android only: whether its *offline* data is present. An Android engine that is
     * installed but needs the network is worse than one that is absent, because it reports
     * itself available and then fails at the moment of speaking.
     */
    val offlineDataVerified: Boolean = true,
    val selfTestPassed: Boolean = true,
) {
    val usableOffline: Boolean
        get() = installed && offlineDataVerified && selfTestPassed
}

sealed class TtsSelection {
    data class Engine(val kind: TtsEngineKind, val why: String) : TtsSelection()

    /**
     * Nothing can speak. Carries the sentence VAN shows instead, because going quiet with
     * no explanation is indistinguishable from VAN having nothing to say.
     */
    data class Silent(val reason: String, val ownerSentence: String) : TtsSelection()
}

/** What is being spoken, which decides which engine is even eligible. */
enum class SpeechKind {
    /** Anything VAN composed: an answer, a summary, a read-back. */
    ASSISTANT_ANSWER,

    /** A fixed phrase from the bank: the wake acknowledgement, a failure notice. */
    CRITICAL_PHRASE,
}

object LocalTtsRouter {

    /**
     * §21.5 — the phrases that must never be synthesised on demand.
     *
     * Each one is spoken at a moment when waiting is the failure: the wake ack is the
     * owner's evidence that VAN heard them, and the others are said when something is
     * already wrong and a synthesiser may be part of what is wrong.
     */
    val CRITICAL_PHRASES: Map<String, String> = mapOf(
        "wake_ack" to "Hie Van",
        "offline" to "I can't reach Hermes right now.",
        "listening" to "I'm listening.",
        "stopped" to "Stopped.",
        "cannot_speak" to "I can't speak aloud right now.",
    )

    fun select(
        kind: SpeechKind,
        engines: Map<TtsEngineKind, TtsEngineReadiness>,
        phraseKey: String? = null,
    ): TtsSelection {
        if (kind == SpeechKind.CRITICAL_PHRASE) {
            val bank = engines[TtsEngineKind.CRITICAL_PHRASE_BANK]
            if (bank?.usableOffline == true && phraseKey != null && phraseKey in CRITICAL_PHRASES) {
                return TtsSelection.Engine(
                    TtsEngineKind.CRITICAL_PHRASE_BANK,
                    "pre-rendered, so it does not wait for a synthesiser",
                )
            }
            // Falling through to a synthesiser for a critical phrase is allowed and is
            // worse: it is late. It is not silent, which is worse still, so the order is
            // bank, then whatever can speak.
        }

        val sherpa = engines[TtsEngineKind.SHERPA_ONNX]
        if (sherpa?.usableOffline == true) {
            return TtsSelection.Engine(
                TtsEngineKind.SHERPA_ONNX,
                "VAN's checksum-pinned sherpa-onnx voice, rendered locally",
            )
        }

        val android = engines[TtsEngineKind.ANDROID_OFFLINE]
        if (android?.usableOffline == true) {
            return TtsSelection.Engine(
                TtsEngineKind.ANDROID_OFFLINE,
                "Android's voice, with its offline data verified",
            )
        }
        if (android?.installed == true && !android.offlineDataVerified) {
            // Named separately because it is the §21.18 failure exactly: the engine is
            // there, reports itself available, and needs a network VAN may not have.
            return TtsSelection.Silent(
                "android_tts_offline_data_missing",
                "I can't answer aloud — my voice needs data this phone no longer has.",
            )
        }

        val bank = engines[TtsEngineKind.CRITICAL_PHRASE_BANK]
        if (bank?.usableOffline == true && kind == SpeechKind.CRITICAL_PHRASE) {
            return TtsSelection.Engine(TtsEngineKind.CRITICAL_PHRASE_BANK, "the only voice left")
        }

        return TtsSelection.Silent(
            "no_usable_tts_engine",
            "I can't answer aloud right now — it's on the screen instead.",
        )
    }

    /**
     * §21.5's guarantee, as a question the wake path can ask before it starts listening.
     *
     * If this is false the owner gets no acknowledgement, which means they do not know VAN
     * heard them, which means they repeat themselves into a microphone that is already
     * recording. Worth knowing before the wake word rather than after it.
     */
    fun wakeAcknowledgementAvailable(engines: Map<TtsEngineKind, TtsEngineReadiness>): Boolean =
        engines[TtsEngineKind.CRITICAL_PHRASE_BANK]?.usableOffline == true

    /** §21.20 — the latency budgets, mirrored so the phone can report a miss rather than hide it. */
    object Slo {
        const val WAKE_ACK_START_MS = 150L
        const val VAD_FINALIZATION_MS = 250L
        const val ASR_FINAL_AFTER_SPEECH_MS = 700L
        const val TTS_FIRST_AUDIO_MS = 500L
        const val BARGE_IN_STOP_MS = 100L
        const val LISTEN_AFTER_BARGE_IN_MS = 150L
    }

    /**
     * Whether a measured latency met its budget.
     *
     * Returns the miss rather than a boolean so the caller can report *which* stage was
     * slow. "Voice was slow" is not actionable; "first audio took 900ms against a 500ms
     * budget" is.
     */
    fun slowStages(
        wakeAckMs: Long? = null,
        asrFinalMs: Long? = null,
        ttsFirstAudioMs: Long? = null,
        bargeInStopMs: Long? = null,
    ): Map<String, Pair<Long, Long>> {
        val misses = linkedMapOf<String, Pair<Long, Long>>()
        fun check(name: String, measured: Long?, budget: Long) {
            if (measured != null && measured > budget) misses[name] = measured to budget
        }
        check("wake acknowledgement", wakeAckMs, Slo.WAKE_ACK_START_MS)
        check("transcript", asrFinalMs, Slo.ASR_FINAL_AFTER_SPEECH_MS)
        check("first audio", ttsFirstAudioMs, Slo.TTS_FIRST_AUDIO_MS)
        check("stopping when you spoke", bargeInStopMs, Slo.BARGE_IN_STOP_MS)
        return misses
    }
}
