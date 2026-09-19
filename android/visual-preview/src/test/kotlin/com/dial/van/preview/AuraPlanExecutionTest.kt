package com.dial.van.preview

import com.dial.van.visual.VanAuraOp
import com.dial.van.visual.VanAuraPlanner
import com.dial.van.visual.VanAuraSpecs
import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanEffectBudget
import java.awt.image.BufferedImage
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * P1-VIS-001 — the Java2D painter draws the plan, including the layer it used to omit.
 *
 * The complementary tests in `android/verification` assert that the *plan* contains
 * electrical branches. These assert that the AWT executor puts them on the canvas, which is
 * the half that was actually missing: the painter was a hand-written reimplementation of
 * `VanAura.kt` and simply had no code for `geometry.electricalBranches`, so every committed
 * piece of visual evidence was a picture of VAN without them.
 */
class AuraPlanExecutionTest {

    private fun canvas(): Pair<BufferedImage, java.awt.Graphics2D> {
        val image = BufferedImage(480, 480, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        return image to g
    }

    /** A phase at which the urgent field has produced at least one electrical branch. */
    private fun branchPhase(): Float {
        for (index in 0 until 400) {
            val phase = index / 400f
            val hasBranch = VanAuraPlanner.plan(
                spec = VanAuraSpecs.forState(VanDurableState.URGENT),
                semanticSpec = VanAuraSpecs.forState(VanDurableState.URGENT),
                centerX = 240f, centerY = 240f, radius = 200f, phase = phase,
            ).filterIsInstance<VanAuraOp.Polyline>().any { it.whiteCoreWidth != null }
            if (hasBranch) return phase
        }
        throw AssertionError("no electrical branch in a full phase sweep")
    }

    @Test
    fun electricalBranchesReachTheCanvas() {
        // The layer the painter had no code for at all. Asserted by drawing the same plan
        // twice — once whole, once with the electrical ops removed — and requiring the two
        // to differ. A "look for white pixels" check would pass on a painter that drew a
        // highlight somewhere else; this can only pass if these ops changed the canvas.
        val phase = branchPhase()
        val spec = VanAuraSpecs.forState(VanDurableState.URGENT)
        val ops = VanAuraPlanner.plan(
            spec = spec, semanticSpec = spec,
            centerX = 240f, centerY = 240f, radius = 200f, phase = phase,
        )
        val withoutBranches = ops.filterNot {
            it is VanAuraOp.Polyline && it.whiteCoreWidth != null
        }
        assertTrue("the plan had no electrical ops to remove", withoutBranches.size < ops.size)

        val (whole, g1) = canvas()
        GlassPainter.drawAuraOps(g1, ops)
        g1.dispose()
        val (partial, g2) = canvas()
        GlassPainter.drawAuraOps(g2, withoutBranches)
        g2.dispose()

        var differing = 0
        for (y in 0 until whole.height) {
            for (x in 0 until whole.width) {
                if (whole.getRGB(x, y) != partial.getRGB(x, y)) differing++
            }
        }
        assertTrue(
            "removing the electrical ops changed $differing pixels: the painter is not drawing them",
            differing > 200,
        )
    }

    @Test
    fun theAuraDrawsNothingWhenThePlanIsEmpty() {
        val (image, g) = canvas()
        GlassPainter.drawAura(
            g,
            VanAuraSpecs.forState(VanDurableState.IDLE),
            240f, 240f, 0.5f,   // a body too small to draw
        )
        g.dispose()
        var painted = 0
        for (y in 0 until image.height) {
            for (x in 0 until image.width) if ((image.getRGB(x, y) ushr 24) and 0xFF > 0) painted++
        }
        assertEquals("a plan with no ops still painted something", 0, painted)
    }

    @Test
    fun thePainterHoldsNoAuraConstantsOfItsOwn() {
        // The property that makes divergence impossible rather than merely fixed: every
        // number the painter draws with came out of the plan. Asserted behaviourally — the
        // same plan, executed twice, produces the same pixels, and a plan whose ops are
        // changed produces different ones.
        val phase = branchPhase()
        val spec = VanAuraSpecs.forState(VanDurableState.URGENT)
        val ops = VanAuraPlanner.plan(
            spec = spec, semanticSpec = spec,
            centerX = 240f, centerY = 240f, radius = 200f, phase = phase,
        )
        val (first, g1) = canvas()
        GlassPainter.drawAuraOps(g1, ops)
        g1.dispose()
        val (second, g2) = canvas()
        GlassPainter.drawAuraOps(g2, ops)
        g2.dispose()
        assertTrue("the same plan produced different pixels", sameImage(first, second))

        val dimmed = ops.map { op ->
            when (op) {
                is VanAuraOp.Polyline -> op.copy(alpha = op.alpha * 0.2f)
                is VanAuraOp.Radial -> op.copy(alpha = op.alpha * 0.2f)
                is VanAuraOp.Dot -> op.copy(alpha = op.alpha * 0.2f)
                is VanAuraOp.Quad -> op.copy(alpha = op.alpha * 0.2f)
            }
        }
        val (third, g3) = canvas()
        GlassPainter.drawAuraOps(g3, dimmed)
        g3.dispose()
        assertTrue(
            "changing the plan changed nothing: the painter is not driven by it",
            !sameImage(first, third),
        )
    }

    private fun sameImage(a: BufferedImage, b: BufferedImage): Boolean {
        if (a.width != b.width || a.height != b.height) return false
        for (y in 0 until a.height) {
            for (x in 0 until a.width) if (a.getRGB(x, y) != b.getRGB(x, y)) return false
        }
        return true
    }
}
