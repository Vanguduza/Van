package com.dial.van.voice

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.sin
import kotlin.math.sqrt
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.json.JSONArray
import org.json.JSONObject

/** Deterministic signal/envelope checks, without creating or claiming an owner voice profile. */
class SpeakerEnrollmentPolicyTest {
    private val binding = SpeakerProfileBinding("phone-1", "a".repeat(64), "b".repeat(64), "bound-1", "owner-1")
    private val model = "c".repeat(64)
    private val revision = "d".repeat(64)
    private val now = 1_780_000_000_000L

    private fun claims(operation: SpeakerEnrollmentOperation = SpeakerEnrollmentOperation.ENROLL, profileRevision: String? = null) =
        SpeakerConsentClaims("consent-1", "e".repeat(64), operation, binding, model, profileRevision, now, now + 30_000)

    private fun pcm(milliseconds: Int = 3_000, sample: (Int) -> Double = { sin(2 * PI * 440 * it / 16_000) * 0.15 }): ByteArray =
        ByteArray(milliseconds * 16 * 2).also { bytes ->
            for (index in 0 until bytes.size / 2) {
                val value = (sample(index) * 32_767).toInt().coerceIn(-32_768, 32_767)
                bytes[index * 2] = value.toByte()
                bytes[index * 2 + 1] = (value shr 8).toByte()
            }
        }

    private fun profile(): JSONObject = JSONObject().put("schema_version", 1).put("binding", binding.toJson())
        .put("model_sha256", model).put("embedding", JSONArray(listOf(0.6, 0.8)))
        .put("created_at_ms", now).put("consent_id", "consent-1").put("consent_sha256", "f".repeat(64))
        .put("clip_qualities", JSONArray(List(3) {
            JSONObject().put("duration_ms", 3_000).put("rms", 0.1).put("peak", 0.15).put("voiced_ms", 3_000)
        }))

    private fun validProfile(value: JSONObject): Boolean = SpeakerEnrollmentPolicy.validateProfile(value, binding, model, 2)

    @Test fun `fresh exact consent accepts only the half open thirty second window`() {
        val consent = claims()
        assertTrue(SpeakerEnrollmentPolicy.validateConsent(consent, binding, model, null, now))
        assertTrue(SpeakerEnrollmentPolicy.validateConsent(consent, binding, model, null, now + 29_999))
        assertFalse(SpeakerEnrollmentPolicy.validateConsent(consent, binding, model, null, now - 1))
        assertFalse(SpeakerEnrollmentPolicy.validateConsent(consent, binding, model, null, now + 30_000))
        assertFalse(SpeakerEnrollmentPolicy.validateConsent(consent.copy(expiresAtMs = now + 30_001), binding, model, null, now))
    }

    @Test fun `consent rejects each changed device owner hardware approval or binding`() {
        val changed = listOf(binding.copy(deviceId = "phone-2"), binding.copy(deviceFingerprint = "0".repeat(64)),
            binding.copy(approvalFingerprint = "0".repeat(64)), binding.copy(bindingId = "bound-2"), binding.copy(ownerPrincipalId = "owner-2"))
        changed.forEach { assertFalse(SpeakerEnrollmentPolicy.validateConsent(claims(), it, model, null, now)) }
        assertFalse(SpeakerEnrollmentPolicy.validateConsent(claims(), binding.copy(deviceFingerprint = "bad"), model, null, now))
    }

    @Test fun `consent binds exact model revision and removal of an existing profile`() {
        assertFalse(SpeakerEnrollmentPolicy.validateConsent(claims(), binding, "0".repeat(64), null, now))
        assertFalse(SpeakerEnrollmentPolicy.validateConsent(claims(), binding, model, revision, now))
        assertFalse(SpeakerEnrollmentPolicy.validateConsent(claims(SpeakerEnrollmentOperation.REMOVE), binding, model, null, now))
        assertTrue(SpeakerEnrollmentPolicy.validateConsent(claims(SpeakerEnrollmentOperation.REMOVE, revision), binding, model, revision, now))
        assertFalse(SpeakerEnrollmentPolicy.validateConsent(claims(profileRevision = "bad"), binding, model, "bad", now))
    }

