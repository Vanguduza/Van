package com.dial.van.visual

import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.compose.ui.platform.LocalLifecycleOwner
import java.util.concurrent.atomic.AtomicLong

/** Observes only VAN's own resumed navigation destination, never external app content. */
object VanNativeScreenContext {
    private val state = VanScreenLease()
    val current: VanOwnedScreen? get() = state.screen
    internal fun observe(lease: Long, route: String) = state.observe(lease, route)
    internal fun clear(lease: Long) = state.clear(lease)
}

private val screenInstances = AtomicLong()

@Composable
fun ObserveVanOwnedScreen(route: String) {
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val lease = remember(lifecycle) { screenInstances.incrementAndGet() }
    DisposableEffect(lifecycle, route, lease) {
        fun refresh() {
            if (lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) VanNativeScreenContext.observe(lease, route)
            else VanNativeScreenContext.clear(lease)
        }
        val observer = LifecycleEventObserver { _, _ -> refresh() }
        lifecycle.addObserver(observer); refresh()
        onDispose { lifecycle.removeObserver(observer); VanNativeScreenContext.clear(lease) }
    }
}
