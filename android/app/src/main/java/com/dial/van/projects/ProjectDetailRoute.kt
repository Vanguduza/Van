package com.dial.van.projects

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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.command.objectList
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.ScreenState
import com.dial.van.design.ScreenStateMerge
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.LiveBadge
import com.dial.van.design.components.LiveBadgeState
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanScreen
import com.dial.van.memory.MemoryReadModel
import com.dial.van.memory.ProvenanceTiers
import com.dial.van.mission.MissionParsing
import kotlinx.coroutines.launch

/**
 * DNA §4 destination 6's per-project screen: "health, phase, current work, blockers,
 * decisions, next actions." Same data sources as `ProjectsRoute`, scoped to one
 * `projectId`, plus `GET /v1/decisions` (filtered client-side — the `decisions` table has
 * no `project_id` column) and the project-scoped slice of `GET /v1/context/export`.
 */
private data class ProjectDetailData(
    val model: ProjectDetailModel,
)

@Composable
fun ProjectDetailRoute(
    app: VanApplication,
    projectId: String,
    onBack: () -> Unit,
    onAskVan: (String) -> Unit = {},
) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    var data by remember { mutableStateOf<ProjectDetailData?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }

    fun load() {
        scope.launch {
            loading = true
            runCatching {
                val truthJson = runCatching { app.gatewayClient.projectTruth(projectId) }.getOrNull()
                val truth = truthJson?.let { ProjectTruthParsing.parse(projectId, it) }
                val missions = MissionParsing.missionSummaries(app.gatewayClient.missions())
                val attention = app.gatewayClient.attention().objectList()
                val decisions = app.gatewayClient.decisions().objectList()
                val facts = runCatching { MemoryReadModel.parseExportFacts(app.gatewayClient.contextExport()) }
                    .getOrDefault(emptyList())
                ProjectDetailData(
                    ProjectDetailBuilder.build(projectId, truth, missions, attention, decisions, facts),
                )
            }.onSuccess { data = it; error = null; loading = false }
                .onFailure { error = it.message ?: "VAN could not open this project."; loading = false }
        }
    }
    LaunchedEffect(projectId) { load() }

    val state: ScreenState<ProjectDetailData> = ScreenStateMerge.merge(
        content = data,
        loading = loading,
        errorMessage = error,
        emptySentence = "VAN has nothing on this project yet.",
    )

    VanScreen(state = state, onRetry = ::load) { detail ->
        val model = detail.model
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter),
            verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
            contentPadding = PaddingValues(vertical = tokens.space.space3),
        ) {
            item {
                SectionHeader(
                    model.projectId,
                    detail = model.phase,
                    trailing = { StatusChip(label = model.health.name, role = ProjectHealthPalette.roleFor(model.health)) },
                )
            }

            item {
                VanPanel {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Text("Project Truth", style = tokens.type.headline, color = tokens.color.textPrimary)
                        val truth = model.truth
                        if (truth == null || truth.truthSha == null) {
                            Text("VAN has never loaded this project's truth.", style = tokens.type.body, color = tokens.color.textSecondary)
                        } else {
                            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                                truthBadge(truth)
                            }
                            Text("truth ${truth.truthSha.take(12)}", style = tokens.type.label, color = tokens.color.textTertiary)
                            truth.repoSha?.let { repoSha ->
                                Text("repo ${repoSha.take(12)}", style = tokens.type.label, color = tokens.color.textTertiary)
                            }
                            if (!truth.ok) {
                                Text(truth.error ?: "Truth is stale.", style = tokens.type.label, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK))
                            }
                        }
                        Button(onClick = { onAskVan("What is the state of $projectId?") }) {
                            Text("Ask VAN about this project", style = tokens.type.label)
                        }
                    }
                }
            }

            item { SectionHeader("Current work", detail = "${model.currentWork.size} running") }
            if (model.currentWork.isEmpty()) {
                item { Text("Nothing running on this project right now.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            items(model.currentWork, key = { "work:" + it.missionId }) { mission ->
                VanPanel(dense = true) {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Text(mission.title.ifBlank { mission.goal }, style = tokens.type.body, color = tokens.color.textPrimary)
                        Text(mission.ownerReadableStatus, style = tokens.type.label, color = tokens.color.textTertiary)
                    }
                }
            }

            item { SectionHeader("Blockers", detail = if (model.blockedMissions.isEmpty() && model.blockerAttention.isEmpty()) "None" else null) }
            if (model.blockedMissions.isEmpty() && model.blockerAttention.isEmpty()) {
                item { Text("Nothing is blocking this project.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            items(model.blockedMissions, key = { "blockedmission:" + it.missionId }) { mission ->
                VanPanel(dense = true) {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Text(mission.title.ifBlank { mission.goal }, style = tokens.type.body, color = tokens.color.textPrimary)
                        Text(mission.ownerReadableStatus, style = tokens.type.label, color = tokens.color.forStatusRole(StatusSemantics.ROLE_CRITICAL))
                    }
                }
            }
            items(model.blockerAttention, key = { "blockerattn:" + it.optString("id") }) { item ->
                VanPanel(dense = true) {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Text(item.optString("title", "Attention item"), style = tokens.type.body, color = tokens.color.textPrimary)
                        StatusChip(label = item.optString("severity", "BLOCKER"), role = StatusSemantics.ROLE_CRITICAL)
                    }
                }
            }

            item { SectionHeader("Recent changes") }
            if (model.recentChanges.isEmpty()) {
                item { Text("No mission activity recorded yet.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            items(model.recentChanges, key = { "recent:" + it.missionId }) { mission ->
                VanPanel(dense = true) {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Text(mission.title.ifBlank { mission.goal }, style = tokens.type.body, color = tokens.color.textPrimary)
                        Text(mission.ownerReadableStatus, style = tokens.type.label, color = tokens.color.textTertiary)
                    }
                }
            }

            item { SectionHeader("Decisions", detail = "${model.decisions.size} mentioning this project") }
            if (model.decisions.isEmpty()) {
                item { Text("No decisions mention this project yet.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            items(model.decisions, key = { "decision:" + it.optString("id") }) { decision ->
                VanPanel(dense = true) {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Text(decision.optString("title", "Decision"), style = tokens.type.body, color = tokens.color.textPrimary)
                        Text(decision.optString("body"), style = tokens.type.label, color = tokens.color.textSecondary)
                    }
                }
            }

            item {
                SectionHeader(
                    "Next actions",
                    detail = if (model.nextActions.isEmpty()) "Nothing open" else "${model.nextActions.size} open",
                )
            }
            if (model.nextActions.isEmpty()) {
                item { Text("VAN has nothing waiting on you for this project.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            items(model.nextActions, key = { "next:" + it.optString("id") }) { item ->
                VanPanel(dense = true) {
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Column(modifier = Modifier.fillMaxWidth()) {
                            Text(item.optString("title", "Attention item"), style = tokens.type.body, color = tokens.color.textPrimary)
                        }
                        StatusChip(
                            label = item.optString("severity", "INFO"),
                            role = severityRoleFor(item.optString("severity", "INFO")),
                        )
                    }
                }
            }

            item { SectionHeader("Relevant context", detail = "${model.relevantFacts.size} facts") }
            if (model.relevantFacts.isEmpty()) {
                item { Text("VAN holds no facts scoped to this project.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            items(model.relevantFacts, key = { "fact:" + it.factId }) { fact ->
                VanPanel(dense = true) {
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Column(modifier = Modifier.fillMaxWidth()) {
                            Text(fact.predicate.replace('_', ' '), style = tokens.type.body, color = tokens.color.textPrimary)
                            Text(fact.value, style = tokens.type.label, color = tokens.color.textSecondary)
                        }
                        val tier = ProvenanceTiers.forAuthority(fact.authority)
                        StatusChip(label = tier.name, role = ProvenanceTiers.statusRole(tier))
                    }
                }
            }
        }
    }
}

@Composable
private fun truthBadge(truth: ProjectTruthSnapshot) {
    val ageMs = truth.updatedAtUnixSec?.let { (System.currentTimeMillis() - it * 1000L).coerceAtLeast(0L) }
    val state = when {
        !truth.ok -> LiveBadgeState.Stale(ageMs ?: 0L)
        ageMs != null && ageMs >= ScreenStateMerge.DEFAULT_STALE_THRESHOLD_MS -> LiveBadgeState.Stale(ageMs)
        else -> LiveBadgeState.Live
    }
    LiveBadge(state = state)
}

private fun severityRoleFor(severity: String): String = when (severity) {
    "URGENT" -> StatusSemantics.ROLE_CRITICAL
    "BLOCKER" -> StatusSemantics.ROLE_EVENT_RISK
    "FOLLOW_UP" -> StatusSemantics.ROLE_COGNITION
    else -> StatusSemantics.ROLE_MONITOR
}
