package com.dial.van.command.work

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.design.LocalVanTokens
import com.dial.van.mission.MissionParsing
import com.dial.van.mission.MissionRepository
import com.dial.van.mission.MissionSummary
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/** The existing mission is the target; a note never creates another mission or grants authority. */
@Composable
internal fun MissionControls(
    app: VanApplication,
    mission: MissionSummary,
    onChanged: (MissionSummary?, String) -> Unit,
    onRefresh: () -> Unit,
) {
    val tokens = LocalVanTokens.current
    val repository = remember(app) { MissionRepository(app.gatewayClient) }
    val scope = rememberCoroutineScope()
    var message by rememberSaveable(mission.missionId) { mutableStateOf("") }
    var pending by remember(mission.missionId) { mutableStateOf(false) }
    var error by remember(mission.missionId) { mutableStateOf<String?>(null) }
    var confirmCancellation by remember(mission.missionId) { mutableStateOf(false) }
    if (mission.isTerminal) {
        Text("This mission has finished. Its record remains available.", style = tokens.type.label, color = tokens.color.textSecondary)
        return
    }

    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        MissionExecutionControls(app, mission.missionId)
        Text("Message this mission", style = tokens.type.label, color = tokens.color.textPrimary)
        OutlinedTextField(
            value = message,
            onValueChange = { message = it },
            enabled = !pending,
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Add direction or context") },
            maxLines = 4,
        )
        Text("This records a note for VAN. It does not restart work or approve an action.", style = tokens.type.label, color = tokens.color.textSecondary)
        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Button(enabled = !pending && message.isNotBlank(), onClick = {
                if (pending) return@Button
                val text = message.trim()
                pending = true
                error = null
                scope.launch {
                    try {
                        repository.message(mission.missionId, text)
                        message = ""
                        onChanged(null, "Message recorded on ${mission.title}. Its execution or adoption is unverified.")
                    } catch (cancel: CancellationException) {
                        throw cancel
                    } catch (failure: Exception) {
                        error = "VAN could not confirm this message. Your draft is kept. Check the timeline before sending it again. ${failure.message.orEmpty()}"
                    } finally { pending = false }
                }
            }) { Text(if (pending) "Saving…" else "Send message") }
            OutlinedButton(enabled = !pending, onClick = { confirmCancellation = true }) { Text("Cancel mission") }
        }
        error?.let {
            Text(it, style = tokens.type.label, color = tokens.color.textSecondary)
            OutlinedButton(enabled = !pending, onClick = onRefresh) { Text("Refresh mission and timeline") }
        }
    }

    if (confirmCancellation) {
        AlertDialog(
            onDismissRequest = { if (!pending) confirmCancellation = false },
            title = { Text("Cancel ${mission.title}?") },
            text = { Text("VAN will cancel its mission record and block new starts. Already-running services may continue; completed effects are not undone.") },
            confirmButton = {
                Button(enabled = !pending, onClick = {
                    if (pending) return@Button
                    pending = true
                    error = null
                    scope.launch {
                        try {
                            val receipt = repository.cancel(mission.missionId)
                            confirmCancellation = false
                            onChanged(MissionParsing.missionSummary(receipt), "VAN marked this mission cancelled; remote work stopping is unverified.")
                        } catch (cancel: CancellationException) {
                            throw cancel
                        } catch (failure: Exception) {
                            confirmCancellation = false
                            error = "VAN could not confirm cancellation. Refresh this mission before trying again. ${failure.message.orEmpty()}"
                        } finally { pending = false }
                    }
                }) { Text(if (pending) "Cancelling…" else "Cancel mission") }
            },
            dismissButton = { TextButton(enabled = !pending, onClick = { confirmCancellation = false }) { Text("Keep mission") } },
        )
    }
}
