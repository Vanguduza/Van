package com.dial.van.design

import org.junit.Assert.assertEquals
import org.junit.Test

class DensityTierTest {

    @Test
    fun `overlay is always compact`() {
        assertEquals(VanDensity.Compact, VanDensity.from(widthDp = 1200, isOverlay = true))
    }

    @Test
    fun `600dp and above is wide, below is regular`() {
        assertEquals(VanDensity.Regular, VanDensity.from(widthDp = 599, isOverlay = false))
        assertEquals(VanDensity.Wide, VanDensity.from(widthDp = 600, isOverlay = false))
    }
}
