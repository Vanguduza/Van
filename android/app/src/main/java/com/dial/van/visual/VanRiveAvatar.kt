package com.dial.van.visual

import android.view.View
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import app.rive.runtime.kotlin.RiveAnimationView
import app.rive.runtime.kotlin.core.Fit
import app.rive.runtime.kotlin.core.Loop

/**
 * Binds the authored `van.riv` artboard to the contract inputs.
 *
 * Construction, load and every state push are guarded: constructing [RiveAnimationView] can
 * itself throw when the native library is missing, so a bare [View] is handed back and
 * [onLoadFailed] flips the caller to the Canvas character rather than leaving a blank hole
 * where Van should be.
 */
@Composable
fun VanRiveAvatar(
    state: VanVisualState,
    modifier: Modifier = Modifier,
    onLoadFailed: () -> Unit = {},
) {
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            try {
                RiveAnimationView(ctx).apply {
                    val bytes = ctx.assets.open(RiveBindingContract.ASSET_FILE).use { it.readBytes() }
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
                }
            } catch (_: Throwable) {
                onLoadFailed()
                View(ctx)
            }
        },
        update = { view ->
            if (view is RiveAnimationView) {
                try {
                    applyVisualState(view, state)
                } catch (_: Throwable) {
                    onLoadFailed()
                }
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
