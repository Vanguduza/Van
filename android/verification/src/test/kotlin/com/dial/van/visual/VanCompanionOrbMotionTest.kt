package com.dial.van.visual

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class VanCompanionOrbMotionTest {
    private fun at(p: Float, reduced: Boolean = false) = VanCompanionOrbMotion.sample(
        phase = p, homeX = 0.18f, homeY = 0.50f, radius = 0.13f, reducedMotion = reduced,
    )

    @Test fun orbStartsAtApprovedViewerLeftRest() {
        val pose = at(0f)
        assertFalse(pose.onRight)
        assertFalse(pose.behindVan)
        assertEquals(0.18f, pose.centerX, 0.00001f)
    }

    @Test fun orbTravelsToVansOtherSideWithoutAnyTaskOrAttentionCue() {
        val pose = at(0.55f)
        assertTrue(pose.onRight)
        assertTrue(pose.centerX > 0.75f)
        assertFalse(pose.behindVan)
    }

    @Test fun companionReturnsToOriginalSideAtEndOfItsOwnCycle() {
        val pose = at(0.95f)
        assertFalse(pose.onRight)
        assertEquals(at(0f).centerX, pose.centerX, 0.00001f)
    }

    @Test fun bothSideTransfersGoBehindVanInsteadOfCrossingHisFace() {
        for (p in listOf(0.23f, 0.30f, 0.38f, 0.72f, 0.80f, 0.88f)) {
            assertTrue(at(p).behindVan, "phase=$p")
        }
        assertFalse(at(0.10f).behindVan)
        assertFalse(at(0.55f).behindVan)
    }

    @Test fun archingFlightGoesAboveItsRestingHeightThenReturns() {
        assertTrue(at(0.30f).centerY < at(0.0f).centerY - 0.17f)
        assertTrue(at(0.80f).centerY < at(0.55f).centerY - 0.17f)
    }

    @Test fun angularRimSpinIsIndependentAndContinuousAcrossLoop() {
        assertEquals(0f, at(0f).spinDegrees)
        assertEquals(180f, at(0.25f).spinDegrees, 0.01f)
        assertEquals(at(0f).spinDegrees, at(1f).spinDegrees, 0.01f)
    }

    @Test fun sideChangeBoundariesHaveNoVisiblePositionSnap() {
        for (edge in listOf(0.20f, 0.41f, 0.69f, 0.90f, 1.0f)) {
            val before = at(edge - 0.00001f)
            val after = at(edge + 0.00001f)
            assertTrue(abs(before.centerX - after.centerX) < 0.002f, "x jump at $edge")
            assertTrue(abs(before.centerY - after.centerY) < 0.002f, "y jump at $edge")
        }
    }

    @Test fun returningAfterCycleDoesNotDisplaceOrbOrChangeAppearance() {
        val a = at(0f)
        val b = at(1f)
        assertEquals(a.centerX, b.centerX, 0.00001f)
        assertEquals(a.centerY, b.centerY, 0.00001f)
        assertEquals(a.onRight, b.onRight)
    }

    @Test fun reducedMotionKeepsTheOrbNearApprovedRestIndependentOfPhase() {
        val rest = at(0f, reduced = true)
        for (p in listOf(0.01f, 0.33f, 0.55f, 0.88f, 1f)) {
            assertEquals(rest, at(p, reduced = true))
        }
    }

    @Test fun allPresentationSizedRadiiRemainBoundedOnTheCanvas() {
        for (radius in listOf(0.025f, 0.08f, 0.15f, 0.24f)) {
            for (p in 0..100) {
                val s = VanCompanionOrbMotion.sample(p / 100f, 0.15f, 0.5f, radius)
                assertTrue(s.centerX in 0.0f..1.0f)
                assertTrue(s.centerY in 0.0f..1.0f)
                assertTrue(s.centerX.isFinite() && s.centerY.isFinite())
            }
        }
    }

    @Test fun corruptPhaseAndGeometryFailToSafeFiniteCoordinates() {
        for (p in listOf(Float.NaN, Float.POSITIVE_INFINITY, Float.NEGATIVE_INFINITY)) {
            val v = VanCompanionOrbMotion.sample(p, Float.NaN, Float.NaN, Float.NaN)
            assertTrue(v.centerX.isFinite() && v.centerY.isFinite() && v.spinDegrees.isFinite())
            assertFalse(v.behindVan)
        }
    }

    @Test fun sideMotionIsNotComputedFromBodyStateOrGestureCode() {
        // The public API deliberately takes no VanDurableState or VanFiniteAction.
        val a = VanCompanionOrbMotion.sample(0.50f, 0.18f, 0.50f, 0.13f)
        val b = VanCompanionOrbMotion.sample(0.50f, 0.18f, 0.50f, 0.13f)
        assertEquals(a, b)
        assertTrue(a.onRight)
    }
}
