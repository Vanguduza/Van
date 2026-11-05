package com.dial.van.visual

import android.view.View
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.layout.LayoutCoordinates
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.findRootCoordinates
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalView
import java.util.concurrent.atomic.AtomicLong

class VanGuidanceBinding internal constructor(val modifier: Modifier, val point: () -> Unit)

private val leases = AtomicLong(1)
private class LayoutProbe(val view: View) {
    var coordinates: LayoutCoordinates? = null
    fun measure(ready: Boolean = true): VanOwnedLayout? {
        val c = coordinates?.takeIf { it.isAttached } ?: return null
        if (!view.isAttachedToWindow || !view.isShown || view.windowVisibility != View.VISIBLE) return null
        val b = c.boundsInWindow(); val v = c.findRootCoordinates().boundsInWindow()
        val origin = c.localToWindow(Offset.Zero)
        val fullArea = c.size.width.toFloat() * c.size.height.toFloat()
        val visibleArea = b.width * b.height
        val enoughVisible = origin.x.isFinite() && origin.y.isFinite() && fullArea > 0f && visibleArea >= fullArea * 0.5f
        return VanOwnedLayout("van-window-${System.identityHashCode(view.rootView)}",
            VanOwnedRect(b.left, b.top, b.right, b.bottom),
            VanOwnedRect(v.left, v.top, v.right, v.bottom), ready && enoughVisible)
    }
}

/** Attach to existing controls, not an accessibility crawler or a second UI. */
@Composable
fun rememberVanGuidanceTarget(id: String): VanGuidanceBinding {
    val view = LocalView.current
    val lease = remember(view, id) { leases.incrementAndGet() }
    val probe = remember(view, lease) { LayoutProbe(view) }
    DisposableEffect(lease, id) {
        VanLivePointing.registerTarget(id, lease) { probe.measure() }
        onDispose { VanLivePointing.unregisterTarget(id, lease); probe.coordinates = null }
    }
    return remember(id, lease) {
        VanGuidanceBinding(Modifier.onGloballyPositioned {
            probe.coordinates = it; VanLivePointing.changed(id)
        }, point = { VanLivePointing.pointAt(id) })
    }
}

/** Only a loaded real Rive renderer registers the arm's artboard-to-window map. */
@Composable
fun Modifier.vanLivePointingAnchor(ready: Boolean): Modifier {
    val view = LocalView.current
    val lease = remember(view) { leases.incrementAndGet() }
    val probe = remember(view, lease) { LayoutProbe(view) }
    val currentReady = rememberUpdatedState(ready)
    DisposableEffect(lease) {
        VanLivePointing.registerAvatar(lease) { probe.measure(currentReady.value) }
        onDispose { VanLivePointing.unregisterAvatar(lease); probe.coordinates = null }
    }
    LaunchedEffect(ready) { VanLivePointing.changed(null) }
    return this.onGloballyPositioned { probe.coordinates = it; VanLivePointing.changed(null) }
}
