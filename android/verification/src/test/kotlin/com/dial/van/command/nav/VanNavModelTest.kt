package com.dial.van.command.nav

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class VanNavModelTest {

    @Test
    fun `restore falls back to home for null, blank or unknown routes`() {
        assertEquals(VanRoute.HOME, VanNavModel.restore(null))
        assertEquals(VanRoute.HOME, VanNavModel.restore(""))
        assertEquals(VanRoute.HOME, VanNavModel.restore("not-a-route"))
    }

    @Test
    fun `restore keeps a known concrete route, including one with an argument`() {
        assertEquals(VanRoute.ATTENTION, VanNavModel.restore(VanRoute.ATTENTION))
        assertEquals("work/missions/m-42", VanNavModel.restore("work/missions/m-42"))
        assertEquals("projects/acme", VanNavModel.restore("projects/acme"))
    }

    @Test
    fun `startDestination resolves a plain launch to home`() {
        assertEquals(VanRoute.HOME, VanNavModel.startDestination(null))
        assertEquals(VanRoute.HOME, VanNavModel.startDestination("  "))
    }

    @Test
    fun `startDestination honours a new-style route already`() {
        assertEquals(VanRoute.TRADING, VanNavModel.startDestination(VanRoute.TRADING))
    }

    @Test
    fun `startDestination maps every legacy CommandModule id somewhere known`() {
        val legacyIds = listOf(
            "overview", "chat", "tasks", "missions", "activity", "decisions", "projects",
            "browser_automation", "browser_tasks", "browser_escalations", "browser_sessions",
            "browser_policy", "systems", "connections", "notifications", "speech", "settings",
        )
        for (id in legacyIds) {
            val resolved = VanNavModel.startDestination(id)
            assertTrue(VanRoute.isKnown(resolved), "legacy id '$id' resolved to unknown route '$resolved'")
        }
    }

    @Test
    fun `startDestination falls back to home for an unrecognised extra`() {
        assertEquals(VanRoute.HOME, VanNavModel.startDestination("something-else-entirely"))
    }

    @Test
    fun `deepLink parses every primary and more destination`() {
        for (route in VanRoute.PRIMARY + VanRoute.MORE) {
            assertEquals(route, VanNavModel.deepLink("van://$route"))
        }
    }

    @Test
    fun `deepLink parses a concrete argument route`() {
        assertEquals("projects/acme-42", VanNavModel.deepLink("van://projects/acme-42"))
        assertEquals("work/missions/m-1", VanNavModel.deepLink("van://work/missions/m-1"))
    }

    @Test
    fun `deepLink bare scheme resolves to home`() {
        assertEquals(VanRoute.HOME, VanNavModel.deepLink("van://"))
    }

    @Test
    fun `deepLink rejects a foreign scheme or unknown path`() {
        assertNull(VanNavModel.deepLink("https://home"))
        assertNull(VanNavModel.deepLink("van://not-a-real-route"))
    }

    @Test
    fun `deepLink ignores a trailing query string`() {
        assertEquals(VanRoute.ATTENTION, VanNavModel.deepLink("van://attention?source=notification"))
    }

    @Test
    fun `back returns each route's DNA-declared parent, and null at home`() {
        assertNull(VanNavModel.back(VanRoute.HOME))
        assertEquals(VanRoute.HOME, VanNavModel.back(VanRoute.ATTENTION))
        assertEquals(VanRoute.HOME, VanNavModel.back(VanRoute.WORK))
        assertEquals(VanRoute.WORK, VanNavModel.back(VanRoute.WORK_BROWSER))
        assertEquals(VanRoute.WORK_BROWSER, VanNavModel.back(VanRoute.WORK_BROWSER_TASKS))
        assertEquals(VanRoute.WORK, VanNavModel.back("work/missions/m-1"))
        assertEquals(VanRoute.PROJECTS, VanNavModel.back("projects/acme"))
        assertEquals(VanRoute.HOME, VanNavModel.back(VanRoute.SETTINGS))
    }

    @Test
    fun `back on an unknown route is null rather than a guess`() {
        assertNull(VanNavModel.back("nonsense"))
    }

    @Test
    fun `isPrimary is true only for the five adaptive-nav destinations`() {
        assertTrue(VanNavModel.isPrimary(VanRoute.HOME))
        assertTrue(VanNavModel.isPrimary(VanRoute.ATTENTION))
        assertTrue(VanNavModel.isPrimary(VanRoute.WORK))
        assertTrue(VanNavModel.isPrimary(VanRoute.TRADING))
        assertTrue(VanNavModel.isPrimary(VanRoute.MEMORY))
        assertFalse(VanNavModel.isPrimary(VanRoute.SETTINGS))
        assertFalse(VanNavModel.isPrimary(VanRoute.CONNECTED))
        assertFalse(VanNavModel.isPrimary("projects/acme"))
    }

    @Test
    fun `every route template has exactly one parent chain up to home`() {
        for (template in VanRoute.ALL_TEMPLATES) {
            if (template == VanRoute.HOME) continue
            var current: String? = template
            var hops = 0
            while (current != null && current != VanRoute.HOME) {
                current = VanRoute.PARENTS[current]
                hops += 1
                assertTrue(hops < 10, "possible cycle starting at $template")
            }
            assertEquals(VanRoute.HOME, current, "$template does not resolve up to home")
        }
    }

    @Test
    fun `missionRoute and projectRoute build routes VanRoute recognises`() {
        val mission = VanRoute.missionRoute("m 1")
        assertTrue(VanRoute.isKnown(mission))
        val project = VanRoute.projectRoute("acme")
        assertTrue(VanRoute.isKnown(project))
    }
}
