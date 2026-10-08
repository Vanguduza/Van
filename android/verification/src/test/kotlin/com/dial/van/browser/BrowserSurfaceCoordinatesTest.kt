package com.dial.van.browser

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class BrowserSurfaceCoordinatesTest {
    @Test fun `letterboxed picture maps actual page pixels and refuses black bar taps`() {
        // 400x200 page fitted into a 400x600 phone surface has a 200px bar at top and bottom.
        assertNull(BrowserSurfaceCoordinates.map(100f, 100f, 400, 600, 400, 200))
        assertNull(BrowserSurfaceCoordinates.map(100f, 500f, 400, 600, 400, 200))
        assertEquals(0 to 0, BrowserSurfaceCoordinates.map(0f, 200f, 400, 600, 400, 200))
        assertEquals(65_535 to 65_535, BrowserSurfaceCoordinates.map(399f, 399f, 400, 600, 400, 200))
    }
    @Test fun `drag release outside image clamps instead of losing pointer up`() {
        assertEquals(65_535 to 0, BrowserSurfaceCoordinates.map(900f, 0f, 400, 600, 400, 200, clamp = true))
        assertNull(BrowserSurfaceCoordinates.map(Float.NaN, 0f, 400, 600, 400, 200, clamp = true))
        assertNull(BrowserSurfaceCoordinates.map(0f, 0f, 0, 600, 400, 200))
    }
    @Test fun `matching aspect ratios preserve existing normalization`() {
        val mapped = BrowserSurfaceCoordinates.map(150f, 300f, 300, 600, 600, 1200)!!
        assertEquals(BrowserInputProtocol.normalize(150f, 300), mapped.first)
        assertEquals(BrowserInputProtocol.normalize(300f, 600), mapped.second)
        assertTrue(mapped.first in 0..65_535)
    }
}
