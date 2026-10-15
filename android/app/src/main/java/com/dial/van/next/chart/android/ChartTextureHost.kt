package com.dial.van.next.chart.android

import android.content.Context
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.SurfaceTexture
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import android.view.Choreographer
import android.view.TextureView
import com.dial.van.next.chart.ChartEngine
import com.dial.van.next.chart.scene.Align
import com.dial.van.next.chart.scene.DisplayList
import com.dial.van.next.chart.scene.DrawCmd
import com.dial.van.next.chart.scene.StyleRole

/**
 * Android host for the VAN Next chart engine (§7.8.2, VAN-NX-041).
 *
 * Frames are produced on a dedicated render thread onto a [TextureView], outside Compose
 * recomposition — the separation MT5's chart surface showed (REA §3.1). The engine itself
 * stays on the main thread; this host builds an immutable display list there and hands it
 * to the render thread, so no engine state is shared across threads.
 *
 * Lifecycle: no surface → no frames; hidden → no frames and no vsync clock; surface lost
 * (rotation, background, GPU reset) → the next surface redraws in full. All of those
 * decisions are made by the engine's [com.dial.van.next.chart.runtime.FrameScheduler],
 * which is unit-tested on the JVM.
 *
 * NOT COMPILED IN THE JVM HARNESS: this file needs the Android SDK. Qualification is the
 * `:app` build plus the §7.8.10 device cases on the Samsung S24.
 */
class ChartTextureHost(
    context: Context,
    private val engine: ChartEngine,
    private val palette: ChartPalette,
) : TextureView(context), TextureView.SurfaceTextureListener, Choreographer.FrameCallback {

    private val renderThread = HandlerThread("van-chart-render").apply { start() }
    private val renderHandler = Handler(renderThread.looper)
    private var clockRunning = false

    init { surfaceTextureListener = this }

    /** Call after any engine change (bar, gesture, overlay, theme). Cheap; frames coalesce. */
    fun requestFrame() {
        engine.scheduler.invalidate()
        ensureClock()
    }

    fun setHostVisible(visible: Boolean) {
        engine.scheduler.onVisibility(visible)
        ensureClock()
    }

    private fun ensureClock() {
        if (engine.scheduler.wantsFrames && !clockRunning) {
            clockRunning = true
            Choreographer.getInstance().postFrameCallback(this)
        }
    }

    override fun doFrame(frameTimeNanos: Long) {
        clockRunning = false
        val now = SystemClock.uptimeMillis()
        if (engine.scheduler.shouldDraw(now)) {
            val list = engine.frame().list // built on the main thread; immutable from here on
            engine.scheduler.frameDrawn(now)
            renderHandler.post { draw(list) }
        }
        if (engine.scheduler.wantsFrames) ensureClock()
    }

    private fun draw(list: DisplayList) {
        val canvas = lockCanvas() ?: return // surface went away between scheduling and drawing
        try {
            canvas.drawColor(palette.background)
            DisplayListPainter.paint(canvas, list, palette)
        } finally {
            unlockCanvasAndPost(canvas)
        }
    }

    override fun onSurfaceTextureAvailable(surface: SurfaceTexture, width: Int, height: Int) {
        engine.resize(engine.layoutFor(width.toFloat(), height.toFloat(), resources.displayMetrics.density))
        engine.scheduler.onSurfaceAvailable()
        ensureClock()
    }

    override fun onSurfaceTextureSizeChanged(surface: SurfaceTexture, width: Int, height: Int) {
        engine.resize(engine.layoutFor(width.toFloat(), height.toFloat(), resources.displayMetrics.density))
        ensureClock()
    }

    override fun onSurfaceTextureDestroyed(surface: SurfaceTexture): Boolean {
        engine.scheduler.onSurfaceLost()
        renderHandler.removeCallbacksAndMessages(null)
        return true
    }

    override fun onSurfaceTextureUpdated(surface: SurfaceTexture) = Unit

    override fun onDetachedFromWindow() {
        super.onDetachedFromWindow()
        Choreographer.getInstance().removeFrameCallback(this)
        renderThread.quitSafely()
    }
}

/** Theme mapping for style roles. Built from VAN Next design tokens, never hard-coded in the engine. */
interface ChartPalette {
    val background: Int
    fun color(role: StyleRole): Int
    fun strokeWidth(role: StyleRole): Float
    val textSizePx: Float
}

/** Replays a display list onto an Android canvas. Stateless apart from reusable paints. */
object DisplayListPainter {
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG)
    private val dash = DashPathEffect(floatArrayOf(10f, 8f), 0f)
    private val path = Path()

    fun paint(canvas: Canvas, list: DisplayList, palette: ChartPalette) {
        text.textSize = palette.textSizePx
        var clipped = false
        for (cmd in list.commands) {
            when (cmd) {
                is DrawCmd.Clip -> { if (clipped) canvas.restore(); canvas.save(); canvas.clipRect(cmd.left, cmd.top, cmd.right, cmd.bottom); clipped = true }
                DrawCmd.Unclip -> { if (clipped) { canvas.restore(); clipped = false } }
                is DrawCmd.Line -> {
                    stroke.color = palette.color(cmd.role); stroke.strokeWidth = palette.strokeWidth(cmd.role)
                    stroke.pathEffect = if (cmd.dashed) dash else null
                    canvas.drawLine(cmd.x1, cmd.y1, cmd.x2, cmd.y2, stroke)
                }
                is DrawCmd.Rect -> {
                    val p = if (cmd.filled) fill else stroke
                    p.color = palette.color(cmd.role); stroke.pathEffect = null; stroke.strokeWidth = palette.strokeWidth(cmd.role)
                    canvas.drawRect(cmd.left, cmd.top, cmd.right, cmd.bottom, p)
                }
                is DrawCmd.Polyline -> {
                    if (cmd.xs.size < 2) continue
                    path.reset(); path.moveTo(cmd.xs[0], cmd.ys[0])
                    for (i in 1 until cmd.xs.size) path.lineTo(cmd.xs[i], cmd.ys[i])
                    stroke.color = palette.color(cmd.role); stroke.strokeWidth = palette.strokeWidth(cmd.role); stroke.pathEffect = null
                    canvas.drawPath(path, stroke)
                }
                is DrawCmd.Text -> {
                    text.color = palette.color(cmd.role)
                    text.textAlign = when (cmd.align) { Align.LEFT -> Paint.Align.LEFT; Align.CENTER -> Paint.Align.CENTER; Align.RIGHT -> Paint.Align.RIGHT }
                    canvas.drawText(cmd.text, cmd.x, cmd.y, text)
                }
            }
        }
        if (clipped) canvas.restore()
    }
}
