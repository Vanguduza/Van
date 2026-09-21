package com.dial.van.command.modules

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.VanApplication
import com.dial.van.command.AdminCard
import com.dial.van.command.SectionHeader
import com.dial.van.command.TruthMessage
import com.dial.van.overlay.FloatingOverlayService
import com.dial.van.status.OwnerLanguage
import kotlinx.coroutines.launch
import org.json.JSONObject

/** Systems, connections and settings. Split out of `CommandCentreActivity` (P3-AND-009). */

@Composable
internal fun SystemsModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    val scope = rememberCoroutineScope()
    var health by remember { mutableStateOf<JSONObject?>(null) }
    var mesh by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    fun refresh() {
        scope.launch {
            runCatching {
                health = app.gatewayClient.health()
                mesh = app.gatewayClient.googleMesh()
            }.onFailure { error = it.message ?: "System health unavailable" }
        }
    }
    LaunchedEffect(Unit) { refresh() }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Systems", "Whether VAN's own machine and services are working") }
        if (health == null && error == null) item { TruthMessage("Loading system health…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        health?.let { h ->
            item {
                AdminCard(glass) {
                    Column {
                        Text("VAN's machine", color = Color.White, fontWeight = FontWeight.Bold)
                        Text("Overall ok: ${h.optBoolean("ok", false)}", color = Color(0xFFD7E7EC))
                        // P2-UX-001 — this printed a JSON array. `ownerSafe` shows a plain
                        // sentence rather than a value that escaped an internal layer.
                        Text(
                            OwnerLanguage.ownerSafe(
                                h.optJSONArray("degraded")?.optString(0),
                                "Nothing is reported as broken.",
                            ),
                            color = Color(0xFFBCD1D8), fontSize = 10.sp,
                        )
                    }
                }
            }
        }
        mesh?.let { m ->
            item {
                AdminCard(glass) {
                    Column {
                        Text("Google mesh", color = Color.White, fontWeight = FontWeight.Bold)
                        Text("Registry: ${m.optString("registry_version", "unknown")}", color = Color(0xFFD7E7EC), fontSize = 11.sp)
                        Text(
                            if (m.optJSONObject("principal")?.optBoolean("registered") == true) {
                                "VAN is signed in to your Google account."
                            } else {
                                "VAN is not signed in to your Google account."
                            },
                            color = Color(0xFFBCD1D8), fontSize = 10.sp,
                        )
                    }
                }
            }
        }
        item { Button(onClick = { refresh() }) { Text("Refresh systems") } }
    }
}

/**
 * Rev 1.5 §0D.2 — read-only diagnostics, and nothing to fill in.
 *
 * This screen used to carry a "Gateway address" field and a "One-time pairing token"
 * field. Those are the first and fifth entries on §0D.2's list of what an owner
 * production build must never expose, and the section's last line is the rule this
 * screen now obeys: *the owner may see read-only diagnostics, but no ordinary
 * connectivity setup form exists.*
 *
 * A "change server address" box on an assistant that holds the owner's mail, calendar
 * and money is a complete compromise one convincing message away — and the compromise
 * leaves nothing on the phone looking wrong. Provisioning is ADR-RB-026's installer path
 * instead: one signed, single-use, short-lived payload the device verifies against a key
 * compiled into this build.
 *
 * What is shown is what an owner can act on: where this phone is pointed, whether it is
 * paired, whether it is hardware-bound, and — when it is not — that the installer is what
 * fixes it rather than anything on this screen.
 */
@Composable
internal fun ConnectionsModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item {
            SectionHeader(
                "Connections",
                "Set up by the installer. Nothing here is typed in, and that is deliberate",
            )
        }
        item {
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    val paired = app.gatewayClient.isPaired()
                    Text("This phone's pairing", color = Color.White, fontWeight = FontWeight.Bold)
                    Text(app.gatewayClient.baseUrl, color = Color(0xFFD7E7EC), fontSize = 12.sp)
                    Text("Paired: $paired", color = Color(0xFFBCD1D8), fontSize = 11.sp)
                    Text(
                        app.gatewayClient.deviceId
                            ?.let { OwnerLanguage.digestReference("This phone", it) ?: "This phone is paired" }
                            ?: "This phone is not paired yet",
                        color = Color(0xFFBCD1D8), fontSize = 11.sp,
                    )
                    // §0D.3 — paired is not bound. A phone with working tokens and no
                    // hardware identity is the state that section exists to prevent, and
                    // reporting only "Paired: true" would hide exactly that.
                    Text(
                        if (app.gatewayClient.hasDeviceIdentity()) {
                            "This phone has a hardware identity, so its access is worth " +
                                "nothing on any other handset."
                        } else {
                            "This phone has no hardware identity yet. Until the installer " +
                                "finishes, its access is not tied to this handset."
                        },
                        color = Color(0xFFBCD1D8), fontSize = 11.sp,
                    )
                    if (paired) {
                        Text(
                            "Ingress, revocable device access, and the command HMAC credential are active.",
                            color = Color(0xFFBCD1D8),
                            fontSize = 11.sp,
                        )
                    } else if (app.provisioning.configured) {
                        Text(
                            "Waiting for the installer. Van will not ask you for an " +
                                "address or a code — no screen in this app can change " +
                                "where it connects.",
                            color = Color(0xFFBCD1D8), fontSize = 11.sp,
                        )
                    } else {
                        // A build with no trust anchor can never be provisioned. Saying
                        // "waiting" would leave the owner watching a screen that cannot
                        // change, which is the kind of honest-looking lie this programme
                        // exists to remove.
                        Text(
                            "This build was not given the key it needs to be set up, so " +
                                "it cannot be provisioned at all. A rebuild is what it needs.",
                            color = Color(0xFFE8A0A0), fontSize = 11.sp,
                        )
                    }
                }
            }
        }
    }
}

@Composable
internal fun SettingsModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Settings", "The floating assistant and what it may do") }
        item {
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Floating VAN", color = Color.White, fontWeight = FontWeight.Bold)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { FloatingOverlayService.start(app) }) { Text("Start") }
                        Button(onClick = { FloatingOverlayService.stop(app) }) { Text("Stop") }
                    }
                }
            }
        }
        item {
            TruthMessage("Anything VAN cannot easily undo still needs your fingerprint or face. Nothing secret is shown on this page.")
        }
    }
}
