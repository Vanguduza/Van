package com.dial.van.command

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * P3-AND-007 / P3-AND-009 — the Command Centre's navigation, out of the 1,342-line Activity
 * and into something that can be executed.
 */
class CommandNavTest {

    @Test
    fun `a browser page goes back to the browser module, not to home`() {
        // Sending the owner to Home from a browser page loses the module they were working
        // in, which on a four-page section means four taps to get back.
        for (child in CommandNav.BROWSER_CHILDREN) {
            assertEquals(CommandModule.BROWSER_AUTOMATION, CommandNav.back(child), child.name)
        }
    }

    @Test
    fun `everything else goes back to home, and home leaves`() {
        assertNull(CommandNav.back(CommandModule.OVERVIEW))
        assertFalse(CommandNav.handlesBack(CommandModule.OVERVIEW))
        for (module in CommandModule.entries) {
            if (module == CommandModule.OVERVIEW) continue
            if (module in CommandNav.BROWSER_CHILDREN) continue
            assertEquals(CommandModule.OVERVIEW, CommandNav.back(module), module.name)
        }
    }

    @Test
    fun `back always terminates`() {
        // A back rule that can cycle is a back button the owner cannot escape with.
        for (module in CommandModule.entries) {
            var at: CommandModule? = module
            var steps = 0
            while (at != null) {
                at = CommandNav.back(at)
                steps += 1
                assertTrue(steps <= CommandModule.entries.size, "back cycles from $module")
            }
        }
    }

    @Test
    fun `saved state round-trips through an id, never an ordinal`() {
        for (module in CommandModule.entries) {
            assertEquals(module, CommandNav.restore(CommandNav.save(module)), module.name)
            assertEquals(module.id, CommandNav.save(module))
        }
    }

    @Test
    fun `an unknown or absent saved module lands on home`() {
        // Ordinals would restore the wrong screen the first time a module is inserted into
        // the enum, silently, to an owner whose process Android had just killed.
        assertEquals(CommandModule.OVERVIEW, CommandNav.restore(null))
        assertEquals(CommandModule.OVERVIEW, CommandNav.restore(""))
        assertEquals(CommandModule.OVERVIEW, CommandNav.restore("a_module_from_a_later_build"))
    }

    @Test
    fun `every primary module is reachable and distinct`() {
        assertEquals(CommandNav.PRIMARY.size, CommandNav.PRIMARY.toSet().size)
        assertTrue(CommandModule.OVERVIEW in CommandNav.PRIMARY, "no way home")
        assertTrue(CommandNav.PRIMARY.all { it in CommandModule.entries })
    }

    @Test
    fun `every module has an id nothing else has`() {
        val ids = CommandModule.entries.map { it.id }
        assertEquals(ids.size, ids.toSet().size, "$ids")
        assertTrue(ids.none { it.isBlank() })
    }
}
