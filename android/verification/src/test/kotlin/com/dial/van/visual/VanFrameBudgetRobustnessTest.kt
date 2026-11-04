package com.dial.van.visual

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class VanFrameBudgetRobustnessTest {
    @Test
    fun `constructor rejects nonpositive or nonfinite budgets and nonpositive windows`() {
        for (budget in listOf(0f, -0f, -1f, Float.NaN, Float.POSITIVE_INFINITY, Float.NEGATIVE_INFINITY)) {
            assertFailsWith<IllegalArgumentException>("budget=$budget") {
                VanFrameBudgetSampler(budgetMillis = budget)
            }
        }
        for (size in listOf(0, -1, Int.MIN_VALUE)) {
            assertFailsWith<IllegalArgumentException>("windowSize=$size") {
                VanFrameBudgetSampler(windowSize = size)
            }
        }
        assertEquals(Float.MIN_VALUE, VanFrameBudgetSampler(budgetMillis = Float.MIN_VALUE).budgetMillis)
        assertEquals(Float.MAX_VALUE, VanFrameBudgetSampler(budgetMillis = Float.MAX_VALUE).budgetMillis)
        assertEquals(1, VanFrameBudgetSampler(windowSize = 1).windowSize)
    }

    @Test
    fun `invalid samples leave window counters and hysteresis unchanged`() {
        val sampler = VanFrameBudgetSampler(budgetMillis = 10f, windowSize = 5)
        sampler.record(20f)
        sampler.record(10f)
        val ratio = sampler.missRatio()
        val p95 = sampler.p95Millis()
        val invalid = listOf(Float.NaN, Float.POSITIVE_INFINITY, Float.NEGATIVE_INFINITY, -1f)

        for (sample in invalid) {
            sampler.record(sample)
            assertEquals(2L, sampler.frames)
            assertEquals(ratio, sampler.missRatio())
            assertEquals(p95, sampler.p95Millis())
            assertFalse(sampler.budgetMissed())
        }
        repeat(2) { sampler.record(10f) }
        assertFalse(sampler.budgetMissed(), "invalid samples must not fill the window")
        sampler.record(10f)
        assertEquals(5L, sampler.frames)
        assertEquals(0.2f, sampler.missRatio())
        assertTrue(sampler.budgetMissed())

        for (sample in invalid) {
            sampler.record(sample)
            assertEquals(5L, sampler.frames)
            assertEquals(0.2f, sampler.missRatio())
            assertEquals(10f, sampler.p95Millis())
            assertTrue(sampler.budgetMissed())
        }
        sampler.record(10f)
        assertEquals(6L, sampler.frames)
        assertEquals(0f, sampler.missRatio())
        assertFalse(sampler.budgetMissed(), "invalid samples must not move the cursor")
    }

    @Test
    fun `zero and finite samples count and retain strict budget comparison`() {
        val sampler = VanFrameBudgetSampler(budgetMillis = 10f, windowSize = 4)
        sampler.record(0f)
        sampler.record(-0f)
        sampler.record(10f)
        assertEquals(3L, sampler.frames)
        assertEquals(0f, sampler.missRatio())
        assertFalse(sampler.budgetMissed())
        sampler.record(Float.MAX_VALUE)
        assertEquals(4L, sampler.frames)
        assertEquals(0.25f, sampler.missRatio())
        assertEquals(10f, sampler.p95Millis())
        assertTrue(sampler.budgetMissed())
        sampler.record(0f)
        assertEquals(5L, sampler.frames, "frames counts accepted samples beyond window capacity")
    }

    @Test
    fun `reset clears accepted count window cursor and degraded state`() {
        val sampler = VanFrameBudgetSampler(budgetMillis = 10f, windowSize = 5)
        repeat(7) { sampler.record(20f) }
        assertTrue(sampler.budgetMissed())
        assertEquals(7L, sampler.frames)
        sampler.reset()
        assertEquals(0L, sampler.frames)
        assertEquals(0f, sampler.missRatio())
        assertEquals(0f, sampler.p95Millis())
        assertFalse(sampler.budgetMissed())

        sampler.record(20f)
        assertEquals(1L, sampler.frames)
        assertEquals(1f, sampler.missRatio())
        assertEquals(20f, sampler.p95Millis())
        assertFalse(sampler.budgetMissed())
        repeat(4) { sampler.record(10f) }
        assertTrue(sampler.budgetMissed())
        sampler.record(10f)
        assertEquals(6L, sampler.frames)
        assertEquals(0f, sampler.missRatio())
        assertFalse(sampler.budgetMissed())
        sampler.reset()
        sampler.reset()
        assertEquals(0L, sampler.frames)
        assertEquals(0f, sampler.p95Millis())
    }

    @Test
    fun `nonincreasing timestamps overflowing differences and pauses do not alter samples`() {
        val sampler = VanFrameBudgetSampler(budgetMillis = 10f, windowSize = 1)
        sampler.record(20f)
        val rejectedPairs = listOf(
            0L to 0L,
            1L to 0L,
            Long.MAX_VALUE to Long.MIN_VALUE,
            Long.MAX_VALUE to (Long.MIN_VALUE + 1_000_000L),
            Long.MIN_VALUE to 0L,
            Long.MIN_VALUE to Long.MAX_VALUE,
            -1L to Long.MAX_VALUE,
            0L to Long.MAX_VALUE,
            0L to 600_000_000_000L,
        )
        for ((previous, current) in rejectedPairs) {
            sampler.recordNanos(previous, current)
            assertEquals(1L, sampler.frames, "timestamps=$previous,$current")
            assertEquals(1f, sampler.missRatio())
            assertEquals(20f, sampler.p95Millis())
            assertTrue(sampler.budgetMissed())
        }
    }

    @Test
    fun `small increasing timestamp differences work at both long extremes and across zero`() {
        val sampler = VanFrameBudgetSampler(budgetMillis = 10f, windowSize = 1)
        val acceptedPairs = listOf(
            Long.MIN_VALUE to (Long.MIN_VALUE + 1_000_000L),
            (Long.MAX_VALUE - 1_000_000L) to Long.MAX_VALUE,
            -500_000L to 500_000L,
        )
        for ((index, pair) in acceptedPairs.withIndex()) {
            sampler.recordNanos(pair.first, pair.second)
            assertEquals(index.toLong() + 1L, sampler.frames)
            assertEquals(1f, sampler.p95Millis())
            assertEquals(0f, sampler.missRatio())
            assertFalse(sampler.budgetMissed())
        }
    }

    @Test
    fun `pause cutoff is inclusive and larger deltas are ignored`() {
        val sampler = VanFrameBudgetSampler(windowSize = 1)
        val cutoff = VanAnimationClock.MAX_FRAME_DELTA_NANOS
        sampler.recordNanos(0L, cutoff)
        assertEquals(1L, sampler.frames)
        assertEquals(cutoff / 1_000_000f, sampler.p95Millis())
        val ratio = sampler.missRatio()
        val missed = sampler.budgetMissed()
        sampler.recordNanos(-1L, cutoff)
        assertEquals(1L, sampler.frames)
        assertEquals(cutoff / 1_000_000f, sampler.p95Millis())
        assertEquals(ratio, sampler.missRatio())
        assertEquals(missed, sampler.budgetMissed())
    }

    @Test
    fun `sustained misses trigger at twenty percent and recover at eight percent`() {
        val sampler = VanFrameBudgetSampler(budgetMillis = 10f, windowSize = 25)
        repeat(5) { sampler.record(20f) }
        repeat(19) { sampler.record(10f) }
        assertFalse(sampler.budgetMissed(), "a partial window must not trigger")
        sampler.record(10f)
        assertEquals(25L, sampler.frames)
        assertEquals(0.2f, sampler.missRatio())
        assertTrue(sampler.budgetMissed())

        sampler.record(10f)
        assertEquals(0.16f, sampler.missRatio())
        assertTrue(sampler.budgetMissed(), "hysteresis retains degradation below the entry threshold")
        sampler.record(10f)
        assertEquals(0.12f, sampler.missRatio())
        assertTrue(sampler.budgetMissed())
        sampler.record(10f)
        assertEquals(0.08f, sampler.missRatio())
        assertFalse(sampler.budgetMissed(), "the existing recovery comparison clears at eight percent")

        repeat(2) { sampler.record(10f) }
        repeat(4) { sampler.record(20f) }
        assertEquals(0.16f, sampler.missRatio())
        assertFalse(sampler.budgetMissed(), "recovery retains the higher entry threshold")
        sampler.record(20f)
        assertEquals(0.2f, sampler.missRatio())
        assertTrue(sampler.budgetMissed())
        repeat(25) { sampler.record(10f) }
        assertEquals(0f, sampler.missRatio())
        assertFalse(sampler.budgetMissed())
        assertEquals(60L, sampler.frames)
    }
}
