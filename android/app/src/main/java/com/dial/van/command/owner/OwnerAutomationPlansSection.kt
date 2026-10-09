package com.dial.van.command.owner

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import com.dial.van.VanApplication
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.util.UUID

@Composable
internal fun OwnerAutomationPlansSection(app: VanApplication, onCommand: (String) -> Unit) {
    val scope = rememberCoroutineScope()
    val clipboard = LocalClipboardManager.current
    var name by rememberSaveable { mutableStateOf("") }
    var ir by rememberSaveable { mutableStateOf("{}") }
    var revisionCapability by rememberSaveable { mutableStateOf<String?>(null) }
    var exactBody by rememberSaveable { mutableStateOf<String?>(null) }
    var pending by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    var selectedId by rememberSaveable { mutableStateOf<String?>(null) }
    var inputs by rememberSaveable(selectedId) { mutableStateOf("{}") }
    var contractsRead by remember { mutableStateOf<JSONObject?>(null) }
    fun send(raw: String) {
        if (pending) return
        exactBody = raw; pending = true; error = null; notice = null
        scope.launch {
            try {
                val request = JSONObject(raw)
                val receipt = app.gatewayClient.proposeAutomationPlan(request)
                val current = app.gatewayClient.automationPlan(receipt.getString("artifact_id"))
                check(OwnerAutomationDraft.confirmsCandidate(receipt, request, current)) { "No matching immutable candidate readback was supplied." }
                exactBody = null; selectedId = current.getString("artifact_id")
                notice = "The exact candidate was stored and independently read back. It is not deployed or authorized to execute."
            } catch (cancel: CancellationException) { throw cancel }
            catch (failure: Exception) { error = "Candidate outcome is unconfirmed or refused. Its exact request is retained; retry only that same body or read stored plans. ${failure.message.orEmpty()}" }
            finally { pending = false }
        }
    }
    OwnerDataSection("Advanced automation plan contracts", load = { app.gatewayClient.automationContracts() }) { body, actions ->
        contractsRead = body
        Text("Prepare a typed plan using the current closed operations, bounded predicates, field mappings and labelled branches. No script or arbitrary code is accepted. A candidate creates no execution or trigger authority.")
        Text("Schedule timezone: ${body.ownerValue("schedule_timezone")} · source triggers require gateway standing authority.")
        val operations = body.optJSONObject("operations")
        operations?.keys()?.asSequence()?.toList()?.forEach { primitive -> Text("${primitive.replace('_', ' ')}: ${operations.ownerValue(primitive)}") }
        Text("Predicate operators: ${body.ownerValue("predicate_operators")}\nValue types: ${body.ownerValue("value_kinds")}\nLimits: ${body.ownerValue("limits")}")
        body.optJSONArray("examples").ownerRows().forEach { example -> TextButton(enabled = actions.canMutate && exactBody == null && !pending, onClick = {
            ir = example.getJSONObject("workflow_ir").toString(2); name = example.ownerValue("semantic_name", example.ownerValue("name")); error = null
        }) { Text("Start from ${example.ownerValue("name", example.ownerValue("semantic_name"))}") } }
        OutlinedButton(onClick = { clipboard.setText(AnnotatedString(body.optJSONObject("workflow_ir_schema")?.toString(2).orEmpty())) }) { Text("Copy current typed plan schema") }
        OutlinedTextField(name, { name = it }, enabled = actions.canMutate && exactBody == null && !pending, label = { Text("Plan name") })
        revisionCapability?.let { Text("Proposing a new immutable version of $it. The current admitted artifact remains separate.")
            TextButton(enabled = exactBody == null && !pending, onClick = { revisionCapability = null }) { Text("Create a separate capability instead") } }
        OutlinedTextField(ir, { ir = it }, enabled = actions.canMutate && exactBody == null && !pending, label = { Text("Typed workflow plan (JSON)") }, maxLines = 12)
        Text("Use admitted credential aliases only. External writes require exact A4 authority, operator-bound method/domain credentials and independent target readback. An uncertain write is never repeated automatically.")
        error?.let { Text(it) }; notice?.let { Text(it) }
        Button(enabled = actions.canMutate && !pending && exactBody == null && name.isNotBlank(), onClick = {
            try { send(OwnerAutomationDraft.prepare(body, name, JSONObject(ir), UUID.randomUUID().toString(), revisionCapability).toString()) }
            catch (failure: Exception) { error = failure.message }
        }) { Text("Propose immutable candidate") }
        exactBody?.let { raw ->
            Text("Retained request ${JSONObject(raw).optString("idempotency_key")}; changing the body would create a different owner proposal.")
            OutlinedButton(enabled = actions.canMutate && !pending, onClick = { send(raw) }) { Text("Recover exact candidate request") }
            OutlinedButton(enabled = !pending, onClick = { pending = true; scope.launch {
                try {
                    val request = JSONObject(raw)
                    val state = app.gatewayClient.automationPlanRequest(request.getString("idempotency_key"))
                    val result = state.optJSONObject("result")
                    if (state.optString("state") == "COMPLETED" && result != null) {
                        val current = app.gatewayClient.automationPlan(result.getString("artifact_id"))
                        check(OwnerAutomationDraft.confirmsCandidate(result, request, current))
                        exactBody = null; selectedId = current.getString("artifact_id"); notice = "The exact completed candidate was recovered by readback."
                    } else if (state.optString("state") == "REFUSED") {
                        exactBody = null; error = "The proposal was definitively refused. Review the current contract before a new proposal."
                    } else error = "The exact proposal is still pending. No new candidate was created."
                } catch (cancel: CancellationException) { throw cancel }
                catch (failure: Exception) { error = "No definitive proposal readback was available. ${failure.message.orEmpty()}" }
                finally { pending = false }
            } }) { Text("Read proposal outcome without replay") }
        }
    }
    OwnerDataSection("Stored immutable automation plans", load = { app.gatewayClient.automationPlans() }) { body, actions ->
        val plans = body.optJSONArray("plans").ownerRows()
        if (plans.isEmpty()) Text("No immutable plans are currently recorded.")
        plans.forEach { plan -> Column {
            Text("${plan.ownerValue("capability_id")} · version ${plan.optInt("version")} · ${plan.ownerValue("lifecycle_state")} · ${plan.ownerValue("binding_state")}")
            Text("Readiness: ${plan.ownerValue("runtime_readiness_errors")}\nSemantic digest: ${plan.ownerValue("semantic_digest")}")
            OutlinedButton(enabled = actions.canMutate, onClick = { selectedId = plan.getString("artifact_id") }) { Text("Review exact plan") }
        } }
    }
    selectedId?.let { id -> AlertDialog(onDismissRequest = { selectedId = null }, title = { Text("Immutable automation plan") }, text = {
        Column(modifier = Modifier.heightIn(max = 480.dp).verticalScroll(rememberScrollState())) {
            OwnerDataSection("Current artifact $id", load = { app.gatewayClient.automationPlan(id) }) { plan, actions ->
                Text("${plan.ownerValue("capability_id")} · version ${plan.optInt("version")}\n${plan.ownerValue("lifecycle_state")} · runtime binding ${plan.ownerValue("binding_state")}")
                Text("Semantic digest ${plan.ownerValue("semantic_digest")}\nValidation ${plan.ownerValue("validation_report_digest")}\nReadiness ${plan.ownerValue("runtime_readiness_errors")}")
                Text(plan.optJSONObject("workflow_ir")?.toString(2).orEmpty())
                OutlinedButton(enabled = actions.canMutate && exactBody == null && !pending && plan.optJSONObject("workflow_ir") != null, onClick = {
                    revisionCapability = plan.getString("capability_id"); name = plan.getString("capability_id")
                    ir = plan.getJSONObject("workflow_ir").toString(2); selectedId = null
                }) { Text("Prepare an immutable revision of this owned capability") }
                contractsRead?.let { contracts -> OwnerAutomationDraft.admissionCommand(contracts, plan)?.let { admission ->
                    Text("Admission provisions this immutable artifact under current owner authority. Missing private runtime bindings remain an explicit refusal.")
                    Button(enabled = actions.canMutate, onClick = { onCommand(admission); selectedId = null }) { Text("Request guarded admission through VAN") }
                } }
                OutlinedTextField(inputs, { inputs = it }, label = { Text("Exact execution inputs (JSON)") })
                val command = runCatching { contractsRead?.let { OwnerAutomationDraft.executionCommand(it, plan, JSONObject(inputs)) } }.getOrNull()
                if (command == null) Text("This version is not currently admitted and deployed for execution. A candidate and an engine exit never verify the owner result.")
                else Button(enabled = actions.canMutate, onClick = { onCommand(command); selectedId = null }) { Text("Request this admitted capability through VAN") }
            }
        }
    }, confirmButton = { TextButton(onClick = { selectedId = null }) { Text("Close") } }) }
}

