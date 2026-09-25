package com.dial.van.command.jev

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.weight
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.control.VanCommandSource
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.MetricTile
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import kotlinx.coroutines.launch

private enum class JevTab(val label: String) {
    OVERVIEW("Overview"), MODULES("Modules"), ACTIVITY("Activity"), VALUE("Value"), CONTROLS("Controls")
}

private fun statusRole(status: String): String = when (status.uppercase()) {
    "ACTIVE" -> StatusSemantics.ROLE_FAVOURABLE
    "ACTIVE_GATED" -> StatusSemantics.ROLE_ENGAGED
    "ADVISORY" -> StatusSemantics.ROLE_COGNITION
    "SHADOW" -> StatusSemantics.ROLE_HYPOTHESIS
    "QUARANTINED" -> StatusSemantics.ROLE_CRITICAL
    "BYPASSED" -> StatusSemantics.ROLE_EVENT_RISK
    else -> StatusSemantics.ROLE_DISABLED
}

private fun projectFor(module: JevModule): String =
    module.projects.firstOrNull() ?: "dial-development-system"

@Composable
fun JevControlRoute(app: VanApplication, onBack: () -> Unit) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    val repository = remember(app.gatewayClient) { JevRepository(app.gatewayClient) }
    var snapshot by remember { mutableStateOf<JevServiceSnapshot?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(true) }
    var tabIndex by remember { mutableIntStateOf(0) }
    var selectedModule by remember { mutableStateOf<JevModule?>(null) }
    var activityProject by remember { mutableStateOf("van") }
    var activityItems by remember { mutableStateOf<List<JevActivityItem>>(emptyList()) }
    var performance by remember { mutableStateOf<JevPerformance?>(null) }
    var selectedContribution by remember { mutableStateOf<JevContribution?>(null) }

    fun refresh() {
        scope.launch {
            loading = true
            runCatching { repository.snapshot() }
                .onSuccess {
                    snapshot = it
                    error = null
                    selectedModule = selectedModule?.let { selected ->
                        it.modules.firstOrNull { module -> module.id == selected.id }
                    }
                }
                .onFailure { error = it.message ?: "Jev status unavailable" }
            loading = false
        }
    }

    fun loadActivity(projectId: String) {
        scope.launch {
            runCatching { repository.activity(projectId) }
                .onSuccess { activityItems = it; error = null }
                .onFailure { error = it.message ?: "Jev activity unavailable" }
        }
    }

    fun loadPerformance(projectId: String) {
        scope.launch {
            runCatching { repository.performance(projectId) }
                .onSuccess { performance = it; error = null }
                .onFailure { error = it.message ?: "Performance evidence unavailable" }
        }
    }

    fun loadContribution(module: JevModule) {
        scope.launch {
            runCatching { repository.contribution(projectFor(module), module.id) }
                .onSuccess { selectedContribution = it; error = null }
                .onFailure { error = it.message ?: "Contribution evidence unavailable" }
        }
    }

    fun ownerCommand(text: String, projectId: String? = "dial-development-system") {
        app.commandController.submitText(
            text = text,
            source = VanCommandSource.SYSTEM,
            projectId = projectId,
            actionClass = "A4",
            noStaleReplay = true,
        )
    }

    LaunchedEffect(Unit) { refresh() }
    LaunchedEffect(activityProject) { loadActivity(activityProject); loadPerformance(activityProject) }

    Column(
        modifier = Modifier.fillMaxWidth().padding(horizontal = tokens.space.pageGutter),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
    ) {
        SectionHeader(
            title = "Jev",
            detail = "System-1 decision intelligence across the DIAL ecosystem",
            trailing = { OutlinedButton(onClick = onBack) { Text("Back") } },
        )
        error?.let {
            VanPanel(dense = true) {
                Text(it, style = tokens.type.body, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK))
            }
        }
        ScrollableTabRow(selectedTabIndex = tabIndex, edgePadding = tokens.space.space2) {
            JevTab.entries.forEachIndexed { index, tab ->
                Tab(
                    selected = tabIndex == index,
                    onClick = { tabIndex = index; selectedModule = null },
                    text = { Text(tab.label) },
                )
            }
        }
        Box(modifier = Modifier.weight(1f, fill = true)) {
            when {
                loading && snapshot == null -> JevLoading()
                snapshot == null -> JevUnavailable(onRetry = ::refresh)
                selectedModule != null -> ModuleDetail(
                    module = selectedModule!!,
                    contribution = selectedContribution,
                    onBack = { selectedModule = null; selectedContribution = null },
                    onLoadContribution = { loadContribution(selectedModule!!) },
                    onTransition = { target ->
                        ownerCommand("set jev module ${selectedModule!!.id} to $target", projectFor(selectedModule!!))
                    },
                )
                tabIndex == JevTab.OVERVIEW.ordinal -> Overview(snapshot!!, onRefresh = ::refresh)
                tabIndex == JevTab.MODULES.ordinal -> Modules(snapshot!!.modules) {
                    selectedModule = it
                    selectedContribution = null
                }
                tabIndex == JevTab.ACTIVITY.ordinal -> Activity(activityProject, activityItems) { activityProject = it }
                tabIndex == JevTab.VALUE.ordinal -> Value(snapshot!!.modules, performance, selectedContribution) { module ->
                    selectedModule = module
                    loadContribution(module)
                }
                else -> Controls(snapshot!!) { ownerCommand(it) }
            }
        }
    }
}

