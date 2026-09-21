package com.dial.van.voice

import com.k2fsa.sherpa.onnx.KeywordSpotter
import com.k2fsa.sherpa.onnx.KeywordSpotterConfig
import com.k2fsa.sherpa.onnx.OnlineModelConfig
import com.k2fsa.sherpa.onnx.OnlineStream
import com.k2fsa.sherpa.onnx.OnlineTransducerModelConfig
import com.k2fsa.sherpa.onnx.getFeatureConfig
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Real local "Hey Van" runtime over sherpa-onnx open-vocabulary KWS.
 *
 * Two independent native streams are used: one candidate detector and one stricter phrase
 * verifier. They share immutable model files but not decoder state, so the second stage is
 * not a cached copy of the first decision. Neither stream grants owner authority.
 */
object SherpaWakePipelineFactory {
    fun create(bundle: WakeSherpaBundle): WakePipeline {
        val candidate = SherpaKeywordDetector(bundle, bundle.candidateThreshold)
        val verifier = SherpaKeywordDetector(bundle, bundle.verificationThreshold)
        return WakePipeline(
            kws = WakeWordEngine { pcm -> candidate.score(pcm) },
            verifier = WakePhraseVerifier { pcm -> verifier.score(pcm) },
        )
    }
}

private class SherpaKeywordDetector(
    private val bundle: WakeSherpaBundle,
    threshold: Float,
) {
    private val lock = Any()
    private val spotter: KeywordSpotter
    private var stream: OnlineStream

    init {
        val config = KeywordSpotterConfig(
            featConfig = getFeatureConfig(
                sampleRate = bundle.sampleRateHz,
                featureDim = bundle.featureDim,
            ),
            modelConfig = OnlineModelConfig(
                transducer = OnlineTransducerModelConfig(
                    encoder = bundle.encoder.absolutePath,
                    decoder = bundle.decoder.absolutePath,
                    joiner = bundle.joiner.absolutePath,
                ),
                tokens = bundle.tokens.absolutePath,
                numThreads = bundle.numThreads,
                debug = false,
                provider = "cpu",
                modelType = bundle.modelType,
            ),
            maxActivePaths = bundle.maxActivePaths,
            keywordsFile = bundle.keywords.absolutePath,
            keywordsScore = bundle.keywordsScore,
            keywordsThreshold = threshold,
            numTrailingBlanks = bundle.numTrailingBlanks,
        )
        spotter = KeywordSpotter(config = config)
        stream = spotter.createStream()
        check(stream.ptr != 0L) { "wake_sherpa_stream_unavailable" }
    }

    fun score(pcm16: ByteArray): Float = synchronized(lock) {
        if (pcm16.size < 2) return@synchronized 0f
        stream.acceptWaveform(pcm16ToFloat(pcm16), sampleRate = bundle.sampleRateHz)

        var decoded = 0
        var detected = false
        while (spotter.isReady(stream) && decoded < MAX_DECODE_STEPS_PER_FRAME) {
            spotter.decode(stream)
            decoded++
            val keyword = spotter.getResult(stream).keyword.trim()
            if (keyword.isNotEmpty()) {
                // The admitted keywords file contains exactly one phrase identity. Any
                // non-empty KWS result therefore means the model decoded "Hey Van".
                detected = true
                spotter.reset(stream)
                break
            }
        }
        if (detected) DETECTED_SCORE else 0f
    }

    private fun pcm16ToFloat(pcm16: ByteArray): FloatArray {
        val count = pcm16.size / 2
        val buffer = ByteBuffer.wrap(pcm16, 0, count * 2).order(ByteOrder.LITTLE_ENDIAN)
        return FloatArray(count) { buffer.short.toFloat() / 32768.0f }
    }

    companion object {
        private const val MAX_DECODE_STEPS_PER_FRAME = 64
        private const val DETECTED_SCORE = 0.99f
    }
}
