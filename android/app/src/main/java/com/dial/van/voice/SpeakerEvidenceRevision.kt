package com.dial.van.voice

import java.util.concurrent.atomic.AtomicLong

/** A published numeric score cannot survive removal/replacement of the profile it measured. */
class SpeakerEvidenceRevision {
    private val revision = AtomicLong()
    fun snapshot(): Long = revision.get()
    fun changed() { revision.incrementAndGet() }
    fun admit(observedRevision: Long, score: Float?): Float? =
        score?.takeIf { revision.get() == observedRevision && it.isFinite() }?.coerceIn(0f, 1f)
}