    @Test fun `consent rejects malformed nonce IDs model digest and invalid timestamps`() {
        val invalid = listOf(claims().copy(nonce = "e".repeat(63)), claims().copy(nonce = "E".repeat(64)),
            claims().copy(id = " "), claims().copy(id = "consent\nsecret"), claims().copy(id = "x".repeat(257)),
            claims().copy(modelSha256 = "bad"), claims().copy(issuedAtMs = 0), claims().copy(expiresAtMs = now))
        invalid.forEach { assertFalse(SpeakerEnrollmentPolicy.validateConsent(it, binding, model, null, now)) }
    }

    @Test fun `canonical consent explicitly binds purpose operation exact identity and absent revision`() {
        val canonical = claims().canonical()
        assertTrue(canonical.startsWith("{\"binding\":{\"approval_fingerprint\":"))
        val json = JSONObject(canonical)
        assertEquals("van.local-speaker-profile", json.getString("purpose"))
        assertEquals(1, json.getInt("schema_version"))
        assertEquals("ENROLL", json.getString("operation"))
        assertTrue(json.has("profile_revision") && json.isNull("profile_revision"))
        assertEquals(binding.deviceFingerprint, json.getJSONObject("binding").getString("device_fingerprint"))
        assertNotEquals(canonical, claims(SpeakerEnrollmentOperation.REMOVE, revision).canonical())
        assertNotEquals(canonical, claims().copy(expiresAtMs = now + 29_999).canonical())
        assertFalse(json.has("owner_approved"))
    }

    @Test fun `offline removal compares genuine local keys without manufacturing current remote binding`() {
        val local = SpeakerLocalIdentity(binding.deviceId, binding.deviceFingerprint, binding.approvalFingerprint)
        assertTrue(SpeakerEnrollmentPolicy.privacyRemovalBindingMatches(binding, local))
        assertTrue(SpeakerEnrollmentPolicy.privacyRemovalBindingMatches(binding.copy(bindingId = "historical-binding", ownerPrincipalId = "historical-owner"), local))
        assertFalse(SpeakerEnrollmentPolicy.privacyRemovalBindingMatches(binding, local.copy(deviceId = "phone-2")))
        assertFalse(SpeakerEnrollmentPolicy.privacyRemovalBindingMatches(binding, local.copy(deviceFingerprint = "0".repeat(64))))
        assertFalse(SpeakerEnrollmentPolicy.privacyRemovalBindingMatches(binding, local.copy(approvalFingerprint = "0".repeat(64))))
        assertFalse(SpeakerEnrollmentPolicy.privacyRemovalBindingMatches(binding, local.copy(approvalFingerprint = "bad")))
    }

    @Test fun `binding parser refuses missing unknown coerced and malformed identity fields`() {
        assertEquals(binding, SpeakerEnrollmentPolicy.parseBinding(binding.toJson()))
        assertNull(SpeakerEnrollmentPolicy.parseBinding(binding.toJson().put("owner_approved", true)))
        assertNull(SpeakerEnrollmentPolicy.parseBinding(binding.toJson().also { it.remove("binding_id") }))
        assertNull(SpeakerEnrollmentPolicy.parseBinding(binding.toJson().put("device_id", 123)))
        assertNull(SpeakerEnrollmentPolicy.parseBinding(binding.toJson().put("approval_fingerprint", "bad")))
    }

    @Test fun `usable changing PCM reports real energy duration and bounded voiced frames`() {
        val result = SpeakerEnrollmentPolicy.quality(pcm())
        assertTrue(result.accepted)
        assertEquals(3_000L, result.durationMs)
        assertEquals(3_000L, result.voicedMs)
        assertTrue(abs(result.rms - 0.15 / sqrt(2.0)) < 0.001)
        assertTrue(result.peak in 0.149..0.151)
        assertNull(result.reason)
    }

