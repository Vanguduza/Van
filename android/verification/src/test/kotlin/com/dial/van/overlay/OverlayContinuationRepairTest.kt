package com.dial.van.overlay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Pure policy/sequence checks. These do not qualify an Android window or handset. */
class OverlayContinuationRepairTest {
    private class Window : OverlayWindowPort {
        var at = OverlayPlacement(400, 900)
        var dimensions = OverlaySize(184, 184)
        var bounds = OverlayScreen(1080, 2400)
        var motion: OverlaySettleMotion? = null
        var duration = -1
        var edge = DockEdge.NONE
        var dockTicks = 0
        var armTicks = 0
        var dismissed = false
        var targetVisible = false
        var pointerMode = false
        var pointer: OverlayPoint? = null
        var targetBounds: OverlayRect? = null
        val calls = mutableListOf<String>()

        override fun screen() = bounds
        override fun dp(value: Int) = value
        override fun size(presentation: VanOverlayPresentation) = dimensions
        override fun position(): OverlayPlacement {
            calls += "position"
            return at
        }
        override fun moveTo(x: Int, y: Int) { at = OverlayPlacement(x, y) }
        override fun armedFeedback() { armTicks++ }
        override fun showDismissTarget() { targetVisible = true }
        override fun refreshDismissTarget() = Unit
        override fun hideDismissTarget() {
            targetVisible = false
            pointer = null
        }
        override fun dismissHitTest(size: OverlaySize): Boolean =
            if (pointerMode) targetVisible &&
                VanOverlayController.isInsideDismissTarget(pointer, targetBounds)
            else super<OverlayWindowPort>.dismissHitTest(size)
        override fun dismissArmedOnRelease(armed: Boolean): Boolean =
            if (pointerMode) armed && dismissHitTest(dimensions) else armed
        override fun dismissOverlay() { dismissed = true }
        override fun dockedTo(edge: DockEdge, durationMs: Int) {
            this.edge = edge
            duration = durationMs
        }
        override fun dockFeedback() { dockTicks++ }
        override fun settleTo(target: OverlayPlacement, edge: DockEdge, durationMs: Int) {
            dockedTo(edge, durationMs)
            if (durationMs == 0) at = target
            else motion = OverlaySettleMotion(at, target, durationMs, 0L)
        }
        override fun cancelSettle() {
            calls += "cancel"
            motion?.cancel()
            motion = null
        }
        fun frame(now: Long) { motion?.let { at = it.position(now) } }
    }

    private val initial = VanOverlayUiState()

    @Test
    fun `pure coordinate composition preserves nested offsets and subtracts view window origin`() {
        // Illustrative localToWindow output: local (12,18), nested translation (140,220).
        // This arithmetic check does not exercise Compose or qualify native coordinates.
        val nestedPointInWindow = OverlayPoint(152.0, 238.0)
        assertEquals(
            OverlayPoint(542.0, 1008.0),
            VanOverlayController.windowPointToScreen(
                nestedPointInWindow, OverlayPoint(400.0, 800.0), OverlayPoint(10.0, 30.0),
            ),
        )
        assertEquals(
            nestedPointInWindow,
            VanOverlayController.windowPointToScreen(
                nestedPointInWindow, OverlayPoint(10.0, 30.0), OverlayPoint(10.0, 30.0),
            ),
        )
        // A fresh displayed origin changes the mapping without using requested placement.
        assertEquals(
            OverlayPoint(562.0, 998.0),
            VanOverlayController.windowPointToScreen(
                nestedPointInWindow, OverlayPoint(420.0, 790.0), OverlayPoint(10.0, 30.0),
            ),
        )
    }

    @Test
    fun `pure coordinate composition preserves negative and fractional positions`() {
        assertEquals(
            OverlayPoint(-112.5, -25.25),
            VanOverlayController.windowPointToScreen(
                OverlayPoint(-7.5, 4.75), OverlayPoint(-100.0, -20.0), OverlayPoint(5.0, 10.0),
            ),
        )
        assertEquals(
            OverlayPoint(15.0, 20.0),
            VanOverlayController.windowPointToScreen(
                OverlayPoint(-5.0, -10.0), OverlayPoint(10.0, 20.0), OverlayPoint(-10.0, -10.0),
            ),
        )
    }

