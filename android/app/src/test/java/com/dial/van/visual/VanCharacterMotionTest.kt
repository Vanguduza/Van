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
        VanDurableState.entries.forEach { durable ->
            listOf(-1f, 0f, 1f).forEach { attention ->
                val state = VanVisualState(
                    durableState = durable,
                    attentionX = attention,
                    attentionY = attention,
                    urgency = 1f,
                )
                val still = VanCharacterMotion.sample(state, 0f, reducedMotion = true)
                listOf(-0.2f, 0.12f, 0.83f, 1f, 1.2f).forEach { phase ->
                    assertEquals(
                        "$durable must not animate in reduced motion",
                        still,
                        VanCharacterMotion.sample(state, phase, reducedMotion = true),
                    )
                }
                assertEquals(0f, still.offsetYDp, 0.0001f)
                assertEquals(1f, still.scale, 0.0001f)
                assertTrue(kotlin.math.abs(still.offsetXDp) <= 0.45f)
                assertTrue(kotlin.math.abs(still.rotationDeg) <= 0.12f)
                if (attention == 0f) {
                    assertEquals(0f, still.offsetXDp, 0.0001f)
                    assertEquals(0f, still.rotationDeg, 0.0001f)
                } else {
                    assertTrue("static lean must face the owner", still.offsetXDp * attention > 0f)
                    assertTrue("static tilt must face the owner", still.rotationDeg * attention > 0f)
                }
                assertEquals(
                    "owner attention must be clamped",
                    still,
                    VanCharacterMotion.sample(state.copy(attentionX = attention * 2f), 0f, reducedMotion = true),
                )
            }
        }
    }

    @Test
    fun ownerArtMotionStaysSubtle() {
        VanDurableState.entries.forEach { durable ->
            listOf(-1f, 0f, 1f).forEach { attentionX ->
                listOf(-1f, 0f, 1f).forEach { attentionY ->
                    listOf(0f, 1f).forEach { urgency ->
                        val state = VanVisualState(
                            durableState = durable,
                            attentionX = attentionX,
                            attentionY = attentionY,
                            urgency = urgency,
                        )
                        repeat(201) { index ->
                            val frame = VanCharacterMotion.sample(state, index / 200f, reducedMotion = false)
                            // Rev 3's stronger phone-visible motion remains inside this bounded envelope.
                            assertTrue("$durable x offset too large", kotlin.math.abs(frame.offsetXDp) <= 1.6f)
                            assertTrue("$durable y offset too large", kotlin.math.abs(frame.offsetYDp) <= 2.5f)
                            assertTrue("$durable rotation too large", kotlin.math.abs(frame.rotationDeg) <= 1.65f)
                            assertTrue("$durable scale too large", frame.scale in 0.992f..1.008f)
                        }
                    }
                }
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
