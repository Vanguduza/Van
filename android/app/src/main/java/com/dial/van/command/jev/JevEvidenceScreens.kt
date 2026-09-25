package com.dial.van.command.jev

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.MetricTile
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel

@Composable
internal fun Activity(projectId: String, activity: List<JevActivityItem>, onProject: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    LazyColumn(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                listOf("van", "dial-development-system", "dial-business-group").forEach { id ->
                    FilterChip(
                        selected = projectId == id,
                        onClick = { onProject(id) },
                        label = { Text(id.removePrefix("dial-")) },
                    )
                }
            }
        }
        if (activity.isEmpty()) {
            item {
                VanPanel {
                    Text("No trusted outcomes recorded for this project yet.", style = tokens.type.body, color = tokens.color.textSecondary)
                }
            }
        } else {
            items(activity, key = { "${it.requestId}:${it.observedAt}:${it.event}" }) { outcome ->
                VanPanel(dense = true) {
                    Row(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(outcome.moduleId, style = tokens.type.headline)
                            Text("${outcome.event} · ${outcome.provider} · ${outcome.latencyMs} ms", style = tokens.type.label, color = tokens.color.textSecondary)
                            Text(outcome.observedAt, style = tokens.type.label, color = tokens.color.textTertiary)
                        }
                        StatusChip(
                            label = outcome.lifecycleState.ifBlank { if (outcome.provider == "fallback") "FALLBACK" else "DECISION" },
                            role = if (outcome.provider == "fallback") StatusSemantics.ROLE_EVENT_RISK else StatusSemantics.ROLE_COGNITION,
                        )
                    }
                }
            }
        }
    }
}

@Composable
internal fun Value(
    modules: List<JevModule>,
    performance: JevPerformance?,
    contribution: JevContribution?,
    proposals: List<JevEvaluationProposal>,
    onSelect: (JevModule) -> Unit,
    onEvaluate: (JevModule) -> Unit,
) {
    val tokens = LocalVanTokens.current
    LazyColumn(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        item {
            VanPanel {
                SectionHeader(
                    title = "Performance & contribution",
                    detail = "Live service telemetry plus counterfactual value against the non-Jev baseline.",
                )
                performance?.let { perf ->
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
                        MetricTile(label = "Decisions", value = perf.decisions.toString(), modifier = Modifier.weight(1f))
                        MetricTile(label = "p50", value = "%.0f ms".format(perf.p50LatencyMs), modifier = Modifier.weight(1f))
                        MetricTile(label = "Fallback", value = "%.1f%%".format(perf.fallbackRate * 100), modifier = Modifier.weight(1f))
                    }
                }
                contribution?.let {
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
                        MetricTile(label = "Samples", value = it.sampleCount.toString(), modifier = Modifier.weight(1f))
                        MetricTile(label = "Cost saved", value = "%.3f".format(it.costSavings), modifier = Modifier.weight(1f))
                        MetricTile(label = "Latency", value = "%.0f ms".format(it.latencySavingsMs), modifier = Modifier.weight(1f))
                    }
                }
            }
        }
        item {
            VanPanel {
                SectionHeader(
                    title = "Independent evaluator",
                    detail = "LLM proposals are advisory, provenance-bound and require independent review before any lifecycle change.",
                )
                if (proposals.isEmpty()) {
                    Text("No evaluator proposals recorded yet.", style = tokens.type.body, color = tokens.color.textSecondary)
                } else {
                    proposals.take(8).forEach { proposal ->
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(vertical = tokens.space.space1),
                            horizontalArrangement = Arrangement.spacedBy(tokens.space.space2),
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(proposal.moduleId, style = tokens.type.headline)
                                Text(
                                    proposal.rationale.take(180).ifBlank { "No rationale projected." },
                                    style = tokens.type.label,
                                    color = tokens.color.textSecondary,
                                )
                                Text(
                                    "${proposal.proposerLineage} · ${proposal.proposedAt}",
                                    style = tokens.type.label,
                                    color = tokens.color.textTertiary,
                                )
                            }
                            StatusChip(
                                label = proposal.recommendation,
                                role = jevStatusRole(
                                    when (proposal.recommendation) {
                                        "KEEP" -> "ACTIVE"
                                        "QUARANTINE", "DETACH_GLOBAL" -> "QUARANTINED"
                                        "DEMOTE", "RETIRE" -> "BYPASSED"
                                        else -> "ADVISORY"
                                    },
                                ),
                            )
                        }
                    }
                }
            }
        }
        items(modules, key = { it.id }) { module ->
            VanPanel(dense = true) {
                Row(modifier = Modifier.fillMaxWidth()) {
                    Text(
                        module.id,
                        modifier = Modifier.weight(1f).clickable { onSelect(module) },
                        style = tokens.type.body,
                    )
                    StatusChip(label = module.status, role = jevStatusRole(module.status))
                }
                Row(
                    modifier = Modifier.fillMaxWidth().padding(top = tokens.space.space1),
                    horizontalArrangement = Arrangement.spacedBy(tokens.space.space2),
                ) {
                    OutlinedButton(onClick = { onSelect(module) }, modifier = Modifier.weight(1f)) { Text("Inspect") }
                    OutlinedButton(onClick = { onEvaluate(module) }, modifier = Modifier.weight(1f)) { Text("Evaluate value") }
                }
            }
        }
    }
}
