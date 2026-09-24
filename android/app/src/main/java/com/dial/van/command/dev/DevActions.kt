package com.dial.van.command.dev

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.ApprovalSheet
import com.dial.van.design.components.LiveBadge
import com.dial.van.design.components.LiveBadgeState
import com.dial.van.design.components.StatusChip
import com.dial.van.dialdev.DialDevActionKind
import com.dial.van.dialdev.DialDevActionPolicy
import com.dial.van.dialdev.DialDevActionReducer
import com.dial.van.dialdev.DialDevActionRequest
import com.dial.van.dialdev.DialDevActionStatus
import com.dial.van.dialdev.DialDevActionTarget
import com.dial.van.dialdev.ProjectedAction
import com.dial.van.gateway.GatewayHttpException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import java.io.IOException
import java.util.UUID

/**
 * VAN-DEV-009 — the Android half of typed owner actions (`VAN-DEVCC-R1` §3.3, §5).
 *
 * Holds one [DialDevActionStatus] per control and never advances it on a tap: 202 →
 * `ACCEPTED · pending` (a [LiveBadge]), and only the projection's own `actions[]` entry for
 * that `action_id` moves it on ([DialDevActionReducer.reconcile]). 409 `STALE_VIEW` refetches
 * the projection before anything else happens. Offline, or with no projection revision on
 * screen, nothing is sent and nothing is queued.
 */
class DevActions(
    val statuses: Map<DialDevActionKind, DialDevActionStatus>,
    val submit: suspend (DialDevActionKind, Map<String, String>) -> DialDevActionStatus,
)

@Composable
fun rememberDevActions(
    app: VanApplication,
    projection: DevProjection<*>,
    target: DialDevActionTarget,
    projected: List<ProjectedAction>,
): DevActions {
    // Keyed on what the actions are *about* (the task/project), not on the target value: a
    // target that gains its workspace or decision id when the projection loads must not wipe
    // an `ACCEPTED · pending` row the owner is watching.
    val stableKey = target.taskId ?: target.workspaceId ?: target.projectId
    var statuses by remember(stableKey) { mutableStateOf<Map<DialDevActionKind, DialDevActionStatus>>(emptyMap()) }
    var keys by remember(stableKey) { mutableStateOf<Map<DialDevActionKind, String>>(emptyMap()) }

    // The projection, not the tap, moves an accepted action on.
    LaunchedEffect(projected, statuses) {
        val reconciled = statuses.mapValues { (_, status) -> DialDevActionReducer.reconcile(status, projected) }
        if (reconciled != statuses) statuses = reconciled
        projection.setAwaitingOutcome(reconciled.values.any(DialDevActionReducer::isPending))
    }

    val submit: suspend (DialDevActionKind, Map<String, String>) -> DialDevActionStatus = submit@{ kind, params ->
        if (!projection.online) {
            val refused = DialDevActionStatus.NotSent("you're offline. VAN does not queue owner actions; they need a live view.")
            statuses = statuses + (kind to refused)
            return@submit refused
        }
        val previous = statuses[kind]
        val key = when (previous?.let(DialDevActionReducer::retry)) {
            DialDevActionReducer.RetryMode.SAME_KEY -> keys[kind] ?: UUID.randomUUID().toString()
            DialDevActionReducer.RetryMode.NEW_KEY, DialDevActionReducer.RetryMode.NONE, null -> UUID.randomUUID().toString()
        }
        val request = DialDevActionRequest.build(kind, target, params, projection.revision, key)
        if (request == null) {
            val refused = DialDevActionStatus.NotSent("there is no DIAL view on screen to act against yet.")
            statuses = statuses + (kind to refused)
            return@submit refused
        }
        keys = keys + (kind to key)
        statuses = statuses + (kind to DialDevActionStatus.Submitting)
        val outcome = try {
            val body = app.gatewayClient.dialDev.submitAction(request)
            DialDevActionReducer.onResponse(202, body.toString())
        } catch (cancel: CancellationException) {
            throw cancel
        } catch (http: GatewayHttpException) {
            DialDevActionReducer.onResponse(http.code, http.body)
        } catch (io: IOException) {
            DialDevActionStatus.Unconfirmed("the connection dropped before DIAL answered.")
        } catch (other: Exception) {
            DialDevActionStatus.NotSent(other.message ?: "VAN could not send the action.")
        }
        statuses = statuses + (kind to outcome)
        // STALE_VIEW: show the new state before any retry. ACCEPTED: start watching for the outcome.
        if (outcome is DialDevActionStatus.StaleView || outcome is DialDevActionStatus.Accepted) projection.reload()
        outcome
    }
    return DevActions(statuses, submit)
}

