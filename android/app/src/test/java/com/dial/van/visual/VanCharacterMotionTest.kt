package com.dial.van.visual

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class VanCharacterMotionTest {

    @Test
    fun loopBoundaryIsSeamless() {
        val state = VanVisualState(durableState = VanDurableState.WORKING, attentionX = 0.4f)
        val start = VanCharacterMotion.sample(state, 0f, reducedMotion = false)
        val end = VanCharacterMotion.sample(state, 1f, reducedMotion = false)

        assertEquals(start.offsetXDp, end.offsetXDp, 0.0001f)
        assertEquals(start.offsetYDp, end.offsetYDp, 0.0001f)
        assertEquals(start.rotationDeg, end.rotationDeg, 0.0001f)
        assertEquals(start.scale, end.scale, 0.0001f)
    }

    @Test
    fun reducedMotionRemovesAutonomousMovement() {
        val state = VanVisualState(
            durableState = VanDurableState.URGENT,
            attentionX = 0.8f,
            urgency = 1f,
        )
        val a = VanCharacterMotion.sample(state, 0.12f, reducedMotion = true)
        val b = VanCharacterMotion.sample(state, 0.83f, reducedMotion = true)

        assertEquals(a, b)
        assertEquals(0f, a.offsetYDp, 0.0001f)
        assertEquals(0f, a.rotationDeg, 0.0001f)
        assertEquals(1f, a.scale, 0.0001f)
    }

    @Test
    fun ownerArtMotionStaysSubtle() {
        VanDurableState.entries.forEach { durable ->
            val state = VanVisualState(
                durableState = durable,
                attentionX = 1f,
                attentionY = 1f,
                urgency = 1f,
            )
            repeat(21) { index ->
                val frame = VanCharacterMotion.sample(state, index / 20f, reducedMotion = false)
                assertTrue("$durable x offset too large", kotlin.math.abs(frame.offsetXDp) <= 1.5f)
                assertTrue("$durable y offset too large", kotlin.math.abs(frame.offsetYDp) <= 1.4f)
                assertTrue("$durable rotation too large", kotlin.math.abs(frame.rotationDeg) <= 1.4f)
                assertTrue("$durable scale too large", frame.scale in 0.992f..1.008f)
            }
        }
    }

    @Test
    fun alertUrgencyAddsTremorButDoesNotBreakBounds() {
        val calm = VanVisualState(durableState = VanDurableState.WARNING, urgency = 0f)
        val urgent = calm.copy(urgency = 1f)
        val calmFrame = VanCharacterMotion.sample(calm, 0.27f, reducedMotion = false)
        val urgentFrame = VanCharacterMotion.sample(urgent, 0.27f, reducedMotion = false)

        assertTrue(
            kotlin.math.abs(urgentFrame.offsetXDp - calmFrame.offsetXDp) > 0.001f ||
                kotlin.math.abs(urgentFrame.rotationDeg - calmFrame.rotationDeg) > 0.001f,
        )
    }
}
