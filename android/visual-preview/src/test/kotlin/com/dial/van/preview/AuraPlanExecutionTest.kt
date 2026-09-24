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
 * P1-VIS-001 — the Java2D painter draws the plan, and nothing but the plan.
 *
 * The complementary tests in `android/verification` assert what the *plan* contains (since
 * CF-D-06, the flame envelope and its embers). These assert that the AWT executor puts it on
 * the canvas: the painter was once a hand-written reimplementation of `VanAura.kt` that
 * silently dropped a whole layer, so every committed piece of evidence showed a VAN the
 * app did not draw.
 */
class AuraPlanExecutionTest {

    private fun canvas(): Pair<BufferedImage, java.awt.Graphics2D> {
        val image = BufferedImage(480, 480, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        return image to g
    }

    private val phase = 0.18f

    @Test
    fun flameLayersReachTheCanvas() {
        // Drawn twice, once whole and once without its flame ops, and the two must differ.
        // A "look for coloured pixels" check would pass on a painter that drew the haze
        // somewhere else; this can only pass if the flame ops changed the canvas.
        val spec = VanAuraSpecs.forState(VanDurableState.WORKING)
        val ops = VanAuraPlanner.plan(
            spec = spec, semanticSpec = spec,
            centerX = 240f, centerY = 240f, radius = 200f, phase = phase,
        )
        val withoutFlames = ops.filterNot { it is VanAuraOp.Flame }
        assertTrue("the plan had no flame ops to remove", withoutFlames.size < ops.size)

        val (whole, g1) = canvas()
        GlassPainter.drawAuraOps(g1, ops)
        g1.dispose()
        val (partial, g2) = canvas()
        GlassPainter.drawAuraOps(g2, withoutFlames)
        g2.dispose()

        var differing = 0
        for (y in 0 until whole.height) {
            for (x in 0 until whole.width) {
                if (whole.getRGB(x, y) != partial.getRGB(x, y)) differing++
            }
        }
        assertTrue(
            "removing the flame ops changed $differing pixels: the painter is not drawing them",
            differing > 2000,
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
        val spec = VanAuraSpecs.forState(VanDurableState.WORKING)
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
                is VanAuraOp.Flame -> op.copy(alpha = op.alpha * 0.2f)
                is VanAuraOp.Rim -> op.copy(alpha = op.alpha * 0.2f)
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
