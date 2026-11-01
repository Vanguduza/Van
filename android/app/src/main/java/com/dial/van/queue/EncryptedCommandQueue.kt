package com.dial.van.queue

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.security.KeyStore
import java.security.MessageDigest
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Encrypted offline command queue using Android Keystore + AES-GCM payload wrapping.
 * Idempotency keys survive retries; expired sensitive commands are never executed.
 *
 * Rev 3.1 invariant: exact A1-A5 policy and replay semantics travel with each queued command.
 * A5 never executes. NO_STALE_REPLAY commands are never retried after a dispatch attempt.
 */
/**
 * **Every mutating call on this class blocks until the bytes are on disk.**
 *
 * `persist` and `remove` use `commit()` rather than `apply()`, because the session outbox
 * tells the owner their command is saved and that sentence has to be true before it is
 * said. The cost is that a write is AES-GCM plus a synchronous file write on whatever
 * thread called it — so no caller may be on the Android main thread.
 *
 * That is not hypothetical. When this changed from `apply()` to `commit()` for the
 * outbox's sake, two callers that had always been fine — `ShareIntakeActivity.onCreate`
 * and `VanNotificationListenerService.onNotificationPosted`, both main-thread Android
 * entry points — silently became main-thread disk writers, with a burst of notifications
 * producing one encrypted write per notification on the thread that draws. Both now
 * dispatch to `Dispatchers.IO`, and
 * `tests/contracts/test_encrypted_queue_writes_are_off_the_main_thread.py` refuses a call
 * site that is not.
 */
