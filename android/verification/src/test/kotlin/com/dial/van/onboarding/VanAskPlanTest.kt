package com.dial.van.onboarding

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * VAN asks for each permission himself, when a feature needs it — no checklist and no
 * pairing step (owner direction, 2026-09-25). The P1-AND-002 rules still hold: a grant is
 * read from the device, and "not now" is remembered.
 */
class VanAskPlanTest {

    @Test
    fun `there is no pairing step for the owner`() {
        // The phone is provisioned by the installer (ADR-RB-026); nothing here can pair.
        assertTrue(VanPermission.entries.none { it.id.contains("pair") })
        VanPermission.entries.forEach { permission ->
            val ask = VanAskPlan.ask(permission)
            assertFalse(ask.line.contains("pair", ignoreCase = true), permission.id)
            assertFalse(ask.line.contains("code", ignoreCase = true) && permission != VanPermission.NOTIFICATION_LISTENER, permission.id)
        }
    }

    @Test
    fun `every ask is VAN speaking in the first person`() {
        VanPermission.entries.forEach { permission ->
            val line = VanAskPlan.ask(permission).line
            assertTrue(Regex("\\b(I|I'm|I'll|me|my)\\b").containsMatchIn(line), "${permission.id}: $line")
        }
    }

    @Test
    fun `a held grant is never asked for`() {
        AskTrigger.entries.forEach { trigger ->
            assertFalse(VanAskPlan.shouldAsk(granted = true, declined = false, trigger = trigger))
            assertFalse(VanAskPlan.shouldAsk(granted = true, declined = true, trigger = trigger))
        }
    }

    @Test
    fun `not now silences VAN but not the owner reaching for the feature`() {
        assertFalse(VanAskPlan.shouldAsk(granted = false, declined = true, trigger = AskTrigger.VAN_NEEDS_IT))
        assertTrue(VanAskPlan.shouldAsk(granted = false, declined = true, trigger = AskTrigger.OWNER_REACHED_FOR_IT))
        assertTrue(VanAskPlan.shouldAsk(granted = false, declined = false, trigger = AskTrigger.VAN_NEEDS_IT))
    }

    @Test
    fun `floating asks for the overlay first, then notifications, and stops when both are held`() {
        val held = mutableSetOf<VanPermission>()
        val declined = mutableSetOf<VanPermission>()
        assertEquals(VanPermission.OVERLAY, VanAskPlan.nextFloatingAsk({ it in held }, { it in declined }))
        held += VanPermission.OVERLAY
        assertEquals(VanPermission.NOTIFICATIONS, VanAskPlan.nextFloatingAsk({ it in held }, { it in declined }))
        held += VanPermission.NOTIFICATIONS
        assertNull(VanAskPlan.nextFloatingAsk({ it in held }, { it in declined }))
    }

    @Test
    fun `a declined floating ask is skipped rather than repeated`() {
        val held = setOf<VanPermission>()
        val declined = setOf(VanPermission.OVERLAY)
        assertEquals(VanPermission.NOTIFICATIONS, VanAskPlan.nextFloatingAsk({ it in held }, { it in declined }))
        assertNull(VanAskPlan.nextFloatingAsk({ it in held }, { true }))
    }

    @Test
    fun `the greeting welcomes the owner back and is honest about the connection`() {
        assertEquals("Welcome back.", VanAskPlan.greeting(firstLaunch = false, connected = true))
        assertEquals("Hi, I'm VAN.", VanAskPlan.greeting(firstLaunch = true, connected = true))
        val offline = VanAskPlan.greeting(firstLaunch = false, connected = false)
        assertTrue(offline.startsWith("Welcome back."))
        assertTrue(offline.contains("can't reach"))
        assertFalse(offline.contains("pair", ignoreCase = true))
    }

    @Test
    fun `ids round trip`() {
        VanPermission.entries.forEach { assertEquals(it, VanPermission.fromId(it.id)) }
        assertNull(VanPermission.fromId("pairing"))
    }
}
