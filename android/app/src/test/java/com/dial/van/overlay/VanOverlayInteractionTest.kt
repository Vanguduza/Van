package com.dial.van.overlay

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VanOverlayInteractionTest {
    @Test
    fun singleTapOpensAndClosesWorkboard() {
        val full = VanOverlayUiState()
        val compact = VanOverlayReducer.onVanTapped(full)
        assertEquals(VanOverlayPresentation.WORKBOARD_COMPACT, compact.presentation)
        assertEquals(VanOverlayPresentation.FULL_FLOATING, VanOverlayReducer.onVanTapped(compact).presentation)

        val expanded = compact.copy(presentation = VanOverlayPresentation.WORKBOARD_EXPANDED)
        assertEquals(VanOverlayPresentation.FULL_FLOATING, VanOverlayReducer.onVanTapped(expanded).presentation)

        val maximized = compact.copy(presentation = VanOverlayPresentation.WORKBOARD_MAXIMIZED)
        assertEquals(VanOverlayPresentation.FULL_FLOATING, VanOverlayReducer.onVanTapped(maximized).presentation)
    }

    @Test
    fun doubleTapNavigatesWithoutMutatingBoardPresentation() {
        val state = VanOverlayUiState(presentation = VanOverlayPresentation.WORKBOARD_EXPANDED)
        val reduction = VanOverlayReducer.onGesture(state, VanGestureEvent.DoubleTap)
        assertEquals(VanOverlayPresentation.WORKBOARD_EXPANDED, reduction.state.presentation)
        assertEquals(VanOverlayEffect.OpenCommandCentre, reduction.effect)
    }

    @Test
    fun longPressOnlyShowsQuickControls() {
        val state = VanOverlayUiState()
        val reduction = VanOverlayReducer.onGesture(state, VanGestureEvent.LongPress)
        assertEquals(VanOverlayPresentation.FULL_FLOATING, reduction.state.presentation)
        assertEquals(VanQuickControlsState.VISIBLE, reduction.state.quickControls)
        assertEquals(null, reduction.effect)
    }

    @Test
    fun minimizedTapRestoresFullVan() {
        val minimized = VanOverlayReducer.minimize(VanOverlayUiState())
        assertEquals(VanOverlayPresentation.MINIMIZED, minimized.presentation)
        assertEquals(VanOverlayPresentation.FULL_FLOATING, VanOverlayReducer.onVanTapped(minimized).presentation)
    }

    @Test
    fun dragShowsDismissTargetAndArmedReleaseCloses() {
        val started = VanOverlayReducer.onGesture(
            VanOverlayUiState(),
            VanGestureEvent.DragStart(10f, 10f),
        ).state
        assertTrue(started.dragging)
        assertTrue(started.dismissTargetVisible)

        val armed = VanOverlayReducer.armDismiss(started, true)
        val released = VanOverlayReducer.onGesture(armed, VanGestureEvent.DragEnd(10f, 100f))
        assertEquals(VanOverlayEffect.CloseOverlay, released.effect)
        assertFalse(released.state.dragging)
        assertFalse(released.state.dismissTargetVisible)
    }
}
