package com.dial.van.muse

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.Manifest
import androidx.core.content.ContextCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.dial.van.command.CommandCentreActivity
import com.dial.van.command.nav.VanRoute
import org.json.JSONObject

/** Uses VAN's existing authenticated application event stream; no extra background poller. */
object MuseNotifications {
    private const val CHANNEL = "van_muse_work"
    fun onEvent(context: Context, type: String, payload: String) {
        if (!type.startsWith("muse.")) return
        val data = runCatching { JSONObject(payload) }.getOrNull() ?: return
        val eventTime = data.optLong("observed_at_ms")
        if (eventTime <= 0 || System.currentTimeMillis() - eventTime !in 0..300_000L) return
        val key = data.optString("approval_id").ifBlank { data.optString("command_id", "muse-watchdog") }
        val manager = NotificationManagerCompat.from(context)
        val id = key.hashCode()
        if (type == "muse.command_changed" && data.optString("state") in setOf("CONFIRMED", "REJECTED", "EXPIRED")) {
            manager.cancel(key, 0); return
        }
        val title = when {
            type in setOf("muse.approval_requested", "muse.owner_verification_required") && data.optLong("expires_at_epoch_ms") > System.currentTimeMillis() -> "Muse needs your decision"
            type == "muse.watchdog_changed" && data.optString("watchdog") != "GREEN" -> "Muse needs attention"
            type == "muse.command_changed" && data.optString("state") == "UNKNOWN" -> "Check a Muse interaction"
            else -> return
        }
        val system = context.getSystemService(NotificationManager::class.java)
        system.createNotificationChannel(NotificationChannel(CHANNEL, "Muse work and decisions", NotificationManager.IMPORTANCE_HIGH))
        if (!manager.areNotificationsEnabled()) return
        // POST_NOTIFICATIONS is revocable on Android 13+. The notification listener
        // must not attempt a notification without the owner's runtime permission.
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(
            context, Manifest.permission.POST_NOTIFICATIONS,
        ) != PackageManager.PERMISSION_GRANTED) return
        val intent = CommandCentreActivity.deepLinkIntent(context, if (data.optString("approval_id").isBlank()) VanRoute.WORK_MUSE else VanRoute.museApprovalRoute(data.optString("approval_id")))
            .setAction("com.dial.van.MUSE_UPDATE." + key)
            .putExtra("muse_approval_id", data.optString("approval_id"))
        val pending = PendingIntent.getActivity(context, id, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText("Open VAN to review the current task. No action runs from this notification.")
            .setContentIntent(pending).setAutoCancel(true)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setCategory(NotificationCompat.CATEGORY_STATUS).build()
        // Permission remains owner-managed; no system settings are changed here.
        runCatching { manager.notify(key, 0, notification) }
    }
}
