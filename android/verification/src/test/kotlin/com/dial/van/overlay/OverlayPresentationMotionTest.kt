package com.dial.van.overlay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class OverlayPresentationMotionTest {
    @Test fun openingWorkboardProducesOpeningGestureIntent() {
        assertEquals(true, OverlayPresentationMotion.expanding(
            VanOverlayPresentation.FULL_FLOATING, VanOverlayPresentation.WORKBOARD_COMPACT,
        ))
    }
    @Test fun expandingWorkboardProducesOpeningGestureIntent() {
        assertEquals(true, OverlayPresentationMotion.expanding(
            VanOverlayPresentation.WORKBOARD_COMPACT, VanOverlayPresentation.WORKBOARD_MAXIMIZED,
        ))
    }
    @Test fun compactingProducesClosingIntent() {
        assertEquals(false, OverlayPresentationMotion.expanding(
            VanOverlayPresentation.WORKBOARD_MAXIMIZED, VanOverlayPresentation.WORKBOARD_COMPACT,
        ))
    }
    @Test fun closingWorkboardProducesClosingIntent() {
        assertEquals(false, OverlayPresentationMotion.expanding(
            VanOverlayPresentation.WORKBOARD_EXPANDED, VanOverlayPresentation.FULL_FLOATING,
        ))
    }
    @Test fun minimizingAndDockingNeverInventNewWorkboardGestures() {
        for (from in listOf(
            VanOverlayPresentation.MINIMIZED, VanOverlayPresentation.DOCKED, VanOverlayPresentation.FULL_FLOATING,
        )) {
            for (to in listOf(
                VanOverlayPresentation.MINIMIZED, VanOverlayPresentation.DOCKED, VanOverlayPresentation.FULL_FLOATING,
            )) {
                assertNull(OverlayPresentationMotion.expanding(from, to))
            }
        }
    }
    @Test fun presentationUnchangedNeverReplaysGesture() {
        for (presentation in VanOverlayPresentation.entries) {
            assertNull(OverlayPresentationMotion.expanding(presentation, presentation))
        }
    }
}