/** One line per control that has been used: its honest status, never optimistic. */
@Composable
fun DevActionStatusRows(actions: DevActions) {
    val tokens = LocalVanTokens.current
    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
        actions.statuses.forEach { (kind, status) ->
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                if (status is DialDevActionStatus.Accepted) LiveBadge(state = LiveBadgeState.Live)
                StatusChip(label = DialDevActionReducer.caption(kind, status), role = DialDevActionReducer.role(status))
            }
        }
    }
}

/**
 * §3.3 / §6.4 / §6.6 controls: Steer, Pause safely, Resume, Request checkpoint, Request review,
 * Revoke. Steer opens [DevSteerSheet]; Revoke opens an [ApprovalSheet] whose digest is
 * [revokeConsequence] (built from projection data) and which is confirmed by typing
 * [confirmText]. There is no raw Orca or terminal control anywhere in this bar.
 */
@Composable
fun DevTaskActionBar(
    actions: DevActions,
    currentIntent: String?,
    nextAction: String?,
    revokeConsequence: String,
    confirmText: String,
) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    var steering by remember { mutableStateOf(false) }
    var revoking by remember { mutableStateOf(false) }
    val simple = listOf(
        DialDevActionKind.PAUSE_TASK_SAFE,
        DialDevActionKind.RESUME_TASK,
        DialDevActionKind.REQUEST_CHECKPOINT,
        DialDevActionKind.REQUEST_REVIEW,
    )
    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        LazyRow(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            item {
                Button(onClick = { steering = true }) {
                    Text(DialDevActionPolicy.label(DialDevActionKind.STEER_TASK), style = tokens.type.label)
                }
            }
            items(simple) { kind ->
                val pending = actions.statuses[kind]?.let(DialDevActionReducer::isPending) == true
                OutlinedButton(onClick = { scope.launch { actions.submit(kind, emptyMap()) } }, enabled = !pending) {
                    Text(DialDevActionPolicy.label(kind), style = tokens.type.label)
                }
            }
            item {
                OutlinedButton(
                    onClick = { revoking = true },
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = tokens.color.forStatusRole(StatusSemantics.ROLE_CRITICAL)),
                ) {
                    Text(DialDevActionPolicy.label(DialDevActionKind.REVOKE_TASK), style = tokens.type.label)
                }
            }
        }
        DevActionStatusRows(actions)
    }
    if (steering) {
        DevSteerSheet(
            currentIntent = currentIntent,
            nextAction = nextAction,
            onSend = { guidance -> actions.submit(DialDevActionKind.STEER_TASK, mapOf("guidance" to guidance)) },
            onDismiss = { steering = false },
        )
    }
    if (revoking) {
        var typed by remember { mutableStateOf("") }
        ApprovalSheet(
            title = "Revoke $confirmText?",
            actionDigest = revokeConsequence,
            approveLabel = "Revoke",
            approveEnabled = typed.trim() == confirmText,
            confirmation = {
                OutlinedTextField(
                    value = typed,
                    onValueChange = { typed = it },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    label = { Text("Type $confirmText to confirm", style = tokens.type.label) },
                )
            },
            onApprove = { outcomeAsResult(DialDevActionKind.REVOKE_TASK, actions.submit(DialDevActionKind.REVOKE_TASK, emptyMap())) },
            onDismiss = { revoking = false },
        )
    }
}

/**
 * An owner decision (§2.2 / §3.3 `DECIDE`). Approve and reject both go through
 * [ApprovalSheet]; reject is destructive, states its consequence, and requires a reason.
 */
