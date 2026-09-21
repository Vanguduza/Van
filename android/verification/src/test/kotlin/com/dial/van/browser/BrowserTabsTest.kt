package com.dial.van.browser

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Rev 1.5 §17.1 — "Chromium target state is authoritative."
 *
 * The phone holds a projection and never invents a tab. Every test here is an ordering a
 * lossy channel can produce, which is why the reducer is pure: none of these can be staged
 * on a phone, and all of them happen.
 */
class BrowserTabsTest {

    private fun state(vararg events: TabEvent) = BrowserTabs.reduceAll(TabState(), events.toList())

    @Test
    fun `a created tab is not an activated tab`() {
        // Chromium opening a target in the background is not the owner being moved to it.
        // §17.1 has a separate event for that, and conflating them makes a background
        // popup steal the screen.
        val after = state(TabEvent.Created("t1"))
        assertEquals(1, after.tabs.size)
        assertNull(after.activeTargetId)
    }

    @Test
    fun `a tab opened from another lands next to it`() {
        val after = state(
            TabEvent.Created("t1"),
            TabEvent.Created("t2"),
            TabEvent.Created("t3", openerTargetId = "t1"),
        )
        assertEquals(listOf("t1", "t3", "t2"), after.tabs.map { it.targetId })
    }

    @Test
    fun `an unknown opener puts the tab at the end rather than nowhere`() {
        val after = state(TabEvent.Created("t1"), TabEvent.Created("t2", openerTargetId = "gone"))
        assertEquals(listOf("t1", "t2"), after.tabs.map { it.targetId })
    }

    @Test
    fun `an update for a tab we never saw created creates it`() {
        // The events arrive over a channel that can drop. A tab the host is telling us
        // about exists, and discarding the update leaves the owner looking at a page that
        // is not in their own tab list.
        val after = state(TabEvent.Updated("t9", title = "Statements", url = "https://x/"))
        assertEquals(1, after.tabs.size)
        assertEquals("Statements", after.tabs.single().title)
    }

    @Test
    fun `an update carries only what it names`() {
        // A partial update that nulled the rest would blank the title every time the
        // loading flag changed.
        val after = state(
            TabEvent.Created("t1"),
            TabEvent.Updated("t1", title = "Statements", url = "https://x/", loading = true),
            TabEvent.Updated("t1", loading = false),
        )
        val tab = after.tabs.single()
        assertEquals("Statements", tab.title)
        assertEquals("https://x/", tab.url)
        assertEquals(false, tab.loading)
    }

    @Test
    fun `a duplicate create is not a second tab`() {
        val after = state(TabEvent.Created("t1"), TabEvent.Created("t1"))
        assertEquals(1, after.tabs.size)
    }

    @Test
    fun `activating an unknown target adopts it rather than losing the owner`() {
        // The host says this is what the owner is looking at. A projection that refused it
        // would show one page and list another.
        val after = state(TabEvent.Activated("t7"))
        assertEquals("t7", after.activeTargetId)
        assertEquals(listOf("t7"), after.tabs.map { it.targetId })
    }

    @Test
    fun `closing the active tab lands on its neighbour, not on the first`() {
        // Closing the fourth of five and finding yourself on the first is a browser nobody
        // recognises.
        val after = state(
            TabEvent.Created("t1"), TabEvent.Created("t2"), TabEvent.Created("t3"),
            TabEvent.Created("t4"), TabEvent.Created("t5"),
            TabEvent.Activated("t4"),
            TabEvent.Closed("t4"),
        )
        assertEquals(listOf("t1", "t2", "t3", "t5"), after.tabs.map { it.targetId })
        assertEquals("t5", after.activeTargetId)
    }

    @Test
    fun `closing the last tab falls back to the one before it`() {
        val after = state(
            TabEvent.Created("t1"), TabEvent.Created("t2"),
            TabEvent.Activated("t2"), TabEvent.Closed("t2"),
        )
        assertEquals("t1", after.activeTargetId)
    }

    @Test
    fun `closing an inactive tab does not move the owner`() {
        // Four tabs, not two. With only two, closing the inactive one leaves the active
        // one as the neighbour that a *wrong* implementation would also pick, so the
        // test passed with the "is this the active tab" check deleted entirely.
        //
        // Here the owner is on t4 and closes t1. The neighbour of t1 is t2, so an
        // implementation that treated every close as a close of the active tab would move
        // them to t2 — a browser that jumps to a different page because they tidied up a
        // tab they were not looking at.
        val after = state(
            TabEvent.Created("t1"), TabEvent.Created("t2"),
            TabEvent.Created("t3"), TabEvent.Created("t4"),
            TabEvent.Activated("t4"), TabEvent.Closed("t1"),
        )
        assertEquals(listOf("t2", "t3", "t4"), after.tabs.map { it.targetId })
        assertEquals("t4", after.activeTargetId)
    }

    @Test
    fun `closing the only tab leaves nothing active rather than a dangling id`() {
        // An activeTargetId pointing at a tab that is gone is how the input path ends up
        // addressing a target the host has closed.
        val after = state(TabEvent.Created("t1"), TabEvent.Activated("t1"), TabEvent.Closed("t1"))
        assertTrue(after.tabs.isEmpty())
        assertNull(after.activeTargetId)
    }

    @Test
    fun `a close for a tab that is already gone changes nothing`() {
        val before = state(TabEvent.Created("t1"), TabEvent.Activated("t1"))
        assertEquals(before, BrowserTabs.reduce(before, TabEvent.Closed("t9")))
    }

    @Test
    fun `the label falls back through title, url and loading`() {
        assertEquals("Statements", BrowserTab("t", title = "Statements", url = "https://x/").ownerReadableLabel)
        assertEquals("https://x/", BrowserTab("t", url = "https://x/").ownerReadableLabel)
        assertEquals("Loading…", BrowserTab("t", loading = true).ownerReadableLabel)
        assertEquals("New tab", BrowserTab("t").ownerReadableLabel)
    }
}

/**
 * §17.6 — the system Back gesture, in the order the section states.
 */
class BrowserBackPolicyTest {

    @Test
    fun `a panel closes first`() {
        assertEquals(
            BackOutcome.CLOSE_TRANSIENT_PANEL,
            BrowserBackPolicy.decide(
                transientPanelOpen = true, addressBarEditing = true, canGoBack = true,
            ),
        )
    }

    @Test
    fun `then the address bar edit`() {
        assertEquals(
            BackOutcome.LEAVE_ADDRESS_EDIT,
            BrowserBackPolicy.decide(
                transientPanelOpen = false, addressBarEditing = true, canGoBack = true,
            ),
        )
    }

    @Test
    fun `back does not close the browser while the page has history`() {
        // The clause §17.6 states as a prohibition, and the one that matters: an owner
        // three pages into a site is one tap from losing all of it if this is wrong.
        assertEquals(
            BackOutcome.BROWSER_BACK,
            BrowserBackPolicy.decide(
                transientPanelOpen = false, addressBarEditing = false, canGoBack = true,
            ),
        )
    }

    @Test
    fun `with nothing left it is Android's back`() {
        assertEquals(
            BackOutcome.ACTIVITY_BACK,
            BrowserBackPolicy.decide(
                transientPanelOpen = false, addressBarEditing = false, canGoBack = false,
            ),
        )
    }
}
