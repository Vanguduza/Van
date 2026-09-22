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
        if (cues.isEmpty()) return 0 to 0f
        var current = cues.first()
        for (cue in cues) {
            if (cue.first <= elapsedMs) current = cue else break
        }
        return current.second to current.third.coerceIn(0f, 1f)
    }
}
