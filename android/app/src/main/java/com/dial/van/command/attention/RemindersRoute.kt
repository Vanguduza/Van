package com.dial.van.command.attention

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.command.owner.OwnerDataSection
import com.dial.van.command.owner.ownerRows
import com.dial.van.command.owner.ownerTime
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.VanPanel
import org.json.JSONObject
import java.util.UUID

@Composable
fun RemindersRoute(app: VanApplication, onBack: () -> Unit) {
    val tokens = LocalVanTokens.current
    LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter), contentPadding = PaddingValues(vertical = tokens.space.space3), verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item { OutlinedButton(onClick = onBack) { Text("← Attention") }; SectionHeader("Reminders") }
        item {
            OwnerDataSection("Upcoming reminders", load = { JSONObject().put("reminders", app.gatewayClient.reminders()) }) { body, actions ->
                var text by rememberSaveable { mutableStateOf("") }
                var due by rememberSaveable { mutableStateOf("") }
                var requestKey by rememberSaveable { mutableStateOf(UUID.randomUUID().toString()) }
                var cancelTarget by remember { mutableStateOf<JSONObject?>(null) }
                OutlinedTextField(value = text, onValueChange = { text = it; requestKey = UUID.randomUUID().toString() }, enabled = actions.canMutate, modifier = Modifier.fillMaxWidth(), label = { Text("Remind me to") })
                OutlinedTextField(value = due, onValueChange = { due = it; requestKey = UUID.randomUUID().toString() }, enabled = actions.canMutate, modifier = Modifier.fillMaxWidth(), label = { Text("When, e.g. in 20 minutes") })
                Text("Clock times such as tomorrow at 9am use UTC. The saved reminder shows the resolved time on this phone.", style = tokens.type.label, color = tokens.color.textSecondary)
                Button(enabled = actions.canMutate && text.isNotBlank() && due.isNotBlank(), onClick = {
                    actions.mutate("create", "Reminder saved. Its due time is shown below.") {
                        app.gatewayClient.createReminder(text.trim(), due.trim(), requestKey).also { receipt ->
                            check(receipt.optString("id").isNotBlank() && receipt.optLong("due_at_unix") > 0L) { "No reminder receipt was returned." }
                            text = ""; due = ""; requestKey = UUID.randomUUID().toString()
                        }
                    }
                }) { Text(if (actions.pending("create")) "Saving…" else "Create reminder") }
                val reminders = body.optJSONArray("reminders").ownerRows()
                if (reminders.isEmpty()) Text("No open reminders.", style = tokens.type.body, color = tokens.color.textSecondary)
                reminders.forEach { reminder ->
                    val id = reminder.optString("id")
                    VanPanel {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text(reminder.optString("text"), style = tokens.type.body, color = tokens.color.textPrimary)
                            Text("Due ${ownerTime(reminder.optLong("due_at_unix") * 1_000L)}", style = tokens.type.label, color = tokens.color.textSecondary)
                            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                                Button(enabled = actions.canMutate && id.isNotBlank(), onClick = {
                                    actions.mutate("resolve:$id", "Reminder marked done.") { app.gatewayClient.resolveReminder(id).also { check(it.optBoolean("resolved")) { "Completion was not confirmed." } } }
                                }) { Text("Done") }
                                OutlinedButton(enabled = actions.canMutate && id.isNotBlank(), onClick = { cancelTarget = reminder }) { Text("Cancel reminder") }
                            }
                        }
                    }
                }
                cancelTarget?.let { reminder ->
                    AlertDialog(
                        onDismissRequest = { cancelTarget = null }, title = { Text("Cancel this reminder?") }, text = { Text(reminder.optString("text")) },
                        confirmButton = { Button(enabled = actions.canMutate, onClick = {
                            val id = reminder.getString("id")
                            cancelTarget = null
                            actions.mutate("cancel:$id", "Reminder cancelled.") { app.gatewayClient.cancelReminder(id).also { check(it.optBoolean("cancelled")) { "Cancellation was not confirmed." } } }
                        }) { Text("Cancel reminder") } },
                        dismissButton = { TextButton(onClick = { cancelTarget = null }) { Text("Keep reminder") } },
                    )
                }
            }
        }
    }
}
