package com.dial.van.command.dev

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.command.nav.VanRoute
import com.dial.van.design.AttentionSeverity
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.MetricTile
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanPressable
import com.dial.van.design.components.VanScreen
import com.dial.van.dialdev.DevHome
import com.dial.van.dialdev.DevProject
import com.dial.van.dialdev.DialDevActionKind
import com.dial.van.dialdev.DialDevActionPolicy
import com.dial.van.dialdev.DialDevActionReducer
import com.dial.van.dialdev.DialDevActionTarget
import com.dial.van.dialdev.DialDevFormat
import com.dial.van.dialdev.DialDevParse
import com.dial.van.dialdev.DialDevRoles
import com.dial.van.dialdev.DialDevHealth
import kotlinx.coroutines.launch

/**
 * `work/dev` — Development Home (VAN-DEVCC-R1 §6.1, VAN-DEV-005): a hub inside Work, not a new
 * destination. VAN displays DIAL development state and forwards typed owner commands; it plans
 * and executes nothing itself.
 *
 * @DataSource("GET /v1/dial-dev/projects") — the project switcher (admitted DIAL projects).
 * @DataSource("GET /v1/dial-dev/projects/{p}/home") — readiness, counts, Now, Needs you,
 *   Latest and the health strip for the selected project.
 */
@Composable
fun DevHomeRoute(app: VanApplication, initialProjectId: String?, nav: DevNavigator) {
    val projects = rememberDevProjection(
        app = app,
        key = "projects",
        sections = setOf("projects"),
        emptySentence = "No admitted DIAL projects yet.",
        isEmpty = { list: List<DevProject> -> list.isEmpty() },
        parse = { DialDevParse.projects(it.data) },
        fetch = { app.gatewayClient.dialDev.projects() },
    )
    var selected by rememberSaveable { mutableStateOf(initialProjectId) }

    VanScreen(state = projects.state, onRetry = projects.reload) { list ->
        val projectId = selected?.takeIf { id -> list.any { it.projectId == id } } ?: list.first().projectId
        DevHomeBody(app, list, projectId, onSelect = { selected = it }, nav = nav)
    }
}

@Composable
private fun DevHomeBody(
    app: VanApplication,
    projects: List<DevProject>,
    projectId: String,
    onSelect: (String) -> Unit,
    nav: DevNavigator,
) {
    val tokens = LocalVanTokens.current
    val home = rememberDevProjection(
        app = app,
        key = "home:$projectId",
        sections = setOf("home", "tasks", "workspaces", "agents", "evidence", "infrastructure"),
        emptySentence = "DIAL has nothing to report for this project yet.",
        parse = { DialDevParse.home(it.data, it.observedAt) },
        fetch = { app.gatewayClient.dialDev.home(projectId) },
    )
    val actions = rememberDevActions(app, home, DialDevActionTarget(projectId = projectId), home.envelope?.let {
        DialDevActionReducer.parseProjected(it.data)
    }.orEmpty())
    val scope = rememberCoroutineScope()

    DevPage {
        item { SectionHeader("Development", detail = "DIAL, as DIAL reports it") }
        item {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                items(projects, key = { it.projectId }) { project ->
                    val active = project.projectId == projectId
                    VanPressable(onClick = { onSelect(project.projectId) }, contentDescription = "Project ${project.name ?: project.projectId}") {
                        StatusChip(
                            label = project.name ?: project.projectId,
                            role = if (active) StatusSemantics.ROLE_ENGAGED else StatusSemantics.ROLE_DISABLED,
                            filled = active,
                        )
                    }
                }
            }
        }
        item {
            VanScreen(state = home.state, onRetry = home.reload) { data -> DevHomeSummary(data, nav, projectId) }
        }
        item {
            VanPanel {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    Text("Mission", style = tokens.type.headline, color = tokens.color.textPrimary)
                    Text(
                        "Pausing or resuming acts on DIAL's persistent Oracle mission — never a loop on this phone.",
                        style = tokens.type.label,
                        color = tokens.color.textTertiary,
                    )
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        items(listOf(DialDevActionKind.PAUSE_MISSION, DialDevActionKind.RESUME_MISSION)) { kind ->
                            OutlinedButton(onClick = { scope.launch { actions.submit(kind, emptyMap()) } }) {
                                Text(DialDevActionPolicy.label(kind), style = tokens.type.label)
                            }
                        }
                    }
                    DevActionStatusRows(actions)
                }
            }
        }
        item { SectionHeader("Inside development") }
        DevHubLinks.forEach { link ->
            item(key = link.title) {
                VanPressable(
                    onClick = { link.open(nav, projectId) },
                    modifier = Modifier.fillMaxWidth(),
                    contentDescription = "${link.title}. ${link.detail}.",
                ) {
                    VanPanel(dense = true) {
                        Column {
                            Text(link.title, style = tokens.type.headline, color = tokens.color.textPrimary)
                            Text(link.detail, style = tokens.type.body, color = tokens.color.textSecondary)
                        }
                    }
                }
            }
        }
        item { DevRevisionFooter(home.envelope) }
    }
}

