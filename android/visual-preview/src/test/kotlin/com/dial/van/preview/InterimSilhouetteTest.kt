package com.dial.van.preview

import com.dial.van.visual.VanAuraOp
import com.dial.van.visual.VanAuraPlanner
import com.dial.van.visual.VanAuraSpecs
import com.dial.van.visual.VanBodyLayout
import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanFlameAura
import com.dial.van.visual.VanPathSeg
import com.dial.van.visual.VanPresentation
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Aura Rev 2 — the aura wraps the silhouette read from the Candidate B art's own alpha, exactly
 * as the app builds it, and that silhouette agrees with the measured landmarks.
 */
class InterimSilhouetteTest {

    @Test
    fun theArtSilhouetteMatchesTheMeasuredFigure() {
        val shape = AwtVanRenderer.interimSilhouette(VanPresentation.COMMAND_CENTRE)!!
        assertTrue("crown ${shape.topV}", kotlin.math.abs(shape.topV - VanBodyLayout.HAIR_CROWN_V) < 0.04f)
        assertTrue("sole ${shape.bottomV}", kotlin.math.abs(shape.bottomV - VanBodyLayout.SOLE_V) < 0.04f)
        assertTrue("the head is not inside", shape.contains(0.49f, 0.20f))
        assertTrue("the orb (held in the art) is not inside", shape.contains(VanBodyLayout.u(67f), VanBodyLayout.v(171f)))
        assertTrue("empty background counted as VAN", !shape.contains(0.90f, 0.10f))
    }

    @Test
    fun flamesWrapTheArtAndNeverCoverIt() {
        val shape = AwtVanRenderer.interimSilhouette(VanPresentation.COMMAND_CENTRE)!!
        val spec = VanAuraSpecs.forState(VanDurableState.WORKING)
        val cx = 300f; val cy = 300f; val r = 150f; val edge = 2 * r
        val rings = VanAuraPlanner.plan(spec, spec, cx, cy, r, silhouette = shape)
            .filterIsInstance<VanAuraOp.Flame>().filter { it.path.size > VanFlameAura.SAMPLES }
        assertTrue(rings.size >= 3)
        for (ring in rings) for (seg in ring.path) {
            val (x, y) = when (seg) {
                is VanPathSeg.QuadTo -> seg.cx to seg.cy
                else -> continue
            }
            assertTrue("a tongue at ($x,$y) covers the art", !shape.contains((x - cx) / edge + 0.5f, (y - cy) / edge + 0.5f))
        }
    }

    @Test
    fun compactFramingZoomsTheSilhouetteWithTheArt() {
        val compact = AwtVanRenderer.interimSilhouette(VanPresentation.COMPACT)!!
        val full = AwtVanRenderer.interimSilhouette(VanPresentation.COMMAND_CENTRE)!!
        val crown = com.dial.van.visual.VanFraming.COMPACT.y(VanBodyLayout.HAIR_CROWN_V)
        assertTrue("compact crown ${compact.topV} is not where the framing puts it ($crown)", kotlin.math.abs(compact.topV - crown) < 0.05f)
        assertTrue("compact must crop the legs off the bottom", compact.bottomV > 0.97f && full.bottomV < 0.97f)
    }
}
