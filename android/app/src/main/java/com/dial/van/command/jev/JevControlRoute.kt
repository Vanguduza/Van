package com.dial.van.command.jev

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.ScrollableTabRow
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
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.VanPanel
import kotlinx.coroutines.launch

internal enum class JevTab(val label: String) {
    OVERVIEW("Overview"), MODULES("Modules"), ACTIVITY("Activity"), VALUE("Value"), CONTROLS("Controls")
}

internal fun jevStatusRole(status: String): String = when (status.uppercase()) {
    "ACTIVE" -> StatusSemantics.ROLE_FAVOURABLE
    "ACTIVE_GATED" -> StatusSemantics.ROLE_ENGAGED
    "ADVISORY" -> StatusSemantics.ROLE_COGNITION
    "SHADOW" -> StatusSemantics.ROLE_HYPOTHESIS
    "QUARANTINED" -> StatusSemantics.ROLE_CRITICAL
    "BYPASSED" -> StatusSemantics.ROLE_EVENT_RISK
    else -> StatusSemantics.ROLE_DISABLED
}

internal fun projectFor(module: JevModule): String =
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
    var evaluationProposals by remember { mutableStateOf<List<JevEvaluationProposal>>(emptyList()) }
    var evaluationReviews by remember { mutableStateOf<List<JevEvaluationReview>>(emptyList()) }
    var candidateRevisions by remember { mutableStateOf<List<JevCandidateRevision>>(emptyList()) }

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
            runCatching { repository.evaluationProposals(limit = 50) }
                .onSuccess { evaluationProposals = it }
            runCatching { repository.evaluationReviews(limit = 50) }
                .onSuccess { evaluationReviews = it }
            runCatching { repository.evaluationCandidates(limit = 50) }
                .onSuccess { candidateRevisions = it }
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

    fun operationalCommand(text: String, projectId: String? = "dial-development-system") {
        app.commandController.submitText(
            text = text,
            source = VanCommandSource.SYSTEM,
            projectId = projectId,
            actionClass = "A2",
            noStaleReplay = false,
        )
    }

    fun requestEvaluation(module: JevModule) {
        app.commandController.submitText(
            text = "Evaluate Jev marginal contribution for ${module.id} in project ${projectFor(module)}. " +
                "Use the Jev evaluation packet, trusted downstream outcomes and non-Jev counterfactual baseline. " +
                "Recommend only KEEP, RECALIBRATE, REVISE, DEMOTE, QUARANTINE, RETIRE or DETACH_GLOBAL. " +
                "Do not mutate lifecycle state; record the proposal for independent review.",
            source = VanCommandSource.SYSTEM,
            projectId = projectFor(module),
            actionClass = "A2",
            noStaleReplay = false,
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
                tabIndex == JevTab.VALUE.ordinal -> Value(
                    modules = snapshot!!.modules,
                    performance = performance,
                    contribution = selectedContribution,
                    proposals = evaluationProposals,
                    reviews = evaluationReviews,
                    candidates = candidateRevisions,
                    onSelect = { module ->
                        selectedModule = module
                        loadContribution(module)
                    },
                    onEvaluate = ::requestEvaluation,
                )
                else -> Controls(
                    snapshot = snapshot!!,
                    onOwnerMutation = { ownerCommand(it) },
                    onOperationalRequest = { operationalCommand(it) },
                )
            }
        }
    }
}

@Composable
internal fun JevLoading() {
    val tokens = LocalVanTokens.current
    VanPanel { Text("Loading Jev control plane…", style = tokens.type.body, color = tokens.color.textSecondary) }
}

@Composable
internal fun JevUnavailable(onRetry: () -> Unit) {
    val tokens = LocalVanTokens.current
    VanPanel {
        Text("Jev projection is unavailable.", style = tokens.type.title)
        Text(
            "VAN remains operational on the registered non-Jev paths.",
            style = tokens.type.body,
            color = tokens.color.textSecondary,
        )
        OutlinedButton(onClick = onRetry, modifier = Modifier.padding(top = tokens.space.space3)) { Text("Retry") }
    }
}
