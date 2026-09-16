package com.dial.van.visual

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.assertNotEquals
import org.junit.Test

class VanAuraEnvelopeTest {

    @Test
    fun everyStateHasAZoneCFragment() {
        VanDurableState.entries.forEach { state ->
            val spec = VanAuraSpecs.forState(state)
            assertTrue("$state missing Zone C", spec.envelopeSegments.isNotEmpty())
            assertTrue("$state envelope too close: ${spec.envelopeRadiusScale}", spec.envelopeRadiusScale >= VanAuraSpec.MIN_ENVELOPE_SCALE)
            assertTrue("$state envelope too far: ${spec.envelopeRadiusScale}", spec.envelopeRadiusScale <= VanAuraSpec.MAX_ENVELOPE_SCALE)
            assertTrue("$state coverage ${spec.envelopeCoverageDeg()}", spec.envelopeCoverageDeg() <= VanAuraSpec.MAX_ENVELOPE_COVERAGE_DEG)
            assertTrue("$state too many segments", spec.envelopeSegments.size <= VanAuraSpec.MAX_ENVELOPE_SEGMENTS)
        }
    }

    @Test
    fun zoneCTopologyIsUniquePerState() {
        val signatures = VanDurableState.entries.map { state ->
            val spec = VanAuraSpecs.forState(state)
            spec.envelopeSegments.joinToString { "${it.startDeg}:${it.sweepDeg}:${it.node}" } + "|${spec.envelopeRadiusScale}"
        }
        assertEquals(18, signatures.size)
        assertEquals("Zone C topology must differ by state, not only colour", 18, signatures.toSet().size)
    }

    @Test
    fun lowAndStaticKeepReadableEnvelope() {
        listOf(VanEffectBudget.LOW, VanEffectBudget.STATIC, VanEffectBudget.REDUCED_MOTION).forEach { budget ->
            VanDurableState.entries.forEach { state ->
                val spec = VanAuraSpecs.forState(state, budget)
                assertTrue("$state/$budget dropped Zone C", spec.segmentsForBudget(budget).isNotEmpty())
                assertTrue("$state/$budget envelope alpha collapsed", spec.envelopeAlpha > 0.04f)
            }
        }
    }

    @Test
    fun semanticColourDoesNotRepaintIdentityStatesWithoutEnvelope() {
        val warning = VanAuraSpecs.forState(VanDurableState.WARNING)
        val idle = VanAuraSpecs.forState(VanDurableState.IDLE)
        assertEquals(VanGlassTokens.ACCENT_AMBER, warning.semanticColor)
        assertEquals(null, idle.semanticColor)
        assertNotEquals(warning.envelopeSegments, idle.envelopeSegments)
    }

    @Test
    fun tradePreviewsReserveDistinctZoneCColours() {
        val watching = VanAuraSpecs.tradePreview("watching")
        val entry = VanAuraSpecs.tradePreview("entry")
        val stop = VanAuraSpecs.tradePreview("stop")
        assertEquals(VanGlassTokens.ACCENT_TEAL, watching.semanticColor)
        assertEquals(VanGlassTokens.ACCENT_GOLD, entry.semanticColor)
        assertEquals(VanGlassTokens.ACCENT_RED, stop.semanticColor)
        assertTrue(watching.envelopeSegments.isNotEmpty())
    }
}
