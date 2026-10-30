package com.dial.van.command.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.command.nav.VanRoute
import com.dial.van.control.VanCommandSource
import com.dial.van.command.owner.OwnerDataSection
import com.dial.van.command.owner.ownerRows
import com.dial.van.command.owner.ownerTime
import com.dial.van.command.owner.ownerValue
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.VanPanel
import org.json.JSONObject

@Composable
fun PermissionsRoute(app: VanApplication, onBack: () -> Unit, onOpenRoute: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter), contentPadding = PaddingValues(vertical = tokens.space.space3), verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item { OutlinedButton(onClick = onBack) { Text("← Settings") }; SectionHeader("Standing permissions & readiness") }
        item { OwnerPermissionGrantSection(app, onOpenRoute) }
        item {
            OwnerDataSection("Your standing permissions", load = { app.gatewayClient.permissions() }) { body, actions ->
                var revoking by remember { mutableStateOf<JSONObject?>(null) }
                var inspecting by remember { mutableStateOf<String?>(null) }
                val grants = body.optJSONArray("granted").ownerRows()
                val stale = body.optJSONArray("stale_grants")
                if (grants.isEmpty()) Text("No live standing permissions.", style = tokens.type.body, color = tokens.color.textSecondary)
                grants.forEach { grant ->
                    val id = grant.optString("grant_id")
                    VanPanel {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text(grant.ownerValue("display_name"), style = tokens.type.body, color = tokens.color.textPrimary)
                            Text("Scope: ${grant.ownerValue("scope", "Owner-wide")}\nOrigin: ${grant.ownerValue("origin")}\nEvidence: ${grant.ownerValue("origin_evidence_ref")}", style = tokens.type.label, color = tokens.color.textSecondary)
                            Text("Granted ${ownerTime(grant.optLong("granted_at_ms"))}\nExpires ${if (grant.isNull("expires_at_ms")) "No recorded expiry" else ownerTime(grant.optLong("expires_at_ms"))}\nLast used ${if (grant.optBoolean("never_used")) "Never" else ownerTime(grant.optLong("last_used_at_ms"))} · ${grant.optInt("use_count")} uses", style = tokens.type.label, color = tokens.color.textTertiary)
                            if (stale != null && (0 until stale.length()).any { stale.optString(it) == id }) Text("Unused for at least 90 days. Review whether VAN still needs this.", style = tokens.type.body, color = tokens.color.textSecondary)
                            OutlinedButton(enabled = actions.canMutate && id.isNotBlank(), onClick = { revoking = grant }) { Text("Revoke") }
                            OutlinedButton(enabled = id.isNotBlank(), onClick = { inspecting = id }) { Text("Inspect exact scope") }
                        }
                    }
                }
                val revoked = body.optJSONArray("revoked").ownerRows()
                if (revoked.isNotEmpty()) SectionHeader("Revoked permissions")
                revoked.forEach { Text("${it.ownerValue("permission")} · revoked ${ownerTime(it.optLong("revoked_at_ms"))}", style = tokens.type.label, color = tokens.color.textSecondary) }
                revoking?.let { grant -> AlertDialog(onDismissRequest = { revoking = null }, title = { Text("Revoke ${grant.ownerValue("display_name")}?") }, text = { Text("VAN will lose this standing permission. Completed effects are unchanged. Any later authority must be granted through a supported owner approval.") }, confirmButton = {
                    Button(enabled = actions.canMutate, onClick = {
                        val id = grant.getString("grant_id"); revoking = null
                        actions.mutate("revoke:$id", "Permission revocation independently read back.") {
                            app.gatewayClient.revokePermission(id).also { receipt ->
                                check(receipt.optString("grant_id") == id && receipt.optBoolean("revoked")) { "Revocation was not confirmed." }
                                val current = app.gatewayClient.permissionGrant(id)
                                check(current.optString("grant_id") == id && !current.isNull("revoked_at_ms") && current.optLong("revoked_at_ms") > 0L) { "The revoked grant could not be independently read back." }
                            }
                        }
                    }) { Text("Revoke permission") }
                }, dismissButton = { TextButton(onClick = { revoking = null }) { Text("Keep permission") } }) }
                inspecting?.let { PermissionGrantDetailDialog(app, it, onDismiss = { inspecting = null }) }
            }
        }
        item {
            OwnerDataSection("What VAN may do unprompted", load = { app.gatewayClient.autonomy() }) { body, actions ->
                val options = DomainAutonomyOptions.parse(body)
                var selectedDomain by remember { mutableStateOf<String?>(null) }
                var selectedLevel by remember { mutableStateOf("S0") }
                var choosingDomain by remember { mutableStateOf(false) }
                var confirming by remember { mutableStateOf(false) }
                val domains = body.optJSONArray("domains").ownerRows()
                if (domains.isEmpty()) Text("No domain autonomy has been established.", style = tokens.type.body, color = tokens.color.textSecondary)
                domains.forEach { domain ->
                    VanPanel {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text(domain.ownerValue("domain"), style = tokens.type.body, color = tokens.color.textPrimary)
                            Text("Effective ceiling: ${domain.ownerValue("effective_ceiling")}\nOwner-granted ceiling: ${domain.ownerValue("owner_granted_ceiling")}\nEarned ceiling: ${domain.ownerValue("earned_ceiling")}", style = tokens.type.label, color = tokens.color.textSecondary)
                            Text("${domain.optInt("verified_successes")} verified successes · ${domain.optInt("false_successes")} false successes", style = tokens.type.label, color = tokens.color.textTertiary)
                            if (domain.optBoolean("suspended_for_false_success")) Text("Suspended following an uncorrected false success.", style = tokens.type.body, color = tokens.color.textSecondary)
                        }
                    }
                }
                Text("A ceiling limits how VAN may suggest, prepare or act in that domain. Each action still needs its own authority. Changing a ceiling requires fresh biometric approval.", style = tokens.type.label, color = tokens.color.textSecondary)
                if (options == null || options.domains.isEmpty()) {
                    Text("Ceiling editing is unavailable until the backend supplies supported domains and levels.", style = tokens.type.label, color = tokens.color.textSecondary)
                } else {
                    OutlinedButton(enabled = actions.canMutate, onClick = { choosingDomain = true }) { Text(selectedDomain ?: "Choose domain") }
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        options.levels.forEach { level ->
                            TextButton(enabled = actions.canMutate, onClick = { selectedLevel = level }) { Text(if (selectedLevel == level) "[$level]" else level) }
                        }
                    }
                    Text("S0 respond only · S1 suggest · S2 prepare · S3 reversible execution · S4 standing authority. Higher ceilings do not create action or service permissions.", style = tokens.type.label, color = tokens.color.textSecondary)
                    Button(enabled = actions.canMutate && selectedDomain in options.domains, onClick = { confirming = true }) { Text("Review ceiling change") }
                    if (choosingDomain) AlertDialog(onDismissRequest = { choosingDomain = false }, title = { Text("Choose domain") }, text = {
                        LazyColumn { options.domains.forEach { domain -> item { TextButton(onClick = { selectedDomain = domain; choosingDomain = false }) { Text(domain) } } } }
                    }, confirmButton = { TextButton(onClick = { choosingDomain = false }) { Text("Close") } })
                    if (confirming) AlertDialog(onDismissRequest = { confirming = false }, title = { Text("Set $selectedDomain to $selectedLevel?") }, text = {
                        Text("This sends an owner request. Review and approve the exact sealed change with biometrics in Work. VAN will confirm it only after checking the stored ceiling.")
                    }, confirmButton = {
                        Button(enabled = actions.canMutate && selectedDomain in options.domains, onClick = {
                            val domain = selectedDomain ?: return@Button
                            val command = options.commandText(domain, selectedLevel)
                            confirming = false
                            app.commandController.submitText(text = command, source = VanCommandSource.QUICK_ACTION, actionClass = "A4")
                            onOpenRoute(VanRoute.WORK)
                        }) { Text("Continue to approval") }
                    }, dismissButton = { TextButton(onClick = { confirming = false }) { Text("Cancel") } })
                }
                val policies = body.optJSONArray("policies").ownerRows()
                SectionHeader("Active proactive policies")
                if (policies.isEmpty()) Text("No active proactive policies.", style = tokens.type.label, color = tokens.color.textSecondary)
                policies.forEach { policy ->
                    Text("${policy.ownerValue("domain")} · ${policy.ownerValue("autonomy_level")} · ${policy.ownerValue("mission_class")}\nOwner evidence: ${policy.ownerValue("owner_evidence_ref")}\nCreated ${ownerTime(policy.optLong("created_at_ms"))}", style = tokens.type.label, color = tokens.color.textSecondary)
                }
            }
        }
        item {
            OwnerDataSection("Action authority", load = { app.gatewayClient.authorityDescriptor() }) { body, _ ->
                body.optJSONArray("subjects").ownerRows().forEach { subject ->
                    Text("${subject.ownerValue("subject")} · ${subject.ownerValue("action_class")} · ${subject.ownerValue("gate")} · ${if (subject.optBoolean("enabled")) "enabled" else "disabled"}", style = tokens.type.label, color = tokens.color.textSecondary)
                }
            }
        }
        item {
            OwnerDataSection("Automatic capability readiness", load = { app.gatewayClient.capabilityStatus() }) { body, _ ->
                body.optJSONArray("capabilities").ownerRows().forEach { capability ->
                    VanPanel(dense = true) {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                            Text(capability.ownerValue("capability_id"), style = tokens.type.body, color = tokens.color.textPrimary)
                            Text(if (capability.optBoolean("routable")) "Available within its authority gates" else "Unavailable: ${capability.ownerValue("reason")}", style = tokens.type.label, color = tokens.color.textSecondary)
                            if (!capability.isNull("detail")) Text(capability.ownerValue("detail"), style = tokens.type.label, color = tokens.color.textTertiary)
                        }
                    }
                }
            }
        }
    }
}
