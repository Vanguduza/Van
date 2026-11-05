package com.dial.van.visual

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** The real renderer-independent scene, not merely standalone trajectory arithmetic. */
class VanCompanionOrbSceneTest {
    private fun ops(orbPhase: Float, presentation: VanPresentation = VanPresentation.COMMAND_CENTRE,
                    bodyPhase: Float = 0.22f, reduced: Boolean = false) = VanScene.build(
        VanVisualState(durableState = VanDurableState.IDLE),
        VanSceneFrame(presentation = presentation, phase = bodyPhase,
            orbPhase = orbPhase, reducedMotion = reduced),
    )

    private fun shell(ops: List<VanDrawOp>): VanDrawOp.Circle =
        ops.filterIsInstance<VanDrawOp.Circle>().single {
            (it.color and 0x00FFFFFF) == (VanScene.ORB_BODY.toInt() and 0x00FFFFFF)
        }

    @Test fun orbActuallyChangesSidesInAllThreeRealRenderFramings() {
        for (presentation in VanPresentation.entries) {
            val l = shell(ops(0f, presentation))
            val r = shell(ops(0.55f, presentation))
            assertTrue(l.cx < 0.45f, "left in $presentation")
            assertTrue(r.cx > 0.55f, "right in $presentation")
            assertEquals(l.cy, r.cy, 0.02f)
        }
    }

    @Test fun changingTheBodyPhaseDoesNotChangeCompanionPosition() {
        val first = shell(ops(orbPhase = 0.55f, bodyPhase = 0f))
        val second = shell(ops(orbPhase = 0.55f, bodyPhase = 0.85f))
        assertEquals(first.cx, second.cx, 0.00001f)
        assertEquals(first.cy, second.cy, 0.00001f)
    }

    @Test fun theOrbCrossesBehindTheActualCharacterRatherThanOverTheFace() {
        val transitionOps = ops(0.30f)
        val orbIndex = transitionOps.indexOf(shell(transitionOps))
        val hairIndex = transitionOps.indexOfFirst {
            (it.color and 0x00FFFFFF) == (VanScene.HAIR.toInt() and 0x00FFFFFF)
        }
        assertTrue(orbIndex in 0 until hairIndex, "flying orb must be behind hair/face")
        val restingOps = ops(0.55f)
        val settledOrbIndex = restingOps.indexOf(shell(restingOps))
        val settledHairIndex = restingOps.indexOfFirst {
            (it.color and 0x00FFFFFF) == (VanScene.HAIR.toInt() and 0x00FFFFFF)
        }
        assertTrue(settledHairIndex in 0 until settledOrbIndex, "resting orb must be independently visible")
    }

    @Test fun independentOpticalSpinIsPresentWithoutAnOwnerAction() {
        val op = ops(0.25f)
        val spinArc = op.filterIsInstance<VanDrawOp.Arc>().any {
            it.startDegrees in 179.9f..180.1f && it.sweepDegrees == 62f
        }
        assertTrue(spinArc, "rotating companion rim must remain visible even at idle")
    }

    @Test fun reducedMotionParksOrbOnOriginalSideWithoutOpticalSpin() {
        val a = ops(0.01f, reduced = true)
        val b = ops(0.55f, reduced = true)
        assertEquals(shell(a).cx, shell(b).cx, 0.00001f)
        assertEquals(shell(a).cy, shell(b).cy, 0.00001f)
        assertTrue(a.none { it is VanDrawOp.Arc && it.sweepDegrees == 62f })
    }

    @Test fun movingOrbRetainsTheCanonicalOpaqueShellAndCyanBarEyes() {
        for (p in listOf(0f, 0.30f, 0.55f, 0.80f, 0.95f)) {
            val drawOps = ops(p)
            val black = shell(drawOps)
            assertEquals(255, VanColors.alpha(black.color))
            val eyes = drawOps.filterIsInstance<VanDrawOp.RoundRect>().filter {
                (it.color and 0x00FFFFFF) == (VanScene.ORB_EYE.toInt() and 0x00FFFFFF)
                && it.halfH > it.halfW
                && kotlin.math.abs(it.cx - black.cx) < black.r
                && kotlin.math.abs(it.cy - black.cy) < black.r
            }
            assertEquals(2, eyes.size, "orb must retain its two cyan eyes at phase $p")
        }
    }
}
