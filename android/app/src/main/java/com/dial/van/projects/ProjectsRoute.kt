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
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanPressable
import com.dial.van.design.components.VanScreen
import com.dial.van.memory.MemoryReadModel
import com.dial.van.mission.MissionParsing
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * DNA §4 destination 6: "Projects — health, phase, current work, blockers, decisions, next
 * actions." This is the list; `ProjectDetailRoute` is the per-project screen.
 *
 * @DataSource("GET /v1/projects") — the known project ids (`registries/projects.json`'s own
 * shape: a bare id list, no name/phase/health — `backend/van_gateway/projects/router.py`).
 * @DataSource("GET /v1/projects/{id}/truth") — once per project.
 * @DataSource("GET /v1/missions") — all missions, filtered client-side by `project_id`
 * (`/v1/missions` has no project filter param).
 * @DataSource("GET /v1/attention") — for the blocker count each project's health folds in.
 * @DataSource("GET /v1/context/export") — for each project's last-change signal
 * (`contextExport()`; see this worker's report — not yet on `VanGatewayClient`).
 *
 * There is no project *name* anywhere in this API — only the id `registries/projects.json`
 * assigns it — so a card's title is the id itself, not an invented display name.
 */
private data class ProjectsData(
    val summaries: List<ProjectSummary>,
)

@Composable
fun ProjectsRoute(app: VanApplication, onOpenProject: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    var data by remember { mutableStateOf<ProjectsData?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }

    fun load() {
        scope.launch {
            loading = true
            runCatching {
                val ids = app.gatewayClient.projects().objectListOrStrings()
                val missions = MissionParsing.missionSummaries(app.gatewayClient.missions())
                val attention = app.gatewayClient.attention().objectList()
                val facts = runCatching { MemoryReadModel.parseExportFacts(app.gatewayClient.contextExport()) }
                    .getOrDefault(emptyList())
                val summaries = ids.map { id ->
                    val truthJson = runCatching { app.gatewayClient.projectTruth(id) }.getOrNull()
                    val truth = truthJson?.let { ProjectTruthParsing.parse(id, it) }
                    ProjectSummaryBuilder.build(id, truth, missions, attention, facts)
                }
                ProjectsData(summaries)
            }.onSuccess { data = it; error = null; loading = false }
                .onFailure { error = it.message ?: "VAN could not reach the projects it knows about."; loading = false }
        }
    }
    LaunchedEffect(Unit) { load() }

    val state: ScreenState<ProjectsData> = ScreenStateMerge.merge(
        content = data,
        loading = loading,
        errorMessage = error,
        emptySentence = "VAN does not have any projects registered.",
    )

    VanScreen(state = state, onRetry = ::load) { projects ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter),
            verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
            contentPadding = PaddingValues(vertical = tokens.space.space3),
        ) {
            item { SectionHeader("Projects", detail = "Health, phase, blockers, next actions") }

            if (projects.summaries.isEmpty()) {
                item { Text("No projects registered.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }

            items(projects.summaries, key = { it.projectId }) { summary ->
                VanPressable(onClick = { onOpenProject(summary.projectId) }, contentDescription = "Open project ${summary.projectId}") {
                    VanPanel(modifier = Modifier.fillMaxWidth()) {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                                Text(summary.projectId, style = tokens.type.headline, color = tokens.color.textPrimary)
                                StatusChip(label = summary.health.name, role = ProjectHealthPalette.roleFor(summary.health))
                            }
                            Text(summary.phase, style = tokens.type.body, color = tokens.color.textSecondary)
                            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
                                Text("${summary.runningMissionsCount} running", style = tokens.type.label, color = tokens.color.textTertiary)
                                Text("${summary.blockersCount} blockers", style = tokens.type.label, color = tokens.color.textTertiary)
                            }
                        }
                    }
                }
            }
        }
    }
}

/** `GET /v1/projects` returns `{"projects": ["van", "dial", ...]}` — a bare string array. */
private fun org.json.JSONArray.objectListOrStrings(): List<String> = buildList {
    for (i in 0 until length()) {
        val v = opt(i)
        when (v) {
            is String -> add(v)
            is JSONObject -> v.optString("id").takeIf { it.isNotBlank() }?.let(::add)
            else -> {}
        }
    }
}
