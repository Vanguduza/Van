package com.dial.van.muse

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.compose.ui.platform.LocalContext
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.repeatOnLifecycle
import com.dial.van.VanApplication
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

private fun JSONObject.ownerRows(key: String): List<JSONObject> = (optJSONArray(key) ?: JSONArray()).let { rows ->
    (0 until rows.length()).mapNotNull { rows.optJSONObject(it) }
}

/** Native controls over the original server workflow; lifecycle changes only stop observations. */
@Composable
fun MuseOwnerControls(app: VanApplication) {
    val scope = rememberCoroutineScope()
    val lifecycle = (LocalContext.current as? FragmentActivity)?.lifecycle
    val clipboard = LocalClipboardManager.current
    var contexts by remember { mutableStateOf<List<JSONObject>>(emptyList()) }
    var selected by rememberSaveable { mutableStateOf("") }
    var query by rememberSaveable { mutableStateOf("") }
    var resources by remember { mutableStateOf<JSONObject?>(null) }
    var profiles by remember { mutableStateOf<JSONObject?>(null) }
    var operation by remember { mutableStateOf<JSONObject?>(null) }
    var session by remember { mutableStateOf<JSONObject?>(null) }
    var sessionRequest by rememberSaveable { mutableStateOf("") }
    var assistance by remember { mutableStateOf<JSONObject?>(null) }
    var assistanceText by rememberSaveable { mutableStateOf("") }
    var pending by rememberSaveable { mutableStateOf("") }
    var result by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var notice by remember { mutableStateOf("Reading native owner workspaces…") }
    var now by remember { mutableStateOf(System.currentTimeMillis()) }
    suspend fun call(name: String, input: JSONObject = JSONObject()): JSONObject =
        app.gatewayClient.museOwnerCall(name, if (name == "dial_owner_contexts") JSONObject()
        else JSONObject().put("context_ref", selected).put("input", input))
    fun act(block: suspend () -> Unit) {
        if (busy) return
        busy = true
        scope.launch {
            try { block() }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { notice = "Native request unavailable or unconfirmed. Reconcile its original operation before another action." }
            finally { busy = false }
        }
    }
    LaunchedEffect(app, lifecycle) {
        val currentLifecycle = lifecycle ?: return@LaunchedEffect
        currentLifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                now = System.currentTimeMillis()
                try {
                    contexts = call("dial_owner_contexts").ownerRows("contexts")
                    if (selected.isBlank()) selected = contexts.firstOrNull()?.optString("context_ref").orEmpty()
                    notice = "Native workspaces observed. Server workflows continue when this screen is closed."
                } catch (cancelled: CancellationException) { throw cancelled }
                catch (_: Exception) { notice = "Native controls unavailable. The existing Muse tasks and approvals remain separate." }
                // Observation only. Pending input and workflow requests are never dispatched here.
                delay(10_000)
            }
        }
    }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Resources and native sessions", style = MaterialTheme.typography.titleLarge)
        Text(notice)
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            contexts.forEach { context ->
                FilterChip(selected == context.optString("context_ref"), enabled = !busy && pending.isBlank(), onClick = {
                    selected = context.optString("context_ref"); operation = null; session = null; resources = null; profiles = null
                }, label = { Text(context.optString("title") + " · " + context.optJSONObject("scope")?.optString("profile_id", "Direct owner")) })
            }
        }
        if (contexts.isEmpty()) Text("An admitted native workspace is required. A screenshot does not create an owner context.")
        OutlinedTextField(query, { query = it }, label = { Text("Find a resource") }, modifier = Modifier.fillMaxWidth())
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(enabled = selected.isNotBlank() && !busy, onClick = { act { resources = call("dial_owner_discover", JSONObject().put("query", query).put("limit", 30)) } }) { Text("Discover") }
            OutlinedButton(enabled = selected.isNotBlank() && !busy, onClick = { act { profiles = call("dial_owner_profiles") } }) { Text("Profile eligibility") }
        }
        resources?.ownerRows("resources")?.forEach { resource ->
            Card { Column(Modifier.fillMaxWidth().padding(14.dp)) {
                Text(resource.optString("name"), style = MaterialTheme.typography.titleMedium)
                Text(resource.optString("resource_id") + " · " + resource.optString("version"))
                Text(resource.optJSONObject("states")?.toString(2) ?: "Resource state unobserved")
                TextButton(onClick = { act { result = call("dial_owner_discover", JSONObject().put("resource_id", resource.getString("resource_id"))).optJSONObject("resource")?.toString(2) } }, enabled = !busy) { Text("Inspect capability") }
            } }
        }
        resources?.optString("next_cursor")?.takeIf { it.isNotBlank() && it != "null" }?.let { cursor ->
            TextButton(onClick = { act { resources = call("dial_owner_discover", JSONObject().put("query", query).put("limit", 30).put("cursor", cursor)) } }, enabled = !busy) { Text("More resources") }
        }
        profiles?.ownerRows("profiles")?.forEach { profile ->
            Text((profile.optString("native_profile_ref").ifBlank { profile.optString("profile_id") }) + " · eligibility " + (profile.optJSONObject("eligibility")?.optString("state") ?: "Unobserved") + " · qualification " + (profile.optJSONObject("qualification")?.optString("state") ?: "Unqualified"))
        }
        val context = contexts.firstOrNull { it.optString("context_ref") == selected }
        context?.ownerRows("operations")?.forEach { native ->
            OutlinedButton(onClick = { act { operation = call("dial_owner_status", JSONObject().put("operation_id", native.getString("operation_id"))) } }, enabled = !busy) { Text("Open " + native.optString("title", native.optString("operation_id"))) }
        }
        context?.ownerRows("session_requests")?.forEach { request ->
            OutlinedButton(onClick = { act {
                session = call("dial_owner_session", JSONObject().put("method", "inspect").put("request", request))
                sessionRequest = request.toString()
                if (pending.isNotBlank() && JSONObject(pending).optString("kind") == "SESSION") pending = ""
            } }, enabled = !busy) { Text("Inspect session " + request.optString("native_session_ref")) }
        }
        operation?.let { row -> Card { Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(row.optString("native_reference").ifBlank { row.optString("operation_id") }, style = MaterialTheme.typography.titleMedium)
            val at = runCatching { java.time.Instant.parse(row.optString("observed_at")).toEpochMilli() }.getOrNull()
            val age = at?.let { if (now >= it) (now - it) / 1000 else null }
            Text("Execution: ${row.optString("state", "UNOBSERVED")}")
            Text("Evidence: " + if (row.has("verification_receipt")) "Available" else "Unverified")
            Text("Qualification: " + (row.optJSONObject("qualification")?.optString("state") ?: "Unqualified"))
            Text("Source age: " + (age?.let { "$it seconds" } ?: "Unobserved"))
            Text("Wait: ${row.optString("reason", "No wait reason observed")}")
            Text("Expected effect: ${row.optString("effect_state", "Unobserved")}")
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("pause", "cancel", "checkpoint", "resume").forEach { action ->
                    OutlinedButton(modifier = Modifier.heightIn(min = 48.dp), enabled = !busy && pending.isBlank() && age != null && age <= 30 && row.optString("state") !in setOf("COMPLETED", "FAILED", "CANCELLED", "OUTCOME_UNKNOWN"), onClick = { act {
                        val input = JSONObject().put("operation_id", row.getString("operation_id")).put("action", action).put("observation_digest", row.getString("observation_digest")).put("request_id", "owner-" + UUID.randomUUID())
                        pending = JSONObject().put("kind", "WORKFLOW").put("context_ref", selected).put("input", input).toString()
                        operation = call("dial_owner_control", input)
                    } }) { Text(action.replaceFirstChar { it.uppercase() }) }
                }
            }
            TextButton(onClick = { act {
                operation = call("dial_owner_status", JSONObject().put("operation_id", row.getString("operation_id")))
                if (operation?.optString("state") in setOf("PAUSED", "CANCELLED", "COMPLETED", "FAILED", "REFUSED")) pending = ""
            } }, enabled = !busy) { Text("Reconcile original operation") }
            row.ownerRows("artifacts").forEach { artifact ->
                TextButton(onClick = { act { val value = call("dial_owner_artifact", JSONObject().put("operation_id", row.getString("operation_id")).put("artifact", artifact)); result = value.optString("text").takeUnless { it.isBlank() || it == "null" } ?: artifact.toString(2) } }, enabled = !busy) { Text("Review " + artifact.optString("reference")) }
            }
        } } }
        session?.let { value -> value.optJSONObject("session")?.let { native -> Card { Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Session ${native.optString("native_session_ref")}", style = MaterialTheme.typography.titleMedium)
            val lease = native.getJSONObject("lease")
            Text("${native.optString("state")} · Input lease ${lease.optLong("generation")} · ${lease.optString("holder_kind")}")
            fun request(): JSONObject = JSONObject(sessionRequest).put("native_session_ref", native.getString("native_session_ref")).put("target_binding_digest", native.getString("target_binding_digest")).put("lease_generation", lease.getLong("generation")).put("request_id", "session-" + UUID.randomUUID())
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("takeover" to "Take over input", "release" to "Return to automation").forEach { (method, label) ->
                    OutlinedButton(modifier = Modifier.heightIn(min = 48.dp), enabled = !busy && pending.isBlank() && (method != "release" || native.optString("state") == "OWNER_CONTROL"), onClick = { act {
                        val input = request(); if (method == "release") input.put("mode", "RETURN_TO_AUTOMATION")
                        pending = JSONObject().put("kind", "SESSION").put("context_ref", selected).put("input", input).toString()
                        session = call("dial_owner_session", JSONObject().put("method", method).put("request", input))
                    } }) { Text(label) }
                }
                TextButton(onClick = { act { result = call("dial_owner_session", JSONObject().put("method", "view").put("request", request())).toString(2) } }, enabled = !busy) { Text("Existing session view") }
            }
            value.optJSONObject("observation")?.optJSONObject("extensions")?.optJSONObject("owner_controls")?.ownerRows("actions")?.forEach { helper ->
                TextButton(enabled = !busy && pending.isBlank() && native.optString("state") == "OWNER_CONTROL", onClick = { assistance = helper; assistanceText = "" }) { Text(helper.optString("label")) }
            }
            assistance?.let { helper ->
                OutlinedTextField(assistanceText, { assistanceText = it }, label = { Text(helper.optString("label", "Native input")) }, modifier = Modifier.fillMaxWidth())
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = { assistanceText = clipboard.getText()?.text.orEmpty() }) { Text("Paste text") }
                    TextButton(onClick = { clipboard.setText(AnnotatedString(assistanceText)) }) { Text("Copy text") }
                    Button(enabled = !busy && pending.isBlank(), onClick = { act {
                        val observation = value.getJSONObject("observation")
                        val input = request()
                        val id = input.getString("request_id")
                        val action = JSONObject().put("schema_version", 1).put("contract_kind", "INTERACTIVE_ACTION").put("action_id", id).put("native_operation", helper.getString("native_operation")).put("mode", helper.getString("mode")).put("native_args", JSONObject(helper.optJSONObject("native_args")?.toString() ?: "{}").put("text", assistanceText)).put("observation_id", observation.getString("observation_id")).put("context_digest", observation.getString("context_digest"))
                        if (helper.has("node_ref")) action.put("node_ref", helper.getString("node_ref")).put("tree_digest", observation.getString("scene_digest")).put("frame_ref", observation.get("frame_ref"))
                        input.put("action", action); pending = JSONObject().put("kind", "SESSION").put("context_ref", selected).put("input", input).toString()
                        session = call("dial_owner_session", JSONObject().put("method", "control").put("request", input))
                    } }) { Text("Send current input") }
                }
            }
        } } } }
        if (pending.isNotBlank()) Text("Original native request retained. Inspect the same session or reconcile the same operation; no automatic input replay occurs.")
        result?.let { Text(it, style = MaterialTheme.typography.bodySmall); TextButton(onClick = { clipboard.setText(AnnotatedString(it)) }) { Text("Copy result / artifact reference") } }
    }
}