@Composable
private fun JevLoading() {
    val tokens = LocalVanTokens.current
    VanPanel { Text("Loading Jev control plane…", style = tokens.type.body, color = tokens.color.textSecondary) }
}

@Composable
private fun JevUnavailable(onRetry: () -> Unit) {
    val tokens = LocalVanTokens.current
    VanPanel {
        Text("Jev projection is unavailable.", style = tokens.type.title)
        Text(
            "VAN remains operational on the registered non-Jev paths.",
            style = tokens.type.body,
            color = tokens.color.textSecondary,
        )
        Button(onClick = onRetry, modifier = Modifier.padding(top = tokens.space.space3)) { Text("Retry") }
    }
}

@Composable
private fun Overview(snapshot: JevServiceSnapshot, onRefresh: () -> Unit) {
    val tokens = LocalVanTokens.current
    val active = snapshot.modules.count { it.status == "ACTIVE" || it.status == "ACTIVE_GATED" }
    val shadow = snapshot.modules.count { it.status == "SHADOW" }
    val quarantined = snapshot.modules.count { it.status == "QUARANTINED" }
    LazyColumn(verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
                MetricTile("Modules", snapshot.modules.size.toString(), modifier = Modifier.weight(1f))
                MetricTile("Active", active.toString(), modifier = Modifier.weight(1f))
                MetricTile("Shadow", shadow.toString(), modifier = Modifier.weight(1f))
            }
        }
        item {
            VanPanel {
                SectionHeader(
                    "Service state",
                    detail = "Provider availability never becomes authority.",
                    trailing = {
                        StatusChip(
                            snapshot.circuit,
                            if (snapshot.circuit == "HEALTHY") StatusSemantics.ROLE_FAVOURABLE
                            else StatusSemantics.ROLE_EVENT_RISK,
                        )
                    },
                )
                Text(
                    "Deployment switch: ${if (snapshot.serviceEnabled) "enabled" else "disabled"}",
                    style = tokens.type.body, color = tokens.color.textSecondary,
                )
                Text(
                    "Owner activation: ${if (snapshot.global.ownerActive) "on" else "off"} · bypass: ${if (snapshot.global.bypassed) "on" else "off"}",
                    style = tokens.type.body, color = tokens.color.textSecondary,
                )
                Text("Quarantined modules: $quarantined", style = tokens.type.body, color = tokens.color.textSecondary)
            }
        }
        item {
            VanPanel {
                SectionHeader(
                    "Provider qualification",
                    "Configured is not the same as qualified; live eligibility requires evidence.",
                    trailing = {
                        StatusChip(
                            if (snapshot.providerQualified) "QUALIFIED" else if (snapshot.providerConfigured) "UNQUALIFIED" else "UNCONFIGURED",
                            if (snapshot.providerQualified) StatusSemantics.ROLE_FAVOURABLE
                            else if (snapshot.providerConfigured) StatusSemantics.ROLE_EVENT_RISK
                            else StatusSemantics.ROLE_DISABLED,
                        )
                    },
                )
                Text(
                    if (snapshot.providerModels.isEmpty()) "No live-qualified model revision recorded."
                    else "Models: ${snapshot.providerModels.joinToString(", ")}",
                    style = tokens.type.body,
                    color = tokens.color.textSecondary,
                )
            }
        }
        item {
            VanPanel {
                SectionHeader("Domain coverage", "One service, isolated use-case contracts.")
                listOf(
                    "dev." to "Development",
                    "van." to "VAN",
                    "van.trading." to "Trading",
                    "business." to "DIAL Business",
                ).forEach { (prefix, label) ->
                    val count = snapshot.modules.count {
                        it.id.startsWith(prefix) && (prefix != "van." || !it.id.startsWith("van.trading."))
                    }
                    Row(modifier = Modifier.fillMaxWidth().padding(vertical = tokens.space.space1)) {
                        Text(label, modifier = Modifier.weight(1f), style = tokens.type.body)
                        Text(count.toString(), style = tokens.type.data)
                    }
                }
            }
        }
        item { OutlinedButton(onClick = onRefresh, modifier = Modifier.fillMaxWidth()) { Text("Refresh live state") } }
    }
}

