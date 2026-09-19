package com.dial.van.visual

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * P1-AURA-002 — one monotonic clock, never restarted, and transitions that blend.
 *
 * The bug these tests are about is precise and was easy to miss by reading: the shipping
 * driver was `rememberInfiniteTransition` with a `durationMillis` chosen per state. Changing
 * state changes the duration, which restarts the tween at zero. So the field snapped back to
 * phase 0 at the exact moment VAN was meant to be showing the owner a change — the one
 * moment where a jump is most visible.
 */
class VanAnimationClockTest {

    private val frame16ms = 16_666_667L

    @Test
    fun `a period change advances the phase differently and never restarts it`() {
        val clock = VanAnimationClock()
        var now = 1_000_000_000L
        clock.advance(now, 4200)                 // first frame establishes the baseline
        repeat(30) { now += frame16ms; clock.advance(now, 4200) }
        val beforeChange = clock.phase
        assertTrue(beforeChange > 0f, "the clock never advanced")

        // The state changes; the period changes with it.
        now += frame16ms
        val afterChange = clock.advance(now, 2000)

        assertTrue(
            afterChange > beforeChange,
            "phase went backwards on a period change: $beforeChange -> $afterChange",
        )
        assertTrue(
            afterChange - beforeChange < 0.02f,
            "a period change produced a jump of ${afterChange - beforeChange}, not a continuation",
        )
    }

    @Test
    fun `the old driver's failure is what this replaces`() {
        // What rememberInfiniteTransition did: value = elapsedSinceStateChange / duration.
        // Modelled here so the difference is stated rather than asserted about an absence.
        fun restartingDriver(elapsedSinceStateChangeMs: Long, durationMs: Int): Float =
            (elapsedSinceStateChangeMs.toFloat() / durationMs) % 1f

        val beforeRestart = restartingDriver(3_000, 4200)
        val afterRestart = restartingDriver(0, 2000)   // the state changed: elapsed resets
        assertTrue(
            abs(afterRestart - beforeRestart) > 0.5f,
            "the model of the old behaviour should snap; it moved only " +
                "${abs(afterRestart - beforeRestart)}",
        )
    }

    @Test
    fun `the first frame advances nothing`() {
        val clock = VanAnimationClock()
        assertEquals(0f, clock.advance(9_999_999_999L, 4200))
        assertEquals(0L, clock.elapsedNanos)
    }

    @Test
    fun `a long pause is clamped rather than spun through hundreds of cycles`() {
        val clock = VanAnimationClock()
        var now = 1_000_000_000L
        clock.advance(now, 4200)
        now += frame16ms
        clock.advance(now, 4200)
        val before = clock.phase

        // The screen was off for ten minutes.
        now += 600L * 1_000_000_000L
        val after = clock.advance(now, 4200)

        val advanced = VanWindFieldMotion.wrap01(after - before)
        assertTrue(
            advanced <= 0.25f,
            "a ten-minute pause advanced the phase by $advanced of a cycle",
        )
    }

    @Test
    fun `a non-monotonic timestamp does not rewind the clock`() {
        val clock = VanAnimationClock()
        clock.advance(1_000_000_000L, 4200)
        clock.advance(1_000_000_000L + frame16ms, 4200)
        val forward = clock.phase
        clock.advance(1_000_000_000L, 4200)  // a source that went backwards
        assertEquals(forward, clock.phase)
    }

    @Test
    fun `the phase stays inside zero to one however long it runs`() {
        val clock = VanAnimationClock()
        var now = 0L
        repeat(2_000) {
            now += frame16ms
            val phase = clock.advance(now, 2000)
            assertTrue(phase >= 0f && phase < 1f, "phase escaped 0..1: $phase")
        }
    }

    // ------------------------------------------------------------- blending

