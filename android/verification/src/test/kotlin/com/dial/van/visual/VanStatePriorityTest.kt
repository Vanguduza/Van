package com.dial.van.visual

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Rev 1.5 §24 — the precedence ordering, now that it has one home rather than two.
 *
 * It was private inside `VanLiveVisualState`, which needs Android and therefore cannot be
 * executed here. So the browser arbitration could not ask the same question without a
 * second copy, and two copies of a precedence ordering diverge on the state that matters:
 * the one where a page load and a halted trade both want the embodiment.
 */
class VanStatePriorityTest {

    @Test
    fun `every state has a priority`() {
        for (state in VanDurableState.entries) {
            VanStatePriority.of(state)
        }
    }

    @Test
    fun `the alarms outrank the work and the work outranks the idle`() {
        assertTrue(VanStatePriority.of(VanDurableState.URGENT) > VanStatePriority.of(VanDurableState.WORKING))
        assertTrue(VanStatePriority.of(VanDurableState.WORKING) > VanStatePriority.of(VanDurableState.SUCCESS))
        assertTrue(VanStatePriority.of(VanDurableState.SUCCESS) > VanStatePriority.of(VanDurableState.IDLE))
    }

    @Test
    fun `the authority set is the states the browser must not take`() {
        assertTrue(VanDurableState.URGENT in VanStatePriority.AUTHORITY_HELD)
        assertTrue(VanDurableState.ERROR in VanStatePriority.AUTHORITY_HELD)
        assertTrue(VanDurableState.WARNING in VanStatePriority.AUTHORITY_HELD)
        assertFalse(VanDurableState.WORKING in VanStatePriority.AUTHORITY_HELD)
        assertFalse(VanDurableState.IDLE in VanStatePriority.AUTHORITY_HELD)
    }
}
