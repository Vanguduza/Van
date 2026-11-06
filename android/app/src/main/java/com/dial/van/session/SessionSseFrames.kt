package com.dial.van.session

import org.json.JSONObject

/** One SSE frame becomes one existing durable downstream event, with a bounded buffer. */
object SessionSseFrames {
    class Parser {
        private val data = StringBuilder()
        fun feed(line: String): JSONObject? {
            if (line.isEmpty()) {
                if (data.isEmpty()) return null
                val value = data.toString()
                data.setLength(0)
                return JSONObject(value)
            }
            if (line.startsWith("data:")) {
                if (data.isNotEmpty()) data.append('\n')
                data.append(line.removePrefix("data:").removePrefix(" "))
                require(data.length <= 256 * 1024) { "session_stream_frame_too_large" }
            }
            return null
        }
    }
}