    @Test fun `duration accepts exact bounds but rejects one overlong sample without rounding`() {
        assertTrue(SpeakerEnrollmentPolicy.quality(pcm(2_500)).accepted)
        assertTrue(SpeakerEnrollmentPolicy.quality(pcm(3_500)).accepted)
        assertEquals("clip_too_short", SpeakerEnrollmentPolicy.quality(pcm(2_499)).reason)
        assertEquals("clip_too_long", SpeakerEnrollmentPolicy.quality(pcm(3_500) + byteArrayOf(0, 0)).reason)
    }

    @Test fun `wrong rate and incomplete PCM samples cannot be treated as usable audio`() {
        assertEquals("unsupported_sample_rate", SpeakerEnrollmentPolicy.quality(pcm(), 48_000).reason)
        assertEquals("unsupported_sample_rate", SpeakerEnrollmentPolicy.quality(pcm(), 0).reason)
        assertEquals("pcm_format_invalid", SpeakerEnrollmentPolicy.quality(pcm() + byteArrayOf(1)).reason)
        assertEquals("clip_too_short", SpeakerEnrollmentPolicy.quality(byteArrayOf()).reason)
    }

    @Test fun `silence and a loud constant DC offset are refused independently`() {
        assertEquals("clip_silent", SpeakerEnrollmentPolicy.quality(pcm(sample = { 0.0 })).reason)
        val offset = SpeakerEnrollmentPolicy.quality(pcm(sample = { 0.2 }))
        assertEquals("clip_constant", offset.reason)
        assertEquals(0L, offset.voicedMs)
        assertFalse(offset.accepted)
    }

    @Test fun `changing frame DC cannot fake the minimum voiced interval`() {
        val result = SpeakerEnrollmentPolicy.quality(pcm(sample = { if ((it / 320) % 2 == 0) 0.2 else -0.2 }))
        assertTrue(result.rms > 0.19)
        assertEquals(0L, result.voicedMs)
        assertEquals("clip_insufficient_voice", result.reason)
    }

    @Test fun `saturated positive and negative PCM cannot produce an accepted embedding clip`() {
        val result = SpeakerEnrollmentPolicy.quality(pcm(sample = { if (it % 2 == 0) 1.0 else -1.0 }))
        assertEquals("clip_clipped", result.reason)
        assertFalse(result.accepted)
        assertTrue(result.peak > 0.99)
    }

    @Test fun `minimum usable energy interval is measured from samples not wall time`() {
        fun partial(activeFrames: Int) = pcm(sample = { if (it < activeFrames * 320) sin(2 * PI * 440 * it / 16_000) * 0.15 else 0.0 })
        val short = SpeakerEnrollmentPolicy.quality(partial(29))
        assertEquals(580L, short.voicedMs)
        assertEquals("clip_insufficient_voice", short.reason)
        val accepted = SpeakerEnrollmentPolicy.quality(partial(30))
        assertEquals(600L, accepted.voicedMs)
        assertTrue(accepted.accepted)
    }

    @Test fun `consistent observations normalize individually and produce an independent normalized result`() {
        val first = floatArrayOf(3f, 4f)
        val vector = SpeakerEnrollmentPolicy.aggregate(listOf(first, floatArrayOf(6f, 8f), floatArrayOf(0.6f, 0.8f)))
        assertTrue(abs(vector[0] - 0.6f) < 0.00001f && abs(vector[1] - 0.8f) < 0.00001f)
        assertContentEquals(floatArrayOf(3f, 4f), first)
        vector[0] = 0f
        assertEquals(3f, first[0])
    }

