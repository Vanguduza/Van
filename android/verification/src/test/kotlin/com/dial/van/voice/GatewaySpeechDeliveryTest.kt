package com.dial.van.voice

import com.dial.van.control.SpokenCommandResult
import java.security.MessageDigest
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.*

class GatewaySpeechDeliveryTest {
    private fun response(heard: Int = -1, interrupted: Boolean = false): JSONObject {
        val texts = listOf("The first answer is ready.", "The next answer is ready.")
        val segments = JSONArray()
        if (!interrupted) texts.forEachIndexed { index, text -> if (index > heard) {
            val digest = MessageDigest.getInstance("SHA-256").digest(text.toByteArray()).joinToString("") { "%02x".format(it) }
            segments.put(JSONObject().put("response_id", "response").put("speech_stream_id", "stream")
                .put("segment_id", "segment-$index").put("segment_index", index).put("text", text)
                .put("content_digest", digest).put("final", index == 1).put("interruptible", true))
        } }
        return JSONObject().put("command_id", "command").put("result_ref", "result")
            .put("response_id", "response").put("speech_stream_id", "stream")
            .put("last_spoken_segment", heard).put("last_received_segment", maxOf(heard, 1))
            .put("total_segments", 2).put("interrupted", interrupted).put("segments", segments)
    }
    private fun request() = SpokenCommandResult("command", "result", "answer", "context", 100L)
    private suspend fun await(condition: () -> Boolean) { withTimeout(3000) { while (!condition()) delay(5) } }

    @Test fun `wire preserves text cues and contiguous unheard tail`() {
        val fresh = BoundSpeechResponse.parse(response())
        assertEquals(listOf(0, 1), fresh.segments.map { it.segmentIndex })
        assertEquals(listOf(1), BoundSpeechResponse.parse(response(0)).segments.map { it.segmentIndex })
        assertTrue(BoundSpeechResponse.parse(response(interrupted = true)).segments.isEmpty())
        val queue = SpeechQueue()
        assertTrue(queue.restoreHeardPrefix("response", "stream", 0))
        assertTrue(queue.offer(BoundSpeechResponse.parse(response(0)).segments.single()))
        assertEquals(1, queue.nextForSynthesis()?.segmentIndex)
        assertFalse(queue.restoreHeardPrefix("other", "other", -1))
    }

    @Test fun `wire refuses coercion altered words mixed responses gaps and missing finality`() {
        val changes: List<(JSONObject) -> Unit> = listOf(
            { it.put("last_spoken_segment", false) },
            { it.put("last_received_segment", 1.0) },
            { it.put("last_spoken_segment", -2) },
            { it.getJSONArray("segments").getJSONObject(0).put("text", "Different words") },
            { it.getJSONArray("segments").getJSONObject(0).put("response_id", "foreign") },
            { it.getJSONArray("segments").getJSONObject(0).put("segment_index", 1) },
            { it.getJSONArray("segments").getJSONObject(1).put("segment_id", "segment-0") },
            { it.getJSONArray("segments").getJSONObject(1).put("final", false) },
            { it.put("interrupted", true) },
        )
        for ((index, change) in changes.withIndex()) {
            val value = response(); change(value)
            assertFails("mutation $index was accepted") { BoundSpeechResponse.parse(value) }
        }
    }

    @Test fun `a late network answer cannot speak into a changed owner context`() = runBlocking<Unit> {
        val scope = CoroutineScope(coroutineContext + SupervisorJob())
        try {
            val ready = CompletableDeferred<Unit>()
            var current = true
            var played = 0
            val interrupted = mutableListOf<String>()
            val delivery = GatewaySpeechDelivery(scope, { current }, { ready.await(); response() },
                { response() }, {}, { interrupted += it }, { played++ }, {}, { SpeechQueue().cursors() })
            delivery.deliver(request())
            current = false
            ready.complete(Unit)
            await { interrupted.isNotEmpty() }
            assertEquals(0, played)
            assertEquals(listOf("stream"), interrupted)
        } finally { scope.cancel() }
    }

