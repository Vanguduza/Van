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
class EncryptedCommandQueue(context: Context) {

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

    fun remove(id: String) {
        indexPrefs.edit().remove(blobKey(id)).apply()
        reindex(listIds().filterNot { it == id })
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

    private fun persist(command: QueuedCommand) {
        val plaintext = json.encodeToString(command)
        val encrypted = encrypt(plaintext.toByteArray(Charsets.UTF_8))
        val encoded = Base64.encodeToString(encrypted, Base64.NO_WRAP)
        indexPrefs.edit().putString(blobKey(command.id), encoded).apply()
        val ids = listIds().toMutableSet()
        ids.add(command.id)
        reindex(ids.toList())
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

    private fun reindex(ids: List<String>) {
        indexPrefs.edit().putString(KEY_INDEX, ids.joinToString(",")).apply()
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
        const val DEFAULT_TTL_MS = 24L * 60 * 60 * 1000 // 24h
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
