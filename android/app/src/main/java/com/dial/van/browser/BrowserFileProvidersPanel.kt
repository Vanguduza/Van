package com.dial.van.browser

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.command.owner.ownerTime
import com.dial.van.control.VanCommandSource
import com.dial.van.gateway.GatewayHttpException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.util.UUID

/** One exact source/destination review; provider effects have no direct Android write API. */
@Composable
fun BrowserFileProvidersPanel(app: VanApplication, activity: FragmentActivity, sessionId: String,
    file: BrowserDownloadReview.Download, offered: BrowserFileProvider.Contract, onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    val command by app.commandController.state.collectAsState()
    var currentContract by remember(sessionId, file.id, offered.provider) { mutableStateOf<BrowserFileProvider.Contract?>(null) }
    var requests by remember(sessionId, file.id, offered.provider) { mutableStateOf<List<JSONObject>>(emptyList()) }
    var selected by remember(sessionId, file.id, offered.provider) { mutableStateOf<JSONObject?>(null) }
    var selectedId by rememberSaveable(sessionId, file.id, offered.provider) { mutableStateOf<String?>(null) }
    var exactDraft by rememberSaveable(sessionId, file.id, offered.provider) { mutableStateOf<String?>(null) }
    var pending by remember { mutableStateOf(false) }
    var fresh by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var nowMs by remember { mutableStateOf(System.currentTimeMillis()) }
    var readAtMs by remember { mutableStateOf(0L) }
    var attemptedChallenges by rememberSaveable(sessionId, file.id, offered.provider) { mutableStateOf("") }
    var approvedRequestId by rememberSaveable(sessionId, file.id, offered.provider) { mutableStateOf<String?>(null) }
    var effectObservation by remember(sessionId, file.id, offered.provider) { mutableStateOf<JSONObject?>(null) }

    suspend fun readSelected(requestId: String) {
        val row = app.gatewayClient.browserFileProviderRequest(sessionId, requestId)
        check(BrowserFileProvider.matchesSource(row, sessionId, file, offered)) { "The request does not match the reviewed source and target." }
        if (selectedId != requestId) effectObservation = null
        selected = row; selectedId = requestId
    }
    suspend fun refresh() {
        fresh = false
        try {
            val catalog = BrowserFileProvider.contracts(app.gatewayClient.browserFileProviderContracts(sessionId), sessionId)
            val target = catalog.singleOrNull { it.provider == offered.provider }
            currentContract = target
            val body = app.gatewayClient.browserFileProviderRequests(sessionId)
            check(body.optString("session_id") == sessionId) { "The request history belongs to another browser session." }
            val all = body.getJSONArray("requests")
            requests = (0 until all.length()).map { all.getJSONObject(it) }
                .filter { it.optString("download_id") == file.id && it.optString("provider") == offered.provider }
            exactDraft?.let { raw ->
                val expected = JSONObject(raw)
                requests.singleOrNull { it.optString("idempotency_key") == expected.getString("idempotency_key") }?.let { found ->
                    check(BrowserFileProvider.matchesDraft(found, expected)) { "The recovered draft has different exact parameters." }
                    selectedId = found.getString("request_id"); exactDraft = null
                }
            }
            selectedId?.let { readSelected(it) }
            fresh = target != null && target.sameScope(offered)
            readAtMs = System.currentTimeMillis()
            error = if (fresh) null else "The target's exact scope changed or is unavailable. Close this review and read current file-provider contracts."
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { error = "Current target evidence could not be read. Last confirmed details remain visible; actions are unavailable until a fresh read." }
    }
    fun prepare(raw: String) {
        exactDraft = raw; pending = true; error = null
        scope.launch {
            try {
                val expected = JSONObject(raw)
                val receipt = app.gatewayClient.createBrowserFileProviderRequest(sessionId, expected)
                check(BrowserFileProvider.matchesSource(receipt, sessionId, file, offered) && BrowserFileProvider.matchesDraft(receipt, expected)) {
                    "The immutable draft did not match the reviewed source and target."
                }
                val observed = app.gatewayClient.browserFileProviderRequest(sessionId, receipt.getString("request_id"))
                check(BrowserFileProvider.matchesSource(observed, sessionId, file, offered) && BrowserFileProvider.matchesDraft(observed, expected) &&
                    observed.optString("request_sha256") == receipt.optString("request_sha256")) { "The immutable draft has no matching independent readback." }
                selectedId = observed.getString("request_id"); selected = observed; exactDraft = null
                refresh()
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (failure: Exception) {
                fresh = false
                val refusal = BrowserFileProvider.draftRefusal((failure as? GatewayHttpException)?.code, (failure as? GatewayHttpException)?.body)
                if (refusal != null) exactDraft = null
                error = refusal ?: "Draft creation is unconfirmed. No provider effect was requested. Read request history to recover this exact draft before another decision."
            } finally { pending = false }
        }
    }
    LaunchedEffect(sessionId, file.id, offered.provider) {
        refresh()
        while (true) { delay(1_000); nowMs = System.currentTimeMillis() }
    }
    LaunchedEffect(selectedId, selected?.optString("status"), approvedRequestId) {
        if (selected?.optString("status") in setOf("RUNNING", "DISPATCHING", "UNKNOWN") ||
            (selectedId != null && selectedId == approvedRequestId)) {
            while (true) {
                delay(3_000)
                if (!pending) refresh()
                if (selected?.optString("status") in setOf("VERIFIED_SUCCESS", "CANCELLED", "REFUSED", "EXPIRED", "UNVERIFIABLE")) break
            }
        }
    }
    val qualified = fresh && BrowserFileProvider.currentRead(readAtMs, nowMs) && currentContract?.mayPrepare == true && BrowserFileProvider.safeSource(file)
    AlertDialog(onDismissRequest = { if (!pending) onDismiss() }, title = { Text(offered.label) }, text = {
        Column(modifier = Modifier.heightIn(max = 480.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("${file.name}\n${file.byteSize ?: "Unknown"} bytes\nSHA256 ${file.contentSha256.orEmpty()}")
            Text("Untrusted owner file evidence. This request cannot execute its contents or change owner/project truth.")
            Text("Provider ${offered.row.optString("provider_identity")}\nOwner scope ${offered.row.optString("owner_namespace")}\nProject scope ${offered.row.optString("project_namespace")}")
            if (!qualified) Text("This exact target is unavailable until its governed contract and current admission readiness are verified.")
            error?.let { Text(it) }
            if (pending) Text("Reading or preparing this exact request…")
            if (exactDraft == null) Button(enabled = qualified && !pending && BrowserFileProvider.mayPrepareAnother(requests), onClick = {
                val now = System.currentTimeMillis()
                prepare(BrowserFileProvider.draft(file, currentContract ?: return@Button, UUID.randomUUID().toString(), now + 300_000, now).toString())
            }) { Text("Prepare exact five-minute request") }
            exactDraft?.let { raw -> OutlinedButton(enabled = qualified && !pending && BrowserFileProvider.mayPrepareAnother(requests),
                onClick = { prepare(raw) }) { Text("Retry exact draft creation") } }
            if (!BrowserFileProvider.mayPrepareAnother(requests)) Text("An existing request still needs review or reconciliation. VAN will not repeat an uncertain target write.")
            requests.forEach { row -> TextButton(enabled = !pending, onClick = {
                pending = true; scope.launch {
                    try { readSelected(row.getString("request_id")); refresh() }
                    catch (cancelled: CancellationException) { throw cancelled }
                    catch (failure: Exception) { fresh = false; error = "The exact request could not be read. No provider effect was requested." }
                    finally { pending = false }
                }
            }) { Text("${row.optString("request_id")} · ${row.optString("status")}") } }
            selected?.let { request ->
                Text(BrowserFileProvider.ownerOutcome(request))
                Text("Request ${request.optString("request_id")}\nDigest ${request.optString("request_sha256")}\nExpires ${ownerTime(request.optLong("deadline_ms"))}")
                val approval = BrowserFileProvider.approvalCommand(request, sessionId, nowMs)
                val challenge = command.pendingA4Approval
                val resolved = challenge?.resolvedParametersJson?.let { runCatching { JSONObject(it) }.getOrNull() }
                val exactChallenge = challenge != null && resolved != null && BrowserFileProvider.matchesApproval(request, challenge.resolvedActionId, resolved)
                command.lastError?.let { Text(it) }
                if (approval != null && challenge == null) Button(enabled = qualified && !pending && !command.submitting, onClick = {
                    app.commandController.submitText(approval, VanCommandSource.QUICK_ACTION, actionClass = "A4",
                        expiresAtUnix = System.currentTimeMillis() / 1000 + 30, noStaleReplay = true)
                }) { Text("Request exact biometric challenge") }
                if (exactChallenge && challenge != null) Button(enabled = qualified && !pending && !command.submitting &&
                    approval != null && nowMs / 1000 < challenge.expiresAtUnix && challenge.challengeId !in attemptedChallenges.split('\n'), onClick = {
                    attemptedChallenges += "\n${challenge.challengeId}"
                    approvedRequestId = request.getString("request_id")
                    app.commandController.approvePendingA4(activity)
                }) { Text("Approve this exact file admission with biometrics") }
                if (challenge != null && challenge.challengeId in attemptedChallenges.split('\n')) {
                    Text("This exact approval has already been attempted. Read authoritative state. If biometrics were declined, dismiss this challenge in Work before a fresh decision.")
                }
                if (challenge != null && !exactChallenge) Text("Another exact action awaits approval. Resolve it in Work before approving this file request.")
                request.optJSONObject("effect_receipt")?.let { receipt ->
                    Text("Target receipt ${receipt.optString("receipt_id")} · ${receipt.optString("status")}")
                    receipt.optJSONObject("independent_content_readback")?.let { observed ->
                        Text("Persisted-byte readback: ${observed.optString("content_sha256")} · ${observed.optLong("byte_size", -1)} bytes")
                    }
                    if (offered.provider == "VEKL_OWNER_CANDIDATE_INGRESS") Text("Candidate ${receipt.optString("canonical_candidate_id")}; no truth promotion is authorized.")
                }
                if (request.optString("status") in setOf("UNKNOWN", "UNVERIFIABLE")) OutlinedButton(enabled = !pending,
                    modifier = Modifier.testTag("browser-file-provider-observation"), onClick = {
                    pending = true; scope.launch {
                        try {
                            val observed = app.gatewayClient.browserFileProviderObservation(sessionId, request.getString("request_id"))
                            check(BrowserFileProvider.matchesObservation(request, observed)) { "The independent observation did not match this exact request." }
                            effectObservation = observed
                            error = null
                        } catch (cancelled: CancellationException) { throw cancelled }
                        catch (failure: Exception) { error = "The external receipt could not be read or did not match this exact request. Its canonical result and replacement fence remain unchanged." }
                        finally { pending = false }
                    }
                }) { Text("Check external receipt") }
                effectObservation?.takeIf { it.optString("request_id") == request.optString("request_id") }?.let { observed ->
                    Text(BrowserFileProvider.observationOutcome(observed), modifier = Modifier.testTag("browser-file-provider-observation-result"))
                    Text("Canonical result at this read: ${observed.optString("canonical_status")}")
                    observed.getJSONObject("effect_observation").optJSONObject("receipt")?.let { receipt ->
                        Text("Observed target receipt ${receipt.optString("receipt_id")} · ${receipt.optString("status")}")
                        Text("Observed SHA256 ${receipt.optString("content_sha256")} · ${receipt.optLong("byte_size", -1)} bytes")
                    }
                }
                if (request.optString("status") == "DRAFT") OutlinedButton(enabled = fresh && BrowserFileProvider.currentRead(readAtMs, nowMs) &&
                    !pending && !command.submitting && request.optString("request_id") != approvedRequestId, onClick = {
                    pending = true; scope.launch {
                        try {
                            app.gatewayClient.cancelBrowserFileProviderRequest(sessionId, request.getString("request_id"))
                            readSelected(request.getString("request_id"))
                            check(selected?.optString("status") == "CANCELLED") { "The draft fence was not confirmed." }
                            refresh()
                        } catch (cancelled: CancellationException) { throw cancelled }
                        catch (failure: Exception) { fresh = false; error = "The fence outcome is unconfirmed. Read authoritative state before another action." }
                        finally { pending = false }
                    }
                }) { Text("Fence this unsubmitted draft") }
            }
            OutlinedButton(enabled = !pending, onClick = { pending = true; scope.launch { try { refresh() } finally { pending = false } } }) {
                Text("Read authoritative requests and result")
            }
        }
    }, confirmButton = { TextButton(enabled = !pending, onClick = onDismiss) { Text("Close") } })
}
