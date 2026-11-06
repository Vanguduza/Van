package com.dial.van.visual

/** Aura flow has its own cadence on the EXISTING active-time clock, not the body's pose. */
object VanAuraMotionPhase {
    const val FLOW_PERIOD_NANOS = 3_600_000_000L
    const val REST_PHASE = 0.18f
    fun at(activeNanos: Long): Float =
        (activeNanos.coerceAtLeast(0L) % FLOW_PERIOD_NANOS).toFloat() / FLOW_PERIOD_NANOS.toFloat()
}
