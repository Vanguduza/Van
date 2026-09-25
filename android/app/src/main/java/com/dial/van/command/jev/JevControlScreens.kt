package com.dial.van.command.jev

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.VanPanel

@Composable
internal fun Controls(snapshot: JevServiceSnapshot, onCommand: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    val ownerEnabled = snapshot.global.ownerActive && !snapshot.global.bypassed
    LazyColumn(verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item {
            VanPanel {
                SectionHeader(
                    title = "Global control",
                    detail = "The deployment kill switch stays server-side. This switch changes owner activation through the signed A4 path.",
                )
                Row(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("Owner activation", style = tokens.type.headline)
                        Text(
                            if (ownerEnabled) "Eligible qualified modules may use Jev." else "All modules use registered non-Jev paths.",
                            style = tokens.type.body, color = tokens.color.textSecondary,
                        )
                    }
                    Switch(
                        checked = ownerEnabled,
                        onCheckedChange = { enabled -> onCommand(if (enabled) "enable jev" else "disable jev") },
                    )
                }
                Row(
                    horizontalArrangement = Arrangement.spacedBy(tokens.space.space2),
                    modifier = Modifier.padding(top = tokens.space.space3),
                ) {
                    OutlinedButton(onClick = { onCommand("bypass jev") }) { Text("Bypass") }
                    Button(onClick = { onCommand("restore jev") }) { Text("Restore") }
                }
            }
        }
        item {
            VanPanel {
                SectionHeader(title = "Project switches", detail = "Each division can opt out without disabling the shared service.")
                listOf(
                    "dial-development-system" to "Development System",
                    "van" to "VAN",
                    "dial-business-group" to "DIAL Business",
                ).forEach { (projectId, label) ->
                    val enabled = snapshot.global.projects[projectId] ?: true
                    Row(modifier = Modifier.fillMaxWidth().padding(vertical = tokens.space.space1)) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(label, style = tokens.type.headline)
                            Text(projectId, style = tokens.type.label, color = tokens.color.textSecondary)
                        }
                        Switch(
                            checked = enabled,
                            onCheckedChange = { on ->
                                onCommand("${if (on) "enable" else "disable"} jev for project $projectId")
                            },
                        )
                    }
                }
            }
        }
        item {
            VanPanel {
                SectionHeader(title = "Privacy & authority")
                Text("Android never receives TypeSafe credentials.", style = tokens.type.body)
                Text("RESTRICTED/SECRET data is refused before provider egress.", style = tokens.type.body)
                Text("Jev outputs remain evidence with authority_effect=NONE.", style = tokens.type.body)
                Text("VATI remains sole trading risk, sizing and execution authority.", style = tokens.type.body)
            }
        }
    }
}
