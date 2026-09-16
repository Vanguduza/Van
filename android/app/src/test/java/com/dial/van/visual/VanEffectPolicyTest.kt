package com.dial.van.visual

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VanEffectPolicyTest {

    @Test
    fun reducedMotionIsDesignedStillnessNotStaticFloor() {
        val budget = VanEffectPolicy.resolve(VanEffectConditions(reducedMotion = true))
        assertEquals(VanEffectBudget.REDUCED_MOTION, budget)
        assertTrue(budget.filamentScale > 0.3f)
        assertFalse(budget.allowMotion)
        assertTrue(budget.allowLiveBlur)
        assertTrue(budget.keepsStateIndicators)
    }

    @Test
    fun thermalSevereUsesStaticFloor() {
        val budget = VanEffectPolicy.resolve(VanEffectConditions(thermalStatus = VanEffectPolicy.THERMAL_SEVERE))
        assertEquals(VanEffectBudget.STATIC, budget)
        assertTrue(budget.filamentScale > 0f)
    }

    @Test
    fun workingAuraNeverDrawsAFullRing() {
        val spec = VanAuraSpecs.forState(VanDurableState.WORKING)
        assertTrue(spec.filamentCount in 1..5)
        assertTrue(spec.deformation > 0f)
        assertTrue(spec.fieldAsymmetry > 0f)
        assertEquals(110f, VanAuraSpec.MAX_ARC_SWEEP_DEG)
        assertEquals(220f, VanAuraSpec.MAX_TOTAL_ARC_DEG)
        assertEquals(180f, VanAuraSpec.MAX_ENVELOPE_COVERAGE_DEG)
        assertTrue(spec.envelopeSegments.size in 1..4)
        assertTrue(spec.envelopeRadiusScale >= 1.35f)
    }
}
