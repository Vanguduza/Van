package com.dial.van.visual

import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.Test

/** Pure policy and actual production-clock coverage; no native performance qualification. */
class VanMotionLifecycleRepairTest {
    @Test
    fun motionGateCoversEveryBudgetVisibilityAnimationAndReducedMotionCombination() {
        for (budget in VanEffectBudget.values()) {
            for (visible in listOf(false, true)) {
                for (animate in listOf(false, true)) {
                    for (reduced in listOf(false, true)) {
                        val expected = when (budget) {
                            VanEffectBudget.FULL,
                            VanEffectBudget.REDUCED,
                            VanEffectBudget.LOW,
                            -> visible && animate && !reduced
                            VanEffectBudget.REDUCED_MOTION,
                            VanEffectBudget.STATIC,
                            -> false
                        }
                        assertEquals(
                            expected,
                            vanMotionEnabled(budget, visible, animate, reduced),
                            "$budget visible=$visible animate=$animate reduced=$reduced",
                        )
                    }
                }
            }
        }
    }

    @Test
    fun suspendPreservesPhaseAndReanchorsWithoutIntegratingHiddenTime() {
        val clock = VanAnimationClock(initialPhase = 0.20f)
        val period = VanMotionPeriods.periodMillisFor(VanDurableState.WORKING)
        clock.advance(1_000_000_000L, period)
        assertEquals(0.25f, clock.advance(1_100_000_000L, period), EPSILON)
        val frames = clock.frames
        val elapsed = clock.elapsedNanos

        clock.suspendTiming()
        clock.suspendTiming()
        assertNull(clock.lastFrameNanos)
        assertEquals(0.25f, clock.phase, EPSILON)
        assertEquals(frames, clock.frames)
        assertEquals(elapsed, clock.elapsedNanos)

        assertEquals(0.25f, clock.advance(61_100_000_000L, period), EPSILON)
        assertEquals(61_100_000_000L, clock.lastFrameNanos!!.toLong())
        assertEquals(elapsed, clock.elapsedNanos)
        assertEquals(0.30f, clock.advance(61_200_000_000L, period), EPSILON)
        assertEquals(elapsed + 100_000_000L, clock.elapsedNanos)
    }

    @Test
    fun visibilityGatePausesEvenForHiddenIntervalsBelowTheDeltaClamp() {
        val clock = VanAnimationClock(initialPhase = 0.10f)
        val period = VanMotionPeriods.periodMillisFor(VanDurableState.WORKING)
        clock.advance(2_000_000_000L, period)
        clock.advance(2_020_000_000L, period)
        val before = clock.phase
        val elapsed = clock.elapsedNanos

        if (!vanMotionEnabled(VanEffectBudget.FULL, visible = false)) clock.suspendTiming()
        assertNull(clock.lastFrameNanos)
        // A 100 ms hidden interval would otherwise pass the clock's delta clamp.
        if (vanMotionEnabled(VanEffectBudget.FULL, visible = true)) {
            assertEquals(before, clock.advance(2_120_000_000L, period), EPSILON)
        }
        assertEquals(elapsed, clock.elapsedNanos)
        assertEquals(before + 0.01f, clock.advance(2_140_000_000L, period), EPSILON)
    }

    @Test
    fun activeStateChangesUseTheNewPeriodWithoutResettingPhase() {
        val clock = VanAnimationClock(initialPhase = 0.20f)
        clock.advance(3_000_000_000L, VanMotionPeriods.periodMillisFor(VanDurableState.IDLE))
        assertEquals(
            0.25f,
            clock.advance(3_210_000_000L, VanMotionPeriods.periodMillisFor(VanDurableState.IDLE)),
            EPSILON,
        )
        assertEquals(
            0.30f,
            clock.advance(3_310_000_000L, VanMotionPeriods.periodMillisFor(VanDurableState.WORKING)),
            EPSILON,
        )
        assertEquals(
            0.35f,
            clock.advance(3_450_000_000L, VanMotionPeriods.periodMillisFor(VanDurableState.WARNING)),
            EPSILON,
        )
        assertEquals(450_000_000L, clock.elapsedNanos)
    }

    @Test
    fun sameStatePeriodContinuesAcrossSuccessiveFrames() {
        val clock = VanAnimationClock(initialPhase = 0.30f)
        val period = VanMotionPeriods.periodMillisFor(VanDurableState.IDLE)
        clock.advance(4_000_000_000L, period)
        assertEquals(0.35f, clock.advance(4_210_000_000L, period), EPSILON)
        assertEquals(0.40f, clock.advance(4_420_000_000L, period), EPSILON)
        assertEquals(420_000_000L, clock.elapsedNanos)
        assertEquals(3L, clock.frames)
    }

    companion object {
        private const val EPSILON = 0.00001f
    }
}
