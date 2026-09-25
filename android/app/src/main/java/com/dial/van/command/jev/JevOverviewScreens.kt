package com.dial.van.command.jev

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
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
internal fun Overview(snapshot: JevServiceSnapshot, onRefresh: () -> Unit) {
    val tokens = LocalVanTokens.current
    val active = snapshot.modules.count { it.status == "ACTIVE" || it.status == "ACTIVE_GATED" }
    val shadow = snapshot.modules.count { it.status == "SHADOW" }
    val quarantined = snapshot.modules.count { it.status == "QUARANTINED" }
    LazyColumn(verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
                MetricTile(label = "Modules", value = snapshot.modules.size.toString(), modifier = Modifier.weight(1f))
                MetricTile(label = "Active", value = active.toString(), modifier = Modifier.weight(1f))
                MetricTile(label = "Shadow", value = shadow.toString(), modifier = Modifier.weight(1f))
            }
        }
        item {
            VanPanel {
                SectionHeader(
                    title = "Service state",
                    detail = "Provider availability never becomes authority.",
                    trailing = {
                        StatusChip(
                            label = snapshot.circuit,
                            role = if (snapshot.circuit == "HEALTHY") StatusSemantics.ROLE_FAVOURABLE
                            else StatusSemantics.ROLE_EVENT_RISK,
                        )
                    },
                )
                Text(
                    "Deployment switch: ${if (snapshot.serviceEnabled) "enabled" else "disabled"}",
                    style = tokens.type.body, color = tokens.color.textSecondary,
                )
                Text(
                    "Owner activation: ${if (snapshot.global.ownerActive) "on" else "off"} · bypass: ${if (snapshot.global.bypassed) "on" else "off"}",
                    style = tokens.type.body, color = tokens.color.textSecondary,
                )
                Text("Quarantined modules: $quarantined", style = tokens.type.body, color = tokens.color.textSecondary)
            }
        }
        item {
            VanPanel {
                SectionHeader(
                    title = "Provider qualification",
                    detail = "Configured is not the same as qualified; live eligibility requires evidence.",
                    trailing = {
                        StatusChip(
                            label = if (snapshot.providerQualified) "QUALIFIED" else if (snapshot.providerConfigured) "UNQUALIFIED" else "UNCONFIGURED",
                            role = if (snapshot.providerQualified) StatusSemantics.ROLE_FAVOURABLE
                            else if (snapshot.providerConfigured) StatusSemantics.ROLE_EVENT_RISK
                            else StatusSemantics.ROLE_DISABLED,
                        )
                    },
                )
                Text(
                    if (snapshot.providerModels.isEmpty()) "No live-qualified model revision recorded."
                    else "Models: ${snapshot.providerModels.joinToString(", ")}",
                    style = tokens.type.body,
                    color = tokens.color.textSecondary,
                )
            }
        }
        item {
            VanPanel {
                SectionHeader(title = "Domain coverage", detail = "One service, isolated use-case contracts.")
                listOf(
                    "dev." to "Development",
                    "van." to "VAN",
                    "van.trading." to "Trading",
                    "business." to "DIAL Business",
                ).forEach { (prefix, label) ->
                    val count = snapshot.modules.count {
                        it.id.startsWith(prefix) && (prefix != "van." || !it.id.startsWith("van.trading."))
                    }
                    Row(modifier = Modifier.fillMaxWidth().padding(vertical = tokens.space.space1)) {
                        Text(label, modifier = Modifier.weight(1f), style = tokens.type.body)
                        Text(count.toString(), style = tokens.type.data)
                    }
                }
            }
        }
        item { OutlinedButton(onClick = onRefresh, modifier = Modifier.fillMaxWidth()) { Text("Refresh live state") } }
    }
}
