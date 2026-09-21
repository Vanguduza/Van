package com.dial.van.voice

import android.content.Context
import java.io.File

/**
 * Admits and binds the local wake-word model bundle.
 *
 * wake_hey_van.kws is a small manifest, not a fake monolithic model. It pins every
 * sherpa-onnx model/token/keyword file by SHA-256 below app-private files/voice/.
 * pipelineOrNull() constructs two real native KWS streams; it never returns an armed
 * zero-score stub.
 */
class WakeModelLoader(
    context: Context,
    private val expectedSha256: String? = null,
) {
    private val voiceRoot = File(context.applicationContext.filesDir, VOICE_ROOT)
    private val manifestFile = File(voiceRoot, MANIFEST_NAME)

    @Volatile
    private var runtimeUnavailable: Boolean = false

    fun status(): WakeModelStatus {
        if (!manifestFile.isFile) return WakeModelPolicy.classify(null)
        if (runtimeUnavailable) {
            return WakeModelStatus(
                state = WakeModelState.UNUSABLE,
                phrase = WakeModelPolicy.PHRASE,
                sizeBytes = manifestFile.length(),
                sha256 = null,
            )
        }
        return try {
            val bundle = loadBundle()
            WakeModelStatus(
                state = WakeModelState.READY,
                phrase = WakeModelPolicy.PHRASE,
                sizeBytes = bundle.totalModelBytes,
                sha256 = bundle.manifestSha256,
            )
        } catch (_: WakeBundleDigestMismatch) {
            WakeModelStatus(
                state = WakeModelState.DIGEST_MISMATCH,
                phrase = WakeModelPolicy.PHRASE,
                sizeBytes = manifestFile.length(),
                sha256 = null,
            )
        } catch (_: Throwable) {
            WakeModelStatus(
                state = WakeModelState.UNUSABLE,
                phrase = WakeModelPolicy.PHRASE,
                sizeBytes = manifestFile.length(),
                sha256 = null,
            )
        }
    }

    /**
     * Build the production wake pipeline or fail closed.
     *
     * Native/JNI/model initialisation is part of readiness. A bundle whose checksums pass
     * but whose runtime cannot initialise is not allowed to make WakeCoordinator arm.
     */
    fun pipelineOrNull(): WakePipeline? {
        val bundle = try {
            loadBundle()
        } catch (_: Throwable) {
            return null
        }
        return try {
            SherpaWakePipelineFactory.create(bundle).also { runtimeUnavailable = false }
        } catch (_: Throwable) {
            runtimeUnavailable = true
            null
        }
    }

    private fun loadBundle(): WakeSherpaBundle =
        WakeSherpaBundle.load(
            voiceRoot = voiceRoot,
            manifestFile = manifestFile,
            expectedManifestSha256 = expectedSha256,
        )

    companion object {
        const val VOICE_ROOT = "voice"
        const val MANIFEST_NAME = "wake_hey_van.kws"
        const val MODEL_PATH = "$VOICE_ROOT/$MANIFEST_NAME"
    }
}
