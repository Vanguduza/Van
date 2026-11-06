package com.dial.van.queue

import com.dial.van.session.*
import kotlinx.coroutines.flow.MutableStateFlow
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** SOURCE: actual canonical queue→adapter→manager read/reconcile; native boundaries use the named host fixtures. */
class SessionRecoveryActualStoreTest {
    private fun fixture() = QueueRestorationActualStoreTest().also { it.setup() }
    private fun envelope(expired: Boolean) = SessionEnvelope.build(
        messageId = "original-message", vanSessionId = "original-session", sessionEpoch = 1,
        pathEpoch = 1, deviceId = "SOURCE-device", kind = "command.submit",
        createdAtMs = if (expired) 1 else System.currentTimeMillis(),
        idempotencyKey = "original-outer-key", commandId = "original-command",
        payload = JSONObject().put("command_id", "original-command").put("device_id", "SOURCE-device")
            .put("idempotency_key", "original-http-key").put("issued_at_unix", if (expired) 1 else System.currentTimeMillis() / 1000)
            .put("signature", "SOURCE-original-proof").put("text", "SOURCE original bytes"),
    )
    private fun entry(expired: Boolean) = OutboxEntry(
        "original-message", "original-command", "original-outer-key", "original-turn",
        if (expired) 1 else System.currentTimeMillis(), if (expired) 2 else System.currentTimeMillis() + 600000,
        CommandStorability.SAFE_TO_RETRY, "A1", false, "original-message",
        neverDispatched = false, profileId = "SOURCE-profile",
    )
    private fun set(target: Any, name: String, value: Any?) = QueueRestorationActualStoreTest.set(target, name, value)
    private fun manager(store: SessionOutboxStore, entry: OutboxEntry, envelope: JSONObject, profile: String = "SOURCE-profile"): VanHermesSessionManager {
        // Run the actual reconciliation method without constructing native sockets/TLS.
        // No native/execution qualification is claimed by this constructor boundary fixture.
        val field = Class.forName("sun.misc.Unsafe").getDeclaredField("theUnsafe").also { it.isAccessible = true }
        val unsafe = field.get(null)
        val owner = unsafe.javaClass.getMethod("allocateInstance", Class::class.java)
            .invoke(unsafe, VanHermesSessionManager::class.java) as VanHermesSessionManager
        val queuedType = VanHermesSessionManager::class.java.declaredClasses.single { it.simpleName == "QueuedMessage" }
        val queued = queuedType.declaredConstructors.single().also { it.isAccessible = true }.newInstance(entry, envelope)
        set(owner, "outbox", ArrayDeque<Any>().also { it.addLast(queued) })
        set(owner, "inFlight", linkedMapOf<String, JSONObject>())
        set(owner, "recoveryHeld", mutableSetOf<String>())
        set(owner, "originalRecoveryAllowed", mutableSetOf<String>())
        set(owner, "transientEntries", linkedMapOf<String, OutboxEntry>())
        set(owner, "transientOwners", linkedMapOf<String, Pair<String, String>>())
        set(owner, "store", store)
        set(owner, "ownerSelection", { profile to "SOURCE-device" })
        set(owner, "expired", mutableListOf<OutboxEntry>())
        set(owner, "onUndelivered", { _: List<Pair<String, String>> -> Unit })
        set(owner, "onRecoveredOriginal", { _: JSONObject -> Unit })
        setState(owner, VanHermesSessionManager.State())
        return owner
    }
    private fun verifiedReceipt(record: OutboxEntry, original: JSONObject, accepted: Boolean = false): JSONObject {
        val reference = OriginalCommandReference.fromStored(record, original, "SOURCE-profile", "SOURCE-device")!!
        reference.remove("command_request")
        val result = JSONObject().put("command_id", record.commandId)
            .put("idempotency_key", original.getJSONObject("payload").getString("idempotency_key"))
            .put("status", if (accepted) "accepted" else "denied")
        val receipt = JSONObject().put("reference", reference).put("request_hash", "a".repeat(64))
            .put("history_owner", if (accepted) "command_mission" else "idempotency_refusal").put("result", result)
        if (accepted) {
            result.put("mission_id", "SOURCE-original-mission").put("hermes_run_id", "SOURCE-original-run")
                .put("correlation_id", "SOURCE-original-correlation")
            receipt.put("owner_result", JSONObject().put("command_id", record.commandId)
                .put("mission_id", "SOURCE-original-mission").put("correlation_id", "SOURCE-original-correlation")
                .put("mission_state", "RUNNING").put("owner_status", "WORKING"))
        }
        return receipt
    }
    private fun reconcile(owner: VanHermesSessionManager, state: String?, identity: String = "original-command") {
        val method = VanHermesSessionManager::class.java.getDeclaredMethod("adoptCursor", JSONObject::class.java)
        method.isAccessible = true
        method.invoke(owner, JSONObject().put("command_states", JSONObject().also {
            if (state != null) it.put(identity, state)
        }))
    }
    @Test fun expiredPendingAndUnavailableReadbackKeepOriginalAcrossOwnerRestart() {
        for (answer in listOf(null, "UNKNOWN", "RESULT_PENDING", "ORIGINAL_UNRESOLVED", "invented-state")) {
            val fixture = fixture()
            val adapter = EncryptedSessionOutboxStore(fixture.queue)
            val original = envelope(true).toString()
            adapter.persist(entry(true), original)
            assertTrue(fixture.queue.recordsOfKind(OutboxPersistence.SESSION_KIND).isEmpty())
            assertEquals(original, adapter.restore().single().second)
            val ciphertext = fixture.store.memory["cmd_original-message"]
            repeat(2) {
                val restored = adapter.restore().single()
                val owner = manager(adapter, restored.first, JSONObject(restored.second))
                reconcile(owner, answer)
                assertEquals(original, adapter.restore().single().second)
                assertEquals(ciphertext, fixture.store.memory["cmd_original-message"])
                assertTrue(owner.queuedForOwner().single().second.contains("unconfirmed"))
            }
            fixture.queue.purgeExpired()
            assertEquals(original, adapter.restore().single().second)
        }
    }
    @Test fun definitiveOriginalResultSettlesOnlyOriginalAndPreservesConcurrentGeneric() {
        val fixture = fixture()
        val adapter = EncryptedSessionOutboxStore(fixture.queue)
        adapter.persist(entry(true), envelope(true).toString())
        val concurrent = QueueRestorationActualStoreTest.enqueue(fixture.queue, "concurrent-generic")
        val restored = adapter.restore().single()
        val owner = manager(adapter, restored.first, JSONObject(restored.second))
        val read = JSONObject().put("command_states", JSONObject().put(restored.first.commandId, "ORIGINAL_COMPLETED"))
            .put("original_command_results", JSONObject().put(restored.first.commandId,
                verifiedReceipt(restored.first, JSONObject(restored.second))))
        VanHermesSessionManager::class.java.getDeclaredMethod("adoptCursor", JSONObject::class.java)
            .also { it.isAccessible = true }.invoke(owner, read)
        assertTrue(adapter.restore().isEmpty())
        assertNotNull(fixture.queue.findByIdempotencyKey(concurrent.idempotencyKey))
    }
    @Test fun referenceRetainsBothOriginalKeysAndRefusesProfileDeviceOrBodyRetargeting() {
        val original = envelope(false)
        val record = entry(false)
        val ref = OriginalCommandReference.fromStored(record, original, "SOURCE-profile", "SOURCE-device")!!
        assertEquals("original-outer-key", ref.getString("idempotency_key"))
        assertEquals("original-http-key", ref.getJSONObject("command_request").getString("idempotency_key"))
        assertEquals(original.getJSONObject("payload").toString(), ref.getJSONObject("command_request").toString())
        assertNull(OriginalCommandReference.fromStored(record, original, "other-profile", "SOURCE-device"))
        assertNull(OriginalCommandReference.fromStored(record, original, "SOURCE-profile", "other-device"))
        assertNull(OriginalCommandReference.fromStored(record.copy(profileId = null), original, "SOURCE-profile", "SOURCE-device"))
        original.getJSONObject("payload").put("command_id", "changed")
        assertNull(OriginalCommandReference.fromStored(record, original, "SOURCE-profile", "SOURCE-device"))
    }
    @Test fun provenFreshDeliveryRemainsEligibleButAmbiguousOriginalsHold() {
        val fresh = SessionReconciliation.Pending("fresh", "fresh-command", neverDispatched = true)
        val ambiguous = SessionReconciliation.Pending("ambiguous", "old-command")
        val plan = SessionReconciliation.plan(listOf(fresh, ambiguous), emptyMap())
        assertEquals(listOf("fresh"), plan.resend)
        assertEquals(listOf("ambiguous"), plan.hold)
        assertTrue(plan.settle.isEmpty())
        assertEquals(listOf("fresh"), SessionReconciliation.plan(listOf(fresh), mapOf("fresh-command" to "RESULT_PENDING")).hold)
    }
    private fun setState(owner: VanHermesSessionManager, state: VanHermesSessionManager.State) {
        val flow = MutableStateFlow(state)
        set(owner, "_state", flow)
        set(owner, "state", flow)
    }
    private fun socket(owner: VanHermesSessionManager, send: (String) -> Boolean) {
        val fake = object : okhttp3.WebSocket {
            override fun request() = okhttp3.Request.Builder().url("https://SOURCE.invalid/session").build()
            override fun queueSize() = 0L
            override fun send(text: String) = send.invoke(text)
            override fun send(bytes: okio.ByteString) = false
            override fun close(code: Int, reason: String?) = true
            override fun cancel() {}
        }
        set(owner, "socket", fake)
        set(owner, "socketReady", true)
        setState(owner, VanHermesSessionManager.State(vanSessionId = "original-session", sessionEpoch = 1, pathEpoch = 2))
    }
    private fun flush(owner: VanHermesSessionManager) {
        VanHermesSessionManager::class.java.getDeclaredMethod("flushOutbox").also { it.isAccessible = true }.invoke(owner)
    }
    @Test fun foreignAndLegacyProfileCannotBeSettledByCurrentProfilesAnswer() {
        for (record in listOf(entry(true), entry(true).copy(profileId = null))) {
            val fixture = fixture(); val adapter = EncryptedSessionOutboxStore(fixture.queue)
            val original = envelope(true).toString(); adapter.persist(record, original)
            reconcile(manager(adapter, record, JSONObject(original), profile = "other-profile"), "ORIGINAL_COMPLETED")
            assertEquals(original, adapter.restore().single().second)
        }
    }
    @Test fun actualSessionFlushDurablyClaimsBeforeSocketAndNeverRetriesAmbiguousAttempt() {
        val fixture = fixture(); val adapter = EncryptedSessionOutboxStore(fixture.queue)
        val fresh = entry(false).copy(neverDispatched = true)
        val original = envelope(false); adapter.persist(fresh, original.toString())
        val owner = manager(adapter, fresh, original)
        var sends = 0
        socket(owner) { sent ->
            assertEquals(false, adapter.restore().single().first.neverDispatched)
            val observed = JSONObject(sent)
            assertEquals("original-message", observed.getString("message_id"))
            assertEquals("original-outer-key", observed.getString("idempotency_key"))
            assertEquals("original-command", observed.getString("command_id"))
            sends++; false // Local delivery queue refusal is still ambiguous after claim.
        }
        flush(owner); flush(owner)
        assertEquals(1, sends)
        assertEquals(false, adapter.restore().single().first.neverDispatched)
        assertEquals("original-message", adapter.restore().single().first.messageId)
    }
    @Test fun failedDurableClaimPreventsAnySocketSend() {
        val fixture = fixture(); val adapter = EncryptedSessionOutboxStore(fixture.queue)
        val fresh = entry(false).copy(neverDispatched = true)
        val original = envelope(false); adapter.persist(fresh, original.toString())
        val owner = manager(adapter, fresh, original)
        var sends = 0; socket(owner) { sends++; true }
        fixture.store.failAt = fixture.store.commits + 1
        flush(owner)
        assertEquals(0, sends)
        assertTrue(runCatching { adapter.restore() }.isFailure)
    }
    @Test fun expiredAmbiguousOriginalIsHeldButProvenNeverSentUsesExistingExpiryPolicy() {
        for (neverSent in listOf(false, true)) {
            val fixture = fixture(); val adapter = EncryptedSessionOutboxStore(fixture.queue)
            val expired = entry(true).copy(neverDispatched = neverSent)
            val original = envelope(true); adapter.persist(expired, original.toString())
            val owner = manager(adapter, expired, original)
            var sends = 0; socket(owner) { sends++; true }
            flush(owner)
            assertEquals(0, sends)
            assertEquals(if (neverSent) 0 else 1, adapter.restore().size)
            if (!neverSent) assertEquals(original.toString(), adapter.restore().single().second)
        }
    }