    @Test
    fun `pure coordinate composition rejects missing nonfinite and overflowing geometry`() {
        val finite = OverlayPoint(10.0, 20.0)
        assertNull(VanOverlayController.windowPointToScreen(null, finite, finite))
        for (bad in listOf(Double.NaN, Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY)) {
            for (invalid in listOf(OverlayPoint(bad, 20.0), OverlayPoint(10.0, bad))) {
                assertNull(VanOverlayController.windowPointToScreen(invalid, finite, finite))
                assertNull(VanOverlayController.windowPointToScreen(finite, invalid, finite))
                assertNull(VanOverlayController.windowPointToScreen(finite, finite, invalid))
            }
        }
        assertNull(VanOverlayController.windowPointToScreen(
            OverlayPoint(Double.MAX_VALUE, 0.0),
            OverlayPoint(Double.MAX_VALUE, 0.0), OverlayPoint(0.0, 0.0),
        ))
        assertNull(VanOverlayController.windowPointToScreen(
            OverlayPoint(0.0, 0.0),
            OverlayPoint(0.0, Double.MAX_VALUE), OverlayPoint(0.0, -Double.MAX_VALUE),
        ))
    }

    @Test
    fun `duplicate obstruction decisions preserve motion and request no reconciliation`() {
        var facts = OverlayVisibility(keyboardOverlapping = false)
        var top = Int.MAX_VALUE
        var reconciliations = 0
        val motion = OverlaySettleMotion(OverlayPlacement(100, 0), OverlayPlacement(0, 0), 100, 0L)
        fun notify(visible: Boolean, nextTop: Int, fullscreen: Boolean) {
            if (OverlayVisibilityPolicy.obstructionChanged(facts, top, visible, nextTop, fullscreen)) {
                reconciliations++
                motion.cancel()
                facts = facts.copy(keyboardVisible = visible, fullscreenAppActive = fullscreen)
                top = OverlayVisibilityPolicy.keyboardTop(visible, nextTop)
            }
        }
        repeat(4) { notify(false, 900 + it, false) }
        assertEquals(0, reconciliations)
        assertEquals(OverlayPlacement(50, 0), motion.positionAtFraction(0.5))
        notify(true, 900, false)
        assertEquals(1, reconciliations)
        assertEquals(OverlayPlacement(50, 0), motion.positionAtFraction(1.0))
        notify(true, 900, false)
        assertEquals(1, reconciliations)
        notify(true, 800, false)
        notify(true, 800, true)
        assertEquals(3, reconciliations)
        notify(true, 800, true)
        assertEquals(3, reconciliations)
        notify(false, 123, true)
        notify(false, 456, true)
        assertEquals(4, reconciliations)
        notify(false, 456, false)
        assertEquals(5, reconciliations)
    }

    @Test
    fun `unknown keyboard geometry cannot invent overlap`() {
        val screen = OverlayScreen(720, 1280)
        for (top in listOf(-1, Int.MIN_VALUE, Int.MAX_VALUE)) {
            assertFalse(OverlayVisibilityPolicy.keyboardOverlaps(
                true, top, OverlayPlacement(0, 0), OverlaySize(356, 420), screen,
            ))
        }
        assertFalse(OverlayVisibilityPolicy.obstructionChanged(
            OverlayVisibility(keyboardVisible = true, keyboardOverlapping = false),
            -1, true, Int.MAX_VALUE, false,
        ))
    }

    @Test
    fun `animator fractions advance monotonically independent of wall clock scaling`() {
        for (duration in listOf(50, 100, 200)) {
            val motion = OverlaySettleMotion(OverlayPlacement(100, 200), OverlayPlacement(0, 400), duration, 0L)
            assertEquals(OverlayPlacement(100, 200), motion.positionAtFraction(-1.0))
            assertEquals(OverlayPlacement(75, 250), motion.positionAtFraction(0.25))
            assertEquals(OverlayPlacement(75, 250), motion.positionAtFraction(0.1))
            assertEquals(OverlayPlacement(50, 300), motion.positionAtFraction(0.5))
            for (bad in listOf(Double.NaN, Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY)) {
                assertEquals(OverlayPlacement(50, 300), motion.positionAtFraction(bad))
            }
            assertEquals(OverlayPlacement(0, 400), motion.positionAtFraction(2.0))
            assertEquals(OverlayPlacement(0, 400), motion.positionAtFraction(0.75))
        }
    }

    @Test
    fun `cancelled fraction motion never advances to target`() {
        val motion = OverlaySettleMotion(OverlayPlacement(100, 200), OverlayPlacement(0, 400), 100, 0L)
        val displayed = motion.positionAtFraction(0.25)
        assertEquals(displayed, motion.cancel())
        assertEquals(displayed, motion.positionAtFraction(1.0))
        assertEquals(displayed, motion.positionAtFraction(Double.NaN))
        assertEquals(displayed, motion.position(1000L))
        val neverStarted = OverlaySettleMotion(OverlayPlacement(100, 200), OverlayPlacement(0, 400), 100, 0L)
        assertEquals(OverlayPlacement(100, 200), neverStarted.cancel())
        assertEquals(OverlayPlacement(100, 200), neverStarted.positionAtFraction(1.0))
    }