@Composable
fun DevDecisionControls(actions: DevActions, prompt: String?, rejectConsequence: String) {
    val tokens = LocalVanTokens.current
    var deciding by remember { mutableStateOf<String?>(null) }
    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        Button(onClick = { deciding = "approve" }) { Text("Approve", style = tokens.type.label) }
        OutlinedButton(
            onClick = { deciding = "reject" },
            colors = ButtonDefaults.outlinedButtonColors(contentColor = tokens.color.forStatusRole(StatusSemantics.ROLE_CRITICAL)),
        ) { Text("Reject", style = tokens.type.label) }
    }
    val decision = deciding ?: return
    var reason by remember(decision) { mutableStateOf("") }
    val reject = decision == "reject"
    ApprovalSheet(
        title = if (reject) "Reject this decision?" else "Approve this decision?",
        actionDigest = if (reject) rejectConsequence else "Approves: ${prompt ?: "the decision DIAL is waiting on"}. DIAL records it; the work resumes when the projection shows it applied.",
        approveLabel = if (reject) "Reject" else "Approve",
        approveEnabled = !reject || reason.isNotBlank(),
        confirmation = {
            if (reject) {
                OutlinedTextField(
                    value = reason,
                    onValueChange = { reason = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Reason (required)", style = tokens.type.label) },
                )
            }
        },
        onApprove = {
            val params = buildMap {
                put("decision", decision)
                if (reason.isNotBlank()) put("reason", reason.trim())
            }
            outcomeAsResult(DialDevActionKind.DECIDE, actions.submit(DialDevActionKind.DECIDE, params))
        },
        onDismiss = { deciding = null },
    )
}

/**
 * §5 steer sheet: the task's current intent and next action are shown *above* the input, so
 * the owner steers against current state. The text is guidance DIAL Hermes relays at a safe
 * boundary — it is never terminal input.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DevSteerSheet(
    currentIntent: String?,
    nextAction: String?,
    onSend: suspend (String) -> DialDevActionStatus,
    onDismiss: () -> Unit,
    kind: DialDevActionKind = DialDevActionKind.STEER_TASK,
    title: String = "Steer",
    inputLabel: String = "Guidance for DIAL Hermes",
    sendLabel: String = "Send guidance",
) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    val sheetState = rememberModalBottomSheetState()
    var guidance by remember { mutableStateOf("") }
    var outcome by remember { mutableStateOf<DialDevActionStatus?>(null) }
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = tokens.color.surfaceAcrylic,
        contentColor = tokens.color.textPrimary,
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = tokens.space.space5, vertical = tokens.space.space3),
            verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
        ) {
            Text(title, style = tokens.type.title, color = tokens.color.textPrimary)
            Text("Current intent", style = tokens.type.label, color = tokens.color.textTertiary)
            Text(currentIntent ?: "DIAL did not report an intent.", style = tokens.type.body, color = tokens.color.textSecondary)
            Text("Next action", style = tokens.type.label, color = tokens.color.textTertiary)
            Text(nextAction ?: "DIAL did not report a next action.", style = tokens.type.body, color = tokens.color.textSecondary)
            OutlinedTextField(
                value = guidance,
                onValueChange = { guidance = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text(inputLabel, style = tokens.type.label) },
                maxLines = 5,
            )
            outcome?.let { status ->
                StatusChip(label = DialDevActionReducer.caption(kind, status), role = DialDevActionReducer.role(status))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                Button(
                    enabled = guidance.isNotBlank() && outcome?.let(DialDevActionReducer::isPending) != true,
                    onClick = {
                        val text = guidance.trim()
                        scope.launch {
                            val result = onSend(text)
                            outcome = result
                            if (result is DialDevActionStatus.Accepted) onDismiss()
                        }
                    },
                ) { Text(sendLabel, style = tokens.type.label) }
                TextButton(onClick = onDismiss) { Text("Cancel", style = tokens.type.label, color = tokens.color.textSecondary) }
            }
        }
    }
}

/** ApprovalSheet closes only on ACCEPTED; anything else is shown inside the sheet. */
private fun outcomeAsResult(kind: DialDevActionKind, status: DialDevActionStatus): Result<Unit> =
    if (status is DialDevActionStatus.Accepted) Result.success(Unit)
    else Result.failure(IllegalStateException(DialDevActionReducer.caption(kind, status)))