    @Test fun `aggregation refuses incomplete extra empty oversized and mismatched observations`() {
        val vector = floatArrayOf(1f, 0f)
        val invalid = listOf(emptyList(), listOf(vector, vector), List(4) { vector }, List(3) { floatArrayOf() },
            List(3) { FloatArray(4_097) { 1f } }, listOf(vector, floatArrayOf(1f), vector))
        invalid.forEach { assertFailsWith<IllegalArgumentException> { SpeakerEnrollmentPolicy.aggregate(it) } }
    }

    @Test fun `aggregation refuses nonfinite zero and inconsistent speaker observations`() {
        val vector = floatArrayOf(1f, 0f)
        val invalid = listOf(floatArrayOf(0f, 0f), floatArrayOf(Float.NaN, 0f), floatArrayOf(Float.POSITIVE_INFINITY, 0f),
            floatArrayOf(0f, 1f), floatArrayOf(-1f, 0f))
        invalid.forEach { assertFailsWith<IllegalArgumentException> { SpeakerEnrollmentPolicy.aggregate(listOf(vector, vector, it)) } }
    }

    @Test fun `all pairs must be consistent even if each secondary clip resembles the first`() {
        // Each outer clip is cosine .8 from the first, but their mutual cosine is .28.
        assertFailsWith<IllegalArgumentException> {
            SpeakerEnrollmentPolicy.aggregate(listOf(floatArrayOf(1f, 0f), floatArrayOf(0.8f, 0.6f), floatArrayOf(0.8f, -0.6f)))
        }
    }

    @Test fun `strict profile readback accepts normalized observations and exact consent metadata`() {
        assertTrue(validProfile(profile()))
        assertTrue(validProfile(JSONObject(profile().toString())))
        assertFalse(SpeakerEnrollmentPolicy.validateProfile(profile(), binding.copy(bindingId = "new-binding"), model, 2))
        assertFalse(SpeakerEnrollmentPolicy.validateProfile(profile(), binding, "0".repeat(64), 2))
        assertFalse(SpeakerEnrollmentPolicy.validateProfile(profile(), binding, model, 256))
    }

    @Test fun `profile refuses extra missing coerced and changed binding envelope fields`() {
        assertFalse(validProfile(profile().put("owner_approved", true)))
        assertFalse(validProfile(profile().also { it.remove("consent_sha256") }))
        assertFalse(validProfile(profile().put("schema_version", "1")))
        assertFalse(validProfile(profile().put("created_at_ms", 0)))
        assertFalse(validProfile(profile().put("created_at_ms", now.toDouble())))
        assertFalse(validProfile(profile().put("consent_id", " ")))
        assertFalse(validProfile(profile().put("consent_sha256", "bad")))
        assertFalse(validProfile(profile().put("binding", binding.toJson().put("device_fingerprint", "0".repeat(64)))))
    }

    @Test fun `profile refuses zero unnormalized string excessive or wrong sized embedding`() {
        val invalid = listOf(JSONArray(listOf(0.0, 0.0)), JSONArray(listOf(3.0, 4.0)), JSONArray(listOf("NaN", 1.0)),
            JSONArray(listOf(1e100, 0.0)), JSONArray(listOf(1.0)))
        invalid.forEach { assertFalse(validProfile(profile().put("embedding", it))) }
    }

    @Test fun `persisted signal records cannot omit or coerce accepted quality bounds`() {
        assertFalse(validProfile(profile().put("clip_qualities", JSONArray())))
        val mutations: List<(JSONObject) -> Unit> = listOf(
            { it.put("duration_ms", 2_499) }, { it.put("duration_ms", "3000") }, { it.put("voiced_ms", 580) },
            { it.put("voiced_ms", 3_001) }, { it.put("rms", 0.001) }, { it.put("rms", 0.2) },
            { it.put("peak", 1.1) }, { it.put("peak", "NaN") }, { it.put("accepted", true) }, { it.remove("voiced_ms") },
        )
        mutations.forEach { change ->
            val value = profile()
            change(value.getJSONArray("clip_qualities").getJSONObject(0))
            assertFalse(validProfile(value))
        }
    }
}