@Composable
private fun DevHomeSummary(data: DevHome, nav: DevNavigator, projectId: String) {
    val tokens = LocalVanTokens.current
    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        LazyRow(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            item { StatusChip(label = "FORENSIC BUILD ${DialDevRoles.chipLabel(data.forensicBuildReady)}", role = readinessRole(data.forensicBuildReady)) }
            item { StatusChip(label = "ORACLE ${DialDevRoles.chipLabel(data.oracleGate)}", role = readinessRole(data.oracleGate)) }
            item { StatusChip(label = "SLOTS ${data.runtimeSlots ?: "—"}", role = StatusSemantics.ROLE_MONITOR) }
        }
        LazyRow(horizontalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
            items(DevHome.COUNT_KEYS) { (key, label) ->
                MetricTile(
                    label = label,
                    value = DialDevFormat.count(data.counts[key]),
                    onClick = { nav.open(VanRoute.devTasksRoute(projectId, countView(key))) },
                )
            }
        }
        SectionHeader("Now", detail = if (data.now.isEmpty()) "Nothing in progress" else null)
        data.now.forEach { task -> DevTaskRowItem(task) { nav.open(VanRoute.devTaskRoute(task.taskId)) } }
        SectionHeader("Needs you", detail = if (data.needsYou.isEmpty()) "Nothing waiting on you" else null)
        data.needsYou.forEach { item ->
            val target = item.deepLink?.let(VanRoute::parseDeepLink) ?: item.taskId?.let(VanRoute::devTaskRoute)
            val severity = AttentionSeverity.entries.firstOrNull { it.name == item.severity?.uppercase() }
            VanPressable(
                onClick = { target?.let(nav::open) },
                enabled = target != null,
                modifier = Modifier.fillMaxWidth(),
                contentDescription = "${item.title}. Open.",
            ) {
                VanPanel(dense = true) {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Text(item.title, style = tokens.type.body, color = tokens.color.textPrimary)
                        StatusChip(
                            label = DialDevRoles.chipLabel(item.severity),
                            role = severity?.let(StatusSemantics::forAttentionSeverity) ?: StatusSemantics.ROLE_DISABLED,
                        )
                    }
                }
            }
        }
        SectionHeader("Latest")
        DevField("Last checkpoint", data.latestCheckpoint)
        if (data.latestEvidence.isEmpty()) DevNote("DIAL reported no recent CI or runtime evidence.")
        data.latestEvidence.forEach { ref -> DevEvidenceItem(ref) { nav.open(VanRoute.devEvidenceRoute(it)) } }
        SectionHeader("Health")
        if (data.health.isEmpty()) DevNote("DIAL reported no subsystem health.")
        else DevHealthStrip(data.health) { nav.open(VanRoute.CONNECTED) }
    }
}

/** Readiness words go through the same exhaustive health vocabulary as every other chip. */
private fun readinessRole(raw: String?): String = DialDevRoles.roleOrDisabled(DialDevHealth.parse(raw), DialDevRoles::health)

private fun countView(key: String): String = when (key) {
    "ready" -> "next"
    "running" -> "in_progress"
    "blocked" -> "blocked"
    "needs_you" -> "needs_me"
    "in_review" -> "review"
    else -> "all"
}

/** The hub's children (§2.1), in the order the owner reads them. */
private class DevHubLink(val title: String, val detail: String, val open: (DevNavigator, String) -> Unit)

private val DevHubLinks = listOf(
    DevHubLink("Stage plan", "STG-00…STG-21, applicability, evidence, blockers") { n, p -> n.open(VanRoute.devPlanRoute(p)) },
    DevHubLink("Tasks", "Now · Next · In progress · Needs me · Blocked · Review · Failed · Completed") { n, p -> n.open(VanRoute.devTasksRoute(p)) },
    DevHubLink("Dependencies", "The task graph as a list, critical path first") { n, p -> n.open(VanRoute.devGraphRoute(p)) },
    DevHubLink("Active agents", "Who is doing what, their intent and owned paths") { n, _ -> n.open(VanRoute.WORK_DEV_AGENTS) },
    DevHubLink("Orca workspaces", "Worktrees, leases, diffs and read-only terminal tails") { n, _ -> n.open(VanRoute.WORK_DEV_WORKSPACES) },
    DevHubLink("Reviews", "Independent review jobs and blocking findings") { n, _ -> n.open(VanRoute.WORK_DEV_REVIEWS) },
    DevHubLink("Memory & handoffs", "Shared-memory cursor, checkpoints, admission queue") { n, _ -> n.open(VanRoute.WORK_DEV_MEMORY) },
    DevHubLink("Research / VEKL", "Knowledge activations, forecasts, research jobs") { n, _ -> n.open(VanRoute.WORK_DEV_RESEARCH) },
    DevHubLink("Frontend / Design", "Screen × feature coverage and design authority") { n, _ -> n.open(VanRoute.WORK_DEV_DESIGN) },
    DevHubLink("Build / CI", "Latest runs per branch with evidence") { n, _ -> n.open(VanRoute.WORK_DEV_CI) },
    DevHubLink("Security", "Open findings, specialist review, mutation suite") { n, _ -> n.open(VanRoute.WORK_DEV_SECURITY) },
    DevHubLink("Android testing (ARTEMIS)", "DIAL's Android harness, through the existing console") { n, _ -> n.open(VanRoute.WORK_ARTEMIS) },
)
