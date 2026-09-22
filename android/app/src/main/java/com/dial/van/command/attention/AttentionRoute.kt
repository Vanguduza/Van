package com.dial.van.command.attention

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.command.objectList
import com.dial.van.design.AttentionSeverity
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.ScreenState
import com.dial.van.design.ScreenStateMerge
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.AttentionItem
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanPressable
import com.dial.van.design.components.VanScreen
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * DNA §4 destination 2: "Attention — triage list INFO/FOLLOW_UP/BLOCKER/URGENT; decisions;
 * approvals."
 *
 * @DataSource("GET /v1/attention") — the triage list.
 * @DataSource("GET /v1/decisions") — the decisions section.
 * @DataSource("com.dial.van.control.VanCommandController.state.pendingA4Approval") — the
 *   in-flight owner approval, if there is one.
 */
private data class AttentionData(
    val items: List<JSONObject>,
    val decisions: List<JSONObject>,
)

@Composable
fun AttentionRoute(app: VanApplication) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    var data by remember { mutableStateOf<AttentionData?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var filter by remember { mutableStateOf<AttentionSeverity?>(null) }
    val commandState by app.commandController.state.collectAsState()
    val activity = LocalContext.current as? FragmentActivity

    fun load() {
        scope.launch {
            loading = true
            runCatching {
                AttentionData(
                    items = app.gatewayClient.attention().objectList(),
                    decisions = app.gatewayClient.decisions().objectList(),
                )
            }.onSuccess { data = it; error = null; loading = false }
                .onFailure { error = it.message ?: "VAN could not load what is waiting on you."; loading = false }
        }
    }
    LaunchedEffect(Unit) { load() }

    val quietHours = app.notificationPolicyStore.quietHours()
    val state: ScreenState<AttentionData> = ScreenStateMerge.merge(
        content = data,
        loading = loading,
        errorMessage = error,
        emptySentence = "Nothing needs you right now.",
    )

    VanScreen(state = state, onRetry = ::load) { attention ->
        val visible = attention.items.filter { item ->
            filter == null || item.optString("severity") == filter?.name
        }
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter),
            verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
            contentPadding = PaddingValues(vertical = tokens.space.space3),
        ) {
            item { SectionHeader("Attention") }

            if (quietHours.enabled) {
                item {
                    VanPanel(dense = true) {
                        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            StatusChip(label = "QUIET HOURS", role = StatusSemantics.ROLE_MONITOR)
                            Text(
                                "VAN is only surfacing priority apps until ${quietHours.endHour}:00.",
                                style = tokens.type.label,
                                color = tokens.color.textSecondary,
                            )
                        }
                    }
                }
            }

            commandState.pendingA4Approval?.let { pending ->
                item {
                    VanPanel {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                                Text("Owner approval required", style = tokens.type.headline, color = tokens.color.textPrimary)
                                StatusChip(label = "PENDING", role = StatusSemantics.ROLE_EVENT_RISK)
                            }
                            Text(pending.resolvedActionId, style = tokens.type.body, color = tokens.color.textSecondary)
                            Text(
                                "VAN needs your fingerprint or face before doing this, because you cannot easily undo it.",
                                style = tokens.type.label,
                                color = tokens.color.textTertiary,
                            )
                            Button(
                                enabled = activity != null && !commandState.submitting,
                                onClick = { activity?.let { app.commandController.approvePendingA4(it) } },
                            ) { Text("Approve") }
                        }
                    }
                }
            }

            item {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    item {
                        FilterChip("ALL", filter == null) { filter = null }
                    }
                    items(AttentionSeverity.entries.toList()) { severity ->
                        FilterChip(severity.name.replace('_', ' '), filter == severity) { filter = severity }
                    }
                }
            }

            if (visible.isEmpty()) {
                item { Text("Nothing matches this filter.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            items(visible, key = { it.optString("id") }) { record ->
                val severity = runCatching { AttentionSeverity.valueOf(record.optString("severity")) }
                    .getOrDefault(AttentionSeverity.INFO)
                AttentionItem(
                    title = record.optString("title", "Attention item"),
                    severity = severity,
                    detail = record.optString("source").takeIf { it.isNotBlank() },
                    onAck = {
                        scope.launch {
                            runCatching { app.gatewayClient.attentionAck(record.optString("id")) }
                                .onSuccess { load() }
                        }
                    },
                    onSnooze = {
                        scope.launch {
                            // The swipe gesture is deliberately one-hour. Longer/shorter
                            // durations belong in the detail surface; the gesture itself
                            // must remain a single deterministic action.
                            val until = (System.currentTimeMillis() / 1000L) + 60L * 60L
                            runCatching {
                                app.gatewayClient.attentionSnooze(record.optString("id"), until)
                            }.onSuccess { load() }
                        }
                    },
                )
            }

            if (attention.decisions.isNotEmpty()) {
                item { SectionHeader("Decisions", detail = "Owner escalations") }
                items(attention.decisions, key = { it.optString("id") }) { decision ->
                    VanPanel {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text(decision.optString("title", "Decision"), style = tokens.type.headline, color = tokens.color.textPrimary)
                            Text(decision.optString("body"), style = tokens.type.body, color = tokens.color.textSecondary)
                            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                                Button(onClick = {
                                    scope.launch {
                                        runCatching { app.gatewayClient.resolveDecision(decision.getString("id"), true) }
                                            .onSuccess { load() }
                                    }
                                }) { Text("Approve") }
                                Button(
                                    onClick = {
                                        scope.launch {
                                            runCatching { app.gatewayClient.resolveDecision(decision.getString("id"), false) }
                                                .onSuccess { load() }
                                        }
                                    },
                                    colors = ButtonDefaults.buttonColors(containerColor = tokens.color.forStatusRole(StatusSemantics.ROLE_CRITICAL)),
                                ) { Text("Refuse") }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun FilterChip(label: String, selected: Boolean, onClick: () -> Unit) {
    val tokens = LocalVanTokens.current
    VanPressable(onClick = onClick, contentDescription = label) {
        StatusChip(label = label, role = if (selected) StatusSemantics.ROLE_ENGAGED else StatusSemantics.ROLE_DISABLED, filled = selected)
    }
}
