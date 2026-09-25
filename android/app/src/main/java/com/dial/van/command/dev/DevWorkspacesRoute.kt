package com.dial.van.command.dev

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.withStyle
import com.dial.van.VanApplication
import com.dial.van.command.nav.VanRoute
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanPressable
import com.dial.van.design.components.VanScreen
import com.dial.van.dialdev.DevDiff
import com.dial.van.dialdev.DevTerminalTail
import com.dial.van.dialdev.DevWorkspace
import com.dial.van.dialdev.DialDevActionKind
import com.dial.van.dialdev.DialDevActionTarget
import com.dial.van.dialdev.DialDevConsequence
import com.dial.van.dialdev.DialDevFabricParse
import com.dial.van.dialdev.DialDevFreshness
import com.dial.van.dialdev.DialDevHealth
import com.dial.van.dialdev.DialDevResult
import com.dial.van.dialdev.DialDevRoles
import com.dial.van.dialdev.TerminalSpan

/**
 * `work/dev/workspaces` — Orca workspaces (VAN-DEVCC-R1 §6.6, VAN-DEV-007). Stale after 10 s.
 *
 * @DataSource("GET /v1/dial-dev/workspaces") — workspace, task, harness/model, host, branch,
 *   status, lease, last activity, tests, diff stats, last checkpoint.
 */
@Composable
fun DevWorkspacesRoute(app: VanApplication, nav: DevNavigator) {
    val tokens = LocalVanTokens.current
    val list = rememberDevProjection(
        app = app,
        key = "workspaces",
        sections = setOf("workspaces"),
        emptySentence = "No Orca workspaces are open.",
        staleThresholdMs = DialDevFreshness.WORKSPACES_STALE_MS,
        isEmpty = { rows: List<DevWorkspace> -> rows.isEmpty() },
        parse = { DialDevFabricParse.workspaces(it.data) },
        fetch = { app.gatewayClient.dialDev.workspaces() },
    )
    VanScreen(state = list.state, onRetry = list.reload) { rows ->
        DevPage {
            item { SectionHeader("Orca workspaces", detail = "${rows.size} open") }
            rows.forEach { ws ->
                item(key = ws.workspaceId) {
                    VanPressable(
                        onClick = { nav.open(VanRoute.devWorkspaceRoute(ws.workspaceId)) },
                        modifier = Modifier.fillMaxWidth(),
                        contentDescription = "Workspace ${ws.workspaceId}, ${ws.status ?: "status not reported"}. Open.",
                    ) {
                        VanPanel(dense = true) {
                            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                                Text(ws.workspaceId, style = tokens.type.body, color = tokens.color.textPrimary)
                                Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                                    StatusChip(label = DialDevRoles.chipLabel(ws.status), role = DialDevRoles.roleOrDisabled(DialDevHealth.parse(ws.status), DialDevRoles::health))
                                    StatusChip(label = "TESTS ${DialDevRoles.chipLabel(ws.testState)}", role = DialDevRoles.roleOrDisabled(DialDevResult.parse(ws.testState), DialDevRoles::result))
                                }
                                Text(listOfNotNull(ws.taskId, ws.harness, ws.model, ws.host).joinToString(" · "), style = tokens.type.label, color = tokens.color.textTertiary)
                                Text(listOfNotNull(ws.branch, ws.leaseId?.let { "lease $it" }, ws.lastActivity).joinToString(" · "), style = tokens.type.label, color = tokens.color.textTertiary)
                                Text(diffLine(ws) + " · checkpoint ${ws.lastCheckpoint ?: "none reported"}", style = tokens.type.data, color = tokens.color.textSecondary)
                            }
                        }
                    }
                }
            }
            item { DevRevisionFooter(list.envelope) }
        }
    }
}

private enum class WorkspaceTab(val label: String) { OVERVIEW("Overview"), DIFF("Diff"), TERMINAL("Terminal"), EVIDENCE("Evidence") }

/**
 * `work/dev/workspaces/{workspaceId}` — one workspace: Overview · Diff · Terminal · Evidence.
 *
 * @DataSource("GET /v1/dial-dev/workspaces/{id}") — the workspace and its projected actions.
 * @DataSource("GET /v1/dial-dev/workspaces/{id}/diff") — file list first; hunks on demand.
 * @DataSource("GET /v1/dial-dev/workspaces/{id}/terminal-tail?lines=200") — read-only,
 *   secret-screened by DIAL, at most 200 lines. There is no input box: VAN never types into an
 *   Orca terminal. Guidance goes through Steer, which DIAL Hermes relays at a safe boundary.
 */
