package com.dial.van.overlay

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Restores overlay after process death / reboot when persisted state indicates it was running. */
class OverlayRecoveryReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED &&
            intent.action != Intent.ACTION_MY_PACKAGE_REPLACED
        ) return
        val store = OverlayStateStore(context)
        val metrics = context.resources.displayMetrics
        val state = store.load(metrics.widthPixels / 2, metrics.heightPixels / 3)
        if (state.serviceRunning) {
            FloatingOverlayService.start(context)
        }
    }
}
