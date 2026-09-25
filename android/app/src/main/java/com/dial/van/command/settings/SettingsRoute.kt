package com.dial.van.command.settings

import com.dial.van.onboarding.AskTrigger
import com.dial.van.onboarding.VanAsks
import com.dial.van.onboarding.VanPermission
import android.content.Intent
import android.provider.Settings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.fragment.app.FragmentActivity
import com.dial.van.BuildConfig
import com.dial.van.VanApplication
import com.dial.van.command.DegradedPanel
import com.dial.van.command.modules.NotificationPolicyModule
import com.dial.van.command.modules.SpeechModule
import com.dial.van.degraded.DeviceSignals
import com.dial.van.degraded.GatewayDegradedMapping
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanPressable
import com.dial.van.overlay.FloatingOverlayService
import com.dial.van.overlay.VanObstructionAccessibilityService
import com.dial.van.visual.DegradedBridge
import com.dial.van.visual.VanCharacterAcceptance
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanPresence
import com.dial.van.visual.rememberVanEffectBudget
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * DNA §4 destination 8: "Devices & Settings — pairing, permissions, voice, notifications
 * policy, quiet hours, character/renderer status, diagnostics."
 *
 * Voice settings and notification policy are the existing, unowned-by-this-worker-to-rewrite
 * `SpeechModule`/`NotificationPolicyModule` bodies, reached here rather than duplicated —
 * both already do everything DNA §4 asks of them (P2-AND-017/018).
 *
 * @DataSource("GET /v1/degraded") — the diagnostics section (GAP-F-010).
 */