@Composable
fun DevWorkspaceDetailRoute(app: VanApplication, workspaceId: String, nav: DevNavigator) {
    val tokens = LocalVanTokens.current
    var tab by rememberSaveable { mutableStateOf(WorkspaceTab.OVERVIEW.name) }
    val selected = WorkspaceTab.entries.firstOrNull { it.name == tab } ?: WorkspaceTab.OVERVIEW
    val detail = rememberDevProjection(
        app = app,
        key = "workspace:$workspaceId",
        sections = setOf("workspaces", "workspace:$workspaceId", "actions"),
        emptySentence = "DIAL has no workspace $workspaceId.",
        staleThresholdMs = DialDevFreshness.WORKSPACES_STALE_MS,
        parse = { DialDevFabricParse.workspace(it.data) },
        fetch = { app.gatewayClient.dialDev.workspace(workspaceId) },
    )
    val loaded = detail.envelope?.let { DialDevFabricParse.workspace(it.data) }
    val actions = rememberDevActions(
        app, detail,
        DialDevActionTarget(taskId = loaded?.taskId, workspaceId = workspaceId),
        loaded?.projectedActions.orEmpty(),
    )
    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        SectionHeader("Workspace", detail = workspaceId)
        LazyRow(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            items(WorkspaceTab.entries.toList(), key = { it.name }) { option ->
                val active = option == selected
                VanPressable(onClick = { tab = option.name }, contentDescription = "${option.label} tab") {
                    StatusChip(label = option.label, role = if (active) StatusSemantics.ROLE_ENGAGED else StatusSemantics.ROLE_DISABLED, filled = active)
                }
            }
        }
        when (selected) {
            WorkspaceTab.OVERVIEW -> VanScreen(state = detail.state, onRetry = detail.reload) { ws ->
                DevPage {
                    item {
                        DevTaskActionBar(
                            actions = actions,
                            currentIntent = ws.intent,
                            nextAction = ws.nextAction,
                            revokeConsequence = DialDevConsequence.revoke(
                                ws.taskId ?: ws.workspaceId, ws.leaseId, ws.uncommittedFiles, ws.consequences[DialDevActionKind.REVOKE_TASK.name],
                            ),
                            confirmText = ws.taskId ?: ws.workspaceId,
                        )
                    }
                    item {
                        DevFieldGroup(
                            "Overview",
                            listOf(
                                "Task" to ws.taskId, "Harness" to ws.harness, "Model" to ws.model, "Host" to ws.host,
                                "Branch" to ws.branch, "Worktree" to ws.worktree, "Lease" to ws.leaseId, "Status" to ws.status,
                                "Terminal" to ws.terminalState, "Tests" to ws.testState, "Diff" to diffLine(ws),
                                "Last checkpoint" to ws.lastCheckpoint, "Last activity" to ws.lastActivity,
                            ),
                        )
                    }
                    ws.taskId?.let { id ->
                        item {
                            VanPressable(onClick = { nav.open(VanRoute.devTaskRoute(id)) }, contentDescription = "Open task $id") {
                                Text("Open task $id", style = tokens.type.label, color = tokens.color.accentCyan)
                            }
                        }
                    }
                    item { DevRevisionFooter(detail.envelope) }
                }
            }
            WorkspaceTab.DIFF -> DevDiffTab(app, workspaceId)
            WorkspaceTab.TERMINAL -> DevTerminalTab(app, workspaceId)
            WorkspaceTab.EVIDENCE -> VanScreen(state = detail.state, onRetry = detail.reload) { ws ->
                DevPage {
                    if (ws.evidence.isEmpty()) item { DevNote("DIAL reports no evidence for this workspace.") }
                    ws.evidence.forEach { ref ->
                        item(key = ref.ref) { DevEvidenceItem(ref) { nav.open(VanRoute.devEvidenceRoute(it)) } }
                    }
                }
            }
        }
    }
}

