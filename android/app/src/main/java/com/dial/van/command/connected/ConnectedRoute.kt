package com.dial.van.command.connected

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
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
import com.dial.van.VanApplication
import com.dial.van.command.dev.DevFabricSection
import com.dial.van.command.objectList
import com.dial.van.command.owner.ownerTime
import com.dial.van.command.owner.ownerValue
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject

/** Each credential plane and each capability is observed separately; registration is not sign-in. */
@Composable
fun ConnectedRoute(app: VanApplication) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    var health by remember { mutableStateOf<JSONObject?>(null) }
    var planes by remember { mutableStateOf<JSONObject?>(null) }
    var workspace by remember { mutableStateOf<JSONObject?>(null) }
    var failures by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var loading by remember { mutableStateOf(false) }
    var observedAt by remember { mutableStateOf(0L) }
    var confirmRevoke by remember { mutableStateOf(false) }
    var revoking by remember { mutableStateOf(false) }
    var revokeUncertain by remember { mutableStateOf(false) }
    var revokeNotice by remember { mutableStateOf<String?>(null) }

    suspend fun refresh() {
        if (loading) return
        loading = true
        try {
            val h = ConnectedReadback.source { app.gatewayClient.health() }
            val p = ConnectedReadback.source { app.gatewayClient.googlePlanes() }
            val w = ConnectedReadback.source { app.gatewayClient.googleStatus() }
            h.value?.let { health = it }
            p.value?.let { planes = it }
            w.value?.let { workspace = it }
            failures = buildMap {
                h.failure?.let { put("Service health", it) }
                p.failure?.let { put("Google planes and capabilities", it) }
                w.failure?.let { put("Workspace connection", it) }
            }
            if (w.value != null) revokeUncertain = false
            observedAt = System.currentTimeMillis()
        } finally { loading = false }
    }
    LaunchedEffect(Unit) { refresh() }
    val connected = if (workspace?.has("connected") == true && !workspace!!.isNull("connected")) workspace!!.optBoolean("connected") else null
    val canRevoke = connected == true && "Workspace connection" !in failures && !loading && !revoking && !revokeUncertain

    LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3), contentPadding = PaddingValues(vertical = tokens.space.space3)) {
        item {
            SectionHeader("Connected", detail = "Services, credential planes and capability verification")
            if (loading) Text("Refreshing connection information…", style = tokens.type.body, color = tokens.color.textSecondary)
            if (observedAt > 0L) Text("Last refresh attempt ${ownerTime(observedAt)}", style = tokens.type.label, color = tokens.color.textTertiary)
            failures.forEach { (source, reason) -> Text("$source could not be refreshed. Any visible information is last known. $reason", style = tokens.type.body, color = tokens.color.textSecondary) }
            OutlinedButton(enabled = !loading && !revoking, onClick = { scope.launch { refresh() } }) { Text("Refresh connections") }
        }
        item {
            val hermes = health?.optJSONObject("hermes")
            val ok = if ("Service health" !in failures && hermes?.has("ok") == true) hermes.optBoolean("ok") else null
            VanPanel { Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    Text("Hermes", style = tokens.type.headline, color = tokens.color.textPrimary)
                    StatusChip(label = when (ok) { true -> "REACHABLE"; false -> "UNREACHABLE"; null -> "UNKNOWN" },
                        role = when (ok) { true -> StatusSemantics.ROLE_FAVOURABLE; false -> StatusSemantics.ROLE_CRITICAL; null -> StatusSemantics.ROLE_DISABLED })
                }
                Text(when (ok) { true -> "VAN's agent runtime answered its last health check."; false -> "VAN could not reach its agent runtime on its last check."; null -> "Current runtime reachability could not be confirmed." }, style = tokens.type.body, color = tokens.color.textSecondary)
            } }
        }
        item {
            val runtime = health?.optJSONObject("owner_runtime")
            val ready = if ("Service health" !in failures && runtime != null && (runtime.has("ready") || runtime.has("ok"))) runtime.optBoolean("ready", runtime.optBoolean("ok")) else null
            VanPanel { Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                SectionHeader("Knowledge readiness")
                StatusChip(label = when (ready) { true -> "READY"; false -> "NOT READY"; null -> "UNKNOWN" },
                    role = if (ready == true) StatusSemantics.ROLE_FAVOURABLE else StatusSemantics.ROLE_EVENT_RISK)
                Text("From the owner runtime's health block. Provider verification is reported separately.", style = tokens.type.label, color = tokens.color.textTertiary)
                health?.optJSONArray("degraded")?.objectList().orEmpty().forEach { row ->
                    Text("Needs attention: ${row.ownerValue("code").replace('_', ' ')}", style = tokens.type.label, color = tokens.color.textSecondary)
                }
            } }
        }
        item { DevFabricSection(app) }
        item { SectionHeader("Google credential planes", detail = "Credentials fail independently; a working credential does not prove a capability works.") }
        val planeRows = planes?.optJSONArray("planes")?.objectList().orEmpty()
        if (planes != null && planeRows.isEmpty()) item { Text("Credential plane records were not supplied.", style = tokens.type.body, color = tokens.color.textSecondary) }
        items(planeRows, key = { "plane:${it.optString("plane")}" }) { plane ->
            VanPanel { Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                Text(plane.ownerValue("plane").replace('_', ' '), style = tokens.type.headline, color = tokens.color.textPrimary)
                Text(plane.ownerValue("state"), style = tokens.type.body, color = tokens.color.textSecondary)
                plane.optString("detail").takeIf { !plane.isNull("detail") && it.isNotBlank() }?.let { Text(it, style = tokens.type.label, color = tokens.color.textSecondary) }
                Text("Credential held by: ${plane.ownerValue("credential_locus")}", style = tokens.type.label, color = tokens.color.textTertiary)
            } }
        }
        item { SectionHeader("Google capabilities", detail = "Recorded execution readiness and verification") }
        val capabilities = planes?.optJSONArray("capabilities")?.objectList().orEmpty()
        if (planes != null && capabilities.isEmpty()) item { Text("No Google capabilities were supplied.", style = tokens.type.body, color = tokens.color.textSecondary) }
        items(capabilities, key = { "capability:${it.optString("capability_id")}" }) { capability ->
            val state = capability.ownerValue("state", "UNKNOWN")
            VanPanel(dense = true) { Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                Text(capability.ownerValue("display_name", capability.ownerValue("capability_id")), style = tokens.type.body, color = tokens.color.textPrimary)
                StatusChip(label = state, role = when (state) { "READY" -> StatusSemantics.ROLE_FAVOURABLE; "CONFIGURED" -> StatusSemantics.ROLE_MONITOR; else -> StatusSemantics.ROLE_EVENT_RISK })
                Text(capability.ownerValue("reason").replace('_', ' '), style = tokens.type.label, color = tokens.color.textSecondary)
                Text("Plane: ${capability.ownerValue("credential_plane").replace('_', ' ')} · identity: ${capability.ownerValue("identity_alias")}", style = tokens.type.label, color = tokens.color.textTertiary)
                if (!capability.isNull("verified_at_unix")) Text("Last verification ${ownerTime(capability.optLong("verified_at_unix") * 1000L)}", style = tokens.type.label, color = tokens.color.textTertiary)
                if (!capability.isNull("evidence_pointer")) Text("Receipt: ${capability.ownerValue("evidence_pointer")}", style = tokens.type.label, color = tokens.color.textTertiary)
            } }
        }
        item { VanPanel { Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            SectionHeader("Workspace account access")
            val message = when {
                "Workspace connection" in failures -> "Current Workspace access could not be read. Refresh before changing it."
                connected == true -> "VAN has an active gateway-held Workspace credential. Individual Gmail, Calendar, Drive, Contacts and Tasks operations still need their required scopes and authority."
                connected == false -> "VAN has no active gateway-held Workspace credential."
                else -> "Workspace connection state has not been confirmed."
            }
            Text(message, style = tokens.type.body, color = tokens.color.textPrimary)
            if (planes?.optJSONObject("principal")?.optBoolean("registered") == true) Text("The canonical owner principal is registered. Registration alone does not establish credential or capability readiness.", style = tokens.type.label, color = tokens.color.textSecondary)
            OutlinedButton(enabled = canRevoke, onClick = { confirmRevoke = true }) { Text(if (revoking) "Confirming revocation…" else "Revoke Workspace access") }
            revokeNotice?.let { Text(it, style = tokens.type.label, color = tokens.color.textSecondary) }
        } } }
    }
    if (confirmRevoke) AlertDialog(onDismissRequest = { confirmRevoke = false }, title = { Text("Revoke Workspace access?") },
        text = { Text("This clears VAN's gateway-held Workspace refresh credential and stops its future Workspace access. It does not undo completed work. Other Google credential planes are reported independently. Reconnecting Workspace requires owner consent on the host.") },
        confirmButton = { Button(enabled = canRevoke, onClick = {
            if (revoking || revokeUncertain || loading) return@Button
            confirmRevoke = false
            revoking = true
            revokeUncertain = true
            revokeNotice = "Requesting Workspace revocation…"
            scope.launch {
                try {
                    val outcome = ConnectedReadback.revoke(request = { app.gatewayClient.googleOwnerRevoke() }, read = { app.gatewayClient.googleStatus() })
                    outcome.status?.let { workspace = it }
                    revokeNotice = if (outcome.confirmed) "Workspace credential revocation was confirmed by a fresh connection read." else outcome.error
                    revokeUncertain = !outcome.confirmed
                    if (outcome.confirmed) refresh()
                } catch (cancel: CancellationException) {
                    revokeNotice = "Workspace revocation was interrupted and may already have been applied. Refresh its connection state before trying again."
                    throw cancel
                } finally { revoking = false }
            }
        }) { Text("Revoke Workspace") } }, dismissButton = { OutlinedButton(onClick = { confirmRevoke = false }) { Text("Cancel") } })
}
