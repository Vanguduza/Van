package com.dial.van.voice

import org.json.JSONObject

/**
 * GAP-F-013 — the device-side mirror of `backend/van_gateway/voice/speech_cues.py`'s
 * `SegmentCueTiming`, and the pure lookup `TtsOutputManager` drives it with.
 *
 * `cues` is `(offsetMs, viseme, mouthOpen)` triples, exactly the shape the Gateway attaches
 * to a segment's `cue_timing` field. [rmsFallback] is carried rather than assumed: it is
 * always `true` today (a length estimate, not a measurement), which is the flag
 * `TtsOutputManager` reads to know these cues are a guess worth preferring real RMS over —
 * see its class doc for what "real RMS" means on this side, and what it falls back to when
 * neither is available.
 */
data class SegmentCueTiming(
    val cues: List<Triple<Int, Int, Float>>,
    val estimatedDurationMs: Int,
    val rmsFallback: Boolean = true,
) {
    companion object {
        val EMPTY = SegmentCueTiming(cues = emptyList(), estimatedDurationMs = 0)

        /** Defensive: a segment from a gateway that predates this field parses to [EMPTY]. */
        fun fromJson(json: JSONObject?): SegmentCueTiming {
            if (json == null) return EMPTY
            val array = json.optJSONArray("cues") ?: return EMPTY
            val cues = buildList {
                for (index in 0 until array.length()) {
                    val cue = array.optJSONArray(index) ?: continue
                    if (cue.length() < 3) continue
                    add(Triple(cue.optInt(0), cue.optInt(1), cue.optDouble(2, 0.0).toFloat()))
                }
            }
            return SegmentCueTiming(
                cues = cues,
                estimatedDurationMs = json.optInt("estimated_duration_ms", 0),
                rmsFallback = json.optBoolean("rms_fallback", true),
            )
        }
    }
}

/**
 * Which cue applies at [elapsedMs] into a phrase — the same walk
 * `backend/van_gateway/voice/speech_cues.py`'s `SpeechCueClock.tick` does, minus the state
 * machine (pause/interrupt/slew) `TtsOutputManager` already owns for its own lifecycle.
 * Pure, so it is exercised in `android/verification` rather than only on a device.
 */
object VanCueWalker {
    fun cueAt(cues: List<Triple<Int, Int, Float>>, elapsedMs: Long): Pair<Int, Float> {
        if (elapsedMs < 0L) return 0 to 0f
        // A future cue never becomes active before its actual offset, even when
        // an upstream packet is out of order or contains invalid numeric values.
        var current: Triple<Int, Int, Float>? = null
        var latest = -1
        for (cue in cues) {
            if (cue.first >= 0 && cue.first <= elapsedMs && cue.first >= latest) {
                current = cue
                latest = cue.first
            }
        }
        val chosen = current ?: return 0 to 0f
        val viseme = when {
            chosen.second < 0 -> 0
            chosen.second > 4 -> 1 // canonical unknown positive viseme fallback
            else -> chosen.second
        }
        val open = if (chosen.third.isFinite()) chosen.third.coerceIn(0f, 1f) else 0f
        return viseme to open
    }
}

/**
 * Android TTS onRangeStart exposes an actual spoken-text range, but no PCM.
 * This is explicitly an approximate fallback (not audio RMS or phoneme recognition),
 * used only when there is no upstream cue track or measured local PCM.
 */
object VanRangeCueEstimator {
    fun forTextRange(text: String, start: Int, end: Int): Pair<Int, Float> {
        if (start < 0 || end <= start || end > text.length) return 0 to 0f
        val segment = text.substring(start, end).lowercase(java.util.Locale.ROOT)
        val vowel = segment.firstOrNull { it in "aeiou" }
        val shape = when (vowel) {
            'e', 'i' -> 2
            'a' -> 3
            'o', 'u' -> 4
            else -> if (segment.any { it.isLetterOrDigit() }) 1 else 0
        }
        val opening = when (shape) {
            0 -> 0f
            1 -> 0.28f
            else -> 0.55f
        }
        return shape to opening
    }
}
