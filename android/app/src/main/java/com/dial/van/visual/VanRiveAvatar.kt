package com.dial.van.visual

import android.graphics.Bitmap
import android.view.TextureView
import android.view.View
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import app.rive.runtime.kotlin.RiveAnimationView
import app.rive.runtime.kotlin.core.Fit
import app.rive.runtime.kotlin.core.Direction
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
    animate: Boolean = true,
    budget: VanEffectBudget = VanEffectBudget.FULL,
    reducedMotion: Boolean = rememberReducedMotion(),
) {
    val enabled = vanMotionEnabled(budget, animate = animate, reducedMotion = reducedMotion)
    val smoothGaze = enabled && VanInteractionResponsePolicy.compatible(state)
    val rendered = if (smoothGaze) {
        val x by animateFloatAsState(if (state.attentionX.isFinite()) state.attentionX.coerceIn(-1f,1f) else 0f, tween(100), label = "van-gaze-x")
        val y by animateFloatAsState(if (state.attentionY.isFinite()) state.attentionY.coerceIn(-1f,1f) else 0f, tween(100), label = "van-gaze-y")
        state.copy(attentionX = x, attentionY = y)
    } else state
    val currentEnabled by rememberUpdatedState(enabled)
    val currentOnSilhouette by rememberUpdatedState(onSilhouette)
    val currentOnLoadFailed by rememberUpdatedState(onLoadFailed)
    val motionBinding = remember { RiveMotionBinding() }
    var riveView by remember { mutableStateOf<View?>(null) }
    DisposableEffect(riveView) {
        val view = riveView as? RiveAnimationView
        onDispose {
            runCatching { view?.pause() }
            if (motionBinding.view === view) {
                motionBinding.view = null
                motionBinding.lastEnabled = null
            }
        }
    }
    // Aura Rev 2 — the flames follow the rig: the rendered artboard's alpha is sampled every
    // few frames and turned into the silhouette the aura wraps.
    LaunchedEffect(riveView, enabled) {
        if (!enabled) return@LaunchedEffect
        val view = riveView as? TextureView ?: return@LaunchedEffect
        // Composition effects and their cancellation cleanup run on the main dispatcher.
        val sampler = VanRiveSilhouetteSampler()
        var last = 0L
        try {
            while (true) {
                val now = withFrameNanos { it }
                if (!currentEnabled) break
                if (now - last < VanRiveSilhouetteSampler.INTERVAL_NANOS) continue
                last = now
                sampler.sample(view)?.let { currentOnSilhouette(it) }
            }
        } finally {
            sampler.recycle()
        }
    }
    AndroidView(
        modifier = modifier.vanLivePointingAnchor(ready = riveView is RiveAnimationView),
        factory = { ctx ->
            try {
                VanRiveRuntime.ensure(ctx.applicationContext)
                VanBoundedRiveView(ctx).apply {
                    onNativeFailure = { currentOnLoadFailed() }
                    val bytes = ctx.assets.open(RiveBindingContract.ASSET_FILE).use { VanAssetReadLimits.read(it, VanAssetReadLimits.RIVE_BYTES) }
                    val metadata = runCatching {
                        ctx.assets.open(VanRiveContextCapabilities.ASSET_FILE).use { VanAssetReadLimits.read(it, VanAssetReadLimits.CONTEXT_BYTES).toString(Charsets.UTF_8) }
                    }.getOrNull()
                    motionBinding.contextCodes = VanRiveContextCapabilities.resolve(bytes, metadata)
                    setRiveBytes(
                        bytes,
                        artboardName = RiveBindingContract.ARTBOARD,
                        stateMachineName = RiveBindingContract.STATE_MACHINE,
                        animationName = null,
                        autoplay = currentEnabled,
                        fit = Fit.CONTAIN,
                        alignment = app.rive.runtime.kotlin.core.Alignment.CENTER,
                        loop = Loop.LOOP,
                    )
                }.also {
                    motionBinding.view = it
                    motionBinding.lastEnabled = currentEnabled
                    riveView = it
                }
            } catch (_: Throwable) {
                currentOnLoadFailed()
                View(ctx)
            }
        },
        update = { view ->
            if (view is RiveAnimationView) {
                try {
                    if (motionBinding.view !== view) {
                        motionBinding.view = view
                        motionBinding.lastEnabled = null
                        motionBinding.updates.reset()
                    }
                    val update = motionBinding.updates.next(rendered, animate, enabled)
                    (view as? VanBoundedRiveView)?.prepareDraw(animate, enabled, update != null)
                    if (update != null) {
                        applyVisualState(view, update, motionBinding.contextCodes)
                        if (enabled && motionBinding.lastEnabled != true) {
                            view.play(
                                loop = Loop.AUTO,
                                direction = Direction.AUTO,
                                settleInitialState = true,
                            )
                        }
                    }
                    motionBinding.lastEnabled = enabled
                    // Hidden compositions are stopped immediately. Visible still-mode
                    // inputs get one bounded native pose draw before its own pause.
                    if (!animate) view.pause()
                } catch (_: Throwable) {
                    runCatching { view.pause() }
                    motionBinding.lastEnabled = false
                    currentOnLoadFailed()
                }
            }
        },
    )
}

/** Composition-owned tracking, bound to the actual Android view rather than global state. */
private class RiveMotionBinding {
    var view: RiveAnimationView? = null
    var lastEnabled: Boolean? = null
    var contextCodes: Set<Int> = emptySet()
    val updates = VanRiveUpdateGate()
}

private fun applyVisualState(view: RiveAnimationView, state: VanVisualState, contexts: Set<Int>) {
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
            VanInput.ACTION_CODE -> view.setNumberState(sm, input.wireName, VanRiveContextCapabilities.actionCode((value as Number).toInt(), state.contextCode, contexts).toFloat())
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

    /** Called on main after the sampling coroutine has stopped using the bitmap. */
    fun recycle() {
        if (!bitmap.isRecycled) bitmap.recycle()
    }

    companion object {
        const val GRID = 48
        const val INTERVAL_NANOS = 83_000_000L
    }
}
