package com.dial.van.browser

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.command.owner.ownerRows
import com.dial.van.command.owner.ownerTime
import com.dial.van.command.owner.ownerValue
import com.dial.van.control.VanCommandSource
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

@Composable
fun BrowserActionPlansPanel(app: VanApplication, activity: FragmentActivity, snapshot: BrowserSessionSnapshot,
    onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    val command by app.commandController.state.collectAsState()
    var body by remember(snapshot.sessionId) { mutableStateOf<JSONObject?>(null) }
    var pending by remember { mutableStateOf(false) }
    var fresh by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var task by rememberSaveable(snapshot.sessionId) { mutableStateOf("") }
    var taskDomain by rememberSaveable(snapshot.sessionId) { mutableStateOf("") }
    var taskGoal by rememberSaveable(snapshot.sessionId) { mutableStateOf("") }
    var preparationRequested by rememberSaveable(snapshot.sessionId) { mutableStateOf(false) }
    var operation by rememberSaveable { mutableStateOf("click_element") }
    var selector by rememberSaveable { mutableStateOf("") }
    var text by rememberSaveable { mutableStateOf("") }
    var resultKind by rememberSaveable { mutableStateOf("url_equals") }
    var resultSelector by rememberSaveable { mutableStateOf("") }
    var resultValue by rememberSaveable { mutableStateOf("") }
    var attribute by rememberSaveable { mutableStateOf("") }
    var stepsJson by rememberSaveable(snapshot.sessionId) { mutableStateOf("[]") }
    var exactDraft by rememberSaveable(snapshot.sessionId) { mutableStateOf<String?>(null) }
    var selected by remember { mutableStateOf<JSONObject?>(null) }
    var cancelPlan by remember { mutableStateOf<JSONObject?>(null) }
    suspend fun refresh() {
        try {
            val next = app.gatewayClient.browserActionPlans(snapshot.sessionId)
            body = next; fresh = true; error = null
            next.optJSONObject("preparation_contract")?.let { contract ->
                if (!contract.isNull("observed_target_domain") && contract.optBoolean("native_domain_observation_available"))
                    taskDomain = contract.getString("observed_target_domain")
            }
            selected?.let { previous -> selected = next.optJSONArray("plans").ownerRows().find { it.optString("plan_id") == previous.optString("plan_id") } ?: previous }
            exactDraft?.let { raw ->
                val id = JSONObject(raw).optString("idempotency_key")
                next.optJSONArray("plans").ownerRows().find { it.optString("idempotency_key") == id }?.let { selected = it; exactDraft = null }
            }
        } catch (cancel: CancellationException) { throw cancel }
        catch (failure: Exception) { fresh = false; error = "Current plan state could not be read. ${failure.message.orEmpty()}" }
    }
    LaunchedEffect(snapshot.sessionId) { refresh(); while (true) { delay(5_000L); if (!pending) refresh() } }
    fun create(raw: String) {
        if (pending) return
        exactDraft = raw; pending = true; error = null
        scope.launch {
            try {
                selected = app.gatewayClient.createBrowserActionPlan(snapshot.sessionId, JSONObject(raw))
                refresh()
            } catch (cancel: CancellationException) { throw cancel }
            catch (failure: Exception) { fresh = false; error = "The draft reply is unconfirmed. Its exact request is retained; read existing plans or retry that same draft only. ${failure.message.orEmpty()}" }
            finally { pending = false }
        }
    }
    AlertDialog(onDismissRequest = { if (!pending) onDismiss() }, title = { Text("Approve exact browser effects") }, text = {
        LazyColumn(modifier = Modifier.fillMaxWidth().heightIn(max = 520.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item {
                Text("Drafts do not execute. Review each exact element and required result, then use fresh biometric approval. Payments, credentials and login secrets are excluded.")
                Text("Session ${snapshot.sessionId} · current target ${snapshot.activeTargetId ?: "Unavailable"}")
                error?.let { Text(it) }
                val editable = fresh && !pending && exactDraft == null && BrowserActionPlan.mayDraft(body?.optJSONObject("plan_contract"))
                if (!BrowserActionPlan.mayDraft(body?.optJSONObject("plan_contract"))) Text("This profile has no current admitted mutation-plan contract. Read-only research remains available; exact effect preparation and approval are unavailable.")
                val tasks = body?.optJSONArray("task_candidates").ownerRows()
                if (tasks.isEmpty()) {
                    val preparation = body?.optJSONObject("preparation_contract")
                    val canPrepare = preparation?.optString("action_id") == "browser.task.prepare" && preparation.optString("action_class") == "A3" &&
                        preparation.optString("command_prefix") == "prepare browser task " && preparation.optBoolean("native_domain_observation_available") &&
                        preparation.opt("profile_mutation_permitted") == true && preparation.optInt("freshness_seconds") == 30 &&
                        !preparation.isNull("observed_target_domain") && preparation.optString("observed_target_domain") == taskDomain
                    Text("Prepare a canonical task for the page you are viewing. This records your exact goal and domain under owner authority; it does not execute any browser effect or delegate control.")
                    Text("Native observed page domain: ${taskDomain.ifBlank { "Unavailable; wait for authenticated current page observation." }}")
                    OutlinedTextField(taskGoal, { taskGoal = it }, enabled = editable && !command.submitting && !preparationRequested, label = { Text("Owner goal for this page, maximum 1000 characters") })
                    Button(enabled = editable && canPrepare && !command.submitting && !preparationRequested && taskGoal.isNotBlank() && taskGoal.length <= 1000, onClick = {
                        try {
                            val exact = BrowserActionPlan.prepareTask(snapshot.sessionId, taskDomain, taskGoal, System.currentTimeMillis() / 1000L)
                            preparationRequested = true
                            app.commandController.submitText(exact.text, VanCommandSource.QUICK_ACTION, actionClass = "A3",
                                expiresAtUnix = exact.expiresAtUnix, noStaleReplay = exact.noStaleReplay)
                        }
                        catch (failure: Exception) { error = failure.message }
                    }) { Text("Prepare this task through VAN") }
                    if (preparationRequested) Text("The exact preparation command was submitted. Read current tasks and command status; an uncertain preparation is not resubmitted as a new command.")
                    command.lastError?.let { Text(it) }
                    Text("After VAN records the task, read current plans to see its exact task identity. A stale or mismatched domain is refused.")
                }
                tasks.forEach { candidate -> TextButton(enabled = editable, onClick = { task = candidate.getString("task_id") }) {
                    Text("${if (task == candidate.optString("task_id")) "✓ " else ""}${candidate.ownerValue("goal")} · ${candidate.ownerValue("target_domain")}")
                } }
                TextButton(enabled = editable, onClick = { operation = "click_element" }) { Text(if (operation == "click_element") "✓ Click exact element" else "Click exact element") }
                TextButton(enabled = editable, onClick = { operation = "fill_element" }) { Text(if (operation == "fill_element") "✓ Fill exact element" else "Fill exact element") }
                OutlinedTextField(selector, { selector = it }, enabled = editable, label = { Text("Exact element selector") })
                if (operation == "fill_element") {
                    OutlinedTextField(text, { text = it }, enabled = editable, label = { Text("Non-secret text to fill") })
                    Text("VAN must independently read back that exact value from that same element.")
                } else {
                    listOf("url_equals" to "Exact final address", "element_text_equals" to "Exact observed element text", "element_attribute_equals" to "Exact observed attribute").forEach { (kind, label) ->
                        TextButton(enabled = editable, onClick = { resultKind = kind }) { Text("${if (kind == resultKind) "✓ " else ""}$label") }
                    }
                    if (resultKind != "url_equals") OutlinedTextField(resultSelector, { resultSelector = it }, enabled = editable, label = { Text("Result element selector") })
                    if (resultKind == "element_attribute_equals") OutlinedTextField(attribute, { attribute = it }, enabled = editable, label = { Text("Result attribute") })
                    OutlinedTextField(resultValue, { resultValue = it }, enabled = editable, label = { Text("Exact expected result") })
                }
                Button(enabled = editable && selector.isNotBlank() && JSONArray(stepsJson).length() < 12, onClick = {
                    try {
                        val steps = JSONArray(stepsJson)
                        val predicate = if (operation == "fill_element") JSONObject().put("kind", "input_value_equals").put("selector", selector).put("value", text)
                        else JSONObject().put("kind", resultKind).also { result -> when (resultKind) {
                            "url_equals" -> result.put("url", resultValue)
                            "element_text_equals" -> result.put("selector", resultSelector).put("text", resultValue)
                            else -> result.put("selector", resultSelector).put("attribute", attribute).put("value", resultValue)
                        } }
                        steps.put(BrowserActionPlan.step(UUID.randomUUID().toString(), operation, selector, text, predicate))
                        stepsJson = steps.toString(); selector = ""; text = ""; error = null
                    } catch (failure: Exception) { error = failure.message }
                }) { Text("Add reviewed step") }
                Text("Proposed exact steps:\n${JSONArray(stepsJson).toString(2)}")
                TextButton(enabled = editable, onClick = { stepsJson = "[]" }) { Text("Clear proposed steps") }
                Button(enabled = editable && tasks.any { it.optString("task_id") == task } && snapshot.activeTargetId != null && JSONArray(stepsJson).length() > 0, onClick = {
                    val now = System.currentTimeMillis()
                    create(BrowserActionPlan.draft(task, snapshot.activeTargetId ?: return@Button, JSONArray(stepsJson), UUID.randomUUID().toString(), now + 300_000L, now).toString())
                }) { Text("Prepare immutable five-minute plan") }
                exactDraft?.let { raw -> OutlinedButton(enabled = !pending, onClick = { create(raw) }) { Text("Retry exact draft creation") } }
                OutlinedButton(enabled = !pending, onClick = { scope.launch { refresh() } }) { Text("Read current plans") }
            }
            body?.optJSONArray("plans").ownerRows().forEach { plan -> item(key = plan.optString("plan_id")) {
                TextButton(onClick = { selected = plan }) { Text("${plan.ownerValue("plan_id")} · ${plan.ownerValue("status")}") }
            } }
        }
    }, confirmButton = { TextButton(enabled = !pending, onClick = onDismiss) { Text("Close") } })
    selected?.let { plan ->
        val approval = BrowserActionPlan.approvalCommand(plan, snapshot.sessionId, System.currentTimeMillis())
        val challenge = command.pendingA4Approval
        val resolved = challenge?.resolvedParametersJson?.let { runCatching { JSONObject(it) }.getOrNull() }
        val exactChallenge = challenge != null && resolved != null && BrowserActionPlan.matchesApproval(plan, challenge.resolvedActionId, resolved)
        AlertDialog(onDismissRequest = { selected = null }, title = { Text("Review immutable browser plan") }, text = {
            Column(modifier = Modifier.heightIn(max = 480.dp).verticalScroll(rememberScrollState())) {
                Text(BrowserActionPlan.ownerOutcome(plan))
                Text("Expires ${ownerTime(plan.optLong("deadline_ms"))}\nAllowed domains ${plan.ownerValue("allowed_domains")}\nPlan digest ${plan.ownerValue("plan_sha256")}")
                Text(plan.optJSONArray("steps")?.toString(2).orEmpty())
                Text("Step evidence: ${plan.optJSONObject("step_states")?.toString(2).orEmpty()}")
                command.lastError?.let { Text(it) }
                if (approval != null && fresh && BrowserActionPlan.mayDraft(body?.optJSONObject("plan_contract")) && !command.submitting && command.pendingA4Approval == null) Button(onClick = {
                    app.commandController.submitText(approval, VanCommandSource.QUICK_ACTION, actionClass = "A4")
                }) { Text("Request exact biometric challenge") }
                if (exactChallenge && challenge != null) Button(enabled = fresh && BrowserActionPlan.mayDraft(body?.optJSONObject("plan_contract")) && approval != null && !command.submitting && System.currentTimeMillis() / 1000L < challenge.expiresAtUnix, onClick = {
                    app.commandController.approvePendingA4(activity)
                }) { Text("Approve this exact plan with biometrics") }
                if (command.pendingA4Approval != null && !exactChallenge) Text("Another exact action is awaiting approval. Resolve it in Work before approving this plan.")
                if (plan.optString("status") !in setOf("VERIFIED_SUCCESS", "CANCELLED")) OutlinedButton(enabled = fresh && !pending, onClick = { cancelPlan = plan }) { Text("Fence remaining effects") }
                OutlinedButton(enabled = !pending, onClick = { scope.launch { refresh() } }) { Text("Read authoritative result") }
            }
        }, confirmButton = { TextButton(onClick = { selected = null }) { Text("Close review") } })
    }
    cancelPlan?.let { plan -> AlertDialog(onDismissRequest = { cancelPlan = null }, title = { Text("Fence remaining browser effects?") }, text = {
        Text("This prevents future steps. It cannot undo an effect already dispatched or establish the outcome of an uncertain step.")
    }, confirmButton = { Button(enabled = !pending, onClick = {
        cancelPlan = null; pending = true
        scope.launch {
            try {
                app.gatewayClient.cancelBrowserActionPlan(snapshot.sessionId, plan.getString("plan_id"))
                val confirmed = app.gatewayClient.browserActionPlan(snapshot.sessionId, plan.getString("plan_id"))
                check(confirmed.optString("status") in setOf("CANCELLED", "VERIFIED_SUCCESS")) { "No terminal cancellation readback was supplied." }
                selected = confirmed; refresh()
            } catch (cancel: CancellationException) { throw cancel }
            catch (failure: Exception) { fresh = false; error = "The fence outcome is unconfirmed. Read current state before another action. ${failure.message.orEmpty()}" }
            finally { pending = false }
        }
    }) { Text("Fence future steps") } }, dismissButton = { TextButton(onClick = { cancelPlan = null }) { Text("Keep plan") } }) }
}
