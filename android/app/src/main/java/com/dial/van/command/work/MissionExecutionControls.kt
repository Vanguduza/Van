package com.dial.van.command.work

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import com.dial.van.VanApplication
import com.dial.van.command.owner.OwnerDataSection
import com.dial.van.command.owner.ownerTime
import com.dial.van.command.owner.ownerValue
import com.dial.van.gateway.GatewayHttpException
import com.dial.van.mission.MissionExecutionControl
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.util.UUID

@Composable
internal fun MissionExecutionControls(app: VanApplication, missionId: String) {
    val scope = rememberCoroutineScope()
    var exact by rememberSaveable(missionId) { mutableStateOf<String?>(null) }
    var message by rememberSaveable(missionId) { mutableStateOf("") }
    var pending by remember(missionId) { mutableStateOf(false) }
    var error by remember(missionId) { mutableStateOf<String?>(null) }
    var receipt by remember(missionId) { mutableStateOf<JSONObject?>(null) }
    var refused by remember(missionId) { mutableStateOf(false) }
    OwnerDataSection("Mission execution fence $missionId", load = { app.gatewayClient.missionControl(missionId) }) { state, actions ->
        Text("Current gateway fence: ${state.ownerValue("desired_execution")} · generation ${state.optInt("generation")}")
        Text(if (state.optBoolean("dispatch_allowed")) "New effects may be dispatched within existing authority." else "New gateway effect starts are fenced. Already-dispatched work may still finish.")
        Text("Pause is a dispatch fence, not a claim that an external process stopped. Resume does not widen command or action authority.")
        val latest = state.optJSONObject("latest_control")
        val report = state.optJSONObject("latest_worker_report")
        if (latest != null && report != null && MissionExecutionControl.workerMatches(latest, report)) {
            Text("Worker report: ${report.ownerValue("status")}\nCheckpoint: ${report.ownerValue("checkpoint_ref")}\nReported ${ownerTime(report.optLong("acknowledged_at_ms"))}")
            Text("This exact worker checkpoint or adoption is recorded. OS process suspension remains unverified.")
        } else Text("No matching current worker checkpoint or direction adoption is confirmed.")
        Text("${state.optJSONArray("pending_directions")?.length() ?: 0} directions await a matching worker adoption report.")
        receipt?.let { Text("Your request was independently read back at generation ${it.optInt("generation")}. Current state above may supersede that request.") }
        error?.let { Text(it) }
        fun send(operation: String, body: JSONObject) {
            if (pending) return
            exact = JSONObject().put("operation", operation).put("body", body).toString()
            pending = true; error = null; refused = false
            scope.launch {
                try {
                    app.gatewayClient.writeMissionControl(missionId, operation, body)
                    val readback = app.gatewayClient.missionControlRequest(missionId, body.getString("request_id"))
                    check(MissionExecutionControl.confirms(missionId, operation, body, readback)) { "No exact mission control receipt was read back." }
                    receipt = readback; exact = null; message = ""; actions.refresh()
                } catch (cancel: CancellationException) { throw cancel }
                catch (failure: Exception) {
                    refused = failure is GatewayHttpException && failure.code in setOf(400, 403, 404, 409, 422)
                    error = if (refused) "This control attempt was refused. Read current state and explicitly review a new action. ${failure.message.orEmpty()}"
                        else "The control outcome is unknown. Its exact identity is retained; read its receipt before another action. ${failure.message.orEmpty()}"
                } finally { pending = false }
            }
        }
        val maySubmit = actions.canMutate && !pending && exact == null
        OutlinedTextField(message, { message = it }, enabled = maySubmit, label = { Text("Reason or new mission direction") }, maxLines = 4)
        Button(enabled = maySubmit && state.optString("desired_execution") == "RUNNING" && message.length <= 2000, onClick = {
            send("PAUSE", MissionExecutionControl.request("PAUSE", state.getInt("generation"), UUID.randomUUID().toString(), message))
        }) { Text("Pause future effect dispatch") }
        OutlinedButton(enabled = maySubmit && state.optString("desired_execution") == "PAUSED" && message.length <= 2000, onClick = {
            send("RESUME", MissionExecutionControl.request("RESUME", state.getInt("generation"), UUID.randomUUID().toString(), message))
        }) { Text("Resume within existing authority") }
        Button(enabled = maySubmit && message.isNotBlank() && message.length <= 16000, onClick = {
            send("DIRECTION", MissionExecutionControl.request("DIRECTION", state.getInt("generation"), UUID.randomUUID().toString(), message))
        }) { Text("Deliver direction to this mission") }
        exact?.let { raw ->
            val saved = JSONObject(raw); val body = saved.getJSONObject("body"); val operation = saved.getString("operation")
            Text("Retained request ${body.optString("request_id")} · expected generation ${body.optInt("expected_generation")}")
            OutlinedButton(enabled = !pending, onClick = {
                pending = true
                scope.launch {
                    try {
                        val recovered = app.gatewayClient.missionControlRequest(missionId, body.getString("request_id"))
                        check(MissionExecutionControl.confirms(missionId, operation, body, recovered)) { "Recovered receipt did not match the exact control." }
                        receipt = recovered; exact = null; error = null; actions.refresh()
                    } catch (cancel: CancellationException) { throw cancel }
                    catch (failure: Exception) { error = "No matching receipt could be read. The original request is kept. ${failure.message.orEmpty()}" }
                    finally { pending = false }
                }
            }) { Text("Recover exact control receipt") }
            if (!refused) OutlinedButton(enabled = actions.canMutate && !pending, onClick = { send(operation, body) }) { Text("Retry exact control request") }
            if (refused) OutlinedButton(enabled = actions.canMutate && !pending, onClick = { exact = null; refused = false; error = null; actions.refresh() }) { Text("Review a new owner action from current state") }
        }
    }
}