@Composable
private fun Modules(modules: List<JevModule>, onSelect: (JevModule) -> Unit) {
    val tokens = LocalVanTokens.current
    var filter by remember { mutableStateOf("ALL") }
    val visible = modules.filter {
        when (filter) {
            "DEV" -> it.id.startsWith("dev.")
            "VAN" -> it.id.startsWith("van.") && !it.id.startsWith("van.trading.")
            "TRADING" -> it.id.startsWith("van.trading.")
            "BUSINESS" -> it.id.startsWith("business.")
            else -> true
        }
    }
    LazyColumn(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                listOf("ALL", "DEV", "VAN", "TRADING", "BUSINESS").forEach { item ->
                    FilterChip(selected = filter == item, onClick = { filter = item }, label = { Text(item) })
                }
            }
        }
        items(visible, key = { it.id }) { module ->
            VanPanel(dense = true, modifier = Modifier.clickable { onSelect(module) }) {
                Row(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(module.id, style = tokens.type.headline)
                        Text(
                            "${module.effectDirection} · ${module.consequence} · ${module.ownerSystem}",
                            style = tokens.type.label,
                            color = tokens.color.textSecondary,
                        )
                    }
                    StatusChip(module.status, statusRole(module.status))
                }
            }
        }
    }
}

@Composable
private fun ModuleDetail(
    module: JevModule,
    contribution: JevContribution?,
    onBack: () -> Unit,
    onLoadContribution: () -> Unit,
    onTransition: (String) -> Unit,
) {
    val tokens = LocalVanTokens.current
    LazyColumn(verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item {
            VanPanel {
                Row(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(module.id, style = tokens.type.title)
                        Text(module.ownerSystem, style = tokens.type.body, color = tokens.color.textSecondary)
                    }
                    StatusChip(module.status, statusRole(module.status))
                }
                HorizontalDivider(modifier = Modifier.padding(vertical = tokens.space.space3))
                Text("Effect: ${module.effectDirection}", style = tokens.type.body)
                Text("Consequence: ${module.consequence}", style = tokens.type.body)
                Text("Fallback: ${module.fallbackClass}", style = tokens.type.body)
                Text("Deadline: ${module.deadlineMs} ms", style = tokens.type.body)
            }
        }
        item {
            VanPanel {
                SectionHeader(
                    "Lifecycle control",
                    "Owner-signed A4 controls. DIAL still enforces the lifecycle ceiling, effect direction and independent review.",
                )
                Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    listOf("SHADOW", "ADVISORY", "ACTIVE_GATED").forEach { state ->
                        OutlinedButton(onClick = { onTransition(state) }) { Text(state) }
                    }
                }
                Row(
                    horizontalArrangement = Arrangement.spacedBy(tokens.space.space2),
                    modifier = Modifier.padding(top = tokens.space.space2),
                ) {
                    Button(onClick = { onTransition("ACTIVE") }) { Text("Active") }
                    OutlinedButton(onClick = { onTransition("DISABLED") }) { Text("Disable") }
                    OutlinedButton(onClick = { onTransition("BYPASSED") }) { Text("Bypass") }
                }
            }
        }
        item {
            VanPanel {
                SectionHeader("Measured contribution", "Counterfactual comparison with the non-Jev path.")
                if (contribution == null) {
                    OutlinedButton(onClick = onLoadContribution) { Text("Load contribution evidence") }
                } else {
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
                        MetricTile("Samples", contribution.sampleCount.toString(), modifier = Modifier.weight(1f))
                        MetricTile("Outcome Δ", "%.3f".format(contribution.outcomeDelta), modifier = Modifier.weight(1f))
                        MetricTile("Composite", "%.3f".format(contribution.composite), modifier = Modifier.weight(1f))
                    }
                    Text(
                        "Cost saved %.3f · latency saved %.0f ms · error cost %.3f".format(
                            contribution.costSavings, contribution.latencySavingsMs, contribution.errorCost,
                        ),
                        style = tokens.type.body, color = tokens.color.textSecondary,
                    )
                }
            }
        }
        item { OutlinedButton(onClick = onBack, modifier = Modifier.fillMaxWidth()) { Text("Back to modules") } }
    }
}

