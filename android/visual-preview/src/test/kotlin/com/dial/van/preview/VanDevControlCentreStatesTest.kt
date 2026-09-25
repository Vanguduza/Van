package com.dial.van.preview

import com.dial.van.command.nav.VanRoute
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * VAN-DEV-011 / DNA V6 — every Development Control Centre route renders all seven screen
 * states, and each tile's state is the one the shipping reducer actually produced (not a
 * label painted over whatever came back).
 */
class VanDevControlCentreStatesTest {

    @Test
    fun everyDevelopmentRouteHasAPreviewFixture() {
        assertEquals(VanRoute.DEV_TEMPLATES.toSet(), VanDevControlCentreStates.templates().toSet())
    }

    @Test
    fun everyRouteRendersAllSevenStatesFromTheShippingReducer() {
        for (template in VanRoute.DEV_TEMPLATES) {
            val tiles = VanDevControlCentreStates.tilesFor(template)
            assertEquals(template, VanDevControlCentreStates.Seven.entries.toList(), tiles.map { it.expected })
            for (tile in tiles) {
                assertEquals("$template ${tile.expected}", tile.expected, VanDevControlCentreStates.classify(tile.state))
            }
        }
    }

    @Test
    fun theSheetsRender() {
        for (template in VanRoute.DEV_TEMPLATES) {
            val sheet = VanDevControlCentreStates.sheetFor(template)
            assertTrue(template, sheet.width > 1000 && sheet.height > 600)
        }
    }

    @Test
    fun slugsAreDistinctFileNames() {
        val slugs = VanRoute.DEV_TEMPLATES.map(VanDevControlCentreStates::slug)
        assertEquals(slugs.size, slugs.toSet().size)
        assertTrue(slugs.none { it.contains('/') || it.contains('{') || it.contains('?') })
    }
}
