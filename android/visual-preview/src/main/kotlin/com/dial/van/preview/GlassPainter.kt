package com.dial.van.preview

import com.dial.van.visual.VanAuraOp
import com.dial.van.visual.VanFlameAura
import com.dial.van.visual.VanAuraPlanner
import com.dial.van.visual.VanAuraSpec
import com.dial.van.visual.VanEffectBudget
import com.dial.van.visual.VanFieldGeometryEngine
import com.dial.van.visual.VanFieldInk
import com.dial.van.visual.VanGlassStyle
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanPathSeg
import com.dial.van.visual.VanWindFieldMotion
import java.awt.BasicStroke
import java.awt.Color
import java.awt.Graphics2D
import java.awt.RadialGradientPaint
import java.awt.Rectangle
import java.awt.Shape
import java.awt.geom.Arc2D
import java.awt.geom.Ellipse2D
import java.awt.geom.Path2D
import java.awt.geom.Point2D
import java.awt.geom.RoundRectangle2D
import java.awt.image.BufferedImage
import kotlin.math.PI
import kotlin.math.max
import kotlin.math.sin

/**
 * Java2D painter for DIAL Glass and VAN's living electrical field.
 *
 * Zone B/C geometry is produced by [VanFieldGeometryEngine], the exact same pure-Kotlin geometry
 * engine used by the shipping Compose overlay. [spec] owns local activity/Zone B while
 * [semanticSpec] independently owns Zone C, so evidence can certify orthogonal runtime states.
 */
object GlassPainter {

    fun blurBehind(g: Graphics2D, canvas: BufferedImage, shape: Shape, radiusPx: Int) {
        if (radiusPx <= 0) return
        val bounds: Rectangle = shape.bounds
        val pad = radiusPx * 2
        val x = (bounds.x - pad).coerceAtLeast(0)
        val y = (bounds.y - pad).coerceAtLeast(0)
        val w = (bounds.width + pad * 2).coerceAtMost(canvas.width - x)
        val h = (bounds.height + pad * 2).coerceAtMost(canvas.height - y)
        if (w <= 2 || h <= 2) return

        var region = canvas.getSubimage(x, y, w, h).let { sub ->
            BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB).also { copy ->
                copy.createGraphics().apply {
                    drawImage(sub, 0, 0, null)
                    dispose()
                }
            }
        }
        repeat(3) { region = boxBlur(region, max(radiusPx / 3, 1)) }

