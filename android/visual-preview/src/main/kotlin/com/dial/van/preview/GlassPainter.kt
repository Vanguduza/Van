package com.dial.van.preview

import com.dial.van.visual.VanAuraSpec
import com.dial.van.visual.VanEffectBudget
import com.dial.van.visual.VanGlassStyle
import com.dial.van.visual.VanGlassTokens
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
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin

/**
 * Java2D painter for the DIAL Glass shell and the blue electrical aura.
 *
 * Reads [VanGlassStyle] and [VanAuraSpec] — the same objects the Compose overlay consumes — so
 * these previews cannot show a look the app does not ship. The one thing the preview does that
 * Compose delegates to the window manager is [blurBehind]: it blurs the mock host-app pixels
 * under the glass, which is what `WindowManager.LayoutParams.blurBehindRadius` does on device.
 */
object GlassPainter {

    /**
     * §10 step 2 — backdrop blur sampling, simulated by blurring what is already on the canvas
     * beneath [shape]. Three box-blur passes approximate a Gaussian closely enough for a still.
     */
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

    /**
     * Optical glass: tint, shaping gradient, grain, inner highlight, contamination,
     * faint structural edge, selective specular. No uniform glowing perimeter.
     */
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

        val structural = style.structuralEdgeAlpha
        if (structural > 0f) {
            g.color = argb(style.borderColor, structural)
            g.stroke = BasicStroke(max(style.borderWidthDp * density, 1f))
            g.draw(shape)
        }

