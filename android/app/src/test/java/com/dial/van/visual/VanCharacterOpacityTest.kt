package com.dial.van.visual

import org.junit.Assert.assertEquals
import org.junit.Test

class VanCharacterOpacityTest {
    @Test
    fun characterPaletteNeverUsesWholeBodyTransparency() {
        VanDurableState.entries.forEach { state ->
            assertEquals(
                "$state must not glassify VAN's body",
                1f,
                VanStatusPalette.forState(state).dim,
                0.0001f,
            )
        }
    }
}
