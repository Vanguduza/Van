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
     * Paints the glass surface itself: §3 tinted charcoal/navy fill, restrained top-left sheen,
     * cyan active glow on the interactive edge, and the 1dp low-opacity border.
     */
    fun fillGlass(g: Graphics2D, style: VanGlassStyle, shape: RoundRectangle2D.Float, density: Float) {
        g.color = argb(VanGlassTokens.TINT_NAVY, style.backgroundAlpha)
        g.fill(shape)

        if (style.innerHighlightAlpha > 0f) {
            val previousClip = g.clip
            g.clip(shape)
            g.paint = java.awt.GradientPaint(
                shape.x,
                shape.y,
                argb(0xFFFFFFFF.toInt(), style.innerHighlightAlpha * 1.6f),
                shape.x + shape.width * 0.7f,
                shape.y + shape.height * 0.7f,
                Color(255, 255, 255, 0),
            )
            g.fill(shape)
            g.clip = previousClip
        }

        if (style.activeGlowAlpha > 0f) {
            g.color = argb(style.borderColor, style.activeGlowAlpha)
            g.stroke = BasicStroke(max(style.borderWidthDp * density * 2.5f, 2f))
            g.draw(
                RoundRectangle2D.Float(
                    shape.x + 1f,
                    shape.y + 1f,
                    shape.width - 2f,
                    shape.height - 2f,
                    shape.arcwidth,
                    shape.archeight,
                ),
            )
        }

        g.color = argb(style.borderColor, style.borderAlpha)
        g.stroke = BasicStroke(max(style.borderWidthDp * density, 1.2f))
        g.draw(shape)
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
     * The §7 aura stack, in order: secondary bloom, core rim glow, ground glow, filaments,
     * micro-sparks, orb link, then the §6 alert accent ring when a state carries one.
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
        val breath = if (budget.allowMotion) 0.85f + 0.15f * sin(phase * 2f * PI.toFloat()) else 0.92f

        // Layer 2 — secondary bloom. §7 wants low opacity but real spatial separation, so the
        // floor keeps a dim state readable as a glow rather than as nothing at all.
        radial(
            g,
            cx,
            cy,
            radius * (1.34f + 0.26f * spec.intensity) * budget.bloomScale * breath,
            argb(cyan, (0.16f + 0.44f * spec.intensity).coerceAtMost(0.52f)),
        )

        // Layer 1 — core rim glow hugging the silhouette.
        rim(g, cx, cy, radius * 1.06f * breath, argb(cyan, (0.20f + 0.62f * spec.intensity).coerceAtMost(0.72f)))

        // Layer 5 — ground/hover glow: a soft elliptical cyan illumination under the body.
        if (spec.groundGlow > 0.01f) {
            val gw = radius * 1.6f
            val previous = g.transform
            g.translate(cx.toDouble(), (cy + radius * 1.02f).toDouble())
            g.scale(1.0, 0.22)
            radial(g, 0f, 0f, gw / 2f, argb(cyan, 0.42f * spec.groundGlow))
            g.transform = previous
        }

        // Layer 3 — electrical filaments: sparse, short-lived, state-driven.
        if (spec.arcActivity > 0.02f) {
            val arcs = (1 + (spec.arcActivity * 4f).toInt()).coerceAtMost(5)
            val r = radius * 1.06f
            repeat(arcs) { index ->
                val seed = index * 0.37f
                val life = (phase + seed) % 1f
                val visible = if (budget.allowMotion) life < 0.45f else index == 0
                if (!visible) return@repeat
                val fade = if (budget.allowMotion) sin((life / 0.45f) * PI.toFloat()) else 0.7f
                val start = (seed * 360f + if (budget.allowMotion) phase * 220f else 0f) % 360f
                val sweep = 22f + 16f * spec.arcActivity
                g.color = argb(spec.alertAccent ?: cyan, 0.55f * spec.arcActivity * fade)
                g.stroke = BasicStroke(max(radius * 0.030f, 1.5f), BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND)
                g.draw(Arc2D.Float(cx - r, cy - r, r * 2f, r * 2f, -start, -sweep, Arc2D.OPEN))
            }
        }

        // Layer 4 — micro-sparks.
        if (spec.sparkRate > 0.02f && budget.allowMotion) {
            val sparks = (spec.sparkRate * 6f).toInt().coerceIn(1, 5)
            repeat(sparks) { index ->
                val seed = index * 0.611f
                val life = (phase * 1.7f + seed) % 1f
                if (life > 0.22f) return@repeat
                val angle = (seed * 2f * PI.toFloat() * 3.1f) % (2f * PI.toFloat())
                val distance = radius * (1.0f + 0.15f * ((seed * 7f) % 1f))
                val sr = max(radius * 0.026f, 1.2f)
                g.color = argb(cyan, 0.85f * (1f - life / 0.22f))
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

        // Layer 6 — orb link.
        if (spec.orbLink > 0.05f) {
            val alpha = if (budget.allowMotion) {
                0.30f + 0.35f * (0.5f + 0.5f * sin(phase * 4f * PI.toFloat()))
            } else {
                0.35f
            }
            val r = radius
            g.color = argb(cyan, alpha * spec.orbLink)
            g.stroke = BasicStroke(max(radius * 0.040f, 1.5f), BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND)
            g.draw(Arc2D.Float(cx - r, cy - r, r * 2f, r * 2f, 58f, -44f, Arc2D.OPEN))
        }

        // §6 alert accent — additive to cyan, never a replacement for it.
        spec.alertAccent?.let { accent ->
            val r = radius * 1.16f
            g.color = argb(accent, 0.30f)
            g.stroke = BasicStroke(max(radius * 0.026f, 1.2f))
            g.draw(Ellipse2D.Float(cx - r, cy - r, r * 2f, r * 2f))
        }
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

    private fun rim(g: Graphics2D, cx: Float, cy: Float, r: Float, edge: Color) {
        if (r <= 1f) return
        g.paint = RadialGradientPaint(
            Point2D.Float(cx, cy),
            r,
            floatArrayOf(0f, 0.58f, 0.86f, 1f),
            arrayOf(fade(edge, 0f), fade(edge, 0.22f), edge, fade(edge, 0.30f)),
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
