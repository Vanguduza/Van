package com.dial.van.command.dev

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.LiveBadge
import com.dial.van.design.components.LiveBadgeState
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.TimelineEvent
import com.dial.van.design.components.TimelineRail
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanPressable
import com.dial.van.design.components.VanScreen
import com.dial.van.dialdev.DevStage
import com.dial.van.dialdev.DevStagePlan
import com.dial.van.dialdev.DialDevActionKind
import com.dial.van.dialdev.DialDevActionReducer
import com.dial.van.dialdev.DialDevActionStatus
import com.dial.van.dialdev.DialDevActionTarget
import com.dial.van.dialdev.DialDevCaptionContext
import com.dial.van.dialdev.DialDevFormat
import com.dial.van.dialdev.DialDevParse
import com.dial.van.dialdev.DialDevSemantics

/**
 * `work/dev/{projectId}/plan` — Stage Plan (VAN-DEVCC-R1 §6.2, VAN-DEV-006).
 *
 * @DataSource("GET /v1/dial-dev/projects/{p}/stage-plan") — stages, dependencies, required
 *   evidence, owner actions, external blockers, plan fingerprint and revision.
 *
 * "Recompiling" is shown while an owner reprioritisation is ACCEPTED and not yet APPLIED, or
 * while DIAL itself reports `recompiling` — never inferred from a tap alone.
 */
@Composable
fun DevPlanRoute(app: VanApplication, projectId: String, nav: DevNavigator) {
    val tokens = LocalVanTokens.current
    val plan = rememberDevProjection(
        app = app,
        key = "plan:$projectId",
        sections = setOf("stage_plan", "stages", "plan"),
        emptySentence = "DIAL has not compiled a stage plan for this project yet.",
        isEmpty = { p: DevStagePlan -> p.stages.isEmpty() },
        parse = { DialDevParse.stagePlan(it.data, it.sources) },
        fetch = { app.gatewayClient.dialDev.stagePlan(projectId) },
    )
    val actions = rememberDevActions(
        app, plan, DialDevActionTarget(projectId = projectId),
        plan.envelope?.let { DialDevActionReducer.parseProjected(it.data) }.orEmpty(),
    )
    var open by remember { mutableStateOf<DevStage?>(null) }
    var reprioritising by remember { mutableStateOf(false) }
    val reprioritisePending = actions.statuses[DialDevActionKind.REPRIORITISE] is DialDevActionStatus.Accepted

    VanScreen(state = plan.state, onRetry = plan.reload) { data ->
        DevPage {
            item { SectionHeader("Stage plan", detail = projectId) }
            if (data.recompiling || reprioritisePending) {
                item {
                    VanPanel(dense = true) {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                            LiveBadge(state = LiveBadgeState.Live)
                            DevNote("Plan recompiling — the new revision has not landed yet.", warning = true)
                        }
                    }
                }
            }
            item {
                OutlinedButton(onClick = { reprioritising = true }) { Text("Reprioritise", style = tokens.type.label) }
            }
            item { DevActionStatusRows(actions) }
            item {
                TimelineRail(
                    events = data.stages.filter { stage -> stage.applicable != false || stage.rawState != null }.map { stage ->
                        val p = DialDevSemantics.presentRaw(stage.rawState, context = DialDevCaptionContext(firstBlocker = stage.externalBlockers.firstOrNull()))
                        TimelineEvent(
                            id = stage.stageId,
                            title = "${stage.stageId} ${stage.title.orEmpty()}".trim(),
                            actor = p.caption,
                            timeLabel = if (stage.applicable == false) "not applicable" else "evidence ${DialDevFormat.count(stage.requiredEvidenceCount)}",
                            severityRole = p.role,
                            detail = stage.externalBlockers.takeIf { it.isNotEmpty() }?.joinToString("; ", prefix = "External: "),
                        )
                    },
                )
            }
            item { SectionHeader("Stages", detail = "Open one for its dependencies, artifacts and evidence") }
            data.stages.forEach { stage ->
                item(key = stage.stageId) {
                    val p = DialDevSemantics.presentRaw(stage.rawState)
                    VanPressable(onClick = { open = stage }, modifier = Modifier.fillMaxWidth(), contentDescription = "${stage.stageId}. ${p.caption}. Open stage detail.") {
                        VanPanel(dense = true) {
                            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                                Text("${stage.stageId} ${stage.title.orEmpty()}".trim(), style = tokens.type.body, color = tokens.color.textPrimary)
                                StatusChip(label = p.caption, role = p.role)
                                if (stage.applicable == false) {
                                    StatusChip(label = "NOT APPLICABLE", role = StatusSemantics.ROLE_DISABLED)
                                }
                            }
                        }
                    }
                }
            }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                    DevField("Plan fingerprint", data.planFingerprint)
                    DevField("Stage plan revision", data.stagePlanRevision)
                    DevRevisionFooter(plan.envelope)
                }
            }
        }
    }

    open?.let { stage -> DevStageSheet(stage, onDismiss = { open = null }) }
    if (reprioritising) {
        DevSteerSheet(
            currentIntent = "Plan ${plan.envelope?.let { DialDevParse.stagePlan(it.data, it.sources).planFingerprint } ?: "fingerprint not reported"}",
            nextAction = "DIAL recompiles the Stage Graph from your priority; VAN shows the new plan when its revision lands.",
            onSend = { text -> actions.submit(DialDevActionKind.REPRIORITISE, mapOf("priority" to text)) },
            onDismiss = { reprioritising = false },
            kind = DialDevActionKind.REPRIORITISE,
            title = "Reprioritise",
            inputLabel = "What should come first, and why",
            sendLabel = "Send priority",
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DevStageSheet(stage: DevStage, onDismiss: () -> Unit) {
    val tokens = LocalVanTokens.current
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(),
        containerColor = tokens.color.surfaceAcrylic,
        contentColor = tokens.color.textPrimary,
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = tokens.space.space5, vertical = tokens.space.space3),
            verticalArrangement = Arrangement.spacedBy(tokens.space.space2),
        ) {
            Text("${stage.stageId} ${stage.title.orEmpty()}".trim(), style = tokens.type.title, color = tokens.color.textPrimary)
            DevField("State", DialDevSemantics.presentRaw(stage.rawState).caption)
            DevField("Dependencies", stage.dependencies.joinToString(", ").ifBlank { null })
            DevField("Required evidence", stage.requiredEvidenceCount?.toString())
            DevField("Artifacts", stage.artifacts.joinToString(", ").ifBlank { null })
            DevField("Evidence", stage.evidence.joinToString(", ").ifBlank { null })
            DevField("Owner actions", stage.ownerActions.joinToString("; ").ifBlank { null })
            DevField("External blockers", stage.externalBlockers.joinToString("; ").ifBlank { null })
        }
    }
}
