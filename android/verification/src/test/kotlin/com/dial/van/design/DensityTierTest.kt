package com.dial.van.design

import kotlin.test.Test
import kotlin.test.assertEquals

class DensityTierTest {

    @Test
    fun `overlay is always compact regardless of width`() {
        assertEquals(VanDensity.Compact, VanDensity.from(widthDp = 100, isOverlay = true))
        assertEquals(VanDensity.Compact, VanDensity.from(widthDp = 1200, isOverlay = true))
    }

    @Test
    fun `narrow non-overlay widths are regular`() {
        assertEquals(VanDensity.Regular, VanDensity.from(widthDp = 360, isOverlay = false))
        assertEquals(VanDensity.Regular, VanDensity.from(widthDp = 599, isOverlay = false))
    }

    @Test
    fun `600dp and above is wide`() {
        assertEquals(VanDensity.Wide, VanDensity.from(widthDp = 600, isOverlay = false))
        assertEquals(VanDensity.Wide, VanDensity.from(widthDp = 1024, isOverlay = false))
    }

    @Test
    fun `breakpoint constant matches the boundary`() {
        assertEquals(600, VanDensity.WIDE_BREAKPOINT_DP)
        assertEquals(
            VanDensity.Regular,
            VanDensity.from(widthDp = VanDensity.WIDE_BREAKPOINT_DP - 1, isOverlay = false),
        )
        assertEquals(
            VanDensity.Wide,
            VanDensity.from(widthDp = VanDensity.WIDE_BREAKPOINT_DP, isOverlay = false),
        )
    }
}