    @Test
    fun `every blend duration is inside the 120 to 420 ms band`() {
        for (from in VanDurableState.entries) {
            for (to in VanDurableState.entries) {
                val duration = VanTransitionBlend.durationMillisFor(from, to)
                assertTrue(
                    duration in VanTransitionBlend.MIN_BLEND_MS..VanTransitionBlend.MAX_BLEND_MS,
                    "$from -> $to blends over ${duration}ms, outside Rev 3.0 §25",
                )
            }
        }
    }

    @Test
    fun `arriving at something urgent is fast and settling down is slow`() {
        val toError = VanTransitionBlend.durationMillisFor(
            VanDurableState.IDLE, VanDurableState.ERROR,
        )
        val toIdle = VanTransitionBlend.durationMillisFor(
            VanDurableState.WORKING, VanDurableState.IDLE,
        )
        assertTrue(toError < toIdle, "an error should not fade in more slowly than an idle settle")
    }

    @Test
    fun `a blend starts and ends with zero velocity`() {
        val early = VanTransitionBlend.progress(1, 300)
        val late = VanTransitionBlend.progress(299, 300)
        assertTrue(early < 0.02f, "the blend starts with a step: $early")
        assertTrue(late > 0.98f, "the blend ends with a step: $late")
        assertEquals(1f, VanTransitionBlend.progress(300, 300))
        assertEquals(1f, VanTransitionBlend.progress(10_000, 300))
    }

    @Test
    fun `a spec blend moves the continuous fields and does not invent a colour`() {
        val idle = VanAuraSpecs.forState(VanDurableState.IDLE)
        val error = VanAuraSpecs.forState(VanDurableState.ERROR)
        val half = idle.blendTo(error, 0.5f)

        assertTrue(
            half.intensity > minOf(idle.intensity, error.intensity) &&
                half.intensity < maxOf(idle.intensity, error.intensity),
            "intensity did not interpolate",
        )
        // There is no meaningful colour between "no semantic" and "error red".
        assertTrue(half.semanticColor == idle.semanticColor || half.semanticColor == error.semanticColor)
        assertEquals(idle, idle.blendTo(error, 0f))
        assertEquals(error, idle.blendTo(error, 1f))
    }

    @Test
    fun `retargeting mid-blend continues from where the field actually is`() {
        val idle = VanAuraSpecs.forState(VanDurableState.IDLE)
        val listening = VanAuraSpecs.forState(VanDurableState.LISTENING)
        val working = VanAuraSpecs.forState(VanDurableState.WORKING)

        val first = VanAuraTransition(idle, listening, startedAtNanos = 0L, durationMillis = 300)
        val midway = first.specAt(150_000_000L)

        val second = VanAuraTransition.retarget(
            existing = first, current = midway, to = working,
            fromState = VanDurableState.LISTENING, toState = VanDurableState.WORKING,
            nowNanos = 150_000_000L,
        )
        // The second blend's first frame is where the first blend had got to, not the
        // previous target — which is what would put the snap back on the second change.
        assertEquals(midway.intensity, second.specAt(150_000_000L).intensity, 0.0001f)
        assertNotEquals(listening.intensity, second.from.intensity)
    }

    @Test
    fun `with no blend in flight the transition starts from what is on screen`() {
        val idle = VanAuraSpecs.forState(VanDurableState.IDLE)
        val error = VanAuraSpecs.forState(VanDurableState.ERROR)
        val started = VanAuraTransition.retarget(
            existing = null, current = idle, to = error,
            fromState = VanDurableState.IDLE, toState = VanDurableState.ERROR,
            nowNanos = 0L,
        )
        assertEquals(idle.intensity, started.specAt(0L).intensity, 0.0001f)
        assertEquals(error.intensity, started.specAt(1_000_000_000L).intensity, 0.0001f)
    }

    @Test
    fun `identical specs are not worth blending`() {
        val idle = VanAuraSpecs.forState(VanDurableState.IDLE)
        assertTrue(!idle.differsFrom(idle))
        assertTrue(idle.differsFrom(VanAuraSpecs.forState(VanDurableState.ERROR)))
    }
}
