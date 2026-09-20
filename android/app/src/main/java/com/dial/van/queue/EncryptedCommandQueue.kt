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
class EncryptedCommandQueue(context: Context) : OutboxRecordStore {

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
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

    fun enqueue(request: QueueEnqueueRequest): QueuedCommand {
        val now = System.currentTimeMillis()
        val idempotencyKey = request.idempotencyKey ?: UUID.randomUUID().toString()
        val existing = findByIdempotencyKey(idempotencyKey)
        if (existing != null && existing.isReplayEligible(now)) {
            return existing
        }

        val resolvedActionClass = request.actionClass ?: when (request.sensitivity) {
            CommandSensitivity.NORMAL -> ActionClass.A1
            CommandSensitivity.ELEVATED -> ActionClass.A3
            CommandSensitivity.DESTRUCTIVE -> ActionClass.A4
            CommandSensitivity.SECRET -> ActionClass.A5
        }
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
        )
        persist(command)
        return command
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
    override fun upsert(command: QueuedCommand) {
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
    override fun recordsOfKind(kind: String): List<QueuedCommand> {
        val now = System.currentTimeMillis()
        return listIds()
            .mapNotNull { load(it) }
            .filter { it.kind == kind && !it.isExpired(now) }
            .sortedBy { it.createdAtEpochMs }
    }

    fun peekReady(nowMs: Long = System.currentTimeMillis()): List<QueuedCommand> {
        purgeExpired(nowMs)
        return listIds()
            .mapNotNull { load(it) }
            .filter { it.isReplayEligible(nowMs) }
            .sortedBy { it.createdAtEpochMs }
    }

    fun markAttempt(id: String, error: String? = null): QueuedCommand? {
        val current = load(id) ?: return null
        val updated = current.copy(attemptCount = current.attemptCount + 1, lastError = error)
        persist(updated)
        return updated
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
    override fun remove(id: String) {
        val ids = listIds().filterNot { it == id }
        indexPrefs.edit()
            .remove(blobKey(id))
            .putString(KEY_INDEX, ids.joinToString(","))
            .commit()
    }

    fun findByIdempotencyKey(key: String): QueuedCommand? =
        listIds().mapNotNull { load(it) }.firstOrNull { it.idempotencyKey == key }

    /**
     * Returns commands safe to dispatch under the exact Rev 3.1 class/replay contract.
     * A5 and stale/no-replay commands are removed rather than silently retained.
     */
    fun drainExecutable(nowMs: Long = System.currentTimeMillis()): List<QueuedCommand> {
        val executable = mutableListOf<QueuedCommand>()
        for (id in listIds()) {
            val cmd = load(id) ?: continue
            if (!cmd.isReplayEligible(nowMs)) {
                remove(cmd.id)
                continue
            }
            executable.add(cmd)
        }
        return executable.sortedBy { it.createdAtEpochMs }
    }

    fun purgeExpired(nowMs: Long = System.currentTimeMillis()) {
        listIds().forEach { id ->
            val cmd = load(id) ?: return@forEach
            if (cmd.isExpired(nowMs)) remove(id)
        }
    }

    fun size(): Int = listIds().size

    /**
     * Discard everything waiting.
     *
     * The destructive half of `RestoreAction.CLEAR_QUEUE` (P3-AND-005), which until now had
     * no implementation behind it. Offered to the owner only when the queue has stopped
     * draining, and the button says what it does: these commands were never sent and will
     * not be.
     */
    fun clear() {
        for (id in listIds()) remove(id)
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
    private fun persist(command: QueuedCommand) {
        val plaintext = json.encodeToString(command)
        val encrypted = encrypt(plaintext.toByteArray(Charsets.UTF_8))
        val encoded = Base64.encodeToString(encrypted, Base64.NO_WRAP)
        val ids = (listIds() + command.id).distinct()
        indexPrefs.edit()
            .putString(blobKey(command.id), encoded)
            .putString(KEY_INDEX, ids.joinToString(","))
            .commit()
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
