package com.dial.van.command.dev

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import com.dial.van.VanApplication
import com.dial.van.command.nav.VanRoute
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.TimelineEvent
import com.dial.van.design.components.TimelineRail
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanScreen
import com.dial.van.dialdev.DevTaskDetail
import com.dial.van.dialdev.DialDevActionKind
import com.dial.van.dialdev.DialDevActionTarget
import com.dial.van.dialdev.DialDevConsequence
import com.dial.van.dialdev.DialDevFormat
import com.dial.van.dialdev.DialDevParse
import com.dial.van.dialdev.DialDevProgressEvent
import com.dial.van.dialdev.DialDevResult
import com.dial.van.dialdev.DialDevRoles
import com.dial.van.dialdev.DialDevState

/**
 * `work/dev/tasks/{taskId}` — one TODO record (VAN-DEVCC-R1 §6.4, VAN-DEV-006/009).
 *
 * @DataSource("GET /v1/dial-dev/tasks/{taskId}") — the Rev 1 §16.3 record, its progress
 *   timeline, lease, workspace, evidence refs and the projection's own `actions[]`.
 *
 * Actions (§3.3): Steer, Pause safely, Resume, Request checkpoint, Request review, Revoke —
 * each `POST /v1/dial-dev/actions` via `postProved`, none marked done by VAN. The ARTEMIS link
 * appears only when DIAL reports an Android verification for this task.
 */
@Composable
fun DevTaskDetailRoute(app: VanApplication, taskId: String, nav: DevNavigator) {
    val tokens = LocalVanTokens.current
    val detail = rememberDevProjection(
        app = app,
        key = "task:$taskId",
        sections = setOf("tasks", "task:$taskId", "workspaces", "evidence", "actions"),
        emptySentence = "DIAL has no record of task $taskId.",
        parse = { DialDevParse.taskDetail(it.data, it.observedAt) },
        fetch = { app.gatewayClient.dialDev.task(taskId) },
    )
    val loaded = detail.envelope?.let { DialDevParse.taskDetail(it.data, it.observedAt) }
    val actions = rememberDevActions(
        app,
        detail,
        DialDevActionTarget(taskId = taskId, workspaceId = loaded?.workspaceId, decisionId = loaded?.ownerAction?.decisionId),
        loaded?.projectedActions.orEmpty(),
    )
    VanScreen(state = detail.state, onRetry = detail.reload) { task ->
        val row = task.row
        val p = row.presentation
        DevPage {
            item { SectionHeader(row.title, detail = listOfNotNull(row.taskId, row.du, row.stage).joinToString(" · ")) }
            item { StatusChip(label = p.caption, role = p.role) }
            item {
                DevTaskActionBar(
                    actions = actions,
                    currentIntent = task.intent ?: task.objective,
                    nextAction = row.nextAction,
                    revokeConsequence = DialDevConsequence.revoke(
                        row.taskId, task.leaseId, task.uncommittedFiles, task.consequences[DialDevActionKind.REVOKE_TASK.name],
                    ),
                    confirmText = row.taskId,
                )
            }
            item { DevFieldGroup("Objective & why now", listOf("Project" to task.projectId, "Objective" to task.objective, "Why now" to row.whyNow)) }
            item {
                DevFieldGroup(
                    "Execution",
                    listOf(
                        "Executor" to task.executor,
                        "Harness" to row.harness,
                        "Model" to row.model,
                        "Host" to row.host,
                        "Orca workspace" to task.workspaceId,
                        "Worktree" to task.worktree,
                        "Lease" to task.leaseId,
                        "Started" to task.startedAt,
                        "Heartbeat" to row.heartbeatAgeMs?.let { "${DialDevFormat.age(it)} ago" },
                    ),
                )
            }
            item {
                DevFieldGroup(
                    "Plan",
                    listOf(
                        "Next action" to row.nextAction,
                        "Expected postcondition" to task.expectedPostcondition,
                        "Dependencies" to task.dependencies.joinToString(", ").ifBlank { null },
                    ),
                )
            }
            item { DevVerification(task) }
            item { DevBlockersAndOwnerAction(task, actions) }
            item { SectionHeader("Evidence", detail = if (task.evidence.isEmpty()) "None reported" else null) }
            task.evidence.forEach { ref ->
                item(key = "evidence:${ref.ref}") { DevEvidenceItem(ref) { nav.open(VanRoute.devEvidenceRoute(it)) } }
            }
            item { SectionHeader("Progress", detail = if (task.timeline.isEmpty()) "No progress events reported" else null) }
            item {
                TimelineRail(
                    events = task.timeline.mapIndexed { index, event ->
                        TimelineEvent(
                            id = "$index:${event.event}",
                            title = event.event.replace('_', ' '),
                            actor = event.actor ?: "actor not reported",
                            timeLabel = event.at ?: "",
                            severityRole = timelineRole(event.event),
                            detail = event.detail,
                        )
                    },
                )
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    task.workspaceId?.let { id ->
                        OutlinedButton(onClick = { nav.open(VanRoute.devWorkspaceRoute(id)) }) { Text("Workspace", style = tokens.type.label) }
                    }
                    // §6.4 / Rev 3 §5a: ARTEMIS is DIAL's Android harness; VAN only links its console.
                    if (task.androidVerification) {
                        OutlinedButton(onClick = { nav.open(VanRoute.WORK_ARTEMIS) }) { Text("Android testing (ARTEMIS)", style = tokens.type.label) }
                    }
                }
            }
            item { DevRevisionFooter(detail.envelope) }
        }
    }
}

@Composable
private fun DevVerification(task: DevTaskDetail) {
    val tokens = LocalVanTokens.current
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Text("Verification", style = tokens.type.headline, color = tokens.color.textPrimary)
            DevField("Required checks", task.requiredChecks.joinToString(", ").ifBlank { null })
            DevField("Reviewer", task.reviewer)
            task.results.forEach { result ->
                Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    Text(result.check, style = tokens.type.body, color = tokens.color.textPrimary)
                    StatusChip(
                        label = DialDevRoles.chipLabel(result.result),
                        role = DialDevRoles.roleOrDisabled(DialDevResult.parse(result.result), DialDevRoles::result),
                    )
                }
            }
        }
    }
}

@Composable
private fun DevBlockersAndOwnerAction(task: DevTaskDetail, actions: DevActions) {
    val tokens = LocalVanTokens.current
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Text("Blockers & owner action", style = tokens.type.headline, color = tokens.color.textPrimary)
            if (task.blockers.isEmpty()) DevNote("DIAL reports no blockers.")
            task.blockers.forEach { DevNote(it, warning = true) }
            val owner = task.ownerAction
            if (owner == null) {
                DevNote("Nothing is waiting on you here.")
            } else {
                DevField("Asked of you", owner.prompt ?: owner.kind)
                // DECIDE needs the decision DIAL is waiting on; without its id there is nothing to decide.
                if (owner.decisionId != null && task.row.presentation.known?.state == DialDevState.WAITING_OWNER) {
                    DevDecisionControls(
                        actions,
                        owner.prompt,
                        DialDevConsequence.reject(owner.prompt, owner.consequence),
                    )
                }
            }
        }
    }
}

/** Progress events (Rev 1 §09.12) → roles; an event this build does not know reads `disabled`. */
private fun timelineRole(event: String): String =
    DialDevRoles.roleOrDisabled(DialDevProgressEvent.parse(event), DialDevRoles::progress)
