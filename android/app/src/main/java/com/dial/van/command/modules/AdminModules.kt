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
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.text.input.PasswordVisualTransformation
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

@Composable
internal fun ConnectionsModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    var endpointDraft by remember { mutableStateOf(app.gatewayClient.baseUrl) }
    var pairingDraft by remember { mutableStateOf("") }
    var connectionMessage by remember { mutableStateOf<String?>(null) }
    var pairingBusy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Connections", "One-time owner pairing; persistent credentials are encrypted and never displayed") }
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
                    if (!paired) {
                        OutlinedTextField(
                            value = endpointDraft,
                            onValueChange = { endpointDraft = it },
                            label = { Text("Gateway address") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                        OutlinedTextField(
                            value = pairingDraft,
                            onValueChange = { pairingDraft = it },
                            label = { Text("One-time pairing token") },
                            visualTransformation = PasswordVisualTransformation(),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                        Button(
                            enabled = pairingDraft.trim().length >= 32 && !pairingBusy,
                            onClick = {
                                pairingBusy = true
                                scope.launch {
                                    connectionMessage = runCatching {
                                        app.gatewayClient.pairThisDevice(endpointDraft, pairingDraft)
                                        pairingDraft = ""
                                        "Device paired securely"
                                    }.getOrElse {
                                        "Pairing failed: ${it.message ?: it.javaClass.simpleName}"
                                    }
                                    pairingBusy = false
                                }
                            },
                        ) { Text(if (pairingBusy) "Pairing…" else "Pair this device") }
                    } else {
                        Text(
                            "Ingress, revocable device access, and the command HMAC credential are active.",
                            color = Color(0xFFBCD1D8),
                            fontSize = 11.sp,
                        )
                    }
                    connectionMessage?.let {
                        Text(it, color = Color(0xFFBCD1D8), fontSize = 11.sp)
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
