package com.dial.van.visual

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * DNA §2 — the aura reacts to voice amplitude during LISTENING/SPEAKING.
 */
class VanAuraVoiceReactivityTest {

    private val base = VanAuraSpecs.forState(VanDurableState.LISTENING)

    @Test
    fun `zero amplitude leaves the spec unchanged`() {
        assertEquals(base, base.reactToVoiceAmplitude(0f))
    }

    @Test
    fun `a negative amplitude is treated as zero`() {
        assertEquals(base, base.reactToVoiceAmplitude(-0.4f))
    }

    @Test
    fun `a louder voice brightens intensity, arc activity and spark rate`() {
        val quiet = base.reactToVoiceAmplitude(0.2f)
        val loud = base.reactToVoiceAmplitude(1f)
        assertTrue(loud.intensity > quiet.intensity)
        assertTrue(loud.arcActivity > quiet.arcActivity)
        assertTrue(loud.sparkRate > quiet.sparkRate)
        assertTrue(loud.intensity > base.intensity)
    }

    @Test
    fun `intensity never exceeds the face-safe ceiling regardless of amplitude`() {
        val reacted = VanAuraSpecs.forState(VanDurableState.WORKING).reactToVoiceAmplitude(1f)
        assertTrue(reacted.intensity <= VanAuraSpec.MAX_INTENSITY)
        assertTrue(reacted.faceSafe)
    }

    @Test
    fun `amplitude above one is clamped the same as exactly one`() {
        assertEquals(base.reactToVoiceAmplitude(1f), base.reactToVoiceAmplitude(3f))
    }

    @Test
    fun `topology fields — filaments, envelope, semantic colour — are untouched`() {
        val reacted = base.reactToVoiceAmplitude(0.7f)
        assertEquals(base.filamentCount, reacted.filamentCount)
        assertEquals(base.envelopeSegments, reacted.envelopeSegments)
        assertEquals(base.semanticColor, reacted.semanticColor)
        assertEquals(base.envelopeRadiusScale, reacted.envelopeRadiusScale)
    }
}
