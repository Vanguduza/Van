package com.dial.van.voice

import android.content.Context
import java.io.File
import java.security.MessageDigest

/**
 * Reads the owner-supplied wake word model off disk (P1-VOICE-001).
 *
 * Separate from [WakeModelPolicy] because the classification is the part worth testing and a
 * filesystem is not. The model lands in app-private storage — it is an owner-installed
 * artefact like the acknowledgement asset, not something bundled in the APK, because a
 * keyword spotter trained on the owner's phrase is not ours to ship.
 */
class WakeModelLoader(
    context: Context,
    private val expectedSha256: String? = null,
) {
    private val modelFile = File(context.applicationContext.filesDir, MODEL_PATH)

    fun status(): WakeModelStatus {
        if (!modelFile.isFile) return WakeModelPolicy.classify(null)
        val size = modelFile.length()
        // Digest only when a size makes it worth reading: hashing a 64MB placeholder to
        // discover it is a placeholder is work nobody needs at boot.
        val digest = if (
            expectedSha256 != null &&
            size in WakeModelPolicy.MIN_MODEL_BYTES..WakeModelPolicy.MAX_MODEL_BYTES
        ) {
            sha256()
        } else {
            null
        }
        return WakeModelPolicy.classify(size, digest, expectedSha256)
    }

    /**
     * The engines, or null when there is no usable model.
     *
     * Null rather than a stub that scores zero. A stub would make `WakePipeline` constructible
     * and `WakeCoordinator` arm, and VAN would sit there listening and never wake — which is
     * indistinguishable from the defect this closes, except that it would also report itself
     * as working.
     */
    fun pipelineOrNull(): WakePipeline? {
        if (!status().ready) return null
        // A real keyword spotter is a trained artefact this repository does not contain.
        // When one is installed, this is where it is bound; until then the honest answer is
        // that VAN cannot listen for its name, and `status()` says so in words.
        return null
    }

    private fun sha256(): String {
        val digest = MessageDigest.getInstance("SHA-256")
        modelFile.inputStream().use { input ->
            val buffer = ByteArray(1 shl 16)
            while (true) {
                val read = input.read(buffer)
                if (read <= 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    companion object {
        const val MODEL_PATH = "voice/wake_hey_van.kws"
    }
}
