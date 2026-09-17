package com.dial.van.preview

import com.dial.van.visual.VanAuraSpec
import com.dial.van.visual.VanEffectBudget
import com.dial.van.visual.VanFieldGeometryEngine
import com.dial.van.visual.VanFieldInk
import com.dial.van.visual.VanGlassStyle
import com.dial.van.visual.VanGlassTokens
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

    /** Canonical living aura: Zone A/B activity + independently truthful Zone C semantics. */
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
        if (radius <= 1f || (spec.intensity <= 0.01f && semanticSpec.intensity <= 0.01f)) return
        val bodyEdge = radius * 2f
        val cyan = VanGlassTokens.ACCENT_CYAN
        val semantic = semanticSpec.semanticColor ?: cyan
        val motion = VanWindFieldMotion.sample(spec, phase, budget)

        drawZoneA(g, spec, cx, cy, bodyEdge, cyan, motion.phase, motion.breathing)

        val geometry = VanFieldGeometryEngine.build(
            spec = spec,
            phase = phase,
            budget = budget,
            bodyEdge = bodyEdge,
            centerX = cx,
            centerY = cy,
            semanticSpec = semanticSpec,
        )
        geometry.strokes.forEach { stroke ->
            val color = if (stroke.ink == VanFieldInk.IDENTITY) cyan else semantic
            val path = Path2D.Float()
            stroke.points.forEachIndexed { index, point ->
                if (index == 0) path.moveTo(point.x, point.y) else path.lineTo(point.x, point.y)
            }
            g.stroke = BasicStroke(stroke.glowWidth, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND)
            g.color = argb(color, stroke.alpha * 0.16f)
            g.draw(path)
            g.stroke = BasicStroke(stroke.width, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND)
            g.color = argb(color, stroke.alpha)
            g.draw(path)
        }
        geometry.dots.forEach { dot ->
            val color = if (dot.ink == VanFieldInk.IDENTITY) cyan else semantic
            g.color = argb(color, dot.alpha)
            g.fill(
                Ellipse2D.Float(
                    dot.point.x - dot.radius,
                    dot.point.y - dot.radius,
                    dot.radius * 2f,
                    dot.radius * 2f,
                ),
            )
        }

        if (spec.orbLink > 0.05f) {
            val pulse = 0.24f + 0.30f * motion.electricPulse
            val path = Path2D.Float()
            path.moveTo(cx + bodyEdge * 0.11f, cy - bodyEdge * 0.04f)
            path.quadTo(
                cx + bodyEdge * 0.25f,
                cy - bodyEdge * 0.17f,
                cx + bodyEdge * 0.35f,
                cy - bodyEdge * 0.10f,
            )
            g.color = argb(cyan, pulse * spec.orbLink)
            g.stroke = BasicStroke(max(bodyEdge * 0.011f, 1.1f), BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND)
            g.draw(path)
        }
    }

    private fun drawZoneA(
        g: Graphics2D,
        spec: VanAuraSpec,
        cx: Float,
        cy: Float,
        bodyEdge: Float,
        cyan: Int,
        phase: Float,
        breathing: Float,
    ) {
        val alpha = (0.10f + 0.08f * spec.intensity).coerceIn(0.08f, 0.18f)
        val r = bodyEdge * 0.20f * VanAuraSpec.INNER_RADIUS_SCALE * breathing
        val driftX = bodyEdge * 0.025f * sin(2f * PI.toFloat() * phase)
        val driftY = bodyEdge * 0.018f * sin(4f * PI.toFloat() * phase + 0.9f)
        radial(g, cx - bodyEdge * 0.05f + driftX, cy + bodyEdge * 0.02f + driftY, r, argb(cyan, alpha * 0.82f))
        radial(g, cx + bodyEdge * 0.07f - driftX * 0.6f, cy - bodyEdge * 0.04f - driftY, r * 0.70f, argb(cyan, alpha * 0.50f))

        if (spec.groundGlow > 0.01f) {
            val gy = cy + bodyEdge * 0.41f
            val gw = bodyEdge * 0.31f
            val crescent = Path2D.Float()
            crescent.moveTo(cx - gw, gy)
            crescent.quadTo(cx.toDouble(), (gy + bodyEdge * 0.060f).toDouble(), (cx + gw).toDouble(), gy.toDouble())
            crescent.quadTo(cx.toDouble(), (gy - bodyEdge * 0.018f).toDouble(), (cx - gw).toDouble(), gy.toDouble())
            crescent.closePath()
            val previous = g.clip
            g.clip(crescent)
            radial(g, cx, gy, gw, argb(cyan, 0.18f * spec.groundGlow))
            g.clip = previous
        }
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
