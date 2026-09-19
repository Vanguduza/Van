package com.dial.van.overlay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * P3-AND-009 / Rev 3.0 §41.
 *
 * This arithmetic was inside a 1,096-line Service, in a file that imports `WindowManager`,
 * so none of it could be executed anywhere. Every case below is one the owner experiences
 * as "VAN went off the edge of the screen and I couldn't get it back".
 */
class VanOverlayControllerTest {

    private val phone = OverlayScreen(widthPx = 1080, heightPx = 2400)

    /** 3x density, the common phone. */
    private val dp: (Int) -> Int = { it * 3 }

    @Test
    fun `an avatar cannot be dragged off any edge`() {
        val size = 144
        for ((x, y) in listOf(-500 to -500, 5000 to 5000, -1 to 1200, 1200 to -1)) {
            val placed = VanOverlayController.clamp(x, y, size, phone)
            assertTrue(placed.x in 0..(phone.widthPx - size), "x=${placed.x}")
            assertTrue(placed.y in 0..(phone.heightPx - size), "y=${placed.y}")
        }
    }

    @Test
    fun `a screen smaller than the avatar still produces a reachable position`() {
        // Not hypothetical: a foldable's cover display, or a split-screen window.
        val tiny = OverlayScreen(widthPx = 100, heightPx = 100)
        val placed = VanOverlayController.clamp(50, 50, touchSize = 400, screen = tiny)
        assertEquals(0, placed.x)
        assertEquals(0, placed.y)
    }

    @Test
    fun `each presentation is measured by its own touch target`() {
        val minimized = VanOverlayController.touchSizeFor(VanOverlayPresentation.MINIMIZED, dp)
        val docked = VanOverlayController.touchSizeFor(VanOverlayPresentation.DOCKED, dp)
        val resting = VanOverlayController.touchSizeFor(VanOverlayPresentation.FULL_FLOATING, dp)
        assertEquals(dp(OverlayTheme.MINIMIZED_TOUCH_DP), minimized)
        assertEquals(dp(OverlayTheme.DOCK_WIDTH_DP), docked)
        assertEquals(dp(OverlayTheme.RESTING_HIT_DP), resting)
        // Every other presentation is a workboard, which is dragged by its resting hit box.
        for (presentation in VanOverlayPresentation.entries) {
            if (presentation == VanOverlayPresentation.MINIMIZED) continue
            if (presentation == VanOverlayPresentation.DOCKED) continue
            assertEquals(resting, VanOverlayController.touchSizeFor(presentation, dp), presentation.name)
        }
    }

    @Test
    fun `the dismiss target arms on the avatar's centre, at every size`() {
        // Corner-based hit testing makes the target feel like it moves when VAN changes
        // size, because the corner of a 48dp avatar and of a 96dp one are in different
        // places relative to the finger.
        val hit = dp(OverlayTheme.DISMISS_HIT_DP)
        val bottom = dp(OverlayTheme.DISMISS_BOTTOM_MARGIN_DP)
        val targetX = phone.widthPx / 2
        val targetY = phone.heightPx - bottom - hit / 2
        for (size in listOf(dp(48), dp(96), dp(144))) {
            val onTarget = VanOverlayController.isInsideDismissTarget(
                x = targetX - size / 2, y = targetY - size / 2, avatarSize = size, screen = phone, dp = dp,
            )
            assertTrue(onTarget, "size=$size does not arm over the target")
        }
    }

    @Test
    fun `the dismiss target does not arm from across the screen`() {
        for ((x, y) in listOf(0 to 0, 900 to 100, 0 to 2200, 1000 to 2300)) {
            assertFalse(
                VanOverlayController.isInsideDismissTarget(x, y, dp(96), phone, dp),
                "($x,$y) armed the dismiss target",
            )
        }
    }

    @Test
    fun `a drag that ends near an edge snaps to it and reports the same edge`() {
        // The service called snap and detectEdge as two consecutive five-argument calls.
        // One argument-order slip and the avatar snaps to one edge and reports the other,
        // which the owner sees as a dock that renders on the wrong side.
        val size = dp(48)
        val cases = mapOf(
            (10 to 800) to DockEdge.LEFT,
            (phone.widthPx - size - 10 to 800) to DockEdge.RIGHT,
            (500 to 10) to DockEdge.TOP,
            (500 to phone.heightPx - size - 10) to DockEdge.BOTTOM,
        )
        for ((position, expected) in cases) {
            val (placed, edge) = VanOverlayController.settle(position.first, position.second, size, phone)
            assertEquals(expected, edge, "from $position")
            assertEquals(
                EdgeDocking.detectEdge(placed.x, placed.y, size, phone.widthPx, phone.heightPx),
                edge,
                "the snapped position and the reported edge disagree from $position",
            )
        }
    }

    @Test
    fun `a drag that ends in open space docks to nothing`() {
        val (placed, edge) = VanOverlayController.settle(500, 1200, dp(48), phone)
        assertEquals(DockEdge.NONE, edge)
        assertEquals(500, placed.x)
        assertEquals(1200, placed.y)
    }

    @Test
    fun `settling never puts the avatar outside the screen`() {
        val size = dp(48)
        for (x in listOf(-200, 0, 540, phone.widthPx, phone.widthPx + 200)) {
            for (y in listOf(-200, 0, 1200, phone.heightPx, phone.heightPx + 200)) {
                val (placed, _) = VanOverlayController.settle(x.coerceAtLeast(0), y.coerceAtLeast(0), size, phone)
                assertTrue(placed.x >= 0 && placed.y >= 0, "($x,$y) -> $placed")
                assertTrue(placed.x + size <= phone.widthPx, "($x,$y) -> $placed")
                assertTrue(placed.y + size <= phone.heightPx, "($x,$y) -> $placed")
            }
        }
    }
}