    @Test
    fun `pure pointer port dismisses tall clamped board with centre outside target`() {
        val window = Window().apply {
            bounds = OverlayScreen(720, 1280)
            dimensions = OverlaySize(356, 420)
            at = OverlayPlacement(182, 860)
            pointerMode = true
            targetBounds = OverlayRect(304.0, 1144.0, 416.0, 1256.0)
        }
        val controller = OverlayDragController(window)
        var state = controller.begin(initial, 0L)
        window.pointer = OverlayPoint(360.0, 1200.0)
        state = controller.drag(state, 0f, 100f, 10L)
        assertEquals(860, window.at.y)
        assertFalse(VanOverlayController.isInsideDismissTarget(
            window.at.x, window.at.y, 356, 420, window.bounds, window::dp,
        ))
        assertTrue(state.dismissTargetArmed)
        state = controller.drag(state, 0f, 0f, 20L)
        assertEquals(1, window.armTicks)
        assertNull(controller.finish(state))
        assertTrue(window.dismissed)
        assertNull(window.pointer)
        assertFalse(window.targetVisible)
        assertEquals(-1, window.duration)
        assertEquals(0, window.dockTicks)
    }

    @Test
    fun `pure pointer port cannot arm unknown target or nonfinite pointer`() {
        val window = Window().apply {
            pointerMode = true
            pointer = OverlayPoint(540.0, 2320.0)
        }
        val controller = OverlayDragController(window)
        var state = controller.begin(initial, 0L)
        state = controller.drag(state, 0f, 0f, 10L)
        assertFalse(state.dismissTargetArmed)
        window.targetBounds = OverlayRect(484.0, 2264.0, 596.0, 2376.0)
        for (bad in listOf(Double.NaN, Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY)) {
            for (point in listOf(OverlayPoint(bad, 2320.0), OverlayPoint(540.0, bad))) {
                window.pointer = point
                state = controller.drag(state, 0f, 0f, 20L)
                assertFalse(state.dismissTargetArmed)
            }
        }
        assertEquals(0, window.armTicks)
        window.pointer = OverlayPoint(540.0, 2320.0)
        state = controller.drag(state, 0f, 0f, 30L)
        assertTrue(state.dismissTargetArmed)
        window.targetBounds = null
        assertNotNull(controller.finish(state, reducedMotion = true))
        assertFalse(window.dismissed)
        assertNull(window.pointer)
        state = controller.begin(initial, 40L)
        window.pointer = OverlayPoint(540.0, 2320.0)
        controller.cancel(state)
        assertNull(window.pointer)
    }

    @Test
    fun `positive and negative fractions accumulate without per-event truncation`() {
        val window = Window()
        val controller = OverlayDragController(window)
        var state = controller.begin(initial, 0L)
        repeat(4) { state = controller.drag(state, 0.25f, -0.25f, (it + 1).toLong()) }
        assertEquals(OverlayPlacement(401, 899), window.at)
        assertEquals(window.at.x, state.xPx)
        assertEquals(window.at.y, state.yPx)
        state = controller.cancel(state)
        state = controller.begin(state, 10L)
        repeat(4) { state = controller.drag(state, -0.25f, 0.25f, 11L + it) }
        assertEquals(OverlayPlacement(400, 900), window.at)
    }

    @Test
    fun `cancel and new begin clear fractional residuals`() {
        val window = Window()
        val controller = OverlayDragController(window)
        var state = controller.begin(initial, 0L)
        state = controller.drag(state, 0.75f, -0.75f, 1L)
        state = controller.cancel(state)
        state = controller.begin(state, 2L)
        state = controller.drag(state, 0.5f, -0.5f, 3L)
        assertEquals(OverlayPlacement(400, 900), window.at)
        controller.begin(state, 4L)
        controller.drag(state, 0.5f, -0.5f, 5L)
        assertEquals(OverlayPlacement(400, 900), window.at)
    }

    @Test
    fun `nonfinite input cannot move arm or create a fling`() {
        val window = Window()
        val controller = OverlayDragController(window)
        var state = controller.begin(initial, 0L)
        for (bad in listOf(Float.NaN, Float.POSITIVE_INFINITY, Float.NEGATIVE_INFINITY)) {
            state = controller.drag(state, bad, 1f, 1L)
            state = controller.drag(state, 1f, bad, 2L)
        }
        assertEquals(OverlayPlacement(400, 900), window.at)
        assertEquals(0, window.armTicks)
        controller.finish(state)
        assertEquals(DockEdge.NONE, window.edge)
        assertEquals(0, window.dockTicks)
    }

