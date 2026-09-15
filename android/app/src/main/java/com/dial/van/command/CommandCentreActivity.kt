package com.dial.van.command

import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.degraded.RestoreAction
import com.dial.van.overlay.FloatingOverlayService
import com.dial.van.queue.CommandKind
import com.dial.van.queue.CommandSensitivity
import com.dial.van.queue.QueueEnqueueRequest
import com.dial.van.security.BiometricGate
import com.dial.van.visual.VanAvatar
import com.dial.van.visual.VanVisualState
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class CommandCentreActivity : FragmentActivity() {

    @OptIn(ExperimentalMaterial3Api::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as VanApplication

        setContent {
            MaterialTheme(colorScheme = darkColorScheme(primary = Color(0xFF00E5FF))) {
                Scaffold(
                    topBar = { TopAppBar(title = { Text("Van Command Centre") }) },
                ) { padding ->
                    CommandCentreScreen(
                        padding = padding,
                        app = app,
                        onA4Approve = { gate, onDone ->
                            gate.requestA4Approval(onApproved = onDone, onDenied = { })
                        },
                    )
                }
            }
        }
    }
}

@Composable
private fun CommandCentreScreen(
    padding: PaddingValues,
    app: VanApplication,
    onA4Approve: (BiometricGate, () -> Unit) -> Unit,
) {
    val activity = LocalContext.current as FragmentActivity
    val gate = remember(activity) { BiometricGate(activity) }
    var meshSummary by remember { mutableStateOf("Google mesh: awaiting gateway evidence") }
    var statusMessage by remember { mutableStateOf("") }
    var sections by remember { mutableStateOf(commandSections(app, meshSummary)) }

    LaunchedEffect(Unit) {
        try {
            val health = withContext(Dispatchers.IO) { app.gatewayClient.health() }
            val mesh = health.optJSONObject("google_mesh")
            val configured = mesh?.optInt("configured_capabilities") ?: 0
            val total = mesh?.optInt("total_capabilities") ?: 0
            val principal = mesh?.optJSONObject("principal")?.optBoolean("registered") == true
            app.degradedModeStore.applyGoogleMesh(configured, total, principal)
            if (!health.optBoolean("ok", false)) {
                app.degradedModeStore.markBroken("hermes", "Hermes offline from /health", RestoreAction.RETRY_CONNECTION)
            } else {
                app.degradedModeStore.markWorking("hermes")
                app.degradedModeStore.markWorking("gateway")
            }
            meshSummary = "Google mesh configured=$configured/$total principal=${if (principal) "registered" else "missing"}"
        } catch (exc: Exception) {
            app.degradedModeStore.markBroken("gateway", "health unreachable: ${exc.message}", RestoreAction.RETRY_CONNECTION)
            meshSummary = "Google mesh: gateway unreachable"
        }
        sections = commandSections(app, meshSummary)
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(padding)
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            VanAvatar(state = VanVisualState(), modifier = Modifier.fillMaxWidth())
        }
        items(sections) { section ->
            CommandSectionCard(section = section)
        }
        item {
            Button(onClick = { FloatingOverlayService.start(app) }) {
                Text("Start overlay")
            }
        }
        item {
            Button(onClick = {
                onA4Approve(gate) {
                    app.commandQueue.enqueue(
                        QueueEnqueueRequest(
                            kind = CommandKind.HERMES_DISPATCH,
                            payloadJson = Json.encodeToString(
                                buildJsonObject { put("action", "owner_approved_a4") },
                            ),
                            sensitivity = CommandSensitivity.DESTRUCTIVE,
                        ),
                    )
                    statusMessage = "A4 action queued with biometric approval"
                }
            }) {
                Text("Approve A4 action (biometric)")
            }
        }
        if (statusMessage.isNotEmpty()) {
            item { Text(statusMessage) }
        }
    }
}

private data class CommandSection(
    val id: String,
    val title: String,
    val summary: String,
    val items: List<String>,
)

private fun commandSections(app: VanApplication, meshSummary: String): List<CommandSection> {
    val queueSize = app.commandQueue.size()
    val degraded = app.degradedModeStore.snapshot()
    return listOf(
        CommandSection("attention", "Attention", "Items needing owner focus", listOf("Review pending attention queue")),
        CommandSection("decisions", "Decisions", "Open decisions awaiting input", listOf("No pending decisions")),
        CommandSection("projects", "Projects", "Active project registry mirror", listOf("Synced from registries/projects.json")),
        CommandSection("tasks", "Tasks", "Actionable tasks", listOf("$queueSize queued commands")),
        CommandSection("reminders", "Reminders / Follow-ups", "Time-bound follow-ups", listOf("None due")),
        CommandSection("memory", "Memory", "Owner memory context (untrusted labels)", listOf("Local context only")),
        CommandSection("audit", "Audit", "Recent capability grants & actions", listOf("Audit trail via Hermes")),
        CommandSection("connections", "Connections", "Device + Hermes connectivity", listOf("Hermes profile: van", meshSummary)),
        CommandSection("hermes", "Hermes", "Agent execution uplink (no embedded loop)", listOf("Dispatch-only — Hermes owns execution")),
        CommandSection(
            "degraded",
            "Degraded status",
            if (degraded.active) degraded.reason else "All subsystems nominal",
            degraded.subsystems.map { sub ->
                "${sub.label}: ${sub.status} — ${sub.detail}" +
                    if (sub.restoreAction != RestoreAction.NONE) " [${sub.restoreAction}]" else ""
            },
        ),
    )
}

@Composable
private fun CommandSectionCard(section: CommandSection) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(text = section.title, style = MaterialTheme.typography.titleMedium)
            Text(text = section.summary, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(bottom = 8.dp))
            section.items.forEach { item ->
                Text(text = "• $item", style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}
