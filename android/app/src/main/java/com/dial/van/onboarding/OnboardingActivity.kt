package com.dial.van.onboarding

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.edit
import androidx.fragment.app.FragmentActivity
import com.dial.van.command.CommandCentreActivity
import com.dial.van.overlay.FloatingOverlayService
import com.dial.van.overlay.OverlayStateStore

class OnboardingActivity : FragmentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (isOnboardingComplete()) {
            navigateToCommandCentre()
            return
        }

        setContent {
            MaterialTheme(colorScheme = darkColorScheme(primary = Color(0xFF00E5FF))) {
                OnboardingFlow(onComplete = {
                    markOnboardingComplete()
                    FloatingOverlayService.start(this)
                    navigateToCommandCentre()
                })
            }
        }
    }

    private fun isOnboardingComplete(): Boolean =
        getSharedPreferences(PREFS, MODE_PRIVATE).getBoolean(KEY_COMPLETE, false)

    private fun markOnboardingComplete() {
        getSharedPreferences(PREFS, MODE_PRIVATE).edit { putBoolean(KEY_COMPLETE, true) }
    }

    private fun navigateToCommandCentre() {
        startActivity(Intent(this, CommandCentreActivity::class.java))
        finish()
    }

    companion object {
        private const val PREFS = "van_onboarding"
        private const val KEY_COMPLETE = "complete"
    }
}

@Composable
private fun OnboardingFlow(onComplete: () -> Unit) {
    val context = LocalContext.current
    val step = remember { mutableIntStateOf(0) }
    val scroll = rememberScrollState()

    val notificationLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { step.intValue++ }

    val micLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { step.intValue++ }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(scroll)
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Welcome to Van", style = MaterialTheme.typography.headlineMedium)
        Text("DIAL owner assistant — embodiment, offline queue, and overlay UI. Hermes profile van owns agent execution.")

        when (step.intValue) {
            0 -> PermissionCard(
                title = "Overlay permission",
                body = "Van needs overlay access for the draggable avatar and quick actions.",
                button = "Grant overlay",
                onClick = {
                    context.startActivity(
                        Intent(
                            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                            Uri.parse("package:${context.packageName}"),
                        ),
                    )
                    step.intValue++
                },
            )
            1 -> PermissionCard(
                title = "Notifications",
                body = "Post notifications for the foreground overlay service (Android 13+).",
                button = "Allow notifications",
                onClick = {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                        notificationLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                    } else step.intValue++
                },
            )
            2 -> PermissionCard(
                title = "Notification listener",
                body = "Optional: ingest notification context with OTP/secret redaction before upload. Enable in system settings.",
                button = "Open listener settings",
                onClick = {
                    context.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                    step.intValue++
                },
            )
            3 -> PermissionCard(
                title = "Microphone",
                body = "Voice input for owner commands. Transcripts are queued — no embedded agent loop.",
                button = "Allow microphone",
                onClick = { micLauncher.launch(Manifest.permission.RECORD_AUDIO) },
            )
            4 -> PermissionCard(
                title = "Biometric",
                body = "A4 destructive actions require BiometricPrompt owner approval.",
                button = "Continue",
                onClick = { step.intValue++ },
            )
            else -> {
                Text("You're set. Van will restore overlay position after process death (START_STICKY + persisted state).")
                Button(onClick = onComplete, modifier = Modifier.fillMaxWidth()) {
                    Text("Enter Command Centre")
                }
            }
        }
    }
}

@Composable
private fun PermissionCard(title: String, body: String, button: String, onClick: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(8.dp))
            Text(body)
            Spacer(modifier = Modifier.height(12.dp))
            Button(onClick = onClick) { Text(button) }
        }
    }
}
