package com.dial.van.overlay

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Settings

/** Restores overlay after process death / reboot when persisted state indicates it was running. */
class OverlayRecoveryReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED &&
            intent.action != Intent.ACTION_MY_PACKAGE_REPLACED
        ) return
        OverlayRecovery.restoreIfOwnerHadItOn(context)
    }
}

/**
 * The one rule both recovery paths share: bring Floating VAN back only if the owner left it on.
 *
 * A reboot reaches it through [OverlayRecoveryReceiver]. A force-stop (or a low-memory kill)
 * does not: it skips `onDestroy`, so the persisted state still says "running", and no broadcast
 * follows. Before the pre-device audit the only way back from that was Settings › Start, so the
 * checklist's `process_kill` row could not pass. Opening VAN now restores it too
 * (`CommandCentreActivity.onResume`). Stopping the overlay deliberately persists `false`, so
 * this never overrides the owner.
 */
internal object OverlayRecovery {
    fun restoreIfOwnerHadItOn(context: Context): Boolean {
        if (FloatingOverlayService.isRunning() || !Settings.canDrawOverlays(context)) return false
        val metrics = context.resources.displayMetrics
        val state = OverlayStateStore(context).load(metrics.widthPixels / 2, metrics.heightPixels / 3)
        if (!state.serviceRunning) return false
        return runCatching { FloatingOverlayService.start(context) }.isSuccess
    }
}
