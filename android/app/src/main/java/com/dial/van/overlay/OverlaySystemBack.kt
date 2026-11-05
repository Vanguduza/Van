package com.dial.van.overlay

import android.os.Build
import android.view.View
import android.window.OnBackInvokedCallback
import android.window.OnBackInvokedDispatcher
import androidx.annotation.RequiresApi
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.platform.LocalView

/** System Back on VAN's OWN focused window; IME keeps first refusal. */
@Composable
internal fun BindOverlaySystemBack(isWorkboard: Boolean, keyboardVisible: Boolean, dismiss: () -> Unit) {
    val view = LocalView.current
    val currentDismiss by rememberUpdatedState(dismiss)
    DisposableEffect(view, isWorkboard, keyboardVisible) {
        val bound = if (Build.VERSION.SDK_INT >= 33 && isWorkboard && !keyboardVisible)
            NativeBackBinding(view) { currentDismiss() }.also { it.attach() } else null
        onDispose { bound?.close() }
    }
}

@RequiresApi(33)
private class NativeBackBinding(private val view: View, private val dismiss: () -> Unit) : View.OnAttachStateChangeListener {
    private var dispatcher: OnBackInvokedDispatcher? = null
    private val callback = OnBackInvokedCallback { dismiss() }
    fun attach() { view.addOnAttachStateChangeListener(this); register() }
    private fun register() {
        if (!view.isAttachedToWindow || dispatcher != null) return
        view.findOnBackInvokedDispatcher()?.let {
            it.registerOnBackInvokedCallback(OnBackInvokedDispatcher.PRIORITY_DEFAULT, callback)
            dispatcher = it
        }
    }
    override fun onViewAttachedToWindow(v: View) = register()
    override fun onViewDetachedFromWindow(v: View) = release()
    private fun release() { dispatcher?.unregisterOnBackInvokedCallback(callback); dispatcher = null }
    fun close() { view.removeOnAttachStateChangeListener(this); release() }
}