@Composable
private fun Activity(projectId: String, activity: List<JevActivityItem>, onProject: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    LazyColumn(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                listOf("van", "dial-development-system", "dial-business-group").forEach { id ->
                    FilterChip(
                        selected = projectId == id,
                        onClick = { onProject(id) },
                        label = { Text(id.removePrefix("dial-")) },
                    )
                }
            }
        }
        if (activity.isEmpty()) {
            item {
                VanPanel {
                    Text("No trusted outcomes recorded for this project yet.", style = tokens.type.body, color = tokens.color.textSecondary)
                }
            }
        } else {
            items(activity, key = { "${it.requestId}:${it.observedAt}:${it.event}" }) { outcome ->
                VanPanel(dense = true) {
                    Row(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(outcome.moduleId, style = tokens.type.headline)
                            Text("${outcome.event} · ${outcome.provider} · ${outcome.latencyMs} ms", style = tokens.type.label, color = tokens.color.textSecondary)
                            Text(outcome.observedAt, style = tokens.type.label, color = tokens.color.textTertiary)
                        }
                        StatusChip(
                            outcome.lifecycleState.ifBlank { if (outcome.provider == "fallback") "FALLBACK" else "DECISION" },
                            if (outcome.provider == "fallback") StatusSemantics.ROLE_EVENT_RISK else StatusSemantics.ROLE_COGNITION,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun Value(modules: List<JevModule>, performance: JevPerformance?, contribution: JevContribution?, onSelect: (JevModule) -> Unit) {
    val tokens = LocalVanTokens.current
    LazyColumn(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        item {
            VanPanel {
                SectionHeader("Performance & contribution", "Live service telemetry plus counterfactual value against the non-Jev baseline.")
                performance?.let { perf ->
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
                        MetricTile("Decisions", perf.decisions.toString(), modifier = Modifier.weight(1f))
                        MetricTile("p50", "%.0f ms".format(perf.p50LatencyMs), modifier = Modifier.weight(1f))
                        MetricTile("Fallback", "%.1f%%".format(perf.fallbackRate * 100), modifier = Modifier.weight(1f))
                    }
                }
                contribution?.let {
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
                        MetricTile("Samples", it.sampleCount.toString(), modifier = Modifier.weight(1f))
                        MetricTile("Cost saved", "%.3f".format(it.costSavings), modifier = Modifier.weight(1f))
                        MetricTile("Latency", "%.0f ms".format(it.latencySavingsMs), modifier = Modifier.weight(1f))
                    }
                }
            }
        }
        items(modules, key = { it.id }) { module ->
            VanPanel(dense = true, modifier = Modifier.clickable { onSelect(module) }) {
                Row(modifier = Modifier.fillMaxWidth()) {
                    Text(module.id, modifier = Modifier.weight(1f), style = tokens.type.body)
                    StatusChip(module.status, statusRole(module.status))
                }
            }
        }
    }
}

@Composable
private fun Controls(snapshot: JevServiceSnapshot, onCommand: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    val ownerEnabled = snapshot.global.ownerActive && !snapshot.global.bypassed
    LazyColumn(verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item {
            VanPanel {
                SectionHeader(
                    "Global control",
                    "The deployment kill switch stays server-side. This switch changes owner activation through the signed A4 path.",
                )
                Row(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("Owner activation", style = tokens.type.headline)
                        Text(
                            if (ownerEnabled) "Eligible qualified modules may use Jev." else "All modules use registered non-Jev paths.",
                            style = tokens.type.body, color = tokens.color.textSecondary,
                        )
                    }
                    Switch(
                        checked = ownerEnabled,
                        onCheckedChange = { enabled -> onCommand(if (enabled) "enable jev" else "disable jev") },
                    )
                }
                Row(
                    horizontalArrangement = Arrangement.spacedBy(tokens.space.space2),
                    modifier = Modifier.padding(top = tokens.space.space3),
                ) {
                    OutlinedButton(onClick = { onCommand("bypass jev") }) { Text("Bypass") }
                    Button(onClick = { onCommand("restore jev") }) { Text("Restore") }
                }
            }
        }
        item {
            VanPanel {
                SectionHeader("Project switches", "Each division can opt out without disabling the shared service.")
                listOf(
                    "dial-development-system" to "Development System",
                    "van" to "VAN",
                    "dial-business-group" to "DIAL Business",
                ).forEach { (projectId, label) ->
                    val enabled = snapshot.global.projects[projectId] ?: true
                    Row(modifier = Modifier.fillMaxWidth().padding(vertical = tokens.space.space1)) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(label, style = tokens.type.headline)
                            Text(projectId, style = tokens.type.label, color = tokens.color.textSecondary)
                        }
                        Switch(
                            checked = enabled,
                            onCheckedChange = { on ->
                                onCommand("${if (on) "enable" else "disable"} jev for project $projectId")
                            },
                        )
                    }
                }
            }
        }
        item {
            VanPanel {
                SectionHeader("Privacy & authority")
                Text("Android never receives TypeSafe credentials.", style = tokens.type.body)
                Text("RESTRICTED/SECRET data is refused before provider egress.", style = tokens.type.body)
                Text("Jev outputs remain evidence with authority_effect=NONE.", style = tokens.type.body)
                Text("VATI remains sole trading risk, sizing and execution authority.", style = tokens.type.body)
            }
        }
    }
}
