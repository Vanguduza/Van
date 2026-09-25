package com.dial.van.degraded

import com.dial.van.onboarding.AskTrigger
import com.dial.van.onboarding.VanAsks
import com.dial.van.onboarding.VanPermission
import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import android.speech.SpeechRecognizer
import androidx.biometric.BiometricManager
import androidx.core.content.ContextCompat
import com.dial.van.VanApplication
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import com.dial.van.notification.VanNotificationListenerService
import com.dial.van.overlay.FloatingOverlayService

/**
 * The device facts behind [SubsystemSignals], and the buttons that change them.
 *
 * P3-AND-004 — `overlay`, `queue`, `notifications`, `voice` and `biometric` were in
 * `DegradedMode.defaultSubsystems()` and nothing anywhere called `markBroken` or
 * `markWorking` for any of them. Every one reported WORKING on a phone that had granted
 * nothing. This file is the missing producer; `SubsystemHealth` is the rule it feeds, and
 * that rule is pure and executed in `android/verification`.
 *
 * P3-AND-005 — [perform] is the missing consumer on the other side: the seven
 * `RestoreAction` values had no code path that acted on any of them.
 */
object DeviceSignals {

    fun read(app: VanApplication): SubsystemSignals {
        val context: Context = app
        return SubsystemSignals(
            overlayPermissionGranted = Settings.canDrawOverlays(context),
            overlayRunning = FloatingOverlayService.isRunning(),
            queuedCommands = runCatching { app.commandQueue.size() }.getOrDefault(0),
            queueReplayFailures = app.queueReplayer.consecutiveFailures(),
            notificationListenerConnected = notificationListenerEnabled(context),
            microphonePermissionGranted = ContextCompat.checkSelfPermission(
                context, Manifest.permission.RECORD_AUDIO,
            ) == PackageManager.PERMISSION_GRANTED,
            speechRecognitionAvailable = SpeechRecognizer.isRecognitionAvailable(context),
            strongBiometricAvailable = biometricStatus(context) != BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE &&
                biometricStatus(context) != BiometricManager.BIOMETRIC_ERROR_HW_UNAVAILABLE,
            biometricEnrolled = biometricStatus(context) == BiometricManager.BIOMETRIC_SUCCESS,
        )
    }

    /** Push what the device reports into the store the health screens read. */
    fun publish(app: VanApplication) {
        for (verdict in SubsystemHealth.evaluate(read(app))) {
            when (verdict.status) {
                SubsystemStatus.WORKING -> app.degradedModeStore.markWorking(verdict.id)
                else -> app.degradedModeStore.mark(
                    verdict.id, verdict.status, verdict.detail, verdict.restoreAction,
                )
            }
        }
    }

    /**
     * Do what the button says.
     *
     * Returns false when there is nothing this app can do from here — `CONTACT_SUPPORT` is
     * the honest case, and pretending to act on it would be worse than saying so.
     */
    fun perform(context: Context, app: VanApplication, subsystem: DegradedSubsystem): Boolean =
        when (subsystem.restoreAction) {
            RestoreAction.OPEN_SETTINGS -> {
                // The owner pressed the button, so VAN asks in his own words and then takes
                // them to the page; anything that is not one of his permissions opens as before.
                val permission = askablePermission(subsystem.id)
                if (permission == null ||
                    !VanAsks.askIfNeeded(context, permission, AskTrigger.OWNER_REACHED_FOR_IT)
                ) {
                    context.startActivity(settingsIntentFor(context, subsystem.id))
                }
                true
            }
            RestoreAction.REQUEST_PERMISSION -> {
                // A runtime permission has to be asked for by an Activity; from here the
                // honest destination is the app's own permission page, which is also where
                // the owner ends up if they have already denied twice.
                context.startActivity(appDetails(context))
                true
            }
            RestoreAction.RETRY_CONNECTION -> {
                app.requestReplay()
                true
            }
            RestoreAction.CLEAR_QUEUE -> {
                // Off the thread that handled the tap. The queue commits synchronously so
                // the outbox's "saved" is true when said, which makes this an encrypted
                // disk write — and this one is reached from a button on a screen.
                app.appScope.launch(Dispatchers.IO) {
                    app.commandQueue.clear()
                    publish(app)
                }
                true
            }
            RestoreAction.RESTART_OVERLAY -> {
                FloatingOverlayService.start(context)
                true
            }
            RestoreAction.CONTACT_SUPPORT, RestoreAction.NONE -> false
        }

    private fun askablePermission(subsystemId: String): VanPermission? = when (subsystemId) {
        "overlay" -> VanPermission.OVERLAY
        "notifications" -> VanPermission.NOTIFICATION_LISTENER
        "biometric" -> VanPermission.BIOMETRIC
        else -> null
    }

    private fun settingsIntentFor(context: Context, subsystemId: String): Intent = when (subsystemId) {
        "overlay" -> Intent(
            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
            Uri.parse("package:${context.packageName}"),
        )
        "notifications" -> Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
        "biometric" -> Intent(Settings.ACTION_SECURITY_SETTINGS)
        else -> appDetails(context)
    }.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    private fun appDetails(context: Context): Intent = Intent(
        Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
        Uri.parse("package:${context.packageName}"),
    ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    private fun biometricStatus(context: Context): Int =
        BiometricManager.from(context)
            .canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG)

    private fun notificationListenerEnabled(context: Context): Boolean {
        val flat = Settings.Secure.getString(
            context.contentResolver, "enabled_notification_listeners",
        ).orEmpty()
        val mine = ComponentName(context, VanNotificationListenerService::class.java)
        return flat.split(':').any {
            val parsed = ComponentName.unflattenFromString(it)
            parsed != null && parsed.packageName == mine.packageName &&
                parsed.className == mine.className
        }
    }
}
