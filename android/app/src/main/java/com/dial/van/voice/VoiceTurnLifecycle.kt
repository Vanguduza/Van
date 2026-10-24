package com.dial.van.voice

/** Main-thread turn admission. Cancellation or a replacement invalidates queued ASR work. */
class VoiceTurnLifecycle {
    data class Token(val turnId: String, val generation: Long)

    private var generation = 0L
    private var active: Token? = null
    private var processing = false

    fun begin(turnId: String): Token {
        require(turnId.isNotBlank())
        return Token(turnId, ++generation).also { active = it; processing = false }
    }

    fun isCurrent(token: Token): Boolean = active == token
    fun acceptsRecognition(token: Token): Boolean = isCurrent(token) && !processing

    fun claimFinal(token: Token): Boolean {
        if (!acceptsRecognition(token)) return false
        processing = true
        return true
    }

    fun finish(token: Token): Boolean {
        if (!isCurrent(token) || !processing) return false
        active = null
        processing = false
        return true
    }

    fun cancel(): Token? = active.also { active = null; processing = false }
}