@Composable
private fun DevDiffTab(app: VanApplication, workspaceId: String) {
    val tokens = LocalVanTokens.current
    val diff = rememberDevProjection(
        app = app,
        key = "diff:$workspaceId",
        sections = setOf("workspaces", "workspace:$workspaceId", "diff"),
        emptySentence = "No changes in this worktree.",
        staleThresholdMs = DialDevFreshness.WORKSPACES_STALE_MS,
        isEmpty = { d: DevDiff -> d.files.isEmpty() },
        parse = { DialDevFabricParse.diff(it.data) },
        fetch = { app.gatewayClient.dialDev.workspaceDiff(workspaceId) },
    )
    var openPath by remember(workspaceId) { mutableStateOf<String?>(null) }
    VanScreen(state = diff.state, onRetry = diff.reload) { d ->
        DevPage {
            if (d.truncated) item { DevNote("This diff is above DIAL's size bound, so only the file list is shown.", warning = true) }
            d.files.forEach { file ->
                item(key = file.path) {
                    val open = openPath == file.path
                    VanPressable(
                        onClick = { openPath = if (open) null else file.path },
                        modifier = Modifier.fillMaxWidth(),
                        contentDescription = "${file.path}, ${file.additions ?: 0} added, ${file.deletions ?: 0} removed. ${if (open) "Hide" else "Show"} changes.",
                    ) {
                        VanPanel(dense = true) {
                            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                                Text(file.path, style = tokens.type.body, color = tokens.color.textPrimary)
                                Text("${file.status ?: "changed"} · +${file.additions ?: "?"} −${file.deletions ?: "?"}", style = tokens.type.data, color = tokens.color.textSecondary)
                                if (open) {
                                    val hunks = d.hunksFor(file.path)
                                    if (hunks == null) {
                                        DevNote(if (d.truncated) "Hunks not sent: the diff is above the size bound." else "DIAL sent no hunks for this file.")
                                    } else {
                                        Text(
                                            hunks,
                                            style = tokens.type.data.copy(fontFamily = FontFamily.Monospace),
                                            color = tokens.color.textSecondary,
                                            modifier = Modifier.horizontalScroll(rememberScrollState()),
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DevTerminalTab(app: VanApplication, workspaceId: String) {
    val tokens = LocalVanTokens.current
    val tail = rememberDevProjection(
        app = app,
        key = "tail:$workspaceId",
        sections = setOf("workspaces", "workspace:$workspaceId", "terminal"),
        emptySentence = "The terminal has printed nothing yet.",
        staleThresholdMs = DialDevFreshness.WORKSPACES_STALE_MS,
        isEmpty = { t: DevTerminalTail -> t.lines.isEmpty() },
        parse = { DialDevFabricParse.terminalTail(it.data) },
        fetch = { app.gatewayClient.dialDev.workspaceTerminalTail(workspaceId, DevTerminalTail.MAX_LINES) },
    )
    val mono = tokens.type.data.copy(fontFamily = FontFamily.Monospace)
    val redactedRole = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK)
    VanScreen(state = tail.state, onRetry = tail.reload) { t ->
        DevPage {
            item {
                DevNote(
                    "Read-only · last ${t.lines.size} of at most ${DevTerminalTail.MAX_LINES} lines · secrets screened by DIAL" +
                        if (t.truncated) " · older lines not shown" else "",
                )
            }
            t.lines.forEachIndexed { index, spans ->
                item(key = index) {
                    val redactions = spans.count(TerminalSpan::redacted)
                    Text(
                        text = terminalLine(spans, redactedRole),
                        style = mono,
                        color = tokens.color.textSecondary,
                        softWrap = false,
                        modifier = Modifier
                            .horizontalScroll(rememberScrollState())
                            .semantics {
                                contentDescription = spans.joinToString("") { if (it.redacted) " redacted " else it.text } +
                                    if (redactions > 0) " ($redactions redacted)" else ""
                            },
                    )
                }
            }
        }
    }
}

/** Redacted spans are marked visibly (the `eventRisk` role), and announced as "redacted". */
private fun terminalLine(spans: List<TerminalSpan>, redacted: androidx.compose.ui.graphics.Color): AnnotatedString = buildAnnotatedString {
    spans.forEach { span ->
        if (span.redacted) withStyle(SpanStyle(color = redacted)) { append(span.text) } else append(span.text)
    }
}

private fun diffLine(ws: DevWorkspace): String = ws.diffStats?.let {
    "${it.files ?: "?"} files +${it.additions ?: "?"} −${it.deletions ?: "?"}"
} ?: "diff not reported"
