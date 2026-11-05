package com.dial.van.visual

import android.content.Context
import app.rive.runtime.kotlin.RiveAnimationView
import app.rive.runtime.kotlin.renderers.Renderer
import app.rive.runtime.kotlin.renderers.RiveArtboardRenderer
import java.util.concurrent.atomic.AtomicLong

/**
 * Still-mode state changes are evaluated on Rive's own render thread, then paused
 * after the new pose has actually drawn. No JNI advance is called by the UI thread.
 */
internal class VanBoundedRiveView(context: Context) : RiveAnimationView(context) {
    @Volatile private var continuouslyAnimated = false
    @Volatile private var mayDraw = false
    private val revision = AtomicLong()
    private var renderedRevision = -1L
    private var pauseRequestedRevision = -1L
    @Volatile var onNativeFailure: () -> Unit = {}

    fun prepareDraw(visible: Boolean, animated: Boolean, inputsChanged: Boolean) {
        mayDraw = visible
        continuouslyAnimated = visible && animated
        if (inputsChanged) revision.incrementAndGet()
        if (!visible) pause()
    }

    override fun createRenderer(): Renderer = object : RiveArtboardRenderer(
        controller = controller, rendererType = rendererAttributes.rendererType,
    ) {
        override fun advance(elapsed: Float) {
            if (!mayDraw || !hasCppObject || !controller.isActive || controller.activeArtboard == null) return
            if (continuouslyAnimated) { super.advance(elapsed); return }
            val requested = revision.get()
            if (renderedRevision == requested) return
            // Consume the queued real inputs and finish the finite transition in
            // one render operation. Intermediate motion is never shown in still mode.
            try {
                super.advance(0f)
                repeat(VanRiveUpdateGate.STATIC_SETTLE_STEPS) { super.advance(VanRiveUpdateGate.STATIC_STEP_SECONDS) }
                renderedRevision = requested
            } catch (_: Throwable) {
                mayDraw = false
                post { pause(); onNativeFailure() }
            }
        }

        override fun draw() {
            if (!mayDraw) return
            super.draw()
            if (!continuouslyAnimated) {
                val completed = renderedRevision
                if (pauseRequestedRevision != completed) {
                    pauseRequestedRevision = completed
                    post { if (!continuouslyAnimated && completed == revision.get()) pause() }
                }
            }
        }
    }

    override fun onDetachedFromWindow() {
        mayDraw = false
        pause()
        super.onDetachedFromWindow()
    }
}