        val specular = style.specularAlpha
        if (specular > 0f) {
            val inset = 3f * density
            val arcBox = RoundRectangle2D.Float(
                shape.x + inset,
                shape.y + inset,
                shape.width - inset * 2f,
                shape.height - inset * 2f,
                shape.arcwidth,
                shape.archeight,
            )
            g.color = argb(0xFFFFFFFF.toInt(), specular)
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

    /** Shallow, soft, spatial shadow (§3). */
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
     * Living refractive field: deformable outer field, core radiance, crescent ground,
     * filaments, broken orbital arcs. A full ring is forbidden.
     *
     * [phase] is fixed by the caller so regenerated previews stay comparable.
     */
    fun drawAura(
        g: Graphics2D,
        spec: VanAuraSpec,
        cx: Float,
        cy: Float,
        radius: Float,
        budget: VanEffectBudget = VanEffectBudget.FULL,
        phase: Float = 0.18f,
    ) {
        if (spec.intensity <= 0.01f || radius <= 1f) return
        val cyan = VanGlassTokens.ACCENT_CYAN
        val fieldColor = spec.alertAccent ?: cyan
        val breath = if (budget.allowMotion) 0.94f + 0.06f * sin(phase * 2f * PI.toFloat()) else 1f
        val rx = radius * (1.05f + 0.10f * spec.intensity) * budget.bloomScale * breath
        val ry = radius * (0.82f + 0.08f * spec.intensity) * budget.bloomScale * breath

        // Offset lobes only when the field is energetic enough not to read as a plate (Gate A).
        if (spec.intensity > 0.32f) {
            radial(
                g,
                cx - rx * 0.22f,
                cy + ry * 0.06f,
                rx * 0.55f,
                argb(fieldColor, 0.05f + 0.08f * spec.intensity),
            )
            radial(
                g,
                cx + rx * 0.28f,
                cy - ry * 0.10f,
                rx * 0.42f,
                argb(fieldColor, 0.04f + 0.06f * spec.intensity),
            )
        }

        if (spec.groundGlow > 0.01f) {
            val crescent = Path2D.Float()
            val gy = cy + radius * 1.05f
            val gw = radius * 1.15f
            crescent.moveTo(cx - gw, gy)
            crescent.quadTo(cx.toDouble(), (gy + radius * 0.22f).toDouble(), (cx + gw).toDouble(), gy.toDouble())
            crescent.quadTo(cx.toDouble(), (gy - radius * 0.08f).toDouble(), (cx - gw).toDouble(), gy.toDouble())
            crescent.closePath()
            val previous = g.clip
            g.clip(crescent)
            radial(g, cx, gy, gw, argb(fieldColor, 0.32f * spec.groundGlow))
            g.clip = previous
        }

        if (spec.filamentCount > 0 && spec.arcActivity > 0.01f) {
            val count = spec.filamentCount.coerceIn(1, 5)
            g.stroke = BasicStroke(max(radius * 0.062f, 2.0f), BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND)
            repeat(count) { index ->
                val seed = index * 1.17f + spec.intensity
                val life = (phase + seed * 0.13f) % 1f
                val visible = if (budget.allowMotion) life < 0.72f else true
                if (!visible) return@repeat
                val fade = if (budget.allowMotion) {
                    sin((life / 0.72f) * PI.toFloat()).coerceAtLeast(0.35f)
                } else {
                    0.82f
                }
                val start = 0.55f + index * 0.9f
                val inner = radius * 0.72f
                val outer = radius * (1.28f + 0.22f * ((seed * 3f) % 1f))
                val path = Path2D.Float()
                path.moveTo(cx + cos(start) * inner, cy + sin(start) * inner)
                val bend = start + 0.55f + 0.25f * sin(seed)
                path.quadTo(
                    cx + cos(bend) * (inner + outer) * 0.48f,
                    cy + sin(bend) * (inner + outer) * 0.42f,
                    cx + cos(start + 0.35f) * outer,
                    cy + sin(start + 0.22f) * outer,
                )
                g.color = argb(fieldColor, (0.42f + 0.40f * spec.arcActivity).coerceIn(0.42f, 0.88f) * fade)
                g.draw(path)
            }
        }

        if (spec.arcActivity > 0.02f) {
            val arcs = (1 + (spec.arcActivity * 3f).toInt()).coerceAtMost(3)
            var remaining = VanAuraSpec.MAX_TOTAL_ARC_DEG
            val ovalRx = radius * 1.12f
            val ovalRy = radius * 1.28f
            g.stroke = BasicStroke(max(radius * 0.048f, 1.8f), BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND)
            repeat(arcs) { index ->
                if (remaining <= 18f) return@repeat
                val seed = index * 0.41f
                val life = (phase * 0.6f + seed) % 1f
                val visible = if (budget.allowMotion) life < 0.62f else true
                if (!visible) return@repeat
                val fade = if (budget.allowMotion) sin((life / 0.62f) * PI.toFloat()).coerceAtLeast(0.4f) else 0.78f
                val sweep = (56f + 36f * spec.arcActivity - index * 12f)
                    .coerceAtMost(VanAuraSpec.MAX_ARC_SWEEP_DEG)
                    .coerceAtMost(remaining)
                remaining -= sweep
                val start = (index * 118f + 18f + if (budget.allowMotion) phase * 40f else 0f) % 360f
                val inset = index * radius * 0.05f
                g.color = argb(fieldColor, (0.38f + 0.32f * spec.arcActivity).coerceIn(0.38f, 0.78f) * fade)
                g.draw(
                    Arc2D.Float(
                        cx - ovalRx + inset,
                        cy - ovalRy - inset * 0.4f,
                        (ovalRx - inset) * 2f,
                        (ovalRy - inset) * 2f,
                        -start,
                        -sweep,
                        Arc2D.OPEN,
                    ),
                )
            }
        }

        if (spec.sparkRate > 0.02f && budget.allowMotion) {
            val sparks = (spec.sparkRate * 5f).toInt().coerceIn(1, 4)
            repeat(sparks) { index ->
                val seed = index * 0.611f
                val life = (phase * 1.7f + seed) % 1f
                if (life > 0.22f) return@repeat
                val angle = (seed * 2f * PI.toFloat() * 3.1f) % (2f * PI.toFloat())
                val distance = radius * (1.0f + 0.18f * ((seed * 7f) % 1f))
                val sr = max(radius * 0.022f, 1.1f)
                g.color = argb(fieldColor, 0.70f * (1f - life / 0.22f))
                g.fill(
                    Ellipse2D.Float(
                        cx + cos(angle) * distance - sr,
                        cy + sin(angle) * distance - sr,
                        sr * 2f,
                        sr * 2f,
                    ),
                )
            }
        }

        if (spec.orbLink > 0.05f) {
            val alpha = if (budget.allowMotion) {
                0.28f + 0.22f * (0.5f + 0.5f * sin(phase * 4f * PI.toFloat()))
            } else {
                0.32f
            }
            val path = Path2D.Float()
            path.moveTo(cx + radius * 0.28f, cy - radius * 0.08f)
            path.quadTo(
                cx + radius * 0.70f,
                cy - radius * 0.42f,
                cx + radius * 0.92f,
                cy - radius * 0.22f,
            )
            g.color = argb(fieldColor, alpha * spec.orbLink)
            g.stroke = BasicStroke(max(radius * 0.036f, 1.4f), BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND)
            g.draw(path)
        }
    }

    /** Edge-dock field: a crescent opening toward the screen, never a clipped disk. */
    fun drawCrescentAura(
        g: Graphics2D,
        spec: VanAuraSpec,
        left: Float,
        top: Float,
        width: Float,
        height: Float,
        budget: VanEffectBudget = VanEffectBudget.FULL,
        phase: Float = 0.18f,
    ) {
        val cyan = spec.alertAccent ?: VanGlassTokens.ACCENT_CYAN
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
        )
        g.clip = previous
        g.color = argb(cyan, 0.22f)
        g.stroke = BasicStroke(max(width * 0.04f, 1.6f), BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND)
        g.draw(crescent)
    }

    // Gradient stops always fade to the *same* hue at zero alpha. Fading to transparent black
    // instead would interpolate through grey in sRGB and leave a muddy dark halo around Van.
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
