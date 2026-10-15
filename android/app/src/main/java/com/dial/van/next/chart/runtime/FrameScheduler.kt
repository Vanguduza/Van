package com.dial.van.next.chart.runtime

/**
 * When to draw (§7.8.2, MT5's surface-lifecycle lesson). The renderer asks this on every
 * vsync; the scheduler answers from pure state, so "never draw while hidden", "coalesce a
 * burst of ticks into one frame" and "recover after the surface is lost" are tested rather
 * than hoped for.
 */
class FrameScheduler(private val minFrameIntervalMs: Long = 16) {
    enum class Surface { NONE, READY, LOST }

    var surface: Surface = Surface.NONE
        private set
    var visible: Boolean = false
        private set
    private var dirty = true
    private var lastFrameMs = Long.MIN_VALUE / 2
    var framesDrawn = 0
        private set

    fun onSurfaceAvailable() { surface = Surface.READY; dirty = true }
    /** Texture or surface destroyed (rotation, background, GPU reset). The next available surface redraws in full. */
    fun onSurfaceLost() { surface = Surface.LOST }
    fun onVisibility(isVisible: Boolean) { if (isVisible && !visible) dirty = true; visible = isVisible }
    /** Any state change (tick, pan, theme) marks the frame dirty; many invalidations make one frame. */
    fun invalidate() { dirty = true }

    /** Called on vsync. True means draw now; the caller then calls [frameDrawn]. */
    fun shouldDraw(nowMs: Long): Boolean =
        surface == Surface.READY && visible && dirty && nowMs - lastFrameMs >= minFrameIntervalMs

    fun frameDrawn(nowMs: Long) { dirty = false; lastFrameMs = nowMs; framesDrawn++ }

    /** Whether vsync callbacks are needed at all; false lets the renderer stop its clock. */
    val wantsFrames: Boolean get() = surface == Surface.READY && visible && dirty
}