        val previousClip = g.clip
        g.clip(shape)
        g.drawImage(region, x, y, null)
        g.clip = previousClip
    }

    private fun boxBlur(src: BufferedImage, radius: Int): BufferedImage {
        val w = src.width
        val h = src.height
        val source = src.getRGB(0, 0, w, h, null, 0, w)
        val horizontal = IntArray(w * h)
        for (y in 0 until h) {
            for (x in 0 until w) {
                horizontal[y * w + x] = average(source, radius) { k ->
                    y * w + (x + k).coerceIn(0, w - 1)
                }
            }
        }
        val vertical = IntArray(w * h)
        for (y in 0 until h) {
            for (x in 0 until w) {
                vertical[y * w + x] = average(horizontal, radius) { k ->
                    (y + k).coerceIn(0, h - 1) * w + x
                }
            }
        }
        val dst = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
        dst.setRGB(0, 0, w, h, vertical, 0, w)
        return dst
    }

    private inline fun average(pixels: IntArray, radius: Int, index: (Int) -> Int): Int {
        var a = 0
        var r = 0
        var g = 0
        var b = 0
        var n = 0
        for (k in -radius..radius) {
            val p = pixels[index(k)]
            a += (p ushr 24) and 0xFF
            r += (p ushr 16) and 0xFF
            g += (p ushr 8) and 0xFF
            b += p and 0xFF
            n++
        }
        return ((a / n) shl 24) or ((r / n) shl 16) or ((g / n) shl 8) or (b / n)
    }

    fun fillGlass(g: Graphics2D, style: VanGlassStyle, shape: RoundRectangle2D.Float, density: Float) {
        g.color = argb(VanGlassTokens.TINT_NAVY, style.backgroundAlpha)
        g.fill(shape)

        val previousClip = g.clip
        g.clip(shape)

        g.paint = java.awt.GradientPaint(
            shape.x,
            shape.y,
            argb(0xFFFFFFFF.toInt(), 0.06f * (style.innerHighlightAlpha / 0.11f).coerceIn(0.4f, 1.4f)),
            shape.x,
            shape.y + shape.height,
            argb(0xFF000000.toInt(), 0.12f),
        )
        g.fill(shape)

        if (style.grainAlpha > 0f) {
            val step = max(shape.width, shape.height) / 28f
            var row = 0
            var gy = shape.y + step
            while (gy < shape.y + shape.height) {
                var gx = shape.x + step * (0.4f + (row % 3) * 0.2f)
                while (gx < shape.x + shape.width) {
                    val jitter = ((gx.toInt() * 13 + gy.toInt() * 7) % 5) - 2f
                    g.color = argb(0xFFFFFFFF.toInt(), style.grainAlpha)
                    g.fill(Ellipse2D.Float(gx + jitter, gy, 1.1f, 1.1f))
                    gx += step
                }
                gy += step
                row++
            }
        }

        if (style.innerHighlightAlpha > 0f) {
            g.paint = java.awt.GradientPaint(
                shape.x,
                shape.y,
                argb(0xFFFFFFFF.toInt(), style.innerHighlightAlpha * 1.4f),
                shape.x + shape.width * 0.55f,
                shape.y + shape.height * 0.42f,
                Color(255, 255, 255, 0),
            )
            g.fill(shape)
        }

        if (style.contaminationAlpha > 0f) {
            radial(
                g,
                shape.x + shape.width * 0.12f,
                shape.y + shape.height * 0.45f,
                max(shape.width, shape.height) * 0.55f,
                argb(style.borderColor, style.contaminationAlpha),
            )
        }

        g.clip = previousClip

        if (style.structuralEdgeAlpha > 0f) {
            g.color = argb(style.borderColor, style.structuralEdgeAlpha)
            g.stroke = BasicStroke(max(style.borderWidthDp * density, 1f))
            g.draw(shape)
        }

        if (style.specularAlpha > 0f) {
            val inset = 3f * density
            val arcBox = RoundRectangle2D.Float(
                shape.x + inset,
                shape.y + inset,
                shape.width - inset * 2f,
                shape.height - inset * 2f,
                shape.arcwidth,
                shape.archeight,
            )
            g.color = argb(0xFFFFFFFF.toInt(), style.specularAlpha)
            g.stroke = BasicStroke(
                max(style.borderWidthDp * density * 1.6f, 1.4f),
                BasicStroke.CAP_ROUND,
                BasicStroke.JOIN_ROUND,
            )
            g.draw(Arc2D.Float(arcBox.x, arcBox.y, arcBox.width, arcBox.height, 110f, 78f, Arc2D.OPEN))
            if (style.activeGlowAlpha > 0f) {
                g.color = argb(style.borderColor, style.activeGlowAlpha)
                g.stroke = BasicStroke(
                    max(style.borderWidthDp * density * 2.0f, 1.6f),
                    BasicStroke.CAP_ROUND,
                    BasicStroke.JOIN_ROUND,
                )
                g.draw(Arc2D.Float(arcBox.x, arcBox.y, arcBox.width, arcBox.height, 118f, 52f, Arc2D.OPEN))
            }
        }
    }

    fun dropShadow(g: Graphics2D, shape: RoundRectangle2D.Float, style: VanGlassStyle, density: Float) {
        val spread = style.elevationDp * density
        for (step in 3 downTo 1) {
            val inset = -spread * step / 3f
            g.color = Color(0, 0, 0, (26 / step))
            g.fill(
                RoundRectangle2D.Float(
                    shape.x + inset,
                    shape.y + inset + spread * 0.25f,
                    shape.width - inset * 2,
                    shape.height - inset * 2,
                    shape.arcwidth,
                    shape.archeight,
                ),
            )
        }
    }

    /**
     * P1-VIS-001 — the Java2D executor for the shared aura plan.
     *
     * This used to be a hand-written second implementation of `VanAura.kt`, and it had
     * drifted: it never drew `electricalBranches` at all, used roughly double the Zone A
     * alpha and 1.5x the radius, placed the haze blobs elsewhere, gave ion fragments no
     * bloom, and used different orb-link constants. Every committed piece of visual evidence
     * was therefore a picture of something the app does not look like — which is the worst
     * possible failure for a renderer whose entire purpose is to produce evidence.
     *
     * It now holds no aura constants at all. [VanAuraPlanner.plan] decides; this draws.
     */
    fun drawAura(
        g: Graphics2D,
        spec: VanAuraSpec,
        cx: Float,
        cy: Float,
        radius: Float,
        budget: VanEffectBudget = VanEffectBudget.FULL,
        phase: Float = 0.18f,
        semanticSpec: VanAuraSpec = spec,
    ) {
        drawAuraOps(
            g,
            VanAuraPlanner.plan(
                spec = spec,
                semanticSpec = semanticSpec,
                centerX = cx,
                centerY = cy,
                radius = radius,
                budget = budget,
                phase = phase,
            ),
        )
    }

    fun drawAuraOps(g: Graphics2D, ops: List<VanAuraOp>) {
        for (op in ops) {
            when (op) {
                is VanAuraOp.Radial -> {
                    if (op.radius <= 0f || op.alpha <= 0.001f) continue
                    val inner = argb(op.color, op.alpha)
                    if (op.clip.isEmpty()) {
                        radial(g, op.cx, op.cy, op.radius, inner)
                    } else {
                        val previous = g.clip
                        g.clip(op.clip.toPath())
                        radial(g, op.cx, op.cy, op.radius, inner)
                        g.clip = previous
                    }
                }
                is VanAuraOp.Polyline -> {
                    if (op.points.size < 2 || op.alpha <= 0.001f) continue
                    val path = Path2D.Float()
                    op.points.forEachIndexed { index, point ->
                        if (index == 0) path.moveTo(point.x, point.y) else path.lineTo(point.x, point.y)
                    }
                    g.stroke = BasicStroke(op.glowWidth, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND)
                    g.color = argb(op.color, minOf(op.alpha * op.glowAlphaScale, op.glowAlphaCeiling))
                    g.draw(path)
                    val core = op.whiteCoreWidth
                    if (core != null) {
                        g.stroke = BasicStroke(core, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND)
                        g.color = Color(255, 255, 255, (op.whiteCoreAlpha.coerceIn(0f, 1f) * 255f).toInt())
                        g.draw(path)
                    }
                    g.stroke = BasicStroke(op.width, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND)
                    g.color = argb(op.color, op.alpha)
                    g.draw(path)
                }
                is VanAuraOp.Dot -> {
                    if (op.radius <= 0f || op.alpha <= 0.001f) continue
                    val bloom = op.radius * op.bloomRadiusScale
                    g.color = argb(op.color, op.alpha * op.bloomAlphaScale)
                    g.fill(Ellipse2D.Float(op.cx - bloom, op.cy - bloom, bloom * 2f, bloom * 2f))
                    g.color = argb(op.color, op.alpha)
                    g.fill(
                        Ellipse2D.Float(
                            op.cx - op.radius, op.cy - op.radius, op.radius * 2f, op.radius * 2f,
                        ),
                    )
                }
                is VanAuraOp.Flame -> {
                    if (op.path.isEmpty() || op.gradientRadius <= 1f || op.alpha <= 0.001f) continue
                    val c = argb(op.color, op.alpha)
                    g.paint = RadialGradientPaint(
                        Point2D.Float(op.gradientX, op.gradientY),
                        op.gradientRadius,
                        floatArrayOf(0f, VanFlameAura.FLAME_SOLID_STOP_FRACTION, 1f),
                        arrayOf(c, c, fade(c, VanFlameAura.FLAME_TIP_ALPHA_FRACTION)),
                    )
                    g.fill(op.path.toPath())
                }
                is VanAuraOp.Quad -> {
                    if (op.alpha <= 0.001f) continue
                    val path = Path2D.Float()
                    path.moveTo(op.startX, op.startY)
                    path.quadTo(op.controlX, op.controlY, op.endX, op.endY)
                    g.color = argb(op.color, op.alpha)
                    g.stroke = BasicStroke(op.width, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND)
                    g.draw(path)
                }
            }
        }
    }

    private fun List<VanPathSeg>.toPath(): Path2D.Float {
        val path = Path2D.Float()
        for (segment in this) {
            when (segment) {
                is VanPathSeg.MoveTo -> path.moveTo(segment.x, segment.y)
                is VanPathSeg.LineTo -> path.lineTo(segment.x, segment.y)
                is VanPathSeg.QuadTo -> path.quadTo(segment.cx, segment.cy, segment.x, segment.y)
                VanPathSeg.Close -> path.closePath()
            }
        }
        return path
    }

    fun drawCrescentAura(
        g: Graphics2D,
        spec: VanAuraSpec,
        left: Float,
        top: Float,
        width: Float,
        height: Float,
        budget: VanEffectBudget = VanEffectBudget.FULL,
        phase: Float = 0.18f,
        semanticSpec: VanAuraSpec = spec,
    ) {
        val cyan = semanticSpec.alertAccent ?: spec.alertAccent ?: VanGlassTokens.ACCENT_CYAN
        val crescent = Path2D.Float()
        crescent.moveTo(left + width * 0.08f, top + height * 0.12f)
        crescent.quadTo(left + width * 0.95f, top + height * 0.08f, left + width, top + height * 0.42f)
        crescent.quadTo(left + width * 0.92f, top + height * 0.92f, left + width * 0.10f, top + height * 0.88f)
        crescent.quadTo(left + width * 0.02f, top + height * 0.50f, left + width * 0.08f, top + height * 0.12f)
        crescent.closePath()
        val previous = g.clip
        g.clip(crescent)
        drawAura(
            g,
            spec,
            left + width * 0.58f,
            top + height * 0.42f,
            height * 0.42f,
            budget,
            phase,
            semanticSpec,
        )
        g.clip = previous
        g.color = argb(cyan, 0.22f)
        g.stroke = BasicStroke(max(width * 0.04f, 1.6f), BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND)
        g.draw(crescent)
    }

    private fun radial(g: Graphics2D, cx: Float, cy: Float, r: Float, inner: Color) {
        if (r <= 1f) return
        g.paint = RadialGradientPaint(
            Point2D.Float(cx, cy),
            r,
            floatArrayOf(0f, 0.5f, 1f),
            arrayOf(inner, fade(inner, 0.42f), fade(inner, 0f)),
        )
        g.fill(Ellipse2D.Float(cx - r, cy - r, r * 2f, r * 2f))
    }

    private fun fade(color: Color, factor: Float): Color =
        Color(color.red, color.green, color.blue, (color.alpha * factor.coerceIn(0f, 1f)).toInt())

    fun argb(color: Int, alpha: Float): Color = Color(
        (color shr 16) and 0xFF,
        (color shr 8) and 0xFF,
        color and 0xFF,
        (alpha.coerceIn(0f, 1f) * 255f).toInt(),
    )
}
