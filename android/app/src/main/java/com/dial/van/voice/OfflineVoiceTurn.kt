package com.dial.van.voice

/** Bounded local endpointing for the actual EnergyVadGate-fed Sherpa primary turn. */
class OfflineVoiceTurn(
    private val sampleRateHz: Int = 16_000,
    private val endSilenceMs: Long = 600,
    private val initialSilenceMs: Long = 8_000,
    private val maximumMs: Long = 30_000,
) {
    enum class State { CAPTURING, FINALIZE, NO_SPEECH, TOO_LONG }
    private var elapsedSamples = 0L
    private var speechSamples = 0L
    private var silenceSamples = 0L
    private var terminal: State? = null

    @Synchronized
    fun accept(pcmBytes: Int, speech: Boolean): State {
        terminal?.let { return it }
        require(pcmBytes >= 0 && pcmBytes % 2 == 0)
        val samples = pcmBytes / 2L
        elapsedSamples += samples
        if (speech) {
            speechSamples += samples
            silenceSamples = 0
        } else {
            silenceSamples += samples
        }
        val heardSpeech = speechSamples * 1000 / sampleRateHz >= 200
        val state = when {
            elapsedSamples * 1000 / sampleRateHz >= maximumMs ->
                if (heardSpeech) State.TOO_LONG else State.NO_SPEECH
            heardSpeech && silenceSamples * 1000 / sampleRateHz >= endSilenceMs -> State.FINALIZE
            !heardSpeech && elapsedSamples * 1000 / sampleRateHz >= initialSilenceMs -> State.NO_SPEECH
            else -> State.CAPTURING
        }
        if (state != State.CAPTURING) terminal = state
        return state
    }

    @Synchronized
    fun heardSpeech(): Boolean = speechSamples * 1000 / sampleRateHz >= 200
}
