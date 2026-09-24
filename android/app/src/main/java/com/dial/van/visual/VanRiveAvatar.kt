package com.dial.van.visual

import android.graphics.Bitmap
import android.view.TextureView
import android.view.View
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
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
    onSilhouette: (VanSilhouette) -> Unit = {},
) {
    var riveView by remember { mutableStateOf<View?>(null) }
    // Aura Rev 2 — the flames follow the rig: the rendered artboard's alpha is sampled every
    // few frames and turned into the silhouette the aura wraps.
    LaunchedEffect(riveView) {
        val view = riveView as? TextureView ?: return@LaunchedEffect
        val sampler = VanRiveSilhouetteSampler()
        var last = 0L
        while (true) {
            val now = withFrameNanos { it }
            if (now - last < VanRiveSilhouetteSampler.INTERVAL_NANOS) continue
            last = now
            sampler.sample(view)?.let(onSilhouette)
        }
    }
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            try {
                VanRiveRuntime.ensure(ctx.applicationContext)
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
                }.also { riveView = it }
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

/**
 * Reads the Rive artboard's rendered alpha at a low resolution and turns it into a
 * [VanSilhouette]. One bitmap and three arrays for the view's lifetime: nothing is allocated
 * per sample, and at [INTERVAL_NANOS] the cost is a 48×48 `getBitmap` roughly twelve times a
 * second, far below a frame.
 */
class VanRiveSilhouetteSampler {
    private val bitmap: Bitmap = Bitmap.createBitmap(GRID, GRID, Bitmap.Config.ARGB_8888)
    private val pixels = IntArray(GRID * GRID)
    private val alpha = ByteArray(GRID * GRID)
    private val square = ByteArray(VanSilhouette.SQUARE * VanSilhouette.SQUARE)

    fun sample(view: TextureView): VanSilhouette? {
        if (!view.isAvailable || view.width <= 0 || view.height <= 0) return null
        return try {
            view.getBitmap(bitmap)
            bitmap.getPixels(pixels, 0, GRID, 0, 0, GRID, GRID)
            for (i in pixels.indices) alpha[i] = (pixels[i] ushr 24).toByte()
            VanSilhouette.fromViewAlpha(GRID, GRID, alpha, view.width.toFloat(), view.height.toFloat(), square)
        } catch (_: Throwable) {
            null
        }
    }

    companion object {
        const val GRID = 48
        const val INTERVAL_NANOS = 83_000_000L
    }
}