    @Test fun `resume uploads actual heard cursor before read and never replays that prefix`() = runBlocking<Unit> {
        val scope = CoroutineScope(coroutineContext + SupervisorJob())
        try {
            val queue = SpeechQueue()
            val events = mutableListOf<String>()
            var played = 0
            val delivery = GatewaySpeechDelivery(scope, { true }, { response() },
                { events += "read"; response(0) }, { events += "report:${it.lastSpokenSegment}" }, {},
                { value -> value.segments.forEach { if (queue.offer(it)) played++ } }, {}, queue::cursors)
            delivery.deliver(request())
            await { played == 2 }
            queue.mark("segment-0", SpeechSegmentState.SPOKEN)
            delivery.reconnect()
            await { "read" in events }
            assertEquals(listOf("report:0", "read"), events)
            assertEquals(2, played)
            assertEquals(0, queue.cursors().lastSpokenSegment)
        } finally { scope.cancel() }
    }

    @Test fun `cancel stops locally before remote interruption and cannot auto resume`() = runBlocking<Unit> {
        val scope = CoroutineScope(coroutineContext + SupervisorJob())
        try {
            val events = mutableListOf<String>()
            var played = 0
            val delivery = GatewaySpeechDelivery(scope, { true }, { response() }, { response() }, {},
                { events += "interrupt" }, { played++ }, { events += "stop" }, { SpeechQueue().cursors() })
            delivery.deliver(request())
            await { played == 1 }
            events.clear()
            delivery.cancel()
            assertEquals(listOf("stop"), events)
            delivery.reconnect()
            await { "interrupt" in events }
            assertEquals(listOf("stop", "interrupt"), events)
            assertEquals(1, played)
        } finally { scope.cancel() }
    }

    @Test fun `a server interruption on reconnect stops the existing local output`() = runBlocking<Unit> {
        val scope = CoroutineScope(coroutineContext + SupervisorJob())
        try {
            var played = 0
            var stops = 0
            val delivery = GatewaySpeechDelivery(scope, { true }, { response() },
                { response(interrupted = true) }, {}, {}, { played++ }, { stops++ }, { SpeechQueue().cursors() })
            delivery.deliver(request())
            await { played == 1 }
            val before = stops
            delivery.reconnect()
            await { stops > before }
            assertEquals(1, played)
            delivery.reconnect()
            delay(10)
            assertEquals(1, played)
        } finally { scope.cancel() }
    }

    @Test fun `a backward clock does not turn an old answer into a current voice turn`() {
        assertEquals(DelayedAnswerAction.SHOW_WITHOUT_SPEAKING,
            DelayedAnswerPolicy.decide(1000, 999, true, true))
    }

    @Test fun `a definitive source refusal while reporting stops the remaining audio`() = runBlocking<Unit> {
        val scope = CoroutineScope(coroutineContext + SupervisorJob())
        try {
            var played = 0
            var stops = 0
            val delivery = GatewaySpeechDelivery(scope, { true }, { response() }, { response() },
                { throw SpeechSourceRefused(409) }, {}, { played++ }, { stops++ }, { SpeechQueue().cursors() })
            delivery.deliver(request())
            await { played == 1 }
            val before = stops
            delivery.progress(SpeechCursors("response", "stream", 1, 0), false)
            await { delivery.failure.value != null }
            assertTrue(stops > before)
            assertTrue(delivery.failure.value!!.contains("changed"))
            delivery.reconnect()
            delay(10)
            assertEquals(1, played)
        } finally { scope.cancel() }
    }

    @Test fun `server errors retain text fallback without inventing playback success`() = runBlocking<Unit> {
        val scope = CoroutineScope(coroutineContext + SupervisorJob())
        try {
            var played = 0
            val delivery = GatewaySpeechDelivery(scope, { true }, { error("not admitted") },
                { response() }, {}, {}, { played++ }, {}, { SpeechQueue().cursors() })
            delivery.deliver(request())
            await { delivery.failure.value != null }
            assertEquals(0, played)
        } finally { scope.cancel() }
    }
}
