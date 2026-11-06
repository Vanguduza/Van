package com.dial.van.voice

import android.content.Context
import android.os.Looper
import android.util.Base64
import com.dial.van.security.OwnerApprovalKeyManager
import java.security.KeyStore
import java.security.PrivateKey
import java.security.PublicKey
import java.security.SecureRandom
import java.security.Signature
import java.util.UUID
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject

/** A dedicated local, one-use biometric ceremony; it does not grant gateway action authority. */
data class SpeakerEnrollmentConsent(val id: String, val challenge: String, val signature: Signature, val expiresAtMs: Long)

class SpeakerEnrollmentManager(
    context: Context,
    private val audioArbiter: VoiceAudioArbiter,
    private val scope: CoroutineScope,
    private val bindingProvider: suspend () -> SpeakerProfileBinding?,
    private val localBindingProvider: () -> SpeakerLocalIdentity?,
    private val onCaptureStarted: () -> Boolean,
    private val onCaptureFinished: () -> Unit,
    private val onProfileChanged: (SpeakerSimilarityScorer?) -> Unit,
) {
    private val store by lazy { SpeakerProfileStore(context.applicationContext) }
    private val lock = Any()
    private val generation = AtomicLong()
    private var pending: Pending? = null
    @Volatile private var capture: Job? = null
    private val modelLock = Any()
    @Volatile private var model: SherpaSpeakerModel? = null
    @Volatile private var scorer: SherpaSpeakerSimilarityScorer? = null
    private val _state = MutableStateFlow(SpeakerEnrollmentState())
    val state: StateFlow<SpeakerEnrollmentState> = _state.asStateFlow()
    private data class Pending(val claims: SpeakerConsentClaims, val publicKey: PublicKey, val generation: Long)

    suspend fun refresh() {
        if (_state.value.phase in setOf(SpeakerEnrollmentPhase.CAPTURING, SpeakerEnrollmentPhase.AWAITING_CONSENT)) return
        val refreshingGeneration = generation.get()
        try {
            val prepared = withContext(Dispatchers.IO) {
                prepareModel()
                val record = store.read()
                val binding = try { bindingProvider() }
                    catch (cancelled: CancellationException) { throw cancelled }
                    catch (_: Exception) { null }
                val native = model
                val allowed = record != null && binding != null && native != null &&
                    SpeakerEnrollmentPolicy.validateProfile(record.json, binding, native.sha256, native.dimension)
                val next = if (allowed) SherpaSpeakerSimilarityScorer(native!!, embedding(record!!.json)) {
                    // All callers must use their background evidence worker, never block the UI.
                    if (Looper.myLooper() == Looper.getMainLooper()) false
                    else runCatching {
                        runBlocking(Dispatchers.IO) {
                            withTimeout(5_000) {
                                store.read()?.revision == record!!.revision && bindingProvider() == binding &&
                                    store.read()?.revision == record.revision
                            }
                        }
                    }.getOrDefault(false)
                } else null
                Triple(record, binding, next)
            }
            withContext(Dispatchers.Main.immediate) {
                if (generation.get() != refreshingGeneration) { prepared.third?.revoke(); return@withContext }
                replaceScorer(prepared.third)
                val present = prepared.first != null
                _state.value = SpeakerEnrollmentState(
                    phase = if (prepared.third != null) SpeakerEnrollmentPhase.ENROLLED else if (model != null && prepared.second != null) SpeakerEnrollmentPhase.READY else SpeakerEnrollmentPhase.UNAVAILABLE,
                    message = if (prepared.third != null) "Your encrypted local speaker profile is ready. Speaker similarity is evidence, not permission to act."
                        else if (present) "Your profile is retained, but its current owner binding or model could not be verified. Speaker evidence is inconclusive."
                        else if (model == null) "The generic speaker model is not ready. No owner profile has been created."
                        else if (prepared.second == null) "The current paired owner binding could not be verified. No profile will be created."
                        else "Record three short clips after a dedicated biometric confirmation. Audio is kept only in memory.",
                    profilePresent = present, modelReady = model != null,
                    profileCreatedAtMs = prepared.first?.json?.optLong("created_at_ms")?.takeIf { it > 0 },
                )
            }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) {
            withContext(Dispatchers.Main.immediate) {
                if (generation.get() != refreshingGeneration) return@withContext
                replaceScorer(null)
                _state.value = _state.value.copy(phase = SpeakerEnrollmentPhase.UNAVAILABLE,
                    message = "The encrypted speaker profile or current owner binding could not be verified. No speaker evidence is being used.")
            }
        }
    }

    suspend fun prepareConsent(operation: SpeakerEnrollmentOperation): SpeakerEnrollmentConsent = withContext(Dispatchers.IO) {
        check(capture?.isActive != true) { "speaker_capture_active" }
        val attempt = generation.incrementAndGet()
        synchronized(lock) { pending = null }
        val record = store.read()
        val binding: SpeakerProfileBinding
        val modelSha: String
        if (operation == SpeakerEnrollmentOperation.REMOVE) {
            check(record != null) { "speaker_profile_absent" }
            binding = SpeakerEnrollmentPolicy.parseBinding(record.json.getJSONObject("binding")) ?: error("speaker_profile_binding_invalid")
            val local = localBindingProvider() ?: error("speaker_local_owner_identity_missing")
            check(SpeakerEnrollmentPolicy.privacyRemovalBindingMatches(binding, local)) { "speaker_local_owner_identity_changed" }
            modelSha = record.json.getString("model_sha256")
        } else {
            binding = bindingProvider() ?: error("speaker_current_owner_binding_unavailable")
            prepareModel()
            modelSha = model?.sha256 ?: error("speaker_model_unavailable")
            check(audioArbiter.hasRecordPermission()) { "speaker_microphone_permission_required" }
        }
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val certificate = keyStore.getCertificate(OwnerApprovalKeyManager.KEY_ALIAS) ?: error("speaker_existing_approval_key_required")
        check(EmbeddedVoiceAssetInstaller.sha256(certificate.publicKey.encoded) == binding.approvalFingerprint) { "speaker_approval_key_changed" }
        val key = keyStore.getKey(OwnerApprovalKeyManager.KEY_ALIAS, null) as? PrivateKey ?: error("speaker_existing_approval_key_required")
        val signature = Signature.getInstance(OwnerApprovalKeyManager.SIGNATURE_ALGORITHM).apply { initSign(key) }
        val now = System.currentTimeMillis()
        val claims = SpeakerConsentClaims(UUID.randomUUID().toString(), ByteArray(32).also(SecureRandom()::nextBytes).joinToString("") { "%02x".format(it) },
            operation, binding, modelSha, record?.revision, now, now + 30_000)
        check(SpeakerEnrollmentPolicy.validateConsent(claims, binding, modelSha, record?.revision, now)) { "speaker_consent_invalid" }
        synchronized(lock) {
            check(generation.get() == attempt) { "speaker_consent_cancelled" }
            pending = Pending(claims, certificate.publicKey, attempt)
            _state.value = _state.value.copy(phase = SpeakerEnrollmentPhase.AWAITING_CONSENT,
            message = if (operation == SpeakerEnrollmentOperation.REMOVE) "Confirm removal of this exact encrypted local profile." else "Confirm local enrollment, then say each displayed phrase. This does not approve any VAN action.",
            profilePresent = record != null, modelReady = model != null)
        }
        SpeakerEnrollmentConsent(claims.id, claims.canonical(), signature, claims.expiresAtMs)
    }

    suspend fun completeConsent(id: String, proofBase64: String) {
        val consent = synchronized(lock) {
            val value = pending ?: error("speaker_consent_absent")
            check(value.claims.id == id && value.generation == generation.get()) { "speaker_consent_changed" }
            pending = null // Consumed before verification: even a malformed reply cannot replay this ceremony.
            value
        }
        try {
            withContext(Dispatchers.IO) {
                require(proofBase64.length in 1..2048) { "speaker_consent_signature_invalid" }
                val verifier = Signature.getInstance(OwnerApprovalKeyManager.SIGNATURE_ALGORITHM).apply { initVerify(consent.publicKey); update(consent.claims.canonical().toByteArray(Charsets.UTF_8)) }
                check(verifier.verify(Base64.decode(proofBase64, Base64.NO_WRAP))) { "speaker_consent_signature_invalid" }
                verifyCurrent(consent)
            }
            if (consent.claims.operation == SpeakerEnrollmentOperation.REMOVE) {
                withContext(Dispatchers.IO) {
                    synchronized(lock) {
                        check(generation.get() == consent.generation) { "speaker_consent_cancelled" }
                        check(SpeakerEnrollmentPolicy.validateConsent(consent.claims, consent.claims.binding,
                            consent.claims.modelSha256, store.read()?.revision, System.currentTimeMillis())) {
                            "speaker_consent_expired_or_changed"
                        }
                        store.remove(consent.claims.profileRevision ?: error("speaker_profile_absent"))
                        scorer?.revoke()
                    }
                }
                withContext(Dispatchers.Main.immediate) {
                    replaceScorer(null)
                    _state.value = SpeakerEnrollmentState(phase = SpeakerEnrollmentPhase.READY, modelReady = model != null,
                        message = "The local encrypted speaker profile has been removed. Speaker evidence is inconclusive.")
                }
            } else {
                withContext(Dispatchers.Main.immediate) {
                    check(generation.get() == consent.generation) { "speaker_consent_cancelled" }
                    check(onCaptureStarted()) { "speaker_audio_owner_busy" }
                    capture = SpeakerCaptureJob.launch(scope, release = {
                        audioArbiter.stopCapture(clearPreRoll = true)
                        val released = SpeakerCaptureJob.awaitReleased(audioArbiter::hasReleasedCapture)
                        // A final read may have completed after stop; wipe it after native release.
                        if (released) audioArbiter.stopCapture(clearPreRoll = true)
                        withContext(Dispatchers.Main.immediate) {
                            runCatching(onCaptureFinished)
                            capture = null
                            if (released) scope.launch { refresh() }
                            else _state.value = _state.value.copy(phase = SpeakerEnrollmentPhase.FAILED,
                                message = "The microphone did not release in time. No wake restart is claimed; read voice readiness before another capture.")
                        }
                    }, capture = { enroll(consent) })
                }
            }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) {
            _state.value = _state.value.copy(phase = SpeakerEnrollmentPhase.FAILED,
                message = "Speaker confirmation could not be completed. Refresh the stored profile before using it. ${safeReason(failure)}")
            throw failure
        }
    }

    private suspend fun verifyCurrent(consent: Pending) {
        check(generation.get() == consent.generation) { "speaker_consent_cancelled" }
        val binding = if (consent.claims.operation == SpeakerEnrollmentOperation.ENROLL) {
            bindingProvider() ?: error("speaker_current_owner_binding_unavailable")
        } else {
            val local = localBindingProvider() ?: error("speaker_local_owner_identity_missing")
            check(SpeakerEnrollmentPolicy.privacyRemovalBindingMatches(consent.claims.binding, local)) { "speaker_local_owner_identity_changed" }
            consent.claims.binding
        }
        val record = store.read()
        check(SpeakerEnrollmentPolicy.validateConsent(consent.claims, binding, consent.claims.modelSha256, record?.revision, System.currentTimeMillis())) { "speaker_consent_expired_or_changed" }
    }

    private suspend fun enroll(consent: Pending) {
        val vectors = ArrayList<FloatArray>()
        val qualities = ArrayList<SpeakerClipQuality>()
        try {
            val native = model ?: error("speaker_model_unavailable")
            check(native.sha256 == consent.claims.modelSha256) { "speaker_model_changed" }
            for (index in PHRASES.indices) {
                _state.value = _state.value.copy(phase = SpeakerEnrollmentPhase.CAPTURING, clipIndex = index + 1, progress = 0f,
                    message = "Please say: ${PHRASES[index]}")
                val pcm = captureClip(consent.generation)
                try {
                    val quality = SpeakerEnrollmentPolicy.quality(pcm)
                    check(quality.accepted) { quality.reason ?: "speaker_clip_unusable" }
                    qualities += quality
                    vectors += withContext(Dispatchers.IO) { native.extract(pcm) }
                } finally { pcm.fill(0) }
                if (index < PHRASES.lastIndex) delay(400)
            }
            val aggregate = SpeakerEnrollmentPolicy.aggregate(vectors)
            try {
                withContext(Dispatchers.IO) {
                    verifyCurrent(consent) // Fresh remote binding and the original30s consent must still hold at commit.
                    val profile = JSONObject().put("schema_version", 1).put("binding", consent.claims.binding.toJson())
                        .put("model_sha256", native.sha256).put("embedding", JSONArray(aggregate.toList()))
                        .put("created_at_ms", System.currentTimeMillis()).put("consent_id", consent.claims.id)
                        .put("consent_sha256", EmbeddedVoiceAssetInstaller.sha256(consent.claims.canonical().toByteArray(Charsets.UTF_8)))
                        .put("clip_qualities", JSONArray(qualities.map { JSONObject().put("duration_ms", it.durationMs).put("rms", it.rms).put("peak", it.peak).put("voiced_ms", it.voicedMs) }))
                    check(SpeakerEnrollmentPolicy.validateProfile(profile, consent.claims.binding, native.sha256, native.dimension)) { "speaker_profile_invalid" }
                    synchronized(lock) {
                        check(generation.get() == consent.generation) { "speaker_consent_cancelled" }
                        check(SpeakerEnrollmentPolicy.validateConsent(consent.claims, consent.claims.binding,
                            native.sha256, store.read()?.revision, System.currentTimeMillis())) {
                            "speaker_consent_expired_or_changed"
                        }
                        store.write(profile, consent.claims.profileRevision)
                    }
                }
            } finally { aggregate.fill(0f) }
            _state.value = _state.value.copy(phase = SpeakerEnrollmentPhase.ENROLLED, profilePresent = true, progress = 1f,
                message = "The encrypted local profile was saved and read back. Speaker similarity remains evidence, not authority.")
        } catch (cancelled: CancellationException) {
            _state.value = _state.value.copy(phase = SpeakerEnrollmentPhase.READY, progress = 0f, message = "Recording stopped. Refreshing the stored profile.")
            throw cancelled
        }
        catch (failure: Exception) {
            _state.value = _state.value.copy(phase = SpeakerEnrollmentPhase.FAILED, message = "Enrollment did not produce a verified result. Refresh the stored profile before using it. ${safeReason(failure)}")
        } finally {
            vectors.forEach { it.fill(0f) }
        }
    }

    private suspend fun captureClip(attempt: Long): ByteArray {
        val bytes = ByteArray(CLIP_BYTES)
        var count = 0
        var accepting = true
        val completed = CompletableDeferred<Unit>()
        val sink: (ByteArray) -> Unit = { frame ->
            synchronized(bytes) {
                if (accepting && generation.get() == attempt && count < bytes.size) {
                    val accepted = minOf(frame.size, bytes.size - count)
                    frame.copyInto(bytes, count, 0, accepted)
                    count += accepted
                    _state.value = _state.value.copy(progress = count.toFloat() / bytes.size)
                    if (count == bytes.size) completed.complete(Unit)
                }
            }
        }
        audioArbiter.registerSink(sink) // Rolling pre-buffer is intentionally excluded from consent-bound clips.
        try {
            check(audioArbiter.start()) { "speaker_capture_unavailable" }
            withTimeout(4_500) { completed.await() }
            check(generation.get() == attempt) { "speaker_capture_cancelled" }
            return bytes
        } catch (failure: Throwable) { synchronized(bytes) { accepting = false; bytes.fill(0) }; throw failure }
        finally { synchronized(bytes) { accepting = false }; audioArbiter.unregisterSink(sink) }
    }

    fun cancelCapture() {
        synchronized(lock) { generation.incrementAndGet(); pending = null }
        capture?.cancel()
        if (_state.value.phase == SpeakerEnrollmentPhase.AWAITING_CONSENT) {
            _state.value = _state.value.copy(phase = SpeakerEnrollmentPhase.READY, message = "Speaker confirmation cancelled. The previous profile is unchanged.")
        }
    }
    private fun prepareModel() = synchronized(modelLock) {
        if (model == null) model = SherpaSpeakerModel.fromInstalled()
    }
    private fun replaceScorer(next: SherpaSpeakerSimilarityScorer?) {
        scorer?.revoke()
        scorer = next
        onProfileChanged(next)
    }
    private fun embedding(profile: JSONObject): FloatArray = profile.getJSONArray("embedding").let { values -> FloatArray(values.length()) { values.getDouble(it).toFloat() } }
    private fun safeReason(failure: Exception): String = when (failure.message) {
        "clip_clipped" -> "The recording clipped; speak farther from the microphone."
        "clip_silent", "clip_constant", "clip_insufficient_voice" -> "The clips need clear, varied speech."
        "speaker_clips_inconsistent" -> "The three clips were inconsistent."
        "speaker_consent_expired_or_changed" -> "The confirmation expired or its exact profile binding changed."
        else -> "Try a fresh confirmation when VAN is ready."
    }
    companion object {
        private const val CLIP_BYTES = 3 * 16_000 * 2
        private val PHRASES = listOf("Hey VAN, I am recording my local speaker profile.", "These clips stay on this phone and do not approve actions.", "VAN still needs my explicit approval for consequential actions.")
    }
}