    @Test
    fun `backwards drag clock does not manufacture release velocity`() {
        val window = Window()
        val controller = OverlayDragController(window)
        var state = controller.begin(initial, 1000L)
        state = controller.drag(state, 100f, 0f, 900L)
        assertEquals(500, window.at.x)
        controller.finish(state)
        assertEquals(DockEdge.NONE, window.edge)
        assertEquals(0, window.dockTicks)
    }

    @Test
    fun `rectangular safe bounds clamp axes independently including extreme input`() {
        val screen = OverlayScreen(1000, 1800, 20, 40, 970, 1700)
        assertEquals(
            OverlayPlacement(670, 1000),
            VanOverlayController.clamp(Int.MAX_VALUE, Int.MAX_VALUE, 300, 700, screen),
        )
        assertEquals(
            OverlayPlacement(20, 40),
            VanOverlayController.clamp(Int.MIN_VALUE, Int.MIN_VALUE, 300, 700, screen),
        )
        assertEquals(
            OverlayPlacement(20, 40),
            VanOverlayController.clamp(500, 900, 2000, 3000, screen),
        )
        assertEquals(
            OverlayPlacement(20, 40),
            VanOverlayController.clamp(Double.NaN, Double.POSITIVE_INFINITY, 300, 700, screen),
        )
    }

    @Test
    fun `rectangular dock uses board height for bottom and width for right`() {
        val screen = OverlayScreen(1000, 1800, 20, 40, 970, 1700)
        val (bottom, bottomEdge) = VanOverlayController.settle(300, 990, 300, 700, screen)
        assertEquals(OverlayPlacement(300, 1000), bottom)
        assertEquals(DockEdge.BOTTOM, bottomEdge)
        val (right, rightEdge) = VanOverlayController.settle(660, 500, 300, 700, screen)
        assertEquals(OverlayPlacement(670, 500), right)
        assertEquals(DockEdge.RIGHT, rightEdge)
        val (oversized, _) = VanOverlayController.settle(500, 500, 2000, 3000, screen, 10f, 10f)
        assertEquals(OverlayPlacement(20, 40), oversized)
    }

    @Test
    fun `board fallbacks are rectangular while legacy square API is preserved`() {
        val screen = OverlayScreen(1000, 1800)
        val dp: (Int) -> Int = { it }
        assertEquals(
            OverlaySize(OverlayTheme.COMPACT_WIDTH_DP, OverlayTheme.COMPACT_HEIGHT_DP),
            VanOverlayController.fallbackSizeFor(VanOverlayPresentation.WORKBOARD_COMPACT, dp, screen),
        )
        assertEquals(
            OverlaySize(OverlayTheme.EXPANDED_WIDTH_DP, OverlayTheme.EXPANDED_HEIGHT_DP),
            VanOverlayController.fallbackSizeFor(VanOverlayPresentation.WORKBOARD_EXPANDED, dp, screen),
        )
        val maximized = VanOverlayController.fallbackSizeFor(
            VanOverlayPresentation.WORKBOARD_MAXIMIZED, dp, screen,
        )
        assertTrue(maximized.widthPx <= screen.safeWidth)
        assertTrue(maximized.heightPx <= screen.safeHeight)
        assertEquals(
            OverlayTheme.RESTING_HIT_DP,
            VanOverlayController.touchSizeFor(VanOverlayPresentation.WORKBOARD_EXPANDED, dp),
        )
    }

    @Test
    fun `keyboard presence with clear geometry keeps responding and overlap pauses`() {
        val screen = OverlayScreen(1080, 2400)
        val size = OverlaySize(356, 420)
        fun visibility(y: Int, top: Int = 1400): OverlayVisibility = OverlayVisibility(
            keyboardVisible = true,
            keyboardOverlapping = OverlayVisibilityPolicy.keyboardOverlaps(
                true, top, OverlayPlacement(200, y), size, screen,
            ),
        )
        assertTrue(OverlayVisibilityPolicy.shouldAnimate(visibility(980)))
        assertFalse(OverlayVisibilityPolicy.shouldAnimate(visibility(981)))
        assertEquals("the keyboard is covering VAN", OverlayVisibilityPolicy.describe(visibility(981)))
        assertTrue(OverlayVisibilityPolicy.shouldAnimate(visibility(981, Int.MAX_VALUE)))
        assertFalse(OverlayVisibilityPolicy.shouldAnimate(visibility(980).copy(screenOn = false)))
        assertFalse(OverlayVisibilityPolicy.shouldAnimate(visibility(980).copy(attached = false)))
        assertFalse(OverlayVisibilityPolicy.shouldAnimate(visibility(980).copy(fullscreenAppActive = true)))
        assertEquals(
            OverlayLifecycleTarget.DESTROYED,
            OverlayVisibilityPolicy.target(visibility(980).copy(destroying = true)),
        )
        assertTrue(OverlayVisibilityPolicy.keyboardOverlaps(
            true, 100, OverlayPlacement(0, 0), OverlaySize(500, 2000), screen,
        ))
    }

