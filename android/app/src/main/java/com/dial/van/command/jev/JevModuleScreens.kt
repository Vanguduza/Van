package com.dial.van.command.jev

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.MetricTile
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel

@Composable
internal fun Modules(modules: List<JevModule>, onSelect: (JevModule) -> Unit) {
    val tokens = LocalVanTokens.current
    var filter by remember { mutableStateOf("ALL") }
    val visible = modules.filter {
        when (filter) {
            "DEV" -> it.id.startsWith("dev.")
            "VAN" -> it.id.startsWith("van.") && !it.id.startsWith("van.trading.")
            "TRADING" -> it.id.startsWith("van.trading.")
            "BUSINESS" -> it.id.startsWith("business.")
            else -> true
        }
    }
    LazyColumn(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                listOf("ALL", "DEV", "VAN", "TRADING", "BUSINESS").forEach { item ->
                    FilterChip(selected = filter == item, onClick = { filter = item }, label = { Text(item) })
                }
            }
        }
        items(visible, key = { it.id }) { module ->
            VanPanel(dense = true, modifier = Modifier.clickable { onSelect(module) }) {
                Row(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(module.id, style = tokens.type.headline)
                        Text(
                            "${module.effectDirection} · ${module.consequence} · ${module.ownerSystem}",
                            style = tokens.type.label,
                            color = tokens.color.textSecondary,
                        )
                    }
                    StatusChip(label = module.status, role = jevStatusRole(module.status))
                }
            }
        }
    }
}

@Composable
internal fun ModuleDetail(
    module: JevModule,
    contribution: JevContribution?,
    onBack: () -> Unit,
    onLoadContribution: () -> Unit,
    onTransition: (String) -> Unit,
) {
    val tokens = LocalVanTokens.current
    LazyColumn(verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item {
            VanPanel {
                Row(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(module.id, style = tokens.type.title)
                        Text(module.ownerSystem, style = tokens.type.body, color = tokens.color.textSecondary)
                    }
                    StatusChip(label = module.status, role = jevStatusRole(module.status))
                }
                HorizontalDivider(modifier = Modifier.padding(vertical = tokens.space.space3))
                Text("Effect: ${module.effectDirection}", style = tokens.type.body)
                Text("Consequence: ${module.consequence}", style = tokens.type.body)
                Text("Fallback: ${module.fallbackClass}", style = tokens.type.body)
                Text("Deadline: ${module.deadlineMs} ms", style = tokens.type.body)
            }
        }
        item {
            VanPanel {
                SectionHeader(
                    title = "Lifecycle control",
                    detail = "Owner-signed A4 controls. DIAL still enforces the lifecycle ceiling, effect direction and independent review.",
                )
                Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    listOf("SHADOW", "ADVISORY", "ACTIVE_GATED").forEach { state ->
                        OutlinedButton(onClick = { onTransition(state) }) { Text(state) }
                    }
                }
                Row(
                    horizontalArrangement = Arrangement.spacedBy(tokens.space.space2),
                    modifier = Modifier.padding(top = tokens.space.space2),
                ) {
                    Button(onClick = { onTransition("ACTIVE") }) { Text("Active") }
                    OutlinedButton(onClick = { onTransition("DISABLED") }) { Text("Disable") }
                    OutlinedButton(onClick = { onTransition("BYPASSED") }) { Text("Bypass") }
                }
            }
        }
        item {
            VanPanel {
                SectionHeader(title = "Measured contribution", detail = "Counterfactual comparison with the non-Jev path.")
                if (contribution == null) {
                    OutlinedButton(onClick = onLoadContribution) { Text("Load contribution evidence") }
                } else {
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
                        MetricTile(label = "Samples", value = contribution.sampleCount.toString(), modifier = Modifier.weight(1f))
                        MetricTile(label = "Outcome Δ", value = "%.3f".format(contribution.outcomeDelta), modifier = Modifier.weight(1f))
                        MetricTile(label = "Composite", value = "%.3f".format(contribution.composite), modifier = Modifier.weight(1f))
                    }
                    Text(
                        "Cost saved %.3f · latency saved %.0f ms · error cost %.3f".format(
                            contribution.costSavings, contribution.latencySavingsMs, contribution.errorCost,
                        ),
                        style = tokens.type.body, color = tokens.color.textSecondary,
                    )
                }
            }
        }
        item { OutlinedButton(onClick = onBack, modifier = Modifier.fillMaxWidth()) { Text("Back to modules") } }
    }
}