    @Test fun explicitlyOptionalTransientLiveSendMarksAttemptInMemoryWithoutDurableClaim() {
        val fixture = fixture(); val adapter = EncryptedSessionOutboxStore(fixture.queue)
        val original = envelope(false)
        val owner = manager(adapter, entry(false), original)
        set(owner, "store", null as Any?)
        set(owner, "outbox", ArrayDeque<Any>())
        var sends = 0
        socket(owner) { sent ->
            val field = VanHermesSessionManager::class.java.getDeclaredField("transientEntries").also { it.isAccessible = true }
            @Suppress("UNCHECKED_CAST") val entries = field.get(owner) as Map<String, OutboxEntry>
            val messageId = JSONObject(sent).getString("message_id")
            assertEquals(false, entries.getValue(messageId).neverDispatched)
            sends++; true
        }
        val outcome = owner.submit("command.submit", original.getJSONObject("payload"), "A1")
        assertTrue(outcome is VanHermesSessionManager.SubmissionOutcome.Sent)
        assertEquals(1, sends)
        assertTrue(adapter.restore().isEmpty())
        assertFalse(owner.state.value.outboxIsDurable)
    }

    @Test fun producerProvenSessionOnlyOwnersRecoverSameEnvelopeWithoutClaimingAbsence() {
        for (kind in listOf("mission.message", "mission.cancel", "decision.answer")) {
            for (answer in listOf("UNKNOWN", "RESULT_PENDING")) {
                val fixture = fixture(); val adapter = EncryptedSessionOutboxStore(fixture.queue)
                val owner = manager(adapter, entry(false), envelope(false))
                set(owner, "outbox", ArrayDeque<Any>())
                socket(owner) { false } // Original producer persists its pre-send fact; reply/delivery is ambiguous.
                val payload = JSONObject().put("mission_id", "SOURCE-owned-mission").put("text", "SOURCE original note")
                    .put("decision_id", "SOURCE-owned-decision").put("approved", false)
                assertTrue(owner.submit(kind, payload, "A1") is VanHermesSessionManager.SubmissionOutcome.Queued)
                val (record, rawOriginal) = adapter.restore().single()
                assertEquals(true, record.sessionOnlyOrigin)
                assertEquals(false, record.neverDispatched)
                val original = JSONObject(rawOriginal)
                var sends = 0
                socket(owner) { raw ->
                    val sent = JSONObject(raw)
                    assertEquals(original.getString("message_id"), sent.getString("message_id"))
                    assertEquals(original.getString("van_session_id"), sent.getString("van_session_id"))
                    assertEquals(original.getString("idempotency_key"), sent.getString("idempotency_key"))
                    assertEquals(original.getString("payload_digest"), sent.getString("payload_digest"))
                    assertEquals(original.getJSONObject("payload").toString(), sent.getJSONObject("payload").toString())
                    assertEquals(original.getLong("expires_at_ms"), sent.getLong("expires_at_ms"))
                    assertEquals(false, adapter.restore().single().first.neverDispatched)
                    sends++; true
                }
                reconcile(owner, answer, record.commandId); flush(owner)
                assertEquals(1, sends)
            }
        }
    }
    @Test fun originIsNeverGuessedAndCommandSubmitUnknownNeverGetsTransportPermission() {
        for (origin in listOf<Boolean?>(null, false, true)) {
            val fixture = fixture(); val adapter = EncryptedSessionOutboxStore(fixture.queue)
            val original = envelope(false)
            val record = entry(false).copy(sessionOnlyOrigin = origin)
            adapter.persist(record, original.toString())
            val owner = manager(adapter, record, original)
            var sends = 0; socket(owner) { sends++; true }
            reconcile(owner, "UNKNOWN"); flush(owner)
            assertEquals(0, sends)
            assertEquals(original.toString(), adapter.restore().single().second)
        }
    }
    @Test fun sameOriginalHttpFallbackReusesFirstDurableEnvelopeAndDoesNotRefreshDeadline() {
        val fixture = fixture(); val adapter = EncryptedSessionOutboxStore(fixture.queue)
        val owner = manager(adapter, entry(false), envelope(false))
        val body = envelope(false).getJSONObject("payload")
        set(owner, "outbox", ArrayDeque<Any>())
        var sends = 0; socket(owner) { sends++; true }
        val first = owner.submit("command.submit", body, "A1", originalProfile = "SOURCE-profile", priorTransportAttempt = true)
        val record = adapter.restore().single()
        val second = owner.submit("command.submit", JSONObject(body.toString()), "A1", originalProfile = "SOURCE-profile", priorTransportAttempt = true)
        assertTrue(first is VanHermesSessionManager.SubmissionOutcome.Queued)
        assertEquals(first, second)
        assertEquals(record, adapter.restore().single())
        assertEquals(0, sends)
        assertEquals(false, record.first.sessionOnlyOrigin)
        assertEquals(false, record.first.neverDispatched)
        val changed = JSONObject(body.toString()).put("text", "changed intent")
        assertTrue(owner.submit("command.submit", changed, "A1", originalProfile = "SOURCE-profile", priorTransportAttempt = true) is VanHermesSessionManager.SubmissionOutcome.Refused)
        assertEquals(record, adapter.restore().single())
    }
    @Test fun safeOriginalTransportRecoveryPreservesExplicitReconfirmationAndRefusesCancellation() {
        val fixture = fixture(); val adapter = EncryptedSessionOutboxStore(fixture.queue)
        val original = envelope(false).put("kind", "mission.message")
        val now = System.currentTimeMillis()
        val record = entry(false).copy(createdAtMs = now - DurableOutbox.STALE_AFTER_MS - 1000,
            expiresAtMs = now + 600000, sessionOnlyOrigin = true)
        adapter.persist(record, original.toString())
        val owner = manager(adapter, record, original)
        var sends = 0; socket(owner) { sends++; true }
        reconcile(owner, "RESULT_PENDING"); flush(owner)
        assertEquals(0, sends)
        assertTrue(owner.pendingOwnerReconfirmations().single().recoveryOnly)
        assertFalse(owner.cancelReconfirmation(record.messageId))
        assertTrue(owner.reconfirmAndFlush(record.messageId))
        assertEquals(1, sends)
        assertEquals(record.expiresAtMs, adapter.restore().single().first.expiresAtMs)
        assertEquals(record.messageId, adapter.restore().single().first.messageId)
    }

