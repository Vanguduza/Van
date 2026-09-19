package com.dial.van.visual

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * P2-PERF-001 — `VanEffectConditions.frameBudgetMissed` finally has a producer.
 *
 * The effect ladder already knew what to do about a device that could not keep up. Nothing
 * ever told it, so the only inputs it received were battery saver and thermal status — both
 * facts about the device rather than about whether VAN is in fact rendering acceptably on it.
 */
class VanFrameBudgetTest {

    private fun sampler() = VanFrameBudgetSampler(windowSize = 20)

    @Test
    fun `one slow frame is not a degraded device`() {
        // A GC, a layout pass, the system drawing something else. Degrading the visuals on
        // one slow frame would make VAN flicker between effect budgets.
        val budget = sampler()
        repeat(19) { budget.record(10f) }
        budget.record(400f)
        assertFalse(budget.budgetMissed())
    }

    @Test
    fun `sustained misses are`() {
        val budget = sampler()
        repeat(14) { budget.record(9f) }
        repeat(6) { budget.record(45f) }   // 30% of the window
        assertTrue(budget.budgetMissed())
    }

    @Test
    fun `a device that cools down gets its field back`() {
        val budget = sampler()
        repeat(20) { budget.record(45f) }
        assertTrue(budget.budgetMissed())
        repeat(20) { budget.record(9f) }
        assertFalse(budget.budgetMissed(), "the signal never cleared")
    }

    @Test
    fun `it does not oscillate at the threshold`() {
        // Hysteresis: it takes 20% to start reporting and under 8% to stop.
        val budget = sampler()
        repeat(16) { budget.record(9f) }
        repeat(4) { budget.record(45f) }   // exactly 20%
        assertTrue(budget.budgetMissed())
        // One good frame replaces one bad one: 15%, still over the recovery floor.
        budget.record(9f)
        assertTrue(budget.budgetMissed(), "one good frame cleared a sustained miss")
    }

    @Test
    fun `no judgement before there is a window to judge on`() {
        val budget = sampler()
        repeat(10) { budget.record(500f) }
        assertFalse(budget.budgetMissed(), "judged a device on half a window")
    }

    @Test
    fun `a pause is not a missed frame`() {
        // The screen was off for ten minutes. That device did nothing wrong.
        val budget = sampler()
        repeat(19) { budget.record(9f) }
        budget.recordNanos(0L, 600L * 1_000_000_000L)
        assertEquals(19L, budget.frames)
        assertFalse(budget.budgetMissed())
    }

    @Test
    fun `the miss ratio and p95 are inspectable`() {
        val budget = sampler()
        repeat(10) { budget.record(8f) }
        repeat(10) { budget.record(50f) }
        assertEquals(0.5f, budget.missRatio(), 0.001f)
        assertTrue(budget.p95Millis() >= 45f)
    }

    @Test
    fun `the signal reaches the effect ladder`() {
        // The whole point: this is what drops the field to LOW on a device that cannot
        // sustain it, and that path was unreachable before.
        val healthy = VanEffectPolicy.resolve(VanEffectConditions())
        val struggling = VanEffectPolicy.resolve(VanEffectConditions(frameBudgetMissed = true))
        assertEquals(VanEffectBudget.FULL, healthy)
        assertEquals(VanEffectBudget.LOW, struggling)
        assertTrue(struggling.filamentScale < healthy.filamentScale)
    }

    @Test
    fun `the default budget is one 60Hz frame`() {
        assertEquals(16.67f, VanFrameBudgetSampler.DEFAULT_BUDGET_MS, 0.01f)
    }
}
