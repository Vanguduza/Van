package com.dial.van.preview

import com.dial.van.visual.VanDrawOp
import com.dial.van.visual.VanPathSeg
import java.awt.BasicStroke
import java.awt.Color
import java.awt.Graphics2D
import java.awt.RenderingHints
import java.awt.geom.Arc2D
import java.awt.geom.Ellipse2D
import java.awt.geom.Path2D
import java.awt.geom.RoundRectangle2D
import java.awt.image.BufferedImage
import java.io.File

/**
 * Java2D interpreter for [VanDrawOp] programs.
 *
 * Deliberately dumb: it replays the shipping geometry and nothing else, so a preview can
 * never flatter the app. The Compose `drawVanScene` renderer applies the same fit rules.
 */
object AwtVanRenderer {

    fun render(
        ops: List<VanDrawOp>,
        width: Int,
        height: Int,
        background: Int? = null,
    ): BufferedImage {
        val image = BufferedImage(width, height, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        prepare(g)
        if (background != null) {
            g.color = Color(background, true)
            g.fillRect(0, 0, width, height)
        }
        paint(g, ops, 0f, 0f, width.toFloat(), height.toFloat())
        g.dispose()
        return image
    }

    fun prepare(g: Graphics2D) {
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        g.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY)
        g.setRenderingHint(RenderingHints.KEY_STROKE_CONTROL, RenderingHints.VALUE_STROKE_PURE)
        g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
    }

    /** Fits the unit-square scene into the box, centred, exactly like the Compose renderer. */
    fun paint(g: Graphics2D, ops: List<VanDrawOp>, boxX: Float, boxY: Float, boxW: Float, boxH: Float) {
        val s = minOf(boxW, boxH)
        if (s <= 0f) return
        val dx = boxX + (boxW - s) / 2f
        val dy = boxY + (boxH - s) / 2f
        fun x(v: Float) = dx + v * s
        fun y(v: Float) = dy + v * s
        fun px(v: Float) = v * s

        ops.forEach { op ->
            g.color = Color(op.color, true)
            val strokeWidth = op.strokeWidth?.let { maxOf(px(it), 1f) }
            g.stroke = strokeWidth?.let { BasicStroke(it, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND) }
                ?: BasicStroke(1f)

            val shape = when (op) {
                is VanDrawOp.Circle -> Ellipse2D.Float(
                    x(op.cx - op.r),
                    y(op.cy - op.r),
                    px(op.r * 2f),
                    px(op.r * 2f),
                )

                is VanDrawOp.Oval -> Ellipse2D.Float(
                    x(op.cx - op.rx),
                    y(op.cy - op.ry),
                    px(op.rx * 2f),
                    px(op.ry * 2f),
                )

                is VanDrawOp.RoundRect -> RoundRectangle2D.Float(
                    x(op.cx - op.halfW),
                    y(op.cy - op.halfH),
                    px(op.halfW * 2f),
                    px(op.halfH * 2f),
                    px(op.radius * 2f),
                    px(op.radius * 2f),
                )

                // Compose sweeps clockwise from 3 o'clock; Java2D sweeps counter-clockwise.
                is VanDrawOp.Arc -> Arc2D.Float(
                    x(op.cx - op.r),
                    y(op.cy - op.r),
                    px(op.r * 2f),
                    px(op.r * 2f),
                    -op.startDegrees,
                    -op.sweepDegrees,
                    Arc2D.OPEN,
                )

                is VanDrawOp.PathOp -> Path2D.Float().apply {
                    op.segments.forEach { seg ->
                        when (seg) {
                            is VanPathSeg.MoveTo -> moveTo(seg.x.let(::x), seg.y.let(::y))
                            is VanPathSeg.LineTo -> lineTo(seg.x.let(::x), seg.y.let(::y))
                            is VanPathSeg.QuadTo -> quadTo(x(seg.cx), y(seg.cy), x(seg.x), y(seg.y))
                            VanPathSeg.Close -> closePath()
                        }
                    }
                }
            }

            if (strokeWidth == null) g.fill(shape) else g.draw(shape)
        }
    }

    /** Walks up to the repository root so previews land in `artifacts/` from any working dir. */
    fun repoRoot(): File {
        var dir: File? = File(".").canonicalFile
        while (dir != null) {
            if (File(dir, "visual-authority").isDirectory && File(dir, "docs").isDirectory) return dir
            dir = dir.parentFile
        }
        error("Could not locate repository root from ${File(".").canonicalPath}")
    }
}
