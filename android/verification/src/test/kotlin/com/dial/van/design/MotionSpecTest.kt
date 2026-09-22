package com.dial.van.design

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

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
    fun `unreduced motion resolves to the DNA durations`() {
        assertEquals(VanMotionSpec.DURATIONS, VanMotionSpec.resolve(reducedMotion = false))
    }

    @Test
    fun `data updates animate at quick, shared elements at standard`() {
        assertEquals(160, VanMotionSpec.dataUpdateDurationMs(reducedMotion = false))
        assertEquals(0, VanMotionSpec.dataUpdateDurationMs(reducedMotion = true))
        assertEquals(240, VanMotionSpec.sharedElementDurationMs(reducedMotion = false))
        assertEquals(0, VanMotionSpec.sharedElementDurationMs(reducedMotion = true))
    }

    @Test
    fun `press scale matches DNA`() {
        assertEquals(0.97f, VanMotionSpec.PRESS_SCALE)
    }

    @Test
    fun `easings are distinct curves`() {
        val easings = setOf(VanMotionSpec.EASING_STANDARD, VanMotionSpec.EASING_ENTER, VanMotionSpec.EASING_EXIT)
        assertEquals(3, easings.size, "the three named easings collapsed to fewer distinct curves")
        assertTrue(VanMotionSpec.EASING_STANDARD.x1 in 0f..1f)
    }
}
