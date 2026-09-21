package com.dial.van.design

import org.junit.Assert.assertEquals
import org.junit.Test

class MotionSpecTest {

    @Test
    fun `DNA durations match the published tokens`() {
        assertEquals(80, VanMotionSpec.DURATIONS.instantMs)
        assertEquals(160, VanMotionSpec.DURATIONS.quickMs)
        assertEquals(240, VanMotionSpec.DURATIONS.standardMs)
        assertEquals(360, VanMotionSpec.DURATIONS.expressiveMs)
    }

    @Test
    fun `reduced motion collapses every duration to zero`() {
        val resolved = VanMotionSpec.resolve(reducedMotion = true)
        assertEquals(0, resolved.instantMs)
        assertEquals(0, resolved.quickMs)
        assertEquals(0, resolved.standardMs)
        assertEquals(0, resolved.expressiveMs)
    }

    @Test
    fun `press scale matches DNA`() {
        assertEquals(0.97f, VanMotionSpec.PRESS_SCALE, 0.0001f)
    }
}
