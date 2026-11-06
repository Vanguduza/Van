package com.dial.van.voice

import java.util.concurrent.atomic.AtomicLong

/** Queued segments share an epoch; cancellation permanently invalidates their late PCM/callbacks. */
class SpeechPlaybackEpoch {
    private val generation = AtomicLong()
    fun snapshot(): Long = generation.get()
    fun isCurrent(epoch: Long): Boolean = generation.get() == epoch
    fun cancel() { generation.incrementAndGet() }
}

/** Exact native utterance admission. The manager serializes callbacks and side effects. */
class SpeechPlaybackState {
    data class Token(val engine: TtsEngineKind, val utteranceId: String, val generation: Long) {
        val nativeId: String get() = "van-playback-$generation"
    }

    private var generation = 0L
    private var active: Token? = null
    private var started = false

    fun begin(engine: TtsEngineKind, utteranceId: String): Token {
        require(utteranceId.isNotBlank())
        started = false
        return Token(engine, utteranceId, ++generation).also { active = it }
    }

    fun current(engine: TtsEngineKind, nativeId: String): Token? =
        active?.takeIf { it.engine == engine && it.nativeId == nativeId }

    fun start(engine: TtsEngineKind, nativeId: String): Token? =
        current(engine, nativeId)?.takeUnless { started }?.also { started = true }

    fun complete(engine: TtsEngineKind, nativeId: String): Token? {
        val token = current(engine, nativeId)?.takeIf { started } ?: return null
        cancel()
        return token
    }

    fun fail(engine: TtsEngineKind, nativeId: String): Token? =
        current(engine, nativeId)?.also { cancel() }

    fun cancel(): Token? = active.also { active = null; started = false }
}

/** PCM accepted by a streaming buffer has not necessarily reached its playback head. */
fun awaitSpeechPlaybackDrain(
    submittedFrames: Int,
    sampleRate: Int,
    playedFrames: () -> Long,
    isCurrent: () -> Boolean,
    clockMs: () -> Long,
    waitForProgress: () -> Unit,
): Boolean {
    require(submittedFrames > 0 && sampleRate > 0)
    if (!isCurrent()) return false
    var played = playedFrames()
    check(played >= 0) { "speech_playback_head_invalid" }
    val remainingMs = ((submittedFrames.toLong() - played).coerceAtLeast(0) * 1000L) / sampleRate
    val deadline = clockMs() + remainingMs + 2000L
    while (isCurrent()) {
        if (played >= submittedFrames) return true
        check(clockMs() < deadline) { "speech_playback_drain_timeout" }
        waitForProgress()
        if (!isCurrent()) return false
        val next = playedFrames()
        check(next >= played) { "speech_playback_head_regressed" }
        played = next
    }
    return false
}
