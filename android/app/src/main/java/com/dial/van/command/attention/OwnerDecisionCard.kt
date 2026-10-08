package com.dial.van.command.attention

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.command.nav.VanRoute
import com.dial.van.command.owner.ownerTime
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.VanPanel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.util.UUID

@Composable
internal fun OwnerDecisionCard(app: VanApplication, record: JSONObject, onOpenRoute: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    val id = record.optString("id")
    var current by remember(id, record.toString()) { mutableStateOf(runCatching { OwnerDecision.parse(record) }.getOrNull()) }
    var choice by rememberSaveable(id) { mutableStateOf("") }
    var note by rememberSaveable(id) { mutableStateOf("") }
    var pendingBody by rememberSaveable(id) { mutableStateOf<String?>(null) }
    var pending by remember(id) { mutableStateOf(false) }
    var error by remember(id) { mutableStateOf<String?>(null) }
    var notice by remember(id) { mutableStateOf<String?>(null) }
    var now by remember { mutableStateOf(System.currentTimeMillis() / 1000L) }
    LaunchedEffect(id) { while (true) { now = System.currentTimeMillis() / 1000L; delay(1_000L) } }

    suspend fun readAnswer(): OwnerDecision {
        val fresh = OwnerDecision.parse(app.gatewayClient.decision(id))
        check(fresh.id == id) { "The decision readback did not match." }
        current = fresh
        val body = pendingBody?.let(::JSONObject)
        if (body != null && fresh.confirms(body)) {
            pendingBody = null
            notice = "Your exact answer and reason were saved and independently read back."
        } else if (body != null && (fresh.status != "OPEN" || fresh.revision != body.optInt("expected_revision") || !fresh.answerable(now))) {
            pendingBody = null; choice = ""
            notice = "The current decision definitively supersedes this unconfirmed attempt. Review its current answer, expiry and revision before a new choice."
        }
        return fresh
    }
    fun send(exact: JSONObject) {
        if (pending) return
        pendingBody = exact.toString()
        pending = true; error = null; notice = null
        scope.launch {
            try {
                app.gatewayClient.answerDecision(id, exact)
                val fresh = readAnswer()
                check(fresh.confirms(exact)) { "The answer has no matching authoritative readback." }
            } catch (cancel: CancellationException) { throw cancel }
            catch (failure: Exception) {
                error = "VAN could not confirm your answer. Its request identity is kept. Check current state before retrying the same answer. ${failure.message.orEmpty()}"
            } finally { pending = false }
        }
    }
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            val decision = current
            if (decision == null) Text("This decision has no usable choices or authority contract. Refresh Attention.")
            else {
                Text(decision.title, style = tokens.type.headline, color = tokens.color.textPrimary)
                Text(decision.body, style = tokens.type.body, color = tokens.color.textSecondary)
                Text("${decision.status.replace('_', ' ')} · revision ${decision.revision}", style = tokens.type.label)
                decision.expiresAtUnix?.let { Text("Answer expires ${ownerTime(it * 1000L)}${if (now >= it) " · expired" else ""}", style = tokens.type.label) }
                decision.evidence.forEach { evidence ->
                    Text("${evidence.optString("label", "Evidence")}: ${evidence.optString("ref")}\n${evidence.optString("kind")} · ${ownerTime(evidence.optLong("observed_at_unix") * 1000L)}", style = tokens.type.label)
                    Text(if (evidence.optString("verification") == "REFERENCE_ONLY") "Reference only; its contents have not been verified for this choice."
                        else "Gateway correlation: ${evidence.optString("verification", "Not supplied")}. This does not authorize an action.", style = tokens.type.label)
                }
                if (decision.evidence.isEmpty()) Text("No evidence references were supplied.", style = tokens.type.label)
                decision.missionId?.let { mission -> TextButton(onClick = { onOpenRoute(VanRoute.missionRoute(mission)) }) { Text("Review linked mission") } }
                Text("This records your choice. Consequential actions require their separate exact authority and approval.", style = tokens.type.label)
                if (decision.selectedChoice != null) {
                    Text("Your answer: ${decision.choices.find { it.id == decision.selectedChoice }?.label ?: decision.selectedChoice}\nYour reason: ${decision.answerNote.ifBlank { "No reason supplied" }}")
                }
                val editable = !pending && pendingBody == null && decision.answerable(now)
                decision.choices.forEach { option ->
                    OutlinedButton(enabled = editable, onClick = { choice = option.id }, modifier = Modifier.fillMaxWidth()) {
                        Text("${if (choice == option.id) "✓ " else ""}${option.label}${option.description.takeIf { it.isNotBlank() }?.let { "\n$it" }.orEmpty()}")
                    }
                }
                if (decision.answerable(now) || pendingBody != null) {
                    OutlinedTextField(note, { note = it }, enabled = editable, label = { Text("Your reason, optional") }, modifier = Modifier.fillMaxWidth())
                    Button(enabled = editable && decision.choices.any { it.id == choice } && note.length <= 2000, onClick = {
                        send(decision.prepareAnswer(choice, note, UUID.randomUUID().toString(), now))
                    }) { Text("Record this answer") }
                }
                pendingBody?.let { raw ->
                    val exact = JSONObject(raw)
                    Text("Unconfirmed request: ${exact.optString("request_id")}. VAN will not substitute a different answer.", style = tokens.type.label)
                    OutlinedButton(enabled = !pending && decision.answerable(now), onClick = { send(exact) }) { Text("Retry exact answer") }
                }
            }
            error?.let { Text(it, style = tokens.type.body) }
            notice?.let { Text(it, style = tokens.type.label) }
            OutlinedButton(enabled = !pending, onClick = {
                pending = true
                scope.launch {
                    try { readAnswer(); error = null }
                    catch (cancel: CancellationException) { throw cancel }
                    catch (failure: Exception) { error = "Current decision could not be read. ${failure.message.orEmpty()}" }
                    finally { pending = false }
                }
            }) { Text(if (pending) "Checking…" else "Check current decision") }
        }
    }
}
