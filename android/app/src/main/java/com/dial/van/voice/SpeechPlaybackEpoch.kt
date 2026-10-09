package com.dial.van.voice

import java.util.concurrent.atomic.AtomicLong

/** Queued segments share an epoch; cancellation permanently invalidates their late PCM/callbacks. */
class SpeechPlaybackEpoch {
    private val generation = AtomicLong()
    fun snapshot(): Long = generation.get()
    fun isCurrent(epoch: Long): Boolean = generation.get() == epoch
    fun cancel() { generation.incrementAndGet() }
}
