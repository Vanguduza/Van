package com.dial.van.browser

import org.json.JSONObject

/** A file is evidence. Provider admission never makes its contents owner or project truth. */
object BrowserFileProvider {
    const val ACTION_ID = "browser.file.provider.submit"
    private val namespaces = Regex("[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
    private val identities = Regex("[A-Za-z0-9_-]{8,128}")
    private val requestIds = Regex("bfile_[a-f0-9]{32}")
    private val sha256 = Regex("[a-f0-9]{64}")

    data class Contract(
        val provider: String, val label: String, val row: JSONObject,
    ) {
        val mayPrepare: Boolean get() = provider in setOf("ORACLE_OWNER_ARCHIVE", "VEKL_OWNER_CANDIDATE_INGRESS") &&
            row.optString("contract") == "VAN_OWNER_ARTIFACT_ADMISSION_V1" &&
            row.optString("action_id") == ACTION_ID && row.optString("required_action_class") == "A4" &&
            row.optInt("freshness_seconds") == 30 && row.opt("target_contract_qualified") == true &&
            row.optString("state") == "QUALIFIED" && row.opt("executable") == true && row.opt("exact_owner_project_admission_required") == true &&
            row.optString("source_authority") == "UNTRUSTED_OWNER_FILE_EVIDENCE" &&
            row.opt("automatic_truth_promotion") == false &&
            row.optString("provider_identity").isNotBlank() &&
            namespaces.matches(row.optString("owner_namespace")) && namespaces.matches(row.optString("project_namespace")) &&
            sha256.matches(row.optString("capability_receipt_sha256")) && sha256.matches(row.optString("provider_principal_sha256"))

        fun sameScope(other: Contract): Boolean = provider == other.provider &&
            listOf("provider_identity", "owner_namespace", "project_namespace", "capability_receipt_sha256", "provider_principal_sha256")
                .all { row.optString(it) == other.row.optString(it) }
    }

    fun contracts(body: JSONObject, sessionId: String): List<Contract> {
        require(body.optString("session_id") == sessionId) { "The file-provider catalog belongs to another session." }
        val rows = body.getJSONArray("contracts")
        return (0 until rows.length()).map { index ->
            val row = rows.getJSONObject(index)
            val provider = row.getString("provider")
            Contract(provider, when (provider) {
                "ORACLE_OWNER_ARCHIVE" -> "Save on Oracle"
                "VEKL_OWNER_CANDIDATE_INGRESS" -> "Add to VEKL"
                else -> "Unavailable file provider"
            }, row)
        }.also { require(it.map(Contract::provider).distinct().size == it.size) { "Duplicate provider contracts are unavailable." } }
    }

    fun safeSource(file: BrowserDownloadReview.Download): Boolean = file.id.matches(Regex("[A-Za-z0-9_-]{1,128}")) &&
        file.state == "COMPLETED" && !file.dangerous && !file.targetId.isNullOrBlank() &&
        file.byteSize != null && file.byteSize in 0..BrowserTransfers.MAX_FILE_BYTES &&
        file.contentSha256?.matches(sha256) == true

    fun currentRead(observedAtMs: Long, nowMs: Long): Boolean = observedAtMs > 0 &&
        nowMs >= observedAtMs && nowMs - observedAtMs <= 30_000

    fun draftRefusal(httpStatus: Int?, body: String?): String? {
        if (httpStatus == null || httpStatus !in 400..499 || httpStatus == 408) return null
        val reason = body?.let { runCatching { JSONObject(it).optString("detail") }.getOrNull() }
        return if (reason == "artifact_target_write_unsettled") {
            "A previous write of these exact bytes to this target is unsettled, possibly in another browser session. Read its evidence; VAN will not submit another copy."
        } else "The gateway refused this exact draft ($httpStatus). No provider effect was requested. Read current requests before another decision."
    }

    fun draft(file: BrowserDownloadReview.Download, contract: Contract, requestKey: String,
        deadlineMs: Long, nowMs: Long): JSONObject {
        require(safeSource(file) && contract.mayPrepare) { "The current safe source and qualified exact target are required." }
        require(identities.matches(requestKey)) { "A stable draft request identity is required." }
        require(nowMs > 0 && deadlineMs > nowMs && deadlineMs - nowMs <= 900_000) { "The exact request must expire within fifteen minutes." }
        return JSONObject().put("download_id", file.id).put("provider", contract.provider)
            .put("owner_namespace", contract.row.getString("owner_namespace"))
            .put("project_namespace", contract.row.getString("project_namespace"))
            .put("content_sha256", file.contentSha256).put("byte_size", file.byteSize)
            .put("idempotency_key", requestKey).put("deadline_ms", deadlineMs)
    }

    fun matchesSource(request: JSONObject, sessionId: String, file: BrowserDownloadReview.Download,
        contract: Contract): Boolean = request.optString("session_id") == sessionId &&
        request.optString("download_id") == file.id && request.optString("provider") == contract.provider &&
        request.optString("content_sha256") == file.contentSha256 && request.optLong("byte_size", -1) == file.byteSize &&
        request.optString("source_authority") == "UNTRUSTED_OWNER_FILE_EVIDENCE" && request.opt("automatic_truth_promotion") == false &&
        listOf("provider_identity", "owner_namespace", "project_namespace", "capability_receipt_sha256", "provider_principal_sha256")
            .all { request.optString(it) == contract.row.optString(it) } &&
        requestIds.matches(request.optString("request_id")) && sha256.matches(request.optString("request_sha256"))

    fun matchesDraft(request: JSONObject, expected: JSONObject): Boolean =
        listOf("download_id", "provider", "owner_namespace", "project_namespace", "content_sha256", "idempotency_key")
            .all { request.optString(it) == expected.optString(it) } &&
            request.optLong("byte_size", -1) == expected.optLong("byte_size", -2) &&
            request.optLong("deadline_ms", -1) == expected.optLong("deadline_ms", -2)

    fun approvalCommand(request: JSONObject, sessionId: String, nowMs: Long): String? {
        val exact = request.optString("approval_command")
        val resolved = exact.takeIf { it.startsWith("submit browser file ") }?.let {
            runCatching { JSONObject(it.removePrefix("submit browser file ")) }.getOrNull()
        }
        return exact.takeIf { request.optString("session_id") == sessionId &&
            requestIds.matches(request.optString("request_id")) && sha256.matches(request.optString("request_sha256")) &&
            request.optString("status") == "DRAFT" && request.optLong("deadline_ms") > nowMs && resolved != null &&
            matchesApproval(request, ACTION_ID, resolved) }
    }

    fun matchesApproval(request: JSONObject, action: String, resolved: JSONObject): Boolean = action == ACTION_ID &&
        resolved.keys().asSequence().toSet() == setOf("session_id", "request_id", "request_sha256") &&
        listOf("session_id", "request_id", "request_sha256").all { resolved.optString(it) == request.optString(it) }

    fun mayPrepareAnother(requests: List<JSONObject>): Boolean = requests.all { request ->
        when (request.optString("status")) {
            "VERIFIED_SUCCESS" -> verifiedEffect(request)
            "REFUSED" -> request.opt("effect_attempted") == false && request.optString("failure_reason").isNotBlank()
            "CANCELLED", "EXPIRED" -> request.opt("effect_attempted") == false && request.isNull("effect_receipt")
            else -> false
        }
    }

    fun ownerOutcome(request: JSONObject): String = when (request.optString("status")) {
        "DRAFT" -> "Prepared for exact review. No provider effect is authorized yet."
        "RUNNING", "DISPATCHING" -> "The approved target admission is pending. Its result is not confirmed."
        "UNKNOWN" -> "The file may have reached the target. Read its evidence; VAN will not repeat the write."
        "UNVERIFIABLE" -> "The exact persisted target bytes could not be verified. No successful admission is confirmed."
        "CANCELLED" -> if (request.opt("effect_attempted") == false) "This request was fenced before provider dispatch. No target write was admitted."
            else "Future dispatch is fenced. A fence does not undo an already dispatched write."
        "REFUSED" -> if (request.opt("effect_attempted") == false && request.optString("failure_reason").isNotBlank())
            "The gateway refused this request before provider dispatch. No target write was admitted."
            else "The refusal lacks a confirmed no-dispatch receipt. Read authoritative state before another decision."
        "EXPIRED" -> "This exact request expired. No successful target admission is confirmed."
        "VERIFIED_SUCCESS" -> if (verifiedEffect(request)) {
            if (request.optString("provider") == "ORACLE_OWNER_ARCHIVE") "Oracle archive bytes were independently verified. File contents remain untrusted evidence."
            else "VEKL candidate bytes were independently verified. Owner and project truth remain unchanged."
        } else "The reported success lacks exact persisted-byte readback. No target admission is confirmed."
        else -> "The current file-provider result is unknown. Read authoritative state before another decision."
    }

    fun verifiedEffect(request: JSONObject): Boolean {
        val receipt = request.optJSONObject("effect_receipt") ?: return false
        val source = request.optJSONObject("source_readback") ?: return false
        val verifications = request.optJSONArray("verification_receipts") ?: return false
        return request.optString("status") == "VERIFIED_SUCCESS" && request.opt("effect_attempted") == true && requestIds.matches(request.optString("request_id")) &&
            sha256.matches(request.optString("request_sha256")) && sha256.matches(request.optString("content_sha256")) &&
            request.optString("admission_id").matches(Regex("bfa_[a-f0-9]{32}")) &&
            request.optString("source_authority") == "UNTRUSTED_OWNER_FILE_EVIDENCE" && request.opt("automatic_truth_promotion") == false &&
            source.optString("observer") == "VAN_NATIVE_PERSISTED_BYTES_READBACK" && source.optString("transfer_id").isNotBlank() &&
            source.optString("content_sha256") == request.optString("content_sha256") && source.optLong("byte_size", -1) == request.optLong("byte_size", -2) &&
            verifications.length() == 2 && receiptMatches(request, receipt) && (0 until verifications.length()).all {
                val readback = verifications.optJSONObject(it)
                readback != null && receiptMatches(request, readback) && readback.optString("admission_claim_id") == receipt.optString("admission_claim_id")
            }
    }

    /** A separate byte observation cannot change canonical command success or release a write fence. */
    fun matchesObservation(request: JSONObject, response: JSONObject): Boolean {
        val observation = response.optJSONObject("effect_observation") ?: return false
        val observedAt = observation.opt("observed_at_ms")
        if (!requestIds.matches(request.optString("request_id")) || !sha256.matches(request.optString("request_sha256")) ||
            listOf("session_id", "request_id", "request_sha256").any { response.optString(it) != request.optString(it) } ||
            response.optString("canonical_status") !in setOf("DRAFT", "RUNNING", "REFUSED", "CANCELLED", "UNKNOWN", "UNVERIFIABLE", "VERIFIED_SUCCESS") ||
            observation.opt("automatic_replacement_authorized") != false || (observedAt !is Long && observedAt !is Int) ||
            observation.optLong("observed_at_ms") <= 0 || !observation.has("receipt") || !observation.has("reason") ||
            observation.opt("governed_reconciliation_required") !is Boolean ||
            (response.optString("canonical_status") != "VERIFIED_SUCCESS" && observation.opt("governed_reconciliation_required") != true)) return false
        val reason = observation.opt("reason")
        if (reason != null && reason != JSONObject.NULL && (reason !is String || !reason.matches(Regex("[A-Za-z0-9_:-]{1,128}")))) return false
        return when (observation.optString("status")) {
            "STILL_UNKNOWN" -> observation.isNull("receipt") && observation.opt("governed_reconciliation_required") == true
            "OBSERVED_EXTERNAL_EFFECT" -> {
                val receipt = observation.optJSONObject("receipt") ?: return false
                val prior = request.optJSONObject("effect_receipt")
                request.opt("effect_attempted") == true && request.optString("admission_id").matches(Regex("bfa_[a-f0-9]{32}")) &&
                    receiptMatches(request, receipt) && (prior == null || prior.optString("admission_claim_id") == receipt.optString("admission_claim_id"))
            }
            else -> false
        }
    }

    fun observationOutcome(response: JSONObject): String = when (response.optJSONObject("effect_observation")?.optString("status")) {
        "OBSERVED_EXTERNAL_EFFECT" -> "Exact external bytes were observed. This separate read does not confirm command success or authorize another write."
        else -> "The external effect remains unknown. Governed reconciliation is required; another write is not authorized."
    }

    private fun receiptMatches(request: JSONObject, receipt: JSONObject): Boolean {
        val observed = receipt.optJSONObject("independent_content_readback") ?: return false
        val fields = listOf("provider", "provider_identity", "owner_namespace", "project_namespace", "content_sha256")
        val candidate = request.optString("provider") == "VEKL_OWNER_CANDIDATE_INGRESS"
        return request.optString("provider") in setOf("ORACLE_OWNER_ARCHIVE", "VEKL_OWNER_CANDIDATE_INGRESS") &&
            fields.all { receipt.optString(it) == request.optString(it) } &&
            receipt.optString("admission_id") == request.optString("admission_id") && identities.matches(receipt.optString("admission_claim_id")) &&
            receipt.optString("contract") == "VAN_OWNER_ARTIFACT_ADMISSION_V1" && receipt.optString("receipt_id").isNotBlank() &&
            receipt.optString("status") == (if (candidate) "CANDIDATE_RECORDED" else "ARCHIVED") &&
            receipt.opt("executed_content") == false && receipt.opt("project_truth_promoted") == false && receipt.opt("owner_truth_promoted") == false &&
            receipt.optLong("byte_size", -1) == request.optLong("byte_size", -2) &&
            observed.optString("observer") == "VAN_BOUNDED_PERSISTED_BYTES_READBACK" &&
            observed.optString("content_sha256") == request.optString("content_sha256") &&
            observed.optLong("byte_size", -1) == request.optLong("byte_size", -2) &&
            receipt.optString("source_authority") == "UNTRUSTED_OWNER_FILE_EVIDENCE" &&
            (!candidate || receipt.optString("canonical_candidate_id").isNotBlank())
    }
}
