package com.dial.van.voice

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * GAP-F-013 — the device-side mirror of the Gateway's estimated cue timing, and the pure
 * lookup `TtsOutputManager` drives against wall-clock time.
 */
class SpeechCueTimingTest {

    @Test
    fun `parsing the exact shape the gateway sends`() {
        val json = JSONObject(
            """{"cues":[[0,1,0.5],[120,2,0.8],[300,0,0.0]],"estimated_duration_ms":300,"rms_fallback":true}""",
        )
        val timing = SegmentCueTiming.fromJson(json)
        assertEquals(3, timing.cues.size)
        assertEquals(Triple(0, 1, 0.5f), timing.cues[0])
        assertEquals(Triple(120, 2, 0.8f), timing.cues[1])
        assertEquals(300, timing.estimatedDurationMs)
        assertTrue(timing.rmsFallback)
    }

    @Test
    fun `a null payload — a gateway that predates this field — parses to empty`() {
        assertEquals(SegmentCueTiming.EMPTY, SegmentCueTiming.fromJson(null))
    }

    @Test
    fun `a payload with no cues array parses to empty rather than throwing`() {
        val timing = SegmentCueTiming.fromJson(JSONObject("""{"estimated_duration_ms":50}"""))
        assertTrue(timing.cues.isEmpty())
    }

    @Test
    fun `a malformed cue entry is skipped rather than crashing the parse`() {
        val json = JSONObject("""{"cues":[[0,1,0.5],[1,2]],"estimated_duration_ms":10}""")
        val timing = SegmentCueTiming.fromJson(json)
        assertEquals(1, timing.cues.size)
    }

    @Test
    fun `cueAt walks forward and never picks a cue that has not started yet`() {
        val cues = listOf(Triple(0, 1, 0.4f), Triple(100, 2, 0.9f), Triple(250, 0, 0.0f))
        assertEquals(1 to 0.4f, VanCueWalker.cueAt(cues, elapsedMs = 0))
        assertEquals(1 to 0.4f, VanCueWalker.cueAt(cues, elapsedMs = 99))
        assertEquals(2 to 0.9f, VanCueWalker.cueAt(cues, elapsedMs = 100))
        assertEquals(2 to 0.9f, VanCueWalker.cueAt(cues, elapsedMs = 249))
        assertEquals(0 to 0.0f, VanCueWalker.cueAt(cues, elapsedMs = 250))
        assertEquals(0 to 0.0f, VanCueWalker.cueAt(cues, elapsedMs = 10_000))
    }

    @Test
    fun `cueAt on an empty track is silent and closed`() {
        assertEquals(0 to 0f, VanCueWalker.cueAt(emptyList(), elapsedMs = 500))
    }

    @Test
    fun `cueAt clamps a mouth_open outside 0 to 1`() {
        val cues = listOf(Triple(0, 1, 1.4f), Triple(10, 2, -0.2f))
        assertEquals(1f, VanCueWalker.cueAt(cues, elapsedMs = 0).second)
        assertEquals(0f, VanCueWalker.cueAt(cues, elapsedMs = 10).second)
    }

    @Test
    fun `a SpeechSegment defaults to no cue timing`() {
        val segment = SpeechSegment(
            responseId = "r", speechStreamId = "s", segmentId = "s_0", segmentIndex = 0, text = "hi",
        )
        assertFalse(segment.cueTiming.cues.isNotEmpty())
        assertEquals(SegmentCueTiming.EMPTY, segment.cueTiming)
    }
}
