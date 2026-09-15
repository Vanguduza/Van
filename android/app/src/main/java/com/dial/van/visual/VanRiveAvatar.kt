package com.dial.van.visual

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import app.rive.runtime.kotlin.RiveAnimationView
import app.rive.runtime.kotlin.core.Fit
import app.rive.runtime.kotlin.core.Loop

@Composable
fun VanRiveAvatar(
    state: VanVisualState,
    modifier: Modifier = Modifier,
    onLoadFailed: () -> Unit = {},
) {
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            RiveAnimationView(ctx).apply {
                try {
                    val bytes = ctx.assets.open(RiveBindingContract.ASSET_FILE).readBytes()
                    setRiveBytes(
                        bytes,
                        artboardName = RiveBindingContract.ARTBOARD,
                        stateMachineName = RiveBindingContract.STATE_MACHINE,
                        animationName = null,
                        autoplay = true,
                        fit = Fit.CONTAIN,
                        alignment = app.rive.runtime.kotlin.core.Alignment.CENTER,
                        loop = Loop.LOOP,
                    )
                } catch (_: Throwable) {
                    onLoadFailed()
                }
            }
        },
        update = { view ->
            try {
                applyVisualState(view, state)
            } catch (_: Throwable) {
                onLoadFailed()
            }
        },
    )
}

private fun applyVisualState(view: RiveAnimationView, state: VanVisualState) {
    val sm = RiveBindingContract.STATE_MACHINE
    state.toRiveInputs().forEach { (input, value) ->
        when (input) {
            VanInput.STATE -> view.setNumberState(sm, input.wireName, (value as Number).toFloat())
            VanInput.SPEAKING -> view.setBooleanState(sm, input.wireName, value as Boolean)
            VanInput.LISTENING -> view.setBooleanState(sm, input.wireName, value as Boolean)
            VanInput.ATTENTION_X -> view.setNumberState(sm, input.wireName, value as Float)
            VanInput.ATTENTION_Y -> view.setNumberState(sm, input.wireName, value as Float)
            VanInput.MOUTH_OPEN -> view.setNumberState(sm, input.wireName, value as Float)
            VanInput.URGENCY -> view.setNumberState(sm, input.wireName, value as Float)
            VanInput.VISEME -> view.setNumberState(sm, input.wireName, (value as Number).toFloat())
            VanInput.ACTION_CODE -> view.setNumberState(sm, input.wireName, (value as Number).toFloat())
        }
    }
}
