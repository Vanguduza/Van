package com.dial.van.onboarding

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.biometric.BiometricManager
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.edit
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.dial.van.VanApplication
import com.dial.van.command.CommandCentreActivity
import com.dial.van.notification.VanNotificationListenerService
import com.dial.van.overlay.FloatingOverlayService
import com.dial.van.overlay.VanObstructionAccessibilityService
import com.dial.van.visual.VanTheme

/**
 * Optional Android permission review, opened from Settings.
 *
 * Enrollment is completed by the signed installer. Launching VAN always opens the
 * Command Centre; this activity never asks the owner for connection or pairing data.
 * Permission advancement still depends on observed OS grants, never on firing an intent.
 */
class OnboardingActivity : FragmentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!intent.getBooleanExtra(EXTRA_REVIEW_PERMISSIONS, false)) {
            navigateToCommandCentre()
            return
        }

        setContent {
            VanTheme {
                OnboardingFlow(onComplete = {
                    markOnboardingComplete()
                    FloatingOverlayService.start(this)
                    navigateToCommandCentre()
                })
            }
        }
    }

    private fun markOnboardingComplete() {
        getSharedPreferences(PREFS, MODE_PRIVATE).edit { putBoolean(KEY_COMPLETE, true) }
    }

    private fun navigateToCommandCentre() {
        startActivity(Intent(this, CommandCentreActivity::class.java))
        finish()
    }

    companion object {
        const val EXTRA_REVIEW_PERMISSIONS = "review_permissions"
        private const val PREFS = "van_onboarding"
        private const val KEY_COMPLETE = "complete"
    }
}

/** Read what the device actually reports. Never what an intent was fired for. */
internal fun readGrants(context: Context): OnboardingGrants = OnboardingGrants(
    overlayGranted = Settings.canDrawOverlays(context),
    displayAwarenessEnabled = VanObstructionAccessibilityService.isEnabled(context),
    notificationsGranted = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
        ContextCompat.checkSelfPermission(
            context, Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED,
    notificationsNotApplicable = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU,
    notificationListenerEnabled = notificationListenerEnabled(context),
    microphoneGranted = ContextCompat.checkSelfPermission(
        context, Manifest.permission.RECORD_AUDIO,
    ) == PackageManager.PERMISSION_GRANTED,
    biometricAvailable = BiometricManager.from(context)
        .canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG) ==
        BiometricManager.BIOMETRIC_SUCCESS,
)

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

@Composable
private fun OnboardingFlow(onComplete: () -> Unit) {
    val context = LocalContext.current
    val app = context.applicationContext as VanApplication
    val scroll = rememberScrollState()

    // P3-AND-007 — survives rotation. Which optional steps the owner chose to pass is a
    // decision they made, and making them make it again is how a flow gets abandoned.
    // A List, not a Set: `rememberSaveable`'s default saver stores into a Bundle, and a
    // Set is not something a Bundle can hold — it would throw the first time the owner
    // rotated the phone on an optional step.
    var skipped by rememberSaveable { mutableStateOf(emptyList<String>()) }
    var grants by remember { mutableStateOf(readGrants(context)) }

    fun refresh() {
        grants = readGrants(context)
    }

    // The re-check that was missing. A permission granted in system settings and returned
    // from used to still show as pending, because nothing looked again.
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) refresh()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    val notificationLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { refresh() }

    val micLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { refresh() }

    val step = OnboardingPlan.currentStep(
        grants,
        skipped = skipped.mapNotNull { id -> OnboardingStep.entries.firstOrNull { it.id == id } }.toSet(),
    )
    val view = OnboardingPlan.view(step, grants)

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(scroll)
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Phone permissions", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Review the Android permissions used by Floating VAN, voice and notifications. " +
                "Each feature starts only after Android confirms its permission.",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        TextButton(onClick = {
            (context as? android.app.Activity)?.let { activity ->
                activity.startActivity(Intent(activity, CommandCentreActivity::class.java))
                activity.finish()
            }
        }) { Text("Back to VAN") }

        if (step == OnboardingStep.DONE) {
            Text(view.title, style = MaterialTheme.typography.titleMedium)
            Text(view.body)
            val blockers = OnboardingPlan.blockers(grants)
            if (blockers.isEmpty()) {
                Button(onClick = onComplete, modifier = Modifier.fillMaxWidth()) {
                    Text(view.button)
                }
            } else {
                // Unreachable while `currentStep` and `mayComplete` agree, and written
                // anyway: the old flow's whole failure was a "you're set" screen appearing
                // over an unpaired phone.
                Text(
                    "Not quite: " + blockers.joinToString { OnboardingPlan.view(it, grants).title },
                    color = MaterialTheme.colorScheme.error,
                )
            }
            return@Column
        }

        StepCard(
            title = view.title,
            body = view.body,
            button = view.button,
            skippable = view.skippable,
            onSkip = { skipped = (skipped + step.id).distinct() },
            onClick = {
                when (step) {
                    OnboardingStep.OVERLAY -> context.startActivity(
                        Intent(
                            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                            Uri.parse("package:${context.packageName}"),
                        ),
                    )
                    OnboardingStep.DISPLAY_AWARENESS ->
                        context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                    OnboardingStep.NOTIFICATIONS ->
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                            notificationLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                        } else {
                            refresh()
                        }
                    OnboardingStep.NOTIFICATION_LISTENER ->
                        context.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                    OnboardingStep.MICROPHONE -> micLauncher.launch(Manifest.permission.RECORD_AUDIO)
                    OnboardingStep.BIOMETRIC ->
                        context.startActivity(Intent(Settings.ACTION_SECURITY_SETTINGS))
                    OnboardingStep.DONE -> Unit
                }
                // Note what is NOT here: a step counter. The next recomposition asks the
                // device again, so firing an intent advances nothing by itself.
            },
        )
    }
}

@Composable
private fun StepCard(
    title: String,
    body: String,
    button: String,
    skippable: Boolean,
    onSkip: () -> Unit,
    onClick: () -> Unit,
    content: @Composable () -> Unit = {},
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(8.dp))
            Text(body, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(modifier = Modifier.height(12.dp))
            content()
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onClick) { Text(button) }
                if (skippable) {
                    TextButton(onClick = onSkip) { Text("Not now") }
                }
            }
        }
    }
}
