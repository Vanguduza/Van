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
        var dockTicks = 0
        var dismissed = false
        var docked: DockEdge? = null
        var dockDurationMs: Int? = null

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
        override fun dockedTo(edge: DockEdge, durationMs: Int) {
            docked = edge
            dockDurationMs = durationMs
        }
        override fun dockFeedback() { dockTicks += 1 }
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
    fun `picking VAN up closes an open board but leaves minimized and docked VAN alone`() {
        // The board opens beside VAN; dragged along with him it would be pushed off screen.
        for (board in listOf(
            VanOverlayPresentation.WORKBOARD_COMPACT,
            VanOverlayPresentation.WORKBOARD_EXPANDED,
            VanOverlayPresentation.WORKBOARD_MAXIMIZED,
        )) {
            val state = OverlayDragController(FakeWindow()).begin(resting.copy(presentation = board))
            assertEquals(VanOverlayPresentation.FULL_FLOATING, state.presentation, board.name)
        }
        for (own in listOf(VanOverlayPresentation.MINIMIZED, VanOverlayPresentation.DOCKED)) {
            val state = OverlayDragController(FakeWindow()).begin(resting.copy(presentation = own))
            assertEquals(own, state.presentation, own.name)
        }
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

    // ---------------------------------------------------------------- item 3: velocity/fling

    @Test
    fun `a slow release mid-screen docks nowhere and ticks nothing`() {
        // No position-only reason to dock (touch size 184dp*3=552px, screen 1080px wide, so
        // safely mid-screen is roughly 48..480; 264 is nowhere near either edge threshold)
        // and no speed to read as a flick: VAN stays exactly where the owner left it.
        val window = FakeWindow(x = 264, y = 1200)
        val controller = OverlayDragController(window)
        controller.begin(resting, nowMs = 0L)
        controller.drag(resting, dx = 1, dy = 0, nowMs = 500L)
        val after = controller.finish(resting.copy(xPx = window.x, yPx = window.y))
        assertEquals(DockEdge.NONE, window.docked)
        assertEquals(0, window.dockTicks, "ticked on a release that did not dock")
        assertNotNull(after)
    }

    @Test
    fun `a fast flick toward an edge docks there even released mid-screen`() {
        // Starts and (after the drag) stays mid-screen — see the note above on why 264 is
        // nowhere near either edge threshold — so only the release velocity, not position,
        // can explain docking LEFT.
        val window = FakeWindow(x = 264, y = 1200)
        val controller = OverlayDragController(window)
        controller.begin(resting, nowMs = 0L)
        // A leftward delta over a short time, well past the flick threshold, that still
        // lands the window mid-screen (164) rather than clamped against the edge.
        controller.drag(resting, dx = -100, dy = 0, nowMs = 20L)
        assertTrue(window.x in 49..479, "test setup drifted onto an edge threshold: ${window.x}")
        val after = controller.finish(resting.copy(xPx = window.x, yPx = window.y))
        assertEquals(DockEdge.LEFT, window.docked)
        assertEquals(1, window.dockTicks, "a real dock did not tick")
        assertNotNull(after)
        assertEquals(0, after.xPx)
    }

    @Test
    fun `docking ticks but dismissing never does`() {
        val window = FakeWindow()
        OverlayDragController(window).finish(resting.copy(dismissTargetArmed = true))
        assertEquals(0, window.dockTicks, "a dismiss should never feel like a dock")
    }

    @Test
    fun `reduced motion still reports a duration of zero for a fast flick`() {
        val window = FakeWindow(x = 264, y = 1200)
        val controller = OverlayDragController(window)
        controller.begin(resting, nowMs = 0L)
        controller.drag(resting, dx = -100, dy = 0, nowMs = 20L)
        controller.finish(resting.copy(xPx = window.x, yPx = window.y), reducedMotion = true)
        assertEquals(0, window.dockDurationMs)
    }

    @Test
    fun `an ordinary dock still reports a positive duration`() {
        val window = FakeWindow(x = 4, y = 900)
        val controller = OverlayDragController(window)
        controller.finish(resting.copy(dragging = true))
        assertNotNull(window.dockDurationMs)
        assertTrue(window.dockDurationMs!! > 0)
    }

    @Test
    fun `velocity resets on a new drag so a stale flick cannot dock the next one`() {
        val window = FakeWindow(x = 264, y = 1200)
        val controller = OverlayDragController(window)
        controller.begin(resting, nowMs = 0L)
        controller.drag(resting, dx = -100, dy = 0, nowMs = 20L)
        controller.cancel(resting)

        // A fresh, slow drag mid-screen — the earlier flick must not still count.
        window.x = 264
        window.y = 1200
        controller.begin(resting, nowMs = 1000L)
        controller.drag(resting, dx = 1, dy = 0, nowMs = 1500L)
        controller.finish(resting.copy(xPx = window.x, yPx = window.y))
        assertEquals(DockEdge.NONE, window.docked)
    }
}
