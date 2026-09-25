package com.dial.van.onboarding

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.biometric.BiometricManager
import androidx.core.content.ContextCompat
import androidx.core.content.edit
import com.dial.van.notification.VanNotificationListenerService
import com.dial.van.overlay.VanObstructionAccessibilityService

/**
 * The device side of [VanAskPlan]: what Android reports, what the owner said "not now" to,
 * and how VAN's ask screen is opened.
 *
 * A grant is always read from the device here, never remembered — the P1-AND-002 finding
 * that a flow advancing on a fired intent tells the owner they are set when they are not.
 */
object VanAsks {

    private const val PREFS = "van_asks"
    private const val KEY_DECLINED = "declined"
    private const val KEY_MET = "met"

    fun isGranted(context: Context, permission: VanPermission): Boolean = when (permission) {
        VanPermission.OVERLAY -> Settings.canDrawOverlays(context)
        VanPermission.NOTIFICATIONS -> Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            runtimeGranted(context, Manifest.permission.POST_NOTIFICATIONS)
        VanPermission.MICROPHONE -> runtimeGranted(context, Manifest.permission.RECORD_AUDIO)
        VanPermission.DISPLAY_AWARENESS -> VanObstructionAccessibilityService.isEnabled(context)
        VanPermission.NOTIFICATION_LISTENER -> notificationListenerEnabled(context)
        VanPermission.BIOMETRIC -> BiometricManager.from(context)
            .canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG) ==
            BiometricManager.BIOMETRIC_SUCCESS
    }

    /** The system surface for permissions Android only grants on its own settings pages. */
    fun settingsIntent(context: Context, permission: VanPermission): Intent? = when (permission) {
        VanPermission.OVERLAY -> Intent(
            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
            Uri.parse("package:${context.packageName}"),
        )
        VanPermission.DISPLAY_AWARENESS -> Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
        VanPermission.NOTIFICATION_LISTENER -> Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
        VanPermission.BIOMETRIC -> Intent(Settings.ACTION_BIOMETRIC_ENROLL).putExtra(
            Settings.EXTRA_BIOMETRIC_AUTHENTICATORS_ALLOWED,
            BiometricManager.Authenticators.BIOMETRIC_STRONG,
        )
        VanPermission.NOTIFICATIONS, VanPermission.MICROPHONE -> null
    }

    /** The runtime permission name, for the two Android grants through its own prompt. */
    fun runtimePermission(permission: VanPermission): String? = when (permission) {
        VanPermission.MICROPHONE -> Manifest.permission.RECORD_AUDIO
        VanPermission.NOTIFICATIONS -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.POST_NOTIFICATIONS
        } else {
            null
        }
        else -> null
    }

    fun isDeclined(context: Context, permission: VanPermission): Boolean =
        permission.id in prefs(context).getStringSet(KEY_DECLINED, emptySet()).orEmpty()

    fun markDeclined(context: Context, permission: VanPermission) {
        val now = prefs(context).getStringSet(KEY_DECLINED, emptySet()).orEmpty() + permission.id
        prefs(context).edit { putStringSet(KEY_DECLINED, now) }
    }

    /** Whether the owner has met VAN on this install: "Hi, I'm VAN." once, then "Welcome back." */
    fun hasMet(context: Context): Boolean = prefs(context).getBoolean(KEY_MET, false)

    fun markMet(context: Context) {
        prefs(context).edit { putBoolean(KEY_MET, true) }
    }

    /**
     * Opens VAN's ask screen if [VanAskPlan.shouldAsk] says to, and returns whether it did.
     * Safe from a service: the overlay holds SYSTEM_ALERT_WINDOW, which Android lets start
     * an activity from the background.
     */
    fun askIfNeeded(context: Context, permission: VanPermission, trigger: AskTrigger): Boolean {
        val ask = VanAskPlan.shouldAsk(
            granted = isGranted(context, permission),
            declined = isDeclined(context, permission),
            trigger = trigger,
        )
        if (ask) {
            context.startActivity(
                VanAskActivity.intent(context, permission).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        }
        return ask
    }

    /**
     * The owner tapped Voice. Without the microphone VAN asks for it instead of opening a
     * voice board that cannot hear; returns whether he did (the caller then stops there).
     */
    fun askForVoice(context: Context): Boolean =
        askIfNeeded(context, VanPermission.MICROPHONE, AskTrigger.OWNER_REACHED_FOR_IT)

    private fun runtimeGranted(context: Context, name: String): Boolean =
        ContextCompat.checkSelfPermission(context, name) == PackageManager.PERMISSION_GRANTED

    private fun notificationListenerEnabled(context: Context): Boolean {
        val flat = Settings.Secure.getString(
            context.contentResolver, "enabled_notification_listeners",
        ).orEmpty()
        val mine = ComponentName(context, VanNotificationListenerService::class.java)
        return flat.split(':').any {
            val parsed = ComponentName.unflattenFromString(it)
            parsed != null && parsed.packageName == mine.packageName && parsed.className == mine.className
        }
    }

    private fun prefs(context: Context) =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