@Composable
fun SettingsRoute(
    app: VanApplication,
    onOpenVoice: () -> Unit,
    onOpenNotifications: () -> Unit,
) {
    val tokens = LocalVanTokens.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val degradedState by app.degradedModeStore.state.collectAsState()
    var gatewayDegraded by remember { mutableStateOf<JSONObject?>(null) }
    var gatewayDegradedError by remember { mutableStateOf<String?>(null) }
    var unfixable by remember { mutableStateOf<String?>(null) }
    var characterAcceptanceStatus by remember { mutableStateOf<String?>(null) }
    val characterAcceptance = remember(context, app.gatewayClient) {
        (context as? FragmentActivity)?.let { VanCharacterAcceptance(it, app.gatewayClient) }
    }

    fun loadDiagnostics() {
        scope.launch {
            runCatching { app.gatewayClient.degraded() }
                .onSuccess { gatewayDegraded = it; gatewayDegradedError = null }
                .onFailure { gatewayDegradedError = it.message ?: "Could not reach the gateway's own diagnostics." }
        }
    }
    LaunchedEffect(Unit) { loadDiagnostics() }

    // GAP-F-014 — the renderer decision `visual/DegradedBridge` publishes, read once per
    // composition; the bridge holds a plain last-value rather than a `StateFlow`, so this is
    // as live as this screen gets without `visual/` growing observable state for it.
    val rendererStatus = DegradedBridge.lastRendererStatus

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
        contentPadding = PaddingValues(vertical = tokens.space.space3),
    ) {
        item { SectionHeader("Settings & Devices", detail = "Connection, permissions, voice, notifications, diagnostics") }

        item {
            VanPanel {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    // A status, never a setup step: this phone is set up by its installer
                    // (ADR-RB-026), and nothing in the app pairs it (owner direction, 2026-09-25).
                    val connected = app.gatewayClient.isPaired()
                    Text("Connection", style = tokens.type.headline, color = tokens.color.textPrimary)
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        StatusChip(
                            label = if (connected) "CONNECTED" else "NOT SET UP",
                            role = if (connected) StatusSemantics.ROLE_FAVOURABLE else StatusSemantics.ROLE_EVENT_RISK,
                        )
                        StatusChip(
                            label = if (app.gatewayClient.hasDeviceIdentity()) "LOCKED TO THIS PHONE" else "NOT LOCKED",
                            role = if (app.gatewayClient.hasDeviceIdentity()) StatusSemantics.ROLE_FAVOURABLE else StatusSemantics.ROLE_EVENT_RISK,
                        )
                    }
                    Text(
                        when {
                            connected -> "VAN is connected to your gateway, with access that can be revoked and a signing key held by this phone."
                            else -> "This phone hasn't been set up for VAN yet. That's done when VAN is installed — there is nothing to enter here."
                        },
                        style = tokens.type.body,
                        color = tokens.color.textSecondary,
                    )
                }
            }
        }

        item {
            VanPanel {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    Text("Floating VAN", style = tokens.type.headline, color = tokens.color.textPrimary)
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Button(onClick = {
                            if (!VanAsks.askIfNeeded(context, VanPermission.OVERLAY, AskTrigger.OWNER_REACHED_FOR_IT)) {
                                FloatingOverlayService.start(app)
                            }
                        }) { Text("Start") }
                        Button(onClick = { FloatingOverlayService.stop(app) }) { Text("Stop") }
                    }
                }
            }
        }

        item {
            VanPanel {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    Text("Display awareness", style = tokens.type.headline, color = tokens.color.textPrimary)
                    val enabled = VanObstructionAccessibilityService.isEnabled(context)
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        StatusChip(
                            label = if (enabled) "ENABLED" else "REQUIRED",
                            role = if (enabled) StatusSemantics.ROLE_FAVOURABLE else StatusSemantics.ROLE_EVENT_RISK,
                        )
                        Button(
                            onClick = {
                                if (!VanAsks.askIfNeeded(context, VanPermission.DISPLAY_AWARENESS, AskTrigger.OWNER_REACHED_FOR_IT)) {
                                    context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                                }
                            },
                        ) { Text(if (enabled) "Review" else "Enable") }
                    }
                    Text(
                        "Window metadata only: this lets Floating VAN move above the keyboard and pause for immersive full-screen apps. VAN does not read accessibility text.",
                        style = tokens.type.body,
                        color = tokens.color.textSecondary,
                    )
                }
            }
        }

        item {
            VanPanel {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                    Text("Character", style = tokens.type.headline, color = tokens.color.textPrimary)
                    Text(
                        rendererStatus?.sentence ?: "VAN has not drawn its embodiment on this device yet.",
                        style = tokens.type.body,
                        color = tokens.color.textSecondary,
                    )
                    characterAcceptanceStatus?.let {
                        Text(it, style = tokens.type.label, color = tokens.color.textSecondary)
                    }
                    Button(
                        enabled = characterAcceptance != null,
                        onClick = { characterAcceptance?.accept { characterAcceptanceStatus = it } },
                    ) { Text("Accept this character asset") }
                    if (BuildConfig.DEBUG) {
                        Button(
                            onClick = {
                                context.startActivity(
                                    Intent().setClassName(
                                        context.packageName,
                                        "com.dial.van.visual.RiveCandidateHostActivity",
                                    ),
                                )
                            },
                        ) { Text("Preview staged candidate") }
                        Button(
                            onClick = {
                                context.startActivity(
                                    Intent().setClassName(
                                        context.packageName,
                                        "com.dial.van.visual.VrmTestModelActivity",
                                    ),
                                )
                            },
                        ) { Text("Test model (VRM)") }
                    }
                }
            }
        }

        item { SectionHeader("Diagnostics") }
        item {
            // P3-AND-005's device-signal rows (overlay/queue/notifications/voice/biometric/
            // hermes/wake_word/google), with the actionable `RestoreAction` this rebuild's
            // own gateway-mapped list (below) deliberately does not carry buttons for. Legacy
            // `VanGlassStyle`-based, same reasoning as the Browser & Automation children.
            DegradedPanel(degradedState.subsystems, legacyGlassFor(degradedState)) { subsystem ->
                if (!DeviceSignals.perform(context, app, subsystem)) {
                    unfixable = subsystem.label
                }
                app.refreshSubsystemHealth()
            }
        }
        unfixable?.let { label ->
            item {
                Text(
                    "\"$label\" is not something VAN can fix from this phone.",
                    style = tokens.type.label,
                    color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK),
                )
            }
        }

        item { SectionHeader("Gateway diagnostics", detail = "The gateway's own degraded state (GET /v1/degraded)") }
        gatewayDegradedError?.let { item { Text(it, style = tokens.type.body, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK)) } }
        val capabilities = gatewayDegraded?.let { GatewayDegradedMapping.parse(it) }.orEmpty()
        if (gatewayDegraded != null && capabilities.isEmpty()) {
            item { Text("Nothing is reported as broken.", style = tokens.type.body, color = tokens.color.textSecondary) }
        }
        items(capabilities, key = { it.code }) { capability ->
            VanPanel(dense = true) {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Text(GatewayDegradedMapping.labelFor(capability.code), style = tokens.type.body, color = tokens.color.textPrimary)
                        StatusChip(label = "DEGRADED", role = StatusSemantics.ROLE_EVENT_RISK)
                    }
                    Text(GatewayDegradedMapping.detailFor(capability), style = tokens.type.label, color = tokens.color.textSecondary)
                }
            }
        }

        item {
            SettingsLink(
                title = "Voice",
                detail = "Teach VAN a mishearing, pin a name, choose where a correction applies",
                onClick = onOpenVoice,
            )
        }
        item {
            SettingsLink(
                title = "Notifications",
                detail = "Which apps VAN reads, and quiet hours",
                onClick = onOpenNotifications,
            )
        }

        item {
            Text(
                "Anything VAN cannot easily undo still needs your fingerprint or face. Nothing secret is shown on this page.",
                style = tokens.type.label,
                color = tokens.color.textTertiary,
            )
        }
    }
}

