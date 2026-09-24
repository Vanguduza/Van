package com.dial.van.visual

import android.content.Context

/**
 * Legacy owner-art bridge retained only so old call sites compile while the authored Rive asset is
 * still external. The former PNG pose set was derived from rejected/low-resolution source material
 * and is intentionally unavailable. It must never be regenerated or selected at runtime.
 */
object VanStateArt {
    fun drawableFor(state: VanDurableState): Int? = null

    @Suppress("UNUSED_PARAMETER")
    fun artAvailable(context: Context): Boolean = false
}
