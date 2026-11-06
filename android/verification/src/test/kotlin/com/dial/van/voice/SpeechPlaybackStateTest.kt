package com.dial.van.voice

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

class SpeechPlaybackStateTest {
    @Test
    fun `a late callback from the same engine cannot complete newer playback`() {
        val state = SpeechPlaybackState()
        val old = state.begin(TtsEngineKind.ANDROID_OFFLINE, "first")
        state.start(old.engine, old.nativeId)
        val next = state.begin(old.engine, "second")
        assertNull(state.complete(old.engine, old.nativeId))
        assertNull(state.fail(old.engine, old.nativeId))
        assertNull(state.start(old.engine, old.nativeId))
        assertEquals(next, state.current(next.engine, next.nativeId))
        assertEquals(next, state.start(next.engine, next.nativeId))
        assertEquals(next, state.complete(next.engine, next.nativeId))
        assertNull(state.complete(next.engine, next.nativeId))
    }

    @Test
    fun `barge in invalidates a pending synthesis before native playback starts`() {
        val state = SpeechPlaybackState()
        val pending = state.begin(TtsEngineKind.SHERPA_ONNX, "pending")
        assertEquals(pending, state.cancel())
        assertNull(state.start(pending.engine, pending.nativeId))
        assertNull(state.complete(pending.engine, pending.nativeId))
    }

    @Test
    fun `reusing a logical segment id does not reuse native callback authority`() {
        val state = SpeechPlaybackState()
        val first = state.begin(TtsEngineKind.ANDROID_OFFLINE, "same-segment")
        state.cancel()
        val retry = state.begin(first.engine, first.utteranceId)
        assertNotEquals(first.nativeId, retry.nativeId)
        assertNull(state.start(first.engine, first.nativeId))
        assertEquals(retry, state.start(retry.engine, retry.nativeId))
    }

    @Test
    fun `a queued request is not proof the owner heard audio`() {
        val state = SpeechPlaybackState()
        val token = state.begin(TtsEngineKind.ANDROID_OFFLINE, "queued")
        assertNull(state.complete(token.engine, token.nativeId))
        assertEquals(token, state.fail(token.engine, token.nativeId))
    }

    @Test
    fun `another engine cannot acknowledge or start the current utterance`() {
        val state = SpeechPlaybackState()
        val token = state.begin(TtsEngineKind.SHERPA_ONNX, "local")
        assertNull(state.start(TtsEngineKind.ANDROID_OFFLINE, token.nativeId))
        assertNull(state.complete(TtsEngineKind.ANDROID_OFFLINE, token.nativeId))
        assertEquals(token, state.current(token.engine, token.nativeId))
    }

    @Test
    fun `buffer admission is not completion until the playback head drains`() {
        var head = 0L
        var ticks = 0L
        val completed = awaitSpeechPlaybackDrain(3000, 1000, { head }, { true }, { ticks * 1000 }) {
            ticks += 1
            head += 1000
        }
        assertTrue(completed)
        assertEquals(3L, ticks)
    }

    @Test
    fun `barge in during buffer drain never completes unheard trailing audio`() {
        var current = true
        assertFalse(awaitSpeechPlaybackDrain(3000, 1000, { 1000 }, { current }, { 0 }) {
            current = false
        })
    }

    @Test
    fun `a stalled playback head times out instead of acknowledging delivery`() {
        var clock = 0L
        val failure = assertThrows(IllegalStateException::class.java) {
            awaitSpeechPlaybackDrain(1000, 1000, { 0 }, { true }, { clock }) { clock += 1000 }
        }
        assertEquals("speech_playback_drain_timeout", failure.message)
    }

    @Test
    fun `a reset playback head is not accepted as a completed stream`() {
        var head = 500L
        val failure = assertThrows(IllegalStateException::class.java) {
            awaitSpeechPlaybackDrain(1000, 1000, { head }, { true }, { 0 }) { head = 0 }
        }
        assertEquals("speech_playback_head_regressed", failure.message)
    }
}
