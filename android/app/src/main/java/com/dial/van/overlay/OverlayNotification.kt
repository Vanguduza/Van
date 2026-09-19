package com.dial.van.overlay

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import com.dial.van.R
import com.dial.van.command.CommandCentreActivity

/**
 * The ongoing notification the overlay's foreground service posts.
 *
 * P3-AND-009. Its own file because it is its own concern: the channel, the text the owner
 * reads in their shade, and where tapping it goes. It was fifty lines inside a class that
 * was already a window manager, a drag controller and a Compose tree.
 */
internal object OverlayNotification {

    const val CHANNEL_ID = "van_overlay"

    fun build(context: Context): Notification {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(
            // IMPORTANCE_LOW: the overlay is visible on screen, so a sound or a heads-up
            // for the notification that says so is VAN interrupting the owner to tell them
            // it is there.
            NotificationChannel(CHANNEL_ID, "Van overlay", NotificationManager.IMPORTANCE_LOW),
        )
        val pending = PendingIntent.getActivity(
            context,
            0,
            Intent(context, CommandCentreActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(context, CHANNEL_ID)
            .setContentTitle(context.getString(R.string.overlay_notification_title))
            .setContentText(context.getString(R.string.overlay_notification_body))
            .setSmallIcon(R.drawable.ic_van_notification)
            .setContentIntent(pending)
            .setOngoing(true)
            .build()
    }
}