    @Test fun malformedOrMissingOriginalReferenceNeverFallsBackToIdOnlySettlement() {
        for (answer in listOf("ADMITTED", "RUNNING", "ORIGINAL_COMPLETED")) {
            val fixture = fixture(); val adapter = EncryptedSessionOutboxStore(fixture.queue)
            val record = entry(false)
            val original = envelope(false)
            original.getJSONObject("payload").remove("signature")
            original.put("payload_digest", SessionEnvelope.payloadDigest(original.getJSONObject("payload")))
            adapter.persist(record, original.toString())
            val bytes = fixture.store.memory["cmd_${record.messageId}"]
            val owner = manager(adapter, record, original)
            assertNull(OriginalCommandReference.fromStored(record, original, "SOURCE-profile", "SOURCE-device"))
            reconcile(owner, answer)
            assertEquals(original.toString(), adapter.restore().single().second)
            assertEquals(bytes, fixture.store.memory["cmd_${record.messageId}"])
        }
    }
    @Test fun verifiedOriginalAcceptedHandoffPreservesRunningOutcomeAndNativeIdsWithoutDeclaringSuccess() {
        val fixture = fixture(); val adapter = EncryptedSessionOutboxStore(fixture.queue)
        val record = entry(false); val original = envelope(false)
        adapter.persist(record, original.toString())
        val owner = manager(adapter, record, original)
        val observed = mutableListOf<JSONObject>()
        set(owner, "onRecoveredOriginal", { result: JSONObject -> observed += result })
        val receipt = verifiedReceipt(record, original, accepted = true)
        val read = JSONObject().put("command_states", JSONObject().put(record.commandId, "ORIGINAL_COMPLETED"))
            .put("original_command_results", JSONObject().put(record.commandId, receipt))
        VanHermesSessionManager::class.java.getDeclaredMethod("adoptCursor", JSONObject::class.java)
            .also { it.isAccessible = true }.invoke(owner, read)
        assertTrue(adapter.restore().isEmpty())
        assertEquals("accepted", observed.single().getJSONObject("result").getString("status"))
        assertEquals("SOURCE-original-run", observed.single().getJSONObject("result").getString("hermes_run_id"))
        assertEquals("RUNNING", observed.single().getJSONObject("owner_result").getString("mission_state"))
    }
    @Test fun missingOrWrongReferenceReceiptKeepsOriginalEvenWhenLookupStateSaysCompleted() {
        for (wrong in listOf(false, true)) {
            val fixture = fixture(); val adapter = EncryptedSessionOutboxStore(fixture.queue)
            val record = entry(false); val original = envelope(false)
            adapter.persist(record, original.toString())
            val owner = manager(adapter, record, original)
            val receipt = verifiedReceipt(record, original, accepted = true)
            receipt.getJSONObject("reference").put("message_id", "changed-original")
            val read = JSONObject().put("command_states", JSONObject().put(record.commandId, "ORIGINAL_COMPLETED"))
            if (wrong) read.put("original_command_results", JSONObject().put(record.commandId, receipt))
            VanHermesSessionManager::class.java.getDeclaredMethod("adoptCursor", JSONObject::class.java)
                .also { it.isAccessible = true }.invoke(owner, read)
            assertEquals(original.toString(), adapter.restore().single().second)
        }
    }

