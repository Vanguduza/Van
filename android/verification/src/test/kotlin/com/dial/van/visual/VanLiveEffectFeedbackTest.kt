package com.dial.van.visual

import com.dial.van.runtime.RuntimeReading
import com.dial.van.runtime.VanResourceEnvelope
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class VanLiveEffectFeedbackTest {
    private fun monitor(rate: Float = 60f) = VanFrameCadenceFeedback(windowSize = 20).also {
        it.configure(rate, true)
        it.record(0L)
    }

    private fun feed(monitor: VanFrameCadenceFeedback, start: Long, delta: Long, count: Int): Long {
        var now = start
        repeat(count) { now += delta; monitor.record(now) }
        return now
    }

    @Test fun `healthy 60Hz callbacks keep full effects`() {
        val m = monitor()
        feed(m, 0L, 16_666_667L, 80)
        assertFalse(m.missed)
        assertEquals(80L, m.observedFrames)
        assertEquals(VanEffectBudget.FULL, VanEffectPolicy.withCadencePressure(VanEffectBudget.FULL, m.missed))
    }

    @Test fun `healthy 120Hz callbacks keep full effects`() {
        val m = monitor(120f)
        feed(m, 0L, 8_333_334L, 80)
        assertFalse(m.missed)
        assertEquals(10f, m.budgetMillis, 0.001f)
    }

    @Test fun `misses are relative to the actual display rate`() {
        val sixty = monitor(60f)
        val fast = monitor(120f)
        feed(sixty, 0L, 16_666_667L, 20)
        feed(fast, 0L, 16_666_667L, 20)
        assertFalse(sixty.missed)
        assertTrue(fast.missed)
    }

    @Test fun `sustained misses really lower the existing effect policy`() {
        val m = monitor()
        feed(m, 0L, 33_333_334L, 20)
        assertTrue(m.missed)
        val result = VanEffectPolicy.withCadencePressure(VanEffectBudget.FULL, m.missed)
        assertEquals(VanEffectBudget.LOW, result)
        assertFalse(result.allowLiveBlur)
        assertFalse(result.allowRefraction)
        assertTrue(result.allowMotion)
        assertTrue(result.keepsStateIndicators)
    }

    @Test fun `recovery restores the original ceiling not unrestricted quality`() {
        val m = monitor()
        val slowEnd = feed(m, 0L, 40_000_000L, 20)
        assertEquals(VanEffectBudget.LOW, VanEffectPolicy.withCadencePressure(VanEffectBudget.REDUCED, m.missed))
        feed(m, slowEnd, 16_666_667L, 20)
        assertFalse(m.missed)
        assertEquals(VanEffectBudget.REDUCED, VanEffectPolicy.withCadencePressure(VanEffectBudget.REDUCED, m.missed))
    }

    @Test fun `small scheduling jitter does not imitate a missed refresh`() {
        val m = monitor()
        feed(m, 0L, 18_000_000L, 40)
        assertFalse(m.missed)
    }

    @Test fun `a single slow callback does not degrade the character`() {
        val m = monitor()
        val t = feed(m, 0L, 16_666_667L, 19)
        m.record(t + 40_000_000L)
        assertFalse(m.missed)
    }

    @Test fun `no pressure claim before the complete observation window`() {
        val m = monitor()
        val t = feed(m, 0L, 40_000_000L, 19)
        assertFalse(m.missed)
        m.record(t + 40_000_000L)
        assertTrue(m.missed)
    }

    @Test fun `pause discards pressure and all hidden callbacks`() {
        val m = monitor()
        val t = feed(m, 0L, 40_000_000L, 20)
        assertTrue(m.missed)
        m.pause()
        feed(m, t, 100_000_000L, 80)
        assertEquals(0L, m.observedFrames)
        assertFalse(m.missed)
    }

    @Test fun `resume anchors now instead of replaying ten minutes in a pocket`() {
        val m = monitor()
        feed(m, 0L, 40_000_000L, 20)
        m.pause()
        m.configure(60f, true)
        m.record(600_000_000_000L)
        assertEquals(0L, m.observedFrames)
        feed(m, 600_000_000_000L, 16_666_667L, 20)
        assertFalse(m.missed)
    }

    @Test fun `display-rate changes discard incomparable history`() {
        val m = monitor(120f)
        feed(m, 0L, 16_666_667L, 20)
        assertTrue(m.missed)
        m.configure(60f, true)
        assertFalse(m.missed)
        assertEquals(0L, m.observedFrames)
        assertEquals(20f, m.budgetMillis, 0.001f)
    }

    @Test fun `ordinary state changes do not clear a bad cadence window`() {
        val m = monitor()
        feed(m, 0L, 40_000_000L, 20)
        m.configure(60f, true)
        assertTrue(m.missed)
        assertEquals(20L, m.observedFrames)
    }

    @Test fun `invalid refresh readings use the explicit fallback`() {
        for (rate in listOf(Float.NaN, Float.POSITIVE_INFINITY, Float.NEGATIVE_INFINITY, -1f, 0f, 1_001f)) {
            assertEquals(60f, VanFrameCadenceFeedback.validRefreshRate(rate))
            assertEquals(20f, monitor(rate).budgetMillis, 0.001f)
        }
    }

    @Test fun `fractional and low-power refresh rates remain valid`() {
        for (rate in listOf(1f, 24f, 59.94f, 90f, 119.88f, 144f, 240f)) {
            assertEquals(rate, VanFrameCadenceFeedback.validRefreshRate(rate))
        }
    }

    @Test fun `out-of-order samples cannot move the anchor backward`() {
        val m = monitor()
        m.record(10_000_000L)
        m.record(5_000_000L)
        m.record(10_000_000L)
        m.record(20_000_000L)
        assertEquals(2L, m.observedFrames)
        assertFalse(m.missed)
    }

    @Test fun `long suspended intervals retain the sampler pause convention`() {
        val m = monitor()
        m.record(600_000_000_000L)
        assertEquals(0L, m.observedFrames)
        feed(m, 600_000_000_000L, 16_666_667L, 20)
        assertFalse(m.missed)
    }

    @Test fun `cadence cannot remove a stricter thermal or accessibility ceiling`() {
        for (budget in listOf(VanEffectBudget.LOW, VanEffectBudget.STATIC, VanEffectBudget.REDUCED_MOTION)) {
            assertEquals(budget, VanEffectPolicy.withCadencePressure(budget, true))
            assertEquals(budget, VanEffectPolicy.withCadencePressure(budget, false))
        }
    }

    @Test fun `all original budgets are unchanged without cadence pressure`() {
        for (budget in VanEffectBudget.entries) {
            assertEquals(budget, VanEffectPolicy.withCadencePressure(budget, false))
        }
    }

    @Test fun `live device readings still go through the original whole-runtime owner`() {
        val initial = RuntimeReading(batteryPercent = 80)
        assertEquals(VanEffectBudget.FULL, VanResourceEnvelope.effectBudget(initial, VanEffectConditions()))
        val saver = initial.copy(powerSaveMode = true)
        val constrained = VanResourceEnvelope.effectBudget(saver, VanEffectConditions(batterySaver = true))
        assertEquals(VanEffectBudget.LOW, constrained)
        assertEquals(VanEffectBudget.LOW, VanEffectPolicy.withCadencePressure(constrained, false))
        val hot = initial.copy(thermalStatus = 3)
        val severe = VanResourceEnvelope.effectBudget(hot, VanEffectConditions(thermalStatus = 3))
        assertEquals(VanEffectBudget.STATIC, severe)
        assertEquals(VanEffectBudget.STATIC, VanEffectPolicy.withCadencePressure(severe, false))
    }

    @Test fun `a hundred pause and refresh cycles retain no stale pressure`() {
        val m = monitor()
        repeat(100) { index ->
            val rate = if (index % 2 == 0) 60f else 120f
            m.configure(rate, true)
            val start = index * 1_000_000_000L
            m.record(start)
            feed(m, start, 33_333_334L, 20)
            assertTrue(m.missed)
            m.pause()
            assertFalse(m.missed)
            assertEquals(0L, m.observedFrames)
        }
    }
}
