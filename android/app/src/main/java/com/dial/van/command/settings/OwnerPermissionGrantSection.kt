package com.dial.van.command.settings

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
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
import androidx.compose.ui.unit.dp
import com.dial.van.VanApplication
import com.dial.van.command.nav.VanRoute
import com.dial.van.command.owner.OwnerDataSection
import com.dial.van.command.owner.ownerRows
import com.dial.van.command.owner.ownerTime
import com.dial.van.command.owner.ownerValue
import com.dial.van.control.VanCommandSource
import org.json.JSONObject

@Composable
internal fun OwnerPermissionGrantSection(app: VanApplication, onOpenRoute: (String) -> Unit) {
    OwnerDataSection("Grant exact owner consent", load = { app.gatewayClient.permissionContracts() }) { body, actions ->
        var selected by remember { mutableStateOf<JSONObject?>(null) }
        var parameters by rememberSaveable { mutableStateOf("{}") }
        var hours by rememberSaveable { mutableStateOf("24") }
        var uses by rememberSaveable { mutableStateOf("1") }
        var error by remember { mutableStateOf<String?>(null) }
        var exact by remember { mutableStateOf<String?>(null) }
        Text("Consent applies only to one registered action and the exact parameters you review. It does not replace canonical command authority, provider policy, VATI gates or per-use A4 approval.")
        val contracts = body.optJSONArray("contracts").ownerRows()
        if (contracts.isEmpty()) Text("No native action contract can currently receive this owner consent.")
        contracts.forEach { contract -> TextButton(enabled = actions.canMutate, onClick = {
            selected = contract; error = null
            val schema = contract.optJSONObject("parameter_schema")
            val fields = schema?.optJSONArray("required")
            val initial = JSONObject()
            if (fields != null) (0 until fields.length()).forEach { index ->
                val name = fields.getString(index)
                initial.put(name, when (schema?.optJSONObject("properties")?.optJSONObject(name)?.optString("type")) {
                    "integer", "number" -> 0; "boolean" -> false; "array" -> org.json.JSONArray(); "object" -> JSONObject(); else -> ""
                })
            }
            parameters = initial.toString(2)
        }) { Text("${if (selected?.optString("action_id") == contract.optString("action_id")) "✓ " else ""}${contract.ownerValue("permission")} · ${contract.ownerValue("action_id")}") } }
        selected?.let { contract ->
            Text("Native class ${contract.ownerValue("action_class")} · required fields ${contract.ownerValue("required_fields")}")
            if (contract.optBoolean("fresh_native_approval_per_use")) Text("Each use still needs a fresh exact native A4 approval.")
            OutlinedTextField(parameters, { parameters = it }, enabled = actions.canMutate, label = { Text("Exact typed parameters (JSON)") }, maxLines = 8)
            OutlinedTextField(hours, { hours = it }, enabled = actions.canMutate, label = { Text("Expires after hours, maximum ${body.optLong("max_duration_ms") / 3_600_000L}") })
            OutlinedTextField(uses, { uses = it }, enabled = actions.canMutate, label = { Text("Maximum uses, 1–${body.optInt("max_uses")}") })
            error?.let { Text(it) }
            Button(enabled = actions.canMutate, onClick = {
                try {
                    val duration = hours.toLongOrNull()?.takeIf { it in 1..720 } ?: error("Choose whole hours within the expiry limit.")
                    val now = System.currentTimeMillis()
                    exact = OwnerPermissionDraft.command(body, contract, JSONObject(parameters), now + duration * 3_600_000L,
                        uses.toIntOrNull() ?: error("Choose a whole-number use budget."), now)
                    error = null
                } catch (failure: Exception) { error = failure.message }
            }) { Text("Review exact permission") }
        }
        exact?.let { command -> AlertDialog(onDismissRequest = { exact = null }, title = { Text("Approve this exact consent scope?") }, text = {
            Column(modifier = Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState())) {
                val scope = JSONObject(command.removePrefix("grant owner permission "))
                Text("${scope.ownerValue("permission")} · ${scope.ownerValue("action_id")}\nExpires ${ownerTime(scope.optLong("expires_at_ms"))}\nMaximum ${scope.optInt("max_uses")} uses")
                Text(scope.getJSONObject("parameters").toString(2))
                Text("Next, approve this sealed scope with fresh biometrics in Work. Only independently read-back consent will be reported as saved.")
            }
        }, confirmButton = { Button(enabled = actions.canMutate, onClick = {
            app.commandController.submitText(command, VanCommandSource.QUICK_ACTION, actionClass = "A4")
            exact = null; onOpenRoute(VanRoute.WORK)
        }) { Text("Continue to approval") } }, dismissButton = { TextButton(onClick = { exact = null }) { Text("Cancel") } }) }
    }
}

@Composable
internal fun PermissionGrantDetailDialog(app: VanApplication, grantId: String, onDismiss: () -> Unit) {
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Exact consent and use history") }, text = {
        Column(modifier = Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState())) {
            OwnerDataSection("Current grant $grantId", load = { app.gatewayClient.permissionGrant(grantId) }) { row, _ ->
                Text("${row.ownerValue("permission")}\nOrigin: ${row.ownerValue("origin_evidence_ref")}")
                val nativeAdmissions = row.optBoolean("native_authority_required")
                Text("Expires ${ownerTime(row.optLong("expires_at_ms"))}\nRevoked ${ownerTime(row.optLong("revoked_at_ms"))}\n${row.optInt("use_count")} ${if (nativeAdmissions) "admissions charged" else "uses"} · last ${if (nativeAdmissions) "admission" else "use"} ${ownerTime(row.optLong("last_used_at_ms"))}")
                if (nativeAdmissions) Text("An admission reserves the budget before execution. Interrupted or uncertain execution remains charged; this count does not prove provider completion.")
                row.optJSONObject("exact_scope")?.let { Text(it.toString(2)) }
                Text(if (row.optBoolean("native_authority_required")) "Every effect still requires independent canonical action authority." else "This historical grant has no supplied native consumption contract.")
                if (row.optBoolean("fresh_native_approval_per_use")) Text("Fresh native biometric approval is required for each A4 use.")
            }
        }
    }, confirmButton = { TextButton(onClick = onDismiss) { Text("Close") } })
}