    @Test fun directHttpReservationPersistsExactOriginalAsAmbiguousBeforeTransportAndDeduplicates() {
        val fixture = fixture(); val adapter = EncryptedSessionOutboxStore(fixture.queue)
        val original = envelope(false); val record = entry(false); val owner = manager(adapter, record, original)
        val body = original.getJSONObject("payload")
        val first = owner.submit("command.submit", body, "A1", originalProfile = "SOURCE-profile", priorTransportAttempt = true, httpPreparation = true)
        assertTrue(first is VanHermesSessionManager.SubmissionOutcome.Queued)
        val stored = adapter.restore().single()
        assertEquals(false, stored.first.neverDispatched); assertEquals(false, stored.first.sessionOnlyOrigin)
        assertEquals(true, stored.first.httpPrepared)
        assertEquals(0, stored.first.attemptCount) // Preparation is not an observed network attempt.
        assertTrue(owner.queuedForOwner().any { it.second.contains("prepared") })
        assertEquals(body.toString(), JSONObject(stored.second).getJSONObject("payload").toString())
        owner.submit("command.submit", body, "A1", originalProfile = "SOURCE-profile", priorTransportAttempt = true, httpPreparation = true)
        assertEquals(stored, adapter.restore().single())
        val restarted = manager(EncryptedSessionOutboxStore(fixture.queue), stored.first, JSONObject(stored.second))
        reconcile(restarted, "RESULT_PENDING")
        assertEquals(stored, adapter.restore().single())
    }
    @Test fun directHttpReservationCannotClaimOwnershipWhenCanonicalStoreCommitFails() {
        val fixture = fixture(); val adapter = EncryptedSessionOutboxStore(fixture.queue)
        val original = envelope(false); val owner = manager(adapter, entry(false), original)
        fixture.store.failAt = fixture.store.commits + 1
        var refused = false
        try { owner.submit("command.submit", original.getJSONObject("payload"), "A1", originalProfile = "SOURCE-profile", priorTransportAttempt = true, httpPreparation = true) }
        catch (_: Exception) { refused = true }
        assertTrue(refused)
    }

}
