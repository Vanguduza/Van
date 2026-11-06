package com.dial.van.instrumentation

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.dial.van.VanApplication
import com.dial.van.control.VanSpokenAnswer
import com.dial.van.voice.SpeechSegmentState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Actual pinned offline synthesis, AudioTrack and application callback/queue wiring. */
@RunWith(AndroidJUnit4::class)
class VoicePlaybackRuntimeTest {
    private val app get() = ApplicationProvider.getApplicationContext<VanApplication>()

    private suspend fun ready() {
        try {
            withTimeout(60_000) {
                app.voiceEdge.readiness.first { !it.installing &&
                    (it.localTtsRuntimeReady || it.localTtsRuntimeError != null) }
            }
        } catch (timeout: kotlinx.coroutines.TimeoutCancellationException) {
            throw AssertionError("Voice startup did not finish: ${app.voiceEdge.readiness.value}; " +
                "installation=${com.dial.van.voice.VoiceAssetInstaller.failure}; " +
                "native=${app.ttsOutput.sherpaPreparationError()}", timeout)
        }
        assertTrue("Actual voice runtime: ${app.voiceEdge.readiness.value}; " +
            "installation=${com.dial.van.voice.VoiceAssetInstaller.failure}", app.ttsOutput.sherpaReady())
    }

    private suspend fun awaitSpoken(): String = withTimeout(45_000) {
        while (true) {
            val stream = withContext(Dispatchers.Main) {
                val queue = app.voiceEdge.queue()
                if (queue.completed()) {
                    assertEquals(0, queue.cursors().lastSpokenSegment)
                    assertEquals(SpeechSegmentState.SPOKEN, queue.snapshot().single().state)
                    queue.cursors().speechStreamId
                } else null
            }
            if (stream != null) return@withTimeout stream
            delay(25)
        }
        @Suppress("UNREACHABLE_CODE") error("speech did not complete")
    }

    @Test
    fun realOfflineAnswerReachesTheApplicationQueueAsSpoken() = runBlocking<Unit> {
        ready()
        withContext(Dispatchers.Main) {
            VanSpokenAnswer.speak(app.voiceEdge, "The test is complete.")
        }
        awaitSpoken()
    }

    @Test
    fun cancellationBeforeNativeStartCannotCompleteOrDamageTheReplacementAnswer() = runBlocking<Unit> {
        ready()
        val oldStream = withContext(Dispatchers.Main) {
            VanSpokenAnswer.speak(app.voiceEdge, "The first answer is ready.")
            val old = app.voiceEdge.queue()
            val id = old.cursors().speechStreamId
            try {
                app.voiceSession.beginOwnerTurn("instrumentation-cancel-pending-speech")
            } finally {
                app.voiceSession.cancelOwnerTurn()
            }
            assertFalse(old.completed())
            assertEquals(-1, old.cursors().lastSpokenSegment)
            assertEquals(SpeechSegmentState.INTERRUPTED, old.snapshot().single().state)
            VanSpokenAnswer.speak(app.voiceEdge, "The next answer is ready.")
            id
        }
        assertNotEquals(oldStream, awaitSpoken())
    }
}
