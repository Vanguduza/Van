package com.dial.van.browser

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class BrowserFileProviderTest {
    private fun file() = BrowserDownloadReview.Download("native_file_1", "owner-notes.txt", "text/plain", 7,
        "COMPLETED", false, null, emptySet(), contentSha256 = "a".repeat(64), targetId = "target_1")
    private fun contractRow() = JSONObject().put("provider", "ORACLE_OWNER_ARCHIVE")
        .put("contract", "VAN_OWNER_ARTIFACT_ADMISSION_V1").put("action_id", BrowserFileProvider.ACTION_ID)
        .put("required_action_class", "A4").put("freshness_seconds", 30)
        .put("state", "QUALIFIED")
        .put("target_contract_qualified", true).put("executable", true).put("exact_owner_project_admission_required", true)
        .put("source_authority", "UNTRUSTED_OWNER_FILE_EVIDENCE").put("automatic_truth_promotion", false)
        .put("provider_identity", "oracle-archive-qualified-test").put("owner_namespace", "owner_1")
        .put("project_namespace", "project_1").put("capability_receipt_sha256", "b".repeat(64)).put("provider_principal_sha256", "f".repeat(64))
    private fun contract(row: JSONObject = contractRow()) = BrowserFileProvider.Contract(row.getString("provider"), "Save on Oracle", row)
    private fun draft() = BrowserFileProvider.draft(file(), contract(), "request_key_123", 300_000, 1)
    private fun request() = draft().put("request_id", "bfile_" + "d".repeat(32)).put("request_sha256", "c".repeat(64))
        .put("session_id", "session_1").put("provider_identity", "oracle-archive-qualified-test").put("status", "DRAFT")
        .put("capability_receipt_sha256", "b".repeat(64)).put("provider_principal_sha256", "f".repeat(64))
        .put("source_authority", "UNTRUSTED_OWNER_FILE_EVIDENCE").put("automatic_truth_promotion", false)
        .put("effect_attempted", false)
        .also { row -> row.put("approval_command", "submit browser file " + JSONObject().put("session_id", "session_1")
            .put("request_id", row.getString("request_id")).put("request_sha256", row.getString("request_sha256"))) }

    @Test fun `configuration and self-reported flags alone never admit a provider`() {
        assertTrue(contract().mayPrepare)
        for (field in listOf("contract", "action_id", "required_action_class", "freshness_seconds", "target_contract_qualified",
            "executable", "exact_owner_project_admission_required", "source_authority", "automatic_truth_promotion",
            "provider_identity", "owner_namespace", "project_namespace", "capability_receipt_sha256", "provider_principal_sha256", "state")) {
            assertFalse(contract(contractRow().apply { remove(field) }).mayPrepare, field)
        }
        assertFalse(contract(contractRow().put("executable", "true")).mayPrepare)
        assertFalse(contract(contractRow().put("target_contract_qualified", false).put("state", "CONFIGURED_UNVERIFIED")).mayPrepare)
        assertFalse(contract(contractRow().put("source_authority", "CANONICAL_OWNER")).mayPrepare)
        assertFalse(contract(contractRow().put("automatic_truth_promotion", true)).mayPrepare)
    }

    @Test fun `provider catalogs cannot cross sessions or duplicate destination identity`() {
        val body = JSONObject().put("session_id", "session_1").put("contracts", JSONArray().put(contractRow()))
        assertEquals("Save on Oracle", BrowserFileProvider.contracts(body, "session_1").single().label)
        assertFailsWith<IllegalArgumentException> { BrowserFileProvider.contracts(body, "another-session") }
        assertFailsWith<IllegalArgumentException> {
            BrowserFileProvider.contracts(body.put("contracts", JSONArray().put(contractRow()).put(contractRow())), "session_1")
        }
    }

    @Test fun `only current completed safe native bytes can be proposed`() {
        assertTrue(BrowserFileProvider.safeSource(file()))
        for (invalid in listOf(file().copy(state = "QUARANTINED"), file().copy(dangerous = true),
            file().copy(contentSha256 = null), file().copy(targetId = null), file().copy(byteSize = null),
            file().copy(byteSize = BrowserTransfers.MAX_FILE_BYTES + 1), file().copy(byteSize = -1))) {
            assertFalse(BrowserFileProvider.safeSource(invalid))
            assertFailsWith<IllegalArgumentException> { BrowserFileProvider.draft(invalid, contract(), "request_key_123", 100, 1) }
        }
    }

    @Test fun `draft names exact advertised namespaces immutable bytes and bounded deadline`() {
        val prepared = draft()
        assertEquals(setOf("download_id", "provider", "owner_namespace", "project_namespace", "content_sha256", "byte_size", "idempotency_key", "deadline_ms"),
            prepared.keys().asSequence().toSet())
        assertEquals("owner_1", prepared.getString("owner_namespace")); assertEquals("project_1", prepared.getString("project_namespace"))
        assertEquals(file().contentSha256, prepared.getString("content_sha256")); assertEquals(7L, prepared.getLong("byte_size"))
        assertFailsWith<IllegalArgumentException> { BrowserFileProvider.draft(file(), contract(), "short", 100, 1) }
        assertFailsWith<IllegalArgumentException> { BrowserFileProvider.draft(file(), contract(), "request_key_123", 900_002, 1) }
        assertFailsWith<IllegalArgumentException> { BrowserFileProvider.draft(file(), contract(contractRow().put("owner_namespace", "arbitrary/path")), "request_key_123", 100, 1) }
    }

    @Test fun `stale or reversed read times never enable another exact approval`() {
        assertTrue(BrowserFileProvider.currentRead(1_000, 31_000))
        assertFalse(BrowserFileProvider.currentRead(1_000, 31_001))
        assertFalse(BrowserFileProvider.currentRead(1_000, 999))
        assertFalse(BrowserFileProvider.currentRead(0, 1_000))
    }

    @Test fun `draft creation receipt and recovery must retain source target key and deadline`() {
        assertTrue(BrowserFileProvider.matchesSource(request(), "session_1", file(), contract()))
        assertTrue(BrowserFileProvider.matchesDraft(request(), draft()))
        for (field in listOf("download_id", "provider", "owner_namespace", "project_namespace", "content_sha256", "idempotency_key")) {
            assertFalse(BrowserFileProvider.matchesDraft(request().put(field, "changed"), draft()), field)
        }
        assertFalse(BrowserFileProvider.matchesSource(request().put("provider_identity", "another-target"), "session_1", file(), contract()))
        assertFalse(BrowserFileProvider.matchesSource(request(), "session_2", file(), contract()))
        assertFalse(BrowserFileProvider.matchesDraft(request().put("byte_size", 8), draft()))
        assertFalse(BrowserFileProvider.matchesDraft(request().put("deadline_ms", 301_000), draft()))
    }

    @Test fun `changing a provider scope or capability digest cannot approve the prior target`() {
        assertTrue(contract().sameScope(contract()))
        for (field in listOf("provider_identity", "owner_namespace", "project_namespace", "capability_receipt_sha256", "provider_principal_sha256")) {
            assertFalse(contract().sameScope(contract(contractRow().put(field, "changed"))), field)
        }
    }

    @Test fun `approval names only the immutable request session and digest before expiry`() {
        val current = request()
        assertNotNull(BrowserFileProvider.approvalCommand(current, "session_1", 100))
        assertNull(BrowserFileProvider.approvalCommand(current, "another-session", 100))
        assertNull(BrowserFileProvider.approvalCommand(current, "session_1", 300_000))
        assertNull(BrowserFileProvider.approvalCommand(current.put("status", "UNKNOWN"), "session_1", 100))
        assertNull(BrowserFileProvider.approvalCommand(request().put("approval_command", "submit browser file " +
            JSONObject().put("session_id", "session_1").put("request_id", current.getString("request_id")).put("request_sha256", "d".repeat(64))), "session_1", 100))
    }

    @Test fun `another action or extra namespace parameter never matches this biometric challenge`() {
        val row = request()
        val resolved = JSONObject(row.getString("approval_command").removePrefix("submit browser file "))
        assertTrue(BrowserFileProvider.matchesApproval(row, BrowserFileProvider.ACTION_ID, resolved))
        assertFalse(BrowserFileProvider.matchesApproval(row, "browser.plan.execute", resolved))
        assertFalse(BrowserFileProvider.matchesApproval(row, BrowserFileProvider.ACTION_ID, resolved.put("owner_namespace", "owner_1")))
    }

    @Test fun `unknown running or unverifiable target writes cannot be proposed again`() {
        for (state in listOf("DRAFT", "RUNNING", "DISPATCHING", "UNKNOWN", "UNVERIFIABLE", "NEW_SERVER_STATE")) {
            assertFalse(BrowserFileProvider.mayPrepareAnother(listOf(request().put("status", state))), state)
        }
        assertTrue(BrowserFileProvider.mayPrepareAnother(emptyList()))
        assertTrue(BrowserFileProvider.mayPrepareAnother(listOf(request().put("status", "CANCELLED"))))
        assertFalse(BrowserFileProvider.mayPrepareAnother(listOf(request().put("status", "CANCELLED").put("effect_attempted", true).put("admission_id", "bfa_" + "e".repeat(32)))))
        assertFalse(BrowserFileProvider.mayPrepareAnother(listOf(request().put("status", "VERIFIED_SUCCESS"))))
        assertTrue(BrowserFileProvider.mayPrepareAnother(listOf(verified())))
        assertTrue(BrowserFileProvider.ownerOutcome(request().put("status", "UNKNOWN")).contains("will not repeat"))
    }

    private fun verified() = request().put("status", "VERIFIED_SUCCESS").put("effect_attempted", true).also { row ->
        row.put("admission_id", "bfa_" + "e".repeat(32))
        row.put("source_readback", JSONObject().put("observer", "VAN_NATIVE_PERSISTED_BYTES_READBACK")
            .put("transfer_id", "transfer_123").put("content_sha256", file().contentSha256).put("byte_size", file().byteSize))
        val receipt = JSONObject().put("contract", "VAN_OWNER_ARTIFACT_ADMISSION_V1").put("receipt_id", "receipt_1")
            .put("status", "ARCHIVED").put("executed_content", false).put("owner_truth_promoted", false).put("project_truth_promoted", false)
            .put("admission_id", row.getString("admission_id")).put("admission_claim_id", "claim_id_123")
            .put("source_authority", "UNTRUSTED_OWNER_FILE_EVIDENCE")
        for (field in listOf("provider", "provider_identity", "owner_namespace", "project_namespace", "content_sha256", "byte_size")) receipt.put(field, row.get(field))
        receipt.put("independent_content_readback", JSONObject().put("observer", "VAN_BOUNDED_PERSISTED_BYTES_READBACK")
            .put("content_sha256", file().contentSha256).put("byte_size", file().byteSize))
        row.put("effect_receipt", receipt)
        row.put("verification_receipts", JSONArray().put(JSONObject(receipt.toString())).put(JSONObject(receipt.toString())))
    }

    @Test fun `success requires exact persisted bytes namespace receipt and no execution or truth promotion`() {
        assertTrue(BrowserFileProvider.verifiedEffect(verified()))
        assertTrue(BrowserFileProvider.ownerOutcome(verified()).contains("independently verified"))
        for (field in listOf("provider_identity", "owner_namespace", "project_namespace", "content_sha256", "byte_size", "receipt_id")) {
            val row = verified(); row.getJSONObject("effect_receipt").remove(field)
            assertFalse(BrowserFileProvider.verifiedEffect(row), field)
        }
        for (flag in listOf("executed_content", "owner_truth_promoted", "project_truth_promoted")) {
            val row = verified(); row.getJSONObject("effect_receipt").put(flag, true)
            assertFalse(BrowserFileProvider.verifiedEffect(row), flag)
        }
        val mismatched = verified(); mismatched.getJSONObject("effect_receipt").getJSONObject("independent_content_readback").put("content_sha256", "d".repeat(64))
        assertFalse(BrowserFileProvider.verifiedEffect(mismatched))
        assertTrue(BrowserFileProvider.ownerOutcome(mismatched).contains("No target admission is confirmed"))
    }

    @Test fun `VEKL admission is a canonical candidate rather than owner or project truth`() {
        val row = verified().put("provider", "VEKL_OWNER_CANDIDATE_INGRESS")
        val receipt = row.getJSONObject("effect_receipt").put("provider", "VEKL_OWNER_CANDIDATE_INGRESS").put("status", "CANDIDATE_RECORDED")
        assertFalse(BrowserFileProvider.verifiedEffect(row))
        receipt.put("source_authority", "UNTRUSTED_OWNER_FILE_EVIDENCE").put("canonical_candidate_id", "candidate_1")
        row.put("verification_receipts", JSONArray().put(JSONObject(receipt.toString())).put(JSONObject(receipt.toString())))
        assertTrue(BrowserFileProvider.verifiedEffect(row))
        assertTrue(BrowserFileProvider.ownerOutcome(row).contains("Owner and project truth remain unchanged"))
        receipt.put("source_authority", "CANONICAL_OWNER")
        assertFalse(BrowserFileProvider.verifiedEffect(row))
    }

    @Test fun `native source readback and separate verification cannot be omitted or swapped`() {
        assertFalse(BrowserFileProvider.verifiedEffect(verified().apply { remove("source_readback") }))
        assertFalse(BrowserFileProvider.verifiedEffect(verified().put("verification_receipts", JSONArray())))
        assertFalse(BrowserFileProvider.verifiedEffect(verified().also { row ->
            row.put("verification_receipts", JSONArray().put(row.getJSONObject("effect_receipt")))
        }))
        val swappedSource = verified().also { it.getJSONObject("source_readback").put("content_sha256", "e".repeat(64)) }
        assertFalse(BrowserFileProvider.verifiedEffect(swappedSource))
        val swappedAdmission = verified().also { it.getJSONObject("effect_receipt").put("admission_id", "bfa_" + "f".repeat(32)) }
        assertFalse(BrowserFileProvider.verifiedEffect(swappedAdmission))
        val swappedVerification = verified().also { it.getJSONArray("verification_receipts").getJSONObject(0).put("admission_claim_id", "another_claim_123") }
        assertFalse(BrowserFileProvider.verifiedEffect(swappedVerification))
        val unexpectedProvider = verified().put("provider", "UNREGISTERED_PROVIDER").also { row ->
            row.getJSONObject("effect_receipt").put("provider", "UNREGISTERED_PROVIDER")
        }
        assertFalse(BrowserFileProvider.verifiedEffect(unexpectedProvider))
    }

    @Test fun `external observation remains scoped evidence without success or replacement authority`() {
        val row = verified().put("status", "UNKNOWN")
        fun observation() = JSONObject().put("session_id", row.getString("session_id"))
            .put("request_id", row.getString("request_id")).put("request_sha256", row.getString("request_sha256"))
            .put("canonical_status", "UNKNOWN").put("effect_observation", JSONObject()
                .put("status", "OBSERVED_EXTERNAL_EFFECT").put("receipt", JSONObject(row.getJSONObject("effect_receipt").toString()))
                .put("reason", JSONObject.NULL).put("observed_at_ms", 1_000)
                .put("automatic_replacement_authorized", false).put("governed_reconciliation_required", true))
        assertTrue(BrowserFileProvider.matchesObservation(row, observation()))
        assertFalse(BrowserFileProvider.verifiedEffect(row))
        assertFalse(BrowserFileProvider.mayPrepareAnother(listOf(row)))
        assertTrue(BrowserFileProvider.observationOutcome(observation()).contains("does not confirm command success"))
        for (field in listOf("session_id", "request_id", "request_sha256")) {
            assertFalse(BrowserFileProvider.matchesObservation(row, observation().put(field, "another")), field)
        }
        for (field in listOf("automatic_replacement_authorized", "governed_reconciliation_required")) {
            val changed = observation(); changed.getJSONObject("effect_observation").put(field, field == "automatic_replacement_authorized")
            assertFalse(BrowserFileProvider.matchesObservation(row, changed), field)
        }
        val swapped = observation(); swapped.getJSONObject("effect_observation").getJSONObject("receipt").put("admission_claim_id", "another_claim_123")
        assertFalse(BrowserFileProvider.matchesObservation(row, swapped))
        val unknown = observation(); unknown.getJSONObject("effect_observation").put("status", "STILL_UNKNOWN").put("receipt", JSONObject.NULL)
        assertTrue(BrowserFileProvider.matchesObservation(row, unknown))
        assertFalse(BrowserFileProvider.matchesObservation(row, unknown.also { it.getJSONObject("effect_observation").put("receipt", row.getJSONObject("effect_receipt")) }))
    }

    @Test fun `known draft refusals and ambiguous transport outcomes stay distinct without exposing error bodies`() {
        assertNull(BrowserFileProvider.draftRefusal(null, null))
        assertNull(BrowserFileProvider.draftRefusal(408, "timeout"))
        assertNull(BrowserFileProvider.draftRefusal(500, "provider secret must not be shown"))
        assertTrue(BrowserFileProvider.draftRefusal(409, """{"detail":"artifact_target_write_unsettled"}""")!!.contains("another browser session"))
        val refused = BrowserFileProvider.draftRefusal(403, """{"detail":"private bearer must not be shown"}""")!!
        assertTrue(refused.contains("refused")); assertFalse(refused.contains("private bearer"))
        val noEffect = request().put("status", "REFUSED").put("effect_attempted", false).put("failure_reason", "artifact_source_refused")
        assertTrue(BrowserFileProvider.mayPrepareAnother(listOf(noEffect)))
        assertTrue(BrowserFileProvider.ownerOutcome(noEffect).contains("No target write was admitted"))
        assertFalse(BrowserFileProvider.mayPrepareAnother(listOf(noEffect.put("effect_attempted", true))))
    }

    @Test fun `unavailable external observations never prove absence or allow replacement`() {
        val row = request().put("status", "UNKNOWN").put("effect_attempted", true)
        fun unknown() = JSONObject().put("session_id", row.getString("session_id"))
            .put("request_id", row.getString("request_id")).put("request_sha256", row.getString("request_sha256"))
            .put("canonical_status", "UNKNOWN").put("effect_observation", JSONObject().put("status", "STILL_UNKNOWN")
                .put("receipt", JSONObject.NULL).put("reason", "artifact_external_observation_unavailable").put("observed_at_ms", 1_000)
                .put("automatic_replacement_authorized", false).put("governed_reconciliation_required", true))
        assertTrue(BrowserFileProvider.matchesObservation(row, unknown()))
        assertFalse(BrowserFileProvider.mayPrepareAnother(listOf(row)))
        assertTrue(BrowserFileProvider.observationOutcome(unknown()).contains("Governed reconciliation"))
        for (field in listOf("receipt", "reason", "observed_at_ms", "automatic_replacement_authorized", "governed_reconciliation_required")) {
            val missing = unknown(); missing.getJSONObject("effect_observation").remove(field)
            assertFalse(BrowserFileProvider.matchesObservation(row, missing), field)
        }
        val leaked = unknown(); leaked.getJSONObject("effect_observation").put("reason", "private bearer token must not be shown")
        assertFalse(BrowserFileProvider.matchesObservation(row, leaked))
        val timestamp = unknown(); timestamp.getJSONObject("effect_observation").put("observed_at_ms", "1000")
        assertFalse(BrowserFileProvider.matchesObservation(row, timestamp))
        assertFalse(BrowserFileProvider.matchesObservation(row, unknown().put("canonical_status", "OBSERVED_EXTERNAL_EFFECT")))
    }
}
