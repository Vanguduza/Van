package com.dial.van.voice

import com.dial.van.security.VanCanonicalJson
import org.json.JSONObject

/**
 * Rev 1.5 §21.4 — the signed voice bundle, and what VAN may claim when parts of it are missing.
 *
 * `WakeModelAsset` already classifies the wake model. This does the same job for the rest of
 * the offline voice edge — VAD, ASR, TTS and the critical phrase bank — and it exists as a
 * separate manifest because §21.4 says so and because the four capabilities fail
 * *independently*. A bundle with a working TTS voice and no ASR model is a VAN that can
 * speak and cannot hear, and that is a different sentence to the owner than "voice is
 * unavailable".
 *
 * The rule the whole file turns on: **a capability with no verified model is UNAVAILABLE
 * with a reason, never degraded silently and never assumed.** `VAN-ADOPT-OFFLINE-VOICE-
 * RUNTIME-001` is explicit that the repository builds the loader, the manifest and the
 * fail-closed classification, and cannot author a model. So the expected state of this
 * manifest today is that every capability is ABSENT, and the code says that clearly rather
 * than looking broken.
 *
 * Digests are checked, not trusted. A model file whose digest does not match what the
 * manifest declares is refused: the model decides what VAN hears, so a substituted one
 * decides what VAN hears.
 */
enum class VoiceCapability {
    LOCAL_WAKE,
    LOCAL_VAD,
    LOCAL_ASR,
    LOCAL_TTS,
    CRITICAL_PHRASES;

    /**
     * §21.5 — the phrase bank is the one capability whose absence is release-blocking on its
     * own, because the wake acknowledgement must not wait on a synthesiser.
     */
    val blocksWakeAcknowledgement: Boolean
        get() = this == CRITICAL_PHRASES
}

enum class VoiceAssetState {
    /** Verified: the file is present, plausible, and its digest matches. */
    READY,

    /** Nothing declared it. The expected state until the owner supplies a bundle. */
    NOT_DECLARED,

    /** Declared and not on disk. Different from NOT_DECLARED: something is wrong. */
    MISSING,

    /** Present, digest does not match. Never used — a substituted model is a substituted VAN. */
    DIGEST_MISMATCH,

    /** Present and implausible: a placeholder, a truncation, or an unpacked failure. */
    UNUSABLE,
}

data class VoiceAssetStatus(
    val capability: VoiceCapability,
    val state: VoiceAssetState,
    val declaredSha256: String? = null,
    val observedSha256: String? = null,
    val sizeBytes: Long? = null,
) {
    val ready: Boolean get() = state == VoiceAssetState.READY

    /**
     * One sentence the owner could read aloud. Never an enum name and never a path.
     *
     * Every non-ready sentence says two things, because the owner needs both and a first
     * version said only the second: **what it costs them**, and **why**. "Part of my voice
     * is missing from this install" tells someone whose VAN has stopped understanding them
     * that something is broken, and leaves them to work out what. The consequence comes
     * first because that is the part they are about to experience.
     */
    val sentence: String
        get() = when (state) {
            VoiceAssetState.READY -> readyConsequence
            VoiceAssetState.NOT_DECLARED -> unavailableConsequence
            VoiceAssetState.MISSING ->
                "$unavailableConsequence — part of my voice is missing from this install"
            VoiceAssetState.DIGEST_MISMATCH ->
                "$unavailableConsequence — part of my voice is not what VAN expects, " +
                    "so I am not using it"
            VoiceAssetState.UNUSABLE ->
                "$unavailableConsequence — part of my voice did not install correctly"
        }

    private val readyConsequence: String
        get() = when (capability) {
            VoiceCapability.LOCAL_WAKE -> "I can hear my name without a network"
            VoiceCapability.LOCAL_VAD -> "I can tell when you have finished speaking"
            VoiceCapability.LOCAL_ASR -> "I can understand you without a network"
            VoiceCapability.LOCAL_TTS -> "I can answer aloud without a network"
            VoiceCapability.CRITICAL_PHRASES -> "I can answer you immediately"
        }

    private val unavailableConsequence: String
        get() = when (capability) {
            VoiceCapability.LOCAL_WAKE -> "I need a network to hear my name"
            VoiceCapability.LOCAL_VAD -> "I may cut you off or wait too long when you speak"
            VoiceCapability.LOCAL_ASR -> "I need a network to understand you"
            VoiceCapability.LOCAL_TTS -> "I need a network to answer aloud"
            VoiceCapability.CRITICAL_PHRASES -> "I may not answer you straight away"
        }
}

/**
 * One file in the bundle, as the manifest declares it.
 */
data class VoiceAssetEntry(
    val capability: VoiceCapability,
    val path: String,
    val sha256: String,
    val sizeBytes: Long,
)

data class VoiceAssetBundle(
    val schema: String,
    val bundleVersion: String,
    val vocabularyRevision: String,
    val entries: List<VoiceAssetEntry>,
) {
    fun entriesFor(capability: VoiceCapability): List<VoiceAssetEntry> =
        entries.filter { it.capability == capability }
}

sealed class VoiceManifestVerdict {
    data class Accepted(val bundle: VoiceAssetBundle) : VoiceManifestVerdict()
    data class Refused(val reason: String) : VoiceManifestVerdict()
}

object VoiceAssetManifest {

    const val SCHEMA = "van-voice-assets/1"

    /** Below this a file is a placeholder rather than a model. */
    const val MIN_MODEL_BYTES = 16L * 1024L