class EncryptedCommandQueue(
    context: Context,
    private val currentOwner: () -> QueueOwnerScope? = { null },
) : OutboxRecordStore {

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val restoreJson = Json { ignoreUnknownKeys = false; encodeDefaults = true }
    private val appContext = context.applicationContext

    private val masterKey = MasterKey.Builder(appContext)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .build()

    private val indexPrefs = EncryptedSharedPreferences.create(
        appContext,
        PREFS_INDEX,
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    private val keystoreAlias = KEYSTORE_ALIAS

    init {
        ensureKeystoreKey()
    }

    fun enqueue(request: QueueEnqueueRequest): QueuedCommand = synchronized(storeLock) {
        requireHealthy()
        val now = System.currentTimeMillis()
        val idempotencyKey = request.idempotencyKey ?: UUID.randomUUID().toString()
        val existing = findByIdempotencyKey(idempotencyKey)
        if (existing != null) {
            check(existing.kind == request.kind.name && existing.payloadJson == request.payloadJson &&
                existing.sensitivity == request.sensitivity.name && existing.replayPolicy == request.replayPolicy.name) {
                "queue_original_intent_changed"
            }
            // Existing identity/expiry survives even after a lost reply or deadline.
            return@synchronized existing
        }

        val resolvedActionClass = request.actionClass ?: when (request.sensitivity) {
            CommandSensitivity.NORMAL -> ActionClass.A1
            CommandSensitivity.ELEVATED -> ActionClass.A3
            CommandSensitivity.DESTRUCTIVE -> ActionClass.A4
            CommandSensitivity.SECRET -> ActionClass.A5
        }
        val owner = currentOwner()?.takeIf { it.current(now) }
        val generic = request.kind != CommandKind.SESSION_ENVELOPE && request.kind != CommandKind.CONTEXT_INGEST
        val command = QueuedCommand(
            id = UUID.randomUUID().toString(),
            idempotencyKey = idempotencyKey,
            kind = request.kind.name,
            payloadJson = request.payloadJson,
            sensitivity = request.sensitivity.name,
            actionClass = resolvedActionClass.name,
            replayPolicy = request.replayPolicy.name,
            createdAtEpochMs = now,
            expiresAtEpochMs = now + request.ttlMs,
            genericOwner = if (generic) owner else null,
            genericDeliveryState = if (generic && owner != null) "UNSENT" else null,
        )
        persist(command)
        return@synchronized command
    }

    /**
     * §20.14 — write or replace a record the caller has built, keyed on its own id.
     *
     * Distinct from [enqueue], which mints a fresh id and is therefore an insert. The
     * session outbox needs replacement: an attempt count or a reconfirmation is the same
     * command with one more fact known about it, and a remove-then-enqueue pair would put
     * a process-death window between the two halves of one update — losing the owner's
     * command entirely, which is worse than the metadata loss it was introduced to fix.
     */
    override fun upsert(command: QueuedCommand) = synchronized(storeLock) {
        requireHealthy()
        val existing = load(command.id)
        if (existing != null) {
            check(existing.kind == command.kind && existing.idempotencyKey == command.idempotencyKey) { "queue_record_owner_changed" }
            if (isGeneric(existing)) check(existing == command) { "queue_generic_owner_update_required" }
        } else if (isGeneric(command)) {
            check(command.genericOwner == null && command.genericDeliveryState == null && command.genericPreparedBody == null && command.genericClaimId == null && command.genericClaimOwner == null) {
                "queue_unsent_producer_required"
            }
        }
        persist(command)
    }

    /**
     * Every unexpired record of one kind, oldest first.
     *
     * Deliberately not [peekReady]. That reader filters on `isReplayEligible`, which
     * drops a `NO_STALE_REPLAY` command once `attemptCount > 0` — and that is precisely
     * the §20.14 class a restore exists to recover: a command that was tried, was not
     * acknowledged, and must be put back to the owner rather than sent on their behalf.
     * Reading the queue through `peekReady` here would have made a restart *silently
     * discard* the commands the owner most needed to be asked about, with every test of
     * the mapping still green because the mapping was never the broken half.
     *
     * Expiry is still honoured: a window that closed while the process was dead has
     * closed, and §20.14 says that command does not run.
     */
    override fun recordsOfKind(kind: String): List<QueuedCommand> = synchronized(storeLock) {
        requireHealthy()
        val now = System.currentTimeMillis()
        return@synchronized listIds()
            .mapNotNull { load(it) }
            .filter { it.kind == kind && !it.isExpired(now) }
            .sortedBy { it.createdAtEpochMs }
    }

    override fun recoveryRecordsOfKind(kind: String): List<QueuedCommand> = synchronized(storeLock) {
        requireHealthy()
        listIds().mapNotNull { load(it) }.filter { it.kind == kind }.sortedBy { it.createdAtEpochMs }
    }

    fun peekReady(nowMs: Long = System.currentTimeMillis()): List<QueuedCommand> = synchronized(storeLock) {
        requireHealthy()
        purgeExpired(nowMs)
        return@synchronized listIds()
            .mapNotNull { load(it) }
            .filter { it.isReplayEligible(nowMs) }
            .sortedBy { it.createdAtEpochMs }
    }

    fun markAttempt(id: String, error: String? = null): QueuedCommand? = synchronized(storeLock) {
        requireHealthy()
        val current = load(id) ?: return@synchronized null
        val updated = current.copy(attemptCount = current.attemptCount + 1, lastError = error)
        persist(updated)
        return@synchronized updated
    }

    /**
     * Forget one command. Atomic: the blob and the index move together.
     *
     * This was two editors and two `apply()` calls. Either order has a window a process
     * death fits through — blob gone and still indexed leaves a row that loads as null,
     * index gone and blob still present leaks a record nothing can reach — and `apply()`
     * makes it worse by writing on a background thread, so a kill can lose a change the
     * caller was already told had happened.
     */
    override fun remove(id: String) = synchronized(storeLock) {
        requireHealthy()
        val ids = listIds().filterNot { it == id }
        commit(indexPrefs.edit()
            .remove(blobKey(id))
            .putString(KEY_INDEX, ids.joinToString(",")))
    }

    fun findByIdempotencyKey(key: String): QueuedCommand? = synchronized(storeLock) {
        requireHealthy()
        listIds().mapNotNull { load(it) }.firstOrNull { it.idempotencyKey == key }
    }

    /**
     * Returns commands safe to dispatch under the exact Rev 3.1 class/replay contract.
     * A5 and stale/no-replay commands are removed rather than silently retained.
     */
    fun drainExecutable(nowMs: Long = System.currentTimeMillis()): List<QueuedCommand> = synchronized(storeLock) {
        requireHealthy()
        val executable = mutableListOf<QueuedCommand>()
        val owner = currentOwner()?.takeIf { it.current(nowMs) }
        for (id in listIds()) {
            val cmd = load(id) ?: continue
            if (!isGeneric(cmd)) {
                // Foreign owners decide expiry/reconfirmation themselves. In
                // particular, generic cleanup must not erase session recovery.
                executable.add(cmd)
                continue
            }
            if (cmd.genericDeliveryState != "UNSENT" || owner == null || cmd.genericOwner?.samePrincipal(owner) != true) continue
            if (!cmd.isReplayEligible(nowMs)) {
                remove(cmd.id)
                continue
            }
            executable.add(cmd)
        }
        executable.sortedBy { it.createdAtEpochMs }
    }

    /** The captured-context owner finishes only its exact original row. */
    fun finishCapturedContext(original: QueuedCommand, expiredOnly: Boolean = false): Boolean = synchronized(storeLock) {
        requireHealthy()
        val current = load(original.id) ?: return@synchronized false
        if (current.kind != CommandKind.CONTEXT_INGEST.name || commandRevision(current) != commandRevision(original) ||
            (expiredOnly && !current.isExpired())) return@synchronized false
        remove(current.id)
        true
    }

    fun purgeExpired(nowMs: Long = System.currentTimeMillis()) = synchronized(storeLock) {
        requireHealthy()
        val owner = currentOwner()?.takeIf { it.current(nowMs) } ?: return@synchronized
        listIds().forEach { id ->
            val cmd = load(id) ?: return@forEach
            if (isGeneric(cmd) && cmd.genericOwner?.samePrincipal(owner) == true && cmd.genericDeliveryState == "UNSENT" && cmd.isExpired(nowMs)) remove(id)
        }
    }

    fun size(): Int = synchronized(storeLock) { requireHealthy(); listIds().size }

    /**
     * Discard everything waiting.
     *
     * This full-store erasure is reserved for the existing explicit owning privacy
     * policy. Generic stalled-queue restoration selects only proven UNSENT work and
     * uses discardReviewed; presence in a shared queue does not establish absence of
     * delivery or permission to erase another owner's recovery.
     */
    fun clear() {
        synchronized(storeLock) {
            // Full erasure remains for an explicit owning privacy policy;
            // generic Settings restoration uses its exact selected operation.
            requireHealthy()
            val editor = indexPrefs.edit()
            for (id in listIds()) editor.remove(blobKey(id))
            indexPrefs.all.keys.filter { it.startsWith("restore_operation_") }.forEach { editor.remove(it) }
            try {
                if (!editor.putString(KEY_INDEX, "").commit()) {
                    storeUncertain = true
                    error("queue_storage_outcome_unknown_restart_required")
                }
            } catch (failure: Throwable) {
                storeUncertain = true
                throw failure
            }
        }
    }

    /**
     * Write or replace one command. Atomic, and `commit()` rather than `apply()`.
     *
     * One editor because the blob and the index are one fact: a record that is in the
     * index and not on disk is a row that loads as null, and one on disk and not in the
     * index is unreachable. SharedPreferences applies an editor's changes together and
     * writes the file by rename, so a single edit is the atomicity this needs.
     *
     * `commit()` because `apply()` returns before the disk write. The caller of this is
     * told the owner's command is queued; a kill a moment later must not be able to make
     * that a lie. The cost is a synchronous write on a path that already does AES-GCM.
     */
    /** Current queue facts, separating generic work from other owners' durable records. */
    fun restoreInventory(): QueueRestoreInventory = synchronized(storeLock) {
        requireHealthy()
        val now = System.currentTimeMillis()
        val owner = currentOwner()?.takeIf { it.current(now) }
        var eligible = 0; var held = 0; var foreign = 0; var unreadable = 0
        for (id in listIds()) {
            val cmd = load(id)
            when {
                cmd == null -> unreadable++
                !isGeneric(cmd) -> foreign++
                owner != null && discardable(cmd, owner) -> eligible++
                else -> held++
            }
        }
        QueueRestoreInventory(eligible, held, foreign, unreadable)
    }

    /** An inert exact selection. It neither claims delivery nor writes an operation. */
    fun reviewDiscard(): QueueRestoreRequest = synchronized(storeLock) {
        requireHealthy()
        val now = System.currentTimeMillis()
        val owner = currentOwner()?.takeIf { it.current(now) } ?: error("queue_current_owner_unavailable")
        val items = listIds().mapNotNull { load(it) }.filter { discardable(it, owner) }
            .map { QueueRestoreItem(it.id, commandRevision(it)) }.sortedBy { it.id }.take(1024)
        check(items.isNotEmpty()) { "queue_no_proven_unsent_selection" }
        check(items.size <= 1024)
        val body = QueueRestoreRequest("queue-restore-"+UUID.randomUUID().toString().replace("-", ""),
            owner, items, selectionRevision(items), now, minOf(now+600000, owner.observedUntilMs))
        body.copy(requestToken = sealRestore(body))
    }

    private fun discardable(command: QueuedCommand, owner: QueueOwnerScope): Boolean =
        isGeneric(command) && command.genericDeliveryState == "UNSENT" && command.attemptCount == 0 &&
            command.genericClaimId == null && command.genericPreparedBody == null &&
            command.genericOwner?.samePrincipal(owner) == true

    private fun commandRevision(command: QueuedCommand): String = digest(json.encodeToString(command))
    private fun selectionRevision(items: List<QueueRestoreItem>): String = digest(restoreJson.encodeToString(items))
    private fun digest(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    private fun sealRestore(value: QueueRestoreRequest): String = Base64.encodeToString(
        encrypt(restoreJson.encodeToString(value.copy(requestToken = "")).toByteArray(Charsets.UTF_8)), Base64.NO_WRAP)

    private fun validateRestore(request: QueueRestoreRequest) {
        check(Regex("queue-restore-[a-f0-9]{32}").matches(request.operationId)) { "queue_restore_invalid" }
        check(request.items.isNotEmpty() && request.items.size <= 1024 && request.items.map { it.id }.distinct().size == request.items.size)
        check(request.items == request.items.sortedBy { it.id } && request.revision == selectionRevision(request.items))
        check(request.issuedAtMs > 0 && request.deadlineMs > request.issuedAtMs && request.deadlineMs <= request.issuedAtMs+600000)
        val opened = restoreJson.decodeFromString<QueueRestoreRequest>(
            String(decrypt(Base64.decode(request.requestToken, Base64.NO_WRAP)), Charsets.UTF_8))
        check(opened == request.copy(requestToken = "")) { "queue_restore_original_changed" }
    }

    private fun operationKey(operationId: String) = "restore_operation_$operationId"
    private fun restoreValue(record: QueueRestoreRecord): String = Base64.encodeToString(
        encrypt(restoreJson.encodeToString(record).toByteArray(Charsets.UTF_8)), Base64.NO_WRAP)
    private fun originalRestore(operationId: String): QueueRestoreRecord? {
        val raw = indexPrefs.getString(operationKey(operationId), null) ?: return null
        val record = restoreJson.decodeFromString<QueueRestoreRecord>(String(decrypt(Base64.decode(raw, Base64.NO_WRAP)), Charsets.UTF_8))
        validateRestore(record.request)
        check(record.request.operationId == operationId)
        record.result?.let { result ->
            check(result.operationId == operationId && result.owner == record.request.owner &&
                result.revision == record.request.revision && result.selectedIds == record.request.items.map { it.id } &&
                result.requestDeadlineMs == record.request.deadlineMs && !result.externalCancellationClaimed)
            check(result.state in setOf("APPLIED", "REFUSED") && result.completedAtMs > 0)
            check(if (result.state == "APPLIED") result.reason == null && result.removedIds == result.selectedIds
                else result.reason != null && result.removedIds.isEmpty())
        }
        return record
    }

    /** Recover original pending intents from this canonical protected journal. */
    fun pendingRestores(): List<QueueRestoreRequest> = synchronized(storeLock) {
        requireHealthy()
        val owner = currentOwner()?.takeIf { it.current(System.currentTimeMillis()) } ?: error("queue_current_owner_unavailable")
        indexPrefs.all.keys.filter { it.startsWith("restore_operation_") }.mapNotNull { key ->
            val original = originalRestore(key.removePrefix("restore_operation_")) ?: return@mapNotNull null
            original.request.takeIf { original.result == null && it.owner.samePrincipal(owner) }
        }.sortedBy { it.issuedAtMs }
    }

    fun restoreResult(operationId: String): QueueRestoreResult? = synchronized(storeLock) {
        requireHealthy()
        val owner = currentOwner()?.takeIf { it.current(System.currentTimeMillis()) } ?: error("queue_current_owner_unavailable")
        val record = originalRestore(operationId) ?: return@synchronized null
        check(record.request.owner.samePrincipal(owner)) { "queue_restore_wrong_owner" }
        record.result
    }

    /**
     * The original intent is durable before local deletion. The selected removals,
     * updated index and terminal original receipt share the one canonical editor.
     * A false commit is UNKNOWN, never an optimistic in-memory success.
     */
    fun discardReviewed(request: QueueRestoreRequest, cancelled: () -> Boolean = { Thread.currentThread().isInterrupted }): QueueRestoreResult = synchronized(storeLock) {
        requireHealthy()
        validateRestore(request)
        val now = System.currentTimeMillis()
        val owner = currentOwner()?.takeIf { it.current(now) } ?: error("queue_current_owner_unavailable")
        check(request.owner.samePrincipal(owner)) { "queue_restore_wrong_owner" }
        val old = originalRestore(request.operationId)
        if (old != null) {
            check(old.request == request) { "queue_restore_original_changed" }
            old.result?.let { return@synchronized it }
        } else {
            commit(indexPrefs.edit().putString(operationKey(request.operationId), restoreValue(QueueRestoreRecord(request))))
        }
        // Currentness is independent of the historical target's owner evidence.
        val fresh = currentOwner()
        val reason = when {
            cancelled() -> "queue_restore_cancelled"
            fresh == null || !fresh.current(System.currentTimeMillis()) || !request.owner.sameActor(fresh) -> "queue_restore_owner_changed"
            System.currentTimeMillis() >= request.deadlineMs || System.currentTimeMillis()+30000 < request.issuedAtMs -> "queue_restore_review_expired"
            request.items.any { selected -> load(selected.id)?.let { !discardable(it, fresh) || commandRevision(it) != selected.revision } != false } -> "queue_restore_selection_changed"
            else -> null
        }
        val selected = request.items.map { it.id }
        val result = QueueRestoreResult(request.operationId, request.owner, request.revision,
            if (reason == null) "APPLIED" else "REFUSED", selected, if (reason == null) selected else emptyList(),
            reason, System.currentTimeMillis(), request.deadlineMs)
        val editor = indexPrefs.edit()
        if (reason == null) {
            val kept = listIds().filterNot { it in selected }
            selected.forEach { editor.remove(blobKey(it)) }
            editor.putString(KEY_INDEX, kept.joinToString(","))
        }
        commit(editor.putString(operationKey(request.operationId), restoreValue(QueueRestoreRecord(request, result))))
        result
    }

    /** Claim before preparing/sending. A competing reviewed discard can no longer erase it. */
    fun claimGeneric(id: String, expectedRevision: String): QueuedCommand? = synchronized(storeLock) {
        requireHealthy()
        val now = System.currentTimeMillis()
        val owner = currentOwner()?.takeIf { it.current(now) } ?: return@synchronized null
        val command = load(id) ?: return@synchronized null
        if (!discardable(command, owner) || !command.isReplayEligible(now) || commandRevision(command) != expectedRevision) return@synchronized null
        val claimed = command.copy(genericDeliveryState = "CLAIMED", genericClaimId = UUID.randomUUID().toString(), genericClaimOwner = owner)
        persist(claimed)
        claimed
    }

    fun genericRevision(command: QueuedCommand): String = commandRevision(command)

    fun heldGeneric(): List<QueuedCommand> = synchronized(storeLock) {
        requireHealthy()
        val owner = currentOwner()?.takeIf { it.current(System.currentTimeMillis()) } ?: return@synchronized emptyList()
        listIds().mapNotNull { load(it) }.filter { isGeneric(it) && it.genericOwner?.samePrincipal(owner) == true && it.genericDeliveryState != "UNSENT" }
    }

    fun recordGenericPrepared(id: String, claimId: String, bodyText: String): QueuedCommand = synchronized(storeLock) {
        requireHealthy()
        val owner = currentOwner()?.takeIf { it.current(System.currentTimeMillis()) } ?: error("queue_current_owner_unavailable")
        val command = load(id) ?: error("queue_claim_missing")
        check(command.genericOwner?.samePrincipal(owner) == true && command.genericDeliveryState == "CLAIMED" && command.genericClaimId == claimId)
        check(command.genericClaimOwner?.sameActor(owner) == true && command.genericClaimOwner.current(System.currentTimeMillis()) && command.isReplayEligible()) {
            "queue_original_claim_authority_not_current"
        }
        val body = org.json.JSONObject(bodyText)
        check(body.getString("idempotency_key") == command.idempotencyKey && body.getString("device_id") == owner.deviceId && body.getString("command_id").isNotBlank())
        check(command.genericPreparedBody == null || command.genericPreparedBody == bodyText) { "queue_original_intent_changed" }
        val prepared = command.copy(genericPreparedBody = bodyText)
        persist(prepared)
        prepared
    }

    fun recordGenericUnknown(id: String, claimId: String, error: String?): QueuedCommand? = synchronized(storeLock) {
        requireHealthy()
        val command = load(id) ?: return@synchronized null
        check(command.genericClaimId == claimId && command.genericDeliveryState in setOf("CLAIMED", "UNKNOWN"))
        val held = command.copy(genericDeliveryState = "UNKNOWN", lastError = error, attemptCount = command.attemptCount+1)
        persist(held)
        held
    }

    fun recordGenericReceipt(id: String, claimId: String, receipt: String): QueuedCommand? = synchronized(storeLock) {
        requireHealthy()
        val command = load(id) ?: return@synchronized null
        check(command.genericClaimId == claimId && command.genericDeliveryState in setOf("CLAIMED", "UNKNOWN", "SUBMITTED"))
        val owner = currentOwner()?.takeIf { it.current(System.currentTimeMillis()) } ?: error("queue_current_owner_unavailable")
        check(command.genericOwner?.samePrincipal(owner) == true) { "queue_original_owner_changed" }
        val original = org.json.JSONObject(command.genericPreparedBody ?: error("queue_original_command_unavailable"))
        val observed = org.json.JSONObject(receipt)
        check(observed.getString("command_id") == original.getString("command_id")) { "queue_original_result_mismatch" }
        command.genericReceiptJson?.let { originalReceipt ->
            val originalResult = org.json.JSONObject(originalReceipt)
            for (field in listOf("mission_id", "correlation_id")) {
                val expected = originalResult.optString(field).takeUnless { it.isBlank() || it == "null" }
                val received = observed.optString(field).takeUnless { it.isBlank() || it == "null" }
                check(expected == null || received == null || expected == received) { "queue_original_result_mismatch" }
            }
        }
        val result = command.copy(genericDeliveryState = "SUBMITTED", genericReceiptJson = command.genericReceiptJson ?: receipt)
        if (result != command) persist(result)
        result
    }

    private fun requireHealthy() {
        check(!storeUncertain) { "queue_storage_outcome_unknown_restart_required" }
    }

    private fun commit(editor: android.content.SharedPreferences.Editor) {
        try {
            if (!editor.commit()) {
                storeUncertain = true
                error("queue_storage_outcome_unknown_restart_required")
            }
        } catch (failure: Throwable) {
            storeUncertain = true
            throw failure
        }
    }

    private fun isGeneric(command: QueuedCommand): Boolean =
        command.kindEnum() != CommandKind.SESSION_ENVELOPE && command.kindEnum() != CommandKind.CONTEXT_INGEST

    private fun persist(command: QueuedCommand) {
        val plaintext = json.encodeToString(command)
        val encrypted = encrypt(plaintext.toByteArray(Charsets.UTF_8))
        val encoded = Base64.encodeToString(encrypted, Base64.NO_WRAP)
        val ids = (listIds() + command.id).distinct()
        commit(indexPrefs.edit()
            .putString(blobKey(command.id), encoded)
            .putString(KEY_INDEX, ids.joinToString(",")))
    }

    private fun load(id: String): QueuedCommand? {
        val encoded = indexPrefs.getString(blobKey(id), null) ?: return null
        return runCatching {
            val decrypted = decrypt(Base64.decode(encoded, Base64.NO_WRAP))
            json.decodeFromString<QueuedCommand>(String(decrypted, Charsets.UTF_8))
        }.getOrNull()
    }

    private fun listIds(): List<String> {
        val raw = indexPrefs.getString(KEY_INDEX, "") ?: ""
        if (raw.isEmpty()) return emptyList()
        return raw.split(",").filter { it.isNotBlank() }
    }

    private fun blobKey(id: String) = "cmd_$id"

    private fun ensureKeystoreKey() {
        val ks = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        if (!ks.containsAlias(keystoreAlias)) {
            val generator = KeyGenerator.getInstance(KEY_ALGORITHM, ANDROID_KEYSTORE)
            generator.init(
                KeyGenParameterSpec.Builder(
                    keystoreAlias,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                )
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setRandomizedEncryptionRequired(true)
                    .build(),
            )
            generator.generateKey()
        }
    }

    private fun secretKey(): SecretKey {
        val ks = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        return (ks.getEntry(keystoreAlias, null) as KeyStore.SecretKeyEntry).secretKey
    }

    private fun encrypt(plain: ByteArray): ByteArray {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val iv = cipher.iv
        val ciphertext = cipher.doFinal(plain)
        return iv + ciphertext
    }

    private fun decrypt(blob: ByteArray): ByteArray {
        val iv = blob.copyOfRange(0, GCM_IV_LENGTH)
        val ciphertext = blob.copyOfRange(GCM_IV_LENGTH, blob.size)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(GCM_TAG_BITS, iv))
        return cipher.doFinal(ciphertext)
    }

    companion object {
        // All app components use this one canonical preferences owner in the
        // default app process. Multiple queue objects share the same writer.
        private val storeLock = Any()
        private var storeUncertain = false
        /** Kept as the name every caller already uses; the value lives in the pure model file. */
        const val DEFAULT_TTL_MS = COMMAND_QUEUE_DEFAULT_TTL_MS
        private const val PREFS_INDEX = "van_command_queue_index"
        private const val KEY_INDEX = "index"
        private const val KEYSTORE_ALIAS = "van_queue_aes"
        private const val ANDROID_KEYSTORE = "AndroidKeyStore"
        private const val KEY_ALGORITHM = "AES"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val GCM_IV_LENGTH = 12
        private const val GCM_TAG_BITS = 128
    }
}
