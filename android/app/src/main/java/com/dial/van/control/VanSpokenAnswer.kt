package com.dial.van.control

import com.dial.van.voice.SpeechSegment
import com.dial.van.voice.VoiceEdge
import java.util.UUID

/**
 * How a command's spoken outcome reaches the owner — through the Rev 1.5 §21 speech-stream
 * path ([VoiceEdge.speak]/`SpeechQueue`), not a bare `TtsOutputManager.speak` call.
 *
 * [VanCommandController] only ever calls a `(String) -> Unit` hook (so it stays constructible
 * with a plain lambda in a test, with no `VoiceEdge` in sight); this is what that hook should
 * be bound to once a [VoiceEdge] exists, which is `VanApplication`, not here. Every call
 * becomes a one-segment, final `SpeechSegment` — a spoken command outcome is one sentence
 * with nothing to interrupt it with, so segment 0 of a fresh stream is always correct.
 *
 * `VanApplication.onCreate` binds it: `speak = { text -> VanSpokenAnswer.speak(voiceEdge, text) }`.
 */
object VanSpokenAnswer {
    fun speak(voiceEdge: VoiceEdge, text: String) {
        if (text.isBlank()) return
        val streamId = UUID.randomUUID().toString()
        voiceEdge.speak(
            SpeechSegment(
                responseId = streamId,
                speechStreamId = streamId,
                segmentId = UUID.randomUUID().toString(),
                segmentIndex = 0,
                text = text,
                final = true,
            ),
            browserAudioPlaying = false,
        )
    }
}
