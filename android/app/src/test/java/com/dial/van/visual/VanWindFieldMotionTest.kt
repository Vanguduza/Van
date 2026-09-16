package com.dial.van.visual

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class VanWindFieldMotionTest {

    @Test
    fun repeatingClockIsSeamlessAtPhaseBoundary() {
        val spec = VanAuraSpecs.forState(VanDurableState.WORKING)
        val start = VanWindFieldMotion.sample(spec, 0f, VanEffectBudget.FULL)
        val end = VanWindFieldMotion.sample(spec, 1f, VanEffectBudget.FULL)

        assertEquals(start.breathing, end.breathing, 0.0001f)
        assertEquals(start.windAngleRad, end.windAngleRad, 0.0001f)
        assertEquals(start.electricPulse, end.electricPulse, 0.0001f)
        assertEquals(start.particleAdvection, end.particleAdvection, 0.0001f)
        assertEquals(start.fieldScale, end.fieldScale, 0.0001f)
    }

    @Test
    fun workingFieldCarriesMoreEnergyThanIdleField() {
        val idle = VanWindFieldMotion.sample(
            VanAuraSpecs.forState(VanDurableState.IDLE),
            phase = 0.23f,
            budget = VanEffectBudget.FULL,
        )
        val working = VanWindFieldMotion.sample(
            VanAuraSpecs.forState(VanDurableState.WORKING),
            phase = 0.23f,
            budget = VanEffectBudget.FULL,
        )

        assertTrue(working.windStrength > idle.windStrength)
        assertTrue(working.turbulence > idle.turbulence)
        assertTrue(working.waveAmplitude > idle.waveAmplitude)
    }

    @Test
    fun staticBudgetFreezesLivingFieldWithoutRemovingIt() {
        val spec = VanAuraSpecs.forState(VanDurableState.WARNING)
        val early = VanWindFieldMotion.sample(spec, 0.11f, VanEffectBudget.STATIC)
        val late = VanWindFieldMotion.sample(spec, 0.87f, VanEffectBudget.STATIC)

        assertEquals(1f, early.breathing, 0.0001f)
        assertEquals(early.breathing, late.breathing, 0.0001f)
        assertEquals(early.windAngleRad, late.windAngleRad, 0.0001f)
        assertEquals(early.electricPulse, late.electricPulse, 0.0001f)
        assertEquals(early.particleAdvection, late.particleAdvection, 0.0001f)
        assertTrue(early.fieldScale > 0f)
    }

    @Test
    fun budgetTightensFieldBeforeStateMeaningIsLost() {
        val spec = VanAuraSpecs.forState(VanDurableState.URGENT)
        val full = VanWindFieldMotion.sample(spec, 0.4f, VanEffectBudget.FULL)
        val low = VanWindFieldMotion.sample(spec, 0.4f, VanEffectBudget.LOW)
        val static = VanWindFieldMotion.sample(spec, 0.4f, VanEffectBudget.STATIC)

        assertTrue(full.fieldScale > low.fieldScale)
        assertTrue(low.fieldScale > static.fieldScale)
        assertTrue(spec.semanticColor != null)
        assertTrue(spec.envelopeSegments.isNotEmpty())
    }
}
