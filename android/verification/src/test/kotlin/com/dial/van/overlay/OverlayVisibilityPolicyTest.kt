package com.dial.van.overlay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * P1-PERF-002 — the overlay used to animate with the screen off.
 *
 * The service drove its lifecycle to STARTED when the view was added and never below it
 * while the service lived, and there was no `ACTION_SCREEN_OFF` receiver, so VAN produced
 * frames into a display nobody was looking at for as long as the service was up.
 */
class OverlayVisibilityPolicyTest {

    @Test
    fun `the screen being off stops the animation`() {
        val visible = OverlayVisibility(screenOn = true)
        assertTrue(OverlayVisibilityPolicy.shouldAnimate(visible))
        assertFalse(OverlayVisibilityPolicy.shouldAnimate(visible.copy(screenOn = false)))
    }

    @Test
    fun `a paused overlay is CREATED, not STOPPED or destroyed`() {
        // The composition is retained, so waking the phone does not rebuild the overlay,
        // and the view stays attached so it does not visibly disappear and reappear.
        assertEquals(
            OverlayLifecycleTarget.PAUSED,
            OverlayVisibilityPolicy.target(OverlayVisibility(screenOn = false)),
        )
        assertEquals(
            OverlayLifecycleTarget.ANIMATING,
            OverlayVisibilityPolicy.target(OverlayVisibility()),
        )
    }

    @Test
    fun `minimized is a size, not a pause`() {
        // Freezing the minimized portrait would freeze a dot the owner is looking at.
        assertTrue(OverlayVisibilityPolicy.shouldAnimate(OverlayVisibility(minimized = true)))
    }

    @Test
    fun `a fully covered overlay does not animate`() {
        assertFalse(OverlayVisibilityPolicy.shouldAnimate(OverlayVisibility(occluded = true)))
    }

    @Test
    fun `a detached view does not animate`() {
        assertFalse(OverlayVisibilityPolicy.shouldAnimate(OverlayVisibility(attached = false)))
    }

    @Test
    fun `destroying wins over everything`() {
        assertEquals(
            OverlayLifecycleTarget.DESTROYED,
            OverlayVisibilityPolicy.target(
                OverlayVisibility(screenOn = true, attached = true, destroying = true),
            ),
        )
    }

    @Test
    fun `a frozen overlay always says why`() {
        // Otherwise it is indistinguishable from a crashed one, and "the overlay is stuck"
        // is the support report this generates.
        val cases = listOf(
            OverlayVisibility(screenOn = false),
            OverlayVisibility(occluded = true),
            OverlayVisibility(attached = false),
            OverlayVisibility(destroying = true),
            OverlayVisibility(minimized = true),
            OverlayVisibility(),
        )
        for (case in cases) {
            val reason = OverlayVisibilityPolicy.describe(case)
            assertTrue(reason.isNotBlank(), "no reason for $case")
            assertFalse(reason.contains("OverlayVisibility"), "raw state leaked: $reason")
        }
        assertEquals("screen is off", OverlayVisibilityPolicy.describe(OverlayVisibility(screenOn = false)))
    }

    @Test
    fun `every combination resolves to exactly one target`() {
        for (screenOn in listOf(true, false)) {
            for (attached in listOf(true, false)) {
                for (minimized in listOf(true, false)) {
                    for (occluded in listOf(true, false)) {
                        for (destroying in listOf(true, false)) {
                            val visibility = OverlayVisibility(
                                screenOn, attached, minimized, occluded, destroying,
                            )
                            val target = OverlayVisibilityPolicy.target(visibility)
                            assertEquals(
                                target == OverlayLifecycleTarget.ANIMATING,
                                OverlayVisibilityPolicy.shouldAnimate(visibility),
                                "shouldAnimate disagrees with target for $visibility",
                            )
                        }
                    }
                }
            }
        }
    }
}
