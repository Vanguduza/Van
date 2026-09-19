package com.dial.van.command.modules

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.VanApplication
import com.dial.van.command.AdminActionCard
import com.dial.van.command.AdminCard
import com.dial.van.command.CommandModule
import com.dial.van.command.DashboardPageHeader
import com.dial.van.command.SectionHeader
import com.dial.van.command.TruthMessage
import com.dial.van.command.objectList
import com.dial.van.command.stringList
import com.dial.van.control.VanCommandSource
import com.dial.van.visual.VanGlassTokens
import kotlinx.coroutines.launch
import org.json.JSONObject
import com.dial.van.status.OwnerLanguage

/** The browser and automation surfaces. Split out of `CommandCentreActivity` (P3-AND-009). */

@Composable
internal fun BrowserAutomationModule(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    navigate: (CommandModule) -> Unit,
) {
    val scope = rememberCoroutineScope()
    var status by remember { mutableStateOf<JSONObject?>(null) }
    var tasks by remember { mutableStateOf<List<JSONObject>?>(null) }
    var escalations by remember { mutableStateOf<List<JSONObject>?>(null) }
    var policy by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    fun refresh() {
        scope.launch {
            runCatching {
                status = app.gatewayClient.browserStatus()
                tasks = app.gatewayClient.browserTasks().objectList()
                escalations = app.gatewayClient.browserEscalations().objectList()
                policy = app.gatewayClient.browserPolicy()
                error = null
            }.onFailure { error = it.message ?: "Browser/automation truth unavailable" }
        }
    }
    LaunchedEffect(Unit) { refresh() }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item {
            SectionHeader(
                "Browser & Automation",
                "Summary dashboard. Open a card for the full operational page.",
            )
        }
        if (status == null && error == null) item { TruthMessage("Loading browser and automation state…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }

        status?.let { s ->
            item {
                AdminCard(glass) {
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text("Runtime overview", color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                        Text(
                            "Browser ${if (s.optBoolean("enabled")) "enabled" else "disabled"} • worker ${if (s.optBoolean("worker_configured")) "configured" else "not configured"}",
                            color = Color(0xFFD7E7EC),
                            fontSize = 11.sp,
                        )
                        Text(
                            "${s.optInt("waiting_for_owner")} waiting for owner • ${s.optInt("admitted_automation_capabilities")} admitted automations",
                            color = Color(VanGlassTokens.EDGE_CYAN),
                            fontSize = 11.sp,
                        )
                    }
                }
            }
        }

        item {
            AdminActionCard(
                "Owner escalations",
                escalations?.let { rows ->
                    val open = rows.count { it.optString("decision_status", it.optString("status")) == "OPEN" }
                    "$open awaiting owner decision • ${rows.size} returned"
                } ?: "Loading escalation summary…",
                glass,
            ) { navigate(CommandModule.BROWSER_ESCALATIONS) }
        }
        item {
            AdminActionCard(
                "Browser tasks & evidence",
                tasks?.let { rows ->
                    val waiting = rows.count { it.optString("status") == "WAITING_FOR_OWNER" }
                    "${rows.size} active/recent task(s) • $waiting resumably waiting"
                } ?: "Loading task summary…",
                glass,
            ) { navigate(CommandModule.BROWSER_TASKS) }
        }
        item {
            val profiles = status?.optJSONArray("profiles")?.objectList().orEmpty()
            AdminActionCard(
                "Sessions & profiles",
                if (status == null) "Loading managed browser profiles…" else {
                    val active = profiles.count { !it.isNull("lease_holder") }
                    "${profiles.size} managed profile(s) • $active active lease(s)"
                },
                glass,
            ) { navigate(CommandModule.BROWSER_SESSIONS) }
        }
        item {
            AdminActionCard(
                "Policy & capabilities",
                policy?.let {
                    "What VAN is allowed to do on the web, and how far it may go on its own"
                } ?: "Checking what VAN is allowed to do…",
                glass,
            ) { navigate(CommandModule.BROWSER_POLICY) }
        }
        item { Button(onClick = { refresh() }) { Text("Refresh summary") } }
    }
}

@Composable
internal fun BrowserEscalationsPage(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    back: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var escalations by remember { mutableStateOf<List<JSONObject>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var resolving by remember { mutableStateOf<String?>(null) }

    fun refresh() {
        scope.launch {
            runCatching { app.gatewayClient.browserEscalations().objectList() }
                .onSuccess { escalations = it; error = null }
                .onFailure { error = it.message ?: "Unable to load browser escalations" }
        }
    }
    LaunchedEffect(Unit) { refresh() }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { DashboardPageHeader("Things VAN is waiting on you for", "Browser & Automation", back) }
        if (escalations == null && error == null) item { TruthMessage("Checking…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        if (escalations?.isEmpty() == true) item { TruthMessage("Nothing is waiting on you.") }
        items(escalations.orEmpty(), key = { it.optString("escalation_id") }) { esc ->
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    val decisionId = esc.optString("decision_id")
                    val decisionStatus = esc.optString("decision_status", esc.optString("status"))
                    Text(esc.optString("summary", "Browser boundary escalation"), color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                    // P2-UX-001 — this was `reason_code`, then 300 truncated characters
                    // of scope JSON, twice. The owner was being asked to approve a browser
                    // boundary extension by reading a debugger.
                    Text(OwnerLanguage.reason(esc.optString("reason_code")), color = Color(VanGlassTokens.ACCENT_AMBER), fontSize = 11.sp)
                    Text(OwnerLanguage.ownerSafe(esc.optString("why_required"), "VAN did not say why it needs this."), color = Color(0xFFD7E7EC), fontSize = 11.sp)
                    Text("It can reach: ${OwnerLanguage.scopeSentenceFromJson(esc.optString("current_scope_json"))}", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                    Text("It is asking for: ${OwnerLanguage.scopeSentenceFromJson(esc.optString("requested_scope_delta_json"))}", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                    if (decisionStatus == "OPEN" && decisionId.isNotBlank()) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(
                                enabled = resolving == null,
                                onClick = {
                                    resolving = decisionId
                                    scope.launch {
                                        runCatching { app.gatewayClient.resolveDecision(decisionId, true) }.onFailure { error = it.message }
                                        resolving = null
                                        refresh()
                                    }
                                },
                            ) { Text(if (resolving == decisionId) "Applying…" else "Let it") }
                            Button(
                                enabled = resolving == null,
                                onClick = {
                                    resolving = decisionId
                                    scope.launch {
                                        runCatching { app.gatewayClient.resolveDecision(decisionId, false) }.onFailure { error = it.message }
                                        resolving = null
                                        refresh()
                                    }
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF5B2730)),
                            ) { Text("Don't let it") }
                        }
                        Button(
                            onClick = {
                                val taskId = esc.optString("task_id")
                                val reason = esc.optString("reason_code")
                                app.commandController.submitText(
                                    "Replan browser task $taskId without crossing the blocked boundary $reason. Preserve completed evidence and propose the safest authorized alternative.",
                                    VanCommandSource.CHAT,
                                )
                            },
                        ) { Text("Ask VAN to replan") }
                    }
                }
            }
        }
        item { Button(onClick = { refresh() }) { Text("Refresh escalations") } }
    }
}

@Composable
internal fun BrowserTasksPage(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    back: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var tasks by remember { mutableStateOf<List<JSONObject>?>(null) }
    var evidenceByTask by remember { mutableStateOf<Map<String, List<JSONObject>>>(emptyMap()) }
    var error by remember { mutableStateOf<String?>(null) }

    fun refresh() {
        scope.launch {
            runCatching { app.gatewayClient.browserTasks().objectList() }
                .onSuccess { tasks = it; error = null }
                .onFailure { error = it.message ?: "Unable to load browser tasks" }
        }
    }
    LaunchedEffect(Unit) { refresh() }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { DashboardPageHeader("Browser tasks & evidence", "Browser & Automation", back) }
        if (tasks == null && error == null) item { TruthMessage("Loading browser tasks…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        if (tasks?.isEmpty() == true) item { TruthMessage("VAN is not working on anything on the web right now.") }
        items(tasks.orEmpty(), key = { it.optString("task_id") }) { task ->
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(task.optString("goal", "Browser task"), color = Color.White, fontWeight = FontWeight.Bold)
                    Text(
                        "${task.optString("status")} • ${task.optString("strategy")} • ${task.optString("autonomy_tier")}",
                        color = if (task.optString("status") == "WAITING_FOR_OWNER") Color(VanGlassTokens.ACCENT_AMBER) else Color(0xFFD7E7EC),
                        fontSize = 11.sp,
                    )
                    Text("${task.optString("target_domain")} • ${task.optString("action_class")}", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                    task.optString("error_code").takeIf { it.isNotBlank() }?.let {
                        Text("State reason: $it", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                    }
                    val taskId = task.optString("task_id")
                    Button(
                        onClick = {
                            scope.launch {
                                runCatching { app.gatewayClient.browserEvidence(taskId).objectList() }
                                    .onSuccess { records -> evidenceByTask = evidenceByTask + (taskId to records) }
                                    .onFailure { error = it.message }
                            }
                        },
                    ) { Text("Open evidence") }
                    evidenceByTask[taskId]?.let { records ->
                        Text("${records.size} evidence receipt(s)", color = Color(VanGlassTokens.EDGE_CYAN), fontSize = 10.sp)
                        records.takeLast(8).forEach { evidence ->
                            Text(
                                "${evidence.optString("kind")} • ${evidence.optString("source_trust")} • ${evidence.optString("injection_assessment")}",
                                color = Color(0xFFBCD1D8),
                                fontSize = 9.sp,
                            )
                        }
                    }
                }
            }
        }
        item { Button(onClick = { refresh() }) { Text("Refresh tasks") } }
    }
}

@Composable
internal fun BrowserSessionsPage(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    back: () -> Unit,
) {
    var status by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        runCatching { app.gatewayClient.browserStatus() }
            .onSuccess { status = it; error = null }
            .onFailure { error = it.message ?: "Unable to load browser sessions" }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { DashboardPageHeader("Sessions & profiles", "Browser & Automation", back) }
        if (status == null && error == null) item { TruthMessage("Loading managed browser profiles…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        val profiles = status?.optJSONArray("profiles")?.objectList().orEmpty()
        if (status != null && profiles.isEmpty()) item { TruthMessage("No managed browser profiles returned.") }
        items(profiles, key = { it.optString("profile_alias") }) { profile ->
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(profile.optString("profile_alias"), color = Color.White, fontWeight = FontWeight.Bold)
                    Text(
                        "${profile.optString("persistence")} • ${profile.optString("authentication")} • ${profile.optString("mutation_policy")}",
                        color = Color(0xFFD7E7EC),
                        fontSize = 11.sp,
                    )
                    Text(
                        if (profile.isNull("lease_holder")) "No active lease" else "Active managed lease",
                        color = Color(0xFFBCD1D8),
                        fontSize = 10.sp,
                    )
                }
            }
        }
        item {
            TruthMessage("Managed aliases only. Raw cookies, credentials and provider tokens are never displayed.")
        }
    }
}

@Composable
internal fun BrowserPolicyPage(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    back: () -> Unit,
) {
    var policy by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        runCatching { app.gatewayClient.browserPolicy() }
            .onSuccess { policy = it; error = null }
            .onFailure { error = it.message ?: "VAN could not read its own web rules just now." }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { DashboardPageHeader("Policy & capabilities", "Browser & Automation", back) }
        if (policy == null && error == null) item { TruthMessage("Checking what VAN is allowed to do…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        policy?.let { p ->
            item {
                AdminCard(glass) {
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text("Browser policy ${p.optString("policy_version")}", color = Color.White, fontWeight = FontWeight.Bold)
                        Text("Max autonomy: ${p.optString("max_autonomy_tier")}", color = Color(0xFFD7E7EC), fontSize = 11.sp)
                        Text("Session leases required: ${p.optBoolean("session_leases_required")}", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                        Text("Mutation default deny: ${p.optBoolean("mutation_default_deny")}", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                        Text("Download default deny: ${p.optBoolean("download_default_deny")}", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                    }
                }
            }
            item {
                AdminCard(glass) {
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text("Admitted domains", color = Color.White, fontWeight = FontWeight.Bold)
                        p.optJSONArray("admitted_domains")?.stringList().orEmpty().forEach {
                            Text("• $it", color = Color(0xFFD7E7EC), fontSize = 11.sp)
                        }
                    }
                }
            }
            item {
                AdminCard(glass) {
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text("Hard prohibitions", color = Color(VanGlassTokens.ACCENT_AMBER), fontWeight = FontWeight.Bold)
                        p.optJSONArray("hard_prohibitions")?.stringList().orEmpty().forEach {
                            Text("• $it", color = Color(0xFFD7E7EC), fontSize = 11.sp)
                        }
                    }
                }
            }
        }
        item { TruthMessage("This page shows the rules; it cannot change them. Changing them is something you ask VAN to do, so there is a record of it.") }
    }
}
