package com.dial.van.voice

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.Manifest
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import com.dial.van.VanApplication

/**
 * Holds the microphone while VAN listens for its name (P1-VOICE-001).
 *
 * Its own service, typed `microphone`, rather than a job inside the overlay's `specialUse`
 * service. Two reasons, and the second is the one that bites: they are two jobs with
 * different lifetimes — the overlay is visible while the phone is awake, the wake listener
 * should be able to outlive it — and a service that holds the microphone while declaring
 * `specialUse` loses microphone access on Android 14 while believing it has it.
 *
 * It refuses to start without a usable wake model. Starting a foreground service that holds
 * the microphone and can never wake is worse than not starting: it costs the owner battery,
 * shows them a persistent notification, and does nothing.
 */
class WakeListenerService : Service() {

    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val app = application as VanApplication
        val status = app.wakeModel.status()
        if (!status.ready) {
            // The owner has already been told why through the degraded-subsystem list;
            // holding their microphone as well would add insult.
            stopSelf()
            return START_NOT_STICKY
        }
        startForegroundCompat(status.sentence)
        if (running) return START_STICKY
        if (!app.wakeCoordinator.arm()) {
            // `arm()` has published the reason — no acknowledgement asset, no microphone
            // permission, capture unavailable — through the coordinator's status callback.
            stopSelf()
            return START_NOT_STICKY
        }
        running = true
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        runCatching { (application as VanApplication).wakeCoordinator.disarm(stopCapture = true) }
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startForegroundCompat(text: String) {
        val notification: Notification = Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("VAN")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE,
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun createChannel() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "VAN wake word", NotificationManager.IMPORTANCE_LOW),
        )
    }

    companion object {
        private const val CHANNEL_ID = "van_wake_listener"
        private const val NOTIFICATION_ID = 0x7A11

        /** Set while the coordinator is armed by this service; re-arming mid-turn would drop the turn. */
        @Volatile
        private var running: Boolean = false

        fun start(context: Context) {
            context.startForegroundService(Intent(context, WakeListenerService::class.java))
        }

        /**
         * The production caller (P1-VOICE-001). Nothing started this service before, so a
         * device with a correct wake bundle still never listened for its name.
         *
         * Called from a visible activity, because a `microphone` foreground service may not
         * be started from the background on Android 14+. Starts nothing without a usable
         * wake model or the microphone grant, and never re-arms a listener that is already
         * armed. Returns whether a start was requested.
         */
        fun startIfReady(context: Context): Boolean {
            if (running) return false
            val app = context.applicationContext as? VanApplication ?: return false
            if (!app.wakeModel.status().ready) return false
            if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) !=
                PackageManager.PERMISSION_GRANTED
            ) return false
            // ForegroundServiceStartNotAllowedException if the activity is already leaving
            // the foreground; the next resume tries again.
            return runCatching { start(context) }.isSuccess
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, WakeListenerService::class.java))
        }
    }
}