/** The one place `visual/`'s glass style is still built, for [DegradedPanel] and the two
 *  legacy full-screen children ([SettingsVoiceRoute]/[SettingsNotificationsRoute]) — all
 *  three predate the design system and take a `VanGlassStyle`, not tokens. */
@Composable
private fun legacyGlassFor(mode: com.dial.van.degraded.DegradedMode): com.dial.van.visual.VanGlassStyle {
    val cue = VanPresence.cue(mode)
    val budget = rememberVanEffectBudget()
    return VanGlassTokens.forState(state = cue.durableState, panel = true, liveBlurAvailable = false, budget = budget)
}

@Composable
private fun SettingsLink(title: String, detail: String, onClick: () -> Unit) {
    val tokens = LocalVanTokens.current
    VanPressable(onClick = onClick, modifier = Modifier.fillMaxWidth(), contentDescription = "$title. $detail. Open.") {
        VanPanel(modifier = Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                Column(modifier = Modifier.fillMaxWidth()) {
                    Text(title, style = tokens.type.headline, color = tokens.color.textPrimary)
                    Text(detail, style = tokens.type.body, color = tokens.color.textSecondary)
                }
            }
        }
    }
}

/**
 * Settings' "Voice" child (DNA §4: "voice settings"). `SpeechModule` is unowned by this
 * worker to rewrite (P2-AND-018) and is itself a `LazyColumn { fillMaxSize() }`, so it gets
 * its own destination rather than being nested inside Settings' own list.
 */
@Composable
fun SettingsVoiceRoute(app: VanApplication, onBack: () -> Unit) {
    val degraded by app.degradedModeStore.state.collectAsState()
    Column(modifier = Modifier.fillMaxSize()) {
        SettingsChildHeader("Voice", onBack)
        SpeechModule(app, legacyGlassFor(degraded))
    }
}

/**
 * Settings' "Notifications" child (DNA §4: "notification policy, quiet hours"). Same reason
 * as [SettingsVoiceRoute]: `NotificationPolicyModule` (P2-AND-017) is a full-screen list.
 */
@Composable
fun SettingsNotificationsRoute(app: VanApplication, onBack: () -> Unit) {
    val degraded by app.degradedModeStore.state.collectAsState()
    Column(modifier = Modifier.fillMaxSize()) {
        SettingsChildHeader("Notifications", onBack)
        NotificationPolicyModule(app, legacyGlassFor(degraded))
    }
}

@Composable
private fun SettingsChildHeader(title: String, onBack: () -> Unit) {
    val tokens = LocalVanTokens.current
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = tokens.space.pageGutter, vertical = tokens.space.space2),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(tokens.space.space2),
    ) {
        Button(onClick = onBack) { Text("← Settings", style = tokens.type.label) }
        Text(title, style = tokens.type.title, color = tokens.color.textPrimary)
    }
}
