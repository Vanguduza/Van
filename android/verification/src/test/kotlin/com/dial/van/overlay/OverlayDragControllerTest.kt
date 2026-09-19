package com.dial.van.overlay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * P3-AND-009 / Rev 3.0 s41 — dragging VAN around, as a sequence rather than as four private
 * methods in a Service.
 *
 * The geometry is `VanOverlayControllerTest`'s. This is the ordering: when the dismiss
 * target appears, when the haptic fires, and whether a lift closes the overlay or docks it.
 * Every one of those was unobservable while it lived beside a `WindowManager`.
 */
class OverlayDragControllerTest {

    private class FakeWindow(
        private val screen: OverlayScreen = OverlayScreen(1080, 2400),
        var x: Int = 400,
        var y: Int = 900,
    ) : OverlayWindowPort {
        val log = mutableListOf<String>()
        var haptics = 0
        var dismissed = false
        var docked: DockEdge? = null

        override fun screen() = screen
        override fun dp(value: Int) = value * 3
        override fun position() = OverlayPlacement(x, y)
        override fun moveTo(x: Int, y: Int) {
            this.x = x
            this.y = y
            log += "move"
        }
        override fun armedFeedback() {
            haptics += 1
        }
        override fun showDismissTarget() { log += "show" }
        override fun refreshDismissTarget() { log += "refresh" }
        override fun hideDismissTarget() { log += "hide" }
        override fun dismissOverlay() { dismissed = true }
        override fun dockedTo(edge: DockEdge) { docked = edge }
    }

    private val resting = VanOverlayUiState(presentation = VanOverlayPresentation.FULL_FLOATING)

    @Test
    fun `starting a drag puts the dismiss target up and the menu away`() {
        val window = FakeWindow()
        val state = OverlayDragController(window).begin(
            resting.copy(quickControls = VanQuickControlsState.VISIBLE),
        )
        assertTrue(state.dragging)
        assertTrue(state.dismissTargetVisible)
        // A menu that follows the finger is a menu the owner cannot hit.
        assertEquals(VanQuickControlsState.HIDDEN, state.quickControls)
        assertTrue(window.log.contains("show"))
    }

    @Test
    fun `a drag moves the window and reports where it ended up`() {
        val window = FakeWindow(x = 400, y = 900)
        val state = OverlayDragController(window).drag(resting, dx = 30, dy = -50)
        assertEquals(430, window.x)
        assertEquals(850, window.y)
        assertEquals(430, state.xPx)
        assertEquals(850, state.yPx)
    }

    @Test
    fun `a drag cannot walk VAN off the screen`() {
        val window = FakeWindow(x = 0, y = 0)
        val controller = OverlayDragController(window)
        controller.drag(resting, dx = -5000, dy = -5000)
        assertTrue(window.x >= 0 && window.y >= 0, "${window.x},${window.y}")
        controller.drag(resting, dx = 9000, dy = 9000)
        val touch = VanOverlayController.touchSizeFor(resting.presentation, window::dp)
        assertTrue(window.x + touch <= 1080, "${window.x}")
        assertTrue(window.y + touch <= 2400, "${window.y}")
    }

    @Test
    fun `the haptic fires on arming, once, not on every frame`() {
        // A tick per frame while the finger hovers the target is a phone buzzing
        // continuously, which owners read as a fault rather than as feedback.
        val window = FakeWindow(x = 400, y = 900)
        val controller = OverlayDragController(window)
        val touch = VanOverlayController.touchSizeFor(resting.presentation, window::dp)
        val targetX = 1080 / 2 - touch / 2
        val targetY = 2400 - window.dp(OverlayTheme.DISMISS_BOTTOM_MARGIN_DP) -
            window.dp(OverlayTheme.DISMISS_HIT_DP) / 2 - touch / 2

        var state = controller.drag(resting, targetX - window.x, targetY - window.y)
        assertTrue(state.dismissTargetArmed, "never armed over the target")
        assertEquals(1, window.haptics)

        repeat(5) { state = controller.drag(state, 0, 0) }
        assertTrue(state.dismissTargetArmed)
        assertEquals(1, window.haptics, "buzzed on every frame")
    }

    @Test
    fun `letting go over the target closes the overlay and renders nothing after`() {
        val window = FakeWindow()
        val after = OverlayDragController(window).finish(resting.copy(dismissTargetArmed = true))
        assertTrue(window.dismissed)
        // Null, not a copy(): an update to a window that is going away.
        assertNull(after)
        assertTrue(window.log.contains("hide"))
    }

    @Test
    fun `letting go anywhere else docks and clears the drag`() {
        val window = FakeWindow(x = 4, y = 900)
        val after = OverlayDragController(window).finish(resting.copy(dragging = true))
        assertNotNull(after)
        assertFalse(after.dragging)
        assertFalse(after.dismissTargetVisible)
        assertFalse(after.dismissTargetArmed)
        assertFalse(window.dismissed)
        assertEquals(DockEdge.LEFT, window.docked)
        assertEquals(window.x, after.xPx)
        assertEquals(window.y, after.yPx)
    }

    @Test
    fun `a cancelled drag never leaves the overlay armed to close`() {
        // Otherwise the owner's next, unrelated touch closes VAN.
        val window = FakeWindow()
        val after = OverlayDragController(window).cancel(
            resting.copy(dragging = true, dismissTargetVisible = true, dismissTargetArmed = true),
        )
        assertFalse(after.dismissTargetArmed)
        assertFalse(after.dragging)
        assertFalse(after.dismissTargetVisible)
        assertFalse(window.dismissed)
        assertTrue(window.log.contains("hide"))
    }

    @Test
    fun `the dismiss target is taken down however the drag ends`() {
        for (end in listOf<(OverlayDragController, VanOverlayUiState) -> Unit>(
            { c, s -> c.finish(s) },
            { c, s -> c.cancel(s) },
        )) {
            val window = FakeWindow()
            end(OverlayDragController(window), resting.copy(dragging = true))
            assertTrue(window.log.contains("hide"), "$window left the dismiss target up")
        }
    }
}