    @Test
    fun `settle interpolates for its duration and backwards time cannot reverse it`() {
        val motion = OverlaySettleMotion(OverlayPlacement(100, 200), OverlayPlacement(0, 400), 100, 1000L)
        assertEquals(OverlayPlacement(100, 200), motion.position(900L))
        assertEquals(OverlayPlacement(50, 300), motion.position(1050L))
        assertEquals(OverlayPlacement(50, 300), motion.position(1020L))
        assertEquals(OverlayPlacement(0, 400), motion.position(1100L))
        assertEquals(OverlayPlacement(0, 400), motion.position(1200L))
        val immediate = OverlaySettleMotion(OverlayPlacement(100, 200), OverlayPlacement(0, 400), 0, 0L)
        assertEquals(OverlayPlacement(0, 400), immediate.position(0L))
    }

    @Test
    fun `cancelled interpolation retains its displayed position instead of target`() {
        val motion = OverlaySettleMotion(OverlayPlacement(100, 200), OverlayPlacement(0, 400), 100, 0L)
        val displayed = motion.position(25L)
        assertEquals(OverlayPlacement(75, 250), displayed)
        assertEquals(displayed, motion.cancel())
        assertEquals(displayed, motion.position(100L))
    }

    @Test
    fun `release delegates duration without snapping and new drag cancels before position read`() {
        val window = Window().apply { at = OverlayPlacement(40, 900) }
        val controller = OverlayDragController(window)
        val released = controller.finish(initial.copy(dragging = true))
        assertNotNull(released)
        assertTrue(window.duration > 0)
        assertEquals(40, window.at.x)
        assertEquals(40, released.xPx)
        assertEquals(1, window.dockTicks)
        window.frame(window.duration.toLong() / 2)
        val displayed = window.at
        assertTrue(displayed.x in 1..39)
        window.calls.clear()
        val dragging = controller.begin(released, 1000L)
        assertEquals("cancel", window.calls.first())
        assertEquals("position", window.calls[1])
        assertEquals(displayed, window.at)
        assertEquals(displayed.x, dragging.xPx)
        window.frame(10000L)
        assertEquals(displayed, window.at)
        assertNull(window.motion)
    }

    @Test
    fun `reduced motion is immediate while dismiss never settles or ticks`() {
        val window = Window().apply { at = OverlayPlacement(40, 900) }
        val controller = OverlayDragController(window)
        val released = controller.finish(initial, reducedMotion = true)
        assertNotNull(released)
        assertEquals(0, window.duration)
        assertEquals(0, released.xPx)
        assertEquals(1, window.dockTicks)
        assertNull(window.motion)

        val dismissWindow = Window()
        val dismissed = OverlayDragController(dismissWindow).finish(
            initial.copy(dragging = true, dismissTargetVisible = true, dismissTargetArmed = true),
        )
        assertNull(dismissed)
        assertTrue(dismissWindow.dismissed)
        assertFalse(dismissWindow.targetVisible)
        assertEquals(-1, dismissWindow.duration)
        assertEquals(0, dismissWindow.dockTicks)
        assertNull(dismissWindow.motion)
    }

    @Test
    fun `rectangular drag arms once at actual centre and cancellation clears dismiss`() {
        val window = Window().apply {
            dimensions = OverlaySize(300, 100)
            at = OverlayPlacement(390, 2270)
        }
        val controller = OverlayDragController(window)
        var state = controller.begin(initial, 0L)
        state = controller.drag(state, 0f, 0f, 10L)
        assertTrue(state.dismissTargetArmed)
        state = controller.drag(state, 0f, 0f, 20L)
        assertEquals(1, window.armTicks)
        state = controller.cancel(state)
        assertFalse(state.dismissTargetArmed)
        assertFalse(state.dragging)
        assertFalse(state.dismissTargetVisible)
        assertFalse(window.dismissed)
        assertEquals(0, window.dockTicks)
    }
}
