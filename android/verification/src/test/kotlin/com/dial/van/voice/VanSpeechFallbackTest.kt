package com.dial.van.voice

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class VanSpeechFallbackTest {
    @Test fun preStartCueNeverOpensMouth() {
        val track = listOf(Triple(100, 3, 0.8f))
        assertEquals(0 to 0f, VanCueWalker.cueAt(track, 0))
        assertEquals(0 to 0f, VanCueWalker.cueAt(track, 99))
        assertEquals(3 to 0.8f, VanCueWalker.cueAt(track, 100))
    }

    @Test fun negativeElapsedTimeDoesNotPretendSpeech() {
        assertEquals(0 to 0f, VanCueWalker.cueAt(listOf(Triple(0, 4, 1f)), -10))
    }

    @Test fun outOfOrderCueTrackSelectsLatestEligibleOffset() {
        val track = listOf(Triple(300, 4, 0.8f), Triple(0, 1, 0.2f), Triple(120, 2, 0.5f))
        assertEquals(2 to 0.5f, VanCueWalker.cueAt(track, 150))
        assertEquals(4 to 0.8f, VanCueWalker.cueAt(track, 300))
    }

    @Test fun invalidPositiveVisemeClampsToCanonicalUnknownFallback() {
        assertEquals(1 to 0.6f, VanCueWalker.cueAt(listOf(Triple(0, 14, 0.6f)), 0))
        assertEquals(0 to 0.6f, VanCueWalker.cueAt(listOf(Triple(0, -2, 0.6f)), 0))
    }

    @Test fun impossibleAmplitudeCannotPoisonRiveInput() {
        for (invalid in listOf(Float.NaN, Float.POSITIVE_INFINITY, Float.NEGATIVE_INFINITY)) {
            assertEquals(0f, VanCueWalker.cueAt(listOf(Triple(0, 2, invalid)), 0).second)
        }
    }

    @Test fun cueAmplitudeStaysInZeroToOne() {
        assertEquals(1f, VanCueWalker.cueAt(listOf(Triple(0, 1, 9f)), 0).second)
        assertEquals(0f, VanCueWalker.cueAt(listOf(Triple(0, 1, -9f)), 0).second)
    }

    @Test fun invalidTextRangesCannotAnimate() {
        for ((start, end) in listOf(-1 to 2, 3 to 2, 2 to 10, 2 to 2)) {
            assertEquals(0 to 0f, VanRangeCueEstimator.forTextRange("hello", start, end))
        }
    }

    @Test fun punctuationProducesNeutralMouth() {
        assertEquals(0 to 0f, VanRangeCueEstimator.forTextRange("... ", 0, 4))
    }

    @Test fun vowelRangeMapsOnlyToTheFiveApprovedShapes() {
        assertEquals(2, VanRangeCueEstimator.forTextRange("ee", 0, 2).first)
        assertEquals(2, VanRangeCueEstimator.forTextRange("ii", 0, 2).first)
        assertEquals(3, VanRangeCueEstimator.forTextRange("aa", 0, 2).first)
        assertEquals(4, VanRangeCueEstimator.forTextRange("oo", 0, 2).first)
        assertEquals(4, VanRangeCueEstimator.forTextRange("uu", 0, 2).first)
        assertEquals(1, VanRangeCueEstimator.forTextRange("sh", 0, 2).first)
    }

    @Test fun allSpeechVisualOutputsStayInsideTheCanonicalContract() {
        for (sample in listOf("alpha", "beta", "one", "two", "no", "...", "ABR", "123", "🤖")) {
            val (shape, opening) = VanRangeCueEstimator.forTextRange(sample, 0, sample.length)
            assertTrue(shape in 0..4, "viseme for " + sample)
            assertTrue(opening in 0f..1f, "opening for " + sample)
        }
    }

    @Test fun legacyCueTimingJsonStillParsesWithoutChangingWireFields() {
        val x = org.json.JSONObject("""{"cues":[[0,1,0.5],[300,0,0]],"estimated_duration_ms":400}""")
        val parsed = SegmentCueTiming.fromJson(x)
        assertEquals(2, parsed.cues.size)
        assertEquals(400, parsed.estimatedDurationMs)
    }
}
