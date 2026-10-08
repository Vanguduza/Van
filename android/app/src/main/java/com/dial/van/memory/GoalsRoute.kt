package com.dial.van.memory

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.command.nav.VanRoute
import com.dial.van.command.owner.OwnerDataSection
import com.dial.van.command.owner.ownerRows
import com.dial.van.command.owner.ownerTime
import com.dial.van.command.owner.ownerValue
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.VanPanel

@Composable
fun GoalsRoute(app: VanApplication, onBack: () -> Unit, onOpenRoute: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter), contentPadding = PaddingValues(vertical = tokens.space.space3), verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item { OutlinedButton(onClick = onBack) { Text("← Memory") }; SectionHeader("Goals, decisions and evidence") }
        item { LearningProducerSection(app) }
        item {
            OwnerDataSection("Goals and unresolved tensions", load = { app.gatewayClient.standingIntents() }) { body, _ ->
                Text(body.ownerValue("stale_means"), style = tokens.type.label, color = tokens.color.textSecondary)
                val goals = body.optJSONArray("standing").ownerRows()
                if (goals.isEmpty()) Text("No standing or project goals recorded.", style = tokens.type.body, color = tokens.color.textSecondary)
                goals.forEach { goal ->
                    VanPanel {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text(goal.ownerValue("owner_goal"), style = tokens.type.body, color = tokens.color.textPrimary)
                            Text("${goal.ownerValue("horizon")} · ${goal.ownerValue("status")} · last mentioned ${ownerTime(goal.optLong("latest_observed_ms"))}", style = tokens.type.label, color = tokens.color.textSecondary)
                            Text("Why it became a standing goal: ${goal.ownerValue("promoted_reason")}", style = tokens.type.label, color = tokens.color.textTertiary)
                            Text("Constraints: ${goal.ownerValue("constraints")}\nLinked projects: ${goal.ownerValue("projects")}\nPriority: ${goal.optInt("priority")}", style = tokens.type.label, color = tokens.color.textTertiary)
                            goal.optJSONArray("conflicts_with").ownerRows().forEach { conflict -> Text("In tension with: ${conflict.ownerValue("owner_goal")}", style = tokens.type.body, color = tokens.color.textSecondary) }
                        }
                    }
                }
                Text("${body.optJSONArray("one_off_requests")?.length() ?: 0} one-off requests are kept separate from standing goals.", style = tokens.type.label, color = tokens.color.textTertiary)
                OutlinedButton(onClick = { onOpenRoute(VanRoute.WORK) }) { Text("Discuss a goal in Work") }
            }
        }
        item {
            OwnerDataSection("Decision history", load = { app.gatewayClient.decisionHistory() }) { body, _ ->
                val inference = body.optJSONObject("pattern_inference")
                if (inference?.optBoolean("active") != true) Text(inference?.ownerValue("why") ?: "Decision pattern inference is not active.", style = tokens.type.label, color = tokens.color.textSecondary)
                inference?.let { Text(LearningProducer.parse(it).ownerStatus, style = tokens.type.label); Text(it.ownerValue("why"), style = tokens.type.label) }
                inference?.let { LearningComparisonRows(it, "patterns") }
                val decisions = body.optJSONArray("decisions").ownerRows()
                if (decisions.isEmpty()) Text("No recorded decisions.", style = tokens.type.body, color = tokens.color.textSecondary)
                decisions.forEach { decision ->
                    VanPanel {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text(decision.ownerValue("owner_choice"), style = tokens.type.body, color = tokens.color.textPrimary)
                            Text("Your stated reason: ${decision.ownerValue("owner_stated_reason")}\nOutcome: ${decision.ownerValue("outcome")}", style = tokens.type.body, color = tokens.color.textSecondary)
                            Text(ownerTime(decision.optLong("created_at_ms")), style = tokens.type.label, color = tokens.color.textTertiary)
                            val missionId = decision.optString("mission_id")
                            if (missionId.isNotBlank() && missionId != "null") TextButton(onClick = { onOpenRoute(VanRoute.missionRoute(missionId)) }) { Text("Open mission") }
                        }
                    }
                }
            }
        }
        item {
            OwnerDataSection("Learned work strategies", load = { app.gatewayClient.learnedStrategies() }) { body, _ ->
                val strategies = body.optJSONArray("strategies").ownerRows()
                if (strategies.isEmpty()) Text("No learned strategies recorded.", style = tokens.type.body, color = tokens.color.textSecondary)
                strategies.forEach { strategy ->
                    VanPanel {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text(strategy.ownerValue("mission_class"), style = tokens.type.body, color = tokens.color.textPrimary)
                            Text("${strategy.ownerValue("promotion_state")} · authority ceiling ${strategy.ownerValue("max_action_class")}", style = tokens.type.label, color = tokens.color.textSecondary)
                            val sequence = strategy.optJSONArray("capability_sequence")
                            if (sequence != null) Text((0 until sequence.length()).joinToString(" → ") { sequence.optString(it) }, style = tokens.type.label, color = tokens.color.textSecondary)
                            Text("${strategy.optInt("verified_successes")} verified successes · ${strategy.optInt("failures")} failures · ${strategy.optInt("inconclusive")} inconclusive", style = tokens.type.label, color = tokens.color.textTertiary)
                            Text(if (strategy.isNull("success_rate")) "No measured success rate." else "Measured success rate ${(strategy.optDouble("success_rate") * 100).toInt()}%", style = tokens.type.label, color = tokens.color.textTertiary)
                            Text("Evaluation: ${strategy.ownerValue("eval_run_id")}", style = tokens.type.label, color = tokens.color.textTertiary)
                        }
                    }
                }
            }
        }
        item {
            OwnerDataSection("External evidence", load = { app.gatewayClient.externalReality() }) { body, _ ->
                val detection = body.optJSONObject("contradiction_detection")
                if (detection?.optBoolean("active") != true) Text(detection?.ownerValue("why") ?: "Evidence is not compared automatically against owner beliefs.", style = tokens.type.label, color = tokens.color.textSecondary)
                detection?.let { Text(LearningProducer.parse(it).ownerStatus, style = tokens.type.label); Text(it.ownerValue("why"), style = tokens.type.label) }
                detection?.let { LearningComparisonRows(it, "comparisons"); LearningComparisonRows(it, "contradictions") }
                val observations = body.optJSONArray("observations").ownerRows()
                if (observations.isEmpty()) Text("No external observations recorded. This does not establish agreement with an owner belief.", style = tokens.type.body, color = tokens.color.textSecondary)
                observations.forEach { observation ->
                    VanPanel {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text(observation.ownerValue("subject"), style = tokens.type.label, color = tokens.color.textSecondary)
                            Text(observation.ownerValue("claim"), style = tokens.type.body, color = tokens.color.textPrimary)
                            Text("Source: ${observation.ownerValue("source_ref")}\nObserved ${ownerTime(observation.optLong("observed_at_ms"))}", style = tokens.type.label, color = tokens.color.textTertiary)
                        }
                    }
                }
            }
        }
        item {
            OwnerDataSection("Technology radar", load = { app.gatewayClient.technologyRadar() }) { body, _ ->
                val technologies = body.optJSONArray("technologies").ownerRows()
                if (technologies.isEmpty()) Text("No technology evaluations recorded.", style = tokens.type.body, color = tokens.color.textSecondary)
                technologies.forEach { technology ->
                    Text("${technology.ownerValue("name", technology.ownerValue("technology_id"))} · ${technology.ownerValue("pipeline_state")}", style = tokens.type.body, color = tokens.color.textPrimary)
                }
                Text("${body.optJSONArray("deprecations")?.length() ?: 0} recorded deprecations.", style = tokens.type.label, color = tokens.color.textTertiary)
            }
        }
        item {
            OwnerDataSection("Evaluation evidence", load = { app.gatewayClient.evalReport() }) { body, _ ->
                Text("Evaluated ${ownerTime(body.optLong("ran_at_ms"))}", style = tokens.type.label, color = tokens.color.textTertiary)
                body.optJSONObject("summary")?.let { Text(it.ownerValue("overall_score_note"), style = tokens.type.label, color = tokens.color.textSecondary) }
                body.optJSONArray("dimensions").ownerRows().forEach { dimension ->
                    VanPanel {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text(dimension.ownerValue("dimension").replace('_', ' '), style = tokens.type.body, color = tokens.color.textPrimary)
                            Text(if (dimension.optBoolean("measured")) "Score ${dimension.ownerValue("score")} · target ${dimension.ownerValue("target")} · ${dimension.optInt("sample_size")} samples" else "Unmeasured: ${dimension.ownerValue("unmeasurable_reason")}", style = tokens.type.label, color = tokens.color.textSecondary)
                        }
                    }
                }
            }
        }
    }
}
