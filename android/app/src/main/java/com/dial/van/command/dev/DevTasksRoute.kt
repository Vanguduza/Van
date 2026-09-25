package com.dial.van.command.dev

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.command.nav.VanRoute
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanPressable
import com.dial.van.design.components.VanScreen
import com.dial.van.dialdev.DevGraph
import com.dial.van.dialdev.DevTaskRow
import com.dial.van.dialdev.DevTaskView
import com.dial.van.dialdev.DialDevParse
import com.dial.van.dialdev.DialDevSemantics

/**
 * `work/dev/{projectId}/tasks?view={view}` — the TODO list (VAN-DEVCC-R1 §6.3, VAN-DEV-006).
 *
 * @DataSource("GET /v1/dial-dev/projects/{p}/tasks?view={view}") — one of §16.3's nine views;
 *   DIAL decides which tasks belong in a view, VAN does not re-filter them.
 *
 * NOT_APPLICABLE rows are hidden (§4); a state this build does not know is shown as itself.
 */
@Composable
fun DevTasksRoute(app: VanApplication, projectId: String, initialView: String?, nav: DevNavigator) {
    val tokens = LocalVanTokens.current
    var view by rememberSaveable { mutableStateOf(DevTaskView.parse(initialView).wire) }
    val selected = DevTaskView.parse(view)
    val tasks = rememberDevProjection(
        app = app,
        key = "tasks:$projectId:${selected.wire}",
        sections = setOf("tasks"),
        emptySentence = "Nothing in ${selected.label.lowercase()} for this project.",
        isEmpty = { rows: List<DevTaskRow> -> rows.isEmpty() },
        parse = { env -> DialDevParse.tasks(env.data, env.observedAt).filter { it.presentation.visibleInLists } },
        fetch = { app.gatewayClient.dialDev.tasks(projectId, selected.wire) },
    )
    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        SectionHeader("Tasks", detail = projectId)
        LazyRow(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            items(DevTaskView.entries.toList(), key = { it.wire }) { option ->
                val active = option == selected
                VanPressable(onClick = { view = option.wire }, contentDescription = "${option.label} view") {
                    StatusChip(label = option.label, role = if (active) StatusSemantics.ROLE_ENGAGED else StatusSemantics.ROLE_DISABLED, filled = active)
                }
            }
            item {
                VanPressable(onClick = { nav.open(VanRoute.devGraphRoute(projectId)) }, contentDescription = "Dependencies") {
                    StatusChip(label = "Dependencies", role = StatusSemantics.ROLE_MONITOR)
                }
            }
        }
        VanScreen(state = tasks.state, onRetry = tasks.reload) { rows ->
            DevPage {
                rows.forEach { task ->
                    item(key = task.taskId) { DevTaskRowItem(task) { nav.open(VanRoute.devTaskRoute(task.taskId)) } }
                }
                item { DevRevisionFooter(tasks.envelope) }
            }
        }
    }
}

/**
 * `work/dev/{projectId}/graph` — dependencies (VAN-DEVCC-R1 §6.3, §5).
 *
 * @DataSource("GET /v1/dial-dev/projects/{p}/graph") — nodes and dependency edges for the
 *   stage plan revision.
 *
 * List-first: every node is a row TalkBack reaches in order (critical path first, marked with
 * the `engaged` role); each row expands to its dependencies and dependents. The optional graph
 * canvas §6.3 allows is not drawn in this build — the list is the complete, accessible view.
 */
@Composable
fun DevGraphRoute(app: VanApplication, projectId: String, nav: DevNavigator) {
    val tokens = LocalVanTokens.current
    val graph = rememberDevProjection(
        app = app,
        key = "graph:$projectId",
        sections = setOf("graph", "tasks", "stage_plan"),
        emptySentence = "DIAL reports no dependency graph for this project yet.",
        isEmpty = { g: DevGraph -> g.nodes.isEmpty() },
        parse = { DialDevParse.graph(it.data) },
        fetch = { app.gatewayClient.dialDev.graph(projectId) },
    )
    var expanded by remember(projectId) { mutableStateOf(setOf<String>()) }
    VanScreen(state = graph.state, onRetry = graph.reload) { data ->
        val titles = data.nodes.associate { it.taskId to (it.title ?: it.taskId) }
        DevPage {
            item { SectionHeader("Dependencies", detail = "${data.nodes.size} tasks · ${data.edges.size} edges") }
            data.accessibleOrder().forEach { node ->
                item(key = node.taskId) {
                    val p = DialDevSemantics.presentRaw(node.rawState)
                    val open = node.taskId in expanded
                    val deps = data.dependenciesOf(node.taskId)
                    val dependents = data.dependentsOf(node.taskId)
                    VanPressable(
                        onClick = { expanded = if (open) expanded - node.taskId else expanded + node.taskId },
                        modifier = Modifier.fillMaxWidth(),
                        contentDescription = "${titles[node.taskId]}. ${p.caption}. " +
                            (if (node.critical) "On the critical path. " else "") +
                            "${deps.size} dependencies, ${dependents.size} dependents. ${if (open) "Collapse" else "Expand"}.",
                    ) {
                        VanPanel(dense = true) {
                            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                                Text(titles[node.taskId].orEmpty(), style = tokens.type.body, color = tokens.color.textPrimary)
                                StatusChip(label = p.caption, role = p.role)
                                if (node.critical) StatusChip(label = "CRITICAL PATH", role = StatusSemantics.ROLE_ENGAGED, filled = true)
                                Text(listOfNotNull(node.taskId, node.stage).joinToString(" · "), style = tokens.type.label, color = tokens.color.textTertiary)
                                if (open) {
                                    DevField("Depends on", deps.joinToString(", ") { titles[it] ?: it }.ifBlank { "nothing" })
                                    DevField("Unblocks", dependents.joinToString(", ") { titles[it] ?: it }.ifBlank { "nothing" })
                                    VanPressable(onClick = { nav.open(VanRoute.devTaskRoute(node.taskId)) }, contentDescription = "Open task ${node.taskId}") {
                                        Text("Open task", style = tokens.type.label, color = tokens.color.accentCyan)
                                    }
                                }
                            }
                        }
                    }
                }
            }
            item { DevRevisionFooter(graph.envelope) }
        }
    }
}
