package com.dial.van.visual

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Existing STATE_ACTION_MATRIX timing, not UI chrome animation duration. */
class VanFiniteActionTimingContractTest {
    @Test fun allFourteenRuntimeGestureDurationsMatchTheAuthoredContract() {
        val expected = listOf(1400L,650L,1200L,1200L,1200L,1200L,1200L,
            1800L,1000L,900L,1100L,1500L,700L,700L)
        for (action in VanFiniteAction.entries) {
            assertEquals(expected[action.code-1], VanMotionMap.actionDurationMs(action), action.name)
        }
    }
    @Test fun everyFiniteGestureHasTimeForAnticipationPoseAndReturn() {
        for (action in VanFiniteAction.entries) {
            assertTrue(VanMotionMap.actionDurationMs(action) in 600L..1800L, action.name)
        }
    }
    @Test fun workboardChromeKeepsItsSeparateShortTransition() {
        assertEquals(240, VanMotionMap.presentationChange().durationMs)
        assertEquals(0, VanMotionMap.presentationChange(reducedMotion=true).durationMs)
        assertEquals(700L, VanMotionMap.actionDurationMs(VanFiniteAction.OPEN_PANEL))
        assertEquals(700L, VanMotionMap.actionDurationMs(VanFiniteAction.CLOSE_PANEL))
    }
}
