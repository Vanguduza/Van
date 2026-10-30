package com.dial.van.visual

import android.content.Context
import android.content.Intent
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import app.rive.runtime.kotlin.RiveAnimationView
import app.rive.runtime.kotlin.core.Alignment
import app.rive.runtime.kotlin.core.Fit
import app.rive.runtime.kotlin.renderers.Renderer
import app.rive.runtime.kotlin.renderers.RiveArtboardRenderer

/** Debug instrumentation only. The pinned runtime explicitly supports createRenderer/advance.
 * Advance on the render thread in 60 Hz steps, then draw the frozen pose. Screenshot and
 * Activity launch latency cannot change its animation time. No shipping renderer uses this.
 */
@Composable
internal fun FixedTimeRiveFrame(bytes: ByteArray, intent: Intent) {
    val sampleMs = intent.getLongExtra(RiveCandidateHostActivity.EXTRA_SAMPLE_TIME_MS, 850L)
    require(sampleMs in 250L..5_000L)
    val size = intent.getIntExtra(RiveCandidateHostActivity.EXTRA_SIZE_DP, 320).dp
    AndroidView(factory = { context ->
        VanRiveRuntime.ensure(context.applicationContext)
        FixedTimeRiveView(context, intent, sampleMs).apply {
            val pixels = (size.value * resources.displayMetrics.density).toInt()
            layoutParams = android.view.ViewGroup.LayoutParams(pixels, pixels)
            setRiveBytes(bytes, artboardName = RiveBindingContract.ARTBOARD,
                stateMachineName = RiveBindingContract.STATE_MACHINE,
                autoplay = true, fit = Fit.CONTAIN, alignment = Alignment.CENTER)
        }
    })
}

private class FixedTimeRiveView(
    context: Context,
    private val inputs: Intent,
    private val sampleMs: Long,
) : RiveAnimationView(context) {
    override fun createRenderer(): Renderer = object : RiveArtboardRenderer(
        controller = controller,
        rendererType = rendererAttributes.rendererType,
    ) {
        private var sampled = false
        private var drawsAfterSample = 0

        override fun advance(elapsed: Float) {
            if (sampled || !hasCppObject || !controller.isActive || controller.activeArtboard == null) return
            val sm = RiveBindingContract.STATE_MACHINE
            controller.setNumberState(sm, VanInput.STATE.wireName, 2f)
            controller.advance(0f)
            // Match the existing host's 250 ms input delay without relying on a timer.
            repeat(15) { controller.advance(1f / 60f) }
            controller.setNumberState(sm, VanInput.STATE.wireName,
                inputs.getIntExtra(RiveCandidateHostActivity.EXTRA_STATE, 2).toFloat())
            controller.setBooleanState(sm, VanInput.SPEAKING.wireName,
                inputs.getBooleanExtra(RiveCandidateHostActivity.EXTRA_SPEAKING, false))
            controller.setBooleanState(sm, VanInput.LISTENING.wireName,
                inputs.getBooleanExtra(RiveCandidateHostActivity.EXTRA_LISTENING, false))
            for ((input, extra) in listOf(
                VanInput.ATTENTION_X to RiveCandidateHostActivity.EXTRA_ATTENTION_X,
                VanInput.ATTENTION_Y to RiveCandidateHostActivity.EXTRA_ATTENTION_Y,
                VanInput.MOUTH_OPEN to RiveCandidateHostActivity.EXTRA_MOUTH_OPEN,
                VanInput.URGENCY to RiveCandidateHostActivity.EXTRA_URGENCY,
            )) controller.setNumberState(sm, input.wireName, inputs.getFloatExtra(extra, 0f))
            controller.setNumberState(sm, VanInput.VISEME.wireName,
                inputs.getIntExtra(RiveCandidateHostActivity.EXTRA_VISEME, 0).toFloat())
            controller.setNumberState(sm, VanInput.ACTION_CODE.wireName,
                inputs.getIntExtra(RiveCandidateHostActivity.EXTRA_ACTION, 0).toFloat())
            inputs.getStringExtra(RiveCandidateHostActivity.EXTRA_TRIGGER)?.let { controller.fireState(sm, it) }
            controller.advance(0f)
            val duration = (sampleMs - 250L) / 1_000f
            val wholeSteps = ((sampleMs - 250L) * 60L / 1_000L).toInt()
            repeat(wholeSteps) { controller.advance(1f / 60f) }
            val remainder = duration - wholeSteps / 60f
            if (remainder > 0f) controller.advance(remainder)
            sampled = true
        }

        override fun draw() {
            super.draw()
            if (sampled && ++drawsAfterSample >= 2) {
                RiveCandidateHostActivity.lastSampleTimeMs = sampleMs
            }
        }
    }
}