    /** Above this it is not something a phone loads into memory for a voice turn. */
    const val MAX_MODEL_BYTES = 512L * 1024L * 1024L

    /** The manifest's own keys, by capability. */
    private val SECTIONS = mapOf(
        "wake" to VoiceCapability.LOCAL_WAKE,
        "vad" to VoiceCapability.LOCAL_VAD,
        "asr" to VoiceCapability.LOCAL_ASR,
        "tts" to VoiceCapability.LOCAL_TTS,
        "critical_phrases" to VoiceCapability.CRITICAL_PHRASES,
    )

    /**
     * Parse and check the manifest itself — not the files it names.
     *
     * Separating the two matters: a malformed manifest is a build problem and a missing file
     * is an install problem, and reporting the first as the second sends whoever is
     * diagnosing it to the wrong place.
     */
    fun parse(manifestJson: String): VoiceManifestVerdict {
        val parsed = runCatching { JSONObject(manifestJson) }.getOrNull()
            ?: return VoiceManifestVerdict.Refused("voice_manifest_malformed")
        if (parsed.optString("schema") != SCHEMA) {
            return VoiceManifestVerdict.Refused("voice_manifest_schema_unknown")
        }
        val bundleVersion = parsed.optString("bundle_version")
        if (bundleVersion.isBlank()) {
            // An unversioned bundle cannot be compared with the one already installed, so
            // there is no way to tell an upgrade from a replacement.
            return VoiceManifestVerdict.Refused("voice_manifest_unversioned")
        }

        val entries = mutableListOf<VoiceAssetEntry>()
        val files = parsed.optJSONArray("files")
        for (index in 0 until (files?.length() ?: 0)) {
            val file = files!!.getJSONObject(index)
            val section = file.optString("capability")
            val capability = SECTIONS[section]
                ?: return VoiceManifestVerdict.Refused("voice_manifest_unknown_capability:$section")
            val sha = file.optString("sha256")
            if (!sha.matches(Regex("[0-9a-fA-F]{64}"))) {
                // A file with no usable digest is a file VAN cannot verify, and an
                // unverifiable model decides what VAN hears.
                return VoiceManifestVerdict.Refused("voice_manifest_bad_digest:$section")
            }
            entries += VoiceAssetEntry(
                capability = capability,
                path = file.optString("path"),
                sha256 = sha.lowercase(),
                sizeBytes = file.optLong("size", -1L),
            )
        }

        return VoiceManifestVerdict.Accepted(
            VoiceAssetBundle(
                schema = SCHEMA,
                bundleVersion = bundleVersion,
                vocabularyRevision = parsed.optString("vocabulary_revision", ""),
                entries = entries,
            ),
        )
    }

    /**
     * The canonical bytes a bundle signature covers.
     *
     * The same rule as the connectivity manifest, and for the same reason: two JSON
     * documents can differ in whitespace and key order while meaning the same thing, and
     * signing one spelling while verifying another is a check that passes by luck.
     */
    fun canonical(manifest: JSONObject): ByteArray = VanCanonicalJson.bytes(manifest)

    /**
     * Classify one capability against what is actually on disk.
     *
     * @param observed digest and size per declared path, as read from the filesystem. A path
     *   absent from this map is a file that is not there.
     */
    fun classify(
        bundle: VoiceAssetBundle?,
        capability: VoiceCapability,
        observed: Map<String, Pair<String, Long>>,
    ): VoiceAssetStatus {
        val declared = bundle?.entriesFor(capability).orEmpty()
        if (declared.isEmpty()) {
            return VoiceAssetStatus(capability, VoiceAssetState.NOT_DECLARED)
        }
        for (entry in declared) {
            val found = observed[entry.path]
                ?: return VoiceAssetStatus(
                    capability, VoiceAssetState.MISSING, declaredSha256 = entry.sha256,
                )
            val (sha, size) = found
            if (size < MIN_MODEL_BYTES || size > MAX_MODEL_BYTES) {
                return VoiceAssetStatus(
                    capability, VoiceAssetState.UNUSABLE,
                    declaredSha256 = entry.sha256, observedSha256 = sha, sizeBytes = size,
                )
            }
            if (!sha.equals(entry.sha256, ignoreCase = true)) {
                return VoiceAssetStatus(
                    capability, VoiceAssetState.DIGEST_MISMATCH,
                    declaredSha256 = entry.sha256, observedSha256 = sha, sizeBytes = size,
                )
            }
        }
        val first = declared.first()
        return VoiceAssetStatus(
            capability, VoiceAssetState.READY,
            declaredSha256 = first.sha256,
            observedSha256 = observed[first.path]?.first,
            sizeBytes = observed[first.path]?.second,
        )
    }

    /** Every capability's state, which is what the owner surface reads. */
    fun classifyAll(
        bundle: VoiceAssetBundle?,
        observed: Map<String, Pair<String, Long>>,
    ): Map<VoiceCapability, VoiceAssetStatus> =
        VoiceCapability.entries.associateWith { classify(bundle, it, observed) }

    /**
     * §21.4 — "missing local voice assets are a release-blocking condition".
     *
     * Reported rather than enforced here, because the release gate is a build task and this
     * is a runtime classification; the one thing this must not do is decide that a build
     * with no voice assets is fine because it happens to be a debug build.
     */
    fun releaseBlockers(statuses: Map<VoiceCapability, VoiceAssetStatus>): List<VoiceCapability> =
        statuses.filterValues { !it.ready }.keys.sortedBy { it.ordinal }
}