@Composable
internal fun OwnerAutomationRunDetails(app: VanApplication, runId: String) {
    var open by rememberSaveable(runId) { mutableStateOf(false) }
    OutlinedButton(onClick = { open = true }) { Text("Read exact run and step evidence") }
    if (open) AlertDialog(onDismissRequest = { open = false }, title = { Text("Automation run evidence") }, text = {
        Column(Modifier.heightIn(max = 480.dp).verticalScroll(rememberScrollState())) {
            OwnerDataSection("Run $runId", load = { app.gatewayClient.automationRun(runId) }) { run, _ ->
                Text(if (OwnerAutomationDraft.verifiedRun(run)) "This exact run has matching independent owner-result verification." else "The owner result is not independently verified.")
                Text("Artifact ${run.ownerValue("artifact_id")}\nState ${run.ownerValue("status")}\nVerifier ${run.ownerValue("verifier_status")}\nEvidence ${run.ownerValue("evidence_pointer")}")
                run.optJSONArray("steps").ownerRows().forEach { step -> Text("${step.ownerValue("step_id")}: ${step.ownerValue("state")}\nResult digest ${step.ownerValue("result_digest")}") }
                Text("Reading this receipt never replays an uncertain effect.")
            }
        }
    }, confirmButton = { TextButton(onClick = { open = false }) { Text("Close") } })
}
