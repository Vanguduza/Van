package com.dial.van.command.connected

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.dial.van.VanApplication
import com.dial.van.command.objectList
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.ScreenState
import com.dial.van.design.ScreenStateMerge
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanScreen
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * DNA §4 destination 7: "Connected — Google planes, Hermes, knowledge providers, readiness."
 *
 * @DataSource("GET /health") — Hermes health, knowledge readiness (`owner_runtime` block).
 * @DataSource("GET /v1/google/planes") — the four Google credentials, one by one.
 */
private data class ConnectedData(
    val health: JSONObject,
    val planes: JSONObject,
)

@Composable
fun ConnectedRoute(app: VanApplication) {
    val scope = rememberCoroutineScope()
    var data by remember { mutableStateOf<ConnectedData?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var confirmRevoke by remember { mutableStateOf(false) }
    var revokeNotice by remember { mutableStateOf<String?>(null) }

    fun load() {
        scope.launch {
            loading = true
            runCatching {
                ConnectedData(health = app.gatewayClient.health(), planes = app.gatewayClient.googlePlanes())
            }.onSuccess { data = it; error = null; loading = false }
                .onFailure { error = it.message ?: "VAN could not reach its own gateway."; loading = false }
        }
    }
    LaunchedEffect(Unit) { load() }

    val degraded = data?.health?.optJSONArray("degraded")?.objectList()?.map { it.optString("code") }.orEmpty()
    val state: ScreenState<ConnectedData> = ScreenStateMerge.merge(
        content = data,
        loading = loading,
        errorMessage = error,
        degradedSubsystems = degraded,
        emptySentence = "VAN has nothing to report about its connections yet.",
    )
    val tokens = LocalVanTokens.current

    VanScreen(state = state, onRetry = ::load) { connected ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter),
            verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
            contentPadding = PaddingValues(vertical = tokens.space.space3),
        ) {
            item { SectionHeader("Connected", detail = "What VAN is signed in to, and whether it can reach it") }

            item {
                val hermesOk = connected.health.optJSONObject("hermes")?.optBoolean("ok") == true
                VanPanel {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text("Hermes", style = tokens.type.headline, color = tokens.color.textPrimary)
                            StatusChip(
                                label = if (hermesOk) "REACHABLE" else "UNREACHABLE",
                                role = if (hermesOk) StatusSemantics.ROLE_FAVOURABLE else StatusSemantics.ROLE_CRITICAL,
                            )
                        }
                        Text(
                            if (hermesOk) "VAN's agent runtime answered its last health check." else "VAN could not reach its agent runtime on its last check.",
                            style = tokens.type.body,
                            color = tokens.color.textSecondary,
                        )
                    }
                }
            }

            item {
                val runtime = connected.health.optJSONObject("owner_runtime")
                val ready = runtime?.optBoolean("ready", runtime.optBoolean("ok", false)) ?: false
                VanPanel {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text("Knowledge readiness", style = tokens.type.headline, color = tokens.color.textPrimary)
                            StatusChip(
                                label = if (ready) "READY" else "NOT READY",
                                role = if (ready) StatusSemantics.ROLE_FAVOURABLE else StatusSemantics.ROLE_EVENT_RISK,
                            )
                        }
                        Text(
                            "From the owner runtime's own health block.",
                            style = tokens.type.label,
                            color = tokens.color.textTertiary,
                        )
                    }
                }
            }

            item { SectionHeader("Google", detail = "Four credentials, reported one by one — not one boolean") }
            val capabilities = connected.planes.optJSONArray("capabilities")?.objectList().orEmpty()
            if (capabilities.isEmpty()) {
                item { Text("No Google planes reported.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            items(capabilities, key = { it.optString("capability_id") }) { plane ->
                val planeState = plane.optString("state", "UNVERIFIED")
                VanPanel(dense = true) {
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Column(modifier = Modifier.fillMaxWidth()) {
                            Text(
                                plane.optString("capability_id"),
                                style = tokens.type.body,
                                color = tokens.color.textPrimary,
                            )
                            StatusChip(
                                label = planeState,
                                role = when (planeState) {
                                    "READY" -> StatusSemantics.ROLE_FAVOURABLE
                                    "CONFIGURED" -> StatusSemantics.ROLE_MONITOR
                                    else -> StatusSemantics.ROLE_EVENT_RISK
                                },
                            )
                        }
                    }
                }
            }

            item {
                val registered = connected.planes.optJSONObject("principal")?.optBoolean("registered") == true
                VanPanel {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Text(
                            if (registered) "VAN is signed in to your Google account." else "VAN is not signed in to your Google account.",
                            style = tokens.type.body,
                            color = tokens.color.textPrimary,
                        )
                        OutlinedButton(
                            onClick = { confirmRevoke = true },
                            enabled = registered,
                            colors = ButtonDefaults.outlinedButtonColors(contentColor = tokens.color.forStatusRole(StatusSemantics.ROLE_CRITICAL)),
                        ) {
                            Text("Revoke Google access", style = tokens.type.label)
                        }
                        revokeNotice?.let {
                            Text(it, style = tokens.type.label, color = tokens.color.textSecondary)
                        }
                    }
                }
            }
        }
    }

    if (confirmRevoke) {
        AlertDialog(
            onDismissRequest = { confirmRevoke = false },
            title = { Text("Revoke Google access?") },
            text = {
                Text(
                    "VAN will lose access to Gmail, Calendar, Drive, Contacts and Tasks " +
                        "until you reconnect from the host. This does not undo anything " +
                        "already done — it only stops future access.",
                )
            },
            confirmButton = {
                Button(onClick = {
                    confirmRevoke = false
                    scope.launch {
                        runCatching { app.gatewayClient.googleOwnerRevoke() }
                            .onSuccess { revokeNotice = "Google access revoked."; load() }
                            .onFailure { revokeNotice = "Could not revoke: ${it.message}" }
                    }
                }) { Text("Revoke") }
            },
            dismissButton = {
                OutlinedButton(onClick = { confirmRevoke = false }) { Text("Cancel") }
            },
        )
    }
}
